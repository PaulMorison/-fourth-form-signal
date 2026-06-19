from __future__ import annotations

from pathlib import Path
import sys
import unittest
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from decision.authority import (  # noqa: E402
    AuthorityAuditAdapter,
    AuthorityResolutionRequest,
    AuthorityResolutionService,
    JsonAuthorityRegistry,
    JsonDelegationPolicyRegistry,
)
from ff_platform.audit.audit_event_store import (  # noqa: E402
    AuditEventStore,
    InMemoryAuditEventRepository,
    JsonAuditEventTypeRegistry,
)
from ff_platform.validation.contract_schema_validator import (  # noqa: E402
    ContractSchemaValidator,
    JsonContractSchemaRepository,
)


class AuthorityServiceLayerTests(unittest.TestCase):
    def setUp(self) -> None:
        registry_root = REPO_ROOT / "registries" / "control_plane"
        schema_repository = JsonContractSchemaRepository(
            REPO_ROOT,
            registry_root / "contract_schemas.json",
        )
        self.contract_validator = ContractSchemaValidator(schema_repository=schema_repository)
        self.audit_store = AuditEventStore(
            event_type_registry=JsonAuditEventTypeRegistry(
                registry_root / "audit_event_types.json"
            ),
            repository=InMemoryAuditEventRepository(),
            contract_validator=self.contract_validator,
        )
        self.contract_validator.set_audit_sink(self.audit_store)

        authority_registry = JsonAuthorityRegistry(
            rules_path=registry_root / "authority_rules.json",
            roles_path=registry_root / "authority_roles.json",
            contract_validator=self.contract_validator,
        )
        delegation_policy_registry = JsonDelegationPolicyRegistry(
            registry_path=registry_root / "delegation_policies.json",
            contract_validator=self.contract_validator,
        )
        authority_audit_adapter = AuthorityAuditAdapter(
            audit_event_store=self.audit_store,
            contract_validator=self.contract_validator,
        )
        self.service = AuthorityResolutionService(
            authority_registry=authority_registry,
            delegation_policy_registry=delegation_policy_registry,
            authority_audit_adapter=authority_audit_adapter,
        )
        self.state_sequence = (
            "raw_intake_ready",
            "feature_review_ready",
            "case_assessment_active",
            "case_interrupted",
        )

    def test_direct_authority_success(self) -> None:
        resolution = self.service.resolve(self._request(actor_role="case_operator", current_state="feature_review_ready", target_state="case_assessment_active", transition_name="promote_to_case_assessment"))

        self.assertTrue(resolution.accepted)
        self.assertEqual(resolution.resolution_kind, "direct")

    def test_delegated_authority_success(self) -> None:
        resolution = self.service.resolve(self._request(actor_role="assistant_case_operator"))

        self.assertTrue(resolution.accepted)
        self.assertEqual(resolution.resolution_kind, "delegated")
        self.assertEqual(resolution.grant_source_role, "case_operator")

    def test_wrong_role_is_blocked(self) -> None:
        resolution = self.service.resolve(self._request(actor_role="observer"))

        self.assertFalse(resolution.accepted)
        self.assertEqual(resolution.resolution_kind, "blocked")

    def test_fallback_authority_application(self) -> None:
        resolution = self.service.resolve(
            self._request(
                actor_role="case_supervisor",
                current_state="case_assessment_active",
                target_state="feature_review_ready",
                transition_name="fallback_to_feature_review",
                transition_class="fallback",
            )
        )

        self.assertTrue(resolution.accepted)
        self.assertEqual(resolution.resolution_kind, "fallback")

    def test_scope_violation_is_blocked(self) -> None:
        resolution = self.service.resolve(
            self._request(
                actor_role="assistant_case_operator",
                current_state="feature_review_ready",
                target_state="case_assessment_active",
                transition_name="promote_to_case_assessment",
            )
        )

        self.assertFalse(resolution.accepted)
        self.assertEqual(resolution.resolution_kind, "scope_violation")

    def test_authority_audit_events_cover_outcomes(self) -> None:
        self.service.resolve(self._request(actor_role="case_operator", current_state="feature_review_ready", target_state="case_assessment_active", transition_name="promote_to_case_assessment"))
        self.service.resolve(self._request(actor_role="assistant_case_operator"))
        self.service.resolve(self._request(actor_role="shadow_case_delegate"))
        self.service.resolve(
            self._request(
                actor_role="assistant_case_operator",
                current_state="feature_review_ready",
                target_state="case_assessment_active",
                transition_name="promote_to_case_assessment",
            )
        )
        self.service.resolve(
            self._request(
                actor_role="case_supervisor",
                current_state="case_assessment_active",
                target_state="feature_review_ready",
                transition_name="fallback_to_feature_review",
                transition_class="fallback",
            )
        )
        self.service.resolve(self._request(actor_role="observer"))

        event_types = [event.event_type for event in self.audit_store.list_events()]
        self.assertIn("decision.authority.authority_resolution_succeeded", event_types)
        self.assertIn("decision.authority.authority_resolution_blocked", event_types)
        self.assertIn("decision.authority.delegation_applied", event_types)
        self.assertIn("decision.authority.delegation_missing", event_types)
        self.assertIn("decision.authority.authority_scope_violation", event_types)
        self.assertIn("decision.authority.authority_fallback_applied", event_types)

    def _request(
        self,
        *,
        actor_role: str,
        current_state: str = "raw_intake_ready",
        target_state: str = "feature_review_ready",
        transition_name: str = "promote_to_feature_review",
        transition_class: str = "forward_progression",
    ) -> AuthorityResolutionRequest:
        return AuthorityResolutionRequest(
            authority_rule_id="case_transition_operator",
            actor_role=actor_role,
            authority_scope="shared_control_plane",
            current_state=current_state,
            target_state=target_state,
            state_sequence=self.state_sequence,
            transition_name=transition_name,
            transition_class=transition_class,
            correlation_id=str(uuid4()),
            episode_id=str(uuid4()),
            actor_id="authority-test",
        )


if __name__ == "__main__":
    unittest.main()