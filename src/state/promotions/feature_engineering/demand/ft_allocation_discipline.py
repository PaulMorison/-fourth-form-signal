from __future__ import annotations

"""Probability-backed allocation discipline ft module."""

import numpy as np
import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series


ALLOCATION_DISCIPLINE_FEATURE_COLUMNS: tuple[str, ...] = (
    "feature_allocation_vs_probability_expected_units_ratio",
    "feature_allocated_units_minus_probability_expected_units",
    "feature_probability_expected_excess_units",
    "feature_probability_expected_excess_units_pct",
    "feature_probability_expected_sell_through_pct",
    "feature_probability_excess_capital_at_risk",
    "feature_probability_allocation_discipline_score",
    "feature_allocation_vs_uplift_supported_units_ratio",
    "feature_allocated_units_minus_uplift_supported_units",
    "feature_uplift_supported_excess_units",
    "feature_uplift_supported_excess_units_pct",
    "feature_uplift_supported_sell_through_pct",
    "feature_uplift_supported_excess_capital_at_risk",
    "feature_uplift_allocation_discipline_score",
    "feature_allocation_vs_baseline_gap_units",
    "feature_allocation_vs_uplift_supported_gap_units",
    "feature_allocation_vs_supported_total_gap_units",
    "feature_supported_sell_through_score",
    "feature_discount_evidence_strength_score",
    "feature_allocation_risk_over_uplift_score",
    "feature_launch_stock_support_score",
    "feature_total_window_pressure_vs_launch_support_conflict_score",
)


