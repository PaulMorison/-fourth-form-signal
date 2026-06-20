# Stage 11 Customer-Output Reliability Review

**Mode:** read-only forensic review. No code patched, no SQL, no training, no Stage 12, no source-packet mutation, no `actual_outcome_source.csv` build.

## 0. Important provenance caveat

The exact uploaded customer files were **not present anywhere in the workspace, Downloads, or Desktop**:

- `772_2026-07-23_allocation-report-se01-skincare-sales-event.csv` (+ operator-audit, manager-summary, feature-inspection)

They appear to have been reviewed by the requester outside the repo. To run a real, data-driven forensic review I analysed the **newest on-disk Stage 11 artifact set that carries the identical operator schema and the identical symptom pattern** to the reported customer output:

- `tmp/stage11_clean_visible_replay_20260614/governed/promotions/priceline/772/prediction/2026-05-21/772_2026-05-21_allocation-report-wk47-48-winter-part-1.csv` (+ manager-summary, feature-inspection)

This proxy is the same store (772), same old operator contract, and reproduces the reported numbers almost exactly:

| Metric | Customer-reported (se01) | Proxy (wk47-48) |
|---|---|---|
| total SKUs | 3,531 | 3,597 |
| `expected_promo_demand == 1` | 3,527 | 3,573 |
| `expected_promo_demand == 0` | 4 | 2 |
| positive demand + NO_DEMAND | 2,521 | 2,794 |
| positive stock gap | 1,744 | 2,090 |
| total stock gap units | 4,781 | 4,180 |
| total order units | 0 | 1 |
| canonical demand fields present | (asked) | **NO** |

The match is close enough that conclusions transfer directly. Numbers below are computed from the proxy and are representative of the customer file's defect class.

---

## 1. Headline verdict

- **Customer-ready: NO.**
- **Stale / incomplete vs latest contract: YES — the output predates the demand-forecast contract build (and even the stock-contract column restructure).**
- **Recommendation: do NOT patch in response to this file. Rerun Stage 11 with the latest build first, then re-review.** Several of the reported defects are already fixed in the committed code; the remaining one (magnitude collapse) is upstream of Stage 11 and must be diagnosed against fresh output, not this stale artifact.

## 2. Canonical demand-contract fields (Review area 1)

**None of the 13 canonical fields are present** in the operator output:
`pre_promo_demand_units, promo_window_demand_units, total_expected_demand_units, demand_forecast_units_q50/q70/q85/q95, selected_demand_quantile, selected_demand_units, demand_forecast_confidence, demand_forecast_basis, demand_forecast_reason_code, demand_forecast_warning`.

The report's 21 columns are the **legacy simplified operator schema**:
`priority_rank, priority_band, sku_number, sku_description, operator_decision, operator_action, order_units, reason_short, risk_flag, review_flag, audit_notes, current_soh, on_order_at_advice_time, expected_units_before_promo_start, projected_SOH_at_promo_start, target_SOH_at_promo_start, floor_units_required, expected_promo_demand, available_to_sell_before_floor, projected_stock_gap_units, discount_percent`.

The current committed contract (`STORE_FACING_OUTPUT_COLUMNS`) leads with `store_number, promotion_id, … model_run_date, …` and includes the full demand-forecast block. **This file therefore cannot have been produced by the latest build → likely-stale = YES.**

## 3. Legacy fields still driving output (Review area 2)

`expected_promo_demand` is the legacy field present and driving the customer-visible promo demand. `expected_units_first_7_days / expected_units_total_promo / projected_promotional_units` are not report columns in this simplified schema but are present in the feature-inspection layer and are equally collapsed there (all = 1 for the same SKUs).

## 4. Why promo demand collapses to 0/1 (Review areas 3–5) — ROOT CAUSE

This is **not just integer rounding of small per-store demand**. The production demand path is collapsed *before* Stage 11, while the raw feature signals are intact. Proof, from `feature_vs_final_demand_gaps.csv`:

