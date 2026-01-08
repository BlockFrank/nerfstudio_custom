# test_cli.py
import subprocess
import sys
import shutil
import io
import os

# Force UTF-8 encoding
sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.detach(), encoding='utf-8')
os.environ["PYTHONIOENCODING"] = "utf-8"

# Optional expected modules to validate trainer registration
EXPECTED_TRAINERS = [
    "zipnerf",
    "splatfacto",
    "sdfstudio",
    "gs2gs",
    "nerfgs"
]

def run_command(cmd, description=""):
    print(f"\n🔹 Running: {cmd}")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding='utf-8')
        if result.returncode != 0:
            print(f"❌ Failed: {description or cmd}")
            print(result.stderr)
            return False
        print("✅ Success")
        return result.stdout
    except Exception as e:
        print(f"❌ Exception while running {cmd}:\n{e}")
        return False

def command_exists(command):
    return shutil.which(command) is not None

def main():
    print("🔧 Nerfstudio CLI Validation Tool\n")

    # 1. Check CLI tools
    for cmd in ["ns-train", "ns-viewer", "ns-process-data"]:
        if not command_exists(cmd):
            print(f"❌ Command not found: {cmd}. Is nerfstudio CLI installed?")
            return
        else:
            print(f"✔️ Found CLI command: {cmd}")

    # 2. CLI Help Check
    if not run_command("ns-train --help", "Check ns-train help"): return
    if not run_command("ns-viewer --help", "Check ns-viewer help"): return

    # 3. Trainer Parsing
    print("\n📋 Checking registered trainers:")
    output = run_command("ns-train --help", "List trainers")
    if not output: return

    trainers = []
    for line in output.splitlines():
        if "usage: ns-train" in line.lower():
            continue
        if "--" in line or "Options:" in line:
            break
        if line.strip():
            trainers.append(line.strip())

    print(f"\n✅ Detected trainers:")
    for t in trainers:
        print(f"   - {t}")

    # 4. Validate Addons
    print("\n🔍 Verifying addon trainer registration:")
    missing = []
    for expected in EXPECTED_TRAINERS:
        if not any(expected in t for t in trainers):
            print(f"❗ Missing expected trainer: {expected}")
            missing.append(expected)
        else:
            print(f"✔️ Found: {expected}")

    if missing:
        print("\n⚠️  Some trainers appear to be missing. Did you run `ns-install-cli` after installing modules?")
    else:
        print("\n🎉 All expected addon trainers are registered.")

    print("\n✅ CLI Validation Complete.")

if __name__ == "__main__":
    main()
