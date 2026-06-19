# RUN PROMOTIONS SYSTEM

## 1. Purpose

This layer provides one simple and repeatable command for promotions execution without changing model logic. It adds orchestration, governance checks, mode selection, and a run summary contract.

Primary entrypoint:

- ./scripts/promotions.sh --as-of-date 2026-05-20 --run-id golden-20260520-auto --mode auto

## 2. One-command examples

Auto mode (default):

- ./scripts/promotions.sh --as-of-date 2026-05-20 --run-id golden-20260520-auto --mode auto

Dry-run validation:

- ./scripts/promotions.sh --as-of-date 2026-05-20 --run-id test-run --mode validate-only --dry-run

Skip training explicitly:

- ./scripts/promotions.sh --as-of-date 2026-05-20 --run-id no-train-20260520 --mode skip-train

## 3. Modes

Supported modes:

- auto: governance-driven selection.
- train: requests training path (currently placeholder-gated).
- skip-train: run prediction cycle without training.
- validate-only: run preflight/planner checks only.

Auto rules:

- unknown drift emits a warning and does not auto-train.
- degraded drift only selects training when training is explicitly permitted.
- missing schema approval forces validate-only with blockers.

## 4. Train/no-train guidance

Use skip-train for normal operational runs.
Use validate-only for readiness checks and CI guardrails.
Use train only when a training workflow is intentionally wired.

Current safety behavior:

- training is placeholder-only and fails unless --allow-training-placeholder is supplied.

## 5. Fortnightly process

Suggested cadence:

1. Run validate-only first.
2. Run skip-train or auto execution.
3. Review generated manifests and governance summary.
4. Run actual-outcome backtest when new review data lands.
5. Promote only after acceptance gates are met.

## 6. Outputs

Controller summary:

- tmp/promotions_runs/<run_id>/run_summary.json

Runtime artifacts (existing runtime ownership):

- manifests/<run_id>/operational_cycle_manifest.json
- prediction/store_downloads/<run_id>/Manifests/store_prediction_download_manifest.json
- manifests/<run_id>/decision_surface_manifest.json

## 7. 98-backtest flow

When actual review data is available, run the diagnostics backtest:

- python -m runtime.promotions.store_allocation_actual_outcome_backtest \
  --stage11-diagnostic-csv <stage11_diagnostic.csv> \
  --stage11-master-csv <stage11_master.csv> \
  --actual-review-csv <actual_review.csv> \
  --output-root tmp/98_readiness_validation/<run_id>

This preserves existing model logic and produces readiness evidence artifacts.

## 8. Scheduling

For automation, schedule the shell command with fixed run-id/date conventions and capture stdout/stderr logs.

Recommended defaults from wrapper:

- env file: .env
- artifact root: /Users/paulmorison/promotions_runtime_governed
- local inspection root: /tmp/promotions_<run_id>/local_inspection
- connect timeout: 60 seconds

## 9. Troubleshooting

If mode auto does not train:

- inspect drift signal warning in run_summary.json
- unknown drift intentionally does not auto-train

If run is blocked:

- check schema approval signals in warnings/blockers
- validate-only mode can still be used for diagnostics

If training mode fails:

- this is expected unless --allow-training-placeholder is provided
