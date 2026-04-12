from __future__ import annotations

import tyro

from nerfstudio.scripts.train import main as ns_train_main
from tetranerf.nerfstudio.registration import tetranerf_config


def entrypoint():
    # Usa direttamente il vero TrainerConfig di Tetra-NeRF,
    # senza passare dal registry/subcommand dummy di ns-train.
    config = tyro.cli(
        type(tetranerf_config),
        default=tetranerf_config,
    )
    ns_train_main(config)


if __name__ == "__main__":
    entrypoint()