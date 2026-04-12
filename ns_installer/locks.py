from __future__ import annotations

import json
import os
import platform
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ns_installer import DEFAULT_LOCK_DIR
from ns_installer.protected import (
    NERFSTUDIO_CORE_OVERRIDES,
    NERFSTUDIO_METHODS_PROTECTED,
    is_core_override_name,
    is_protected_method_name,
)

DEFAULT_NUMPY = "numpy==1.26.4"
DEFAULT_TORCH = ["torch==2.1.2+cu118", "torchvision==0.16.2+cu118"]
TORCH_INDEX = "https://download.pytorch.org/whl/cu118"
PYG_INDEX_TEMPLATE = "https://data.pyg.org/whl/{torch_tag}.html"

TORCH_LINE_RE = re.compile(r"^(torch|torchvision|torchaudio)==", re.I)
PYG_LINE_RE = re.compile(r"^torch[-_](scatter|sparse|cluster|spline[-_]conv)==", re.I)
AV_LINE_RE = re.compile(r"^av==", re.I)
PYWIN32_BAD_RE = re.compile(r"^pywin32==305\.1$", re.I)
TCNN_REQ_RE = re.compile(r"^(tinycudann|tiny-cuda-nn)(==|\s*@\s*)", re.I)

SKIP_PATTERNS = [
    re.compile(r"^-e\s+\.", re.I),
    re.compile(r"^-e\s+.+nerfstudio", re.I),
    re.compile(r"^\S+\s*@\s*file:///", re.I),
    re.compile(r"^cuda_backend==", re.I),
    re.compile(r"^av==", re.I),
    re.compile(r"^torch==", re.I),
    re.compile(r"^torchvision==", re.I),
    re.compile(r"^torchaudio==", re.I),
    re.compile(r"^torch[-_]scatter==", re.I),
    re.compile(r"^torch[-_]sparse==", re.I),
    re.compile(r"^torch[-_]cluster==", re.I),
    re.compile(r"^torch[-_]spline[-_]conv==", re.I),
    re.compile(r"^numpy(==|<|<=|>=|>|~=)", re.I),
]
DEFER_PATTERNS = [
    re.compile(r"^tinycudann\s*@\s*git\+https://github.com/NVlabs/tiny-cuda-nn/", re.I),
    re.compile(r"^tiny-cuda-nn\s*@\s*git\+https://github.com/NVlabs/tiny-cuda-nn/", re.I),
    re.compile(r"^tinycudann==", re.I),
    re.compile(r"^tiny-cuda-nn==", re.I),
]

def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)

