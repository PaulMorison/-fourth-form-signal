# Phase 4B Training-Ready Enrichment Review

**Mode:** Local smoke rebuild + read-only review. No SQL, no training, no retrain.

## Patch applied

Dataset assembly now merges repair-evidence and parallel sufficient-stock target columns from the engineered target frame into `training_ready.parquet`.

## Artifacts used

- policy-measurement-envfix-recent5k-20260522 (tmp/phase4b_training_ready_enrichment_smoke/promotions_artifacts/training/datasets/phase4b-enriched-policy-measurement-envfix-recent5k-20260522/training_ready.parquet, n=5,004)
- policy-measurement-envfix-hard5k-20260522 (tmp/phase4b_training_ready_enrichment_smoke/promotions_artifacts/training/datasets/phase4b-enriched-policy-measurement-envfix-hard5k-20260522/training_ready.parquet, n=6,419)

**Combined deduplicated rows:** 11,261

## Before vs after (target quality)

| Metric | Before (4B.3) | After (4B.5 enriched) |
|---|---|---|
| Clean share | 33.8% | 33.8% |
| Repaired share | 0.0% | 64.2% |
| Insufficient share | 65.7% | 1.5% |
| Trainable share | 33.8% | 98.0% |
| demand_reference on underallocated rows | 0% (absent) | 100.0% |

## Repair evidence field presence

All four required fields present in enriched parquet: **True**

## Decision

| Question | Answer |
|---|---|
| Retrain now? | **NO** — review enriched distribution first |
| Replace live target? | **NO** — `target_actual_units_sold` remains live |
| Shadow training allowed? | **YES** |
| Report release? | **NO** |
| Recommended next step | Review enriched target-quality distribution; if gates pass, proceed to shadow trainer evaluation (not retrain) |

## Output files

- `training_ready_field_presence.csv`
- `repair_evidence_field_coverage.csv`
- `target_quality_distribution_after_enrichment.csv`
- `target_weight_distribution_after_enrichment.csv`
- `repairable_rows_after_enrichment.csv`
- `legacy_vs_sufficient_stock_target_after_enrichment.csv`
