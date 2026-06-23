# Phase 4B Sufficient-Stock Target Smoke

**Mode:** Read-only smoke on local artifacts. No training.

**Source:** completed_test_rows+training_ready+decision_surface_sample(n=516)

## Quality distribution

See `target_quality_distribution.csv`.

## Target units

See `target_units_distribution.csv`.

## Notes

- Output columns verified: realized_sales_units, stock_constrained_flag, stock_integrity_issue_flag, sufficient_stock_observed_flag, sufficient_stock_demand_units_target, target_quality_label, target_weight, target_repair_basis, target_warning
- Feature consensus recorded as diagnostic warning only when present.
- No model retrain performed.
