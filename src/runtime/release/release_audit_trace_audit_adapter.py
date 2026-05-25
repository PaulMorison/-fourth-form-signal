from __future__ import annotations

"""Structured audit emission for governed release audit trace.

Canon ownership:
- Emits explicit release-audit-trace recorded, blocked, lineage-preserved,
  invalid-release-state-visible, invalid-exposure-visible,
  no-silent-promotion-preserved, deferred, rejected, missing-context,
  prohibited-overlap, and fallback audit events.
- Keeps release closure or final disposition meaning, runtime verification,
  monitoring admission, reopen handling, orchestration meaning, and lifecycle
  meaning out of this slice.
"""

from typing import TYPE_CHECKING

from platform.audit.audit_event_store import AuditEventStore
from platform.validation.contract_schema_validator import ContractSchemaValidator

if TYPE_CHECKING:
    from runtime.release.release_audit_trace import (
        ReleaseAuditTraceRecord,
        ReleaseAuditTraceRequest,
    )


class ReleaseAuditTraceAuditAdapter:
    """Emits governed audit events for release audit trace."""

    def __init__(
        self,
        *,
        audit_event_store: AuditEventStore,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._audit_event_store = audit_event_store
        self._contract_validator = contract_validator

    def record_release_audit_trace(
        self,
        release_audit_trace: "ReleaseAuditTraceRecord",
        *,
        request: "ReleaseAuditTraceRequest",
    ) -> None:
        payload = release_audit_trace.to_contract_dict()
        self._contract_validator.validate_or_raise(
            "release_audit_trace_record",
            payload,
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.contained_rollback.episode_id,
            actor_id=request.actor_id,
            emit_audit_events=False,
        )

        status = release_audit_trace.release_audit_trace_status
        if status in {
            "blocked_missing_context",
            "rejected_for_release_audit_trace_use",
            "prohibited_overlap_blocked",
        }:
            self._emit(
                event_type="runtime.release.release_audit_trace_blocked",
                payload=payload,
                request=request,
                tags=(
                    "runtime-release",
                    release_audit_trace.release_audit_trace_class_id,
                    status,
                ),
            )
            if status == "blocked_missing_context":
                self._emit(
                    event_type=(
                        "runtime.release.release_audit_trace_missing_context"
                    ),
                    payload=payload,
                    request=request,
                    tags=(
                        "runtime-release",
                        release_audit_trace.release_audit_trace_class_id,
                        "missing-context",
                    ),
                )
            if status == "rejected_for_release_audit_trace_use":
                self._emit(
                    event_type=(
                        "runtime.release.release_audit_trace_rejected_for_release_audit_trace_use"
                    ),
                    payload=payload,
                    request=request,
                    tags=(
                        "runtime-release",
                        release_audit_trace.release_audit_trace_class_id,
                        "rejected-for-release-audit-trace-use",
                    ),
                )
            if status == "prohibited_overlap_blocked":
                self._emit(
                    event_type=(
                        "runtime.release.release_audit_trace_prohibited_overlap_blocked"
                    ),
                    payload=payload,
                    request=request,
                    tags=(
                        "runtime-release",
                        release_audit_trace.release_audit_trace_class_id,
                        "prohibited-overlap",
                    ),
                )
            return

        self._emit(
            event_type="runtime.release.release_audit_trace_recorded",
            payload=payload,
            request=request,
            tags=(
                "runtime-release",
                release_audit_trace.release_audit_trace_class_id,
                "recorded",
            ),
        )
        self._emit(
            event_type=(
                "runtime.release.release_audit_trace_release_control_lineage_preserved"
            ),
            payload=payload,
            request=request,
            tags=(
                "runtime-release",
                release_audit_trace.release_audit_trace_class_id,
                "lineage-preserved",
            ),
        )
        self._emit(
            event_type=(
                "runtime.release.release_audit_trace_invalid_release_state_visible"
            ),
            payload=payload,
            request=request,
            tags=(
                "runtime-release",
                release_audit_trace.release_audit_trace_class_id,
                "invalid-release-state-visible",
            ),
        )
        self._emit(
            event_type=(
                "runtime.release.release_audit_trace_invalid_exposure_visible"
            ),
            payload=payload,
            request=request,
            tags=(
                "runtime-release",
                release_audit_trace.release_audit_trace_class_id,
                "invalid-exposure-visible",
            ),
        )
        self._emit(
            event_type=(
                "runtime.release.release_audit_trace_no_silent_promotion_preserved"
            ),
            payload=payload,
            request=request,
            tags=(
                "runtime-release",
                release_audit_trace.release_audit_trace_class_id,
                "no-silent-promotion-preserved",
            ),
        )

        if (
            release_audit_trace.release_audit_trace_outcome
            == "deferred_pending_release_audit_trace_evidence"
        ):
            self._emit(
                event_type=(
                    "runtime.release.release_audit_trace_deferred_pending_release_audit_trace_evidence"
                ),
                payload=payload,
                request=request,
                tags=(
                    "runtime-release",
                    release_audit_trace.release_audit_trace_class_id,
                    "deferred-pending-release-audit-trace-evidence",
                ),
            )

        if status == "fallback_template_applied":
            self._emit(
                event_type=(
                    "runtime.release.release_audit_trace_fallback_template_applied"
                ),
                payload=payload,
                request=request,
                tags=(
                    "runtime-release",
                    release_audit_trace.release_audit_trace_class_id,
                    "fallback-template",
                ),
            )

    def _emit(
        self,
        *,
        event_type: str,
        payload: dict[str, object],
        request: "ReleaseAuditTraceRequest",
        tags: tuple[str, ...],
    ) -> None:
        self._audit_event_store.record_event(
            event_type=event_type,
            owner="runtime.release.release_audit_trace_audit_adapter",
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.contained_rollback.episode_id,
            actor_id=request.actor_id,
            payload=payload,
            tags=tags,
        )