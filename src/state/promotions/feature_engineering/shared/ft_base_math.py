from __future__ import annotations

"""Small deterministic math helpers used across promotions ft modules."""

from typing import Iterable

import pandas as pd


def ensure_numeric_series(
    frame: pd.DataFrame,
    column_name: str,
    *,
    default: float = 0.0,
) -> pd.Series:
    """Return an index-aligned numeric series for the named column or default."""

    if column_name in frame.columns:
        return pd.to_numeric(frame[column_name], errors="coerce").fillna(default)
    return pd.Series(default, index=frame.index, dtype="float64")


def ensure_text_series(
    frame: pd.DataFrame,
    column_name: str,
    *,
    default: str = "",
) -> pd.Series:
    """Return an index-aligned text series for the named column or default."""

    if column_name in frame.columns:
        return frame[column_name].fillna(default).astype(str)
    return pd.Series(default, index=frame.index, dtype="object")


def first_non_null_series(
    frame: pd.DataFrame,
    columns: Iterable[str],
    *,
    positive_only: bool = False,
) -> pd.Series:
    """Return the first available numeric column value in preference order."""

    present_columns = [column_name for column_name in columns if column_name in frame.columns]
    if not present_columns:
        return pd.Series(0.0, index=frame.index, dtype="float64")
    candidate_frame = frame[present_columns].apply(pd.to_numeric, errors="coerce")
    if positive_only:
        candidate_frame = candidate_frame.where(candidate_frame > 0.0)
    return candidate_frame.bfill(axis=1).iloc[:, 0].fillna(0.0)


def bounded_score(distance: pd.Series) -> pd.Series:
    """Turn a non-negative distance or instability signal into a bounded score."""

    return 1.0 / (1.0 + distance.clip(lower=0.0))
