#!/bin/bash
# One-time installer for cfo-helper on macOS. Idempotent.
# Invoked by CFOHelper.command on first launch (when .venv is missing).
set -e

echo
echo "First-time setup for cfo-helper. This takes 2-3 minutes."
echo "Do not close this window until you see 'Setup complete'."
echo

if ! command -v uv >/dev/null 2>&1; then
    echo "[1/4] Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
else
    echo "[1/4] uv already installed."
fi

echo "[2/4] Creating Python environment (uv installs 3.13 if missing)..."
uv venv --python 3.13

echo "[3/4] Installing dependencies (this is the slow part)..."
uv pip install -e .

if [ -f profile/company_profile.yaml ] && [ ! -f profile/db/team.json ]; then
    echo "[4/4] Seeding runtime database..."
    ./.venv/bin/python -m scripts.seed_team
    ./.venv/bin/python -m scripts.seed_standard_work
elif [ ! -f profile/company_profile.yaml ]; then
    echo "[4/4] Skipping seed: profile not configured (see ONBOARDING.md)."
else
    echo "[4/4] Skipping seed: database already exists."
fi

echo
echo "Setup complete. Launching cfo-helper..."
sleep 1
