from __future__ import annotations

"""Structured audit emission for governed execution requests.

Canon ownership:
- Emits explicit execution-request, execution-request-block,
  missing-context, fallback-template, and ready-for-downstream-use audit
  events.
- Keeps action-instruction meaning, authority meaning, and actual execution
  meaning out of this slice.
"""

from typing import TYPE_CHECKING

from platform.audit.audit_event_store import AuditEventStore
from platform.validation.contract_schema_validator import ContractSchemaValidator

if TYPE_CHECKING:
    from execution.execution_request_service import (
        ExecutionRequestRecord,
        ExecutionRequestRequest,
    )


class ExecutionRequestAuditAdapter:
    """Emits governed audit events for execution-request outcomes."""

    def __init__(
        self,
        *,
        audit_event_store: AuditEventStore,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._audit_event_store = audit_event_store
        self._contract_validator = contract_validator

    def record_execution_request(
        self,
        execution_request: "ExecutionRequestRecord",
        *,
        request: "ExecutionRequestRequest",
    ) -> None:
        payload = execution_request.to_contract_dict()
        self._contract_validator.validate_or_raise(
            "execution_request_record",
            payload,
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.action_instruction.episode_id,
            actor_id=request.actor_id,
            emit_audit_events=False,
        )

        if execution_request.execution_request_status == "blocked":
            self._emit(
                event_type="execution_request_blocked",
                payload=payload,
                request=request,
                tags=(
                    "execution-request",
                    execution_request.action_boundary_posture,
                    "blocked",
                ),
            )
            if execution_request.missing_execution_request_fields:
                self._emit(
                    event_type="execution_request_missing_context",
                    payload=payload,
                    request=request,
                    tags=(
                        "execution-request",
                        execution_request.action_boundary_posture,
                        "missing-context",
                    ),
                )
            return

        self._emit(
            event_type="execution_request_recorded",
            payload=payload,
            request=request,
            tags=(
                "execution-request",
                execution_request.action_boundary_posture,
                "recorded",
            ),
        )
        self._emit(
            event_type="execution_request_ready_for_downstream_use",
            payload=payload,
            request=request,
            tags=(
                "execution-request",
                execution_request.action_boundary_posture,
                execution_request.execution_request_status,
            ),
        )
        if execution_request.execution_request_status == "fallback_template_applied":
            self._emit(
                event_type="execution_request_fallback_template_applied",
                payload=payload,
                request=request,
                tags=(
                    "execution-request",
                    execution_request.action_boundary_posture,
                    "fallback-template",
                ),
            )

    def _emit(
        self,
        *,
        event_type: str,
        payload: dict[str, object],
        request: "ExecutionRequestRequest",
        tags: tuple[str, ...],
    ) -> None:
        self._audit_event_store.record_event(
            event_type=event_type,
            owner="execution.execution_request_audit_adapter",
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.action_instruction.episode_id,
            actor_id=request.actor_id,
            payload=payload,
            tags=tags,
        )