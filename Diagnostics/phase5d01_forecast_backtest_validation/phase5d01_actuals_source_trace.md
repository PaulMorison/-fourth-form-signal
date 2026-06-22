# Phase 5D01 — Historical Actuals Source Trace

## Purpose
Document the realised promotion outcome source used to backtest Phase 5C promo-period demand forecasts.

## Primary source (selected)

| Field | Value |
|---|---|
| **Path** | `/Users/paulmorison/promotions_runtime_governed/training/models/e2e-live-20260619T123109/test_set_predictions.parquet` |
| **Run / cycle** | `e2e-live-20260619T123109` |
| **Row count** | 52,285 |
| **Grain** | `store_number` + `promotion_start_date` + `promotional_end_date` + `sku_number` |
| **Equivalent key** | `promotion_row_key` when present in sibling completed-promotion artefacts |

## Join fields

| Role | Column |
|---|---|
| Store | `store_number` |
| SKU | `sku_number` |
| Promo window start | `promotion_start_date` |
| Promo window end | `promotional_end_date` |
| Optional promo id | `promotion_row_key`, `promotional_sku_id` |

Backtest deduplication uses the composite above (one row per promo SKU event).

## Date window logic

Actual units are realised over the **live promotion window** defined by `promotion_start_date` through `promotional_end_date` (inclusive). This matches the completed-promotion training label pipeline:

- Upstream extractor: `src/data/promotions/completed_window_aggregates_extractor.py` (PWLOGD promo window)
- Joiner: `src/state/promotions/datasets/completed_dataset_joiner.py` maps `actual_units_sold` → `actual_units_sold_promo`

The parquet test split preserves those labels; it is **not** a forward-looking SE01 prediction file.

## Actual units field selected

**Primary:** `actual_units_sold_promo`  
**Fallback:** `actual_units_sold` (same promo-window semantics via completed dataset joiner)

Total realised units in test split: **48,808**.

## Actual GP field selected (proxy)

**Primary GP proxy:** `actual_sales_ex_gst_promo` / `actual_sales_ex_gst` when present  
**Unit GP proxy for economics:** `promo_gm_unit`, else `actual_sales_ex_gst / actual_units_sold`

Economics in Phase 5D are explicitly labelled **proxy** fields — not audited P&L.

## Stock / order context fields

Used for stockout and leftover suspicion (not as forecast targets):

| Field | Use |
|---|---|
| `store_adjusted_qty`, `pl_allocation_qty` | Recommended order proxy |
| `total_stock_available`, `stock_basis_units` | Sell-through / stockout suspicion |
| `post_14d_units` | Post-promo tail (when available) |

## Alternate / sibling sources (not primary for 5D01)

| Source | Why not primary |
|---|---|
| SE01 future prediction CSVs (`2026-07-23`) | No realised actuals — forward promo |
| `store-prediction-review.csv` | Pre-promo review; no `actual_units_sold` |
| `commercial_outcome_attribution.csv` | Sparse attribution rows; good for learning queue, not full SKU backtest |
| Legacy `promotion_demand_backtest.csv` | Uses old `predicted_units_total_promo`; retained for comparison only |

## Known limitations

1. **Test-set not live production** — labels come from held-out model training split, not customer-facing prediction exports.
2. **Missing `promotion_name` in parquet** — backtest uses `promotion_id` / row key where name absent.
3. **Order proxies** — `store_adjusted_qty` / allocation may reflect operator overrides, not pure model recommendation.
4. **GP proxies** — unit margin fields vary by row completeness; economic summary uses clearly named proxy metrics.
5. **Store 772-heavy sample** — e2e run is Priceline 772 centric; multi-store generalisation not proven here.

## Leakage risks

| Risk | Mitigation |
|---|---|
| Training features built with post-promo knowledge | Test split parquet is the honest evaluation holdout from training pipeline |
| Re-applying Phase 5C forecast on same rows used to tune uplift | Phase 5C formula uses pre-promo feature columns only; forecast logic unchanged in 5D |
| Using `predicted_units_total_promo` as actual | **Not used** — realised `actual_units_sold_promo` is the target |
| SE01 future promo actuals | **Excluded** — no actuals available |

## Governance

- Production prediction files under `promotions/priceline/772/prediction/` were **not modified**.
- No orders placed.
- Customer release recommendation derived only from this backtest evidence.
