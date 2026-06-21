# Phase 2/3 Demand Repair Design

**Date:** 2026-06-21  
**Branch:** `cursor/promotions-actual-outcome-stock-truth`  
**Phase 1 commit:** `5365c3f` (already pushed)  
**Scope:** Design only — no code patched  
**Evidence:** se01-skincare / store 772 / 3,531 SKUs; decision surface + Phase 1 Stage 11 rerun

---

## Executive summary

Phase 1 correctly separated **demand forecast** from **order policy caps** in live scoring (`predicted_units_sold = calibrated_predicted_units_sold`). Customer-facing demand collapse **did not improve** (3,506 SKUs still at `selected_demand_units = 1`; promo-window total still 3,527). This confirms the remaining collapse is **not** the scoring assignment bug alone.

The **next earliest remaining active demand shrink** after Phase 1 is **`apply_allocation_aware_units_cap`** in `allocation_calibration.py`, which still writes directly into `calibrated_predicted_units_sold` on the demand path (1,959 / 3,531 rows capped on se01 evidence). Downstream, **Stage 11 still applies order-policy ceilings** to forecast totals and **`_integerize_forecast_total_units` floors 3,526 near-zero calibrated values to 1**, masking flat model output.

**Recommended Phase 2:** Align `trainer.py` backtest export (`predicted_units_total_promo = policy_adjusted` at L1495) with Phase 1 scoring semantics.  
**Recommended Phase 3:** Remove allocation cap and Stage 11 order cap from the **demand display path**; route caps to order reconciliation only; pair with integerize/warning fix (Phase 3B).

**Patch next?** NO — await explicit approval after design review.  
**Report releasable?** NO.

---

## Phase 1 checkpoint

| Item | Status |
|---|---|
| Commit | `5365c3f` — *Phase 1: stop order caps overwriting predicted_units_sold.* |
| Push | ✅ `origin/cursor/promotions-actual-outcome-stock-truth` |
| Working tree | Clean at design start |

*(User-requested message “Separate promo demand forecast from order policy caps” — semantics match; commit already pushed with alternate wording.)*

---

## Answers to design questions

### Q1 — After Phase 1, what is the next earliest remaining point where demand is still capped or collapsed?

**`apply_allocation_aware_units_cap`** (`allocation_calibration.py` L96–99), invoked in `scoring_service.py` **before** `predicted_units_sold` assignment.

On se01 evidence (3,531 SKUs):
- **83.8%** raw model flat at ~0.0528 (`raw_predicted_units_sold`)
- **55.5%** rows shrunk by allocation calibration (`cal < raw`)
- Phase 1 order-cap overwrite: **fixed in code** (stale DS still shows `pred == cap` for all rows)

Pipeline order after Phase 1:
```
raw → [allocation cap shrinks demand] → calibrated → predicted_units_sold
      → decision surface → Stage 11 [order cap ceiling] → [integerize floor to 1] → selected_demand_units
```

### Q2 — Does trainer.py still write policy-adjusted demand into predicted_units_total_promo?

**YES** — backtest/test export path at **`trainer.py` L1495**:
```python
out["predicted_units_total_promo"] = policy_adjusted_predicted_units.values
```
Policy replay diagnostics at L2454 already use `calibrated_predicted_units` — **inconsistent** with export path.

Existing test **`test_promotions_training_scoring_pipeline.py` L128–130** still asserts `predicted_units_total_promo.equals(policy_adjusted_predicted_units_total_promo)`.

### Q3 — Does Stage 11 still cap resolved forecast demand using order policy?

**YES** — `_build_download_forecast_outputs` L2218–2226:
```python
predicted_units_total_promo_raw = predicted_units_total_promo_raw.where(
    predicted_units_total_promo_raw.le(total_cap_units),
    total_cap_units,
)
```
`policy_adjusted_total_cap_units` is passed from `adjusted_order_cap_units` when `policy_adjustment_fired_flag` (caller L1473–1480).

Simulated on se01 with post-Phase-1 demand semantics: **1,298 rows** would shrink at this ceiling.

### Q4 — Does integerisation turn true near-zero demand into 1 and hide model failure?

**YES** — `_integerize_forecast_total_units` L6151–6152:
```python
0 if value <= 0 else max(int(round(value)), 1)
```

On se01:
- **3,526** rows have `0 < calibrated < 1`
- **All** integerize to **1**
- Customer output after Phase 1 rerun: **3,506 / 3,531** at `selected_demand_units = 1`

