from __future__ import annotations

"""Governed runtime release release-watch discipline.

Canon ownership:
- Consumes a governed rollback-trigger record and explicit release-watch
  discipline context to decide whether post-release watch discipline is
  explicit enough, explicit only conditionally, deferred, blocked for missing
  context, rejected for release-watch-discipline use, or blocked for prohibited
  overlap.
- Does not own post-release watch execution, release confirmation judgment,
  rollback execution, monitoring, reopen handling, orchestration meaning, or
  lifecycle state meaning.
"""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Mapping
from uuid import uuid4

from runtime.release.release_registry import ReleaseRegistry
from runtime.release.release_watch_discipline_audit_adapter import (
    ReleaseWatchDisciplineAuditAdapter,
)
from runtime.release.rollback_trigger_guard import RollbackTriggerRecord

_REQUIRED_COLLECTION_FIELDS = {
    "required_release_watch_discipline_fields",
    "optional_release_watch_discipline_fields",
    "required_audit_fields",
    "prohibited_release_watch_discipline_fields",
    "required_release_watch_discipline_snapshot",
    "optional_release_watch_discipline_snapshot",
    "required_audit_snapshot",
    "lineage",
    "outstanding_release_watch_prerequisites",
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
class ReleaseWatchDisciplineRequest:
    rollback_trigger: RollbackTriggerRecord
    release_watch_discipline_class_id: str
    release_watch_discipline_author_role: str
    release_watch_discipline_context: Mapping[str, object]
    correlation_id: str
    actor_id: str


@dataclass(frozen=True)
class ReleaseWatchDisciplineRecord:
    release_watch_discipline_id: str
    release_watch_discipline_status: str
    reason: str
    release_watch_discipline_class_id: str
    release_watch_discipline_template_id: str
    release_watch_discipline_outcome: str
    release_watch_discipline_summary: str
    release_confirmation_window: str
    release_response_threshold_reference: str
    release_watch_owner_reference: str
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
    rollback_trigger_id: str
    rollback_trigger_status: str
    rollback_trigger_class_id: str
    rollback_trigger_template_id: str
    rollback_trigger_outcome: str
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
    release_watch_discipline_author_role: str
    release_watch_discipline_author_id: str
    required_release_watch_discipline_fields: tuple[str, ...]
    optional_release_watch_discipline_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    prohibited_release_watch_discipline_fields: tuple[str, ...]
    required_release_watch_discipline_snapshot: Mapping[str, str]
    optional_release_watch_discipline_snapshot: Mapping[str, str]
    required_audit_snapshot: Mapping[str, str]
    lineage: Mapping[str, str]
    generated_at: datetime
    reporting_scope_reference: str | None = None
    restriction_summary: str | None = None
    promotion_scope_restriction_reference: str | None = None
    follow_up_review_reference: str | None = None
    release_escalation_path_reference: str | None = None
    release_watch_prerequisite_reference: str | None = None
    outstanding_release_watch_prerequisites: tuple[str, ...] = ()
    missing_release_watch_discipline_fields: tuple[str, ...] = ()
    prohibited_release_watch_discipline_fields_present: tuple[str, ...] = ()

    def to_contract_dict(self) -> dict[str, object]:
        return _serialize_payload(asdict(self))

    def to_transport_context(self) -> dict[str, object]:
        context: dict[str, object] = {
            "release_watch_discipline_outcome": (
                self.release_watch_discipline_outcome
            ),
            "release_watch_discipline_summary": (
                self.release_watch_discipline_summary
            ),
            "release_watch_window": self.release_watch_window,
            "release_confirmation_window": self.release_confirmation_window,
            "release_confirmation_threshold_reference": (
                self.release_confirmation_threshold_reference
            ),
            "release_response_threshold_reference": (
                self.release_response_threshold_reference
            ),
            "release_watch_owner_reference": self.release_watch_owner_reference,
        }
        if self.release_escalation_path_reference is not None:
            context["release_escalation_path_reference"] = (
                self.release_escalation_path_reference
            )
        if self.restriction_summary is not None:
            context["restriction_summary"] = self.restriction_summary
        if self.promotion_scope_restriction_reference is not None:
            context["promotion_scope_restriction_reference"] = (
                self.promotion_scope_restriction_reference
            )
        if self.follow_up_review_reference is not None:
            context["follow_up_review_reference"] = self.follow_up_review_reference
        if self.release_watch_prerequisite_reference is not None:
            context["release_watch_prerequisite_reference"] = (
                self.release_watch_prerequisite_reference
            )
        if self.outstanding_release_watch_prerequisites:
            context["outstanding_release_watch_prerequisites"] = list(
                self.outstanding_release_watch_prerequisites
            )
        return context


class ReleaseWatchDiscipline:
    """Builds release-watch-discipline records from rollback-trigger records."""

    def __init__(
        self,
        *,
        release_registry: ReleaseRegistry,
        release_watch_discipline_audit_adapter: ReleaseWatchDisciplineAuditAdapter,
    ) -> None:
        self._release_registry = release_registry
        self._release_watch_discipline_audit_adapter = (
            release_watch_discipline_audit_adapter
        )

    def generate(
        self,
        request: ReleaseWatchDisciplineRequest,
    ) -> ReleaseWatchDisciplineRecord:
        template, fallback_template_used = (
            self._release_registry.resolve_release_watch_discipline_template(
                semantic_scope=request.rollback_trigger.semantic_scope,
                rollback_trigger_class_id=(
                    request.rollback_trigger.rollback_trigger_class_id
                ),
                release_watch_discipline_class_id=(
                    request.release_watch_discipline_class_id
                ),
                route_name=request.rollback_trigger.lineage.get("route_name"),
            )
        )
        class_definition = self._release_registry.get_release_watch_discipline_class(
            request.release_watch_discipline_class_id
        )
        combined_context = self._combined_context(request, class_definition)
        (
            required_release_watch_discipline_snapshot,
            missing_release_watch_discipline_fields,
        ) = self._snapshot_required_fields(
            template.required_release_watch_discipline_fields,
            combined_context,
        )
        required_audit_snapshot, missing_audit_fields = self._snapshot_required_fields(
            template.required_audit_fields,
            combined_context,
        )
        all_missing_fields = tuple(
            dict.fromkeys(
                missing_release_watch_discipline_fields + missing_audit_fields
            )
        )
        optional_release_watch_discipline_snapshot = self._snapshot_optional_fields(
            template.optional_release_watch_discipline_fields,
            combined_context,
        )
        prohibited_release_watch_discipline_fields_present = (
            self._prohibited_release_watch_discipline_fields_present(
                class_definition.prohibited_release_watch_discipline_fields,
                request.release_watch_discipline_context,
            )
        )
        release_watch_discipline_status = self._release_watch_discipline_status(
            rollback_trigger=request.rollback_trigger,
            class_definition=class_definition,
            combined_context=combined_context,
            missing_release_watch_discipline_fields=all_missing_fields,
            prohibited_release_watch_discipline_fields_present=(
                prohibited_release_watch_discipline_fields_present
            ),
            fallback_template_used=fallback_template_used,
        )
        release_watch_discipline_outcome = self._release_watch_discipline_outcome(
            template=template,
            release_watch_discipline_status=release_watch_discipline_status,
        )
        reason = self._reason(
            rollback_trigger=request.rollback_trigger,
            release_watch_discipline_status=release_watch_discipline_status,
            release_watch_discipline_class_id=(
                class_definition.release_watch_discipline_class_id
            ),
            missing_release_watch_discipline_fields=all_missing_fields,
            prohibited_release_watch_discipline_fields_present=(
                prohibited_release_watch_discipline_fields_present
            ),
            class_definition=class_definition,
            combined_context=combined_context,
            release_watch_discipline_outcome=release_watch_discipline_outcome,
        )
        lineage = self._lineage(request, class_definition, template)

        upstream = request.rollback_trigger
        record = ReleaseWatchDisciplineRecord(
            release_watch_discipline_id=str(uuid4()),
            release_watch_discipline_status=release_watch_discipline_status,
            reason=reason,
            release_watch_discipline_class_id=(
                class_definition.release_watch_discipline_class_id
            ),
            release_watch_discipline_template_id=(
                template.release_watch_discipline_template_id
            ),
            release_watch_discipline_outcome=release_watch_discipline_outcome,
            release_watch_discipline_summary=self._field_value_or_placeholder(
                field_name="release_watch_discipline_summary",
                snapshot=required_release_watch_discipline_snapshot,
                context=combined_context,
            ),
            release_confirmation_window=self._field_value_or_placeholder(
                field_name="release_confirmation_window",
                snapshot=required_release_watch_discipline_snapshot,
                context=combined_context,
            ),
            release_response_threshold_reference=(
                self._field_value_or_placeholder(
                    field_name="release_response_threshold_reference",
                    snapshot=required_release_watch_discipline_snapshot,
                    context=combined_context,
                )
            ),
            release_watch_owner_reference=self._field_value_or_placeholder(
                field_name="release_watch_owner_reference",
                snapshot=required_release_watch_discipline_snapshot,
                context=combined_context,
            ),
            rollback_trigger_reference=self._field_value_or_placeholder(
                field_name="rollback_trigger_reference",
                snapshot=required_release_watch_discipline_snapshot,
                context=combined_context,
            ),
            rollback_plan_reference=self._field_value_or_placeholder(
                field_name="rollback_plan_reference",
                snapshot=required_release_watch_discipline_snapshot,
                context=combined_context,
            ),
            promotion_candidate_reference=self._field_value_or_placeholder(
                field_name="promotion_candidate_reference",
                snapshot=required_release_watch_discipline_snapshot,
                context=combined_context,
            ),
            promotion_threshold_reference=self._field_value_or_placeholder(
                field_name="promotion_threshold_reference",
                snapshot=required_release_watch_discipline_snapshot,
                context=combined_context,
            ),
            production_entitlement_boundary=self._field_value_or_placeholder(
                field_name="production_entitlement_boundary",
                snapshot=required_release_watch_discipline_snapshot,
                context=combined_context,
            ),
            rollback_posture_reference=self._field_value_or_placeholder(
                field_name="rollback_posture_reference",
                snapshot=required_release_watch_discipline_snapshot,
                context=combined_context,
            ),
            release_watch_window=self._field_value_or_placeholder(
                field_name="release_watch_window",
                snapshot=required_release_watch_discipline_snapshot,
                context=combined_context,
            ),
            release_confirmation_threshold_reference=(
                self._field_value_or_placeholder(
                    field_name="release_confirmation_threshold_reference",
                    snapshot=required_release_watch_discipline_snapshot,
                    context=combined_context,
                )
            ),
            promotion_scope_reference=self._field_value_or_placeholder(
                field_name="promotion_scope_reference",
                snapshot=required_release_watch_discipline_snapshot,
                context=combined_context,
            ),
            promotion_boundary_summary=self._field_value_or_placeholder(
                field_name="promotion_boundary_summary",
                snapshot=required_release_watch_discipline_snapshot,
                context=combined_context,
            ),
            rollout_scope_boundary_reference=self._field_value_or_placeholder(
                field_name="rollout_scope_boundary_reference",
                snapshot=required_release_watch_discipline_snapshot,
                context=combined_context,
            ),
            exposure_boundary_reference=self._field_value_or_placeholder(
                field_name="exposure_boundary_reference",
                snapshot=required_release_watch_discipline_snapshot,
                context=combined_context,
            ),
            rollout_boundary_summary=self._field_value_or_placeholder(
                field_name="rollout_boundary_summary",
                snapshot=required_release_watch_discipline_snapshot,
                context=combined_context,
            ),
            rollback_trigger_id=upstream.rollback_trigger_id,
            rollback_trigger_status=upstream.rollback_trigger_status,
            rollback_trigger_class_id=upstream.rollback_trigger_class_id,
            rollback_trigger_template_id=upstream.rollback_trigger_template_id,
            rollback_trigger_outcome=upstream.rollback_trigger_outcome,
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
            release_watch_discipline_author_role=(
                request.release_watch_discipline_author_role
            ),
            release_watch_discipline_author_id=request.actor_id,
            required_release_watch_discipline_fields=(
                template.required_release_watch_discipline_fields
            ),
            optional_release_watch_discipline_fields=(
                template.optional_release_watch_discipline_fields
            ),
            required_audit_fields=template.required_audit_fields,
            prohibited_release_watch_discipline_fields=(
                class_definition.prohibited_release_watch_discipline_fields
            ),
            required_release_watch_discipline_snapshot=(
                required_release_watch_discipline_snapshot
            ),
            optional_release_watch_discipline_snapshot=(
                optional_release_watch_discipline_snapshot
            ),
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
            release_escalation_path_reference=combined_context.get(
                "release_escalation_path_reference"
            ),
            release_watch_prerequisite_reference=combined_context.get(
                "release_watch_prerequisite_reference"
            ),
            outstanding_release_watch_prerequisites=(
                combined_context["outstanding_release_watch_prerequisites"]
            ),
            missing_release_watch_discipline_fields=all_missing_fields,
            prohibited_release_watch_discipline_fields_present=(
                prohibited_release_watch_discipline_fields_present
            ),
        )
        self._release_watch_discipline_audit_adapter.record_release_watch_discipline(
            record,
            request=request,
        )
        return record

    def _combined_context(
        self,
        request: ReleaseWatchDisciplineRequest,
        class_definition,
    ) -> dict[str, object]:
        context = dict(request.rollback_trigger.required_rollback_trigger_snapshot)
        context.update(request.rollback_trigger.optional_rollback_trigger_snapshot)
        context.update(request.rollback_trigger.required_audit_snapshot)
        context.update(dict(request.release_watch_discipline_context))
        upstream = request.rollback_trigger
        context.update(
            {
                "release_watch_discipline_class_id": (
                    class_definition.release_watch_discipline_class_id
                ),
                "release_watch_discipline_author_id": request.actor_id,
                "release_watch_discipline_author_role": (
                    request.release_watch_discipline_author_role
                ),
                "rollback_trigger_id": upstream.rollback_trigger_id,
                "rollback_trigger_status": upstream.rollback_trigger_status,
                "rollback_trigger_class_id": upstream.rollback_trigger_class_id,
                "rollback_trigger_template_id": (
                    upstream.rollback_trigger_template_id
                ),
                "rollback_trigger_outcome": upstream.rollback_trigger_outcome,
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
                )
                or upstream.rollback_trigger_reference,
                "rollback_plan_reference": self._optional_text(
                    context.get("rollback_plan_reference")
                )
                or upstream.rollback_plan_reference,
                "release_watch_discipline_summary": self._optional_text(
                    context.get("release_watch_discipline_summary")
                ),
                "release_confirmation_window": self._optional_text(
                    context.get("release_confirmation_window")
                ),
                "release_response_threshold_reference": self._optional_text(
                    context.get("release_response_threshold_reference")
                ),
                "release_watch_owner_reference": self._optional_text(
                    context.get("release_watch_owner_reference")
                ),
                "release_escalation_path_reference": self._optional_text(
                    context.get("release_escalation_path_reference")
                ),
                "release_watch_prerequisite_reference": self._optional_text(
                    context.get("release_watch_prerequisite_reference")
                ),
                "outstanding_release_watch_prerequisites": (
                    self._sequence_as_tuple(
                        context.get("outstanding_release_watch_prerequisites")
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

    def _prohibited_release_watch_discipline_fields_present(
        self,
        prohibited_fields: tuple[str, ...],
        context: Mapping[str, object],
    ) -> tuple[str, ...]:
        return tuple(
            field_name
            for field_name in prohibited_fields
            if not self._is_missing_value(context.get(field_name))
        )

    def _release_watch_discipline_status(
        self,
        *,
        rollback_trigger: RollbackTriggerRecord,
        class_definition,
        combined_context: Mapping[str, object],
        missing_release_watch_discipline_fields: tuple[str, ...],
        prohibited_release_watch_discipline_fields_present: tuple[str, ...],
        fallback_template_used: bool,
    ) -> str:
        if prohibited_release_watch_discipline_fields_present:
            return "prohibited_overlap_blocked"
        if missing_release_watch_discipline_fields:
            return "blocked_missing_context"
        if (
            rollback_trigger.rollback_trigger_status
            not in class_definition.allowed_rollback_trigger_statuses
        ):
            return "rejected_for_release_watch_discipline_use"
        if (
            rollback_trigger.rollback_trigger_outcome
            not in class_definition.allowed_rollback_trigger_outcomes
        ):
            return "rejected_for_release_watch_discipline_use"
        if self._has_release_watch_discipline_restrictions(combined_context) and not (
            class_definition.allow_release_watch_discipline_restrictions
        ):
            return "rejected_for_release_watch_discipline_use"
        if self._has_release_watch_prerequisite_deferral(combined_context) and not (
            class_definition.allow_release_watch_discipline_prerequisite_deferral
        ):
            return "rejected_for_release_watch_discipline_use"
        return (
            "fallback_template_applied"
            if fallback_template_used
            else "release_watch_discipline_defined"
        )

    def _release_watch_discipline_outcome(
        self,
        *,
        template,
        release_watch_discipline_status: str,
    ) -> str:
        if release_watch_discipline_status in {
            "blocked_missing_context",
            "rejected_for_release_watch_discipline_use",
            "prohibited_overlap_blocked",
        }:
            return release_watch_discipline_status
        return template.release_watch_discipline_outcome

    def _reason(
        self,
        *,
        rollback_trigger: RollbackTriggerRecord,
        release_watch_discipline_status: str,
        release_watch_discipline_class_id: str,
        missing_release_watch_discipline_fields: tuple[str, ...],
        prohibited_release_watch_discipline_fields_present: tuple[str, ...],
        class_definition,
        combined_context: Mapping[str, object],
        release_watch_discipline_outcome: str,
    ) -> str:
        if release_watch_discipline_status == "blocked_missing_context":
            return (
                "Release-watch discipline is blocked because governed release-watch "
                "discipline context is missing required fields: "
                + ", ".join(missing_release_watch_discipline_fields)
                + "."
            )
        if release_watch_discipline_status == "prohibited_overlap_blocked":
            return (
                "Release-watch discipline is blocked because context overlaps "
                "post-release watch execution, release confirmation judgment, "
                "rollback execution, monitoring, reopen, or orchestration fields: "
                + ", ".join(prohibited_release_watch_discipline_fields_present)
                + "."
            )
        if release_watch_discipline_status == "rejected_for_release_watch_discipline_use":
            if (
                rollback_trigger.rollback_trigger_status
                not in class_definition.allowed_rollback_trigger_statuses
            ):
                return (
                    "Release-watch discipline rejects rollback-trigger status '"
                    f"{rollback_trigger.rollback_trigger_status}' for class '"
                    f"{release_watch_discipline_class_id}'."
                )
            if (
                rollback_trigger.rollback_trigger_outcome
                not in class_definition.allowed_rollback_trigger_outcomes
            ):
                return (
                    "Release-watch discipline rejects rollback-trigger outcome '"
                    f"{rollback_trigger.rollback_trigger_outcome}' for class '"
                    f"{release_watch_discipline_class_id}'."
                )
            if self._has_release_watch_discipline_restrictions(combined_context) and not (
                class_definition.allow_release_watch_discipline_restrictions
            ):
                return (
                    "Release-watch discipline rejects restricted production exposure "
                    f"for class '{release_watch_discipline_class_id}'."
                )
            if self._has_release_watch_prerequisite_deferral(combined_context) and not (
                class_definition.allow_release_watch_discipline_prerequisite_deferral
            ):
                return (
                    "Release-watch discipline rejects deferred release-watch "
                    f"discipline evidence for class '{release_watch_discipline_class_id}'."
                )
        if release_watch_discipline_outcome == "ready_for_release_confirmation":
            return (
                "Governed release-watch discipline is explicit and the promoted "
                "release is ready for downstream release confirmation."
            )
        if (
            release_watch_discipline_outcome
            == "conditionally_ready_for_release_confirmation"
        ):
            return (
                "Governed release-watch discipline is explicit only conditionally "
                "and must preserve narrowed production exposure before downstream "
                "release confirmation."
            )
        return (
            "Governed release-watch discipline is deferred until explicit watch "
            "discipline evidence is completed."
        )

    def _lineage(
        self,
        request: ReleaseWatchDisciplineRequest,
        class_definition,
        template,
    ) -> dict[str, str]:
        lineage = dict(request.rollback_trigger.lineage)
        lineage.update(
            {
                "rollback_trigger_id": request.rollback_trigger.rollback_trigger_id,
                "release_watch_discipline_class_id": (
                    class_definition.release_watch_discipline_class_id
                ),
                "release_watch_discipline_template_id": (
                    template.release_watch_discipline_template_id
                ),
            }
        )
        return lineage

    def _has_release_watch_discipline_restrictions(
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

    def _has_release_watch_prerequisite_deferral(
        self,
        context: Mapping[str, object],
    ) -> bool:
        return any(
            not self._is_missing_value(context.get(field_name))
            for field_name in (
                "release_watch_prerequisite_reference",
                "outstanding_release_watch_prerequisites",
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