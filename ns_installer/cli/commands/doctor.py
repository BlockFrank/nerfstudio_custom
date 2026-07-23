from __future__ import annotations

from pathlib import Path

from ns_installer.core.doctor import main as doctor_main


def handle_doctor(
    *,
    lock_dir: Path,
    msvc_mode: str,
    json_output: bool,
) -> int:
    doctor_argv = ["--lock-dir", str(lock_dir), "--msvc-mode", msvc_mode]
    if json_output:
        doctor_argv.append("--json")
    return int(doctor_main(doctor_argv) or 0)