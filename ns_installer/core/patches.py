from __future__ import annotations

import filecmp
import shutil
from pathlib import Path
from typing import Iterable

PATCHABLE_REPOS: tuple[str, ...] = (
    "lerf",
    "tetra-nerf",
    "zipnerf-pytorch",
    "opennerf",
    "NeRFtoGSandBack",
    "relationfield",
    "pynerf",
    "splatfacto-w",
    "feature-splatting",
    "igs2gs",
    "livescene",
    "nerfplayer",
)

SKIP_SUFFIXES: tuple[str, ...] = (".diff", ".patch", ".patched", ".tensorpatch")
SKIP_FILENAMES: set[str] = {".DS_Store", "Thumbs.db"}

def _should_skip_patch_file(path: Path) -> bool:
    return path.name in SKIP_FILENAMES or any(path.name.endswith(s) for s in SKIP_SUFFIXES)

def _iter_patch_files(repo_patch_root: Path) -> Iterable[Path]:
    for src in repo_patch_root.rglob("*"):
        if src.is_dir() or _should_skip_patch_file(src):
            continue
        yield src

def _safe_copy_with_backup(src: Path, dst: Path, *, create_missing: bool, make_backup: bool) -> str:
    if not dst.exists():
        if not create_missing:
            return "missing-target"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return "created"
    try:
        same = filecmp.cmp(src, dst, shallow=False)
    except Exception:
        same = False
    if same:
        return "unchanged"
    if make_backup:
        backup = dst.with_suffix(dst.suffix + ".orig")
        if not backup.exists():
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dst, backup)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return "patched"

def list_available_patch_roots(root_dir: Path) -> list[str]:
    patch_root = root_dir / "Extra-Methods-Patches"
    if not patch_root.exists():
        return []
    return sorted([p.name for p in patch_root.iterdir() if p.is_dir()])

def apply_repo_patches(root_dir: Path, repo_name: str, *, create_missing: bool = False, make_backup: bool = True) -> int:
    patch_root = root_dir / "Extra-Methods-Patches"
    repo_patch_root = patch_root / repo_name
    repo_real_root = root_dir / repo_name
    if not repo_patch_root.exists():
        print(f"[INFO] No patch tree for repo '{repo_name}'; skipping.")
        return 0
    if not repo_real_root.exists():
        print(f"[WARN] Repo root missing for patch '{repo_name}': {repo_real_root}")
        return 0
    print(f"[INFO] Applying patches for repo: {repo_name}")
    changed = 0
    missing = 0
    unchanged = 0
    for src in _iter_patch_files(repo_patch_root):
        rel = src.relative_to(repo_patch_root)
        dst = repo_real_root / rel
        result = _safe_copy_with_backup(src, dst, create_missing=create_missing, make_backup=make_backup)
        if result == "patched":
            changed += 1
            print(f"[PATCH] {repo_name}/{rel}")
        elif result == "created":
            changed += 1
            print(f"[CREATE] {repo_name}/{rel}")
        elif result == "unchanged":
            unchanged += 1
        else:
            missing += 1
            print(f"[WARN] Target missing for patch: {dst}")
    print(f"[INFO] Repo '{repo_name}' done: changed={changed}, unchanged={unchanged}, missing-targets={missing}")
    return changed

def apply_extra_patches(root_dir: Path, *, create_missing: bool = False, make_backup: bool = True, include_unknown_patch_roots: bool = False) -> None:
    patch_root = root_dir / "Extra-Methods-Patches"
    if not patch_root.exists():
        print("[INFO] No Extra-Methods-Patches directory found; skipping.")
        return
    available = list_available_patch_roots(root_dir)
    if not available:
        print("[INFO] Extra-Methods-Patches exists but contains no patch roots; skipping.")
        return
    print("[INFO] Applying external patch trees...")
    repo_names: list[str] = [name for name in PATCHABLE_REPOS if (patch_root / name).exists()]
    if include_unknown_patch_roots:
        extras = [name for name in available if name not in repo_names]
        repo_names.extend(extras)
    total_changed = 0
    for repo_name in repo_names:
        total_changed += apply_repo_patches(root_dir, repo_name, create_missing=create_missing, make_backup=make_backup)
    print(f"[INFO] External patch application complete. Total changed/created files: {total_changed}")
