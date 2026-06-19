from __future__ import annotations

"""Registry-backed authority rules and roles for governed decision rights.

Canon ownership:
- Owns decision-right meaning, authority scope, ceiling and floor metadata,
  and registry-backed role identity for the control-plane slice.
- Does not decide lifecycle legitimacy, routing precedence, or review posture.
"""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping, Protocol

from ff_platform.validation.contract_schema_validator import ContractSchemaValidator

_REGISTRY_VALIDATION_CORRELATION_ID = "00000000-0000-0000-0000-000000000000"


class AuthorityRegistryError(ValueError):
    """Base error for authority registry failures."""


class AuthorityRuleNotFoundError(AuthorityRegistryError):
    """Raised when an authority rule is not registered."""


class AuthorityRoleNotFoundError(AuthorityRegistryError):
    """Raised when an authority role is not registered."""


@dataclass(frozen=True)
class AuthorityRoleDefinition:
    role_id: str
    authority_scope: str
    authority_ceiling: str
    authority_floor: str
    status: str
    lineage: Mapping[str, str]


@dataclass(frozen=True)
class AuthorityRuleDefinition:
    authority_rule_id: str
    decision_right: str
    allowed_roles: tuple[str, ...]
    delegated_roles: tuple[str, ...]
    authority_scope: str
    authority_ceiling: str
    authority_floor: str
    fallback_role: str | None
    review_required: bool
    status: str
    lineage: Mapping[str, str]


class AuthorityRegistry(Protocol):
    def get_authority_rule(self, authority_rule_id: str) -> AuthorityRuleDefinition:
        """Return the named authority rule."""

    def get_authority_role(self, role_id: str) -> AuthorityRoleDefinition:
        """Return the named authority role."""


class JsonAuthorityRegistry:
    """Loads authority rules and role metadata from checked-in registries."""

    def __init__(
        self,
        *,
        rules_path: Path,
        roles_path: Path,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        self._contract_validator = contract_validator
        self._roles = self._load_roles(roles_path)
        self._rules = self._load_rules(rules_path)

    def get_authority_rule(self, authority_rule_id: str) -> AuthorityRuleDefinition:
        try:
            return self._rules[authority_rule_id]
        except KeyError as error:
            raise AuthorityRuleNotFoundError(
                f"Authority rule '{authority_rule_id}' is not registered."
            ) from error

    def get_authority_role(self, role_id: str) -> AuthorityRoleDefinition:
        try:
            return self._roles[role_id]
        except KeyError as error:
            raise AuthorityRoleNotFoundError(f"Authority role '{role_id}' is not registered.") from error

    def _load_roles(self, roles_path: Path) -> dict[str, AuthorityRoleDefinition]:
        content = json.loads(roles_path.read_text(encoding="utf-8"))
        roles: dict[str, AuthorityRoleDefinition] = {}
        for role_id, role_entry in content["authority_roles"].items():
            self._validate_role_entry(role_id, role_entry)
            roles[role_id] = AuthorityRoleDefinition(
                role_id=role_entry["role_id"],
                authority_scope=role_entry["authority_scope"],
                authority_ceiling=role_entry["authority_ceiling"],
                authority_floor=role_entry["authority_floor"],
                status=role_entry["status"],
                lineage=dict(role_entry["lineage"]),
            )
        return roles

    def _load_rules(self, rules_path: Path) -> dict[str, AuthorityRuleDefinition]:
        content = json.loads(rules_path.read_text(encoding="utf-8"))
        rules: dict[str, AuthorityRuleDefinition] = {}
        for authority_rule_id, rule_entry in content["authority_rules"].items():
            self._contract_validator.validate_or_raise(
                "authority_rule",
                rule_entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="authority_rule",
                entity_id=authority_rule_id,
                emit_audit_events=False,
            )
            rule = AuthorityRuleDefinition(
                authority_rule_id=rule_entry["authority_rule_id"],
                decision_right=rule_entry["decision_right"],
                allowed_roles=tuple(rule_entry["allowed_roles"]),
                delegated_roles=tuple(rule_entry["delegated_roles"]),
                authority_scope=rule_entry["authority_scope"],
                authority_ceiling=rule_entry["authority_ceiling"],
                authority_floor=rule_entry["authority_floor"],
                fallback_role=rule_entry.get("fallback_role"),
                review_required=bool(rule_entry["review_required"]),
                status=rule_entry["status"],
                lineage=dict(rule_entry["lineage"]),
            )
            self._validate_rule_roles(rule)
            rules[authority_rule_id] = rule
        return rules

    def _validate_role_entry(self, role_id: str, role_entry: Mapping[str, Any]) -> None:
        required_keys = {
            "role_id",
            "authority_scope",
            "authority_ceiling",
            "authority_floor",
            "status",
            "lineage",
        }
        missing = required_keys.difference(role_entry)
        if missing:
            raise AuthorityRegistryError(
                f"Authority role '{role_id}' is missing required keys: {sorted(missing)}"
            )
        if role_entry["role_id"] != role_id:
            raise AuthorityRegistryError(
                f"Authority role key '{role_id}' must match role_id '{role_entry['role_id']}'."
            )
        if role_entry["status"] not in {"active", "deprecated"}:
            raise AuthorityRegistryError(
                f"Authority role '{role_id}' has invalid status '{role_entry['status']}'."
            )
        lineage = role_entry["lineage"]
        if not isinstance(lineage, dict) or "version" not in lineage:
            raise AuthorityRegistryError(
                f"Authority role '{role_id}' must provide lineage.version metadata."
            )

    def _validate_rule_roles(self, rule: AuthorityRuleDefinition) -> None:
        for role_id in (*rule.allowed_roles, *rule.delegated_roles):
            if role_id not in self._roles:
                raise AuthorityRegistryError(
                    f"Authority rule '{rule.authority_rule_id}' references unknown role '{role_id}'."
                )
        if rule.fallback_role is not None and rule.fallback_role not in self._roles:
            raise AuthorityRegistryError(
                f"Authority rule '{rule.authority_rule_id}' references unknown fallback_role '{rule.fallback_role}'."
            )
