from __future__ import annotations

from tetranerf.nerfstudio.registration import tetranerf


def try_get(obj, path: str) -> None:
    cur = obj
    ok = True
    for chunk in path.split("."):
        if not hasattr(cur, chunk):
            ok = False
            break
        cur = getattr(cur, chunk)
    if ok:
        print(f"[OK] {path} = {cur!r}")
    else:
        print(f"[NO] {path}")


if __name__ == "__main__":
    cfg = tetranerf.config

    candidates = [
        "data",
        "output_dir",
        "pipeline",
        "pipeline.datamanager",
        "pipeline.datamanager.data",
        "pipeline.datamanager.dataparser",
        "pipeline.datamanager.dataparser.data",
        "pipeline.datamanager.dataparser.colmap_path",
        "pipeline.datamanager.dataparser.colmap-path",
    ]

    for c in candidates:
        try_get(cfg, c.replace("-", "_"))