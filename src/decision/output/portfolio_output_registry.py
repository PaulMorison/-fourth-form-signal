from __future__ import annotations

"""Registry-backed portfolio-output classes and portfolio-output templates.

Canon ownership:
- Owns governed portfolio-output identity and template identity for bounded
  portfolio objects emitted after legitimate policy outputs.
- Does not execute commitment issuance, action-instruction issuance, playbook
  execution, reopen handling, router meaning, review meaning, or authority
  meaning.
"""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping, Protocol

from platform.validation.contract_schema_validator import ContractSchemaValidator

_REGISTRY_VALIDATION_CORRELATION_ID = "00000000-0000-0000-0000-000000000000"
_VALID_STATUS = {"active", "deprecated"}
_VALID_ALLOCATION_POSTURES = {
    "bounded_allocation",
    "ranked_preference",
    "suppression_hold",
}
_VALID_WEIGHT_POSTURES = {
    "weighted_allocation",
    "priority_rank_only",
    "not_applicable",
}
_VALID_ACTION_BOUNDARY_POSTURES = {
    "allocative_non_instructional",
    "policy_shaped_non_instructional",
}
_VALID_PROMOTION_SAFE_USE = {"promotion_safe_output"}
_VALID_PORTFOLIO_OUTPUT_STATUSES = {
    "ready_for_downstream_use",
    "fallback_template_applied",
}


class PortfolioOutputRegistryError(ValueError):
    """Base error for portfolio-output registry failures."""


@dataclass(frozen=True)
class PortfolioOutputClassDefinition:
    portfolio_output_class_id: str
    description: str
    allocation_posture: str
    weight_posture: str
    action_boundary_posture: str
    promotion_safe_use: str
    allowed_policy_output_class_ids: tuple[str, ...]
    allowed_recommendation_class_ids: tuple[str, ...]
    allowed_resolution_class_ids: tuple[str, ...]
    allowed_disposition_class_ids: tuple[str, ...]
    prohibited_context_fields: tuple[str, ...]
    status: str
    lineage: Mapping[str, str]


@dataclass(frozen=True)
class PortfolioOutputTemplateDefinition:
    portfolio_output_template_id: str
    semantic_scope: str
    resolution_class_id: str
    disposition_class_id: str
    recommendation_class_id: str
    policy_output_class_id: str
    portfolio_output_class_id: str
    required_context_fields: tuple[str, ...]
    optional_context_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    portfolio_output_status: str
    status: str
    lineage: Mapping[str, str]
    route_name: str | None = None


class PortfolioOutputRegistry(Protocol):
    def resolve_template(
        self,
        *,
        semantic_scope: str,
        resolution_class_id: str,
        disposition_class_id: str,
        recommendation_class_id: str,
        policy_output_class_id: str,
        portfolio_output_class_id: str,
        route_name: str | None,
    ) -> tuple[PortfolioOutputTemplateDefinition, bool]:
        """Return the matching portfolio-output template and fallback status."""

    def get_portfolio_output_class(
        self,
        portfolio_output_class_id: str,
    ) -> PortfolioOutputClassDefinition:
        """Return the named portfolio-output class."""


