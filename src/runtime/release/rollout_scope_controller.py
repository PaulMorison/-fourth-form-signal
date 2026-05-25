from __future__ import annotations

"""Governed runtime release rollout-scope control.

Canon ownership:
- Consumes a governed promotion-readiness record and explicit rollout-scope
  context to decide whether explicit rollout and exposure boundaries are
  satisfied, satisfied only conditionally, deferred, blocked for missing
  context, rejected for rollout-scope use, or blocked for prohibited overlap.
- Does not own rollback-trigger control, post-release watch execution,
  monitoring, reopen handling, orchestration meaning, or lifecycle state
  meaning.
"""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Mapping
from uuid import uuid4

from runtime.release.promotion_readiness_gate import PromotionReadinessRecord
from runtime.release.release_registry import ReleaseRegistry
from runtime.release.rollout_scope_audit_adapter import RolloutScopeAuditAdapter

_REQUIRED_COLLECTION_FIELDS = {
    "required_rollout_scope_fields",
    "optional_rollout_scope_fields",
    "required_audit_fields",
    "prohibited_rollout_scope_fields",
    "required_rollout_scope_snapshot",
    "optional_rollout_scope_snapshot",
    "required_audit_snapshot",
    "lineage",
    "outstanding_rollout_scope_prerequisites",
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
class RolloutScopeControllerRequest:
    promotion_readiness: PromotionReadinessRecord
    rollout_scope_class_id: str
    rollout_scope_author_role: str
    rollout_scope_context: Mapping[str, object]
    correlation_id: str
    actor_id: str


@dataclass(frozen=True)
class RolloutScopeRecord:
    rollout_scope_id: str
    rollout_scope_status: str
    reason: str
    rollout_scope_class_id: str
    rollout_scope_template_id: str
    rollout_scope_outcome: str
    rollout_scope_boundary_reference: str
    exposure_boundary_reference: str
    rollout_boundary_summary: str
    promotion_candidate_reference: str
    promotion_threshold_reference: str
    production_entitlement_boundary: str
    rollback_posture_reference: str
    release_watch_window: str
    release_confirmation_threshold_reference: str
    promotion_scope_reference: str
    promotion_boundary_summary: str
    promotion_readiness_id: str
    promotion_readiness_status: str
    promotion_readiness_class_id: str
    promotion_readiness_template_id: str
    promotion_readiness_outcome: str
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
    rollout_scope_author_role: str
    rollout_scope_author_id: str
    required_rollout_scope_fields: tuple[str, ...]
    optional_rollout_scope_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    prohibited_rollout_scope_fields: tuple[str, ...]
    required_rollout_scope_snapshot: Mapping[str, str]
    optional_rollout_scope_snapshot: Mapping[str, str]
    required_audit_snapshot: Mapping[str, str]
    lineage: Mapping[str, str]
    generated_at: datetime
    reporting_scope_reference: str | None = None
    restriction_summary: str | None = None
    promotion_scope_restriction_reference: str | None = None
    follow_up_review_reference: str | None = None
    rollout_scope_prerequisite_reference: str | None = None
    outstanding_rollout_scope_prerequisites: tuple[str, ...] = ()
    missing_rollout_scope_fields: tuple[str, ...] = ()
    prohibited_rollout_scope_fields_present: tuple[str, ...] = ()

    def to_contract_dict(self) -> dict[str, object]:
        return _serialize_payload(asdict(self))

    def to_transport_context(self) -> dict[str, object]:
        context: dict[str, object] = {
            "rollout_scope_outcome": self.rollout_scope_outcome,
            "rollout_scope_boundary_reference": self.rollout_scope_boundary_reference,
            "exposure_boundary_reference": self.exposure_boundary_reference,
            "production_entitlement_boundary": self.production_entitlement_boundary,
        }
        if self.restriction_summary is not None:
            context["restriction_summary"] = self.restriction_summary
        if self.promotion_scope_restriction_reference is not None:
            context["promotion_scope_restriction_reference"] = (
                self.promotion_scope_restriction_reference
            )
        if self.follow_up_review_reference is not None:
            context["follow_up_review_reference"] = self.follow_up_review_reference
        if self.rollout_scope_prerequisite_reference is not None:
            context["rollout_scope_prerequisite_reference"] = (
                self.rollout_scope_prerequisite_reference
            )
        if self.outstanding_rollout_scope_prerequisites:
            context["outstanding_rollout_scope_prerequisites"] = list(
                self.outstanding_rollout_scope_prerequisites
            )
        return context


class RolloutScopeController:
    """Builds rollout-scope records from promotion-readiness records."""

    def __init__(
        self,
        *,
        release_registry: ReleaseRegistry,
        rollout_scope_audit_adapter: RolloutScopeAuditAdapter,
    ) -> None:
        self._release_registry = release_registry
        self._rollout_scope_audit_adapter = rollout_scope_audit_adapter

    def generate(self, request: RolloutScopeControllerRequest) -> RolloutScopeRecord:
        template, fallback_template_used = (
            self._release_registry.resolve_rollout_scope_template(
                semantic_scope=request.promotion_readiness.semantic_scope,
                promotion_readiness_class_id=(
                    request.promotion_readiness.promotion_readiness_class_id
                ),
                rollout_scope_class_id=request.rollout_scope_class_id,
                route_name=request.promotion_readiness.lineage.get("route_name"),
            )
        )
        class_definition = self._release_registry.get_rollout_scope_class(
            request.rollout_scope_class_id
        )
        combined_context = self._combined_context(request, class_definition)
        required_rollout_scope_snapshot, missing_rollout_scope_fields = (
            self._snapshot_required_fields(
                template.required_rollout_scope_fields,
                combined_context,
            )
        )
        required_audit_snapshot, missing_audit_fields = self._snapshot_required_fields(
            template.required_audit_fields,
            combined_context,
        )
        all_missing_fields = tuple(
            dict.fromkeys(missing_rollout_scope_fields + missing_audit_fields)
        )
        optional_rollout_scope_snapshot = self._snapshot_optional_fields(
            template.optional_rollout_scope_fields,
            combined_context,
        )
        prohibited_rollout_scope_fields_present = (
            self._prohibited_rollout_scope_fields_present(
                class_definition.prohibited_rollout_scope_fields,
                request.rollout_scope_context,
            )
        )
        rollout_scope_status = self._rollout_scope_status(
            promotion_readiness=request.promotion_readiness,
            class_definition=class_definition,
            combined_context=combined_context,
            missing_rollout_scope_fields=all_missing_fields,
            prohibited_rollout_scope_fields_present=(
                prohibited_rollout_scope_fields_present
            ),
            fallback_template_used=fallback_template_used,
        )
        rollout_scope_outcome = self._rollout_scope_outcome(
            template=template,
            rollout_scope_status=rollout_scope_status,
        )
        reason = self._reason(
            promotion_readiness=request.promotion_readiness,
            rollout_scope_status=rollout_scope_status,
            rollout_scope_class_id=class_definition.rollout_scope_class_id,
            missing_rollout_scope_fields=all_missing_fields,
            prohibited_rollout_scope_fields_present=(
                prohibited_rollout_scope_fields_present
            ),
            class_definition=class_definition,
            combined_context=combined_context,
            rollout_scope_outcome=rollout_scope_outcome,
        )
        lineage = self._lineage(request, class_definition, template)

        upstream = request.promotion_readiness
        record = RolloutScopeRecord(
            rollout_scope_id=str(uuid4()),
            rollout_scope_status=rollout_scope_status,
            reason=reason,
            rollout_scope_class_id=class_definition.rollout_scope_class_id,
            rollout_scope_template_id=template.rollout_scope_template_id,
            rollout_scope_outcome=rollout_scope_outcome,
            rollout_scope_boundary_reference=self._field_value_or_placeholder(
                field_name="rollout_scope_boundary_reference",
                snapshot=required_rollout_scope_snapshot,
                context=combined_context,
            ),
            exposure_boundary_reference=self._field_value_or_placeholder(
                field_name="exposure_boundary_reference",
                snapshot=required_rollout_scope_snapshot,
                context=combined_context,
            ),
            rollout_boundary_summary=self._field_value_or_placeholder(
                field_name="rollout_boundary_summary",
                snapshot=required_rollout_scope_snapshot,
                context=combined_context,
            ),
            promotion_candidate_reference=self._field_value_or_placeholder(
                field_name="promotion_candidate_reference",
                snapshot=required_rollout_scope_snapshot,
                context=combined_context,
            ),
            promotion_threshold_reference=self._field_value_or_placeholder(
                field_name="promotion_threshold_reference",
                snapshot=required_rollout_scope_snapshot,
                context=combined_context,
            ),
            production_entitlement_boundary=self._field_value_or_placeholder(
                field_name="production_entitlement_boundary",
                snapshot=required_rollout_scope_snapshot,
                context=combined_context,
            ),
            rollback_posture_reference=self._field_value_or_placeholder(
                field_name="rollback_posture_reference",
                snapshot=required_rollout_scope_snapshot,
                context=combined_context,
            ),
            release_watch_window=self._field_value_or_placeholder(
                field_name="release_watch_window",
                snapshot=required_rollout_scope_snapshot,
                context=combined_context,
            ),
            release_confirmation_threshold_reference=(
                self._field_value_or_placeholder(
                    field_name="release_confirmation_threshold_reference",
                    snapshot=required_rollout_scope_snapshot,
                    context=combined_context,
                )
            ),
            promotion_scope_reference=self._field_value_or_placeholder(
                field_name="promotion_scope_reference",
                snapshot=required_rollout_scope_snapshot,
                context=combined_context,
            ),
            promotion_boundary_summary=self._field_value_or_placeholder(
                field_name="promotion_boundary_summary",
                snapshot=required_rollout_scope_snapshot,
                context=combined_context,
            ),
            promotion_readiness_id=upstream.promotion_readiness_id,
            promotion_readiness_status=upstream.promotion_readiness_status,
            promotion_readiness_class_id=upstream.promotion_readiness_class_id,
            promotion_readiness_template_id=upstream.promotion_readiness_template_id,
            promotion_readiness_outcome=upstream.promotion_readiness_outcome,
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
            rollout_scope_author_role=request.rollout_scope_author_role,
            rollout_scope_author_id=request.actor_id,
            required_rollout_scope_fields=template.required_rollout_scope_fields,
            optional_rollout_scope_fields=template.optional_rollout_scope_fields,
            required_audit_fields=template.required_audit_fields,
            prohibited_rollout_scope_fields=(
                class_definition.prohibited_rollout_scope_fields
            ),
            required_rollout_scope_snapshot=required_rollout_scope_snapshot,
            optional_rollout_scope_snapshot=optional_rollout_scope_snapshot,
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
            rollout_scope_prerequisite_reference=combined_context.get(
                "rollout_scope_prerequisite_reference"
            ),
            outstanding_rollout_scope_prerequisites=(
                combined_context["outstanding_rollout_scope_prerequisites"]
            ),
            missing_rollout_scope_fields=all_missing_fields,
            prohibited_rollout_scope_fields_present=(
                prohibited_rollout_scope_fields_present
            ),
        )
        self._rollout_scope_audit_adapter.record_rollout_scope(
            record,
            request=request,
        )
        return record

    def _combined_context(self, request: RolloutScopeControllerRequest, class_definition) -> dict[str, object]:
        context = dict(request.promotion_readiness.required_promotion_readiness_snapshot)
        context.update(request.promotion_readiness.optional_promotion_readiness_snapshot)
        context.update(request.promotion_readiness.required_audit_snapshot)
        context.update(dict(request.rollout_scope_context))
        upstream = request.promotion_readiness
        context.update(
            {
                "rollout_scope_class_id": class_definition.rollout_scope_class_id,
                "rollout_scope_author_id": request.actor_id,
                "rollout_scope_author_role": request.rollout_scope_author_role,
                "promotion_readiness_id": upstream.promotion_readiness_id,
                "promotion_readiness_status": upstream.promotion_readiness_status,
                "promotion_readiness_class_id": upstream.promotion_readiness_class_id,
                "promotion_readiness_template_id": (
                    upstream.promotion_readiness_template_id
                ),
                "promotion_readiness_outcome": upstream.promotion_readiness_outcome,
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
                "rollout_scope_prerequisite_reference": self._optional_text(
                    context.get("rollout_scope_prerequisite_reference")
                ),
                "outstanding_rollout_scope_prerequisites": self._sequence_as_tuple(
                    context.get("outstanding_rollout_scope_prerequisites")
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

    def _prohibited_rollout_scope_fields_present(
        self,
        prohibited_fields: tuple[str, ...],
        context: Mapping[str, object],
    ) -> tuple[str, ...]:
        return tuple(
            field_name
            for field_name in prohibited_fields
            if not self._is_missing_value(context.get(field_name))
        )

    def _rollout_scope_status(
        self,
        *,
        promotion_readiness: PromotionReadinessRecord,
        class_definition,
        combined_context: Mapping[str, object],
        missing_rollout_scope_fields: tuple[str, ...],
        prohibited_rollout_scope_fields_present: tuple[str, ...],
        fallback_template_used: bool,
    ) -> str:
        if prohibited_rollout_scope_fields_present:
            return "prohibited_overlap_blocked"
        if missing_rollout_scope_fields:
            return "blocked_missing_context"
        if (
            promotion_readiness.promotion_readiness_status
            not in class_definition.allowed_promotion_readiness_statuses
        ):
            return "rejected_for_rollout_scope_use"
        if (
            promotion_readiness.promotion_readiness_outcome
            not in class_definition.allowed_promotion_readiness_outcomes
        ):
            return "rejected_for_rollout_scope_use"
        if self._has_rollout_scope_restrictions(combined_context) and not (
            class_definition.allow_rollout_scope_restrictions
        ):
            return "rejected_for_rollout_scope_use"
        if self._has_rollout_scope_prerequisite_deferral(combined_context) and not (
            class_definition.allow_rollout_scope_prerequisite_deferral
        ):
            return "rejected_for_rollout_scope_use"
        return (
            "fallback_template_applied"
            if fallback_template_used
            else "rollout_scope_defined"
        )

    def _rollout_scope_outcome(self, *, template, rollout_scope_status: str) -> str:
        if rollout_scope_status in {
            "blocked_missing_context",
            "rejected_for_rollout_scope_use",
            "prohibited_overlap_blocked",
        }:
            return rollout_scope_status
        return template.rollout_scope_outcome

    def _reason(
        self,
        *,
        promotion_readiness: PromotionReadinessRecord,
        rollout_scope_status: str,
        rollout_scope_class_id: str,
        missing_rollout_scope_fields: tuple[str, ...],
        prohibited_rollout_scope_fields_present: tuple[str, ...],
        class_definition,
        combined_context: Mapping[str, object],
        rollout_scope_outcome: str,
    ) -> str:
        if rollout_scope_status == "blocked_missing_context":
            return (
                "Rollout-scope control is blocked because governed rollout context is "
                "missing required fields: "
                + ", ".join(missing_rollout_scope_fields)
                + "."
            )
        if rollout_scope_status == "prohibited_overlap_blocked":
            return (
                "Rollout-scope control is blocked because context overlaps rollback, "
                "post-release watch execution, monitoring, reopen, or orchestration "
                "fields: "
                + ", ".join(prohibited_rollout_scope_fields_present)
                + "."
            )
        if rollout_scope_status == "rejected_for_rollout_scope_use":
            if (
                promotion_readiness.promotion_readiness_status
                not in class_definition.allowed_promotion_readiness_statuses
            ):
                return (
                    "Rollout-scope control rejects promotion-readiness status '"
                    f"{promotion_readiness.promotion_readiness_status}' for class '"
                    f"{rollout_scope_class_id}'."
                )
            if (
                promotion_readiness.promotion_readiness_outcome
                not in class_definition.allowed_promotion_readiness_outcomes
            ):
                return (
                    "Rollout-scope control rejects promotion-readiness outcome '"
                    f"{promotion_readiness.promotion_readiness_outcome}' for class '"
                    f"{rollout_scope_class_id}'."
                )
            if self._has_rollout_scope_restrictions(combined_context) and not (
                class_definition.allow_rollout_scope_restrictions
            ):
                return (
                    "Rollout-scope control rejects restricted production exposure for "
                    f"class '{rollout_scope_class_id}'."
                )
            if self._has_rollout_scope_prerequisite_deferral(combined_context) and not (
                class_definition.allow_rollout_scope_prerequisite_deferral
            ):
                return (
                    "Rollout-scope control rejects deferred rollout-scope evidence for "
                    f"class '{rollout_scope_class_id}'."
                )
        if rollout_scope_outcome == "ready_for_rollback_trigger_guard":
            return (
                "Governed rollout scope is explicit and the promoted release is ready "
                "for downstream rollback-trigger guard."
            )
        if rollout_scope_outcome == "conditionally_ready_for_rollback_trigger_guard":
            return (
                "Governed rollout scope is explicit only conditionally and must "
                "preserve bounded production exposure before downstream rollback-trigger guard."
            )
        return (
            "Governed rollout scope is deferred until explicit rollout boundary evidence "
            "and re-gate prerequisites are completed."
        )

    def _lineage(self, request: RolloutScopeControllerRequest, class_definition, template) -> dict[str, str]:
        lineage = dict(request.promotion_readiness.lineage)
        lineage.update(
            {
                "promotion_readiness_id": request.promotion_readiness.promotion_readiness_id,
                "rollout_scope_class_id": class_definition.rollout_scope_class_id,
                "rollout_scope_template_id": template.rollout_scope_template_id,
            }
        )
        return lineage

    def _has_rollout_scope_restrictions(self, context: Mapping[str, object]) -> bool:
        return any(
            not self._is_missing_value(context.get(field_name))
            for field_name in (
                "restriction_summary",
                "promotion_scope_restriction_reference",
            )
        )

    def _has_rollout_scope_prerequisite_deferral(
        self,
        context: Mapping[str, object],
    ) -> bool:
        return any(
            not self._is_missing_value(context.get(field_name))
            for field_name in (
                "rollout_scope_prerequisite_reference",
                "outstanding_rollout_scope_prerequisites",
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
            return tuple(self._to_text(item) for item in value if not self._is_missing_value(item))
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