from __future__ import annotations

"""Structured audit emission for governed policy outputs.

Canon ownership:
- Emits explicit policy-output, policy-output-block, missing-context,
  fallback-template, and ready-for-downstream-use audit events.
- Keeps recommendation meaning, commitment issuance, instruction issuance,
  playbook execution, and state progression out of this slice.
"""

from typing import TYPE_CHECKING

from platform.audit.audit_event_store import AuditEventStore
from platform.validation.contract_schema_validator import ContractSchemaValidator

if TYPE_CHECKING:
    from decision.output.policy_output_service import (
        PolicyOutputRecord,
        PolicyOutputRequest,
    )


class PolicyOutputAuditAdapter:
    """Emits governed audit events for policy-output outcomes."""

    def __init__(
        self,
        *,
        audit_event_store: AuditEventStore,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._audit_event_store = audit_event_store
        self._contract_validator = contract_validator

    def record_policy_output(
        self,
        policy_output: "PolicyOutputRecord",
        *,
        request: "PolicyOutputRequest",
    ) -> None:
        payload = policy_output.to_contract_dict()
        self._contract_validator.validate_or_raise(
            "policy_output_record",
            payload,
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.recommendation.episode_id,
            actor_id=request.actor_id,
            emit_audit_events=False,
        )

        if policy_output.policy_output_status == "blocked":
            self._emit(
                event_type="decision.output.policy_output_blocked",
                payload=payload,
                request=request,
                tags=(
                    "policy-output",
                    policy_output.bounded_policy_posture,
                    "blocked",
                ),
            )
            if policy_output.missing_context_fields:
                self._emit(
                    event_type="decision.output.policy_output_missing_context",
                    payload=payload,
                    request=request,
                    tags=(
                        "policy-output",
                        policy_output.bounded_policy_posture,
                        "missing-context",
                    ),
                )
            return

        self._emit(
            event_type="decision.output.policy_output_recorded",
            payload=payload,
            request=request,
            tags=(
                "policy-output",
                policy_output.bounded_policy_posture,
                "recorded",
            ),
        )
        self._emit(
            event_type="decision.output.policy_output_ready_for_downstream_use",
            payload=payload,
            request=request,
            tags=(
                "policy-output",
                policy_output.bounded_policy_posture,
                policy_output.policy_output_status,
            ),
        )
        if policy_output.policy_output_status == "fallback_template_applied":
            self._emit(
                event_type="decision.output.policy_output_fallback_template_applied",
                payload=payload,
                request=request,
                tags=(
                    "policy-output",
                    policy_output.bounded_policy_posture,
                    "fallback-template",
                ),
            )

    def _emit(
        self,
        *,
        event_type: str,
        payload: dict[str, object],
        request: "PolicyOutputRequest",
        tags: tuple[str, ...],
    ) -> None:
        self._audit_event_store.record_event(
            event_type=event_type,
            owner="decision.output.policy_output_audit_adapter",
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.recommendation.episode_id,
            actor_id=request.actor_id,
            payload=payload,
            tags=tags,
        )