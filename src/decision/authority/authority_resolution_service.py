from __future__ import annotations

"""Deterministic authority resolution for lifecycle transitions.

Canon ownership:
- Resolves direct authority, delegated authority, fallback authority, or no
  authority from explicit registries.
- Keeps routing and review execution outside this slice.
"""

from dataclasses import dataclass
from typing import Sequence

from decision.authority.authority_audit_adapter import AuthorityAuditAdapter
from decision.authority.authority_registry import (
    AuthorityRegistry,
    AuthorityRoleDefinition,
    AuthorityRoleNotFoundError,
    AuthorityRuleDefinition,
    AuthorityRuleNotFoundError,
)
from decision.authority.delegation_policy import (
    DelegationPolicyDefinition,
    DelegationPolicyRegistry,
)


@dataclass(frozen=True)
class AuthorityResolutionRequest:
    authority_rule_id: str
    actor_role: str
    authority_scope: str
    current_state: str
    target_state: str
    state_sequence: tuple[str, ...]
    transition_name: str
    transition_class: str
    correlation_id: str
    episode_id: str
    actor_id: str


@dataclass(frozen=True)
class AuthorityResolution:
    accepted: bool
    resolution_kind: str
    reason: str
    authority_rule_id: str
    decision_right: str
    authority_scope: str
    authority_ceiling: str
    authority_floor: str
    review_required: bool
    resolved_role: str | None = None
    grant_source_role: str | None = None


