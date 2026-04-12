from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from ns_installer import DEFAULT_LOCK_DIR
from ns_installer.bootstrap import print_run_bootstrapped, run, which
from ns_installer.locks import (
    DEFAULT_NUMPY,
    DEFAULT_TORCH,
    PYG_INDEX_TEMPLATE,
    TORCH_INDEX,
    load_build_plan,
    normalize_lines,
    normalize_pkg_line,
    parse_name,
    pip_lock_filename,
    read_text,
    write_text,
)
from ns_installer.protected import (
    NERFSTUDIO_CORE_OVERRIDES,
    PROTECTED_GIT_PACKAGES,
    TCNN_GIT,
)


PIP_VERBOSE_ARGS = ["-v"]
BUILD_TOOL_PKGS = ["pip", "setuptools", "wheel", "Cython", "pkgconfig", "pybind11", "ninja", "cmake"]


def normalized_current_pip_lines() -> list[str]:
    try:
        cp = run([sys.executable, "-m", "pip", "freeze", "--all"])
    except subprocess.CalledProcessError:
        cp = run([sys.executable, "-m", "pip", "freeze"])
    return [normalize_pkg_line(x) for x in normalize_lines(cp.stdout, kind="pip")]


def installed_pip_map() -> dict[str, str]:
    return {parse_name(x): normalize_pkg_line(x) for x in normalized_current_pip_lines()}


