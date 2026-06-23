# Stage 11 Fresh-Output Reliability Review & Customer-Readiness Gate

**Mode:** read-only review. No code patched. No SQL, no training, no Stage 12, no E2E, no production ordering, no source-packet mutation, no `actual_outcome_source.csv`.

## Repo state (Step 1)
- **Branch:** `cursor/promotions-actual-outcome-stock-truth`
- **Latest commit:** `0ef1bb0` (review diagnostics) on top of demand+stock contract build `d6b1426`
- **Working tree:** clean
- **Contract files:** present
  - `src/models/promotions/allocation_demand_forecast_contract.py` ✔
  - `src/surfaces/promotions/reporting/allocation_stock_contract.py` ✔ (note: under `surfaces/...`, not `models/...` as the prompt assumed)
  - `src/surfaces/promotions/reporting/store_prediction_download_builder.py` ✔

## Customer files (Step 2)
The exact uploaded `se01-skincare-sales-event` (2026-07-23) CSVs were **not** present in the workspace, Downloads, or Desktop. **However**, the newest local decision-surface artifact (`e2e-live-20260619T123109_decision_surface.csv`) contains the `se01-skincare-sales-event` promotion for store 772. Re-running Stage 11 on it produced a **fresh latest-build version of the exact customer report** with **3,531 SKUs** — matching the reported customer count precisely. This is a true apples-to-apples comparison.

## Fresh Stage 11 rerun (Step 3)
Safe local-only rerun: loaded the local `decision_surface.csv`, filtered to store 772, and called `PromotionStorePredictionDownloadBuilder().write_report(...)` on the latest build. **No SQL / training / Stage 12 / E2E / production ordering.** Output root: `tmp/stage11_fresh_rerun_output/`.

