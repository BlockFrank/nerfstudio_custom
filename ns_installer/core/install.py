from __future__ import annotations

import os
from pathlib import Path

from ns_installer import DEFAULT_LOCK_DIR, ROOT
from ns_installer.core.bootstrap import (
    build_bootstrap_context,
    validate_msvc_from_shell,
    which,
)
from ns_installer.core.build import (
    choose_conda_restore_cmd,
    current_tcnn_arch,
    ensure_numpy_stable,
    install_av,
    install_deferred,
    install_packaging_base,
    install_pyg_wheels,
    install_remaining_from_full_lock,
    install_requirements_file,
    install_tcnn,
    install_torch_preinstall,
    print_strict_alignment_status,
    repin_after_method_install,
)
from ns_installer.core.locks import (
    DEFAULT_NUMPY,
    find_conda_lock,
    load_build_plan,
    load_installer_selection,
    replay_pip_filename,
    split_pip_lock,
    pip_lock_filename,
    read_text,
)
from ns_installer.core.patches import apply_extra_patches
from ns_installer.core.methods import install_methods

def repin(
    lock_dir: Path,
    *,
    skip_conda: bool = False,
    force_conda: bool = False,
    conda_exe: str | None = None,
    msvc_mode: str = "",
) -> int:
    conda_lock = find_conda_lock(lock_dir)
    if conda_lock and not skip_conda:
        conda_exe = conda_exe or os.environ.get("CONDA_EXE") or which("conda") or which("conda.bat")
        if force_conda and conda_exe and os.environ.get("CONDA_PREFIX"):
            from ns_installer.core.bootstrap import print_run
            print_run(choose_conda_restore_cmd(conda_exe, conda_lock))

    installer = load_installer_selection(lock_dir)
    effective_msvc = str(
        installer.get("preferred_msvc") or msvc_mode or os.environ.get("PREFERRED_MSVC") or ""
    ).strip()

    ctx = build_bootstrap_context(lock_dir, effective_msvc)
    ok, errors = validate_msvc_from_shell(lock_dir, ctx)
    if not ok:
        for err in errors:
            print(f"[ERR] {err}")
        return 2

    pip_lock = replay_pip_filename(lock_dir)
    pip_lock = pip_lock if pip_lock.exists() else pip_lock_filename(lock_dir)
    if not pip_lock.exists():
        print("[INFO] No pip lock found; nothing to repin.")
        return 0

    plan = load_build_plan(lock_dir)
    numpy_spec = plan.get("numpy_stable") or DEFAULT_NUMPY
    tcnn_arch = str((plan.get("tinycudann") or {}).get("cuda_arch", "")).strip() or current_tcnn_arch()

    torch_lines, pyg_lines, tcnn_line, bulk, deferred, av_lines = split_pip_lock(read_text(pip_lock), lock_dir)

    state: dict = {}
    install_packaging_base(lock_dir, effective_msvc)
    ensure_numpy_stable(lock_dir, effective_msvc, numpy_spec, state, reason="bootstrap")
    install_torch_preinstall(lock_dir, effective_msvc, torch_lines, numpy_spec, state)
    ensure_numpy_stable(lock_dir, effective_msvc, numpy_spec, state, reason="post-torch")
    install_pyg_wheels(lock_dir, effective_msvc, torch_lines, pyg_lines)
    install_tcnn(lock_dir, effective_msvc, tcnn_line, tcnn_arch)
    install_requirements_file(lock_dir, effective_msvc, bulk, lock_dir / ".tmp-bulk-install.txt")
    ensure_numpy_stable(lock_dir, effective_msvc, numpy_spec, state, reason="post-bulk")
    install_remaining_from_full_lock(lock_dir, effective_msvc)
    ensure_numpy_stable(lock_dir, effective_msvc, numpy_spec, state, reason="post-full-remaining")
    install_deferred(lock_dir, effective_msvc, deferred)
    ensure_numpy_stable(lock_dir, effective_msvc, numpy_spec, state, reason="post-deferred")
    install_av(lock_dir, effective_msvc, av_lines)
    repin_after_method_install(lock_dir, effective_msvc)
    print_strict_alignment_status(lock_dir)
    return 0


def install_core(lock_dir: Path = DEFAULT_LOCK_DIR, msvc_mode: str = "") -> int:
    apply_extra_patches(ROOT)
    return repin(lock_dir, skip_conda=True, msvc_mode=msvc_mode)


def install_all(lock_dir: Path = DEFAULT_LOCK_DIR, msvc_mode: str = "") -> int:
    rc = install_core(lock_dir, msvc_mode)
    if rc != 0:
        return rc
    install_methods(root=ROOT, lock_dir=lock_dir, msvc_mode=msvc_mode)
    return 0