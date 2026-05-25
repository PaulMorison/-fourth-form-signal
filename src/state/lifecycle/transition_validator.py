from __future__ import annotations

"""Deterministic validation for governed lifecycle transitions.

Canon ownership:
- Validates state meaning, transition legitimacy, and explicit authority.
- Does not resolve routing and does not mutate orchestration state directly.
"""

from dataclasses import dataclass

from decision.authority.authority_resolution_service import (
    AuthorityResolutionService,
    AuthorityResolutionRequest,
)
from state.lifecycle.state_model_registry import (
    GovernedTransitionDefinition,
    StateModelRegistry,
    TransitionDefinitionNotFoundError,
)


class TransitionValidationError(ValueError):
    """Base error for governed transition validation."""

    def __init__(self, evaluation: "TransitionEvaluation") -> None:
        self.evaluation = evaluation
        super().__init__(evaluation.reason)


class InvalidTransitionError(TransitionValidationError):
    """Raised when a requested transition is not legitimate."""


class TransitionBlockedError(TransitionValidationError):
    """Raised when a transition is legitimate in principle but currently blocked."""


class MissingAuthorityError(TransitionBlockedError):
    """Raised when required authority is missing or mismatched."""


@dataclass(frozen=True)
class TransitionValidationRequest:
    case_type: str
    state_model_name: str
    current_state: str
    current_status: str
    transition_name: str
    actor_role: str
    correlation_id: str
    episode_id: str
    actor_id: str


@dataclass(frozen=True)
class TransitionEvaluation:
    accepted: bool
    outcome_kind: str
    reason: str
    transition_name: str
    state_model_name: str
    from_state: str
    to_state: str
    transition_class: str
    router_rule_id: str
    authority_rule_id: str
    actor_role: str
    authority_resolution_kind: str
    resolved_role: str | None
    review_required: bool
    resulting_status: str
    grant_source_role: str | None = None


