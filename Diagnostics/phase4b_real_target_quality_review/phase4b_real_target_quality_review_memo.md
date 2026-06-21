# Phase 4B Real Target Quality Review

**Mode:** Read-only review on local materialized training slices. No SQL, no training.

## Artifacts used

- policy-measurement-envfix-recent5k-20260522 (tmp/policy_measurement_envfix_recent5k_20260522/promotions_artifacts/training/datasets/policy-measurement-envfix-recent5k-20260522T000000Z/training_ready.parquet, n=5,004)
- policy-measurement-envfix-hard5k-20260522 (tmp/policy_measurement_envfix_hard5k_20260522/promotions_artifacts/training/datasets/policy-measurement-envfix-hard5k-20260522T000000Z/training_ready.parquet, n=6,419)

**Combined deduplicated rows:** 11,261

## Summary metrics

| Metric | Value |
|---|---|
| Clean share | 33.8% |
| Repaired share | 0.0% |
| Contaminated share | 0.5% |
| Insufficient/excluded share | 65.7% |
| Mean target weight per row | 0.3380 |
| Trainable row share (weight > 0) | 33.8% |
| Clean+repaired row share | 33.8% |
| Legacy vs sufficient mean diff | 0.0 |

## Findings

1. **Quality mix:**             target_quality_label  row_count    share
           INSUFFICIENT_EVIDENCE       7401 0.657224
           CLEAN_REALIZED_DEMAND       3807 0.338069
INVENTORY_INTEGRITY_CONTAMINATED         53 0.004707
2. **Repaired rows:** 0 — none on these slices; repair rules did not trigger
3. **Legacy vs sufficient:** On rows with both targets, sufficient equals legacy for clean rows; repairs would uplift only when stock-constrained repair rules fire.
4. **Supplier/category risk:** See `real_target_quality_by_supplier.csv` and department/category breakdown for elevated insufficient or contaminated rates.
5. **Shadow training viability:** **NO — clean+repaired coverage too low and/or no repaired cohort**

## Decision

| Question | Answer |
|---|---|
| Patch trainer next? | **NO — improve stock evidence / repair coverage first** |
| Retrain now? | **NO** |
| Replace live target? | **NO** |
| Report release? | **NO** |
| Recommended next step | Improve stock-basis / promo-window evidence fields so insufficient share drops; then re-run this review before shadow trainer mode. |

## Output files

- `real_target_quality_distribution.csv`
- `real_target_weight_distribution.csv`
- `real_target_quality_by_supplier.csv`
- `real_target_quality_by_department_or_category.csv`
- `real_target_quality_by_promotion_type.csv`
- `legacy_vs_sufficient_stock_target_distribution.csv`
- `repaired_target_rows_review.csv`
- `excluded_or_zero_weight_rows_review.csv`
- `target_warning_summary.csv`
