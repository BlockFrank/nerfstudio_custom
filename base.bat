@echo off
setlocal enabledelayedexpansion

REM ==== CONFIG ====
set ENV_NAME=nerfstudio
set YAML_FILE=nerfstudio_stable_environment_post_zipnerf.yaml
set REQUIREMENTS=requirements_post_zipnerf.txt
set PYTHON_EXE=python

echo.
echo === Nerfstudio Base Installer ===
echo.

REM === Choose install mode ===
choice /C CVP /M "Choose environment type: (C)onda, (V)env, or (P)reinstalled python?"
if errorlevel 3 set INSTALL_MODE=PYTHON
if errorlevel 2 set INSTALL_MODE=VENV
if errorlevel 1 set INSTALL_MODE=CONDA

REM === Setup environment ===
if "%INSTALL_MODE%"=="CONDA" (
    choice /C YN /M "Use YAML file? (Y=yes, N=use requirements.txt)"
    if errorlevel 2 (
        echo Creating conda env from pip reqs...
        conda create -y -n %ENV_NAME% python=3.10
        call conda activate %ENV_NAME%
        pip install -r %REQUIREMENTS%
    ) else (
        echo Creating conda env from YAML...
        conda env create -f %YAML_FILE%
        call conda activate %ENV_NAME%
    )
) else if "%INSTALL_MODE%"=="VENV" (
    echo Creating venv...
    %PYTHON_EXE% -m venv %ENV_NAME%
    call %ENV_NAME%\Scripts\activate
    pip install -r %REQUIREMENTS%
) else (
    echo Using system-installed Python...
    pip install -r %REQUIREMENTS%
)

REM === Nerfstudio CLI ===
pip install nerfstudio
call ns-install-cli

echo.
echo ✅ Base Nerfstudio environment ready.
echo Run extras.bat to install optional modules.
pause
