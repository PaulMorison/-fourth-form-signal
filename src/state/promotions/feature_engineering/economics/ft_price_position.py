from __future__ import annotations

"""Price-position ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series
from state.promotions.feature_engineering.shared.ft_safe_division import safe_ratio


def apply_ft_price_position(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add the promo price position versus the regular price."""

    del reference_frame
    working = frame.copy()
    working["feature_promo_price_ratio_vs_normal"] = safe_ratio(
        ensure_numeric_series(working, "promo_price_ex_gst_effective"),
        ensure_numeric_series(working, "regular_price_ex_gst_effective"),
    )
    return working
