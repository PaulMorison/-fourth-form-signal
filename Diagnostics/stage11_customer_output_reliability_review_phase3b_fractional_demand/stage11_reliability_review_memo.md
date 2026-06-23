# Stage 11 Phase 3B Fractional Demand Reliability Review

**Mode:** Phase 3B — canonical demand contract preserves fractional model output;
`_integerize_forecast_total_units` applies only to display/order-support fields.

## Phase 3B code changes
1. `allocation_demand_forecast_contract.py`: canonical demand fields use fractional
   units; emit `MODEL_DEMAND_COLLAPSED` when 0 < model demand < 1.
2. `store_prediction_download_builder.py`: `predicted_units_total_promo_fractional`
   feeds the demand contract; integer `predicted_units_total_promo` remains display-only.

## Stage 11 rerun
DS patched: `calibrated_predicted_units_sold = raw_predicted_units_sold` before
`write_report` (Phase 3 demand path on frozen artifact).

Command: `PYTHONPATH=src .venv/bin/python tmp/stage11_phase3b_fractional_demand_rerun.py`

Output: `tmp/stage11_phase3b_fractional_demand_rerun_output/`

## se01-skincare gate results (3,531 SKUs)

| Gate | Result |
|---|---|
| Canonical demand fields | **PASS** |
| positive demand + NO_DEMAND audit | **0** |
| Feature-vs-model collapse warnings | **26** |
| Tiny model demand warnings | **2661** |
| rows selected_demand between 0 and 1 | **2661** |
| rows selected_demand = 1 | **3** |
| total promo-window demand | **11582.0** |
| total order units | **9687** |
| positive gap + zero order without blocker | **0** |
| Internal leakage | **0** |

## Verdict: customer-ready = **NO**

## Remaining blocker
tiny_model_demand_share_high

## vs Phase 3 uncap rerun
Phase 3: selected_demand=1 on 2645/3531, promo_window total 14124, collapse warnings 27.
Phase 3B should show fractional canonical demand and tiny-model warnings instead of silent floor-to-1.
