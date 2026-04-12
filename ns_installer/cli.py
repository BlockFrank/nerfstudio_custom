from __future__ import annotations
import argparse
import sys
from pathlib import Path
from typing import Optional
import re
import subprocess

from ns_installer import DEFAULT_LOCK_DIR, ROOT
from ns_installer.core import install_all, install_core, repin
from ns_installer.doctor import main as doctor_main
from ns_installer.methods_registry import discover_method_entrypoints, install_methods, install_single_method
from ns_installer.patches import apply_extra_patches, apply_repo_patches


MSVC_MODE_CHOICES = ["", "auto", "14.38", "14", "system"]
CUDA_MODE_CHOICES = ["vanilla", "experimental-env"]


def _add_common_build_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--msvc-mode", default=None, choices=MSVC_MODE_CHOICES)
    parser.add_argument(
        "--cuda-mode",
        default=None,
        choices=CUDA_MODE_CHOICES,
        help="CUDA mode: 'vanilla' (default, force CUDA 11.8) or 'experimental-env' (use system CUDA).",
    )


def _resolve_lock_dir(value: str) -> Path:
    return Path(value).expanduser().resolve()


def _resolve_msvc_mode(args: argparse.Namespace) -> str:
    return getattr(args, "msvc_mode", None) or getattr(args, "global_msvc_mode", "auto") or "auto"


def _resolve_cuda_mode(args: argparse.Namespace) -> str:
    return getattr(args, "cuda_mode", None) or getattr(args, "global_cuda_mode", "vanilla") or "vanilla"


def _print_compat_completion(shell: str) -> int:
    """
    Compatibility shim for tools that expect Tyro-style completion flags.

    We are argparse-based, not Tyro-based, so we generate completion output
    through shtab if available. This is enough for ns-install-cli, which only
    expects the command to succeed and print a shell completion script.
    """
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


def _maybe_handle_tyro_completion(argv: Optional[list[str]]) -> Optional[int]:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        return None

    if args[0] == "--tyro-print-completion":
        if len(args) < 2:
            raise SystemExit("--tyro-print-completion requires a shell name")
        return _print_compat_completion(args[1])

    return None

