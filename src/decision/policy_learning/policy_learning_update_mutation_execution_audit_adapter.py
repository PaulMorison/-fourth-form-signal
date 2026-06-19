from __future__ import annotations

"""Structured audit emission for governed policy-learning update mutation execution.

Canon ownership:
- Emits explicit update-mutation-execution recorded, blocked, ready,
  ready-with-restrictions, deferred, rejected, missing-context,
  prohibited-overlap, and fallback audit events.
- Keeps rollout, deployment, retraining, model-update execution,
  monitoring, reopen handling, and lifecycle meaning out of this slice.
"""

from typing import TYPE_CHECKING

from ff_platform.audit.audit_event_store import AuditEventStore
from ff_platform.validation.contract_schema_validator import ContractSchemaValidator

if TYPE_CHECKING:
    from decision.policy_learning.policy_learning_update_mutation_execution_service import (
        PolicyLearningUpdateMutationExecutionRecord,
        PolicyLearningUpdateMutationExecutionRequest,
    )


class PolicyLearningUpdateMutationExecutionAuditAdapter:
    """Emits governed audit events for policy-learning update mutation execution."""

    def __init__(
        self,
        *,
        audit_event_store: AuditEventStore,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._audit_event_store = audit_event_store
        self._contract_validator = contract_validator

    def record_policy_learning_update_mutation_execution(
        self,
        policy_learning_update_mutation_execution: "PolicyLearningUpdateMutationExecutionRecord",
        *,
        request: "PolicyLearningUpdateMutationExecutionRequest",
    ) -> None:
        payload = policy_learning_update_mutation_execution.to_contract_dict()
        self._contract_validator.validate_or_raise(
            "policy_learning_update_mutation_execution_record",
            payload,
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.policy_learning_update_mutation_planning.episode_id,
            actor_id=request.actor_id,
            emit_audit_events=False,
        )

        status = (
            policy_learning_update_mutation_execution.policy_learning_update_mutation_execution_status
        )
        if status in {
            "blocked_missing_context",
            "rejected_for_mutation_execution_use",
            "prohibited_overlap_blocked",
        }:
            self._emit(
                event_type="decision.policy_learning.policy_learning_update_mutation_execution_blocked",
                payload=payload,
                request=request,
                tags=(
                    "policy-learning",
                    policy_learning_update_mutation_execution.policy_learning_update_mutation_execution_class_id,
                    status,
                ),
            )
            if status == "blocked_missing_context":
                self._emit(
                    event_type="decision.policy_learning.policy_learning_update_mutation_execution_missing_context",
                    payload=payload,
                    request=request,
                    tags=(
                        "policy-learning",
                        policy_learning_update_mutation_execution.policy_learning_update_mutation_execution_class_id,
                        "missing-context",
                    ),
                )
            if status == "rejected_for_mutation_execution_use":
                self._emit(
                    event_type="decision.policy_learning.policy_learning_update_mutation_execution_rejected_for_mutation_execution_use",
                    payload=payload,
                    request=request,
                    tags=(
                        "policy-learning",
                        policy_learning_update_mutation_execution.policy_learning_update_mutation_execution_class_id,
                        "rejected-for-mutation-execution-use",
                    ),
                )
            if status == "prohibited_overlap_blocked":
                self._emit(
                    event_type="decision.policy_learning.policy_learning_update_mutation_execution_prohibited_overlap_blocked",
                    payload=payload,
                    request=request,
                    tags=(
                        "policy-learning",
                        policy_learning_update_mutation_execution.policy_learning_update_mutation_execution_class_id,
                        "prohibited-overlap",
                    ),
                )
            return

        self._emit(
            event_type="decision.policy_learning.policy_learning_update_mutation_execution_recorded",
            payload=payload,
            request=request,
            tags=(
                "policy-learning",
                policy_learning_update_mutation_execution.policy_learning_update_mutation_execution_class_id,
                "recorded",
            ),
        )

        outcome = (
            policy_learning_update_mutation_execution.policy_learning_update_mutation_execution_outcome
        )
        if outcome == "ready_for_policy_mutation_execution":
            self._emit(
                event_type="decision.policy_learning.policy_learning_update_mutation_execution_ready_for_policy_mutation_execution",
                payload=payload,
                request=request,
                tags=(
                    "policy-learning",
                    policy_learning_update_mutation_execution.policy_learning_update_mutation_execution_class_id,
                    "ready-for-policy-mutation-execution",
                ),
            )
        elif outcome == "ready_for_policy_mutation_execution_with_restrictions":
            self._emit(
                event_type="decision.policy_learning.policy_learning_update_mutation_execution_ready_for_policy_mutation_execution_with_restrictions",
                payload=payload,
                request=request,
                tags=(
                    "policy-learning",
                    policy_learning_update_mutation_execution.policy_learning_update_mutation_execution_class_id,
                    "ready-for-policy-mutation-execution-with-restrictions",
                ),
            )
        elif outcome == "deferred_pending_mutation_execution_prerequisites":
            self._emit(
                event_type="decision.policy_learning.policy_learning_update_mutation_execution_deferred_pending_mutation_execution_prerequisites",
                payload=payload,
                request=request,
                tags=(
                    "policy-learning",
                    policy_learning_update_mutation_execution.policy_learning_update_mutation_execution_class_id,
                    "deferred-pending-mutation-execution-prerequisites",
                ),
            )

        if status == "fallback_template_applied":
            self._emit(
                event_type="decision.policy_learning.policy_learning_update_mutation_execution_fallback_template_applied",
                payload=payload,
                request=request,
                tags=(
                    "policy-learning",
                    policy_learning_update_mutation_execution.policy_learning_update_mutation_execution_class_id,
                    "fallback-template",
                ),
            )

    def _emit(
        self,
        *,
        event_type: str,
        payload: dict[str, object],
        request: "PolicyLearningUpdateMutationExecutionRequest",
        tags: tuple[str, ...],
    ) -> None:
        self._audit_event_store.record_event(
            event_type=event_type,
            owner=(
                "decision.policy_learning.policy_learning_update_mutation_execution_audit_adapter"
            ),
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.policy_learning_update_mutation_planning.episode_id,
            actor_id=request.actor_id,
            payload=payload,
            tags=tags,
        )
