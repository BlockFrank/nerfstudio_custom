@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "ROOT_DIR=%CD%"
set "LOCK_DIR=%ROOT_DIR%\deps-lock"
set "PY_SCRIPT=%ROOT_DIR%\deps_lock.py"
set "PORTABLE_ENV_BAT=%ROOT_DIR%\portable_env.bat"
set "INSTALLER_SELECTION_JSON=%LOCK_DIR%\installer-selection.json"
set "MSVC_TOOLSET_LIST_FILE=%LOCK_DIR%\msvc-toolsets.txt"
set "MSVC_SELECTED_LOG=%LOCK_DIR%\msvc-selected.txt"

if not exist "%LOCK_DIR%" mkdir "%LOCK_DIR%" 2>nul
if not exist "%PY_SCRIPT%" (
    echo [ERROR] Missing "%PY_SCRIPT%"
    exit /b 1
)

call :select_conda_backend
if errorlevel 1 exit /b %errorlevel%

call :activate_target_env "%~1"
if errorlevel 1 exit /b %errorlevel%

call :select_gpu_arch
if errorlevel 1 exit /b %errorlevel%

call :select_msvc_toolset
if errorlevel 1 exit /b %errorlevel%

call :write_installer_selection_json
if errorlevel 1 exit /b %errorlevel%

echo.
echo ============================================
echo   Freeze current env to deps-lock
echo ============================================
echo ROOT_DIR                = %ROOT_DIR%
echo LOCK_DIR                = %LOCK_DIR%
echo PY_SCRIPT               = %PY_SCRIPT%
echo CONDA_MODE              = %CONDA_MODE%
echo CONDA_ROOT              = %SELECTED_CONDA_ROOT%
echo CONDA_DEFAULT_ENV       = %CONDA_DEFAULT_ENV%
echo CONDA_PREFIX            = %CONDA_PREFIX%
echo GPU_NAME                = %GPU_NAME%
echo CUDA_ARCH               = %CUDA_ARCH%
echo TCNN_CUDA_ARCHITECTURES = %TCNN_CUDA_ARCHITECTURES%
echo Preferred MSVC mode     = %PREFERRED_MSVC%
echo Available toolsets log  = %MSVC_TOOLSET_LIST_FILE%
echo Bootstrap result log    = %MSVC_SELECTED_LOG%
echo ============================================

"%PYTHON_EXE%" "%PY_SCRIPT%" --lock-dir "%LOCK_DIR%" --conda-exe "%CONDA_EXE%" --msvc-mode "%PREFERRED_MSVC%" export
if errorlevel 1 exit /b %errorlevel%

echo.
set "MISSING=0"
for %%F in (
  "%LOCK_DIR%\pip-freeze-all.txt"
  "%LOCK_DIR%\pip-freeze-replay.txt"
  "%LOCK_DIR%\build-plan.json"
  "%LOCK_DIR%\lock-meta.json"
  "%LOCK_DIR%\numpy-compat-audit.txt"
  "%LOCK_DIR%\msvc-toolsets.txt"
  "%LOCK_DIR%\msvc-selected.txt"
) do (
  if exist %%~F (
    echo [OK] Exists: %%~F
  ) else (
    echo [ERROR] Missing expected file: %%~F
    set "MISSING=1"
  )
)

set "FOUND_CONDA_LOCK=0"
for %%F in ("%LOCK_DIR%\conda-explicit-*.txt") do (
  if exist "%%~F" (
    echo [OK] Exists: %%~F
    set "FOUND_CONDA_LOCK=1"
  )
)

if "%MISSING%"=="1" exit /b 1

echo.
echo [DONE] Freeze completed.
exit /b 0


:activate_target_env
set "TARGET_ENV=%~1"

if defined TARGET_ENV (
    echo [INFO] Activating target env: %TARGET_ENV%
    call "%CONDA_BAT%" activate "%TARGET_ENV%"
    exit /b %errorlevel%
)

