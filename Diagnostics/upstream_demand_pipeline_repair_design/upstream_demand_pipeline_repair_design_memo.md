# Upstream Demand Pipeline Repair Design

**Date:** 2026-06-21  
**Branch:** cursor/promotions-actual-outcome-stock-truth  
**Scope:** Design only — no code patched  
**Inputs:** `Diagnostics/upstream_calibration_shrinkage_diagnostic/`, code review of scoring/calibration/policy/Stage 11 paths  
**Output dir:** `Diagnostics/upstream_demand_pipeline_repair_design/`

---

## Design Principle

> **Demand forecast and order/risk policy must be separate.**

`predicted_units_sold` / promo-window demand must represent **expected customer demand under sufficient stock**. Risk, capital drag, weak evidence, supplier limits, and policy caps may reduce **order_units**, but must **not** overwrite the demand forecast.

---

## 1. Current Broken Demand Flow

```
units_model.predict
  → raw_predicted_units_sold                    [DEMAND — flat 0.053 cohort]
  → apply_allocation_aware_units_cap
  → calibrated_predicted_units_sold             [MISPLACED — allocation risk cap on demand]
  → build_order_policy_adjustments
  → adjusted_order_cap_units                    [ORDER CAP — correct intent]
  → policy_adjusted_predicted_units_sold        [MISNAMED]
  → predicted_units_sold = adjusted_order_cap   [❌ PRIMARY BUG]
  → decision surface CSV
  → Stage 11 forecast resolution (predicted_units_sold as source)
  → Stage 11 applies order cap AGAIN to resolved total  [❌ SECONDARY BUG]
  → _integerize_forecast_total_units (~0.05 → 1)      [❌ MASKING]
  → demand contract → selected_demand_units = 1
```

**Canonical pre-Stage-11 column today:** `predicted_units_sold` on the decision surface — but it is **not demand**; it is `adjusted_order_cap_units`.

---

## 2. Exact Overwrite Points

| Priority | Location | Overwrite |
|---|---|---|
| **P1** | `scoring_service.py` L171, L225 | `predicted_units_sold ← adjusted_order_cap_units` |
| **P2** | `scoring_service.py` L231-242 | Derived metrics use policy-capped demand |
| **P3** | `trainer.py` L1495 | `predicted_units_total_promo ← policy_adjusted` |
| **P4** | `store_prediction_download_builder.py` L2218-2226 | Resolved forecast total capped by order policy |
| **P5** | `allocation_calibration.py` L96-99 | Demand replaced by allocation upper bound |
| **P6** | `_integerize_forecast_total_units` | Fractional demand floored to 1 |

---

## 3. Answers to Design Questions

### Q1 — Canonical demand output before Stage 11?

**Nominal:** `predicted_units_sold`  
**Actual:** `adjusted_order_cap_units` (via `policy_adjusted_predicted_units_sold`)  
**Auditable layers present but unused as demand:** `raw_predicted_units_sold`, `calibrated_predicted_units_sold`

### Q2 — Where is demand overwritten by order cap?

Primary: `scoring_service.py` lines 171 and 225.  
Secondary: Stage 11 `_build_download_forecast_outputs` applies `adjusted_order_cap_units` as ceiling on `predicted_units_total_promo_raw`.

### Q3 — Demand columns

| Column | Role |
|---|---|
| `raw_predicted_units_sold` | Model output (auditable) |
| `calibrated_predicted_units_sold` | Canonical demand interim (Phase 1-2) |
| `demand_repaired_predicted_units_sold` | Future demand-only repair (Phase 5+) |
| `predicted_units_total_promo` | Promo-window demand total for allocation |
| `predicted_units_first_7_days` | Prorated launch-window demand |
| `demand_prediction_basis` | MODEL_PREDICTION / REVIEW / etc. |
| `demand_prediction_warning` | Flat cohort, collapse risk |
| `demand_prediction_confidence` | Demand confidence (not policy strength) |
| `predicted_units_sold` | **Reassign to demand** (= calibrated); deprecate cap semantics |

### Q4 — Order-policy columns

| Column | Role |
|---|---|
| `allocation_cap_units` | From allocation-aware cap (order path) |
| `adjusted_order_cap_units` | Final governed order cap |
| `adjusted_launch_units` | Launch-window order cap |
| `risk_adjusted_order_cap_units` | Optional intermediate |
| `order_policy_reason_code` | Renamed from `policy_adjustment_reason` |
| `order_policy_warning` | Order-side warnings |

### Q5 — Deprecate `policy_adjusted_predicted_units_sold`?

**YES.** Misnamed. Alias to `adjusted_order_cap_units` for one release with deprecation note. Must not feed Stage 11 demand.

### Q6 — What should Stage 11 consume?

**`calibrated_predicted_units_sold`** (interim) via `predicted_units_total_promo` after forecast resolution — **never** policy cap.  
Longer term: `demand_repaired_predicted_units_sold` once model flat-cohort is fixed.  
Stage 11 itself needs **no demand-logic patch** in Phase 1 except removing order-cap ceiling on forecast total (Phase 3).

### Q7 — `apply_allocation_aware_units_cap`?

**Remove from demand path (Phase 3).** Rename output to `allocation_cap_units`. Keep as **order/allocation ceiling** and diagnostic. Do not write to `calibrated_predicted_units_sold` unless separately recast as statistical demand calibration (future work).

