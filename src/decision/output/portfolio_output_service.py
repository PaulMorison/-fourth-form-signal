from __future__ import annotations

"""Deterministic portfolio-output generation after policy-output recording.

Canon ownership:
- Converts legitimate policy-output records plus explicit portfolio-output
  context into governed portfolio outputs.
- Owns allocation posture, weight posture, action-boundary legitimacy,
  lineage, and audit trace for portfolio outputs.
- Does not redefine policy meaning, recommendation meaning, issue commitments
  or instructions, execute playbooks, own escalation posture, own state
  progression, or absorb authority meaning.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Mapping
from uuid import uuid4

from decision.output.policy_output_service import PolicyOutputRecord
from decision.output.portfolio_output_audit_adapter import PortfolioOutputAuditAdapter
from decision.output.portfolio_output_registry import PortfolioOutputRegistry


@dataclass(frozen=True)
class PortfolioOutputRequest:
    policy_output: PolicyOutputRecord
    portfolio_output_class_id: str
    portfolio_author_role: str
    portfolio_output_context: Mapping[str, object]
    correlation_id: str
    actor_id: str


@dataclass(frozen=True)
class PortfolioOutputRecord:
    portfolio_output_id: str
    portfolio_output_status: str
    reason: str
    portfolio_output_class_id: str
    portfolio_output_template_id: str
    allocation_posture: str
    weight_posture: str
    action_boundary_posture: str
    promotion_safe_use: str
    policy_output_id: str
    policy_output_status: str
    policy_output_class_id: str
    policy_output_template_id: str
    bounded_policy_posture: str
    policy_output_action_boundary_posture: str
    policy_output_promotion_safe_use: str
    recommendation_id: str
    recommendation_status: str
    recommendation_class_id: str
    recommendation_template_id: str
    recommendation_action_class: str
    recommendation_advisory_status: str
    recommendation_commitment_readiness: str
    review_resolution_id: str
    review_resolution_status: str
    resolution_class_id: str
    resolution_state: str
    review_outcome: str
    disposition_class_id: str
    disposition_state: str
    closure_state: str
    closure_quality: str
    packet_id: str
    packet_template_id: str
    packet_status: str
    handoff_ready: bool
    semantic_scope: str
    case_type: str
    case_key: str
    state_model_name: str
    episode_id: str
    transition_name: str
    transition_class: str
    source_stage: str
    target_stage: str
    reviewer_role: str
    reviewer_id: str
    recommender_role: str
    recommender_id: str
    policy_author_role: str
    policy_author_id: str
    portfolio_author_role: str
    portfolio_author_id: str
    authority_resolution_kind: str
    authority_review_required: bool
    router_rule_id: str
    routing_resolution_status: str
    routing_review_required: bool
    review_mode: str
    reason_class: str
    packet_scope: str
    handoff_channel: str
    handoff_purpose: str
    required_context_fields: tuple[str, ...]
    optional_context_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    prohibited_context_fields: tuple[str, ...]
    required_context_snapshot: Mapping[str, str]
    optional_context_snapshot: Mapping[str, str]
    required_audit_snapshot: Mapping[str, str]
    lineage: Mapping[str, str]
    generated_at: datetime
    route_name: str | None = None
    threshold_id: str | None = None
    trigger_class: str | None = None
    playbook_reference: str | None = None
    missing_context_fields: tuple[str, ...] = ()
    prohibited_context_fields_present: tuple[str, ...] = ()

    def to_contract_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "portfolio_output_id": self.portfolio_output_id,
            "portfolio_output_status": self.portfolio_output_status,
            "reason": self.reason,
            "portfolio_output_class_id": self.portfolio_output_class_id,
            "portfolio_output_template_id": self.portfolio_output_template_id,
            "allocation_posture": self.allocation_posture,
            "weight_posture": self.weight_posture,
            "action_boundary_posture": self.action_boundary_posture,
            "promotion_safe_use": self.promotion_safe_use,
            "policy_output_id": self.policy_output_id,
            "policy_output_status": self.policy_output_status,
            "policy_output_class_id": self.policy_output_class_id,
            "policy_output_template_id": self.policy_output_template_id,
            "bounded_policy_posture": self.bounded_policy_posture,
            "policy_output_action_boundary_posture": self.policy_output_action_boundary_posture,
            "policy_output_promotion_safe_use": self.policy_output_promotion_safe_use,
            "recommendation_id": self.recommendation_id,
            "recommendation_status": self.recommendation_status,
            "recommendation_class_id": self.recommendation_class_id,
            "recommendation_template_id": self.recommendation_template_id,
            "recommendation_action_class": self.recommendation_action_class,
            "recommendation_advisory_status": self.recommendation_advisory_status,
            "recommendation_commitment_readiness": self.recommendation_commitment_readiness,
            "review_resolution_id": self.review_resolution_id,
            "review_resolution_status": self.review_resolution_status,
            "resolution_class_id": self.resolution_class_id,
            "resolution_state": self.resolution_state,
            "review_outcome": self.review_outcome,
            "disposition_class_id": self.disposition_class_id,
            "disposition_state": self.disposition_state,
            "closure_state": self.closure_state,
            "closure_quality": self.closure_quality,
            "packet_id": self.packet_id,
            "packet_template_id": self.packet_template_id,
            "packet_status": self.packet_status,
            "handoff_ready": self.handoff_ready,
            "semantic_scope": self.semantic_scope,
            "case_type": self.case_type,
            "case_key": self.case_key,
            "state_model_name": self.state_model_name,
            "episode_id": self.episode_id,
            "transition_name": self.transition_name,
            "transition_class": self.transition_class,
            "source_stage": self.source_stage,
            "target_stage": self.target_stage,
            "reviewer_role": self.reviewer_role,
            "reviewer_id": self.reviewer_id,
            "recommender_role": self.recommender_role,
            "recommender_id": self.recommender_id,
            "policy_author_role": self.policy_author_role,
            "policy_author_id": self.policy_author_id,
            "portfolio_author_role": self.portfolio_author_role,
            "portfolio_author_id": self.portfolio_author_id,
            "authority_resolution_kind": self.authority_resolution_kind,
            "authority_review_required": self.authority_review_required,
            "router_rule_id": self.router_rule_id,
            "routing_resolution_status": self.routing_resolution_status,
            "routing_review_required": self.routing_review_required,
            "review_mode": self.review_mode,
            "reason_class": self.reason_class,
            "packet_scope": self.packet_scope,
            "handoff_channel": self.handoff_channel,
            "handoff_purpose": self.handoff_purpose,
            "required_context_fields": list(self.required_context_fields),
            "optional_context_fields": list(self.optional_context_fields),
            "required_audit_fields": list(self.required_audit_fields),
            "prohibited_context_fields": list(self.prohibited_context_fields),
            "required_context_snapshot": dict(self.required_context_snapshot),
            "optional_context_snapshot": dict(self.optional_context_snapshot),
            "required_audit_snapshot": dict(self.required_audit_snapshot),
            "lineage": dict(self.lineage),
            "generated_at": self.generated_at.isoformat(),
        }
        if self.route_name is not None:
            payload["route_name"] = self.route_name
        if self.threshold_id is not None:
            payload["threshold_id"] = self.threshold_id
        if self.trigger_class is not None:
            payload["trigger_class"] = self.trigger_class
        if self.playbook_reference is not None:
            payload["playbook_reference"] = self.playbook_reference
        if self.missing_context_fields:
            payload["missing_context_fields"] = list(self.missing_context_fields)
        if self.prohibited_context_fields_present:
            payload["prohibited_context_fields_present"] = list(
                self.prohibited_context_fields_present
            )
        return payload


class PortfolioOutputService:
    """Builds governed portfolio outputs from legitimate policy outputs."""

    def __init__(
        self,
        *,
        portfolio_output_registry: PortfolioOutputRegistry,
        portfolio_output_audit_adapter: PortfolioOutputAuditAdapter,
    ) -> None:
        self._portfolio_output_registry = portfolio_output_registry
        self._portfolio_output_audit_adapter = portfolio_output_audit_adapter

    def generate(self, request: PortfolioOutputRequest) -> PortfolioOutputRecord:
        portfolio_output_template, fallback_template_used = (
            self._portfolio_output_registry.resolve_template(
                semantic_scope=request.policy_output.semantic_scope,
                resolution_class_id=request.policy_output.resolution_class_id,
                disposition_class_id=request.policy_output.disposition_class_id,
                recommendation_class_id=request.policy_output.recommendation_class_id,
                policy_output_class_id=request.policy_output.policy_output_class_id,
                portfolio_output_class_id=request.portfolio_output_class_id,
                route_name=request.policy_output.route_name,
            )
        )
        portfolio_output_class = self._portfolio_output_registry.get_portfolio_output_class(
            request.portfolio_output_class_id
        )
        combined_context = self._combined_context(request, portfolio_output_class)
        required_context_snapshot, missing_context_fields = self._snapshot_required_fields(
            portfolio_output_template.required_context_fields,
            combined_context,
        )
        required_audit_snapshot, missing_audit_fields = self._snapshot_required_fields(
            portfolio_output_template.required_audit_fields,
            combined_context,
        )
        all_missing_fields = tuple(
            dict.fromkeys(missing_context_fields + missing_audit_fields)
        )
        optional_context_snapshot = self._snapshot_optional_fields(
            portfolio_output_template.optional_context_fields,
            combined_context,
        )
        prohibited_context_fields_present = self._prohibited_context_fields_present(
            portfolio_output_class.prohibited_context_fields,
            request.portfolio_output_context,
        )

        portfolio_output_status = self._portfolio_output_status(
            policy_output=request.policy_output,
            missing_context_fields=all_missing_fields,
            prohibited_context_fields_present=prohibited_context_fields_present,
            fallback_template_used=fallback_template_used,
        )
        reason = self._portfolio_output_reason(
            policy_output=request.policy_output,
            portfolio_output_status=portfolio_output_status,
            portfolio_output_class_id=portfolio_output_class.portfolio_output_class_id,
            missing_context_fields=all_missing_fields,
            prohibited_context_fields_present=prohibited_context_fields_present,
        )

        portfolio_output = PortfolioOutputRecord(
            portfolio_output_id=str(uuid4()),
            portfolio_output_status=portfolio_output_status,
            reason=reason,
            portfolio_output_class_id=portfolio_output_class.portfolio_output_class_id,
            portfolio_output_template_id=(
                portfolio_output_template.portfolio_output_template_id
            ),
            allocation_posture=portfolio_output_class.allocation_posture,
            weight_posture=portfolio_output_class.weight_posture,
            action_boundary_posture=portfolio_output_class.action_boundary_posture,
            promotion_safe_use=portfolio_output_class.promotion_safe_use,
            policy_output_id=request.policy_output.policy_output_id,
            policy_output_status=request.policy_output.policy_output_status,
            policy_output_class_id=request.policy_output.policy_output_class_id,
            policy_output_template_id=request.policy_output.policy_output_template_id,
            bounded_policy_posture=request.policy_output.bounded_policy_posture,
            policy_output_action_boundary_posture=(
                request.policy_output.action_boundary_posture
            ),
            policy_output_promotion_safe_use=request.policy_output.promotion_safe_use,
            recommendation_id=request.policy_output.recommendation_id,
            recommendation_status=request.policy_output.recommendation_status,
            recommendation_class_id=request.policy_output.recommendation_class_id,
            recommendation_template_id=request.policy_output.recommendation_template_id,
            recommendation_action_class=request.policy_output.recommendation_action_class,
            recommendation_advisory_status=(
                request.policy_output.recommendation_advisory_status
            ),
            recommendation_commitment_readiness=(
                request.policy_output.recommendation_commitment_readiness
            ),
            review_resolution_id=request.policy_output.review_resolution_id,
            review_resolution_status=request.policy_output.review_resolution_status,
            resolution_class_id=request.policy_output.resolution_class_id,
            resolution_state=request.policy_output.resolution_state,
            review_outcome=request.policy_output.review_outcome,
            disposition_class_id=request.policy_output.disposition_class_id,
            disposition_state=request.policy_output.disposition_state,
            closure_state=request.policy_output.closure_state,
            closure_quality=request.policy_output.closure_quality,
            packet_id=request.policy_output.packet_id,
            packet_template_id=request.policy_output.packet_template_id,
            packet_status=request.policy_output.packet_status,
            handoff_ready=request.policy_output.handoff_ready,
            semantic_scope=request.policy_output.semantic_scope,
            case_type=request.policy_output.case_type,
            case_key=request.policy_output.case_key,
            state_model_name=request.policy_output.state_model_name,
            episode_id=request.policy_output.episode_id,
            transition_name=request.policy_output.transition_name,
            transition_class=request.policy_output.transition_class,
            source_stage=request.policy_output.source_stage,
            target_stage=request.policy_output.target_stage,
            reviewer_role=request.policy_output.reviewer_role,
            reviewer_id=request.policy_output.reviewer_id,
            recommender_role=request.policy_output.recommender_role,
            recommender_id=request.policy_output.recommender_id,
            policy_author_role=request.policy_output.policy_author_role,
            policy_author_id=request.policy_output.policy_author_id,
            portfolio_author_role=request.portfolio_author_role,
            portfolio_author_id=request.actor_id,
            authority_resolution_kind=request.policy_output.authority_resolution_kind,
            authority_review_required=request.policy_output.authority_review_required,
            router_rule_id=request.policy_output.router_rule_id,
            routing_resolution_status=request.policy_output.routing_resolution_status,
            routing_review_required=request.policy_output.routing_review_required,
            review_mode=request.policy_output.review_mode,
            reason_class=request.policy_output.reason_class,
            packet_scope=request.policy_output.packet_scope,
            handoff_channel=request.policy_output.handoff_channel,
            handoff_purpose=request.policy_output.handoff_purpose,
            required_context_fields=portfolio_output_template.required_context_fields,
            optional_context_fields=portfolio_output_template.optional_context_fields,
            required_audit_fields=portfolio_output_template.required_audit_fields,
            prohibited_context_fields=portfolio_output_class.prohibited_context_fields,
            required_context_snapshot=required_context_snapshot,
            optional_context_snapshot=optional_context_snapshot,
            required_audit_snapshot=required_audit_snapshot,
            lineage=self._lineage(
                request,
                portfolio_output_class,
                portfolio_output_template,
            ),
            generated_at=datetime.now(tz=UTC),
            route_name=request.policy_output.route_name,
            threshold_id=request.policy_output.threshold_id,
            trigger_class=request.policy_output.trigger_class,
            playbook_reference=request.policy_output.playbook_reference,
            missing_context_fields=all_missing_fields,
            prohibited_context_fields_present=prohibited_context_fields_present,
        )
        self._portfolio_output_audit_adapter.record_portfolio_output(
            portfolio_output,
            request=request,
        )
        return portfolio_output

    def _combined_context(
        self,
        request: PortfolioOutputRequest,
        portfolio_output_class,
    ) -> dict[str, object]:
        context = dict(request.policy_output.required_context_snapshot)
        context.update(request.policy_output.optional_context_snapshot)
        context.update(request.policy_output.required_audit_snapshot)
        context.update(dict(request.portfolio_output_context))
        context.update(
            {
                "portfolio_output_class_id": portfolio_output_class.portfolio_output_class_id,
                "allocation_posture": portfolio_output_class.allocation_posture,
                "weight_posture": portfolio_output_class.weight_posture,
                "action_boundary_posture": portfolio_output_class.action_boundary_posture,
                "promotion_safe_use": portfolio_output_class.promotion_safe_use,
                "policy_output_id": request.policy_output.policy_output_id,
                "policy_output_status": request.policy_output.policy_output_status,
                "policy_output_class_id": request.policy_output.policy_output_class_id,
                "policy_output_template_id": request.policy_output.policy_output_template_id,
                "bounded_policy_posture": request.policy_output.bounded_policy_posture,
                "policy_output_action_boundary_posture": (
                    request.policy_output.action_boundary_posture
                ),
                "policy_output_promotion_safe_use": request.policy_output.promotion_safe_use,
                "recommendation_id": request.policy_output.recommendation_id,
                "recommendation_status": request.policy_output.recommendation_status,
                "recommendation_class_id": request.policy_output.recommendation_class_id,
                "recommendation_template_id": request.policy_output.recommendation_template_id,
                "review_resolution_id": request.policy_output.review_resolution_id,
                "review_resolution_status": request.policy_output.review_resolution_status,
                "resolution_class_id": request.policy_output.resolution_class_id,
                "disposition_class_id": request.policy_output.disposition_class_id,
                "packet_id": request.policy_output.packet_id,
                "packet_template_id": request.policy_output.packet_template_id,
                "packet_status": request.policy_output.packet_status,
                "case_key": request.policy_output.case_key,
                "route_name": request.policy_output.route_name or "",
                "threshold_id": request.policy_output.threshold_id or "",
                "trigger_class": request.policy_output.trigger_class or "",
                "playbook_reference": request.policy_output.playbook_reference or "",
                "portfolio_author_id": request.actor_id,
                "portfolio_author_role": request.portfolio_author_role,
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
            if value is None or value == "":
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
            if value is None or value == "":
                continue
            snapshot[field_name] = self._to_text(value)
        return snapshot

    def _prohibited_context_fields_present(
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

    def _portfolio_output_status(
        self,
        *,
        policy_output: PolicyOutputRecord,
        missing_context_fields: tuple[str, ...],
        prohibited_context_fields_present: tuple[str, ...],
        fallback_template_used: bool,
    ) -> str:
        if policy_output.policy_output_status == "blocked":
            return "blocked"
        if missing_context_fields or prohibited_context_fields_present:
            return "blocked"
        if fallback_template_used:
            return "fallback_template_applied"
        return "ready_for_downstream_use"

    def _portfolio_output_reason(
        self,
        *,
        policy_output: PolicyOutputRecord,
        portfolio_output_status: str,
        portfolio_output_class_id: str,
        missing_context_fields: tuple[str, ...],
        prohibited_context_fields_present: tuple[str, ...],
    ) -> str:
        if policy_output.policy_output_status == "blocked":
            return (
                "Portfolio output generation requires a legitimate policy output record and cannot proceed "
                f"from policy output status '{policy_output.policy_output_status}'."
            )
        if missing_context_fields:
            return (
                "Portfolio output is missing required context fields: "
                + ", ".join(missing_context_fields)
                + "."
            )
        if prohibited_context_fields_present:
            return (
                f"Portfolio output class '{portfolio_output_class_id}' cannot carry instruction-like or commitment-like context fields: "
                + ", ".join(prohibited_context_fields_present)
                + "."
            )
        if portfolio_output_status == "fallback_template_applied":
            return (
                "A governed fallback portfolio-output template was applied because no route-specific portfolio-output template exists for the governed policy output."
            )
        return "Portfolio output is complete and ready for downstream governed use."

    def _lineage(
        self,
        request: PortfolioOutputRequest,
        portfolio_output_class,
        portfolio_output_template,
    ) -> dict[str, str]:
        lineage = {
            "policy_output_id": request.policy_output.policy_output_id,
            "policy_output_class_id": request.policy_output.policy_output_class_id,
            "policy_output_class_version": request.policy_output.lineage.get(
                "policy_output_class_version",
                "unknown",
            ),
            "policy_output_template_id": request.policy_output.policy_output_template_id,
            "policy_output_template_version": request.policy_output.lineage.get(
                "policy_output_template_version",
                "unknown",
            ),
            "recommendation_id": request.policy_output.recommendation_id,
            "recommendation_class_id": request.policy_output.recommendation_class_id,
            "review_resolution_id": request.policy_output.review_resolution_id,
            "resolution_class_id": request.policy_output.resolution_class_id,
            "disposition_class_id": request.policy_output.disposition_class_id,
            "packet_id": request.policy_output.packet_id,
            "packet_template_id": request.policy_output.packet_template_id,
            "portfolio_output_class_id": portfolio_output_class.portfolio_output_class_id,
            "portfolio_output_class_version": portfolio_output_class.lineage.get(
                "version",
                "unknown",
            ),
            "portfolio_output_template_id": (
                portfolio_output_template.portfolio_output_template_id
            ),
            "portfolio_output_template_version": (
                portfolio_output_template.lineage.get("version", "unknown")
            ),
            "router_rule_id": request.policy_output.router_rule_id,
            "authority_resolution_kind": request.policy_output.authority_resolution_kind,
        }
        if request.policy_output.route_name is not None:
            lineage["route_name"] = request.policy_output.route_name
        if request.policy_output.threshold_id is not None:
            lineage["threshold_id"] = request.policy_output.threshold_id
        if request.policy_output.trigger_class is not None:
            lineage["trigger_class"] = request.policy_output.trigger_class
        return lineage

    def _to_text(self, value: object) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)