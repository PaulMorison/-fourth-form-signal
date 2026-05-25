from __future__ import annotations

"""Chronological cohort-history-only backtesting for promotions archetypes."""

from dataclasses import dataclass
from datetime import date
import math

import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, precision_score, recall_score

from models.promotions.cohorts.cohort_similarity import (
    CohortSimilarityConfig,
    PromotionCohortSimilarity,
)
from state.promotions.cohorts import PromotionCohortAssigner
from state.promotions.cohorts.cohort_history_builder import PromotionCohortHistoryBuilder
from state.promotions.cohorts.cohort_validators import (
    filter_completed_rows_as_of,
    filter_rows_before_cutoff,
    validate_non_empty_cohort_frame,
)


@dataclass(frozen=True)
class PromotionCohortBacktestResult:
    row_matches_frame: pd.DataFrame
    metrics: dict[str, object]


class PromotionCohortBacktester:
    """Simulate cohort-history-only predictions on later completed promotions."""

    def __init__(
        self,
        *,
        cohort_assigner: PromotionCohortAssigner | None = None,
        history_builder: PromotionCohortHistoryBuilder | None = None,
        similarity: PromotionCohortSimilarity | None = None,
    ) -> None:
        self._cohort_assigner = cohort_assigner or PromotionCohortAssigner()
        self._history_builder = history_builder or PromotionCohortHistoryBuilder()
        self._similarity = similarity or PromotionCohortSimilarity()

    def backtest(
        self,
        frame: pd.DataFrame,
        *,
        as_of_date: date | str | pd.Timestamp,
        minimum_sample_size: int = 3,
        similarity_threshold: float = 0.55,
    ) -> PromotionCohortBacktestResult:
        """Score later rows using only cohort history visible before each cutoff."""

        eligible_rows = filter_completed_rows_as_of(frame, as_of_date=as_of_date)
        validate_non_empty_cohort_frame(eligible_rows, context="Promotion cohort backtest")
        assigned_rows = self._cohort_assigner.assign(eligible_rows).frame
        evaluation_dates = sorted(
            pd.to_datetime(assigned_rows["promotion_start_date_date"], errors="coerce")
            .dropna()
            .unique()
            .tolist()
        )
        if len(evaluation_dates) < 2:
            raise ValueError("Promotion cohort backtest requires at least two unique promotion start dates.")
        scored_slices: list[pd.DataFrame] = []
        similarity_config = CohortSimilarityConfig(
            minimum_sample_size=minimum_sample_size,
            similarity_threshold=similarity_threshold,
        )
        for evaluation_date in evaluation_dates[1:]:
            evaluation_rows = assigned_rows.loc[
                pd.to_datetime(assigned_rows["promotion_start_date_date"], errors="coerce")
                == pd.Timestamp(evaluation_date)
            ].copy()
            history_source = filter_rows_before_cutoff(
                assigned_rows,
                cutoff_date=evaluation_date,
                date_column="promotional_end_date_date",
            )
            if evaluation_rows.empty or history_source.empty:
                continue
            history_result = self._history_builder.build(
                history_source,
                as_of_date=evaluation_date,
                minimum_sample_size=minimum_sample_size,
            )
            match_frame = self._similarity.score(
                evaluation_rows,
                history_result.archetype_history_frame,
                config=similarity_config,
            )
            scored_slice = evaluation_rows.merge(match_frame, on="promotion_row_key", how="left")
            scored_slice["backtest_cutoff_date"] = str(pd.Timestamp(evaluation_date).date())
            scored_slice["predicted_overallocation_flag_from_cohort"] = (
                scored_slice["nearest_archetype_expected_overallocation_rate"].fillna(0.0) >= 0.5
            ).astype(int)
            scored_slice["predicted_underallocation_flag_from_cohort"] = (
                scored_slice["nearest_archetype_expected_underallocation_rate"].fillna(0.0) >= 0.5
            ).astype(int)
            scored_slice["predicted_stockout_flag_from_cohort"] = (
                scored_slice["nearest_archetype_expected_stockout_rate"].fillna(0.0) >= 0.5
            ).astype(int)
            scored_slices.append(scored_slice)
        if not scored_slices:
            raise ValueError("Promotion cohort backtest could not score any evaluation rows.")
        row_matches_frame = pd.concat(scored_slices, axis=0, ignore_index=True)
        metrics = self._build_metrics(
            row_matches_frame,
            minimum_sample_size=minimum_sample_size,
            similarity_threshold=similarity_threshold,
        )
        return PromotionCohortBacktestResult(row_matches_frame=row_matches_frame, metrics=metrics)

    def _build_metrics(
        self,
        frame: pd.DataFrame,
        *,
        minimum_sample_size: int,
        similarity_threshold: float,
    ) -> dict[str, object]:
        covered_rows = frame.loc[frame["cohort_coverage_flag"] == 1].copy()
        return {
            "row_count": int(len(frame.index)),
            "covered_row_count": int(len(covered_rows.index)),
            "cohort_coverage_rate": float(frame["cohort_coverage_flag"].mean()),
            "sparse_cohort_failure_rate": float(frame["sparse_cohort_flag"].mean()),
            "minimum_sample_size": int(minimum_sample_size),
            "similarity_threshold": float(similarity_threshold),
            "regression": {
                "units": self._regression_metrics(
                    covered_rows,
                    actual_column="target_actual_units_sold",
                    predicted_column="nearest_archetype_expected_units",
                ),
                "sales_ex_gst": self._regression_metrics(
                    covered_rows,
                    actual_column="target_actual_sales_ex_gst",
                    predicted_column="nearest_archetype_expected_sales_ex_gst",
                ),
                "gross_profit": self._regression_metrics(
                    covered_rows,
                    actual_column="target_actual_gross_profit_dollars",
                    predicted_column="nearest_archetype_expected_gp",
                ),
                "sell_through": self._regression_metrics(
                    covered_rows,
                    actual_column="target_sell_through_pct",
                    predicted_column="nearest_archetype_expected_sell_through",
                ),
                "leftover": self._regression_metrics(
                    covered_rows,
                    actual_column="target_leftover_stock_pct",
                    predicted_column="nearest_archetype_expected_leftover",
                ),
            },
            "classification": {
                "overallocation": self._classification_metrics(
                    covered_rows,
                    actual_column="target_overallocation_flag",
                    predicted_column="predicted_overallocation_flag_from_cohort",
                ),
                "underallocation": self._classification_metrics(
                    covered_rows,
                    actual_column="target_underallocation_flag",
                    predicted_column="predicted_underallocation_flag_from_cohort",
                ),
                "stockout": self._classification_metrics(
                    covered_rows,
                    actual_column="target_stockout_flag",
                    predicted_column="predicted_stockout_flag_from_cohort",
                ),
            },
        }

    def _regression_metrics(
        self,
        frame: pd.DataFrame,
        *,
        actual_column: str,
        predicted_column: str,
    ) -> dict[str, float | int]:
        valid_rows = frame[[actual_column, predicted_column]].dropna()
        if valid_rows.empty:
            return {"row_count": 0, "mae": 0.0, "rmse": 0.0}
        return {
            "row_count": int(len(valid_rows.index)),
            "mae": float(mean_absolute_error(valid_rows[actual_column], valid_rows[predicted_column])),
            "rmse": float(
                math.sqrt(
                    mean_squared_error(
                        valid_rows[actual_column],
                        valid_rows[predicted_column],
                    )
                )
            ),
        }

    def _classification_metrics(
        self,
        frame: pd.DataFrame,
        *,
        actual_column: str,
        predicted_column: str,
    ) -> dict[str, float | int]:
        valid_rows = frame[[actual_column, predicted_column]].dropna()
        if valid_rows.empty:
            return {"row_count": 0, "precision": 0.0, "recall": 0.0}
        return {
            "row_count": int(len(valid_rows.index)),
            "precision": float(
                precision_score(valid_rows[actual_column], valid_rows[predicted_column], zero_division=0)
            ),
            "recall": float(
                recall_score(valid_rows[actual_column], valid_rows[predicted_column], zero_division=0)
            ),
        }