import subprocess
import sys
import re

ROOT = "C:/Users/crist/Documents/nerfstudio_custom"

def run_cmd(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def try_ns():
    result = run_cmd("ns-viewer --help")
    return result.stderr + result.stdout

def install_module(module_name):
    print(f"[AUTO] Trying to install: {module_name}")

    import os

    for folder in os.listdir(ROOT):
        path = os.path.join(ROOT, folder)
        if os.path.isdir(path):
            if module_name.lower() in folder.lower():
                print(f"[FOUND] Installing from {folder}")
                subprocess.run(f'cd "{path}" && pip install -e . --no-deps', shell=True)
                return True

    print(f"[MISS] Could not find folder for {module_name}")
    return False


def main():
    for _ in range(10):
        output = try_ns()

        match = re.search(r"No module named '([^']+)'", output)
        if not match:
            print("✅ All dependencies resolved")
            return

        missing = match.group(1).split(".")[0]
        print(f"[MISSING] {missing}")

        ok = install_module(missing)
        if not ok:
            print("❌ Could not resolve automatically")
            return

    print("⚠️ Too many iterations")


if __name__ == "__main__":
    main()