from __future__ import annotations

"""Structured audit emission for governed release-watch discipline.

Canon ownership:
- Emits explicit release-watch-discipline recorded, blocked, ready,
  conditional, deferred, rejected, missing-context, prohibited-overlap, and
  fallback audit events.
- Keeps post-release watch execution, release confirmation judgment, rollback
  execution, monitoring, reopen handling, and lifecycle meaning out of this
  slice.
"""

from typing import TYPE_CHECKING

from platform.audit.audit_event_store import AuditEventStore
from platform.validation.contract_schema_validator import ContractSchemaValidator

if TYPE_CHECKING:
    from runtime.release.release_watch_discipline import (
        ReleaseWatchDisciplineRecord,
        ReleaseWatchDisciplineRequest,
    )


class ReleaseWatchDisciplineAuditAdapter:
    """Emits governed audit events for release-watch discipline."""

    def __init__(
        self,
        *,
        audit_event_store: AuditEventStore,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._audit_event_store = audit_event_store
        self._contract_validator = contract_validator

    def record_release_watch_discipline(
        self,
        release_watch_discipline: "ReleaseWatchDisciplineRecord",
        *,
        request: "ReleaseWatchDisciplineRequest",
    ) -> None:
        payload = release_watch_discipline.to_contract_dict()
        self._contract_validator.validate_or_raise(
            "release_watch_discipline_record",
            payload,
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.rollback_trigger.episode_id,
            actor_id=request.actor_id,
            emit_audit_events=False,
        )

        status = release_watch_discipline.release_watch_discipline_status
        if status in {
            "blocked_missing_context",
            "rejected_for_release_watch_discipline_use",
            "prohibited_overlap_blocked",
        }:
            self._emit(
                event_type="runtime.release.release_watch_discipline_blocked",
                payload=payload,
                request=request,
                tags=(
                    "runtime-release",
                    release_watch_discipline.release_watch_discipline_class_id,
                    status,
                ),
            )
            if status == "blocked_missing_context":
                self._emit(
                    event_type=(
                        "runtime.release.release_watch_discipline_missing_context"
                    ),
                    payload=payload,
                    request=request,
                    tags=(
                        "runtime-release",
                        release_watch_discipline.release_watch_discipline_class_id,
                        "missing-context",
                    ),
                )
            if status == "rejected_for_release_watch_discipline_use":
                self._emit(
                    event_type=(
                        "runtime.release.release_watch_discipline_rejected_for_release_watch_discipline_use"
                    ),
                    payload=payload,
                    request=request,
                    tags=(
                        "runtime-release",
                        release_watch_discipline.release_watch_discipline_class_id,
                        "rejected-for-release-watch-discipline-use",
                    ),
                )
            if status == "prohibited_overlap_blocked":
                self._emit(
                    event_type=(
                        "runtime.release.release_watch_discipline_prohibited_overlap_blocked"
                    ),
                    payload=payload,
                    request=request,
                    tags=(
                        "runtime-release",
                        release_watch_discipline.release_watch_discipline_class_id,
                        "prohibited-overlap",
                    ),
                )
            return

        self._emit(
            event_type="runtime.release.release_watch_discipline_recorded",
            payload=payload,
            request=request,
            tags=(
                "runtime-release",
                release_watch_discipline.release_watch_discipline_class_id,
                "recorded",
            ),
        )

        outcome = release_watch_discipline.release_watch_discipline_outcome
        if outcome == "ready_for_release_confirmation":
            self._emit(
                event_type=(
                    "runtime.release.release_watch_discipline_ready_for_release_confirmation"
                ),
                payload=payload,
                request=request,
                tags=(
                    "runtime-release",
                    release_watch_discipline.release_watch_discipline_class_id,
                    "ready-for-release-confirmation",
                ),
            )
        elif outcome == "conditionally_ready_for_release_confirmation":
            self._emit(
                event_type=(
                    "runtime.release.release_watch_discipline_conditionally_ready_for_release_confirmation"
                ),
                payload=payload,
                request=request,
                tags=(
                    "runtime-release",
                    release_watch_discipline.release_watch_discipline_class_id,
                    "conditionally-ready-for-release-confirmation",
                ),
            )
        elif outcome == "deferred_pending_release_watch_discipline_evidence":
            self._emit(
                event_type=(
                    "runtime.release.release_watch_discipline_deferred_pending_release_watch_discipline_evidence"
                ),
                payload=payload,
                request=request,
                tags=(
                    "runtime-release",
                    release_watch_discipline.release_watch_discipline_class_id,
                    "deferred-pending-release-watch-discipline-evidence",
                ),
            )

        if status == "fallback_template_applied":
            self._emit(
                event_type=(
                    "runtime.release.release_watch_discipline_fallback_template_applied"
                ),
                payload=payload,
                request=request,
                tags=(
                    "runtime-release",
                    release_watch_discipline.release_watch_discipline_class_id,
                    "fallback-template",
                ),
            )

    def _emit(
        self,
        *,
        event_type: str,
        payload: dict[str, object],
        request: "ReleaseWatchDisciplineRequest",
        tags: tuple[str, ...],
    ) -> None:
        self._audit_event_store.record_event(
            event_type=event_type,
            owner="runtime.release.release_watch_discipline_audit_adapter",
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.rollback_trigger.episode_id,
            actor_id=request.actor_id,
            payload=payload,
            tags=tags,
        )