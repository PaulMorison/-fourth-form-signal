# Phase 4B Shadow Smoke Review

**Mode:** Read-only review of existing smoke outputs. No training rerun. No production retrain.

## Smoke inputs

- Slice: enriched 5,004-row `training_ready.parquet` (recent5k rebuild)
- Run id: `phase4b-shadow-sufficient-stock-smoke`
- Artifacts: `tmp/phase4b_shadow_trainer_smoke/`
- Source diagnostics: `Diagnostics/phase4b_shadow_trainer_smoke/`

## 1. Shadow artifact paths

| Role | Path |
|---|---|
| Production units (legacy target) | `.../units_gradient_boosting.joblib` |
| Shadow units GB | `.../target_mode_shadow_sufficient_stock_units_gb.joblib` |
| Shadow predictions | `.../test_set_predictions_sufficient_stock_shadow.parquet` |
| Live predictions | `.../test_set_predictions.parquet` |

Manifest confirms `units_target_mode=sufficient_stock_shadow`, `live_units_training_target_column=target_actual_units_sold`, `units_target_weight_used=True`.

## 2–4. Prediction distribution

Test rows: **716**. Shadow bucket mix (raw units): 179 ≤1, 96 (1–5], 414 (5–20], 27 (20–100], 0 >100.

Legacy vs shadow: legacy mean **1.26** / p50 **0.06**; shadow mean **8.06** / p50 **10.28**. Shadow shifts mass upward — expected given repaired sufficient-stock targets.

## 5–6. Flat / tiny shares & training weights

| Metric | Legacy | Shadow |
|---|---|---|
| Flat share | **48.9%** | **4.2%** |
| Tiny (≤1) share | **59.5%** | **25.0%** |
| Positive-weight training rows | — | **4,889 / 5,004** |

**Flat-share:** shadow is materially less flat (−44.7 pp).

## 7–8. Credibility & risk

- **Less flat:** yes — primary smoke success signal.
- **Extreme order risk:** shadow max **86.7** vs legacy **25.5**; p90 **12.1** vs **2.9**. Stock-basis over-order rate not computable from smoke passthrough columns — **must gate on formal eval**.
- **Artifact safety:** passed — separate shadow paths; production bundle preserved.

## 9. Formal shadow eval readiness

**Recommend formal shadow evaluation** (not run here) because:
- Flat/tiny shares improved materially
- P0 dedicated tests 11/11 pass
- Broader 4 failures do not touch sufficient-stock shadow code

**Conditions for formal run:**
- Include stock_basis over-order and weighted MAE gates
- Monitor elevated shadow tail vs legacy
- Still no production retrain or live target swap

## 10. Test failures

See `shadow_smoke_test_risk_review.csv` and `Diagnostics/phase4b_shadow_trainer_smoke/test_risk_note.md`. Failures appear pre-existing/data-dependent; **do not block** proposing formal shadow eval.

## Decision

| Question | Answer |
|---|---|
| Formal shadow eval recommended? | **YES — pending human acceptance of this review** |
| Production retrain? | **NO** |
| Live model changed? | **NO** |
| Report release? | **NO** |
| Next step | Accept review → run formal shadow eval on full enriched slices with tail/weighted-error gates; do not retrain production |
