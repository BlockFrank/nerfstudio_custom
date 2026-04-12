#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Nerfstudio Custom - Linux/macOS installer
# - Linux: supports CUDA/Torch/tiny-cuda-nn path
# - macOS: installs base package only and skips CUDA-specific parts
# ============================================================

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

DEFAULT_ENV_NAME="nerfstudio"
DEFAULT_PYTHON="3.10"
OS_NAME="$(uname -s)"
INSTALL_MODE=""
ENV_NAME=""
PY_VER="$DEFAULT_PYTHON"
CUDA_PRESET="11.8"
NS_EXTRAS=""

banner() {
  echo
  echo "======================================================"
  echo "  Nerfstudio Custom - Linux/macOS Installer"
  echo "======================================================"
  echo
  echo "Working directory: $PWD"
  echo "Detected OS: $OS_NAME"
  echo
}

ask() {
  local prompt="$1"
  local default="${2:-}"
  local value
  if [[ -n "$default" ]]; then
    read -r -p "$prompt [$default]: " value
    echo "${value:-$default}"
  else
    read -r -p "$prompt: " value
    echo "$value"
  fi
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "[ERROR] Missing command: $1"; exit 1; }
}

create_or_activate_env() {
  echo "Choose environment mode:"
  echo "  1) new conda env"
  echo "  2) existing conda env"
  echo "  3) new venv"
  echo "  4) current python"
  read -r -p "Enter choice [1-4]: " mode

  case "$mode" in
    1)
      need_cmd conda
      INSTALL_MODE="new_conda"
      ENV_NAME="$(ask 'New conda env name' "$DEFAULT_ENV_NAME")"
      PY_VER="$(ask 'Python version' "$DEFAULT_PYTHON")"
      conda create -y -n "$ENV_NAME" "python=$PY_VER"
      # shellcheck disable=SC1091
      source "$(conda info --base)/etc/profile.d/conda.sh"
      conda activate "$ENV_NAME"
      ;;
    2)
      need_cmd conda
      INSTALL_MODE="existing_conda"
      ENV_NAME="$(ask 'Existing conda env name')"
      # shellcheck disable=SC1091
      source "$(conda info --base)/etc/profile.d/conda.sh"
      conda activate "$ENV_NAME"
      ;;
    3)
      INSTALL_MODE="new_venv"
      ENV_NAME="$(ask 'New venv folder name' "$DEFAULT_ENV_NAME.venv")"
      PY_VER="$(ask 'Python command for venv creation' "python3")"
      "$PY_VER" -m venv "$ENV_NAME"
      # shellcheck disable=SC1091
      source "$ENV_NAME/bin/activate"
      ;;
    4)
      INSTALL_MODE="current"
      ;;
    *)
      echo "[ERROR] Invalid environment choice."; exit 1 ;;
  esac

  python -m pip install --upgrade pip setuptools wheel
}

choose_cuda_stack() {
  if [[ "$OS_NAME" == "Darwin" ]]; then
    CUDA_PRESET="cpu"
    echo "[INFO] macOS detected. CUDA/tiny-cuda-nn steps will be skipped."
    return
  fi

  echo
  echo "CUDA / Torch preset:"
  echo "  1) CUDA 11.8 + Torch 2.1.2"
  echo "  2) CUDA 11.7 + Torch 2.0.1"
  echo "  3) CPU-only"
  read -r -p "Enter choice [1-3]: " choice
  case "$choice" in
    1) CUDA_PRESET="11.8" ;;
    2) CUDA_PRESET="11.7" ;;
    3) CUDA_PRESET="cpu" ;;
    *) echo "[ERROR] Invalid CUDA choice."; exit 1 ;;
  esac
}

install_torch_and_tcnn() {
  if [[ "$CUDA_PRESET" == "11.8" ]]; then
    python -m pip install torch==2.1.2+cu118 torchvision==0.16.2+cu118 --extra-index-url https://download.pytorch.org/whl/cu118
    if [[ "$INSTALL_MODE" == *conda* ]]; then
      conda install -y -c "nvidia/label/cuda-11.8.0" cuda-toolkit
    fi
    python -m pip install ninja git+https://github.com/NVlabs/tiny-cuda-nn/#subdirectory=bindings/torch
  elif [[ "$CUDA_PRESET" == "11.7" ]]; then
    python -m pip install torch==2.0.1+cu117 torchvision==0.15.2+cu117 --extra-index-url https://download.pytorch.org/whl/cu117
    if [[ "$INSTALL_MODE" == *conda* ]]; then
      conda install -y -c "nvidia/label/cuda-11.7.1" cuda-toolkit
    fi
    python -m pip install ninja git+https://github.com/NVlabs/tiny-cuda-nn/#subdirectory=bindings/torch
  else
    python -m pip install torch torchvision
    echo "[INFO] Skipping tiny-cuda-nn for CPU/macOS install."
  fi
}

choose_package_flavor() {
  echo
  echo "Nerfstudio package flavor:"
  echo "  1) base"
  echo "  2) gen"
  echo "  3) dev"
  echo "  4) dev,docs"
  read -r -p "Enter choice [1-4]: " choice
  case "$choice" in
    1) NS_EXTRAS="" ;;
    2) NS_EXTRAS='[gen]' ;;
    3) NS_EXTRAS='[dev]' ;;
    4) NS_EXTRAS='[dev,docs]' ;;
    *) echo "[ERROR] Invalid package choice."; exit 1 ;;
  esac
}

install_nerfstudio() {
  if [[ -f pyproject.toml ]]; then
    python -m pip install -e ".${NS_EXTRAS}"
  else
    python -m pip install nerfstudio
  fi
  ns-install-cli
}

write_notes() {
  cat <<MSG

[OK] Base install completed.

Recommended next steps:
  python -c "import nerfstudio; print('import ok')"
  ns-train --help

Notes:
  - On macOS, CUDA-only methods are intentionally skipped.
  - For SDFStudio / Neuralangelo, prefer a separate env because they target an older stack.
MSG
}

banner
need_cmd git
create_or_activate_env
choose_cuda_stack
install_torch_and_tcnn
choose_package_flavor
install_nerfstudio
write_notes
