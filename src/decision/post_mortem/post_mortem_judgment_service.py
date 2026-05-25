from __future__ import annotations

"""Deterministic post-mortem judgment capture after governed execution outcomes.

Canon ownership:
- Converts legitimate execution outcomes plus explicit attribution context into
  governed post-mortem judgment records.
- Owns attribution-category meaning, evidence-quality posture,
  confidence posture, bounded comparison posture, rationale capture, and
  judgment lineage.
- Does not admit policy learning, reopen cases, replace monitoring, or absorb
  broker, venue, or execution-control semantics.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Mapping, Sequence
from uuid import uuid4

from decision.post_mortem.post_mortem_judgment_audit_adapter import (
    PostMortemJudgmentAuditAdapter,
)
from decision.post_mortem.post_mortem_judgment_registry import (
    PostMortemJudgmentRegistry,
)
from execution.execution_outcome_capture_service import ExecutionOutcomeRecord


@dataclass(frozen=True)
class PostMortemJudgmentRequest:
    execution_outcome: ExecutionOutcomeRecord
    post_mortem_judgment_class_id: str
    post_mortem_author_role: str
    post_mortem_context: Mapping[str, object]
    correlation_id: str
    actor_id: str


@dataclass(frozen=True)
class PostMortemJudgmentRecord:
    post_mortem_judgment_id: str
    post_mortem_status: str
    reason: str
    post_mortem_judgment_class_id: str
    post_mortem_judgment_template_id: str
    primary_attribution_category: str
    evidence_quality: str
    confidence_posture: str
    learning_direction: str
    comparison_posture: str
    execution_outcome_id: str
    execution_outcome_status: str
    execution_outcome_class_id: str
    execution_outcome_template_id: str
    realized_result_class: str
    feedback_capture_readiness: str
    expected_relation: str
    execution_dispatch_id: str
    execution_dispatch_class_id: str
    execution_request_id: str
    semantic_scope: str
    case_type: str
    case_key: str
    state_model_name: str
    episode_id: str
    transition_name: str
    transition_class: str
    source_stage: str
    target_stage: str
    execution_outcome_author_role: str
    execution_outcome_author_id: str
    post_mortem_author_role: str
    post_mortem_author_id: str
    authority_resolution_kind: str
    authority_review_required: bool
    router_rule_id: str
    routing_resolution_status: str
    routing_review_required: bool
    review_mode: str
    required_post_mortem_fields: tuple[str, ...]
    optional_post_mortem_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    prohibited_judgment_fields: tuple[str, ...]
    required_post_mortem_snapshot: Mapping[str, str]
    optional_post_mortem_snapshot: Mapping[str, str]
    required_audit_snapshot: Mapping[str, str]
    lineage: Mapping[str, str]
    generated_at: datetime
    observation_horizon_reference: str | None = None
    domain_reference: str | None = None
    decision_scope_reference: str | None = None
    reporting_scope_reference: str | None = None
    tenant_scope_reference: str | None = None
    rationale_snapshot: str | None = None
    evidence_basis_summary: str | None = None
    recommendation_id: str | None = None
    action_instruction_id: str | None = None
    executed_action_reference: str | None = None
    non_execution_reference: str | None = None
    realized_outcome_reference: str | None = None
    execution_deviation_reference: str | None = None
    override_reference: str | None = None
    secondary_contributing_factors: tuple[str, ...] = ()
    competing_explanations: tuple[str, ...] = ()
    evidence_gaps: tuple[str, ...] = ()
    execution_condition_references: tuple[str, ...] = ()
    missing_post_mortem_fields: tuple[str, ...] = ()
    prohibited_judgment_fields_present: tuple[str, ...] = ()

    def to_contract_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "post_mortem_judgment_id": self.post_mortem_judgment_id,
            "post_mortem_status": self.post_mortem_status,
            "reason": self.reason,
            "post_mortem_judgment_class_id": self.post_mortem_judgment_class_id,
            "post_mortem_judgment_template_id": (
                self.post_mortem_judgment_template_id
            ),
            "primary_attribution_category": self.primary_attribution_category,
            "evidence_quality": self.evidence_quality,
            "confidence_posture": self.confidence_posture,
            "learning_direction": self.learning_direction,
            "comparison_posture": self.comparison_posture,
            "execution_outcome_id": self.execution_outcome_id,
            "execution_outcome_status": self.execution_outcome_status,
            "execution_outcome_class_id": self.execution_outcome_class_id,
            "execution_outcome_template_id": self.execution_outcome_template_id,
            "realized_result_class": self.realized_result_class,
            "feedback_capture_readiness": self.feedback_capture_readiness,
            "expected_relation": self.expected_relation,
            "execution_dispatch_id": self.execution_dispatch_id,
            "execution_dispatch_class_id": self.execution_dispatch_class_id,
            "execution_request_id": self.execution_request_id,
            "semantic_scope": self.semantic_scope,
            "case_type": self.case_type,
            "case_key": self.case_key,
            "state_model_name": self.state_model_name,
            "episode_id": self.episode_id,
            "transition_name": self.transition_name,
            "transition_class": self.transition_class,
            "source_stage": self.source_stage,
            "target_stage": self.target_stage,
            "execution_outcome_author_role": self.execution_outcome_author_role,
            "execution_outcome_author_id": self.execution_outcome_author_id,
            "post_mortem_author_role": self.post_mortem_author_role,
            "post_mortem_author_id": self.post_mortem_author_id,
            "authority_resolution_kind": self.authority_resolution_kind,
            "authority_review_required": self.authority_review_required,
            "router_rule_id": self.router_rule_id,
            "routing_resolution_status": self.routing_resolution_status,
            "routing_review_required": self.routing_review_required,
            "review_mode": self.review_mode,
            "required_post_mortem_fields": list(self.required_post_mortem_fields),
            "optional_post_mortem_fields": list(self.optional_post_mortem_fields),
            "required_audit_fields": list(self.required_audit_fields),
            "prohibited_judgment_fields": list(self.prohibited_judgment_fields),
            "required_post_mortem_snapshot": dict(self.required_post_mortem_snapshot),
            "optional_post_mortem_snapshot": dict(self.optional_post_mortem_snapshot),
            "required_audit_snapshot": dict(self.required_audit_snapshot),
            "lineage": dict(self.lineage),
            "generated_at": self.generated_at.isoformat(),
        }
        if self.observation_horizon_reference is not None:
            payload["observation_horizon_reference"] = (
                self.observation_horizon_reference
            )
        if self.domain_reference is not None:
            payload["domain_reference"] = self.domain_reference
        if self.decision_scope_reference is not None:
            payload["decision_scope_reference"] = self.decision_scope_reference
        if self.reporting_scope_reference is not None:
            payload["reporting_scope_reference"] = self.reporting_scope_reference
        if self.tenant_scope_reference is not None:
            payload["tenant_scope_reference"] = self.tenant_scope_reference
        if self.rationale_snapshot is not None:
            payload["rationale_snapshot"] = self.rationale_snapshot
        if self.evidence_basis_summary is not None:
            payload["evidence_basis_summary"] = self.evidence_basis_summary
        if self.recommendation_id is not None:
            payload["recommendation_id"] = self.recommendation_id
        if self.action_instruction_id is not None:
            payload["action_instruction_id"] = self.action_instruction_id
        if self.executed_action_reference is not None:
            payload["executed_action_reference"] = self.executed_action_reference
        if self.non_execution_reference is not None:
            payload["non_execution_reference"] = self.non_execution_reference
        if self.realized_outcome_reference is not None:
            payload["realized_outcome_reference"] = self.realized_outcome_reference
        if self.execution_deviation_reference is not None:
            payload["execution_deviation_reference"] = (
                self.execution_deviation_reference
            )
        if self.override_reference is not None:
            payload["override_reference"] = self.override_reference
        if self.secondary_contributing_factors:
            payload["secondary_contributing_factors"] = list(
                self.secondary_contributing_factors
            )
        if self.competing_explanations:
            payload["competing_explanations"] = list(self.competing_explanations)
        if self.evidence_gaps:
            payload["evidence_gaps"] = list(self.evidence_gaps)
        if self.execution_condition_references:
            payload["execution_condition_references"] = list(
                self.execution_condition_references
            )
        if self.missing_post_mortem_fields:
            payload["missing_post_mortem_fields"] = list(
                self.missing_post_mortem_fields
            )
        if self.prohibited_judgment_fields_present:
            payload["prohibited_judgment_fields_present"] = list(
                self.prohibited_judgment_fields_present
            )
        return payload


class PostMortemJudgmentService:
    """Builds governed post-mortem judgments from legitimate execution outcomes."""

    def __init__(
        self,
        *,
        post_mortem_judgment_registry: PostMortemJudgmentRegistry,
        post_mortem_judgment_audit_adapter: PostMortemJudgmentAuditAdapter,
    ) -> None:
        self._post_mortem_judgment_registry = post_mortem_judgment_registry
        self._post_mortem_judgment_audit_adapter = post_mortem_judgment_audit_adapter

    def generate(
        self,
        request: PostMortemJudgmentRequest,
    ) -> PostMortemJudgmentRecord:
        template, fallback_template_used = self._post_mortem_judgment_registry.resolve_template(
            semantic_scope=request.execution_outcome.semantic_scope,
            execution_outcome_class_id=request.execution_outcome.execution_outcome_class_id,
            post_mortem_judgment_class_id=request.post_mortem_judgment_class_id,
            route_name=request.execution_outcome.route_name,
        )
        class_definition = self._post_mortem_judgment_registry.get_post_mortem_judgment_class(
            request.post_mortem_judgment_class_id
        )
        combined_context = self._combined_context(request, class_definition)
        required_post_mortem_snapshot, missing_post_mortem_fields = (
            self._snapshot_required_fields(
                template.required_post_mortem_fields,
                combined_context,
            )
        )
        required_audit_snapshot, missing_audit_fields = self._snapshot_required_fields(
            template.required_audit_fields,
            combined_context,
        )
        all_missing_fields = tuple(
            dict.fromkeys(missing_post_mortem_fields + missing_audit_fields)
        )
        optional_post_mortem_snapshot = self._snapshot_optional_fields(
            template.optional_post_mortem_fields,
            combined_context,
        )
        prohibited_judgment_fields_present = self._prohibited_judgment_fields_present(
            class_definition.prohibited_judgment_fields,
            request.post_mortem_context,
        )
        post_mortem_status = self._post_mortem_status(
            execution_outcome=request.execution_outcome,
            missing_post_mortem_fields=all_missing_fields,
            prohibited_judgment_fields_present=prohibited_judgment_fields_present,
            fallback_template_used=fallback_template_used,
        )
        comparison_posture = self._comparison_posture(request.execution_outcome)
        evidence_quality = self._evidence_quality(
            combined_context.get("evidence_quality"),
            post_mortem_status=post_mortem_status,
        )
        confidence_posture = self._confidence_posture(
            combined_context.get("confidence_posture"),
            evidence_quality=evidence_quality,
        )
        learning_direction = self._learning_direction(
            combined_context.get("learning_direction"),
            post_mortem_status=post_mortem_status,
        )
        reason = self._post_mortem_reason(
            execution_outcome=request.execution_outcome,
            post_mortem_status=post_mortem_status,
            post_mortem_judgment_class_id=class_definition.post_mortem_judgment_class_id,
            missing_post_mortem_fields=all_missing_fields,
            prohibited_judgment_fields_present=prohibited_judgment_fields_present,
        )

        post_mortem_judgment = PostMortemJudgmentRecord(
            post_mortem_judgment_id=str(uuid4()),
            post_mortem_status=post_mortem_status,
            reason=reason,
            post_mortem_judgment_class_id=(
                class_definition.post_mortem_judgment_class_id
            ),
            post_mortem_judgment_template_id=(
                template.post_mortem_judgment_template_id
            ),
            primary_attribution_category=class_definition.primary_attribution_category,
            evidence_quality=evidence_quality,
            confidence_posture=confidence_posture,
            learning_direction=learning_direction,
            comparison_posture=comparison_posture,
            execution_outcome_id=request.execution_outcome.execution_outcome_id,
            execution_outcome_status=request.execution_outcome.execution_outcome_status,
            execution_outcome_class_id=request.execution_outcome.execution_outcome_class_id,
            execution_outcome_template_id=(
                request.execution_outcome.execution_outcome_template_id
            ),
            realized_result_class=request.execution_outcome.realized_result_class,
            feedback_capture_readiness=(
                request.execution_outcome.feedback_capture_readiness
            ),
            expected_relation=request.execution_outcome.expected_relation,
            execution_dispatch_id=request.execution_outcome.execution_dispatch_id,
            execution_dispatch_class_id=(
                request.execution_outcome.execution_dispatch_class_id
            ),
            execution_request_id=request.execution_outcome.execution_request_id,
            semantic_scope=request.execution_outcome.semantic_scope,
            case_type=request.execution_outcome.case_type,
            case_key=request.execution_outcome.case_key,
            state_model_name=request.execution_outcome.state_model_name,
            episode_id=request.execution_outcome.episode_id,
            transition_name=request.execution_outcome.transition_name,
            transition_class=request.execution_outcome.transition_class,
            source_stage=request.execution_outcome.source_stage,
            target_stage=request.execution_outcome.target_stage,
            execution_outcome_author_role=(
                request.execution_outcome.execution_outcome_author_role
            ),
            execution_outcome_author_id=(
                request.execution_outcome.execution_outcome_author_id
            ),
            post_mortem_author_role=request.post_mortem_author_role,
            post_mortem_author_id=request.actor_id,
            authority_resolution_kind=(
                request.execution_outcome.authority_resolution_kind
            ),
            authority_review_required=(
                request.execution_outcome.authority_review_required
            ),
            router_rule_id=request.execution_outcome.router_rule_id,
            routing_resolution_status=(
                request.execution_outcome.routing_resolution_status
            ),
            routing_review_required=(
                request.execution_outcome.routing_review_required
            ),
            review_mode=request.execution_outcome.review_mode,
            required_post_mortem_fields=template.required_post_mortem_fields,
            optional_post_mortem_fields=template.optional_post_mortem_fields,
            required_audit_fields=template.required_audit_fields,
            prohibited_judgment_fields=class_definition.prohibited_judgment_fields,
            required_post_mortem_snapshot=required_post_mortem_snapshot,
            optional_post_mortem_snapshot=optional_post_mortem_snapshot,
            required_audit_snapshot=required_audit_snapshot,
            lineage=self._lineage(request, class_definition, template),
            generated_at=datetime.now(tz=UTC),
            observation_horizon_reference=self._optional_text(
                combined_context.get("observation_horizon_reference")
            ),
            domain_reference=self._optional_text(combined_context.get("domain_reference")),
            decision_scope_reference=self._optional_text(
                combined_context.get("decision_scope_reference")
            ),
            reporting_scope_reference=self._optional_text(
                combined_context.get("reporting_scope_reference")
            ),
            tenant_scope_reference=self._optional_text(
                combined_context.get("tenant_scope_reference")
            ),
            rationale_snapshot=self._optional_text(
                combined_context.get("rationale_snapshot")
            ),
            evidence_basis_summary=self._optional_text(
                combined_context.get("evidence_basis_summary")
            ),
            recommendation_id=self._optional_text(
                request.execution_outcome.lineage.get("recommendation_id")
            ),
            action_instruction_id=self._optional_text(
                request.execution_outcome.lineage.get("action_instruction_id")
            ),
            executed_action_reference=self._optional_text(
                combined_context.get("executed_action_reference")
            ),
            non_execution_reference=self._optional_text(
                combined_context.get("non_execution_reference")
            ),
            realized_outcome_reference=self._optional_text(
                combined_context.get("realized_outcome_reference")
            ),
            execution_deviation_reference=self._optional_text(
                combined_context.get("execution_deviation_reference")
            ),
            override_reference=self._optional_text(
                combined_context.get("override_reference")
            ),
            secondary_contributing_factors=self._sequence_as_tuple(
                combined_context.get("secondary_contributing_factors")
            ),
            competing_explanations=self._sequence_as_tuple(
                combined_context.get("competing_explanations")
            ),
            evidence_gaps=self._sequence_as_tuple(
                combined_context.get("evidence_gaps")
            ),
            execution_condition_references=self._sequence_as_tuple(
                combined_context.get("execution_condition_references")
            ),
            missing_post_mortem_fields=all_missing_fields,
            prohibited_judgment_fields_present=prohibited_judgment_fields_present,
        )
        self._post_mortem_judgment_audit_adapter.record_post_mortem_judgment(
            post_mortem_judgment,
            request=request,
        )
        return post_mortem_judgment

    def _combined_context(
        self,
        request: PostMortemJudgmentRequest,
        class_definition,
    ) -> dict[str, object]:
        context = dict(request.execution_outcome.required_execution_outcome_snapshot)
        context.update(request.execution_outcome.optional_execution_outcome_snapshot)
        context.update(request.execution_outcome.required_audit_snapshot)
        context.update(dict(request.post_mortem_context))
        context.update(
            {
                "post_mortem_judgment_class_id": (
                    class_definition.post_mortem_judgment_class_id
                ),
                "primary_attribution_category": (
                    class_definition.primary_attribution_category
                ),
                "post_mortem_author_id": request.actor_id,
                "post_mortem_author_role": request.post_mortem_author_role,
                "domain_reference": self._optional_text(
                    context.get("domain_reference")
                )
                or request.execution_outcome.domain_reference
                or request.execution_outcome.semantic_scope,
                "decision_scope_reference": self._optional_text(
                    context.get("decision_scope_reference")
                )
                or request.execution_outcome.decision_scope_reference
                or "",
                "tenant_scope_reference": self._optional_text(
                    context.get("tenant_scope_reference")
                )
                or request.execution_outcome.tenant_scope_reference
                or "",
                "reporting_scope_reference": self._optional_text(
                    context.get("reporting_scope_reference")
                )
                or request.execution_outcome.reporting_scope_reference
                or "",
                "observation_horizon_reference": self._optional_text(
                    context.get("observation_horizon_reference")
                )
                or request.execution_outcome.observation_horizon_reference
                or "",
                "executed_action_reference": self._optional_text(
                    context.get("executed_action_reference")
                )
                or request.execution_outcome.executed_action_reference
                or "",
                "non_execution_reference": self._optional_text(
                    context.get("non_execution_reference")
                )
                or request.execution_outcome.non_execution_reference
                or "",
                "realized_outcome_reference": self._optional_text(
                    context.get("realized_outcome_reference")
                )
                or request.execution_outcome.realized_outcome_reference
                or "",
                "execution_condition_references": (
                    request.post_mortem_context.get("execution_condition_references")
                    or request.execution_outcome.execution_condition_references
                ),
            }
        )
        return context

    def _snapshot_required_fields(
        self,
        field_names: tuple[str, ...],
        context: Mapping[str, object],
    ) -> tuple[dict[str, str], tuple[str, ...]]:
        snapshot: dict[str, str] = {}
        missing_fields: list[str] = []
        for field_name in field_names:
            value = context.get(field_name)
            if value is None or value == "" or value == ():
                missing_fields.append(field_name)
                continue
            snapshot[field_name] = self._to_text(value)
        return snapshot, tuple(missing_fields)

    def _snapshot_optional_fields(
        self,
        field_names: tuple[str, ...],
        context: Mapping[str, object],
    ) -> dict[str, str]:
        snapshot: dict[str, str] = {}
        for field_name in field_names:
            value = context.get(field_name)
            if value is None or value == "" or value == ():
                continue
            snapshot[field_name] = self._to_text(value)
        return snapshot

    def _prohibited_judgment_fields_present(
        self,
        field_names: tuple[str, ...],
        context: Mapping[str, object],
    ) -> tuple[str, ...]:
        present_fields: list[str] = []
        for field_name in field_names:
            value = context.get(field_name)
            if value is None or value == "":
                continue
            present_fields.append(field_name)
        return tuple(present_fields)

    def _post_mortem_status(
        self,
        *,
        execution_outcome: ExecutionOutcomeRecord,
        missing_post_mortem_fields: tuple[str, ...],
        prohibited_judgment_fields_present: tuple[str, ...],
        fallback_template_used: bool,
    ) -> str:
        if execution_outcome.execution_outcome_status == "blocked":
            return "blocked"
        if missing_post_mortem_fields or prohibited_judgment_fields_present:
            return "blocked"
        if (
            fallback_template_used
            or execution_outcome.execution_outcome_status == "fallback_template_applied"
        ):
            return "fallback_template_applied"
        return "ready_for_downstream_use"

    def _comparison_posture(self, execution_outcome: ExecutionOutcomeRecord) -> str:
        if execution_outcome.feedback_capture_readiness != "feedback_capture_ready_for_post_mortem":
            return "post_mortem_pending_mature_observation"
        if execution_outcome.comparison_posture == "comparison_pending_observation":
            return "post_mortem_requires_execution_clarification"
        return "post_mortem_ready_expected_vs_realized"

    def _evidence_quality(
        self,
        value: object,
        *,
        post_mortem_status: str,
    ) -> str:
        explicit_value = self._optional_text(value)
        if explicit_value is not None:
            return explicit_value
        if post_mortem_status == "fallback_template_applied":
            return "immature_observation_horizon"
        return "insufficient_reconstructible_evidence"

    def _confidence_posture(self, value: object, *, evidence_quality: str) -> str:
        explicit_value = self._optional_text(value)
        if explicit_value is not None:
            return explicit_value
        if evidence_quality == "strong_reconstructible_evidence":
            return "confident_for_attribution"
        if evidence_quality == "mixed_evidence_requires_caution":
            return "cautious_for_review_only"
        return "insufficient_for_confident_judgment"

    def _learning_direction(self, value: object, *, post_mortem_status: str) -> str:
        explicit_value = self._optional_text(value)
        if explicit_value is not None:
            return explicit_value
        if post_mortem_status == "fallback_template_applied":
            return "defer_learning_until_evidence_matures"
        return "withhold_learning_update"

    def _post_mortem_reason(
        self,
        *,
        execution_outcome: ExecutionOutcomeRecord,
        post_mortem_status: str,
        post_mortem_judgment_class_id: str,
        missing_post_mortem_fields: tuple[str, ...],
        prohibited_judgment_fields_present: tuple[str, ...],
    ) -> str:
        if execution_outcome.execution_outcome_status == "blocked":
            return (
                "Post-mortem judgment requires a legitimate execution outcome record "
                "and cannot proceed from execution outcome status "
                f"'{execution_outcome.execution_outcome_status}'."
            )
        if missing_post_mortem_fields:
            return (
                "Post-mortem judgment is missing required attribution fields: "
                + ", ".join(missing_post_mortem_fields)
                + "."
            )
        if prohibited_judgment_fields_present:
            return (
                "Post-mortem judgment class "
                f"'{post_mortem_judgment_class_id}' cannot carry policy-learning admission, reopen, monitoring, or execution-control fields: "
                + ", ".join(prohibited_judgment_fields_present)
                + "."
            )
        if post_mortem_status == "fallback_template_applied":
            return (
                "A governed fallback post-mortem template was applied because the "
                "outcome evidence remains deferred or immature and therefore cannot "
                "support a confident attribution judgment yet."
            )
        return "Post-mortem judgment capture is complete and ready for downstream governed use."

    def _lineage(
        self,
        request: PostMortemJudgmentRequest,
        class_definition,
        template,
    ) -> dict[str, str]:
        lineage = dict(request.execution_outcome.lineage)
        lineage.update(
            {
                "execution_outcome_id": request.execution_outcome.execution_outcome_id,
                "execution_outcome_class_id": (
                    request.execution_outcome.execution_outcome_class_id
                ),
                "execution_outcome_class_version": (
                    request.execution_outcome.lineage.get(
                        "execution_outcome_class_version",
                        "unknown",
                    )
                ),
                "execution_outcome_template_id": (
                    request.execution_outcome.execution_outcome_template_id
                ),
                "execution_outcome_template_version": (
                    request.execution_outcome.lineage.get(
                        "execution_outcome_template_version",
                        "unknown",
                    )
                ),
                "post_mortem_judgment_class_id": (
                    class_definition.post_mortem_judgment_class_id
                ),
                "post_mortem_judgment_class_version": (
                    class_definition.lineage.get("version", "unknown")
                ),
                "post_mortem_judgment_template_id": (
                    template.post_mortem_judgment_template_id
                ),
                "post_mortem_judgment_template_version": (
                    template.lineage.get("version", "unknown")
                ),
            }
        )
        if request.execution_outcome.route_name is not None:
            lineage["route_name"] = request.execution_outcome.route_name
        if request.execution_outcome.threshold_id is not None:
            lineage["threshold_id"] = request.execution_outcome.threshold_id
        if request.execution_outcome.trigger_class is not None:
            lineage["trigger_class"] = request.execution_outcome.trigger_class
        return lineage

    def _optional_text(self, value: object) -> str | None:
        if value is None or value == "":
            return None
        return self._to_text(value)

    def _sequence_as_tuple(self, value: object) -> tuple[str, ...]:
        if value is None or value == "" or value == ():
            return ()
        if isinstance(value, str):
            return (value,)
        if isinstance(value, Sequence):
            return tuple(
                self._to_text(item)
                for item in value
                if item not in {None, ""}
            )
        return (self._to_text(value),)

    def _to_text(self, value: object) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)