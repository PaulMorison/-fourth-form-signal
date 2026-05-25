from __future__ import annotations

"""Governed runtime release rollback-trigger guard.

Canon ownership:
- Consumes a governed rollout-scope record and explicit rollback-trigger
  context to decide whether named rollback triggers and rollback-plan
  completeness are explicit enough, explicit only conditionally, deferred,
  blocked for missing context, rejected for rollback-trigger use, or blocked
  for prohibited overlap.
- Does not own post-release watch execution, rollback execution, monitoring,
  reopen handling, orchestration meaning, or lifecycle state meaning.
"""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Mapping
from uuid import uuid4

from runtime.release.release_registry import ReleaseRegistry
from runtime.release.rollback_trigger_audit_adapter import RollbackTriggerAuditAdapter
from runtime.release.rollout_scope_controller import RolloutScopeRecord

_REQUIRED_COLLECTION_FIELDS = {
    "required_rollback_trigger_fields",
    "optional_rollback_trigger_fields",
    "required_audit_fields",
    "prohibited_rollback_trigger_fields",
    "required_rollback_trigger_snapshot",
    "optional_rollback_trigger_snapshot",
    "required_audit_snapshot",
    "lineage",
    "outstanding_rollback_trigger_prerequisites",
}


def _serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_serialize_value(item) for item in value]
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize_value(item) for key, item in value.items()}
    return value


