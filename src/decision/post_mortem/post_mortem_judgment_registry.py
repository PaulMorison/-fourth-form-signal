from __future__ import annotations

"""Registry-backed post-mortem judgment classes and templates.

Canon ownership:
- Owns governed post-mortem judgment identity and template identity for the
  attribution layer that sits downstream of legitimate execution outcomes.
- Does not redefine execution outcome meaning, monitoring, reopen decisions,
  or policy-learning admission.
"""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping, Protocol

from platform.validation.contract_schema_validator import ContractSchemaValidator

_REGISTRY_VALIDATION_CORRELATION_ID = "00000000-0000-0000-0000-000000000000"
_VALID_STATUS = {"active", "deprecated"}
_VALID_ATTRIBUTION_CATEGORIES = {
    "correct_recommendation_correct_execution",
    "correct_recommendation_weak_execution",
    "correct_recommendation_environment_changed",
    "weak_recommendation_good_execution",
    "weak_recommendation_weak_causal_logic",
    "weak_recommendation_poor_local_state_capture",
    "weak_recommendation_simulation_miss",
    "weak_recommendation_constraint_miss",
    "override_improved_outcome",
    "override_worsened_outcome",
    "insufficient_evidence_for_confident_judgment",
}
_VALID_POST_MORTEM_STATUSES = {
    "ready_for_downstream_use",
    "fallback_template_applied",
}


class PostMortemJudgmentRegistryError(ValueError):
    """Base error for post-mortem registry failures."""


@dataclass(frozen=True)
class PostMortemJudgmentClassDefinition:
    post_mortem_judgment_class_id: str
    description: str
    primary_attribution_category: str
    allowed_execution_outcome_class_ids: tuple[str, ...]
    prohibited_judgment_fields: tuple[str, ...]
    status: str
    lineage: Mapping[str, str]


@dataclass(frozen=True)
class PostMortemJudgmentTemplateDefinition:
    post_mortem_judgment_template_id: str
    semantic_scope: str
    execution_outcome_class_id: str
    post_mortem_judgment_class_id: str
    required_post_mortem_fields: tuple[str, ...]
    optional_post_mortem_fields: tuple[str, ...]
    required_audit_fields: tuple[str, ...]
    post_mortem_status: str
    status: str
    lineage: Mapping[str, str]
    route_name: str | None = None


class PostMortemJudgmentRegistry(Protocol):
    def resolve_template(
        self,
        *,
        semantic_scope: str,
        execution_outcome_class_id: str,
        post_mortem_judgment_class_id: str,
        route_name: str | None,
    ) -> tuple[PostMortemJudgmentTemplateDefinition, bool]:
        """Return the matching post-mortem template and fallback status."""

    def get_post_mortem_judgment_class(
        self,
        post_mortem_judgment_class_id: str,
    ) -> PostMortemJudgmentClassDefinition:
        """Return the named post-mortem judgment class."""