class JsonPortfolioOutputRegistry:
    """Loads portfolio-output classes and templates from checked-in registries."""

    def __init__(
        self,
        *,
        portfolio_output_classes_path: Path,
        portfolio_output_templates_path: Path,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._contract_validator = contract_validator
        self._portfolio_output_classes = self._load_portfolio_output_classes(
            portfolio_output_classes_path
        )
        self._portfolio_output_templates = self._load_portfolio_output_templates(
            portfolio_output_templates_path
        )
        self._validate_cross_registry_links()

    def resolve_template(
        self,
        *,
        semantic_scope: str,
        resolution_class_id: str,
        disposition_class_id: str,
        recommendation_class_id: str,
        policy_output_class_id: str,
        portfolio_output_class_id: str,
        route_name: str | None,
    ) -> tuple[PortfolioOutputTemplateDefinition, bool]:
        exact_matches = tuple(
            template
            for template in self._portfolio_output_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.resolution_class_id == resolution_class_id
            and template.disposition_class_id == disposition_class_id
            and template.recommendation_class_id == recommendation_class_id
            and template.policy_output_class_id == policy_output_class_id
            and template.portfolio_output_class_id == portfolio_output_class_id
            and template.route_name == route_name
        )
        if exact_matches:
            template = sorted(
                exact_matches,
                key=lambda item: item.portfolio_output_template_id,
            )[0]
            return template, template.portfolio_output_status == "fallback_template_applied"

        generic_matches = tuple(
            template
            for template in self._portfolio_output_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.resolution_class_id == resolution_class_id
            and template.disposition_class_id == disposition_class_id
            and template.recommendation_class_id == recommendation_class_id
            and template.policy_output_class_id == policy_output_class_id
            and template.portfolio_output_class_id == portfolio_output_class_id
            and template.route_name is None
        )
        if generic_matches:
            template = sorted(
                generic_matches,
                key=lambda item: item.portfolio_output_template_id,
            )[0]
            return template, template.portfolio_output_status == "fallback_template_applied"

        raise PortfolioOutputRegistryError(
            "No governed portfolio-output template applies to portfolio_output_class_id="
            f"'{portfolio_output_class_id}' for policy_output_class_id='{policy_output_class_id}', "
            f"recommendation_class_id='{recommendation_class_id}', resolution_class_id='{resolution_class_id}', "
            f"disposition_class_id='{disposition_class_id}', route_name='{route_name}'."
        )

    def get_portfolio_output_class(
        self,
        portfolio_output_class_id: str,
    ) -> PortfolioOutputClassDefinition:
        try:
            return self._portfolio_output_classes[portfolio_output_class_id]
        except KeyError as error:
            raise PortfolioOutputRegistryError(
                f"Portfolio output class '{portfolio_output_class_id}' is not registered."
            ) from error

    def _load_portfolio_output_classes(
        self,
        portfolio_output_classes_path: Path,
    ) -> dict[str, PortfolioOutputClassDefinition]:
        content = json.loads(portfolio_output_classes_path.read_text(encoding="utf-8"))
        portfolio_output_classes: dict[str, PortfolioOutputClassDefinition] = {}
        for class_id, entry in content["portfolio_output_classes"].items():
            self._contract_validator.validate_or_raise(
                "portfolio_output_class",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="portfolio_output_class",
                entity_id=class_id,
                emit_audit_events=False,
            )
            if entry["portfolio_output_class_id"] != class_id:
                raise PortfolioOutputRegistryError(
                    f"Portfolio output class key '{class_id}' must match portfolio_output_class_id '{entry['portfolio_output_class_id']}'."
                )
            if entry["status"] not in _VALID_STATUS:
                raise PortfolioOutputRegistryError(
                    f"Portfolio output class '{class_id}' has invalid status '{entry['status']}'."
                )
            if entry["allocation_posture"] not in _VALID_ALLOCATION_POSTURES:
                raise PortfolioOutputRegistryError(
                    f"Portfolio output class '{class_id}' has invalid allocation_posture '{entry['allocation_posture']}'."
                )
            if entry["weight_posture"] not in _VALID_WEIGHT_POSTURES:
                raise PortfolioOutputRegistryError(
                    f"Portfolio output class '{class_id}' has invalid weight_posture '{entry['weight_posture']}'."
                )
            if entry["action_boundary_posture"] not in _VALID_ACTION_BOUNDARY_POSTURES:
                raise PortfolioOutputRegistryError(
                    f"Portfolio output class '{class_id}' has invalid action_boundary_posture '{entry['action_boundary_posture']}'."
                )
            if entry["promotion_safe_use"] not in _VALID_PROMOTION_SAFE_USE:
                raise PortfolioOutputRegistryError(
                    f"Portfolio output class '{class_id}' has invalid promotion_safe_use '{entry['promotion_safe_use']}'."
                )
            portfolio_output_classes[class_id] = PortfolioOutputClassDefinition(
                portfolio_output_class_id=entry["portfolio_output_class_id"],
                description=entry["description"],
                allocation_posture=entry["allocation_posture"],
                weight_posture=entry["weight_posture"],
                action_boundary_posture=entry["action_boundary_posture"],
                promotion_safe_use=entry["promotion_safe_use"],
                allowed_policy_output_class_ids=tuple(
                    entry["allowed_policy_output_class_ids"]
                ),
                allowed_recommendation_class_ids=tuple(
                    entry["allowed_recommendation_class_ids"]
                ),
                allowed_resolution_class_ids=tuple(entry["allowed_resolution_class_ids"]),
                allowed_disposition_class_ids=tuple(
                    entry["allowed_disposition_class_ids"]
                ),
                prohibited_context_fields=tuple(entry["prohibited_context_fields"]),
                status=entry["status"],
                lineage=dict(entry["lineage"]),
            )
        return portfolio_output_classes

    def _load_portfolio_output_templates(
        self,
        portfolio_output_templates_path: Path,
    ) -> tuple[PortfolioOutputTemplateDefinition, ...]:
        content = json.loads(portfolio_output_templates_path.read_text(encoding="utf-8"))
        portfolio_output_templates: list[PortfolioOutputTemplateDefinition] = []
        template_ids: set[str] = set()
        for template_id, entry in content["portfolio_output_templates"].items():
            self._contract_validator.validate_or_raise(
                "portfolio_output_template",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="portfolio_output_template",
                entity_id=template_id,
                emit_audit_events=False,
            )
            if entry["portfolio_output_template_id"] != template_id:
                raise PortfolioOutputRegistryError(
                    f"Portfolio output template key '{template_id}' must match portfolio_output_template_id '{entry['portfolio_output_template_id']}'."
                )
            if template_id in template_ids:
                raise PortfolioOutputRegistryError(
                    f"Duplicate portfolio_output_template_id '{template_id}' found in portfolio output template registry."
                )
            if entry["status"] not in _VALID_STATUS:
                raise PortfolioOutputRegistryError(
                    f"Portfolio output template '{template_id}' has invalid status '{entry['status']}'."
                )
            if entry["portfolio_output_status"] not in _VALID_PORTFOLIO_OUTPUT_STATUSES:
                raise PortfolioOutputRegistryError(
                    f"Portfolio output template '{template_id}' has invalid portfolio_output_status '{entry['portfolio_output_status']}'."
                )
            portfolio_output_templates.append(
                PortfolioOutputTemplateDefinition(
                    portfolio_output_template_id=entry["portfolio_output_template_id"],
                    semantic_scope=entry["semantic_scope"],
                    resolution_class_id=entry["resolution_class_id"],
                    disposition_class_id=entry["disposition_class_id"],
                    recommendation_class_id=entry["recommendation_class_id"],
                    policy_output_class_id=entry["policy_output_class_id"],
                    portfolio_output_class_id=entry["portfolio_output_class_id"],
                    required_context_fields=tuple(entry["required_context_fields"]),
                    optional_context_fields=tuple(entry["optional_context_fields"]),
                    required_audit_fields=tuple(entry["required_audit_fields"]),
                    portfolio_output_status=entry["portfolio_output_status"],
                    status=entry["status"],
                    lineage=dict(entry["lineage"]),
                    route_name=entry.get("route_name"),
                )
            )
            template_ids.add(template_id)
        return tuple(portfolio_output_templates)

    def _validate_cross_registry_links(self) -> None:
        for template in self._portfolio_output_templates:
            portfolio_output_class = self._portfolio_output_classes.get(
                template.portfolio_output_class_id
            )
            if portfolio_output_class is None:
                raise PortfolioOutputRegistryError(
                    f"Portfolio output template '{template.portfolio_output_template_id}' references unknown portfolio_output_class_id '{template.portfolio_output_class_id}'."
                )
            if portfolio_output_class.status != "active":
                raise PortfolioOutputRegistryError(
                    f"Portfolio output template '{template.portfolio_output_template_id}' references inactive portfolio output class '{template.portfolio_output_class_id}'."
                )
            if (
                template.policy_output_class_id
                not in portfolio_output_class.allowed_policy_output_class_ids
            ):
                raise PortfolioOutputRegistryError(
                    f"Portfolio output template '{template.portfolio_output_template_id}' uses policy_output_class_id '{template.policy_output_class_id}' outside portfolio output class '{template.portfolio_output_class_id}' allowances."
                )
            if (
                template.recommendation_class_id
                not in portfolio_output_class.allowed_recommendation_class_ids
            ):
                raise PortfolioOutputRegistryError(
                    f"Portfolio output template '{template.portfolio_output_template_id}' uses recommendation_class_id '{template.recommendation_class_id}' outside portfolio output class '{template.portfolio_output_class_id}' allowances."
                )
            if (
                template.resolution_class_id
                not in portfolio_output_class.allowed_resolution_class_ids
            ):
                raise PortfolioOutputRegistryError(
                    f"Portfolio output template '{template.portfolio_output_template_id}' uses resolution_class_id '{template.resolution_class_id}' outside portfolio output class '{template.portfolio_output_class_id}' allowances."
                )
            if (
                template.disposition_class_id
                not in portfolio_output_class.allowed_disposition_class_ids
            ):
                raise PortfolioOutputRegistryError(
                    f"Portfolio output template '{template.portfolio_output_template_id}' uses disposition_class_id '{template.disposition_class_id}' outside portfolio output class '{template.portfolio_output_class_id}' allowances."
                )
            if not template.required_context_fields:
                raise PortfolioOutputRegistryError(
                    f"Portfolio output template '{template.portfolio_output_template_id}' must declare at least one required_context_field."
                )
            if not template.required_audit_fields:
                raise PortfolioOutputRegistryError(
                    f"Portfolio output template '{template.portfolio_output_template_id}' must declare at least one required_audit_field."
                )
            if not portfolio_output_class.prohibited_context_fields:
                raise PortfolioOutputRegistryError(
                    f"Portfolio output class '{portfolio_output_class.portfolio_output_class_id}' must declare at least one prohibited_context_field."
                )