class AuthorityResolutionService:
    """Resolves authority decisions from explicit rules and delegation policy."""

    def __init__(
        self,
        *,
        authority_registry: AuthorityRegistry,
        delegation_policy_registry: DelegationPolicyRegistry,
        authority_audit_adapter: AuthorityAuditAdapter,
    ) -> None:
        self._authority_registry = authority_registry
        self._delegation_policy_registry = delegation_policy_registry
        self._authority_audit_adapter = authority_audit_adapter

    def resolve(self, request: AuthorityResolutionRequest) -> AuthorityResolution:
        resolution = self._resolve_without_audit(request)
        self._authority_audit_adapter.record_resolution(resolution, request=request)
        return resolution

    def _resolve_without_audit(self, request: AuthorityResolutionRequest) -> AuthorityResolution:
        try:
            rule = self._authority_registry.get_authority_rule(request.authority_rule_id)
        except AuthorityRuleNotFoundError as error:
            return AuthorityResolution(
                accepted=False,
                resolution_kind="blocked",
                reason=str(error),
                authority_rule_id=request.authority_rule_id,
                decision_right="unknown",
                authority_scope=request.authority_scope,
                authority_ceiling=request.target_state,
                authority_floor=request.current_state,
                review_required=False,
            )

        if rule.status != "active":
            return self._blocked(rule, "blocked", f"Authority rule '{rule.authority_rule_id}' is not active.")

        try:
            actor_role = self._authority_registry.get_authority_role(request.actor_role)
        except AuthorityRoleNotFoundError as error:
            return self._blocked(rule, "blocked", str(error))

        if actor_role.status != "active":
            return self._blocked(rule, "blocked", f"Authority role '{actor_role.role_id}' is not active.")

        rule_violation = self._rule_scope_violation_reason(
            request,
            rule=rule,
        )
        if rule_violation is not None:
            return self._blocked(rule, "scope_violation", rule_violation)

        if request.actor_role in rule.allowed_roles:
            role_violation = self._role_scope_violation_reason(request, role=actor_role)
            if role_violation is not None:
                return self._blocked(rule, "scope_violation", role_violation)
            return AuthorityResolution(
                accepted=True,
                resolution_kind="direct",
                reason="Direct authority resolved.",
                authority_rule_id=rule.authority_rule_id,
                decision_right=rule.decision_right,
                authority_scope=rule.authority_scope,
                authority_ceiling=rule.authority_ceiling,
                authority_floor=rule.authority_floor,
                review_required=rule.review_required,
                resolved_role=request.actor_role,
            )

        if request.actor_role in rule.delegated_roles:
            policy = self._delegation_policy_registry.find_policy(
                rule.authority_rule_id,
                request.actor_role,
            )
            if policy is None or policy.status != "active":
                return self._blocked(
                    rule,
                    "delegated_missing",
                    (
                        f"Role '{request.actor_role}' is marked delegable for authority rule "
                        f"'{rule.authority_rule_id}' but no active delegation policy exists."
                    ),
                )

            role_violation = self._role_scope_violation_reason(request, role=actor_role)
            if role_violation is not None:
                return self._blocked(rule, "scope_violation", role_violation)

            policy_violation = self._policy_scope_violation_reason(request, policy=policy)
            if policy_violation is not None:
                return self._blocked(rule, "scope_violation", policy_violation)

            return AuthorityResolution(
                accepted=True,
                resolution_kind="delegated",
                reason="Delegated authority resolved through an active delegation policy.",
                authority_rule_id=rule.authority_rule_id,
                decision_right=rule.decision_right,
                authority_scope=rule.authority_scope,
                authority_ceiling=policy.authority_ceiling,
                authority_floor=policy.authority_floor,
                review_required=rule.review_required or policy.review_required,
                resolved_role=request.actor_role,
                grant_source_role=policy.delegating_role,
            )

        if (
            request.transition_class == "fallback"
            and rule.fallback_role is not None
            and request.actor_role == rule.fallback_role
        ):
            role_violation = self._role_scope_violation_reason(request, role=actor_role)
            if role_violation is not None:
                return self._blocked(rule, "scope_violation", role_violation)
            return AuthorityResolution(
                accepted=True,
                resolution_kind="fallback",
                reason="Fallback authority resolved through the authority rule fallback role.",
                authority_rule_id=rule.authority_rule_id,
                decision_right=rule.decision_right,
                authority_scope=rule.authority_scope,
                authority_ceiling=rule.authority_ceiling,
                authority_floor=rule.authority_floor,
                review_required=rule.review_required,
                resolved_role=request.actor_role,
            )

        return self._blocked(
            rule,
            "blocked",
            (
                f"Role '{request.actor_role}' has no direct, delegated, or fallback authority for "
                f"authority rule '{rule.authority_rule_id}'."
            ),
        )

    def _rule_scope_violation_reason(
        self,
        request: AuthorityResolutionRequest,
        *,
        rule: AuthorityRuleDefinition,
    ) -> str | None:
        if request.authority_scope != rule.authority_scope:
            return (
                f"Authority rule '{rule.authority_rule_id}' applies to scope '{rule.authority_scope}', "
                f"not '{request.authority_scope}'."
            )
        if not self._state_within_bounds(
            request.target_state,
            request.state_sequence,
            rule.authority_floor,
            rule.authority_ceiling,
        ):
            return (
                f"Target state '{request.target_state}' is outside the authority rule bounds "
                f"'{rule.authority_floor}' to '{rule.authority_ceiling}'."
            )
        return None

    def _role_scope_violation_reason(
        self,
        request: AuthorityResolutionRequest,
        *,
        role: AuthorityRoleDefinition,
    ) -> str | None:
        if request.authority_scope != role.authority_scope:
            return (
                f"Authority role '{role.role_id}' applies to scope '{role.authority_scope}', "
                f"not '{request.authority_scope}'."
            )
        if not self._state_within_bounds(
            request.target_state,
            request.state_sequence,
            role.authority_floor,
            role.authority_ceiling,
        ):
            return (
                f"Target state '{request.target_state}' is outside the role bounds "
                f"'{role.authority_floor}' to '{role.authority_ceiling}'."
            )
        return None

    def _policy_scope_violation_reason(
        self,
        request: AuthorityResolutionRequest,
        *,
        policy: DelegationPolicyDefinition,
    ) -> str | None:
        if request.authority_scope != policy.authority_scope:
            return (
                f"Delegation policy '{policy.delegation_policy_id}' applies to scope "
                f"'{policy.authority_scope}', not '{request.authority_scope}'."
            )
        if not self._state_within_bounds(
            request.target_state,
            request.state_sequence,
            policy.authority_floor,
            policy.authority_ceiling,
        ):
            return (
                f"Target state '{request.target_state}' is outside the delegation policy bounds "
                f"'{policy.authority_floor}' to '{policy.authority_ceiling}'."
            )
        return None

    def _state_within_bounds(
        self,
        state_name: str,
        state_sequence: Sequence[str],
        floor_state: str,
        ceiling_state: str,
    ) -> bool:
        if state_name == "__entry__":
            return True
        state_order = {name: index for index, name in enumerate(state_sequence)}
        try:
            state_index = state_order[state_name]
            floor_index = state_order[floor_state]
            ceiling_index = state_order[ceiling_state]
        except KeyError:
            return False
        return floor_index <= state_index <= ceiling_index

    def _blocked(
        self,
        rule: AuthorityRuleDefinition,
        resolution_kind: str,
        reason: str,
    ) -> AuthorityResolution:
        return AuthorityResolution(
            accepted=False,
            resolution_kind=resolution_kind,
            reason=reason,
            authority_rule_id=rule.authority_rule_id,
            decision_right=rule.decision_right,
            authority_scope=rule.authority_scope,
            authority_ceiling=rule.authority_ceiling,
            authority_floor=rule.authority_floor,
            review_required=rule.review_required,
        )
