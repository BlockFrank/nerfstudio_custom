from __future__ import annotations

import importlib
from importlib.metadata import entry_points
from pathlib import Path

from ns_installer import ROOT
from ns_installer.build import install_editable_project, maybe_build_method_native, maybe_build_method_native, repin_after_method_install
from ns_installer.patches import apply_repo_patches


def method_specs() -> dict[str, dict]:
    return {
        "splatfacto-w": {
            "folder": "splatfacto-w",
            "module": "splatfactow",
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
            "entrypoint_group": "nerfstudio.method_configs",
            "preferred_repo": "https://github.com/jkulhanek/tetra-nerf",
            "upstream_repo": "https://github.com/jkulhanek/tetra-nerf",
            "patch_rel": "tetra-nerf",
            "needs_cpp_build": True,
            "windows_build": "tetra",
            "post_install_repin": False,
        },
        "opennerf": {
            "folder": "opennerf",
            "module": "opennerf",
            "entrypoint_group": "nerfstudio.method_configs",
            "preferred_repo": "https://github.com/opennerf/opennerf",
            "upstream_repo": "https://github.com/opennerf/opennerf",
            "patch_rel": "opennerf",
            "needs_cpp_build": False,
            "windows_build": None,
            "post_install_repin": False,
        },
        "igs2gs": {
            "folder": "instruct-gs2gs",
            "module": "igs2gs",
            "entrypoint_group": "nerfstudio.method_configs",
            "preferred_repo": "https://github.com/cvachha/instruct-gs2gs",
            "upstream_repo": "https://github.com/cvachha/instruct-gs2gs",
            "patch_rel": "igs2gs",
            "needs_cpp_build": False,
            "windows_build": None,
            "post_install_repin": False,
        },
        "lerf": {
            "folder": "lerf",
            "module": "lerf",
            "entrypoint_group": "nerfstudio.method_configs",
            "preferred_repo": "https://github.com/BlockFrank/lerf",
            "upstream_repo": "https://github.com/BlockFrank/lerf",
            "patch_rel": "lerf",
            "needs_cpp_build": False,
            "windows_build": None,
            "post_install_repin": False,
        },
        "NeRFtoGSandBack": {
            "folder": "NeRFtoGSandBack",
            "module": "nerftogsandback",
            "entrypoint_group": "nerfstudio.method_configs",
            "preferred_repo": "https://github.com/grasp-lyrl/NeRFtoGSandBack",
            "upstream_repo": "https://github.com/grasp-lyrl/NeRFtoGSandBack",
            "patch_rel": "NeRFtoGSandBack",
            "needs_cpp_build": False,
            "windows_build": None,
            "post_install_repin": False,
        },
        "relationfield": {
            "folder": "relationfield",
            "module": "relationfield",
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
        repin_after_method_install(lock_dir, msvc_mode, cuda_mode=cuda_mode)  # ✅ PATCH
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