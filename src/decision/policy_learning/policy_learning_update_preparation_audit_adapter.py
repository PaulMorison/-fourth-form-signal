from __future__ import annotations

"""Structured audit emission for governed policy-learning update preparation.

Canon ownership:
- Emits explicit update-preparation recorded, blocked, prepared,
  prepared-with-restrictions, deferred, rejected, missing-context,
  prohibited-overlap, and fallback audit events.
- Keeps policy mutation, rollout, deployment, retraining, monitoring,
  reopen handling, and lifecycle meaning out of this slice.
"""

from typing import TYPE_CHECKING

from platform.audit.audit_event_store import AuditEventStore
from platform.validation.contract_schema_validator import ContractSchemaValidator

if TYPE_CHECKING:
    from decision.policy_learning.policy_learning_update_preparation_service import (
        PolicyLearningUpdatePreparationRecord,
        PolicyLearningUpdatePreparationRequest,
    )


class PolicyLearningUpdatePreparationAuditAdapter:
    """Emits governed audit events for policy-learning update preparation."""

    def __init__(
        self,
        *,
        audit_event_store: AuditEventStore,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._audit_event_store = audit_event_store
        self._contract_validator = contract_validator

    def record_policy_learning_update_preparation(
        self,
        policy_learning_update_preparation: "PolicyLearningUpdatePreparationRecord",
        *,
        request: "PolicyLearningUpdatePreparationRequest",
    ) -> None:
        payload = policy_learning_update_preparation.to_contract_dict()
        self._contract_validator.validate_or_raise(
            "policy_learning_update_preparation_record",
            payload,
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.policy_learning_update_approval.episode_id,
            actor_id=request.actor_id,
            emit_audit_events=False,
        )

        status = (
            policy_learning_update_preparation.policy_learning_update_preparation_status
        )
        if status in {
            "blocked_missing_context",
            "rejected_for_preparation_use",
            "prohibited_overlap_blocked",
        }:
            self._emit(
                event_type="decision.policy_learning.policy_learning_update_preparation_blocked",
                payload=payload,
                request=request,
                tags=(
                    "policy-learning",
                    policy_learning_update_preparation.policy_learning_update_preparation_class_id,
                    status,
                ),
            )
            if status == "blocked_missing_context":
                self._emit(
                    event_type="decision.policy_learning.policy_learning_update_preparation_missing_context",
                    payload=payload,
                    request=request,
                    tags=(
                        "policy-learning",
                        policy_learning_update_preparation.policy_learning_update_preparation_class_id,
                        "missing-context",
                    ),
                )
            if status == "rejected_for_preparation_use":
                self._emit(
                    event_type="decision.policy_learning.policy_learning_update_preparation_rejected_for_preparation_use",
                    payload=payload,
                    request=request,
                    tags=(
                        "policy-learning",
                        policy_learning_update_preparation.policy_learning_update_preparation_class_id,
                        "rejected-for-preparation-use",
                    ),
                )
            if status == "prohibited_overlap_blocked":
                self._emit(
                    event_type="decision.policy_learning.policy_learning_update_preparation_prohibited_overlap_blocked",
                    payload=payload,
                    request=request,
                    tags=(
                        "policy-learning",
                        policy_learning_update_preparation.policy_learning_update_preparation_class_id,
                        "prohibited-overlap",
                    ),
                )
            return

        self._emit(
            event_type="decision.policy_learning.policy_learning_update_preparation_recorded",
            payload=payload,
            request=request,
            tags=(
                "policy-learning",
                policy_learning_update_preparation.policy_learning_update_preparation_class_id,
                "recorded",
            ),
        )

        outcome = (
            policy_learning_update_preparation.policy_learning_update_preparation_outcome
        )
        if outcome == "prepared_for_policy_mutation_planning":
            self._emit(
                event_type="decision.policy_learning.policy_learning_update_preparation_prepared_for_policy_mutation_planning",
                payload=payload,
                request=request,
                tags=(
                    "policy-learning",
                    policy_learning_update_preparation.policy_learning_update_preparation_class_id,
                    "prepared-for-policy-mutation-planning",
                ),
            )
        elif outcome == "prepared_with_restrictions":
            self._emit(
                event_type="decision.policy_learning.policy_learning_update_preparation_prepared_with_restrictions",
                payload=payload,
                request=request,
                tags=(
                    "policy-learning",
                    policy_learning_update_preparation.policy_learning_update_preparation_class_id,
                    "prepared-with-restrictions",
                ),
            )
        elif outcome == "deferred_pending_preparation_prerequisites":
            self._emit(
                event_type="decision.policy_learning.policy_learning_update_preparation_deferred_pending_preparation_prerequisites",
                payload=payload,
                request=request,
                tags=(
                    "policy-learning",
                    policy_learning_update_preparation.policy_learning_update_preparation_class_id,
                    "deferred-pending-preparation-prerequisites",
                ),
            )

        if status == "fallback_template_applied":
            self._emit(
                event_type="decision.policy_learning.policy_learning_update_preparation_fallback_template_applied",
                payload=payload,
                request=request,
                tags=(
                    "policy-learning",
                    policy_learning_update_preparation.policy_learning_update_preparation_class_id,
                    "fallback-template",
                ),
            )

    def _emit(
        self,
        *,
        event_type: str,
        payload: dict[str, object],
        request: "PolicyLearningUpdatePreparationRequest",
        tags: tuple[str, ...],
    ) -> None:
        self._audit_event_store.record_event(
            event_type=event_type,
            owner=(
                "decision.policy_learning.policy_learning_update_preparation_audit_adapter"
            ),
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.policy_learning_update_approval.episode_id,
            actor_id=request.actor_id,
            payload=payload,
            tags=tags,
        )