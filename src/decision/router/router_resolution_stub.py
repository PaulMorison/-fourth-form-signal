from __future__ import annotations

"""Compatibility adapter around the governed router service.

Canon ownership:
- Preserves the legacy router-stub import surface while delegating to the real
  registry-backed router layer.
- Does not restore lifecycle-owned precedence or conflict handling.
"""

from pathlib import Path

from ff_platform.validation.contract_schema_validator import ContractSchemaValidator

from .conflict_classifier import ConflictClassifier
from .router_audit_adapter import RouterAuditAdapter
from .router_registry import JsonRouterRegistry
from .router_service import RouterResolution, RouterResolutionError, RouterResolutionRequest, RouterService


class JsonRouterRuleRegistry(JsonRouterRegistry):
    """Backwards-compatible name for the router registry."""

    def __init__(
        self,
        *,
        registry_root: Path,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        super().__init__(
            router_rules_path=registry_root / "router_rules.json",
            conflict_classes_path=registry_root / "conflict_classes.json",
            route_precedence_path=registry_root / "route_precedence.json",
            contract_validator=contract_validator,
        )


class RouterResolutionStub:
    """Backwards-compatible wrapper over the governed router service."""

    def __init__(self, router_service: RouterService) -> None:
        self._router_service = router_service

    def resolve(self, request: RouterResolutionRequest) -> RouterResolution:
        return self._router_service.resolve(request)

    @classmethod
    def from_registry(
        cls,
        *,
        registry_root: Path,
        contract_validator: ContractSchemaValidator,
        router_audit_adapter: RouterAuditAdapter,
    ) -> "RouterResolutionStub":
        router_registry = JsonRouterRuleRegistry(
            registry_root=registry_root,
            contract_validator=contract_validator,
        )
        router_service = RouterService(
            router_registry=router_registry,
            conflict_classifier=ConflictClassifier(router_registry),
            router_audit_adapter=router_audit_adapter,
        )
        return cls(router_service)

