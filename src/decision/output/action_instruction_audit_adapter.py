from __future__ import annotations

"""Structured audit emission for governed action instructions.

Canon ownership:
- Emits explicit action-instruction, action-instruction-block,
  missing-context, fallback-template, and ready-for-downstream-use audit
  events.
- Keeps portfolio meaning, policy meaning, recommendation meaning,
  commitment generation, and execution handling out of this slice.
"""

from typing import TYPE_CHECKING

from ff_platform.audit.audit_event_store import AuditEventStore
from ff_platform.validation.contract_schema_validator import ContractSchemaValidator

if TYPE_CHECKING:
    from decision.output.action_instruction_service import (
        ActionInstructionRecord,
        ActionInstructionRequest,
    )


class ActionInstructionAuditAdapter:
    """Emits governed audit events for action-instruction outcomes."""

    def __init__(
        self,
        *,
        audit_event_store: AuditEventStore,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._audit_event_store = audit_event_store
        self._contract_validator = contract_validator

    def record_action_instruction(
        self,
        action_instruction: "ActionInstructionRecord",
        *,
        request: "ActionInstructionRequest",
    ) -> None:
        payload = action_instruction.to_contract_dict()
        self._contract_validator.validate_or_raise(
            "action_instruction_record",
            payload,
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.portfolio_output.episode_id,
            actor_id=request.actor_id,
            emit_audit_events=False,
        )

        if action_instruction.action_instruction_status == "blocked":
            self._emit(
                event_type="decision.output.action_instruction_blocked",
                payload=payload,
                request=request,
                tags=(
                    "action-instruction",
                    action_instruction.bounded_action_posture,
                    "blocked",
                ),
            )
            if action_instruction.missing_instruction_fields:
                self._emit(
                    event_type="decision.output.action_instruction_missing_context",
                    payload=payload,
                    request=request,
                    tags=(
                        "action-instruction",
                        action_instruction.bounded_action_posture,
                        "missing-context",
                    ),
                )
            return

        self._emit(
            event_type="decision.output.action_instruction_recorded",
            payload=payload,
            request=request,
            tags=(
                "action-instruction",
                action_instruction.bounded_action_posture,
                "recorded",
            ),
        )
        self._emit(
            event_type="decision.output.action_instruction_ready_for_downstream_use",
            payload=payload,
            request=request,
            tags=(
                "action-instruction",
                action_instruction.bounded_action_posture,
                action_instruction.action_instruction_status,
            ),
        )
        if action_instruction.action_instruction_status == "fallback_template_applied":
            self._emit(
                event_type="decision.output.action_instruction_fallback_template_applied",
                payload=payload,
                request=request,
                tags=(
                    "action-instruction",
                    action_instruction.bounded_action_posture,
                    "fallback-template",
                ),
            )

    def _emit(
        self,
        *,
        event_type: str,
        payload: dict[str, object],
        request: "ActionInstructionRequest",
        tags: tuple[str, ...],
    ) -> None:
        self._audit_event_store.record_event(
            event_type=event_type,
            owner="decision.output.action_instruction_audit_adapter",
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.portfolio_output.episode_id,
            actor_id=request.actor_id,
            payload=payload,
            tags=tags,
        )