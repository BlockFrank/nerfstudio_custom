from __future__ import annotations

import os

# Registra i metodi external prima che Nerfstudio costruisca la CLI.
os.environ["NERFSTUDIO_METHOD_CONFIGS"] = (
    "tetra-nerf=tetranerf.nerfstudio.registration:tetranerf,"
    "tetra-nerf-original=tetranerf.nerfstudio.registration:tetranerf_original"
)

# Import esplicito per forzare la registrazione del modulo/plugin.
import tetranerf.nerfstudio.registration  # noqa: F401

from nerfstudio.scripts.train import entrypoint


if __name__ == "__main__":
    entrypoint()