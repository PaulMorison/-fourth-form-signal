# Phase 4B Shadow Trainer Evaluation Design

**Mode:** Design only. No training, no production retrain, no live target swap.

## Context

Phase 4B.5 enriched `training_ready.parquet` with repair evidence and parallel sufficient-stock fields. Enriched slices show 98% trainable / 64.2% repaired / 100% `demand_reference_units` on underallocated rows. Live training target remains `target_actual_units_sold`.

## Target mode design

| Parameter | Default | Shadow option |
|---|---|---|
| `units_target_mode` | `legacy_realized_sales` | `sufficient_stock_shadow` |
| Units fit target | `target_actual_units_sold` | `sufficient_stock_demand_units_target` |
| Sample weights | none (today) | `target_weight` where > 0 |
| Production artifacts | `units_gradient_boosting.joblib` | **not written** in shadow run |
| Shadow artifacts | n/a | `target_mode_shadow_sufficient_stock_units_*.joblib` |
| Shadow predictions | n/a | `test_set_predictions_sufficient_stock_shadow.parquet` |

## Exact selection point

**Primary patch location:** `PromotionModelTrainer.train()` in `src/models/promotions/trainer.py` (lines ~424–466 today hardcode `target_actual_units_sold`).

Add resolver helpers:
- `_resolve_units_target_mode(...)` → column name for fit/metrics
- `_resolve_units_sample_weights(dataset, mode)` → `target_weight` series or `None`

Wire through `_training_sets()` or inline at `units_*.fit(...)`.

**CLI entry:** extend `run_promotions_operational_cycle.py` / dedicated shadow runner with `--units-target-mode sufficient_stock_shadow` and mandatory `--run-id {id}-shadow-sufficient-stock`. Production cycles keep default.

**Precedent:** existing `target_mode` shadow path (`_write_target_mode_comparison_artifacts`, `target_mode_shadow_model_path`) already trains parallel models without touching production bundle.

## Sample weights

| Layer | Supports sample_weight? |
|---|---|
| sklearn `HistGradientBoostingRegressor` | yes |
| sklearn `Ridge` (units linear) | yes |
| `PromotionModelTrainer` today | **no — not passed** |

**Decision:** Not a fundamental blocker. Small trainer patch can pass `target_weight` for shadow mode only. Until patched, shadow eval can fall back to masking `target_weight > 0` rows but should not run as gate-passing without weight wiring.

## Legacy vs sufficient-stock comparison

Use enriched parquet fields:
- `target_actual_units_sold` (legacy live)
- `sufficient_stock_demand_units_target` (shadow label)
- `target_weight`, `target_quality_label`, `target_repair_basis`, `target_warning`

Compare on validation+test via parallel shadow fit:
1. Prediction distribution / flat share / zero-tiny share
2. MAE/RMSE vs `target_actual_units_sold` where realized sales valid (holdout truth stays realized for both models)
3. Weighted MAE on CLEAN + REPAIRED slices
4. Supplier/category slice checks
5. Over-order risk vs `stock_basis_units`

Production scoring and customer reports remain on legacy bundle.

## Safety gate before any live swap

1. Shadow flat prediction share materially below legacy
2. No increase in extreme over-order risk vs legacy
3. Weighted validation error improves or documented trade-off
4. Stage 11 reliability diagnostics pass on shadow backtest output
5. Manager summary reconciliation preserved
6. No feature consensus as target truth

## Recommended first implementation patch (not executed here)

1. Add `sufficient_stock_shadow` to trainer units mode resolver (separate from existing historical allocation `target_mode`).
2. In shadow branch: fit units heads on `sufficient_stock_demand_units_target` with `sample_weight=target_weight` and train mask `target_weight > 0`.
3. Persist to `target_mode_shadow_sufficient_stock_units_gb.joblib` via `target_mode_shadow_model_path`.
4. Write `test_set_predictions_sufficient_stock_shadow.parquet` with columns prefixed `shadow_sufficient_stock_*`.
5. Emit comparison CSV/JSON alongside existing target_mode comparison artifacts.
6. Run via enriched local parquet (`tmp/phase4b_training_ready_enrichment_smoke/`) with explicit shadow run_id.

## Decisions

| Question | Answer |
|---|---|
| Shadow training run now? | **NO** — await explicit approval after this design |
| Production retrain now? | **NO** |
| Report releasable? | **NO** |
| Next step | Approve patch scope → implement shadow branch + P0 tests → run local shadow eval on enriched smoke slices |