def _serialize_payload(data: Mapping[str, Any]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in data.items():
        if value is None:
            continue
        if key not in _REQUIRED_COLLECTION_FIELDS and value in ((), [], {}):
            continue
        payload[key] = _serialize_value(value)
    return payload


@dataclass(frozen=True)
class RollbackTriggerGuardRequest:
    rollout_scope: RolloutScopeRecord
    rollback_trigger_class_id: str
    rollback_trigger_author_role: str
    rollback_trigger_context: Mapping[str, object]
    correlation_id: str
    actor_id: str


@dataclass(frozen=True)
class RollbackTriggerRecord:
    rollback_trigger_id: str
    rollback_trigger_status: str
    reason: str
    rollback_trigger_class_id: str
    rollback_trigger_template_id: str
    rollback_trigger_outcome: str
    rollback_trigger_reference: str
    rollback_plan_reference: str
    promotion_candidate_reference: str
    promotion_threshold_reference: str
    production_entitlement_boundary: str
    rollback_posture_reference: str
    release_watch_window: str
    release_confirmation_threshold_reference: str
    promotion_scope_reference: str
    promotion_boundary_summary: str
    rollout_scope_boundary_reference: str
    exposure_boundary_reference: str
    rollout_boundary_summary: str
    rollout_scope_id: str
    rollout_scope_status: str
    rollout_scope_class_id: str
    rollout_scope_template_id: str
    rollout_scope_outcome: str
    semantic_scope: str
    case_type: str
    case_key: str
    state_model_name: str
    episode_id: str
    transition_name: str
    transition_class: str
    domain_reference: str
    decision_scope_reference: str
    tenant_scope_reference: str
    learning_scope_reference: str
    rollback_trigger_author_role: str
    rollback_trigger_author_id: str
    required_rollback_trigger_fields: tuple[str, ...]
    optional_rollback_trigger_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    prohibited_rollback_trigger_fields: tuple[str, ...]
    required_rollback_trigger_snapshot: Mapping[str, str]
    optional_rollback_trigger_snapshot: Mapping[str, str]
    required_audit_snapshot: Mapping[str, str]
    lineage: Mapping[str, str]
    generated_at: datetime
    reporting_scope_reference: str | None = None
    restriction_summary: str | None = None
    promotion_scope_restriction_reference: str | None = None
    follow_up_review_reference: str | None = None
    rollback_trigger_prerequisite_reference: str | None = None
    outstanding_rollback_trigger_prerequisites: tuple[str, ...] = ()
    missing_rollback_trigger_fields: tuple[str, ...] = ()
    prohibited_rollback_trigger_fields_present: tuple[str, ...] = ()

    def to_contract_dict(self) -> dict[str, object]:
        return _serialize_payload(asdict(self))

    def to_transport_context(self) -> dict[str, object]:
        context: dict[str, object] = {
            "rollback_trigger_outcome": self.rollback_trigger_outcome,
            "rollback_trigger_reference": self.rollback_trigger_reference,
            "rollback_plan_reference": self.rollback_plan_reference,
            "release_watch_window": self.release_watch_window,
            "release_confirmation_threshold_reference": (
                self.release_confirmation_threshold_reference
            ),
        }
        if self.restriction_summary is not None:
            context["restriction_summary"] = self.restriction_summary
        if self.promotion_scope_restriction_reference is not None:
            context["promotion_scope_restriction_reference"] = (
                self.promotion_scope_restriction_reference
            )
        if self.follow_up_review_reference is not None:
            context["follow_up_review_reference"] = self.follow_up_review_reference
        if self.rollback_trigger_prerequisite_reference is not None:
            context["rollback_trigger_prerequisite_reference"] = (
                self.rollback_trigger_prerequisite_reference
            )
        if self.outstanding_rollback_trigger_prerequisites:
            context["outstanding_rollback_trigger_prerequisites"] = list(
                self.outstanding_rollback_trigger_prerequisites
            )
        return context


class RollbackTriggerGuard:
    """Builds rollback-trigger records from rollout-scope records."""

    def __init__(
        self,
        *,
        release_registry: ReleaseRegistry,
        rollback_trigger_audit_adapter: RollbackTriggerAuditAdapter,
    ) -> None:
        self._release_registry = release_registry
        self._rollback_trigger_audit_adapter = rollback_trigger_audit_adapter

    def generate(self, request: RollbackTriggerGuardRequest) -> RollbackTriggerRecord:
        template, fallback_template_used = (
            self._release_registry.resolve_rollback_trigger_template(
                semantic_scope=request.rollout_scope.semantic_scope,
                rollout_scope_class_id=request.rollout_scope.rollout_scope_class_id,
                rollback_trigger_class_id=request.rollback_trigger_class_id,
                route_name=request.rollout_scope.lineage.get("route_name"),
            )
        )
        class_definition = self._release_registry.get_rollback_trigger_class(
            request.rollback_trigger_class_id
        )
        combined_context = self._combined_context(request, class_definition)
        required_rollback_trigger_snapshot, missing_rollback_trigger_fields = (
            self._snapshot_required_fields(
                template.required_rollback_trigger_fields,
                combined_context,
            )
        )
        required_audit_snapshot, missing_audit_fields = self._snapshot_required_fields(
            template.required_audit_fields,
            combined_context,
        )
        all_missing_fields = tuple(
            dict.fromkeys(missing_rollback_trigger_fields + missing_audit_fields)
        )
        optional_rollback_trigger_snapshot = self._snapshot_optional_fields(
            template.optional_rollback_trigger_fields,
            combined_context,
        )
        prohibited_rollback_trigger_fields_present = (
            self._prohibited_rollback_trigger_fields_present(
                class_definition.prohibited_rollback_trigger_fields,
                request.rollback_trigger_context,
            )
        )
        rollback_trigger_status = self._rollback_trigger_status(
            rollout_scope=request.rollout_scope,
            class_definition=class_definition,
            combined_context=combined_context,
            missing_rollback_trigger_fields=all_missing_fields,
            prohibited_rollback_trigger_fields_present=(
                prohibited_rollback_trigger_fields_present
            ),
            fallback_template_used=fallback_template_used,
        )
        rollback_trigger_outcome = self._rollback_trigger_outcome(
            template=template,
            rollback_trigger_status=rollback_trigger_status,
        )
        reason = self._reason(
            rollout_scope=request.rollout_scope,
            rollback_trigger_status=rollback_trigger_status,
            rollback_trigger_class_id=class_definition.rollback_trigger_class_id,
            missing_rollback_trigger_fields=all_missing_fields,
            prohibited_rollback_trigger_fields_present=(
                prohibited_rollback_trigger_fields_present
            ),
            class_definition=class_definition,
            combined_context=combined_context,
            rollback_trigger_outcome=rollback_trigger_outcome,
        )
        lineage = self._lineage(request, class_definition, template)

        upstream = request.rollout_scope
        record = RollbackTriggerRecord(
            rollback_trigger_id=str(uuid4()),
            rollback_trigger_status=rollback_trigger_status,
            reason=reason,
            rollback_trigger_class_id=class_definition.rollback_trigger_class_id,
            rollback_trigger_template_id=template.rollback_trigger_template_id,
            rollback_trigger_outcome=rollback_trigger_outcome,
            rollback_trigger_reference=self._field_value_or_placeholder(
                field_name="rollback_trigger_reference",
                snapshot=required_rollback_trigger_snapshot,
                context=combined_context,
            ),
            rollback_plan_reference=self._field_value_or_placeholder(
                field_name="rollback_plan_reference",
                snapshot=required_rollback_trigger_snapshot,
                context=combined_context,
            ),
            promotion_candidate_reference=self._field_value_or_placeholder(
                field_name="promotion_candidate_reference",
                snapshot=required_rollback_trigger_snapshot,
                context=combined_context,
            ),
            promotion_threshold_reference=self._field_value_or_placeholder(
                field_name="promotion_threshold_reference",
                snapshot=required_rollback_trigger_snapshot,
                context=combined_context,
            ),
            production_entitlement_boundary=self._field_value_or_placeholder(
                field_name="production_entitlement_boundary",
                snapshot=required_rollback_trigger_snapshot,
                context=combined_context,
            ),
            rollback_posture_reference=self._field_value_or_placeholder(
                field_name="rollback_posture_reference",
                snapshot=required_rollback_trigger_snapshot,
                context=combined_context,
            ),
            release_watch_window=self._field_value_or_placeholder(
                field_name="release_watch_window",
                snapshot=required_rollback_trigger_snapshot,
                context=combined_context,
            ),
            release_confirmation_threshold_reference=(
                self._field_value_or_placeholder(
                    field_name="release_confirmation_threshold_reference",
                    snapshot=required_rollback_trigger_snapshot,
                    context=combined_context,
                )
            ),
            promotion_scope_reference=self._field_value_or_placeholder(
                field_name="promotion_scope_reference",
                snapshot=required_rollback_trigger_snapshot,
                context=combined_context,
            ),
            promotion_boundary_summary=self._field_value_or_placeholder(
                field_name="promotion_boundary_summary",
                snapshot=required_rollback_trigger_snapshot,
                context=combined_context,
            ),
            rollout_scope_boundary_reference=self._field_value_or_placeholder(
                field_name="rollout_scope_boundary_reference",
                snapshot=required_rollback_trigger_snapshot,
                context=combined_context,
            ),
            exposure_boundary_reference=self._field_value_or_placeholder(
                field_name="exposure_boundary_reference",
                snapshot=required_rollback_trigger_snapshot,
                context=combined_context,
            ),
            rollout_boundary_summary=self._field_value_or_placeholder(
                field_name="rollout_boundary_summary",
                snapshot=required_rollback_trigger_snapshot,
                context=combined_context,
            ),
            rollout_scope_id=upstream.rollout_scope_id,
            rollout_scope_status=upstream.rollout_scope_status,
            rollout_scope_class_id=upstream.rollout_scope_class_id,
            rollout_scope_template_id=upstream.rollout_scope_template_id,
            rollout_scope_outcome=upstream.rollout_scope_outcome,
            semantic_scope=upstream.semantic_scope,
            case_type=upstream.case_type,
            case_key=upstream.case_key,
            state_model_name=upstream.state_model_name,
            episode_id=upstream.episode_id,
            transition_name=upstream.transition_name,
            transition_class=upstream.transition_class,
            domain_reference=combined_context["domain_reference"],
            decision_scope_reference=combined_context["decision_scope_reference"],
            tenant_scope_reference=combined_context["tenant_scope_reference"],
            learning_scope_reference=combined_context["learning_scope_reference"],
            rollback_trigger_author_role=request.rollback_trigger_author_role,
            rollback_trigger_author_id=request.actor_id,
            required_rollback_trigger_fields=template.required_rollback_trigger_fields,
            optional_rollback_trigger_fields=template.optional_rollback_trigger_fields,
            required_audit_fields=template.required_audit_fields,
            prohibited_rollback_trigger_fields=(
                class_definition.prohibited_rollback_trigger_fields
            ),
            required_rollback_trigger_snapshot=required_rollback_trigger_snapshot,
            optional_rollback_trigger_snapshot=optional_rollback_trigger_snapshot,
            required_audit_snapshot=required_audit_snapshot,
            lineage=lineage,
            generated_at=datetime.now(tz=UTC),
            reporting_scope_reference=combined_context.get(
                "reporting_scope_reference"
            ),
            restriction_summary=combined_context.get("restriction_summary"),
            promotion_scope_restriction_reference=combined_context.get(
                "promotion_scope_restriction_reference"
            ),
            follow_up_review_reference=combined_context.get(
                "follow_up_review_reference"
            ),
            rollback_trigger_prerequisite_reference=combined_context.get(
                "rollback_trigger_prerequisite_reference"
            ),
            outstanding_rollback_trigger_prerequisites=(
                combined_context["outstanding_rollback_trigger_prerequisites"]
            ),
            missing_rollback_trigger_fields=all_missing_fields,
            prohibited_rollback_trigger_fields_present=(
                prohibited_rollback_trigger_fields_present
            ),
        )
        self._rollback_trigger_audit_adapter.record_rollback_trigger(
            record,
            request=request,
        )
        return record

    def _combined_context(
        self,
        request: RollbackTriggerGuardRequest,
        class_definition,
    ) -> dict[str, object]:
        context = dict(request.rollout_scope.required_rollout_scope_snapshot)
        context.update(request.rollout_scope.optional_rollout_scope_snapshot)
        context.update(request.rollout_scope.required_audit_snapshot)
        context.update(dict(request.rollback_trigger_context))
        upstream = request.rollout_scope
        context.update(
            {
                "rollback_trigger_class_id": class_definition.rollback_trigger_class_id,
                "rollback_trigger_author_id": request.actor_id,
                "rollback_trigger_author_role": request.rollback_trigger_author_role,
                "rollout_scope_id": upstream.rollout_scope_id,
                "rollout_scope_status": upstream.rollout_scope_status,
                "rollout_scope_class_id": upstream.rollout_scope_class_id,
                "rollout_scope_template_id": upstream.rollout_scope_template_id,
                "rollout_scope_outcome": upstream.rollout_scope_outcome,
                "domain_reference": self._optional_text(
                    context.get("domain_reference")
                )
                or upstream.domain_reference
                or upstream.semantic_scope,
                "decision_scope_reference": self._optional_text(
                    context.get("decision_scope_reference")
                )
                or upstream.decision_scope_reference
                or "",
                "reporting_scope_reference": self._optional_text(
                    context.get("reporting_scope_reference")
                )
                or upstream.reporting_scope_reference
                or "",
                "tenant_scope_reference": self._optional_text(
                    context.get("tenant_scope_reference")
                )
                or upstream.tenant_scope_reference
                or "",
                "learning_scope_reference": self._optional_text(
                    context.get("learning_scope_reference")
                )
                or upstream.learning_scope_reference
                or upstream.semantic_scope,
                "promotion_candidate_reference": self._optional_text(
                    context.get("promotion_candidate_reference")
                )
                or upstream.promotion_candidate_reference,
                "promotion_threshold_reference": self._optional_text(
                    context.get("promotion_threshold_reference")
                )
                or upstream.promotion_threshold_reference,
                "production_entitlement_boundary": self._optional_text(
                    context.get("production_entitlement_boundary")
                )
                or upstream.production_entitlement_boundary,
                "rollback_posture_reference": self._optional_text(
                    context.get("rollback_posture_reference")
                )
                or upstream.rollback_posture_reference,
                "release_watch_window": self._optional_text(
                    context.get("release_watch_window")
                )
                or upstream.release_watch_window,
                "release_confirmation_threshold_reference": self._optional_text(
                    context.get("release_confirmation_threshold_reference")
                )
                or upstream.release_confirmation_threshold_reference,
                "promotion_scope_reference": self._optional_text(
                    context.get("promotion_scope_reference")
                )
                or upstream.promotion_scope_reference,
                "promotion_boundary_summary": self._optional_text(
                    context.get("promotion_boundary_summary")
                )
                or upstream.promotion_boundary_summary,
                "rollout_scope_boundary_reference": self._optional_text(
                    context.get("rollout_scope_boundary_reference")
                )
                or upstream.rollout_scope_boundary_reference,
                "exposure_boundary_reference": self._optional_text(
                    context.get("exposure_boundary_reference")
                )
                or upstream.exposure_boundary_reference,
                "rollout_boundary_summary": self._optional_text(
                    context.get("rollout_boundary_summary")
                )
                or upstream.rollout_boundary_summary,
                "restriction_summary": self._optional_text(
                    context.get("restriction_summary")
                )
                or upstream.restriction_summary,
                "promotion_scope_restriction_reference": self._optional_text(
                    context.get("promotion_scope_restriction_reference")
                )
                or upstream.promotion_scope_restriction_reference,
                "follow_up_review_reference": self._optional_text(
                    context.get("follow_up_review_reference")
                )
                or upstream.follow_up_review_reference,
                "rollback_trigger_reference": self._optional_text(
                    context.get("rollback_trigger_reference")
                ),
                "rollback_plan_reference": self._optional_text(
                    context.get("rollback_plan_reference")
                ),
                "rollback_trigger_prerequisite_reference": self._optional_text(
                    context.get("rollback_trigger_prerequisite_reference")
                ),
                "outstanding_rollback_trigger_prerequisites": (
                    self._sequence_as_tuple(
                        context.get("outstanding_rollback_trigger_prerequisites")
                    )
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
            if self._is_missing_value(value):
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
            if self._is_missing_value(value):
                continue
            snapshot[field_name] = self._to_text(value)
        return snapshot

    def _prohibited_rollback_trigger_fields_present(
        self,
        prohibited_fields: tuple[str, ...],
        context: Mapping[str, object],
    ) -> tuple[str, ...]:
        return tuple(
            field_name
            for field_name in prohibited_fields
            if not self._is_missing_value(context.get(field_name))
        )

    def _rollback_trigger_status(
        self,
        *,
        rollout_scope: RolloutScopeRecord,
        class_definition,
        combined_context: Mapping[str, object],
        missing_rollback_trigger_fields: tuple[str, ...],
        prohibited_rollback_trigger_fields_present: tuple[str, ...],
        fallback_template_used: bool,
    ) -> str:
        if prohibited_rollback_trigger_fields_present:
            return "prohibited_overlap_blocked"
        if missing_rollback_trigger_fields:
            return "blocked_missing_context"
        if (
            rollout_scope.rollout_scope_status
            not in class_definition.allowed_rollout_scope_statuses
        ):
            return "rejected_for_rollback_trigger_use"
        if (
            rollout_scope.rollout_scope_outcome
            not in class_definition.allowed_rollout_scope_outcomes
        ):
            return "rejected_for_rollback_trigger_use"
        if self._has_rollback_trigger_restrictions(combined_context) and not (
            class_definition.allow_rollback_trigger_restrictions
        ):
            return "rejected_for_rollback_trigger_use"
        if self._has_rollback_trigger_prerequisite_deferral(combined_context) and not (
            class_definition.allow_rollback_trigger_prerequisite_deferral
        ):
            return "rejected_for_rollback_trigger_use"
        return (
            "fallback_template_applied"
            if fallback_template_used
            else "rollback_trigger_named"
        )

    def _rollback_trigger_outcome(
        self,
        *,
        template,
        rollback_trigger_status: str,
    ) -> str:
        if rollback_trigger_status in {
            "blocked_missing_context",
            "rejected_for_rollback_trigger_use",
            "prohibited_overlap_blocked",
        }:
            return rollback_trigger_status
        return template.rollback_trigger_outcome

    def _reason(
        self,
        *,
        rollout_scope: RolloutScopeRecord,
        rollback_trigger_status: str,
        rollback_trigger_class_id: str,
        missing_rollback_trigger_fields: tuple[str, ...],
        prohibited_rollback_trigger_fields_present: tuple[str, ...],
        class_definition,
        combined_context: Mapping[str, object],
        rollback_trigger_outcome: str,
    ) -> str:
        if rollback_trigger_status == "blocked_missing_context":
            return (
                "Rollback-trigger guard is blocked because governed rollback-trigger "
                "context is missing required fields: "
                + ", ".join(missing_rollback_trigger_fields)
                + "."
            )
        if rollback_trigger_status == "prohibited_overlap_blocked":
            return (
                "Rollback-trigger guard is blocked because context overlaps "
                "post-release watch execution, rollback execution, monitoring, "
                "reopen, or orchestration fields: "
                + ", ".join(prohibited_rollback_trigger_fields_present)
                + "."
            )
        if rollback_trigger_status == "rejected_for_rollback_trigger_use":
            if (
                rollout_scope.rollout_scope_status
                not in class_definition.allowed_rollout_scope_statuses
            ):
                return (
                    "Rollback-trigger guard rejects rollout-scope status '"
                    f"{rollout_scope.rollout_scope_status}' for class '"
                    f"{rollback_trigger_class_id}'."
                )
            if (
                rollout_scope.rollout_scope_outcome
                not in class_definition.allowed_rollout_scope_outcomes
            ):
                return (
                    "Rollback-trigger guard rejects rollout-scope outcome '"
                    f"{rollout_scope.rollout_scope_outcome}' for class '"
                    f"{rollback_trigger_class_id}'."
                )
            if self._has_rollback_trigger_restrictions(combined_context) and not (
                class_definition.allow_rollback_trigger_restrictions
            ):
                return (
                    "Rollback-trigger guard rejects restricted production exposure "
                    f"for class '{rollback_trigger_class_id}'."
                )
            if self._has_rollback_trigger_prerequisite_deferral(combined_context) and not (
                class_definition.allow_rollback_trigger_prerequisite_deferral
            ):
                return (
                    "Rollback-trigger guard rejects deferred rollback-trigger "
                    f"evidence for class '{rollback_trigger_class_id}'."
                )
        if rollback_trigger_outcome == "ready_for_release_watch_discipline":
            return (
                "Governed rollback triggers are explicit and the promoted release "
                "is ready for downstream release-watch discipline."
            )
        if rollback_trigger_outcome == "conditionally_ready_for_release_watch_discipline":
            return (
                "Governed rollback triggers are explicit only conditionally and "
                "must preserve narrowed production exposure before downstream "
                "release-watch discipline."
            )
        return (
            "Governed rollback triggers are deferred until explicit rollback-trigger "
            "evidence and rollback-plan completeness are completed."
        )

    def _lineage(
        self,
        request: RollbackTriggerGuardRequest,
        class_definition,
        template,
    ) -> dict[str, str]:
        lineage = dict(request.rollout_scope.lineage)
        lineage.update(
            {
                "rollout_scope_id": request.rollout_scope.rollout_scope_id,
                "rollback_trigger_class_id": class_definition.rollback_trigger_class_id,
                "rollback_trigger_template_id": (
                    template.rollback_trigger_template_id
                ),
            }
        )
        return lineage

    def _has_rollback_trigger_restrictions(
        self,
        context: Mapping[str, object],
    ) -> bool:
        return any(
            not self._is_missing_value(context.get(field_name))
            for field_name in (
                "restriction_summary",
                "promotion_scope_restriction_reference",
            )
        )

    def _has_rollback_trigger_prerequisite_deferral(
        self,
        context: Mapping[str, object],
    ) -> bool:
        return any(
            not self._is_missing_value(context.get(field_name))
            for field_name in (
                "rollback_trigger_prerequisite_reference",
                "outstanding_rollback_trigger_prerequisites",
            )
        )

    def _field_value_or_placeholder(
        self,
        *,
        field_name: str,
        snapshot: Mapping[str, str],
        context: Mapping[str, object],
    ) -> str:
        if field_name in snapshot:
            return snapshot[field_name]
        return self._to_text(context.get(field_name))

    def _sequence_as_tuple(self, value: object) -> tuple[str, ...]:
        if value in (None, "", (), []):
            return ()
        if isinstance(value, (list, tuple)):
            return tuple(
                self._to_text(item)
                for item in value
                if not self._is_missing_value(item)
            )
        return (self._to_text(value),)

    def _optional_text(self, value: object) -> str | None:
        if self._is_missing_value(value):
            return None
        return self._to_text(value)

    def _to_text(self, value: object) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)

    def _is_missing_value(self, value: object) -> bool:
        return value is None or value == "" or value == () or value == []