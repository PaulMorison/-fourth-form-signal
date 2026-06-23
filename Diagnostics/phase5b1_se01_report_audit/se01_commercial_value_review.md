# SE01 Skincare Sales Event — Commercial Value Review (5B.1)

## Promotion
- **Event:** SE01 skincare sales event
- **Start:** 2026-07-23
- **Store:** 772 (Priceline)
- **Path:** `promotions/priceline/772/prediction/2026-07-23/`

## Critical finding (SE01 production file)
- **3,531 SKUs** present (all-SKU coverage: YES)
- **Actions:** DO_NOT_BUY 2,558 | REVIEW 972 | MONITOR 1 | **BUY 0**
- **order_units > 0:** **0 across entire promotion**
- Store cannot place orders from this file as-is — no positive recommendations despite future promo start 2026-07-23

## What is useful
- Main allocation (21 cols) has the right **concepts**: priority, SOH, pre-promo demand, promo demand, target SOH, gap, discount, order units.
- Manager summary aggregates capital and demand totals for one-screen oversight.
- Operator audit has recommended vs final order, confidence %, capital at risk — essential for 98+ schema.
- Feature inspection has historical/discount-band demand — audit only.

## What is confusing
- **Four files** for one promotion; buyer does not know which to open.
- **661-column** feature inspection presented alongside 21-column action file.
- Field names mix styles: `projected_SOH_at_promo_start` vs `expected_units_before_promo_start`.
- `expected_promo_demand` does not state it is **promo-period only**.
- `operator_action` vs `operator_decision` vs policy labels — unclear decision enum.
- BUY rows with demand collapse (`expected_promo_demand=1`) destroy trust.

## Why not commercially usable (~12/100 for this promo)
0. **Zero order units for all 3,531 SKUs** — no actionable BUY path in production output.
1. No single `order_plan_all_skus.csv` with all SKUs and split reasons.
2. Rejected/HOLD SKUs not surfaced in a dedicated trust file.
3. No confidence/data-quality scores on main file.
4. Governance labels absent on production CSVs.
5. Reconciliation across 4 files not automated.

## What must change for 98+
- One canonical file: `se01_skincare_sales_event_order_plan.csv` (45 cols, all SKUs).
- Pull confidence/capital from audit; never expose 661 feature cols to buyer.
- Explicit demand windows in column names.
- Split reasons into 5 cells.
- Manager summary as 1-row reconcile target only.
