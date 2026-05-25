from __future__ import annotations

"""Structured audit emission for governed policy-learning evidence admission.

Canon ownership:
- Emits explicit evidence-admission, missing-context, rejected-for-learning,
  prohibited-overlap, and fallback-template audit events.
- Keeps post-mortem meaning, reopen handling, monitoring, model mutation, and
  policy execution out of this slice.
"""

from typing import TYPE_CHECKING

from platform.audit.audit_event_store import AuditEventStore
from platform.validation.contract_schema_validator import ContractSchemaValidator

if TYPE_CHECKING:
    from decision.policy_learning.policy_learning_evidence_admission_service import (
        PolicyLearningEvidenceAdmissionRecord,
        PolicyLearningEvidenceAdmissionRequest,
    )


class PolicyLearningEvidenceAdmissionAuditAdapter:
    """Emits governed audit events for policy-learning evidence outcomes."""

    def __init__(
        self,
        *,
        audit_event_store: AuditEventStore,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._audit_event_store = audit_event_store
        self._contract_validator = contract_validator

    def record_policy_learning_evidence_admission(
        self,
        policy_learning_evidence_admission: "PolicyLearningEvidenceAdmissionRecord",
        *,
        request: "PolicyLearningEvidenceAdmissionRequest",
    ) -> None:
        payload = policy_learning_evidence_admission.to_contract_dict()
        self._contract_validator.validate_or_raise(
            "policy_learning_evidence_admission_record",
            payload,
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.post_mortem_judgment.episode_id,
            actor_id=request.actor_id,
            emit_audit_events=False,
        )

        status = (
            policy_learning_evidence_admission.policy_learning_evidence_admission_status
        )
        if status in {
            "blocked_missing_context",
            "blocked_insufficient_evidence",
            "prohibited_overlap_blocked",
        }:
            self._emit(
                event_type=(
                    "decision.policy_learning.policy_learning_evidence_admission_blocked"
                ),
                payload=payload,
                request=request,
                tags=(
                    "policy-learning",
                    policy_learning_evidence_admission.policy_learning_evidence_class_id,
                    status,
                ),
            )
            if status == "blocked_missing_context":
                self._emit(
                    event_type=(
                        "decision.policy_learning.policy_learning_evidence_admission_missing_context"
                    ),
                    payload=payload,
                    request=request,
                    tags=(
                        "policy-learning",
                        policy_learning_evidence_admission.policy_learning_evidence_class_id,
                        "missing-context",
                    ),
                )
            if status == "blocked_insufficient_evidence":
                self._emit(
                    event_type=(
                        "decision.policy_learning.policy_learning_evidence_admission_rejected_for_learning_use"
                    ),
                    payload=payload,
                    request=request,
                    tags=(
                        "policy-learning",
                        policy_learning_evidence_admission.policy_learning_evidence_class_id,
                        "rejected-for-learning-use",
                    ),
                )
            if status == "prohibited_overlap_blocked":
                self._emit(
                    event_type=(
                        "decision.policy_learning.policy_learning_evidence_admission_prohibited_overlap_blocked"
                    ),
                    payload=payload,
                    request=request,
                    tags=(
                        "policy-learning",
                        policy_learning_evidence_admission.policy_learning_evidence_class_id,
                        "prohibited-overlap",
                    ),
                )
            return

        self._emit(
            event_type=(
                "decision.policy_learning.policy_learning_evidence_admission_recorded"
            ),
            payload=payload,
            request=request,
            tags=(
                "policy-learning",
                policy_learning_evidence_admission.policy_learning_evidence_class_id,
                "recorded",
            ),
        )

        outcome = policy_learning_evidence_admission.policy_learning_evidence_admission_outcome
        if outcome == "admitted_for_update_consideration":
            self._emit(
                event_type=(
                    "decision.policy_learning.policy_learning_evidence_admission_admitted_for_update_consideration"
                ),
                payload=payload,
                request=request,
                tags=(
                    "policy-learning",
                    policy_learning_evidence_admission.policy_learning_evidence_class_id,
                    "admitted-for-update-consideration",
                ),
            )
        elif outcome == "admitted_with_restrictions":
            self._emit(
                event_type=(
                    "decision.policy_learning.policy_learning_evidence_admission_admitted_with_restrictions"
                ),
                payload=payload,
                request=request,
                tags=(
                    "policy-learning",
                    policy_learning_evidence_admission.policy_learning_evidence_class_id,
                    "admitted-with-restrictions",
                ),
            )
        elif outcome == "deferred_pending_more_evidence":
            self._emit(
                event_type=(
                    "decision.policy_learning.policy_learning_evidence_admission_deferred_pending_more_evidence"
                ),
                payload=payload,
                request=request,
                tags=(
                    "policy-learning",
                    policy_learning_evidence_admission.policy_learning_evidence_class_id,
                    "deferred-pending-more-evidence",
                ),
            )

        if status == "fallback_template_applied":
            self._emit(
                event_type=(
                    "decision.policy_learning.policy_learning_evidence_admission_fallback_template_applied"
                ),
                payload=payload,
                request=request,
                tags=(
                    "policy-learning",
                    policy_learning_evidence_admission.policy_learning_evidence_class_id,
                    "fallback-template",
                ),
            )

    def _emit(
        self,
        *,
        event_type: str,
        payload: dict[str, object],
        request: "PolicyLearningEvidenceAdmissionRequest",
        tags: tuple[str, ...],
    ) -> None:
        self._audit_event_store.record_event(
            event_type=event_type,
            owner=(
                "decision.policy_learning.policy_learning_evidence_admission_audit_adapter"
            ),
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.post_mortem_judgment.episode_id,
            actor_id=request.actor_id,
            payload=payload,
            tags=tags,
        )