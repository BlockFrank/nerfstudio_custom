from __future__ import annotations

import importlib
import subprocess
import sys
from importlib.metadata import entry_points
from pathlib import Path

from ns_installer import ROOT
from ns_installer.core.build import (
    install_editable_project,
    maybe_build_method_native,
    repin_after_method_install,
)
from ns_installer.core.patches import apply_repo_patches


def method_specs() -> dict[str, dict]:
    return {
        "splatfacto-w": {
            "folder": "splatfacto-w",
            "module": "splatfactow",
            "train_name": "splatfacto-w",
            "entrypoint_group": "nerfstudio.method_configs",
            "preferred_repo": "https://github.com/BlockFrank/splatfacto-w_reforged",
            "upstream_repo": "https://github.com/BlockFrank/splatfacto-w_reforged",
            "patch_rel": "splatfacto-w",
            "needs_cpp_build": False,
            "windows_build": None,
            "post_install_repin": False,
        },
        "zipnerf": {
            "folder": "zipnerf-pytorch",
            "module": "zipnerf_ns",
            "train_name": "zipnerf",
            "entrypoint_group": "nerfstudio.method_configs",
            "preferred_repo": "https://github.com/SuLvXiangXin/zipnerf-pytorch.git",
            "upstream_repo": "https://github.com/SuLvXiangXin/zipnerf-pytorch.git",
            "patch_rel": "zipnerf-pytorch",
            "needs_cpp_build": True,
            "windows_build": "zipnerf_cuda",
            "post_install_repin": False,
        },
        "tetra-nerf": {
            "folder": "tetra-nerf",
            "module": "tetranerf",
            "train_name": "tetra-nerf",
            "entrypoint_group": "nerfstudio.method_configs",
            "preferred_repo": "https://github.com/jkulhanek/tetra-nerf",
            "upstream_repo": "https://github.com/jkulhanek/tetra-nerf",
            "patch_rel": "tetra-nerf",
            "needs_cpp_build": True,
            "windows_build": "tetra",
            "post_install_repin": False,
            "install_mode": "editable"
        },
        "opennerf": {
            "folder": "opennerf",
            "module": "opennerf",
            "train_name": "opennerf",
            "entrypoint_group": "nerfstudio.method_configs",
            "preferred_repo": "https://github.com/opennerf/opennerf",
            "upstream_repo": "https://github.com/opennerf/opennerf",
            "patch_rel": "opennerf",
            "needs_cpp_build": False,
            "windows_build": None,
            "post_install_repin": False,
            "install_mode": "editable"
        },
        "igs2gs": {
            "folder": "instruct-gs2gs",
            "module": "igs2gs",
            "train_name": "igs2gs",
            "entrypoint_group": "nerfstudio.method_configs",
            "preferred_repo": "https://github.com/cvachha/instruct-gs2gs",
            "upstream_repo": "https://github.com/cvachha/instruct-gs2gs",
            "patch_rel": "igs2gs",
            "needs_cpp_build": False,
            "windows_build": None,
            "post_install_repin": False,
            "install_mode": "editable"
        },
        "lerf": {
            "folder": "lerf",
            "module": "lerf",
            "train_name": "lerf",
            "entrypoint_group": "nerfstudio.method_configs",
            "preferred_repo": "https://github.com/BlockFrank/lerf",
            "upstream_repo": "https://github.com/BlockFrank/lerf",
            "patch_rel": "lerf",
            "needs_cpp_build": False,
            "windows_build": None,
            "post_install_repin": False,
            "install_mode": "editable"
        },
        "NeRFtoGSandBack": {
            "folder": "NeRFtoGSandBack",
            "module": "nerftogsandback",
            "train_name": "NeRFtoGSandBack",
            "entrypoint_group": "nerfstudio.method_configs",
            "preferred_repo": "https://github.com/grasp-lyrl/NeRFtoGSandBack",
            "upstream_repo": "https://github.com/grasp-lyrl/NeRFtoGSandBack",
            "patch_rel": "NeRFtoGSandBack",
            "needs_cpp_build": False,
            "windows_build": None,
            "post_install_repin": False,
            "install_mode": "custom",
        },
        "relationfield": {
            "folder": "relationfield",
            "module": "relationfield",
            "train_name": "relationfield",
            "entrypoint_group": "nerfstudio.method_configs",
            "preferred_repo": "https://github.com/boschresearch/RelationField.git",
            "upstream_repo": "https://github.com/boschresearch/RelationField.git",
            "patch_rel": "relationfield",
            "needs_cpp_build": False,
            "windows_build": None,
            "post_install_repin": False,
        },
        "pynerf": {
            "folder": "pynerf",
            "module": "pynerf",
            "train_name": "pynerf",
            "entrypoint_group": "nerfstudio.method_configs",
            "preferred_repo": "https://github.com/hturki/pynerf",
            "upstream_repo": "https://github.com/hturki/pynerf",
            "patch_rel": "pynerf",
            "needs_cpp_build": False,
            "windows_build": None,
            "post_install_repin": False,
        },
    }


