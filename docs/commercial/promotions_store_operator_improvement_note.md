# Promotions Store Operator Improvement Note

Reviewed sample: `/Users/paulmorison/promotions_runtime_governed/promotions/priceline/772/prediction/2026-05-13/772_2026-05-13_all-predictions.csv`.

Observed issues in the published sample:

- `discount_percent` is `0.0` on the visible rows even where the promotion should carry a discount. That weakens operator trust because the file asks the store to buy without showing the commercial offer strength.
- The all-predictions CSV exposes internal execution fields such as `store_number`, `minimum_safe_stock_day_one_units`, `lead_days_to_promo_start`, `days_until_action`, `buy_now_flag`, `watch_flag`, `do_not_buy_flag`, `on_order_units`, `effective_available_units`, `gap_to_day_one_target_units`, `demand_evidence_class`, and `confidence_band` before the store manager has enough plain-English context.
- High order recommendations are repeated with similar reason text but no visible same-discount history, discount-response evidence, or completed-promotion backtest trust cue.
- Stockout risk is presented as a band only. The operator cannot see a likelihood, the launch-cover gap, or why the stockout risk is material.
- The file includes duplicated demand concepts (`lead_up_demand_units` and `expected_units_before_promo_start`) and old internal names that should stay in diagnostics or feature-inspection siblings.

Implemented direction:

- The operator CSV now starts with priority/action/SKU/order/discount/forecast/stockout/trust fields in the governed order.
- Discount now resolves row-wise: governed discount first, then price-derived fallback from normal/promo price when the mapped discount is missing or zero.
- Rows using price fallback are marked `REVIEW_DISCOUNT_MAPPING` rather than silently publishing a false zero discount.
- Same-discount and same-or-better discount history features are engineered leakage-safely and surfaced as readable response summaries.
- Backtest trust and approximate stockout probability/cover fields are included in the store-facing output; diagnostic feature details remain in the feature-inspection sibling.
- Demand uplift is now decomposed explicitly into baseline promo-window demand, expected incremental promo uplift, launch-window uplift, and lead-up depletion instead of flattening all demand pressure into one total figure.
- Store-facing launch targets now use baseline-led lead-up demand and uplift-aware first-7-day demand, while high window-blend conflict rows are forced to `REVIEW` instead of auto-ordering against total-window pressure.
- Allocation discipline is being tightened around evidence quality: same-discount support, uplift confidence, baseline trend, and elasticity confidence must now constrain aggressive quantity instead of letting broad promo demand pressure justify it.
- The next governed pass should convert those diagnostics into an explicit conservative order-policy overlay rather than widening the store CSV again. The overlay should only fire in the worst evidence buckets, should cap supported demand or force `REVIEW` with named reasons, and should write its actions into separate scoring and Stage 11 diagnostic artifacts.

Operator-facing constraint for that pass:

- keep the store-facing CSV stable unless a field is strictly needed for action
- write order-diagnostic summaries as separate governed artifacts
- expose why rows were pushed to `REVIEW` or conservatively capped without forcing internal model-debug fields into the operator contract
