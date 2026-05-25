from __future__ import annotations

"""Window and commercial-basis columns shared by promotions ft modules."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_schema_helpers import (
    coerce_promotions_frame_types,
    resolve_allocation_basis_units,
    resolve_effective_cost_per_unit,
    resolve_promo_price_ex_gst,
    resolve_promo_window_days,
    resolve_regular_price_ex_gst,
)


def apply_ft_baseline_windows(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add shared baseline, stock, cost, and demand-reference columns."""

    del reference_frame
    working = coerce_promotions_frame_types(frame)
    promo_window_days = resolve_promo_window_days(working)
    baseline_daily_units = (
        ensure_numeric_series(working, "pre_28d_avg_daily_units").where(lambda values: values > 0.0)
        .fillna(ensure_numeric_series(working, "pre_56d_avg_daily_units").where(lambda values: values > 0.0))
        .fillna(ensure_numeric_series(working, "avg_daily_units").where(lambda values: values > 0.0))
        .fillna(ensure_numeric_series(working, "avg_1_wk_units").divide(7.0).where(lambda values: values > 0.0))
        .fillna(ensure_numeric_series(working, "avg_8_wk_unit_sales").divide(7.0))
        .fillna(0.0)
    )
    promo_price_ex_gst_effective = resolve_promo_price_ex_gst(working)
    baseline_expected_units = baseline_daily_units * promo_window_days
    required_implied_units = ensure_numeric_series(working, "required_implied_daily") * promo_window_days
    required_implied_units = required_implied_units.where(
        required_implied_units > 0.0,
        baseline_expected_units,
    )
    derived_columns = pd.DataFrame(
        {
            "baseline_daily_units": baseline_daily_units,
            "baseline_expected_units": baseline_expected_units,
            "promo_price_ex_gst_effective": promo_price_ex_gst_effective,
            "regular_price_ex_gst_effective": resolve_regular_price_ex_gst(working),
            "baseline_expected_sales_ex_gst": baseline_expected_units * promo_price_ex_gst_effective,
            "stock_basis_units": resolve_allocation_basis_units(working),
            "effective_cost_per_unit": resolve_effective_cost_per_unit(working),
            "required_implied_units": required_implied_units,
            "demand_reference_units": pd.concat(
                [baseline_expected_units, required_implied_units],
                axis=1,
            ).max(axis=1),
        },
        index=working.index,
    )
    base_columns = working.drop(columns=list(derived_columns.columns), errors="ignore")
    return pd.concat([base_columns, derived_columns], axis=1)
