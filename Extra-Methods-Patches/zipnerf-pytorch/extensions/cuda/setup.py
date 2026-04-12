import os
from setuptools import setup
from torch.utils.cpp_extension import BuildExtension, CUDAExtension

_src_path = os.path.dirname(os.path.abspath(__file__))

if os.name == "nt":
    nvcc_flags = [
        "-O3",
        "-std=c++17",
        "-U__CUDA_NO_HALF_OPERATORS__",
        "-U__CUDA_NO_HALF_CONVERSIONS__",
        "-U__CUDA_NO_HALF2_OPERATORS__",
    ]
    c_flags = ["/O2", "/std:c++17"]

    def find_cl_path():
        import glob

        for edition in ["Enterprise", "Professional", "BuildTools", "Community"]:
            paths = sorted(
                glob.glob(
                    rf"C:\Program Files (x86)\Microsoft Visual Studio\*\{edition}\VC\Tools\MSVC\*\bin\Hostx64\x64"
                ),
                reverse=True,
            )
            if paths:
                return paths[0]
        return None

    if os.system("where cl.exe >nul 2>nul") != 0:
        cl_path = find_cl_path()
        if cl_path is None:
            raise RuntimeError("Could not locate a supported Microsoft Visual C++ installation")
        os.environ["PATH"] += ";" + cl_path

else:
    nvcc_flags = [
        "-O3",
        "-std=c++14",
        "-U__CUDA_NO_HALF_OPERATORS__",
        "-U__CUDA_NO_HALF_CONVERSIONS__",
        "-U__CUDA_NO_HALF2_OPERATORS__",
    ]
    c_flags = ["-O3", "-std=c++14"]

setup(
    name="cuda_backend",
    ext_modules=[
        CUDAExtension(
            name="_cuda_backend",
            sources=[
                os.path.join(_src_path, "src", "gridencoder.cu"),
                os.path.join(_src_path, "src", "pdf.cu"),
                os.path.join(_src_path, "src", "bindings.cpp"),
            ],
            extra_compile_args={
                "cxx": c_flags,
                "nvcc": nvcc_flags,
            },
        ),
    ],
    cmdclass={"build_ext": BuildExtension},
)