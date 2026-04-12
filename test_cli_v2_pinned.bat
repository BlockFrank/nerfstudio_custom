@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

call "%~dp0portable_env.bat"
if errorlevel 1 exit /b %errorlevel%

set "ROOT_DIR=%CD%"
set "LOCK_DIR=%ROOT_DIR%\deps-lock"

if not exist "%LOCK_DIR%\pip-freeze-all.txt" (
    echo [ERROR] Missing %LOCK_DIR%\pip-freeze-all.txt
    exit /b 1
)

echo ============================================
echo   Nerfstudio pinned CLI validation
echo ============================================
echo.

python "%ROOT_DIR%\deps_lock.py" --lock-dir "%LOCK_DIR%" --conda-exe "%CONDA_EXE%" check
if errorlevel 1 exit /b %errorlevel%

python -c "import torch, torchvision, nerfstudio; print('[OK] core imports passed')"
if errorlevel 1 exit /b %errorlevel%

where ns-install-cli >nul 2>nul
if errorlevel 1 (
    echo [WARN] ns-install-cli not found on PATH in this shell.
) else (
    ns-install-cli --help >nul 2>nul
    if errorlevel 1 (
        echo [WARN] ns-install-cli exists but did not return cleanly.
    ) else (
        echo [OK] ns-install-cli responded.
    )
)

where ns-train >nul 2>nul
if errorlevel 1 (
    echo [WARN] ns-train not found on PATH in this shell.
) else (
    ns-train --help >nul 2>nul
    if errorlevel 1 (
        echo [WARN] ns-train exists but did not return cleanly.
    ) else (
        echo [OK] ns-train responded.
    )
)

echo [OK] CLI validation complete.
exit /b 0
