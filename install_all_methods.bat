@echo off
set ROOT=%CD%

echo ==============================
echo Installing all Nerfstudio methods (editable)
echo ==============================

for %%D in (*) do (
    if exist "%%D\pyproject.toml" (
        echo.
        echo Installing %%D ...
        cd %%D
        pip install -e . --no-deps
        cd %ROOT%
    )
)

echo.
echo ✅ All editable installs completed
pause