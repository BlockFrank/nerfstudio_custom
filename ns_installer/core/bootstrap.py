from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

from ns_installer.locks import (
    load_installer_selection,
    msvc_log_filename,
    msvc_selected_filename,
    write_text,
)


def run(
    cmd: list[str],
    *,
    check: bool = True,
    capture: bool = True,
    env: Optional[dict[str, str]] = None,
    cwd: Optional[Path | str] = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=check,
        capture_output=capture,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=str(cwd) if cwd is not None else None,
    )


def print_run(
    cmd: list[str],
    *,
    env: Optional[dict[str, str]] = None,
    cwd: Optional[Path | str] = None,
) -> None:
    print(f"[RUN] {' '.join(str(x) for x in cmd)}")
    subprocess.run(cmd, check=True, env=env, cwd=str(cwd) if cwd is not None else None)


def which(name: str) -> Optional[str]:
    return shutil.which(name)


def _looks_like_windows_path(value: str) -> bool:
    v = (value or "").strip()
    return bool(re.match(r"^[A-Za-z]:\\", v) or re.match(r"^\\\\", v))


def _strip_wrapping_quotes(value: str) -> str:
    v = (value or "").strip()
    while len(v) >= 2 and ((v[0] == '"' and v[-1] == '"') or (v[0] == "'" and v[-1] == "'")):
        v = v[1:-1].strip()
    return v


def sanitize_windows_path(value: str) -> str:
    v = (value or "").strip()
    if not v:
        return ""
    v = v.replace("/", "\\")
    v = v.replace('\\"', '"').replace("\\'", "'")
    v = _strip_wrapping_quotes(v)
    m = re.match(r'^[A-Za-z]:(?:\\?["\']+)([A-Za-z]:\\.*)$', v)
    if m:
        v = m.group(1).strip()
    if len(v) >= 2 and v[0] == '"' and _looks_like_windows_path(v[1:]):
        v = v[1:]
    if len(v) >= 2 and v[-1] == '"' and _looks_like_windows_path(v[:-1]):
        v = v[:-1]
    v = v.strip().strip('"').strip("'").strip()
    if _looks_like_windows_path(v):
        drive_m = re.match(r'^([A-Za-z]:\\)(.*)$', v)
        unc_m = re.match(r'^(\\\\[^\\]+\\[^\\]+\\?)(.*)$', v)
        if drive_m:
            prefix, rest = drive_m.groups()
            rest = re.sub(r'\\+', r'\\', rest)
            v = prefix + rest
        elif unc_m:
            prefix, rest = unc_m.groups()
            rest = re.sub(r'\\+', r'\\', rest)
            v = prefix + rest
    if re.search(r'\.(exe|bat|cmd)$', v, re.I):
        v = v.rstrip("\\/")
    return os.path.normpath(v) if v else ""


def normalize_windows_path_list(value: str) -> str:
    if platform.system().lower() != "windows":
        return value or ""
    parts: list[str] = []
    seen: set[str] = set()
    for raw in (value or "").split(os.pathsep):
        item = sanitize_windows_path(raw)
        if not item:
            continue
        key = os.path.normcase(os.path.normpath(item))
        if key in seen:
            continue
        seen.add(key)
        parts.append(os.path.normpath(item))
    return os.pathsep.join(parts)


def _norm_win_path(value: str) -> str:
    clean = sanitize_windows_path(value)
    return os.path.normpath(clean) if clean else ""


