from __future__ import annotations

"""Offer-text flag ft module."""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_base_math import ensure_text_series


def apply_ft_offer_text_flags(
    frame: pd.DataFrame,
    *,
    reference_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Add numeric encodings from the customer-offer text."""

    del reference_frame
    working = frame.copy()
    offer_text = ensure_text_series(working, "customer_offer").str.lower()
    working["feature_offer_text_percent_flag"] = (
        offer_text.str.contains("percent", regex=False)
        | offer_text.str.contains("%", regex=False)
    ).astype(float)
    working["feature_offer_text_amount_flag"] = (
        offer_text.str.contains("$", regex=False)
        | offer_text.str.contains("save", regex=False)
        | offer_text.str.contains("dollar", regex=False)
    ).astype(float)
    working["feature_offer_text_multi_buy_flag"] = (
        offer_text.str.contains("buy", regex=False)
        | offer_text.str.contains("2 for", regex=False)
        | offer_text.str.contains("3 for", regex=False)
        | offer_text.str.contains("multi", regex=False)
    ).astype(float)
    working["feature_offer_text_bonus_flag"] = (
        offer_text.str.contains("bonus", regex=False)
        | offer_text.str.contains("free", regex=False)
        | offer_text.str.contains("gift", regex=False)
    ).astype(float)
    return working
