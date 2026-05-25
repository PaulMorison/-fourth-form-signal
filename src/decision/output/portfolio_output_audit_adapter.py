from __future__ import annotations

"""Structured audit emission for governed portfolio outputs.

Canon ownership:
- Emits explicit portfolio-output, portfolio-output-block, missing-context,
  fallback-template, and ready-for-downstream-use audit events.
- Keeps policy meaning, recommendation meaning, commitment issuance,
  instruction issuance, playbook execution, and state progression out of this
  slice.
"""

from typing import TYPE_CHECKING

from platform.audit.audit_event_store import AuditEventStore
from platform.validation.contract_schema_validator import ContractSchemaValidator

if TYPE_CHECKING:
    from decision.output.portfolio_output_service import (
        PortfolioOutputRecord,
        PortfolioOutputRequest,
    )


class PortfolioOutputAuditAdapter:
    """Emits governed audit events for portfolio-output outcomes."""

    def __init__(
        self,
        *,
        audit_event_store: AuditEventStore,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._audit_event_store = audit_event_store
        self._contract_validator = contract_validator

    def record_portfolio_output(
        self,
        portfolio_output: "PortfolioOutputRecord",
        *,
        request: "PortfolioOutputRequest",
    ) -> None:
        payload = portfolio_output.to_contract_dict()
        self._contract_validator.validate_or_raise(
            "portfolio_output_record",
            payload,
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.policy_output.episode_id,
            actor_id=request.actor_id,
            emit_audit_events=False,
        )

        if portfolio_output.portfolio_output_status == "blocked":
            self._emit(
                event_type="decision.output.portfolio_output_blocked",
                payload=payload,
                request=request,
                tags=(
                    "portfolio-output",
                    portfolio_output.allocation_posture,
                    "blocked",
                ),
            )
            if portfolio_output.missing_context_fields:
                self._emit(
                    event_type="decision.output.portfolio_output_missing_context",
                    payload=payload,
                    request=request,
                    tags=(
                        "portfolio-output",
                        portfolio_output.allocation_posture,
                        "missing-context",
                    ),
                )
            return

        self._emit(
            event_type="decision.output.portfolio_output_recorded",
            payload=payload,
            request=request,
            tags=(
                "portfolio-output",
                portfolio_output.allocation_posture,
                "recorded",
            ),
        )
        self._emit(
            event_type="decision.output.portfolio_output_ready_for_downstream_use",
            payload=payload,
            request=request,
            tags=(
                "portfolio-output",
                portfolio_output.allocation_posture,
                portfolio_output.portfolio_output_status,
            ),
        )
        if portfolio_output.portfolio_output_status == "fallback_template_applied":
            self._emit(
                event_type="decision.output.portfolio_output_fallback_template_applied",
                payload=payload,
                request=request,
                tags=(
                    "portfolio-output",
                    portfolio_output.allocation_posture,
                    "fallback-template",
                ),
            )

    def _emit(
        self,
        *,
        event_type: str,
        payload: dict[str, object],
        request: "PortfolioOutputRequest",
        tags: tuple[str, ...],
    ) -> None:
        self._audit_event_store.record_event(
            event_type=event_type,
            owner="decision.output.portfolio_output_audit_adapter",
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.policy_output.episode_id,
            actor_id=request.actor_id,
            payload=payload,
            tags=tags,
        )