from __future__ import annotations

"""Registry-backed router rules, conflict classes, and precedence definitions.

Canon ownership:
- Owns governed router identity, conflict-class identity, and precedence metadata.
- Does not perform lifecycle validation, authority resolution, or review execution.
"""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping, Protocol, Sequence

from ff_platform.validation.contract_schema_validator import ContractSchemaValidator

_REGISTRY_VALIDATION_CORRELATION_ID = "00000000-0000-0000-0000-000000000000"
_VALID_ROUTE_STATUS = {"active", "deprecated"}
_VALID_CONFLICT_STATUS = {"active", "deprecated"}
_VALID_PRECEDENCE_STATUS = {"active", "deprecated"}
_VALID_TIE_BREAK_POLICIES = {"none", "lexicographic_route_name", "manual_resolution_required"}


class RouterRegistryError(ValueError):
    """Base error for router registry failures."""


class RouterRuleNotFoundError(RouterRegistryError):
    """Raised when a router rule is not registered."""


class ConflictClassNotFoundError(RouterRegistryError):
    """Raised when a conflict class is not registered."""


class RoutePrecedenceNotFoundError(RouterRegistryError):
    """Raised when route precedence is missing."""


@dataclass(frozen=True)
class RouterRuleDefinition:
    router_rule_id: str
    route_name: str
    semantic_scope: str
    allowed_transition_classes: tuple[str, ...]
    allowed_sources: tuple[str, ...]
    allowed_targets: tuple[str, ...]
    conflict_class: str
    tie_break_policy: str
    fallback_route_name: str | None
    review_required: bool
    status: str
    lineage: Mapping[str, str]


@dataclass(frozen=True)
class ConflictClassDefinition:
    conflict_class: str
    description: str
    resolution_basis: str
    allows_tie_break: bool
    allows_fallback: bool
    status: str
    lineage: Mapping[str, str]


@dataclass(frozen=True)
class RoutePrecedenceDefinition:
    router_rule_id: str
    route_name: str
    precedence_rank: int
    status: str
    lineage: Mapping[str, str]


class RouterRegistry(Protocol):
    def list_routes(self, router_rule_id: str) -> Sequence[RouterRuleDefinition]:
        """Return all registered routes for the named router rule."""

    def get_route(self, router_rule_id: str, route_name: str) -> RouterRuleDefinition:
        """Return the named route under a router rule."""

    def get_conflict_class(self, conflict_class: str) -> ConflictClassDefinition:
        """Return the named conflict class."""

    def get_precedence(
        self,
        router_rule_id: str,
        route_name: str,
    ) -> RoutePrecedenceDefinition:
        """Return precedence metadata for a route."""


