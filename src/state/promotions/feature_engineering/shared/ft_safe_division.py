from __future__ import annotations

"""Guarded division helpers for promotions features and targets."""

import numpy as np
import pandas as pd


def safe_divide(
    numerator: pd.Series,
    denominator: pd.Series,
    *,
    default: float = 0.0,
) -> pd.Series:
    """Return a ratio with zero and infinity collapsed to a stable default."""

    denominator_clean = denominator.replace(0.0, np.nan)
    return numerator.divide(denominator_clean).replace([np.inf, -np.inf], np.nan).fillna(default)


def safe_ratio(
    numerator: pd.Series,
    denominator: pd.Series,
    *,
    default: float = 0.0,
) -> pd.Series:
    """Alias kept for call sites that prefer ratio-oriented naming."""

    return safe_divide(numerator, denominator, default=default)
