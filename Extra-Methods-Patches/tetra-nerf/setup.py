from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from setuptools import Extension, setup, find_packages
from setuptools.command.build_ext import build_ext


ROOT = Path(__file__).resolve().parent
PKG_NAME = "tetra-nerf"
VERSION = "0.1.1"

VANILLA_CUDA_VERSION = "11.8"
VANILLA_MSVC_TOOLSET = "14.38.33130"
VANILLA_MSVC_MAJOR = "v143"


def _norm(p: str | Path | None) -> str:
    if not p:
        return ""
    return os.path.normpath(str(p))


def _cmake_path(p: str | Path | None) -> str:
    return _norm(p).replace("\\", "/")


def _existing_dir(*candidates: str | Path | None) -> str:
    for c in candidates:
        if not c:
            continue
        p = Path(str(c))
        if p.exists() and p.is_dir():
            return _norm(p)
    return ""


def _existing_file(*candidates: str | Path | None) -> str:
    for c in candidates:
        if not c:
            continue
        p = Path(str(c))
        if p.exists() and p.is_file():
            return _norm(p)
    return ""


def _safe_env_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name, "").strip().lower()
    if not v:
        return default
    return v in {"1", "true", "yes", "on"}


def _print_info(label: str, value: object) -> None:
    print(f"[INFO] {label} = {value}")


