from __future__ import annotations

"""Chronological train/validation/test splitting for promotions datasets."""

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class PromotionTimeSplit:
    train_mask: pd.Series
    validation_mask: pd.Series
    test_mask: pd.Series
    train_last_date: str
    validation_last_date: str
    test_last_date: str


class PromotionTimeSplitter:
    """Hold out the most recent promotions instead of using random splits."""

    def split(
        self,
        frame: pd.DataFrame,
        *,
        date_column: str = "promotion_start_date_date",
        validation_fraction: float = 0.15,
        test_fraction: float = 0.15,
    ) -> PromotionTimeSplit:
        """Create chronological masks from sorted unique promotion dates."""

        ordered_dates = sorted(
            pd.to_datetime(frame[date_column], errors="coerce").dropna().unique().tolist()
        )
        if len(ordered_dates) < 3:
            raise ValueError("At least three unique promotion dates are required for time-aware splits.")
        validation_count = max(1, int(round(len(ordered_dates) * validation_fraction)))
        test_count = max(1, int(round(len(ordered_dates) * test_fraction)))
        if validation_count + test_count >= len(ordered_dates):
            validation_count = 1
            test_count = 1
        train_dates = ordered_dates[: len(ordered_dates) - validation_count - test_count]
        validation_dates = ordered_dates[len(train_dates) : len(train_dates) + validation_count]
        test_dates = ordered_dates[len(train_dates) + validation_count :]
        promotion_dates = pd.to_datetime(frame[date_column], errors="coerce")
        return PromotionTimeSplit(
            train_mask=promotion_dates.isin(train_dates),
            validation_mask=promotion_dates.isin(validation_dates),
            test_mask=promotion_dates.isin(test_dates),
            train_last_date=str(pd.Timestamp(train_dates[-1]).date()),
            validation_last_date=str(pd.Timestamp(validation_dates[-1]).date()),
            test_last_date=str(pd.Timestamp(test_dates[-1]).date()),
        )
