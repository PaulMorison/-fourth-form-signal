from __future__ import annotations

"""Governed runtime release production-entitlement check.

Canon ownership:
- Consumes a governed release-confirmation record and explicit production
  entitlement context to decide whether a release may cross from bounded
  exposure into broader trusted production entitlement, remain conditionally
  bounded, be deferred, be blocked for missing context, be rejected for
  production-entitlement use, or be blocked for prohibited overlap.
- Does not own contained rollback, rollback execution, release closure,
  monitoring admission, runtime verification, reopen handling, orchestration
  meaning, or lifecycle state meaning.
"""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Mapping
from uuid import uuid4

from runtime.release.production_entitlement_check_audit_adapter import (
    ProductionEntitlementCheckAuditAdapter,
)
from runtime.release.release_confirmation import ReleaseConfirmationRecord
from runtime.release.release_registry import ReleaseRegistry

_REQUIRED_COLLECTION_FIELDS = {
    "required_production_entitlement_check_fields",
    "optional_production_entitlement_check_fields",
    "required_audit_fields",
    "prohibited_production_entitlement_fields",
    "required_production_entitlement_check_snapshot",
    "optional_production_entitlement_check_snapshot",
    "required_audit_snapshot",
    "lineage",
    "outstanding_production_entitlement_prerequisites",
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
class ProductionEntitlementCheckRequest:
    release_confirmation: ReleaseConfirmationRecord
    production_entitlement_check_class_id: str
    production_entitlement_check_author_role: str
    production_entitlement_check_context: Mapping[str, object]
    correlation_id: str
    actor_id: str


@dataclass(frozen=True)
class ProductionEntitlementCheckRecord:
    production_entitlement_check_id: str
    production_entitlement_check_status: str
    reason: str
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
    production_entitlement_check_author_role: str
    production_entitlement_check_author_id: str
    required_production_entitlement_check_fields: tuple[str, ...]
    optional_production_entitlement_check_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    prohibited_production_entitlement_fields: tuple[str, ...]
    required_production_entitlement_check_snapshot: Mapping[str, str]
    optional_production_entitlement_check_snapshot: Mapping[str, str]
    required_audit_snapshot: Mapping[str, str]
    lineage: Mapping[str, str]
    generated_at: datetime
    reporting_scope_reference: str | None = None
    restriction_summary: str | None = None
    promotion_scope_restriction_reference: str | None = None
    follow_up_review_reference: str | None = None
    release_escalation_path_reference: str | None = None
    production_entitlement_prerequisite_reference: str | None = None
    outstanding_production_entitlement_prerequisites: tuple[str, ...] = ()
    missing_production_entitlement_check_fields: tuple[str, ...] = ()
    prohibited_production_entitlement_fields_present: tuple[str, ...] = ()

    def to_contract_dict(self) -> dict[str, object]:
        return _serialize_payload(asdict(self))

    def to_transport_context(self) -> dict[str, object]:
        context: dict[str, object] = {
            "production_entitlement_check_outcome": (
                self.production_entitlement_check_outcome
            ),
            "production_entitlement_judgment": self.production_entitlement_judgment,
            "production_entitlement_evidence_reference": (
                self.production_entitlement_evidence_reference
            ),
            "production_entitlement_authority_reference": (
                self.production_entitlement_authority_reference
            ),
            "production_entitlement_boundary": self.production_entitlement_boundary,
            "release_confirmation_outcome": self.release_confirmation_outcome,
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
        if self.production_entitlement_prerequisite_reference is not None:
            context["production_entitlement_prerequisite_reference"] = (
                self.production_entitlement_prerequisite_reference
            )
        if self.outstanding_production_entitlement_prerequisites:
            context["outstanding_production_entitlement_prerequisites"] = list(
                self.outstanding_production_entitlement_prerequisites
            )
        return context


class ProductionEntitlementCheck:
    """Builds production-entitlement-check records from release confirmations."""

    def __init__(
        self,
        *,
        release_registry: ReleaseRegistry,
        production_entitlement_check_audit_adapter: (
            ProductionEntitlementCheckAuditAdapter
        ),
    ) -> None:
        self._release_registry = release_registry
        self._production_entitlement_check_audit_adapter = (
            production_entitlement_check_audit_adapter
        )

    def generate(
        self,
        request: ProductionEntitlementCheckRequest,
    ) -> ProductionEntitlementCheckRecord:
        template, fallback_template_used = (
            self._release_registry.resolve_production_entitlement_check_template(
                semantic_scope=request.release_confirmation.semantic_scope,
                release_confirmation_class_id=(
                    request.release_confirmation.release_confirmation_class_id
                ),
                production_entitlement_check_class_id=(
                    request.production_entitlement_check_class_id
                ),
                route_name=request.release_confirmation.lineage.get("route_name"),
            )
        )
        class_definition = (
            self._release_registry.get_production_entitlement_check_class(
                request.production_entitlement_check_class_id
            )
        )
        combined_context = self._combined_context(request, class_definition)
        (
            required_production_entitlement_check_snapshot,
            missing_production_entitlement_check_fields,
        ) = self._snapshot_required_fields(
            template.required_production_entitlement_check_fields,
            combined_context,
        )
        required_audit_snapshot, missing_audit_fields = self._snapshot_required_fields(
            template.required_audit_fields,
            combined_context,
        )
        all_missing_fields = tuple(
            dict.fromkeys(
                missing_production_entitlement_check_fields + missing_audit_fields
            )
        )
        optional_production_entitlement_check_snapshot = self._snapshot_optional_fields(
            template.optional_production_entitlement_check_fields,
            combined_context,
        )
        prohibited_production_entitlement_fields_present = (
            self._prohibited_production_entitlement_fields_present(
                class_definition.prohibited_production_entitlement_fields,
                request.production_entitlement_check_context,
            )
        )
        production_entitlement_check_status = self._production_entitlement_check_status(
            release_confirmation=request.release_confirmation,
            class_definition=class_definition,
            combined_context=combined_context,
            missing_production_entitlement_check_fields=all_missing_fields,
            prohibited_production_entitlement_fields_present=(
                prohibited_production_entitlement_fields_present
            ),
            fallback_template_used=fallback_template_used,
        )
        production_entitlement_check_outcome = (
            self._production_entitlement_check_outcome(
                template=template,
                production_entitlement_check_status=(
                    production_entitlement_check_status
                ),
            )
        )
        reason = self._reason(
            release_confirmation=request.release_confirmation,
            production_entitlement_check_status=production_entitlement_check_status,
            production_entitlement_check_class_id=(
                class_definition.production_entitlement_check_class_id
            ),
            missing_production_entitlement_check_fields=all_missing_fields,
            prohibited_production_entitlement_fields_present=(
                prohibited_production_entitlement_fields_present
            ),
            class_definition=class_definition,
            combined_context=combined_context,
            production_entitlement_check_outcome=(
                production_entitlement_check_outcome
            ),
        )
        lineage = self._lineage(request, class_definition, template)

        upstream = request.release_confirmation
        record = ProductionEntitlementCheckRecord(
            production_entitlement_check_id=str(uuid4()),
            production_entitlement_check_status=production_entitlement_check_status,
            reason=reason,
            production_entitlement_check_class_id=(
                class_definition.production_entitlement_check_class_id
            ),
            production_entitlement_check_template_id=(
                template.production_entitlement_check_template_id
            ),
            production_entitlement_check_outcome=production_entitlement_check_outcome,
            production_entitlement_judgment=self._field_value_or_placeholder(
                field_name="production_entitlement_judgment",
                snapshot=required_production_entitlement_check_snapshot,
                context=combined_context,
            ),
            production_entitlement_evidence_reference=(
                self._field_value_or_placeholder(
                    field_name="production_entitlement_evidence_reference",
                    snapshot=required_production_entitlement_check_snapshot,
                    context=combined_context,
                )
            ),
            production_entitlement_authority_reference=(
                self._field_value_or_placeholder(
                    field_name="production_entitlement_authority_reference",
                    snapshot=required_production_entitlement_check_snapshot,
                    context=combined_context,
                )
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
            production_entitlement_check_author_role=(
                request.production_entitlement_check_author_role
            ),
            production_entitlement_check_author_id=request.actor_id,
            required_production_entitlement_check_fields=(
                template.required_production_entitlement_check_fields
            ),
            optional_production_entitlement_check_fields=(
                template.optional_production_entitlement_check_fields
            ),
            required_audit_fields=template.required_audit_fields,
            prohibited_production_entitlement_fields=(
                class_definition.prohibited_production_entitlement_fields
            ),
            required_production_entitlement_check_snapshot=(
                required_production_entitlement_check_snapshot
            ),
            optional_production_entitlement_check_snapshot=(
                optional_production_entitlement_check_snapshot
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
            production_entitlement_prerequisite_reference=combined_context.get(
                "production_entitlement_prerequisite_reference"
            ),
            outstanding_production_entitlement_prerequisites=(
                combined_context["outstanding_production_entitlement_prerequisites"]
            ),
            missing_production_entitlement_check_fields=all_missing_fields,
            prohibited_production_entitlement_fields_present=(
                prohibited_production_entitlement_fields_present
            ),
        )
        self._production_entitlement_check_audit_adapter.record_production_entitlement_check(
            record,
            request=request,
        )
        return record

    def _combined_context(
        self,
        request: ProductionEntitlementCheckRequest,
        class_definition,
    ) -> dict[str, object]:
        upstream = request.release_confirmation
        context = dict(upstream.required_release_confirmation_snapshot)
        context.update(upstream.optional_release_confirmation_snapshot)
        context.update(upstream.required_audit_snapshot)
        context.update(dict(request.production_entitlement_check_context))
        context.update(
            {
                "production_entitlement_check_class_id": (
                    class_definition.production_entitlement_check_class_id
                ),
                "production_entitlement_check_author_id": request.actor_id,
                "production_entitlement_check_author_role": (
                    request.production_entitlement_check_author_role
                ),
                "release_confirmation_id": upstream.release_confirmation_id,
                "release_confirmation_status": upstream.release_confirmation_status,
                "release_confirmation_class_id": (
                    upstream.release_confirmation_class_id
                ),
                "release_confirmation_template_id": (
                    upstream.release_confirmation_template_id
                ),
                "release_confirmation_outcome": upstream.release_confirmation_outcome,
                "release_confirmation_judgment": upstream.release_confirmation_judgment,
                "release_confirmation_threshold_evidence_reference": (
                    upstream.release_confirmation_threshold_evidence_reference
                ),
                "release_confirmation_authority_reference": (
                    upstream.release_confirmation_authority_reference
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
                "production_entitlement_judgment": self._optional_text(
                    context.get("production_entitlement_judgment")
                ),
                "production_entitlement_evidence_reference": self._optional_text(
                    context.get("production_entitlement_evidence_reference")
                ),
                "production_entitlement_authority_reference": self._optional_text(
                    context.get("production_entitlement_authority_reference")
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
                "production_entitlement_prerequisite_reference": self._optional_text(
                    context.get("production_entitlement_prerequisite_reference")
                ),
                "outstanding_production_entitlement_prerequisites": (
                    self._sequence_as_tuple(
                        context.get(
                            "outstanding_production_entitlement_prerequisites"
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

    def _prohibited_production_entitlement_fields_present(
        self,
        prohibited_fields: tuple[str, ...],
        context: Mapping[str, object],
    ) -> tuple[str, ...]:
        return tuple(
            field_name
            for field_name in prohibited_fields
            if not self._is_missing_value(context.get(field_name))
        )

    def _production_entitlement_check_status(
        self,
        *,
        release_confirmation: ReleaseConfirmationRecord,
        class_definition,
        combined_context: Mapping[str, object],
        missing_production_entitlement_check_fields: tuple[str, ...],
        prohibited_production_entitlement_fields_present: tuple[str, ...],
        fallback_template_used: bool,
    ) -> str:
        if prohibited_production_entitlement_fields_present:
            return "prohibited_overlap_blocked"
        if missing_production_entitlement_check_fields:
            return "blocked_missing_context"
        if (
            release_confirmation.release_confirmation_status
            not in class_definition.allowed_release_confirmation_statuses
        ):
            return "rejected_for_production_entitlement_use"
        if (
            release_confirmation.release_confirmation_outcome
            not in class_definition.allowed_release_confirmation_outcomes
        ):
            return "rejected_for_production_entitlement_use"
        if self._has_production_entitlement_restrictions(
            combined_context
        ) and not class_definition.allow_production_entitlement_restrictions:
            return "rejected_for_production_entitlement_use"
        if self._has_production_entitlement_prerequisite_deferral(
            combined_context
        ) and not class_definition.allow_production_entitlement_prerequisite_deferral:
            return "rejected_for_production_entitlement_use"
        return (
            "fallback_template_applied"
            if fallback_template_used
            else "production_entitlement_checked"
        )

    def _production_entitlement_check_outcome(
        self,
        *,
        template,
        production_entitlement_check_status: str,
    ) -> str:
        if production_entitlement_check_status in {
            "blocked_missing_context",
            "rejected_for_production_entitlement_use",
            "prohibited_overlap_blocked",
        }:
            return production_entitlement_check_status
        return template.production_entitlement_check_outcome

    def _reason(
        self,
        *,
        release_confirmation: ReleaseConfirmationRecord,
        production_entitlement_check_status: str,
        production_entitlement_check_class_id: str,
        missing_production_entitlement_check_fields: tuple[str, ...],
        prohibited_production_entitlement_fields_present: tuple[str, ...],
        class_definition,
        combined_context: Mapping[str, object],
        production_entitlement_check_outcome: str,
    ) -> str:
        if production_entitlement_check_status == "blocked_missing_context":
            return (
                "Production-entitlement check is blocked because governed "
                "entitlement context is missing required fields: "
                + ", ".join(missing_production_entitlement_check_fields)
                + "."
            )
        if production_entitlement_check_status == "prohibited_overlap_blocked":
            return (
                "Production-entitlement check is blocked because context overlaps "
                "contained rollback, rollback execution, release closure, runtime "
                "verification, monitoring admission, reopen, or orchestration fields: "
                + ", ".join(prohibited_production_entitlement_fields_present)
                + "."
            )
        if production_entitlement_check_status == (
            "rejected_for_production_entitlement_use"
        ):
            if (
                release_confirmation.release_confirmation_status
                not in class_definition.allowed_release_confirmation_statuses
            ):
                return (
                    "Production-entitlement check rejects release-confirmation "
                    "status '"
                    f"{release_confirmation.release_confirmation_status}' for "
                    f"class '{production_entitlement_check_class_id}'."
                )
            if (
                release_confirmation.release_confirmation_outcome
                not in class_definition.allowed_release_confirmation_outcomes
            ):
                return (
                    "Production-entitlement check rejects release-confirmation "
                    "outcome '"
                    f"{release_confirmation.release_confirmation_outcome}' for "
                    f"class '{production_entitlement_check_class_id}'."
                )
            if self._has_production_entitlement_restrictions(
                combined_context
            ) and not class_definition.allow_production_entitlement_restrictions:
                return (
                    "Production-entitlement check rejects restricted production "
                    f"entitlement for class '{production_entitlement_check_class_id}'."
                )
            if self._has_production_entitlement_prerequisite_deferral(
                combined_context
            ) and not class_definition.allow_production_entitlement_prerequisite_deferral:
                return (
                    "Production-entitlement check rejects deferred entitlement "
                    f"evidence for class '{production_entitlement_check_class_id}'."
                )
        if (
            production_entitlement_check_outcome
            == "approved_for_broader_trusted_production_entitlement"
        ):
            return (
                "Production entitlement evidence and authority approve crossing "
                "from bounded exposure into broader trusted production entitlement."
            )
        if (
            production_entitlement_check_outcome
            == "conditionally_approved_for_bounded_production_entitlement"
        ):
            return (
                "Production entitlement remains conditional and bounded; broader "
                "trusted production entitlement is not silently granted."
            )
        return (
            "Production entitlement is deferred until explicit entitlement evidence "
            "and authority prerequisites are complete."
        )

    def _lineage(
        self,
        request: ProductionEntitlementCheckRequest,
        class_definition,
        template,
    ) -> dict[str, str]:
        lineage = dict(request.release_confirmation.lineage)
        lineage.update(
            {
                "release_confirmation_id": (
                    request.release_confirmation.release_confirmation_id
                ),
                "production_entitlement_check_class_id": (
                    class_definition.production_entitlement_check_class_id
                ),
                "production_entitlement_check_template_id": (
                    template.production_entitlement_check_template_id
                ),
            }
        )
        return lineage

    def _has_production_entitlement_restrictions(
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

    def _has_production_entitlement_prerequisite_deferral(
        self,
        context: Mapping[str, object],
    ) -> bool:
        return any(
            not self._is_missing_value(context.get(field_name))
            for field_name in (
                "production_entitlement_prerequisite_reference",
                "outstanding_production_entitlement_prerequisites",
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