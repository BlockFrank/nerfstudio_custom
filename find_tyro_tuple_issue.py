from pathlib import Path

roots = [
    Path("opennerf"),
    Path("NeRFtoGSandBack"),
    Path("relationfield"),
    Path("lerf"),
]

for root in roots:
    if not root.exists():
        continue
    for p in root.rglob("*.py"):
        s = p.read_text(encoding="utf-8", errors="ignore")
        hit = False
        lines = []
        for line in s.splitlines():
            if "hashgrid_layers" in line or "negatives" in line:
                lines.append(line)
                hit = True
            elif "Tuple[int]" in line or "Tuple[str]" in line:
                lines.append(line)
                hit = True
        if hit:
            print(f"\n== {p} ==")
            for line in lines:
                print(line)