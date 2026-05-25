from __future__ import annotations

"""Structured audit emission for governed promotion readiness.

Canon ownership:
- Emits explicit promotion-readiness recorded, blocked, ready, conditional,
  deferred, rejected, missing-context, prohibited-overlap, and fallback audit
  events.
- Keeps rollout-scope control, rollback-trigger control, post-release watch
  execution, monitoring, reopen handling, and lifecycle meaning out of this
  slice.
"""

from typing import TYPE_CHECKING

from platform.audit.audit_event_store import AuditEventStore
from platform.validation.contract_schema_validator import ContractSchemaValidator

if TYPE_CHECKING:
    from runtime.release.promotion_readiness_gate import (
        PromotionReadinessGateRequest,
        PromotionReadinessRecord,
    )


class PromotionReadinessAuditAdapter:
    """Emits governed audit events for promotion readiness."""

    def __init__(
        self,
        *,
        audit_event_store: AuditEventStore,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._audit_event_store = audit_event_store
        self._contract_validator = contract_validator

    def record_promotion_readiness(
        self,
        promotion_readiness: "PromotionReadinessRecord",
        *,
        request: "PromotionReadinessGateRequest",
    ) -> None:
        payload = promotion_readiness.to_contract_dict()
        self._contract_validator.validate_or_raise(
            "promotion_readiness_record",
            payload,
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.policy_learning_update_mutation_execution.episode_id,
            actor_id=request.actor_id,
            emit_audit_events=False,
        )

        status = promotion_readiness.promotion_readiness_status
        if status in {
            "blocked_missing_context",
            "rejected_for_promotion_use",
            "prohibited_overlap_blocked",
        }:
            self._emit(
                event_type="runtime.release.promotion_readiness_blocked",
                payload=payload,
                request=request,
                tags=(
                    "runtime-release",
                    promotion_readiness.promotion_readiness_class_id,
                    status,
                ),
            )
            if status == "blocked_missing_context":
                self._emit(
                    event_type="runtime.release.promotion_readiness_missing_context",
                    payload=payload,
                    request=request,
                    tags=(
                        "runtime-release",
                        promotion_readiness.promotion_readiness_class_id,
                        "missing-context",
                    ),
                )
            if status == "rejected_for_promotion_use":
                self._emit(
                    event_type="runtime.release.promotion_readiness_rejected_for_promotion_use",
                    payload=payload,
                    request=request,
                    tags=(
                        "runtime-release",
                        promotion_readiness.promotion_readiness_class_id,
                        "rejected-for-promotion-use",
                    ),
                )
            if status == "prohibited_overlap_blocked":
                self._emit(
                    event_type="runtime.release.promotion_readiness_prohibited_overlap_blocked",
                    payload=payload,
                    request=request,
                    tags=(
                        "runtime-release",
                        promotion_readiness.promotion_readiness_class_id,
                        "prohibited-overlap",
                    ),
                )
            return

        self._emit(
            event_type="runtime.release.promotion_readiness_recorded",
            payload=payload,
            request=request,
            tags=(
                "runtime-release",
                promotion_readiness.promotion_readiness_class_id,
                "recorded",
            ),
        )

        outcome = promotion_readiness.promotion_readiness_outcome
        if outcome == "ready_for_rollout_scope_control":
            self._emit(
                event_type="runtime.release.promotion_readiness_ready_for_rollout_scope_control",
                payload=payload,
                request=request,
                tags=(
                    "runtime-release",
                    promotion_readiness.promotion_readiness_class_id,
                    "ready-for-rollout-scope-control",
                ),
            )
        elif outcome == "conditionally_ready_for_rollout_scope_control":
            self._emit(
                event_type="runtime.release.promotion_readiness_conditionally_ready_for_rollout_scope_control",
                payload=payload,
                request=request,
                tags=(
                    "runtime-release",
                    promotion_readiness.promotion_readiness_class_id,
                    "conditionally-ready-for-rollout-scope-control",
                ),
            )
        elif outcome == "deferred_pending_promotion_readiness_evidence":
            self._emit(
                event_type="runtime.release.promotion_readiness_deferred_pending_promotion_readiness_evidence",
                payload=payload,
                request=request,
                tags=(
                    "runtime-release",
                    promotion_readiness.promotion_readiness_class_id,
                    "deferred-pending-promotion-readiness-evidence",
                ),
            )

        if status == "fallback_template_applied":
            self._emit(
                event_type="runtime.release.promotion_readiness_fallback_template_applied",
                payload=payload,
                request=request,
                tags=(
                    "runtime-release",
                    promotion_readiness.promotion_readiness_class_id,
                    "fallback-template",
                ),
            )

    def _emit(
        self,
        *,
        event_type: str,
        payload: dict[str, object],
        request: "PromotionReadinessGateRequest",
        tags: tuple[str, ...],
    ) -> None:
        self._audit_event_store.record_event(
            event_type=event_type,
            owner="runtime.release.promotion_readiness_audit_adapter",
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.policy_learning_update_mutation_execution.episode_id,
            actor_id=request.actor_id,
            payload=payload,
            tags=tags,
        )
