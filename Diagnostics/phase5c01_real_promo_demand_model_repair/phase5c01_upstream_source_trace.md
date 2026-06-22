# Phase 5C.01 upstream source trace

## Flat placeholder origin (pre-5C)

| Item | Detail |
|---|---|
| **Source file** | `src/surfaces/promotions/reporting/store_prediction_download_builder.py` |
| **Primary functions** | `_resolve_commercial_forecast_inputs`, `_build_download_forecast_outputs`, `_integerize_forecast_total_units`, `_build_store_facing_frame` |
| **Input columns** | `predicted_units_sold`, `required_implied_units`, `demand_reference_units`, `baseline_expected_units`, `avg_daily_units`, `bar_units`, `promo_window_days`, feature baseline/uplift columns |
| **Output columns created** | `predicted_units_total_promo` → exported as `expected_units_total_promo`, `expected_promo_demand`, `projected_promotional_units`, `expected_units_per_day` |
| **Why output was flat** | (1) `_integerize_forecast_total_units` forces any positive fractional total to **minimum 1** (`max(round(x), 1)`). (2) Resolved totals were often sub-unit before integerization, collapsing to 0/1. (3) Legacy `expected_units_per_day = total / promo_days` yields **0.1429** (= 1/7) for 7-day promos. |
| **Evidence upstream not Stage 11 / report builder** | Flat 0/1 values exist in governed prediction CSVs (`772_2026-07-23_allocation-report-se01-skincare-sales-event_operator-audit.csv`) **before** commercial report assembly. Stage 11 `_build_store_facing_frame` maps `predicted_units_total_promo` through `_store_int` / integerize helpers. Commercial report builder **reads** these fields and correctly rejects them as placeholders (Phase 5B.12). |

## Phase 5C repair module

| Item | Detail |
|---|---|
| **New module** | `src/models/promotions/promo_period_demand_forecast.py` |
| **Functions** | `detect_flat_placeholder_forecast`, `build_promo_period_demand_forecast_frame`, `attach_promo_period_demand_forecast` |
| **New field** | `model_expected_units_total_promo` — SKU-discriminating promo-window total from baseline × promo days × guarded uplift × adjustments |
| **Wiring** | `store_prediction_download_builder._build_store_facing_frame` (upstream export), `commercial_report_builder.load_se01_scored_sources` (runtime repair on read) |
| **Legacy fields** | `expected_units_total_promo` etc. **not overwritten** — kept for audit comparison |

## Demand contract (related, not root cause)

`src/models/promotions/allocation_demand_forecast_contract.py` governs `selected_demand_units` / alias mapping but does not produce the flat `expected_units_total_promo` integer export; that comes from download builder forecast resolution + integerization.