def known_method_names() -> list[str]:
    return sorted(method_specs().keys())


def discover_method_entrypoints() -> dict[str, str]:
    return {ep.name: ep.value for ep in entry_points(group="nerfstudio.method_configs")}


def discover_dataparser_entrypoints() -> dict[str, str]:
    return {ep.name: ep.value for ep in entry_points(group="nerfstudio.dataparser_configs")}


def normalize_entrypoint_train_name(entrypoint_name: str) -> str:
    mapping = {
        "zipnerf_ns": "zipnerf",
        "splatfactow": "splatfacto-w",
    }
    return mapping.get(entrypoint_name, entrypoint_name)


def resolved_method_catalog() -> list[dict]:
    """
    Build a canonical method catalog that merges:
    - discovered Python entrypoints (primary, most reliable)
    - methods currently visible through ns-train (optional enrichment)
    - installer-known methods (fallback)

    Returned records are safe for GUI display and command generation.
    """
    specs = method_specs()

    discovered_entrypoints: dict[str, str] = {}
    available_methods: list[str] = []

    try:
        discovered_entrypoints = discover_method_entrypoints()
    except Exception:
        discovered_entrypoints = {}

    try:
        from ns_installer.cli.commands.methods import discover_all_trainable_methods

        info = discover_all_trainable_methods()
        raw_methods = info.get("methods", [])
        if isinstance(raw_methods, list):
            available_methods = [str(x).strip() for x in raw_methods if str(x).strip()]
    except Exception:
        available_methods = []

    rows: list[dict] = []
    seen_train_names: set[str] = set()

    # 1) Entrypoint-discovered methods first
    for entrypoint_name in sorted(discovered_entrypoints.keys()):
        train_name = normalize_entrypoint_train_name(entrypoint_name)
        installer_name = None

        for k, spec in specs.items():
            spec_train_name = str(spec.get("train_name", k)).strip()
            if spec_train_name == train_name or k == train_name or k == entrypoint_name:
                installer_name = k
                break

        rows.append(
            {
                "display_name": train_name,
                "train_name": train_name,
                "installer_name": installer_name,
                "entrypoint_name": entrypoint_name,
                "source": "entrypoint",
            }
        )
        seen_train_names.add(train_name)

    # 2) Methods actually visible in ns-train right now
    for train_name in available_methods:
        if train_name in seen_train_names:
            continue

        installer_name = None
        for k, spec in specs.items():
            if str(spec.get("train_name", k)).strip() == train_name or k == train_name:
                installer_name = k
                break

        entrypoint_name = None
        for ep_name in discovered_entrypoints.keys():
            if normalize_entrypoint_train_name(ep_name) == train_name:
                entrypoint_name = ep_name
                break

        rows.append(
            {
                "display_name": train_name,
                "train_name": train_name,
                "installer_name": installer_name,
                "entrypoint_name": entrypoint_name,
                "source": "available",
            }
        )
        seen_train_names.add(train_name)

    # 3) Installer-known methods as fallback
    for installer_name, spec in specs.items():
        train_name = str(spec.get("train_name", installer_name)).strip()

        if train_name in seen_train_names:
            continue

        entrypoint_name = None
        for ep_name in discovered_entrypoints.keys():
            if normalize_entrypoint_train_name(ep_name) == train_name:
                entrypoint_name = ep_name
                break

        rows.append(
            {
                "display_name": installer_name,
                "train_name": train_name,
                "installer_name": installer_name,
                "entrypoint_name": entrypoint_name,
                "source": "known",
            }
        )
        seen_train_names.add(train_name)

    return rows

