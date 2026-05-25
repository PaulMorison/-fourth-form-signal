from __future__ import annotations

"""Catalogue-position ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


def apply_ft_catalogue_position(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add numeric catalogue-position strength flags."""

    del reference_frame
    working = frame.copy()
    catalogue_position = ensure_numeric_series(working, "catalogue_position")
    working["feature_catalogue_position_score"] = safe_ratio(
        pd.Series(1.0, index=working.index, dtype="float64"),
        catalogue_position.where(catalogue_position > 0.0),
    )
    working["feature_catalogue_top_quartile_flag"] = (
        (catalogue_position > 0.0) & (catalogue_position <= 4.0)
    ).astype(float)
    working["feature_catalogue_front_half_flag"] = (
        (catalogue_position > 0.0) & (catalogue_position <= 8.0)
    ).astype(float)
    return working
