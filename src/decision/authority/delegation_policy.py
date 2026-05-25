from __future__ import annotations

"""Explicit delegation policy registry for governed authority reuse.

Canon ownership:
- Owns the machine-readable delegation policies that permit delegated authority.
- Does not itself decide lifecycle validity or route selection.
"""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping, Protocol, Sequence

from platform.validation.contract_schema_validator import ContractSchemaValidator

_REGISTRY_VALIDATION_CORRELATION_ID = "00000000-0000-0000-0000-000000000000"


class DelegationPolicyError(ValueError):
    """Base error for delegation-policy failures."""


class DelegationPolicyNotFoundError(DelegationPolicyError):
    """Raised when a delegation policy is not registered."""


@dataclass(frozen=True)
class DelegationPolicyDefinition:
    delegation_policy_id: str
    authority_rule_id: str
    delegating_role: str
    delegated_role: str
    authority_scope: str
    authority_ceiling: str
    authority_floor: str
    review_required: bool
    status: str
    lineage: Mapping[str, str]


class DelegationPolicyRegistry(Protocol):
    def find_policy(
        self,
        authority_rule_id: str,
        delegated_role: str,
    ) -> DelegationPolicyDefinition | None:
        """Return the active policy for a delegated role when it exists."""

    def list_policies_for_rule(self, authority_rule_id: str) -> Sequence[DelegationPolicyDefinition]:
        """Return all policies for the named authority rule."""


class JsonDelegationPolicyRegistry:
    """Loads explicit delegation policies from a checked-in registry."""

    def __init__(
        self,
        *,
        registry_path: Path,
        contract_validator: ContractSchemaValidator,
    ) -> None:
        content = json.loads(registry_path.read_text(encoding="utf-8"))
        self._policies_by_rule_and_role: dict[tuple[str, str], DelegationPolicyDefinition] = {}
        self._policies_by_rule: dict[str, list[DelegationPolicyDefinition]] = {}
        for delegation_policy_id, policy_entry in content["delegation_policies"].items():
            contract_validator.validate_or_raise(
                "delegation_policy",
                policy_entry,
                correlation_id=_REGISTRY_VALIDATION_CORRELATION_ID,
                entity_type="delegation_policy",
                entity_id=delegation_policy_id,
                emit_audit_events=False,
            )
            policy = DelegationPolicyDefinition(
                delegation_policy_id=policy_entry["delegation_policy_id"],
                authority_rule_id=policy_entry["authority_rule_id"],
                delegating_role=policy_entry["delegating_role"],
                delegated_role=policy_entry["delegated_role"],
                authority_scope=policy_entry["authority_scope"],
                authority_ceiling=policy_entry["authority_ceiling"],
                authority_floor=policy_entry["authority_floor"],
                review_required=bool(policy_entry["review_required"]),
                status=policy_entry["status"],
                lineage=dict(policy_entry["lineage"]),
            )
            key = (policy.authority_rule_id, policy.delegated_role)
            self._policies_by_rule_and_role[key] = policy
            self._policies_by_rule.setdefault(policy.authority_rule_id, []).append(policy)

    def find_policy(
        self,
        authority_rule_id: str,
        delegated_role: str,
    ) -> DelegationPolicyDefinition | None:
        return self._policies_by_rule_and_role.get((authority_rule_id, delegated_role))

    def list_policies_for_rule(self, authority_rule_id: str) -> Sequence[DelegationPolicyDefinition]:
        return tuple(self._policies_by_rule.get(authority_rule_id, ()))
