@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "ROOT_DIR=%CD%"
set "PORTABLE_ENV_BAT=%ROOT_DIR%\portable_env.bat"
set "LOCK_DIR=%ROOT_DIR%\deps-lock"
set "PY_SCRIPT=%ROOT_DIR%\deps_lock.py"
set "PATCH_ROOT=%ROOT_DIR%\Extra-Methods-Patches"
set "CORE_OVERRIDES_JSON=%LOCK_DIR%\nerfstudio-core-overrides.json"
set "METHODS_PROTECTED_JSON=%LOCK_DIR%\nerfstudio-methods-protected.json"

set "TARGET_ENV=%~1"
if not defined TARGET_ENV set "TARGET_ENV=nerfstudio-portable"

if not exist "%PY_SCRIPT%" (
    echo [ERROR] Missing deps_lock.py
    exit /b 1
)

if not exist "%PORTABLE_ENV_BAT%" (
    echo [ERROR] Missing portable helper: %PORTABLE_ENV_BAT%
    exit /b 1
)

call "%PORTABLE_ENV_BAT%"
if errorlevel 1 exit /b %errorlevel%

if not defined PORTABLE_CONDA_ROOT if exist "%ROOT_DIR%\.conda\Scripts\conda.exe" set "PORTABLE_CONDA_ROOT=%ROOT_DIR%\.conda"
if not defined PORTABLE_CONDA_ROOT (
    echo [ERROR] PORTABLE_CONDA_ROOT not available.
    exit /b 1
)

set "CONDA_EXE=%PORTABLE_CONDA_ROOT%\Scripts\conda.exe"
set "CONDA_BAT=%PORTABLE_CONDA_ROOT%\condabin\conda.bat"

if not exist "%CONDA_EXE%" (
    echo [ERROR] Missing conda.exe: %CONDA_EXE%
    exit /b 1
)
if not exist "%CONDA_BAT%" (
    echo [ERROR] Missing conda.bat: %CONDA_BAT%
    exit /b 1
)
REM Nerfstudio Custom - pinned extras / methods installer
call :clear_rocm_env
call "%CONDA_BAT%" activate "%TARGET_ENV%"
if errorlevel 1 (
    echo [ERROR] Failed to activate env: %TARGET_ENV%
    exit /b %errorlevel%
)

echo [INFO] Active env: %TARGET_ENV%
where python
python --version

set "PIN_TORCH=torch==2.1.2+cu118"
set "PIN_TORCHVISION=torchvision==0.16.2+cu118"
set "PIN_TORCHAUDIO=torchaudio==2.1.2+cu118"
set "PIN_NUMPY=numpy==1.26.4"
set "PIN_NERFSTUDIO=nerfstudio==1.0.3"
set "PIN_TYRO=tyro==0.8.12"

set "PIN_PYCOLMAP_RMBRUALLA=git+https://github.com/rmbrualla/pycolmap.git"
set "PIN_TCNN_GIT=git+https://github.com/NVlabs/tiny-cuda-nn/#subdirectory=bindings/torch"

set "PIN_VISER=viser==0.1.26"
set "PIN_NERFACC=nerfacc==0.5.2"
set "PIN_GSPLAT=gsplat==1.5.3"
set "PIN_HF_HUB=huggingface-hub==1.9.0"
set "PIN_BITSANDBYTES=bitsandbytes==0.49.2"

if not exist "%LOCK_DIR%" mkdir "%LOCK_DIR%" 2>nul

call :clear_rocm_env
if errorlevel 1 exit /b %errorlevel%

echo.
echo ======================================================
echo   Extras target env: %TARGET_ENV%
echo   Conda exe: %CONDA_EXE%
echo   Python script: %PY_SCRIPT%
echo ======================================================
echo.
echo Available extras:
echo   1. Install / repair pinned Nerfstudio core packages
echo   2. Install Zip-NeRF ^(Windows-patched^)
echo   3. Install rmbrualla pycolmap only
echo   4. Install torch-scatter only
echo   5. Run ns-install-cli only
echo   6. Re-pin current target env only
echo   7. Install support packages ^(nerfacc, gsplat, viser, hf-hub, bitsandbytes, tyro^)
echo   8. Full recommended extras bootstrap ^(core + support + Zip-NeRF^)
echo   9. Install Tetra-NeRF (Windows-patched)
echo   10. Install manifest-managed core overrides
echo   11. Install manifest-managed protected methods
echo   12. Full manifest-driven extras bootstrap
 echo   13. Install Splatfacto-W (Windows-patched)
