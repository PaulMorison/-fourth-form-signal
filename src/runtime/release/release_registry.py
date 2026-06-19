from __future__ import annotations

"""Registry-backed release candidate classes and release-control templates.

Canon ownership:
- Owns governed promotion-readiness class identity and template identity for the
    narrow release gate that sits downstream of a non-blocked policy-learning
    update-mutation-execution record.
- Owns governed rollout-scope class identity and template identity for the
    explicit rollout and exposure-control layer that sits downstream of a
    non-blocked promotion-readiness record.
- Owns governed rollback-trigger class identity and template identity for the
    explicit rollback-trigger guard that sits downstream of a non-blocked
    rollout-scope record.
- Owns governed release-watch-discipline class identity and template identity
    for the explicit post-release watch discipline layer that sits downstream of
    a non-blocked rollback-trigger record.
- Owns governed release-confirmation class identity and template identity for
    the explicit confirmation-judgment layer that sits downstream of a
    non-blocked release-watch-discipline record.
- Owns governed production-entitlement-check class identity and template
    identity for the explicit entitlement review that sits downstream of a
    non-blocked release-confirmation record.
- Owns governed contained-rollback class identity and template identity for the
    explicit bounded rollback state that sits downstream of a non-blocked
    production-entitlement-check record.
- Owns governed release-audit-trace class identity and template identity for
    the explicit release-control lineage trace that sits downstream of a
    non-blocked contained-rollback record.
- Does not redefine mutation execution, post-release watch execution, release
    confirmation judgment, rollback execution, release
    closure, runtime verification, monitoring admission, reopen handling,
    orchestration ownership, or lifecycle meaning.
"""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping, Protocol

from ff_platform.validation.contract_schema_validator import ContractSchemaValidator

_REGISTRY_VALIDATION_CORRELATION_ID = "00000000-0000-0000-0000-000000000000"
_VALID_STATUS = {"active", "deprecated"}
_VALID_UPDATE_MUTATION_EXECUTION_STATUSES = {
    "mutation_execution_ready",
    "fallback_template_applied",
}
_VALID_UPDATE_MUTATION_EXECUTION_OUTCOMES = {
    "ready_for_policy_mutation_execution",
    "ready_for_policy_mutation_execution_with_restrictions",
    "deferred_pending_mutation_execution_prerequisites",
    "blocked_missing_context",
    "rejected_for_mutation_execution_use",
    "prohibited_overlap_blocked",
}
_VALID_DIMENSION_STRENGTH = {"weak", "moderate", "strong"}
_VALID_PROMOTION_READINESS_STATUSES = {
    "promotion_ready",
    "fallback_template_applied",
}
_VALID_PROMOTION_READINESS_OUTCOMES = {
    "ready_for_rollout_scope_control",
    "conditionally_ready_for_rollout_scope_control",
    "deferred_pending_promotion_readiness_evidence",
}
_VALID_ROLLOUT_SCOPE_STATUSES = {
    "rollout_scope_defined",
    "fallback_template_applied",
}
_VALID_ROLLOUT_SCOPE_OUTCOMES = {
    "ready_for_rollback_trigger_guard",
    "conditionally_ready_for_rollback_trigger_guard",
    "deferred_pending_rollout_scope_evidence",
}
_VALID_ROLLBACK_TRIGGER_STATUSES = {
    "rollback_trigger_named",
    "fallback_template_applied",
}
_VALID_ROLLBACK_TRIGGER_OUTCOMES = {
    "ready_for_release_watch_discipline",
    "conditionally_ready_for_release_watch_discipline",
    "deferred_pending_rollback_trigger_evidence",
}
_VALID_RELEASE_WATCH_DISCIPLINE_STATUSES = {
    "release_watch_discipline_defined",
    "fallback_template_applied",
}
_VALID_RELEASE_WATCH_DISCIPLINE_OUTCOMES = {
    "ready_for_release_confirmation",
    "conditionally_ready_for_release_confirmation",
    "deferred_pending_release_watch_discipline_evidence",
}
_VALID_RELEASE_CONFIRMATION_STATUSES = {
    "release_confirmation_judged",
    "fallback_template_applied",
}
_VALID_RELEASE_CONFIRMATION_OUTCOMES = {
    "confirmed_for_broader_trusted_production_use",
    "conditionally_confirmed_for_bounded_production_use",
    "deferred_pending_release_confirmation_evidence",
}
_VALID_PRODUCTION_ENTITLEMENT_CHECK_STATUSES = {
    "production_entitlement_checked",
    "fallback_template_applied",
}
_VALID_PRODUCTION_ENTITLEMENT_CHECK_OUTCOMES = {
    "approved_for_broader_trusted_production_entitlement",
    "conditionally_approved_for_bounded_production_entitlement",
    "deferred_pending_production_entitlement_evidence",
}
_VALID_CONTAINED_ROLLBACK_STATUSES = {
    "contained_rollback_bounded",
    "fallback_template_applied",
}
_VALID_CONTAINED_ROLLBACK_OUTCOMES = {
    "bounded_exposure_preserved",
    "partial_reversal_bounded",
    "deferred_pending_contained_rollback_evidence",
}
_VALID_RELEASE_AUDIT_TRACE_STATUSES = {
    "release_audit_trace_recorded",
    "fallback_template_applied",
}
_VALID_RELEASE_AUDIT_TRACE_OUTCOMES = {
    "release_control_lineage_preserved",
    "invalid_exposure_visibility_preserved",
    "deferred_pending_release_audit_trace_evidence",
}


class ReleaseRegistryError(ValueError):
    """Base error for release-registry failures."""


@dataclass(frozen=True)
class PromotionReadinessClassDefinition:
    promotion_readiness_class_id: str
    description: str
    allowed_policy_learning_update_mutation_execution_statuses: tuple[str, ...]
    allowed_policy_learning_update_mutation_execution_outcomes: tuple[str, ...]
    minimum_dimension_strength: str
    allow_promotion_restrictions: bool
    allow_promotion_prerequisite_deferral: bool
    prohibited_promotion_readiness_fields: tuple[str, ...]
    status: str
    lineage: Mapping[str, str]


@dataclass(frozen=True)
class PromotionReadinessTemplateDefinition:
    promotion_readiness_template_id: str
    semantic_scope: str
    policy_learning_update_mutation_execution_class_id: str
    promotion_readiness_class_id: str
    required_promotion_readiness_fields: tuple[str, ...]
    optional_promotion_readiness_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    promotion_readiness_status: str
    promotion_readiness_outcome: str
    status: str
    lineage: Mapping[str, str]
    route_name: str | None = None


@dataclass(frozen=True)
class RolloutScopeClassDefinition:
    rollout_scope_class_id: str
    description: str
    allowed_promotion_readiness_statuses: tuple[str, ...]
    allowed_promotion_readiness_outcomes: tuple[str, ...]
    allow_rollout_scope_restrictions: bool
    allow_rollout_scope_prerequisite_deferral: bool
    prohibited_rollout_scope_fields: tuple[str, ...]
    status: str
    lineage: Mapping[str, str]


@dataclass(frozen=True)
class RolloutScopeTemplateDefinition:
    rollout_scope_template_id: str
    semantic_scope: str
    promotion_readiness_class_id: str
    rollout_scope_class_id: str
    required_rollout_scope_fields: tuple[str, ...]
    optional_rollout_scope_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    rollout_scope_status: str
    rollout_scope_outcome: str
    status: str
    lineage: Mapping[str, str]
    route_name: str | None = None


@dataclass(frozen=True)
class RollbackTriggerClassDefinition:
    rollback_trigger_class_id: str
    description: str
    allowed_rollout_scope_statuses: tuple[str, ...]
    allowed_rollout_scope_outcomes: tuple[str, ...]
    allow_rollback_trigger_restrictions: bool
    allow_rollback_trigger_prerequisite_deferral: bool
    prohibited_rollback_trigger_fields: tuple[str, ...]
    status: str
    lineage: Mapping[str, str]


@dataclass(frozen=True)
class RollbackTriggerTemplateDefinition:
    rollback_trigger_template_id: str
    semantic_scope: str
    rollout_scope_class_id: str
    rollback_trigger_class_id: str
    required_rollback_trigger_fields: tuple[str, ...]
    optional_rollback_trigger_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    rollback_trigger_status: str
    rollback_trigger_outcome: str
    status: str
    lineage: Mapping[str, str]
    route_name: str | None = None


@dataclass(frozen=True)
class ReleaseWatchDisciplineClassDefinition:
    release_watch_discipline_class_id: str
    description: str
    allowed_rollback_trigger_statuses: tuple[str, ...]
    allowed_rollback_trigger_outcomes: tuple[str, ...]
    allow_release_watch_discipline_restrictions: bool
    allow_release_watch_discipline_prerequisite_deferral: bool
    prohibited_release_watch_discipline_fields: tuple[str, ...]
    status: str
    lineage: Mapping[str, str]


@dataclass(frozen=True)
class ReleaseWatchDisciplineTemplateDefinition:
    release_watch_discipline_template_id: str
    semantic_scope: str
    rollback_trigger_class_id: str
    release_watch_discipline_class_id: str
    required_release_watch_discipline_fields: tuple[str, ...]
    optional_release_watch_discipline_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    release_watch_discipline_status: str
    release_watch_discipline_outcome: str
    status: str
    lineage: Mapping[str, str]
    route_name: str | None = None


@dataclass(frozen=True)
class ReleaseConfirmationClassDefinition:
    release_confirmation_class_id: str
    description: str
    allowed_release_watch_discipline_statuses: tuple[str, ...]
    allowed_release_watch_discipline_outcomes: tuple[str, ...]
    allow_release_confirmation_restrictions: bool
    allow_release_confirmation_prerequisite_deferral: bool
    prohibited_release_confirmation_fields: tuple[str, ...]
    status: str
    lineage: Mapping[str, str]


@dataclass(frozen=True)
class ReleaseConfirmationTemplateDefinition:
    release_confirmation_template_id: str
    semantic_scope: str
    release_watch_discipline_class_id: str
    release_confirmation_class_id: str
    required_release_confirmation_fields: tuple[str, ...]
    optional_release_confirmation_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    release_confirmation_status: str
    release_confirmation_outcome: str
    status: str
    lineage: Mapping[str, str]
    route_name: str | None = None


@dataclass(frozen=True)
class ProductionEntitlementCheckClassDefinition:
    production_entitlement_check_class_id: str
    description: str
    allowed_release_confirmation_statuses: tuple[str, ...]
    allowed_release_confirmation_outcomes: tuple[str, ...]
    allow_production_entitlement_restrictions: bool
    allow_production_entitlement_prerequisite_deferral: bool
    prohibited_production_entitlement_fields: tuple[str, ...]
    status: str
    lineage: Mapping[str, str]


@dataclass(frozen=True)
class ProductionEntitlementCheckTemplateDefinition:
    production_entitlement_check_template_id: str
    semantic_scope: str
    release_confirmation_class_id: str
    production_entitlement_check_class_id: str
    required_production_entitlement_check_fields: tuple[str, ...]
    optional_production_entitlement_check_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    production_entitlement_check_status: str
    production_entitlement_check_outcome: str
    status: str
    lineage: Mapping[str, str]
    route_name: str | None = None