| sku | expected_promo_demand (final) | expected_units_total_promo | feature_expected_total_units_first_7_days | feature_probability_expected_units_consensus | historical_units_same_discount_avg | demand_evidence_label | demand_evidence_class |
|---|---|---|---|---|---|---|---|
| 62472 | 1 | 1 | **130.4** | 8.5 | 3.0 | NO_DEMAND | low_nonzero_demand |
| 63361 | 1 | 1 | **51.2** | 19.1 | 0.0 | NO_DEMAND | low_nonzero_demand |
| 194048 | 1 | 1 | 1.1 | **47.9** | **49.8** | NO_DEMAND | low_nonzero_demand |
| 613487 | 3 | 3 | 6.6 | **35.8** | 0.0 | NEVER_SOLD_IN_PROMO | healthy_nonzero_demand |

Two internal impossibilities confirm the collapse is upstream of the operator formatting:
1. `expected_units_total_promo = 1` but `feature_expected_total_units_first_7_days = 130` for the **same row** — total-promo demand cannot be below first-7-day demand. The productionised `expected_units_*` family has been flattened to 0/1 while the raw `feature_*` consensus retained signal.
2. **717 SKUs** have a feature demand signal exceeding final demand by ≥2 units (many by 30–130).

**Most likely root cause of demand collapse:** the store-level demand production path (`predicted_units_total_promo` / `expected_units_*`) feeding Stage 11 is being flattened to a 0/1 per-SKU indicator — consistent with a forecast-repair / store-disaggregation / allocation step collapsing chain-level demand to ~1 unit per store and then integer-rounding — while the `feature_*` consensus columns (which Stage 11 only displays, never consumes) keep the real magnitude. Because the new demand contract consumes `predicted_units_total_promo` as its q50 base, **rerunning with the latest build will not by itself restore magnitude** if this upstream collapse persists; it will, however, surface it honestly via `demand_forecast_basis`, `demand_forecast_confidence=REVIEW`, and warnings rather than a silent 1.

## 5. Positive demand + NO_DEMAND contradiction (Review area 6) — ROOT CAUSE

**2,794 rows** show `expected_promo_demand >= 1` together with `demand=NO_DEMAND` in `audit_notes` and `demand_evidence_label = NO_DEMAND`. Many of these rows simultaneously carry `demand_evidence_class = low_nonzero_demand` or even `healthy_nonzero_demand` — the label and the class disagree on the same row.

**Most likely root cause:** in this stale build the audit/`demand_evidence_label` is produced by a separate evidence classifier (sparse/zero-history → `NO_DEMAND`) that is **not reconciled** against the numeric `expected_promo_demand`, which is rounded up to 1. The two code paths disagree.

This exact contradiction is the one the new stock contract's `compose_contract_audit_demand_label` was written to prevent (it forces `PROMO_DEMAND_PRESENT` whenever promo demand > 0) and which the new demand contract guards in validation. **A rerun on the latest build removes this contradiction class.**

## 6. All-zero orders despite positive gaps (Review areas 7–8) — ROOT CAUSE

`total order units = 1` across 3,597 SKUs; **2,089 SKUs have a positive stock gap and a zero order** (manager summary: `total_recommended_order_units = 1`, `skus_with_stock_gap_before_launch = 2,090`, `total_stock_gap_units_before_launch = 4,180`).

From `positive_gap_zero_order_review.csv`, the dominant pattern is `operator_decision = LOW_SOH_NO_AUTO_BUY`, `operator_action = DO_NOT_BUY`, gap = 2 (the 2-unit launch floor), demand = 1, with `demand=NO_DEMAND` in the audit trail.

**Most likely root cause of all-zero orders:** the zero-order suppression is gated on the **same unreliable weak-demand / NO_DEMAND signal** that is itself contradicted by the data (section 5). The gating logic is "weak demand → do not auto-order", but the "weak demand" classification is wrong for thousands of SKUs that actually have nonzero/healthy demand evidence. So the suppression is **over-gated on a broken input**, not justified by an explicit promotion-level no-order decision. There is no promotion-level "do not order this event" flag — it is a per-SKU collapse cascading into blanket suppression.

## 7. Pre-promo demand (Review area 9)

