from __future__ import annotations

"""Post-promo-followthrough target ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series


def apply_ft_target_post_promo_followthrough(frame: pd.DataFrame) -> pd.DataFrame:
    """Add post-promo follow-through targets."""

    working = frame.copy()
    working["target_post_promo_followthrough_units"] = ensure_numeric_series(working, "post_14d_units")
    working["target_post_promo_followthrough_sales_ex_gst"] = ensure_numeric_series(
        working,
        "post_14d_sales_ex_gst",
    )
    return working
