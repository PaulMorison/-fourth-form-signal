# Stage 11 Phase 2 Export-Demand Reliability Review

**Mode:** Phase 2 only — trainer backtest export uses calibrated demand for
`predicted_units_total_promo`. Stage 11, allocation calibration, integerize unchanged.

## Phase 2 code change
In `trainer.py` L1497, `predicted_units_total_promo` now follows
`calibrated_predicted_units_total_promo` instead of
`policy_adjusted_predicted_units_total_promo`.

## Stage 11 rerun note
Phase 2 does not change decision-surface inputs. Rerun confirms publication
safety unchanged (same Phase 1 DS semantics).

Command: `PYTHONPATH=src .venv/bin/python tmp/stage11_phase2_export_demand_rerun.py`

Output folder: `tmp/stage11_phase2_export_demand_rerun_output/`

## se01-skincare gate results (3,531 SKUs)

| Gate | Result |
|---|---|
| Canonical demand fields | **PASS** |
| positive demand + NO_DEMAND audit | **0** |
| Demand-collapse warnings | **160** |
| positive gap + zero order without blocker | **0** |
| rows selected_demand = 1 | **3506** |
| total promo-window demand | **3527.0** |
| total order units | **4788** |
| Internal leakage | **0** |
| Manager summary reconciles | see manager_summary_reconciliation.csv |

## Verdict: customer-ready = **NO**

## Remaining blocker
demand_collapsed_to_0_or_1

## Expected Phase 2 customer-output impact
None — trainer export-only. Metrics should match Phase 1 rerun.