if defined CONDA_PREFIX (
    echo [INFO] Current active env detected:
    echo        %CONDA_PREFIX%
    set "USE_CURRENT="
    set /p "USE_CURRENT=Export CURRENT active env? [Y/n]: "
    if /I "!USE_CURRENT!"=="N" (
        set "TARGET_ENV="
        set /p "TARGET_ENV=Enter conda env name to activate before export: "
        if defined TARGET_ENV (
            call "%CONDA_BAT%" activate "%TARGET_ENV%"
            exit /b %errorlevel%
        )
    ) else (
        exit /b 0
    )
)

exit /b 0


:select_conda_backend
echo.
echo Freeze source conda backend:
echo   1. portable  ^(project-local .conda^)
echo   2. system    ^(existing Anaconda/Miniconda on this PC^)
echo   3. current   ^(derive from active shell / PATH^)

set "CONDA_MODE_CHOICE="
set /p "CONDA_MODE_CHOICE=Choose source backend [1-3, default 1]: "
if not defined CONDA_MODE_CHOICE set "CONDA_MODE_CHOICE=1"

if "%CONDA_MODE_CHOICE%"=="1" call :resolve_named_conda_backend portable
if "%CONDA_MODE_CHOICE%"=="2" call :resolve_named_conda_backend system
if "%CONDA_MODE_CHOICE%"=="3" call :resolve_named_conda_backend current
if errorlevel 1 exit /b %errorlevel%

if not defined RESOLVED_CONDA_MODE (
    echo [ERROR] Invalid conda backend choice.
    exit /b 1
)

set "CONDA_MODE=%RESOLVED_CONDA_MODE%"
set "SELECTED_CONDA_ROOT=%RESOLVED_CONDA_ROOT%"
set "CONDA_EXE=%RESOLVED_CONDA_EXE%"
set "CONDA_BAT=%RESOLVED_CONDA_BAT%"
set "PYTHON_EXE=%RESOLVED_PYTHON_EXE%"
exit /b 0


:resolve_named_conda_backend
set "REQ_MODE=%~1"
set "RESOLVED_CONDA_MODE="
set "RESOLVED_CONDA_ROOT="
set "RESOLVED_CONDA_EXE="
set "RESOLVED_CONDA_BAT="
set "RESOLVED_PYTHON_EXE="

if /I "%REQ_MODE%"=="portable" goto :resolve_portable
if /I "%REQ_MODE%"=="system" goto :resolve_system
if /I "%REQ_MODE%"=="current" goto :resolve_current

echo [ERROR] Unknown conda backend: %REQ_MODE%
exit /b 1


:resolve_portable
if not exist "%PORTABLE_ENV_BAT%" (
    echo [ERROR] Missing portable helper: %PORTABLE_ENV_BAT%
    exit /b 1
)

call "%PORTABLE_ENV_BAT%"
if errorlevel 1 exit /b %errorlevel%

if not defined PORTABLE_CONDA_ROOT if exist "%ROOT_DIR%\.conda\Scripts\conda.exe" set "PORTABLE_CONDA_ROOT=%ROOT_DIR%\.conda"
if not defined PORTABLE_CONDA_ROOT (
    echo [ERROR] PORTABLE_CONDA_ROOT not exported by portable_env.bat
    exit /b 1
)

set "RESOLVED_CONDA_MODE=portable"
set "RESOLVED_CONDA_ROOT=%PORTABLE_CONDA_ROOT%"
set "RESOLVED_CONDA_EXE=%PORTABLE_CONDA_ROOT%\Scripts\conda.exe"
set "RESOLVED_CONDA_BAT=%PORTABLE_CONDA_ROOT%\condabin\conda.bat"
set "RESOLVED_PYTHON_EXE=%PORTABLE_CONDA_ROOT%\python.exe"
goto :validate_resolved_conda


:resolve_system
call :detect_system_conda_root
if errorlevel 1 exit /b %errorlevel%

set "RESOLVED_CONDA_MODE=system"
set "RESOLVED_CONDA_ROOT=%SYSTEM_CONDA_ROOT%"
set "RESOLVED_CONDA_EXE=%SYSTEM_CONDA_ROOT%\Scripts\conda.exe"
set "RESOLVED_CONDA_BAT=%SYSTEM_CONDA_ROOT%\condabin\conda.bat"
set "RESOLVED_PYTHON_EXE=%SYSTEM_CONDA_ROOT%\python.exe"
goto :validate_resolved_conda


