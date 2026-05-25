from __future__ import annotations

"""Reusable promotions feature-engineering layer."""

from state.promotions.feature_engineering.feature_pipeline import (
    PromotionFeatureEngineer,
    PromotionFeatureEngineeringResult,
)
from state.promotions.feature_engineering.registry import (
    PromotionFeatureModuleDefinition,
    iter_registered_feature_modules,
)

__all__ = [
    "PromotionFeatureEngineer",
    "PromotionFeatureEngineeringResult",
    "PromotionFeatureModuleDefinition",
    "iter_registered_feature_modules",
]
