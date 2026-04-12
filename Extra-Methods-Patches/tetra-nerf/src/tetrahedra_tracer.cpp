#include "tetrahedra_tracer.h"

#include <optix_function_table_definition.h>
#include <optix_stack_size.h>
#include <optix_stubs.h>

#include <algorithm>
#include <array>
#include <cassert>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <unordered_map>
#include <utility>
#include <vector>

#include "optix_types.h"
#include "utils/exception.h"
#include "utils/tensor.h"
#include "utils/vec_math.h"

namespace fs = std::filesystem;

namespace {

template <typename T>
struct SbtRecord {
    __align__(OPTIX_SBT_RECORD_ALIGNMENT) char header[OPTIX_SBT_RECORD_HEADER_SIZE];
    T data;
};

using RayGenSbtRecord = SbtRecord<RayGenData>;
using MissSbtRecord = SbtRecord<MissData>;
using HitGroupSbtRecord = SbtRecord<HitGroupData>;

uint3 order_faces(const uint3 &face) {
    uint3 ordered_face = face;
    if (ordered_face.x > ordered_face.y) std::swap(ordered_face.x, ordered_face.y);
    if (ordered_face.y > ordered_face.z) std::swap(ordered_face.y, ordered_face.z);
    if (ordered_face.x > ordered_face.y) std::swap(ordered_face.x, ordered_face.y);
    return ordered_face;
}

static void context_log_cb(unsigned int level, const char *tag, const char *message, void *) {
    std::cerr << "[" << std::setw(2) << level << "][" << std::setw(12) << tag << "]: " << message << "\n";
}

void create_module_from_embedded(
    const OptixDeviceContext &context,
    const std::string &input,
    const OptixModuleCompileOptions &module_compile_options,
    const OptixPipelineCompileOptions &pipeline_compile_options,
    OptixModule *module) {
    char log[2048] = {};
    size_t sizeof_log = sizeof(log);

#if (OPTIX_ABI_VERSION > 54)
    OPTIX_CHECK(optixModuleCreate(
        context,
        &module_compile_options,
        &pipeline_compile_options,
        input.c_str(),
        input.size(),
        log,
        &sizeof_log,
        module));
#else
    OPTIX_CHECK(optixModuleCreateFromPTX(
        context,
        &module_compile_options,
        &pipeline_compile_options,
        input.c_str(),
        input.size(),
        log,
        &sizeof_log,
        module));
#endif
}

OptixStackSizes collect_stack_sizes(const std::vector<OptixProgramGroup> &program_groups, OptixPipeline pipeline) {
    OptixStackSizes out = {};
    for (auto pg : program_groups) {
        OptixStackSizes ss = {};
#if (OPTIX_ABI_VERSION >= 55)
        OPTIX_CHECK(optixProgramGroupGetStackSize(pg, &ss, pipeline));
#else
        OPTIX_CHECK(optixProgramGroupGetStackSize(pg, &ss));
#endif
        out.cssRG = std::max(out.cssRG, ss.cssRG);
        out.cssMS = std::max(out.cssMS, ss.cssMS);
        out.cssCH = std::max(out.cssCH, ss.cssCH);
        out.cssAH = std::max(out.cssAH, ss.cssAH);
        out.cssIS = std::max(out.cssIS, ss.cssIS);
        out.cssCC = std::max(out.cssCC, ss.cssCC);
        out.dssDC = std::max(out.dssDC, ss.dssDC);
    }
    return out;
}

void configure_pipeline_stack(OptixPipeline pipeline, const std::vector<OptixProgramGroup> &program_groups, uint32_t max_trace_depth) {
    OptixStackSizes stack_sizes = collect_stack_sizes(program_groups, pipeline);

    uint32_t direct_callable_stack_size_from_traversal = 0;
    uint32_t direct_callable_stack_size_from_state = 0;
    uint32_t continuation_stack_size = 0;

    OPTIX_CHECK(optixUtilComputeStackSizes(
        &stack_sizes,
        max_trace_depth,
        0,  // maxCCDepth
        0,  // maxDCDepth
        &direct_callable_stack_size_from_traversal,
        &direct_callable_stack_size_from_state,
        &continuation_stack_size));

    OPTIX_CHECK(optixPipelineSetStackSize(
        pipeline,
        direct_callable_stack_size_from_traversal,
        direct_callable_stack_size_from_state,
        continuation_stack_size,
        1));
}

void destroy_sbt_records(OptixShaderBindingTable &sbt) {
    if (sbt.raygenRecord) {
        CUDA_CHECK(cudaFree(reinterpret_cast<void *>(sbt.raygenRecord)));
    }
    if (sbt.missRecordBase) {
        CUDA_CHECK(cudaFree(reinterpret_cast<void *>(sbt.missRecordBase)));
    }
    if (sbt.hitgroupRecordBase) {
        CUDA_CHECK(cudaFree(reinterpret_cast<void *>(sbt.hitgroupRecordBase)));
    }
    if (sbt.callablesRecordBase) {
        CUDA_CHECK(cudaFree(reinterpret_cast<void *>(sbt.callablesRecordBase)));
    }
    if (sbt.exceptionRecord) {
        CUDA_CHECK(cudaFree(reinterpret_cast<void *>(sbt.exceptionRecord)));
    }
    sbt = {};
}

void build_basic_sbt(
    OptixProgramGroup raygen_prog_group,
    OptixProgramGroup miss_prog_group,
    OptixProgramGroup hitgroup_prog_group,
    OptixShaderBindingTable *sbt) {
    CUdeviceptr raygen_record = 0;
    CUdeviceptr miss_record = 0;
    CUdeviceptr hitgroup_record = 0;

    const size_t raygen_record_size = sizeof(RayGenSbtRecord);
    const size_t miss_record_size = sizeof(MissSbtRecord);
    const size_t hitgroup_record_size = sizeof(HitGroupSbtRecord);

    CUDA_CHECK(cudaMalloc(reinterpret_cast<void **>(&raygen_record), raygen_record_size));
    CUDA_CHECK(cudaMalloc(reinterpret_cast<void **>(&miss_record), miss_record_size));
    CUDA_CHECK(cudaMalloc(reinterpret_cast<void **>(&hitgroup_record), hitgroup_record_size));

    RayGenSbtRecord rg_sbt = {};
    MissSbtRecord ms_sbt = {};
    HitGroupSbtRecord hg_sbt = {};

    OPTIX_CHECK(optixSbtRecordPackHeader(raygen_prog_group, &rg_sbt));
    OPTIX_CHECK(optixSbtRecordPackHeader(miss_prog_group, &ms_sbt));
    OPTIX_CHECK(optixSbtRecordPackHeader(hitgroup_prog_group, &hg_sbt));

    CUDA_CHECK(cudaMemcpy(reinterpret_cast<void *>(raygen_record), &rg_sbt, raygen_record_size, cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(reinterpret_cast<void *>(miss_record), &ms_sbt, miss_record_size, cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(reinterpret_cast<void *>(hitgroup_record), &hg_sbt, hitgroup_record_size, cudaMemcpyHostToDevice));

    sbt->raygenRecord = raygen_record;
    sbt->missRecordBase = miss_record;
    sbt->missRecordStrideInBytes = sizeof(MissSbtRecord);
    sbt->missRecordCount = 1;
    sbt->hitgroupRecordBase = hitgroup_record;
    sbt->hitgroupRecordStrideInBytes = sizeof(HitGroupSbtRecord);
    sbt->hitgroupRecordCount = 1;
}

}  // namespace

template <>
struct std::hash<uint3> {
    std::size_t operator()(const uint3 &k) const {
        using std::hash;
        return ((hash<unsigned int>()(k.x) ^ (hash<unsigned int>()(k.y) << 1)) >> 1) ^ (hash<unsigned int>()(k.z) << 1);
    }
};

void convert_tetrahedra_to_triangles(
    const size_t num_tetrahedra,
    const uint4 *tetrahedra,
    std::vector<uint3> &triangles,
    std::vector<uint2> &triangles_tetrahedra) {
    unsigned int empty = ~((unsigned int)0);
    std::unordered_map<uint3, unsigned int> known_faces;

    for (size_t i = 0; i < num_tetrahedra; ++i) {
        for (int j = 0; j < 4; ++j) {
            uint4 tetrahedron = tetrahedra[i];
            uint3 triangle = make_uint3(
                ((unsigned int *)&tetrahedron)[(j + 1) % 4],
                ((unsigned int *)&tetrahedron)[(j + 2) % 4],
                ((unsigned int *)&tetrahedron)[(j + 3) % 4]);
            auto ordered_triangle = order_faces(triangle);

            if (known_faces.find(ordered_triangle) == known_faces.end()) {
                known_faces[ordered_triangle] = static_cast<unsigned int>(triangles_tetrahedra.size());
                triangles.push_back(triangle);
                triangles_tetrahedra.push_back(make_uint2(static_cast<unsigned int>(i), empty));
            } else {
                if (triangles_tetrahedra[known_faces[ordered_triangle]].y != empty) {
                    throw std::runtime_error("A triangle is shared by more than two tetrahedra!");
                }
                triangles_tetrahedra[known_faces[ordered_triangle]].y = static_cast<unsigned int>(i);
            }
        }
    }
}

TetrahedraTracer::TetrahedraTracer(int8_t device) : device(device) {
    context = nullptr;
    CUDA_CHECK(cudaSetDevice(device));

    {
        CUDA_CHECK(cudaFree(0));
        OPTIX_CHECK(optixInit());

        OptixDeviceContextOptions options = {};
        options.logCallbackFunction = &context_log_cb;
        options.logCallbackLevel = 4;

        CUcontext cuCtx = 0;
        OPTIX_CHECK(optixDeviceContextCreate(cuCtx, &options, &context));
    }

    tetrahedra_structure = std::move(TetrahedraStructure(context, device));
    trace_rays_pipeline = std::move(TraceRaysPipeline(context, device));
    trace_rays_triangles_pipeline = std::move(TraceRaysTrianglesPipeline(context, device));
    find_tetrahedra_pipeline = std::move(FindTetrahedraPipeline(context, device));
}

TetrahedraTracer::TetrahedraTracer(TetrahedraTracer &&other) noexcept
    : device(std::exchange(other.device, -1)),
      context(std::exchange(other.context, nullptr)),
      tetrahedra_structure(std::move(other.tetrahedra_structure)),
      trace_rays_pipeline(std::move(other.trace_rays_pipeline)),
      trace_rays_triangles_pipeline(std::move(other.trace_rays_triangles_pipeline)),
      find_tetrahedra_pipeline(std::move(other.find_tetrahedra_pipeline)) {}

TetrahedraTracer::~TetrahedraTracer() noexcept(false) {
    auto moved_structure = std::move(tetrahedra_structure);
    auto moved_trace = std::move(trace_rays_pipeline);
    auto moved_trace_tri = std::move(trace_rays_triangles_pipeline);
    auto moved_find = std::move(find_tetrahedra_pipeline);
    (void)moved_structure;
    (void)moved_trace;
    (void)moved_trace_tri;
    (void)moved_find;

    if (context != nullptr && device != -1) {
        CUDA_CHECK(cudaSetDevice(device));
        OPTIX_CHECK(optixDeviceContextDestroy(std::exchange(context, nullptr)));
    }
}

TetrahedraStructure::TetrahedraStructure() noexcept
    : device(-1),
      context(nullptr),
      num_vertices(0),
      num_cells(0),
      gas_handle_(0),
      d_gas_output_buffer(0),
      tetrahedra_vertices(nullptr),
      triangle_indices_(nullptr),
      triangle_tetrahedra_(nullptr) {}

TetrahedraStructure::TetrahedraStructure(TetrahedraStructure &&other) noexcept
    : context(std::exchange(other.context, nullptr)),
      device(std::exchange(other.device, -1)),
      num_vertices(std::exchange(other.num_vertices, 0)),
      num_cells(std::exchange(other.num_cells, 0)),
      gas_handle_(std::exchange(other.gas_handle_, 0)),
      d_gas_output_buffer(std::exchange(other.d_gas_output_buffer, 0)),
      tetrahedra_vertices(std::exchange(other.tetrahedra_vertices, nullptr)),
      triangle_indices_(std::exchange(other.triangle_indices_, nullptr)),
      triangle_tetrahedra_(std::exchange(other.triangle_tetrahedra_, nullptr)) {}

void TetrahedraStructure::release() {
    bool device_set = false;

    if (d_gas_output_buffer != 0) {
        if (!device_set) {
            CUDA_CHECK(cudaSetDevice(device));
            device_set = true;
        }
        CUDA_CHECK(cudaFree(reinterpret_cast<void *>(d_gas_output_buffer)));
        d_gas_output_buffer = 0;
    }

    gas_handle_ = 0;
    tetrahedra_vertices = nullptr;

    if (triangle_indices_ != nullptr) {
        if (!device_set) {
            CUDA_CHECK(cudaSetDevice(device));
            device_set = true;
        }
        CUDA_CHECK(cudaFree(reinterpret_cast<void *>(triangle_indices_)));
        triangle_indices_ = nullptr;
    }

    if (triangle_tetrahedra_ != nullptr) {
        if (!device_set) {
            CUDA_CHECK(cudaSetDevice(device));
            device_set = true;
        }
        CUDA_CHECK(cudaFree(reinterpret_cast<void *>(triangle_tetrahedra_)));
        triangle_tetrahedra_ = nullptr;
    }
}

TetrahedraStructure::~TetrahedraStructure() noexcept(false) {
    if (device != -1) {
        release();
    }
    device = -1;
    context = nullptr;
}

void TetrahedraStructure::build(
    const size_t num_vertices,
    const size_t num_cells,
    const float3 *d_vertices,
    const uint4 *cells) {
    release();
    CUDA_CHECK(cudaSetDevice(device));

    unsigned int num_triangles = 0;
    {
        auto *h_cells = new uint4[num_cells];
        CUDA_CHECK(cudaMemcpy(
            reinterpret_cast<void *>(h_cells),
            cells,
            num_cells * sizeof(uint4),
            cudaMemcpyDeviceToHost));

        std::vector<uint3> h_triangle_indices;
        std::vector<uint2> h_triangle_tetrahedra;
        convert_tetrahedra_to_triangles(num_cells, h_cells, h_triangle_indices, h_triangle_tetrahedra);
        delete[] h_cells;

        CUDA_CHECK(cudaMalloc(reinterpret_cast<void **>(&triangle_tetrahedra_), h_triangle_tetrahedra.size() * sizeof(uint2)));
        CUDA_CHECK(cudaMemcpy(
            reinterpret_cast<void *>(triangle_tetrahedra_),
            h_triangle_tetrahedra.data(),
            h_triangle_tetrahedra.size() * sizeof(uint2),
            cudaMemcpyHostToDevice));

        CUDA_CHECK(cudaMalloc(reinterpret_cast<void **>(&triangle_indices_), h_triangle_indices.size() * sizeof(uint3)));
        CUDA_CHECK(cudaMemcpy(
            reinterpret_cast<void *>(triangle_indices_),
            h_triangle_indices.data(),
            h_triangle_indices.size() * sizeof(uint3),
            cudaMemcpyHostToDevice));

        num_triangles = static_cast<unsigned int>(h_triangle_indices.size());
    }

    OptixAccelBuildOptions accel_options = {};
    accel_options.buildFlags = OPTIX_BUILD_FLAG_NONE;
    accel_options.operation = OPTIX_BUILD_OPERATION_BUILD;

    const uint32_t triangle_input_flags[1] = {OPTIX_GEOMETRY_FLAG_NONE};

    OptixBuildInput triangle_input = {};
    triangle_input.type = OPTIX_BUILD_INPUT_TYPE_TRIANGLES;
    triangle_input.triangleArray.vertexFormat = OPTIX_VERTEX_FORMAT_FLOAT3;
    triangle_input.triangleArray.vertexBuffers = reinterpret_cast<CUdeviceptr *>(&d_vertices);
    triangle_input.triangleArray.numVertices = static_cast<uint32_t>(num_vertices);
    triangle_input.triangleArray.indexFormat = OPTIX_INDICES_FORMAT_UNSIGNED_INT3;
    triangle_input.triangleArray.indexBuffer = reinterpret_cast<CUdeviceptr>(triangle_indices_);
    triangle_input.triangleArray.numIndexTriplets = num_triangles;
    triangle_input.triangleArray.flags = triangle_input_flags;
    triangle_input.triangleArray.numSbtRecords = 1;

    OptixAccelBufferSizes gas_buffer_sizes = {};
    OPTIX_CHECK(optixAccelComputeMemoryUsage(context, &accel_options, &triangle_input, 1, &gas_buffer_sizes));

    CUdeviceptr d_temp_buffer_gas = 0;
    CUDA_CHECK(cudaMalloc(reinterpret_cast<void **>(&d_temp_buffer_gas), gas_buffer_sizes.tempSizeInBytes));
    CUDA_CHECK(cudaMalloc(reinterpret_cast<void **>(&d_gas_output_buffer), gas_buffer_sizes.outputSizeInBytes));

    OPTIX_CHECK(optixAccelBuild(
        context,
        0,
        &accel_options,
        &triangle_input,
        1,
        d_temp_buffer_gas,
        gas_buffer_sizes.tempSizeInBytes,
        d_gas_output_buffer,
        gas_buffer_sizes.outputSizeInBytes,
        &gas_handle_,
        nullptr,
        0));

    this->num_vertices = num_vertices;
    this->num_cells = num_cells;
    this->tetrahedra_vertices = d_vertices;

    CUDA_CHECK(cudaFree(reinterpret_cast<void *>(d_temp_buffer_gas)));
}

TraceRaysPipeline::TraceRaysPipeline(const OptixDeviceContext &context, int8_t device)
    : context(context), device(device) {
    CUDA_CHECK(cudaSetDevice(device));

    OptixModuleCompileOptions module_compile_options = {};
    module_compile_options.maxRegisterCount = OPTIX_COMPILE_DEFAULT_MAX_REGISTER_COUNT;
    module_compile_options.optLevel = OPTIX_COMPILE_OPTIMIZATION_DEFAULT;
#if (OPTIX_ABI_VERSION > 54)
    module_compile_options.debugLevel = OPTIX_COMPILE_DEBUG_LEVEL_MINIMAL;
#else
    module_compile_options.debugLevel = OPTIX_COMPILE_DEBUG_LEVEL_LINEINFO;
#endif

    OptixPipelineCompileOptions pipeline_compile_options = {};
    pipeline_compile_options.usesMotionBlur = false;
    pipeline_compile_options.traversableGraphFlags = OPTIX_TRAVERSABLE_GRAPH_FLAG_ALLOW_SINGLE_GAS;
    pipeline_compile_options.numPayloadValues = 1;
    pipeline_compile_options.numAttributeValues = 2;
#ifdef DEBUG
    pipeline_compile_options.exceptionFlags =
        OPTIX_EXCEPTION_FLAG_DEBUG | OPTIX_EXCEPTION_FLAG_TRACE_DEPTH | OPTIX_EXCEPTION_FLAG_STACK_OVERFLOW;
#else
    pipeline_compile_options.exceptionFlags = OPTIX_EXCEPTION_FLAG_NONE;
#endif
    pipeline_compile_options.pipelineLaunchParamsVariableName = "params";
    pipeline_compile_options.usesPrimitiveTypeFlags = OPTIX_PRIMITIVE_TYPE_FLAGS_TRIANGLE;

    const std::string input = load_ptx_data();
    create_module_from_embedded(context, input, module_compile_options, pipeline_compile_options, &module);

    {
        OptixProgramGroupOptions program_group_options = {};

        OptixProgramGroupDesc raygen_desc = {};
        raygen_desc.kind = OPTIX_PROGRAM_GROUP_KIND_RAYGEN;
        raygen_desc.raygen.module = module;
        raygen_desc.raygen.entryFunctionName = "__raygen__rg";

        OptixProgramGroupDesc miss_desc = {};
        miss_desc.kind = OPTIX_PROGRAM_GROUP_KIND_MISS;
        miss_desc.miss.module = module;
        miss_desc.miss.entryFunctionName = "__miss__ms";

        OptixProgramGroupDesc hitgroup_desc = {};
        hitgroup_desc.kind = OPTIX_PROGRAM_GROUP_KIND_HITGROUP;
        hitgroup_desc.hitgroup.moduleCH = module;
        hitgroup_desc.hitgroup.moduleAH = module;
        hitgroup_desc.hitgroup.entryFunctionNameCH = "__closesthit__ms";
        hitgroup_desc.hitgroup.entryFunctionNameAH = "__anyhit__ms";

        char log[2048] = {};
        size_t sizeof_log = sizeof(log);

        OPTIX_CHECK_LOG(optixProgramGroupCreate(context, &raygen_desc, 1, &program_group_options, log, &sizeof_log, &raygen_prog_group));

        sizeof_log = sizeof(log);
        OPTIX_CHECK_LOG(optixProgramGroupCreate(context, &miss_desc, 1, &program_group_options, log, &sizeof_log, &miss_prog_group));

        sizeof_log = sizeof(log);
        OPTIX_CHECK_LOG(optixProgramGroupCreate(context, &hitgroup_desc, 1, &program_group_options, log, &sizeof_log, &hitgroup_prog_group));
    }

    {
        const uint32_t max_trace_depth = 2;
        std::vector<OptixProgramGroup> program_groups = {raygen_prog_group, miss_prog_group, hitgroup_prog_group};

        OptixPipelineLinkOptions pipeline_link_options = {};
        pipeline_link_options.maxTraceDepth = max_trace_depth;
#if (OPTIX_ABI_VERSION <= 54)
        pipeline_link_options.debugLevel = OPTIX_COMPILE_DEBUG_LEVEL_FULL;
#endif

        char log[2048] = {};
        size_t sizeof_log = sizeof(log);
        OPTIX_CHECK_LOG(optixPipelineCreate(
            context,
            &pipeline_compile_options,
            &pipeline_link_options,
            program_groups.data(),
            static_cast<unsigned int>(program_groups.size()),
            log,
            &sizeof_log,
            &pipeline));

        configure_pipeline_stack(pipeline, program_groups, max_trace_depth);
    }

    build_basic_sbt(raygen_prog_group, miss_prog_group, hitgroup_prog_group, &sbt);

    CUDA_CHECK(cudaStreamCreate(&stream));
    CUDA_CHECK(cudaMalloc(reinterpret_cast<void **>(&d_param), sizeof(Params)));
}

TraceRaysPipeline::TraceRaysPipeline(TraceRaysPipeline &&other) noexcept
    : context(std::exchange(other.context, nullptr)),
      device(std::exchange(other.device, -1)),
      module(std::exchange(other.module, nullptr)),
      sbt(std::exchange(other.sbt, {})),
      pipeline(std::exchange(other.pipeline, nullptr)),
      d_param(std::exchange(other.d_param, 0)),
      stream(std::exchange(other.stream, nullptr)),
      raygen_prog_group(std::exchange(other.raygen_prog_group, nullptr)),
      miss_prog_group(std::exchange(other.miss_prog_group, nullptr)),
      hitgroup_prog_group(std::exchange(other.hitgroup_prog_group, nullptr)),
      eps(std::exchange(other.eps, 1e-6f)) {}

TraceRaysPipeline::~TraceRaysPipeline() noexcept(false) {
    const auto current_device = std::exchange(device, -1);
    if (current_device == -1) {
        return;
    }

    CUDA_CHECK(cudaSetDevice(current_device));

    if (d_param != 0) {
        CUDA_CHECK(cudaFree(reinterpret_cast<void *>(std::exchange(d_param, 0))));
    }

    destroy_sbt_records(sbt);

    if (stream != nullptr) {
        CUDA_CHECK(cudaStreamDestroy(std::exchange(stream, nullptr)));
    }
    if (pipeline != nullptr) {
        OPTIX_CHECK(optixPipelineDestroy(std::exchange(pipeline, nullptr)));
    }
    if (raygen_prog_group != nullptr) {
        OPTIX_CHECK(optixProgramGroupDestroy(std::exchange(raygen_prog_group, nullptr)));
    }
    if (miss_prog_group != nullptr) {
        OPTIX_CHECK(optixProgramGroupDestroy(std::exchange(miss_prog_group, nullptr)));
    }
    if (hitgroup_prog_group != nullptr) {
        OPTIX_CHECK(optixProgramGroupDestroy(std::exchange(hitgroup_prog_group, nullptr)));
    }
    if (module != nullptr) {
        OPTIX_CHECK(optixModuleDestroy(std::exchange(module, nullptr)));
    }

    context = nullptr;
}

void TraceRaysPipeline::trace_rays(
    const TetrahedraStructure *tetrahedra_structure,
    const size_t num_rays,
    const unsigned int max_ray_triangles,
    const float3 *ray_origins,
    const float3 *ray_directions,
    unsigned int *num_visited_cells_out,
    unsigned int *visited_cells_out,
    float3 *barycentric_coordinates_out,
    float2 *hit_distances_out,
    uint4 *vertex_indices_out) {
    CUDA_CHECK(cudaSetDevice(device));

    Params params = {};
    params.triangle_tetrahedra = tetrahedra_structure->triangle_tetrahedra();
    params.triangle_indices = tetrahedra_structure->triangle_indices();
    params.num_visited_tetrahedra = num_visited_cells_out;
    params.visited_tetrahedra = visited_cells_out;
    params.vertex_indices = vertex_indices_out;
    params.max_ray_triangles = max_ray_triangles;
    params.barycentric_coordinates = barycentric_coordinates_out;
    params.hit_distances = hit_distances_out;
    params.handle = tetrahedra_structure->gas_handle();
    params.ray_origins = ray_origins;
    params.ray_directions = ray_directions;

    CUDA_CHECK(cudaMemcpy(reinterpret_cast<void *>(d_param), &params, sizeof(params), cudaMemcpyHostToDevice));
    OPTIX_CHECK(optixLaunch(pipeline, stream, d_param, sizeof(params), &sbt, static_cast<unsigned int>(num_rays), 1, 1));
    CUDA_SYNC_CHECK();
    CUDA_CHECK(cudaStreamSynchronize(stream));
}

FindTetrahedraPipeline::FindTetrahedraPipeline(const OptixDeviceContext &context, int8_t device)
    : context(context), device(device) {
    CUDA_CHECK(cudaSetDevice(device));

    OptixModuleCompileOptions module_compile_options = {};
    module_compile_options.maxRegisterCount = OPTIX_COMPILE_DEFAULT_MAX_REGISTER_COUNT;
    module_compile_options.optLevel = OPTIX_COMPILE_OPTIMIZATION_DEFAULT;
#if (OPTIX_ABI_VERSION > 54)
    module_compile_options.debugLevel = OPTIX_COMPILE_DEBUG_LEVEL_MINIMAL;
#else
    module_compile_options.debugLevel = OPTIX_COMPILE_DEBUG_LEVEL_LINEINFO;
#endif

    OptixPipelineCompileOptions pipeline_compile_options = {};
    pipeline_compile_options.usesMotionBlur = false;
    pipeline_compile_options.traversableGraphFlags = OPTIX_TRAVERSABLE_GRAPH_FLAG_ALLOW_SINGLE_GAS;
    pipeline_compile_options.numPayloadValues = 4;
    pipeline_compile_options.numAttributeValues = 2;
#ifdef DEBUG
    pipeline_compile_options.exceptionFlags =
        OPTIX_EXCEPTION_FLAG_DEBUG | OPTIX_EXCEPTION_FLAG_TRACE_DEPTH | OPTIX_EXCEPTION_FLAG_STACK_OVERFLOW;
#else
    pipeline_compile_options.exceptionFlags = OPTIX_EXCEPTION_FLAG_NONE;
#endif
    pipeline_compile_options.pipelineLaunchParamsVariableName = "params";
    pipeline_compile_options.usesPrimitiveTypeFlags = OPTIX_PRIMITIVE_TYPE_FLAGS_TRIANGLE;

    const std::string input = load_ptx_data();
    create_module_from_embedded(context, input, module_compile_options, pipeline_compile_options, &module);

    {
        OptixProgramGroupOptions program_group_options = {};

        OptixProgramGroupDesc raygen_desc = {};
        raygen_desc.kind = OPTIX_PROGRAM_GROUP_KIND_RAYGEN;
        raygen_desc.raygen.module = module;
        raygen_desc.raygen.entryFunctionName = "__raygen__ft";

        OptixProgramGroupDesc miss_desc = {};
        miss_desc.kind = OPTIX_PROGRAM_GROUP_KIND_MISS;
        miss_desc.miss.module = module;
        miss_desc.miss.entryFunctionName = "__miss__ft";

        OptixProgramGroupDesc hitgroup_desc = {};
        hitgroup_desc.kind = OPTIX_PROGRAM_GROUP_KIND_HITGROUP;
        hitgroup_desc.hitgroup.moduleCH = module;
        hitgroup_desc.hitgroup.entryFunctionNameCH = "__closesthit__ft";

        char log[2048] = {};
        size_t sizeof_log = sizeof(log);

        OPTIX_CHECK_LOG(optixProgramGroupCreate(context, &raygen_desc, 1, &program_group_options, log, &sizeof_log, &raygen_prog_group));

        sizeof_log = sizeof(log);
        OPTIX_CHECK_LOG(optixProgramGroupCreate(context, &miss_desc, 1, &program_group_options, log, &sizeof_log, &miss_prog_group));

        sizeof_log = sizeof(log);
        OPTIX_CHECK_LOG(optixProgramGroupCreate(context, &hitgroup_desc, 1, &program_group_options, log, &sizeof_log, &hitgroup_prog_group));
    }

    {
        const uint32_t max_trace_depth = 1;
        std::vector<OptixProgramGroup> program_groups = {raygen_prog_group, miss_prog_group, hitgroup_prog_group};

        OptixPipelineLinkOptions pipeline_link_options = {};
        pipeline_link_options.maxTraceDepth = max_trace_depth;
#if (OPTIX_ABI_VERSION <= 54)
        pipeline_link_options.debugLevel = OPTIX_COMPILE_DEBUG_LEVEL_FULL;
#endif

        char log[2048] = {};
        size_t sizeof_log = sizeof(log);
        OPTIX_CHECK_LOG(optixPipelineCreate(
            context,
            &pipeline_compile_options,
            &pipeline_link_options,
            program_groups.data(),
            static_cast<unsigned int>(program_groups.size()),
            log,
            &sizeof_log,
            &pipeline));

        configure_pipeline_stack(pipeline, program_groups, max_trace_depth);
    }

    build_basic_sbt(raygen_prog_group, miss_prog_group, hitgroup_prog_group, &sbt);

    CUDA_CHECK(cudaStreamCreate(&stream));
    CUDA_CHECK(cudaMalloc(reinterpret_cast<void **>(&d_param), sizeof(ParamsFindTetrahedra)));
}

FindTetrahedraPipeline::FindTetrahedraPipeline(FindTetrahedraPipeline &&other) noexcept
    : context(std::exchange(other.context, nullptr)),
      device(std::exchange(other.device, -1)),
      module(std::exchange(other.module, nullptr)),
      sbt(std::exchange(other.sbt, {})),
      pipeline(std::exchange(other.pipeline, nullptr)),
      d_param(std::exchange(other.d_param, 0)),
      stream(std::exchange(other.stream, nullptr)),
      raygen_prog_group(std::exchange(other.raygen_prog_group, nullptr)),
      miss_prog_group(std::exchange(other.miss_prog_group, nullptr)),
      hitgroup_prog_group(std::exchange(other.hitgroup_prog_group, nullptr)),
      eps(std::exchange(other.eps, 1e-6f)) {}

FindTetrahedraPipeline::~FindTetrahedraPipeline() noexcept(false) {
    const auto current_device = std::exchange(device, -1);
    if (current_device == -1) {
        return;
    }

    CUDA_CHECK(cudaSetDevice(current_device));

    if (d_param != 0) {
        CUDA_CHECK(cudaFree(reinterpret_cast<void *>(std::exchange(d_param, 0))));
    }

    destroy_sbt_records(sbt);

    if (stream != nullptr) {
        CUDA_CHECK(cudaStreamDestroy(std::exchange(stream, nullptr)));
    }
    if (pipeline != nullptr) {
        OPTIX_CHECK(optixPipelineDestroy(std::exchange(pipeline, nullptr)));
    }
    if (raygen_prog_group != nullptr) {
        OPTIX_CHECK(optixProgramGroupDestroy(std::exchange(raygen_prog_group, nullptr)));
    }
    if (miss_prog_group != nullptr) {
        OPTIX_CHECK(optixProgramGroupDestroy(std::exchange(miss_prog_group, nullptr)));
    }
    if (hitgroup_prog_group != nullptr) {
        OPTIX_CHECK(optixProgramGroupDestroy(std::exchange(hitgroup_prog_group, nullptr)));
    }
    if (module != nullptr) {
        OPTIX_CHECK(optixModuleDestroy(std::exchange(module, nullptr)));
    }

    context = nullptr;
}

void FindTetrahedraPipeline::find_tetrahedra(
    const TetrahedraStructure *tetrahedra_structure,
    const size_t num_points,
    const float3 *points,
    unsigned int *tetrahedra_out,
    float3 *barycentric_coordinates_out,
    uint4 *vertex_indices_out) {
    CUDA_CHECK(cudaSetDevice(device));

    ParamsFindTetrahedra params = {};
    params.barycentric_coordinates = barycentric_coordinates_out;
    params.ray_origins = points;
    params.tetrahedra = tetrahedra_out;
    params.vertex_indices = vertex_indices_out;
    params.triangle_indices = tetrahedra_structure->triangle_indices();
    params.triangle_tetrahedra = tetrahedra_structure->triangle_tetrahedra();
    params.handle = tetrahedra_structure->gas_handle();

    CUDA_CHECK(cudaMemcpy(reinterpret_cast<void *>(d_param), &params, sizeof(params), cudaMemcpyHostToDevice));
    OPTIX_CHECK(optixLaunch(pipeline, stream, d_param, sizeof(params), &sbt, static_cast<unsigned int>(num_points), 1, 1));
    CUDA_SYNC_CHECK();
    CUDA_CHECK(cudaStreamSynchronize(stream));
}

TraceRaysTrianglesPipeline::TraceRaysTrianglesPipeline(const OptixDeviceContext &context, int8_t device)
    : context(context), device(device) {
    CUDA_CHECK(cudaSetDevice(device));

    OptixModuleCompileOptions module_compile_options = {};
    module_compile_options.maxRegisterCount = OPTIX_COMPILE_DEFAULT_MAX_REGISTER_COUNT;
    module_compile_options.optLevel = OPTIX_COMPILE_OPTIMIZATION_DEFAULT;
#if (OPTIX_ABI_VERSION > 54)
    module_compile_options.debugLevel = OPTIX_COMPILE_DEBUG_LEVEL_MINIMAL;
#else
    module_compile_options.debugLevel = OPTIX_COMPILE_DEBUG_LEVEL_LINEINFO;
#endif

    OptixPipelineCompileOptions pipeline_compile_options = {};
    pipeline_compile_options.usesMotionBlur = false;
    pipeline_compile_options.traversableGraphFlags = OPTIX_TRAVERSABLE_GRAPH_FLAG_ALLOW_SINGLE_GAS;
    pipeline_compile_options.numPayloadValues = 1;
    pipeline_compile_options.numAttributeValues = 2;
#ifdef DEBUG
    pipeline_compile_options.exceptionFlags =
        OPTIX_EXCEPTION_FLAG_DEBUG | OPTIX_EXCEPTION_FLAG_TRACE_DEPTH | OPTIX_EXCEPTION_FLAG_STACK_OVERFLOW;
#else
    pipeline_compile_options.exceptionFlags = OPTIX_EXCEPTION_FLAG_NONE;
#endif
    pipeline_compile_options.pipelineLaunchParamsVariableName = "params";
    pipeline_compile_options.usesPrimitiveTypeFlags = OPTIX_PRIMITIVE_TYPE_FLAGS_TRIANGLE;

    const std::string input = load_ptx_data();
    create_module_from_embedded(context, input, module_compile_options, pipeline_compile_options, &module);

    {
        OptixProgramGroupOptions program_group_options = {};

        OptixProgramGroupDesc raygen_desc = {};
        raygen_desc.kind = OPTIX_PROGRAM_GROUP_KIND_RAYGEN;
        raygen_desc.raygen.module = module;
        raygen_desc.raygen.entryFunctionName = "__raygen__rg";

        OptixProgramGroupDesc miss_desc = {};
        miss_desc.kind = OPTIX_PROGRAM_GROUP_KIND_MISS;
        miss_desc.miss.module = module;
        miss_desc.miss.entryFunctionName = "__miss__ms";

        OptixProgramGroupDesc hitgroup_desc = {};
        hitgroup_desc.kind = OPTIX_PROGRAM_GROUP_KIND_HITGROUP;
        hitgroup_desc.hitgroup.moduleCH = module;
        hitgroup_desc.hitgroup.moduleAH = module;
        hitgroup_desc.hitgroup.entryFunctionNameCH = "__closesthit__ms";
        hitgroup_desc.hitgroup.entryFunctionNameAH = "__anyhit__ms";

        char log[2048] = {};
        size_t sizeof_log = sizeof(log);

        OPTIX_CHECK_LOG(optixProgramGroupCreate(context, &raygen_desc, 1, &program_group_options, log, &sizeof_log, &raygen_prog_group));

        sizeof_log = sizeof(log);
        OPTIX_CHECK_LOG(optixProgramGroupCreate(context, &miss_desc, 1, &program_group_options, log, &sizeof_log, &miss_prog_group));

        sizeof_log = sizeof(log);
        OPTIX_CHECK_LOG(optixProgramGroupCreate(context, &hitgroup_desc, 1, &program_group_options, log, &sizeof_log, &hitgroup_prog_group));
    }

    {
        const uint32_t max_trace_depth = 2;
        std::vector<OptixProgramGroup> program_groups = {raygen_prog_group, miss_prog_group, hitgroup_prog_group};

        OptixPipelineLinkOptions pipeline_link_options = {};
        pipeline_link_options.maxTraceDepth = max_trace_depth;
#if (OPTIX_ABI_VERSION <= 54)
        pipeline_link_options.debugLevel = OPTIX_COMPILE_DEBUG_LEVEL_FULL;
#endif

        char log[2048] = {};
        size_t sizeof_log = sizeof(log);
        OPTIX_CHECK_LOG(optixPipelineCreate(
            context,
            &pipeline_compile_options,
            &pipeline_link_options,
            program_groups.data(),
            static_cast<unsigned int>(program_groups.size()),
            log,
            &sizeof_log,
            &pipeline));

        configure_pipeline_stack(pipeline, program_groups, max_trace_depth);
    }

    build_basic_sbt(raygen_prog_group, miss_prog_group, hitgroup_prog_group, &sbt);

    CUDA_CHECK(cudaStreamCreate(&stream));
    CUDA_CHECK(cudaMalloc(reinterpret_cast<void **>(&d_param), sizeof(ParamsTraceRaysTriangles)));
}

TraceRaysTrianglesPipeline::TraceRaysTrianglesPipeline(TraceRaysTrianglesPipeline &&other) noexcept
    : context(std::exchange(other.context, nullptr)),
      device(std::exchange(other.device, -1)),
      module(std::exchange(other.module, nullptr)),
      sbt(std::exchange(other.sbt, {})),
      pipeline(std::exchange(other.pipeline, nullptr)),
      d_param(std::exchange(other.d_param, 0)),
      stream(std::exchange(other.stream, nullptr)),
      raygen_prog_group(std::exchange(other.raygen_prog_group, nullptr)),
      miss_prog_group(std::exchange(other.miss_prog_group, nullptr)),
      hitgroup_prog_group(std::exchange(other.hitgroup_prog_group, nullptr)) {}

TraceRaysTrianglesPipeline::~TraceRaysTrianglesPipeline() noexcept(false) {
    const auto current_device = std::exchange(device, -1);
    if (current_device == -1) {
        return;
    }

    CUDA_CHECK(cudaSetDevice(current_device));

    if (d_param != 0) {
        CUDA_CHECK(cudaFree(reinterpret_cast<void *>(std::exchange(d_param, 0))));
    }

    destroy_sbt_records(sbt);

    if (stream != nullptr) {
        CUDA_CHECK(cudaStreamDestroy(std::exchange(stream, nullptr)));
    }
    if (pipeline != nullptr) {
        OPTIX_CHECK(optixPipelineDestroy(std::exchange(pipeline, nullptr)));
    }
    if (raygen_prog_group != nullptr) {
        OPTIX_CHECK(optixProgramGroupDestroy(std::exchange(raygen_prog_group, nullptr)));
    }
    if (miss_prog_group != nullptr) {
        OPTIX_CHECK(optixProgramGroupDestroy(std::exchange(miss_prog_group, nullptr)));
    }
    if (hitgroup_prog_group != nullptr) {
        OPTIX_CHECK(optixProgramGroupDestroy(std::exchange(hitgroup_prog_group, nullptr)));
    }
    if (module != nullptr) {
        OPTIX_CHECK(optixModuleDestroy(std::exchange(module, nullptr)));
    }

    context = nullptr;
}

void TraceRaysTrianglesPipeline::trace_rays(
    const TetrahedraStructure *tetrahedra_structure,
    const size_t num_rays,
    const unsigned int max_ray_triangles,
    const float3 *ray_origins,
    const float3 *ray_directions,
    unsigned int *num_visited_triangles_out,
    unsigned int *visited_triangles_out,
    float2 *barycentric_coordinates_out,
    float *hit_distances_out,
    uint3 *vertex_indices_out) {
    CUDA_CHECK(cudaSetDevice(device));

    ParamsTraceRaysTriangles params = {};
    params.triangle_tetrahedra = tetrahedra_structure->triangle_tetrahedra();
    params.triangle_indices = tetrahedra_structure->triangle_indices();
    params.num_visited_triangles = num_visited_triangles_out;
    params.visited_triangles = visited_triangles_out;
    params.vertex_indices = vertex_indices_out;
    params.max_ray_triangles = max_ray_triangles;
    params.barycentric_coordinates = barycentric_coordinates_out;
    params.hit_distances = hit_distances_out;
    params.handle = tetrahedra_structure->gas_handle();
    params.ray_origins = ray_origins;
    params.ray_directions = ray_directions;

    CUDA_CHECK(cudaMemcpy(reinterpret_cast<void *>(d_param), &params, sizeof(params), cudaMemcpyHostToDevice));
    OPTIX_CHECK(optixLaunch(pipeline, stream, d_param, sizeof(params), &sbt, static_cast<unsigned int>(num_rays), 1, 1));
    CUDA_SYNC_CHECK();
    CUDA_CHECK(cudaStreamSynchronize(stream));
}