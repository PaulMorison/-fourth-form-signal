# Target commercial architecture (Phase 5A design — target 80/100)

## Runtime root (single source for store)

```
promotions_runtime_governed/promotions/priceline/772/commercial_reports/
  read_me_first.md
  future_promotions_index.csv
  completed_promotions_index.csv
  report_quality_scorecard.csv
  future/
    <yyyy-mm-dd>_<promotion_slug>/
      read_me_first.md
      order_plan_all_skus.csv      # ALL SKUs — primary buyer file
      order_decision_sheet.csv     # buyer fills in
      rejected_or_hold_skus.csv    # trust file — poor sellers explained
      review_exceptions.csv
      manager_summary.csv
      audit_trail.csv
  completed/
    <yyyy-mm-dd>_<promotion_slug>/
      read_me_first.md
      model_performance_summary.csv
      sku_prediction_vs_actual.csv
      miss_analysis.csv
      stockout_and_supply_review.csv
      learning_actions.csv
      audit_trail.csv
  archive/
    shadow_pilot_20260622/
    pre_5b_production_snapshots/
```

**Rule:** Only promotions with `promotion_start_date >= 2026-06-20` appear under `future/`.

## Report families

| Family | Trigger | Primary file | Audience |
|--------|---------|--------------|----------|
| **Order planning** | Future promo | `order_plan_all_skus.csv` | Store buyer |
| **Performance review** | Completed promo + actuals | `sku_prediction_vs_actual.csv` | Manager + model owner |
| **Audit** | Always | `audit_trail.csv` | Engineering / compliance |
| **Governance** | Pack level | `read_me_first.md`, indexes | Everyone first |

## Future promotion workflow

1. Operational cycle scores live packets for upcoming promos (start ≥ 2026-06-20).
2. `commercial_report_builder` (new module) writes one folder per promotion.
3. Buyer opens index → promotion folder → `order_plan_all_skus.csv`.
4. Buyer acts on BUY/REVIEW rows; checks `rejected_or_hold_skus.csv` for trust.
5. Buyer completes `order_decision_sheet.csv`.
6. No automatic ordering; `SHADOW_NOT_PRODUCTION` until explicit production approval.

## Completed promotion workflow

1. After promo end + actuals landed, builder writes `completed/<slug>/`.
2. Manager opens `model_performance_summary.csv` then `sku_prediction_vs_actual.csv`.
3. Learning actions feed back to model owner — **not** to store order file.

## Model audit workflow (internal)

- Keep `Diagnostics/` for engineering gates.
- Never use diagnostics as store primary path.
- Shadow eval (`shadow_store_action_eval`) runs pre-publish QA only.

## Governance workflow

Every CSV row includes:
- `model_status`
- `production_ordering_approved`
- `customer_report_release_approved`
- `human_review_required`

Pack-level scorecard gates publish (target ≥ 95, aim 98).

## Code module boundaries (target)

| Module | Owns |
|--------|------|
| `sufficient_stock_demand_target` | Training target repair |
| `allocation_stock_contract` | Stock/demand/order math |
| `commercial_report_builder` (new) | Store-facing CSVs |
| `store_prediction_publisher` | Runtime folder writes only |
| `shadow_store_action_eval` | Pre-production cap QA |
| `trainer` | Artifacts only — no report logic |

## Column standard (order_plan_all_skus.csv)

Use 4B.21 schema — 41 columns, lowercase snake_case, split reason cells, explicit demand windows.

## Migration from current state

1. Freeze new shadow tmp scripts.
2. Point publisher at `commercial_reports/future/` for Jul 2026+ priceline promos.
3. Archive Feb–Apr 2026 shadow packs to `archive/shadow_pilot_20260622/`.
4. Update `README_SHADOW_REVIEW_LOCATION.md` to new root.
5. Single integration test: one promotion folder passes scorecard ≥ 95.
