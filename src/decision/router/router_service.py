from __future__ import annotations

"""Deterministic router resolution for governed decision routes.

Canon ownership:
- Resolves route selection, precedence, tie-break, fallback, and unresolved
  outcomes from explicit registries.
- Keeps lifecycle legitimacy, authority legitimacy, and review execution out of
  the router decision.
"""

from dataclasses import dataclass

from decision.router.conflict_classifier import ConflictClassifier, RoutingConflictClassification
from decision.router.router_audit_adapter import RouterAuditAdapter
from decision.router.router_registry import RouterRegistry, RouterRuleDefinition


@dataclass(frozen=True)
class RouterResolutionRequest:
    router_rule_id: str
    semantic_scope: str
    state_model_name: str
    transition_name: str
    transition_class: str
    source_stage: str
    target_stage: str
    correlation_id: str
    episode_id: str
    actor_id: str


@dataclass(frozen=True)
class RouterResolution:
    accepted: bool
    resolution_status: str
    reason: str
    router_rule_id: str
    semantic_scope: str
    source_stage: str
    target_stage: str
    conflict_class: str
    classification_kind: str
    candidate_count: int
    review_required: bool
    route_name: str | None = None
    precedence_rank: int | None = None
    tie_break_policy: str | None = None
    fallback_route_name: str | None = None
    tie_break_applied: bool = False
    fallback_route_applied: bool = False


class RouterResolutionError(ValueError):
    """Raised when router configuration is incomplete or inconsistent."""


