from __future__ import annotations

"""Deterministic action-instruction generation after portfolio-output recording.

Canon ownership:
- Converts legitimate portfolio-output records plus explicit instruction
  context into governed action instructions.
- Owns action-instruction legitimacy, completeness, lineage, bounded action
  posture, and explicit separation between instruction and execution.
- Does not redefine portfolio, policy, recommendation, review, authority,
  router, execution, or reopen meaning.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Mapping, Sequence
from uuid import uuid4

from decision.output.action_instruction_audit_adapter import ActionInstructionAuditAdapter
from decision.output.action_instruction_registry import ActionInstructionRegistry
from decision.output.portfolio_output_service import PortfolioOutputRecord


@dataclass(frozen=True)
class ActionInstructionRequest:
    portfolio_output: PortfolioOutputRecord
    action_instruction_class_id: str
    instruction_author_role: str
    action_instruction_context: Mapping[str, object]
    correlation_id: str
    actor_id: str


@dataclass(frozen=True)
class ActionInstructionRecord:
    action_instruction_id: str
    action_instruction_status: str
    reason: str
    action_instruction_class_id: str
    action_instruction_template_id: str
    instruction_status: str
    bounded_action_posture: str
    execution_boundary_posture: str
    promotion_safe_use: str
    portfolio_output_id: str
    portfolio_output_status: str
    portfolio_output_class_id: str
    portfolio_output_template_id: str
    allocation_posture: str
    weight_posture: str
    portfolio_output_action_boundary_posture: str
    portfolio_output_promotion_safe_use: str
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
    instruction_author_role: str
    instruction_author_id: str
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
    required_instruction_fields: tuple[str, ...]
    optional_instruction_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    prohibited_execution_fields: tuple[str, ...]
    required_instruction_snapshot: Mapping[str, str]
    optional_instruction_snapshot: Mapping[str, str]
    required_audit_snapshot: Mapping[str, str]
    lineage: Mapping[str, str]
    generated_at: datetime
    route_name: str | None = None
    threshold_id: str | None = None
    trigger_class: str | None = None
    playbook_reference: str | None = None
    upstream_commitment_reference: str | None = None
    instruction_authority_reference: str | None = None
    executable_scope_reference: str | None = None
    blocking_condition_kind: str | None = None
    blocking_condition_references: tuple[str, ...] = ()
    invalidation_reference: str | None = None
    unauthorized_instruction_reference: str | None = None
    reopen_reference: str | None = None
    missing_instruction_fields: tuple[str, ...] = ()
    prohibited_execution_fields_present: tuple[str, ...] = ()

    def to_contract_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "action_instruction_id": self.action_instruction_id,
            "action_instruction_status": self.action_instruction_status,
            "reason": self.reason,
            "action_instruction_class_id": self.action_instruction_class_id,
            "action_instruction_template_id": self.action_instruction_template_id,
            "instruction_status": self.instruction_status,
            "bounded_action_posture": self.bounded_action_posture,
            "execution_boundary_posture": self.execution_boundary_posture,
            "promotion_safe_use": self.promotion_safe_use,
            "portfolio_output_id": self.portfolio_output_id,
            "portfolio_output_status": self.portfolio_output_status,
            "portfolio_output_class_id": self.portfolio_output_class_id,
            "portfolio_output_template_id": self.portfolio_output_template_id,
            "allocation_posture": self.allocation_posture,
            "weight_posture": self.weight_posture,
            "portfolio_output_action_boundary_posture": self.portfolio_output_action_boundary_posture,
            "portfolio_output_promotion_safe_use": self.portfolio_output_promotion_safe_use,
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
            "instruction_author_role": self.instruction_author_role,
            "instruction_author_id": self.instruction_author_id,
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
            "required_instruction_fields": list(self.required_instruction_fields),
            "optional_instruction_fields": list(self.optional_instruction_fields),
            "required_audit_fields": list(self.required_audit_fields),
            "prohibited_execution_fields": list(self.prohibited_execution_fields),
            "required_instruction_snapshot": dict(self.required_instruction_snapshot),
            "optional_instruction_snapshot": dict(self.optional_instruction_snapshot),
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
        if self.upstream_commitment_reference is not None:
            payload["upstream_commitment_reference"] = self.upstream_commitment_reference
        if self.instruction_authority_reference is not None:
            payload["instruction_authority_reference"] = self.instruction_authority_reference
        if self.executable_scope_reference is not None:
            payload["executable_scope_reference"] = self.executable_scope_reference
        if self.blocking_condition_kind is not None:
            payload["blocking_condition_kind"] = self.blocking_condition_kind
        if self.blocking_condition_references:
            payload["blocking_condition_references"] = list(
                self.blocking_condition_references
            )
        if self.invalidation_reference is not None:
            payload["invalidation_reference"] = self.invalidation_reference
        if self.unauthorized_instruction_reference is not None:
            payload["unauthorized_instruction_reference"] = (
                self.unauthorized_instruction_reference
            )
        if self.reopen_reference is not None:
            payload["reopen_reference"] = self.reopen_reference
        if self.missing_instruction_fields:
            payload["missing_instruction_fields"] = list(self.missing_instruction_fields)
        if self.prohibited_execution_fields_present:
            payload["prohibited_execution_fields_present"] = list(
                self.prohibited_execution_fields_present
            )
        return payload


class ActionInstructionService:
    """Builds governed action instructions from legitimate portfolio outputs."""

    def __init__(
        self,
        *,
        action_instruction_registry: ActionInstructionRegistry,
        action_instruction_audit_adapter: ActionInstructionAuditAdapter,
    ) -> None:
        self._action_instruction_registry = action_instruction_registry
        self._action_instruction_audit_adapter = action_instruction_audit_adapter

    def generate(self, request: ActionInstructionRequest) -> ActionInstructionRecord:
        action_instruction_template, fallback_template_used = (
            self._action_instruction_registry.resolve_template(
                semantic_scope=request.portfolio_output.semantic_scope,
                resolution_class_id=request.portfolio_output.resolution_class_id,
                disposition_class_id=request.portfolio_output.disposition_class_id,
                recommendation_class_id=request.portfolio_output.recommendation_class_id,
                policy_output_class_id=request.portfolio_output.policy_output_class_id,
                portfolio_output_class_id=request.portfolio_output.portfolio_output_class_id,
                action_instruction_class_id=request.action_instruction_class_id,
                route_name=request.portfolio_output.route_name,
            )
        )
        action_instruction_class = self._action_instruction_registry.get_action_instruction_class(
            request.action_instruction_class_id
        )
        combined_context = self._combined_context(request, action_instruction_class)
        required_instruction_snapshot, missing_instruction_fields = (
            self._snapshot_required_fields(
                action_instruction_template.required_instruction_fields,
                combined_context,
            )
        )
        required_audit_snapshot, missing_audit_fields = self._snapshot_required_fields(
            action_instruction_template.required_audit_fields,
            combined_context,
        )
        all_missing_fields = tuple(
            dict.fromkeys(missing_instruction_fields + missing_audit_fields)
        )
        optional_instruction_snapshot = self._snapshot_optional_fields(
            action_instruction_template.optional_instruction_fields,
            combined_context,
        )
        prohibited_execution_fields_present = self._prohibited_execution_fields_present(
            action_instruction_class.prohibited_execution_fields,
            request.action_instruction_context,
        )
        action_instruction_status = self._action_instruction_status(
            portfolio_output=request.portfolio_output,
            missing_instruction_fields=all_missing_fields,
            prohibited_execution_fields_present=prohibited_execution_fields_present,
            fallback_template_used=fallback_template_used,
        )
        instruction_status = self._instruction_status(
            template_instruction_status=action_instruction_template.instruction_status,
            action_instruction_status=action_instruction_status,
            missing_instruction_fields=all_missing_fields,
            prohibited_execution_fields_present=prohibited_execution_fields_present,
            context=request.action_instruction_context,
        )
        reason = self._action_instruction_reason(
            portfolio_output=request.portfolio_output,
            action_instruction_status=action_instruction_status,
            action_instruction_class_id=action_instruction_class.action_instruction_class_id,
            missing_instruction_fields=all_missing_fields,
            prohibited_execution_fields_present=prohibited_execution_fields_present,
        )

        action_instruction = ActionInstructionRecord(
            action_instruction_id=str(uuid4()),
            action_instruction_status=action_instruction_status,
            reason=reason,
            action_instruction_class_id=action_instruction_class.action_instruction_class_id,
            action_instruction_template_id=(
                action_instruction_template.action_instruction_template_id
            ),
            instruction_status=instruction_status,
            bounded_action_posture=action_instruction_class.bounded_action_posture,
            execution_boundary_posture=action_instruction_class.execution_boundary_posture,
            promotion_safe_use=action_instruction_class.promotion_safe_use,
            portfolio_output_id=request.portfolio_output.portfolio_output_id,
            portfolio_output_status=request.portfolio_output.portfolio_output_status,
            portfolio_output_class_id=request.portfolio_output.portfolio_output_class_id,
            portfolio_output_template_id=request.portfolio_output.portfolio_output_template_id,
            allocation_posture=request.portfolio_output.allocation_posture,
            weight_posture=request.portfolio_output.weight_posture,
            portfolio_output_action_boundary_posture=(
                request.portfolio_output.action_boundary_posture
            ),
            portfolio_output_promotion_safe_use=request.portfolio_output.promotion_safe_use,
            policy_output_id=request.portfolio_output.policy_output_id,
            policy_output_status=request.portfolio_output.policy_output_status,
            policy_output_class_id=request.portfolio_output.policy_output_class_id,
            policy_output_template_id=request.portfolio_output.policy_output_template_id,
            bounded_policy_posture=request.portfolio_output.bounded_policy_posture,
            policy_output_action_boundary_posture=(
                request.portfolio_output.policy_output_action_boundary_posture
            ),
            policy_output_promotion_safe_use=(
                request.portfolio_output.policy_output_promotion_safe_use
            ),
            recommendation_id=request.portfolio_output.recommendation_id,
            recommendation_status=request.portfolio_output.recommendation_status,
            recommendation_class_id=request.portfolio_output.recommendation_class_id,
            recommendation_template_id=request.portfolio_output.recommendation_template_id,
            recommendation_action_class=request.portfolio_output.recommendation_action_class,
            recommendation_advisory_status=(
                request.portfolio_output.recommendation_advisory_status
            ),
            recommendation_commitment_readiness=(
                request.portfolio_output.recommendation_commitment_readiness
            ),
            review_resolution_id=request.portfolio_output.review_resolution_id,
            review_resolution_status=request.portfolio_output.review_resolution_status,
            resolution_class_id=request.portfolio_output.resolution_class_id,
            resolution_state=request.portfolio_output.resolution_state,
            review_outcome=request.portfolio_output.review_outcome,
            disposition_class_id=request.portfolio_output.disposition_class_id,
            disposition_state=request.portfolio_output.disposition_state,
            closure_state=request.portfolio_output.closure_state,
            closure_quality=request.portfolio_output.closure_quality,
            packet_id=request.portfolio_output.packet_id,
            packet_template_id=request.portfolio_output.packet_template_id,
            packet_status=request.portfolio_output.packet_status,
            handoff_ready=request.portfolio_output.handoff_ready,
            semantic_scope=request.portfolio_output.semantic_scope,
            case_type=request.portfolio_output.case_type,
            case_key=request.portfolio_output.case_key,
            state_model_name=request.portfolio_output.state_model_name,
            episode_id=request.portfolio_output.episode_id,
            transition_name=request.portfolio_output.transition_name,
            transition_class=request.portfolio_output.transition_class,
            source_stage=request.portfolio_output.source_stage,
            target_stage=request.portfolio_output.target_stage,
            reviewer_role=request.portfolio_output.reviewer_role,
            reviewer_id=request.portfolio_output.reviewer_id,
            recommender_role=request.portfolio_output.recommender_role,
            recommender_id=request.portfolio_output.recommender_id,
            policy_author_role=request.portfolio_output.policy_author_role,
            policy_author_id=request.portfolio_output.policy_author_id,
            portfolio_author_role=request.portfolio_output.portfolio_author_role,
            portfolio_author_id=request.portfolio_output.portfolio_author_id,
            instruction_author_role=request.instruction_author_role,
            instruction_author_id=request.actor_id,
            authority_resolution_kind=request.portfolio_output.authority_resolution_kind,
            authority_review_required=request.portfolio_output.authority_review_required,
            router_rule_id=request.portfolio_output.router_rule_id,
            routing_resolution_status=request.portfolio_output.routing_resolution_status,
            routing_review_required=request.portfolio_output.routing_review_required,
            review_mode=request.portfolio_output.review_mode,
            reason_class=request.portfolio_output.reason_class,
            packet_scope=request.portfolio_output.packet_scope,
            handoff_channel=request.portfolio_output.handoff_channel,
            handoff_purpose=request.portfolio_output.handoff_purpose,
            required_instruction_fields=(
                action_instruction_template.required_instruction_fields
            ),
            optional_instruction_fields=(
                action_instruction_template.optional_instruction_fields
            ),
            required_audit_fields=action_instruction_template.required_audit_fields,
            prohibited_execution_fields=(
                action_instruction_class.prohibited_execution_fields
            ),
            required_instruction_snapshot=required_instruction_snapshot,
            optional_instruction_snapshot=optional_instruction_snapshot,
            required_audit_snapshot=required_audit_snapshot,
            lineage=self._lineage(
                request,
                action_instruction_class,
                action_instruction_template,
            ),
            generated_at=datetime.now(tz=UTC),
            route_name=request.portfolio_output.route_name,
            threshold_id=request.portfolio_output.threshold_id,
            trigger_class=request.portfolio_output.trigger_class,
            playbook_reference=request.portfolio_output.playbook_reference,
            upstream_commitment_reference=self._optional_text(
                request.action_instruction_context.get("upstream_commitment_reference")
            ),
            instruction_authority_reference=self._optional_text(
                request.action_instruction_context.get("instruction_authority_reference")
            ),
            executable_scope_reference=self._optional_text(
                request.action_instruction_context.get("executable_scope_reference")
            ),
            blocking_condition_kind=self._optional_text(
                request.action_instruction_context.get("blocking_condition_kind")
            ),
            blocking_condition_references=self._blocking_condition_references(
                request.action_instruction_context
            ),
            invalidation_reference=self._optional_text(
                request.action_instruction_context.get("invalidation_reference")
            ),
            unauthorized_instruction_reference=self._optional_text(
                request.action_instruction_context.get(
                    "unauthorized_instruction_reference"
                )
            ),
            reopen_reference=self._optional_text(
                request.action_instruction_context.get("reopen_reference")
            ),
            missing_instruction_fields=all_missing_fields,
            prohibited_execution_fields_present=prohibited_execution_fields_present,
        )
        self._action_instruction_audit_adapter.record_action_instruction(
            action_instruction,
            request=request,
        )
        return action_instruction

    def _combined_context(
        self,
        request: ActionInstructionRequest,
        action_instruction_class,
    ) -> dict[str, object]:
        context = dict(request.portfolio_output.required_context_snapshot)
        context.update(request.portfolio_output.optional_context_snapshot)
        context.update(request.portfolio_output.required_audit_snapshot)
        context.update(dict(request.action_instruction_context))
        context.update(
            {
                "action_instruction_class_id": (
                    action_instruction_class.action_instruction_class_id
                ),
                "bounded_action_posture": action_instruction_class.bounded_action_posture,
                "execution_boundary_posture": (
                    action_instruction_class.execution_boundary_posture
                ),
                "promotion_safe_use": action_instruction_class.promotion_safe_use,
                "portfolio_output_id": request.portfolio_output.portfolio_output_id,
                "portfolio_output_status": request.portfolio_output.portfolio_output_status,
                "portfolio_output_class_id": (
                    request.portfolio_output.portfolio_output_class_id
                ),
                "portfolio_output_template_id": (
                    request.portfolio_output.portfolio_output_template_id
                ),
                "policy_output_id": request.portfolio_output.policy_output_id,
                "policy_output_status": request.portfolio_output.policy_output_status,
                "policy_output_class_id": request.portfolio_output.policy_output_class_id,
                "policy_output_template_id": (
                    request.portfolio_output.policy_output_template_id
                ),
                "recommendation_id": request.portfolio_output.recommendation_id,
                "recommendation_status": request.portfolio_output.recommendation_status,
                "recommendation_class_id": request.portfolio_output.recommendation_class_id,
                "recommendation_template_id": (
                    request.portfolio_output.recommendation_template_id
                ),
                "review_resolution_id": request.portfolio_output.review_resolution_id,
                "review_resolution_status": (
                    request.portfolio_output.review_resolution_status
                ),
                "resolution_class_id": request.portfolio_output.resolution_class_id,
                "disposition_class_id": request.portfolio_output.disposition_class_id,
                "packet_id": request.portfolio_output.packet_id,
                "packet_template_id": request.portfolio_output.packet_template_id,
                "packet_status": request.portfolio_output.packet_status,
                "case_key": request.portfolio_output.case_key,
                "route_name": request.portfolio_output.route_name or "",
                "threshold_id": request.portfolio_output.threshold_id or "",
                "trigger_class": request.portfolio_output.trigger_class or "",
                "playbook_reference": request.portfolio_output.playbook_reference or "",
                "instruction_author_id": request.actor_id,
                "instruction_author_role": request.instruction_author_role,
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

    def _prohibited_execution_fields_present(
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

    def _action_instruction_status(
        self,
        *,
        portfolio_output: PortfolioOutputRecord,
        missing_instruction_fields: tuple[str, ...],
        prohibited_execution_fields_present: tuple[str, ...],
        fallback_template_used: bool,
    ) -> str:
        if portfolio_output.portfolio_output_status == "blocked":
            return "blocked"
        if missing_instruction_fields or prohibited_execution_fields_present:
            return "blocked"
        if fallback_template_used:
            return "fallback_template_applied"
        return "ready_for_downstream_use"

    def _instruction_status(
        self,
        *,
        template_instruction_status: str,
        action_instruction_status: str,
        missing_instruction_fields: tuple[str, ...],
        prohibited_execution_fields_present: tuple[str, ...],
        context: Mapping[str, object],
    ) -> str:
        unauthorized_instruction_reference = context.get(
            "unauthorized_instruction_reference"
        )
        if unauthorized_instruction_reference not in (None, ""):
            return "unauthorized_instruction_state"
        invalidation_reference = context.get("invalidation_reference")
        if invalidation_reference not in (None, ""):
            return "instruction_invalidated"
        if prohibited_execution_fields_present:
            return "instruction_prohibited"
        blocking_condition_kind = context.get("blocking_condition_kind")
        if blocking_condition_kind == "authority":
            return "instruction_blocked_pending_authority"
        if blocking_condition_kind == "timing":
            return "instruction_blocked_pending_timing"
        if blocking_condition_kind in {"prerequisite", "integrity", "scope"}:
            return "instruction_blocked_pending_prerequisite"
        if action_instruction_status == "blocked":
            if "instruction_authority_reference" in missing_instruction_fields:
                return "instruction_blocked_pending_authority"
            return "instruction_blocked_pending_prerequisite"
        return template_instruction_status

    def _action_instruction_reason(
        self,
        *,
        portfolio_output: PortfolioOutputRecord,
        action_instruction_status: str,
        action_instruction_class_id: str,
        missing_instruction_fields: tuple[str, ...],
        prohibited_execution_fields_present: tuple[str, ...],
    ) -> str:
        if portfolio_output.portfolio_output_status == "blocked":
            return (
                "Action instruction generation requires a legitimate portfolio output record and cannot proceed "
                f"from portfolio output status '{portfolio_output.portfolio_output_status}'."
            )
        if missing_instruction_fields:
            return (
                "Action instruction is missing required instruction fields: "
                + ", ".join(missing_instruction_fields)
                + "."
            )
        if prohibited_execution_fields_present:
            return (
                f"Action instruction class '{action_instruction_class_id}' cannot carry execution fields: "
                + ", ".join(prohibited_execution_fields_present)
                + "."
            )
        if action_instruction_status == "fallback_template_applied":
            return (
                "A governed fallback action-instruction template was applied because no route-specific action-instruction template exists for the governed portfolio output."
            )
        return "Action instruction is complete and ready for downstream governed use."

    def _lineage(
        self,
        request: ActionInstructionRequest,
        action_instruction_class,
        action_instruction_template,
    ) -> dict[str, str]:
        lineage = {
            "portfolio_output_id": request.portfolio_output.portfolio_output_id,
            "portfolio_output_class_id": request.portfolio_output.portfolio_output_class_id,
            "portfolio_output_class_version": request.portfolio_output.lineage.get(
                "portfolio_output_class_version",
                "unknown",
            ),
            "portfolio_output_template_id": (
                request.portfolio_output.portfolio_output_template_id
            ),
            "portfolio_output_template_version": request.portfolio_output.lineage.get(
                "portfolio_output_template_version",
                "unknown",
            ),
            "policy_output_id": request.portfolio_output.policy_output_id,
            "policy_output_class_id": request.portfolio_output.policy_output_class_id,
            "recommendation_id": request.portfolio_output.recommendation_id,
            "review_resolution_id": request.portfolio_output.review_resolution_id,
            "resolution_class_id": request.portfolio_output.resolution_class_id,
            "disposition_class_id": request.portfolio_output.disposition_class_id,
            "packet_id": request.portfolio_output.packet_id,
            "packet_template_id": request.portfolio_output.packet_template_id,
            "action_instruction_class_id": (
                action_instruction_class.action_instruction_class_id
            ),
            "action_instruction_class_version": action_instruction_class.lineage.get(
                "version",
                "unknown",
            ),
            "action_instruction_template_id": (
                action_instruction_template.action_instruction_template_id
            ),
            "action_instruction_template_version": (
                action_instruction_template.lineage.get("version", "unknown")
            ),
            "router_rule_id": request.portfolio_output.router_rule_id,
            "authority_resolution_kind": request.portfolio_output.authority_resolution_kind,
        }
        if request.portfolio_output.route_name is not None:
            lineage["route_name"] = request.portfolio_output.route_name
        if request.portfolio_output.threshold_id is not None:
            lineage["threshold_id"] = request.portfolio_output.threshold_id
        if request.portfolio_output.trigger_class is not None:
            lineage["trigger_class"] = request.portfolio_output.trigger_class
        return lineage

    def _optional_text(self, value: object) -> str | None:
        if value is None or value == "":
            return None
        return self._to_text(value)

    def _blocking_condition_references(
        self,
        context: Mapping[str, object],
    ) -> tuple[str, ...]:
        values: list[str] = []
        single_value = context.get("blocking_condition_reference")
        if single_value not in (None, ""):
            values.append(self._to_text(single_value))
        multi_value = context.get("blocking_condition_references")
        if isinstance(multi_value, Sequence) and not isinstance(
            multi_value,
            (str, bytes, bytearray),
        ):
            for item in multi_value:
                if item in (None, ""):
                    continue
                values.append(self._to_text(item))
        return tuple(dict.fromkeys(values))

    def _to_text(self, value: object) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)