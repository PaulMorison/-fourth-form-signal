from __future__ import annotations

"""Structured audit emission for governed production-entitlement checks.

Canon ownership:
- Emits explicit production-entitlement-check recorded, blocked, approved,
  conditional, deferred, rejected, missing-context, prohibited-overlap, and
  fallback audit events.
- Keeps contained rollback, rollback execution, release closure, monitoring
  admission, runtime verification, reopen handling, and lifecycle meaning out
  of this slice.
"""

from typing import TYPE_CHECKING

from platform.audit.audit_event_store import AuditEventStore
from platform.validation.contract_schema_validator import ContractSchemaValidator

if TYPE_CHECKING:
    from runtime.release.production_entitlement_check import (
        ProductionEntitlementCheckRecord,
        ProductionEntitlementCheckRequest,
    )


class ProductionEntitlementCheckAuditAdapter:
    """Emits governed audit events for production-entitlement checks."""

    def __init__(
        self,
        *,
        audit_event_store: AuditEventStore,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._audit_event_store = audit_event_store
        self._contract_validator = contract_validator

    def record_production_entitlement_check(
        self,
        production_entitlement_check: "ProductionEntitlementCheckRecord",
        *,
        request: "ProductionEntitlementCheckRequest",
    ) -> None:
        payload = production_entitlement_check.to_contract_dict()
        self._contract_validator.validate_or_raise(
            "production_entitlement_check_record",
            payload,
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.release_confirmation.episode_id,
            actor_id=request.actor_id,
            emit_audit_events=False,
        )

        status = production_entitlement_check.production_entitlement_check_status
        if status in {
            "blocked_missing_context",
            "rejected_for_production_entitlement_use",
            "prohibited_overlap_blocked",
        }:
            self._emit(
                event_type="runtime.release.production_entitlement_check_blocked",
                payload=payload,
                request=request,
                tags=(
                    "runtime-release",
                    production_entitlement_check.production_entitlement_check_class_id,
                    status,
                ),
            )
            if status == "blocked_missing_context":
                self._emit(
                    event_type=(
                        "runtime.release.production_entitlement_check_missing_context"
                    ),
                    payload=payload,
                    request=request,
                    tags=(
                        "runtime-release",
                        production_entitlement_check.production_entitlement_check_class_id,
                        "missing-context",
                    ),
                )
            if status == "rejected_for_production_entitlement_use":
                self._emit(
                    event_type=(
                        "runtime.release.production_entitlement_check_rejected_for_production_entitlement_use"
                    ),
                    payload=payload,
                    request=request,
                    tags=(
                        "runtime-release",
                        production_entitlement_check.production_entitlement_check_class_id,
                        "rejected-for-production-entitlement-use",
                    ),
                )
            if status == "prohibited_overlap_blocked":
                self._emit(
                    event_type=(
                        "runtime.release.production_entitlement_check_prohibited_overlap_blocked"
                    ),
                    payload=payload,
                    request=request,
                    tags=(
                        "runtime-release",
                        production_entitlement_check.production_entitlement_check_class_id,
                        "prohibited-overlap",
                    ),
                )
            return

        self._emit(
            event_type="runtime.release.production_entitlement_check_recorded",
            payload=payload,
            request=request,
            tags=(
                "runtime-release",
                production_entitlement_check.production_entitlement_check_class_id,
                "recorded",
            ),
        )

        outcome = production_entitlement_check.production_entitlement_check_outcome
        if outcome == "approved_for_broader_trusted_production_entitlement":
            self._emit(
                event_type=(
                    "runtime.release.production_entitlement_check_approved_for_broader_trusted_production_entitlement"
                ),
                payload=payload,
                request=request,
                tags=(
                    "runtime-release",
                    production_entitlement_check.production_entitlement_check_class_id,
                    "approved-for-broader-trusted-production-entitlement",
                ),
            )
        elif outcome == "conditionally_approved_for_bounded_production_entitlement":
            self._emit(
                event_type=(
                    "runtime.release.production_entitlement_check_conditionally_approved_for_bounded_production_entitlement"
                ),
                payload=payload,
                request=request,
                tags=(
                    "runtime-release",
                    production_entitlement_check.production_entitlement_check_class_id,
                    "conditionally-approved-for-bounded-production-entitlement",
                ),
            )
        elif outcome == "deferred_pending_production_entitlement_evidence":
            self._emit(
                event_type=(
                    "runtime.release.production_entitlement_check_deferred_pending_production_entitlement_evidence"
                ),
                payload=payload,
                request=request,
                tags=(
                    "runtime-release",
                    production_entitlement_check.production_entitlement_check_class_id,
                    "deferred-pending-production-entitlement-evidence",
                ),
            )

        if status == "fallback_template_applied":
            self._emit(
                event_type=(
                    "runtime.release.production_entitlement_check_fallback_template_applied"
                ),
                payload=payload,
                request=request,
                tags=(
                    "runtime-release",
                    production_entitlement_check.production_entitlement_check_class_id,
                    "fallback-template",
                ),
            )

    def _emit(
        self,
        *,
        event_type: str,
        payload: dict[str, object],
        request: "ProductionEntitlementCheckRequest",
        tags: tuple[str, ...],
    ) -> None:
        self._audit_event_store.record_event(
            event_type=event_type,
            owner="runtime.release.production_entitlement_check_audit_adapter",
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.release_confirmation.episode_id,
            actor_id=request.actor_id,
            payload=payload,
            tags=tags,
        )