def installed_direct_url_map() -> dict[str, str]:
    cp = subprocess.run(
        [sys.executable, "-m", "pip", "freeze", "--all"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    out: dict[str, str] = {}
    for raw in normalize_lines(cp.stdout, kind="pip"):
        line = normalize_pkg_line(raw)
        if " @ " not in line:
            continue
        out[parse_name(line)] = line
    return out


def get_installed_version(pkg_name: str) -> str:
    try:
        import importlib.metadata as importlib_metadata
    except Exception:
        import importlib_metadata  # type: ignore

    for candidate in {pkg_name, pkg_name.replace("-", "_"), pkg_name.replace("_", "-")}:
        try:
            return importlib_metadata.version(candidate)
        except Exception:
            pass
    return ""


def git_requirement_matches(installed_line: str, expected_git: str) -> bool:
    a = (installed_line or "").strip().lower()
    b = (expected_git or "").strip().lower()
    return bool(a and b and b in a)


def spec_is_exact_pin(spec: str) -> bool:
    return "==" in spec and " @ " not in spec and not spec.startswith(("-", "--"))


def filter_already_installed_exact_specs(lines: list[str]) -> tuple[list[str], list[str]]:
    installed = installed_pip_map()
    pending, skipped = [], []
    for raw in lines:
        line = normalize_pkg_line(raw)
        if spec_is_exact_pin(line):
            name = parse_name(line)
            if installed.get(name, "") == line:
                skipped.append(line)
                continue
        pending.append(line)
    return pending, skipped


def detect_tcnn_runtime() -> bool:
    try:
        cp = run([sys.executable, "-c", "import tinycudann as tcnn; print('OK')"], check=False)
        return cp.returncode == 0
    except Exception:
        return False


def tcnn_runtime_ok(expected_arch: str = "") -> bool:
    try:
        import torch
        import tinycudann as _tcnn  # noqa: F401
        return torch.cuda.is_available()
    except Exception:
        return False


def torch_pyg_tag(torch_line: str) -> str:
    version = torch_line.split("==", 1)[1].strip() if "==" in torch_line else "2.1.2+cu118"
    return f"torch-{version}"


def torch_cuda_arch_list_value(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    parts = [x.strip() for x in raw.replace(",", ";").split(";") if x.strip()]
    out = []
    for p in parts:
        if "." in p:
            out.append(p)
        elif p.isdigit() and len(p) >= 2:
            out.append(f"{p[0]}.{p[1:]}")
        else:
            out.append(p)
    return ";".join(out)


def current_tcnn_arch() -> str:
    return (
        os.environ.get("TCNN_CUDA_ARCHITECTURES", "")
        or os.environ.get("CUDA_ARCH", "")
        or os.environ.get("TORCH_CUDA_ARCH_LIST", "")
    ).strip()


def install_packaging_base(lock_dir: Path, msvc_mode: str) -> None:
    print("[INFO] Installing build/runtime base tooling...")
    print_run_bootstrapped(
        lock_dir,
        [sys.executable, "-m", "pip", "install", *PIP_VERBOSE_ARGS, "--upgrade", "--force-reinstall", *BUILD_TOOL_PKGS],
        msvc_mode,
    )


def ensure_build_tooling_for_cpp(lock_dir: Path, msvc_mode: str) -> None:
    print("[INFO] Repairing Python build tooling required by native extensions...")
    print_run_bootstrapped(
        lock_dir,
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            *PIP_VERBOSE_ARGS,
            "--upgrade",
            "--force-reinstall",
            "pip",
            "setuptools==75.1.0",
            "wheel==0.44.0",
            "Cython",
            "pkgconfig",
            "pybind11",
            "ninja",
            "cmake",
        ],
        msvc_mode,
    )


def ensure_numpy_stable(lock_dir: Path, msvc_mode: str, numpy_spec: str, state: dict, *, reason: str) -> None:
    desired = numpy_spec.split("==", 1)[1] if "==" in numpy_spec else ""
    current = get_installed_version("numpy")
    if state.get("numpy_version") == desired and current == desired:
        print(f"[INFO] NumPy already stable at {desired}; skipping reinstall ({reason}).")
        return
    print(f"[INFO] Enforcing stable NumPy policy: {numpy_spec} ({reason})")
    print_run_bootstrapped(
        lock_dir,
        [sys.executable, "-m", "pip", "install", *PIP_VERBOSE_ARGS, "--upgrade", "--force-reinstall", numpy_spec],
        msvc_mode,
    )
    state["numpy_version"] = desired or get_installed_version("numpy")


def install_torch_preinstall(lock_dir: Path, msvc_mode: str, torch_lines: list[str], numpy_spec: str, state: dict) -> None:
    torch_lines = torch_lines or DEFAULT_TORCH[:]
    pending, skipped = filter_already_installed_exact_specs(torch_lines)
    if skipped:
        print(f"[INFO] Skipping already-installed torch package(s): {', '.join(skipped)}")
    if not pending:
        state["numpy_version"] = numpy_spec.split("==", 1)[1] if "==" in numpy_spec else state.get("numpy_version", "")
        return

    print_run_bootstrapped(
        lock_dir,
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            *PIP_VERBOSE_ARGS,
            "--upgrade",
            "--force-reinstall",
            numpy_spec,
            *pending,
            "--index-url",
            TORCH_INDEX,
        ],
        msvc_mode,
    )
    state["numpy_version"] = numpy_spec.split("==", 1)[1] if "==" in numpy_spec else state.get("numpy_version", "")


def install_pyg_wheels(lock_dir: Path, msvc_mode: str, torch_lines: list[str], pyg_lines: list[str]) -> None:
    if not pyg_lines:
        return

    torch_line = next((x for x in torch_lines if x.lower().startswith("torch==")), DEFAULT_TORCH[0])
    index_url = PYG_INDEX_TEMPLATE.format(torch_tag=torch_pyg_tag(torch_line))
    pending, skipped = filter_already_installed_exact_specs(pyg_lines)

    if skipped:
        print(f"[INFO] Skipping already-installed PyG wheel(s): {', '.join(skipped)}")

    for line in pending:
        print_run_bootstrapped(
            lock_dir,
            [sys.executable, "-m", "pip", "install", *PIP_VERBOSE_ARGS, line, "-f", index_url],
            msvc_mode,
        )


def install_requirements_file(lock_dir: Path, msvc_mode: str, lines: list[str], tmp_path: Path) -> None:
    if not lines:
        return

    pending, skipped = filter_already_installed_exact_specs([normalize_pkg_line(x) for x in lines])
    if skipped:
        print(
            f"[INFO] Skipping already-installed exact requirement(s): {', '.join(skipped[:20])}"
            + (" ..." if len(skipped) > 20 else "")
        )
    if not pending:
        return

    write_text(tmp_path, "\n".join(pending) + "\n")
    try:
        print_run_bootstrapped(
            lock_dir,
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                *PIP_VERBOSE_ARGS,
                "--upgrade",
                "--force-reinstall",
                "--no-deps",
                "--no-build-isolation",
                "-r",
                str(tmp_path),
            ],
            msvc_mode,
        )
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass


def install_tcnn(lock_dir: Path, msvc_mode: str, tcnn_line: str, tcnn_arch: str) -> None:
    if tcnn_runtime_ok(tcnn_arch):
        return

    ensure_build_tooling_for_cpp(lock_dir, msvc_mode)
    plan = load_build_plan(lock_dir)
    selected_arch = (tcnn_arch or str((plan.get("tinycudann") or {}).get("cuda_arch", ""))).strip()
    selected_req = (tcnn_line or str((plan.get("tinycudann") or {}).get("requirement", ""))).strip() or TCNN_GIT

    extra_env = {
        "FORCE_CUDA": "1",
        "TORCH_CUDA_ARCH_LIST": torch_cuda_arch_list_value(selected_arch),
        "MAX_JOBS": "1",
        "CMAKE_BUILD_PARALLEL_LEVEL": "1",
        "DISTUTILS_USE_SDK": "1",
        "MSSdk": "1",
        "ROCM_HOME": "",
        "ROCM_PATH": "",
        "HIP_HOME": "",
        "HIP_PATH": "",
        "HCC_HOME": "",
        "HIP_PATH_57": "",
        "HIP_DEVICE_LIB_PATH": "",
        "PYTORCH_ROCM_ARCH": "",
    }
    if selected_arch:
        extra_env["TCNN_CUDA_ARCHITECTURES"] = selected_arch

    try:
        print_run_bootstrapped(
            lock_dir,
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                *PIP_VERBOSE_ARGS,
                "--upgrade",
                "--force-reinstall",
                "--no-build-isolation",
                "--no-cache-dir",
                selected_req,
            ],
            msvc_mode,
            extra_env=extra_env,
        )
    except Exception:
        print_run_bootstrapped(
            lock_dir,
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                *PIP_VERBOSE_ARGS,
                "--upgrade",
                "--force-reinstall",
                "--no-build-isolation",
                "--no-cache-dir",
                TCNN_GIT,
            ],
            msvc_mode,
            extra_env=extra_env,
        )


def install_deferred(lock_dir: Path, msvc_mode: str, lines: list[str]) -> None:
    leftovers = [x for x in lines if "tinycudann" not in x.lower() and "tiny-cuda-nn" not in x.lower()]
    if leftovers:
        install_requirements_file(lock_dir, msvc_mode, leftovers, lock_dir / ".tmp-deferred-install.txt")


def install_av(lock_dir: Path, msvc_mode: str, lines: list[str]) -> None:
    if not lines:
        return
    print_run_bootstrapped(
        lock_dir,
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            *PIP_VERBOSE_ARGS,
            "--upgrade",
            "--force-reinstall",
            "setuptools<81",
            "wheel",
            "pip",
            "Cython",
            "pkgconfig",
            "pybind11",
            "numpy<2",
        ],
        msvc_mode,
    )
    install_requirements_file(lock_dir, msvc_mode, lines, lock_dir / ".tmp-av-install.txt")