def probe_entrypoint_load(entrypoint_name: str) -> tuple[bool, str]:
    try:
        eps = entry_points(group="nerfstudio.method_configs")
        for ep in eps:
            if ep.name == entrypoint_name:
                ep.load()
                return True, "OK"
        return False, f"Entry point not found: {entrypoint_name}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def probe_module_import(module_name: str | None) -> tuple[bool, str]:
    if not module_name:
        return False, "No module declared"
    try:
        importlib.import_module(module_name)
        return True, "OK"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    
def gui_method_choices() -> list[tuple[str, str]]:
    """
    Returns Gradio-friendly choices:
    (label shown to user, value returned by dropdown)

    Returned value is always the canonical train_name.
    """
    rows = resolved_method_catalog()
    choices: list[tuple[str, str]] = []

    for row in rows:
        installer_name = row.get("installer_name")
        train_name = row["train_name"]
        source = row["source"]

        if installer_name and installer_name != train_name:
            label = f"{train_name}  • {source}  (installer: {installer_name})"
        else:
            label = f"{train_name}  • {source}"

        choices.append((label, train_name))

    return choices


def probe_train_method_help(train_name: str) -> dict:
    """
    Probe whether a method is effectively trainable by asking for
    method-specific help from ns-train.
    """
    cmd_variants = [
        ["ns-train", train_name, "--help"],
        [sys.executable, "-m", "nerfstudio.scripts.train", train_name, "--help"],
    ]

    last_error = None
    last_output = ""
    last_returncode = None

    for cmd in cmd_variants:
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            output = (proc.stdout or "") + "\n" + (proc.stderr or "")
            last_output = output
            last_returncode = proc.returncode

            if proc.returncode == 0:
                return {
                    "ok": True,
                    "command": " ".join(cmd),
                    "returncode": proc.returncode,
                    "output": output,
                    "error": None,
                }

            last_error = f"returncode={proc.returncode}"
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"

    return {
        "ok": False,
        "command": None,
        "returncode": last_returncode,
        "output": last_output,
        "error": last_error or "Unknown error",
    }


