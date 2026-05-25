from __future__ import annotations

"""Historical-allocation target family for completed promotions."""

import pandas as pd


HISTORICAL_ALLOCATION_TARGET_COLUMNS: tuple[str, ...] = (
    "target_historical_allocation_units",
    "target_historical_replay_excess_units",
    "target_historical_replay_excess_capital",
    "target_historical_overallocation_flag",
    "target_historical_allocation_missing_flag",
    "target_historical_realised_promo_units_missing_flag",
    "target_historical_unit_cost_missing_flag",
    "target_historical_allocation_target_valid_flag",
    "target_historical_allocation_exclusion_reason",
    "target_historical_allocation_source_column",
    "target_historical_realised_units_source_column",
    "target_historical_unit_cost_source_column",
)

HISTORICAL_ALLOCATION_SOURCE_COLUMNS: tuple[str, ...] = (
    "pl_allocation_qty",
    "pl_allocated",
    "store_adjusted_qty",
    "total_units_commited",
)
HISTORICAL_REALISED_PROMO_UNITS_SOURCE_COLUMNS: tuple[str, ...] = (
    "actual_units_sold_promo",
    "actual_units_sold",
)
HISTORICAL_UNIT_COST_SOURCE_COLUMNS: tuple[str, ...] = (
    "effective_cost_per_unit",
    "promo_effective_cost",
    "promo_cost_price",
    "last_received_cost",
)

_HISTORICAL_TARGET_ELIGIBLE = "eligible"
_HISTORICAL_TARGET_MISSING_ALLOCATION = "missing_historical_allocation_evidence"
_HISTORICAL_TARGET_MISSING_REALISED = "missing_realised_promo_evidence"
_HISTORICAL_TARGET_MISSING_COST = "missing_historical_unit_cost_evidence"
_HISTORICAL_TARGET_MULTIPLE_MISSING = "multiple_missing_historical_target_inputs"


class HistoricalAllocationTargetEvidenceError(ValueError):
    """Raised when the historical allocation target family has no explicit source evidence."""


def apply_ft_target_historical_allocation(frame: pd.DataFrame) -> pd.DataFrame:
    """Add the governed historical-allocation target family without stock-basis fallback."""

    working = frame.copy()
    allocation_units, allocation_source = _first_present_nonnegative_numeric_series(
        working,
        HISTORICAL_ALLOCATION_SOURCE_COLUMNS,
        evidence_name="historical allocation units",
    )
    realised_units, realised_source = _first_present_nonnegative_numeric_series(
        working,
        HISTORICAL_REALISED_PROMO_UNITS_SOURCE_COLUMNS,
        evidence_name="realised promo units",
    )
    unit_cost, unit_cost_source = _first_present_nonnegative_numeric_series(
        working,
        HISTORICAL_UNIT_COST_SOURCE_COLUMNS,
        evidence_name="historical unit cost",
    )

    missing_allocation = allocation_units.isna()
    missing_realised = realised_units.isna()
    missing_cost = unit_cost.isna() | unit_cost.le(0.0)
    valid_mask = ~(missing_allocation | missing_realised | missing_cost)

    excess_units = (allocation_units - realised_units).clip(lower=0.0).where(valid_mask)
    excess_capital = (excess_units * unit_cost).where(valid_mask)
    overallocation_flag = allocation_units.gt(realised_units).where(valid_mask)

    missing_count = (
        missing_allocation.astype(int)
        + missing_realised.astype(int)
        + missing_cost.astype(int)
    )
    exclusion_reason = pd.Series(_HISTORICAL_TARGET_ELIGIBLE, index=working.index, dtype="object")
    exclusion_reason = exclusion_reason.mask(missing_allocation, _HISTORICAL_TARGET_MISSING_ALLOCATION)
    exclusion_reason = exclusion_reason.mask(~missing_allocation & missing_realised, _HISTORICAL_TARGET_MISSING_REALISED)
    exclusion_reason = exclusion_reason.mask(~missing_allocation & ~missing_realised & missing_cost, _HISTORICAL_TARGET_MISSING_COST)
    exclusion_reason = exclusion_reason.mask(missing_count.gt(1), _HISTORICAL_TARGET_MULTIPLE_MISSING)

    working["target_historical_allocation_units"] = allocation_units.where(valid_mask)
    working["target_historical_replay_excess_units"] = excess_units
    working["target_historical_replay_excess_capital"] = excess_capital
    working["target_historical_overallocation_flag"] = overallocation_flag.astype("boolean").astype("Int64")
    working["target_historical_allocation_missing_flag"] = missing_allocation.astype(int)
    working["target_historical_realised_promo_units_missing_flag"] = missing_realised.astype(int)
    working["target_historical_unit_cost_missing_flag"] = missing_cost.astype(int)
    working["target_historical_allocation_target_valid_flag"] = valid_mask.astype(int)
    working["target_historical_allocation_exclusion_reason"] = exclusion_reason
    working["target_historical_allocation_source_column"] = allocation_source
    working["target_historical_realised_units_source_column"] = realised_source
    working["target_historical_unit_cost_source_column"] = unit_cost_source
    return working


def _first_present_nonnegative_numeric_series(
    frame: pd.DataFrame,
    candidate_columns: tuple[str, ...],
    *,
    evidence_name: str,
) -> tuple[pd.Series, str]:
    present_columns = [column_name for column_name in candidate_columns if column_name in frame.columns]
    if not present_columns:
        raise HistoricalAllocationTargetEvidenceError(
            f"Cannot build historical allocation target family: missing explicit {evidence_name} source column. "
            f"Expected one of: {', '.join(candidate_columns)}"
        )
    result = pd.Series(pd.NA, index=frame.index, dtype="Float64")
    source_column = present_columns[0]
    for column_name in present_columns:
        candidate = pd.to_numeric(frame[column_name], errors="coerce").astype("Float64")
        candidate = candidate.where(candidate.ge(0.0))
        result = result.fillna(candidate)
    return result, source_column