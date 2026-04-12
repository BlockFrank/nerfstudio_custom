# Nerfstudio Custom installer notes

## What changed
- Removed hardcoded absolute paths for CUDA, Visual Studio, and Conda prefixes.
- Added prompts for new or existing environments instead of forcing a fixed env name.
- Added package flavor selection (`base`, `gen`, `dev`, `dev,docs`).
- Added safer CUDA/Torch presets that follow the Nerfstudio installation guide.
- Split optional methods from the base installer.
- Added a separate helper flow for SDFStudio / Neuralangelo instead of mixing them into the main Nerfstudio env.

## Why keep SDFStudio / Neuralangelo separate
SDFStudio still documents an older environment target and says it was tested with Python 3.8, Torch 1.12.1 + CUDA 11.3, plus tiny-cuda-nn. It also exposes Neuralangelo support inside the SDFStudio codebase. Mixing that into a modern Nerfstudio 1.1.x environment is likely to create version conflicts.

## Docker note
Your Docker build likely needs to be split or slimmed down. Right now the Dockerfile builds GLOMAP, COLMAP, tiny-cuda-nn, HLOC, gsplat, and Nerfstudio in one GH Actions job, which is expensive for the default runner budget.
