from __future__ import annotations

"""Promotions cohort assignment and history modules."""

from state.promotions.cohorts.archetype_signature_builder import (
    ARCHETYPE_REGIME_COLUMNS,
    PRIMARY_SIGNATURE_COLUMNS,
    SECONDARY_SIGNATURE_COLUMNS,
    build_archetype_signature_columns,
)
from state.promotions.cohorts.cohort_assigner import (
    PromotionCohortAssigner,
    PromotionCohortAssignmentResult,
)
from state.promotions.cohorts.cohort_history_builder import (
    PromotionCohortHistoryBuilder,
    PromotionCohortHistoryResult,
)
from state.promotions.cohorts.cohort_keys import COHORT_KEY_COLUMNS

__all__ = [
    "ARCHETYPE_REGIME_COLUMNS",
    "COHORT_KEY_COLUMNS",
    "PRIMARY_SIGNATURE_COLUMNS",
    "SECONDARY_SIGNATURE_COLUMNS",
    "PromotionCohortAssigner",
    "PromotionCohortAssignmentResult",
    "PromotionCohortHistoryBuilder",
    "PromotionCohortHistoryResult",
    "build_archetype_signature_columns",
]