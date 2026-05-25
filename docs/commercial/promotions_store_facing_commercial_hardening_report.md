# Promotions Store-Facing Reporting — Commercial Hardening Final Report

Run completed: this cycle. As-of-date: 2026-05-14.
Run id (live attempt): `promotions-e2e-live-commercial-final`.

## 1. Files changed in this hardening pass

- `src/surfaces/promotions/reporting/store_prediction_download_builder.py`
  - Constants: `MIN_LAUNCH_STOCK_UNITS`, `STORE_PRE_PROMO_HORIZON_DAYS = 56`,
    `STORE_FACING_OUTPUT_COLUMNS` (code-owned operator contract),
    extended `STORE_FACING_SCHEMA_COLUMNS`, `INTEGER_COLUMNS`,
    `CURRENCY_COLUMNS`.
  - New helper `_resolve_discount_percent_series` (auto fraction-vs-percent
    detect, clip 0..100, round 1 dp).
  - `_build_store_facing_frame` rewritten with kwargs-only signature,
    risk-adjusted recommended order, capital-at-risk, risk-reward
    fields, demand evidence multiplier, base-stock-first zeroing,
    launch floor (`MIN_LAUNCH_STOCK_UNITS = 2`), `DO_NOT_ORDER` force-zero,
    timing clamp (0..`STORE_PRE_PROMO_HORIZON_DAYS`).
  - Pre-promo expected units now scaled by the 56-day horizon ratio so a
    drifting `prediction_date` cannot inflate `expected_units_before_promo_start`.
  - Writer projects `STORE_FACING_OUTPUT_COLUMNS` to operator CSV; full
    intermediate frame still flows to manager-summary and feature-inspection.
  - `_build_store_promotion_manager_summary_frame` now reports
    `discount_percent_summary`, `total_risk_adjusted_capital_at_risk_dollars`,
    `average_risk_reward_ratio`.
  - `_compose_model_reason_summary` now consumes the risk-adjusted
    `capital_at_risk_dollars` so the operator sentence matches the dollar
    figure on the same row.
  - **New artifact**: per-promotion `*_feature-inspection.csv` sibling
    file containing all internal sort/diagnostic fields plus upstream
    model `feature_*` and `final_decision_score` / `final_confidence_score`
    columns. File type: `store_promotion_feature_inspection`.
- `tests/unit/test_promotions_store_prediction_download.py`
  - Schema test rewritten to OUTPUT contract.
  - 5 new end-to-end tests via `write_report` covering: discount auto-detect,
    risk-adjusted recommended order, base-stock-first behaviour, manager
    summary new fields, model reason summary cleanliness.
  - 1 new test for the feature inspection sibling artifact.
- `tests/unit/test_promotions_operational_cycle.py`
  - Updated assertions for new fields.
- `docs/architecture/domains/promotions_stage_11_12_transparency.md`
  - New transparency note describing Stage 11 vs Stage 12 NOOP semantics.
- `/memories/repo/implementation_notes.md`
  - Stage 11/12 commercial hardening summary (line 138).

## 2. Timing-bug root cause (599-day pre-promo window)

Upstream `prediction_date` could drift far ahead of the cycle's
`as_of_date`, so a future promotion 599 days out received 599 days of
modelled pre-promo demand, yielding an absurd
`expected_units_before_promo_start` and an inflated launch gap.

**Fix**: in `_build_store_facing_frame`, lead time is now computed as
`(promotion_start_date − as_of_date).days`, clipped to
`[0, STORE_PRE_PROMO_HORIZON_DAYS = 56]`. The model's raw pre-promo
units are then multiplied by `min(1.0, 56 / lead_unclamped)`. So a
promotion 599 days out is treated for stocking purposes as if it were
56 days out — within a horizon a store team can actually plan for.

## 3. Overbuying root cause and risk-adjusted formula

Upstream `suggested_order_units` was being copied straight to
`recommended_order_units`, so weak forecasts and sparse-evidence rows
generated identical buys to high-confidence rows.

**Fix**: `recommended_order_units = suggested_order_units ×
confidence_multiplier × evidence_multiplier`, then base-stock-first
zeroing and a launch floor.

- `confidence_multiplier = clip(0.5 + 0.5 × confidence_fraction, 0, 1)`
- `evidence_multiplier ∈ {1.0 healthy, 0.7 sparse, 0.5 no-evidence}`
- If `projected_on_hand_at_promo_start ≥ target_stock_day_one_units`
  → recommended order forced to 0 (use base stock first).
- Action `DO_NOT_ORDER` → forced to 0 regardless of all above.
- Otherwise: minimum launch quantity is
  `MIN_LAUNCH_STOCK_UNITS = 2`.

## 4. Capital-at-risk formula

```
order_exposure   = recommended_order_units × unit_cost
leftover_cost    = expected_leftover_units_end_of_promo × unit_cost
exposure_base    = max(order_exposure, leftover_cost)
confidence_risk  = (1 − confidence_fraction)
evidence_risk    = {0.6 healthy, 0.85 sparse, 1.0 no-evidence}
overstock_risk   = clip(target_day_one / max(projected_on_hand, 1), 0.05, 1.0)
capital_at_risk_dollars
                 = exposure_base × confidence_risk × evidence_risk × overstock_risk
```

This is the dollar a store manager could lose if the action is wrong.

## 5. Risk-reward ratio

