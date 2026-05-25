from __future__ import annotations

"""Deterministic execution-dispatch boundary generation after execution requests.

Canon ownership:
- Converts legitimate execution-request records plus explicit
  execution-dispatch context into governed dispatch-boundary records.
- Owns execution-dispatch legitimacy, completeness, lineage, readiness
  posture, and explicit separation between dispatch-boundary formation and
  actual execution.
- Does not execute requests, place broker or venue work, redefine
  execution-request meaning, or absorb execution outcome, reopen, or
  reinstatement semantics.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Mapping
from uuid import uuid4

from execution.execution_dispatch_audit_adapter import ExecutionDispatchAuditAdapter
from execution.execution_dispatch_registry import ExecutionDispatchRegistry
from execution.execution_request_service import ExecutionRequestRecord


@dataclass(frozen=True)
class ExecutionDispatchBoundaryRequest:
    execution_request: ExecutionRequestRecord
    execution_dispatch_class_id: str
    execution_dispatch_author_role: str
    execution_dispatch_context: Mapping[str, object]
    correlation_id: str
    actor_id: str


@dataclass(frozen=True)
class ExecutionDispatchBoundaryRecord:
    execution_dispatch_id: str
    execution_dispatch_status: str
    reason: str
    execution_dispatch_class_id: str
    execution_dispatch_template_id: str
    execution_dispatch_readiness: str
    dispatch_boundary_posture: str
    execution_request_id: str
    execution_request_status: str
    execution_request_class_id: str
    execution_request_template_id: str
    execution_request_readiness: str
    execution_request_action_boundary_posture: str
    semantic_scope: str
    case_type: str
    case_key: str
    state_model_name: str
    episode_id: str
    transition_name: str
    transition_class: str
    source_stage: str
    target_stage: str
    execution_request_author_role: str
    execution_request_author_id: str
    execution_dispatch_author_role: str
    execution_dispatch_author_id: str
    authority_resolution_kind: str
    authority_review_required: bool
    router_rule_id: str
    routing_resolution_status: str
    routing_review_required: bool
    review_mode: str
    required_execution_dispatch_fields: tuple[str, ...]
    optional_execution_dispatch_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    prohibited_dispatch_fields: tuple[str, ...]
    required_execution_dispatch_snapshot: Mapping[str, str]
    optional_execution_dispatch_snapshot: Mapping[str, str]
    required_audit_snapshot: Mapping[str, str]
    lineage: Mapping[str, str]
    generated_at: datetime
    route_name: str | None = None
    threshold_id: str | None = None
    trigger_class: str | None = None
    executable_scope_reference: str | None = None
    blocking_condition_kind: str | None = None
    blocking_condition_references: tuple[str, ...] = ()
    missing_execution_dispatch_fields: tuple[str, ...] = ()
    prohibited_dispatch_fields_present: tuple[str, ...] = ()

    def to_contract_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "execution_dispatch_id": self.execution_dispatch_id,
            "execution_dispatch_status": self.execution_dispatch_status,
            "reason": self.reason,
            "execution_dispatch_class_id": self.execution_dispatch_class_id,
            "execution_dispatch_template_id": self.execution_dispatch_template_id,
            "execution_dispatch_readiness": self.execution_dispatch_readiness,
            "dispatch_boundary_posture": self.dispatch_boundary_posture,
            "execution_request_id": self.execution_request_id,
            "execution_request_status": self.execution_request_status,
            "execution_request_class_id": self.execution_request_class_id,
            "execution_request_template_id": self.execution_request_template_id,
            "execution_request_readiness": self.execution_request_readiness,
            "execution_request_action_boundary_posture": (
                self.execution_request_action_boundary_posture
            ),
            "semantic_scope": self.semantic_scope,
            "case_type": self.case_type,
            "case_key": self.case_key,
            "state_model_name": self.state_model_name,
            "episode_id": self.episode_id,
            "transition_name": self.transition_name,
            "transition_class": self.transition_class,
            "source_stage": self.source_stage,
            "target_stage": self.target_stage,
            "execution_request_author_role": self.execution_request_author_role,
            "execution_request_author_id": self.execution_request_author_id,
            "execution_dispatch_author_role": self.execution_dispatch_author_role,
            "execution_dispatch_author_id": self.execution_dispatch_author_id,
            "authority_resolution_kind": self.authority_resolution_kind,
            "authority_review_required": self.authority_review_required,
            "router_rule_id": self.router_rule_id,
            "routing_resolution_status": self.routing_resolution_status,
            "routing_review_required": self.routing_review_required,
            "review_mode": self.review_mode,
            "required_execution_dispatch_fields": list(
                self.required_execution_dispatch_fields
            ),
            "optional_execution_dispatch_fields": list(
                self.optional_execution_dispatch_fields
            ),
            "required_audit_fields": list(self.required_audit_fields),
            "prohibited_dispatch_fields": list(self.prohibited_dispatch_fields),
            "required_execution_dispatch_snapshot": dict(
                self.required_execution_dispatch_snapshot
            ),
            "optional_execution_dispatch_snapshot": dict(
                self.optional_execution_dispatch_snapshot
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
        if self.executable_scope_reference is not None:
            payload["executable_scope_reference"] = self.executable_scope_reference
        if self.blocking_condition_kind is not None:
            payload["blocking_condition_kind"] = self.blocking_condition_kind
        if self.blocking_condition_references:
            payload["blocking_condition_references"] = list(
                self.blocking_condition_references
            )
        if self.missing_execution_dispatch_fields:
            payload["missing_execution_dispatch_fields"] = list(
                self.missing_execution_dispatch_fields
            )
        if self.prohibited_dispatch_fields_present:
            payload["prohibited_dispatch_fields_present"] = list(
                self.prohibited_dispatch_fields_present
            )
        return payload


class ExecutionDispatchBoundaryService:
    """Builds governed execution-dispatch boundaries from legitimate requests."""

    def __init__(
        self,
        *,
        execution_dispatch_registry: ExecutionDispatchRegistry,
        execution_dispatch_audit_adapter: ExecutionDispatchAuditAdapter,
    ) -> None:
        self._execution_dispatch_registry = execution_dispatch_registry
        self._execution_dispatch_audit_adapter = execution_dispatch_audit_adapter

    def generate(
        self,
        request: ExecutionDispatchBoundaryRequest,
    ) -> ExecutionDispatchBoundaryRecord:
        execution_dispatch_template, fallback_template_used = (
            self._execution_dispatch_registry.resolve_template(
                semantic_scope=request.execution_request.semantic_scope,
                execution_request_class_id=(
                    request.execution_request.execution_request_class_id
                ),
                execution_dispatch_class_id=request.execution_dispatch_class_id,
                route_name=request.execution_request.route_name,
            )
        )
        execution_dispatch_class = (
            self._execution_dispatch_registry.get_execution_dispatch_class(
                request.execution_dispatch_class_id
            )
        )
        combined_context = self._combined_context(request, execution_dispatch_class)
        required_execution_dispatch_snapshot, missing_execution_dispatch_fields = (
            self._snapshot_required_fields(
                execution_dispatch_template.required_execution_dispatch_fields,
                combined_context,
            )
        )
        required_audit_snapshot, missing_audit_fields = self._snapshot_required_fields(
            execution_dispatch_template.required_audit_fields,
            combined_context,
        )
        all_missing_fields = tuple(
            dict.fromkeys(missing_execution_dispatch_fields + missing_audit_fields)
        )
        optional_execution_dispatch_snapshot = self._snapshot_optional_fields(
            execution_dispatch_template.optional_execution_dispatch_fields,
            combined_context,
        )
        prohibited_dispatch_fields_present = self._prohibited_dispatch_fields_present(
            execution_dispatch_class.prohibited_dispatch_fields,
            request.execution_dispatch_context,
        )
        execution_dispatch_status = self._execution_dispatch_status(
            execution_request=request.execution_request,
            missing_execution_dispatch_fields=all_missing_fields,
            prohibited_dispatch_fields_present=prohibited_dispatch_fields_present,
            fallback_template_used=fallback_template_used,
        )
        execution_dispatch_readiness = self._execution_dispatch_readiness(
            template_execution_dispatch_readiness=(
                execution_dispatch_template.execution_dispatch_readiness
            ),
            execution_dispatch_status=execution_dispatch_status,
            execution_request=request.execution_request,
            missing_execution_dispatch_fields=all_missing_fields,
            prohibited_dispatch_fields_present=prohibited_dispatch_fields_present,
        )
        reason = self._execution_dispatch_reason(
            execution_request=request.execution_request,
            execution_dispatch_status=execution_dispatch_status,
            execution_dispatch_class_id=(
                execution_dispatch_class.execution_dispatch_class_id
            ),
            missing_execution_dispatch_fields=all_missing_fields,
            prohibited_dispatch_fields_present=prohibited_dispatch_fields_present,
        )

        execution_dispatch = ExecutionDispatchBoundaryRecord(
            execution_dispatch_id=str(uuid4()),
            execution_dispatch_status=execution_dispatch_status,
            reason=reason,
            execution_dispatch_class_id=(
                execution_dispatch_class.execution_dispatch_class_id
            ),
            execution_dispatch_template_id=(
                execution_dispatch_template.execution_dispatch_template_id
            ),
            execution_dispatch_readiness=execution_dispatch_readiness,
            dispatch_boundary_posture=(
                execution_dispatch_class.dispatch_boundary_posture
            ),
            execution_request_id=request.execution_request.execution_request_id,
            execution_request_status=request.execution_request.execution_request_status,
            execution_request_class_id=(
                request.execution_request.execution_request_class_id
            ),
            execution_request_template_id=(
                request.execution_request.execution_request_template_id
            ),
            execution_request_readiness=(
                request.execution_request.execution_request_readiness
            ),
            execution_request_action_boundary_posture=(
                request.execution_request.action_boundary_posture
            ),
            semantic_scope=request.execution_request.semantic_scope,
            case_type=request.execution_request.case_type,
            case_key=request.execution_request.case_key,
            state_model_name=request.execution_request.state_model_name,
            episode_id=request.execution_request.episode_id,
            transition_name=request.execution_request.transition_name,
            transition_class=request.execution_request.transition_class,
            source_stage=request.execution_request.source_stage,
            target_stage=request.execution_request.target_stage,
            execution_request_author_role=(
                request.execution_request.execution_request_author_role
            ),
            execution_request_author_id=(
                request.execution_request.execution_request_author_id
            ),
            execution_dispatch_author_role=request.execution_dispatch_author_role,
            execution_dispatch_author_id=request.actor_id,
            authority_resolution_kind=(
                request.execution_request.authority_resolution_kind
            ),
            authority_review_required=(
                request.execution_request.authority_review_required
            ),
            router_rule_id=request.execution_request.router_rule_id,
            routing_resolution_status=(
                request.execution_request.routing_resolution_status
            ),
            routing_review_required=(
                request.execution_request.routing_review_required
            ),
            review_mode=request.execution_request.review_mode,
            required_execution_dispatch_fields=(
                execution_dispatch_template.required_execution_dispatch_fields
            ),
            optional_execution_dispatch_fields=(
                execution_dispatch_template.optional_execution_dispatch_fields
            ),
            required_audit_fields=execution_dispatch_template.required_audit_fields,
            prohibited_dispatch_fields=(
                execution_dispatch_class.prohibited_dispatch_fields
            ),
            required_execution_dispatch_snapshot=required_execution_dispatch_snapshot,
            optional_execution_dispatch_snapshot=optional_execution_dispatch_snapshot,
            required_audit_snapshot=required_audit_snapshot,
            lineage=self._lineage(
                request,
                execution_dispatch_class,
                execution_dispatch_template,
            ),
            generated_at=datetime.now(tz=UTC),
            route_name=request.execution_request.route_name,
            threshold_id=request.execution_request.threshold_id,
            trigger_class=request.execution_request.trigger_class,
            executable_scope_reference=(
                self._optional_text(
                    request.execution_dispatch_context.get("execution_scope_reference")
                )
                or request.execution_request.executable_scope_reference
            ),
            blocking_condition_kind=request.execution_request.blocking_condition_kind,
            blocking_condition_references=(
                request.execution_request.blocking_condition_references
            ),
            missing_execution_dispatch_fields=all_missing_fields,
            prohibited_dispatch_fields_present=prohibited_dispatch_fields_present,
        )
        self._execution_dispatch_audit_adapter.record_execution_dispatch(
            execution_dispatch,
            request=request,
        )
        return execution_dispatch

    def _combined_context(
        self,
        request: ExecutionDispatchBoundaryRequest,
        execution_dispatch_class,
    ) -> dict[str, object]:
        context = dict(request.execution_request.required_execution_request_snapshot)
        context.update(request.execution_request.optional_execution_request_snapshot)
        context.update(request.execution_request.required_audit_snapshot)
        context.update(dict(request.execution_dispatch_context))
        context.update(
            {
                "execution_dispatch_class_id": (
                    execution_dispatch_class.execution_dispatch_class_id
                ),
                "dispatch_boundary_posture": (
                    execution_dispatch_class.dispatch_boundary_posture
                ),
                "execution_request_id": request.execution_request.execution_request_id,
                "execution_request_status": (
                    request.execution_request.execution_request_status
                ),
                "execution_request_class_id": (
                    request.execution_request.execution_request_class_id
                ),
                "execution_request_template_id": (
                    request.execution_request.execution_request_template_id
                ),
                "execution_request_author_id": (
                    request.execution_request.execution_request_author_id
                ),
                "execution_request_author_role": (
                    request.execution_request.execution_request_author_role
                ),
                "execution_dispatch_author_id": request.actor_id,
                "execution_dispatch_author_role": request.execution_dispatch_author_role,
                "case_key": request.execution_request.case_key,
                "route_name": request.execution_request.route_name or "",
                "threshold_id": request.execution_request.threshold_id or "",
                "trigger_class": request.execution_request.trigger_class or "",
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

    def _prohibited_dispatch_fields_present(
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

    def _execution_dispatch_status(
        self,
        *,
        execution_request: ExecutionRequestRecord,
        missing_execution_dispatch_fields: tuple[str, ...],
        prohibited_dispatch_fields_present: tuple[str, ...],
        fallback_template_used: bool,
    ) -> str:
        if execution_request.execution_request_status == "blocked":
            return "blocked"
        if missing_execution_dispatch_fields or prohibited_dispatch_fields_present:
            return "blocked"
        if (
            fallback_template_used
            or execution_request.execution_request_status == "fallback_template_applied"
        ):
            return "fallback_template_applied"
        return "ready_for_downstream_use"

    def _execution_dispatch_readiness(
        self,
        *,
        template_execution_dispatch_readiness: str,
        execution_dispatch_status: str,
        execution_request: ExecutionRequestRecord,
        missing_execution_dispatch_fields: tuple[str, ...],
        prohibited_dispatch_fields_present: tuple[str, ...],
    ) -> str:
        if execution_dispatch_status == "blocked":
            return "dispatch_boundary_incomplete"
        if prohibited_dispatch_fields_present:
            return "dispatch_boundary_incomplete"
        if (
            execution_request.execution_request_readiness
            == "dispatch_blocked_pending_authority"
        ):
            return "dispatch_boundary_blocked_pending_authority"
        if execution_request.execution_request_readiness == "dispatch_blocked_pending_timing":
            return "dispatch_boundary_blocked_pending_timing"
        if (
            execution_request.execution_request_readiness
            == "dispatch_blocked_pending_prerequisite"
        ):
            return "dispatch_boundary_blocked_pending_prerequisite"
        if execution_request.execution_request_readiness in {
            "dispatch_prohibited",
            "request_incomplete",
        }:
            return "dispatch_boundary_prohibited"
        if missing_execution_dispatch_fields:
            return "dispatch_boundary_incomplete"
        return template_execution_dispatch_readiness

    def _execution_dispatch_reason(
        self,
        *,
        execution_request: ExecutionRequestRecord,
        execution_dispatch_status: str,
        execution_dispatch_class_id: str,
        missing_execution_dispatch_fields: tuple[str, ...],
        prohibited_dispatch_fields_present: tuple[str, ...],
    ) -> str:
        if execution_request.execution_request_status == "blocked":
            return (
                "Execution dispatch boundary generation requires a legitimate execution request record and cannot proceed "
                f"from execution request status '{execution_request.execution_request_status}'."
            )
        if missing_execution_dispatch_fields:
            return (
                "Execution dispatch boundary is missing required dispatch fields: "
                + ", ".join(missing_execution_dispatch_fields)
                + "."
            )
        if prohibited_dispatch_fields_present:
            return (
                f"Execution dispatch class '{execution_dispatch_class_id}' cannot carry broker, venue, or actual execution fields: "
                + ", ".join(prohibited_dispatch_fields_present)
                + "."
            )
        if execution_dispatch_status == "fallback_template_applied":
            return (
                "A governed fallback execution-dispatch template was applied because the bounded execution request remains a contained hold rather than a dispatch-ready boundary."
            )
        return "Execution dispatch boundary is complete and ready for downstream governed use."

    def _lineage(
        self,
        request: ExecutionDispatchBoundaryRequest,
        execution_dispatch_class,
        execution_dispatch_template,
    ) -> dict[str, str]:
        lineage = dict(request.execution_request.lineage)
        lineage.update(
            {
                "execution_request_id": request.execution_request.execution_request_id,
                "execution_request_class_id": (
                    request.execution_request.execution_request_class_id
                ),
                "execution_request_class_version": (
                    request.execution_request.lineage.get(
                        "execution_request_class_version",
                        "unknown",
                    )
                ),
                "execution_request_template_id": (
                    request.execution_request.execution_request_template_id
                ),
                "execution_request_template_version": (
                    request.execution_request.lineage.get(
                        "execution_request_template_version",
                        "unknown",
                    )
                ),
                "execution_dispatch_class_id": (
                    execution_dispatch_class.execution_dispatch_class_id
                ),
                "execution_dispatch_class_version": (
                    execution_dispatch_class.lineage.get("version", "unknown")
                ),
                "execution_dispatch_template_id": (
                    execution_dispatch_template.execution_dispatch_template_id
                ),
                "execution_dispatch_template_version": (
                    execution_dispatch_template.lineage.get("version", "unknown")
                ),
            }
        )
        if request.execution_request.route_name is not None:
            lineage["route_name"] = request.execution_request.route_name
        if request.execution_request.threshold_id is not None:
            lineage["threshold_id"] = request.execution_request.threshold_id
        if request.execution_request.trigger_class is not None:
            lineage["trigger_class"] = request.execution_request.trigger_class
        return lineage

    def _optional_text(self, value: object) -> str | None:
        if value is None or value == "":
            return None
        return self._to_text(value)

    def _to_text(self, value: object) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)
