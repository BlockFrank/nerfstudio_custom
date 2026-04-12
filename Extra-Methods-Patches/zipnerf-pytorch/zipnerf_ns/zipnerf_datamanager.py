"""
ZipNerf DataManager
"""

from dataclasses import dataclass, field
from typing import Dict, Literal, Tuple, Type, Union

import torch

from nerfstudio.cameras.rays import RayBundle
from nerfstudio.data.datamanagers.base_datamanager import (
    VanillaDataManager,
    VanillaDataManagerConfig,
)
from nerfstudio.data.dataparsers.colmap_dataparser import ColmapDataParserConfig


@dataclass
class ZipNerfDataManagerConfig(VanillaDataManagerConfig):
    """ZipNerf DataManager Config."""

    _target: Type = field(default_factory=lambda: ZipNerfDataManager)

    # Important:
    # use a concrete dataparser type here, not AnnotatedDataParserUnion.
    # This avoids Tyro subcommand matching failures on Windows / newer tyro.
    dataparser: ColmapDataParserConfig = field(
        default_factory=lambda: ColmapDataParserConfig(
            downscale_factor=4,
            orientation_method="up",
            center_method="poses",
            colmap_path="sparse/0",
        )
    )


class ZipNerfDataManager(VanillaDataManager):
    """ZipNerf DataManager"""

    config: ZipNerfDataManagerConfig

    def __init__(
        self,
        config: ZipNerfDataManagerConfig,
        device: Union[torch.device, str] = "cpu",
        test_mode: Literal["test", "val", "inference"] = "val",
        world_size: int = 1,
        local_rank: int = 0,
        **kwargs,
    ):
        super().__init__(
            config=config,
            device=device,
            test_mode=test_mode,
            world_size=world_size,
            local_rank=local_rank,
            **kwargs,
        )

    def next_train(self, step: int) -> Tuple[RayBundle, Dict]:
        """Returns the next batch of data from the train dataloader."""
        self.train_count += 1
        image_batch = next(self.iter_train_image_dataloader)
        assert self.train_pixel_sampler is not None
        assert isinstance(image_batch, dict)

        batch = self.train_pixel_sampler.sample(image_batch)
        batch["rgb"] = batch["image"].to(self.device)

        ray_indices = batch["indices"]
        ray_bundle = self.train_ray_generator(ray_indices)
        return ray_bundle, batch

    def next_eval(self, step: int) -> Tuple[RayBundle, Dict]:
        """Returns the next batch of data from the eval dataloader."""
        self.eval_count += 1
        image_batch = next(self.iter_eval_image_dataloader)
        assert self.eval_pixel_sampler is not None
        assert isinstance(image_batch, dict)

        batch = self.eval_pixel_sampler.sample(image_batch)
        batch["rgb"] = batch["image"].to(self.device)

        ray_indices = batch["indices"]
        ray_bundle = self.eval_ray_generator(ray_indices)
        return ray_bundle, batch