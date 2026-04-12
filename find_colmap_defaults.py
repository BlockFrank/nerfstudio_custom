from pathlib import Path

roots = ["splatfacto-w", "NeRFtoGSandBack", "opennerf", "relationfield", "lerf", "pynerf"]

for root in roots:
    rp = Path(root)
    if not rp.exists():
        continue
    for p in rp.rglob("*.py"):
        s = p.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(s.splitlines(), start=1):
            if "ColmapDataParserConfig(" in line:
                print(f"{p}:{i}: {line.strip()}")