:resolve_current
if defined CONDA_EXE (
    for %%I in ("%CONDA_EXE%") do set "CUR_SCRIPTS_DIR=%%~dpI"
    for %%I in ("!CUR_SCRIPTS_DIR!..") do set "CUR_CONDA_ROOT=%%~fI"
)

if not defined CUR_CONDA_ROOT for /f "delims=" %%I in ('where conda.exe 2^>nul') do if not defined CUR_CONDA_ROOT (
    for %%J in ("%%I") do set "CUR_SCRIPTS_DIR=%%~dpJ"
    for %%J in ("!CUR_SCRIPTS_DIR!..") do set "CUR_CONDA_ROOT=%%~fJ"
)

if not defined CUR_CONDA_ROOT (
    echo [ERROR] Could not derive current conda root from active shell / PATH.
    exit /b 1
)

set "RESOLVED_CONDA_MODE=current"
set "RESOLVED_CONDA_ROOT=%CUR_CONDA_ROOT%"
set "RESOLVED_CONDA_EXE=%CUR_CONDA_ROOT%\Scripts\conda.exe"
set "RESOLVED_CONDA_BAT=%CUR_CONDA_ROOT%\condabin\conda.bat"
set "RESOLVED_PYTHON_EXE=%CUR_CONDA_ROOT%\python.exe"
goto :validate_resolved_conda


:validate_resolved_conda
if not exist "%RESOLVED_CONDA_EXE%" (
    echo [ERROR] Conda executable not found: %RESOLVED_CONDA_EXE%
    exit /b 1
)
if not exist "%RESOLVED_PYTHON_EXE%" (
    echo [ERROR] Python executable not found: %RESOLVED_PYTHON_EXE%
    exit /b 1
)
exit /b 0


:detect_system_conda_root
set "SYSTEM_CONDA_ROOT="

if defined CONDA_EXE (
    echo %CONDA_EXE% | find /I "%ROOT_DIR%\.conda" >nul
    if errorlevel 1 (
        for %%I in ("%CONDA_EXE%") do set "_sys_scripts=%%~dpI"
        for %%I in ("!_sys_scripts!..") do set "SYSTEM_CONDA_ROOT=%%~fI"
    )
)

if not defined SYSTEM_CONDA_ROOT for /f "delims=" %%I in ('where conda.exe 2^>nul') do (
    echo %%I | find /I "%ROOT_DIR%\.conda" >nul
    if errorlevel 1 if not defined SYSTEM_CONDA_ROOT (
        for %%J in ("%%I") do set "_sys_scripts=%%~dpJ"
        for %%J in ("!_sys_scripts!..") do set "SYSTEM_CONDA_ROOT=%%~fJ"
    )
)

if not defined SYSTEM_CONDA_ROOT if exist "%UserProfile%\miniconda3\Scripts\conda.exe" set "SYSTEM_CONDA_ROOT=%UserProfile%\miniconda3"
if not defined SYSTEM_CONDA_ROOT if exist "%UserProfile%\anaconda3\Scripts\conda.exe" set "SYSTEM_CONDA_ROOT=%UserProfile%\anaconda3"
if not defined SYSTEM_CONDA_ROOT if exist "%ProgramData%\Miniconda3\Scripts\conda.exe" set "SYSTEM_CONDA_ROOT=%ProgramData%\Miniconda3"
if not defined SYSTEM_CONDA_ROOT if exist "%ProgramData%\Anaconda3\Scripts\conda.exe" set "SYSTEM_CONDA_ROOT=%ProgramData%\Anaconda3"

if not defined SYSTEM_CONDA_ROOT (
    echo [ERROR] Could not find a system conda installation.
    exit /b 1
)
exit /b 0


:select_gpu_arch
set "GPU_NAME=unknown"
set "CUDA_ARCH="
set "TCNN_CUDA_ARCHITECTURES="

echo.
echo GPU arch mode:
echo   1. Auto-detect from nvidia-smi
echo   2. Manual entry
echo   3. Leave blank / skip

set "GPU_MODE="
set /p "GPU_MODE=Choose GPU arch mode [1-3, default 1]: "
if not defined GPU_MODE set "GPU_MODE=1"

