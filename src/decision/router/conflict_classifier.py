from __future__ import annotations

"""Conflict classification for governed route candidates.

Canon ownership:
- Classifies routing situations into explicit conflict classes and resolution modes.
- Does not select routes, resolve authority, or mutate lifecycle state.
"""

from dataclasses import dataclass
from typing import Sequence

from decision.router.router_registry import RouterRegistry, RouterRuleDefinition


@dataclass(frozen=True)
class RoutingConflictClassification:
    conflict_class: str
    classification_kind: str
    candidate_count: int
    reason: str


class ConflictClassifier:
    """Maps eligible routes into explicit routing conflict classes."""

    def __init__(self, router_registry: RouterRegistry) -> None:
        self._router_registry = router_registry

    def classify(
        self,
        candidates: Sequence[RouterRuleDefinition],
    ) -> RoutingConflictClassification:
        if not candidates:
            return RoutingConflictClassification(
                conflict_class="no_route_available",
                classification_kind="no_candidate",
                candidate_count=0,
                reason="No eligible route candidates matched the routing request.",
            )

        conflict_classes = {candidate.conflict_class for candidate in candidates}
        if len(conflict_classes) != 1:
            return RoutingConflictClassification(
                conflict_class="unresolved_route_conflict",
                classification_kind="mixed_conflict_class",
                candidate_count=len(candidates),
                reason="Eligible routes span multiple conflict classes and cannot be compared safely.",
            )

        conflict_class = self._router_registry.get_conflict_class(next(iter(conflict_classes)))
        if conflict_class.status != "active":
            return RoutingConflictClassification(
                conflict_class="unresolved_route_conflict",
                classification_kind="inactive_conflict_class",
                candidate_count=len(candidates),
                reason=(
                    f"Conflict class '{conflict_class.conflict_class}' is not active for governed routing."
                ),
            )

        if len(candidates) == 1:
            return RoutingConflictClassification(
                conflict_class=conflict_class.conflict_class,
                classification_kind="single_candidate",
                candidate_count=1,
                reason="A single eligible route candidate was found.",
            )

        if conflict_class.resolution_basis == "precedence":
            classification_kind = "precedence_required"
            reason = "Multiple eligible routes require precedence comparison."
        elif conflict_class.resolution_basis == "tie_break":
            classification_kind = "tie_break_required"
            reason = "Multiple eligible routes require an explicit tie-break policy."
        elif conflict_class.resolution_basis == "unresolved":
            classification_kind = "unresolved"
            reason = "The conflict class explicitly requires unresolved handling."
        else:
            classification_kind = "unresolved"
            reason = (
                f"Conflict class '{conflict_class.conflict_class}' does not support multi-route resolution."
            )

        return RoutingConflictClassification(
            conflict_class=conflict_class.conflict_class,
            classification_kind=classification_kind,
            candidate_count=len(candidates),
            reason=reason,
        )