echo.
set /p "CHOICE=Enter choice [1-13]: "

if "%CHOICE%"=="1" goto :do_core
if "%CHOICE%"=="2" goto :do_zipnerf
if "%CHOICE%"=="3" goto :do_pycolmap
if "%CHOICE%"=="4" goto :do_torchscatter
if "%CHOICE%"=="5" goto :do_ns_cli
if "%CHOICE%"=="6" goto :do_repin
if "%CHOICE%"=="7" goto :do_support
if "%CHOICE%"=="8" goto :full_bootstrap
if "%CHOICE%"=="9" goto 
:do_splatfactow
call :install_splatfactow
if errorlevel 1 exit /b %errorlevel%
goto :success

:do_tetra_nerf
if "%CHOICE%"=="10" goto :do_core_overrides_manifest
if "%CHOICE%"=="11" goto :do_methods_manifest
if "%CHOICE%"=="12" goto :do_full_manifest
if "%CHOICE%"=="13" goto :do_splatfactow
echo [ERROR] Invalid choice.
exit /b 1

:full_bootstrap
echo.
echo [STEP] Ensuring support packages used by extra methods...
call :run_in_env python -m pip install --upgrade --force-reinstall --no-deps %PIN_NERFACC% %PIN_GSPLAT% %PIN_VISER% %PIN_HF_HUB% %PIN_BITSANDBYTES% %PIN_TYRO%
if errorlevel 1 exit /b %errorlevel%

echo.
echo [STEP] Ensuring pinned Nerfstudio core packages...
call :run_in_env python -m pip install --upgrade --force-reinstall --no-deps %PIN_NERFSTUDIO%
if errorlevel 1 exit /b %errorlevel%

echo.
echo [STEP] Installing rmbrualla pycolmap...
call :run_in_env python -m pip install --upgrade --force-reinstall --no-deps --no-build-isolation git+https://github.com/rmbrualla/pycolmap.git
if errorlevel 1 exit /b %errorlevel%

echo.
echo [STEP] Installing torch-scatter...
call :run_in_env python -m pip install --upgrade --force-reinstall --no-deps torch-scatter==2.1.2+pt21cu118 -f https://data.pyg.org/whl/torch-2.1.0+cu118.html
if errorlevel 1 exit /b %errorlevel%

echo.
echo [STEP] Installing Zip-NeRF...
call :install_zipnerf
if errorlevel 1 exit /b %errorlevel%

call :run_ns_install_cli
if errorlevel 1 exit /b %errorlevel%

call :repin_target_env
exit /b %errorlevel%

:do_full
call :ensure_support_packages
if errorlevel 1 exit /b %errorlevel%
call :install_zipnerf
if errorlevel 1 exit /b %errorlevel%
goto 
:do_core_overrides_manifest
call :install_core_overrides_from_manifest
if errorlevel 1 exit /b %errorlevel%
goto :success

:do_methods_manifest
call :install_manifest_methods
if errorlevel 1 exit /b %errorlevel%
goto :success

:do_full_manifest
echo.
echo [STEP] Ensuring core stack and support packages...
call :ensure_core_stack
if errorlevel 1 exit /b %errorlevel%
call :ensure_support_packages
if errorlevel 1 exit /b %errorlevel%

echo.
echo [STEP] Installing manifest-managed core overrides...
call :install_core_overrides_from_manifest
if errorlevel 1 exit /b %errorlevel%

echo.
echo [STEP] Installing torch-scatter...
call :install_torch_scatter
if errorlevel 1 exit /b %errorlevel%

echo.
echo [STEP] Installing manifest-managed protected methods...
call :install_manifest_methods
if errorlevel 1 exit /b %errorlevel%

call :run_ns_install_cli
if errorlevel 1 exit /b %errorlevel%
call :repin_target_env
exit /b %errorlevel%
:success

:do_core
call :ensure_core_stack
if errorlevel 1 exit /b %errorlevel%
goto :success

