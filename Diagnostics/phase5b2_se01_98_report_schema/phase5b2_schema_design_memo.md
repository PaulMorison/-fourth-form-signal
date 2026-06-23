# Phase 5B.2 schema design memo

## Why materially better
- One file, all 3531 SKUs, 45 clear columns, explicit demand windows, split reasons, governance labels.

## Field sources
| Canonical field | Primary source |
|-----------------|----------------|
| priority_rank, order_units, SOH, gap | main allocation |
| confidence_score, capital_at_risk, recommended_order | operator audit |
| promotion_days, totals | manager summary |
| avg_promo_demand_same_discount | feature inspection (aggregated, not raw features) |

## Formulas
- `total_expected_demand_to_promo_end_units` = pre_promo + promo_period
- `optimal_stock_on_hand_day_one_units` = predicted_promo_period_sales + target_end
- `projected_stock_on_hand_at_promo_start_after_order` = before_order + recommended_order
- `target_stock_on_hand_at_promo_end_units` = max(2, 30-day cover)

## Tests before trust
- Contradiction suite (current violations: 0)
- Manager summary reconciliation
- Zero-order BUY gate
- All-SKU count vs packet
- Scorecard >= 98

## Phase 5B.3 recommendation
Build `commercial_report_builder` for SE01 only from **scored model output** (not zeroed production allocation), emit 45-col schema to:
`promotions/priceline/772/commercial_reports/future/2026-07-23_se01_skincare_sales_event/se01_skincare_sales_event_order_plan.csv`

**Blocker:** Current production SE01 file has 0 BUY rows and 0 order units — 5B.3 must source from shadow/scoring path or fix Stage 11 policy before store handoff. Do not republish existing 2026-07-23 folder as canonical.