Not a primary defect here. `total_pre_promo_demand_units = 199` vs `total_promo_window_demand_units = 3,685`; only **1 SKU** has pre-promo materially above promo-window demand. The 56-day horizon clamp is not producing unrealistic depletion in this output (pre-promo is small because lead-up demand is itself collapsed). See `pre_promo_demand_anomalies.csv`. Manager summary's `total_projected_pre_promo_sales_units = 199` vs `total_projected_first_7_days_units = 3,659` is internally consistent with the per-row data — the customer-reported 18,389 vs 3,527 split is a different promotion but the same structural pattern (pre-promo and promo-window demand drawn from different, unreconciled scales).

## 8. Customer-output contract quality (Review area 10)

From `customer_output_column_quality.csv`:
- **Internal-only order-state columns as columns:** none in this simplified report — but `recommended_order_units`, `final_store_order_units`, `provisional_units`, `raw_units` are **embedded verbatim inside `audit_notes`** (e.g. `raw_units=2; provisional_units=0; final_units=0`). The customer's wider file likely exposes these as full columns; either way internal order-state is leaking into the customer surface.
- **Audit-note contradictions:** `demand=NO_DEMAND` next to positive `expected_promo_demand` (2,794 rows).
- **Manager-summary contradiction:** `total_recommended_order_units = 1` while 2,090 SKUs are short by 4,180 units.
- **Duplicate/aliased demand views:** `expected_promo_demand` (report) vs `expected_units_total_promo` (feature) vs `feature_expected_total_units_first_7_days` — three demand numbers per SKU that disagree by 1–130 units with no reconciliation column.

## 9. Top 10 reliability defects

1. Canonical demand-contract fields absent — output predates the latest build (stale).
2. Promo demand collapsed to 0/1 for ~99% of SKUs (`expected_promo_demand`, `expected_units_*`).
3. Production demand contradicts itself: `expected_units_total_promo (1) < feature first-7-days (130)`.
4. 2,794 rows: positive numeric demand labelled `NO_DEMAND` (audit + `demand_evidence_label`).
5. `demand_evidence_label = NO_DEMAND` on rows whose `demand_evidence_class = healthy_nonzero_demand`.
6. All customer orders zero (total = 0–1) despite 4,180-unit aggregate launch gap.
7. 2,089 positive-gap SKUs suppressed to zero order on an unreliable weak-demand signal (over-gated).
8. Internal order-state (`raw_units/provisional_units/final_units`) leaking into `audit_notes` / customer surface.
9. Manager summary internally contradictory (orders ≈ 0 vs 2,090 SKUs short).
10. Three unreconciled demand magnitudes per SKU (report vs feature-total vs feature-first-7-days).

## 10. What must be fixed before the next customer-facing run

1. **Rerun Stage 11 on the latest build (commit `d6b1426`)** so the customer surface carries the canonical demand-forecast contract fields, removes the `NO_DEMAND`-with-positive-demand contradiction, and stops leaking internal order-state.
2. **Diagnose the upstream demand collapse** (the `predicted_units_total_promo` / `expected_units_*` flattening to 0/1) against fresh output. This is the dominant defect and is **not** fixed by Stage 11 formatting alone — confirm whether store-level disaggregation/forecast-repair is collapsing chain-level demand and whether `feature_*` consensus should feed the contract's q50 base when the productionised prediction is sub-unit.
3. **Reconcile the demand-evidence label/class** so `NO_DEMAND` cannot be emitted when numeric demand or `demand_evidence_class` is nonzero (the new contract's audit-demand-label guard does this; verify it after rerun).
4. **Re-examine the zero-order gating** once demand magnitude is restored — confirm suppression is driven by explicit blockers, not by the collapsed weak-demand signal.
5. Confirm no internal order-state columns/strings appear on the customer surface after rerun.

## 11. Patch now or rerun first?

**Rerun the latest build first, then re-review.** Patching against this stale file would (a) risk re-fixing defects the committed contract already addresses and (b) cannot diagnose the real upstream demand collapse, which only fresh latest-build output can isolate. Do not paper over the magnitude collapse with REVIEW labels — surface it through `demand_forecast_basis/confidence/warning` and fix the upstream demand path.