:do_support
call :ensure_support_packages
if errorlevel 1 exit /b %errorlevel%
goto :success

:do_zipnerf
call :install_zipnerf
if errorlevel 1 exit /b %errorlevel%
goto :success

:do_pycolmap
call :install_rmbrualla_pycolmap
if errorlevel 1 exit /b %errorlevel%
call :ns_register_and_repin
if errorlevel 1 exit /b %errorlevel%
goto :success

:do_torchscatter
call :install_torch_scatter
if errorlevel 1 exit /b %errorlevel%
call :ns_register_and_repin
if errorlevel 1 exit /b %errorlevel%
goto :success

:do_ns_cli
call :run_in_env python -m ns_install_cli
if errorlevel 1 (
    call :run_in_env ns-install-cli
    if errorlevel 1 exit /b %errorlevel%
)
goto :success

:do_repin
call :repin_target
if errorlevel 1 exit /b %errorlevel%
goto :success

:success
echo.
echo [OK] Extras flow completed successfully.
exit /b 0

:ensure_core_stack
echo.
echo [STEP] Ensuring pinned Nerfstudio core stack...
call :clear_rocm_env
call :run_in_env python -m pip install --upgrade pip setuptools^<81 wheel
if errorlevel 1 exit /b %errorlevel%
call :run_in_env python -m pip install --upgrade --force-reinstall %PIN_NUMPY%
if errorlevel 1 exit /b %errorlevel%
call :run_in_env python -m pip install --upgrade --force-reinstall %PIN_TORCH% %PIN_TORCHVISION% %PIN_TORCHAUDIO% --index-url https://download.pytorch.org/whl/cu118
if errorlevel 1 exit /b %errorlevel%
call :run_in_env python -m pip install --upgrade --force-reinstall %PIN_NUMPY%
if errorlevel 1 exit /b %errorlevel%
call :run_in_env python -m pip install --upgrade --force-reinstall %PIN_NERFSTUDIO% %PIN_TYRO%
if errorlevel 1 exit /b %errorlevel%
call :set_cuda_arch_env
call :run_in_env python -m pip install -v --upgrade --force-reinstall --no-build-isolation --no-cache-dir %PIN_TCNN_GIT%
if errorlevel 1 exit /b %errorlevel%
call :ns_register_and_repin
exit /b %errorlevel%

:set_cuda_env
if not defined CUDA_HOME if exist "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v11.8" set "CUDA_HOME=C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v11.8"
if not defined CUDA_PATH if defined CUDA_HOME set "CUDA_PATH=%CUDA_HOME%"
if defined CUDA_HOME set "PATH=%CUDA_HOME%\bin;%CUDA_HOME%\libnvvp;%PATH%"
if not defined TCNN_CUDA_ARCHITECTURES set "TCNN_CUDA_ARCHITECTURES=86"
if not defined TORCH_CUDA_ARCH_LIST set "TORCH_CUDA_ARCH_LIST=8.6"
if not defined MAX_JOBS set "MAX_JOBS=1"
exit /b 0

:do_tetra_nerf
call 
:install_splatfactow
echo.
echo [STEP] Installing Splatfacto-W with Windows-safe patches...
call :clear_rocm_env
if errorlevel 1 exit /b %errorlevel%

if not exist "%ROOT_DIR%\splatfacto-w" (
    echo [INFO] Cloning splatfacto-w...
    call :run_in_env git clone https://github.com/KevinXu02/splatfacto-w "%ROOT_DIR%\splatfacto-w"
    if errorlevel 1 exit /b %errorlevel%
)

if exist "%PATCH_ROOT%\splatfacto-w" (
    call :apply_patch_tree "%PATCH_ROOT%\splatfacto-w" "%ROOT_DIR%\splatfacto-w"
    if errorlevel 1 exit /b %errorlevel%
) else (
    echo [INFO] No patch tree found for splatfacto-w at %PATCH_ROOT%\splatfacto-w
)

call :run_in_env cmd /d /s /c "cd /d "%ROOT_DIR%\splatfacto-w" && python -m pip install -e . --no-deps"
if errorlevel 1 exit /b %errorlevel%

call :ns_register_and_repin
exit /b %errorlevel%

:install_tetra_nerf
if errorlevel 1 exit /b %errorlevel%
goto :success

