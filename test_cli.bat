@echo off
echo.
echo ========== Nerfstudio CLI Validator ==========
echo.
@echo off
REM Ensure UTF-8 output
chcp 65001 > nul
set PYTHONIOENCODING=utf-8

REM Check if CLI works
echo Running: ns-train --help
ns-train --help
if errorlevel 1 (
    echo ❌ ERROR: ns-train failed to run. CLI may be broken or module not registered.
    goto end
)

REM Check if viewer works
echo.
echo Running: ns-viewer --help
ns-viewer --help
if errorlevel 1 (
    echo ❌ ERROR: ns-viewer failed to run.
    goto end
)

REM Optional: Detect available trainers
echo.
echo 🔍 Listing available trainers:
ns-train --help | findstr /R "Usage:.*"

REM (Optional dry-run logic can be added here per addon)

echo.
echo ✅ CLI appears to be working correctly.

:end
pause
