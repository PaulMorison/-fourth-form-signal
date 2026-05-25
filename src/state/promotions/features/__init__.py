from __future__ import annotations

"""Compatibility wrapper for the promotions feature-engineering layer."""

from state.promotions.feature_engineering.feature_pipeline import (
    PromotionFeatureEngineer,
    PromotionFeatureEngineeringResult,
)

__all__ = ["PromotionFeatureEngineer", "PromotionFeatureEngineeringResult"]
