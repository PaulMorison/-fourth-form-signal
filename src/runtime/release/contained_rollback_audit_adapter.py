from __future__ import annotations

"""Structured audit emission for governed contained rollback.

Canon ownership:
- Emits explicit contained-rollback recorded, blocked, bounded, partial-reversal,
  deferred, rejected, missing-context, prohibited-overlap, and fallback audit
  events.
- Keeps rollback execution, release closure, monitoring admission, runtime
  verification, reopen handling, and lifecycle meaning out of this slice.
"""

from typing import TYPE_CHECKING

from platform.audit.audit_event_store import AuditEventStore
from platform.validation.contract_schema_validator import ContractSchemaValidator

if TYPE_CHECKING:
    from runtime.release.contained_rollback import (
        ContainedRollbackRecord,
        ContainedRollbackRequest,
    )


class ContainedRollbackAuditAdapter:
    """Emits governed audit events for contained rollback."""

    def __init__(
        self,
        *,
        audit_event_store: AuditEventStore,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._audit_event_store = audit_event_store
        self._contract_validator = contract_validator

    def record_contained_rollback(
        self,
        contained_rollback: "ContainedRollbackRecord",
        *,
        request: "ContainedRollbackRequest",
    ) -> None:
        payload = contained_rollback.to_contract_dict()
        self._contract_validator.validate_or_raise(
            "contained_rollback_record",
            payload,
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.production_entitlement_check.episode_id,
            actor_id=request.actor_id,
            emit_audit_events=False,
        )

        status = contained_rollback.contained_rollback_status
        if status in {
            "blocked_missing_context",
            "rejected_for_contained_rollback_use",
            "prohibited_overlap_blocked",
        }:
            self._emit(
                event_type="runtime.release.contained_rollback_blocked",
                payload=payload,
                request=request,
                tags=(
                    "runtime-release",
                    contained_rollback.contained_rollback_class_id,
                    status,
                ),
            )
            if status == "blocked_missing_context":
                self._emit(
                    event_type="runtime.release.contained_rollback_missing_context",
                    payload=payload,
                    request=request,
                    tags=(
                        "runtime-release",
                        contained_rollback.contained_rollback_class_id,
                        "missing-context",
                    ),
                )
            if status == "rejected_for_contained_rollback_use":
                self._emit(
                    event_type=(
                        "runtime.release.contained_rollback_rejected_for_contained_rollback_use"
                    ),
                    payload=payload,
                    request=request,
                    tags=(
                        "runtime-release",
                        contained_rollback.contained_rollback_class_id,
                        "rejected-for-contained-rollback-use",
                    ),
                )
            if status == "prohibited_overlap_blocked":
                self._emit(
                    event_type=(
                        "runtime.release.contained_rollback_prohibited_overlap_blocked"
                    ),
                    payload=payload,
                    request=request,
                    tags=(
                        "runtime-release",
                        contained_rollback.contained_rollback_class_id,
                        "prohibited-overlap",
                    ),
                )
            return

        self._emit(
            event_type="runtime.release.contained_rollback_recorded",
            payload=payload,
            request=request,
            tags=(
                "runtime-release",
                contained_rollback.contained_rollback_class_id,
                "recorded",
            ),
        )

        outcome = contained_rollback.contained_rollback_outcome
        if outcome == "bounded_exposure_preserved":
            self._emit(
                event_type=(
                    "runtime.release.contained_rollback_bounded_exposure_preserved"
                ),
                payload=payload,
                request=request,
                tags=(
                    "runtime-release",
                    contained_rollback.contained_rollback_class_id,
                    "bounded-exposure-preserved",
                ),
            )
        elif outcome == "partial_reversal_bounded":
            self._emit(
                event_type=(
                    "runtime.release.contained_rollback_partial_reversal_bounded"
                ),
                payload=payload,
                request=request,
                tags=(
                    "runtime-release",
                    contained_rollback.contained_rollback_class_id,
                    "partial-reversal-bounded",
                ),
            )
        elif outcome == "deferred_pending_contained_rollback_evidence":
            self._emit(
                event_type=(
                    "runtime.release.contained_rollback_deferred_pending_contained_rollback_evidence"
                ),
                payload=payload,
                request=request,
                tags=(
                    "runtime-release",
                    contained_rollback.contained_rollback_class_id,
                    "deferred-pending-contained-rollback-evidence",
                ),
            )

        if status == "fallback_template_applied":
            self._emit(
                event_type=(
                    "runtime.release.contained_rollback_fallback_template_applied"
                ),
                payload=payload,
                request=request,
                tags=(
                    "runtime-release",
                    contained_rollback.contained_rollback_class_id,
                    "fallback-template",
                ),
            )

    def _emit(
        self,
        *,
        event_type: str,
        payload: dict[str, object],
        request: "ContainedRollbackRequest",
        tags: tuple[str, ...],
    ) -> None:
        self._audit_event_store.record_event(
            event_type=event_type,
            owner="runtime.release.contained_rollback_audit_adapter",
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.production_entitlement_check.episode_id,
            actor_id=request.actor_id,
            payload=payload,
            tags=tags,
        )
