# Stage 11 Post-Fix Reliability Review (Patch B + Patch C)

**Mode:** narrow implementation verification. Patches B and C applied (working tree). No SQL, training, Stage 12, E2E, production ordering, source-packet mutation, or stock-identity changes.

## What changed
- **Patch C — NO_DEMAND reconciliation** (`store_prediction_download_builder.py`): `demand_evidence_label` can no longer be `NO_DEMAND`/`NEVER_SOLD_IN_PROMO` when `selected_demand_units > 0`. A de-minimis (`promo_window_demand_units <= 1`) companion keeps single-unit forecasts treated as safe holds for suppression-safety.
- **Patch B — demand collapse guard** (`allocation_demand_forecast_contract.py` + Stage 11 wiring): a feature-layer demand signal (`feature_probability_expected_units_consensus`, fallbacks first-7-days / same-discount history) is threaded into the contract. When promo-window demand collapses to 0/1 while the feature signal is materially higher (≥ max(5, 3×promo)), the row gets `demand_forecast_warning = DEMAND_COLLAPSE_RISK_FEATURE_SIGNAL_HIGHER` and `validate_demand_forecast_contract_frame` counts `rows_with_demand_collapse_risk`. Demand is **not** inflated and **not** routed to REVIEW.

## Focused tests
`175 passed, 27 subtests passed` (was 167; +8 new tests for B and C).

## Fresh post-fix output reviewed
`tmp/stage11_post_fix_rerun_output/.../2026-07-23/772_2026-07-23_allocation-report-se01-skincare-sales-event.csv` (3,531 SKUs).

> The full Stage 11 bundle **aborted at publication** on the safety guard `_validate_store_suppressed_order_risk_audit` (rows=3, in the **wk47-48** and **wk01-03** promotions — none in se01). The se01 per-promotion files were written before the abort and are reviewable.

## Post-fix gate results (se01)

| Gate | Result |
|---|---|
| Canonical demand fields present | **PASS** (all 13) |
| Positive demand + NO_DEMAND (audit) | **PASS** (0; was ~2,521) |
| Positive demand + NO_DEMAND (`demand_evidence_label`) | **PASS** (0; was 2,514) |
| Demand-collapse risk surfaced via warning/diagnostics | **PASS** (160 rows warned; was all-null) |
| Positive gap + zero order has explicit blocker | **PASS** (1,737 suppressed, 0 without blocker) |
| Internal field leakage | **PASS** (0 leak columns; raw/provisional/final tokens = 0) |
| Manager summary reconciles | **PASS** (SKUs 3531, orders 28, gap SKUs 1744, gap units 4802, pre-promo 18393, promo-window 3527 — all exact) |
| All-null columns | `demand_forecast_warning` no longer all-null (160 populated); `stock_constraint_adjustment_units`/`flag` still all-zero (justified — no stock-constraint signal in input) |
| Demand does NOT collapse to 0/1 | **FAIL** — `selected_demand_units`=1 for 3,506/3,531 (upstream model magnitude; now surfaced, not silent) |

## Verdict: customer-ready = NO

Two remaining blockers, both **outside the B/C scope**:

### Blocker 1 (hard, publication) — store_action_label / order-suppression not reconciled with positive demand
The bundle cannot publish: 3 SKUs have `demand_evidence_label=CREDIBLE_PROMO_DEMAND` (Patch C worked) but `store_action_label` still `NO_DEMAND`/`NO_PRIOR_PROMO_EVIDENCE_BASELINE_DEMAND`/`HOLD_STOCK` with their orders suppressed despite floor gaps of 13 / 2 / 1. The safety guard correctly refuses to publish unsafely suppressed executable orders.
- **Exact target:** `_build_store_action_label_frame` in `store_prediction_download_builder.py` (the `label`/`store_action_label` series, ~lines 8199–8223) and/or the order-suppression reconciliation — apply the same positive-demand reconciliation used for `demand_evidence_label` so credible-demand floor-risk SKUs either order to floor or carry an explicit documented hard blocker, instead of being suppressed under a no-demand/hold action.

### Blocker 2 (demand magnitude) — upstream promo-window collapse to ~1
`selected_demand_units` is 1 for 99% of SKUs with `basis=MODEL_PREDICTION`; 160 are now flagged as collapse risk (feature signal materially higher), 692 have feature signal ≥2 above final. Patch B surfaces this honestly but cannot correct it.
- **Exact target:** upstream store-level promo-window demand model (outside Stage 11). Validate against source why per-store promo prediction is ~1 for nearly all SKUs.

## Recommendation
Do **not** release. Resolve Blocker 1 (a narrow store_action_label reconciliation, same shape as Patch C) so the bundle can publish, then investigate Blocker 2 upstream. Re-run Stage 11 + diagnostics after Blocker 1 is fixed.
