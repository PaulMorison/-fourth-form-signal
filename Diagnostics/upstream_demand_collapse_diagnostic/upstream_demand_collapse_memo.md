# Upstream Demand Collapse Diagnostic Memo

**Date:** 2026-06-21  
**Branch:** cursor/promotions-actual-outcome-stock-truth  
**Scope:** Read-only. No code patched, no SQL run, no training run, no Stage 12.  
**Input:** `e2e-live-20260619T123109_decision_surface.csv` (se01-skincare, store 772, 3,531 SKUs)  
**Output dir:** `Diagnostics/upstream_demand_collapse_diagnostic/`

---

## 1. Question Answers

### Q1 — Which input column is Stage 11 using as the model promo-window demand?

Stage 11 runs a **forecast resolution chain** (`_perform_per_promotion_source_selection` → `_compute_resolved_forecast_values` → `_apply_anti_collapse_repair`) that ingests `predicted_units_sold` (per-day, calibrated) and other source candidates from the decision surface, then emits `forecast_resolution["resolved_total_units"]`. This resolved value is written to `forecast_outputs["predicted_units_total_promo"]` at line 2217, which then feeds the demand contract as `model_promo_units_raw`.

**The canonical expected column `predicted_units_total_promo` does not exist in this decision surface at all.** The forecast resolution chain is the bridge.

### Q2 — Where is `selected_demand_units` ultimately sourced from?

```
DS: predicted_units_sold (per-day, calibrated)
  → Stage 11 forecast resolution: × promo_window_days → resolved_total_units
  → model_promo_units_raw (passed to demand contract)
  → demand contract: promo_window_demand_units = MODEL_PREDICTION basis
  → selected_quantile (q50 for MEDIUM/LOW confidence) = promo_window_demand_units
  → selected_demand_units (rounded integer)
```

### Q3 — Is the collapse already present in the decision surface before Stage 11?

**YES.** The collapse originates in the upstream model calibration pipeline **before** the decision surface is materialised. Evidence:

| Column | p50 | max | Total × 7d p50 |
|---|---|---|---|
| `raw_predicted_units_sold` (uncalibrated) | 0.053/day | 28.95/day | **0.37 total** |
| `calibrated_predicted_units_sold` | 0.012/day | 1.39/day | **0.082 total** |
| `policy_adjusted_predicted_units_sold` | 0.005/day | 0.456/day | **0.035 total** |
| `predicted_units_sold` (final, post-policy) | 0.005/day | 0.456/day | **0.035 total** |

After policy adjustment, 99.8% of SKUs resolve to < 0.5 total units over a 7-day promo window, which rounds to 0. The anti-collapse repair floor then lifts zeros to **1**, producing the uniform 1-unit pattern.

The decision surface never had `predicted_units_total_promo`. The forecast resolution chain reconstructs it from the per-day rate — but by the time the per-day rate reaches Stage 11, the collapse has already occurred upstream.

### Q4 — Collapse cause classification

| Cause | Verdict |
|---|---|
| Model prediction output | **PRIMARY CAUSE** — raw signal is meaningful (max 28.95/day) but 97% is removed by calibration |
| Store-level disaggregation | NOT the cause — already per-store |
| Per-store allocation share | NOT confirmed as a factor |
| Rounding/ceil/floor logic | **CONTRIBUTING** — int rounding of 0.035 to 0, then anti-collapse floor to 1 |
| Horizon clamp | NOT the cause |
| Fallback/default path | NOT triggered — `MODEL_PREDICTION_USED` for all rows |
| Stale alias field | NOT the cause — column is just missing; resolution chain handles it |
| Stage 11 mapping bug | **NO** — Stage 11 demand contract runs correctly; basis=MODEL_PREDICTION for all rows |

### Q5 — Field comparison (distribution)

| Field | Source | p50 | Mean | Max |
|---|---|---|---|---|
| `raw_predicted_units_sold` × 7d | DS (upstream) | 0.37 | 0.78 | 202.5 |
| `calibrated_predicted_units_sold` × 7d | DS (upstream) | 0.082 | 0.19 | 9.7 |
| `policy_adjusted_predicted_units_sold` × 7d | DS (upstream) | 0.035 | 0.11 | 3.2 |
| `feature_probability_expected_units_consensus` | DS feature layer | 0.56 | 1.45 | 113 |
| `feature_expected_total_units_first_7_days` | DS feature layer | 0.002 | 0.62 | 24.5 |
| `promo_window_demand_units` | Report (demand contract) | 1 | ~1 | 1 |
| `selected_demand_units` | Report (demand contract) | 1 | ~1 | 2 |

The feature consensus (`feature_probability_bayesian_poisson_expected_units`) has p50=0.56 and max=113 — materially closer to a plausible per-SKU per-event demand distribution than the policy-adjusted prediction.

### Q6 — Top 50 rows with feature demand materially higher than final

See `feature_vs_model_demand_top_gaps.csv`. Key pattern: 472 SKUs where `feature_consensus >= 5`; top gap = 112 units (feature 113 vs selected 1). The feature-high SKUs are driven by `feature_probability_bayesian_poisson_expected_units` (= `feature_probability_expected_units_consensus`).