:install_tetra_nerf
echo.
echo [STEP] Installing Tetra-NeRF with Windows-safe patches...
call :clear_rocm_env
if errorlevel 1 exit /b %errorlevel%

if not exist "%ROOT_DIR%\tetra-nerf" (
    echo [INFO] Cloning tetra-nerf...
    call :run_in_env git clone https://github.com/jkulhanek/tetra-nerf.git
    if errorlevel 1 exit /b %errorlevel%
)

call :apply_patch_file "%PATCH_ROOT%\tetra-nerf\CMakeLists.txt" "%ROOT_DIR%\tetra-nerf\CMakeLists.txt"
if errorlevel 1 exit /b %errorlevel%

call :apply_patch_file "%PATCH_ROOT%\tetra-nerf\cmake\FindTorch.cmake" "%ROOT_DIR%\tetra-nerf\cmake\FindTorch.cmake"
if errorlevel 1 exit /b %errorlevel%

call :apply_patch_file "%PATCH_ROOT%\tetra-nerf\cmake\FindCUDA.cmake" "%ROOT_DIR%\tetra-nerf\cmake\FindCUDA.cmake"
if errorlevel 1 exit /b %errorlevel%

call :apply_patch_file "%PATCH_ROOT%\tetra-nerf\src\tetrahedra_tracer.h" "%ROOT_DIR%\tetra-nerf\src\tetrahedra_tracer.h"
if errorlevel 1 exit /b %errorlevel%

call :apply_patch_file "%PATCH_ROOT%\tetra-nerf\src\utils\vec_math.h" "%ROOT_DIR%\tetra-nerf\src\utils\vec_math.h"
if errorlevel 1 exit /b %errorlevel%

for %%I in ("C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v11.8") do set "CUDA118_SHORT=%%~sI"
for %%I in ("C:\Program Files\NVIDIA Corporation\OptiX SDK 9.1.0") do set "OPTIX_SHORT=%%~sI"

set "CUDA118_CMAKE=%CUDA118_SHORT:\=/%"
set "OPTIX_CMAKE=%OPTIX_SHORT:\=/%"
set "TETRA_SCRIPT=%TEMP%\tetra_build_%RANDOM%.cmd"

> "%TETRA_SCRIPT%" echo @echo off
>> "%TETRA_SCRIPT%" echo setlocal
>> "%TETRA_SCRIPT%" echo cd /d "%ROOT_DIR%\tetra-nerf"
>> "%TETRA_SCRIPT%" echo if exist build-cu118 rmdir /S /Q build-cu118
>> "%TETRA_SCRIPT%" echo set "PATH=%CUDA118_SHORT%\bin;%%PATH%%"
>> "%TETRA_SCRIPT%" echo cmake -S . -B build-cu118 -T cuda="%CUDA118_CMAKE%" -DCUDA_TOOLKIT_ROOT_DIR="%CUDA118_CMAKE%" -DOptiX_INSTALL_DIR="%OPTIX_CMAKE%"
>> "%TETRA_SCRIPT%" echo if errorlevel 1 exit /b 1
>> "%TETRA_SCRIPT%" echo cmake --build build-cu118 --config Release
>> "%TETRA_SCRIPT%" echo if errorlevel 1 exit /b 1
>> "%TETRA_SCRIPT%" echo python -m pip install -e . --no-deps

call :run_in_env cmd /d /s /c ""%TETRA_SCRIPT%""
set "TETRA_RC=%errorlevel%"
del /Q "%TETRA_SCRIPT%" >nul 2>nul

if not "%TETRA_RC%"=="0" exit /b %TETRA_RC%

call :ns_register_and_repin
exit /b %errorlevel%

:install_zipnerf
echo.
echo [STEP] Installing Zip-NeRF with Windows-safe patches...
call :clear_rocm_env
if errorlevel 1 exit /b %errorlevel%

if not exist "%ROOT_DIR%\zipnerf-pytorch" (
    echo [INFO] Cloning zipnerf-pytorch...
    call :run_in_env git clone https://github.com/SuLvXiangXin/zipnerf-pytorch.git
    if errorlevel 1 exit /b %errorlevel%
)

