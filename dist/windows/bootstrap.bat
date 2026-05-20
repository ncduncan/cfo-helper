@echo off
REM One-time installer for cfo-helper on Windows. Idempotent.
REM Invoked by CFOHelper.vbs on first launch when .venv is missing.

cd /d "%~dp0\..\.."

echo.
echo First-time setup for cfo-helper. This takes 2-3 minutes.
echo Do not close this window until you see "Setup complete".
echo.

where uv >nul 2>nul
if errorlevel 1 (
    echo [1/4] Installing uv...
    powershell -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
) else (
    echo [1/4] uv already installed.
)

echo [2/4] Creating Python environment (uv installs 3.13 if missing)...
uv venv --python 3.13
if errorlevel 1 goto :error

echo [3/4] Installing dependencies (this is the slow part)...
uv pip install -e .
if errorlevel 1 goto :error

if exist profile\company_profile.yaml (
    if not exist profile\db\team.json (
        echo [4/4] Seeding runtime database...
        .venv\Scripts\python -m scripts.seed_team
        .venv\Scripts\python -m scripts.seed_standard_work
    ) else (
        echo [4/4] Skipping seed: database already exists.
    )
) else (
    echo [4/4] Skipping seed: profile not configured ^(see ONBOARDING.md^).
)

echo.
echo Setup complete. Launching cfo-helper...
timeout /t 2 >nul
exit /b 0

:error
echo.
echo Setup FAILED. See errors above. Press any key to close.
pause >nul
exit /b 1
