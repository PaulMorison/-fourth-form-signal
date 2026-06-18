#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON="${REPO_ROOT}/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "Missing .venv. Create one with: python3.12 -m venv .venv && .venv/bin/pip install -e ." >&2
  exit 1
fi

"$PYTHON" -m unittest discover -s tests/unit -p "test_*.py" "$@"
