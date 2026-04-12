from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from ns_installer import DEFAULT_LOCK_DIR, ROOT
from ns_installer.bootstrap import (
    build_bootstrap_context,
    validate_msvc_from_shell,
    which,
)
from ns_installer.build import (
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
from ns_installer.locks import (
    DEFAULT_NUMPY,
    export_locks,
    find_conda_lock,
    load_build_plan,
    load_installer_selection,
    normalize_lines,
    normalize_pkg_line,
    replay_pip_filename,
    split_pip_lock,
    pip_lock_filename,
    read_text,
)
from ns_installer.patches import apply_extra_patches
from ns_installer.methods_registry import (
    discover_method_entrypoints,
    install_methods,
    install_single_method,
    known_method_names,
)

from ns_installer.doctor import main as doctor_main


def diff_summary(expected: list[str], current: list[str], label: str) -> tuple[bool, str]:
    if expected == current:
        return True, f"[OK] {label} matches lock exactly."
    expected_set = set(expected)
    current_set = set(current)
    missing = sorted(expected_set - current_set)
    extra = sorted(current_set - expected_set)
    lines = [f"[FAIL] {label} differs from lock."]
    if missing:
        lines.append("  Missing/changed (first 10):")
        lines.extend([f"    - {x}" for x in missing[:10]])
    if extra:
        lines.append("  Extra/different (first 10):")
        lines.extend([f"    + {x}" for x in extra[:10]])
    return False, "\n".join(lines)


def normalized_current_pip_lines() -> list[str]:
    import subprocess
    import sys
    from ns_installer.bootstrap import run

    try:
        cp = run([sys.executable, "-m", "pip", "freeze", "--all"])
    except subprocess.CalledProcessError:
        cp = run([sys.executable, "-m", "pip", "freeze"])
    return [normalize_pkg_line(x) for x in normalize_lines(cp.stdout, kind="pip")]

def check_locks(lock_dir: Path, conda_exe: str | None = None) -> int:
    from ns_installer.bootstrap import run

    ok = True
    conda_lock = find_conda_lock(lock_dir)
    conda_exe = conda_exe or os.environ.get("CONDA_EXE") or which("conda") or which("conda.bat")

    if conda_lock and conda_exe and os.environ.get("CONDA_PREFIX"):
        current = run([conda_exe, "list", "--explicit", "--md5"]).stdout
        good, msg = diff_summary(
            normalize_lines(read_text(conda_lock), kind="conda"),
            normalize_lines(current, kind="conda"),
            "Conda explicit lock",
        )
        print(msg)
        ok &= good

    pip_lock = pip_lock_filename(lock_dir)
    if pip_lock.exists():
        current = normalized_current_pip_lines()
        good, msg = diff_summary(
            [normalize_pkg_line(x) for x in normalize_lines(read_text(pip_lock), kind="pip")],
            current,
            "pip freeze lock",
        )
        print(msg)
        ok &= good

    return 0 if ok else 2


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
            from ns_installer.bootstrap import print_run
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


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser("deps_lock/core wrapper")
    p.add_argument("--lock-dir", default=str(DEFAULT_LOCK_DIR))
    p.add_argument("--conda-exe", default=os.environ.get("CONDA_EXE"))
    p.add_argument("--msvc-mode", default="", choices=["", "auto", "14.38", "14", "system"])

    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("export")
    sub.add_parser("check")

    rep = sub.add_parser("repin")
    rep.add_argument("--skip-conda", action="store_true")
    rep.add_argument("--force-conda", action="store_true")

    sub.add_parser("core")
    sub.add_parser("patches")
    sub.add_parser("all")

    m = sub.add_parser("method")
    m.add_argument("name")

    doc = sub.add_parser("doctor")
    doc.add_argument("--json", action="store_true")

    args = p.parse_args(argv)
    lock_dir = Path(args.lock_dir).resolve()

    if args.cmd == "export":
        return export_locks(lock_dir, conda_exe=args.conda_exe, msvc_mode=args.msvc_mode)

    if args.cmd == "check":
        return check_locks(lock_dir, conda_exe=args.conda_exe)

    if args.cmd == "repin":
        return repin(
            lock_dir,
            skip_conda=args.skip_conda,
            force_conda=args.force_conda,
            conda_exe=args.conda_exe,
            msvc_mode=args.msvc_mode,
        )

    if args.cmd == "core":
        return install_core(lock_dir, args.msvc_mode)

    if args.cmd == "patches":
        apply_extra_patches(ROOT)
        return 0

    if args.cmd == "method":
        install_single_method(args.name, root=ROOT, lock_dir=lock_dir, msvc_mode=args.msvc_mode)
        return 0

    if args.cmd == "all":
        return install_all(lock_dir, args.msvc_mode)

    if args.cmd == "doctor":
        doctor_args = ["--lock-dir", str(lock_dir), "--msvc-mode", args.msvc_mode]
        if args.json:
            doctor_args.append("--json")
        return doctor_main(doctor_args)

    return 0