class RouterService:
    """Resolves governed routes from registry-backed router definitions."""

    def __init__(
        self,
        *,
        router_registry: RouterRegistry,
        conflict_classifier: ConflictClassifier,
        router_audit_adapter: RouterAuditAdapter,
    ) -> None:
        self._router_registry = router_registry
        self._conflict_classifier = conflict_classifier
        self._router_audit_adapter = router_audit_adapter

    def resolve(self, request: RouterResolutionRequest) -> RouterResolution:
        resolution, classification = self._resolve_without_audit(request)
        self._router_audit_adapter.record_resolution(
            resolution,
            classification,
            request=request,
        )
        return resolution

    def _resolve_without_audit(
        self,
        request: RouterResolutionRequest,
    ) -> tuple[RouterResolution, RoutingConflictClassification]:
        active_routes = tuple(
            route
            for route in self._router_registry.list_routes(request.router_rule_id)
            if route.status == "active" and route.semantic_scope == request.semantic_scope
        )
        primary_routes = self._primary_routes(active_routes)
        eligible_routes = tuple(
            route for route in primary_routes if self._is_eligible(route, request)
        )
        classification = self._conflict_classifier.classify(eligible_routes)

        if classification.classification_kind == "no_candidate":
            return self._blocked_resolution(request, classification), classification

        if classification.classification_kind == "single_candidate":
            selected = eligible_routes[0]
            return self._accepted_resolution(
                request,
                selected,
                classification,
                resolution_status="resolved",
            ), classification

        if classification.classification_kind == "precedence_required":
            highest_ranked_routes = self._highest_ranked_routes(eligible_routes)
            if len(highest_ranked_routes) == 1:
                selected = highest_ranked_routes[0]
                return self._accepted_resolution(
                    request,
                    selected,
                    classification,
                    resolution_status="resolved",
                ), classification
            return self._resolve_tie_break_or_fallback(
                request,
                highest_ranked_routes,
                classification,
            )

        if classification.classification_kind == "tie_break_required":
            return self._resolve_tie_break_or_fallback(request, eligible_routes, classification)

        return self._resolve_fallback_or_unresolved(request, eligible_routes, classification)

    def _primary_routes(
        self,
        routes: tuple[RouterRuleDefinition, ...],
    ) -> tuple[RouterRuleDefinition, ...]:
        fallback_route_names = {
            route.fallback_route_name
            for route in routes
            if route.fallback_route_name is not None
        }
        return tuple(route for route in routes if route.route_name not in fallback_route_names)

    def _is_eligible(
        self,
        route: RouterRuleDefinition,
        request: RouterResolutionRequest,
    ) -> bool:
        return (
            request.transition_class in route.allowed_transition_classes
            and request.source_stage in route.allowed_sources
            and request.target_stage in route.allowed_targets
        )

    def _highest_ranked_routes(
        self,
        routes: tuple[RouterRuleDefinition, ...],
    ) -> tuple[RouterRuleDefinition, ...]:
        precedence_by_route = {
            route.route_name: self._router_registry.get_precedence(
                route.router_rule_id,
                route.route_name,
            ).precedence_rank
            for route in routes
        }
        highest_rank = max(precedence_by_route.values())
        return tuple(
            route for route in routes if precedence_by_route[route.route_name] == highest_rank
        )

    def _resolve_tie_break_or_fallback(
        self,
        request: RouterResolutionRequest,
        routes: tuple[RouterRuleDefinition, ...],
        classification: RoutingConflictClassification,
    ) -> tuple[RouterResolution, RoutingConflictClassification]:
        tie_break_policies = {route.tie_break_policy for route in routes}
        if len(tie_break_policies) == 1:
            tie_break_policy = next(iter(tie_break_policies))
            if tie_break_policy == "lexicographic_route_name":
                selected = sorted(routes, key=lambda route: route.route_name)[0]
                return self._accepted_resolution(
                    request,
                    selected,
                    classification,
                    resolution_status="resolved",
                    tie_break_applied=True,
                ), classification
        return self._resolve_fallback_or_unresolved(request, routes, classification)

    def _resolve_fallback_or_unresolved(
        self,
        request: RouterResolutionRequest,
        routes: tuple[RouterRuleDefinition, ...],
        classification: RoutingConflictClassification,
    ) -> tuple[RouterResolution, RoutingConflictClassification]:
        fallback_route_names = {
            route.fallback_route_name for route in routes if route.fallback_route_name is not None
        }
        if len(fallback_route_names) == 1:
            fallback_route_name = next(iter(fallback_route_names))
            fallback_route = self._router_registry.get_route(
                request.router_rule_id,
                fallback_route_name,
            )
            if fallback_route.status == "active" and self._is_eligible(fallback_route, request):
                return self._accepted_resolution(
                    request,
                    fallback_route,
                    classification,
                    resolution_status="fallback_applied",
                    fallback_route_applied=True,
                    fallback_route_name=fallback_route_name,
                ), classification

        resolution = RouterResolution(
            accepted=False,
            resolution_status="unresolved",
            reason=classification.reason,
            router_rule_id=request.router_rule_id,
            semantic_scope=request.semantic_scope,
            source_stage=request.source_stage,
            target_stage=request.target_stage,
            conflict_class=classification.conflict_class,
            classification_kind=classification.classification_kind,
            candidate_count=classification.candidate_count,
            review_required=any(route.review_required for route in routes),
        )
        return resolution, classification

    def _accepted_resolution(
        self,
        request: RouterResolutionRequest,
        route: RouterRuleDefinition,
        classification: RoutingConflictClassification,
        *,
        resolution_status: str,
        tie_break_applied: bool = False,
        fallback_route_applied: bool = False,
        fallback_route_name: str | None = None,
    ) -> RouterResolution:
        precedence = self._router_registry.get_precedence(route.router_rule_id, route.route_name)
        return RouterResolution(
            accepted=True,
            resolution_status=resolution_status,
            reason=(
                "A deterministic router selection was produced."
                if resolution_status == "resolved"
                else "A configured fallback route was applied."
            ),
            router_rule_id=route.router_rule_id,
            semantic_scope=route.semantic_scope,
            source_stage=request.source_stage,
            target_stage=request.target_stage,
            conflict_class=classification.conflict_class,
            classification_kind=classification.classification_kind,
            candidate_count=classification.candidate_count,
            review_required=route.review_required,
            route_name=route.route_name,
            precedence_rank=precedence.precedence_rank,
            tie_break_policy=route.tie_break_policy,
            fallback_route_name=fallback_route_name,
            tie_break_applied=tie_break_applied,
            fallback_route_applied=fallback_route_applied,
        )

    def _blocked_resolution(
        self,
        request: RouterResolutionRequest,
        classification: RoutingConflictClassification,
    ) -> RouterResolution:
        return RouterResolution(
            accepted=False,
            resolution_status="blocked",
            reason=classification.reason,
            router_rule_id=request.router_rule_id,
            semantic_scope=request.semantic_scope,
            source_stage=request.source_stage,
            target_stage=request.target_stage,
            conflict_class=classification.conflict_class,
            classification_kind=classification.classification_kind,
            candidate_count=classification.candidate_count,
            review_required=False,
        )
