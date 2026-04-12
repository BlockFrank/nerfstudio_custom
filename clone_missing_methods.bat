@echo off
set ROOT=%CD%

echo ==============================
echo Cloning missing Nerfstudio methods
echo ==============================

REM ---- splatfacto-w ----
if not exist "%ROOT%\splatfacto-w" (
    echo Cloning splatfacto-w...
    git clone https://github.com/your-fork/splatfacto-w.git
)

REM ---- zipnerf ----
if not exist "%ROOT%\zipnerf-pytorch" (
    echo Cloning zipnerf-pytorch...
    git clone https://github.com/SuLvXiangXin/zipnerf-pytorch.git
)

REM ---- instruct-gs2gs ----
if not exist "%ROOT%\instruct-gs2gs" (
    echo Cloning instruct-gs2gs...
    git clone https://github.com/ashawkey/instruct-gs2gs.git
)

REM ---- tetra-nerf ----
if not exist "%ROOT%\tetra-nerf" (
    echo Cloning tetra-nerf...
    git clone https://github.com/jkulhanek/tetra-nerf.git
)

REM ---- opennerf ----
if not exist "%ROOT%\opennerf" (
    echo Cloning opennerf...
    git clone https://github.com/opennerf/opennerf.git
)

REM ---- OPTIONAL / PRESENT IN YOUR ROOT ----

if not exist "%ROOT%\sdfstudio" (
    echo Cloning sdfstudio...
    git clone https://github.com/autonomousvision/sdfstudio.git
)

if not exist "%ROOT%\relationfield" (
    echo Cloning relationfield...
    git clone https://github.com/nerfstudio-project/relationfield.git
)

echo.
echo ✅ Clone step completed
pause