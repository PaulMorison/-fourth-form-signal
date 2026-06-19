from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sys
import unittest
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from data.ingestion.raw_ingestion_pipeline import (  # noqa: E402
    InMemoryRawRecordRepository,
    JsonIngestionSourceRegistry,
    RawIngestionCommand,
    RawIngestionPipeline,
)
from decision.authority import (  # noqa: E402
    AuthorityAuditAdapter,
    AuthorityResolutionService,
    JsonAuthorityRegistry,
    JsonDelegationPolicyRegistry,
)
from decision.case.case_state_manager import CaseStateManager  # noqa: E402
from decision.case.case_transition_audit_adapter import CaseTransitionAuditAdapter  # noqa: E402
from decision.case.case_episode_orchestrator import (  # noqa: E402
    CaseEpisodeOrchestrator,
    InMemoryCaseEpisodeRepository,
    JsonCaseTypeRegistry,
)
from decision.review import (  # noqa: E402
    HumanReviewPacketBuilder,
    JsonReviewPacketRegistry,
    JsonThresholdRegistry,
    ReviewAuditAdapter,
    ReviewPacketAuditAdapter,
    ReviewTriggerService,
    ThresholdEvaluator,
)
from decision.router import (  # noqa: E402
    ConflictClassifier,
    JsonRouterRegistry,
    RouterAuditAdapter,
    RouterResolutionRequest,
    RouterService,
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
from state.features.feature_registry import (  # noqa: E402
    FeatureDefinition,
    FeatureRegistry,
    InMemoryFeatureDefinitionRepository,
    JsonFeatureOwnerRegistry,
)
from state.lifecycle.state_model_registry import JsonStateModelRegistry  # noqa: E402
from state.lifecycle.transition_validator import TransitionValidator  # noqa: E402


class RouterServiceLayerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry_root = REPO_ROOT / "registries" / "control_plane"
        schema_repository = JsonContractSchemaRepository(
            REPO_ROOT,
            self.registry_root / "contract_schemas.json",
        )
        self.contract_validator = ContractSchemaValidator(schema_repository=schema_repository)
        self.audit_store = AuditEventStore(
            event_type_registry=JsonAuditEventTypeRegistry(
                self.registry_root / "audit_event_types.json"
            ),
            repository=InMemoryAuditEventRepository(),
            contract_validator=self.contract_validator,
        )
        self.contract_validator.set_audit_sink(self.audit_store)
        self.router_service = self._build_router_service()
        self.feature_registry = self._build_feature_registry()

    def test_single_valid_route_resolution(self) -> None:
        resolution = self.router_service.resolve(
            self._router_request(
                router_rule_id="default_case_route",
                source_stage="raw_ingestion",
                target_stage="feature_registry",
            )
        )

        self.assertTrue(resolution.accepted)
        self.assertEqual(resolution.route_name, "primary_case_path")
        self.assertEqual(resolution.resolution_status, "resolved")

    def test_multiple_route_precedence_selection(self) -> None:
        resolution = self.router_service.resolve(
            self._router_request(
                router_rule_id="default_case_route",
                source_stage="feature_registry",
                target_stage="case_orchestration",
            )
        )

        self.assertTrue(resolution.accepted)
        self.assertEqual(resolution.route_name, "primary_case_path")
        self.assertEqual(resolution.precedence_rank, 200)

    def test_tie_break_path(self) -> None:
        resolution = self.router_service.resolve(
            self._router_request(router_rule_id="tie_break_case_route")
        )

        self.assertTrue(resolution.accepted)
        self.assertEqual(resolution.route_name, "alpha_tie_path")
        self.assertTrue(resolution.tie_break_applied)

    def test_blocked_routing_when_no_route_is_valid(self) -> None:
        resolution = self.router_service.resolve(
            self._router_request(
                router_rule_id="default_case_route",
                source_stage="case_orchestration",
                target_stage="raw_ingestion",
                transition_class="fallback",
            )
        )

        self.assertFalse(resolution.accepted)
        self.assertEqual(resolution.resolution_status, "blocked")
        self.assertEqual(resolution.conflict_class, "no_route_available")

    def test_unresolved_conflict_classification(self) -> None:
        resolution = self.router_service.resolve(
            self._router_request(router_rule_id="unresolved_case_route")
        )

        self.assertFalse(resolution.accepted)
        self.assertEqual(resolution.resolution_status, "unresolved")
        self.assertEqual(resolution.conflict_class, "unresolved_route_conflict")

    def test_fallback_route_application(self) -> None:
        resolution = self.router_service.resolve(
            self._router_request(router_rule_id="fallback_resolution_case_route")
        )

        self.assertTrue(resolution.accepted)
        self.assertEqual(resolution.resolution_status, "fallback_applied")
        self.assertEqual(resolution.route_name, "contained_manual_fallback_path")

    def test_orchestrator_lifecycle_integration_uses_router_service(self) -> None:
        case_orchestrator = self._build_case_orchestrator()
        feature = self.feature_registry.register_feature(
            FeatureDefinition(
                name="shared.control.revenue_delta",
                namespace="shared.control",
                owner_id="shared_control_plane",
                description="Expected revenue delta used to seed router tests.",
                semantic_scope="shared_control_plane",
                formula="candidate_revenue - baseline_revenue",
                unit="currency",
                denominator=None,
                time_basis="event_time",
                window="7d",
                data_type="float",
                status="active",
                source_fields=("candidate_revenue", "baseline_revenue"),
                created_at=datetime.now(tz=UTC),
            ),
            correlation_id=str(uuid4()),
            actor_id="router-test",
        )
        raw_pipeline = self._build_raw_pipeline()
        ingestion_result = raw_pipeline.ingest_batch(
            commands=(
                RawIngestionCommand(
                    source_name="domain_01_promotional_allocation",
                    source_record_id="promo-001",
                    scope_key="store:001",
                    scope_type="store",
                    observed_at=datetime(2026, 4, 22, 0, 0, tzinfo=UTC),
                    payload={
                        "store_id": "001",
                        "sku": "SKU-001",
                        "candidate_revenue": 1200.0,
                        "baseline_revenue": 1000.0,
                        "event_type": "promotion_candidate",
                    },
                ),
            ),
            correlation_id=str(uuid4()),
            actor_id="router-test",
        )
        correlation_id = str(uuid4())
        episode = case_orchestrator.open_episode(
            case_type="shared_control_plane_case",
            case_key="case:promo-001",
            raw_record_ids=(ingestion_result.accepted_records[0].raw_record_id,),
            feature_names=(feature.name,),
            correlation_id=correlation_id,
            actor_id="router-test",
            actor_role="case_operator",
        )
        updated = case_orchestrator.record_handoff(
            episode.episode_id,
            to_stage="feature_registry",
            transition_name="promote_to_feature_review",
            reason="Router service should govern the route for this transition.",
            correlation_id=correlation_id,
            actor_id="router-test",
            actor_role="assistant_case_operator",
        )

        self.assertEqual(updated.current_stage, "feature_registry")
        self.assertIn("decision.router.router_resolution_succeeded", self._event_types())

    def test_routing_audit_emission_covers_router_outcomes(self) -> None:
        self.router_service.resolve(
            self._router_request(
                router_rule_id="default_case_route",
                source_stage="raw_ingestion",
                target_stage="feature_registry",
            )
        )
        self.router_service.resolve(self._router_request(router_rule_id="tie_break_case_route"))
        self.router_service.resolve(self._router_request(router_rule_id="unresolved_case_route"))
        self.router_service.resolve(self._router_request(router_rule_id="fallback_resolution_case_route"))
        self.router_service.resolve(
            self._router_request(
                router_rule_id="default_case_route",
                source_stage="case_orchestration",
                target_stage="raw_ingestion",
                transition_class="fallback",
            )
        )

        event_types = self._event_types()
        self.assertIn("decision.router.router_resolution_succeeded", event_types)
        self.assertIn("decision.router.router_resolution_blocked", event_types)
        self.assertIn("decision.router.conflict_classified", event_types)
        self.assertIn("decision.router.tie_break_applied", event_types)
        self.assertIn("decision.router.fallback_route_applied", event_types)
        self.assertIn("decision.router.unresolved_conflict_detected", event_types)

    def _build_router_service(self) -> RouterService:
        router_registry = JsonRouterRegistry(
            router_rules_path=self.registry_root / "router_rules.json",
            conflict_classes_path=self.registry_root / "conflict_classes.json",
            route_precedence_path=self.registry_root / "route_precedence.json",
            contract_validator=self.contract_validator,
        )
        router_audit_adapter = RouterAuditAdapter(
            audit_event_store=self.audit_store,
            contract_validator=self.contract_validator,
        )
        return RouterService(
            router_registry=router_registry,
            conflict_classifier=ConflictClassifier(router_registry),
            router_audit_adapter=router_audit_adapter,
        )

    def _build_case_orchestrator(self) -> CaseEpisodeOrchestrator:
        authority_registry = JsonAuthorityRegistry(
            rules_path=self.registry_root / "authority_rules.json",
            roles_path=self.registry_root / "authority_roles.json",
            contract_validator=self.contract_validator,
        )
        delegation_policy_registry = JsonDelegationPolicyRegistry(
            registry_path=self.registry_root / "delegation_policies.json",
            contract_validator=self.contract_validator,
        )
        authority_audit_adapter = AuthorityAuditAdapter(
            audit_event_store=self.audit_store,
            contract_validator=self.contract_validator,
        )
        authority_resolution_service = AuthorityResolutionService(
            authority_registry=authority_registry,
            delegation_policy_registry=delegation_policy_registry,
            authority_audit_adapter=authority_audit_adapter,
        )
        state_model_registry = JsonStateModelRegistry(self.registry_root / "lifecycle_state_models.json")
        transition_validator = TransitionValidator(
            state_model_registry=state_model_registry,
            authority_resolution_service=authority_resolution_service,
        )
        threshold_registry = JsonThresholdRegistry(
            review_thresholds_path=self.registry_root / "review_thresholds.json",
            trigger_classes_path=self.registry_root / "trigger_classes.json",
            calibration_profiles_path=self.registry_root / "calibration_profiles.json",
            contract_validator=self.contract_validator,
        )
        review_audit_adapter = ReviewAuditAdapter(
            audit_event_store=self.audit_store,
            contract_validator=self.contract_validator,
        )
        review_trigger_service = ReviewTriggerService(
            threshold_registry=threshold_registry,
            threshold_evaluator=ThresholdEvaluator(),
            review_audit_adapter=review_audit_adapter,
        )
        review_packet_registry = JsonReviewPacketRegistry(
            review_packet_templates_path=self.registry_root / "review_packet_templates.json",
            review_reason_classes_path=self.registry_root / "review_reason_classes.json",
            contract_validator=self.contract_validator,
        )
        review_packet_audit_adapter = ReviewPacketAuditAdapter(
            audit_event_store=self.audit_store,
            contract_validator=self.contract_validator,
        )
        human_review_packet_builder = HumanReviewPacketBuilder(
            review_packet_registry=review_packet_registry,
            review_packet_audit_adapter=review_packet_audit_adapter,
        )
        transition_audit_adapter = CaseTransitionAuditAdapter(self.audit_store)
        state_manager = CaseStateManager(
            state_model_registry=state_model_registry,
            transition_validator=transition_validator,
            router_service=self.router_service,
            review_trigger_service=review_trigger_service,
            human_review_packet_builder=human_review_packet_builder,
            transition_audit_adapter=transition_audit_adapter,
        )
        return CaseEpisodeOrchestrator(
            case_type_registry=JsonCaseTypeRegistry(self.registry_root / "case_episode_registry.json"),
            repository=InMemoryCaseEpisodeRepository(),
            contract_validator=self.contract_validator,
            audit_event_store=self.audit_store,
            feature_lookup=self.feature_registry,
            state_manager=state_manager,
        )

    def _build_feature_registry(self) -> FeatureRegistry:
        return FeatureRegistry(
            owner_registry=JsonFeatureOwnerRegistry(self.registry_root / "feature_owners.json"),
            repository=InMemoryFeatureDefinitionRepository(),
            contract_validator=self.contract_validator,
            audit_event_store=self.audit_store,
        )

    def _build_raw_pipeline(self) -> RawIngestionPipeline:
        return RawIngestionPipeline(
            source_registry=JsonIngestionSourceRegistry(self.registry_root / "ingestion_sources.json"),
            repository=InMemoryRawRecordRepository(),
            contract_validator=self.contract_validator,
            audit_event_store=self.audit_store,
        )

    def _router_request(
        self,
        *,
        router_rule_id: str,
        source_stage: str = "feature_registry",
        target_stage: str = "case_orchestration",
        transition_class: str = "forward_progression",
    ) -> RouterResolutionRequest:
        return RouterResolutionRequest(
            router_rule_id=router_rule_id,
            semantic_scope="shared_control_plane",
            state_model_name="shared_control_plane_lifecycle",
            transition_name="promote_to_case_assessment",
            transition_class=transition_class,
            source_stage=source_stage,
            target_stage=target_stage,
            correlation_id=str(uuid4()),
            episode_id=str(uuid4()),
            actor_id="router-test",
        )

    def _event_types(self) -> list[str]:
        return [event.event_type for event in self.audit_store.list_events()]


if __name__ == "__main__":
    unittest.main()