```
expected_promo_revenue_proxy = predicted_units_total_promo × unit_cost
risk_reward_ratio = expected_promo_revenue_proxy
                  / max(capital_at_risk_dollars, $1)
```

Higher is better; values < 1 warn that capital exposure outweighs the
demand the model expects.

## 6. Tests run

- Promotions focus suite (`tests/unit/test_promotions_store_prediction_download.py`): **76 passed, 20 sub-tests**.
- Full promotions suite (`tests/unit/test_promotions_*.py`): **364 passed, 27 sub-tests** in 113 s.
- Full repo suite (`tests/`): cannot collect — pre-existing 28 collection
  errors caused by `ModuleNotFoundError: No module named 'platform.audit'`
  (an unrelated `platform` package shadowing). **Not introduced by this
  change.** Promotions tests are unaffected.

## 7. Live rerun command

```bash
PROMOTIONS_MSSQL_CONNECT_TIMEOUT_SECONDS=60 .venv/bin/python -c "
import sys; from pathlib import Path
sys.path.append(str(Path('.').resolve() / 'src'))
from runtime.promotions.run_promotions_operational_cycle import main
main([
  '--env-file','.env',
  '--artifact-root','/Users/paulmorison/promotions_runtime_governed',
  '--local-inspection-root','/tmp/promotions_e2e_live_commercial/local_inspection',
  '--run-id','promotions-e2e-live-commercial-final',
  '--as-of-date','2026-05-14',
])"
```

## 8. Live rerun result

The MSSQL connection succeeded this run (no 28000 / 18456 login failure)
and the cycle was actively iterating partitions (`completed_landed`
extraction across 129 store-SKU hash buckets) at the time this report
was finalised. Preflight artifacts and per-partition extraction
telemetry were already on disk under
`/Users/paulmorison/promotions_runtime_governed/.../promotions-e2e-live-commercial-final*/`.
The run was not yet complete enough to produce per-store CSVs by
report-write time.

## 9. Real per-store CSV paths inspected

None inspected against fully-completed live data because the live cycle
was still running through the completed-landed extraction stages when
this report was written. Prior local-fixture runs validated the new
columns end-to-end and the updated 76-test suite covers the contract
shape, risk-adjusted formula, manager summary fields, feature-inspection
sibling, and timing clamp.

## 10. Blunt rating

**77 / 100.** The store-facing operator CSV is now genuinely commercial:
code-owned operator contract, risk-adjusted order, capital-at-risk, risk-reward,
discount %, base-stock-first, launch floor, 56-day horizon clamp,
manager summary, feature inspection sibling, transparent Stage 11/12
boundary. Tests are dense and green. Points off because: (a) cadence
features from the SQL realised actuals (`pre_7d_days_with_sales`,
`pre_28d_days_with_sales`, `pre_56d_days_with_sales`) are present
upstream but not yet surfaced as a `historical_promo_response_summary`
sentence on the operator CSV; (b) no per-cycle `backtest_summary.json`
output yet, so prior-cycle accuracy is not surfaced to operators; (c)
live verification ended mid-run rather than with hand-inspected real
per-store CSVs.

## 12. Follow-up resilience and transparency addendum

A later hostile review found that the MSSQL retry loop existed but the real
operational-cycle configuration could still resolve omitted retry settings to
zero. The governing rule now lives in
`docs/architecture/domains/promotions_runtime_resilience_and_operator_trust_contract.md`:
omitted SQL connect retry settings use a bounded default, explicit zero remains
a visible override, and only transient connect/login failures are retried.

The Stage 11 contract has also moved beyond the old fixed 31-column statement.
The current source of truth is the `STORE_FACING_OUTPUT_COLUMNS` tuple in the
builder, with documentation required to describe the contract by behavior and
source rather than by stale column count.

## 13. Next governed diagnostic loop

The next hardening pass should not widen the store-facing CSV again. The gap is
no longer presentation; it is converting the new order-risk diagnosis into a
small governed live policy that actually suppresses the worst over-ordering
mistakes.

The governed next step is:

- keep the raw model and calibrated outputs visible, then add one explicit
  policy-adjusted layer on top of the calibrated output
- fire named conservative rules only in the worst governed buckets: weak
  same-discount history, weak elasticity, weak uplift, falling base demand,
  launch-vs-total conflict, stock-vs-supported-gap risk, and sparse-history
  multi-driver rows
- persist policy action diagnostics showing whether a rule fired, why it fired,
  whether it forced `REVIEW`, how many units it removed, and how much
  capital-at-risk it removed
- extend the trainer scoreboard to compare raw vs calibrated vs policy-adjusted
  error overall and in the major failure buckets
- publish a separate Stage 11 policy summary artifact for commercial review
  instead of pushing more internals into the operator CSV

That keeps the action file stable while making the next over-ordering fixes
evidence-based, explicit, and auditable rather than intuitive.

## 11. Single biggest remaining weakness

Operator-visible **historical promo response cadence** is the biggest
gap. The data is already extracted (`pre_7d_days_with_sales`,
`pre_28d_days_with_sales`, `pre_56d_days_with_sales` from
`promotion_base_extraction.sql`) but the store-facing CSV currently
reports the model's forward demand without a plain-English line such as
"Sold on 5/7 days last week, 18/28 days last month, 32/56 days last two
months". Adding that single sentence to the operator file (and using it
as a third evidence input alongside `demand_evidence_class` /
`confidence_band`) would close the trust gap a store manager
instinctively asks about: *"how often does this SKU actually move?"*.
