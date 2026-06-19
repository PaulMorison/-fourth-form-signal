from __future__ import annotations

"""Structured audit emission for governed post-mortem judgment capture.

Canon ownership:
- Emits explicit post-mortem judgment, missing-context, fallback-template, and
  ready-for-downstream-use audit events.
- Keeps execution-outcome meaning, reopen handling, monitoring meaning, and
  policy-learning admission out of this slice.
"""

from typing import TYPE_CHECKING

from ff_platform.audit.audit_event_store import AuditEventStore
from ff_platform.validation.contract_schema_validator import ContractSchemaValidator

if TYPE_CHECKING:
    from decision.post_mortem.post_mortem_judgment_service import (
        PostMortemJudgmentRecord,
        PostMortemJudgmentRequest,
    )


class PostMortemJudgmentAuditAdapter:
    """Emits governed audit events for post-mortem judgment outcomes."""

    def __init__(
        self,
        *,
        audit_event_store: AuditEventStore,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._audit_event_store = audit_event_store
        self._contract_validator = contract_validator

    def record_post_mortem_judgment(
        self,
        post_mortem_judgment: "PostMortemJudgmentRecord",
        *,
        request: "PostMortemJudgmentRequest",
    ) -> None:
        payload = post_mortem_judgment.to_contract_dict()
        self._contract_validator.validate_or_raise(
            "post_mortem_judgment_record",
            payload,
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.execution_outcome.episode_id,
            actor_id=request.actor_id,
            emit_audit_events=False,
        )

        if post_mortem_judgment.post_mortem_status == "blocked":
            self._emit(
                event_type="decision.post_mortem.post_mortem_judgment_blocked",
                payload=payload,
                request=request,
                tags=(
                    "post-mortem",
                    post_mortem_judgment.primary_attribution_category,
                    "blocked",
                ),
            )
            if post_mortem_judgment.missing_post_mortem_fields:
                self._emit(
                    event_type=(
                        "decision.post_mortem.post_mortem_judgment_missing_context"
                    ),
                    payload=payload,
                    request=request,
                    tags=(
                        "post-mortem",
                        post_mortem_judgment.primary_attribution_category,
                        "missing-context",
                    ),
                )
            return

        self._emit(
            event_type="decision.post_mortem.post_mortem_judgment_recorded",
            payload=payload,
            request=request,
            tags=(
                "post-mortem",
                post_mortem_judgment.primary_attribution_category,
                "recorded",
            ),
        )
        self._emit(
            event_type=(
                "decision.post_mortem.post_mortem_judgment_ready_for_downstream_use"
            ),
            payload=payload,
            request=request,
            tags=(
                "post-mortem",
                post_mortem_judgment.primary_attribution_category,
                post_mortem_judgment.post_mortem_status,
            ),
        )
        if post_mortem_judgment.post_mortem_status == "fallback_template_applied":
            self._emit(
                event_type=(
                    "decision.post_mortem.post_mortem_judgment_fallback_template_applied"
                ),
                payload=payload,
                request=request,
                tags=(
                    "post-mortem",
                    post_mortem_judgment.primary_attribution_category,
                    "fallback-template",
                ),
            )

    def _emit(
        self,
        *,
        event_type: str,
        payload: dict[str, object],
        request: "PostMortemJudgmentRequest",
        tags: tuple[str, ...],
    ) -> None:
        self._audit_event_store.record_event(
            event_type=event_type,
            owner="decision.post_mortem.post_mortem_judgment_audit_adapter",
            correlation_id=request.correlation_id,
            entity_type="case_episode",
            entity_id=request.execution_outcome.episode_id,
            actor_id=request.actor_id,
            payload=payload,
            tags=tags,
        )