from __future__ import annotations

"""Structured audit emission for governed rollout-scope control.

Canon ownership:
- Emits explicit rollout-scope recorded, blocked, ready, conditional,
  deferred, rejected, missing-context, prohibited-overlap, and fallback audit
  events.
- Keeps rollback-trigger control, post-release watch execution, monitoring,
  reopen handling, and lifecycle meaning out of this slice.
"""

from typing import TYPE_CHECKING

from platform.audit.audit_event_store import AuditEventStore
from platform.validation.contract_schema_validator import ContractSchemaValidator

if TYPE_CHECKING:
    from runtime.release.rollout_scope_controller import (
        RolloutScopeControllerRequest,
        RolloutScopeRecord,
    )


class RolloutScopeAuditAdapter:
    """Emits governed audit events for rollout-scope control."""

    def __init__(
        self,
        *,
        audit_event_store: AuditEventStore,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._audit_event_store = audit_event_store
        self._contract_validator = contract_validator

    def record_rollout_scope(
        self,
        rollout_scope: "RolloutScopeRecord",
        *,
        request: "RolloutScopeControllerRequest",
    ) -> None:
        payload = rollout_scope.to_contract_dict()
        self._contract_validator.validate_or_raise(
            "rollout_scope_record",
            payload,
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.promotion_readiness.episode_id,
            actor_id=request.actor_id,
            emit_audit_events=False,
        )

        status = rollout_scope.rollout_scope_status
        if status in {
            "blocked_missing_context",
            "rejected_for_rollout_scope_use",
            "prohibited_overlap_blocked",
        }:
            self._emit(
                event_type="runtime.release.rollout_scope_blocked",
                payload=payload,
                request=request,
                tags=(
                    "runtime-release",
                    rollout_scope.rollout_scope_class_id,
                    status,
                ),
            )
            if status == "blocked_missing_context":
                self._emit(
                    event_type="runtime.release.rollout_scope_missing_context",
                    payload=payload,
                    request=request,
                    tags=(
                        "runtime-release",
                        rollout_scope.rollout_scope_class_id,
                        "missing-context",
                    ),
                )
            if status == "rejected_for_rollout_scope_use":
                self._emit(
                    event_type="runtime.release.rollout_scope_rejected_for_rollout_scope_use",
                    payload=payload,
                    request=request,
                    tags=(
                        "runtime-release",
                        rollout_scope.rollout_scope_class_id,
                        "rejected-for-rollout-scope-use",
                    ),
                )
            if status == "prohibited_overlap_blocked":
                self._emit(
                    event_type="runtime.release.rollout_scope_prohibited_overlap_blocked",
                    payload=payload,
                    request=request,
                    tags=(
                        "runtime-release",
                        rollout_scope.rollout_scope_class_id,
                        "prohibited-overlap",
                    ),
                )
            return

        self._emit(
            event_type="runtime.release.rollout_scope_recorded",
            payload=payload,
            request=request,
            tags=(
                "runtime-release",
                rollout_scope.rollout_scope_class_id,
                "recorded",
            ),
        )

        outcome = rollout_scope.rollout_scope_outcome
        if outcome == "ready_for_rollback_trigger_guard":
            self._emit(
                event_type="runtime.release.rollout_scope_ready_for_rollback_trigger_guard",
                payload=payload,
                request=request,
                tags=(
                    "runtime-release",
                    rollout_scope.rollout_scope_class_id,
                    "ready-for-rollback-trigger-guard",
                ),
            )
        elif outcome == "conditionally_ready_for_rollback_trigger_guard":
            self._emit(
                event_type=(
                    "runtime.release.rollout_scope_conditionally_ready_for_rollback_trigger_guard"
                ),
                payload=payload,
                request=request,
                tags=(
                    "runtime-release",
                    rollout_scope.rollout_scope_class_id,
                    "conditionally-ready-for-rollback-trigger-guard",
                ),
            )
        elif outcome == "deferred_pending_rollout_scope_evidence":
            self._emit(
                event_type=(
                    "runtime.release.rollout_scope_deferred_pending_rollout_scope_evidence"
                ),
                payload=payload,
                request=request,
                tags=(
                    "runtime-release",
                    rollout_scope.rollout_scope_class_id,
                    "deferred-pending-rollout-scope-evidence",
                ),
            )

        if status == "fallback_template_applied":
            self._emit(
                event_type="runtime.release.rollout_scope_fallback_template_applied",
                payload=payload,
                request=request,
                tags=(
                    "runtime-release",
                    rollout_scope.rollout_scope_class_id,
                    "fallback-template",
                ),
            )

    def _emit(
        self,
        *,
        event_type: str,
        payload: dict[str, object],
        request: "RolloutScopeControllerRequest",
        tags: tuple[str, ...],
    ) -> None:
        self._audit_event_store.record_event(
            event_type=event_type,
            owner="runtime.release.rollout_scope_audit_adapter",
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.promotion_readiness.episode_id,
            actor_id=request.actor_id,
            payload=payload,
            tags=tags,
        )