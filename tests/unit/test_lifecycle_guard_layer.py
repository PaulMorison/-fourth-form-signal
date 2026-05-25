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
    RouterService,
)
from platform.audit.audit_event_store import (  # noqa: E402
    AuditEventStore,
    InMemoryAuditEventRepository,
    JsonAuditEventTypeRegistry,
)
from platform.validation.contract_schema_validator import (  # noqa: E402
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
from state.lifecycle.transition_validator import (  # noqa: E402
    InvalidTransitionError,
    MissingAuthorityError,
    TransitionValidator,
)


class LifecycleGuardLayerTests(unittest.TestCase):
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

        state_model_registry = JsonStateModelRegistry(registry_root / "lifecycle_state_models.json")
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
        authority_resolution_service = AuthorityResolutionService(
            authority_registry=authority_registry,
            delegation_policy_registry=delegation_policy_registry,
            authority_audit_adapter=authority_audit_adapter,
        )
        transition_validator = TransitionValidator(
            state_model_registry=state_model_registry,
            authority_resolution_service=authority_resolution_service,
        )
        transition_audit_adapter = CaseTransitionAuditAdapter(self.audit_store)
        router_registry = JsonRouterRegistry(
            router_rules_path=registry_root / "router_rules.json",
            conflict_classes_path=registry_root / "conflict_classes.json",
            route_precedence_path=registry_root / "route_precedence.json",
            contract_validator=self.contract_validator,
        )
        router_audit_adapter = RouterAuditAdapter(
            audit_event_store=self.audit_store,
            contract_validator=self.contract_validator,
        )
        router_service = RouterService(
            router_registry=router_registry,
            conflict_classifier=ConflictClassifier(router_registry),
            router_audit_adapter=router_audit_adapter,
        )
        threshold_registry = JsonThresholdRegistry(
            review_thresholds_path=registry_root / "review_thresholds.json",
            trigger_classes_path=registry_root / "trigger_classes.json",
            calibration_profiles_path=registry_root / "calibration_profiles.json",
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
            review_packet_templates_path=registry_root / "review_packet_templates.json",
            review_reason_classes_path=registry_root / "review_reason_classes.json",
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
        state_manager = CaseStateManager(
            state_model_registry=state_model_registry,
            transition_validator=transition_validator,
            router_service=router_service,
            review_trigger_service=review_trigger_service,
            human_review_packet_builder=human_review_packet_builder,
            transition_audit_adapter=transition_audit_adapter,
        )

        self.feature_registry = FeatureRegistry(
            owner_registry=JsonFeatureOwnerRegistry(registry_root / "feature_owners.json"),
            repository=InMemoryFeatureDefinitionRepository(),
            contract_validator=self.contract_validator,
            audit_event_store=self.audit_store,
        )
        self.raw_pipeline = RawIngestionPipeline(
            source_registry=JsonIngestionSourceRegistry(registry_root / "ingestion_sources.json"),
            repository=InMemoryRawRecordRepository(),
            contract_validator=self.contract_validator,
            audit_event_store=self.audit_store,
        )
        self.case_orchestrator = CaseEpisodeOrchestrator(
            case_type_registry=JsonCaseTypeRegistry(registry_root / "case_episode_registry.json"),
            repository=InMemoryCaseEpisodeRepository(),
            contract_validator=self.contract_validator,
            audit_event_store=self.audit_store,
            feature_lookup=self.feature_registry,
            state_manager=state_manager,
        )
        self.correlation_id = str(uuid4())
        self.actor_id = "unit-test"

    def test_orchestrator_integration_uses_delegated_authority_service(self) -> None:
        episode = self._open_episode()

        updated = self.case_orchestrator.record_handoff(
            episode.episode_id,
            to_stage="feature_registry",
            transition_name="promote_to_feature_review",
            reason="Delegated authority should be honored through the orchestrator.",
            correlation_id=self.correlation_id,
            actor_id=self.actor_id,
            actor_role="assistant_case_operator",
        )

        self.assertEqual(updated.current_state, "feature_review_ready")
        self.assertEqual(updated.current_stage, "feature_registry")
        self.assertIn(
            "decision.case.transition_accepted",
            self._event_types(),
        )
        self.assertIn("decision.authority.delegation_applied", self._event_types())
        self.assertIn("decision.router.router_resolution_succeeded", self._event_types())

    def test_invalid_transition_rejection(self) -> None:
        episode = self._open_episode()

        with self.assertRaises(InvalidTransitionError):
            self.case_orchestrator.record_handoff(
                episode.episode_id,
                to_stage="case_orchestration",
                transition_name="promote_to_case_assessment",
                reason="Direct state jump should be rejected.",
                correlation_id=self.correlation_id,
                actor_id=self.actor_id,
                actor_role="case_operator",
            )

        self.assertIn("decision.case.transition_invalid", self._event_types())

    def test_missing_authority_rejection(self) -> None:
        episode = self._open_episode()

        with self.assertRaises(MissingAuthorityError):
            self.case_orchestrator.record_handoff(
                episode.episode_id,
                to_stage="feature_registry",
                transition_name="promote_to_feature_review",
                reason="Observer should not advance lifecycle state.",
                correlation_id=self.correlation_id,
                actor_id=self.actor_id,
                actor_role="observer",
            )

        self.assertIn("decision.case.transition_blocked", self._event_types())

    def test_fallback_path_legitimacy(self) -> None:
        episode = self._open_episode()
        feature_review = self.case_orchestrator.record_handoff(
            episode.episode_id,
            to_stage="feature_registry",
            transition_name="promote_to_feature_review",
            reason="Feature review can begin.",
            correlation_id=self.correlation_id,
            actor_id=self.actor_id,
            actor_role="assistant_case_operator",
        )
        assessed = self.case_orchestrator.record_handoff(
            feature_review.episode_id,
            to_stage="case_orchestration",
            transition_name="promote_to_case_assessment",
            reason="Assessment may begin.",
            correlation_id=self.correlation_id,
            actor_id=self.actor_id,
            actor_role="case_operator",
            threshold_context={"impact_score": 0.20},
        )

        fallback = self.case_orchestrator.fallback_episode(
            assessed.episode_id,
            to_stage="feature_registry",
            transition_name="fallback_to_feature_review",
            reason="Assessment needs a governed fallback to feature review.",
            correlation_id=self.correlation_id,
            actor_id=self.actor_id,
            actor_role="case_supervisor",
        )

        self.assertEqual(fallback.current_state, "feature_review_ready")
        self.assertEqual(fallback.current_stage, "feature_registry")
        self.assertIn("decision.case.transition_fallback", self._event_types())
        self.assertIn("decision.router.router_resolution_succeeded", self._event_types())

    def test_transition_audit_events_cover_every_outcome(self) -> None:
        episode = self._open_episode()

        with self.assertRaises(InvalidTransitionError):
            self.case_orchestrator.record_handoff(
                episode.episode_id,
                to_stage="case_orchestration",
                transition_name="promote_to_case_assessment",
                reason="Direct state jump should be rejected.",
                correlation_id=self.correlation_id,
                actor_id=self.actor_id,
                actor_role="case_operator",
            )

        with self.assertRaises(MissingAuthorityError):
            self.case_orchestrator.record_handoff(
                episode.episode_id,
                to_stage="feature_registry",
                transition_name="promote_to_feature_review",
                reason="Observer should not advance lifecycle state.",
                correlation_id=self.correlation_id,
                actor_id=self.actor_id,
                actor_role="observer",
            )

        feature_review = self.case_orchestrator.record_handoff(
            episode.episode_id,
            to_stage="feature_registry",
            transition_name="promote_to_feature_review",
            reason="Feature review can begin.",
            correlation_id=self.correlation_id,
            actor_id=self.actor_id,
            actor_role="assistant_case_operator",
        )
        assessed = self.case_orchestrator.record_handoff(
            feature_review.episode_id,
            to_stage="case_orchestration",
            transition_name="promote_to_case_assessment",
            reason="Assessment may begin.",
            correlation_id=self.correlation_id,
            actor_id=self.actor_id,
            actor_role="case_operator",
            threshold_context={"impact_score": 0.20},
        )
        interrupted = self.case_orchestrator.interrupt_episode(
            assessed.episode_id,
            transition_name="interrupt_case_assessment",
            reason="External review input interrupts the case.",
            correlation_id=self.correlation_id,
            actor_id=self.actor_id,
            actor_role="case_operator",
            threshold_context={"impact_score": 0.20},
        )
        resumed = self.case_orchestrator.resume_episode(
            interrupted.episode_id,
            transition_name="resume_case_assessment",
            reason="Required authority resumes the case.",
            correlation_id=self.correlation_id,
            actor_id=self.actor_id,
            actor_role="case_operator",
        )
        self.case_orchestrator.fallback_episode(
            resumed.episode_id,
            to_stage="feature_registry",
            transition_name="fallback_to_feature_review",
            reason="Assessment detects missing detail and falls back.",
            correlation_id=self.correlation_id,
            actor_id=self.actor_id,
            actor_role="case_supervisor",
        )

        event_types = self._event_types()
        self.assertIn("decision.case.transition_accepted", event_types)
        self.assertIn("decision.case.transition_blocked", event_types)
        self.assertIn("decision.case.transition_invalid", event_types)
        self.assertIn("decision.case.transition_fallback", event_types)
        self.assertIn("decision.case.transition_resumed", event_types)
        self.assertIn("decision.router.router_resolution_succeeded", event_types)

    def _open_episode(self):
        feature = self.feature_registry.register_feature(
            FeatureDefinition(
                name="shared.control.revenue_delta",
                namespace="shared.control",
                owner_id="shared_control_plane",
                description="Expected revenue delta used to seed lifecycle tests.",
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
            correlation_id=self.correlation_id,
            actor_id=self.actor_id,
        )
        ingestion_result = self.raw_pipeline.ingest_batch(
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
            correlation_id=self.correlation_id,
            actor_id=self.actor_id,
        )

        return self.case_orchestrator.open_episode(
            case_type="shared_control_plane_case",
            case_key="case:promo-001",
            raw_record_ids=(ingestion_result.accepted_records[0].raw_record_id,),
            feature_names=(feature.name,),
            correlation_id=self.correlation_id,
            actor_id=self.actor_id,
            actor_role="case_operator",
        )

    def _event_types(self) -> list[str]:
        return [event.event_type for event in self.audit_store.list_events()]


if __name__ == "__main__":
    unittest.main()
