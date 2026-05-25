from __future__ import annotations

"""Historical cohort summary construction for promotions backtesting and reporting."""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from state.promotions.cohorts.archetype_signature_builder import ARCHETYPE_REGIME_COLUMNS
from state.promotions.cohorts.archetype_signature_builder import PRIMARY_SIGNATURE_COLUMNS
from state.promotions.cohorts.archetype_signature_builder import SECONDARY_SIGNATURE_COLUMNS
from state.promotions.cohorts.cohort_assigner import PromotionCohortAssigner
from state.promotions.cohorts.cohort_keys import COHORT_KEY_COLUMNS
from state.promotions.cohorts.cohort_metrics import (
    add_prefixed_trailing_metrics,
    aggregate_cohort_metrics,
)
from state.promotions.cohorts.cohort_validators import (
    filter_completed_rows_as_of,
    validate_non_empty_cohort_frame,
)


_ARCHETYPE_FAMILIES = {
    "cohort_key_archetype_primary": "primary",
    "cohort_key_archetype_secondary": "secondary",
}


@dataclass(frozen=True)
class PromotionCohortHistoryResult:
    assigned_frame: pd.DataFrame
    historical_frame: pd.DataFrame
    summary_frame: pd.DataFrame
    archetype_history_frame: pd.DataFrame
    as_of_date: str
    minimum_sample_size: int


class PromotionCohortHistoryBuilder:
    """Build leakage-safe historical cohort summaries from completed promotions."""

    def __init__(self, *, cohort_assigner: PromotionCohortAssigner | None = None) -> None:
        self._cohort_assigner = cohort_assigner or PromotionCohortAssigner()

    def build(
        self,
        frame: pd.DataFrame,
        *,
        as_of_date: date | str | pd.Timestamp,
        minimum_sample_size: int = 3,
    ) -> PromotionCohortHistoryResult:
        """Return assigned rows plus historical summaries visible at the cutoff."""

        assigned_frame = self._cohort_assigner.assign(frame).frame
        historical_frame = filter_completed_rows_as_of(assigned_frame, as_of_date=as_of_date)
        validate_non_empty_cohort_frame(historical_frame, context="Promotion cohort history")
        summary_frames: list[pd.DataFrame] = []
        for cohort_family in COHORT_KEY_COLUMNS:
            if cohort_family == "cohort_key_archetype_primary":
                first_value_columns = PRIMARY_SIGNATURE_COLUMNS
            elif cohort_family == "cohort_key_archetype_secondary":
                first_value_columns = SECONDARY_SIGNATURE_COLUMNS
            else:
                first_value_columns = ()
            summary = aggregate_cohort_metrics(
                historical_frame,
                group_column=cohort_family,
                as_of_date=as_of_date,
                minimum_sample_size=minimum_sample_size,
                first_value_columns=first_value_columns,
            )
            summary = add_prefixed_trailing_metrics(
                summary,
                frame=historical_frame,
                group_column=cohort_family,
                as_of_date=as_of_date,
                minimum_sample_size=minimum_sample_size,
                months=12,
                first_value_columns=first_value_columns,
            )
            summary = add_prefixed_trailing_metrics(
                summary,
                frame=historical_frame,
                group_column=cohort_family,
                as_of_date=as_of_date,
                minimum_sample_size=minimum_sample_size,
                months=24,
                first_value_columns=first_value_columns,
            )
            summary = pd.concat(
                [
                    pd.DataFrame(
                        {
                            "cohort_family": cohort_family,
                            "archetype_granularity": _ARCHETYPE_FAMILIES.get(cohort_family, ""),
                        },
                        index=summary.index,
                    ),
                    summary.rename(columns={cohort_family: "cohort_key"}),
                ],
                axis=1,
            )
            summary_frames.append(summary)
        summary_frame = pd.concat(summary_frames, axis=0, ignore_index=True)
        archetype_history_frame = summary_frame.loc[
            summary_frame["cohort_family"].isin(tuple(_ARCHETYPE_FAMILIES.keys()))
        ].copy()
        return PromotionCohortHistoryResult(
            assigned_frame=assigned_frame,
            historical_frame=historical_frame,
            summary_frame=summary_frame,
            archetype_history_frame=archetype_history_frame,
            as_of_date=str(pd.Timestamp(as_of_date).date()),
            minimum_sample_size=minimum_sample_size,
        )