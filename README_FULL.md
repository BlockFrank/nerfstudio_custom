install nerfstudio via base.bat Conda or python venv(experimental)
install extra nerfstudio algorythms via extras_portable_manager.bat
validate the installed and available algorythms with test_cli.py

NEW:

Nerfstudio Custom – Installation Prerequisites (Windows)

Before running the installer, you must install the required toolchains manually.
The installer assumes these are already present and correctly configured.

1. Install Anaconda (Required)

Download and install Anaconda (Python distribution) from the official source:

👉 https://www.anaconda.com/download

Notes:

Install for your user (recommended)

Make sure conda works from terminal:

conda --version

Do NOT rely on system Python — the installer will manage environments via Conda

2. Install CUDA Toolkit 11.8 (Required for GPU)

Download CUDA 11.8 specifically (do NOT install newer versions for this setup):

👉 https://developer.nvidia.com/cuda-11-8-0-download-archive

Important:

Choose:

Windows → x86_64 → your OS → exe (local)

Install with default settings

After install, verify:

nvcc --version
Expected path (default):
C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v11.8
3. Install Visual Studio Build Tools (Required)

You need MSVC for compiling native extensions.

👉 https://visualstudio.microsoft.com/downloads/

Install:

Build Tools for Visual Studio 2022

Required components:

✔ Desktop development with C++

✔ MSVC v143 toolset

✔ Windows 10/11 SDK

4. Install ROCm HIP SDK (Optional but Recommended)

Even if you're using NVIDIA, some builds probe for ROCm/HIP.

Download from official AMD source:

👉 https://www.amd.com/en/developer/resources/rocm-hub/hip-sdk.html

Notes:

Install default configuration

The installer will disable HIP/ROCm automatically during builds

This avoids PyTorch extension conflicts on Windows

5. Environment Variables (Handled by Installer)

You DO NOT need to manually set:

CUDA_HOME

CUDA_PATH

CUB_HOME

The installer will:

detect your paths

convert them to short (8.3) paths

override them locally when needed (e.g. for tiny-cuda-nn)

6. After Prerequisites

Once everything is installed, run:

install_windows_all_in_one.bat

The installer will:

create or use a Conda environment

install Nerfstudio + dependencies

align Torch + CUDA versions

build native modules (tiny-cuda-nn, gsplat, etc.)

store built wheels in:

./wheelhouse
⚠️ Common Pitfalls
Wrong CUDA version

Must be 11.8

Newer versions (12.x) will break builds

Missing MSVC

If cl.exe is missing → installs will fail

Conflicting environment variables

System-level CUDA_PATH pointing to another version (e.g. 12.8)

The installer overrides this, but misconfigurations can still leak

✅ Recommended Setup Summary
Component	Version
Python (Conda)	3.10
CUDA Toolkit	11.8
PyTorch	2.1.2 + cu118
Torchvision	0.16.2
MSVC	VS 2022
# Nerfstudio Custom

A custom Nerfstudio fork focused on improved Windows installation support and optional extra NeRF methods.

## Windows prerequisites

Install these manually before running the installer:

### 1. Anaconda
Download and install from the official source:
- https://www.anaconda.com/download

### 2. CUDA Toolkit 11.8
Use CUDA **11.8** for the recommended Windows stack.
- https://developer.nvidia.com/cuda-11-8-0-download-archive

### 3. Visual Studio 2022 C++ Build Tools
Install:
- Desktop development with C++
- MSVC v143
- Windows 10/11 SDK

For best compatibility with CUDA 11.8, also install the **14.38** MSVC toolset if available.

### 4. AMD HIP SDK / ROCm for Windows
Optional, official source:
- https://www.amd.com/en/developer/resources/rocm-hub/hip-sdk.html

If HIP/ROCm is installed, it may need to be temporarily hidden during some NVIDIA/CUDA extension builds.

---

## Recommended Windows stack

- Python 3.10
- Torch 2.1.2 + cu118
- Torchvision 0.16.2 + cu118
- CUDA Toolkit 11.8
- Visual Studio 2022 with MSVC 14.38 preferred

---

## Base install

Run the Windows all-in-one installer from the repo root.

It will:
- create or reuse a Python environment
- install Nerfstudio
- align Torch/CUDA versions
- cache wheels in `wheelhouse`
- optionally install extra modules

---

## Important compatibility notes

### NumPy
Keep an eye on NumPy version drift.

Some plugins still work best with:
- `numpy<2.0`

But newer OpenCV wheels may try to force:
- `numpy>=2`

If plugin installs upgrade NumPy unexpectedly, re-check compatibility before continuing.

### Torch / CUDA
Do not let plugin-specific requirements replace the stable base stack unless you are intentionally testing a separate environment.

Recommended stable pair:
- `torch==2.1.2+cu118`
- `torchvision==0.16.2+cu118`

---

## Extra methods and plugin notes

## Zip-NeRF on Windows

This plugin is experimental on Windows and needs a few manual fixes.

### 1. Keep the stable Nerfstudio stack
Use the same stack as the base installer:

- Python 3.10
- Torch 2.1.2 + cu118
- Torchvision 0.16.2 + cu118
- CUDA Toolkit 11.8
- MSVC 14.38 / VS2022 C++ tools

Do not let `zipnerf-pytorch/requirements.txt` replace:
- torch
- torchvision
- numpy
- opencv-python
- opencv-contrib-python

Those upgrades can break the Nerfstudio environment.

### 2. Build the CUDA extension without build isolation
The extension imports `torch` during build, so install it with:

```bat
python -m pip install --no-build-isolation .\extensions\cuda

## Instruct-GS2GS / IGS2GS on Windows

If CLI issues appear, pin:
```bat
pip install tyro==0.8.12