class JsonPostMortemJudgmentRegistry:
    """Loads post-mortem judgment classes and templates from registries."""

    def __init__(
        self,
        *,
        post_mortem_judgment_classes_path: Path,
        post_mortem_judgment_templates_path: Path,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._contract_validator = contract_validator
        self._post_mortem_judgment_classes = self._load_classes(
            post_mortem_judgment_classes_path
        )
        self._post_mortem_judgment_templates = self._load_templates(
            post_mortem_judgment_templates_path
        )
        self._validate_cross_registry_links()

    def resolve_template(
        self,
        *,
        semantic_scope: str,
        execution_outcome_class_id: str,
        post_mortem_judgment_class_id: str,
        route_name: str | None,
    ) -> tuple[PostMortemJudgmentTemplateDefinition, bool]:
        exact_matches = tuple(
            template
            for template in self._post_mortem_judgment_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.execution_outcome_class_id == execution_outcome_class_id
            and template.post_mortem_judgment_class_id == post_mortem_judgment_class_id
            and template.route_name == route_name
        )
        if exact_matches:
            template = sorted(
                exact_matches,
                key=lambda item: item.post_mortem_judgment_template_id,
            )[0]
            return template, template.post_mortem_status == "fallback_template_applied"

        generic_matches = tuple(
            template
            for template in self._post_mortem_judgment_templates
            if template.status == "active"
            and template.semantic_scope == semantic_scope
            and template.execution_outcome_class_id == execution_outcome_class_id
            and template.post_mortem_judgment_class_id == post_mortem_judgment_class_id
            and template.route_name is None
        )
        if generic_matches:
            template = sorted(
                generic_matches,
                key=lambda item: item.post_mortem_judgment_template_id,
            )[0]
            return template, template.post_mortem_status == "fallback_template_applied"

        raise PostMortemJudgmentRegistryError(
            "No governed post-mortem template applies to post_mortem_judgment_class_id="
            f"'{post_mortem_judgment_class_id}' for execution_outcome_class_id="
            f"'{execution_outcome_class_id}' and route_name='{route_name}'."
        )

    def get_post_mortem_judgment_class(
        self,
        post_mortem_judgment_class_id: str,
    ) -> PostMortemJudgmentClassDefinition:
        try:
            return self._post_mortem_judgment_classes[post_mortem_judgment_class_id]
        except KeyError as error:
            raise PostMortemJudgmentRegistryError(
                "Post-mortem judgment class "
                f"'{post_mortem_judgment_class_id}' is not registered."
            ) from error

    def _load_classes(
        self,
        post_mortem_judgment_classes_path: Path,
    ) -> dict[str, PostMortemJudgmentClassDefinition]:
        content = json.loads(post_mortem_judgment_classes_path.read_text(encoding="utf-8"))
        class_definitions: dict[str, PostMortemJudgmentClassDefinition] = {}
        for class_id, entry in content["post_mortem_judgment_classes"].items():
            self._contract_validator.validate_or_raise(
                "post_mortem_judgment_class",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="post_mortem_judgment_class",
                entity_id=class_id,
                emit_audit_events=False,
            )
            if entry["post_mortem_judgment_class_id"] != class_id:
                raise PostMortemJudgmentRegistryError(
                    "Post-mortem judgment class key "
                    f"'{class_id}' must match post_mortem_judgment_class_id "
                    f"'{entry['post_mortem_judgment_class_id']}'."
                )
            if entry["status"] not in _VALID_STATUS:
                raise PostMortemJudgmentRegistryError(
                    f"Post-mortem judgment class '{class_id}' has invalid status '{entry['status']}'."
                )
            if entry["primary_attribution_category"] not in _VALID_ATTRIBUTION_CATEGORIES:
                raise PostMortemJudgmentRegistryError(
                    "Post-mortem judgment class "
                    f"'{class_id}' has invalid primary_attribution_category "
                    f"'{entry['primary_attribution_category']}'."
                )
            class_definitions[class_id] = PostMortemJudgmentClassDefinition(
                post_mortem_judgment_class_id=entry["post_mortem_judgment_class_id"],
                description=entry["description"],
                primary_attribution_category=entry["primary_attribution_category"],
                allowed_execution_outcome_class_ids=tuple(
                    entry["allowed_execution_outcome_class_ids"]
                ),
                prohibited_judgment_fields=tuple(entry["prohibited_judgment_fields"]),
                status=entry["status"],
                lineage=dict(entry["lineage"]),
            )
        return class_definitions

    def _load_templates(
        self,
        post_mortem_judgment_templates_path: Path,
    ) -> tuple[PostMortemJudgmentTemplateDefinition, ...]:
        content = json.loads(post_mortem_judgment_templates_path.read_text(encoding="utf-8"))
        templates: list[PostMortemJudgmentTemplateDefinition] = []
        template_ids: set[str] = set()
        for template_id, entry in content["post_mortem_judgment_templates"].items():
            self._contract_validator.validate_or_raise(
                "post_mortem_judgment_template",
                entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="post_mortem_judgment_template",
                entity_id=template_id,
                emit_audit_events=False,
            )
            if entry["post_mortem_judgment_template_id"] != template_id:
                raise PostMortemJudgmentRegistryError(
                    "Post-mortem judgment template key "
                    f"'{template_id}' must match post_mortem_judgment_template_id "
                    f"'{entry['post_mortem_judgment_template_id']}'."
                )
            if template_id in template_ids:
                raise PostMortemJudgmentRegistryError(
                    "Duplicate post_mortem_judgment_template_id "
                    f"'{template_id}' found in post-mortem template registry."
                )
            if entry["status"] not in _VALID_STATUS:
                raise PostMortemJudgmentRegistryError(
                    f"Post-mortem judgment template '{template_id}' has invalid status '{entry['status']}'."
                )
            if entry["post_mortem_status"] not in _VALID_POST_MORTEM_STATUSES:
                raise PostMortemJudgmentRegistryError(
                    "Post-mortem judgment template "
                    f"'{template_id}' has invalid post_mortem_status "
                    f"'{entry['post_mortem_status']}'."
                )
            templates.append(
                PostMortemJudgmentTemplateDefinition(
                    post_mortem_judgment_template_id=entry[
                        "post_mortem_judgment_template_id"
                    ],
                    semantic_scope=entry["semantic_scope"],
                    execution_outcome_class_id=entry["execution_outcome_class_id"],
                    post_mortem_judgment_class_id=entry[
                        "post_mortem_judgment_class_id"
                    ],
                    required_post_mortem_fields=tuple(
                        entry["required_post_mortem_fields"]
                    ),
                    optional_post_mortem_fields=tuple(
                        entry["optional_post_mortem_fields"]
                    ),
                    required_audit_fields=tuple(entry["required_audit_fields"]),
                    post_mortem_status=entry["post_mortem_status"],
                    status=entry["status"],
                    lineage=dict(entry["lineage"]),
                    route_name=entry.get("route_name"),
                )
            )
            template_ids.add(template_id)
        return tuple(templates)

    def _validate_cross_registry_links(self) -> None:
        for template in self._post_mortem_judgment_templates:
            class_definition = self._post_mortem_judgment_classes.get(
                template.post_mortem_judgment_class_id
            )
            if class_definition is None:
                raise PostMortemJudgmentRegistryError(
                    "Post-mortem judgment template "
                    f"'{template.post_mortem_judgment_template_id}' references unknown "
                    f"post_mortem_judgment_class_id '{template.post_mortem_judgment_class_id}'."
                )
            if class_definition.status != "active":
                raise PostMortemJudgmentRegistryError(
                    "Post-mortem judgment template "
                    f"'{template.post_mortem_judgment_template_id}' references inactive "
                    f"post-mortem class '{template.post_mortem_judgment_class_id}'."
                )
            if (
                template.execution_outcome_class_id
                not in class_definition.allowed_execution_outcome_class_ids
            ):
                raise PostMortemJudgmentRegistryError(
                    "Post-mortem judgment template "
                    f"'{template.post_mortem_judgment_template_id}' uses execution_outcome_class_id "
                    f"'{template.execution_outcome_class_id}' outside post-mortem class "
                    f"'{template.post_mortem_judgment_class_id}' allowances."
                )
            if not template.required_post_mortem_fields:
                raise PostMortemJudgmentRegistryError(
                    "Post-mortem judgment template "
                    f"'{template.post_mortem_judgment_template_id}' must declare at least one required_post_mortem_field."
                )
            if not template.required_audit_fields:
                raise PostMortemJudgmentRegistryError(
                    "Post-mortem judgment template "
                    f"'{template.post_mortem_judgment_template_id}' must declare at least one required_audit_field."
                )