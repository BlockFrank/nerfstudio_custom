# Docker fix notes for `nerfstudio_custom`

The current failing layer groups several risky operations into a single `RUN`, so GitHub Actions only reports the full shell line and exit code. Split the layer so the failing sub-step becomes visible.

Recommended replacement pattern:

```dockerfile
RUN python3.10 -m pip install --no-cache-dir --upgrade pip 'setuptools<70.0.0'
RUN python3.10 -m pip install --no-cache-dir torch==2.1.2+cu118 torchvision==0.16.2+cu118 'numpy<2.0.0' \
    --extra-index-url https://download.pytorch.org/whl/cu118
RUN git clone --branch master --recursive https://github.com/cvg/Hierarchical-Localization.git /opt/hloc \
    && cd /opt/hloc \
    && git checkout v1.4 \
    && python3.10 -m pip install --no-cache-dir .
RUN TCNN_CUDA_ARCHITECTURES="${CUDA_ARCHITECTURES}" python3.10 -m pip install --no-cache-dir -v \
    "git+https://github.com/NVlabs/tiny-cuda-nn.git@b3473c81396fe927293bdfd5a6be32df8769927c#subdirectory=bindings/torch"
RUN python3.10 -m pip install --no-cache-dir pycolmap==0.6.1 pyceres==2.1 omegaconf==2.3.0
```

Two practical changes matter here:

1. Use `python3.10 -m pip` everywhere instead of mixing `pip` and `python3.10 -m pip`.
2. Add `-v` to the tiny-cuda-nn install, because that is one of the most common native-build failure points in CUDA Docker builds.

If the split build still fails, the log will finally tell you whether the culprit is:
- `hloc`
- `tiny-cuda-nn`
- `pycolmap`
- `pyceres`

Also consider lowering the architecture list while debugging, for example:

```dockerfile
ARG CUDA_ARCHITECTURES="86"
```

That reduces compile work significantly while you stabilize CI.
