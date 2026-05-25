from __future__ import annotations

"""Promotions cohort backtesting, similarity, and archetype ranking models."""

from models.promotions.cohorts.archetype_ranker import (
    PromotionArchetypeRanker,
    PromotionArchetypeRankingResult,
)
from models.promotions.cohorts.cohort_backtester import (
    PromotionCohortBacktestResult,
    PromotionCohortBacktester,
)
from models.promotions.cohorts.cohort_similarity import (
    CohortSimilarityConfig,
    PromotionCohortSimilarity,
)
from models.promotions.cohorts.calibration import (
    PromotionDecisionCalibrationResult,
    PromotionDecisionCalibrator,
)
from models.promotions.cohorts.decision_fusion import (
    PromotionDecisionFusion,
    PromotionDecisionFusionConfig,
    PromotionDecisionFusionResult,
    build_row_cohort_disagreement_score,
)
from models.promotions.cohorts.diagnostics import (
    PromotionDecisionDiagnostics,
    PromotionDecisionDiagnosticsResult,
)

__all__ = [
    "CohortSimilarityConfig",
    "PromotionArchetypeRanker",
    "PromotionArchetypeRankingResult",
    "PromotionCohortBacktestResult",
    "PromotionCohortBacktester",
    "PromotionCohortSimilarity",
    "PromotionDecisionCalibrationResult",
    "PromotionDecisionCalibrator",
    "PromotionDecisionDiagnostics",
    "PromotionDecisionDiagnosticsResult",
    "PromotionDecisionFusion",
    "PromotionDecisionFusionConfig",
    "PromotionDecisionFusionResult",
    "build_row_cohort_disagreement_score",
]