def choose_conda_restore_cmd(conda_exe: str, explicit_file: Path) -> list[str]:
    mamba = which("mamba") or which("mamba.exe")
    micromamba = which("micromamba") or which("micromamba.exe")
    if mamba:
        return [mamba, "install", "--yes", "--verbose", "--file", str(explicit_file)]
    if micromamba:
        return [micromamba, "install", "--yes", "--verbose", "--file", str(explicit_file)]
    return [conda_exe, "install", "--solver=libmamba", "--yes", "--verbose", "--file", str(explicit_file)]


def install_remaining_from_full_lock(lock_dir: Path, msvc_mode: str) -> None:
    full_lock = pip_lock_filename(lock_dir)
    if not full_lock.exists():
        return

    current_names = {parse_name(x) for x in normalized_current_pip_lines()}
    wanted = []
    for raw in normalize_lines(read_text(full_lock), kind="pip"):
        cand = normalize_pkg_line(raw)
        name = parse_name(cand)
        if name in current_names or name in {"numpy", "torch", "torchvision", "torchaudio", "tinycudann", "tiny-cuda-nn"}:
            continue
        if " @ file:///" in cand or cand.startswith("-e ") or "cuda_backend==" in cand:
            continue
        wanted.append(cand)

    wanted = list(dict.fromkeys(wanted))
    if wanted:
        install_requirements_file(lock_dir, msvc_mode, wanted, lock_dir / ".tmp-full-remaining-install.txt")


def restore_core_overrides(lock_dir: Path, msvc_mode: str) -> None:
    current_direct = installed_direct_url_map()
    restore_specs = []

    for _, spec in NERFSTUDIO_CORE_OVERRIDES.items():
        install_ref = str(spec.get("install_ref", "")).strip()
        pip_names = [str(x).strip().lower().replace("_", "-") for x in spec.get("pip_names", set())]
        matched = False
        for pip_name in pip_names:
            if git_requirement_matches(current_direct.get(pip_name, ""), install_ref):
                matched = True
                break
        if not matched and install_ref:
            restore_specs.append(install_ref)

    if restore_specs:
        print_run_bootstrapped(
            lock_dir,
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                *PIP_VERBOSE_ARGS,
                "--upgrade",
                "--force-reinstall",
                "--no-build-isolation",
                "--no-cache-dir",
                *list(dict.fromkeys(restore_specs)),
            ],
            msvc_mode,
        )


def restore_protected_from_lock(lock_dir: Path, msvc_mode: str) -> None:
    full_lock = pip_lock_filename(lock_dir)
    if not full_lock.exists():
        return

    locked = {}
    for raw in normalize_lines(read_text(full_lock), kind="pip"):
        line = normalize_pkg_line(raw)
        name = parse_name(line)
        if name in {"numpy", "torch", "torchvision", "torchaudio", "tinycudann", "tiny-cuda-nn", "pycolmap"}:
            locked[name] = line

    current = {parse_name(x): x for x in normalized_current_pip_lines()}
    restore_specs = []

    for name, spec in locked.items():
        if spec and current.get(name, "") != spec and " @ file:///" not in spec:
            restore_specs.append(spec)

    for name, git_spec in PROTECTED_GIT_PACKAGES.items():
        if not git_requirement_matches(installed_direct_url_map().get(name, ""), git_spec):
            restore_specs.append(git_spec)

    torch_specs = [x for x in restore_specs if parse_name(x) in {"torch", "torchvision", "torchaudio"}]
    other_specs = [x for x in restore_specs if parse_name(x) not in {"torch", "torchvision", "torchaudio"}]

    if torch_specs:
        print_run_bootstrapped(
            lock_dir,
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                *PIP_VERBOSE_ARGS,
                "--upgrade",
                "--force-reinstall",
                *torch_specs,
                "--index-url",
                TORCH_INDEX,
            ],
            msvc_mode,
        )

    if other_specs:
        install_requirements_file(lock_dir, msvc_mode, other_specs, lock_dir / ".tmp-protected-restore.txt")


