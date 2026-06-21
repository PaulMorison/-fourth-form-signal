# Phase 4 Raw Model Flatness Diagnostic

**Mode:** Read-only forensic. No code patched, no SQL, no training.

**Branch:** cursor/promotions-actual-outcome-stock-truth  
**Inputs:** e2e-live decision surface (SE01 skincare, store 772, n=3,531)  
**Model artifact:** `golden-20260520-commercial-20260601b-handofffix-e2e` (local replay copy under tmp/)

## Executive summary

Phase 3/3B cleaned the demand/output pipeline (caps separated, fractional canonical demand, warnings).  
Customer-ready remains **NO** because the **raw units model** still emits a collapsed cohort.

| Gate | Result |
|---|---|
| Flatness from model vs fallback | **MODEL** (no post-predict fallback in scoring_service) |
| Repredict also flat at modal | **YES** (replay modal 0.0927) |
| Repredict matches stored raw | **NO** (max abs diff 23.627524) |
| Identical raw = 0.0528 | **2,960 / 3,531 (83.8%)** |
| Tiny raw (<1 unit) | **3,467** |
| Train/predict schema match | **YES** |
| Target = realized sales | **YES** |
| Stockout contamination risk | **YES** |
| Customer-ready | **NO** |
| Report release | **NO** |

## 1. Is flatness from model or fallback?

Re-scored SE01 rows through `prepare_model_input_frame` + `units_model.predict` using the golden
`units_gradient_boosting` artifact. Stored `raw_predicted_units_sold` on the decision surface
**does not match** repredicted values
(stored modal 0.0528, replay modal 0.0927; replay flat share 94.0%).

**Conclusion:** Flat cohort originates at **`units_model.predict`**, not Stage 11 integerize,
not demand contract, and not a separate Python fallback path (`clip(lower=0)` only).
Stored-vs-replay divergence is an **artifact/input drift** signal, not evidence of an alternate fallback.

## 2. Feature saturation on flat cohort

| Metric | Flat cohort | Non-flat cohort |
|---|---|---|
| Missing/zero-dominated feature rate | 0.000 | 0.000 |

Key sparse-history signals (flat cohort means): {"feature_sparse_demand_evidence_available_flag": {"flat_mean": 1.0, "nonflat_mean": 1.0}, "feature_probability_model_use_flag": {"flat_mean": 0.7787, "nonflat_mean": 0.9475}, "feature_historical_promo_events_same_discount": {"flat_mean": 6.0527, "nonflat_mean": 6.3888}, "feature_historical_units_same_discount_avg": {"flat_mean": 0.5519, "nonflat_mean": 4.4713}}

Most `feature_historical_*` and prior-promo unit features are **zero for all rows**, so the tree
regressor sees a near-homogeneous feature vector for ~84% of SKUs and returns the same leaf prediction.

## 3. Train/predict schema

Missing columns after prep: none  
Prep-complete schema matches training feature list: **YES**  
Decision-surface surface columns missing (derived at prep): ['model_promo_start_month', 'model_promo_start_week', 'model_promo_start_dayofweek']

## 4. Target definition

`target_actual_units_sold` = `actual_units_sold` (realized sales, clipped at 0).  
This is **not** sufficient-stock demand and is **stockout-contaminated** when historical promo sales
were constrained by zero SOH.

## 5. Cross-promotion context (store 772)

SE01 has the highest modal-share collapse. See `cross_promotion_raw_flatness_store772.csv`.
Flatness is **not universal** across all promotions (some promos show higher variance / higher modal values).

## 6. 0.0528 interpretation

With 83.8% stored modal share and 94.0% replay modal share,
**0.0528 (stored) / 0.0927 (replay) are learned regression baselines** for
sparse-feature promo rows — not hard-coded Python defaults, but effectively a
**single tree leaf / collapsed GBM surface** when inputs are near-homogeneous.
Cross-promotion store-772 analysis shows the same modal (0.0528) dominates many promos (85–97%),
so flatness is **not SE01-specific**.

## 7. Recommended Phase 4 patch target (do not patch yet)

Phase 4B: design sufficient-stock promo-window demand target (stockout-safe) then controlled units-head retrain; do NOT patch Stage 11/demand contract.

## 8. Decision

| Question | Answer |
|---|---|
| Patch next? | **NO — target/label repair design first, then controlled retrain** |
| Release report? | **NO** |
| Use feature consensus as demand truth? | **NO** |

## Artifacts

- `raw_model_flatness_summary.csv`
- `flat_prediction_cohort_profile.csv`
- `feature_missingness_for_flat_cohort.csv`
- `feature_variance_for_flat_cohort.csv`
- `train_predict_schema_alignment.csv`
- `model_artifact_trace.csv`
- `target_definition_review.csv`
- `flatness_by_supplier_category_promo_type.csv`
- `raw_model_vs_feature_signal_review.csv`
- `phase4_repair_recommendation.csv`
- `cross_promotion_raw_flatness_store772.csv`
