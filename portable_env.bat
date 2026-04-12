@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

set "ROOT_DIR=%CD%"
set "PORTABLE_CONDA_ROOT=%ROOT_DIR%\.conda"
set "CONDA_BAT=%PORTABLE_CONDA_ROOT%\condabin\conda.bat"
set "CONDA_EXE=%PORTABLE_CONDA_ROOT%\Scripts\conda.exe"
set "BOOTSTRAP_EXE=%ROOT_DIR%\Miniconda3-py310_26.1.1-1-Windows-x86_64.exe"
set "BOOTSTRAP_URL=https://repo.anaconda.com/miniconda/Miniconda3-py310_26.1.1-1-Windows-x86_64.exe"

if exist "%CONDA_BAT%" goto :activate_portable

echo [INFO] Portable conda not found. Bootstrapping...

if not exist "%BOOTSTRAP_EXE%" (
    echo [INFO] Downloading Miniconda Python 3.10 bootstrapper...
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "$ProgressPreference='SilentlyContinue';" ^
      "$url='%BOOTSTRAP_URL%';" ^
      "$out='%BOOTSTRAP_EXE%';" ^
      "Invoke-WebRequest -Uri $url -OutFile $out"
    if errorlevel 1 (
        echo [ERROR] Failed to download Miniconda bootstrapper.
        exit /b 1
    )
)

echo [INFO] Installing portable Miniconda into:
echo         %PORTABLE_CONDA_ROOT%

start /wait "" "%BOOTSTRAP_EXE%" ^
    /InstallationType=JustMe ^
    /RegisterPython=0 ^
    /AddToPath=0 ^
    /S ^
    /D=%PORTABLE_CONDA_ROOT%

if errorlevel 1 (
    echo [ERROR] Portable Miniconda installation failed.
    exit /b 1
)

if not exist "%CONDA_BAT%" (
    echo [ERROR] Portable conda install completed but conda.bat was not found.
    exit /b 1
)

if not exist "%PORTABLE_CONDA_ROOT%\.condarc" (
    >"%PORTABLE_CONDA_ROOT%\.condarc" echo auto_activate_base: true
    >>"%PORTABLE_CONDA_ROOT%\.condarc" echo channels:
    >>"%PORTABLE_CONDA_ROOT%\.condarc" echo   - defaults
    >>"%PORTABLE_CONDA_ROOT%\.condarc" echo solver: libmamba
    >>"%PORTABLE_CONDA_ROOT%\.condarc" echo envs_dirs:
    >>"%PORTABLE_CONDA_ROOT%\.condarc" echo   - %PORTABLE_CONDA_ROOT%\envs
    >>"%PORTABLE_CONDA_ROOT%\.condarc" echo pkgs_dirs:
    >>"%PORTABLE_CONDA_ROOT%\.condarc" echo   - %PORTABLE_CONDA_ROOT%\pkgs
)

:activate_portable
echo [INFO] Activating portable conda base...

set "CONDA_SHLVL="
set "CONDA_PREFIX="
set "CONDA_DEFAULT_ENV="
set "CONDA_EXE="
set "PYTHONHOME="
set "PYTHONPATH="

call "%CONDA_BAT%" activate "%PORTABLE_CONDA_ROOT%"
if errorlevel 1 (
    echo [ERROR] Failed to activate portable conda base.
    exit /b 1
)

for /f "delims=" %%P in ('where python 2^>nul') do (
    set "FIRST_PY=%%P"
    goto :gotpy
)

echo [ERROR] python not found after portable activation.
exit /b 1

:gotpy
if /I not "%FIRST_PY%"=="%PORTABLE_CONDA_ROOT%\python.exe" (
    echo [WARN] First python on PATH is not portable python:
    echo        %FIRST_PY%
    echo [INFO] Forcing portable python to the front of PATH...
    set "PATH=%PORTABLE_CONDA_ROOT%;%PORTABLE_CONDA_ROOT%\Scripts;%PORTABLE_CONDA_ROOT%\Library\bin;%PORTABLE_CONDA_ROOT%\condabin;%PATH%"
)

echo [OK] Portable conda active.
where python
python --version

endlocal & (
    set "ROOT_DIR=%ROOT_DIR%"
    set "PORTABLE_CONDA_ROOT=%PORTABLE_CONDA_ROOT%"
    set "CONDA_BAT=%CONDA_BAT%"
    set "CONDA_EXE=%CONDA_EXE%"
    set "BOOTSTRAP_EXE=%BOOTSTRAP_EXE%"
)
exit /b 0