@dataclass(frozen=True)
class ContainedRollbackClassDefinition:
    contained_rollback_class_id: str
    description: str
    allowed_production_entitlement_check_statuses: tuple[str, ...]
    allowed_production_entitlement_check_outcomes: tuple[str, ...]
    allow_contained_rollback_restrictions: bool
    allow_contained_rollback_prerequisite_deferral: bool
    prohibited_contained_rollback_fields: tuple[str, ...]
    status: str
    lineage: Mapping[str, str]


@dataclass(frozen=True)
class ContainedRollbackTemplateDefinition:
    contained_rollback_template_id: str
    semantic_scope: str
    production_entitlement_check_class_id: str
    contained_rollback_class_id: str
    required_contained_rollback_fields: tuple[str, ...]
    optional_contained_rollback_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    contained_rollback_status: str
    contained_rollback_outcome: str
    status: str
    lineage: Mapping[str, str]
    route_name: str | None = None


@dataclass(frozen=True)
class ReleaseAuditTraceClassDefinition:
    release_audit_trace_class_id: str
    description: str
    allowed_contained_rollback_statuses: tuple[str, ...]
    allowed_contained_rollback_outcomes: tuple[str, ...]
    allow_release_audit_trace_restrictions: bool
    allow_release_audit_trace_prerequisite_deferral: bool
    prohibited_release_audit_trace_fields: tuple[str, ...]
    status: str
    lineage: Mapping[str, str]


@dataclass(frozen=True)
class ReleaseAuditTraceTemplateDefinition:
    release_audit_trace_template_id: str
    semantic_scope: str
    contained_rollback_class_id: str
    release_audit_trace_class_id: str
    required_release_audit_trace_fields: tuple[str, ...]
    optional_release_audit_trace_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    release_audit_trace_status: str
    release_audit_trace_outcome: str
    status: str
    lineage: Mapping[str, str]
    route_name: str | None = None


class ReleaseRegistry(Protocol):
    def resolve_template(
        self,
        *,
        semantic_scope: str,
        policy_learning_update_mutation_execution_class_id: str,
        promotion_readiness_class_id: str,
        route_name: str | None,
    ) -> tuple[PromotionReadinessTemplateDefinition, bool]:
        """Return the matching promotion-readiness template and fallback status."""

    def get_promotion_readiness_class(
        self,
        promotion_readiness_class_id: str,
    ) -> PromotionReadinessClassDefinition:
        """Return the named promotion-readiness class."""

    def resolve_rollout_scope_template(
        self,
        *,
        semantic_scope: str,
        promotion_readiness_class_id: str,
        rollout_scope_class_id: str,
        route_name: str | None,
    ) -> tuple[RolloutScopeTemplateDefinition, bool]:
        """Return the matching rollout-scope template and fallback status."""

    def get_rollout_scope_class(
        self,
        rollout_scope_class_id: str,
    ) -> RolloutScopeClassDefinition:
        """Return the named rollout-scope class."""

    def resolve_rollback_trigger_template(
        self,
        *,
        semantic_scope: str,
        rollout_scope_class_id: str,
        rollback_trigger_class_id: str,
        route_name: str | None,
    ) -> tuple[RollbackTriggerTemplateDefinition, bool]:
        """Return the matching rollback-trigger template and fallback status."""

    def get_rollback_trigger_class(
        self,
        rollback_trigger_class_id: str,
    ) -> RollbackTriggerClassDefinition:
        """Return the named rollback-trigger class."""

    def resolve_release_watch_discipline_template(
        self,
        *,
        semantic_scope: str,
        rollback_trigger_class_id: str,
        release_watch_discipline_class_id: str,
        route_name: str | None,
    ) -> tuple[ReleaseWatchDisciplineTemplateDefinition, bool]:
        """Return the matching release-watch-discipline template and fallback status."""

    def get_release_watch_discipline_class(
        self,
        release_watch_discipline_class_id: str,
    ) -> ReleaseWatchDisciplineClassDefinition:
        """Return the named release-watch-discipline class."""

    def resolve_release_confirmation_template(
        self,
        *,
        semantic_scope: str,
        release_watch_discipline_class_id: str,
        release_confirmation_class_id: str,
        route_name: str | None,
    ) -> tuple[ReleaseConfirmationTemplateDefinition, bool]:
        """Return the matching release-confirmation template and fallback status."""

    def get_release_confirmation_class(
        self,
        release_confirmation_class_id: str,
    ) -> ReleaseConfirmationClassDefinition:
        """Return the named release-confirmation class."""

    def resolve_production_entitlement_check_template(
        self,
        *,
        semantic_scope: str,
        release_confirmation_class_id: str,
        production_entitlement_check_class_id: str,
        route_name: str | None,
    ) -> tuple[ProductionEntitlementCheckTemplateDefinition, bool]:
        """Return the matching production-entitlement-check template and fallback status."""

    def get_production_entitlement_check_class(
        self,
        production_entitlement_check_class_id: str,
    ) -> ProductionEntitlementCheckClassDefinition:
        """Return the named production-entitlement-check class."""

    def resolve_contained_rollback_template(
        self,
        *,
        semantic_scope: str,
        production_entitlement_check_class_id: str,
        contained_rollback_class_id: str,
        route_name: str | None,
    ) -> tuple[ContainedRollbackTemplateDefinition, bool]:
        """Return the matching contained-rollback template and fallback status."""

    def get_contained_rollback_class(
        self,
        contained_rollback_class_id: str,
    ) -> ContainedRollbackClassDefinition:
        """Return the named contained-rollback class."""

    def resolve_release_audit_trace_template(
        self,
        *,
        semantic_scope: str,
        contained_rollback_class_id: str,
        release_audit_trace_class_id: str,
        route_name: str | None,
    ) -> tuple[ReleaseAuditTraceTemplateDefinition, bool]:
        """Return the matching release-audit-trace template and fallback status."""

    def get_release_audit_trace_class(
        self,
        release_audit_trace_class_id: str,
    ) -> ReleaseAuditTraceClassDefinition:
        """Return the named release-audit-trace class."""