class JsonRouterRegistry:
    """Loads router rules, conflict classes, and precedence from registries."""

    def __init__(
        self,
        *,
        router_rules_path: Path,
        conflict_classes_path: Path,
        route_precedence_path: Path,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._contract_validator = contract_validator
        self._routes_by_rule = self._load_routes(router_rules_path)
        self._conflict_classes = self._load_conflict_classes(conflict_classes_path)
        self._precedence_by_route = self._load_precedence(route_precedence_path)
        self._validate_cross_registry_links()

    def list_routes(self, router_rule_id: str) -> Sequence[RouterRuleDefinition]:
        try:
            return tuple(self._routes_by_rule[router_rule_id].values())
        except KeyError as error:
            raise RouterRuleNotFoundError(
                f"Router rule '{router_rule_id}' is not registered."
            ) from error

    def get_route(self, router_rule_id: str, route_name: str) -> RouterRuleDefinition:
        try:
            return self._routes_by_rule[router_rule_id][route_name]
        except KeyError as error:
            raise RouterRuleNotFoundError(
                f"Route '{route_name}' is not registered under router rule '{router_rule_id}'."
            ) from error

    def get_conflict_class(self, conflict_class: str) -> ConflictClassDefinition:
        try:
            return self._conflict_classes[conflict_class]
        except KeyError as error:
            raise ConflictClassNotFoundError(
                f"Conflict class '{conflict_class}' is not registered."
            ) from error

    def get_precedence(
        self,
        router_rule_id: str,
        route_name: str,
    ) -> RoutePrecedenceDefinition:
        try:
            return self._precedence_by_route[(router_rule_id, route_name)]
        except KeyError as error:
            raise RoutePrecedenceNotFoundError(
                f"Route precedence for '{route_name}' under '{router_rule_id}' is not registered."
            ) from error

    def _load_routes(
        self,
        router_rules_path: Path,
    ) -> dict[str, dict[str, RouterRuleDefinition]]:
        content = json.loads(router_rules_path.read_text(encoding="utf-8"))
        routes_by_rule: dict[str, dict[str, RouterRuleDefinition]] = {}

        for router_rule_id, route_entries in content["router_rules"].items():
            route_map: dict[str, RouterRuleDefinition] = {}
            for route_entry in route_entries:
                self._contract_validator.validate_or_raise(
                    "router_rule",
                    route_entry,
                    correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                    entity_type="router_rule",
                    entity_id=f"{router_rule_id}:{route_entry['route_name']}",
                    emit_audit_events=False,
                )
                if route_entry["router_rule_id"] != router_rule_id:
                    raise RouterRegistryError(
                        f"Router rule key '{router_rule_id}' must match router_rule_id "
                        f"'{route_entry['router_rule_id']}'."
                    )
                if route_entry["status"] not in _VALID_ROUTE_STATUS:
                    raise RouterRegistryError(
                        f"Router route '{route_entry['route_name']}' has invalid status "
                        f"'{route_entry['status']}'."
                    )
                if route_entry["tie_break_policy"] not in _VALID_TIE_BREAK_POLICIES:
                    raise RouterRegistryError(
                        f"Router route '{route_entry['route_name']}' has invalid tie_break_policy "
                        f"'{route_entry['tie_break_policy']}'."
                    )
                route_definition = RouterRuleDefinition(
                    router_rule_id=route_entry["router_rule_id"],
                    route_name=route_entry["route_name"],
                    semantic_scope=route_entry["semantic_scope"],
                    allowed_transition_classes=tuple(route_entry["allowed_transition_classes"]),
                    allowed_sources=tuple(route_entry["allowed_sources"]),
                    allowed_targets=tuple(route_entry["allowed_targets"]),
                    conflict_class=route_entry["conflict_class"],
                    tie_break_policy=route_entry["tie_break_policy"],
                    fallback_route_name=route_entry.get("fallback_route_name"),
                    review_required=bool(route_entry["review_required"]),
                    status=route_entry["status"],
                    lineage=dict(route_entry["lineage"]),
                )
                if route_definition.route_name in route_map:
                    raise RouterRegistryError(
                        f"Duplicate route_name '{route_definition.route_name}' under router rule '{router_rule_id}'."
                    )
                route_map[route_definition.route_name] = route_definition
            routes_by_rule[router_rule_id] = route_map

        return routes_by_rule

    def _load_conflict_classes(
        self,
        conflict_classes_path: Path,
    ) -> dict[str, ConflictClassDefinition]:
        content = json.loads(conflict_classes_path.read_text(encoding="utf-8"))
        conflict_classes: dict[str, ConflictClassDefinition] = {}

        for conflict_class_id, class_entry in content["conflict_classes"].items():
            self._contract_validator.validate_or_raise(
                "conflict_class",
                class_entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="conflict_class",
                entity_id=conflict_class_id,
                emit_audit_events=False,
            )
            if class_entry["conflict_class"] != conflict_class_id:
                raise RouterRegistryError(
                    f"Conflict class key '{conflict_class_id}' must match conflict_class "
                    f"'{class_entry['conflict_class']}'."
                )
            if class_entry["status"] not in _VALID_CONFLICT_STATUS:
                raise RouterRegistryError(
                    f"Conflict class '{conflict_class_id}' has invalid status '{class_entry['status']}'."
                )
            conflict_classes[conflict_class_id] = ConflictClassDefinition(
                conflict_class=class_entry["conflict_class"],
                description=class_entry["description"],
                resolution_basis=class_entry["resolution_basis"],
                allows_tie_break=bool(class_entry["allows_tie_break"]),
                allows_fallback=bool(class_entry["allows_fallback"]),
                status=class_entry["status"],
                lineage=dict(class_entry["lineage"]),
            )

        return conflict_classes

    def _load_precedence(
        self,
        route_precedence_path: Path,
    ) -> dict[tuple[str, str], RoutePrecedenceDefinition]:
        content = json.loads(route_precedence_path.read_text(encoding="utf-8"))
        precedence_by_route: dict[tuple[str, str], RoutePrecedenceDefinition] = {}

        for entry in content["route_precedence"]:
            self._validate_precedence_entry(entry)
            key = (entry["router_rule_id"], entry["route_name"])
            if key in precedence_by_route:
                raise RouterRegistryError(
                    f"Duplicate precedence entry for route '{entry['route_name']}' under "
                    f"router rule '{entry['router_rule_id']}'."
                )
            precedence_by_route[key] = RoutePrecedenceDefinition(
                router_rule_id=entry["router_rule_id"],
                route_name=entry["route_name"],
                precedence_rank=int(entry["precedence_rank"]),
                status=entry["status"],
                lineage=dict(entry["lineage"]),
            )

        return precedence_by_route

    def _validate_precedence_entry(self, entry: Mapping[str, object]) -> None:
        required_keys = {"router_rule_id", "route_name", "precedence_rank", "status", "lineage"}
        missing = required_keys.difference(entry)
        if missing:
            raise RouterRegistryError(
                f"Route precedence entry is missing required keys: {sorted(missing)}"
            )
        if not isinstance(entry["precedence_rank"], int):
            raise RouterRegistryError("Route precedence precedence_rank must be an integer.")
        if int(entry["precedence_rank"]) < 0:
            raise RouterRegistryError("Route precedence precedence_rank must be non-negative.")
        if entry["status"] not in _VALID_PRECEDENCE_STATUS:
            raise RouterRegistryError(
                f"Route precedence for '{entry['route_name']}' has invalid status '{entry['status']}'."
            )
        lineage = entry["lineage"]
        if not isinstance(lineage, dict) or "version" not in lineage:
            raise RouterRegistryError(
                f"Route precedence for '{entry['route_name']}' must provide lineage.version metadata."
            )

    def _validate_cross_registry_links(self) -> None:
        for router_rule_id, route_map in self._routes_by_rule.items():
            for route in route_map.values():
                if route.conflict_class not in self._conflict_classes:
                    raise RouterRegistryError(
                        f"Route '{route.route_name}' references unknown conflict_class '{route.conflict_class}'."
                    )
                if (router_rule_id, route.route_name) not in self._precedence_by_route:
                    raise RouterRegistryError(
                        f"Route '{route.route_name}' under '{router_rule_id}' is missing precedence metadata."
                    )
                if route.fallback_route_name is not None and route.fallback_route_name not in route_map:
                    raise RouterRegistryError(
                        f"Route '{route.route_name}' references unknown fallback route '{route.fallback_route_name}'."
                    )
