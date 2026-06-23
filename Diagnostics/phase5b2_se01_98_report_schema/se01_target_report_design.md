# SE01 target report design

## Final store-facing file
`promotions/priceline/772/commercial_reports/future/2026-07-23_se01_skincare_sales_event/se01_skincare_sales_event_order_plan.csv`

## Supporting files (same folder)
- `read_me_first.md`
- `rejected_or_hold_skus.csv` — filter decision in (HOLD, DO_NOT_BUY)
- `order_decision_sheet.csv` — buyer fill-in columns
- `manager_summary.csv` — 1 row reconcile
- `audit_trail.csv` — merge of operator_audit key cols + feature IDs only

## Column count
**45 columns** per 5B.2 schema (all SKUs, no feature dump).

## Sort
BUY → REVIEW → HOLD → DO_NOT_BUY; within group by predicted_promo_period_sales_units desc.

## DO_NOT_BUY mapping
Map from HOLD where `expected_promo_demand` < 0.5 or policy blocks auto-buy or INSUFFICIENT evidence.