def write_text(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8", newline="\n")

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")

def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(read_text(path))
    except Exception:
        return {}

def current_platform_guess() -> str:
    sysname = platform.system().lower()
    machine = platform.machine().lower()
    if sysname == "windows":
        return "win-arm64" if machine in {"arm64", "aarch64"} else "win-64"
    if sysname == "linux":
        return "linux-aarch64" if machine in {"arm64", "aarch64"} else "linux-64"
    if sysname == "darwin":
        return "osx-arm64" if machine in {"arm64", "aarch64"} else "osx-64"
    return f"{sysname}-{machine}"

def conda_explicit_filename(lock_dir: Path, platform_tag: str) -> Path: return lock_dir / f"conda-explicit-{platform_tag}.txt"
def pip_lock_filename(lock_dir: Path) -> Path: return lock_dir / "pip-freeze-all.txt"
def replay_pip_filename(lock_dir: Path) -> Path: return lock_dir / "pip-freeze-replay.txt"
def build_plan_filename(lock_dir: Path) -> Path: return lock_dir / "build-plan.json"
def meta_filename(lock_dir: Path) -> Path: return lock_dir / "lock-meta.json"
def numpy_audit_filename(lock_dir: Path) -> Path: return lock_dir / "numpy-compat-audit.txt"
def nerfstudio_methods_filename(lock_dir: Path) -> Path: return lock_dir / "nerfstudio-methods-protected.json"
def nerfstudio_core_overrides_filename(lock_dir: Path) -> Path: return lock_dir / "nerfstudio-core-overrides.json"
def msvc_log_filename(lock_dir: Path) -> Path: return lock_dir / "msvc-toolsets.txt"
def msvc_selected_filename(lock_dir: Path) -> Path: return lock_dir / "msvc-selected.txt"
def installer_selection_filename(lock_dir: Path) -> Path: return lock_dir / "installer-selection.json"

def load_build_plan(lock_dir: Path) -> dict:
    return load_json(build_plan_filename(lock_dir))

def load_installer_selection(lock_dir: Path) -> dict:
    return load_json(installer_selection_filename(lock_dir))

def normalize_lines(text: str, *, kind: str) -> list[str]:
    out: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if kind == "pip" and (line.startswith("-e ") or line.startswith("--editable")):
            continue
        out.append(line)
    return out

def normalize_pkg_line(line: str) -> str:
    line = line.strip()
    return "pywin32==305" if PYWIN32_BAD_RE.match(line) else line

def parse_name(line: str) -> str:
    if " @ " in line:
        return line.split(" @ ", 1)[0].strip().lower().replace("_", "-")
    for sep in ("==", "<=", ">=", "~=", "<", ">"):
        if sep in line:
            return line.split(sep, 1)[0].strip().lower().replace("_", "-")
    return line.strip().lower().replace("_", "-")

def detect_torch_lines(lines: list[str]) -> list[str]:
    found = [normalize_pkg_line(line) for line in lines if TORCH_LINE_RE.match(line)]
    if not found:
        return DEFAULT_TORCH[:]
    uniq: list[str] = []
    for line in found:
        if line not in uniq:
            uniq.append(line)
    return uniq

def detect_pyg_lines(lines: list[str]) -> list[str]:
    uniq: list[str] = []
    for line in lines:
        line = normalize_pkg_line(line)
        if PYG_LINE_RE.match(line) and line not in uniq:
            uniq.append(line)
    return uniq

def detect_numpy_baseline(lines: list[str]) -> str:
    for line in lines:
        if line.lower().startswith("numpy=="):
            version = line.split("==", 1)[1].strip()
            if version and not version.startswith("2"):
                return f"numpy=={version}"
    return DEFAULT_NUMPY

def detect_tcnn_line(lines: list[str]) -> str:
    for line in lines:
        if TCNN_REQ_RE.match(line):
            return normalize_pkg_line(line)
    return "git+https://github.com/NVlabs/tiny-cuda-nn/#subdirectory=bindings/torch"

def compute_replay_lines(lines: list[str]) -> list[str]:
    replay: list[str] = []
    for raw in lines:
        line = normalize_pkg_line(raw)
        name = parse_name(line)
        if is_protected_method_name(name) or is_core_override_name(name):
            continue
        if any(p.search(line) for p in SKIP_PATTERNS):
            continue
        if any(p.search(line) for p in DEFER_PATTERNS):
            continue
        replay.append(line)
    return replay

def split_pip_lock(lock_text: str, lock_dir: Path) -> tuple[list[str], list[str], str, list[str], list[str], list[str]]:
    lines = [normalize_pkg_line(x) for x in normalize_lines(lock_text, kind="pip")]
    plan = load_build_plan(lock_dir)
    torch_lines = plan.get("torch_preinstall") or detect_torch_lines(lines)
    pyg_lines = plan.get("pyg_wheels") or detect_pyg_lines(lines)
    tcnn_line = (plan.get("tinycudann") or {}).get("requirement") or detect_tcnn_line(lines)
    torch_names = {parse_name(x) for x in torch_lines}
    pyg_names = {parse_name(x) for x in pyg_lines}
    bulk, deferred, av_lines = [], [], []
    for line in lines:
        name = parse_name(line)
        if name in torch_names or name in pyg_names or name == "numpy":
            continue
        if is_protected_method_name(name) or is_core_override_name(name):
            continue
        if name in {"tinycudann", "tiny-cuda-nn"}:
            continue
        if AV_LINE_RE.match(line):
            av_lines.append(line)
            continue
        if any(p.search(line) for p in DEFER_PATTERNS):
            deferred.append(line)
            continue
        if any(p.search(line) for p in SKIP_PATTERNS):
            continue
        bulk.append(line)
    return torch_lines, pyg_lines, tcnn_line, bulk, deferred, av_lines

def find_conda_lock(lock_dir: Path) -> Optional[Path]:
    matches = sorted(lock_dir.glob("conda-explicit-*.txt"))
    if matches:
        platform_tag = current_platform_guess()
        platform_match = lock_dir / f"conda-explicit-{platform_tag}.txt"
        if platform_match.exists():
            return platform_match
        return matches[0]
    fallback = lock_dir / "conda-explicit.txt"
    return fallback if fallback.exists() else None

def parse_platform_from_explicit(explicit_text: str) -> str:
    for line in explicit_text.splitlines():
        m = re.match(r"\s*#\s*platform:\s*(\S+)", line)
        if m:
            return m.group(1)
    return current_platform_guess()

def export_nerfstudio_methods(lock_dir: Path, lines: list[str]) -> None:
    installed: dict[str, dict] = {}
    for raw in lines:
        line = normalize_pkg_line(raw)
        name = parse_name(line)
        if not is_protected_method_name(name):
            continue
        for key, spec in NERFSTUDIO_METHODS_PROTECTED.items():
            if name in spec["pip_names"]:
                installed[key] = {
                    "locked_requirement": line,
                    "install_ref": spec["install_ref"],
                    "patch_rel": spec["patch_rel"],
                    "pip_names": sorted(spec["pip_names"]),
                    "category": spec.get("category", "method"),
                }
                break
    payload = {"protected_methods": {
        key: {
            "install_ref": spec["install_ref"],
            "patch_rel": spec["patch_rel"],
            "pip_names": sorted(spec["pip_names"]),
            "category": spec.get("category", "method"),
            "locked_requirement": installed.get(key, {}).get("locked_requirement", ""),
            "present_in_lock": key in installed,
        } for key, spec in NERFSTUDIO_METHODS_PROTECTED.items()
    }}
    write_text(nerfstudio_methods_filename(lock_dir), json.dumps(payload, indent=2) + "\n")

def export_nerfstudio_core_overrides(lock_dir: Path, lines: list[str]) -> None:
    installed: dict[str, dict] = {}
    for raw in lines:
        line = normalize_pkg_line(raw)
        name = parse_name(line)
        if not is_core_override_name(name):
            continue
        for key, spec in NERFSTUDIO_CORE_OVERRIDES.items():
            if name in spec["pip_names"]:
                installed[key] = {
                    "locked_requirement": line,
                    "install_ref": spec["install_ref"],
                    "patch_rel": spec["patch_rel"],
                    "pip_names": sorted(spec["pip_names"]),
                    "category": spec.get("category", "core_dependency"),
                    "enforce_as_standard": bool(spec.get("enforce_as_standard", False)),
                }
                break
    payload = {"core_overrides": {
        key: {
            "install_ref": spec["install_ref"],
            "patch_rel": spec["patch_rel"],
            "pip_names": sorted(spec["pip_names"]),
            "category": spec.get("category", "core_dependency"),
            "enforce_as_standard": bool(spec.get("enforce_as_standard", False)),
            "locked_requirement": installed.get(key, {}).get("locked_requirement", ""),
            "present_in_lock": key in installed,
        } for key, spec in NERFSTUDIO_CORE_OVERRIDES.items()
    }}
    write_text(nerfstudio_core_overrides_filename(lock_dir), json.dumps(payload, indent=2) + "\n")

def export_numpy_audit(lock_dir: Path, lines: list[str], plan: dict) -> None:
    rows = []
    for line in lines:
        name = parse_name(line)
        if name.startswith("numpy") or name in {"torch", "torchvision", "torchaudio", "opencv-python", "opencv-contrib-python", "matplotlib", "scipy", "pandas", "pycolmap", "open3d", "tensorflow"}:
            rows.append(line)
    rows.extend([f"PLAN torch_preinstall: {x}" for x in plan.get("torch_preinstall", [])])
    rows.extend([f"PLAN pyg_wheels: {x}" for x in plan.get("pyg_wheels", [])])
    rows.extend([f"PLAN deferred: {x}" for x in plan.get("deferred", [])])
    write_text(numpy_audit_filename(lock_dir), "\n".join(dict.fromkeys(rows)) + "\n")

def export_locks(lock_dir: Path, conda_exe: str | None = None, msvc_mode: str = "") -> int:
    from ns_installer.bootstrap import build_bootstrap_context, run, which, write_msvc_log
    ensure_dir(lock_dir)
    conda_exe = conda_exe or os.environ.get("CONDA_EXE") or which("conda") or which("conda.bat")
    platform_tag = current_platform_guess()
    conda_lock_path: Optional[Path] = None
    if conda_exe and os.environ.get("CONDA_PREFIX"):
        cp = run([conda_exe, "list", "--explicit", "--md5"])
        explicit = cp.stdout
        platform_tag = parse_platform_from_explicit(explicit)
        conda_lock_path = conda_explicit_filename(lock_dir, platform_tag)
        write_text(conda_lock_path, explicit)
        cp_json = run([conda_exe, "list", "--json"])
        write_text(lock_dir / "conda-list.json", cp_json.stdout)
    pip_cp = run([os.sys.executable, "-m", "pip", "freeze", "--all"], check=False)
    pip_lines = [normalize_pkg_line(x) for x in normalize_lines(pip_cp.stdout, kind="pip")]
    write_text(pip_lock_filename(lock_dir), "\n".join(pip_lines) + "\n")
    write_text(replay_pip_filename(lock_dir), "\n".join(compute_replay_lines(pip_lines)) + "\n")
    installer = load_installer_selection(lock_dir)
    effective_msvc = str(installer.get("preferred_msvc") or msvc_mode or os.environ.get("PREFERRED_MSVC") or "").strip()
    ctx = build_bootstrap_context(lock_dir, effective_msvc)
    plan = {
        "numpy_stable": detect_numpy_baseline(pip_lines),
        "torch_preinstall": detect_torch_lines(pip_lines),
        "torch_index": TORCH_INDEX,
        "pyg_wheels": detect_pyg_lines(pip_lines),
        "pyg_index_template": PYG_INDEX_TEMPLATE,
        "tinycudann": {
            "requirement": detect_tcnn_line(pip_lines),
            "cuda_arch": str(installer.get("cuda_arch") or "").strip(),
        },
        "deferred": [x for x in pip_lines if any(p.search(x) for p in DEFER_PATTERNS)],
        "preferred_msvc": effective_msvc,
        "bootstrap_mode": "subprocess-shell-bootstrap",
        "selected_toolset": (ctx.get("selected") or {}).get("toolset_full", ""),
        "selected_installation": (ctx.get("selected") or {}).get("installation", ""),
        "cuda_root": ctx.get("cuda_root", ""),
        "materialized_include": (ctx.get("materialized_env") or {}).get("INCLUDE", ""),
        "materialized_lib": (ctx.get("materialized_env") or {}).get("LIB", ""),
        "materialized_libpath": (ctx.get("materialized_env") or {}).get("LIBPATH", ""),
    }
    write_text(build_plan_filename(lock_dir), json.dumps(plan, indent=2) + "\n")
    export_numpy_audit(lock_dir, pip_lines, plan)
    export_nerfstudio_methods(lock_dir, pip_lines)
    export_nerfstudio_core_overrides(lock_dir, pip_lines)
    write_msvc_log(lock_dir)
    meta = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "platform_guess": platform_tag,
        "conda_lock": conda_lock_path.name if conda_lock_path else None,
        "pip_lock": pip_lock_filename(lock_dir).name,
        "pip_replay": replay_pip_filename(lock_dir).name,
        "build_plan": build_plan_filename(lock_dir).name,
    }
    write_text(meta_filename(lock_dir), json.dumps(meta, indent=2) + "\n")
    return 0
