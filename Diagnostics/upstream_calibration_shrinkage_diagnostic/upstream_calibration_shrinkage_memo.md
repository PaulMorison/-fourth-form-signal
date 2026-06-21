# Upstream Model Calibration Shrinkage Diagnostic Memo

**Date:** 2026-06-21  
**Branch:** cursor/promotions-actual-outcome-stock-truth  
**Scope:** Read-only forensic. No code patched, no SQL, no training.  
**Input:** `e2e-live-20260619T123109_decision_surface.csv` (SE01 skincare, store 772, 3,531 SKUs)  
**Output dir:** `Diagnostics/upstream_calibration_shrinkage_diagnostic/`

---

## Executive Summary

Demand collapse is **not** caused by a per-day vs total-promo unit-scale bug or double horizon multiplication. All model outputs (`raw_predicted_units_sold`, `calibrated_predicted_units_sold`, `policy_adjusted_predicted_units_sold`) are **total promo-window units**, confirmed by `scoring_service.py` and Stage 11 forecast resolution.

The collapse is caused by a **stack of upstream shrinkage layers**:

1. **Raw model inference** produces a degenerate flat cohort (83.8% of SKUs = exactly 0.0528 total units).
2. **Allocation-aware calibration** caps a further 55.5% of rows (median cal/raw = 0.12).
3. **Order policy adjustment** fires on 99.9% of rows and writes `adjusted_order_cap_units` into `predicted_units_sold` — applying risk/capital dampening to the **demand field**, not just orders.
4. **Stage 11** applies the policy cap again as a ceiling on resolved forecast totals, crushing rows where forecast resolution selected a stronger source (785 rows: source ≥3 → selected = 1).
5. **Integerize floor** (`_integerize_forecast_total_units`) lifts 0 < value < 0.5 to 1, masking true ~0.05 predictions as uniform 1-unit demand.

**Customer-ready: NO. Report release: NO.**

---

## 1. Unit Scale Correction

The prior upstream demand-collapse diagnostic treated values as per-day and multiplied by 7. That was **incorrect**.

| Evidence | Finding |
|---|---|
| `scoring_service.py` ~L228 | "The model forecasts **total promo-window units**" |
| `predicted_units_first_day` | Derived as `predicted_units_sold / promo_window_days` (divide, not multiply) |
| Stage 11 `_compute_resolved_forecast_values` | `total = source_value`; `daily = total / window` |
| `ft_group_windows.py` | `baseline_expected_units = baseline_daily × promo_window_days` |

**No unit-scale or double-horizon bug.** Raw p50 = 0.0528 means ~0.05 total units expected over the full 7-day promo window — already near-zero before any downstream processing.

---

## 2. Distribution: Raw → Calibrated → Policy-Adjusted

All values are **total promo-window units** (SE01, n=3,531):

| Stat | Raw | Calibrated | Policy-Adjusted | Feature Consensus |
|---|---|---|---|---|
| p50 | 0.0528 | 0.0115 | 0.0052 | 0.556 |
| p90 | 0.0616 | 0.0528 | 0.0369 | 3.0 |
| p99 | 1.58 | 0.0616 | 0.0528 | 13.6 |
| max | 28.95 | 1.39 | 0.46 | 113 |
| mean | 0.111 | 0.027 | 0.016 | 1.45 |
| sum | 392 | 96 | 55 | 5,109 |

### Shrinkage ratios (median)

| Ratio | Value |
|---|---|
| calibrated / raw | 0.119 |
| policy_adjusted / calibrated | 1.000 (median unchanged; 36.8% rows reduced) |
| policy_adjusted / raw | 0.079 |

---

## 3. Cause Classification (10 hypotheses)

