#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"

mode="auto"
run_id="promotions-$(date +%Y%m%dT%H%M%S)"
as_of_date=""
env_file=".env"
artifact_root="/Users/paulmorison/promotions_runtime_governed"
local_inspection_root=""
connect_timeout_seconds="60"

extra_args=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      mode="$2"
      shift 2
      ;;
    --run-id)
      run_id="$2"
      shift 2
      ;;
    --as-of-date)
      as_of_date="$2"
      shift 2
      ;;
    --env-file)
      env_file="$2"
      shift 2
      ;;
    --artifact-root)
      artifact_root="$2"
      shift 2
      ;;
    --local-inspection-root)
      local_inspection_root="$2"
      shift 2
      ;;
    --connect-timeout-seconds)
      connect_timeout_seconds="$2"
      shift 2
      ;;
    *)
      extra_args+=("$1")
      shift
      ;;
  esac
done

if [[ -z "$as_of_date" ]]; then
  echo "Missing required argument: --as-of-date YYYY-MM-DD" >&2
  exit 2
fi

if [[ -z "$local_inspection_root" ]]; then
  local_inspection_root="/tmp/promotions_${run_id}/local_inspection"
fi

cd "$repo_root"
export PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}"

python_bin="python3"
if [[ -x "$repo_root/.venv/bin/python" ]]; then
  python_bin="$repo_root/.venv/bin/python"
fi

exec "$python_bin" -m runtime.promotions.promotion_run_controller \
  --mode "$mode" \
  --run-id "$run_id" \
  --as-of-date "$as_of_date" \
  --env-file "$env_file" \
  --artifact-root "$artifact_root" \
  --local-inspection-root "$local_inspection_root" \
  --connect-timeout-seconds "$connect_timeout_seconds" \
  "${extra_args[@]}"
