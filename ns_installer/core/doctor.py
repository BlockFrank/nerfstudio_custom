from __future__ import annotations

import argparse
import json
from pathlib import Path

from ns_installer import DEFAULT_LOCK_DIR
from ns_installer.core.bootstrap import (
    build_bootstrap_context,
    build_bootstrap_env,
    find_header_in_include,
    validate_msvc_from_shell,
    write_bootstrap_env_snapshot,
)
from ns_installer.locks import load_build_plan


def diagnose(lock_dir: Path, msvc_mode: str = "") -> dict:
    ctx = build_bootstrap_context(lock_dir, msvc_mode)
    ok, errors = validate_msvc_from_shell(lock_dir, ctx)
    env = build_bootstrap_env(lock_dir, msvc_mode)
    snapshot = write_bootstrap_env_snapshot(lock_dir, env)

    include_value = env.get("INCLUDE", "")
    result = {
        "ok": ok,
        "errors": errors,
        "selected_toolset": (ctx.get("selected") or {}).get("toolset_full", ""),
        "cuda_root": ctx.get("cuda_root", ""),
        "include_present": bool(include_value),
        "lib_present": bool(env.get("LIB", "")),
        "libpath_present": bool(env.get("LIBPATH", "")),
        "corecrt_h": find_header_in_include(include_value, "corecrt.h"),
        "windows_h": find_header_in_include(include_value, "Windows.h"),
        "bootstrap_snapshot": str(snapshot),
        "build_plan": load_build_plan(lock_dir),
    }
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser("ns-install doctor")
    p.add_argument("--json", action="store_true")
    p.add_argument("--lock-dir", default=str(DEFAULT_LOCK_DIR))
    p.add_argument("--msvc-mode", default="")
    args = p.parse_args(argv)

    result = diagnose(Path(args.lock_dir), args.msvc_mode)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"[OK] {result['ok']}")
        print(f"[MSVC] {result['selected_toolset'] or 'system'}")
        print(f"[CUDA] {result['cuda_root'] or 'missing'}")
        print(f"[INCLUDE] {'present' if result['include_present'] else 'missing'}")
        print(f"[LIB] {'present' if result['lib_present'] else 'missing'}")
        print(f"[LIBPATH] {'present' if result['libpath_present'] else 'missing'}")
        print(f"[corecrt.h] {result['corecrt_h'] or 'missing'}")
        print(f"[Windows.h] {result['windows_h'] or 'missing'}")
        print(f"[bootstrap snapshot] {result['bootstrap_snapshot']}")
        for err in result["errors"]:
            print(f"[ERR] {err}")

    return 0 if result["ok"] else 2