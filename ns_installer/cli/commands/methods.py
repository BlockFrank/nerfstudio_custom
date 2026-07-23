# (FULL FILE — cleaned + auto-fix added)

from __future__ import annotations

import argparse
import re
import subprocess
import sys

from ns_installer.core.methods import (
    discover_method_entrypoints,
    fix_methods,
    known_method_names,
    ready_methods,
    resolved_method_health_catalog,
)

# ---------------------------
# Parsing ns-train help
# ---------------------------

def extract_methods_from_ns_train_help(text: str) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    match = re.search(
        r"usage:\s*(?:ns-train|.*nerfstudio\.scripts\.train)\s+\[-h\]\s*\{([^}]*)\}",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match:
        raw = match.group(1)
        parts = [p.strip() for p in raw.replace("\n", "").split(",")]
        methods = [p for p in parts if p and not p.startswith("...")]
        if methods:
            return sorted(dict.fromkeys(methods))

    return []

def discover_all_trainable_methods() -> dict:
    try:
        proc = subprocess.run(
            ["ns-train", "--help"],
            capture_output=True,
            text=True,
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        methods = extract_methods_from_ns_train_help(output)
        return {"methods": methods, "source": "ns-train"}
    except Exception as e:
        return {"methods": [], "error": str(e)}

# ---------------------------
# CLI parsers
# ---------------------------

def add_methods_list_parser(subparsers):
    p = subparsers.add_parser("methods-list")
    p.add_argument("--source", default="effective")

def add_methods_check_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "methods-check",
        help="Check trainability and registration health for methods",
    )
    p.add_argument("names", nargs="*", help="Optional specific method names")
    p.add_argument(
        "--with-cli-probe",
        action="store_true",
        help="Also run ns-train <method> --help for each method (slow).",
    )
    p.add_argument(
        "--fix",
        action="store_true",
        help="Auto-fix only broken methods after checking them.",
    )
    p.add_argument(
        "--pull",
        action="store_true",
        help="Pull latest changes for existing repos before fixing.",
    )

def add_methods_fix_parser(subparsers):
    p = subparsers.add_parser("methods-fix")
    p.add_argument("names", nargs="*")
    p.add_argument("--all-known", action="store_true")
    p.add_argument("--pull", action="store_true")

# ---------------------------
# Handlers
# ---------------------------

def handle_methods_list(args):
    rows = ready_methods()
    print("[INFO] Methods structurally ready for training:")
    for r in rows:
        print(f"  - {r['train_name']}")
    return 0


def handle_methods_check(
    args: argparse.Namespace,
    *,
    lock_dir=None,
    msvc_mode: str = "",
    cuda_mode: str = "vanilla",
) -> int:
    rows = resolved_method_health_catalog(
        run_cli_probe=bool(getattr(args, "with_cli_probe", False))
    )

    wanted = set(getattr(args, "names", []) or [])

    if wanted:
        rows = [
            row
            for row in rows
            if row.get("train_name") in wanted
            or row.get("installer_name") in wanted
            or row.get("entrypoint_name") in wanted
        ]

    if not rows:
        print("[WARN] No matching methods found.")
        return 1

    rc = 0
    broken_names: list[str] = []

    for row in rows:
        train_name = row.get("train_name", "<unknown>")
        source = row.get("source")

        is_registered = row.get("is_registered", False)
        entry_ok = row.get("entrypoint_load_ok", False)
        module_ok = row.get("module_import_ok", False)

        listed_by_train_cli = row.get("listed_by_train_cli")
        if listed_by_train_cli is None:
            listed_by_train_cli = (source == "available")

        structurally_ready = row.get("structurally_ready")
        if structurally_ready is None:
            structurally_ready = ((is_registered and entry_ok) or module_ok)

        ready = row.get("ready")
        if ready is None:
            ready = structurally_ready or listed_by_train_cli

        status = "READY" if ready else "BROKEN"

        print(f"[{status}] {train_name}")
        print(f"  source: {source}")
        print(f"  installer_name: {row.get('installer_name')}")
        print(f"  entrypoint_name: {row.get('entrypoint_name')}")
        print(f"  registered: {is_registered}")
        print(f"  entrypoint_load_ok: {entry_ok}")
        print(f"  module_import_ok: {module_ok}")
        print(f"  cli_help_ok: {row.get('cli_help_ok')}")
        print(f"  listed_by_train_cli: {listed_by_train_cli}")
        print(f"  structurally_ready: {structurally_ready}")
        print(f"  ready: {ready}")

        if row.get("entrypoint_load_msg"):
            print(f"  entrypoint_load_msg: {row['entrypoint_load_msg']}")
        if row.get("module_import_msg"):
            print(f"  module_import_msg: {row['module_import_msg']}")
        if row.get("probe_error"):
            print(f"  probe_error: {row['probe_error']}")

        if row.get("probe_output"):
            first = row["probe_output"].splitlines()[:6]
            if first:
                print("  probe_output:")
                for line in first:
                    print(f"    {line}")

        print()

        if not ready:
            rc = 2
            installer_name = row.get("installer_name")
            candidate = installer_name or train_name
            if candidate in known_method_names():
                broken_names.append(candidate)

    if getattr(args, "fix", False):
        broken_names = sorted(dict.fromkeys(broken_names))
        if not broken_names:
            print("[INFO] No installer-known broken methods to auto-fix.")
            return rc

        print(f"[INFO] Auto-fixing broken methods: {', '.join(broken_names)}")
        fix_results = fix_methods(
            broken_names,
            lock_dir=lock_dir,
            msvc_mode=msvc_mode,
            cuda_mode=cuda_mode,
            pull=bool(getattr(args, "pull", False)),
        )

        for result in fix_results:
            name = result["name"]
            if "error" in result:
                print(f"[FAIL] auto-fix {name}")
                print(f"  error: {result['error']}")
                print()
                rc = 2
                continue

            before = result.get("before") or {}
            after = result.get("after") or {}

            print(f"[DONE] auto-fix {name}")
            print(f"  path: {result.get('path')}")
            print(f"  before_ready: {before.get('ready')}")
            print(f"  after_ready: {after.get('ready')}")
            print(f"  before_structurally_ready: {before.get('structurally_ready')}")
            print(f"  after_structurally_ready: {after.get('structurally_ready')}")
            print()

    return rc


def handle_methods_fix(args, lock_dir=None, msvc_mode="", cuda_mode="vanilla"):
    names = args.names or []
    if args.all_known:
        names = known_method_names()

    if not names:
        print("[WARN] No methods specified.")
        return 1

    results = fix_methods(
        names,
        lock_dir=lock_dir,
        msvc_mode=msvc_mode,
        cuda_mode=cuda_mode,
        pull=args.pull,
    )

    rc = 0

    for r in results:
        if "error" in r:
            print(f"[FAIL] {r['name']}: {r['error']}")
            rc = 2
            continue

        print(f"[DONE] {r['name']}")
        print(f"  before_ready: {r['before'].get('ready') if r['before'] else None}")
        print(f"  after_ready: {r['after'].get('ready') if r['after'] else None}")
        print()

    return rc