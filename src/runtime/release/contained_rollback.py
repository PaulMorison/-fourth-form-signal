from __future__ import annotations

"""Governed runtime release contained-rollback state.

Canon ownership:
- Consumes a governed production-entitlement-check record and explicit
  contained-rollback context to record whether rollback or partial reversal
  remains bounded across exposure, downstream effects, and reconstructible
  release lineage.
- Does not own rollback execution, release closure, monitoring admission,
  runtime verification, reopen handling, orchestration meaning, or lifecycle
  state meaning.
"""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Mapping
from uuid import uuid4

from runtime.release.contained_rollback_audit_adapter import (
    ContainedRollbackAuditAdapter,
)
from runtime.release.production_entitlement_check import (
    ProductionEntitlementCheckRecord,
)
from runtime.release.release_registry import ReleaseRegistry

_REQUIRED_COLLECTION_FIELDS = {
    "required_contained_rollback_fields",
    "optional_contained_rollback_fields",
    "required_audit_fields",
    "prohibited_contained_rollback_fields",
    "required_contained_rollback_snapshot",
    "optional_contained_rollback_snapshot",
    "required_audit_snapshot",
    "lineage",
    "outstanding_contained_rollback_prerequisites",
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
class ContainedRollbackRequest:
    production_entitlement_check: ProductionEntitlementCheckRecord
    contained_rollback_class_id: str
    contained_rollback_author_role: str
    contained_rollback_context: Mapping[str, object]
    correlation_id: str
    actor_id: str


@dataclass(frozen=True)
class ContainedRollbackRecord:
    contained_rollback_id: str
    contained_rollback_status: str
    reason: str
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
    contained_rollback_author_role: str
    contained_rollback_author_id: str
    required_contained_rollback_fields: tuple[str, ...]
    optional_contained_rollback_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    prohibited_contained_rollback_fields: tuple[str, ...]
    required_contained_rollback_snapshot: Mapping[str, str]
    optional_contained_rollback_snapshot: Mapping[str, str]
    required_audit_snapshot: Mapping[str, str]
    lineage: Mapping[str, str]
    generated_at: datetime
    reporting_scope_reference: str | None = None
    restriction_summary: str | None = None
    promotion_scope_restriction_reference: str | None = None
    follow_up_review_reference: str | None = None
    release_escalation_path_reference: str | None = None
    contained_rollback_prerequisite_reference: str | None = None
    outstanding_contained_rollback_prerequisites: tuple[str, ...] = ()
    missing_contained_rollback_fields: tuple[str, ...] = ()
    prohibited_contained_rollback_fields_present: tuple[str, ...] = ()

    def to_contract_dict(self) -> dict[str, object]:
        return _serialize_payload(asdict(self))

    def to_transport_context(self) -> dict[str, object]:
        context: dict[str, object] = {
            "contained_rollback_outcome": self.contained_rollback_outcome,
            "contained_rollback_judgment": self.contained_rollback_judgment,
            "rollback_execution_reference": self.rollback_execution_reference,
            "containment_evidence_reference": self.containment_evidence_reference,
            "bounded_exposure_reference": self.bounded_exposure_reference,
            "downstream_effects_boundary_reference": (
                self.downstream_effects_boundary_reference
            ),
            "release_lineage_reconstruction_reference": (
                self.release_lineage_reconstruction_reference
            ),
            "production_entitlement_check_outcome": (
                self.production_entitlement_check_outcome
            ),
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
        if self.contained_rollback_prerequisite_reference is not None:
            context["contained_rollback_prerequisite_reference"] = (
                self.contained_rollback_prerequisite_reference
            )
        if self.outstanding_contained_rollback_prerequisites:
            context["outstanding_contained_rollback_prerequisites"] = list(
                self.outstanding_contained_rollback_prerequisites
            )
        return context


class ContainedRollback:
    """Builds contained-rollback records from production-entitlement checks."""

    def __init__(
        self,
        *,
        release_registry: ReleaseRegistry,
        contained_rollback_audit_adapter: ContainedRollbackAuditAdapter,
    ) -> None:
        self._release_registry = release_registry
        self._contained_rollback_audit_adapter = contained_rollback_audit_adapter

    def generate(self, request: ContainedRollbackRequest) -> ContainedRollbackRecord:
        template, fallback_template_used = (
            self._release_registry.resolve_contained_rollback_template(
                semantic_scope=request.production_entitlement_check.semantic_scope,
                production_entitlement_check_class_id=(
                    request.production_entitlement_check.production_entitlement_check_class_id
                ),
                contained_rollback_class_id=request.contained_rollback_class_id,
                route_name=request.production_entitlement_check.lineage.get(
                    "route_name"
                ),
            )
        )
        class_definition = self._release_registry.get_contained_rollback_class(
            request.contained_rollback_class_id
        )
        combined_context = self._combined_context(request, class_definition)
        (
            required_contained_rollback_snapshot,
            missing_contained_rollback_fields,
        ) = self._snapshot_required_fields(
            template.required_contained_rollback_fields,
            combined_context,
        )
        required_audit_snapshot, missing_audit_fields = self._snapshot_required_fields(
            template.required_audit_fields,
            combined_context,
        )
        all_missing_fields = tuple(
            dict.fromkeys(missing_contained_rollback_fields + missing_audit_fields)
        )
        optional_contained_rollback_snapshot = self._snapshot_optional_fields(
            template.optional_contained_rollback_fields,
            combined_context,
        )
        prohibited_contained_rollback_fields_present = (
            self._prohibited_contained_rollback_fields_present(
                class_definition.prohibited_contained_rollback_fields,
                request.contained_rollback_context,
            )
        )
        contained_rollback_status = self._contained_rollback_status(
            production_entitlement_check=request.production_entitlement_check,
            class_definition=class_definition,
            combined_context=combined_context,
            missing_contained_rollback_fields=all_missing_fields,
            prohibited_contained_rollback_fields_present=(
                prohibited_contained_rollback_fields_present
            ),
            fallback_template_used=fallback_template_used,
        )
        contained_rollback_outcome = self._contained_rollback_outcome(
            template=template,
            contained_rollback_status=contained_rollback_status,
        )
        reason = self._reason(
            production_entitlement_check=request.production_entitlement_check,
            contained_rollback_status=contained_rollback_status,
            contained_rollback_class_id=class_definition.contained_rollback_class_id,
            missing_contained_rollback_fields=all_missing_fields,
            prohibited_contained_rollback_fields_present=(
                prohibited_contained_rollback_fields_present
            ),
            class_definition=class_definition,
            combined_context=combined_context,
            contained_rollback_outcome=contained_rollback_outcome,
        )
        lineage = self._lineage(request, class_definition, template)

        upstream = request.production_entitlement_check
        record = ContainedRollbackRecord(
            contained_rollback_id=str(uuid4()),
            contained_rollback_status=contained_rollback_status,
            reason=reason,
            contained_rollback_class_id=class_definition.contained_rollback_class_id,
            contained_rollback_template_id=template.contained_rollback_template_id,
            contained_rollback_outcome=contained_rollback_outcome,
            contained_rollback_judgment=self._field_value_or_placeholder(
                field_name="contained_rollback_judgment",
                snapshot=required_contained_rollback_snapshot,
                context=combined_context,
            ),
            rollback_execution_reference=self._field_value_or_placeholder(
                field_name="rollback_execution_reference",
                snapshot=required_contained_rollback_snapshot,
                context=combined_context,
            ),
            containment_evidence_reference=self._field_value_or_placeholder(
                field_name="containment_evidence_reference",
                snapshot=required_contained_rollback_snapshot,
                context=combined_context,
            ),
            bounded_exposure_reference=self._field_value_or_placeholder(
                field_name="bounded_exposure_reference",
                snapshot=required_contained_rollback_snapshot,
                context=combined_context,
            ),
            downstream_effects_boundary_reference=self._field_value_or_placeholder(
                field_name="downstream_effects_boundary_reference",
                snapshot=required_contained_rollback_snapshot,
                context=combined_context,
            ),
            release_lineage_reconstruction_reference=self._field_value_or_placeholder(
                field_name="release_lineage_reconstruction_reference",
                snapshot=required_contained_rollback_snapshot,
                context=combined_context,
            ),
            contained_rollback_authority_reference=self._field_value_or_placeholder(
                field_name="contained_rollback_authority_reference",
                snapshot=required_contained_rollback_snapshot,
                context=combined_context,
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
            release_watch_discipline_class_id=upstream.release_watch_discipline_class_id,
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
            contained_rollback_author_role=request.contained_rollback_author_role,
            contained_rollback_author_id=request.actor_id,
            required_contained_rollback_fields=(
                template.required_contained_rollback_fields
            ),
            optional_contained_rollback_fields=(
                template.optional_contained_rollback_fields
            ),
            required_audit_fields=template.required_audit_fields,
            prohibited_contained_rollback_fields=(
                class_definition.prohibited_contained_rollback_fields
            ),
            required_contained_rollback_snapshot=(
                required_contained_rollback_snapshot
            ),
            optional_contained_rollback_snapshot=(
                optional_contained_rollback_snapshot
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
            contained_rollback_prerequisite_reference=combined_context.get(
                "contained_rollback_prerequisite_reference"
            ),
            outstanding_contained_rollback_prerequisites=(
                combined_context["outstanding_contained_rollback_prerequisites"]
            ),
            missing_contained_rollback_fields=all_missing_fields,
            prohibited_contained_rollback_fields_present=(
                prohibited_contained_rollback_fields_present
            ),
        )
        self._contained_rollback_audit_adapter.record_contained_rollback(
            record,
            request=request,
        )
        return record

    def _combined_context(
        self,
        request: ContainedRollbackRequest,
        class_definition,
    ) -> dict[str, object]:
        upstream = request.production_entitlement_check
        context = dict(upstream.required_production_entitlement_check_snapshot)
        context.update(upstream.optional_production_entitlement_check_snapshot)
        context.update(upstream.required_audit_snapshot)
        context.update(dict(request.contained_rollback_context))
        context.update(
            {
                "contained_rollback_class_id": (
                    class_definition.contained_rollback_class_id
                ),
                "contained_rollback_author_id": request.actor_id,
                "contained_rollback_author_role": (
                    request.contained_rollback_author_role
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
                "contained_rollback_judgment": self._optional_text(
                    context.get("contained_rollback_judgment")
                ),
                "rollback_execution_reference": self._optional_text(
                    context.get("rollback_execution_reference")
                ),
                "containment_evidence_reference": self._optional_text(
                    context.get("containment_evidence_reference")
                ),
                "bounded_exposure_reference": self._optional_text(
                    context.get("bounded_exposure_reference")
                ),
                "downstream_effects_boundary_reference": self._optional_text(
                    context.get("downstream_effects_boundary_reference")
                ),
                "release_lineage_reconstruction_reference": self._optional_text(
                    context.get("release_lineage_reconstruction_reference")
                ),
                "contained_rollback_authority_reference": self._optional_text(
                    context.get("contained_rollback_authority_reference")
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
                "contained_rollback_prerequisite_reference": self._optional_text(
                    context.get("contained_rollback_prerequisite_reference")
                ),
                "outstanding_contained_rollback_prerequisites": (
                    self._sequence_as_tuple(
                        context.get("outstanding_contained_rollback_prerequisites")
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

    def _prohibited_contained_rollback_fields_present(
        self,
        prohibited_fields: tuple[str, ...],
        context: Mapping[str, object],
    ) -> tuple[str, ...]:
        return tuple(
            field_name
            for field_name in prohibited_fields
            if not self._is_missing_value(context.get(field_name))
        )

    def _contained_rollback_status(
        self,
        *,
        production_entitlement_check: ProductionEntitlementCheckRecord,
        class_definition,
        combined_context: Mapping[str, object],
        missing_contained_rollback_fields: tuple[str, ...],
        prohibited_contained_rollback_fields_present: tuple[str, ...],
        fallback_template_used: bool,
    ) -> str:
        if prohibited_contained_rollback_fields_present:
            return "prohibited_overlap_blocked"
        if missing_contained_rollback_fields:
            return "blocked_missing_context"
        if (
            production_entitlement_check.production_entitlement_check_status
            not in class_definition.allowed_production_entitlement_check_statuses
        ):
            return "rejected_for_contained_rollback_use"
        if (
            production_entitlement_check.production_entitlement_check_outcome
            not in class_definition.allowed_production_entitlement_check_outcomes
        ):
            return "rejected_for_contained_rollback_use"
        if self._has_contained_rollback_restrictions(
            combined_context
        ) and not class_definition.allow_contained_rollback_restrictions:
            return "rejected_for_contained_rollback_use"
        if self._has_contained_rollback_prerequisite_deferral(
            combined_context
        ) and not class_definition.allow_contained_rollback_prerequisite_deferral:
            return "rejected_for_contained_rollback_use"
        return (
            "fallback_template_applied"
            if fallback_template_used
            else "contained_rollback_bounded"
        )

    def _contained_rollback_outcome(
        self,
        *,
        template,
        contained_rollback_status: str,
    ) -> str:
        if contained_rollback_status in {
            "blocked_missing_context",
            "rejected_for_contained_rollback_use",
            "prohibited_overlap_blocked",
        }:
            return contained_rollback_status
        return template.contained_rollback_outcome

    def _reason(
        self,
        *,
        production_entitlement_check: ProductionEntitlementCheckRecord,
        contained_rollback_status: str,
        contained_rollback_class_id: str,
        missing_contained_rollback_fields: tuple[str, ...],
        prohibited_contained_rollback_fields_present: tuple[str, ...],
        class_definition,
        combined_context: Mapping[str, object],
        contained_rollback_outcome: str,
    ) -> str:
        if contained_rollback_status == "blocked_missing_context":
            return (
                "Contained rollback is blocked because governed rollback "
                "containment context is missing required fields: "
                + ", ".join(missing_contained_rollback_fields)
                + "."
            )
        if contained_rollback_status == "prohibited_overlap_blocked":
            return (
                "Contained rollback is blocked because context overlaps release "
                "closure, runtime verification, monitoring admission, reopen, or "
                "orchestration fields: "
                + ", ".join(prohibited_contained_rollback_fields_present)
                + "."
            )
        if contained_rollback_status == "rejected_for_contained_rollback_use":
            if (
                production_entitlement_check.production_entitlement_check_status
                not in class_definition.allowed_production_entitlement_check_statuses
            ):
                return (
                    "Contained rollback rejects production-entitlement-check "
                    "status '"
                    f"{production_entitlement_check.production_entitlement_check_status}' "
                    f"for class '{contained_rollback_class_id}'."
                )
            if (
                production_entitlement_check.production_entitlement_check_outcome
                not in class_definition.allowed_production_entitlement_check_outcomes
            ):
                return (
                    "Contained rollback rejects production-entitlement-check "
                    "outcome '"
                    f"{production_entitlement_check.production_entitlement_check_outcome}' "
                    f"for class '{contained_rollback_class_id}'."
                )
            if self._has_contained_rollback_restrictions(
                combined_context
            ) and not class_definition.allow_contained_rollback_restrictions:
                return (
                    "Contained rollback rejects restricted rollback containment "
                    f"for class '{contained_rollback_class_id}'."
                )
            if self._has_contained_rollback_prerequisite_deferral(
                combined_context
            ) and not class_definition.allow_contained_rollback_prerequisite_deferral:
                return (
                    "Contained rollback rejects deferred containment evidence "
                    f"for class '{contained_rollback_class_id}'."
                )
        if contained_rollback_outcome == "bounded_exposure_preserved":
            return (
                "Rollback remains contained because exposure, downstream effects, "
                "and release lineage are explicitly bounded and reconstructible."
            )
        if contained_rollback_outcome == "partial_reversal_bounded":
            return (
                "Partial reversal remains contained while bounded production use, "
                "downstream effects, and lineage are explicitly preserved."
            )
        return (
            "Contained rollback is deferred until explicit containment evidence "
            "and rollback containment prerequisites are complete."
        )

    def _lineage(
        self,
        request: ContainedRollbackRequest,
        class_definition,
        template,
    ) -> dict[str, str]:
        lineage = dict(request.production_entitlement_check.lineage)
        lineage.update(
            {
                "production_entitlement_check_id": (
                    request.production_entitlement_check.production_entitlement_check_id
                ),
                "contained_rollback_class_id": (
                    class_definition.contained_rollback_class_id
                ),
                "contained_rollback_template_id": (
                    template.contained_rollback_template_id
                ),
            }
        )
        return lineage

    def _has_contained_rollback_restrictions(
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

    def _has_contained_rollback_prerequisite_deferral(
        self,
        context: Mapping[str, object],
    ) -> bool:
        return any(
            not self._is_missing_value(context.get(field_name))
            for field_name in (
                "contained_rollback_prerequisite_reference",
                "outstanding_contained_rollback_prerequisites",
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
