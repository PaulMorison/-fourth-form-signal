# Stage 11 Phase 1 Demand Uncap Reliability Review

**Mode:** Phase 1 only — stop order caps overwriting demand in `scoring_service.py`.
Stage 11, training, SQL, and Phase 2–5 untouched.

## Phase 1 code change
In `PromotionModelScorer.score`, `predicted_units_sold` now follows
`calibrated_predicted_units_sold` instead of `adjusted_order_cap_units` /
`policy_adjusted_predicted_units_sold`. Order caps remain in separate columns.

## Stage 11 rerun methodology
The frozen decision-surface CSV was scored under the **old** assignment
(`predicted_units_sold == adjusted_order_cap_units` for all rows). Because full
rescoring is out of scope, the rerun script applies the same Phase 1 semantics
on DS inputs (`predicted_units_sold = calibrated_predicted_units_sold`) before
`write_report`.

Command: `PYTHONPATH=src .venv/bin/python tmp/stage11_phase1_demand_uncap_rerun.py`

Output folder: `tmp/stage11_phase1_demand_uncap_rerun_output/`

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

## Before vs post-action-label-fix baseline
Prior post-action-label-fix run (order cap still overwriting demand at scoring):
- rows_selected_demand_eq_1: 3506
- total_promo_window_demand_units: 3527.0
- rows_demand_collapse_warning: 160
- customer_ready: NO (demand_collapsed_to_0_or_1)

Phase 1 rerun should show higher promo-window demand if policy-cap overwrite was
the dominant collapse mechanism; customer-ready may still be NO if calibrated
model output remains near-zero before integerization.
