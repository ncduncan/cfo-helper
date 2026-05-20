"""Top-level scripts package. Adds a Python version guard early so analysts on
3.10 see a clear error instead of a cryptic union-type TypeError."""

import sys

if sys.version_info < (3, 11):
    raise SystemExit(
        f"Python 3.11+ required (got {sys.version.split()[0]}). "
        f"Use `uv venv --python 3.13` from the repo root, or upgrade your interpreter."
    )