def print_strict_alignment_status(lock_dir: Path) -> None:
    plan = load_build_plan(lock_dir)
    pip_set = {parse_name(x): x for x in normalized_current_pip_lines()}

    print("[INFO] Strict alignment status:")
    print(f"  [TARGET NUMPY] {plan.get('numpy_stable', DEFAULT_NUMPY)}")
    for name in ["numpy", "torch", "torchvision", "torchaudio", "pycolmap"]:
        if name in pip_set:
            print(f"  [OK] {pip_set[name]}")
        else:
            print(f"  [MISS] {name}")
    print(f"  [RUNTIME tinycudann] {'OK' if detect_tcnn_runtime() else 'MISSING'}")


def install_editable_project(
    project_dir: Path,
    *,
    lock_dir: Path | None = None,
    msvc_mode: str = "",
    cuda_mode: str = "vanilla",  # ✅ PATCH
    no_deps: bool = True,
    no_build_isolation: bool = False,
) -> None:
    lock_dir = lock_dir or DEFAULT_LOCK_DIR

    cmd = [sys.executable, "-m", "pip", "install", *PIP_VERBOSE_ARGS]

    if no_deps:
        cmd.append("--no-deps")
    if no_build_isolation:
        cmd.append("--no-build-isolation")

    cmd.extend(["-e", str(project_dir)])

    print_run_bootstrapped(
        lock_dir,
        cmd,
        msvc_mode,
        cuda_mode=cuda_mode,  # ✅ CRUCIALE
        cwd=project_dir,
    )

def build_tetra_nerf_windows(
    repo_dir: Path,
    *,
    lock_dir: Path | None = None,
    msvc_mode: str = "",
    cuda_mode: str = "vanilla",  # ✅ PATCH
) -> None:
    lock_dir = lock_dir or DEFAULT_LOCK_DIR

    print_run_bootstrapped(
        lock_dir,
        [sys.executable, "setup.py", "build_ext"],
        msvc_mode,
        cuda_mode=cuda_mode,  # ✅ CRUCIALE
        cwd=repo_dir,
    )

def build_zipnerf_cuda_windows(repo_dir: Path, *, lock_dir: Path | None = None, msvc_mode: str = "", cuda_mode: str = "vanilla") -> None:
    lock_dir = lock_dir or DEFAULT_LOCK_DIR
    ensure_build_tooling_for_cpp(lock_dir, msvc_mode)

    candidates = [repo_dir / "make_patch_zipnerf_cuda.bat", repo_dir / "make_zipnerf_cuda.bat"]
    for script in candidates:
        if script.exists():
            print_run_bootstrapped(
                lock_dir,
                ["cmd", "/d", "/s", "/c", str(script)],
                msvc_mode,
                cuda_mode=cuda_mode,
                cwd=repo_dir,
            )
            return

    print("[WARN] No Windows zipnerf CUDA build script found; skipped.")


def maybe_build_method_native(
    method_name: str,
    repo_dir: Path,
    *,
    lock_dir: Path | None = None,
    msvc_mode: str = "",
    cuda_mode: str = "vanilla",  # ✅ PATCH
) -> None:
    if method_name == "tetra-nerf":
        build_tetra_nerf_windows(
            repo_dir,
            lock_dir=lock_dir,
            msvc_mode=msvc_mode,
            cuda_mode=cuda_mode,  # ✅
        )

def repin_after_method_install(
    lock_dir: Path,
    msvc_mode: str,
    cuda_mode: str = "vanilla",  # opzionale ma coerente
) -> None:
    plan = load_build_plan(lock_dir)
    numpy_spec = plan.get("numpy_stable") or DEFAULT_NUMPY
    state: dict = {}

    ensure_numpy_stable(lock_dir, msvc_mode, numpy_spec, state, reason="post-method")

    restore_core_overrides(lock_dir, msvc_mode)
    restore_protected_from_lock(lock_dir, msvc_mode)

    ensure_numpy_stable(lock_dir, msvc_mode, numpy_spec, state, reason="post-protected-restore")