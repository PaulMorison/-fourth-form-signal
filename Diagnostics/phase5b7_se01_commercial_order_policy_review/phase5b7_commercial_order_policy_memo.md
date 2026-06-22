# Phase 5B.7 commercial order policy review

## Summary
- Report quality score: 85/100
- Decisions before: {}
- Decisions after: {'REVIEW': 2253, 'DO_NOT_BUY': 1271, 'BUY': 7}
- HOLD with target order >20 before/after: 0 / 0
- REVIEW+NO_ORDER_REQUIRED conflicts before/after: 0 / 0
- Stock target conflicts: 467
- Target stock policy lifts: 0

## Target SOH vs raw model order
Target day-one SOH logic is more commercially credible as a **stock objective** because it ties promo demand and end-stock cover together. Raw model orders remain valuable as **conservative lower-bound evidence** but often under-cover target stock (avg commercial coverage ~3.8%).

## When to trust raw model order
Trust raw model order as the commercial recommendation when data quality >=70, confidence >=45, promo demand quality is not VERY_LOW, and raw order covers >=50% of target or leaves <=5 unit shortfall.

## When target stock policy should override or escalate
Escalate to REVIEW with TARGET_STOCK_REVIEW_RANGE when target order >=20 and raw model <50% of target. Apply TARGET_STOCK_POLICY_LIFT only for high-confidence best sellers with MEDIUM+ promo demand evidence.

## Recommended policy before production
Use operator review range (raw model low, target order high), never HOLD on material stock gaps, and do not release customer report while promo demand remains predominantly fallback/unsafe.
