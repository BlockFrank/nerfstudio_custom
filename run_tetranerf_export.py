from __future__ import annotations

import os

os.environ["NERFSTUDIO_METHOD_CONFIGS"] = (
    "tetra-nerf=tetranerf.nerfstudio.registration:tetranerf,"
    "tetra-nerf-original=tetranerf.nerfstudio.registration:tetranerf_original"
)

import tetranerf.nerfstudio.registration  # noqa: F401

from nerfstudio.scripts.exporter import entrypoint


if __name__ == "__main__":
    entrypoint()