if "%GPU_MODE%"=="1" goto :gpu_auto
if "%GPU_MODE%"=="2" goto :gpu_manual
if "%GPU_MODE%"=="3" goto :gpu_skip

echo [ERROR] Invalid GPU mode.
exit /b 1

:gpu_skip
exit /b 0

:gpu_auto
for /f "usebackq delims=" %%G in (`nvidia-smi --query-gpu=name --format=csv,noheader 2^>nul`) do if /I "!GPU_NAME!"=="unknown" set "GPU_NAME=%%G"
call :map_gpu_to_arch "%GPU_NAME%"
if not defined CUDA_ARCH goto :gpu_manual_default
set "TCNN_CUDA_ARCHITECTURES=%CUDA_ARCH%"
exit /b 0

:gpu_manual_default
set "GPU_NAME=manual"
set /p "CUDA_ARCH=Enter CUDA arch [default 86 for RTX 3090]: "
if not defined CUDA_ARCH set "CUDA_ARCH=86"
set "TCNN_CUDA_ARCHITECTURES=%CUDA_ARCH%"
exit /b 0

:gpu_manual
set "GPU_NAME=manual"
set /p "CUDA_ARCH=Enter CUDA arch (75, 80, 86, 89, 90, 120 ...): "
if not defined CUDA_ARCH exit /b 1
set "TCNN_CUDA_ARCHITECTURES=%CUDA_ARCH%"
exit /b 0

:map_gpu_to_arch
set "GPU_LABEL=%~1"
set "CUDA_ARCH="
echo %GPU_LABEL% | find /I "3090" >nul && set "CUDA_ARCH=86"
echo %GPU_LABEL% | find /I "4090" >nul && set "CUDA_ARCH=89"
echo %GPU_LABEL% | find /I "H100" >nul && set "CUDA_ARCH=90"
exit /b 0


:select_msvc_toolset
set "PREFERRED_MSVC="
echo.
echo Preferred MSVC toolset:
echo   1. auto    ^(prefer 14.38 if found, else best compatible^)
echo   2. 14.38   ^(force VS2022 v143 14.38 toolset if installed^)
echo   3. 14      ^(any 14.x compatible MSVC^)
echo   4. system  ^(do not force; use current/default MSVC on PATH^)
set /p "MSVC_CHOICE=Choose preferred MSVC toolset [1-4, default 1]: "
if not defined MSVC_CHOICE set "MSVC_CHOICE=1"

if "%MSVC_CHOICE%"=="1" set "PREFERRED_MSVC=auto"
if "%MSVC_CHOICE%"=="2" set "PREFERRED_MSVC=14.38"
if "%MSVC_CHOICE%"=="3" set "PREFERRED_MSVC=14"
if "%MSVC_CHOICE%"=="4" set "PREFERRED_MSVC=system"

if not defined PREFERRED_MSVC (
    echo [ERROR] Invalid MSVC choice.
    exit /b 1
)

if not exist "%LOCK_DIR%" mkdir "%LOCK_DIR%" 2>nul

> "%MSVC_TOOLSET_LIST_FILE%" echo Detected MSVC toolsets:
for %%R in (
    "%ProgramFiles%\Microsoft Visual Studio\2022\BuildTools"
    "%ProgramFiles%\Microsoft Visual Studio\2022\Community"
    "%ProgramFiles%\Microsoft Visual Studio\2022\Professional"
    "%ProgramFiles%\Microsoft Visual Studio\2022\Enterprise"
    "%ProgramFiles(x86)%\Microsoft Visual Studio\2022\BuildTools"
    "%ProgramFiles(x86)%\Microsoft Visual Studio\2022\Community"
    "%ProgramFiles(x86)%\Microsoft Visual Studio\2022\Professional"
    "%ProgramFiles(x86)%\Microsoft Visual Studio\2022\Enterprise"
) do (
    if exist "%%~R\VC\Tools\MSVC" (
        for /d %%T in ("%%~R\VC\Tools\MSVC\*") do (
            >> "%MSVC_TOOLSET_LIST_FILE%" echo %%~nxT ^| %%~R
        )
    )
)

if exist "%MSVC_TOOLSET_LIST_FILE%" type "%MSVC_TOOLSET_LIST_FILE%"
exit /b 0


