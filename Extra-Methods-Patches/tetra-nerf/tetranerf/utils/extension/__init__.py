import os
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent


def _existing_dir(*candidates):
    for c in candidates:
        if not c:
            continue
        p = Path(str(c))
        if p.exists() and p.is_dir():
            return p
    return None


def _add_dll_dir(path):
    if not path:
        return
    try:
        os.add_dll_directory(str(path))
    except Exception:
        pass


def _prepend_path(path):
    if not path:
        return
    p = str(path)
    old = os.environ.get("PATH", "")
    parts = old.split(os.pathsep) if old else []
    norm_p = os.path.normcase(os.path.normpath(p))
    normalized = [os.path.normcase(os.path.normpath(x)) for x in parts if x]
    if norm_p not in normalized:
        os.environ["PATH"] = p + (os.pathsep + old if old else "")


def _register_runtime_dir(path):
    if not path:
        return
    _add_dll_dir(path)
    _prepend_path(path)


def _candidate_vcpkg_bins():
    candidates = []

    vcpkg_root = os.environ.get("VCPKG_ROOT")
    if vcpkg_root:
        candidates.append(Path(vcpkg_root) / "installed" / "x64-windows" / "bin")
        candidates.append(Path(vcpkg_root) / "installed" / "x64-windows" / "debug" / "bin")

    candidates.append(Path("C:/vcpkg/installed/x64-windows/bin"))
    candidates.append(Path("C:/vcpkg/installed/x64-windows/debug/bin"))

    return candidates


def _setup_windows_runtime():
    if os.name != "nt":
        return

    conda_prefix = os.environ.get("CONDA_PREFIX")
    if conda_prefix:
        _register_runtime_dir(Path(conda_prefix) / "Library" / "bin")
        _register_runtime_dir(Path(conda_prefix) / "DLLs")
        _register_runtime_dir(Path(conda_prefix) / "Lib" / "site-packages" / "torch" / "lib")

    try:
        import torch
        torch_dir = Path(torch.__file__).resolve().parent
        _register_runtime_dir(torch_dir / "lib")
    except Exception:
        pass

    cuda_root = _existing_dir(
        os.environ.get("CUDAToolkit_ROOT"),
        os.environ.get("CUDA_HOME"),
        os.environ.get("CUDA_PATH"),
        r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v11.8",
    )
    if cuda_root:
        _register_runtime_dir(cuda_root / "bin")
        _register_runtime_dir(cuda_root / "libnvvp")

    optix_root = _existing_dir(
        os.environ.get("OPTIX_ROOT_DIR"),
        os.environ.get("OPTIX_INSTALL_DIR"),
        os.environ.get("OptiX_ROOT_DIR"),
        os.environ.get("OptiX_INSTALL_DIR"),
        r"C:\Program Files\NVIDIA Corporation\OptiX SDK 9.1.0",
    )
    if optix_root:
        _register_runtime_dir(optix_root / "bin")

    for p in _candidate_vcpkg_bins():
        if p.exists():
            _register_runtime_dir(p)

    _register_runtime_dir(_THIS_DIR)


_setup_windows_runtime()

import torch

try:
    from . import tetranerf_cpp_extension as cpp
except Exception as err:
    print("\033[91;1mERROR: Tetra-NeRF could not load the cpp extension.\033[0m")
    print(f"REAL ERROR: {err}")

    class LazyError:
        class LazyErrorObj:
            def __call__(self, *args, **kwargs):
                raise RuntimeError(
                    "ERROR: Tetra-NeRF could not load cpp extension. Please build the project first."
                ) from err

            def __getattribute__(self, name: str):
                raise RuntimeError(
                    "ERROR: Tetra-NeRF could not load cpp extension. Please build the project first."
                ) from err

        def __getattribute__(self, name: str):
            return LazyError.LazyErrorObj()

    cpp = LazyError()

TetrahedraTracer = cpp.TetrahedraTracer
triangulate = cpp.triangulate
gather_uint32 = cpp.gather_uint32
scatter_ema_uint32_ = cpp.scatter_ema_uint32


class _InterpolateValuesFunction(torch.autograd.Function):
    @staticmethod
    def forward(ctx, vertex_indices, barycentric_coordinates, field):
        output = cpp.interpolate_values(vertex_indices, barycentric_coordinates, field)
        ctx.save_for_backward(vertex_indices, barycentric_coordinates, field)
        return output

    @staticmethod
    def backward(ctx, grad_out):
        vertex_indices, barycentric_coordinates, field = ctx.saved_tensors
        grad_field = cpp.interpolate_values_backward(
            vertex_indices, barycentric_coordinates, field, grad_out.contiguous()
        )
        return None, None, grad_field


class _BarycentricsGradFunction(torch.autograd.Function):
    @staticmethod
    def forward(ctx, barycentrics, vertices, points):
        ctx.save_for_backward(barycentrics, vertices)
        return barycentrics

    @staticmethod
    def backward(ctx, grad_barycentrics):
        barycentrics, vertices = ctx.saved_tensors
        grad_vertices = None
        grad_points = None
        if ctx.needs_input_grad[1] or ctx.needs_input_grad[2]:
            t_mat = (vertices[..., 1:, :] - vertices[..., :1, :])
            m_vec = torch.linalg.solve(t_mat, grad_barycentrics)
            full_barycentrics = torch.cat(
                [1.0 - barycentrics.sum(-1, keepdim=True), barycentrics], -1
            )
        if ctx.needs_input_grad[1]:
            grad_vertices = (full_barycentrics.unsqueeze(-1) * m_vec.unsqueeze(-2)).mul_(-1.0)
        if ctx.needs_input_grad[2]:
            grad_points = m_vec
        return grad_barycentrics, grad_vertices, grad_points


def add_barycentrics_grad(barycentrics, vertices, points):
    return _BarycentricsGradFunction.apply(barycentrics, vertices, points)


def interpolate_values(vertex_indices, barycentric_coordinates, field):
    return _InterpolateValuesFunction.apply(vertex_indices, barycentric_coordinates, field)