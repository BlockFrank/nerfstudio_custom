from pathlib import Path

roots = [
    Path("opennerf"),
    Path("NeRFtoGSandBack"),
    Path("relationfield"),
    Path("livescene"),
    Path("pynerf"),
    Path("splatfacto-w"),
    Path("lerf"),
]

needles = [
    "dataparser: AnnotatedDataParserUnion = ",
    "dataparser: AnnotatedDataParserUnion=",
]

for root in roots:
    if not root.exists():
        continue
    for p in root.rglob("*.py"):
        s = p.read_text(encoding="utf-8", errors="ignore")
        if any(n in s for n in needles):
            print(f"\n== {p} ==")
            for line in s.splitlines():
                if "dataparser:" in line and "AnnotatedDataParserUnion" in line:
                    print(line)