def apply_ft_allocation_discipline(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Compare allocation to model-use probability expected demand."""

    del reference_frame
    working = frame.copy()
    stock_basis = ensure_numeric_series(working, "stock_basis_units")
    unit_cost = ensure_numeric_series(working, "effective_cost_per_unit")
    baseline_expected_units = _first_present_numeric_series(
        working,
        ("feature_expected_baseline_units_promo_window", "feature_baseline_units_expected_promo_window"),
    )
    expected_units = _optional_numeric_series(working, "feature_probability_expected_units_consensus")
    demand_confidence = _optional_numeric_series(working, "feature_probability_demand_confidence_score").clip(
        lower=0.0,
        upper=1.0,
    )
    uplift_supported_units = _first_present_numeric_series(
        working,
        ("feature_expected_incremental_uplift_units_same_discount", "feature_probability_uplift_supported_units"),
    )
    uplift_upper_units = _first_present_numeric_series(
        working,
        ("feature_expected_incremental_uplift_units_same_discount", "feature_probability_uplift_upper_units"),
    )
    uplift_confidence = _first_present_numeric_series(
        working,
        ("feature_uplift_confidence_score", "feature_probability_uplift_confidence"),
    ).clip(
        lower=0.0,
        upper=1.0,
    )
    elasticity_confidence = _optional_numeric_series(working, "feature_discount_elasticity_confidence_score").clip(
        lower=0.0,
        upper=1.0,
    )
    same_discount_history_available = _optional_numeric_series(
        working,
        "feature_same_discount_history_available_flag",
    ).clip(lower=0.0, upper=1.0)
    same_discount_event_count = _first_present_numeric_series(
        working,
        ("feature_same_discount_prior_event_count", "feature_uplift_support_event_count"),
    )
    window_blend_conflict = _first_present_numeric_series(
        working,
        (
            "feature_total_window_pressure_vs_launch_support_conflict_score",
            "feature_window_blend_conflict_score",
        ),
    ).clip(
        lower=0.0,
        upper=1.0,
    )
    supported_total_units = _first_present_numeric_series(
        working,
        ("feature_expected_total_units_from_baseline_plus_uplift", "feature_probability_expected_units_consensus"),
    )
    launch_supported_units = _first_present_numeric_series(
        working,
        ("feature_expected_total_units_first_7_days", "feature_expected_baseline_units_first_7_days"),
    )
    model_use_flag = _optional_numeric_series(working, "feature_probability_model_use_flag")
    supported_probability = expected_units.gt(0.0) & model_use_flag.eq(1.0)
    supported_expected_units = expected_units.where(supported_probability)
    uplift_supported_total_units = (baseline_expected_units + uplift_supported_units).where(
        uplift_supported_units.notna(),
        supported_total_units.where(supported_total_units.notna(), supported_expected_units),
    )
    uplift_supported_upper_units = (baseline_expected_units + uplift_upper_units).where(
        uplift_upper_units.notna(),
        uplift_supported_total_units,
    )
    supported_uplift_probability = uplift_supported_total_units.gt(0.0) & (
        model_use_flag.eq(1.0) | same_discount_history_available.eq(1.0)
    )
    allocation_support_available = model_use_flag.eq(1.0) | same_discount_history_available.eq(1.0)
    uplift_supported_total_units = uplift_supported_total_units.where(supported_uplift_probability)
    uplift_supported_upper_units = uplift_supported_upper_units.where(supported_uplift_probability)
    discount_evidence_strength_score = _rowwise_nanmean(
        [
            same_discount_history_available,
            (same_discount_event_count / 4.0).clip(lower=0.0, upper=1.0),
            uplift_confidence,
            elasticity_confidence,
        ]
    ).fillna(0.0).clip(lower=0.0, upper=1.0)

    allocation_gap = stock_basis - supported_expected_units
    expected_excess_units = allocation_gap.clip(lower=0.0)
    stock_excess_share = _nan_ratio(expected_excess_units, stock_basis).clip(lower=0.0, upper=1.0)
    uplift_allocation_gap = stock_basis - uplift_supported_total_units
    uplift_supported_excess_units = (stock_basis - uplift_supported_upper_units).clip(lower=0.0)
    uplift_stock_excess_share = _nan_ratio(uplift_supported_excess_units, stock_basis).clip(lower=0.0, upper=1.0)
    allocation_vs_supported_total_gap_units = stock_basis - uplift_supported_total_units
    supported_sell_through_score = _nan_ratio(uplift_supported_total_units, stock_basis).clip(lower=0.0, upper=1.0)
    launch_stock_support_score = _nan_ratio(launch_supported_units, stock_basis).clip(lower=0.0, upper=1.0)
    total_window_pressure = _nan_ratio(uplift_supported_total_units, stock_basis).clip(lower=0.0, upper=20.0)
    legacy_uplift_allocation_discipline_score = (
        uplift_stock_excess_share
        * uplift_confidence.where(supported_uplift_probability, demand_confidence)
        * (1.0 - window_blend_conflict.where(supported_uplift_probability, 0.0))
    ).clip(lower=0.0, upper=1.0)
    total_window_vs_launch_conflict = _rowwise_nanmean(
        [
            (total_window_pressure - launch_stock_support_score).clip(lower=0.0, upper=1.0),
            (1.0 - uplift_confidence),
            (1.0 - discount_evidence_strength_score),
        ]
    ).clip(lower=0.0, upper=1.0)
    allocation_risk_over_uplift_score = _rowwise_nanmean(
        [
            _nan_ratio(
                allocation_vs_supported_total_gap_units.clip(lower=0.0),
                stock_basis,
            ).clip(lower=0.0, upper=1.0),
            (1.0 - discount_evidence_strength_score),
            (1.0 - launch_stock_support_score),
            total_window_vs_launch_conflict,
        ]
    ).clip(lower=0.0, upper=1.0)
    uplift_allocation_discipline_score = legacy_uplift_allocation_discipline_score
    legacy_allocation_discipline_score = (
        stock_excess_share * demand_confidence.where(supported_probability)
    ).clip(lower=0.0, upper=1.0)

    derived_columns = pd.DataFrame(
        {
            "feature_allocation_vs_probability_expected_units_ratio": _nan_ratio(
                stock_basis,
                supported_expected_units,
            ).clip(lower=0.0, upper=20.0),
            "feature_allocated_units_minus_probability_expected_units": allocation_gap,
            "feature_probability_expected_excess_units": expected_excess_units,
            "feature_probability_expected_excess_units_pct": _nan_ratio(
                expected_excess_units,
                supported_expected_units,
            ).clip(lower=0.0, upper=20.0),
            "feature_probability_expected_sell_through_pct": _nan_ratio(
                supported_expected_units,
                stock_basis,
            ).clip(lower=0.0, upper=1.0),
            "feature_probability_excess_capital_at_risk": expected_excess_units * unit_cost,
            "feature_probability_allocation_discipline_score": uplift_allocation_discipline_score.where(
                supported_uplift_probability & uplift_supported_units.notna(),
                legacy_allocation_discipline_score,
            ),
            "feature_allocation_vs_uplift_supported_units_ratio": _nan_ratio(
                stock_basis,
                uplift_supported_total_units,
            ).clip(lower=0.0, upper=20.0),
            "feature_allocated_units_minus_uplift_supported_units": uplift_allocation_gap,
            "feature_uplift_supported_excess_units": uplift_supported_excess_units,
            "feature_uplift_supported_excess_units_pct": _nan_ratio(
                uplift_supported_excess_units,
                uplift_supported_upper_units,
            ).clip(lower=0.0, upper=20.0),
            "feature_uplift_supported_sell_through_pct": supported_sell_through_score,
            "feature_uplift_supported_excess_capital_at_risk": uplift_supported_excess_units * unit_cost,
            "feature_uplift_allocation_discipline_score": uplift_allocation_discipline_score,
            "feature_allocation_vs_baseline_gap_units": (stock_basis - baseline_expected_units).where(
                allocation_support_available,
            ),
            "feature_allocation_vs_uplift_supported_gap_units": (stock_basis - uplift_supported_units).where(
                allocation_support_available,
            ),
            "feature_allocation_vs_supported_total_gap_units": allocation_vs_supported_total_gap_units.where(
                allocation_support_available,
            ),
            "feature_supported_sell_through_score": supported_sell_through_score.where(allocation_support_available),
            "feature_discount_evidence_strength_score": discount_evidence_strength_score.where(
                allocation_support_available,
            ),
            "feature_allocation_risk_over_uplift_score": allocation_risk_over_uplift_score.where(
                allocation_support_available,
            ),
            "feature_launch_stock_support_score": launch_stock_support_score.where(allocation_support_available),
            "feature_total_window_pressure_vs_launch_support_conflict_score": total_window_vs_launch_conflict.where(
                allocation_support_available,
            ),
        },
        index=working.index,
    )
    base_columns = working.drop(columns=list(derived_columns.columns), errors="ignore")
    return pd.concat([base_columns, derived_columns], axis=1)


def _optional_numeric_series(frame: pd.DataFrame, column_name: str) -> pd.Series:
    if column_name not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column_name], errors="coerce")


def _first_present_numeric_series(frame: pd.DataFrame, column_names: tuple[str, ...]) -> pd.Series:
    present_columns = [column_name for column_name in column_names if column_name in frame.columns]
    if not present_columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    candidate_frame = frame[present_columns].apply(pd.to_numeric, errors="coerce")
    return candidate_frame.bfill(axis=1).iloc[:, 0]


def _nan_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denominator_clean = denominator.where(denominator.ne(0.0))
    return numerator.divide(denominator_clean).replace([np.inf, -np.inf], np.nan)


def _rowwise_nanmean(series_list: list[pd.Series]) -> pd.Series:
    combined = pd.concat([pd.to_numeric(series, errors="coerce") for series in series_list], axis=1)
    return combined.mean(axis=1, skipna=True).astype("float64")