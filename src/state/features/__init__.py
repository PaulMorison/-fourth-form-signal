"""Governed feature registry services."""

from .feature_registry import (
    DuplicateFeatureDefinitionError,
    FeatureDefinition,
    FeatureRegistry,
    FeatureRegistryError,
    FeatureSemanticValidationError,
    FeatureOwnerNotRegisteredError,
    InMemoryFeatureDefinitionRepository,
    JsonFeatureOwnerRegistry,
)

__all__ = [
    "DuplicateFeatureDefinitionError",
    "FeatureDefinition",
    "FeatureRegistry",
    "FeatureRegistryError",
    "FeatureSemanticValidationError",
    "FeatureOwnerNotRegisteredError",
    "InMemoryFeatureDefinitionRepository",
    "JsonFeatureOwnerRegistry",
]