set "ZIP_PATCH_SRC=%PATCH_ROOT%\zipnerf-pytorch\extensions\cuda\setup.py"
set "ZIP_PATCH_DST=%ROOT_DIR%\zipnerf-pytorch\extensions\cuda\setup.py"

call :apply_patch_file "%ZIP_PATCH_SRC%" "%ZIP_PATCH_DST%"
if errorlevel 1 exit /b %errorlevel%
call :set_cuda_arch_env
call :set_cuda_env

echo [INFO] Installing Zip-NeRF CUDA extension...
call :run_in_env cmd /d /s /c "cd /d ""%ROOT_DIR%\zipnerf-pytorch\extensions\cuda"" && python -m pip install --no-build-isolation ."
if errorlevel 1 (
    echo [WARN] pip install . failed, trying setup.py install fallback...
    call :set_cuda_env
    call :run_in_env cmd /d /s /c "cd /d ""%ROOT_DIR%\zipnerf-pytorch\extensions\cuda"" && python setup.py install"
    if errorlevel 1 exit /b %errorlevel%
)

echo [INFO] Installing Zip-NeRF editable package...
call :run_in_env cmd /d /s /c "cd /d ""%ROOT_DIR%\zipnerf-pytorch"" && python -m pip install -e . --no-deps"
if errorlevel 1 exit /b %errorlevel%

call :run_in_env python -m pip install --upgrade tyro==0.8.12
if errorlevel 1 exit /b %errorlevel%

call :copy_zipnerf_configs
if errorlevel 1 exit /b %errorlevel%

call :ns_register_and_repin
exit /b %errorlevel%

:install_rmbrualla_pycolmap
echo [INFO] Installing rmbrualla pycolmap for Zip-NeRF compatibility...
call :run_in_env python -m pip install --upgrade --force-reinstall --no-deps --no-build-isolation git+https://github.com/rmbrualla/pycolmap.git
exit /b %errorlevel%

:install_torch_scatter
echo [INFO] Installing torch-scatter compatible with torch 2.1/cu118...
call :run_in_env python -m pip install --upgrade --force-reinstall --no-deps torch-scatter==2.1.2+pt21cu118 -f https://data.pyg.org/whl/torch-2.1.0+cu118.html
exit /b %errorlevel%

:copy_zipnerf_configs
set "ZIP_CFG_SRC=%ROOT_DIR%\zipnerf-pytorch\zipnerf_ns\config"
set "ZIP_CFG_DST="
for /f "usebackq delims=" %%I in (`call "%CONDA_EXE%" run -n "%TARGET_ENV%" python -c "import pathlib, nerfstudio; print(pathlib.Path(nerfstudio.__file__).resolve().parent / 'configs')"` ) do set "ZIP_CFG_DST=%%I"
if not defined ZIP_CFG_DST (
    echo [WARN] Could not resolve nerfstudio config path automatically. Skipping config copy.
    exit /b 0
)
if exist "%ZIP_CFG_SRC%" (
    echo [INFO] Copying Zip-NeRF config files into nerfstudio config dir...
    if not exist "%ZIP_CFG_DST%" mkdir "%ZIP_CFG_DST%" 2>nul
    xcopy /E /Y /I "%ZIP_CFG_SRC%\*" "%ZIP_CFG_DST%\" >nul
    exit /b 0
)
echo [WARN] Zip-NeRF config source not found, skipping copy: %ZIP_CFG_SRC%
exit /b 0

:ns_register_and_repin
echo [INFO] Running ns-install-cli to register plugins...
call :run_in_env ns-install-cli
if errorlevel 1 (
    call :run_in_env python -m nerfstudio.scripts.completions.install
    if errorlevel 1 exit /b %errorlevel%
)
call :repin_target
exit /b %errorlevel%

:repin_target
echo [INFO] Re-applying protected pinned stack after extra installation...
call :clear_rocm_env
call :run_in_env python "%PY_SCRIPT%" --lock-dir "%LOCK_DIR%" --conda-exe "%CONDA_EXE%" repin --skip-conda
exit /b %errorlevel%

:set_cuda_arch_env
if not defined TCNN_CUDA_ARCHITECTURES set "TCNN_CUDA_ARCHITECTURES=86"
if not defined TORCH_CUDA_ARCH_LIST set "TORCH_CUDA_ARCH_LIST=8.6"
if not defined MAX_JOBS set "MAX_JOBS=1"
exit /b 0

