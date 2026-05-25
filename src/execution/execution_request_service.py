from __future__ import annotations

"""Deterministic execution-request generation after action-instruction recording.

Canon ownership:
- Converts legitimate action-instruction records plus explicit execution-request
  context into governed execution requests.
- Owns execution-request legitimacy, completeness, lineage, readiness posture,
  and explicit separation between request and actual execution.
- Does not execute requests, redefine action-instruction meaning, or absorb
  portfolio, policy, recommendation, review, router, or reopen meaning.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Mapping, Sequence
from uuid import uuid4

from decision.output.action_instruction_service import ActionInstructionRecord
from execution.execution_request_audit_adapter import ExecutionRequestAuditAdapter
from execution.execution_request_registry import ExecutionRequestRegistry


@dataclass(frozen=True)
class ExecutionRequestRequest:
    action_instruction: ActionInstructionRecord
    execution_request_class_id: str
    execution_request_author_role: str
    execution_request_context: Mapping[str, object]
    correlation_id: str
    actor_id: str


@dataclass(frozen=True)
class ExecutionRequestRecord:
    execution_request_id: str
    execution_request_status: str
    reason: str
    execution_request_class_id: str
    execution_request_template_id: str
    execution_request_readiness: str
    action_boundary_posture: str
    action_instruction_id: str
    action_instruction_status: str
    action_instruction_class_id: str
    action_instruction_template_id: str
    instruction_status: str
    bounded_action_posture: str
    execution_boundary_posture: str
    action_instruction_promotion_safe_use: str
    portfolio_output_id: str
    portfolio_output_status: str
    portfolio_output_class_id: str
    portfolio_output_template_id: str
    policy_output_id: str
    policy_output_status: str
    policy_output_class_id: str
    policy_output_template_id: str
    recommendation_id: str
    recommendation_status: str
    recommendation_class_id: str
    recommendation_template_id: str
    review_resolution_id: str
    review_resolution_status: str
    resolution_class_id: str
    disposition_class_id: str
    packet_id: str
    packet_template_id: str
    packet_status: str
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
    execution_request_author_role: str
    execution_request_author_id: str
    authority_resolution_kind: str
    authority_review_required: bool
    router_rule_id: str
    routing_resolution_status: str
    routing_review_required: bool
    review_mode: str
    required_execution_request_fields: tuple[str, ...]
    optional_execution_request_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    prohibited_execution_fields: tuple[str, ...]
    required_execution_request_snapshot: Mapping[str, str]
    optional_execution_request_snapshot: Mapping[str, str]
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
    missing_execution_request_fields: tuple[str, ...] = ()
    prohibited_execution_fields_present: tuple[str, ...] = ()

    def to_contract_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "execution_request_id": self.execution_request_id,
            "execution_request_status": self.execution_request_status,
            "reason": self.reason,
            "execution_request_class_id": self.execution_request_class_id,
            "execution_request_template_id": self.execution_request_template_id,
            "execution_request_readiness": self.execution_request_readiness,
            "action_boundary_posture": self.action_boundary_posture,
            "action_instruction_id": self.action_instruction_id,
            "action_instruction_status": self.action_instruction_status,
            "action_instruction_class_id": self.action_instruction_class_id,
            "action_instruction_template_id": self.action_instruction_template_id,
            "instruction_status": self.instruction_status,
            "bounded_action_posture": self.bounded_action_posture,
            "execution_boundary_posture": self.execution_boundary_posture,
            "action_instruction_promotion_safe_use": self.action_instruction_promotion_safe_use,
            "portfolio_output_id": self.portfolio_output_id,
            "portfolio_output_status": self.portfolio_output_status,
            "portfolio_output_class_id": self.portfolio_output_class_id,
            "portfolio_output_template_id": self.portfolio_output_template_id,
            "policy_output_id": self.policy_output_id,
            "policy_output_status": self.policy_output_status,
            "policy_output_class_id": self.policy_output_class_id,
            "policy_output_template_id": self.policy_output_template_id,
            "recommendation_id": self.recommendation_id,
            "recommendation_status": self.recommendation_status,
            "recommendation_class_id": self.recommendation_class_id,
            "recommendation_template_id": self.recommendation_template_id,
            "review_resolution_id": self.review_resolution_id,
            "review_resolution_status": self.review_resolution_status,
            "resolution_class_id": self.resolution_class_id,
            "disposition_class_id": self.disposition_class_id,
            "packet_id": self.packet_id,
            "packet_template_id": self.packet_template_id,
            "packet_status": self.packet_status,
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
            "execution_request_author_role": self.execution_request_author_role,
            "execution_request_author_id": self.execution_request_author_id,
            "authority_resolution_kind": self.authority_resolution_kind,
            "authority_review_required": self.authority_review_required,
            "router_rule_id": self.router_rule_id,
            "routing_resolution_status": self.routing_resolution_status,
            "routing_review_required": self.routing_review_required,
            "review_mode": self.review_mode,
            "required_execution_request_fields": list(self.required_execution_request_fields),
            "optional_execution_request_fields": list(self.optional_execution_request_fields),
            "required_audit_fields": list(self.required_audit_fields),
            "prohibited_execution_fields": list(self.prohibited_execution_fields),
            "required_execution_request_snapshot": dict(
                self.required_execution_request_snapshot
            ),
            "optional_execution_request_snapshot": dict(
                self.optional_execution_request_snapshot
            ),
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
        if self.missing_execution_request_fields:
            payload["missing_execution_request_fields"] = list(
                self.missing_execution_request_fields
            )
        if self.prohibited_execution_fields_present:
            payload["prohibited_execution_fields_present"] = list(
                self.prohibited_execution_fields_present
            )
        return payload


class ExecutionRequestService:
    """Builds governed execution requests from legitimate action instructions."""

    def __init__(
        self,
        *,
        execution_request_registry: ExecutionRequestRegistry,
        execution_request_audit_adapter: ExecutionRequestAuditAdapter,
    ) -> None:
        self._execution_request_registry = execution_request_registry
        self._execution_request_audit_adapter = execution_request_audit_adapter

    def generate(self, request: ExecutionRequestRequest) -> ExecutionRequestRecord:
        execution_request_template, fallback_template_used = (
            self._execution_request_registry.resolve_template(
                semantic_scope=request.action_instruction.semantic_scope,
                resolution_class_id=request.action_instruction.resolution_class_id,
                disposition_class_id=request.action_instruction.disposition_class_id,
                recommendation_class_id=request.action_instruction.recommendation_class_id,
                policy_output_class_id=request.action_instruction.policy_output_class_id,
                portfolio_output_class_id=request.action_instruction.portfolio_output_class_id,
                action_instruction_class_id=request.action_instruction.action_instruction_class_id,
                execution_request_class_id=request.execution_request_class_id,
                route_name=request.action_instruction.route_name,
            )
        )
        execution_request_class = self._execution_request_registry.get_execution_request_class(
            request.execution_request_class_id
        )
        combined_context = self._combined_context(request, execution_request_class)
        required_execution_request_snapshot, missing_execution_request_fields = (
            self._snapshot_required_fields(
                execution_request_template.required_execution_request_fields,
                combined_context,
            )
        )
        required_audit_snapshot, missing_audit_fields = self._snapshot_required_fields(
            execution_request_template.required_audit_fields,
            combined_context,
        )
        all_missing_fields = tuple(
            dict.fromkeys(missing_execution_request_fields + missing_audit_fields)
        )
        optional_execution_request_snapshot = self._snapshot_optional_fields(
            execution_request_template.optional_execution_request_fields,
            combined_context,
        )
        prohibited_execution_fields_present = self._prohibited_execution_fields_present(
            execution_request_class.prohibited_execution_fields,
            request.execution_request_context,
        )
        execution_request_status = self._execution_request_status(
            action_instruction=request.action_instruction,
            missing_execution_request_fields=all_missing_fields,
            prohibited_execution_fields_present=prohibited_execution_fields_present,
            fallback_template_used=fallback_template_used,
        )
        execution_request_readiness = self._execution_request_readiness(
            template_execution_request_readiness=(
                execution_request_template.execution_request_readiness
            ),
            execution_request_status=execution_request_status,
            action_instruction=request.action_instruction,
            missing_execution_request_fields=all_missing_fields,
            prohibited_execution_fields_present=prohibited_execution_fields_present,
        )
        reason = self._execution_request_reason(
            action_instruction=request.action_instruction,
            execution_request_status=execution_request_status,
            execution_request_class_id=(
                execution_request_class.execution_request_class_id
            ),
            missing_execution_request_fields=all_missing_fields,
            prohibited_execution_fields_present=prohibited_execution_fields_present,
        )

        execution_request = ExecutionRequestRecord(
            execution_request_id=str(uuid4()),
            execution_request_status=execution_request_status,
            reason=reason,
            execution_request_class_id=(
                execution_request_class.execution_request_class_id
            ),
            execution_request_template_id=(
                execution_request_template.execution_request_template_id
            ),
            execution_request_readiness=execution_request_readiness,
            action_boundary_posture=execution_request_class.action_boundary_posture,
            action_instruction_id=request.action_instruction.action_instruction_id,
            action_instruction_status=request.action_instruction.action_instruction_status,
            action_instruction_class_id=(
                request.action_instruction.action_instruction_class_id
            ),
            action_instruction_template_id=(
                request.action_instruction.action_instruction_template_id
            ),
            instruction_status=request.action_instruction.instruction_status,
            bounded_action_posture=request.action_instruction.bounded_action_posture,
            execution_boundary_posture=request.action_instruction.execution_boundary_posture,
            action_instruction_promotion_safe_use=request.action_instruction.promotion_safe_use,
            portfolio_output_id=request.action_instruction.portfolio_output_id,
            portfolio_output_status=request.action_instruction.portfolio_output_status,
            portfolio_output_class_id=request.action_instruction.portfolio_output_class_id,
            portfolio_output_template_id=(
                request.action_instruction.portfolio_output_template_id
            ),
            policy_output_id=request.action_instruction.policy_output_id,
            policy_output_status=request.action_instruction.policy_output_status,
            policy_output_class_id=request.action_instruction.policy_output_class_id,
            policy_output_template_id=request.action_instruction.policy_output_template_id,
            recommendation_id=request.action_instruction.recommendation_id,
            recommendation_status=request.action_instruction.recommendation_status,
            recommendation_class_id=request.action_instruction.recommendation_class_id,
            recommendation_template_id=(
                request.action_instruction.recommendation_template_id
            ),
            review_resolution_id=request.action_instruction.review_resolution_id,
            review_resolution_status=(
                request.action_instruction.review_resolution_status
            ),
            resolution_class_id=request.action_instruction.resolution_class_id,
            disposition_class_id=request.action_instruction.disposition_class_id,
            packet_id=request.action_instruction.packet_id,
            packet_template_id=request.action_instruction.packet_template_id,
            packet_status=request.action_instruction.packet_status,
            semantic_scope=request.action_instruction.semantic_scope,
            case_type=request.action_instruction.case_type,
            case_key=request.action_instruction.case_key,
            state_model_name=request.action_instruction.state_model_name,
            episode_id=request.action_instruction.episode_id,
            transition_name=request.action_instruction.transition_name,
            transition_class=request.action_instruction.transition_class,
            source_stage=request.action_instruction.source_stage,
            target_stage=request.action_instruction.target_stage,
            reviewer_role=request.action_instruction.reviewer_role,
            reviewer_id=request.action_instruction.reviewer_id,
            recommender_role=request.action_instruction.recommender_role,
            recommender_id=request.action_instruction.recommender_id,
            policy_author_role=request.action_instruction.policy_author_role,
            policy_author_id=request.action_instruction.policy_author_id,
            portfolio_author_role=request.action_instruction.portfolio_author_role,
            portfolio_author_id=request.action_instruction.portfolio_author_id,
            instruction_author_role=request.action_instruction.instruction_author_role,
            instruction_author_id=request.action_instruction.instruction_author_id,
            execution_request_author_role=request.execution_request_author_role,
            execution_request_author_id=request.actor_id,
            authority_resolution_kind=request.action_instruction.authority_resolution_kind,
            authority_review_required=request.action_instruction.authority_review_required,
            router_rule_id=request.action_instruction.router_rule_id,
            routing_resolution_status=request.action_instruction.routing_resolution_status,
            routing_review_required=request.action_instruction.routing_review_required,
            review_mode=request.action_instruction.review_mode,
            required_execution_request_fields=(
                execution_request_template.required_execution_request_fields
            ),
            optional_execution_request_fields=(
                execution_request_template.optional_execution_request_fields
            ),
            required_audit_fields=execution_request_template.required_audit_fields,
            prohibited_execution_fields=(
                execution_request_class.prohibited_execution_fields
            ),
            required_execution_request_snapshot=required_execution_request_snapshot,
            optional_execution_request_snapshot=optional_execution_request_snapshot,
            required_audit_snapshot=required_audit_snapshot,
            lineage=self._lineage(
                request,
                execution_request_class,
                execution_request_template,
            ),
            generated_at=datetime.now(tz=UTC),
            route_name=request.action_instruction.route_name,
            threshold_id=request.action_instruction.threshold_id,
            trigger_class=request.action_instruction.trigger_class,
            playbook_reference=request.action_instruction.playbook_reference,
            upstream_commitment_reference=(
                request.action_instruction.upstream_commitment_reference
            ),
            instruction_authority_reference=(
                request.action_instruction.instruction_authority_reference
            ),
            executable_scope_reference=(
                self._optional_text(
                    request.execution_request_context.get("execution_scope_reference")
                )
                or request.action_instruction.executable_scope_reference
            ),
            blocking_condition_kind=request.action_instruction.blocking_condition_kind,
            blocking_condition_references=(
                request.action_instruction.blocking_condition_references
            ),
            invalidation_reference=request.action_instruction.invalidation_reference,
            unauthorized_instruction_reference=(
                request.action_instruction.unauthorized_instruction_reference
            ),
            reopen_reference=request.action_instruction.reopen_reference,
            missing_execution_request_fields=all_missing_fields,
            prohibited_execution_fields_present=prohibited_execution_fields_present,
        )
        self._execution_request_audit_adapter.record_execution_request(
            execution_request,
            request=request,
        )
        return execution_request

    def _combined_context(
        self,
        request: ExecutionRequestRequest,
        execution_request_class,
    ) -> dict[str, object]:
        context = dict(request.action_instruction.required_instruction_snapshot)
        context.update(request.action_instruction.optional_instruction_snapshot)
        context.update(request.action_instruction.required_audit_snapshot)
        context.update(dict(request.execution_request_context))
        context.update(
            {
                "execution_request_class_id": (
                    execution_request_class.execution_request_class_id
                ),
                "action_boundary_posture": execution_request_class.action_boundary_posture,
                "action_instruction_id": request.action_instruction.action_instruction_id,
                "action_instruction_status": (
                    request.action_instruction.action_instruction_status
                ),
                "action_instruction_class_id": (
                    request.action_instruction.action_instruction_class_id
                ),
                "action_instruction_template_id": (
                    request.action_instruction.action_instruction_template_id
                ),
                "portfolio_output_id": request.action_instruction.portfolio_output_id,
                "policy_output_id": request.action_instruction.policy_output_id,
                "recommendation_id": request.action_instruction.recommendation_id,
                "review_resolution_id": request.action_instruction.review_resolution_id,
                "packet_id": request.action_instruction.packet_id,
                "case_key": request.action_instruction.case_key,
                "route_name": request.action_instruction.route_name or "",
                "threshold_id": request.action_instruction.threshold_id or "",
                "trigger_class": request.action_instruction.trigger_class or "",
                "playbook_reference": request.action_instruction.playbook_reference or "",
                "execution_request_author_id": request.actor_id,
                "execution_request_author_role": request.execution_request_author_role,
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

    def _execution_request_status(
        self,
        *,
        action_instruction: ActionInstructionRecord,
        missing_execution_request_fields: tuple[str, ...],
        prohibited_execution_fields_present: tuple[str, ...],
        fallback_template_used: bool,
    ) -> str:
        if action_instruction.action_instruction_status == "blocked":
            return "blocked"
        if missing_execution_request_fields or prohibited_execution_fields_present:
            return "blocked"
        if fallback_template_used:
            return "fallback_template_applied"
        return "ready_for_downstream_use"

    def _execution_request_readiness(
        self,
        *,
        template_execution_request_readiness: str,
        execution_request_status: str,
        action_instruction: ActionInstructionRecord,
        missing_execution_request_fields: tuple[str, ...],
        prohibited_execution_fields_present: tuple[str, ...],
    ) -> str:
        if execution_request_status == "blocked":
            return "request_incomplete"
        if prohibited_execution_fields_present:
            return "request_incomplete"
        if action_instruction.instruction_status == "instruction_blocked_pending_authority":
            return "dispatch_blocked_pending_authority"
        if action_instruction.instruction_status == "instruction_blocked_pending_timing":
            return "dispatch_blocked_pending_timing"
        if action_instruction.instruction_status == "instruction_blocked_pending_prerequisite":
            return "dispatch_blocked_pending_prerequisite"
        if action_instruction.instruction_status in {
            "instruction_prohibited",
            "instruction_invalidated",
            "unauthorized_instruction_state",
        }:
            return "dispatch_prohibited"
        if action_instruction.blocking_condition_kind == "authority":
            return "dispatch_blocked_pending_authority"
        if action_instruction.blocking_condition_kind == "timing":
            return "dispatch_blocked_pending_timing"
        if action_instruction.blocking_condition_kind in {"prerequisite", "integrity", "scope"}:
            return "dispatch_blocked_pending_prerequisite"
        if missing_execution_request_fields:
            return "request_incomplete"
        return template_execution_request_readiness

    def _execution_request_reason(
        self,
        *,
        action_instruction: ActionInstructionRecord,
        execution_request_status: str,
        execution_request_class_id: str,
        missing_execution_request_fields: tuple[str, ...],
        prohibited_execution_fields_present: tuple[str, ...],
    ) -> str:
        if action_instruction.action_instruction_status == "blocked":
            return (
                "Execution request generation requires a legitimate action instruction record and cannot proceed "
                f"from action instruction status '{action_instruction.action_instruction_status}'."
            )
        if missing_execution_request_fields:
            return (
                "Execution request is missing required execution-request fields: "
                + ", ".join(missing_execution_request_fields)
                + "."
            )
        if prohibited_execution_fields_present:
            return (
                f"Execution request class '{execution_request_class_id}' cannot carry actual execution fields: "
                + ", ".join(prohibited_execution_fields_present)
                + "."
            )
        if execution_request_status == "fallback_template_applied":
            return (
                "A governed fallback execution-request template was applied because the bounded action instruction remains a contained hold rather than a dispatch-ready request."
            )
        return "Execution request is complete and ready for downstream governed use."

    def _lineage(
        self,
        request: ExecutionRequestRequest,
        execution_request_class,
        execution_request_template,
    ) -> dict[str, str]:
        lineage = {
            "action_instruction_id": request.action_instruction.action_instruction_id,
            "action_instruction_class_id": (
                request.action_instruction.action_instruction_class_id
            ),
            "action_instruction_class_version": request.action_instruction.lineage.get(
                "action_instruction_class_version",
                "unknown",
            ),
            "action_instruction_template_id": (
                request.action_instruction.action_instruction_template_id
            ),
            "action_instruction_template_version": request.action_instruction.lineage.get(
                "action_instruction_template_version",
                "unknown",
            ),
            "portfolio_output_id": request.action_instruction.portfolio_output_id,
            "policy_output_id": request.action_instruction.policy_output_id,
            "recommendation_id": request.action_instruction.recommendation_id,
            "review_resolution_id": request.action_instruction.review_resolution_id,
            "disposition_class_id": request.action_instruction.disposition_class_id,
            "packet_id": request.action_instruction.packet_id,
            "execution_request_class_id": (
                execution_request_class.execution_request_class_id
            ),
            "execution_request_class_version": execution_request_class.lineage.get(
                "version",
                "unknown",
            ),
            "execution_request_template_id": (
                execution_request_template.execution_request_template_id
            ),
            "execution_request_template_version": (
                execution_request_template.lineage.get("version", "unknown")
            ),
            "router_rule_id": request.action_instruction.router_rule_id,
            "authority_resolution_kind": request.action_instruction.authority_resolution_kind,
        }
        if request.action_instruction.route_name is not None:
            lineage["route_name"] = request.action_instruction.route_name
        if request.action_instruction.threshold_id is not None:
            lineage["threshold_id"] = request.action_instruction.threshold_id
        if request.action_instruction.trigger_class is not None:
            lineage["trigger_class"] = request.action_instruction.trigger_class
        return lineage

    def _optional_text(self, value: object) -> str | None:
        if value is None or value == "":
            return None
        return self._to_text(value)

    def _to_text(self, value: object) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)