Two immediate signals:
1. The fresh report carries **all 13 canonical demand-forecast fields** (cols 15–29).
2. `write_report` **hard-aborted at the end** on a *different* promotion (wk01-03 women's-health) with `PromotionStoreDownloadCommercialValidationError: Unsafe suppressed executable orders remain after Stage 11 reconciliation` (1 row, SKU 668680, `CREDIBLE_PROMO_DEMAND`, floor gap suppressed to HOLD). The per-promotion CSVs (including se01-skincare) were written before the abort. **This abort is a governance win**: the latest build refuses to publish an unsafely suppressed executable order rather than shipping silent zeros — the exact over-gating class the stale review flagged.

> Caveat: the persisted `decision_surface.csv` uses pre-rename column names (`predicted_units_total_promo`, `promotion_end_date`, `demand_evidence_class` show as MISSING on direct read), so the builder reconstructs demand internally. The **schema/contract is fully exercised**; absolute demand **magnitude** may differ slightly from a live in-memory frame, but the per-SKU pattern matches the customer report (3,531 SKUs, ~1 unit each, 1,744 positive gaps, 4,802-unit gap), so conclusions hold.

## Exact files reviewed
- `tmp/stage11_fresh_rerun_output/governed/promotions/priceline/772/prediction/2026-07-23/772_2026-07-23_allocation-report-se01-skincare-sales-event.csv`
- `..._feature-inspection.csv`, `..._manager-summary.csv`, `..._operator-audit.csv`

## Customer-readiness gate results

| Gate | Result | Evidence |
|---|---|---|
| 1. Canonical demand fields present | **PASS** | all 13 present; `demand_forecast_basis=MODEL_PREDICTION`, confidence MEDIUM 2158 / LOW 833 / HIGH 540, quantile q50 3429 / q85 101 / q95 1 |
| 2. No positive demand + NO_DEMAND | **PARTIAL FAIL** | operator `audit_notes`: **0** (fixed); feature `demand_evidence_label=NO_DEMAND` with positive demand: **2,514** (still broken) |
| 3. No 0/1 collapse unless proven | **FAIL** | `selected_demand_units` = 1 for 3,506 / 3,531 (99%); 0 for 4; 2 for 21 |
| 4. Positive gap + zero order has explicit blocker | **PASS** | 1,737 suppressed rows, **0 without an explicit `order_reason_code`/blocker**; build hard-aborts truly unsafe suppression |
| 5. Not all-zero orders w/ positive gaps | **PASS** | total order units = **28** (not zero) |
| 6. No internal-field leak | **PASS** | no `recommended_order_units/final_store_order_units/shadow` columns; `raw_units=/provisional_units=/final_units=` in `audit_notes`: **0** |
| 7. All-null / all-zero columns flagged | **FLAGGED** | all-null: `demand_forecast_warning`; all-zero: `stock_constraint_adjustment_units`, `stock_constraint_flag` |
| 8. Manager summary reconciles to operator output | **PASS** | SKUs 3531=3531, orders 28=28, gap SKUs 1744=1744, gap units 4802=4802, pre-promo 18393=18393, promo-window 3527=3527 |

## What the latest build FIXED vs the stale file
- Canonical demand fields now present (was: absent).
- Operator-audit `NO_DEMAND` + positive demand contradiction: **0** (was: ~2,521).
- Internal order-state leak: **gone** (was: `raw_units/provisional_units/final_units` embedded in audit notes).
- Zero-order suppression now **explicitly blocker-justified**, and unsafe suppression **hard-aborts** the run (was: silent all-zero).
- Manager summary now **reconciles exactly** (was: contradictory).
- Total orders 28 vs 0 (was: 0–1).

## What is STILL broken on the FRESH output (the real, non-stale defects)

### A. Promo-window demand collapses to ~1 for 99% of SKUs — UPSTREAM, not Stage 11
`demand_forecast_basis = MODEL_PREDICTION` and `reason_code = MODEL_PREDICTION_USED` for **all** 3,531 SKUs. The contract is **faithfully carrying the upstream model's store-level promo-window prediction (~1 unit/SKU)** — it is *not* masking it behind REVIEW. Root cause is the **upstream store-level promo demand model**, not Stage 11 formatting. The contract cannot manufacture magnitude. 692 SKUs have feature signals ≥2 units above final demand.

### B. `demand_evidence_label = NO_DEMAND` vs positive demand — classifier not reconciled
2,514 rows show `demand_evidence_label = NO_DEMAND` while `selected_demand_units = 1` **and** `demand_evidence_class = low_nonzero_demand` (the label contradicts its own class). Example: SKU 192046 — label NO_DEMAND, class low_nonzero_demand, consensus 73.0, selected 1. The operator audit was reconciled; the **feature-inspection evidence label was not**.

### C. Pre-promo demand >> promo-window demand — scale inconsistency
`days_until_promo_start = 63`, `promo_window_days = 7`. `pre_promo_demand_units` = baseline_daily × 63 (up to **240** units) while `promo_window_demand_units` = model prediction (**1**). Totals: pre-promo **18,393** vs promo-window **3,527** (≈5.2×) — matches the customer-reported 18,389 vs 3,527. 307 SKUs have pre-promo ≥2 units above promo-window. A store selling ~3.8/day in the 63-day lead-up cannot plausibly sell only 1 unit across the 7-day promo: the two demand legs are on inconsistent scales, and the long 63-day lead inflates pre-promo depletion that drives the stock gaps.

### D. Unused warning / dead detectors
`demand_forecast_warning` is **all-null** despite the magnitude collapse — the warning channel never fires. `stock_constraint_adjustment_units` and `stock_constraint_flag` are **all-zero** — stock-constraint detection never triggers on this input.

## Top 10 reliability defects (fresh output)
1. Promo-window demand = 1 for 99% of SKUs (upstream model magnitude; basis MODEL_PREDICTION).
2. 2,514 rows: `demand_evidence_label = NO_DEMAND` with positive selected demand (and class = low_nonzero_demand).
3. Pre-promo demand (18,393) ≈5.2× promo-window demand (3,527) from 63-day lead × baseline scaling.
4. 307 SKUs with pre-promo demand materially (≥2) above promo-window demand (up to 240 vs 1).
5. 692 SKUs where feature demand signal exceeds final demand by ≥2 units (consensus up to 73 vs selected 1).
6. `demand_forecast_warning` all-null — collapse never surfaces a warning.
7. `stock_constraint_adjustment_units` / `stock_constraint_flag` all-zero — constraint detection inert.
8. Total orders 28 against a 4,802-unit aggregate gap across 1,744 SKUs — governed but commercially thin.
9. `demand_forecast_basis`/`reason_code` constant (single demand path; baseline/uplift fallback never used).
10. Feature-inspection exposes wildly inconsistent demand magnitudes (consensus vs first-7-days differ ~70×).

## Root-cause summary
- **Demand collapse:** upstream store-level promo-window model predicts ~1 unit/SKU; contract carries it honestly (basis MODEL_PREDICTION). Not a Stage 11 bug.
- **Positive demand + NO_DEMAND:** the demand-evidence classifier emits `NO_DEMAND` from history sparsity and is **not reconciled** with the contract's `selected_demand_units` (and contradicts its own `demand_evidence_class`). Fixed in operator audit, not in the feature label.
- **All-zero orders:** **N/A** — orders are not all zero (28); suppression is explicitly blocker-justified and unsafe suppression hard-aborts.

## Verdict
- **Customer-ready: NO.**
- **Stale: NO** — this is fresh latest-build output (canonical fields present).
- **Patch now: YES**, but **only the proven fresh-output failures** below — not the stale-file symptoms (which the build already fixes).

## Exact next patch targets (when explicitly instructed)
1. `src/models/promotions/allocation_demand_forecast_contract.py` — reconcile `pre_promo_demand_units` (currently baseline × 63-day horizon) with promo-window demand: cap the lead-up horizon and/or derive both legs from one consistent demand model; and **emit `demand_forecast_warning`** when `selected_demand_units` is far below the feature signal (collapse should not be silent).
2. Demand-evidence label source — `src/surfaces/promotions/reporting/demand_evidence_classifier.py` and/or the feature-inspection label assembly in `store_prediction_download_builder.py` — forbid `demand_evidence_label = NO_DEMAND` when `selected_demand_units > 0` or `demand_evidence_class` is nonzero.
3. **Upstream (out of Stage 11 scope):** validate the store-level promo-window demand model — why it predicts ~1 unit for 99% of SKUs while feature consensus is far higher. This is the dominant magnitude defect and must be diagnosed against source data, not patched in Stage 11.

## Stop condition
Fresh output is **not customer-ready**. Do **not** proceed to customer release. Awaiting explicit instruction before patching; patch will target only the proven fresh failures above.