### Q7 — Earliest column where demand becomes 1

The collapse occurs **inside the model calibration step** before the decision surface is written. The sequence:

1. Raw model output: `raw_predicted_units_sold` — values up to 28.95/day present.  
2. After calibration: `calibrated_predicted_units_sold` — 97% of signal removed (p50 drops from 0.053 to 0.012).  
3. After policy adjustment: `policy_adjusted_predicted_units_sold` — further shrinkage (p50 0.005).  
4. Stage 11 forecast resolution: × 7 days → 0.035 → rounds to 0 → anti-collapse repair → **1**.

The earliest collapse column is **`calibrated_predicted_units_sold`** in the decision surface.

### Q8 — Feature demand recommended use

**SANITY CHECK AND ESCALATION SIGNAL only.**

`feature_probability_expected_units_consensus` is the Bayesian-posterior per-store demand estimate from the feature layer. It has plausible magnitudes (mean 1.45, max 113). However:
- Its provenance is not confirmed against observed sales outcomes for this event type.
- It may reflect chain-level or cluster-level demand rather than per-store per-unit truth.
- It is already being used correctly as an escalation signal (Patch B: 160 collapse warnings emitted, feature signal cited in warnings).

Do NOT use as truth or as a replacement for the calibrated model. Use as:
- A collapse detection signal (Patch B already does this).
- A potential floor/fallback only after provenance is validated against historical actuals.

### Q9 — Where does the fix belong?

| Layer | Fix Required? |
|---|---|
| **Model calibration pipeline** | **YES** — primary fix. Calibration is removing too much signal. Investigate calibration methodology and training data for this event type. |
| Decision surface builder | NO — it correctly writes what calibration produces. |
| Store disaggregation layer | NOT confirmed as contributor. |
| **Demand forecast contract** | **PARTIAL** — consider adding a provenance-confirmed feature fallback for collapse cases once upstream is investigated. |
| Stage 11 mapping | **NO** — Stage 11 is working correctly. Forecast resolution, demand contract, label reconciliation all functioning. |

### Q10 — Smallest safe next patch

**Do not patch yet.** The fix belongs upstream in the **model calibration pipeline**. The investigation should:

1. Compare `raw_predicted_units_sold` vs `calibrated_predicted_units_sold` for prior events with known outcomes.
2. Determine whether the calibration is event-type-specific (skincare events may have been systematically down-calibrated).
3. Determine whether policy adjustment further crushes legitimate demand.

Once the calibration root cause is confirmed, either re-calibrate or add a governed fallback in the demand forecast contract that uses `feature_probability_bayesian_poisson_expected_units` as a floor when per-day model total resolves < 2 units.

---

## 2. Stage 11 Status

**Stage 11 is NOT the source of the collapse.**

- `demand_forecast_basis = MODEL_PREDICTION` for all 3,531 rows.
- `demand_forecast_confidence`: HIGH=540, MEDIUM=2,158, LOW=833.
- `demand_forecast_reason_code = MODEL_PREDICTION_USED` for all rows.
- `demand_forecast_warning`: 160 rows flagged with `DEMAND_COLLAPSE_RISK_FEATURE_SIGNAL_HIGHER` (Patch B working correctly).
- `store_action_label` reconciliation passes; publication safety guard passes.
- All Stage 11 governance checks are clean.

Stage 11 is surfacing the collapse accurately and honestly. Do not patch Stage 11.

---

## 3. Customer Readiness Gate

| Gate | Status |
|---|---|
| Demand contract runs correctly | PASS |
| demand_evidence_label NO_DEMAND contradiction | PASS (Patch C) |
| store_action_label NO_DEMAND contradiction | PASS (action-label fix) |
| Publication safety guard | PASS |
| Stage 11 internal coherence | PASS |
| **Demand magnitude commercially credible** | **FAIL — 99.3% of SKUs at 1 unit** |
| Feature collapse warnings emitted | PASS (160 warnings) |

**Customer-ready: NO**

The output is **internally coherent and publication-safe**, but cannot be released to customers because demand magnitude is commercially invalid. The root cause is upstream in the model calibration pipeline.

---

## 4. Summary Table

| Field | Value |
|---|---|
| total_skus | 3,531 |
| rows_selected_demand_eq_1 | 3,506 (99.3%) |
| rows_selected_demand_eq_0 | 4 |
| rows_feature_signal_materially_higher (consensus ≥ 5) | 472 |
| rows_raw_total_ge_2 | 87 |
| rows_calibrated_total_ge_2 | 3 |
| rows_policy_adj_total_ge_2 | 2 |
| pct_final_rounds_to_zero_before_floor | 99.8% |
| earliest_collapse_layer | model calibration pipeline (upstream) |
| earliest_collapse_column | calibrated_predicted_units_sold |
| stage11_mapping_bug | NO |
| upstream_model_bug | YES — calibration over-shrinks by ~97% |
| feature_signal_use | SANITY CHECK / ESCALATION only |
| customer_ready | NO |
| recommended_patch_target | Upstream model calibration pipeline |
| patch_now | NO — requires upstream data investigation |