:ensure_support_packages
echo.
echo [STEP] Ensuring support packages used by extra methods...
call :clear_rocm_env

call :run_in_env python -m pip install --upgrade --force-reinstall --no-deps %PIN_TYRO% %PIN_NERFACC% %PIN_VISER% %PIN_HF_HUB% %PIN_BITSANDBYTES%
if errorlevel 1 exit /b %errorlevel%

call :run_in_env python -m pip install --upgrade --force-reinstall --no-deps %PIN_GSPLAT%
if errorlevel 1 exit /b %errorlevel%

call :run_in_env python -c "import torch; print(torch.__version__); import gsplat; from gsplat._torch_impl import quat_to_rotmat; print('gsplat OK')"
if errorlevel 1 exit /b %errorlevel%

call :ns_register_and_repin
exit /b %errorlevel%

:run_in_env
call :clear_rocm_env
echo [RUN] %*
call "%CONDA_EXE%" run -n "%TARGET_ENV%" --no-capture-output %*
exit /b %errorlevel%

:repin_target_env
echo.
echo [STEP] Re-pinning target env after extras...
call "%CONDA_BAT%" activate "%TARGET_ENV%"
if errorlevel 1 exit /b %errorlevel%
python "%PY_SCRIPT%" --lock-dir "%LOCK_DIR%" --conda-exe "%CONDA_EXE%" repin --skip-conda
set "_REP_RC=%errorlevel%"
call conda deactivate >nul 2>nul
exit /b %_REP_RC%

:run_ns_install_cli
echo.
echo [STEP] Running ns-install-cli...
call "%CONDA_BAT%" activate "%TARGET_ENV%"
if errorlevel 1 exit /b %errorlevel%
where ns-install-cli >nul 2>nul
if errorlevel 1 (
    python -m ns.install_cli
) else (
    ns-install-cli
)
set "_NSCLI_RC=%errorlevel%"
call conda deactivate >nul 2>nul
exit /b %_NSCLI_RC%


:install_core_overrides_from_manifest
if not exist "%CORE_OVERRIDES_JSON%" (
    echo [WARN] Core overrides manifest not found: %CORE_OVERRIDES_JSON%
    exit /b 0
)
for /f "usebackq delims=" %%I in (`call "%CONDA_EXE%" run -n "%TARGET_ENV%" python -c "import json, pathlib; p=pathlib.Path(r'%CORE_OVERRIDES_JSON%'); data=json.loads(p.read_text(encoding='utf-8')); items=data.get('core_overrides', {}); [print(v.get('install_ref','')) for k,v in items.items() if v.get('install_ref')]"`) do (
    echo [INFO] Installing core override: %%I
    call :run_in_env python -m pip install --upgrade --force-reinstall --no-deps --no-build-isolation %%I
    if errorlevel 1 exit /b %errorlevel%
)
exit /b 0

:install_manifest_methods
if not exist "%METHODS_PROTECTED_JSON%" (
    echo [WARN] Methods manifest not found: %METHODS_PROTECTED_JSON%
    exit /b 0
)
for /f "usebackq tokens=1,2,3 delims=|" %%A in (`call "%CONDA_EXE%" run -n "%TARGET_ENV%" python -c "import json, pathlib; p=pathlib.Path(r'%METHODS_PROTECTED_JSON%'); data=json.loads(p.read_text(encoding='utf-8')); items=data.get('protected_methods', {}); [print(f'{k}|{v.get('install_ref','')}|{v.get('patch_rel','')}') for k,v in items.items() if v.get('install_ref')]"`) do (
    call :install_one_manifest_method "%%~A" "%%~B" "%%~C"
    if errorlevel 1 exit /b %errorlevel%
)
exit /b 0

:install_one_manifest_method
set "METHOD_KEY=%~1"
set "METHOD_REF=%~2"
set "METHOD_PATCH_REL=%~3"
if /I "%METHOD_KEY%"=="zipnerf-pytorch" (
    call :install_zipnerf
    exit /b %errorlevel%
)
if /I "%METHOD_KEY%"=="tetra-nerf" (
    call :install_tetra_nerf
    exit /b %errorlevel%
)
if /I "%METHOD_KEY%"=="splatfacto-w" (
    call :install_splatfactow
    exit /b %errorlevel%
)
call :install_generic_manifest_method "%METHOD_KEY%" "%METHOD_REF%" "%METHOD_PATCH_REL%"
exit /b %errorlevel%

