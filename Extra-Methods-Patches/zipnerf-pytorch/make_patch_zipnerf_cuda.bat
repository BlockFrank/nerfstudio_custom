@echo off
setlocal EnableExtensions

REM Script lives in Extra-Methods-Patches\zipnerf-pytorch
cd /d "%~dp0"
set "PATCH_ROOT=%CD%"

REM Go up to nerfstudio_custom root
cd /d "%PATCH_ROOT%\..\.."
set "ROOT_DIR=%CD%"

REM Paths
set "ORIG_FILE=%ROOT_DIR%\zipnerf-pytorch\extensions\cuda\setup.py"
set "PATCHED_FILE=%PATCH_ROOT%\extensions\cuda\setup.py"
set "PATCH_FILE=%PATCH_ROOT%\extensions\cuda\setup.py.patch"

REM Checks
if not exist "%ORIG_FILE%" (
    echo [ERROR] Original file not found:
    echo         %ORIG_FILE%
    exit /b 1
)

if not exist "%PATCHED_FILE%" (
    echo [ERROR] Patched file not found:
    echo         %PATCHED_FILE%
    exit /b 1
)

where git >nul 2>nul
if errorlevel 1 (
    echo [ERROR] git not found in PATH
    exit /b 1
)

echo [INFO] Generating patch...
git diff --no-index "%ORIG_FILE%" "%PATCHED_FILE%" > "%PATCH_FILE%"
set "RC=%errorlevel%"

if "%RC%"=="0" (
    echo [INFO] No differences found
    echo [INFO] Patch file still written:
    echo        %PATCH_FILE%
    exit /b 0
)

if "%RC%"=="1" (
    echo [OK] Patch created:
    echo      %PATCH_FILE%
    exit /b 0
)

echo [ERROR] git diff failed with code %RC%
del /q "%PATCH_FILE%" >nul 2>nul
exit /b %RC%