class JsonReleaseRegistry:
    """Loads release classes and release-control templates."""

    def __init__(
        self,
        *,
        promotion_readiness_classes_path: Path,
        promotion_readiness_templates_path: Path,
        rollout_scope_classes_path: Path | None = None,
        rollout_scope_templates_path: Path | None = None,
        rollback_trigger_classes_path: Path | None = None,
        rollback_trigger_templates_path: Path | None = None,
        release_watch_discipline_classes_path: Path | None = None,
        release_watch_discipline_templates_path: Path | None = None,
        release_confirmation_classes_path: Path | None = None,
        release_confirmation_templates_path: Path | None = None,
        production_entitlement_check_classes_path: Path | None = None,
        production_entitlement_check_templates_path: Path | None = None,
        contained_rollback_classes_path: Path | None = None,
        contained_rollback_templates_path: Path | None = None,
        release_audit_trace_classes_path: Path | None = None,
        release_audit_trace_templates_path: Path | None = None,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._contract_validator = contract_validator
        self._promotion_readiness_classes = self._load_classes(
            promotion_readiness_classes_path
        )
        self._promotion_readiness_templates = self._load_templates(
            promotion_readiness_templates_path
        )
        if (rollout_scope_classes_path is None) != (
            rollout_scope_templates_path is None
        ):
            raise ReleaseRegistryError(
                "Rollout-scope registry paths must either both be provided or both be omitted."
            )
        if rollout_scope_classes_path is not None:
            self._rollout_scope_classes = self._load_rollout_scope_classes(
                rollout_scope_classes_path
            )
            self._rollout_scope_templates = self._load_rollout_scope_templates(
                rollout_scope_templates_path
            )
        else:
            self._rollout_scope_classes = {}
            self._rollout_scope_templates = ()
        if (rollback_trigger_classes_path is None) != (
            rollback_trigger_templates_path is None
        ):
            raise ReleaseRegistryError(
                "Rollback-trigger registry paths must either both be provided or both be omitted."
            )
        if rollback_trigger_classes_path is not None:
            if rollout_scope_classes_path is None or rollout_scope_templates_path is None:
                raise ReleaseRegistryError(
                    "Rollback-trigger registry paths require rollout-scope registry paths."
                )
            self._rollback_trigger_classes = self._load_rollback_trigger_classes(
                rollback_trigger_classes_path
            )
            self._rollback_trigger_templates = self._load_rollback_trigger_templates(
                rollback_trigger_templates_path
            )
        else:
            self._rollback_trigger_classes = {}
            self._rollback_trigger_templates = ()
        if (release_watch_discipline_classes_path is None) != (
            release_watch_discipline_templates_path is None
        ):
            raise ReleaseRegistryError(
                "Release-watch-discipline registry paths must either both be provided or both be omitted."
            )
        if release_watch_discipline_classes_path is not None:
            if (
                rollback_trigger_classes_path is None
                or rollback_trigger_templates_path is None
            ):
                raise ReleaseRegistryError(
                    "Release-watch-discipline registry paths require rollback-trigger registry paths."
                )
            self._release_watch_discipline_classes = (
                self._load_release_watch_discipline_classes(
                    release_watch_discipline_classes_path
                )
            )
            self._release_watch_discipline_templates = (
                self._load_release_watch_discipline_templates(
                    release_watch_discipline_templates_path
                )
            )
        else:
            self._release_watch_discipline_classes = {}
            self._release_watch_discipline_templates = ()
        if (release_confirmation_classes_path is None) != (
            release_confirmation_templates_path is None
        ):
            raise ReleaseRegistryError(
                "Release-confirmation registry paths must either both be provided or both be omitted."
            )
        if release_confirmation_classes_path is not None:
            if (
                release_watch_discipline_classes_path is None
                or release_watch_discipline_templates_path is None
            ):
                raise ReleaseRegistryError(
                    "Release-confirmation registry paths require release-watch-discipline registry paths."
                )
            self._release_confirmation_classes = (
                self._load_release_confirmation_classes(
                    release_confirmation_classes_path
                )
            )
            self._release_confirmation_templates = (
                self._load_release_confirmation_templates(
                    release_confirmation_templates_path
                )
            )
        else:
            self._release_confirmation_classes = {}
            self._release_confirmation_templates = ()
        if (production_entitlement_check_classes_path is None) != (
            production_entitlement_check_templates_path is None
        ):
            raise ReleaseRegistryError(
                "Production-entitlement-check registry paths must either both be provided or both be omitted."
            )
        if production_entitlement_check_classes_path is not None:
            if (
                release_confirmation_classes_path is None
                or release_confirmation_templates_path is None
            ):
                raise ReleaseRegistryError(
                    "Production-entitlement-check registry paths require release-confirmation registry paths."
                )
            self._production_entitlement_check_classes = (
                self._load_production_entitlement_check_classes(
                    production_entitlement_check_classes_path
                )
            )
            self._production_entitlement_check_templates = (
                self._load_production_entitlement_check_templates(
                    production_entitlement_check_templates_path
                )
            )
        else:
            self._production_entitlement_check_classes = {}
            self._production_entitlement_check_templates = ()
        if (contained_rollback_classes_path is None) != (
            contained_rollback_templates_path is None
        ):
            raise ReleaseRegistryError(
                "Contained-rollback registry paths must either both be provided or both be omitted."
            )
        if contained_rollback_classes_path is not None:
            if (
                production_entitlement_check_classes_path is None
                or production_entitlement_check_templates_path is None
            ):
                raise ReleaseRegistryError(
                    "Contained-rollback registry paths require production-entitlement-check registry paths."
                )
            self._contained_rollback_classes = (
                self._load_contained_rollback_classes(
                    contained_rollback_classes_path
                )
            )
            self._contained_rollback_templates = (
                self._load_contained_rollback_templates(
                    contained_rollback_templates_path
                )
            )
        else:
            self._contained_rollback_classes = {}
            self._contained_rollback_templates = ()
        if (release_audit_trace_classes_path is None) != (
            release_audit_trace_templates_path is None
        ):
            raise ReleaseRegistryError(
                "Release-audit-trace registry paths must either both be provided or both be omitted."
            )
        if release_audit_trace_classes_path is not None:
            if (
                contained_rollback_classes_path is None
                or contained_rollback_templates_path is None
            ):
                raise ReleaseRegistryError(
                    "Release-audit-trace registry paths require contained-rollback registry paths."
                )
            self._release_audit_trace_classes = (
                self._load_release_audit_trace_classes(
                    release_audit_trace_classes_path
                )
            )
            self._release_audit_trace_templates = (
                self._load_release_audit_trace_templates(
                    release_audit_trace_templates_path
                )
            )
        else:
            self._release_audit_trace_classes = {}
            self._release_audit_trace_templates = ()
        self._validate_cross_registry_links()

    def resolve_template(
        self,
        *,
        semantic_scope: str,
        policy_learning_update_mutation_execution_class_id: str,
        promotion_readiness_class_id: str,
        route_name: str | None,
    ) -> tuple[PromotionReadinessTemplateDefinition, bool]:
        exact_matches = tuple(
            template
            for template in self._promotion_readiness_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.policy_learning_update_mutation_execution_class_id
            == policy_learning_update_mutation_execution_class_id
            and template.promotion_readiness_class_id == promotion_readiness_class_id
            and template.route_name == route_name
        )
        if exact_matches:
            template = sorted(
                exact_matches,
                key=lambda item: item.promotion_readiness_template_id,
            )[0]
            return (
                template,
                template.promotion_readiness_status == "fallback_template_applied",
            )

        generic_matches = tuple(
            template
            for template in self._promotion_readiness_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.policy_learning_update_mutation_execution_class_id
            == policy_learning_update_mutation_execution_class_id
            and template.promotion_readiness_class_id == promotion_readiness_class_id
            and template.route_name is None
        )
        if generic_matches:
            template = sorted(
                generic_matches,
                key=lambda item: item.promotion_readiness_template_id,
            )[0]
            return (
                template,
                template.promotion_readiness_status == "fallback_template_applied",
            )

        raise ReleaseRegistryError(
            "No governed promotion-readiness template applies to "
            f"promotion_readiness_class_id='{promotion_readiness_class_id}' for "
            "policy_learning_update_mutation_execution_class_id='"
            f"{policy_learning_update_mutation_execution_class_id}' and route_name='"
            f"{route_name}'."
        )

    def get_promotion_readiness_class(
        self,
        promotion_readiness_class_id: str,
    ) -> PromotionReadinessClassDefinition:
        try:
            return self._promotion_readiness_classes[promotion_readiness_class_id]
        except KeyError as error:
            raise ReleaseRegistryError(
                "Promotion-readiness class "
                f"'{promotion_readiness_class_id}' is not registered."
            ) from error

    def resolve_rollout_scope_template(
        self,
        *,
        semantic_scope: str,
        promotion_readiness_class_id: str,
        rollout_scope_class_id: str,
        route_name: str | None,
    ) -> tuple[RolloutScopeTemplateDefinition, bool]:
        exact_matches = tuple(
            template
            for template in self._rollout_scope_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.promotion_readiness_class_id == promotion_readiness_class_id
            and template.rollout_scope_class_id == rollout_scope_class_id
            and template.route_name == route_name
        )
        if exact_matches:
            template = sorted(
                exact_matches,
                key=lambda item: item.rollout_scope_template_id,
            )[0]
            return (
                template,
                template.rollout_scope_status == "fallback_template_applied",
            )

        generic_matches = tuple(
            template
            for template in self._rollout_scope_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.promotion_readiness_class_id == promotion_readiness_class_id
            and template.rollout_scope_class_id == rollout_scope_class_id
            and template.route_name is None
        )
        if generic_matches:
            template = sorted(
                generic_matches,
                key=lambda item: item.rollout_scope_template_id,
            )[0]
            return (
                template,
                template.rollout_scope_status == "fallback_template_applied",
            )

        raise ReleaseRegistryError(
            "No governed rollout-scope template applies to "
            f"rollout_scope_class_id='{rollout_scope_class_id}' for "
            f"promotion_readiness_class_id='{promotion_readiness_class_id}' and "
            f"route_name='{route_name}'."
        )

    def get_rollout_scope_class(
        self,
        rollout_scope_class_id: str,
    ) -> RolloutScopeClassDefinition:
        try:
            return self._rollout_scope_classes[rollout_scope_class_id]
        except KeyError as error:
            raise ReleaseRegistryError(
                f"Rollout-scope class '{rollout_scope_class_id}' is not registered."
            ) from error

    def resolve_rollback_trigger_template(
        self,
        *,
        semantic_scope: str,
        rollout_scope_class_id: str,
        rollback_trigger_class_id: str,
        route_name: str | None,
    ) -> tuple[RollbackTriggerTemplateDefinition, bool]:
        exact_matches = tuple(
            template
            for template in self._rollback_trigger_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.rollout_scope_class_id == rollout_scope_class_id
            and template.rollback_trigger_class_id == rollback_trigger_class_id
            and template.route_name == route_name
        )
        if exact_matches:
            template = sorted(
                exact_matches,
                key=lambda item: item.rollback_trigger_template_id,
            )[0]
            return (
                template,
                template.rollback_trigger_status == "fallback_template_applied",
            )

        generic_matches = tuple(
            template
            for template in self._rollback_trigger_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.rollout_scope_class_id == rollout_scope_class_id
            and template.rollback_trigger_class_id == rollback_trigger_class_id
            and template.route_name is None
        )
        if generic_matches:
            template = sorted(
                generic_matches,
                key=lambda item: item.rollback_trigger_template_id,
            )[0]
            return (
                template,
                template.rollback_trigger_status == "fallback_template_applied",
            )

        raise ReleaseRegistryError(
            "No governed rollback-trigger template applies to "
            f"rollback_trigger_class_id='{rollback_trigger_class_id}' for "
            f"rollout_scope_class_id='{rollout_scope_class_id}' and "
            f"route_name='{route_name}'."
        )

    def get_rollback_trigger_class(
        self,
        rollback_trigger_class_id: str,
    ) -> RollbackTriggerClassDefinition:
        try:
            return self._rollback_trigger_classes[rollback_trigger_class_id]
        except KeyError as error:
            raise ReleaseRegistryError(
                "Rollback-trigger class "
                f"'{rollback_trigger_class_id}' is not registered."
            ) from error

    def resolve_release_watch_discipline_template(
        self,
        *,
        semantic_scope: str,
        rollback_trigger_class_id: str,
        release_watch_discipline_class_id: str,
        route_name: str | None,
    ) -> tuple[ReleaseWatchDisciplineTemplateDefinition, bool]:
        exact_matches = tuple(
            template
            for template in self._release_watch_discipline_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.rollback_trigger_class_id == rollback_trigger_class_id
            and template.release_watch_discipline_class_id
            == release_watch_discipline_class_id
            and template.route_name == route_name
        )
        if exact_matches:
            template = sorted(
                exact_matches,
                key=lambda item: item.release_watch_discipline_template_id,
            )[0]
            return (
                template,
                template.release_watch_discipline_status
                == "fallback_template_applied",
            )

        generic_matches = tuple(
            template
            for template in self._release_watch_discipline_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.rollback_trigger_class_id == rollback_trigger_class_id
            and template.release_watch_discipline_class_id
            == release_watch_discipline_class_id
            and template.route_name is None
        )
        if generic_matches:
            template = sorted(
                generic_matches,
                key=lambda item: item.release_watch_discipline_template_id,
            )[0]
            return (
                template,
                template.release_watch_discipline_status
                == "fallback_template_applied",
            )

        raise ReleaseRegistryError(
            "No governed release-watch-discipline template applies to "
            f"release_watch_discipline_class_id='{release_watch_discipline_class_id}' "
            f"for rollback_trigger_class_id='{rollback_trigger_class_id}' and "
            f"route_name='{route_name}'."
        )

    def get_release_watch_discipline_class(
        self,
        release_watch_discipline_class_id: str,
    ) -> ReleaseWatchDisciplineClassDefinition:
        try:
            return self._release_watch_discipline_classes[
                release_watch_discipline_class_id
            ]
        except KeyError as error:
            raise ReleaseRegistryError(
                "Release-watch-discipline class "
                f"'{release_watch_discipline_class_id}' is not registered."
            ) from error

    def resolve_release_confirmation_template(
        self,
        *,
        semantic_scope: str,
        release_watch_discipline_class_id: str,
        release_confirmation_class_id: str,
        route_name: str | None,
    ) -> tuple[ReleaseConfirmationTemplateDefinition, bool]:
        exact_matches = tuple(
            template
            for template in self._release_confirmation_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.release_watch_discipline_class_id
            == release_watch_discipline_class_id
            and template.release_confirmation_class_id == release_confirmation_class_id
            and template.route_name == route_name
        )
        if exact_matches:
            template = sorted(
                exact_matches,
                key=lambda item: item.release_confirmation_template_id,
            )[0]
            return (
                template,
                template.release_confirmation_status == "fallback_template_applied",
            )

        generic_matches = tuple(
            template
            for template in self._release_confirmation_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.release_watch_discipline_class_id
            == release_watch_discipline_class_id
            and template.release_confirmation_class_id == release_confirmation_class_id
            and template.route_name is None
        )
        if generic_matches:
            template = sorted(
                generic_matches,
                key=lambda item: item.release_confirmation_template_id,
            )[0]
            return (
                template,
                template.release_confirmation_status == "fallback_template_applied",
            )

        raise ReleaseRegistryError(
            "No governed release-confirmation template applies to "
            f"release_confirmation_class_id='{release_confirmation_class_id}' "
            "for release_watch_discipline_class_id='"
            f"{release_watch_discipline_class_id}' and route_name='{route_name}'."
        )

    def get_release_confirmation_class(
        self,
        release_confirmation_class_id: str,
    ) -> ReleaseConfirmationClassDefinition:
        try:
            return self._release_confirmation_classes[release_confirmation_class_id]
        except KeyError as error:
            raise ReleaseRegistryError(
                "Release-confirmation class "
                f"'{release_confirmation_class_id}' is not registered."
            ) from error

    def resolve_production_entitlement_check_template(
        self,
        *,
        semantic_scope: str,
        release_confirmation_class_id: str,
        production_entitlement_check_class_id: str,
        route_name: str | None,
    ) -> tuple[ProductionEntitlementCheckTemplateDefinition, bool]:
        exact_matches = tuple(
            template
            for template in self._production_entitlement_check_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.release_confirmation_class_id == release_confirmation_class_id
            and template.production_entitlement_check_class_id
            == production_entitlement_check_class_id
            and template.route_name == route_name
        )
        if exact_matches:
            template = sorted(
                exact_matches,
                key=lambda item: item.production_entitlement_check_template_id,
            )[0]
            return (
                template,
                template.production_entitlement_check_status
                == "fallback_template_applied",
            )

        generic_matches = tuple(
            template
            for template in self._production_entitlement_check_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.release_confirmation_class_id == release_confirmation_class_id
            and template.production_entitlement_check_class_id
            == production_entitlement_check_class_id
            and template.route_name is None
        )
        if generic_matches:
            template = sorted(
                generic_matches,
                key=lambda item: item.production_entitlement_check_template_id,
            )[0]
            return (
                template,
                template.production_entitlement_check_status
                == "fallback_template_applied",
            )

        raise ReleaseRegistryError(
            "No governed production-entitlement-check template applies to "
            "production_entitlement_check_class_id='"
            f"{production_entitlement_check_class_id}' for "
            f"release_confirmation_class_id='{release_confirmation_class_id}' and "
            f"route_name='{route_name}'."
        )

    def get_production_entitlement_check_class(
        self,
        production_entitlement_check_class_id: str,
    ) -> ProductionEntitlementCheckClassDefinition:
        try:
            return self._production_entitlement_check_classes[
                production_entitlement_check_class_id
            ]
        except KeyError as error:
            raise ReleaseRegistryError(
                "Production-entitlement-check class "
                f"'{production_entitlement_check_class_id}' is not registered."
            ) from error

    def resolve_contained_rollback_template(
        self,
        *,
        semantic_scope: str,
        production_entitlement_check_class_id: str,
        contained_rollback_class_id: str,
        route_name: str | None,
    ) -> tuple[ContainedRollbackTemplateDefinition, bool]:
        exact_matches = tuple(
            template
            for template in self._contained_rollback_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.production_entitlement_check_class_id
            == production_entitlement_check_class_id
            and template.contained_rollback_class_id == contained_rollback_class_id
            and template.route_name == route_name
        )
        if exact_matches:
            template = sorted(
                exact_matches,
                key=lambda item: item.contained_rollback_template_id,
            )[0]
            return (
                template,
                template.contained_rollback_status == "fallback_template_applied",
            )

        generic_matches = tuple(
            template
            for template in self._contained_rollback_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.production_entitlement_check_class_id
            == production_entitlement_check_class_id
            and template.contained_rollback_class_id == contained_rollback_class_id
            and template.route_name is None
        )
        if generic_matches:
            template = sorted(
                generic_matches,
                key=lambda item: item.contained_rollback_template_id,
            )[0]
            return (
                template,
                template.contained_rollback_status == "fallback_template_applied",
            )

        raise ReleaseRegistryError(
            "No governed contained-rollback template applies to "
            f"contained_rollback_class_id='{contained_rollback_class_id}' for "
            "production_entitlement_check_class_id='"
            f"{production_entitlement_check_class_id}' and route_name='"
            f"{route_name}'."
        )

    def get_contained_rollback_class(
        self,
        contained_rollback_class_id: str,
    ) -> ContainedRollbackClassDefinition:
        try:
            return self._contained_rollback_classes[contained_rollback_class_id]
        except KeyError as error:
            raise ReleaseRegistryError(
                "Contained-rollback class "
                f"'{contained_rollback_class_id}' is not registered."
            ) from error

    def resolve_release_audit_trace_template(
        self,
        *,
        semantic_scope: str,
        contained_rollback_class_id: str,
        release_audit_trace_class_id: str,
        route_name: str | None,
    ) -> tuple[ReleaseAuditTraceTemplateDefinition, bool]:
        exact_matches = tuple(
            template
            for template in self._release_audit_trace_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.contained_rollback_class_id == contained_rollback_class_id
            and template.release_audit_trace_class_id == release_audit_trace_class_id
            and template.route_name == route_name
        )
        if exact_matches:
            template = sorted(
                exact_matches,
                key=lambda item: item.release_audit_trace_template_id,
            )[0]
            return (
                template,
                template.release_audit_trace_status == "fallback_template_applied",
            )

        generic_matches = tuple(
            template
            for template in self._release_audit_trace_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.contained_rollback_class_id == contained_rollback_class_id
            and template.release_audit_trace_class_id == release_audit_trace_class_id
            and template.route_name is None
        )
        if generic_matches:
            template = sorted(
                generic_matches,
                key=lambda item: item.release_audit_trace_template_id,
            )[0]
            return (
                template,
                template.release_audit_trace_status == "fallback_template_applied",
            )

        raise ReleaseRegistryError(
            "No governed release-audit-trace template applies to "
            f"release_audit_trace_class_id='{release_audit_trace_class_id}' for "
            f"contained_rollback_class_id='{contained_rollback_class_id}' and "
            f"route_name='{route_name}'."
        )

    def get_release_audit_trace_class(
        self,
        release_audit_trace_class_id: str,
    ) -> ReleaseAuditTraceClassDefinition:
        try:
            return self._release_audit_trace_classes[release_audit_trace_class_id]
        except KeyError as error:
            raise ReleaseRegistryError(
                "Release-audit-trace class "
                f"'{release_audit_trace_class_id}' is not registered."
            ) from error

    def _load_classes(
        self,
        promotion_readiness_classes_path: Path,
    ) -> dict[str, PromotionReadinessClassDefinition]:
        content = json.loads(
            promotion_readiness_classes_path.read_text(encoding="utf-8")
        )
        class_definitions: dict[str, PromotionReadinessClassDefinition] = {}
        for class_id, entry in content["promotion_readiness_classes"].items():
            self._contract_validator.validate_or_raise(
                "promotion_readiness_class",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="promotion_readiness_class",
                entity_id=class_id,
                emit_audit_events=False,
            )
            if entry["promotion_readiness_class_id"] != class_id:
                raise ReleaseRegistryError(
                    "Promotion-readiness class key "
                    f"'{class_id}' must match promotion_readiness_class_id "
                    f"'{entry['promotion_readiness_class_id']}'."
                )
            if entry["status"] not in _VALID_STATUS:
                raise ReleaseRegistryError(
                    "Promotion-readiness class "
                    f"'{class_id}' has invalid status '{entry['status']}'."
                )
            invalid_mutation_execution_statuses = sorted(
                set(entry["allowed_policy_learning_update_mutation_execution_statuses"])
                - _VALID_UPDATE_MUTATION_EXECUTION_STATUSES
            )
            if invalid_mutation_execution_statuses:
                raise ReleaseRegistryError(
                    "Promotion-readiness class "
                    f"'{class_id}' has invalid allowed_policy_learning_update_"
                    "mutation_execution_statuses: "
                    + ", ".join(invalid_mutation_execution_statuses)
                    + "."
                )
            invalid_mutation_execution_outcomes = sorted(
                set(entry["allowed_policy_learning_update_mutation_execution_outcomes"])
                - _VALID_UPDATE_MUTATION_EXECUTION_OUTCOMES
            )
            if invalid_mutation_execution_outcomes:
                raise ReleaseRegistryError(
                    "Promotion-readiness class "
                    f"'{class_id}' has invalid allowed_policy_learning_update_"
                    "mutation_execution_outcomes: "
                    + ", ".join(invalid_mutation_execution_outcomes)
                    + "."
                )
            if entry["minimum_dimension_strength"] not in _VALID_DIMENSION_STRENGTH:
                raise ReleaseRegistryError(
                    "Promotion-readiness class "
                    f"'{class_id}' has invalid minimum_dimension_strength "
                    f"'{entry['minimum_dimension_strength']}'."
                )
            class_definitions[class_id] = PromotionReadinessClassDefinition(
                promotion_readiness_class_id=entry["promotion_readiness_class_id"],
                description=entry["description"],
                allowed_policy_learning_update_mutation_execution_statuses=tuple(
                    entry["allowed_policy_learning_update_mutation_execution_statuses"]
                ),
                allowed_policy_learning_update_mutation_execution_outcomes=tuple(
                    entry["allowed_policy_learning_update_mutation_execution_outcomes"]
                ),
                minimum_dimension_strength=entry["minimum_dimension_strength"],
                allow_promotion_restrictions=entry["allow_promotion_restrictions"],
                allow_promotion_prerequisite_deferral=entry[
                    "allow_promotion_prerequisite_deferral"
                ],
                prohibited_promotion_readiness_fields=tuple(
                    entry["prohibited_promotion_readiness_fields"]
                ),
                status=entry["status"],
                lineage=dict(entry["lineage"]),
            )
        return class_definitions

    def _load_templates(
        self,
        promotion_readiness_templates_path: Path,
    ) -> tuple[PromotionReadinessTemplateDefinition, ...]:
        content = json.loads(
            promotion_readiness_templates_path.read_text(encoding="utf-8")
        )
        templates: list[PromotionReadinessTemplateDefinition] = []
        for template_id, entry in content["promotion_readiness_templates"].items():
            self._contract_validator.validate_or_raise(
                "promotion_readiness_template",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="promotion_readiness_template",
                entity_id=template_id,
                emit_audit_events=False,
            )
            if entry["promotion_readiness_template_id"] != template_id:
                raise ReleaseRegistryError(
                    "Promotion-readiness template key "
                    f"'{template_id}' must match promotion_readiness_template_id "
                    f"'{entry['promotion_readiness_template_id']}'."
                )
            if entry["status"] not in _VALID_STATUS:
                raise ReleaseRegistryError(
                    "Promotion-readiness template "
                    f"'{template_id}' has invalid status '{entry['status']}'."
                )
            if (
                entry["promotion_readiness_status"]
                not in _VALID_PROMOTION_READINESS_STATUSES
            ):
                raise ReleaseRegistryError(
                    "Promotion-readiness template "
                    f"'{template_id}' has invalid status '"
                    f"{entry['promotion_readiness_status']}'."
                )
            if (
                entry["promotion_readiness_outcome"]
                not in _VALID_PROMOTION_READINESS_OUTCOMES
            ):
                raise ReleaseRegistryError(
                    "Promotion-readiness template "
                    f"'{template_id}' has invalid outcome '"
                    f"{entry['promotion_readiness_outcome']}'."
                )
            templates.append(
                PromotionReadinessTemplateDefinition(
                    promotion_readiness_template_id=entry[
                        "promotion_readiness_template_id"
                    ],
                    semantic_scope=entry["semantic_scope"],
                    policy_learning_update_mutation_execution_class_id=entry[
                        "policy_learning_update_mutation_execution_class_id"
                    ],
                    promotion_readiness_class_id=entry[
                        "promotion_readiness_class_id"
                    ],
                    required_promotion_readiness_fields=tuple(
                        entry["required_promotion_readiness_fields"]
                    ),
                    optional_promotion_readiness_fields=tuple(
                        entry["optional_promotion_readiness_fields"]
                    ),
                    required_audit_fields=tuple(entry["required_audit_fields"]),
                    promotion_readiness_status=entry["promotion_readiness_status"],
                    promotion_readiness_outcome=entry[
                        "promotion_readiness_outcome"
                    ],
                    status=entry["status"],
                    lineage=dict(entry["lineage"]),
                    route_name=entry.get("route_name"),
                )
            )
        return tuple(templates)

    def _load_rollout_scope_classes(
        self,
        rollout_scope_classes_path: Path,
    ) -> dict[str, RolloutScopeClassDefinition]:
        content = json.loads(rollout_scope_classes_path.read_text(encoding="utf-8"))
        class_definitions: dict[str, RolloutScopeClassDefinition] = {}
        for class_id, entry in content["rollout_scope_classes"].items():
            self._contract_validator.validate_or_raise(
                "rollout_scope_class",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="rollout_scope_class",
                entity_id=class_id,
                emit_audit_events=False,
            )
            if entry["rollout_scope_class_id"] != class_id:
                raise ReleaseRegistryError(
                    "Rollout-scope class key "
                    f"'{class_id}' must match rollout_scope_class_id "
                    f"'{entry['rollout_scope_class_id']}'."
                )
            if entry["status"] not in _VALID_STATUS:
                raise ReleaseRegistryError(
                    "Rollout-scope class "
                    f"'{class_id}' has invalid status '{entry['status']}'."
                )
            invalid_promotion_statuses = sorted(
                set(entry["allowed_promotion_readiness_statuses"])
                - (
                    _VALID_PROMOTION_READINESS_STATUSES
                    | {
                        "blocked_missing_context",
                        "rejected_for_promotion_use",
                        "prohibited_overlap_blocked",
                    }
                )
            )
            if invalid_promotion_statuses:
                raise ReleaseRegistryError(
                    "Rollout-scope class "
                    f"'{class_id}' has invalid allowed_promotion_readiness_statuses: "
                    + ", ".join(invalid_promotion_statuses)
                    + "."
                )
            invalid_promotion_outcomes = sorted(
                set(entry["allowed_promotion_readiness_outcomes"])
                - (
                    _VALID_PROMOTION_READINESS_OUTCOMES
                    | {
                        "blocked_missing_context",
                        "rejected_for_promotion_use",
                        "prohibited_overlap_blocked",
                    }
                )
            )
            if invalid_promotion_outcomes:
                raise ReleaseRegistryError(
                    "Rollout-scope class "
                    f"'{class_id}' has invalid allowed_promotion_readiness_outcomes: "
                    + ", ".join(invalid_promotion_outcomes)
                    + "."
                )
            class_definitions[class_id] = RolloutScopeClassDefinition(
                rollout_scope_class_id=entry["rollout_scope_class_id"],
                description=entry["description"],
                allowed_promotion_readiness_statuses=tuple(
                    entry["allowed_promotion_readiness_statuses"]
                ),
                allowed_promotion_readiness_outcomes=tuple(
                    entry["allowed_promotion_readiness_outcomes"]
                ),
                allow_rollout_scope_restrictions=entry[
                    "allow_rollout_scope_restrictions"
                ],
                allow_rollout_scope_prerequisite_deferral=entry[
                    "allow_rollout_scope_prerequisite_deferral"
                ],
                prohibited_rollout_scope_fields=tuple(
                    entry["prohibited_rollout_scope_fields"]
                ),
                status=entry["status"],
                lineage=dict(entry["lineage"]),
            )
        return class_definitions

    def _load_rollout_scope_templates(
        self,
        rollout_scope_templates_path: Path,
    ) -> tuple[RolloutScopeTemplateDefinition, ...]:
        content = json.loads(rollout_scope_templates_path.read_text(encoding="utf-8"))
        templates: list[RolloutScopeTemplateDefinition] = []
        for template_id, entry in content["rollout_scope_templates"].items():
            self._contract_validator.validate_or_raise(
                "rollout_scope_template",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="rollout_scope_template",
                entity_id=template_id,
                emit_audit_events=False,
            )
            if entry["rollout_scope_template_id"] != template_id:
                raise ReleaseRegistryError(
                    "Rollout-scope template key "
                    f"'{template_id}' must match rollout_scope_template_id "
                    f"'{entry['rollout_scope_template_id']}'."
                )
            if entry["status"] not in _VALID_STATUS:
                raise ReleaseRegistryError(
                    "Rollout-scope template "
                    f"'{template_id}' has invalid status '{entry['status']}'."
                )
            if entry["rollout_scope_status"] not in _VALID_ROLLOUT_SCOPE_STATUSES:
                raise ReleaseRegistryError(
                    "Rollout-scope template "
                    f"'{template_id}' has invalid status '{entry['rollout_scope_status']}'."
                )
            if entry["rollout_scope_outcome"] not in _VALID_ROLLOUT_SCOPE_OUTCOMES:
                raise ReleaseRegistryError(
                    "Rollout-scope template "
                    f"'{template_id}' has invalid outcome '{entry['rollout_scope_outcome']}'."
                )
            templates.append(
                RolloutScopeTemplateDefinition(
                    rollout_scope_template_id=entry["rollout_scope_template_id"],
                    semantic_scope=entry["semantic_scope"],
                    promotion_readiness_class_id=entry[
                        "promotion_readiness_class_id"
                    ],
                    rollout_scope_class_id=entry["rollout_scope_class_id"],
                    required_rollout_scope_fields=tuple(
                        entry["required_rollout_scope_fields"]
                    ),
                    optional_rollout_scope_fields=tuple(
                        entry["optional_rollout_scope_fields"]
                    ),
                    required_audit_fields=tuple(entry["required_audit_fields"]),
                    rollout_scope_status=entry["rollout_scope_status"],
                    rollout_scope_outcome=entry["rollout_scope_outcome"],
                    status=entry["status"],
                    lineage=dict(entry["lineage"]),
                    route_name=entry.get("route_name"),
                )
            )
        return tuple(templates)

    def _load_rollback_trigger_classes(
        self,
        rollback_trigger_classes_path: Path,
    ) -> dict[str, RollbackTriggerClassDefinition]:
        content = json.loads(
            rollback_trigger_classes_path.read_text(encoding="utf-8")
        )
        class_definitions: dict[str, RollbackTriggerClassDefinition] = {}
        for class_id, entry in content["rollback_trigger_classes"].items():
            self._contract_validator.validate_or_raise(
                "rollback_trigger_class",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="rollback_trigger_class",
                entity_id=class_id,
                emit_audit_events=False,
            )
            if entry["rollback_trigger_class_id"] != class_id:
                raise ReleaseRegistryError(
                    "Rollback-trigger class key "
                    f"'{class_id}' must match rollback_trigger_class_id "
                    f"'{entry['rollback_trigger_class_id']}'."
                )
            if entry["status"] not in _VALID_STATUS:
                raise ReleaseRegistryError(
                    "Rollback-trigger class "
                    f"'{class_id}' has invalid status '{entry['status']}'."
                )
            invalid_rollout_statuses = sorted(
                set(entry["allowed_rollout_scope_statuses"])
                - (
                    _VALID_ROLLOUT_SCOPE_STATUSES
                    | {
                        "blocked_missing_context",
                        "rejected_for_rollout_scope_use",
                        "prohibited_overlap_blocked",
                    }
                )
            )
            if invalid_rollout_statuses:
                raise ReleaseRegistryError(
                    "Rollback-trigger class "
                    f"'{class_id}' has invalid allowed_rollout_scope_statuses: "
                    + ", ".join(invalid_rollout_statuses)
                    + "."
                )
            invalid_rollout_outcomes = sorted(
                set(entry["allowed_rollout_scope_outcomes"])
                - (
                    _VALID_ROLLOUT_SCOPE_OUTCOMES
                    | {
                        "blocked_missing_context",
                        "rejected_for_rollout_scope_use",
                        "prohibited_overlap_blocked",
                    }
                )
            )
            if invalid_rollout_outcomes:
                raise ReleaseRegistryError(
                    "Rollback-trigger class "
                    f"'{class_id}' has invalid allowed_rollout_scope_outcomes: "
                    + ", ".join(invalid_rollout_outcomes)
                    + "."
                )
            class_definitions[class_id] = RollbackTriggerClassDefinition(
                rollback_trigger_class_id=entry["rollback_trigger_class_id"],
                description=entry["description"],
                allowed_rollout_scope_statuses=tuple(
                    entry["allowed_rollout_scope_statuses"]
                ),
                allowed_rollout_scope_outcomes=tuple(
                    entry["allowed_rollout_scope_outcomes"]
                ),
                allow_rollback_trigger_restrictions=entry[
                    "allow_rollback_trigger_restrictions"
                ],
                allow_rollback_trigger_prerequisite_deferral=entry[
                    "allow_rollback_trigger_prerequisite_deferral"
                ],
                prohibited_rollback_trigger_fields=tuple(
                    entry["prohibited_rollback_trigger_fields"]
                ),
                status=entry["status"],
                lineage=dict(entry["lineage"]),
            )
        return class_definitions

    def _load_rollback_trigger_templates(
        self,
        rollback_trigger_templates_path: Path,
    ) -> tuple[RollbackTriggerTemplateDefinition, ...]:
        content = json.loads(
            rollback_trigger_templates_path.read_text(encoding="utf-8")
        )
        templates: list[RollbackTriggerTemplateDefinition] = []
        for template_id, entry in content["rollback_trigger_templates"].items():
            self._contract_validator.validate_or_raise(
                "rollback_trigger_template",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="rollback_trigger_template",
                entity_id=template_id,
                emit_audit_events=False,
            )
            if entry["rollback_trigger_template_id"] != template_id:
                raise ReleaseRegistryError(
                    "Rollback-trigger template key "
                    f"'{template_id}' must match rollback_trigger_template_id "
                    f"'{entry['rollback_trigger_template_id']}'."
                )
            if entry["status"] not in _VALID_STATUS:
                raise ReleaseRegistryError(
                    "Rollback-trigger template "
                    f"'{template_id}' has invalid status '{entry['status']}'."
                )
            if (
                entry["rollback_trigger_status"]
                not in _VALID_ROLLBACK_TRIGGER_STATUSES
            ):
                raise ReleaseRegistryError(
                    "Rollback-trigger template "
                    f"'{template_id}' has invalid status '"
                    f"{entry['rollback_trigger_status']}'."
                )
            if (
                entry["rollback_trigger_outcome"]
                not in _VALID_ROLLBACK_TRIGGER_OUTCOMES
            ):
                raise ReleaseRegistryError(
                    "Rollback-trigger template "
                    f"'{template_id}' has invalid outcome '"
                    f"{entry['rollback_trigger_outcome']}'."
                )
            templates.append(
                RollbackTriggerTemplateDefinition(
                    rollback_trigger_template_id=entry[
                        "rollback_trigger_template_id"
                    ],
                    semantic_scope=entry["semantic_scope"],
                    rollout_scope_class_id=entry["rollout_scope_class_id"],
                    rollback_trigger_class_id=entry["rollback_trigger_class_id"],
                    required_rollback_trigger_fields=tuple(
                        entry["required_rollback_trigger_fields"]
                    ),
                    optional_rollback_trigger_fields=tuple(
                        entry["optional_rollback_trigger_fields"]
                    ),
                    required_audit_fields=tuple(entry["required_audit_fields"]),
                    rollback_trigger_status=entry["rollback_trigger_status"],
                    rollback_trigger_outcome=entry["rollback_trigger_outcome"],
                    status=entry["status"],
                    lineage=dict(entry["lineage"]),
                    route_name=entry.get("route_name"),
                )
            )
        return tuple(templates)

    def _load_release_watch_discipline_classes(
        self,
        release_watch_discipline_classes_path: Path,
    ) -> dict[str, ReleaseWatchDisciplineClassDefinition]:
        content = json.loads(
            release_watch_discipline_classes_path.read_text(encoding="utf-8")
        )
        class_definitions: dict[str, ReleaseWatchDisciplineClassDefinition] = {}
        for class_id, entry in content["release_watch_discipline_classes"].items():
            self._contract_validator.validate_or_raise(
                "release_watch_discipline_class",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="release_watch_discipline_class",
                entity_id=class_id,
                emit_audit_events=False,
            )
            if entry["release_watch_discipline_class_id"] != class_id:
                raise ReleaseRegistryError(
                    "Release-watch-discipline class key "
                    f"'{class_id}' must match release_watch_discipline_class_id "
                    f"'{entry['release_watch_discipline_class_id']}'."
                )
            if entry["status"] not in _VALID_STATUS:
                raise ReleaseRegistryError(
                    "Release-watch-discipline class "
                    f"'{class_id}' has invalid status '{entry['status']}'."
                )
            invalid_rollback_trigger_statuses = sorted(
                set(entry["allowed_rollback_trigger_statuses"])
                - (
                    _VALID_ROLLBACK_TRIGGER_STATUSES
                    | {
                        "blocked_missing_context",
                        "rejected_for_rollback_trigger_use",
                        "prohibited_overlap_blocked",
                    }
                )
            )
            if invalid_rollback_trigger_statuses:
                raise ReleaseRegistryError(
                    "Release-watch-discipline class "
                    f"'{class_id}' has invalid allowed_rollback_trigger_statuses: "
                    + ", ".join(invalid_rollback_trigger_statuses)
                    + "."
                )
            invalid_rollback_trigger_outcomes = sorted(
                set(entry["allowed_rollback_trigger_outcomes"])
                - (
                    _VALID_ROLLBACK_TRIGGER_OUTCOMES
                    | {
                        "blocked_missing_context",
                        "rejected_for_rollback_trigger_use",
                        "prohibited_overlap_blocked",
                    }
                )
            )
            if invalid_rollback_trigger_outcomes:
                raise ReleaseRegistryError(
                    "Release-watch-discipline class "
                    f"'{class_id}' has invalid allowed_rollback_trigger_outcomes: "
                    + ", ".join(invalid_rollback_trigger_outcomes)
                    + "."
                )
            class_definitions[class_id] = ReleaseWatchDisciplineClassDefinition(
                release_watch_discipline_class_id=entry[
                    "release_watch_discipline_class_id"
                ],
                description=entry["description"],
                allowed_rollback_trigger_statuses=tuple(
                    entry["allowed_rollback_trigger_statuses"]
                ),
                allowed_rollback_trigger_outcomes=tuple(
                    entry["allowed_rollback_trigger_outcomes"]
                ),
                allow_release_watch_discipline_restrictions=entry[
                    "allow_release_watch_discipline_restrictions"
                ],
                allow_release_watch_discipline_prerequisite_deferral=entry[
                    "allow_release_watch_discipline_prerequisite_deferral"
                ],
                prohibited_release_watch_discipline_fields=tuple(
                    entry["prohibited_release_watch_discipline_fields"]
                ),
                status=entry["status"],
                lineage=dict(entry["lineage"]),
            )
        return class_definitions

    def _load_release_watch_discipline_templates(
        self,
        release_watch_discipline_templates_path: Path,
    ) -> tuple[ReleaseWatchDisciplineTemplateDefinition, ...]:
        content = json.loads(
            release_watch_discipline_templates_path.read_text(encoding="utf-8")
        )
        templates: list[ReleaseWatchDisciplineTemplateDefinition] = []
        for template_id, entry in content["release_watch_discipline_templates"].items():
            self._contract_validator.validate_or_raise(
                "release_watch_discipline_template",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="release_watch_discipline_template",
                entity_id=template_id,
                emit_audit_events=False,
            )
            if entry["release_watch_discipline_template_id"] != template_id:
                raise ReleaseRegistryError(
                    "Release-watch-discipline template key "
                    f"'{template_id}' must match release_watch_discipline_template_id "
                    f"'{entry['release_watch_discipline_template_id']}'."
                )
            if entry["status"] not in _VALID_STATUS:
                raise ReleaseRegistryError(
                    "Release-watch-discipline template "
                    f"'{template_id}' has invalid status '{entry['status']}'."
                )
            if (
                entry["release_watch_discipline_status"]
                not in _VALID_RELEASE_WATCH_DISCIPLINE_STATUSES
            ):
                raise ReleaseRegistryError(
                    "Release-watch-discipline template "
                    f"'{template_id}' has invalid status '"
                    f"{entry['release_watch_discipline_status']}'."
                )
            if (
                entry["release_watch_discipline_outcome"]
                not in _VALID_RELEASE_WATCH_DISCIPLINE_OUTCOMES
            ):
                raise ReleaseRegistryError(
                    "Release-watch-discipline template "
                    f"'{template_id}' has invalid outcome '"
                    f"{entry['release_watch_discipline_outcome']}'."
                )
            templates.append(
                ReleaseWatchDisciplineTemplateDefinition(
                    release_watch_discipline_template_id=entry[
                        "release_watch_discipline_template_id"
                    ],
                    semantic_scope=entry["semantic_scope"],
                    rollback_trigger_class_id=entry["rollback_trigger_class_id"],
                    release_watch_discipline_class_id=entry[
                        "release_watch_discipline_class_id"
                    ],
                    required_release_watch_discipline_fields=tuple(
                        entry["required_release_watch_discipline_fields"]
                    ),
                    optional_release_watch_discipline_fields=tuple(
                        entry["optional_release_watch_discipline_fields"]
                    ),
                    required_audit_fields=tuple(entry["required_audit_fields"]),
                    release_watch_discipline_status=entry[
                        "release_watch_discipline_status"
                    ],
                    release_watch_discipline_outcome=entry[
                        "release_watch_discipline_outcome"
                    ],
                    status=entry["status"],
                    lineage=dict(entry["lineage"]),
                    route_name=entry.get("route_name"),
                )
            )
        return tuple(templates)

    def _load_release_confirmation_classes(
        self,
        release_confirmation_classes_path: Path,
    ) -> dict[str, ReleaseConfirmationClassDefinition]:
        content = json.loads(
            release_confirmation_classes_path.read_text(encoding="utf-8")
        )
        class_definitions: dict[str, ReleaseConfirmationClassDefinition] = {}
        for class_id, entry in content["release_confirmation_classes"].items():
            self._contract_validator.validate_or_raise(
                "release_confirmation_class",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="release_confirmation_class",
                entity_id=class_id,
                emit_audit_events=False,
            )
            if entry["release_confirmation_class_id"] != class_id:
                raise ReleaseRegistryError(
                    "Release-confirmation class key "
                    f"'{class_id}' must match release_confirmation_class_id "
                    f"'{entry['release_confirmation_class_id']}'."
                )
            if entry["status"] not in _VALID_STATUS:
                raise ReleaseRegistryError(
                    "Release-confirmation class "
                    f"'{class_id}' has invalid status '{entry['status']}'."
                )
            invalid_release_watch_discipline_statuses = sorted(
                set(entry["allowed_release_watch_discipline_statuses"])
                - (
                    _VALID_RELEASE_WATCH_DISCIPLINE_STATUSES
                    | {
                        "blocked_missing_context",
                        "rejected_for_release_watch_discipline_use",
                        "prohibited_overlap_blocked",
                    }
                )
            )
            if invalid_release_watch_discipline_statuses:
                raise ReleaseRegistryError(
                    "Release-confirmation class "
                    f"'{class_id}' has invalid allowed_release_watch_discipline_statuses: "
                    + ", ".join(invalid_release_watch_discipline_statuses)
                    + "."
                )
            invalid_release_watch_discipline_outcomes = sorted(
                set(entry["allowed_release_watch_discipline_outcomes"])
                - (
                    _VALID_RELEASE_WATCH_DISCIPLINE_OUTCOMES
                    | {
                        "blocked_missing_context",
                        "rejected_for_release_watch_discipline_use",
                        "prohibited_overlap_blocked",
                    }
                )
            )
            if invalid_release_watch_discipline_outcomes:
                raise ReleaseRegistryError(
                    "Release-confirmation class "
                    f"'{class_id}' has invalid allowed_release_watch_discipline_outcomes: "
                    + ", ".join(invalid_release_watch_discipline_outcomes)
                    + "."
                )
            class_definitions[class_id] = ReleaseConfirmationClassDefinition(
                release_confirmation_class_id=entry["release_confirmation_class_id"],
                description=entry["description"],
                allowed_release_watch_discipline_statuses=tuple(
                    entry["allowed_release_watch_discipline_statuses"]
                ),
                allowed_release_watch_discipline_outcomes=tuple(
                    entry["allowed_release_watch_discipline_outcomes"]
                ),
                allow_release_confirmation_restrictions=entry[
                    "allow_release_confirmation_restrictions"
                ],
                allow_release_confirmation_prerequisite_deferral=entry[
                    "allow_release_confirmation_prerequisite_deferral"
                ],
                prohibited_release_confirmation_fields=tuple(
                    entry["prohibited_release_confirmation_fields"]
                ),
                status=entry["status"],
                lineage=dict(entry["lineage"]),
            )
        return class_definitions

    def _load_release_confirmation_templates(
        self,
        release_confirmation_templates_path: Path,
    ) -> tuple[ReleaseConfirmationTemplateDefinition, ...]:
        content = json.loads(
            release_confirmation_templates_path.read_text(encoding="utf-8")
        )
        templates: list[ReleaseConfirmationTemplateDefinition] = []
        for template_id, entry in content["release_confirmation_templates"].items():
            self._contract_validator.validate_or_raise(
                "release_confirmation_template",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="release_confirmation_template",
                entity_id=template_id,
                emit_audit_events=False,
            )
            if entry["release_confirmation_template_id"] != template_id:
                raise ReleaseRegistryError(
                    "Release-confirmation template key "
                    f"'{template_id}' must match release_confirmation_template_id "
                    f"'{entry['release_confirmation_template_id']}'."
                )
            if entry["status"] not in _VALID_STATUS:
                raise ReleaseRegistryError(
                    "Release-confirmation template "
                    f"'{template_id}' has invalid status '{entry['status']}'."
                )
            if (
                entry["release_confirmation_status"]
                not in _VALID_RELEASE_CONFIRMATION_STATUSES
            ):
                raise ReleaseRegistryError(
                    "Release-confirmation template "
                    f"'{template_id}' has invalid status '"
                    f"{entry['release_confirmation_status']}'."
                )
            if (
                entry["release_confirmation_outcome"]
                not in _VALID_RELEASE_CONFIRMATION_OUTCOMES
            ):
                raise ReleaseRegistryError(
                    "Release-confirmation template "
                    f"'{template_id}' has invalid outcome '"
                    f"{entry['release_confirmation_outcome']}'."
                )
            templates.append(
                ReleaseConfirmationTemplateDefinition(
                    release_confirmation_template_id=entry[
                        "release_confirmation_template_id"
                    ],
                    semantic_scope=entry["semantic_scope"],
                    release_watch_discipline_class_id=entry[
                        "release_watch_discipline_class_id"
                    ],
                    release_confirmation_class_id=entry[
                        "release_confirmation_class_id"
                    ],
                    required_release_confirmation_fields=tuple(
                        entry["required_release_confirmation_fields"]
                    ),
                    optional_release_confirmation_fields=tuple(
                        entry["optional_release_confirmation_fields"]
                    ),
                    required_audit_fields=tuple(entry["required_audit_fields"]),
                    release_confirmation_status=entry[
                        "release_confirmation_status"
                    ],
                    release_confirmation_outcome=entry[
                        "release_confirmation_outcome"
                    ],
                    status=entry["status"],
                    lineage=dict(entry["lineage"]),
                    route_name=entry.get("route_name"),
                )
            )
        return tuple(templates)

    def _load_production_entitlement_check_classes(
        self,
        production_entitlement_check_classes_path: Path,
    ) -> dict[str, ProductionEntitlementCheckClassDefinition]:
        content = json.loads(
            production_entitlement_check_classes_path.read_text(encoding="utf-8")
        )
        class_definitions: dict[str, ProductionEntitlementCheckClassDefinition] = {}
        for class_id, entry in content[
            "production_entitlement_check_classes"
        ].items():
            self._contract_validator.validate_or_raise(
                "production_entitlement_check_class",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="production_entitlement_check_class",
                entity_id=class_id,
                emit_audit_events=False,
            )
            if entry["production_entitlement_check_class_id"] != class_id:
                raise ReleaseRegistryError(
                    "Production-entitlement-check class key "
                    f"'{class_id}' must match production_entitlement_check_class_id "
                    f"'{entry['production_entitlement_check_class_id']}'."
                )
            if entry["status"] not in _VALID_STATUS:
                raise ReleaseRegistryError(
                    "Production-entitlement-check class "
                    f"'{class_id}' has invalid status '{entry['status']}'."
                )
            invalid_release_confirmation_statuses = sorted(
                set(entry["allowed_release_confirmation_statuses"])
                - (
                    _VALID_RELEASE_CONFIRMATION_STATUSES
                    | {
                        "blocked_missing_context",
                        "rejected_for_release_confirmation_use",
                        "prohibited_overlap_blocked",
                    }
                )
            )
            if invalid_release_confirmation_statuses:
                raise ReleaseRegistryError(
                    "Production-entitlement-check class "
                    f"'{class_id}' has invalid allowed_release_confirmation_statuses: "
                    + ", ".join(invalid_release_confirmation_statuses)
                    + "."
                )
            invalid_release_confirmation_outcomes = sorted(
                set(entry["allowed_release_confirmation_outcomes"])
                - (
                    _VALID_RELEASE_CONFIRMATION_OUTCOMES
                    | {
                        "blocked_missing_context",
                        "rejected_for_release_confirmation_use",
                        "prohibited_overlap_blocked",
                    }
                )
            )
            if invalid_release_confirmation_outcomes:
                raise ReleaseRegistryError(
                    "Production-entitlement-check class "
                    f"'{class_id}' has invalid allowed_release_confirmation_outcomes: "
                    + ", ".join(invalid_release_confirmation_outcomes)
                    + "."
                )
            class_definitions[class_id] = ProductionEntitlementCheckClassDefinition(
                production_entitlement_check_class_id=entry[
                    "production_entitlement_check_class_id"
                ],
                description=entry["description"],
                allowed_release_confirmation_statuses=tuple(
                    entry["allowed_release_confirmation_statuses"]
                ),
                allowed_release_confirmation_outcomes=tuple(
                    entry["allowed_release_confirmation_outcomes"]
                ),
                allow_production_entitlement_restrictions=entry[
                    "allow_production_entitlement_restrictions"
                ],
                allow_production_entitlement_prerequisite_deferral=entry[
                    "allow_production_entitlement_prerequisite_deferral"
                ],
                prohibited_production_entitlement_fields=tuple(
                    entry["prohibited_production_entitlement_fields"]
                ),
                status=entry["status"],
                lineage=dict(entry["lineage"]),
            )
        return class_definitions

    def _load_production_entitlement_check_templates(
        self,
        production_entitlement_check_templates_path: Path,
    ) -> tuple[ProductionEntitlementCheckTemplateDefinition, ...]:
        content = json.loads(
            production_entitlement_check_templates_path.read_text(encoding="utf-8")
        )
        templates: list[ProductionEntitlementCheckTemplateDefinition] = []
        for template_id, entry in content[
            "production_entitlement_check_templates"
        ].items():
            self._contract_validator.validate_or_raise(
                "production_entitlement_check_template",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="production_entitlement_check_template",
                entity_id=template_id,
                emit_audit_events=False,
            )
            if entry["production_entitlement_check_template_id"] != template_id:
                raise ReleaseRegistryError(
                    "Production-entitlement-check template key "
                    f"'{template_id}' must match "
                    "production_entitlement_check_template_id "
                    f"'{entry['production_entitlement_check_template_id']}'."
                )
            if entry["status"] not in _VALID_STATUS:
                raise ReleaseRegistryError(
                    "Production-entitlement-check template "
                    f"'{template_id}' has invalid status '{entry['status']}'."
                )
            if (
                entry["production_entitlement_check_status"]
                not in _VALID_PRODUCTION_ENTITLEMENT_CHECK_STATUSES
            ):
                raise ReleaseRegistryError(
                    "Production-entitlement-check template "
                    f"'{template_id}' has invalid status '"
                    f"{entry['production_entitlement_check_status']}'."
                )
            if (
                entry["production_entitlement_check_outcome"]
                not in _VALID_PRODUCTION_ENTITLEMENT_CHECK_OUTCOMES
            ):
                raise ReleaseRegistryError(
                    "Production-entitlement-check template "
                    f"'{template_id}' has invalid outcome '"
                    f"{entry['production_entitlement_check_outcome']}'."
                )
            templates.append(
                ProductionEntitlementCheckTemplateDefinition(
                    production_entitlement_check_template_id=entry[
                        "production_entitlement_check_template_id"
                    ],
                    semantic_scope=entry["semantic_scope"],
                    release_confirmation_class_id=entry[
                        "release_confirmation_class_id"
                    ],
                    production_entitlement_check_class_id=entry[
                        "production_entitlement_check_class_id"
                    ],
                    required_production_entitlement_check_fields=tuple(
                        entry["required_production_entitlement_check_fields"]
                    ),
                    optional_production_entitlement_check_fields=tuple(
                        entry["optional_production_entitlement_check_fields"]
                    ),
                    required_audit_fields=tuple(entry["required_audit_fields"]),
                    production_entitlement_check_status=entry[
                        "production_entitlement_check_status"
                    ],
                    production_entitlement_check_outcome=entry[
                        "production_entitlement_check_outcome"
                    ],
                    status=entry["status"],
                    lineage=dict(entry["lineage"]),
                    route_name=entry.get("route_name"),
                )
            )
        return tuple(templates)

    def _load_contained_rollback_classes(
        self,
        contained_rollback_classes_path: Path,
    ) -> dict[str, ContainedRollbackClassDefinition]:
        content = json.loads(
            contained_rollback_classes_path.read_text(encoding="utf-8")
        )
        class_definitions: dict[str, ContainedRollbackClassDefinition] = {}
        for class_id, entry in content["contained_rollback_classes"].items():
            self._contract_validator.validate_or_raise(
                "contained_rollback_class",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="contained_rollback_class",
                entity_id=class_id,
                emit_audit_events=False,
            )
            if entry["contained_rollback_class_id"] != class_id:
                raise ReleaseRegistryError(
                    "Contained-rollback class key "
                    f"'{class_id}' must match contained_rollback_class_id "
                    f"'{entry['contained_rollback_class_id']}'."
                )
            if entry["status"] not in _VALID_STATUS:
                raise ReleaseRegistryError(
                    "Contained-rollback class "
                    f"'{class_id}' has invalid status '{entry['status']}'."
                )
            invalid_production_entitlement_check_statuses = sorted(
                set(entry["allowed_production_entitlement_check_statuses"])
                - (
                    _VALID_PRODUCTION_ENTITLEMENT_CHECK_STATUSES
                    | {
                        "blocked_missing_context",
                        "rejected_for_production_entitlement_use",
                        "prohibited_overlap_blocked",
                    }
                )
            )
            if invalid_production_entitlement_check_statuses:
                raise ReleaseRegistryError(
                    "Contained-rollback class "
                    f"'{class_id}' has invalid allowed_production_entitlement_check_statuses: "
                    + ", ".join(invalid_production_entitlement_check_statuses)
                    + "."
                )
            invalid_production_entitlement_check_outcomes = sorted(
                set(entry["allowed_production_entitlement_check_outcomes"])
                - (
                    _VALID_PRODUCTION_ENTITLEMENT_CHECK_OUTCOMES
                    | {
                        "blocked_missing_context",
                        "rejected_for_production_entitlement_use",
                        "prohibited_overlap_blocked",
                    }
                )
            )
            if invalid_production_entitlement_check_outcomes:
                raise ReleaseRegistryError(
                    "Contained-rollback class "
                    f"'{class_id}' has invalid allowed_production_entitlement_check_outcomes: "
                    + ", ".join(invalid_production_entitlement_check_outcomes)
                    + "."
                )
            class_definitions[class_id] = ContainedRollbackClassDefinition(
                contained_rollback_class_id=entry["contained_rollback_class_id"],
                description=entry["description"],
                allowed_production_entitlement_check_statuses=tuple(
                    entry["allowed_production_entitlement_check_statuses"]
                ),
                allowed_production_entitlement_check_outcomes=tuple(
                    entry["allowed_production_entitlement_check_outcomes"]
                ),
                allow_contained_rollback_restrictions=entry[
                    "allow_contained_rollback_restrictions"
                ],
                allow_contained_rollback_prerequisite_deferral=entry[
                    "allow_contained_rollback_prerequisite_deferral"
                ],
                prohibited_contained_rollback_fields=tuple(
                    entry["prohibited_contained_rollback_fields"]
                ),
                status=entry["status"],
                lineage=dict(entry["lineage"]),
            )
        return class_definitions

    def _load_contained_rollback_templates(
        self,
        contained_rollback_templates_path: Path,
    ) -> tuple[ContainedRollbackTemplateDefinition, ...]:
        content = json.loads(
            contained_rollback_templates_path.read_text(encoding="utf-8")
        )
        templates: list[ContainedRollbackTemplateDefinition] = []
        for template_id, entry in content["contained_rollback_templates"].items():
            self._contract_validator.validate_or_raise(
                "contained_rollback_template",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="contained_rollback_template",
                entity_id=template_id,
                emit_audit_events=False,
            )
            if entry["contained_rollback_template_id"] != template_id:
                raise ReleaseRegistryError(
                    "Contained-rollback template key "
                    f"'{template_id}' must match contained_rollback_template_id "
                    f"'{entry['contained_rollback_template_id']}'."
                )
            if entry["status"] not in _VALID_STATUS:
                raise ReleaseRegistryError(
                    "Contained-rollback template "
                    f"'{template_id}' has invalid status '{entry['status']}'."
                )
            if (
                entry["contained_rollback_status"]
                not in _VALID_CONTAINED_ROLLBACK_STATUSES
            ):
                raise ReleaseRegistryError(
                    "Contained-rollback template "
                    f"'{template_id}' has invalid status '"
                    f"{entry['contained_rollback_status']}'."
                )
            if (
                entry["contained_rollback_outcome"]
                not in _VALID_CONTAINED_ROLLBACK_OUTCOMES
            ):
                raise ReleaseRegistryError(
                    "Contained-rollback template "
                    f"'{template_id}' has invalid outcome '"
                    f"{entry['contained_rollback_outcome']}'."
                )
            templates.append(
                ContainedRollbackTemplateDefinition(
                    contained_rollback_template_id=entry[
                        "contained_rollback_template_id"
                    ],
                    semantic_scope=entry["semantic_scope"],
                    production_entitlement_check_class_id=entry[
                        "production_entitlement_check_class_id"
                    ],
                    contained_rollback_class_id=entry[
                        "contained_rollback_class_id"
                    ],
                    required_contained_rollback_fields=tuple(
                        entry["required_contained_rollback_fields"]
                    ),
                    optional_contained_rollback_fields=tuple(
                        entry["optional_contained_rollback_fields"]
                    ),
                    required_audit_fields=tuple(entry["required_audit_fields"]),
                    contained_rollback_status=entry["contained_rollback_status"],
                    contained_rollback_outcome=entry["contained_rollback_outcome"],
                    status=entry["status"],
                    lineage=dict(entry["lineage"]),
                    route_name=entry.get("route_name"),
                )
            )
        return tuple(templates)

    def _load_release_audit_trace_classes(
        self,
        release_audit_trace_classes_path: Path,
    ) -> dict[str, ReleaseAuditTraceClassDefinition]:
        content = json.loads(
            release_audit_trace_classes_path.read_text(encoding="utf-8")
        )
        class_definitions: dict[str, ReleaseAuditTraceClassDefinition] = {}
        for class_id, entry in content["release_audit_trace_classes"].items():
            self._contract_validator.validate_or_raise(
                "release_audit_trace_class",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="release_audit_trace_class",
                entity_id=class_id,
                emit_audit_events=False,
            )
            if entry["release_audit_trace_class_id"] != class_id:
                raise ReleaseRegistryError(
                    "Release-audit-trace class key "
                    f"'{class_id}' must match release_audit_trace_class_id "
                    f"'{entry['release_audit_trace_class_id']}'."
                )
            if entry["status"] not in _VALID_STATUS:
                raise ReleaseRegistryError(
                    "Release-audit-trace class "
                    f"'{class_id}' has invalid status '{entry['status']}'."
                )
            invalid_contained_rollback_statuses = sorted(
                set(entry["allowed_contained_rollback_statuses"])
                - (
                    _VALID_CONTAINED_ROLLBACK_STATUSES
                    | {
                        "blocked_missing_context",
                        "rejected_for_contained_rollback_use",
                        "prohibited_overlap_blocked",
                    }
                )
            )
            if invalid_contained_rollback_statuses:
                raise ReleaseRegistryError(
                    "Release-audit-trace class "
                    f"'{class_id}' has invalid allowed_contained_rollback_statuses: "
                    + ", ".join(invalid_contained_rollback_statuses)
                    + "."
                )
            invalid_contained_rollback_outcomes = sorted(
                set(entry["allowed_contained_rollback_outcomes"])
                - (
                    _VALID_CONTAINED_ROLLBACK_OUTCOMES
                    | {
                        "blocked_missing_context",
                        "rejected_for_contained_rollback_use",
                        "prohibited_overlap_blocked",
                    }
                )
            )
            if invalid_contained_rollback_outcomes:
                raise ReleaseRegistryError(
                    "Release-audit-trace class "
                    f"'{class_id}' has invalid allowed_contained_rollback_outcomes: "
                    + ", ".join(invalid_contained_rollback_outcomes)
                    + "."
                )
            class_definitions[class_id] = ReleaseAuditTraceClassDefinition(
                release_audit_trace_class_id=entry[
                    "release_audit_trace_class_id"
                ],
                description=entry["description"],
                allowed_contained_rollback_statuses=tuple(
                    entry["allowed_contained_rollback_statuses"]
                ),
                allowed_contained_rollback_outcomes=tuple(
                    entry["allowed_contained_rollback_outcomes"]
                ),
                allow_release_audit_trace_restrictions=entry[
                    "allow_release_audit_trace_restrictions"
                ],
                allow_release_audit_trace_prerequisite_deferral=entry[
                    "allow_release_audit_trace_prerequisite_deferral"
                ],
                prohibited_release_audit_trace_fields=tuple(
                    entry["prohibited_release_audit_trace_fields"]
                ),
                status=entry["status"],
                lineage=dict(entry["lineage"]),
            )
        return class_definitions

    def _load_release_audit_trace_templates(
        self,
        release_audit_trace_templates_path: Path,
    ) -> tuple[ReleaseAuditTraceTemplateDefinition, ...]:
        content = json.loads(
            release_audit_trace_templates_path.read_text(encoding="utf-8")
        )
        templates: list[ReleaseAuditTraceTemplateDefinition] = []
        for template_id, entry in content["release_audit_trace_templates"].items():
            self._contract_validator.validate_or_raise(
                "release_audit_trace_template",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="release_audit_trace_template",
                entity_id=template_id,
                emit_audit_events=False,
            )
            if entry["release_audit_trace_template_id"] != template_id:
                raise ReleaseRegistryError(
                    "Release-audit-trace template key "
                    f"'{template_id}' must match release_audit_trace_template_id "
                    f"'{entry['release_audit_trace_template_id']}'."
                )
            if entry["status"] not in _VALID_STATUS:
                raise ReleaseRegistryError(
                    "Release-audit-trace template "
                    f"'{template_id}' has invalid status '{entry['status']}'."
                )
            if (
                entry["release_audit_trace_status"]
                not in _VALID_RELEASE_AUDIT_TRACE_STATUSES
            ):
                raise ReleaseRegistryError(
                    "Release-audit-trace template "
                    f"'{template_id}' has invalid status '"
                    f"{entry['release_audit_trace_status']}'."
                )
            if (
                entry["release_audit_trace_outcome"]
                not in _VALID_RELEASE_AUDIT_TRACE_OUTCOMES
            ):
                raise ReleaseRegistryError(
                    "Release-audit-trace template "
                    f"'{template_id}' has invalid outcome '"
                    f"{entry['release_audit_trace_outcome']}'."
                )
            templates.append(
                ReleaseAuditTraceTemplateDefinition(
                    release_audit_trace_template_id=entry[
                        "release_audit_trace_template_id"
                    ],
                    semantic_scope=entry["semantic_scope"],
                    contained_rollback_class_id=entry[
                        "contained_rollback_class_id"
                    ],
                    release_audit_trace_class_id=entry[
                        "release_audit_trace_class_id"
                    ],
                    required_release_audit_trace_fields=tuple(
                        entry["required_release_audit_trace_fields"]
                    ),
                    optional_release_audit_trace_fields=tuple(
                        entry["optional_release_audit_trace_fields"]
                    ),
                    required_audit_fields=tuple(entry["required_audit_fields"]),
                    release_audit_trace_status=entry[
                        "release_audit_trace_status"
                    ],
                    release_audit_trace_outcome=entry[
                        "release_audit_trace_outcome"
                    ],
                    status=entry["status"],
                    lineage=dict(entry["lineage"]),
                    route_name=entry.get("route_name"),
                )
            )
        return tuple(templates)

    def _validate_cross_registry_links(self) -> None:
        for template in self._promotion_readiness_templates:
            if (
                template.promotion_readiness_class_id
                not in self._promotion_readiness_classes
            ):
                raise ReleaseRegistryError(
                    "Promotion-readiness template '"
                    f"{template.promotion_readiness_template_id}' references "
                    "unknown promotion_readiness_class_id '"
                    f"{template.promotion_readiness_class_id}'."
                )
        for template in self._rollout_scope_templates:
            if template.rollout_scope_class_id not in self._rollout_scope_classes:
                raise ReleaseRegistryError(
                    "Rollout-scope template '"
                    f"{template.rollout_scope_template_id}' references unknown "
                    "rollout_scope_class_id '"
                    f"{template.rollout_scope_class_id}'."
                )
        for template in self._rollback_trigger_templates:
            if (
                template.rollback_trigger_class_id
                not in self._rollback_trigger_classes
            ):
                raise ReleaseRegistryError(
                    "Rollback-trigger template '"
                    f"{template.rollback_trigger_template_id}' references unknown "
                    "rollback_trigger_class_id '"
                    f"{template.rollback_trigger_class_id}'."
                )
            if template.rollout_scope_class_id not in self._rollout_scope_classes:
                raise ReleaseRegistryError(
                    "Rollback-trigger template '"
                    f"{template.rollback_trigger_template_id}' references unknown "
                    "rollout_scope_class_id '"
                    f"{template.rollout_scope_class_id}'."
                )
        for template in self._release_watch_discipline_templates:
            if (
                template.release_watch_discipline_class_id
                not in self._release_watch_discipline_classes
            ):
                raise ReleaseRegistryError(
                    "Release-watch-discipline template '"
                    f"{template.release_watch_discipline_template_id}' references "
                    "unknown release_watch_discipline_class_id '"
                    f"{template.release_watch_discipline_class_id}'."
                )
            if (
                template.rollback_trigger_class_id
                not in self._rollback_trigger_classes
            ):
                raise ReleaseRegistryError(
                    "Release-watch-discipline template '"
                    f"{template.release_watch_discipline_template_id}' references "
                    "unknown rollback_trigger_class_id '"
                    f"{template.rollback_trigger_class_id}'."
                )
        for template in self._release_confirmation_templates:
            if (
                template.release_confirmation_class_id
                not in self._release_confirmation_classes
            ):
                raise ReleaseRegistryError(
                    "Release-confirmation template '"
                    f"{template.release_confirmation_template_id}' references "
                    "unknown release_confirmation_class_id '"
                    f"{template.release_confirmation_class_id}'."
                )
            if (
                template.release_watch_discipline_class_id
                not in self._release_watch_discipline_classes
            ):
                raise ReleaseRegistryError(
                    "Release-confirmation template '"
                    f"{template.release_confirmation_template_id}' references "
                    "unknown release_watch_discipline_class_id '"
                    f"{template.release_watch_discipline_class_id}'."
                )
        for template in self._production_entitlement_check_templates:
            if (
                template.production_entitlement_check_class_id
                not in self._production_entitlement_check_classes
            ):
                raise ReleaseRegistryError(
                    "Production-entitlement-check template '"
                    f"{template.production_entitlement_check_template_id}' references "
                    "unknown production_entitlement_check_class_id '"
                    f"{template.production_entitlement_check_class_id}'."
                )
            if (
                template.release_confirmation_class_id
                not in self._release_confirmation_classes
            ):
                raise ReleaseRegistryError(
                    "Production-entitlement-check template '"
                    f"{template.production_entitlement_check_template_id}' references "
                    "unknown release_confirmation_class_id '"
                    f"{template.release_confirmation_class_id}'."
                )
        for template in self._contained_rollback_templates:
            if (
                template.contained_rollback_class_id
                not in self._contained_rollback_classes
            ):
                raise ReleaseRegistryError(
                    "Contained-rollback template '"
                    f"{template.contained_rollback_template_id}' references "
                    "unknown contained_rollback_class_id '"
                    f"{template.contained_rollback_class_id}'."
                )
            if (
                template.production_entitlement_check_class_id
                not in self._production_entitlement_check_classes
            ):
                raise ReleaseRegistryError(
                    "Contained-rollback template '"
                    f"{template.contained_rollback_template_id}' references "
                    "unknown production_entitlement_check_class_id '"
                    f"{template.production_entitlement_check_class_id}'."
                )
        for template in self._release_audit_trace_templates:
            if (
                template.release_audit_trace_class_id
                not in self._release_audit_trace_classes
            ):
                raise ReleaseRegistryError(
                    "Release-audit-trace template '"
                    f"{template.release_audit_trace_template_id}' references "
                    "unknown release_audit_trace_class_id '"
                    f"{template.release_audit_trace_class_id}'."
                )
            if (
                template.contained_rollback_class_id
                not in self._contained_rollback_classes
            ):
                raise ReleaseRegistryError(
                    "Release-audit-trace template '"
                    f"{template.release_audit_trace_template_id}' references "
                    "unknown contained_rollback_class_id '"
                    f"{template.contained_rollback_class_id}'."
                )
