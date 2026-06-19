from __future__ import annotations

"""Structured audit emission for governed release confirmation.

Canon ownership:
- Emits explicit release-confirmation recorded, blocked, confirmed,
  conditional, deferred, rejected, missing-context, prohibited-overlap, and
  fallback audit events.
- Keeps release-watch execution, observation capture, rollback execution,
  monitoring, reopen handling, and lifecycle meaning out of this slice.
"""

from typing import TYPE_CHECKING

from ff_platform.audit.audit_event_store import AuditEventStore
from ff_platform.validation.contract_schema_validator import ContractSchemaValidator

if TYPE_CHECKING:
    from runtime.release.release_confirmation import (
        ReleaseConfirmationRecord,
        ReleaseConfirmationRequest,
    )


class ReleaseConfirmationAuditAdapter:
    """Emits governed audit events for release confirmation."""

    def __init__(
        self,
        *,
        audit_event_store: AuditEventStore,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._audit_event_store = audit_event_store
        self._contract_validator = contract_validator

    def record_release_confirmation(
        self,
        release_confirmation: "ReleaseConfirmationRecord",
        *,
        request: "ReleaseConfirmationRequest",
    ) -> None:
        payload = release_confirmation.to_contract_dict()
        self._contract_validator.validate_or_raise(
            "release_confirmation_record",
            payload,
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.release_watch_discipline.episode_id,
            actor_id=request.actor_id,
            emit_audit_events=False,
        )

        status = release_confirmation.release_confirmation_status
        if status in {
            "blocked_missing_context",
            "rejected_for_release_confirmation_use",
            "prohibited_overlap_blocked",
        }:
            self._emit(
                event_type="runtime.release.release_confirmation_blocked",
                payload=payload,
                request=request,
                tags=(
                    "runtime-release",
                    release_confirmation.release_confirmation_class_id,
                    status,
                ),
            )
            if status == "blocked_missing_context":
                self._emit(
                    event_type="runtime.release.release_confirmation_missing_context",
                    payload=payload,
                    request=request,
                    tags=(
                        "runtime-release",
                        release_confirmation.release_confirmation_class_id,
                        "missing-context",
                    ),
                )
            if status == "rejected_for_release_confirmation_use":
                self._emit(
                    event_type=(
                        "runtime.release.release_confirmation_rejected_for_release_confirmation_use"
                    ),
                    payload=payload,
                    request=request,
                    tags=(
                        "runtime-release",
                        release_confirmation.release_confirmation_class_id,
                        "rejected-for-release-confirmation-use",
                    ),
                )
            if status == "prohibited_overlap_blocked":
                self._emit(
                    event_type=(
                        "runtime.release.release_confirmation_prohibited_overlap_blocked"
                    ),
                    payload=payload,
                    request=request,
                    tags=(
                        "runtime-release",
                        release_confirmation.release_confirmation_class_id,
                        "prohibited-overlap",
                    ),
                )
            return

        self._emit(
            event_type="runtime.release.release_confirmation_recorded",
            payload=payload,
            request=request,
            tags=(
                "runtime-release",
                release_confirmation.release_confirmation_class_id,
                "recorded",
            ),
        )

        outcome = release_confirmation.release_confirmation_outcome
        if outcome == "confirmed_for_broader_trusted_production_use":
            self._emit(
                event_type=(
                    "runtime.release.release_confirmation_confirmed_for_broader_trusted_production_use"
                ),
                payload=payload,
                request=request,
                tags=(
                    "runtime-release",
                    release_confirmation.release_confirmation_class_id,
                    "confirmed-for-broader-trusted-production-use",
                ),
            )
        elif outcome == "conditionally_confirmed_for_bounded_production_use":
            self._emit(
                event_type=(
                    "runtime.release.release_confirmation_conditionally_confirmed_for_bounded_production_use"
                ),
                payload=payload,
                request=request,
                tags=(
                    "runtime-release",
                    release_confirmation.release_confirmation_class_id,
                    "conditionally-confirmed-for-bounded-production-use",
                ),
            )
        elif outcome == "deferred_pending_release_confirmation_evidence":
            self._emit(
                event_type=(
                    "runtime.release.release_confirmation_deferred_pending_release_confirmation_evidence"
                ),
                payload=payload,
                request=request,
                tags=(
                    "runtime-release",
                    release_confirmation.release_confirmation_class_id,
                    "deferred-pending-release-confirmation-evidence",
                ),
            )

        if status == "fallback_template_applied":
            self._emit(
                event_type=(
                    "runtime.release.release_confirmation_fallback_template_applied"
                ),
                payload=payload,
                request=request,
                tags=(
                    "runtime-release",
                    release_confirmation.release_confirmation_class_id,
                    "fallback-template",
                ),
            )

    def _emit(
        self,
        *,
        event_type: str,
        payload: dict[str, object],
        request: "ReleaseConfirmationRequest",
        tags: tuple[str, ...],
    ) -> None:
        self._audit_event_store.record_event(
            event_type=event_type,
            owner="runtime.release.release_confirmation_audit_adapter",
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.release_watch_discipline.episode_id,
            actor_id=request.actor_id,
            payload=payload,
            tags=tags,
        )