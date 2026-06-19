#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

python_bin="${PYTHON:-}"
if [[ -z "$python_bin" ]]; then
  if [[ -x ".venv/bin/python" ]]; then
    python_bin=".venv/bin/python"
  else
    python_bin="$(command -v python3 || true)"
  fi
fi

if [[ -z "$python_bin" ]]; then
  echo "python3 or .venv/bin/python is required to inspect CSV row counts" >&2
  exit 1
fi

print_candidate() {
  local candidate_file="$1"
  CANDIDATE_FILE="$candidate_file" "$python_bin" - <<'PY'
from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path

import pandas as pd

candidate = Path(os.environ["CANDIDATE_FILE"])
modified = datetime.fromtimestamp(candidate.stat().st_mtime).isoformat(timespec="seconds")
row_count = "unreadable"
sku_count = ""
try:
    header = pd.read_csv(candidate, nrows=0, keep_default_na=False, low_memory=False)
    columns = list(header.columns)
    if "sku_number" in columns:
        rows = pd.read_csv(candidate, usecols=["sku_number"], keep_default_na=False, low_memory=False)
        row_count = str(len(rows.index))
        sku_count = str(rows["sku_number"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip().replace("", pd.NA).dropna().nunique())
    else:
        row_count = str(sum(1 for _ in candidate.open("rb")) - 1)
        sku_count = "sku_number_missing"
except Exception as exc:  # pragma: no cover - shell helper diagnostics only
    row_count = f"unreadable:{type(exc).__name__}"
    sku_count = ""
print(f"path={candidate}\tmodified_time={modified}\trow_count={row_count}\tsku_count={sku_count}")
PY
}

{
  for search_root in "$repo_root" "$repo_root/tmp" "/Users/paulmorison/Downloads" "/mnt/data" "/Users/paulmorison/promotions_runtime_governed"; do
    [[ -d "$search_root" ]] || continue
    find "$search_root" -type f \( \
      -name 'promotion_review_analysis_25052026*.csv' -o \
      -name '*promotion_review*.csv' -o \
      -name '*actual*outcome*.csv' \
    \) -print 2>/dev/null
  done
} | sort -u | while IFS= read -r candidate_file; do
  [[ -n "$candidate_file" ]] || continue
  print_candidate "$candidate_file"
done