:install_generic_manifest_method
set "GEN_METHOD_KEY=%~1"
set "GEN_METHOD_REF=%~2"
set "GEN_METHOD_PATCH_REL=%~3"
if not defined GEN_METHOD_KEY (
    echo [ERROR] Missing generic method key.
    exit /b 1
)
set "GEN_METHOD_DIR=%ROOT_DIR%\%GEN_METHOD_KEY%"
if not exist "%GEN_METHOD_DIR%" (
    echo [INFO] Cloning %GEN_METHOD_KEY%...
    call :run_in_env git clone "%GEN_METHOD_REF%" "%GEN_METHOD_DIR%"
    if errorlevel 1 exit /b %errorlevel%
)
if defined GEN_METHOD_PATCH_REL (
    if exist "%PATCH_ROOT%\%GEN_METHOD_PATCH_REL%" (
        call :apply_patch_tree "%PATCH_ROOT%\%GEN_METHOD_PATCH_REL%" "%GEN_METHOD_DIR%"
        if errorlevel 1 exit /b %errorlevel%
    ) else (
        echo [INFO] No patch tree found for %GEN_METHOD_KEY% at %PATCH_ROOT%\%GEN_METHOD_PATCH_REL%
    )
)
call :run_in_env cmd /d /s /c "cd /d \"%GEN_METHOD_DIR%\" && python -m pip install -e . --no-deps"
if errorlevel 1 exit /b %errorlevel%
call :ns_register_and_repin
exit /b %errorlevel%

:apply_patch_tree
set "PATCH_TREE_SRC=%~1"
set "PATCH_TREE_DST=%~2"
if not exist "%PATCH_TREE_SRC%" (
    echo [WARN] Patch tree missing: %PATCH_TREE_SRC%
    exit /b 0
)
if not exist "%PATCH_TREE_DST%" (
    echo [ERROR] Patch destination root missing: %PATCH_TREE_DST%
    exit /b 1
)
for /r "%PATCH_TREE_SRC%" %%F in (*) do (
    set "SRC_FILE=%%~fF"
    set "REL_FILE=!SRC_FILE:%PATCH_TREE_SRC%\=!"
    if /I not "%%~xF"==".diff" if /I not "%%~xF"==".patch" if /I not "%%~xF"==".patched" (
        call :apply_patch_file "%%~fF" "%PATCH_TREE_DST%\!REL_FILE!"
        if errorlevel 1 exit /b %errorlevel%
    )
)
exit /b 0

:apply_patch_file
set "PATCH_SRC=%~1"
set "PATCH_DST=%~2"

if not defined PATCH_SRC (
    echo [ERROR] Missing patch source path.
    exit /b 1
)
if not defined PATCH_DST (
    echo [ERROR] Missing patch destination path.
    exit /b 1
)

if not exist "%PATCH_SRC%" (
    echo [ERROR] Patch source not found: %PATCH_SRC%
    exit /b 1
)

if not exist "%PATCH_DST%" (
    echo [ERROR] Patch target not found: %PATCH_DST%
    exit /b 1
)

if not exist "%PATCH_DST%.orig" (
    copy /Y "%PATCH_DST%" "%PATCH_DST%.orig" >nul
    if errorlevel 1 (
        echo [ERROR] Failed creating backup: %PATCH_DST%.orig
        exit /b 1
    )
)

copy /Y "%PATCH_SRC%" "%PATCH_DST%" >nul
if errorlevel 1 (
    echo [ERROR] Failed applying patch file.
    exit /b 1
)

echo [OK] Applied patch:
echo      SRC: %PATCH_SRC%
echo      DST: %PATCH_DST%
exit /b 0

:clear_rocm_env
set "ROCM_HOME="
set "ROCM_PATH="
set "HIP_HOME="
set "HIP_PATH="
set "HCC_HOME="
set "HIP_PATH_57="
set "HIP_DEVICE_LIB_PATH="
set "PYTORCH_ROCM_ARCH="
exit /b 0


