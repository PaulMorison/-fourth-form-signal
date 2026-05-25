from __future__ import annotations

"""Validation helpers for promotions cohort inputs and history windows."""

from datetime import date

import pandas as pd

from state.promotions.cohorts.cohort_frame_schema import (
    COHORT_REQUIRED_COLUMNS,
    missing_required_cohort_columns,
)


def validate_required_cohort_columns(
    frame: pd.DataFrame,
    *,
    required_columns: tuple[str, ...] = COHORT_REQUIRED_COLUMNS,
    context: str,
) -> None:
    """Fail loudly when a cohort operation receives an incomplete frame."""

    missing_columns = missing_required_cohort_columns(frame, required_columns=required_columns)
    if missing_columns:
        raise ValueError(
            f"{context} requires columns: {', '.join(missing_columns)}"
        )


def validate_cohort_date_columns(frame: pd.DataFrame) -> None:
    """Ensure the cohort layer has valid start and end dates for every row."""

    missing_date_columns = [
        column_name
        for column_name in ("promotion_start_date_date", "promotional_end_date_date")
        if column_name not in frame.columns
    ]
    if missing_date_columns:
        raise ValueError(
            "Cohort date validation requires columns: " + ", ".join(missing_date_columns)
        )
    start_dates = pd.to_datetime(frame["promotion_start_date_date"], errors="coerce")
    end_dates = pd.to_datetime(frame["promotional_end_date_date"], errors="coerce")
    if start_dates.isna().any() or end_dates.isna().any():
        raise ValueError("Cohort inputs require non-null promotion start and end dates.")


def filter_completed_rows_as_of(
    frame: pd.DataFrame,
    *,
    as_of_date: date | str | pd.Timestamp,
) -> pd.DataFrame:
    """Return only rows whose promotion end date is strictly before the cutoff."""

    cutoff = pd.Timestamp(as_of_date).normalize()
    completed_mask = pd.to_datetime(frame["promotional_end_date_date"], errors="coerce") < cutoff
    return frame.loc[completed_mask].copy()


def filter_rows_before_cutoff(
    frame: pd.DataFrame,
    *,
    cutoff_date: date | str | pd.Timestamp,
    date_column: str,
) -> pd.DataFrame:
    """Return only rows whose selected date is strictly before the cutoff."""

    cutoff = pd.Timestamp(cutoff_date).normalize()
    comparison_dates = pd.to_datetime(frame[date_column], errors="coerce")
    return frame.loc[comparison_dates < cutoff].copy()


def validate_non_empty_cohort_frame(frame: pd.DataFrame, *, context: str) -> None:
    """Fail loudly when a cohort step has no rows to operate on."""

    if frame.empty:
        raise ValueError(f"{context} requires at least one eligible row.")