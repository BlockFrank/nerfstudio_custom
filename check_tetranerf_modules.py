import importlib

mods = [
    "tetranerf.nerfstudio.config",
    "tetranerf.nerfstudio.method",
    "tetranerf.nerfstudio.tetra_nerf",
    "tetranerf.nerfstudio.dataparser",
    "tetranerf.nerfstudio.tetranerf",
    # aggiungiamo anche quelli che hai visto esistere
    "tetranerf.nerfstudio.model",
    "tetranerf.nerfstudio.pipeline",
    "tetranerf.nerfstudio.registration",
]

print("=== Tetra-NeRF module probe ===\n")

for m in mods:
    try:
        x = importlib.import_module(m)
        print(f"[OK] {m}")
        print(f"     -> {getattr(x, '__file__', None)}\n")
    except Exception as e:
        print(f"[NO] {m}")
        print(f"     -> {e}\n")

print("=== done ===")