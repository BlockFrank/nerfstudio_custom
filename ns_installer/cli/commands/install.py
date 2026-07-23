from __future__ import annotations

import argparse
from pathlib import Path

from ns_installer import ROOT
from ns_installer.core import install_all, install_core, repin
from ns_installer.core.methods import install_methods, install_single_method


def handle_core(
    *,
    lock_dir: Path,
    msvc_mode: str,
) -> int:
    return int(install_core(lock_dir, msvc_mode) or 0)


def handle_methods(
    *,
    lock_dir: Path,
    msvc_mode: str,
    cuda_mode: str,
) -> int:
    install_methods(ROOT, lock_dir=lock_dir, msvc_mode=msvc_mode, cuda_mode=cuda_mode)
    return 0


def handle_method(
    *,
    name: str,
    lock_dir: Path,
    msvc_mode: str,
    cuda_mode: str,
) -> int:
    install_single_method(
        name,
        ROOT,
        lock_dir=lock_dir,
        msvc_mode=msvc_mode,
        cuda_mode=cuda_mode,
    )
    return 0


def handle_all(
    *,
    lock_dir: Path,
    msvc_mode: str,
) -> int:
    return int(install_all(lock_dir, msvc_mode) or 0)


def handle_repin(
    *,
    lock_dir: Path,
    skip_conda: bool,
    force_conda: bool,
    msvc_mode: str,
) -> int:
    return int(
        repin(
            lock_dir,
            skip_conda=skip_conda,
            force_conda=force_conda,
            msvc_mode=msvc_mode,
        )
        or 0
    )