:write_installer_selection_json
if not exist "%LOCK_DIR%" mkdir "%LOCK_DIR%" 2>nul
if not exist "%LOCK_DIR%" (
    echo [ERROR] Unable to create lock directory: %LOCK_DIR%
    exit /b 1
)

set "MSVC_HINT="
set "MSVC_INSTALL_HINT="
set "MSVC_INSTALL_HINT_SHORT="

if exist "%MSVC_TOOLSET_LIST_FILE%" (
    for /f "usebackq tokens=1,* delims=|" %%A in ("%MSVC_TOOLSET_LIST_FILE%") do (
        set "MSVC_VER=%%~A"
        set "MSVC_LOC=%%~B"
        call :trim_var MSVC_VER
        call :trim_var MSVC_LOC

        if defined MSVC_VER (
            echo !MSVC_VER! | findstr /R "^[0-9][0-9]*\.[0-9][0-9]*" >nul
            if not errorlevel 1 (
                if /I "%PREFERRED_MSVC%"=="auto" (
                    if not defined MSVC_HINT if /I "!MSVC_VER:~0,5!"=="14.38" (
                        set "MSVC_HINT=!MSVC_VER!"
                        set "MSVC_INSTALL_HINT=!MSVC_LOC!"
                    )
                ) else if /I "%PREFERRED_MSVC%"=="14.38" (
                    if not defined MSVC_HINT if /I "!MSVC_VER:~0,5!"=="14.38" (
                        set "MSVC_HINT=!MSVC_VER!"
                        set "MSVC_INSTALL_HINT=!MSVC_LOC!"
                    )
                ) else if /I "%PREFERRED_MSVC%"=="14" (
                    if not defined MSVC_HINT if /I "!MSVC_VER:~0,3!"=="14." (
                        set "MSVC_HINT=!MSVC_VER!"
                        set "MSVC_INSTALL_HINT=!MSVC_LOC!"
                    )
                )
            )
        )
    )
)

if not defined MSVC_HINT set "MSVC_HINT=%PREFERRED_MSVC%"
if defined MSVC_INSTALL_HINT call :to_short_path "%MSVC_INSTALL_HINT%" MSVC_INSTALL_HINT_SHORT
if not defined MSVC_INSTALL_HINT_SHORT set "MSVC_INSTALL_HINT_SHORT=%MSVC_INSTALL_HINT%"

"%PYTHON_EXE%" -c "import json, pathlib; from datetime import datetime, timezone; p=pathlib.Path(r'%INSTALLER_SELECTION_JSON%'); p.parent.mkdir(parents=True, exist_ok=True); data={'cuda_arch': r'%CUDA_ARCH%','tcnn_cuda_architectures': r'%TCNN_CUDA_ARCHITECTURES%','gpu_name': r'%GPU_NAME%','preferred_msvc': r'%PREFERRED_MSVC%','preferred_msvc_mode': r'%PREFERRED_MSVC%','selected_msvc_toolset_hint': r'%MSVC_HINT%','selected_msvc_installation_hint': r'%MSVC_INSTALL_HINT_SHORT%','conda_mode': r'%CONDA_MODE%','conda_root': r'%SELECTED_CONDA_ROOT%','written_utc': datetime.now(timezone.utc).isoformat()}; p.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')"
if errorlevel 1 (
    echo [ERROR] Failed to write installer selection metadata.
    exit /b 1
)

echo [OK] Wrote installer selection metadata: %INSTALLER_SELECTION_JSON%
exit /b 0


:trim_var
setlocal EnableDelayedExpansion
set "s=!%~1!"
if not defined s (
    endlocal & set "%~1=" & exit /b 0
)
for /f "tokens=* delims= " %%Z in ("!s!") do set "s=%%Z"
:trim_var_r
if "!s:~-1!"==" " set "s=!s:~0,-1!" & goto trim_var_r
endlocal & set "%~1=%s%"
exit /b 0


:to_short_path
setlocal
set "in=%~1"
set "out="
if not defined in (
    endlocal & set "%~2=" & exit /b 0
)
for %%I in ("%in%") do set "out=%%~sI"
if not defined out set "out=%in%"
endlocal & set "%~2=%out%"
exit /b 0
