from __future__ import annotations

"""Structured audit emission for governed policy-learning update approval.

Canon ownership:
- Emits explicit update-approval recorded, blocked, approved,
  approved-with-restrictions, deferred, rejected, missing-context,
  prohibited-overlap, and fallback audit events.
- Keeps policy mutation, rollout, deployment, retraining, monitoring,
  reopen handling, and lifecycle meaning out of this slice.
"""

from typing import TYPE_CHECKING

from platform.audit.audit_event_store import AuditEventStore
from platform.validation.contract_schema_validator import ContractSchemaValidator

if TYPE_CHECKING:
    from decision.policy_learning.policy_learning_update_approval_service import (
        PolicyLearningUpdateApprovalRecord,
        PolicyLearningUpdateApprovalRequest,
    )


class PolicyLearningUpdateApprovalAuditAdapter:
    """Emits governed audit events for policy-learning update approval."""

    def __init__(
        self,
        *,
        audit_event_store: AuditEventStore,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._audit_event_store = audit_event_store
        self._contract_validator = contract_validator

    def record_policy_learning_update_approval(
        self,
        policy_learning_update_approval: "PolicyLearningUpdateApprovalRecord",
        *,
        request: "PolicyLearningUpdateApprovalRequest",
    ) -> None:
        payload = policy_learning_update_approval.to_contract_dict()
        self._contract_validator.validate_or_raise(
            "policy_learning_update_approval_record",
            payload,
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.policy_learning_update_threshold.episode_id,
            actor_id=request.actor_id,
            emit_audit_events=False,
        )

        status = policy_learning_update_approval.policy_learning_update_approval_status
        if status in {
            "blocked_missing_context",
            "rejected_for_policy_update_use",
            "prohibited_overlap_blocked",
        }:
            self._emit(
                event_type="decision.policy_learning.policy_learning_update_approval_blocked",
                payload=payload,
                request=request,
                tags=(
                    "policy-learning",
                    policy_learning_update_approval.policy_learning_update_approval_class_id,
                    status,
                ),
            )
            if status == "blocked_missing_context":
                self._emit(
                    event_type="decision.policy_learning.policy_learning_update_approval_missing_context",
                    payload=payload,
                    request=request,
                    tags=(
                        "policy-learning",
                        policy_learning_update_approval.policy_learning_update_approval_class_id,
                        "missing-context",
                    ),
                )
            if status == "rejected_for_policy_update_use":
                self._emit(
                    event_type="decision.policy_learning.policy_learning_update_approval_rejected_for_policy_update_use",
                    payload=payload,
                    request=request,
                    tags=(
                        "policy-learning",
                        policy_learning_update_approval.policy_learning_update_approval_class_id,
                        "rejected-for-policy-update-use",
                    ),
                )
            if status == "prohibited_overlap_blocked":
                self._emit(
                    event_type="decision.policy_learning.policy_learning_update_approval_prohibited_overlap_blocked",
                    payload=payload,
                    request=request,
                    tags=(
                        "policy-learning",
                        policy_learning_update_approval.policy_learning_update_approval_class_id,
                        "prohibited-overlap",
                    ),
                )
            return

        self._emit(
            event_type="decision.policy_learning.policy_learning_update_approval_recorded",
            payload=payload,
            request=request,
            tags=(
                "policy-learning",
                policy_learning_update_approval.policy_learning_update_approval_class_id,
                "recorded",
            ),
        )

        outcome = policy_learning_update_approval.policy_learning_update_approval_outcome
        if outcome == "approved_for_policy_update_preparation":
            self._emit(
                event_type="decision.policy_learning.policy_learning_update_approval_approved_for_policy_update_preparation",
                payload=payload,
                request=request,
                tags=(
                    "policy-learning",
                    policy_learning_update_approval.policy_learning_update_approval_class_id,
                    "approved-for-policy-update-preparation",
                ),
            )
        elif outcome == "approved_with_restrictions":
            self._emit(
                event_type="decision.policy_learning.policy_learning_update_approval_approved_with_restrictions",
                payload=payload,
                request=request,
                tags=(
                    "policy-learning",
                    policy_learning_update_approval.policy_learning_update_approval_class_id,
                    "approved-with-restrictions",
                ),
            )
        elif outcome == "deferred_pending_additional_governance":
            self._emit(
                event_type="decision.policy_learning.policy_learning_update_approval_deferred_pending_additional_governance",
                payload=payload,
                request=request,
                tags=(
                    "policy-learning",
                    policy_learning_update_approval.policy_learning_update_approval_class_id,
                    "deferred-pending-additional-governance",
                ),
            )

        if status == "fallback_template_applied":
            self._emit(
                event_type="decision.policy_learning.policy_learning_update_approval_fallback_template_applied",
                payload=payload,
                request=request,
                tags=(
                    "policy-learning",
                    policy_learning_update_approval.policy_learning_update_approval_class_id,
                    "fallback-template",
                ),
            )

    def _emit(
        self,
        *,
        event_type: str,
        payload: dict[str, object],
        request: "PolicyLearningUpdateApprovalRequest",
        tags: tuple[str, ...],
    ) -> None:
        self._audit_event_store.record_event(
            event_type=event_type,
            owner=(
                "decision.policy_learning.policy_learning_update_approval_audit_adapter"
            ),
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.policy_learning_update_threshold.episode_id,
            actor_id=request.actor_id,
            payload=payload,
            tags=tags,
        )
