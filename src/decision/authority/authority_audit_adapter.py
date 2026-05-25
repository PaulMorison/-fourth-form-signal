from __future__ import annotations

"""Structured audit emission for authority-resolution outcomes.

Canon ownership:
- Emits audit events for direct, delegated, fallback, blocked, and scope-violating
  authority decisions.
- Keeps authority legitimacy auditable without absorbing transition or routing logic.
"""

from typing import TYPE_CHECKING, Any

from platform.audit.audit_event_store import AuditEventStore
from platform.validation.contract_schema_validator import ContractSchemaValidator

if TYPE_CHECKING:
    from decision.authority.authority_resolution_service import (
        AuthorityResolution,
        AuthorityResolutionRequest,
    )


class AuthorityAuditAdapter:
    """Emits governed audit events for authority decisions."""

    def __init__(
        self,
        *,
        audit_event_store: AuditEventStore,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._audit_event_store = audit_event_store
        self._contract_validator = contract_validator

    def record_resolution(
        self,
        resolution: "AuthorityResolution",
        *,
        request: "AuthorityResolutionRequest",
    ) -> None:
        if resolution.accepted:
            if resolution.resolution_kind == "delegated":
                self._emit_event("decision.authority.delegation_applied", resolution, request)
            elif resolution.resolution_kind == "fallback":
                self._emit_event("decision.authority.authority_fallback_applied", resolution, request)
            self._emit_event("decision.authority.authority_resolution_succeeded", resolution, request)
            return

        if resolution.resolution_kind == "delegated_missing":
            self._emit_event("decision.authority.delegation_missing", resolution, request)
        elif resolution.resolution_kind == "scope_violation":
            self._emit_event("decision.authority.authority_scope_violation", resolution, request)
        self._emit_event("decision.authority.authority_resolution_blocked", resolution, request)

    def _emit_event(
        self,
        event_name: str,
        resolution: "AuthorityResolution",
        request: "AuthorityResolutionRequest",
    ) -> None:
        payload = self._build_payload(event_name, resolution, request)
        self._contract_validator.validate_or_raise(
            "authority_resolution_event",
            payload,
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.episode_id,
            actor_id=request.actor_id,
            emit_audit_events=False,
        )
        self._audit_event_store.record_event(
            event_type=event_name,
            owner="decision.authority.authority_audit_adapter",
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.episode_id,
            actor_id=request.actor_id,
            payload=payload,
            tags=("authority", resolution.resolution_kind, request.transition_class),
        )

    def _build_payload(
        self,
        event_name: str,
        resolution: "AuthorityResolution",
        request: "AuthorityResolutionRequest",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "event_name": event_name,
            "authority_rule_id": resolution.authority_rule_id,
            "decision_right": resolution.decision_right,
            "actor_role": request.actor_role,
            "resolution_kind": resolution.resolution_kind,
            "authority_scope": resolution.authority_scope,
            "authority_ceiling": resolution.authority_ceiling,
            "authority_floor": resolution.authority_floor,
            "review_required": resolution.review_required,
            "transition_name": request.transition_name,
            "transition_class": request.transition_class,
            "reason": resolution.reason,
        }
        if resolution.resolved_role is not None:
            payload["resolved_role"] = resolution.resolved_role
        if resolution.grant_source_role is not None:
            payload["grant_source_role"] = resolution.grant_source_role
        return payload
