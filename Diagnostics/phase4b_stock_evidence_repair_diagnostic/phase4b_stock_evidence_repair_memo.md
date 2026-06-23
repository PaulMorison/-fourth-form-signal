# Phase 4B Stock Evidence Repair Diagnostic

**Mode:** Read-only. No SQL, no training, no target-module patch.

## Artifacts reviewed

- policy-measurement-envfix-recent5k-20260522 (tmp/policy_measurement_envfix_recent5k_20260522/promotions_artifacts/training/datasets/policy-measurement-envfix-recent5k-20260522T000000Z/training_ready.parquet, n=5,004)
- policy-measurement-envfix-hard5k-20260522 (tmp/policy_measurement_envfix_hard5k_20260522/promotions_artifacts/training/datasets/policy-measurement-envfix-hard5k-20260522T000000Z/training_ready.parquet, n=6,419)
- `Diagnostics/phase4b_real_target_quality_review/`
- `src/models/promotions/sufficient_stock_demand_target.py`
- `src/state/promotions/targets/target_engineering.py`

**Rows analyzed:** 11,261

## Root cause

65.7% of rows are `INSUFFICIENT_EVIDENCE` because **repair rules require `demand_reference_units`**, but that column (and `baseline_expected_units`, `required_implied_units`, `stock_basis_units`) is **computed upstream during baseline window / target engineering and not persisted** in `training_ready.parquet`.

`target_underallocation_flag` **was** computed at dataset-build time using `demand_reference_units`, so 66% of rows carry underallocation=1. At sufficient-stock review time `demand_reference_units` is null, so:

1. Rows cannot qualify as `CLEAN_REALIZED_DEMAND` (underallocation blocks sufficient-stock observation).
2. All four repair paths fail the `demand_reference.notna()` gate.
3. Rows fall through to `UNREPAIRABLE_STOCK_CONSTRAINT`.

## Field availability summary

| Family | Present? | Notes |
|---|---|---|
| stock_basis_units | **Absent** | `total_stock_available` present 98.2% > 0 (usable fallback) |
| demand_reference_units | **Absent** | Primary repair blocker |
| baseline_expected_units | **Absent** | Available upstream via `apply_ft_baseline_windows` |
| post_14d_units | Present | 32.6% > 0 on insufficient rows |
| promo window / sales days | Present | `live_promo_window_days`, `promo_sales_day_count` |
| stockout flags | Present | `target_stockout_flag` on parquet; packet-level `actual_stockout_flag` absent |

## Scenario uplift (simulated)

                                      scenario  trainable_row_share  clean_share  repaired_share  insufficient_share  contaminated_share  uplift_trainable_vs_base
                      baseline_current_parquet             0.338069     0.338069        0.000000            0.657224            0.004707                  0.000000
           add_explicit_stock_basis_units_only             0.338069     0.338069        0.000000            0.657224            0.004707                  0.000000
add_upstream_baseline_demand_reference_columns             0.980108     0.338069        0.642039            0.015185            0.004707                  0.642039
     baseline_no_change_post14_already_present             0.338069     0.338069        0.000000            0.657224            0.004707                  0.000000
add_demand_reference_from_pre28_x_window_proxy             0.969274     0.338069        0.631205            0.026019            0.004707                  0.631205

## Decision

| Question | Answer |
|---|---|
| Patch target module next? | **NO** — enrich training parquet first |
| Enrich training data next? | **YES** — persist baseline/demand/stock_basis columns |
| Shadow training allowed? | **NO** |
| Report release? | **NO** |
| Recommended next step | Dataset assembly: merge `baseline_expected_units`, `demand_reference_units`, `required_implied_units`, `stock_basis_units` into training_ready.parquet; re-run Phase 4B.3 review |

## Minimum evidence before shadow training

- Trainable row share **≥ 50%** (currently 33.8%)
- Repaired cohort **> 0%** with governed ceilings (currently 0%)
- `demand_reference_units` non-null on **≥ 80%** of underallocated rows
- Do **not** use feature consensus as repair truth
