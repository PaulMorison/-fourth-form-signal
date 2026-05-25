from __future__ import annotations

"""Structured audit emission for governed rollback-trigger control.

Canon ownership:
- Emits explicit rollback-trigger recorded, blocked, ready, conditional,
  deferred, rejected, missing-context, prohibited-overlap, and fallback audit
  events.
- Keeps post-release watch execution, rollback execution, monitoring, reopen
  handling, and lifecycle meaning out of this slice.
"""

from typing import TYPE_CHECKING

from platform.audit.audit_event_store import AuditEventStore
from platform.validation.contract_schema_validator import ContractSchemaValidator

if TYPE_CHECKING:
    from runtime.release.rollback_trigger_guard import (
        RollbackTriggerGuardRequest,
        RollbackTriggerRecord,
    )


class RollbackTriggerAuditAdapter:
    """Emits governed audit events for rollback-trigger control."""

    def __init__(
        self,
        *,
        audit_event_store: AuditEventStore,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._audit_event_store = audit_event_store
        self._contract_validator = contract_validator

    def record_rollback_trigger(
        self,
        rollback_trigger: "RollbackTriggerRecord",
        *,
        request: "RollbackTriggerGuardRequest",
    ) -> None:
        payload = rollback_trigger.to_contract_dict()
        self._contract_validator.validate_or_raise(
            "rollback_trigger_record",
            payload,
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.rollout_scope.episode_id,
            actor_id=request.actor_id,
            emit_audit_events=False,
        )

        status = rollback_trigger.rollback_trigger_status
        if status in {
            "blocked_missing_context",
            "rejected_for_rollback_trigger_use",
            "prohibited_overlap_blocked",
        }:
            self._emit(
                event_type="runtime.release.rollback_trigger_blocked",
                payload=payload,
                request=request,
                tags=(
                    "runtime-release",
                    rollback_trigger.rollback_trigger_class_id,
                    status,
                ),
            )
            if status == "blocked_missing_context":
                self._emit(
                    event_type="runtime.release.rollback_trigger_missing_context",
                    payload=payload,
                    request=request,
                    tags=(
                        "runtime-release",
                        rollback_trigger.rollback_trigger_class_id,
                        "missing-context",
                    ),
                )
            if status == "rejected_for_rollback_trigger_use":
                self._emit(
                    event_type=(
                        "runtime.release.rollback_trigger_rejected_for_rollback_trigger_use"
                    ),
                    payload=payload,
                    request=request,
                    tags=(
                        "runtime-release",
                        rollback_trigger.rollback_trigger_class_id,
                        "rejected-for-rollback-trigger-use",
                    ),
                )
            if status == "prohibited_overlap_blocked":
                self._emit(
                    event_type=(
                        "runtime.release.rollback_trigger_prohibited_overlap_blocked"
                    ),
                    payload=payload,
                    request=request,
                    tags=(
                        "runtime-release",
                        rollback_trigger.rollback_trigger_class_id,
                        "prohibited-overlap",
                    ),
                )
            return

        self._emit(
            event_type="runtime.release.rollback_trigger_recorded",
            payload=payload,
            request=request,
            tags=(
                "runtime-release",
                rollback_trigger.rollback_trigger_class_id,
                "recorded",
            ),
        )

        outcome = rollback_trigger.rollback_trigger_outcome
        if outcome == "ready_for_release_watch_discipline":
            self._emit(
                event_type=(
                    "runtime.release.rollback_trigger_ready_for_release_watch_discipline"
                ),
                payload=payload,
                request=request,
                tags=(
                    "runtime-release",
                    rollback_trigger.rollback_trigger_class_id,
                    "ready-for-release-watch-discipline",
                ),
            )
        elif outcome == "conditionally_ready_for_release_watch_discipline":
            self._emit(
                event_type=(
                    "runtime.release.rollback_trigger_conditionally_ready_for_release_watch_discipline"
                ),
                payload=payload,
                request=request,
                tags=(
                    "runtime-release",
                    rollback_trigger.rollback_trigger_class_id,
                    "conditionally-ready-for-release-watch-discipline",
                ),
            )
        elif outcome == "deferred_pending_rollback_trigger_evidence":
            self._emit(
                event_type=(
                    "runtime.release.rollback_trigger_deferred_pending_rollback_trigger_evidence"
                ),
                payload=payload,
                request=request,
                tags=(
                    "runtime-release",
                    rollback_trigger.rollback_trigger_class_id,
                    "deferred-pending-rollback-trigger-evidence",
                ),
            )

        if status == "fallback_template_applied":
            self._emit(
                event_type="runtime.release.rollback_trigger_fallback_template_applied",
                payload=payload,
                request=request,
                tags=(
                    "runtime-release",
                    rollback_trigger.rollback_trigger_class_id,
                    "fallback-template",
                ),
            )

    def _emit(
        self,
        *,
        event_type: str,
        payload: dict[str, object],
        request: "RollbackTriggerGuardRequest",
        tags: tuple[str, ...],
    ) -> None:
        self._audit_event_store.record_event(
            event_type=event_type,
            owner="runtime.release.rollback_trigger_audit_adapter",
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.rollout_scope.episode_id,
            actor_id=request.actor_id,
            payload=payload,
            tags=tags,
        )