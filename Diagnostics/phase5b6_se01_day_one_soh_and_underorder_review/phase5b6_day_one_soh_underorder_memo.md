# Phase 5B.6 day-one SOH and under-order review

## Summary
- Report quality score: 85/100
- Commercial release score: 85
- BUY low-coverage (>10 shortfall): 0
- Best-seller under-order reviews: 308
- Projected day-one SOH formula failures: 0

Decisions before policy: {'HOLD': 1708, 'DO_NOT_BUY': 850, 'REVIEW': 778, 'BUY': 195}

## Is the system under-ordering best sellers?
Yes. Raw model orders cover only ~3.8% of target day-one order need on average. 308 likely best sellers are escalated to REVIEW with `best_seller_underorder_review` because historical/baseline demand is strong but the model order is far below target.

## Should BUY mean full target coverage or governed partial order?
**Governed partial order with explicit gaps.** BUY is reserved for rows where recommendation covers >=50% of target or remaining shortfall is <=5 units, and promo demand evidence is not unsafe/fallback. Partial model orders with large remaining gaps are REVIEW, not confident BUY.

## Recommended commercial policy
1. Treat `target_order_units_to_hit_day_one_soh` as the stock target gap, not the automatic order.
2. Use `recommended_order_units` as the governed model/store suggestion only.
3. Use `remaining_day_one_shortfall_units` and `recommendation_coverage_ratio` before placing orders.
4. Do not release customer-facing BUY labels while promo demand is fallback/unsafe for all SKUs.
5. Operator must accept/reject on the decision sheet; production ordering remains NO.
