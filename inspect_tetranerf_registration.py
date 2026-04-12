# inspect_tetranerf_registration.py
import importlib
from pprint import pprint

mod = importlib.import_module("tetranerf.nerfstudio.registration")

print("MODULE:", mod.__file__)
print("\nNAMES:")
pprint([x for x in dir(mod) if not x.startswith("_")])

for name in dir(mod):
    if name.startswith("_"):
        continue
    obj = getattr(mod, name)
    print(f"\n--- {name} ---")
    print(type(obj))
    if hasattr(obj, "config"):
        print("has .config")
    if hasattr(obj, "description"):
        print("has .description")