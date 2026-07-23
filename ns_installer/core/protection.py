from __future__ import annotations

TCNN_GIT = "git+https://github.com/NVlabs/tiny-cuda-nn/#subdirectory=bindings/torch"
PYCOLMAP_GIT = "git+https://github.com/rmbrualla/pycolmap.git"

NERFSTUDIO_METHODS_PROTECTED = {
    "feature-splatting": {
        "pip_names": {"feature-splatting", "feature_splatting"},
        "install_ref": "git+https://github.com/vuer-ai/feature-splatting",
        "patch_rel": "feature-splatting",
        "category": "method",
    },
    "igs2gs": {
        "pip_names": {"igs2gs"},
        "install_ref": "git+https://github.com/cvachha/instruct-gs2gs",
        "patch_rel": "igs2gs",
        "category": "method",
    },
    "lerf": {
        "pip_names": {"lerf"},
        "install_ref": "git+https://github.com/kerrj/lerf",
        "patch_rel": "lerf",
        "category": "method",
    },
    "livescene": {
        "pip_names": {"livescene"},
        "install_ref": "git+https://github.com/Tavish9/livescene",
        "patch_rel": "livescene",
        "category": "method",
    },
    "nerfplayer": {
        "pip_names": {"nerfplayer"},
        "install_ref": "git+https://github.com/lsongx/nerfplayer-nerfstudio.git",
        "patch_rel": "nerfplayer",
        "category": "method",
    },
    "opennerf": {
        "pip_names": {"opennerf"},
        "install_ref": "git+https://github.com/opennerf/opennerf",
        "patch_rel": "opennerf",
        "category": "method",
    },
    "pynerf": {
        "pip_names": {"pynerf"},
        "install_ref": "git+https://github.com/hturki/pynerf",
        "patch_rel": "pynerf",
        "category": "method",
    },
    "relationfield": {
        "pip_names": {"relationfield"},
        "install_ref": "git+https://github.com/boschresearch/RelationField.git",
        "patch_rel": "relationfield",
        "category": "method",
    },
    "tetra-nerf": {
        "pip_names": {"tetra-nerf", "tetra_nerf"},
        "install_ref": "git+https://github.com/jkulhanek/tetra-nerf",
        "patch_rel": "tetra-nerf",
        "category": "method",
    },
    "zipnerf-pytorch": {
        "pip_names": {"zipnerf", "zipnerf-pytorch"},
        "install_ref": "git+https://github.com/SuLvXiangXin/zipnerf-pytorch.git",
        "patch_rel": "zipnerf-pytorch",
        "category": "method",
    },
    "splatfacto-w": {
        "pip_names": {"splatfacto-w", "splatfactow"},
        "install_ref": "git+https://github.com/KevinXu02/splatfacto-w",
        "patch_rel": "splatfacto-w",
        "category": "method",
    },
}

NERFSTUDIO_CORE_OVERRIDES = {
    "pycolmap": {
        "pip_names": {"pycolmap"},
        "install_ref": PYCOLMAP_GIT,
        "patch_rel": None,
        "category": "core_dependency",
        "enforce_as_standard": True,
    },
}

NERFSTUDIO_METHODS_PROTECTED_NAMES = {
    alias
    for spec in NERFSTUDIO_METHODS_PROTECTED.values()
    for alias in spec["pip_names"]
}
NERFSTUDIO_CORE_OVERRIDE_NAMES = {
    alias
    for spec in NERFSTUDIO_CORE_OVERRIDES.values()
    for alias in spec["pip_names"]
}

PROTECTED_GIT_PACKAGES = {
    "tinycudann": TCNN_GIT,
    "tiny-cuda-nn": TCNN_GIT,
    "pycolmap": PYCOLMAP_GIT,
}

def is_protected_method_name(name: str) -> bool:
    return (name or "").strip().lower().replace("_", "-") in NERFSTUDIO_METHODS_PROTECTED_NAMES

def is_core_override_name(name: str) -> bool:
    return (name or "").strip().lower().replace("_", "-") in NERFSTUDIO_CORE_OVERRIDE_NAMES