def _dedupe_paths(parts: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        if not p:
            continue
        pn = _norm(p)
        key = pn.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(pn)
    return out


def _remove_env_keys_casefold(env: dict[str, str], *keys: str) -> None:
    wanted = {k.casefold() for k in keys}
    to_del = [k for k in list(env.keys()) if k.casefold() in wanted]
    for k in to_del:
        env.pop(k, None)


def _clean_cuda_path_entries(old_parts: list[str], selected_cuda_root: str, cuda_mode: str) -> list[str]:
    selected_cuda_root_norm = _norm(selected_cuda_root).lower()
    out: list[str] = []

    for p in old_parts:
        pn = _norm(p)
        if not pn:
            continue
        low = pn.lower()

        # in vanilla, keep only the selected CUDA tree
        if "nvidia gpu computing toolkit" in low and "\\cuda\\" in low:
            if cuda_mode == "vanilla":
                if not low.startswith(selected_cuda_root_norm):
                    continue

        # purge ROCm/HIP noise that breaks torch cpp_extension on Windows
        if any(token in low for token in [
            "\\rocm\\",
            "\\hip\\",
            "amd\\rocm",
            "rocm\\bin",
            "hip\\bin",
        ]):
            continue

        out.append(pn)

    return _dedupe_paths(out)


def _discover_cuda_mode() -> str:
    mode = os.environ.get("NS_CUDA_MODE", "").strip().lower()
    if mode in {"vanilla", "experimental-env"}:
        return mode
    return "vanilla"


def _vanilla_cuda_root_candidate() -> Path:
    return Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "NVIDIA GPU Computing Toolkit" / "CUDA" / f"v{VANILLA_CUDA_VERSION}"


def _discover_cuda_root(cuda_mode: str) -> str:
    vanilla_candidates = [
        _vanilla_cuda_root_candidate(),
        os.environ.get("CUDAToolkit_ROOT"),
        os.environ.get("CUDA_HOME"),
        os.environ.get("CUDA_PATH"),
    ]

    experimental_candidates = [
        os.environ.get("CUDAToolkit_ROOT"),
        os.environ.get("CUDA_HOME"),
        os.environ.get("CUDA_PATH"),
        _vanilla_cuda_root_candidate(),
    ]

    candidates = vanilla_candidates if cuda_mode == "vanilla" else experimental_candidates
    cuda_root = _existing_dir(*candidates)
    if not cuda_root:
        raise RuntimeError("CUDA toolkit root not found.")
    return cuda_root


def _discover_nvcc(cuda_root: str, cuda_mode: str) -> str:
    root_nvcc = Path(cuda_root) / "bin" / "nvcc.exe"
    if root_nvcc.exists():
        return _norm(root_nvcc)

    if cuda_mode == "experimental-env":
        nvcc = shutil.which("nvcc.exe") or shutil.which("nvcc")
        if nvcc:
            return _norm(nvcc)

    raise RuntimeError("nvcc not found under selected CUDA toolkit.")


def _discover_optix_root() -> str:
    candidates = [
        os.environ.get("OPTIX_ROOT_DIR"),
        os.environ.get("OPTIX_INSTALL_DIR"),
        os.environ.get("OPTIX_PATH"),
        os.environ.get("OPTIX_HOME"),
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "NVIDIA Corporation" / "OptiX SDK 9.1.0",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "NVIDIA Corporation" / "OptiX SDK 9.0.0",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "NVIDIA Corporation" / "OptiX SDK 8.1.0",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "NVIDIA Corporation" / "OptiX SDK 8.0.0",
    ]
    return _existing_dir(*candidates)


def _discover_optix_include(optix_root: str) -> str:
    candidates = [
        os.environ.get("OPTIX_INCLUDE_DIR"),
    ]
    if optix_root:
        candidates.insert(0, str(Path(optix_root) / "include"))
        candidates.insert(1, optix_root)

    include_dir = _existing_dir(*candidates)
    if include_dir and (Path(include_dir) / "optix.h").exists():
        return include_dir
    return ""


def _torch_cmake_prefixes() -> list[str]:
    prefixes: list[str] = []

    conda_prefix = os.environ.get("CONDA_PREFIX", "")
    if conda_prefix:
        prefixes.append(_norm(Path(conda_prefix)))
        prefixes.append(_norm(Path(conda_prefix) / "Library"))
        prefixes.append(_norm(Path(conda_prefix) / "Lib"))
        prefixes.append(_norm(Path(conda_prefix) / "lib" / "site-packages"))

    try:
        import torch  # type: ignore

        torch_dir = Path(torch.__file__).resolve().parent
        prefixes.append(_norm(torch_dir))
        prefixes.append(_norm(torch_dir.parent))
    except Exception:
        pass

    return _dedupe_paths(prefixes)


def _discover_generator() -> str:
    return os.environ.get("CMAKE_GENERATOR", "Visual Studio 17 2022").strip() or "Visual Studio 17 2022"


def _discover_toolset() -> str:
    explicit = os.environ.get("CMAKE_GENERATOR_TOOLSET", "").strip()
    if explicit:
        return explicit
    return ""


def _default_vanilla_toolset(cuda_root: str) -> str:
    return f"{VANILLA_MSVC_MAJOR},version={VANILLA_MSVC_TOOLSET},cuda={cuda_root}"


def _detect_build_type() -> str:
    return "Debug" if os.environ.get("DEBUG", "0") == "1" else "Release"


def _find_cl_from_env() -> str:
    vctools = _norm(os.environ.get("VCToolsInstallDir"))
    if vctools:
        candidate = Path(vctools) / "bin" / "Hostx64" / "x64" / "cl.exe"
        if candidate.exists():
            return _norm(candidate)

    candidates = [
        os.environ.get("CMAKE_CXX_COMPILER"),
        os.environ.get("CXX"),
        os.environ.get("CC"),
        shutil.which("cl.exe"),
    ]
    return _existing_file(*candidates)


def _read_vcvars_paths() -> tuple[str, str]:
    vctools = _norm(os.environ.get("VCToolsInstallDir"))
    vcinst = _norm(os.environ.get("VCINSTALLDIR"))
    return vctools, vcinst


def _ensure_clean_toolset_cache(build_temp: Path, desired_toolset: str) -> None:
    cache_file = build_temp / "CMakeCache.txt"
    if not cache_file.exists():
        return

    try:
        text = cache_file.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        text = ""

    old_toolset = ""
    for line in text.splitlines():
        if line.startswith("CMAKE_GENERATOR_TOOLSET:INTERNAL=") or line.startswith("CMAKE_GENERATOR_TOOLSET:STRING="):
            old_toolset = line.split("=", 1)[1].strip()
            break

    if old_toolset and desired_toolset and old_toolset != desired_toolset:
        print(f"[FIX] Removing stale CMake cache because toolset changed:")
        print(f"[FIX]   old = {old_toolset}")
        print(f"[FIX]   new = {desired_toolset}")
        shutil.rmtree(build_temp, ignore_errors=True)
        build_temp.mkdir(parents=True, exist_ok=True)


class CMakeExtension(Extension):
    def __init__(self, name: str, sourcedir: str = "") -> None:
        super().__init__(name, sources=[])
        self.sourcedir = _norm(Path(sourcedir or ".").resolve())


class CMakeBuild(build_ext):
    def run(self) -> None:
        try:
            subprocess.run(["cmake", "--version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception as exc:
            raise RuntimeError("CMake is required to build tetra-nerf") from exc

        for ext in self.extensions:
            self.build_extension(ext)

    def build_extension(self, ext: CMakeExtension) -> None:
        source_dir = Path(ext.sourcedir).resolve()
        cfg = _detect_build_type()

        build_root = Path(self.build_temp or (ROOT / "build" / "cmake")).resolve()
        build_temp = build_root if build_root.name.lower() == cfg.lower() else (build_root / cfg)
        build_temp.mkdir(parents=True, exist_ok=True)

        python_exe = _norm(sys.executable)
        cuda_mode = _discover_cuda_mode()

        cuda_root = _discover_cuda_root(cuda_mode)
        nvcc = _discover_nvcc(cuda_root, cuda_mode)
        optix_root = _discover_optix_root()
        optix_include = _discover_optix_include(optix_root)

        generator = _discover_generator()
        base_toolset = _discover_toolset()
        prefixes = _torch_cmake_prefixes()
        cmake_prefix_path = ";".join(prefixes)

        extdir = Path(self.get_ext_fullpath(ext.name)).resolve().parent
        extdir.mkdir(parents=True, exist_ok=True)

        if not optix_include:
            raise RuntimeError("OptiX headers not found. Set OPTIX_ROOT_DIR or OPTIX_INCLUDE_DIR correctly.")

        cl_path = _find_cl_from_env()
        vctools_install_dir, vcinstalldir = _read_vcvars_paths()

        if not cl_path:
            raise RuntimeError(
                "cl.exe not found in environment. Run this build from a vcvars-initialized shell or through ns-installer bootstrap."
            )

        toolset = base_toolset
        if "Visual Studio" in generator:
            if not toolset and cuda_mode == "vanilla":
                toolset = _default_vanilla_toolset(cuda_root)
            elif toolset and "cuda=" not in toolset.lower():
                toolset = f"{toolset},cuda={cuda_root}"
            elif not toolset and cuda_root:
                toolset = f"cuda={cuda_root}"

        _ensure_clean_toolset_cache(build_temp, toolset)

        _print_info("source_dir", source_dir)
        _print_info("build_temp", build_temp)
        _print_info("cfg", cfg)
        _print_info("python_executable", python_exe)
        _print_info("cuda_mode", cuda_mode)
        _print_info("generator", generator)
        _print_info("toolset", toolset or "<default>")
        _print_info("cl_path", cl_path or "<not found>")
        _print_info("VCToolsInstallDir", vctools_install_dir or "<unset>")
        _print_info("VCINSTALLDIR", vcinstalldir or "<unset>")
        _print_info("cuda_root", cuda_root or "<not found>")
        _print_info("nvcc", nvcc or "<not found>")
        _print_info("optix_root", optix_root or "<not found>")
        _print_info("optix_include", optix_include or "<not found>")
        _print_info("cmake_prefix_path", cmake_prefix_path or "<empty>")

        cmake_args = [
            "-S", _cmake_path(source_dir),
            "-B", _cmake_path(build_temp),
            f"-DPYTHON_EXECUTABLE={_cmake_path(python_exe)}",
            f"-DCMAKE_BUILD_TYPE={cfg}",
            f"-DEXAMPLE_VERSION_INFO={VERSION}",
            f"-DCMAKE_LIBRARY_OUTPUT_DIRECTORY={_cmake_path(extdir)}",
            f"-DCMAKE_RUNTIME_OUTPUT_DIRECTORY={_cmake_path(extdir)}",
            f"-DCMAKE_LIBRARY_OUTPUT_DIRECTORY_RELEASE={_cmake_path(extdir)}",
            f"-DCMAKE_RUNTIME_OUTPUT_DIRECTORY_RELEASE={_cmake_path(extdir)}",
            f"-DCMAKE_LIBRARY_OUTPUT_DIRECTORY_DEBUG={_cmake_path(extdir)}",
            f"-DCMAKE_RUNTIME_OUTPUT_DIRECTORY_DEBUG={_cmake_path(extdir)}",
            f"-DCUDAToolkit_ROOT={_cmake_path(cuda_root)}",
            f"-DCUDA_TOOLKIT_ROOT_DIR={_cmake_path(cuda_root)}",
            f"-DCMAKE_CUDA_COMPILER={_cmake_path(nvcc)}",
            f"-DCMAKE_C_COMPILER={_cmake_path(cl_path)}",
            f"-DCMAKE_CXX_COMPILER={_cmake_path(cl_path)}",
            f"-DOPTIX_ROOT_DIR={_cmake_path(optix_root)}",
            f"-DOPTIX_INSTALL_DIR={_cmake_path(optix_root)}",
            f"-DOPTIX_INCLUDE_DIR={_cmake_path(optix_include)}",
        ]

        if cmake_prefix_path:
            parts = [_cmake_path(p) for p in cmake_prefix_path.split(";") if p]
            cmake_args.append(f"-DCMAKE_PREFIX_PATH={';'.join(parts)}")

        if generator:
            cmake_args.extend(["-G", generator])

        if "Visual Studio" in generator:
            cmake_args.extend(["-A", "x64"])
            if toolset:
                cmake_args.extend(["-T", toolset])

        if _safe_env_bool("NS_FORCE_CUDA_11_8", default=(cuda_mode == "vanilla")):
            cmake_args.append("-DNS_FORCE_CUDA_11_8=ON")

        build_args = [
            "--build",
            _cmake_path(build_temp),
            "--config",
            cfg,
        ]

        max_jobs = (
            os.environ.get("CMAKE_BUILD_PARALLEL_LEVEL", "").strip()
            or os.environ.get("MAX_JOBS", "").strip()
        )
        if max_jobs:
            build_args.extend(["--parallel", max_jobs])

        env = os.environ.copy()

        # remove duplicate keys that break MSBuild on Windows
        _remove_env_keys_casefold(
            env,
            "VCToolsInstallDir",
            "VCINSTALLDIR",
            "CUDA_PATH",
            "CUDA_HOME",
            "CUDAToolkit_ROOT",
            "CUDA_TOOLKIT_ROOT_DIR",
            "CUDACXX",
            "CC",
            "CXX",
            "OPTIX_ROOT_DIR",
            "OPTIX_INSTALL_DIR",
            "OPTIX_INCLUDE_DIR",
            "ROCM_HOME",
            "ROCM_PATH",
            "HIP_HOME",
            "HIP_PATH",
            "HIP_ROOT_DIR",
            "HSA_PATH",
            "MIOPEN_PATH",
            "HIP_PLATFORM",
            "HIP_COMPILER",
            "HCC_AMDGPU_TARGET",
            "PYTORCH_ROCM_ARCH",
            "HCC_HOME",
            "HIP_PATH_57",
            "HIP_DEVICE_LIB_PATH",
        )

        if vctools_install_dir:
            env["VCToolsInstallDir"] = vctools_install_dir
        if vcinstalldir:
            env["VCINSTALLDIR"] = vcinstalldir

        env["CUDA_PATH"] = cuda_root
        env["CUDA_HOME"] = cuda_root
        env["CUDAToolkit_ROOT"] = cuda_root
        env["CUDA_TOOLKIT_ROOT_DIR"] = cuda_root
        env["CUDACXX"] = nvcc

        env["CC"] = cl_path
        env["CXX"] = cl_path

        if optix_root:
            env["OPTIX_ROOT_DIR"] = optix_root
            env["OPTIX_INSTALL_DIR"] = optix_root
        if optix_include:
            env["OPTIX_INCLUDE_DIR"] = optix_include

        cuda_bin = _norm(Path(cuda_root) / "bin")
        cuda_libnvvp = _norm(Path(cuda_root) / "libnvvp")
        cl_dir = _norm(Path(cl_path).parent)

        old_path_parts = env.get("PATH", "").split(os.pathsep)
        filtered = _clean_cuda_path_entries(old_path_parts, cuda_root, cuda_mode)
        env["PATH"] = os.pathsep.join(_dedupe_paths([cl_dir, cuda_bin, cuda_libnvvp] + filtered))

        subprocess.run(["cmake", *cmake_args], cwd=str(source_dir), env=env, check=True)
        subprocess.run(["cmake", *build_args], cwd=str(source_dir), env=env, check=True)

        # Try to locate the built extension and copy it into the Python package.
        built_candidates = [
            build_temp / "Release" / f"{ext.name}.cp{sys.version_info.major}{sys.version_info.minor}-win_amd64.pyd",
            build_temp / "lib" / "Release" / f"{ext.name}.cp{sys.version_info.major}{sys.version_info.minor}-win_amd64.pyd",
            ROOT / "build" / f"lib.win-amd64-cpython-{sys.version_info.major}{sys.version_info.minor}" / f"{ext.name}.cp{sys.version_info.major}{sys.version_info.minor}-win_amd64.pyd",
            ROOT / f"{ext.name}.cp{sys.version_info.major}{sys.version_info.minor}-win_amd64.pyd",
        ]

        built_pyd = None
        for candidate in built_candidates:
            if candidate.exists():
                built_pyd = candidate
                break

        if built_pyd is None:
            matches = list(ROOT.rglob(f"{ext.name}.cp{sys.version_info.major}{sys.version_info.minor}-win_amd64.pyd"))
            if matches:
                built_pyd = matches[0]

        if built_pyd is None:
            raise RuntimeError(f"Built extension {ext.name} was not found after build.")

        package_ext_dir = ROOT / "tetranerf" / "utils" / "extension"
        package_ext_dir.mkdir(parents=True, exist_ok=True)

        final_pyd = package_ext_dir / built_pyd.name
        shutil.copy2(built_pyd, final_pyd)
        _print_info("copied_extension", final_pyd)

        # Windows multi-config fallback: move pyd from Release/Debug to importable extdir
        for sub in ["Release", "Debug"]:
            subdir = extdir / sub
            if subdir.exists():
                for pyd in subdir.glob("*.pyd"):
                    target = extdir / pyd.name
                    print(f"[FIX] moving {pyd} -> {target}")
                    if target.exists():
                        target.unlink()
                    shutil.move(str(pyd), str(target))


setup(
    name=PKG_NAME,
    version=VERSION,
    packages=find_packages(include=["tetranerf", "tetranerf.*"]),
    include_package_data=True,
    ext_modules=[CMakeExtension("tetranerf_cpp_extension", sourcedir=str(ROOT))],
    cmdclass={"build_ext": CMakeBuild},
    zip_safe=False,
)