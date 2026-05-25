from __future__ import annotations

"""Deterministic execution-outcome capture after execution-dispatch boundaries.

Canon ownership:
- Converts legitimate execution-dispatch-boundary records plus explicit
  observed-reality context into governed execution-outcome records.
- Owns realized-result legitimacy, expected-versus-realized comparison
  posture, feedback-capture readiness, explicit negative-outcome visibility,
  and outcome lineage.
- Does not perform execution, redefine execution-dispatch meaning, or absorb
  broker, venue, post-mortem, or policy-learning admission semantics.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Mapping, Sequence
from uuid import uuid4

from execution.execution_dispatch_boundary import ExecutionDispatchBoundaryRecord
from execution.execution_outcome_audit_adapter import ExecutionOutcomeAuditAdapter
from execution.execution_outcome_registry import ExecutionOutcomeRegistry


@dataclass(frozen=True)
class ExecutionOutcomeCaptureRequest:
    execution_dispatch: ExecutionDispatchBoundaryRecord
    execution_outcome_class_id: str
    execution_outcome_author_role: str
    execution_outcome_context: Mapping[str, object]
    correlation_id: str
    actor_id: str


@dataclass(frozen=True)
class ExecutionOutcomeRecord:
    execution_outcome_id: str
    execution_outcome_status: str
    reason: str
    execution_outcome_class_id: str
    execution_outcome_template_id: str
    realized_result_class: str
    feedback_capture_readiness: str
    expected_relation: str
    comparison_posture: str
    execution_dispatch_id: str
    execution_dispatch_status: str
    execution_dispatch_class_id: str
    execution_dispatch_template_id: str
    dispatch_boundary_posture: str
    execution_request_id: str
    execution_request_status: str
    execution_request_class_id: str
    semantic_scope: str
    case_type: str
    case_key: str
    state_model_name: str
    episode_id: str
    transition_name: str
    transition_class: str
    source_stage: str
    target_stage: str
    execution_dispatch_author_role: str
    execution_dispatch_author_id: str
    execution_outcome_author_role: str
    execution_outcome_author_id: str
    authority_resolution_kind: str
    authority_review_required: bool
    router_rule_id: str
    routing_resolution_status: str
    routing_review_required: bool
    review_mode: str
    required_execution_outcome_fields: tuple[str, ...]
    optional_execution_outcome_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    prohibited_observation_fields: tuple[str, ...]
    required_execution_outcome_snapshot: Mapping[str, str]
    optional_execution_outcome_snapshot: Mapping[str, str]
    required_audit_snapshot: Mapping[str, str]
    lineage: Mapping[str, str]
    generated_at: datetime
    observation_basis: str | None = None
    observation_horizon_reference: str | None = None
    comparison_basis: str | None = None
    feedback_maturity_posture: str | None = None
    feedback_reuse_boundary: str | None = None
    domain_reference: str | None = None
    decision_scope_reference: str | None = None
    reporting_scope_reference: str | None = None
    tenant_scope_reference: str | None = None
    expected_state_basis: str | None = None
    realized_state_basis: str | None = None
    recommendation_id: str | None = None
    action_instruction_id: str | None = None
    executed_action_reference: str | None = None
    non_execution_reference: str | None = None
    realized_outcome_reference: str | None = None
    route_name: str | None = None
    threshold_id: str | None = None
    trigger_class: str | None = None
    executable_scope_reference: str | None = None
    execution_condition_references: tuple[str, ...] = ()
    missing_execution_outcome_fields: tuple[str, ...] = ()
    prohibited_observation_fields_present: tuple[str, ...] = ()

    def to_contract_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "execution_outcome_id": self.execution_outcome_id,
            "execution_outcome_status": self.execution_outcome_status,
            "reason": self.reason,
            "execution_outcome_class_id": self.execution_outcome_class_id,
            "execution_outcome_template_id": self.execution_outcome_template_id,
            "realized_result_class": self.realized_result_class,
            "feedback_capture_readiness": self.feedback_capture_readiness,
            "expected_relation": self.expected_relation,
            "comparison_posture": self.comparison_posture,
            "execution_dispatch_id": self.execution_dispatch_id,
            "execution_dispatch_status": self.execution_dispatch_status,
            "execution_dispatch_class_id": self.execution_dispatch_class_id,
            "execution_dispatch_template_id": self.execution_dispatch_template_id,
            "dispatch_boundary_posture": self.dispatch_boundary_posture,
            "execution_request_id": self.execution_request_id,
            "execution_request_status": self.execution_request_status,
            "execution_request_class_id": self.execution_request_class_id,
            "semantic_scope": self.semantic_scope,
            "case_type": self.case_type,
            "case_key": self.case_key,
            "state_model_name": self.state_model_name,
            "episode_id": self.episode_id,
            "transition_name": self.transition_name,
            "transition_class": self.transition_class,
            "source_stage": self.source_stage,
            "target_stage": self.target_stage,
            "execution_dispatch_author_role": self.execution_dispatch_author_role,
            "execution_dispatch_author_id": self.execution_dispatch_author_id,
            "execution_outcome_author_role": self.execution_outcome_author_role,
            "execution_outcome_author_id": self.execution_outcome_author_id,
            "authority_resolution_kind": self.authority_resolution_kind,
            "authority_review_required": self.authority_review_required,
            "router_rule_id": self.router_rule_id,
            "routing_resolution_status": self.routing_resolution_status,
            "routing_review_required": self.routing_review_required,
            "review_mode": self.review_mode,
            "required_execution_outcome_fields": list(
                self.required_execution_outcome_fields
            ),
            "optional_execution_outcome_fields": list(
                self.optional_execution_outcome_fields
            ),
            "required_audit_fields": list(self.required_audit_fields),
            "prohibited_observation_fields": list(self.prohibited_observation_fields),
            "required_execution_outcome_snapshot": dict(
                self.required_execution_outcome_snapshot
            ),
            "optional_execution_outcome_snapshot": dict(
                self.optional_execution_outcome_snapshot
            ),
            "required_audit_snapshot": dict(self.required_audit_snapshot),
            "lineage": dict(self.lineage),
            "generated_at": self.generated_at.isoformat(),
        }
        if self.observation_basis is not None:
            payload["observation_basis"] = self.observation_basis
        if self.observation_horizon_reference is not None:
            payload["observation_horizon_reference"] = (
                self.observation_horizon_reference
            )
        if self.comparison_basis is not None:
            payload["comparison_basis"] = self.comparison_basis
        if self.feedback_maturity_posture is not None:
            payload["feedback_maturity_posture"] = self.feedback_maturity_posture
        if self.feedback_reuse_boundary is not None:
            payload["feedback_reuse_boundary"] = self.feedback_reuse_boundary
        if self.domain_reference is not None:
            payload["domain_reference"] = self.domain_reference
        if self.decision_scope_reference is not None:
            payload["decision_scope_reference"] = self.decision_scope_reference
        if self.reporting_scope_reference is not None:
            payload["reporting_scope_reference"] = self.reporting_scope_reference
        if self.tenant_scope_reference is not None:
            payload["tenant_scope_reference"] = self.tenant_scope_reference
        if self.expected_state_basis is not None:
            payload["expected_state_basis"] = self.expected_state_basis
        if self.realized_state_basis is not None:
            payload["realized_state_basis"] = self.realized_state_basis
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
        if self.route_name is not None:
            payload["route_name"] = self.route_name
        if self.threshold_id is not None:
            payload["threshold_id"] = self.threshold_id
        if self.trigger_class is not None:
            payload["trigger_class"] = self.trigger_class
        if self.executable_scope_reference is not None:
            payload["executable_scope_reference"] = self.executable_scope_reference
        if self.execution_condition_references:
            payload["execution_condition_references"] = list(
                self.execution_condition_references
            )
        if self.missing_execution_outcome_fields:
            payload["missing_execution_outcome_fields"] = list(
                self.missing_execution_outcome_fields
            )
        if self.prohibited_observation_fields_present:
            payload["prohibited_observation_fields_present"] = list(
                self.prohibited_observation_fields_present
            )
        return payload


class ExecutionOutcomeCaptureService:
    """Builds governed execution outcomes from legitimate dispatch boundaries."""

    def __init__(
        self,
        *,
        execution_outcome_registry: ExecutionOutcomeRegistry,
        execution_outcome_audit_adapter: ExecutionOutcomeAuditAdapter,
    ) -> None:
        self._execution_outcome_registry = execution_outcome_registry
        self._execution_outcome_audit_adapter = execution_outcome_audit_adapter

    def generate(
        self,
        request: ExecutionOutcomeCaptureRequest,
    ) -> ExecutionOutcomeRecord:
        execution_outcome_template, fallback_template_used = (
            self._execution_outcome_registry.resolve_template(
                semantic_scope=request.execution_dispatch.semantic_scope,
                execution_dispatch_class_id=(
                    request.execution_dispatch.execution_dispatch_class_id
                ),
                execution_outcome_class_id=request.execution_outcome_class_id,
                route_name=request.execution_dispatch.route_name,
            )
        )
        execution_outcome_class = (
            self._execution_outcome_registry.get_execution_outcome_class(
                request.execution_outcome_class_id
            )
        )
        combined_context = self._combined_context(request, execution_outcome_class)
        required_execution_outcome_snapshot, missing_execution_outcome_fields = (
            self._snapshot_required_fields(
                execution_outcome_template.required_execution_outcome_fields,
                combined_context,
            )
        )
        required_audit_snapshot, missing_audit_fields = self._snapshot_required_fields(
            execution_outcome_template.required_audit_fields,
            combined_context,
        )
        all_missing_fields = tuple(
            dict.fromkeys(missing_execution_outcome_fields + missing_audit_fields)
        )
        optional_execution_outcome_snapshot = self._snapshot_optional_fields(
            execution_outcome_template.optional_execution_outcome_fields,
            combined_context,
        )
        prohibited_observation_fields_present = self._prohibited_observation_fields_present(
            execution_outcome_class.prohibited_observation_fields,
            request.execution_outcome_context,
        )
        execution_outcome_status = self._execution_outcome_status(
            execution_dispatch=request.execution_dispatch,
            missing_execution_outcome_fields=all_missing_fields,
            prohibited_observation_fields_present=prohibited_observation_fields_present,
            fallback_template_used=fallback_template_used,
        )
        feedback_capture_readiness = self._feedback_capture_readiness(
            template_feedback_capture_readiness=(
                execution_outcome_template.feedback_capture_readiness
            ),
            execution_outcome_status=execution_outcome_status,
            missing_execution_outcome_fields=all_missing_fields,
            prohibited_observation_fields_present=prohibited_observation_fields_present,
        )
        executed_action_reference = self._optional_text(
            request.execution_outcome_context.get("executed_action_reference")
        )
        non_execution_reference = self._optional_text(
            request.execution_outcome_context.get("non_execution_reference")
        )
        realized_outcome_reference = self._optional_text(
            request.execution_outcome_context.get("realized_outcome_reference")
        )
        expected_state_basis = self._optional_text(
            combined_context.get("expected_state_basis")
        )
        realized_state_basis = (
            executed_action_reference or non_execution_reference or realized_outcome_reference
        )
        comparison_posture = self._comparison_posture(
            expected_state_basis=expected_state_basis,
            realized_state_basis=realized_state_basis,
            executed_action_reference=executed_action_reference,
            non_execution_reference=non_execution_reference,
        )
        expected_relation = self._expected_relation(comparison_posture)
        reason = self._execution_outcome_reason(
            execution_dispatch=request.execution_dispatch,
            execution_outcome_status=execution_outcome_status,
            execution_outcome_class_id=(
                execution_outcome_class.execution_outcome_class_id
            ),
            missing_execution_outcome_fields=all_missing_fields,
            prohibited_observation_fields_present=prohibited_observation_fields_present,
        )

        execution_outcome = ExecutionOutcomeRecord(
            execution_outcome_id=str(uuid4()),
            execution_outcome_status=execution_outcome_status,
            reason=reason,
            execution_outcome_class_id=(
                execution_outcome_class.execution_outcome_class_id
            ),
            execution_outcome_template_id=(
                execution_outcome_template.execution_outcome_template_id
            ),
            realized_result_class=execution_outcome_class.realized_result_class,
            feedback_capture_readiness=feedback_capture_readiness,
            expected_relation=expected_relation,
            comparison_posture=comparison_posture,
            execution_dispatch_id=request.execution_dispatch.execution_dispatch_id,
            execution_dispatch_status=(
                request.execution_dispatch.execution_dispatch_status
            ),
            execution_dispatch_class_id=(
                request.execution_dispatch.execution_dispatch_class_id
            ),
            execution_dispatch_template_id=(
                request.execution_dispatch.execution_dispatch_template_id
            ),
            dispatch_boundary_posture=(
                request.execution_dispatch.dispatch_boundary_posture
            ),
            execution_request_id=request.execution_dispatch.execution_request_id,
            execution_request_status=(
                request.execution_dispatch.execution_request_status
            ),
            execution_request_class_id=(
                request.execution_dispatch.execution_request_class_id
            ),
            semantic_scope=request.execution_dispatch.semantic_scope,
            case_type=request.execution_dispatch.case_type,
            case_key=request.execution_dispatch.case_key,
            state_model_name=request.execution_dispatch.state_model_name,
            episode_id=request.execution_dispatch.episode_id,
            transition_name=request.execution_dispatch.transition_name,
            transition_class=request.execution_dispatch.transition_class,
            source_stage=request.execution_dispatch.source_stage,
            target_stage=request.execution_dispatch.target_stage,
            execution_dispatch_author_role=(
                request.execution_dispatch.execution_dispatch_author_role
            ),
            execution_dispatch_author_id=(
                request.execution_dispatch.execution_dispatch_author_id
            ),
            execution_outcome_author_role=request.execution_outcome_author_role,
            execution_outcome_author_id=request.actor_id,
            authority_resolution_kind=(
                request.execution_dispatch.authority_resolution_kind
            ),
            authority_review_required=(
                request.execution_dispatch.authority_review_required
            ),
            router_rule_id=request.execution_dispatch.router_rule_id,
            routing_resolution_status=(
                request.execution_dispatch.routing_resolution_status
            ),
            routing_review_required=(
                request.execution_dispatch.routing_review_required
            ),
            review_mode=request.execution_dispatch.review_mode,
            required_execution_outcome_fields=(
                execution_outcome_template.required_execution_outcome_fields
            ),
            optional_execution_outcome_fields=(
                execution_outcome_template.optional_execution_outcome_fields
            ),
            required_audit_fields=execution_outcome_template.required_audit_fields,
            prohibited_observation_fields=(
                execution_outcome_class.prohibited_observation_fields
            ),
            required_execution_outcome_snapshot=required_execution_outcome_snapshot,
            optional_execution_outcome_snapshot=optional_execution_outcome_snapshot,
            required_audit_snapshot=required_audit_snapshot,
            lineage=self._lineage(
                request,
                execution_outcome_class,
                execution_outcome_template,
            ),
            generated_at=datetime.now(tz=UTC),
            observation_basis=self._optional_text(combined_context.get("observation_basis")),
            observation_horizon_reference=self._optional_text(
                combined_context.get("observation_horizon_reference")
            ),
            comparison_basis=self._optional_text(combined_context.get("comparison_basis")),
            feedback_maturity_posture=self._optional_text(
                combined_context.get("feedback_maturity_posture")
            ),
            feedback_reuse_boundary=self._optional_text(
                combined_context.get("feedback_reuse_boundary")
            ),
            domain_reference=self._optional_text(combined_context.get("domain_reference")),
            decision_scope_reference=self._optional_text(
                combined_context.get("decision_scope_reference")
            ),
            reporting_scope_reference=self._optional_text(
                request.execution_outcome_context.get("reporting_scope_reference")
            ),
            tenant_scope_reference=self._optional_text(
                combined_context.get("tenant_scope_reference")
            ),
            expected_state_basis=expected_state_basis,
            realized_state_basis=realized_state_basis,
            recommendation_id=self._optional_text(
                request.execution_dispatch.lineage.get("recommendation_id")
            ),
            action_instruction_id=self._optional_text(
                request.execution_dispatch.lineage.get("action_instruction_id")
            ),
            executed_action_reference=executed_action_reference,
            non_execution_reference=non_execution_reference,
            realized_outcome_reference=realized_outcome_reference,
            route_name=request.execution_dispatch.route_name,
            threshold_id=request.execution_dispatch.threshold_id,
            trigger_class=request.execution_dispatch.trigger_class,
            executable_scope_reference=(
                self._optional_text(combined_context.get("decision_scope_reference"))
                or request.execution_dispatch.executable_scope_reference
            ),
            execution_condition_references=self._sequence_as_tuple(
                request.execution_outcome_context.get("execution_condition_references")
            ),
            missing_execution_outcome_fields=all_missing_fields,
            prohibited_observation_fields_present=prohibited_observation_fields_present,
        )
        self._execution_outcome_audit_adapter.record_execution_outcome(
            execution_outcome,
            request=request,
        )
        return execution_outcome

    def _combined_context(
        self,
        request: ExecutionOutcomeCaptureRequest,
        execution_outcome_class,
    ) -> dict[str, object]:
        context = dict(request.execution_dispatch.required_execution_dispatch_snapshot)
        context.update(request.execution_dispatch.optional_execution_dispatch_snapshot)
        context.update(request.execution_dispatch.required_audit_snapshot)
        context.update(dict(request.execution_outcome_context))
        decision_scope_reference = self._optional_text(
            request.execution_outcome_context.get("decision_scope_reference")
        ) or request.execution_dispatch.executable_scope_reference
        expected_state_basis = (
            request.execution_dispatch.required_execution_dispatch_snapshot.get(
                "execution_target_reference"
            )
            or request.execution_dispatch.required_execution_dispatch_snapshot.get(
                "dispatch_reference"
            )
            or ""
        )
        context.update(
            {
                "execution_outcome_class_id": (
                    execution_outcome_class.execution_outcome_class_id
                ),
                "realized_result_class": execution_outcome_class.realized_result_class,
                "execution_dispatch_id": request.execution_dispatch.execution_dispatch_id,
                "execution_dispatch_status": (
                    request.execution_dispatch.execution_dispatch_status
                ),
                "execution_dispatch_class_id": (
                    request.execution_dispatch.execution_dispatch_class_id
                ),
                "execution_dispatch_template_id": (
                    request.execution_dispatch.execution_dispatch_template_id
                ),
                "execution_request_id": request.execution_dispatch.execution_request_id,
                "execution_request_status": (
                    request.execution_dispatch.execution_request_status
                ),
                "execution_request_class_id": (
                    request.execution_dispatch.execution_request_class_id
                ),
                "execution_dispatch_author_id": (
                    request.execution_dispatch.execution_dispatch_author_id
                ),
                "execution_dispatch_author_role": (
                    request.execution_dispatch.execution_dispatch_author_role
                ),
                "execution_outcome_author_id": request.actor_id,
                "execution_outcome_author_role": request.execution_outcome_author_role,
                "domain_reference": (
                    self._optional_text(
                        request.execution_outcome_context.get("domain_reference")
                    )
                    or request.execution_dispatch.semantic_scope
                ),
                "decision_scope_reference": decision_scope_reference or "",
                "expected_state_basis": expected_state_basis,
                "route_name": request.execution_dispatch.route_name or "",
                "threshold_id": request.execution_dispatch.threshold_id or "",
                "trigger_class": request.execution_dispatch.trigger_class or "",
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

    def _prohibited_observation_fields_present(
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

    def _execution_outcome_status(
        self,
        *,
        execution_dispatch: ExecutionDispatchBoundaryRecord,
        missing_execution_outcome_fields: tuple[str, ...],
        prohibited_observation_fields_present: tuple[str, ...],
        fallback_template_used: bool,
    ) -> str:
        if execution_dispatch.execution_dispatch_status == "blocked":
            return "blocked"
        if missing_execution_outcome_fields or prohibited_observation_fields_present:
            return "blocked"
        if (
            fallback_template_used
            or execution_dispatch.execution_dispatch_status == "fallback_template_applied"
        ):
            return "fallback_template_applied"
        return "ready_for_downstream_use"

    def _feedback_capture_readiness(
        self,
        *,
        template_feedback_capture_readiness: str,
        execution_outcome_status: str,
        missing_execution_outcome_fields: tuple[str, ...],
        prohibited_observation_fields_present: tuple[str, ...],
    ) -> str:
        if execution_outcome_status == "blocked":
            return "feedback_capture_incomplete"
        if prohibited_observation_fields_present or missing_execution_outcome_fields:
            return "feedback_capture_incomplete"
        return template_feedback_capture_readiness

    def _comparison_posture(
        self,
        *,
        expected_state_basis: str | None,
        realized_state_basis: str | None,
        executed_action_reference: str | None,
        non_execution_reference: str | None,
    ) -> str:
        if non_execution_reference is not None and executed_action_reference is None:
            return "comparison_pending_observation"
        if not expected_state_basis or not realized_state_basis:
            return "comparison_pending_observation"
        if expected_state_basis == realized_state_basis:
            return "comparison_ready_expected_matches_realized"
        return "comparison_ready_expected_differs_from_realized"

    def _expected_relation(self, comparison_posture: str) -> str:
        if comparison_posture == "comparison_ready_expected_matches_realized":
            return "realized_matches_expected_path"
        if comparison_posture == "comparison_ready_expected_differs_from_realized":
            return "realized_deviates_from_expected_path"
        return "expected_relation_pending_observation"

    def _execution_outcome_reason(
        self,
        *,
        execution_dispatch: ExecutionDispatchBoundaryRecord,
        execution_outcome_status: str,
        execution_outcome_class_id: str,
        missing_execution_outcome_fields: tuple[str, ...],
        prohibited_observation_fields_present: tuple[str, ...],
    ) -> str:
        if execution_dispatch.execution_dispatch_status == "blocked":
            return (
                "Execution outcome capture requires a legitimate execution dispatch boundary record and cannot proceed "
                f"from execution dispatch status '{execution_dispatch.execution_dispatch_status}'."
            )
        if missing_execution_outcome_fields:
            return (
                "Execution outcome capture is missing required outcome fields: "
                + ", ".join(missing_execution_outcome_fields)
                + "."
            )
        if prohibited_observation_fields_present:
            return (
                f"Execution outcome class '{execution_outcome_class_id}' cannot carry broker, venue, execution-control, post-mortem, or learning-admission fields: "
                + ", ".join(prohibited_observation_fields_present)
                + "."
            )
        if execution_outcome_status == "fallback_template_applied":
            return (
                "A governed fallback execution-outcome template was applied because the bounded execution dispatch remains a deferred or hold-only observation posture rather than a settled realized execution outcome."
            )
        return "Execution outcome capture is complete and ready for downstream governed use."

    def _lineage(
        self,
        request: ExecutionOutcomeCaptureRequest,
        execution_outcome_class,
        execution_outcome_template,
    ) -> dict[str, str]:
        lineage = dict(request.execution_dispatch.lineage)
        lineage.update(
            {
                "execution_dispatch_id": request.execution_dispatch.execution_dispatch_id,
                "execution_dispatch_class_id": (
                    request.execution_dispatch.execution_dispatch_class_id
                ),
                "execution_dispatch_class_version": (
                    request.execution_dispatch.lineage.get(
                        "execution_dispatch_class_version",
                        "unknown",
                    )
                ),
                "execution_dispatch_template_id": (
                    request.execution_dispatch.execution_dispatch_template_id
                ),
                "execution_dispatch_template_version": (
                    request.execution_dispatch.lineage.get(
                        "execution_dispatch_template_version",
                        "unknown",
                    )
                ),
                "execution_outcome_class_id": (
                    execution_outcome_class.execution_outcome_class_id
                ),
                "execution_outcome_class_version": (
                    execution_outcome_class.lineage.get("version", "unknown")
                ),
                "execution_outcome_template_id": (
                    execution_outcome_template.execution_outcome_template_id
                ),
                "execution_outcome_template_version": (
                    execution_outcome_template.lineage.get("version", "unknown")
                ),
            }
        )
        if request.execution_dispatch.route_name is not None:
            lineage["route_name"] = request.execution_dispatch.route_name
        if request.execution_dispatch.threshold_id is not None:
            lineage["threshold_id"] = request.execution_dispatch.threshold_id
        if request.execution_dispatch.trigger_class is not None:
            lineage["trigger_class"] = request.execution_dispatch.trigger_class
        return lineage

    def _optional_text(self, value: object) -> str | None:
        if value is None or value == "":
            return None
        return self._to_text(value)

    def _sequence_as_tuple(self, value: object) -> tuple[str, ...]:
        if value is None or value == "":
            return ()
        if isinstance(value, str):
            return (value,)
        if isinstance(value, Sequence):
            items = tuple(self._to_text(item) for item in value if item not in {None, ""})
            return items
        return (self._to_text(value),)

    def _to_text(self, value: object) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)