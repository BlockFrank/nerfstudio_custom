@echo off
setlocal enabledelayedexpansion

REM ==== Optional modules config ====
set MODULES=zipnerf-pytorch sdfstudio splatfacto-w NeRFtoGSandBack opennerf instruct-gs2gs
set FLAG_REFRESH_CLI=0

echo.
echo === Nerfstudio Optional Module Installer ===
echo.

REM === CUDA / TORCH INFO ===
echo Detecting CUDA + Torch info...
python -c "import torch; print(f'Torch: {torch.__version__}, CUDA: {torch.version.cuda}, Available: {torch.cuda.is_available()}')"
echo.

REM === Iterate modules ===
for %%M in (%MODULES%) do (
    choice /C YN /M "Install %%M? (Y/N)"
    if errorlevel 1 (
        if not exist %%M (
            if "%%M"=="zipnerf-pytorch" (
                git clone https://github.com/SuLvXiangXin/zipnerf-pytorch.git
                cd zipnerf-pytorch
                pip install -r requirements.txt
                pip install ./extensions/cuda
                if not exist nvdiffrast (
                    git clone https://github.com/NVlabs/nvdiffrast
                    pip install ./nvdiffrast
                )
                set CUDA=cu118
                pip install torch-scatter -f https://data.pyg.org/whl/torch-2.1.0+%CUDA%.html
                cd ..
            ) else if "%%M"=="splatfacto-w" (
                git clone https://github.com/KevinXu02/splatfacto-w
                pip install -e splatfacto-w
            ) else if "%%M"=="sdfstudio" (
                git clone https://github.com/autonomousvision/sdfstudio.git
                pip install -e sdfstudio
            ) else if "%%M"=="NeRFtoGSandBack" (
                git clone https://github.com/grasp-lyrl/NeRFtoGSandBack
            ) else if "%%M"=="opennerf" (
                git clone https://github.com/opennerf/opennerf
            ) else if "%%M"=="instruct-gs2gs" (
                git clone https://github.com/cvachha/instruct-gs2gs
                pip install git+https://github.com/cvachha/instruct-gs2gs
            )
        )
        set FLAG_REFRESH_CLI=1
    )
)

if %FLAG_REFRESH_CLI%==1 (
    echo Refreshing Nerfstudio CLI...
    call ns-install-cli
)

echo.
echo ✅ Optional module setup complete.
pause
