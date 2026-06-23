#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"

run_id="${1:-e2e-$(date +%Y%m%dT%H%M%S)}"
as_of_date="${2:-$(date +%Y-%m-%d)}"
artifact_root="${3:-/Users/paulmorison/promotions_runtime_governed}"

cd "$repo_root"

python_bin="python3"
if [[ -x "$repo_root/.venv/bin/python" ]]; then
  python_bin="$repo_root/.venv/bin/python"
fi

export PROMOTIONS_OPERATOR_DISPLAY=operator

exec "$python_bin" -m runtime.promotions.run_promotions_operational_cycle \
  --run-id "$run_id" \
  --as-of-date "$as_of_date" \
  --artifact-root "$artifact_root" \
  --env-file .env \
  --operator-display operator \
  --connect-timeout-seconds 60