def check_method_health(row: dict, *, run_cli_probe: bool = False) -> dict:
    enriched = dict(row)

    installer_name = row.get("installer_name")
    entrypoint_name = row.get("entrypoint_name")

    enriched["is_known"] = installer_name is not None
    enriched["is_registered"] = entrypoint_name is not None
    enriched["listed_by_train_cli"] = (row.get("source") == "available")

    spec = method_specs().get(installer_name) if installer_name else None
    module_name = spec.get("module") if spec else None

    ep_ok, ep_msg = (
        probe_entrypoint_load(entrypoint_name)
        if entrypoint_name
        else (False, "No entrypoint")
    )
    mod_ok, mod_msg = (
        probe_module_import(module_name)
        if module_name
        else (False, "No module mapping")
    )

    enriched["entrypoint_load_ok"] = ep_ok
    enriched["entrypoint_load_msg"] = ep_msg
    enriched["module_import_ok"] = mod_ok
    enriched["module_import_msg"] = mod_msg

    if run_cli_probe:
        cli_probe = probe_train_method_help(row["train_name"])
        enriched["cli_help_ok"] = bool(cli_probe.get("ok"))
        enriched["probe_command"] = cli_probe.get("command")
        enriched["probe_returncode"] = cli_probe.get("returncode")
        enriched["probe_error"] = cli_probe.get("error")

        output = (cli_probe.get("output") or "").strip()
        if len(output) > 1200:
            output = output[:1200] + "\n...[truncated]..."
        enriched["probe_output"] = output
    else:
        enriched["cli_help_ok"] = None
        enriched["probe_command"] = None
        enriched["probe_returncode"] = None
        enriched["probe_error"] = None
        enriched["probe_output"] = ""

    enriched["structurally_ready"] = (
        (enriched["is_registered"] and enriched["entrypoint_load_ok"])
        or (enriched["is_known"] and enriched["module_import_ok"])
    )

    enriched["ready"] = (
        enriched["structurally_ready"]
        or enriched["listed_by_train_cli"]
    )

    return enriched

def resolved_method_health_catalog(*, run_cli_probe: bool = False) -> list[dict]:
    rows: list[dict] = []

    for row in resolved_method_catalog():
        try:
            rows.append(check_method_health(row, run_cli_probe=run_cli_probe))
        except Exception as e:
            broken = dict(row)
            broken["is_known"] = row.get("installer_name") is not None
            broken["is_registered"] = row.get("entrypoint_name") is not None
            broken["listed_by_train_cli"] = (row.get("source") == "available")
            broken["entrypoint_load_ok"] = False
            broken["entrypoint_load_msg"] = f"{type(e).__name__}: {e}"
            broken["module_import_ok"] = False
            broken["module_import_msg"] = f"{type(e).__name__}: {e}"
            broken["cli_help_ok"] = None
            broken["probe_command"] = None
            broken["probe_returncode"] = None
            broken["probe_error"] = f"{type(e).__name__}: {e}"
            broken["probe_output"] = ""
            broken["structurally_ready"] = False
            broken["ready"] = broken["listed_by_train_cli"]
            rows.append(broken)

    return rows

def ready_methods() -> list[dict]:
    return [row for row in resolved_method_health_catalog(run_cli_probe=False) if row.get("ready")]

def effective_trainable_methods() -> list[dict]:
    return [row for row in resolved_method_health_catalog(run_cli_probe=True) if row.get("cli_help_ok")]

def resolved_method_catalog_debug_text() -> str:
    rows = resolved_method_catalog()
    lines = []
    for row in rows:
        lines.append(
            f"{row['display_name']} | train={row['train_name']} | "
            f"installer={row.get('installer_name')} | "
            f"entrypoint={row.get('entrypoint_name')} | "
            f"source={row['source']}"
        )
    return "\n".join(lines)


def install_single_method(
    name: str,
    root: Path | None = None,
    lock_dir: Path | None = None,
    msvc_mode: str = "",
    cuda_mode: str = "vanilla",
) -> None:
    root = root or ROOT
    specs = method_specs()

    if name not in specs:
        raise ValueError(f"Unknown method: {name}")

    spec = specs[name]
    path = root / spec["folder"]

    if not path.exists():
        raise FileNotFoundError(f"Missing repo: {path}")

    patch_rel = spec.get("patch_rel")
    if patch_rel:
        apply_repo_patches(root, patch_rel)

    install_editable_project(
        path,
        lock_dir=lock_dir,
        msvc_mode=msvc_mode,
        cuda_mode=cuda_mode,
        no_deps=True,
        no_build_isolation=bool(spec.get("needs_cpp_build", False)),
    )

    maybe_build_method_native(
        name,
        path,
        lock_dir=lock_dir,
        msvc_mode=msvc_mode,
        cuda_mode=cuda_mode,
    )

    if spec.get("post_install_repin", True) and lock_dir is not None:
        print("[INFO] Running repin after method installation...")
        repin_after_method_install(lock_dir, msvc_mode, cuda_mode=cuda_mode)
        print(f"[INSTALL] {name} -> {path}")
    else:
        print(f"[INFO] {name} Method installed successfully.")
        print("[INFO] Automatic repin skipped.")


