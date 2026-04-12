@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "ROOT=%CD%"
set "DOCTOR_PY=%ROOT%\doctor.py"
set "PORTABLE_ENV_BAT=%ROOT%\portable_env.bat"
set "PYTHON_EXE="

echo ==========================================
echo   Nerfstudio Doctor
echo ==========================================

if exist "%PORTABLE_ENV_BAT%" (
    echo [INFO] Activating portable conda...
    call "%PORTABLE_ENV_BAT%"
    if errorlevel 1 echo [WARN] Portable activation failed. Trying current python.
)

if not exist "%DOCTOR_PY%" (
    echo [ERROR] Missing doctor script:
    echo   %DOCTOR_PY%
    exit /b 1
)

if not defined PYTHON_EXE if exist "%ROOT%\.conda\python.exe" set "PYTHON_EXE=%ROOT%\.conda\python.exe"
if not defined PYTHON_EXE if defined CONDA_PREFIX if exist "%CONDA_PREFIX%\python.exe" set "PYTHON_EXE=%CONDA_PREFIX%\python.exe"
if not defined PYTHON_EXE set "PYTHON_EXE=python"

echo [INFO] Running diagnostics with: %PYTHON_EXE%
"%PYTHON_EXE%" "%DOCTOR_PY%" %*
if errorlevel 1 (
    echo.
    echo [FAIL] Doctor detected problems
    exit /b 1
)

echo.
echo [OK] Environment is healthy
exit /b 0
