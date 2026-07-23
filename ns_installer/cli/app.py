from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from ns_installer import DEFAULT_LOCK_DIR
from ns_installer.cli.commands.doctor import handle_doctor
from ns_installer.cli.commands.gui import handle_gui
from ns_installer.cli.commands.install import (
    handle_all,
    handle_core,
    handle_method,
    handle_methods,
    handle_repin,
)
from ns_installer.cli.commands.methods import (
    add_methods_check_parser,
    add_methods_fix_parser,
    add_methods_list_parser,
    handle_methods_check,
    handle_methods_fix,
    handle_methods_list,
)


MSVC_MODE_CHOICES = ["", "auto", "14.38", "14", "system"]
CUDA_MODE_CHOICES = ["vanilla", "experimental-env"]


def add_common_build_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--msvc-mode", default=None, choices=MSVC_MODE_CHOICES)
    parser.add_argument(
        "--cuda-mode",
        default=None,
        choices=CUDA_MODE_CHOICES,
        help="CUDA mode: 'vanilla' (default, force CUDA 11.8) or 'experimental-env' (use system CUDA).",
    )


def resolve_lock_dir(value: str) -> Path:
    return Path(value).expanduser().resolve()


def resolve_msvc_mode(args: argparse.Namespace) -> str:
    return getattr(args, "msvc_mode", None) or getattr(args, "global_msvc_mode", "auto") or "auto"


def resolve_cuda_mode(args: argparse.Namespace) -> str:
    return getattr(args, "cuda_mode", None) or getattr(args, "global_cuda_mode", "vanilla") or "vanilla"


def print_compat_completion(shell: str) -> int:
    shell = (shell or "").strip().lower()
    if shell not in {"bash", "zsh"}:
        raise SystemExit(f"Unsupported completion shell: {shell}")

    parser = build_parser()

    try:
        import shtab  # type: ignore
    except Exception as e:
        raise SystemExit(
            "Completion generation requires 'shtab'. Install it with: pip install shtab"
        ) from e

    print(shtab.complete(parser, shell=shell))
    return 0


def maybe_handle_tyro_completion(argv: Optional[list[str]]) -> Optional[int]:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        return None

    if args[0] == "--tyro-print-completion":
        if len(args) < 2:
            raise SystemExit("--tyro-print-completion requires a shell name")
        return print_compat_completion(args[1])

    return None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser("ns-install")

    p.add_argument("--lock-dir", default=str(DEFAULT_LOCK_DIR))
    p.add_argument("--msvc-mode", dest="global_msvc_mode", default="auto", choices=MSVC_MODE_CHOICES)
    p.add_argument("--cuda-mode", dest="global_cuda_mode", default="vanilla", choices=CUDA_MODE_CHOICES)

    sub = p.add_subparsers(dest="cmd", required=True)

    core_p = sub.add_parser("core")
    add_common_build_args(core_p)

    methods_p = sub.add_parser("methods")
    add_common_build_args(methods_p)

    add_methods_list_parser(sub)
    add_methods_check_parser(sub)
    add_methods_fix_parser(sub)
    
    method_p = sub.add_parser("method")
    method_p.add_argument("name")
    add_common_build_args(method_p)

    all_p = sub.add_parser("all")
    add_common_build_args(all_p)

    repin_p = sub.add_parser("repin")
    repin_p.add_argument("--skip-conda", action="store_true")
    repin_p.add_argument("--force-conda", action="store_true")
    add_common_build_args(repin_p)

    doctor_p = sub.add_parser("doctor", help="Inspect environment")
    doctor_p.add_argument("--json", action="store_true")
    add_common_build_args(doctor_p)

    sub.add_parser("gui", help="Launch the Gradio training GUI")

    return p


def main(argv: Optional[list[str]] = None) -> int:
    compat_rc = maybe_handle_tyro_completion(argv)
    if compat_rc is not None:
        return compat_rc

    parser = build_parser()
    args = parser.parse_args(argv)

    lock_dir = resolve_lock_dir(args.lock_dir)
    msvc_mode = resolve_msvc_mode(args)
    cuda_mode = resolve_cuda_mode(args)

    if args.cmd == "core":
        return handle_core(
            lock_dir=lock_dir,
            msvc_mode=msvc_mode,
        )

    if args.cmd == "methods":
        return handle_methods(
            lock_dir=lock_dir,
            msvc_mode=msvc_mode,
            cuda_mode=cuda_mode,
        )

    if args.cmd == "methods-list":
        return handle_methods_list(args)

    if args.cmd == "methods-check":
        return handle_methods_check(
            args,
            lock_dir=lock_dir,
            msvc_mode=msvc_mode,
            cuda_mode=cuda_mode,
        )
    
    if args.cmd == "methods-fix":
        return handle_methods_fix(
            args,
            lock_dir=lock_dir,
            msvc_mode=msvc_mode,
            cuda_mode=cuda_mode,
        )
        
    if args.cmd == "method":
        return handle_method(
            name=args.name,
            lock_dir=lock_dir,
            msvc_mode=msvc_mode,
            cuda_mode=cuda_mode,
        )

    if args.cmd == "all":
        return handle_all(
            lock_dir=lock_dir,
            msvc_mode=msvc_mode,
        )

    if args.cmd == "repin":
        return handle_repin(
            lock_dir=lock_dir,
            skip_conda=bool(getattr(args, "skip_conda", False)),
            force_conda=bool(getattr(args, "force_conda", False)),
            msvc_mode=msvc_mode,
        )

    if args.cmd == "doctor":
        return handle_doctor(
            lock_dir=lock_dir,
            msvc_mode=msvc_mode,
            json_output=bool(getattr(args, "json", False)),
        )

    if args.cmd == "gui":
        return handle_gui()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())