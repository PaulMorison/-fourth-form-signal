"""Governed router registries, conflict classification, and resolution services."""

from .conflict_classifier import ConflictClassifier, RoutingConflictClassification
from .router_audit_adapter import RouterAuditAdapter
from .router_registry import (
    ConflictClassDefinition,
    ConflictClassNotFoundError,
    JsonRouterRegistry,
    RoutePrecedenceDefinition,
    RoutePrecedenceNotFoundError,
    RouterRegistry,
    RouterRegistryError,
    RouterRuleDefinition,
    RouterRuleNotFoundError,
)
from .router_resolution_stub import JsonRouterRuleRegistry, RouterResolutionStub
from .router_service import RouterResolution, RouterResolutionError, RouterResolutionRequest, RouterService

__all__ = [
    "ConflictClassifier",
    "ConflictClassDefinition",
    "ConflictClassNotFoundError",
    "JsonRouterRegistry",
    "JsonRouterRuleRegistry",
    "RoutePrecedenceDefinition",
    "RoutePrecedenceNotFoundError",
    "RouterAuditAdapter",
    "RouterRegistry",
    "RouterRegistryError",
    "RouterResolution",
    "RouterResolutionError",
    "RouterResolutionRequest",
    "RouterResolutionStub",
    "RouterRuleDefinition",
    "RouterRuleNotFoundError",
    "RouterService",
    "RoutingConflictClassification",
]
