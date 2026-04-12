from pathlib import Path

for p in Path(".").rglob("*.py"):
    try:
        s = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        continue
    if "patch_tile_size_range" in s or "(0.05, 0.5)" in s:
        print(f"\n== {p} ==")
        for line in s.splitlines():
            if "patch_tile_size_range" in line or "(0.05, 0.5)" in line:
                print(line)