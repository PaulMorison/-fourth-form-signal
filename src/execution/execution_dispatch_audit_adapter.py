from __future__ import annotations

"""Structured audit emission for governed execution-dispatch outcomes.

Canon ownership:
- Emits explicit execution-dispatch, execution-dispatch-block,
  missing-context, fallback-template, and ready-for-downstream-use audit
  events.
- Keeps execution-request meaning, broker or venue meaning, and execution
  outcome meaning out of this slice.
"""

from typing import TYPE_CHECKING

from platform.audit.audit_event_store import AuditEventStore
from platform.validation.contract_schema_validator import ContractSchemaValidator

if TYPE_CHECKING:
    from execution.execution_dispatch_boundary import (
        ExecutionDispatchBoundaryRecord,
        ExecutionDispatchBoundaryRequest,
    )


class ExecutionDispatchAuditAdapter:
    """Emits governed audit events for execution-dispatch outcomes."""

    def __init__(
        self,
        *,
        audit_event_store: AuditEventStore,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._audit_event_store = audit_event_store
        self._contract_validator = contract_validator

    def record_execution_dispatch(
        self,
        execution_dispatch: "ExecutionDispatchBoundaryRecord",
        *,
        request: "ExecutionDispatchBoundaryRequest",
    ) -> None:
        payload = execution_dispatch.to_contract_dict()
        self._contract_validator.validate_or_raise(
            "execution_dispatch_record",
            payload,
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.execution_request.episode_id,
            actor_id=request.actor_id,
            emit_audit_events=False,
        )

        if execution_dispatch.execution_dispatch_status == "blocked":
            self._emit(
                event_type="execution_dispatch_blocked",
                payload=payload,
                request=request,
                tags=(
                    "execution-dispatch",
                    execution_dispatch.dispatch_boundary_posture,
                    "blocked",
                ),
            )
            if execution_dispatch.missing_execution_dispatch_fields:
                self._emit(
                    event_type="execution_dispatch_missing_context",
                    payload=payload,
                    request=request,
                    tags=(
                        "execution-dispatch",
                        execution_dispatch.dispatch_boundary_posture,
                        "missing-context",
                    ),
                )
            return

        self._emit(
            event_type="execution_dispatch_recorded",
            payload=payload,
            request=request,
            tags=(
                "execution-dispatch",
                execution_dispatch.dispatch_boundary_posture,
                "recorded",
            ),
        )
        self._emit(
            event_type="execution_dispatch_ready_for_downstream_use",
            payload=payload,
            request=request,
            tags=(
                "execution-dispatch",
                execution_dispatch.dispatch_boundary_posture,
                execution_dispatch.execution_dispatch_status,
            ),
        )
        if execution_dispatch.execution_dispatch_status == "fallback_template_applied":
            self._emit(
                event_type="execution_dispatch_fallback_template_applied",
                payload=payload,
                request=request,
                tags=(
                    "execution-dispatch",
                    execution_dispatch.dispatch_boundary_posture,
                    "fallback-template",
                ),
            )

    def _emit(
        self,
        *,
        event_type: str,
        payload: dict[str, object],
        request: "ExecutionDispatchBoundaryRequest",
        tags: tuple[str, ...],
    ) -> None:
        self._audit_event_store.record_event(
            event_type=event_type,
            owner="execution.execution_dispatch_audit_adapter",
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.execution_request.episode_id,
            actor_id=request.actor_id,
            payload=payload,
            tags=tags,
        )
