from __future__ import annotations

"""Days-cover ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


def apply_ft_days_cover(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add days-cover pressure relative to the live promo window."""

    del reference_frame
    working = frame.copy()
    working["feature_days_cover_pressure_ratio"] = safe_ratio(
        ensure_numeric_series(working, "tot_days_cover"),
        ensure_numeric_series(working, "live_promo_window_days").where(
            lambda values: values > 0.0,
            ensure_numeric_series(working, "promo_days"),
        ),
    )
    return working
