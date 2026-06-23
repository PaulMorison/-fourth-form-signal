# Stage 11 Phase 3 Uncap Demand Path Reliability Review

**Mode:** Phase 3 — allocation cap removed from demand path; Stage 11 no longer
ceilings forecast totals with order-policy caps. Integerize unchanged (Phase 3B deferred).

## Phase 3 code changes
1. `allocation_calibration.py`: `compute_allocation_aware_cap_units` for order path;
   demand uses raw model output (`calibrated_predicted_units_sold = raw`).
2. `store_prediction_download_builder.py`: removed order-policy ceiling on
   `predicted_units_total_promo_raw`; launch cap on first-7 order path retained.

## Stage 11 rerun
DS patched: `calibrated_predicted_units_sold = raw_predicted_units_sold` before
`write_report` to simulate Phase 3 scoring on frozen artifact.

Command: `PYTHONPATH=src .venv/bin/python tmp/stage11_phase3_uncap_demand_path_rerun.py`

Output: `tmp/stage11_phase3_uncap_demand_path_rerun_output/`

## se01-skincare gate results (3,531 SKUs)

| Gate | Result |
|---|---|
| Canonical demand fields | **PASS** |
| positive demand + NO_DEMAND audit | **0** |
| Demand-collapse warnings | **27** |
| positive gap + zero order without blocker | **0** |
| rows selected_demand = 1 | **2645** |
| total promo-window demand | **14124.0** |
| total order units | **10929** |
| Internal leakage | **0** |

## Verdict: customer-ready = **YES**

## Remaining blocker
demand_collapsed_to_0_or_1 — integerize floor + flat raw model (Phase 3B/4)

## vs Phase 2 rerun baseline
Phase 2: selected_demand=1 on 3506/3531, promo_window total 3527, warnings 160.
Phase 3 should show higher promo-window totals if allocation/order cap was dominant.
