# Phase 4B.16 Prediction Folder Rewrite

## Paths
- **Output folder:** `/Users/paulmorison/promotions_runtime_governed/promotions/772/prediction`
- **Backup folder:** `/Users/paulmorison/promotions_runtime_governed/promotions/772/prediction/archive/pre_phase4b16_20260622_1506`
- **Production source inspected (not overwritten):** `/Users/paulmorison/promotions_runtime_governed/promotions/priceline/772/prediction`

## Current priceline prediction files (sample latest)
- 2026-07-23/772_2026-07-23_allocation-report-se01-skincare-sales-event.csv
- 2026-07-23/772_2026-07-23_allocation-report-se01-skincare-sales-event_feature-inspection.csv
- 2026-07-23/772_2026-07-23_allocation-report-se01-skincare-sales-event_manager-summary.csv
- 2026-07-23/772_2026-07-23_allocation-report-se01-skincare-sales-event_operator-audit.csv
- 2026-07-24/772_2026-07-24_allocation-report-op07-1-2-price-friday.csv
- 2026-07-24/772_2026-07-24_allocation-report-op07-1-2-price-friday_feature-inspection.csv
- 2026-07-24/772_2026-07-24_allocation-report-op07-1-2-price-friday_manager-summary.csv
- 2026-07-24/772_2026-07-24_allocation-report-op07-1-2-price-friday_operator-audit.csv

## Files created/rewritten
- MANAGER_SUMMARY_SHADOW.csv: 20 rows
- STORE_ACTIONS_SHADOW.csv: 2140 rows
- OPERATOR_DECISION_SHEET_SHADOW.csv: 714 rows
- ACTION_CAP_AUDIT_SHADOW.csv: 2140 rows
- ADDED_BUYS_REVIEW_SHADOW.csv: 462 rows
- TINY_DEMAND_BUYS_REVIEW_SHADOW.csv: 295 rows
- STOCK_BASIS_REVIEW_SHADOW.csv: 60 rows
- README_SHADOW_NOT_PRODUCTION.md

## Quality gates
| Gate | Result |
|------|--------|
| Backup before rewrite | YES (111 files archived) |
| Production priceline files overwritten | NO (copied to backup only) |
| Store action schema | PASS |
| Shadow labels on all CSVs | PASS |
| Manager summary reconciles | PASS |
| Zero-order BUY count | 0 (gate: 0) |
| Live model changed | NO |
| Production retrain run | NO |
| Orders placed | NO |
| Customer report release approved | NO |

## Store buyer opens first
1. `README_SHADOW_NOT_PRODUCTION.md`
2. `STORE_ACTIONS_SHADOW.csv`
