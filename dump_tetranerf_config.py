from __future__ import annotations

from dataclasses import fields, is_dataclass
from typing import Any

from tetranerf.nerfstudio.registration import tetranerf


def walk(name: str, obj: Any, depth: int = 0, max_depth: int = 8) -> None:
    indent = "  " * depth
    print(f"{indent}{name}: {type(obj).__name__}")

    if depth >= max_depth:
        return

    if is_dataclass(obj):
        for f in fields(obj):
            try:
                value = getattr(obj, f.name)
            except Exception as exc:
                print(f"{indent}  {f.name}: <error: {exc}>")
                continue
            walk(f.name, value, depth + 1, max_depth)


if __name__ == "__main__":
    print("=== Tetra-NeRF TrainerConfig tree ===")
    walk("config", tetranerf.config)