| # | Hypothesis | Verdict |
|---|---|---|
| 1 | Raw model already too low | **YES — PRIMARY** — 83.8% flat at 0.0528; p75 still 0.0528 |
| 2 | Calibration over-shrinks | **YES — SECONDARY** — 55.5% rows capped; `apply_allocation_aware_units_cap` |
| 3 | Policy adjustment over-shrinks | **PARTIAL** — 36.8% reduced vs calibrated; 99.9% fired |
| 4 | Wrong unit scale (per-day vs total) | **NO** |
| 5 | Wrong horizon multiplication | **NO** |
| 6 | Wrong target definition | **LIKELY** — `target_actual_units_sold = actual_units_sold` (realized sales) |
| 7 | Category/promotion-type calibration leakage | **NOT PRIMARY** — shrinkage uniform across SE01 (single promotion) |
| 8 | Store disaggregation error | **NO** — already per-store |
| 9 | Sparse-history fallback dominating | **YES — CONTRIBUTING** — 884 rows (25%) under `sparse_history_multi_driver_baseline_only` |
| 10 | Chain/store mismatch | **NO** |

---

## 4. Policy Adjustment Breakdown

| Rule | Rows | % |
|---|---|---|
| `weak_elasticity_uplift_restraint` | 2,427 | 68.7% |
| `sparse_history_multi_driver_baseline_only` | 884 | 25.0% |
| `weak_same_discount_and_uplift_cap` | 184 | 5.2% |
| `falling_base_launch_conflict_review` | 21 | 0.6% |
| `stock_gap_high_review_cap` | 13 | 0.4% |
| `no_policy_adjustment` | 2 | 0.1% |

**Critical semantic bug:** In `scoring_service.py`, `predicted_units_sold = policy_adjusted_predicted_units_sold = adjusted_order_cap_units`. Policy rules designed for order/risk restraint are applied to the **demand forecast field** that downstream stages consume as expected customer demand.

---

## 5. Calibration Cap Analysis

`apply_allocation_aware_units_cap` (`allocation_calibration.py`) caps raw predictions to `min(raw, effective_upper_bound)` when:
- `model_use_flag | uplift_support_flag`
- `effective_expected_units > 0`
- `effective_discipline_score >= 0.15`
- `effective_confidence > 0`

For SE01: **1,959 / 3,531 rows (55.5%)** capped below raw. Example SKU 188700: raw=28.95 → calibrated=0.0052 (cal/raw = 0.00018).

---

## 6. Stage 11 Forecast Resolution + Policy Cap Interaction

Stage 11 selects forecast source by priority:
1. `required_implied_units` (64% of SE01 rows)
2. `predicted_units_sold` (25%)
3. `baseline_expected_units` (11%)

Many rows resolve to materially higher totals (e.g. baseline=7.0, required_implied up to 698). But `_build_download_forecast_outputs` then applies:

```python
predicted_units_total_promo_raw.where(
    predicted_units_total_promo_raw.le(total_cap_units),
    total_cap_units,
)
```

When `resolved=7.0` but `adjusted_order_cap_units=0.0528`, demand is crushed to 0.0528 → integerized to **1**.

**785 SE01 rows** have `forecast_source_raw_units >= 3` but `selected_demand_units = 1`.

Example SKU 90980:
- Feature baseline promo window = **7.0**
- Forecast source selected = `baseline_expected_units` (7.0)
- Policy cap = 0.0528 (`sparse_history_multi_driver_baseline_only`)
- Final `promo_window_demand_units` = **1**

---

## 7. Stockout-Contaminated Calibration

| Evidence | Implication |
|---|---|
| `target_actual_units_sold = actual_units_sold` | Training target is realized sales, not sufficient-stock demand |
| `feature_prior_promo_units_*` all zero | No promo history signal in features |
| `feature_sparse_demand_evidence_available_flag` p50 = 1.0 | Sparse evidence flagged for all rows |
| Feature consensus >> model output | Bayesian posterior retains more demand signal than GBM model |

Calibration appears trained/conditioned on **stock-constrained historical sales**, causing systematic understatement of promo-window demand.

---

## 8. Anti-Collapse Floor

`_integerize_forecast_total_units`: any value > 0 but rounding to 0 becomes **1**. This masks the true ~0.05 policy-adjusted prediction as commercially misleading "1 unit expected demand" for 3,506 / 3,531 SKUs.

The floor does not fix demand — it **hides** the collapse.

---

## 9. Code Path (Earliest → Latest)

