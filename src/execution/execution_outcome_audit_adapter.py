from __future__ import annotations

"""Structured audit emission for governed execution-outcome capture.

Canon ownership:
- Emits explicit execution-outcome, execution-outcome-block,
  missing-context, fallback-template, and ready-for-downstream-use audit
  events.
- Keeps execution-dispatch meaning, broker or venue meaning, post-mortem
  judgment, and policy-learning admission out of this slice.
"""

from typing import TYPE_CHECKING

from platform.audit.audit_event_store import AuditEventStore
from platform.validation.contract_schema_validator import ContractSchemaValidator

if TYPE_CHECKING:
    from execution.execution_outcome_capture_service import (
        ExecutionOutcomeCaptureRequest,
        ExecutionOutcomeRecord,
    )


class ExecutionOutcomeAuditAdapter:
    """Emits governed audit events for execution-outcome outcomes."""

    def __init__(
        self,
        *,
        audit_event_store: AuditEventStore,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._audit_event_store = audit_event_store
        self._contract_validator = contract_validator

    def record_execution_outcome(
        self,
        execution_outcome: "ExecutionOutcomeRecord",
        *,
        request: "ExecutionOutcomeCaptureRequest",
    ) -> None:
        payload = execution_outcome.to_contract_dict()
        self._contract_validator.validate_or_raise(
            "execution_outcome_record",
            payload,
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.execution_dispatch.episode_id,
            actor_id=request.actor_id,
            emit_audit_events=False,
        )

        if execution_outcome.execution_outcome_status == "blocked":
            self._emit(
                event_type="execution_outcome_blocked",
                payload=payload,
                request=request,
                tags=(
                    "execution-outcome",
                    execution_outcome.realized_result_class,
                    "blocked",
                ),
            )
            if execution_outcome.missing_execution_outcome_fields:
                self._emit(
                    event_type="execution_outcome_missing_context",
                    payload=payload,
                    request=request,
                    tags=(
                        "execution-outcome",
                        execution_outcome.realized_result_class,
                        "missing-context",
                    ),
                )
            return

        self._emit(
            event_type="execution_outcome_recorded",
            payload=payload,
            request=request,
            tags=(
                "execution-outcome",
                execution_outcome.realized_result_class,
                "recorded",
            ),
        )
        self._emit(
            event_type="execution_outcome_ready_for_downstream_use",
            payload=payload,
            request=request,
            tags=(
                "execution-outcome",
                execution_outcome.realized_result_class,
                execution_outcome.execution_outcome_status,
            ),
        )
        if execution_outcome.execution_outcome_status == "fallback_template_applied":
            self._emit(
                event_type="execution_outcome_fallback_template_applied",
                payload=payload,
                request=request,
                tags=(
                    "execution-outcome",
                    execution_outcome.realized_result_class,
                    "fallback-template",
                ),
            )

    def _emit(
        self,
        *,
        event_type: str,
        payload: dict[str, object],
        request: "ExecutionOutcomeCaptureRequest",
        tags: tuple[str, ...],
    ) -> None:
        self._audit_event_store.record_event(
            event_type=event_type,
            owner="execution.execution_outcome_audit_adapter",
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.execution_dispatch.episode_id,
            actor_id=request.actor_id,
            payload=payload,
            tags=tags,
        )