def install_methods(
    root: Path | None = None,
    only: list[str] | None = None,
    lock_dir: Path | None = None,
    msvc_mode: str = "",
    cuda_mode: str = "vanilla",
) -> None:
    for name in (only or known_method_names()):
        install_single_method(
            name,
            root=root,
            lock_dir=lock_dir,
            msvc_mode=msvc_mode,
            cuda_mode=cuda_mode,
        )


def validate_method_install(name: str, root: Path | None = None) -> tuple[bool, str]:
    specs = method_specs()
    if name not in specs:
        return False, f"Unknown method: {name}"

    module = specs[name]["module"]
    try:
        importlib.import_module(module)
        return True, f"OK: module '{module}' importable"
    except Exception as e:
        return False, f"FAIL: module '{module}' not importable: {type(e).__name__}: {e}"

def clone_method_repo(name: str, root: Path | None = None) -> Path:
    root = root or ROOT
    spec = method_specs()[name]

    repo = spec.get("preferred_repo") or spec.get("upstream_repo")
    if not repo:
        raise ValueError(f"No repo URL configured for method: {name}")

    dest = root / spec["folder"]
    if dest.exists():
        return dest

    print(f"[FIX] Cloning {name} from {repo}")
    subprocess.run(["git", "clone", repo, str(dest)], check=True)
    return dest


def fix_single_method(
    name: str,
    root: Path | None = None,
    lock_dir: Path | None = None,
    msvc_mode: str = "",
    cuda_mode: str = "vanilla",
    pull: bool = False,
) -> dict:
    root = root or ROOT
    spec = method_specs()[name]
    path = root / spec["folder"]

    before = next(
        (r for r in resolved_method_health_catalog(run_cli_probe=False)
         if r.get("train_name") == name or r.get("installer_name") == name),
        None,
    )

    if not path.exists():
        clone_method_repo(name, root=root)
    elif pull:
        subprocess.run(["git", "-C", str(path), "pull"], check=False)

    patch_rel = spec.get("patch_rel")
    if patch_rel:
        apply_repo_patches(root, patch_rel)

    install_editable_project(
        path,
        lock_dir=lock_dir,
        msvc_mode=msvc_mode,
        cuda_mode=cuda_mode,
        no_deps=True,
        no_build_isolation=bool(spec.get("needs_cpp_build", False)),
    )

    maybe_build_method_native(
        name,
        path,
        lock_dir=lock_dir,
        msvc_mode=msvc_mode,
        cuda_mode=cuda_mode,
    )

    if spec.get("post_install_repin", False) and lock_dir is not None:
        repin_after_method_install(lock_dir, msvc_mode, cuda_mode=cuda_mode)

    after = next(
        (r for r in resolved_method_health_catalog(run_cli_probe=False)
         if r.get("train_name") == name or r.get("installer_name") == name),
        None,
    )

    return {
        "name": name,
        "before": before,
        "after": after,
        "path": str(path),
    }


def fix_methods(
    names: list[str],
    root: Path | None = None,
    lock_dir: Path | None = None,
    msvc_mode: str = "",
    cuda_mode: str = "vanilla",
    pull: bool = False,
) -> list[dict]:
    results: list[dict] = []

    for name in names:
        try:
            results.append(
                fix_single_method(
                    name,
                    root=root,
                    lock_dir=lock_dir,
                    msvc_mode=msvc_mode,
                    cuda_mode=cuda_mode,
                    pull=pull,
                )
            )
        except Exception as e:
            results.append(
                {
                    "name": name,
                    "error": f"{type(e).__name__}: {e}",
                }
            )

    return results