| Step | File | Function | Effect |
|---|---|---|---|
| 1 | `scoring_service.py` | `units_model.predict` | Flat raw cohort (0.0528 for 84%) |
| 2 | `allocation_calibration.py` | `apply_allocation_aware_units_cap` | Caps 56% to probability upper bound |
| 3 | `order_policy_adjustments.py` | `build_order_policy_adjustments` | Writes cap to `predicted_units_sold` |
| 4 | Decision surface CSV | persist | Collapse materialized upstream |
| 5 | `store_prediction_download_builder.py` | `_resolve_commercial_forecast_inputs` | Selects best source per promotion |
| 6 | `store_prediction_download_builder.py` | `_build_download_forecast_outputs` | Policy cap crushes resolved total |
| 7 | `store_prediction_download_builder.py` | `_integerize_forecast_total_units` | ~0.05 → 1 |
| 8 | `allocation_demand_forecast_contract.py` | `build_demand_forecast_contract_frame` | Faithfully passes through collapsed input |

**Earliest exact function:** `units_model.predict` in `scoring_service.py` (flat 0.053 cohort origin).

---

## 10. Top 10 Suppressed High-Signal Rows

| SKU | Raw | Policy-Adj | Feature Consensus | Forecast Source Raw | Selected Demand | Policy Rule |
|---|---|---|---|---|---|---|
| 188705 | 0.0 | 0.0 | 113.0 | 2.0 (req_implied) | 0 | sparse_history |
| 188706 | 0.0 | 0.0 | 113.0 | 10.0 | 0 | sparse_history |
| 192047 | 0.0 | 0.0 | 77.0 | 2.0 | 0 | sparse_history |
| 192046 | 20.66 | 0.46 | 73.0 | 404.0 | 1 | weak_elasticity |
| 188707 | 1.33 | 0.004 | 68.0 | 0.06 | 1 | sparse_history |
| 188698 | 9.19 | 0.011 | 39.5 | 0.17 | 1 | sparse_history |
| 188700 | 28.95 | 0.005 | 39.0 | 0.08 | 1 | sparse_history |
| 841250 | 0.14 | 0.013 | 30.7 | 0.19 | 1 | sparse_history |
| 654921 | 26.04 | 0.15 | 27.0 | 698.0 | 1 | weak_elasticity |
| 189553 | 7.78 | 0.066 | 26.7 | 162.0 | 1 | weak_elasticity |

Pattern: even SKUs with raw model signal 7–29 total units and forecast source 162–698 are crushed to selected demand = 1.

---

## 11. Recommended Repair Target (Do Not Patch Yet)

| Priority | Layer | Action |
|---|---|---|
| 1 | Model training/inference | Audit flat 0.053 cohort; review target definition vs sufficient-stock demand |
| 2 | `order_policy_adjustments` + `scoring_service` | Separate order caps from demand forecast; stop writing caps to `predicted_units_sold` |
| 3 | `allocation_calibration.py` | Review cap thresholds; backtest capped vs uncapped by segment |
| 4 | Stage 11 `_build_download_forecast_outputs` | Do not apply order policy cap to demand forecast total |
| 5 | Feature consensus | Escalation/sanity-check only (Patch B already in place) |

---

## 12. Decision Gates

| Gate | Result |
|---|---|
| Raw model plausible | **NO** |
| Calibration over-shrinks | **YES** |
| Policy adjustment over-shrinks | **PARTIAL (yes for high-signal rows)** |
| Unit-scale/horizon bug | **NO** |
| Store disaggregation implicated | **NO** |
| Stockout-contaminated calibration | **LIKELY** |
| Customer-ready | **NO** |
| Report can be released | **NO** |
| Patch now | **NO** — design upstream repair first |

---

## 13. Correction to Prior Diagnostic

The prior memo (`upstream_demand_collapse_diagnostic/`) stated calibration shrinks raw by ~97% using per-day × 7-day math. Corrected finding: values are already **total promo-window units**. Median cal/raw = **0.12** (88% shrinkage, not 97%). The qualitative conclusion (upstream collapse, not Stage 11 mapping bug) remains valid, but the unit-scale framing is corrected here.
