from __future__ import annotations

"""Baseline and window helpers for promotions target and feature engineering.

Canon ownership:
- Turns extracted pre-promo demand observations into explicit baseline and
  demand-reference columns reused by both training-target engineering and
  future scoring feature generation.
- Keeps window semantics explicit: 56-day pre-promo baseline, 28-day short
  baseline, 7-day immediate baseline, and 14-day post-promo follow-through.
- Does not decide labels, model thresholds, or report output classes.
"""

import pandas as pd

from state.promotions.feature_engineering.shared.ft_group_windows import apply_ft_baseline_windows


def add_baseline_window_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Compatibility wrapper around the shared baseline-window ft module."""

    return apply_ft_baseline_windows(frame)
