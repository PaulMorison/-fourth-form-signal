# Keep / rewrite / archive plan (Phase 5A)

**No deletions in this phase.** Delete candidates require explicit approval.

## Keep as-is

| Asset | Why |
|-------|-----|
| `src/models/promotions/sufficient_stock_demand_target.py` | Core target repair; commercially essential |
| `src/models/promotions/shadow_store_action_eval.py` | Proven cap logic; migrate to production path after approval |
| `src/surfaces/promotions/reporting/allocation_stock_contract.py` | Order/stock math contract |
| `src/models/promotions/allocation_demand_forecast_contract.py` | Demand window separation logic |
| `src/state/promotions/datasets/*` | Feature/target assembly |
| Unit tests for above | Confidence gates |
| `priceline/772/prediction/<run-date>/` production folders | Source of truth until 5B replaces publisher |

## Keep but rename / relocate

| Asset | Action |
|-------|--------|
| `README_SHADOW_REVIEW_LOCATION.md` | Move under single `commercial_reports/read_me_first.md` |
| `promotions/772/predictions/shadow_review_*` | Relabel as `archive/shadow_pilot_20260622/` in repo |
| Shadow uppercase CSVs | Deprecate; lowercase schema only going forward |
| `Diagnostics/phase4b*/` | Move to `Diagnostics/archive/phase4b/` |

## Rewrite (Phase 5B+)

| Asset | Why |
|-------|-----|
| `store_prediction_download_builder.py` | Emit commercial pack per promotion, not 600-col dump |
| `store_prediction_publisher.py` | Write `future/<date>_<slug>/order_plan_all_skus.csv` |
| Post-hoc tmp scripts `phase4b16–21` | Replace with single `commercial_report_builder` module |
| Manager summary generation | One row per promotion with capital/risk totals |
| Index files | `future_promotions_index.csv` driven by start_date ≥ 2026-06-20 |

## Archive (read-only, do not delete)

| Asset | Why |
|-------|-----|
| `store_action_pack_shadow_20260622/` | Superseded by commercial pack concept |
| `promotion_order_pack_shadow_20260622/` | Superseded; good schema reference |
| `commercial_promotion_reports_shadow_20260622/` (Feb–Apr promos) | Pilot; wrong date window for live use |
| `shadow_review_20260622_phase4b16/` mirror | Historical pilot |
| All `Diagnostics/phase4b*` | Engineering audit trail |

## Delete candidates (DO NOT DELETE YET)

| Asset | Condition for future delete |
|-------|----------------------------|
| Duplicate shadow CSV sets at repo + runtime | After 5B publisher verified |
| `01_STORE_ACTIONS.csv` uppercase packs | After migration |
| Orphan tmp eval parquets | After archived to cold storage |
| `.DS_Store` in runtime | Anytime with approval |

## Explicitly do not do in Phase 5B without approval

- Delete production priceline folders
- Retrain or live-swap models
- Ingest operator feedback automatically
- Release customer-facing reports
