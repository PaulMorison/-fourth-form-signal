# Phase 5B.12 promo demand evidence blocker

## Summary
- Structural report score: 100/100
- Commercial release score: 85/100
- Primary release blocker: real_promo_demand_forecast_missing
- Promo demand fallback rows before/after: 936 / 936
- Unsafe promo demand rows: 936
- Model promo forecast release-ready rows: 0

## Why rows were fallback-governed
All scored model promo-period fields (`expected_units_total_promo`, `expected_promo_demand`, `projected_promotional_units`, `expected_units_per_day`) are flat 0/1 placeholders in source files. The report builder correctly rejects them. Governed historical demand (same-discount and same-or-better-discount) is used instead. Row-level fallback now means missing/zero selected demand, not merely 'not model forecast'.

## Real promo-period model forecast
**No.** No SKU-discriminating non-flat promo-period model forecast exists in operator-audit, feature-inspection, or allocation-report sources for this promotion.

## Root cause
**Source data / upstream model scoring**, not Stage 11 mapping loss or report-builder rounding. Fields are present but flat. `raw_model_order_units` is order evidence, not promo-period demand.

## Fixable without retraining
Honest fallback semantics, lineage fields, same-or-better history tier, unsafe counting, and dual scorecard caps. Customer release remains blocked.

## Requires Phase 5C / upstream work
Retrain or repair scoring so `expected_units_total_promo` (or equivalent) is SKU-discriminating and passes sanity checks against baseline, same-discount history, SOH, and raw order units.
