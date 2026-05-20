#!/bin/bash
# Double-click entry point for CFO Helper on macOS.
# Detects whether the venv is set up; if not, runs the visible
# bootstrap. Then detaches the launcher so Terminal can close.
set -e

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO"
mkdir -p logs

if [ ! -x ".venv/bin/python" ]; then
    bash dist/mac/bootstrap.sh
fi

# Spawn launcher detached so this Terminal window can close immediately.
# launcher.py owns the pywebview window for the rest of the session.
nohup ./.venv/bin/python launcher.py >> logs/launcher.log 2>&1 </dev/null &
disown
exit 0
