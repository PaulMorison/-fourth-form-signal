from __future__ import annotations

"""Governed runtime release audit trace.

Canon ownership:
- Consumes a governed contained-rollback record and explicit trace context to
  preserve reconstructible release-control lineage, invalid-release-state
  visibility, invalid-exposure visibility, and no-silent-promotion evidence.
- Does not own release closure or final disposition meaning, promotion
  completion as a lifecycle object, runtime verification, monitoring
  admission, reopen handling, orchestration meaning, or lifecycle state
  meaning.
"""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Mapping
from uuid import uuid4

from runtime.release.contained_rollback import ContainedRollbackRecord
from runtime.release.release_audit_trace_audit_adapter import (
    ReleaseAuditTraceAuditAdapter,
)
from runtime.release.release_registry import ReleaseRegistry

_REQUIRED_COLLECTION_FIELDS = {
    "required_release_audit_trace_fields",
    "optional_release_audit_trace_fields",
    "required_audit_fields",
    "prohibited_release_audit_trace_fields",
    "required_release_audit_trace_snapshot",
    "optional_release_audit_trace_snapshot",
    "required_audit_snapshot",
    "lineage",
    "outstanding_release_audit_trace_prerequisites",
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
class ReleaseAuditTraceRequest:
    contained_rollback: ContainedRollbackRecord
    release_audit_trace_class_id: str
    release_audit_trace_author_role: str
    release_audit_trace_context: Mapping[str, object]
    correlation_id: str
    actor_id: str


@dataclass(frozen=True)
class ReleaseAuditTraceRecord:
    release_audit_trace_id: str
    release_audit_trace_status: str
    reason: str
    release_audit_trace_class_id: str
    release_audit_trace_template_id: str
    release_audit_trace_outcome: str
    release_audit_trace_judgment: str
    release_control_lineage_reference: str
    invalid_release_state_visibility_reference: str
    invalid_exposure_visibility_reference: str
    no_silent_promotion_preservation_reference: str
    release_audit_trace_authority_reference: str
    contained_rollback_id: str
    contained_rollback_status: str
    contained_rollback_class_id: str
    contained_rollback_template_id: str
    contained_rollback_outcome: str
    contained_rollback_judgment: str
    rollback_execution_reference: str
    containment_evidence_reference: str
    bounded_exposure_reference: str
    downstream_effects_boundary_reference: str
    release_lineage_reconstruction_reference: str
    contained_rollback_authority_reference: str
    production_entitlement_check_id: str
    production_entitlement_check_status: str
    production_entitlement_check_class_id: str
    production_entitlement_check_template_id: str
    production_entitlement_check_outcome: str
    production_entitlement_judgment: str
    production_entitlement_evidence_reference: str
    production_entitlement_authority_reference: str
    release_confirmation_id: str
    release_confirmation_status: str
    release_confirmation_class_id: str
    release_confirmation_template_id: str
    release_confirmation_outcome: str
    release_confirmation_judgment: str
    release_confirmation_threshold_evidence_reference: str
    release_confirmation_authority_reference: str
    release_watch_discipline_id: str
    release_watch_discipline_status: str
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
    release_audit_trace_author_role: str
    release_audit_trace_author_id: str
    required_release_audit_trace_fields: tuple[str, ...]
    optional_release_audit_trace_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    prohibited_release_audit_trace_fields: tuple[str, ...]
    required_release_audit_trace_snapshot: Mapping[str, str]
    optional_release_audit_trace_snapshot: Mapping[str, str]
    required_audit_snapshot: Mapping[str, str]
    lineage: Mapping[str, str]
    generated_at: datetime
    reporting_scope_reference: str | None = None
    restriction_summary: str | None = None
    promotion_scope_restriction_reference: str | None = None
    follow_up_review_reference: str | None = None
    release_escalation_path_reference: str | None = None
    later_final_disposition_reference: str | None = None
    release_audit_trace_prerequisite_reference: str | None = None
    outstanding_release_audit_trace_prerequisites: tuple[str, ...] = ()
    missing_release_audit_trace_fields: tuple[str, ...] = ()
    prohibited_release_audit_trace_fields_present: tuple[str, ...] = ()

    def to_contract_dict(self) -> dict[str, object]:
        return _serialize_payload(asdict(self))

    def to_transport_context(self) -> dict[str, object]:
        context: dict[str, object] = {
            "release_audit_trace_outcome": self.release_audit_trace_outcome,
            "release_audit_trace_judgment": self.release_audit_trace_judgment,
            "release_control_lineage_reference": (
                self.release_control_lineage_reference
            ),
            "invalid_release_state_visibility_reference": (
                self.invalid_release_state_visibility_reference
            ),
            "invalid_exposure_visibility_reference": (
                self.invalid_exposure_visibility_reference
            ),
            "no_silent_promotion_preservation_reference": (
                self.no_silent_promotion_preservation_reference
            ),
            "contained_rollback_outcome": self.contained_rollback_outcome,
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
        if self.later_final_disposition_reference is not None:
            context["later_final_disposition_reference"] = (
                self.later_final_disposition_reference
            )
        if self.release_audit_trace_prerequisite_reference is not None:
            context["release_audit_trace_prerequisite_reference"] = (
                self.release_audit_trace_prerequisite_reference
            )
        if self.outstanding_release_audit_trace_prerequisites:
            context["outstanding_release_audit_trace_prerequisites"] = list(
                self.outstanding_release_audit_trace_prerequisites
            )
        return context


class ReleaseAuditTrace:
    """Builds release-audit-trace records from contained rollback records."""

    def __init__(
        self,
        *,
        release_registry: ReleaseRegistry,
        release_audit_trace_audit_adapter: ReleaseAuditTraceAuditAdapter,
    ) -> None:
        self._release_registry = release_registry
        self._release_audit_trace_audit_adapter = release_audit_trace_audit_adapter

    def generate(self, request: ReleaseAuditTraceRequest) -> ReleaseAuditTraceRecord:
        template, fallback_template_used = (
            self._release_registry.resolve_release_audit_trace_template(
                semantic_scope=request.contained_rollback.semantic_scope,
                contained_rollback_class_id=(
                    request.contained_rollback.contained_rollback_class_id
                ),
                release_audit_trace_class_id=(
                    request.release_audit_trace_class_id
                ),
                route_name=request.contained_rollback.lineage.get("route_name"),
            )
        )
        class_definition = self._release_registry.get_release_audit_trace_class(
            request.release_audit_trace_class_id
        )
        combined_context = self._combined_context(request, class_definition)
        (
            required_release_audit_trace_snapshot,
            missing_release_audit_trace_fields,
        ) = self._snapshot_required_fields(
            template.required_release_audit_trace_fields,
            combined_context,
        )
        required_audit_snapshot, missing_audit_fields = self._snapshot_required_fields(
            template.required_audit_fields,
            combined_context,
        )
        all_missing_fields = tuple(
            dict.fromkeys(missing_release_audit_trace_fields + missing_audit_fields)
        )
        optional_release_audit_trace_snapshot = self._snapshot_optional_fields(
            template.optional_release_audit_trace_fields,
            combined_context,
        )
        prohibited_release_audit_trace_fields_present = (
            self._prohibited_release_audit_trace_fields_present(
                class_definition.prohibited_release_audit_trace_fields,
                request.release_audit_trace_context,
            )
        )
        release_audit_trace_status = self._release_audit_trace_status(
            contained_rollback=request.contained_rollback,
            class_definition=class_definition,
            combined_context=combined_context,
            missing_release_audit_trace_fields=all_missing_fields,
            prohibited_release_audit_trace_fields_present=(
                prohibited_release_audit_trace_fields_present
            ),
            fallback_template_used=fallback_template_used,
        )
        release_audit_trace_outcome = self._release_audit_trace_outcome(
            template=template,
            release_audit_trace_status=release_audit_trace_status,
        )
        reason = self._reason(
            contained_rollback=request.contained_rollback,
            release_audit_trace_status=release_audit_trace_status,
            release_audit_trace_class_id=(
                class_definition.release_audit_trace_class_id
            ),
            missing_release_audit_trace_fields=all_missing_fields,
            prohibited_release_audit_trace_fields_present=(
                prohibited_release_audit_trace_fields_present
            ),
            class_definition=class_definition,
            combined_context=combined_context,
            release_audit_trace_outcome=release_audit_trace_outcome,
        )
        lineage = self._lineage(request, class_definition, template)

        upstream = request.contained_rollback
        record = ReleaseAuditTraceRecord(
            release_audit_trace_id=str(uuid4()),
            release_audit_trace_status=release_audit_trace_status,
            reason=reason,
            release_audit_trace_class_id=(
                class_definition.release_audit_trace_class_id
            ),
            release_audit_trace_template_id=(
                template.release_audit_trace_template_id
            ),
            release_audit_trace_outcome=release_audit_trace_outcome,
            release_audit_trace_judgment=self._field_value_or_placeholder(
                field_name="release_audit_trace_judgment",
                snapshot=required_release_audit_trace_snapshot,
                context=combined_context,
            ),
            release_control_lineage_reference=self._field_value_or_placeholder(
                field_name="release_control_lineage_reference",
                snapshot=required_release_audit_trace_snapshot,
                context=combined_context,
            ),
            invalid_release_state_visibility_reference=(
                self._field_value_or_placeholder(
                    field_name="invalid_release_state_visibility_reference",
                    snapshot=required_release_audit_trace_snapshot,
                    context=combined_context,
                )
            ),
            invalid_exposure_visibility_reference=self._field_value_or_placeholder(
                field_name="invalid_exposure_visibility_reference",
                snapshot=required_release_audit_trace_snapshot,
                context=combined_context,
            ),
            no_silent_promotion_preservation_reference=(
                self._field_value_or_placeholder(
                    field_name="no_silent_promotion_preservation_reference",
                    snapshot=required_release_audit_trace_snapshot,
                    context=combined_context,
                )
            ),
            release_audit_trace_authority_reference=(
                self._field_value_or_placeholder(
                    field_name="release_audit_trace_authority_reference",
                    snapshot=required_release_audit_trace_snapshot,
                    context=combined_context,
                )
            ),
            contained_rollback_id=upstream.contained_rollback_id,
            contained_rollback_status=upstream.contained_rollback_status,
            contained_rollback_class_id=upstream.contained_rollback_class_id,
            contained_rollback_template_id=upstream.contained_rollback_template_id,
            contained_rollback_outcome=upstream.contained_rollback_outcome,
            contained_rollback_judgment=upstream.contained_rollback_judgment,
            rollback_execution_reference=upstream.rollback_execution_reference,
            containment_evidence_reference=upstream.containment_evidence_reference,
            bounded_exposure_reference=upstream.bounded_exposure_reference,
            downstream_effects_boundary_reference=(
                upstream.downstream_effects_boundary_reference
            ),
            release_lineage_reconstruction_reference=(
                upstream.release_lineage_reconstruction_reference
            ),
            contained_rollback_authority_reference=(
                upstream.contained_rollback_authority_reference
            ),
            production_entitlement_check_id=upstream.production_entitlement_check_id,
            production_entitlement_check_status=(
                upstream.production_entitlement_check_status
            ),
            production_entitlement_check_class_id=(
                upstream.production_entitlement_check_class_id
            ),
            production_entitlement_check_template_id=(
                upstream.production_entitlement_check_template_id
            ),
            production_entitlement_check_outcome=(
                upstream.production_entitlement_check_outcome
            ),
            production_entitlement_judgment=upstream.production_entitlement_judgment,
            production_entitlement_evidence_reference=(
                upstream.production_entitlement_evidence_reference
            ),
            production_entitlement_authority_reference=(
                upstream.production_entitlement_authority_reference
            ),
            release_confirmation_id=upstream.release_confirmation_id,
            release_confirmation_status=upstream.release_confirmation_status,
            release_confirmation_class_id=upstream.release_confirmation_class_id,
            release_confirmation_template_id=upstream.release_confirmation_template_id,
            release_confirmation_outcome=upstream.release_confirmation_outcome,
            release_confirmation_judgment=upstream.release_confirmation_judgment,
            release_confirmation_threshold_evidence_reference=(
                upstream.release_confirmation_threshold_evidence_reference
            ),
            release_confirmation_authority_reference=(
                upstream.release_confirmation_authority_reference
            ),
            release_watch_discipline_id=upstream.release_watch_discipline_id,
            release_watch_discipline_status=upstream.release_watch_discipline_status,
            release_watch_discipline_class_id=(
                upstream.release_watch_discipline_class_id
            ),
            release_watch_discipline_template_id=(
                upstream.release_watch_discipline_template_id
            ),
            release_watch_discipline_outcome=upstream.release_watch_discipline_outcome,
            release_watch_discipline_summary=upstream.release_watch_discipline_summary,
            release_confirmation_window=upstream.release_confirmation_window,
            release_response_threshold_reference=(
                upstream.release_response_threshold_reference
            ),
            release_watch_owner_reference=upstream.release_watch_owner_reference,
            rollback_trigger_reference=upstream.rollback_trigger_reference,
            rollback_plan_reference=upstream.rollback_plan_reference,
            promotion_candidate_reference=upstream.promotion_candidate_reference,
            promotion_threshold_reference=upstream.promotion_threshold_reference,
            production_entitlement_boundary=upstream.production_entitlement_boundary,
            rollback_posture_reference=upstream.rollback_posture_reference,
            release_watch_window=upstream.release_watch_window,
            release_confirmation_threshold_reference=(
                upstream.release_confirmation_threshold_reference
            ),
            promotion_scope_reference=upstream.promotion_scope_reference,
            promotion_boundary_summary=upstream.promotion_boundary_summary,
            rollout_scope_boundary_reference=upstream.rollout_scope_boundary_reference,
            exposure_boundary_reference=upstream.exposure_boundary_reference,
            rollout_boundary_summary=upstream.rollout_boundary_summary,
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
            release_audit_trace_author_role=request.release_audit_trace_author_role,
            release_audit_trace_author_id=request.actor_id,
            required_release_audit_trace_fields=(
                template.required_release_audit_trace_fields
            ),
            optional_release_audit_trace_fields=(
                template.optional_release_audit_trace_fields
            ),
            required_audit_fields=template.required_audit_fields,
            prohibited_release_audit_trace_fields=(
                class_definition.prohibited_release_audit_trace_fields
            ),
            required_release_audit_trace_snapshot=(
                required_release_audit_trace_snapshot
            ),
            optional_release_audit_trace_snapshot=(
                optional_release_audit_trace_snapshot
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
            later_final_disposition_reference=combined_context.get(
                "later_final_disposition_reference"
            ),
            release_audit_trace_prerequisite_reference=combined_context.get(
                "release_audit_trace_prerequisite_reference"
            ),
            outstanding_release_audit_trace_prerequisites=(
                combined_context["outstanding_release_audit_trace_prerequisites"]
            ),
            missing_release_audit_trace_fields=all_missing_fields,
            prohibited_release_audit_trace_fields_present=(
                prohibited_release_audit_trace_fields_present
            ),
        )
        self._release_audit_trace_audit_adapter.record_release_audit_trace(
            record,
            request=request,
        )
        return record

    def _combined_context(
        self,
        request: ReleaseAuditTraceRequest,
        class_definition,
    ) -> dict[str, object]:
        upstream = request.contained_rollback
        context = dict(upstream.required_contained_rollback_snapshot)
        context.update(upstream.optional_contained_rollback_snapshot)
        context.update(upstream.required_audit_snapshot)
        context.update(dict(request.release_audit_trace_context))
        context.update(
            {
                "release_audit_trace_class_id": (
                    class_definition.release_audit_trace_class_id
                ),
                "release_audit_trace_author_id": request.actor_id,
                "release_audit_trace_author_role": (
                    request.release_audit_trace_author_role
                ),
                "contained_rollback_id": upstream.contained_rollback_id,
                "contained_rollback_status": upstream.contained_rollback_status,
                "contained_rollback_class_id": (
                    upstream.contained_rollback_class_id
                ),
                "contained_rollback_template_id": (
                    upstream.contained_rollback_template_id
                ),
                "contained_rollback_outcome": (
                    upstream.contained_rollback_outcome
                ),
                "contained_rollback_judgment": (
                    upstream.contained_rollback_judgment
                ),
                "production_entitlement_check_id": (
                    upstream.production_entitlement_check_id
                ),
                "production_entitlement_check_status": (
                    upstream.production_entitlement_check_status
                ),
                "production_entitlement_check_class_id": (
                    upstream.production_entitlement_check_class_id
                ),
                "production_entitlement_check_template_id": (
                    upstream.production_entitlement_check_template_id
                ),
                "production_entitlement_check_outcome": (
                    upstream.production_entitlement_check_outcome
                ),
                "production_entitlement_judgment": (
                    upstream.production_entitlement_judgment
                ),
                "production_entitlement_evidence_reference": (
                    upstream.production_entitlement_evidence_reference
                ),
                "production_entitlement_authority_reference": (
                    upstream.production_entitlement_authority_reference
                ),
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
                "release_audit_trace_judgment": self._optional_text(
                    context.get("release_audit_trace_judgment")
                ),
                "release_control_lineage_reference": self._optional_text(
                    context.get("release_control_lineage_reference")
                ),
                "invalid_release_state_visibility_reference": (
                    self._optional_text(
                        context.get(
                            "invalid_release_state_visibility_reference"
                        )
                    )
                ),
                "invalid_exposure_visibility_reference": self._optional_text(
                    context.get("invalid_exposure_visibility_reference")
                ),
                "no_silent_promotion_preservation_reference": (
                    self._optional_text(
                        context.get(
                            "no_silent_promotion_preservation_reference"
                        )
                    )
                ),
                "release_audit_trace_authority_reference": (
                    self._optional_text(
                        context.get("release_audit_trace_authority_reference")
                    )
                ),
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
                "release_escalation_path_reference": self._optional_text(
                    context.get("release_escalation_path_reference")
                )
                or upstream.release_escalation_path_reference,
                "later_final_disposition_reference": self._optional_text(
                    context.get("later_final_disposition_reference")
                ),
                "release_audit_trace_prerequisite_reference": (
                    self._optional_text(
                        context.get(
                            "release_audit_trace_prerequisite_reference"
                        )
                    )
                ),
                "outstanding_release_audit_trace_prerequisites": (
                    self._sequence_as_tuple(
                        context.get(
                            "outstanding_release_audit_trace_prerequisites"
                        )
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

    def _prohibited_release_audit_trace_fields_present(
        self,
        prohibited_fields: tuple[str, ...],
        context: Mapping[str, object],
    ) -> tuple[str, ...]:
        return tuple(
            field_name
            for field_name in prohibited_fields
            if not self._is_missing_value(context.get(field_name))
        )

    def _release_audit_trace_status(
        self,
        *,
        contained_rollback: ContainedRollbackRecord,
        class_definition,
        combined_context: Mapping[str, object],
        missing_release_audit_trace_fields: tuple[str, ...],
        prohibited_release_audit_trace_fields_present: tuple[str, ...],
        fallback_template_used: bool,
    ) -> str:
        if prohibited_release_audit_trace_fields_present:
            return "prohibited_overlap_blocked"
        if missing_release_audit_trace_fields:
            return "blocked_missing_context"
        if (
            contained_rollback.contained_rollback_status
            not in class_definition.allowed_contained_rollback_statuses
        ):
            return "rejected_for_release_audit_trace_use"
        if (
            contained_rollback.contained_rollback_outcome
            not in class_definition.allowed_contained_rollback_outcomes
        ):
            return "rejected_for_release_audit_trace_use"
        if self._has_release_audit_trace_restrictions(
            combined_context
        ) and not class_definition.allow_release_audit_trace_restrictions:
            return "rejected_for_release_audit_trace_use"
        if self._has_release_audit_trace_prerequisite_deferral(
            combined_context
        ) and not class_definition.allow_release_audit_trace_prerequisite_deferral:
            return "rejected_for_release_audit_trace_use"
        return (
            "fallback_template_applied"
            if fallback_template_used
            else "release_audit_trace_recorded"
        )

    def _release_audit_trace_outcome(
        self,
        *,
        template,
        release_audit_trace_status: str,
    ) -> str:
        if release_audit_trace_status in {
            "blocked_missing_context",
            "rejected_for_release_audit_trace_use",
            "prohibited_overlap_blocked",
        }:
            return release_audit_trace_status
        return template.release_audit_trace_outcome

    def _reason(
        self,
        *,
        contained_rollback: ContainedRollbackRecord,
        release_audit_trace_status: str,
        release_audit_trace_class_id: str,
        missing_release_audit_trace_fields: tuple[str, ...],
        prohibited_release_audit_trace_fields_present: tuple[str, ...],
        class_definition,
        combined_context: Mapping[str, object],
        release_audit_trace_outcome: str,
    ) -> str:
        if release_audit_trace_status == "blocked_missing_context":
            return (
                "Release audit trace is blocked because governed release-control "
                "trace context is missing required fields: "
                + ", ".join(missing_release_audit_trace_fields)
                + "."
            )
        if release_audit_trace_status == "prohibited_overlap_blocked":
            return (
                "Release audit trace is blocked because context overlaps runtime "
                "verification, monitoring, reopen, orchestration, or lifecycle "
                "fields: "
                + ", ".join(prohibited_release_audit_trace_fields_present)
                + "."
            )
        if release_audit_trace_status == "rejected_for_release_audit_trace_use":
            if (
                contained_rollback.contained_rollback_status
                not in class_definition.allowed_contained_rollback_statuses
            ):
                return (
                    "Release audit trace rejects contained-rollback status '"
                    f"{contained_rollback.contained_rollback_status}' for class "
                    f"'{release_audit_trace_class_id}'."
                )
            if (
                contained_rollback.contained_rollback_outcome
                not in class_definition.allowed_contained_rollback_outcomes
            ):
                return (
                    "Release audit trace rejects contained-rollback outcome '"
                    f"{contained_rollback.contained_rollback_outcome}' for class "
                    f"'{release_audit_trace_class_id}'."
                )
            if self._has_release_audit_trace_restrictions(
                combined_context
            ) and not class_definition.allow_release_audit_trace_restrictions:
                return (
                    "Release audit trace rejects restricted release lineage for "
                    f"class '{release_audit_trace_class_id}'."
                )
            if self._has_release_audit_trace_prerequisite_deferral(
                combined_context
            ) and not class_definition.allow_release_audit_trace_prerequisite_deferral:
                return (
                    "Release audit trace rejects deferred trace evidence for "
                    f"class '{release_audit_trace_class_id}'."
                )
        if release_audit_trace_outcome == "release_control_lineage_preserved":
            return (
                "Release audit trace preserves reconstructible release-control "
                "lineage, invalid-state visibility, invalid-exposure visibility, "
                "and no-silent-promotion evidence."
            )
        if release_audit_trace_outcome == "invalid_exposure_visibility_preserved":
            return (
                "Release audit trace preserves bounded conditional release lineage "
                "while keeping invalid-exposure visibility and no-silent-promotion "
                "evidence explicit."
            )
        return (
            "Release audit trace is deferred until explicit lineage-preservation "
            "evidence and trace prerequisites are complete."
        )

    def _lineage(
        self,
        request: ReleaseAuditTraceRequest,
        class_definition,
        template,
    ) -> dict[str, str]:
        lineage = dict(request.contained_rollback.lineage)
        lineage.update(
            {
                "contained_rollback_id": request.contained_rollback.contained_rollback_id,
                "release_audit_trace_class_id": (
                    class_definition.release_audit_trace_class_id
                ),
                "release_audit_trace_template_id": (
                    template.release_audit_trace_template_id
                ),
            }
        )
        return lineage

    def _has_release_audit_trace_restrictions(
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

    def _has_release_audit_trace_prerequisite_deferral(
        self,
        context: Mapping[str, object],
    ) -> bool:
        return any(
            not self._is_missing_value(context.get(field_name))
            for field_name in (
                "release_audit_trace_prerequisite_reference",
                "outstanding_release_audit_trace_prerequisites",
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