from __future__ import annotations

"""Structured audit emission for governed policy-learning update thresholds.

Canon ownership:
- Emits explicit update-threshold recorded, blocked, accepted, narrowed,
  deferred, rejected, missing-context, prohibited-overlap, and fallback audit
  events.
- Keeps policy mutation, model retraining, deployment, monitoring ownership,
  reopen handling, and lifecycle meaning out of this slice.
"""

from typing import TYPE_CHECKING

from platform.audit.audit_event_store import AuditEventStore
from platform.validation.contract_schema_validator import ContractSchemaValidator

if TYPE_CHECKING:
    from decision.policy_learning.policy_learning_update_threshold_service import (
        PolicyLearningUpdateThresholdRecord,
        PolicyLearningUpdateThresholdRequest,
    )


class PolicyLearningUpdateThresholdAuditAdapter:
    """Emits governed audit events for policy-learning update-threshold outcomes."""

    def __init__(
        self,
        *,
        audit_event_store: AuditEventStore,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._audit_event_store = audit_event_store
        self._contract_validator = contract_validator

    def record_policy_learning_update_threshold(
        self,
        policy_learning_update_threshold: "PolicyLearningUpdateThresholdRecord",
        *,
        request: "PolicyLearningUpdateThresholdRequest",
    ) -> None:
        payload = policy_learning_update_threshold.to_contract_dict()
        self._contract_validator.validate_or_raise(
            "policy_learning_update_threshold_record",
            payload,
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.policy_learning_evidence_admission.episode_id,
            actor_id=request.actor_id,
            emit_audit_events=False,
        )

        status = policy_learning_update_threshold.policy_learning_update_threshold_status
        if status in {
            "blocked_missing_context",
            "blocked_below_threshold",
            "prohibited_overlap_blocked",
        }:
            self._emit(
                event_type="decision.policy_learning.policy_learning_update_threshold_blocked",
                payload=payload,
                request=request,
                tags=(
                    "policy-learning",
                    policy_learning_update_threshold.policy_learning_update_threshold_class_id,
                    status,
                ),
            )
            if status == "blocked_missing_context":
                self._emit(
                    event_type="decision.policy_learning.policy_learning_update_threshold_missing_context",
                    payload=payload,
                    request=request,
                    tags=(
                        "policy-learning",
                        policy_learning_update_threshold.policy_learning_update_threshold_class_id,
                        "missing-context",
                    ),
                )
            if status == "blocked_below_threshold":
                self._emit(
                    event_type="decision.policy_learning.policy_learning_update_threshold_rejected",
                    payload=payload,
                    request=request,
                    tags=(
                        "policy-learning",
                        policy_learning_update_threshold.policy_learning_update_threshold_class_id,
                        "rejected",
                    ),
                )
            if status == "prohibited_overlap_blocked":
                self._emit(
                    event_type="decision.policy_learning.policy_learning_update_threshold_prohibited_overlap_blocked",
                    payload=payload,
                    request=request,
                    tags=(
                        "policy-learning",
                        policy_learning_update_threshold.policy_learning_update_threshold_class_id,
                        "prohibited-overlap",
                    ),
                )
            return

        self._emit(
            event_type="decision.policy_learning.policy_learning_update_threshold_recorded",
            payload=payload,
            request=request,
            tags=(
                "policy-learning",
                policy_learning_update_threshold.policy_learning_update_threshold_class_id,
                "recorded",
            ),
        )

        outcome = policy_learning_update_threshold.policy_learning_update_decision_outcome
        if outcome == "accepted":
            self._emit(
                event_type="decision.policy_learning.policy_learning_update_threshold_accepted",
                payload=payload,
                request=request,
                tags=(
                    "policy-learning",
                    policy_learning_update_threshold.policy_learning_update_threshold_class_id,
                    "accepted",
                ),
            )
        elif outcome == "accepted_with_narrowed_scope":
            self._emit(
                event_type=(
                    "decision.policy_learning.policy_learning_update_threshold_accepted_with_narrowed_scope"
                ),
                payload=payload,
                request=request,
                tags=(
                    "policy-learning",
                    policy_learning_update_threshold.policy_learning_update_threshold_class_id,
                    "accepted-with-narrowed-scope",
                ),
            )
        elif outcome == "deferred_for_continued_monitoring":
            self._emit(
                event_type=(
                    "decision.policy_learning.policy_learning_update_threshold_deferred_for_continued_monitoring"
                ),
                payload=payload,
                request=request,
                tags=(
                    "policy-learning",
                    policy_learning_update_threshold.policy_learning_update_threshold_class_id,
                    "deferred-for-continued-monitoring",
                ),
            )

        if status == "fallback_template_applied":
            self._emit(
                event_type=(
                    "decision.policy_learning.policy_learning_update_threshold_fallback_template_applied"
                ),
                payload=payload,
                request=request,
                tags=(
                    "policy-learning",
                    policy_learning_update_threshold.policy_learning_update_threshold_class_id,
                    "fallback-template",
                ),
            )

    def _emit(
        self,
        *,
        event_type: str,
        payload: dict[str, object],
        request: "PolicyLearningUpdateThresholdRequest",
        tags: tuple[str, ...],
    ) -> None:
        self._audit_event_store.record_event(
            event_type=event_type,
            owner=(
                "decision.policy_learning.policy_learning_update_threshold_audit_adapter"
            ),
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.policy_learning_evidence_admission.episode_id,
            actor_id=request.actor_id,
            payload=payload,
            tags=tags,
        )