This is **masking**, not forecasting. A flat ~0.05 promo-window model cohort becomes a uniform 1-unit customer forecast.

### Q5 — Which patch should be Phase 2?

**`trainer.py` L1495** (+ ablation runners if they mirror the same assignment):
- Set `predicted_units_total_promo = calibrated_predicted_units_total_promo`
- Keep `policy_adjusted_predicted_units_total_promo` as separate order column
- Update backtest export contract test

**Rationale:** Smallest next patch; aligns offline/backtest artifacts with live Phase 1 scoring; does **not** change Stage 11 customer output by itself.

### Q6 — Which patch should be Phase 3?

**Combined demand-path decoupling:**
1. **`allocation_calibration.py`** — stop writing cap output to `calibrated_predicted_units_sold`; emit `allocation_cap_units` for order path only; demand stays at raw (or explicitly named demand layer).
2. **`store_prediction_download_builder.py` `_build_download_forecast_outputs`** — remove L2218–2226 and L2276–2284 order-cap ceilings from forecast resolution; apply caps only in order reconciliation.
3. **Phase 3B (same release or immediately after):** `_integerize_forecast_total_units` / demand contract — fractional canonical fields; `MODEL_DEMAND_COLLAPSED` warning for tiny positive; no floor-to-1 on contract input.

### Q7 — What tests are required?

| Phase | Test |
|---|---|
| 2 | `test_backtest_export_predicted_units_total_promo_is_calibrated` |
| 2 | Update `test_promotions_training_scoring_pipeline` L128–130 |
| 3 | `test_allocation_cap_units_separate_from_calibrated_demand` |
| 3 | `test_stage11_forecast_total_not_capped_by_order_policy` |
| 3B | `test_integerize_does_not_floor_subunit_demand_for_contract_input` |
| 3B | `test_tiny_calibrated_demand_emits_model_demand_collapsed_warning` |
| 4 | `test_flat_raw_cohort_blocks_customer_ready` |

### Q8 — Fractional canonical demand vs integer display?

**Recommend both:**
- **Canonical contract fields** (`promo_window_demand_units`, `selected_demand_units` source): preserve **fractional** model/calibrated values for audit and diagnostics.
- **Display / order fields**: integer rounding acceptable for operator-facing order quantities.
- Document that integer `expected_promo_demand = 1` may represent ~0.05 fractional truth until model is fixed.

### Q9 — Route tiny forecasts to MODEL_DEMAND_COLLAPSED instead of floor to 1?

**YES** for demand contract / canonical path. Tiny positive calibrated demand with flat raw cohort should emit **`MODEL_DEMAND_COLLAPSED`** (or existing `DEMAND_COLLAPSE_RISK_*` family) and **not** silently floor to 1. Floor-to-1 may remain for legacy display columns only until Phase 4 gate passes.

### Q10 — Is raw-model flatness a separate training issue?

**YES.** Even after all caps are removed from the demand path, **83.8% modal raw at 0.0528** is a **training/model head issue** requiring a separate pass (feature family, target definition, GBM hyperparameters, specialist routing). Cap removal exposes the problem; it does not fix the model.

**Do not** use feature consensus as truth or inflate demand blindly.

---

## Recommended repair sequence

| Phase | Target | Customer release |
|---|---|---|
| 1 ✅ | `scoring_service.py` — demand ≠ order cap | NO (confirmed) |
| **2** | `trainer.py` L1495 — export calibrated as canonical | NO |
| **3** | `allocation_calibration.py` + Stage 11 forecast cap removal | NO |
| **3B** | Integerize / demand contract warning fix | NO |
| 4 | Flat raw cohort gate | Conditional |
| 5 | Training + provenance-gated fallback | Defer |

---

## Release verdict

| Gate | Status |
|---|---|
| Demand/order separated at scoring | ✅ Phase 1 |
| Demand magnitude credible | ❌ |
| Customer-ready | ❌ |
| Report releasable | ❌ |

**Exact remaining blocker:** `demand_collapsed_to_0_or_1` driven by flat raw model + allocation calibration on demand path + Stage 11 order cap ceiling + integerize floor-to-1.

---

## Do not patch until approved

Stop here. Phase 2/3 implementation requires explicit go-ahead after review of:
- `remaining_demand_cap_points.csv`
- `trainer_predicted_units_total_trace.csv`
- `stage11_forecast_cap_trace.csv`
- `integerisation_floor_masking_review.csv`