def _norm_win_list(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        nv = _norm_win_path(value)
        if not nv:
            continue
        key = nv.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(nv)
    return out


def _split_path_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [x for x in value.split(os.pathsep) if x]


def _dedupe_keep_order(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _is_cuda_path_entry(path_entry: str) -> bool:
    p = path_entry.replace("/", "\\").lower()
    return bool(
        re.search(r"\\nvidia gpu computing toolkit\\cuda\\v[\d\.]+\\bin$", p)
        or re.search(r"\\nvidia gpu computing toolkit\\cuda\\v[\d\.]+\\libnvvp$", p)
        or re.search(r"\\cuda\\v[\d\.]+\\bin$", p)
        or re.search(r"\\cuda\\v[\d\.]+\\libnvvp$", p)
    )


def _remove_other_cuda_from_path(path_value: str, selected_cuda_root: str) -> str:
    selected_root = _norm_win_path(selected_cuda_root).lower().replace("/", "\\")
    kept: list[str] = []

    for raw in _split_path_list(path_value):
        norm = _norm_win_path(raw)
        low = norm.lower().replace("/", "\\")
        if _is_cuda_path_entry(norm):
            if low.startswith(selected_root + "\\"):
                kept.append(norm)
            continue
        kept.append(norm)

    return os.pathsep.join(_dedupe_keep_order(kept))


def _clear_rocm_like_env(env: dict[str, str]) -> None:
    for key in [
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
    ]:
        env.pop(key, None)


def _detect_user_requested_cuda_from_env(env: dict[str, str]) -> str:
    for key in ("CUDAToolkit_ROOT", "CUDA_HOME", "CUDA_PATH"):
        value = _norm_win_path(env.get(key, ""))
        if value and Path(value).exists():
            return value
    return ""


def short_toolset_version(version: str) -> str:
    version = (version or "").strip()
    if not version:
        return ""
    parts = version.split(".")
    return f"{parts[0]}.{parts[1]}" if len(parts) >= 2 else version


def normalize_selected_toolset(selected: dict | None) -> dict | None:
    if not selected:
        return None
    out = dict(selected)
    full = (out.get("toolset_full") or out.get("toolset") or "").strip()
    out["toolset_full"] = full
    out["toolset_short"] = short_toolset_version(full)
    out["toolset"] = full
    return out


def vswhere_path() -> Optional[str]:
    candidates = [
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Microsoft Visual Studio", "Installer", "vswhere.exe"),
        os.path.join(os.environ.get("ProgramFiles", ""), "Microsoft Visual Studio", "Installer", "vswhere.exe"),
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def list_msvc_toolsets() -> list[dict]:
    if platform.system().lower() != "windows":
        return []

    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    installs: list[Path] = []

    vswhere = vswhere_path()
    if vswhere:
        cp = run(
            [
                vswhere,
                "-products",
                "*",
                "-requires",
                "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                "-property",
                "installationPath",
            ],
            check=False,
        )
        for line in cp.stdout.splitlines():
            line = line.strip()
            if line:
                installs.append(Path(line))

    fallback_roots = [
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft Visual Studio",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Microsoft Visual Studio",
    ]
    for root in fallback_roots:
        if not root.exists():
            continue
        for year_dir in root.iterdir():
            if not year_dir.is_dir():
                continue
            for edition_dir in year_dir.iterdir():
                if edition_dir.is_dir():
                    installs.append(edition_dir)

    dedup_installs: list[Path] = []
    seen_install = set()
    for inst in installs:
        key = os.path.normcase(str(inst))
        if key in seen_install:
            continue
        seen_install.add(key)
        dedup_installs.append(inst)

    for root in dedup_installs:
        msvc_root = root / "VC" / "Tools" / "MSVC"
        if not msvc_root.exists():
            continue
        for d in sorted(msvc_root.iterdir()):
            if not d.is_dir():
                continue
            vcvarsall = root / "VC" / "Auxiliary" / "Build" / "vcvarsall.bat"
            cl = d / "bin" / "Hostx64" / "x64" / "cl.exe"
            if not (vcvarsall.exists() and cl.exists()):
                continue
            key = (str(root), d.name)
            if key in seen:
                continue
            seen.add(key)
            normalized = normalize_selected_toolset(
                {
                    "installation": _norm_win_path(str(root)),
                    "toolset": d.name,
                    "vcvarsall": _norm_win_path(str(vcvarsall)),
                    "cl": _norm_win_path(str(cl)),
                }
            )
            if normalized:
                out.append(normalized)

    out.sort(key=lambda x: x["toolset_full"], reverse=True)
    return out


def write_msvc_log(lock_dir: Path) -> list[dict]:
    toolsets = list_msvc_toolsets()
    lines: list[str] = []
    if not toolsets:
        lines.append("No MSVC toolsets detected.")
    else:
        lines.append("Detected MSVC toolsets:")
        for t in toolsets:
            lines.append(
                f"{t['toolset_full']} | short={t['toolset_short']} | "
                f"install={t['installation']} | cl={t['cl']} | vcvarsall={t['vcvarsall']}"
            )
    write_text(msvc_log_filename(lock_dir), "\n".join(lines) + "\n")
    return toolsets


def choose_msvc_toolset(lock_dir: Path, requested: str) -> Optional[dict]:
    toolsets = write_msvc_log(lock_dir)
    requested = (requested or "").strip().lower()

    if not toolsets or requested in {"", "system"}:
        return None

    if requested == "auto":
        for t in toolsets:
            if t["toolset_short"] == "14.38" or t["toolset_full"].startswith("14.38"):
                return t
        return toolsets[0]

    if requested == "14":
        for t in toolsets:
            if t["toolset_full"].startswith("14."):
                return t
        return None

    for t in toolsets:
        if t["toolset_short"] == requested or t["toolset_full"].startswith(requested):
            return t

    return None


def detect_cuda_root(*, cuda_mode: str = "vanilla") -> str:
    default_cuda_118 = (
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "NVIDIA GPU Computing Toolkit"
        / "CUDA"
        / "v11.8"
    )

    if cuda_mode != "experimental-env" and default_cuda_118.exists():
        return str(default_cuda_118)

    candidates = [os.environ.get("CUDA_PATH", ""), os.environ.get("CUDA_HOME", ""), os.environ.get("CUDAToolkit_ROOT", "")]
    for cand in candidates:
        cand = _norm_win_path(cand)
        if cand and Path(cand).exists():
            return cand

    nvcc = shutil.which("nvcc.exe") or shutil.which("nvcc")
    if nvcc:
        try:
            return str(Path(nvcc).resolve().parent.parent)
        except Exception:
            pass

    return str(default_cuda_118) if default_cuda_118.exists() else ""


def detect_git_dirs() -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    git_exe = shutil.which("git.exe") or shutil.which("git")
    if git_exe:
        gp = os.path.normpath(str(Path(git_exe).resolve().parent))
        key = os.path.normcase(gp)
        if key not in seen:
            seen.add(key)
            candidates.append(gp)

    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    for p in (Path(program_files) / "Git" / "cmd", Path(program_files) / "Git" / "bin"):
        if p.exists():
            gp = os.path.normpath(str(p))
            key = os.path.normcase(gp)
            if key not in seen:
                seen.add(key)
                candidates.append(gp)

    return candidates


def get_runtime_path_entries() -> list[str]:
    entries: list[str] = []
    conda_prefix = os.environ.get("CONDA_PREFIX", "")
    if conda_prefix:
        prefix = Path(conda_prefix)
        for p in (
            prefix / "Scripts",
            prefix,
            prefix / "Library" / "bin",
            prefix / "Library" / "usr" / "bin",
            prefix / "bin",
        ):
            entries.append(str(p))
    entries.append(str(Path(sys.executable).resolve().parent))
    entries.extend(detect_git_dirs())
    return entries


def parse_set_output_to_env(text: str) -> dict[str, str]:
    parsed_env: dict[str, str] = {}
    path_list_keys = {"PATH", "INCLUDE", "LIB", "LIBPATH"}
    path_scalar_keys = {
        "CC",
        "CXX",
        "CUDAHOSTCXX",
        "CLCACHE_CL",
        "CMAKE_CUDA_HOST_COMPILER",
        "VCToolsInstallDir",
        "VCINSTALLDIR",
        "VSINSTALLDIR",
        "WindowsSdkDir",
        "WindowsSDKVersion",
        "UniversalCRTSdkDir",
        "UCRTVersion",
        "CUDA_PATH",
        "CUDA_HOME",
        "CUDAToolkit_ROOT",
    }
    path_scalar_keys_upper = {x.upper() for x in path_scalar_keys}

    for line in (text or "").splitlines():
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        if not k:
            continue
        ku = k.upper()
        if ku in path_list_keys:
            parsed_env[k] = normalize_windows_path_list(v)
        elif ku in path_scalar_keys_upper:
            parsed_env[k] = _norm_win_path(v)
        else:
            parsed_env[k] = v.strip().replace('\\"', '"').replace('""', '"')
    return parsed_env


def _capture_vcvars_env(vcvarsall: str, short_ver: str, full_ver: str) -> dict[str, str]:
    cmd_lines = [
        "@echo off",
        "setlocal EnableExtensions",
        f'call "{vcvarsall}" x64 -vcvars_ver={short_ver}',
        f'if errorlevel 1 call "{vcvarsall}" x64 -vcvars_ver={full_ver}',
        f'if errorlevel 1 call "{vcvarsall}" x64',
        "if errorlevel 1 exit /b %errorlevel%",
        "set",
    ]
    script = "\r\n".join(cmd_lines) + "\r\n"

    with tempfile.NamedTemporaryFile("w", suffix=".cmd", delete=False, encoding="utf-8", newline="\r\n") as f:
        f.write(script)
        temp_cmd = f.name

    try:
        cp = subprocess.run(
            ["cmd", "/d", "/s", "/c", temp_cmd],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        return parse_set_output_to_env(cp.stdout)
    finally:
        try:
            os.unlink(temp_cmd)
        except OSError:
            pass


def apply_cuda_env_policy(
    env: dict[str, str],
    selected_cuda_root: str,
    *,
    cuda_mode: str = "vanilla",
) -> dict[str, str]:
    env = dict(env)
    _clear_rocm_like_env(env)

    bootstrap_cuda = _norm_win_path(selected_cuda_root)
    user_cuda = _detect_user_requested_cuda_from_env(env)

    if cuda_mode == "experimental-env" and user_cuda:
        active_cuda = user_cuda
    else:
        active_cuda = bootstrap_cuda

    if not active_cuda:
        return env

    cuda_bin = _norm_win_path(str(Path(active_cuda) / "bin"))
    cuda_libnvvp = _norm_win_path(str(Path(active_cuda) / "libnvvp"))

    env["CUDA_PATH"] = active_cuda
    env["CUDA_HOME"] = active_cuda
    env["CUDAToolkit_ROOT"] = active_cuda
    env["CUDA_BIN_PATH"] = cuda_bin

    cleaned_path = _remove_other_cuda_from_path(env.get("PATH", ""), active_cuda)
    new_path_entries = [cuda_bin, cuda_libnvvp] + _split_path_list(cleaned_path)
    env["PATH"] = os.pathsep.join(_dedupe_keep_order([x for x in new_path_entries if x]))

    return env


def build_bootstrap_context(lock_dir: Path, requested: str, *, cuda_mode: str = "vanilla") -> dict:
    installer = load_installer_selection(lock_dir)
    effective = str(
        installer.get("preferred_msvc") or requested or os.environ.get("PREFERRED_MSVC") or ""
    ).strip()

    selected = None
    materialized_env: dict[str, str] = {}
    cuda_root = ""
    git_dirs: list[str] = []
    runtime_entries: list[str] = []

    if platform.system().lower() == "windows":
        selected = normalize_selected_toolset(choose_msvc_toolset(lock_dir, effective))
        if selected:
            selected = {
                **selected,
                "installation": _norm_win_path(selected.get("installation", "")),
                "vcvarsall": _norm_win_path(selected.get("vcvarsall", "")),
                "cl": _norm_win_path(selected.get("cl", "")),
            }
            try:
                materialized_env = _capture_vcvars_env(
                    selected["vcvarsall"],
                    selected["toolset_short"],
                    selected["toolset_full"],
                )
            except Exception:
                materialized_env = {}

        cuda_root = _norm_win_path(detect_cuda_root(cuda_mode=cuda_mode))
        git_dirs = _norm_win_list(detect_git_dirs())
        runtime_entries = _norm_win_list(get_runtime_path_entries())

    ctx = {
        "requested": effective,
        "selected": selected,
        "cuda_root": cuda_root,
        "git_dirs": git_dirs,
        "runtime_path_entries": runtime_entries,
        "materialized_env": materialized_env,
        "cuda_mode": cuda_mode,
    }

    lines = [
        f"requested={effective or 'system'}",
        f"cuda_mode={cuda_mode}",
        f"cuda_root={cuda_root}",
        f"git_dirs={';'.join(git_dirs)}",
        f"runtime_path_entries={';'.join(runtime_entries)}",
        f"include={materialized_env.get('INCLUDE', '')}",
        f"lib={materialized_env.get('LIB', '')}",
        f"libpath={materialized_env.get('LIBPATH', '')}",
        f"winsdk={materialized_env.get('WindowsSdkDir', '')}",
        f"ucrt={materialized_env.get('UniversalCRTSdkDir', '')}",
    ]
    if selected:
        lines.extend(
            [
                f"selected_toolset={selected['toolset_full']}",
                f"selected_short={selected['toolset_short']}",
                f"selected_install={selected['installation']}",
                f"selected_cl={selected['cl']}",
                f"selected_vcvarsall={selected['vcvarsall']}",
                "mode=subprocess-shell-bootstrap",
            ]
        )
    else:
        lines.append("mode=system/no-forced-toolset")

    write_text(msvc_selected_filename(lock_dir), "\n".join(lines) + "\n")
    return ctx


def build_bootstrap_env(
    lock_dir: Path,
    requested: str,
    extra_env: Optional[dict[str, str]] = None,
    *,
    cuda_mode: str = "vanilla",
) -> dict[str, str]:
    ctx = build_bootstrap_context(lock_dir, requested, cuda_mode=cuda_mode)
    env = os.environ.copy()
    materialized = dict(ctx.get("materialized_env") or {})
    selected = ctx.get("selected")
    runtime_entries = list(ctx.get("runtime_path_entries", []))
    cuda_root = _norm_win_path(ctx.get("cuda_root", ""))

    for key, value in materialized.items():
        if key.upper() in {"PATH", "INCLUDE", "LIB", "LIBPATH"}:
            env[key] = normalize_windows_path_list(value)
        else:
            env[key] = value

    if selected:
        cl = _norm_win_path(selected.get("cl", ""))
        full_ver = str(selected.get("toolset_full", "")).strip()
        env["NS_SELECTED_MSVC_TOOLSET"] = full_ver
        env["NS_SELECTED_MSVC_CL"] = cl
        env["CC"] = cl
        env["CXX"] = cl
        env["CUDAHOSTCXX"] = cl
        env["CLCACHE_CL"] = cl
        env["CMAKE_CUDA_HOST_COMPILER"] = cl
        env["DISTUTILS_USE_SDK"] = "1"
        env["MSSdk"] = "1"
        env["CMAKE_GENERATOR"] = "Visual Studio 17 2022"
        if full_ver:
            env["CMAKE_GENERATOR_TOOLSET"] = f"v143,version={full_ver}"

    merged_runtime = normalize_windows_path_list(os.pathsep.join(runtime_entries))
    if merged_runtime:
        current_path = env.get("PATH", "")
        env["PATH"] = f"{merged_runtime}{os.pathsep}{current_path}" if current_path else merged_runtime

    env = apply_cuda_env_policy(env, cuda_root, cuda_mode=cuda_mode)

    if extra_env:
        for k, v in extra_env.items():
            if v is None:
                continue
            env[k] = str(v)

    return env


def write_bootstrap_env_snapshot(lock_dir: Path, env: dict[str, str]) -> Path:
    snapshot_path = lock_dir / "bootstrap-env.txt"
    lines = []
    for key in [
        "NS_SELECTED_MSVC_TOOLSET",
        "NS_SELECTED_MSVC_CL",
        "CC",
        "CXX",
        "CUDAHOSTCXX",
        "CMAKE_CUDA_HOST_COMPILER",
        "CMAKE_GENERATOR",
        "CMAKE_GENERATOR_TOOLSET",
        "CUDA_PATH",
        "CUDA_HOME",
        "CUDAToolkit_ROOT",
        "WindowsSdkDir",
        "WindowsSDKVersion",
        "UniversalCRTSdkDir",
        "UCRTVersion",
        "VCToolsInstallDir",
        "VCINSTALLDIR",
        "VSINSTALLDIR",
        "INCLUDE",
        "LIB",
        "LIBPATH",
        "PATH",
    ]:
        lines.append(f"{key}={env.get(key, '')}")
    write_text(snapshot_path, "\n".join(lines) + "\n")
    return snapshot_path


def find_header_in_include(include_value: str, header_name: str) -> str:
    header_name = (header_name or "").strip()
    if not header_name:
        return ""
    for raw in normalize_windows_path_list(include_value).split(os.pathsep):
        root = _norm_win_path(raw)
        if not root:
            continue
        p = Path(root) / header_name
        if p.exists():
            return str(p)
    return ""


def validate_msvc_from_shell(lock_dir: Path, ctx: dict) -> tuple[bool, list[str]]:
    if platform.system().lower() != "windows":
        return True, []

    selected = ctx.get("selected")
    if not selected:
        return True, []

    errors: list[str] = []
    vcvarsall = _norm_win_path(selected.get("vcvarsall", ""))
    cl = _norm_win_path(selected.get("cl", ""))

    if not vcvarsall or not Path(vcvarsall).exists():
        errors.append(f"vcvarsall missing: {vcvarsall}")
    if not cl or not Path(cl).exists():
        errors.append(f"cl.exe missing: {cl}")

    env = ctx.get("materialized_env") or {}
    include_value = env.get("INCLUDE", "")
    if not include_value:
        errors.append("INCLUDE is empty after vcvars materialization")
    else:
        if not find_header_in_include(include_value, "corecrt.h"):
            errors.append("corecrt.h not found inside INCLUDE")
        if not find_header_in_include(include_value, "Windows.h"):
            errors.append("Windows.h not found inside INCLUDE")

    return len(errors) == 0, errors


def _cmdline_from_args(args: list[str]) -> str:
    return subprocess.list2cmdline([str(x) for x in args])


def _make_bootstrap_batch(
    lock_dir: Path,
    command: list[str],
    msvc_mode: str,
    *,
    cwd: Optional[Path | str] = None,
    extra_env: Optional[dict[str, str]] = None,
    cuda_mode: str = "vanilla",
) -> str:
    ctx = build_bootstrap_context(lock_dir, msvc_mode, cuda_mode=cuda_mode)
    ok, errors = validate_msvc_from_shell(lock_dir, ctx)
    if not ok:
        raise RuntimeError("MSVC bootstrap metadata invalid: " + "; ".join(errors))

    selected = ctx.get("selected")
    final_env = build_bootstrap_env(
        lock_dir,
        msvc_mode,
        extra_env=extra_env,
        cuda_mode=cuda_mode,
    )

    lines: list[str] = ["@echo off", "setlocal EnableExtensions"]

    if cwd is not None:
        lines.append(f'cd /d "{Path(cwd).resolve()}"')
        lines.append("if errorlevel 1 exit /b %errorlevel%")

    if platform.system().lower() == "windows" and selected:
        vcvarsall = _norm_win_path(selected["vcvarsall"])
        short_ver = selected["toolset_short"]
        full_ver = selected["toolset_full"]
        lines.extend(
            [
                f'call "{vcvarsall}" x64 -vcvars_ver={short_ver}',
                f'if errorlevel 1 call "{vcvarsall}" x64 -vcvars_ver={full_ver}',
                f'if errorlevel 1 call "{vcvarsall}" x64',
                "if errorlevel 1 exit /b %errorlevel%",
            ]
        )

    export_keys = [
        "NS_SELECTED_MSVC_TOOLSET",
        "NS_SELECTED_MSVC_CL",
        "CC",
        "CXX",
        "CUDAHOSTCXX",
        "CLCACHE_CL",
        "CMAKE_CUDA_HOST_COMPILER",
        "CMAKE_GENERATOR",
        "CMAKE_GENERATOR_TOOLSET",
        "DISTUTILS_USE_SDK",
        "MSSdk",
        "CUDA_PATH",
        "CUDA_HOME",
        "CUDAToolkit_ROOT",
        "CUDA_BIN_PATH",
        "WindowsSdkDir",
        "WindowsSDKVersion",
        "UniversalCRTSdkDir",
        "UCRTVersion",
        "VCToolsInstallDir",
        "VCINSTALLDIR",
        "VSINSTALLDIR",
        "INCLUDE",
        "LIB",
        "LIBPATH",
        "PATH",
    ]

    for key in export_keys:
        value = final_env.get(key, "")
        if value:
            lines.append(f'set "{key}={value}"')

    for key in (
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
    ):
        lines.append(f'set "{key}="')

    lines.append(_cmdline_from_args(command))
    lines.append("exit /b %errorlevel%")
    return "\n".join(lines) + "\n"


def run_bootstrapped(
    lock_dir: Path,
    command: list[str],
    msvc_mode: str,
    *,
    check: bool = True,
    cwd: Optional[Path | str] = None,
    extra_env: Optional[dict[str, str]] = None,
    cuda_mode: str = "vanilla",
) -> subprocess.CompletedProcess:
    if platform.system().lower() != "windows":
        env = os.environ.copy()
        if extra_env:
            env.update({k: str(v) for k, v in extra_env.items() if v is not None})
        return subprocess.run(
            command,
            check=check,
            env=env,
            cwd=str(cwd) if cwd is not None else None,
        )

    script = _make_bootstrap_batch(
        lock_dir,
        command,
        msvc_mode,
        cwd=cwd,
        extra_env=extra_env,
        cuda_mode=cuda_mode,
    )
    with tempfile.NamedTemporaryFile("w", suffix=".cmd", delete=False, encoding="utf-8", newline="\r\n") as f:
        f.write(script)
        temp_cmd = f.name
    try:
        return subprocess.run(["cmd", "/d", "/s", "/c", temp_cmd], check=check)
    finally:
        try:
            os.unlink(temp_cmd)
        except OSError:
            pass


def print_run_bootstrapped(
    lock_dir: Path,
    command: list[str],
    msvc_mode: str,
    *,
    cwd: Optional[Path | str] = None,
    extra_env: Optional[dict[str, str]] = None,
    cuda_mode: str = "vanilla",
) -> None:
    print(f"[RUN] {' '.join(str(x) for x in command)}")
    run_bootstrapped(
        lock_dir,
        command,
        msvc_mode,
        check=True,
        cwd=cwd,
        extra_env=extra_env,
        cuda_mode=cuda_mode,
    )