class TransitionValidator:
    """Checks governed state transitions before any routing or mutation occurs."""

    def __init__(
        self,
        *,
        state_model_registry: StateModelRegistry,
        authority_resolution_service: AuthorityResolutionService,
    ) -> None:
        self._state_model_registry = state_model_registry
        self._authority_resolution_service = authority_resolution_service

    def validate_transition(self, request: TransitionValidationRequest) -> TransitionEvaluation:
        model = self._state_model_registry.get_state_model(request.state_model_name)
        try:
            transition = self._state_model_registry.get_transition(
                request.state_model_name,
                request.transition_name,
            )
        except TransitionDefinitionNotFoundError as error:
            raise InvalidTransitionError(
                self._rejection_from_request(
                    request,
                    outcome_kind="invalid",
                    reason=str(error),
                )
            ) from error

        if request.current_state != transition.from_state:
            raise InvalidTransitionError(
                self._rejection(
                    request,
                    transition,
                    outcome_kind="invalid",
                    reason=(
                        f"Transition '{transition.transition_name}' requires state '{transition.from_state}', "
                        f"not '{request.current_state}'."
                    ),
                    authority_resolution_kind="not_evaluated",
                    resolved_role=None,
                    review_required=False,
                )
            )

        if request.current_status not in transition.allowed_current_statuses:
            raise InvalidTransitionError(
                self._rejection(
                    request,
                    transition,
                    outcome_kind="invalid",
                    reason=(
                        f"Transition '{transition.transition_name}' does not allow current status "
                        f"'{request.current_status}'."
                    ),
                    authority_resolution_kind="not_evaluated",
                    resolved_role=None,
                    review_required=False,
                )
            )

        if transition.from_state != "__entry__":
            from_state = self._state_model_registry.get_state(
                request.state_model_name,
                transition.from_state,
            )
            if transition.transition_class in from_state.blocked_transition_classes:
                raise InvalidTransitionError(
                    self._rejection(
                        request,
                        transition,
                        outcome_kind="invalid",
                        reason=(
                            f"Transition class '{transition.transition_class}' is blocked from state "
                            f"'{transition.from_state}'."
                        ),
                        authority_resolution_kind="not_evaluated",
                        resolved_role=None,
                        review_required=False,
                    )
                )

        if not request.actor_role.strip():
            raise MissingAuthorityError(
                self._rejection(
                    request,
                    transition,
                    outcome_kind="blocked",
                    reason="A non-empty actor_role is required for governed transitions.",
                    authority_resolution_kind="blocked",
                    resolved_role=None,
                    review_required=False,
                )
            )

        authority_resolution = self._authority_resolution_service.resolve(
            AuthorityResolutionRequest(
                authority_rule_id=transition.authority_rule_id,
                actor_role=request.actor_role,
                authority_scope=model.semantic_scope,
                current_state=request.current_state,
                target_state=transition.to_state,
                state_sequence=tuple(model.states.keys()),
                transition_name=transition.transition_name,
                transition_class=transition.transition_class,
                correlation_id=request.correlation_id,
                episode_id=request.episode_id,
                actor_id=request.actor_id,
            )
        )
        if not authority_resolution.accepted:
            raise MissingAuthorityError(
                self._rejection(
                    request,
                    transition,
                    outcome_kind="blocked",
                    reason=authority_resolution.reason,
                    authority_resolution_kind=authority_resolution.resolution_kind,
                    resolved_role=authority_resolution.resolved_role,
                    review_required=authority_resolution.review_required,
                    grant_source_role=authority_resolution.grant_source_role,
                )
            )

        return TransitionEvaluation(
            accepted=True,
            outcome_kind=self._outcome_kind(transition.transition_class),
            reason="Transition accepted.",
            transition_name=transition.transition_name,
            state_model_name=request.state_model_name,
            from_state=transition.from_state,
            to_state=transition.to_state,
            transition_class=transition.transition_class,
            router_rule_id=transition.router_rule,
            authority_rule_id=transition.authority_rule_id,
            actor_role=request.actor_role,
            authority_resolution_kind=authority_resolution.resolution_kind,
            resolved_role=authority_resolution.resolved_role,
            review_required=authority_resolution.review_required,
            resulting_status=transition.resulting_status,
            grant_source_role=authority_resolution.grant_source_role,
        )

    def _outcome_kind(self, transition_class: str) -> str:
        if transition_class == "fallback":
            return "fallback"
        if transition_class == "resumption":
            return "resumed"
        return "accepted"

    def _rejection(
        self,
        request: TransitionValidationRequest,
        transition: GovernedTransitionDefinition,
        *,
        outcome_kind: str,
        reason: str,
        authority_resolution_kind: str,
        resolved_role: str | None,
        review_required: bool,
        grant_source_role: str | None = None,
    ) -> TransitionEvaluation:
        return TransitionEvaluation(
            accepted=False,
            outcome_kind=outcome_kind,
            reason=reason,
            transition_name=transition.transition_name,
            state_model_name=request.state_model_name,
            from_state=transition.from_state,
            to_state=transition.to_state,
            transition_class=transition.transition_class,
            router_rule_id=transition.router_rule,
            authority_rule_id=transition.authority_rule_id,
            actor_role=request.actor_role,
            authority_resolution_kind=authority_resolution_kind,
            resolved_role=resolved_role,
            review_required=review_required,
            resulting_status=transition.resulting_status,
            grant_source_role=grant_source_role,
        )

    def _rejection_from_request(
        self,
        request: TransitionValidationRequest,
        *,
        outcome_kind: str,
        reason: str,
    ) -> TransitionEvaluation:
        return TransitionEvaluation(
            accepted=False,
            outcome_kind=outcome_kind,
            reason=reason,
            transition_name=request.transition_name,
            state_model_name=request.state_model_name,
            from_state=request.current_state,
            to_state=request.current_state,
            transition_class="unknown",
            router_rule_id="unknown",
            authority_rule_id="unknown",
            actor_role=request.actor_role,
            authority_resolution_kind="not_evaluated",
            resolved_role=None,
            review_required=False,
            resulting_status=request.current_status,
        )