def _extract_methods_from_ns_train_help(text: str) -> list[str]:
    """
    Parse `ns-train --help` output and extract the method subcommand names.

    We look for the usage block:
        usage: ns-train [-h] {a,b,c,...}

    and parse the comma-separated items inside the braces.
    """
    match = re.search(r"usage:\s*ns-train\s+\[-h\]\s*\{([^}]*)\}", text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return []

    raw = match.group(1)
    parts = [p.strip() for p in raw.replace("\n", "").split(",")]
    methods = [p for p in parts if p and not p.startswith("...")]
    return sorted(dict.fromkeys(methods))


def discover_all_trainable_methods() -> dict[str, list[str] | str]:
    """
    Ask the actual ns-train CLI what methods are available in the current environment.
    This includes built-in nerfstudio methods and installed external/plugin methods.
    """
    cmd_variants = [
        ["ns-train", "--help"],
        [sys.executable, "-m", "nerfstudio.scripts.train", "--help"],
    ]

    last_error = None
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
            methods = _extract_methods_from_ns_train_help(output)
            if methods:
                return {
                    "source": "ns-train --help",
                    "methods": methods,
                }
            last_error = f"Could not parse methods from command: {' '.join(cmd)}"
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"

    return {
        "source": "unavailable",
        "methods": [],
        "error": last_error or "Unknown error",
    }
    
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser("ns-install")

    p.add_argument("--lock-dir", default=str(DEFAULT_LOCK_DIR))
    p.add_argument("--msvc-mode", dest="global_msvc_mode", default="auto", choices=MSVC_MODE_CHOICES)
    p.add_argument("--cuda-mode", dest="global_cuda_mode", default="vanilla", choices=CUDA_MODE_CHOICES)

    sub = p.add_subparsers(dest="cmd", required=True)

    core_p = sub.add_parser("core")
    _add_common_build_args(core_p)

    methods_p = sub.add_parser("methods")
    _add_common_build_args(methods_p)

    methods_list_p = sub.add_parser(
        "methods-list",
        help="List methods visible in the current environment",
    )
    methods_list_p.add_argument(
        "--source",
        choices=["available", "discovered", "both"],
        default="available",
        help=(
            "'available' = parse ns-train --help (best view of what can actually be trained), "
            "'discovered' = Python entry points only, "
            "'both' = show both."
        ),
    )
    methods_list_p.add_argument(
        "--verbose",
        action="store_true",
        help="Show additional details such as entry point targets.",
    )

    method_p = sub.add_parser("method")
    method_p.add_argument("name")
    _add_common_build_args(method_p)

    all_p = sub.add_parser("all")
    _add_common_build_args(all_p)

    repin_p = sub.add_parser("repin")
    repin_p.add_argument("--skip-conda", action="store_true")
    repin_p.add_argument("--force-conda", action="store_true")
    _add_common_build_args(repin_p)

    doctor_p = sub.add_parser("doctor", help="Inspect environment")
    doctor_p.add_argument("--json", action="store_true")
    _add_common_build_args(doctor_p)
    return p


def main(argv: Optional[list[str]] = None) -> int:
    compat_rc = _maybe_handle_tyro_completion(argv)
    if compat_rc is not None:
        return compat_rc

    parser = build_parser()
    args = parser.parse_args(argv)

    lock_dir = _resolve_lock_dir(args.lock_dir)
    msvc_mode = _resolve_msvc_mode(args)
    cuda_mode = _resolve_cuda_mode(args)

    if args.cmd == "core":
        return int(install_core(lock_dir, msvc_mode) or 0)

    if args.cmd == "methods":
        install_methods(ROOT, lock_dir=lock_dir, msvc_mode=msvc_mode, cuda_mode=cuda_mode)
        return 0

    if args.cmd == "methods-list":
        source = getattr(args, "source", "available")

        if source in {"discovered", "both"}:
            discovered = discover_method_entrypoints()
        else:
            discovered = {}

        if source in {"available", "both"}:
            available_info = discover_all_trainable_methods()
            available = available_info.get("methods", [])
        else:
            available_info = {"source": "disabled"}
            available = []

        if source == "discovered":
            if not discovered:
                print("[INFO] No nerfstudio method entrypoints discovered in this environment.")
                return 0

            print("[INFO] Methods discovered via nerfstudio.method_configs entry points:")
            for name in sorted(discovered):
                if getattr(args, "verbose", False):
                    print(f"  - {name}: {discovered[name]}")
                else:
                    print(f"  - {name}")
            return 0

        if source == "available":
            if not available:
                print("[WARN] Could not determine available methods from ns-train.")
                if "error" in available_info:
                    print(f"[WARN] {available_info['error']}")
                return 1

            print(f"[INFO] Methods currently available through ns-train ({available_info['source']}):")
            for name in available:
                print(f"  - {name}")
            return 0

        # source == "both"
        print("[INFO] Methods currently available through ns-train:")
        if available:
            for name in available:
                print(f"  - {name}")
        else:
            print("  (none detected)")
            if "error" in available_info:
                print(f"[WARN] {available_info['error']}")

        print()
        print("[INFO] Methods discovered via nerfstudio.method_configs entry points:")
        if discovered:
            for name in sorted(discovered):
                if getattr(args, "verbose", False):
                    print(f"  - {name}: {discovered[name]}")
                else:
                    print(f"  - {name}")
        else:
            print("  (none detected)")

        if available:
            available_set = set(available)
            discovered_set = set(discovered.keys())
            only_available = sorted(available_set - discovered_set)
            only_discovered = sorted(discovered_set - available_set)

            if only_available:
                print()
                print("[INFO] Available in ns-train but not entrypoint-discovered:")
                for name in only_available:
                    print(f"  - {name}")

            if only_discovered:
                print()
                print("[INFO] Entrypoint-discovered but not shown by ns-train:")
                for name in only_discovered:
                    print(f"  - {name}")

        return 0

    if args.cmd == "method":
        install_single_method(args.name, ROOT, lock_dir=lock_dir, msvc_mode=msvc_mode, cuda_mode=cuda_mode)
        return 0

    if args.cmd == "all":
        return int(install_all(lock_dir, msvc_mode) or 0)

    if args.cmd == "repin":
        return int(repin(lock_dir, msvc_mode=msvc_mode) or 0)

    if args.cmd == "doctor":
        doctor_argv = ["--lock-dir", str(lock_dir), "--msvc-mode", msvc_mode]
        if getattr(args, "json", False):
            doctor_argv.append("--json")
        return int(doctor_main(doctor_argv) or 0)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())