### Q8 — `build_order_policy_adjustments`?

**Must stop indirectly writing demand** (via scoring_service). Continue outputting order cap fields only. Rules unchanged — they govern **orders**, not demand.

### Q9 — Flat raw model outputs?

| Action | When |
|---|---|
| Warning | Phase 4 — promotion-level modal share gate |
| Block customer release | Phase 4 — if flat cohort without explicit blocker |
| Review route | Via demand contract when evidence insufficient |
| Fallback | Phase 5 only — after actual-outcome validation |
| Floor to 1 | **Remove for demand contract input** — masks failure |

### Q10 — Minimum safe patch sequence?

See Section 4 below.

---

## 4. Proposed Patch Sequence

### Phase 1 — Stop order caps overwriting demand (FIRST PATCH)

**File:** `src/runtime/promotions/scoring_service.py`  
**Change:**
```python
# BEFORE (broken)
scored_rows["predicted_units_sold"] = scored_rows["policy_adjusted_predicted_units_sold"]

# AFTER (correct)
scored_rows["predicted_units_sold"] = scored_rows["calibrated_predicted_units_sold"]
# policy_adjusted_predicted_units_sold remains deprecated alias to adjusted_order_cap_units
```
**Tests:** `test_scoring_predicted_units_sold_equals_calibrated_not_policy_cap`  
**Release:** Still NO (flat raw model)

### Phase 2 — Preserve demand-only calibrated across exports

**Files:** `trainer.py`, `run_promotions_feature_family_ablation.py`, `run_promotions_low_nonzero_specialist.py`  
**Change:** `predicted_units_total_promo = calibrated` (not policy_adjusted)  
**Tests:** Backtest export contract tests

### Phase 3 — Route caps into order policy only

**Files:** `allocation_calibration.py`, `order_policy_adjustments.py`, `store_prediction_download_builder.py`  
**Changes:**
- Split `allocation_cap_units` from demand
- Remove order cap ceiling on `predicted_units_total_promo_raw`
- Apply caps only in order reconciliation path

### Phase 4 — Flat raw-model diagnostic gate

**Files:** New gate module + `scoring_service.py`  
**Changes:** Detect flat cohort; emit warnings; block customer-ready; stop integerize masking for demand input

### Phase 5 — Feature consensus fallback (after validation only)

**Files:** `allocation_demand_forecast_contract.py`  
**Changes:** Provenance-gated fallback only — **not in initial repair**

---

## 5. Forbidden After Repair

- ❌ Assign `adjusted_order_cap_units` into `predicted_units_sold`
- ❌ Use order cap as demand
- ❌ Let capital/risk policy shrink demand forecast
- ❌ Let anti-collapse floor hide model failure
- ❌ Release if demand remains flat without warning/blocker
- ❌ Replace model demand with feature consensus without actual-outcome validation

---

## 6. First File/Function to Patch

**`src/runtime/promotions/scoring_service.py`** — `PromotionScoringService.score` — lines **171** and **225**.

This is the smallest safe change with highest leverage: restores demand semantics without touching Stage 11, calibration logic, or model training.

---

## 7. Tests Required

| Phase | Test |
|---|---|
| 1 | `test_scoring_predicted_units_sold_equals_calibrated_when_policy_fires` |
| 1 | `test_policy_adjusted_predicted_units_sold_differs_from_predicted_units_sold_when_capped` |
| 1 | `test_predicted_units_first_day_derived_from_demand_not_cap` |
| 2 | `test_backtest_export_predicted_units_total_promo_is_calibrated` |
| 3 | `test_allocation_cap_units_separate_from_calibrated_demand` |
| 3 | `test_stage11_forecast_total_not_capped_by_order_policy` |
| 4 | `test_flat_raw_cohort_emits_demand_warning_and_blocks_release` |
| 4 | `test_se01_rerun_selected_demand_not_uniform_one_without_floor` |

---

## 8. Release Gates

| Gate | Current | After Phase 1 | After Phase 3 | After Phase 4+model fix |
|---|---|---|---|---|
| Demand/order separated | ❌ | ✅ | ✅ | ✅ |
| Demand magnitude credible | ❌ | ❌ | ❌ | TBD |
| Customer-ready | ❌ | ❌ | ❌ | TBD |
| Report releasable | ❌ | ❌ | ❌ | TBD |

---

## 9. Risk Summary

| Risk | Mitigation |
|---|---|
| Orders increase when demand uncapped | Keep caps on order path; shadow replay |
| Downstream assumes conservative predicted_units_sold | Alias period + audit |
| Flat model exposed | Phase 4 gate blocks release |
| Premature feature fallback | Phase 5 gated on actuals |

**Overall repair risk:** MEDIUM — semantic correction with controlled rollout. Safer than continuing to publish demand that is actually an order cap.

---

## 10. Recommendation

| Question | Answer |
|---|---|
| Patch next? | **YES — Phase 1 only** (`scoring_service.py`) |
| Report can be released? | **NO** |
| Stage 11 patch needed? | **Not in Phase 1**; Phase 3 removes order cap on forecast total only |

Stop here. Do not implement until Phase 1 patch is explicitly approved.
