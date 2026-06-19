from __future__ import annotations

"""Minimal bootstrap flow connecting the first control-plane modules.

The flow is intentionally narrow:
1. Load schemas and registries.
2. Stand up the audit store and schema validator.
3. Register one governed feature.
4. Ingest one governed raw record.
5. Open and hand off one governed case episode.

This demonstrates how the first batch connects without implementing UI, ML,
simulation, or broader lifecycle services.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from data.ingestion.raw_ingestion_pipeline import (
    InMemoryRawRecordRepository,
    JsonIngestionSourceRegistry,
    RawIngestionCommand,
    RawIngestionPipeline,
)
from decision.authority import (
    AuthorityAuditAdapter,
    AuthorityResolutionService,
    JsonAuthorityRegistry,
    JsonDelegationPolicyRegistry,
)
from decision.case.case_state_manager import CaseStateManager
from decision.case.case_transition_audit_adapter import CaseTransitionAuditAdapter
from decision.case.case_episode_orchestrator import (
    CaseEpisodeOrchestrator,
    InMemoryCaseEpisodeRepository,
    JsonCaseTypeRegistry,
)
from decision.policy_learning import (
    JsonPolicyLearningEvidenceAdmissionRegistry,
    JsonPolicyLearningUpdateApprovalRegistry,
    JsonPolicyLearningUpdateMutationExecutionRegistry,
    JsonPolicyLearningUpdateMutationPlanningRegistry,
    JsonPolicyLearningUpdatePreparationRegistry,
    JsonPolicyLearningUpdateThresholdRegistry,
    PolicyLearningEvidenceAdmissionAuditAdapter,
    PolicyLearningEvidenceAdmissionRequest,
    PolicyLearningEvidenceAdmissionService,
    PolicyLearningUpdateApprovalAuditAdapter,
    PolicyLearningUpdateApprovalRequest,
    PolicyLearningUpdateApprovalService,
    PolicyLearningUpdateMutationExecutionAuditAdapter,
    PolicyLearningUpdateMutationExecutionRequest,
    PolicyLearningUpdateMutationExecutionService,
    PolicyLearningUpdateMutationPlanningAuditAdapter,
    PolicyLearningUpdateMutationPlanningRequest,
    PolicyLearningUpdateMutationPlanningService,
    PolicyLearningUpdatePreparationAuditAdapter,
    PolicyLearningUpdatePreparationRequest,
    PolicyLearningUpdatePreparationService,
    PolicyLearningUpdateThresholdAuditAdapter,
    PolicyLearningUpdateThresholdRequest,
    PolicyLearningUpdateThresholdService,
)
from runtime.release import (
    ContainedRollback,
    ContainedRollbackAuditAdapter,
    ContainedRollbackRequest,
    JsonReleaseRegistry,
    ProductionEntitlementCheck,
    ProductionEntitlementCheckAuditAdapter,
    ProductionEntitlementCheckRequest,
    PromotionReadinessAuditAdapter,
    PromotionReadinessGate,
    PromotionReadinessGateRequest,
    ReleaseConfirmation,
    ReleaseConfirmationAuditAdapter,
    ReleaseConfirmationRequest,
    ReleaseAuditTrace,
    ReleaseAuditTraceAuditAdapter,
    ReleaseAuditTraceRequest,
    ReleaseWatchDiscipline,
    ReleaseWatchDisciplineAuditAdapter,
    ReleaseWatchDisciplineRequest,
    RollbackTriggerAuditAdapter,
    RollbackTriggerGuard,
    RollbackTriggerGuardRequest,
    RolloutScopeAuditAdapter,
    RolloutScopeController,
    RolloutScopeControllerRequest,
)
from decision.post_mortem import (
    JsonPostMortemJudgmentRegistry,
    PostMortemJudgmentAuditAdapter,
    PostMortemJudgmentRequest,
    PostMortemJudgmentService,
)
from decision.output import (
    ActionInstructionAuditAdapter,
    ActionInstructionRequest,
    ActionInstructionService,
    JsonActionInstructionRegistry,
    JsonPortfolioOutputRegistry,
    JsonPolicyOutputRegistry,
    PortfolioOutputAuditAdapter,
    PortfolioOutputRequest,
    PortfolioOutputService,
    PolicyOutputAuditAdapter,
    PolicyOutputRequest,
    PolicyOutputService,
    JsonRecommendationRegistry,
    RecommendationAuditAdapter,
    RecommendationRequest,
    RecommendationService,
)
from execution import (
    ExecutionDispatchAuditAdapter,
    ExecutionDispatchBoundaryRequest,
    ExecutionDispatchBoundaryService,
    ExecutionOutcomeAuditAdapter,
    ExecutionOutcomeCaptureRequest,
    ExecutionOutcomeCaptureService,
    ExecutionRequestAuditAdapter,
    ExecutionRequestRequest,
    ExecutionRequestService,
    JsonExecutionDispatchRegistry,
    JsonExecutionOutcomeRegistry,
    JsonExecutionRequestRegistry,
)
from decision.review import (
    HumanReviewPacketBuildRequest,
    HumanReviewPacketBuilder,
    JsonReviewPacketRegistry,
    JsonReviewResolutionRegistry,
    JsonThresholdRegistry,
    ReviewAuditAdapter,
    ReviewPacketAuditAdapter,
    ReviewResolutionAuditAdapter,
    ReviewResolutionRequest,
    ReviewResolutionService,
    ReviewTriggerRequest,
    ReviewTriggerService,
    ThresholdEvaluator,
)
from decision.router import (
    ConflictClassifier,
    JsonRouterRegistry,
    RouterAuditAdapter,
    RouterResolutionRequest,
    RouterService,
)
from ff_platform.audit.audit_event_store import (
    AuditEventStore,
    InMemoryAuditEventRepository,
    JsonAuditEventTypeRegistry,
)
from ff_platform.validation.contract_schema_validator import (
    ContractSchemaValidator,
    JsonContractSchemaRepository,
)
from state.features.feature_registry import (
    FeatureDefinition,
    FeatureRegistry,
    InMemoryFeatureDefinitionRepository,
    JsonFeatureOwnerRegistry,
)
from state.lifecycle.state_model_registry import JsonStateModelRegistry
from state.lifecycle.transition_validator import (
    InvalidTransitionError,
    TransitionBlockedError,
    TransitionValidator,
)


@dataclass(frozen=True)
class BootstrapArtifacts:
    feature_name: str
    raw_record_id: str
    episode_id: str
    final_state: str
    final_stage: str
    authority_success_count: int
    authority_blocked_count: int
    delegation_event_count: int
    scope_violation_count: int
    fallback_authority_count: int
    router_success_count: int
    router_blocked_count: int
    conflict_classification_count: int
    tie_break_count: int
    unresolved_conflict_count: int
    fallback_route_count: int
    review_required_count: int
    review_optional_count: int
    threshold_blocked_count: int
    threshold_not_triggered_count: int
    calibration_profile_count: int
    fallback_review_mode_count: int
    review_packet_built_count: int
    review_packet_blocked_count: int
    review_packet_ready_count: int
    review_packet_missing_context_count: int
    review_packet_fallback_template_count: int
    review_resolution_recorded_count: int
    review_resolution_blocked_count: int
    review_resolution_ready_count: int
    review_resolution_missing_context_count: int
    review_resolution_fallback_count: int
    recommendation_recorded_count: int
    recommendation_blocked_count: int
    recommendation_ready_count: int
    recommendation_missing_context_count: int
    recommendation_fallback_template_count: int
    policy_output_recorded_count: int
    policy_output_blocked_count: int
    policy_output_ready_count: int
    policy_output_missing_context_count: int
    policy_output_fallback_template_count: int
    portfolio_output_recorded_count: int
    portfolio_output_blocked_count: int
    portfolio_output_ready_count: int
    portfolio_output_missing_context_count: int
    portfolio_output_fallback_template_count: int
    action_instruction_recorded_count: int
    action_instruction_blocked_count: int
    action_instruction_ready_count: int
    action_instruction_missing_context_count: int
    action_instruction_fallback_template_count: int
    execution_request_recorded_count: int
    execution_request_blocked_count: int
    execution_request_ready_count: int
    execution_request_missing_context_count: int
    execution_request_fallback_template_count: int
    execution_dispatch_recorded_count: int
    execution_dispatch_blocked_count: int
    execution_dispatch_ready_count: int
    execution_dispatch_missing_context_count: int
    execution_dispatch_fallback_template_count: int
    execution_outcome_recorded_count: int
    execution_outcome_blocked_count: int
    execution_outcome_ready_count: int
    execution_outcome_missing_context_count: int
    execution_outcome_fallback_template_count: int
    post_mortem_recorded_count: int
    post_mortem_blocked_count: int
    post_mortem_ready_count: int
    post_mortem_missing_context_count: int
    post_mortem_fallback_template_count: int
    policy_learning_recorded_count: int
    policy_learning_blocked_count: int
    policy_learning_admitted_for_update_consideration_count: int
    policy_learning_missing_context_count: int
    policy_learning_rejected_for_learning_use_count: int
    policy_learning_deferred_pending_more_evidence_count: int
    policy_learning_fallback_template_count: int
    policy_learning_prohibited_overlap_count: int
    policy_learning_update_threshold_recorded_count: int
    policy_learning_update_threshold_blocked_count: int
    policy_learning_update_threshold_accepted_count: int
    policy_learning_update_threshold_accepted_with_narrowed_scope_count: int
    policy_learning_update_threshold_deferred_for_continued_monitoring_count: int
    policy_learning_update_threshold_missing_context_count: int
    policy_learning_update_threshold_rejected_count: int
    policy_learning_update_threshold_fallback_template_count: int
    policy_learning_update_threshold_prohibited_overlap_count: int
    policy_learning_update_approval_recorded_count: int
    policy_learning_update_approval_blocked_count: int
    policy_learning_update_approval_approved_count: int
    policy_learning_update_approval_approved_with_restrictions_count: int
    policy_learning_update_approval_deferred_count: int
    policy_learning_update_approval_missing_context_count: int
    policy_learning_update_approval_rejected_count: int
    policy_learning_update_approval_prohibited_overlap_count: int
    policy_learning_update_approval_fallback_template_count: int
    policy_learning_update_preparation_recorded_count: int
    policy_learning_update_preparation_blocked_count: int
    policy_learning_update_preparation_prepared_count: int
    policy_learning_update_preparation_prepared_with_restrictions_count: int
    policy_learning_update_preparation_deferred_count: int
    policy_learning_update_preparation_missing_context_count: int
    policy_learning_update_preparation_rejected_count: int
    policy_learning_update_preparation_prohibited_overlap_count: int
    policy_learning_update_preparation_fallback_template_count: int
    policy_learning_update_mutation_planning_recorded_count: int
    policy_learning_update_mutation_planning_blocked_count: int
    policy_learning_update_mutation_planning_ready_count: int
    policy_learning_update_mutation_planning_ready_with_restrictions_count: int
    policy_learning_update_mutation_planning_deferred_count: int
    policy_learning_update_mutation_planning_missing_context_count: int
    policy_learning_update_mutation_planning_rejected_count: int
    policy_learning_update_mutation_planning_prohibited_overlap_count: int
    policy_learning_update_mutation_planning_fallback_template_count: int
    policy_learning_update_mutation_execution_recorded_count: int
    policy_learning_update_mutation_execution_blocked_count: int
    policy_learning_update_mutation_execution_ready_count: int
    policy_learning_update_mutation_execution_ready_with_restrictions_count: int
    policy_learning_update_mutation_execution_deferred_count: int
    policy_learning_update_mutation_execution_missing_context_count: int
    policy_learning_update_mutation_execution_rejected_count: int
    policy_learning_update_mutation_execution_prohibited_overlap_count: int
    policy_learning_update_mutation_execution_fallback_template_count: int
    promotion_readiness_recorded_count: int
    promotion_readiness_blocked_count: int
    promotion_readiness_ready_for_rollout_scope_control_count: int
    promotion_readiness_conditionally_ready_for_rollout_scope_control_count: int
    promotion_readiness_deferred_count: int
    promotion_readiness_missing_context_count: int
    promotion_readiness_rejected_count: int
    promotion_readiness_prohibited_overlap_count: int
    promotion_readiness_fallback_template_count: int
    rollout_scope_recorded_count: int
    rollout_scope_blocked_count: int
    rollout_scope_ready_for_rollback_trigger_guard_count: int
    rollout_scope_conditionally_ready_for_rollback_trigger_guard_count: int
    rollout_scope_deferred_count: int
    rollout_scope_missing_context_count: int
    rollout_scope_rejected_count: int
    rollout_scope_prohibited_overlap_count: int
    rollout_scope_fallback_template_count: int
    rollback_trigger_recorded_count: int
    rollback_trigger_blocked_count: int
    rollback_trigger_ready_for_release_watch_discipline_count: int
    rollback_trigger_conditionally_ready_for_release_watch_discipline_count: int
    rollback_trigger_deferred_count: int
    rollback_trigger_missing_context_count: int
    rollback_trigger_rejected_count: int
    rollback_trigger_prohibited_overlap_count: int
    rollback_trigger_fallback_template_count: int
    release_watch_discipline_recorded_count: int
    release_watch_discipline_blocked_count: int
    release_watch_discipline_ready_for_release_confirmation_count: int
    release_watch_discipline_conditionally_ready_for_release_confirmation_count: int
    release_watch_discipline_deferred_count: int
    release_watch_discipline_missing_context_count: int
    release_watch_discipline_rejected_count: int
    release_watch_discipline_prohibited_overlap_count: int
    release_watch_discipline_fallback_template_count: int
    release_confirmation_recorded_count: int
    release_confirmation_blocked_count: int
    release_confirmation_confirmed_count: int
    release_confirmation_conditionally_confirmed_count: int
    release_confirmation_deferred_count: int
    release_confirmation_missing_context_count: int
    release_confirmation_rejected_count: int
    release_confirmation_prohibited_overlap_count: int
    release_confirmation_fallback_template_count: int
    production_entitlement_check_recorded_count: int
    production_entitlement_check_blocked_count: int
    production_entitlement_check_approved_count: int
    production_entitlement_check_conditionally_approved_count: int
    production_entitlement_check_deferred_count: int
    production_entitlement_check_missing_context_count: int
    production_entitlement_check_rejected_count: int
    production_entitlement_check_prohibited_overlap_count: int
    production_entitlement_check_fallback_template_count: int
    contained_rollback_recorded_count: int
    contained_rollback_blocked_count: int
    contained_rollback_bounded_exposure_preserved_count: int
    contained_rollback_partial_reversal_bounded_count: int
    contained_rollback_deferred_count: int
    contained_rollback_missing_context_count: int
    contained_rollback_rejected_count: int
    contained_rollback_prohibited_overlap_count: int
    contained_rollback_fallback_template_count: int
    release_audit_trace_recorded_count: int
    release_audit_trace_blocked_count: int
    release_audit_trace_lineage_preserved_count: int
    release_audit_trace_invalid_release_state_visible_count: int
    release_audit_trace_invalid_exposure_visible_count: int
    release_audit_trace_no_silent_promotion_preserved_count: int
    release_audit_trace_deferred_count: int
    release_audit_trace_missing_context_count: int
    release_audit_trace_rejected_count: int
    release_audit_trace_prohibited_overlap_count: int
    release_audit_trace_fallback_template_count: int
    blocked_transition_count: int
    invalid_transition_count: int
    audit_event_count: int


class FirstControlPlaneBootstrap:
    """Wires together the first shared control-plane services."""

    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root

    @classmethod
    def for_current_repo(cls) -> "FirstControlPlaneBootstrap":
        return cls(Path(__file__).resolve().parents[2])

    def run(self) -> BootstrapArtifacts:
        registry_root = self._repo_root / "registries" / "control_plane"
        schema_repository = JsonContractSchemaRepository(
            self._repo_root,
            registry_root / "contract_schemas.json",
        )
        contract_validator = ContractSchemaValidator(schema_repository=schema_repository)
        audit_store = AuditEventStore(
            event_type_registry=JsonAuditEventTypeRegistry(
                registry_root / "audit_event_types.json"
            ),
            repository=InMemoryAuditEventRepository(),
            contract_validator=contract_validator,
        )
        contract_validator.set_audit_sink(audit_store)
        state_model_registry = JsonStateModelRegistry(registry_root / "lifecycle_state_models.json")
        authority_registry = JsonAuthorityRegistry(
            rules_path=registry_root / "authority_rules.json",
            roles_path=registry_root / "authority_roles.json",
            contract_validator=contract_validator,
        )
        delegation_policy_registry = JsonDelegationPolicyRegistry(
            registry_path=registry_root / "delegation_policies.json",
            contract_validator=contract_validator,
        )
        authority_audit_adapter = AuthorityAuditAdapter(
            audit_event_store=audit_store,
            contract_validator=contract_validator,
        )
        authority_resolution_service = AuthorityResolutionService(
            authority_registry=authority_registry,
            delegation_policy_registry=delegation_policy_registry,
            authority_audit_adapter=authority_audit_adapter,
        )
        router_registry = JsonRouterRegistry(
            router_rules_path=registry_root / "router_rules.json",
            conflict_classes_path=registry_root / "conflict_classes.json",
            route_precedence_path=registry_root / "route_precedence.json",
            contract_validator=contract_validator,
        )
        router_audit_adapter = RouterAuditAdapter(
            audit_event_store=audit_store,
            contract_validator=contract_validator,
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
            contract_validator=contract_validator,
        )
        review_audit_adapter = ReviewAuditAdapter(
            audit_event_store=audit_store,
            contract_validator=contract_validator,
        )
        review_trigger_service = ReviewTriggerService(
            threshold_registry=threshold_registry,
            threshold_evaluator=ThresholdEvaluator(),
            review_audit_adapter=review_audit_adapter,
        )
        review_packet_registry = JsonReviewPacketRegistry(
            review_packet_templates_path=registry_root / "review_packet_templates.json",
            review_reason_classes_path=registry_root / "review_reason_classes.json",
            contract_validator=contract_validator,
        )
        review_packet_audit_adapter = ReviewPacketAuditAdapter(
            audit_event_store=audit_store,
            contract_validator=contract_validator,
        )
        human_review_packet_builder = HumanReviewPacketBuilder(
            review_packet_registry=review_packet_registry,
            review_packet_audit_adapter=review_packet_audit_adapter,
        )
        review_resolution_registry = JsonReviewResolutionRegistry(
            review_resolution_classes_path=registry_root / "review_resolution_classes.json",
            case_disposition_classes_path=registry_root / "case_disposition_classes.json",
            contract_validator=contract_validator,
        )
        review_resolution_audit_adapter = ReviewResolutionAuditAdapter(
            audit_event_store=audit_store,
            contract_validator=contract_validator,
        )
        review_resolution_service = ReviewResolutionService(
            review_resolution_registry=review_resolution_registry,
            review_resolution_audit_adapter=review_resolution_audit_adapter,
        )
        recommendation_registry = JsonRecommendationRegistry(
            recommendation_classes_path=registry_root / "recommendation_classes.json",
            recommendation_templates_path=registry_root / "recommendation_templates.json",
            contract_validator=contract_validator,
        )
        recommendation_audit_adapter = RecommendationAuditAdapter(
            audit_event_store=audit_store,
            contract_validator=contract_validator,
        )
        recommendation_service = RecommendationService(
            recommendation_registry=recommendation_registry,
            recommendation_audit_adapter=recommendation_audit_adapter,
        )
        policy_output_registry = JsonPolicyOutputRegistry(
            policy_output_classes_path=registry_root / "policy_output_classes.json",
            policy_output_templates_path=registry_root / "policy_output_templates.json",
            contract_validator=contract_validator,
        )
        policy_output_audit_adapter = PolicyOutputAuditAdapter(
            audit_event_store=audit_store,
            contract_validator=contract_validator,
        )
        policy_output_service = PolicyOutputService(
            policy_output_registry=policy_output_registry,
            policy_output_audit_adapter=policy_output_audit_adapter,
        )
        portfolio_output_registry = JsonPortfolioOutputRegistry(
            portfolio_output_classes_path=registry_root / "portfolio_output_classes.json",
            portfolio_output_templates_path=(
                registry_root / "portfolio_output_templates.json"
            ),
            contract_validator=contract_validator,
        )
        portfolio_output_audit_adapter = PortfolioOutputAuditAdapter(
            audit_event_store=audit_store,
            contract_validator=contract_validator,
        )
        portfolio_output_service = PortfolioOutputService(
            portfolio_output_registry=portfolio_output_registry,
            portfolio_output_audit_adapter=portfolio_output_audit_adapter,
        )
        action_instruction_registry = JsonActionInstructionRegistry(
            action_instruction_classes_path=(
                registry_root / "action_instruction_classes.json"
            ),
            action_instruction_templates_path=(
                registry_root / "action_instruction_templates.json"
            ),
            contract_validator=contract_validator,
        )
        action_instruction_audit_adapter = ActionInstructionAuditAdapter(
            audit_event_store=audit_store,
            contract_validator=contract_validator,
        )
        action_instruction_service = ActionInstructionService(
            action_instruction_registry=action_instruction_registry,
            action_instruction_audit_adapter=action_instruction_audit_adapter,
        )
        execution_request_registry = JsonExecutionRequestRegistry(
            execution_request_classes_path=(
                registry_root / "execution_request_classes.json"
            ),
            execution_request_templates_path=(
                registry_root / "execution_request_templates.json"
            ),
            contract_validator=contract_validator,
        )
        execution_request_audit_adapter = ExecutionRequestAuditAdapter(
            audit_event_store=audit_store,
            contract_validator=contract_validator,
        )
        execution_request_service = ExecutionRequestService(
            execution_request_registry=execution_request_registry,
            execution_request_audit_adapter=execution_request_audit_adapter,
        )
        execution_dispatch_registry = JsonExecutionDispatchRegistry(
            execution_dispatch_classes_path=(
                registry_root / "execution_dispatch_classes.json"
            ),
            execution_dispatch_templates_path=(
                registry_root / "execution_dispatch_templates.json"
            ),
            contract_validator=contract_validator,
        )
        execution_dispatch_audit_adapter = ExecutionDispatchAuditAdapter(
            audit_event_store=audit_store,
            contract_validator=contract_validator,
        )
        execution_dispatch_service = ExecutionDispatchBoundaryService(
            execution_dispatch_registry=execution_dispatch_registry,
            execution_dispatch_audit_adapter=execution_dispatch_audit_adapter,
        )
        execution_outcome_registry = JsonExecutionOutcomeRegistry(
            execution_outcome_classes_path=(
                registry_root / "execution_outcome_classes.json"
            ),
            execution_outcome_templates_path=(
                registry_root / "execution_outcome_templates.json"
            ),
            contract_validator=contract_validator,
        )
        execution_outcome_audit_adapter = ExecutionOutcomeAuditAdapter(
            audit_event_store=audit_store,
            contract_validator=contract_validator,
        )
        execution_outcome_service = ExecutionOutcomeCaptureService(
            execution_outcome_registry=execution_outcome_registry,
            execution_outcome_audit_adapter=execution_outcome_audit_adapter,
        )
        post_mortem_registry = JsonPostMortemJudgmentRegistry(
            post_mortem_judgment_classes_path=(
                registry_root / "post_mortem_judgment_classes.json"
            ),
            post_mortem_judgment_templates_path=(
                registry_root / "post_mortem_judgment_templates.json"
            ),
            contract_validator=contract_validator,
        )
        post_mortem_audit_adapter = PostMortemJudgmentAuditAdapter(
            audit_event_store=audit_store,
            contract_validator=contract_validator,
        )
        post_mortem_service = PostMortemJudgmentService(
            post_mortem_judgment_registry=post_mortem_registry,
            post_mortem_judgment_audit_adapter=post_mortem_audit_adapter,
        )
        policy_learning_registry = JsonPolicyLearningEvidenceAdmissionRegistry(
            policy_learning_evidence_classes_path=(
                registry_root / "policy_learning_evidence_admission_classes.json"
            ),
            policy_learning_evidence_templates_path=(
                registry_root / "policy_learning_evidence_admission_templates.json"
            ),
            contract_validator=contract_validator,
        )
        policy_learning_audit_adapter = PolicyLearningEvidenceAdmissionAuditAdapter(
            audit_event_store=audit_store,
            contract_validator=contract_validator,
        )
        policy_learning_service = PolicyLearningEvidenceAdmissionService(
            policy_learning_evidence_admission_registry=policy_learning_registry,
            policy_learning_evidence_admission_audit_adapter=(
                policy_learning_audit_adapter
            ),
        )
        policy_learning_update_threshold_registry = (
            JsonPolicyLearningUpdateThresholdRegistry(
                policy_learning_update_threshold_classes_path=(
                    registry_root / "policy_learning_update_threshold_classes.json"
                ),
                policy_learning_update_threshold_templates_path=(
                    registry_root / "policy_learning_update_threshold_templates.json"
                ),
                contract_validator=contract_validator,
            )
        )
        policy_learning_update_threshold_audit_adapter = (
            PolicyLearningUpdateThresholdAuditAdapter(
                audit_event_store=audit_store,
                contract_validator=contract_validator,
            )
        )
        policy_learning_update_threshold_service = (
            PolicyLearningUpdateThresholdService(
                policy_learning_update_threshold_registry=(
                    policy_learning_update_threshold_registry
                ),
                policy_learning_update_threshold_audit_adapter=(
                    policy_learning_update_threshold_audit_adapter
                ),
            )
        )
        policy_learning_update_approval_registry = (
            JsonPolicyLearningUpdateApprovalRegistry(
                policy_learning_update_approval_classes_path=(
                    registry_root / "policy_learning_update_approval_classes.json"
                ),
                policy_learning_update_approval_templates_path=(
                    registry_root / "policy_learning_update_approval_templates.json"
                ),
                contract_validator=contract_validator,
            )
        )
        policy_learning_update_approval_audit_adapter = (
            PolicyLearningUpdateApprovalAuditAdapter(
                audit_event_store=audit_store,
                contract_validator=contract_validator,
            )
        )
        policy_learning_update_approval_service = (
            PolicyLearningUpdateApprovalService(
                policy_learning_update_approval_registry=(
                    policy_learning_update_approval_registry
                ),
                policy_learning_update_approval_audit_adapter=(
                    policy_learning_update_approval_audit_adapter
                ),
            )
        )
        policy_learning_update_preparation_registry = (
            JsonPolicyLearningUpdatePreparationRegistry(
                policy_learning_update_preparation_classes_path=(
                    registry_root / "policy_learning_update_preparation_classes.json"
                ),
                policy_learning_update_preparation_templates_path=(
                    registry_root / "policy_learning_update_preparation_templates.json"
                ),
                contract_validator=contract_validator,
            )
        )
        policy_learning_update_preparation_audit_adapter = (
            PolicyLearningUpdatePreparationAuditAdapter(
                audit_event_store=audit_store,
                contract_validator=contract_validator,
            )
        )
        policy_learning_update_preparation_service = (
            PolicyLearningUpdatePreparationService(
                policy_learning_update_preparation_registry=(
                    policy_learning_update_preparation_registry
                ),
                policy_learning_update_preparation_audit_adapter=(
                    policy_learning_update_preparation_audit_adapter
                ),
            )
        )
        policy_learning_update_mutation_planning_registry = (
            JsonPolicyLearningUpdateMutationPlanningRegistry(
                policy_learning_update_mutation_planning_classes_path=(
                    registry_root
                    / "policy_learning_update_mutation_planning_classes.json"
                ),
                policy_learning_update_mutation_planning_templates_path=(
                    registry_root
                    / "policy_learning_update_mutation_planning_templates.json"
                ),
                contract_validator=contract_validator,
            )
        )
        policy_learning_update_mutation_planning_audit_adapter = (
            PolicyLearningUpdateMutationPlanningAuditAdapter(
                audit_event_store=audit_store,
                contract_validator=contract_validator,
            )
        )
        policy_learning_update_mutation_planning_service = (
            PolicyLearningUpdateMutationPlanningService(
                policy_learning_update_mutation_planning_registry=(
                    policy_learning_update_mutation_planning_registry
                ),
                policy_learning_update_mutation_planning_audit_adapter=(
                    policy_learning_update_mutation_planning_audit_adapter
                ),
            )
        )
        policy_learning_update_mutation_execution_registry = (
            JsonPolicyLearningUpdateMutationExecutionRegistry(
                policy_learning_update_mutation_execution_classes_path=(
                    registry_root
                    / "policy_learning_update_mutation_execution_classes.json"
                ),
                policy_learning_update_mutation_execution_templates_path=(
                    registry_root
                    / "policy_learning_update_mutation_execution_templates.json"
                ),
                contract_validator=contract_validator,
            )
        )
        policy_learning_update_mutation_execution_audit_adapter = (
            PolicyLearningUpdateMutationExecutionAuditAdapter(
                audit_event_store=audit_store,
                contract_validator=contract_validator,
            )
        )
        policy_learning_update_mutation_execution_service = (
            PolicyLearningUpdateMutationExecutionService(
                policy_learning_update_mutation_execution_registry=(
                    policy_learning_update_mutation_execution_registry
                ),
                policy_learning_update_mutation_execution_audit_adapter=(
                    policy_learning_update_mutation_execution_audit_adapter
                ),
            )
        )
        release_registry = JsonReleaseRegistry(
            promotion_readiness_classes_path=(
                registry_root / "promotion_readiness_classes.json"
            ),
            promotion_readiness_templates_path=(
                registry_root / "promotion_readiness_templates.json"
            ),
            rollout_scope_classes_path=(registry_root / "rollout_scope_classes.json"),
            rollout_scope_templates_path=(
                registry_root / "rollout_scope_templates.json"
            ),
            rollback_trigger_classes_path=(
                registry_root / "rollback_trigger_classes.json"
            ),
            rollback_trigger_templates_path=(
                registry_root / "rollback_trigger_templates.json"
            ),
            release_watch_discipline_classes_path=(
                registry_root / "release_watch_discipline_classes.json"
            ),
            release_watch_discipline_templates_path=(
                registry_root / "release_watch_discipline_templates.json"
            ),
            release_confirmation_classes_path=(
                registry_root / "release_confirmation_classes.json"
            ),
            release_confirmation_templates_path=(
                registry_root / "release_confirmation_templates.json"
            ),
            production_entitlement_check_classes_path=(
                registry_root / "production_entitlement_check_classes.json"
            ),
            production_entitlement_check_templates_path=(
                registry_root / "production_entitlement_check_templates.json"
            ),
            contained_rollback_classes_path=(
                registry_root / "contained_rollback_classes.json"
            ),
            contained_rollback_templates_path=(
                registry_root / "contained_rollback_templates.json"
            ),
            release_audit_trace_classes_path=(
                registry_root / "release_audit_trace_classes.json"
            ),
            release_audit_trace_templates_path=(
                registry_root / "release_audit_trace_templates.json"
            ),
            contract_validator=contract_validator,
        )
        promotion_readiness_audit_adapter = PromotionReadinessAuditAdapter(
            audit_event_store=audit_store,
            contract_validator=contract_validator,
        )
        promotion_readiness_gate = PromotionReadinessGate(
            release_registry=release_registry,
            promotion_readiness_audit_adapter=promotion_readiness_audit_adapter,
        )
        rollout_scope_audit_adapter = RolloutScopeAuditAdapter(
            audit_event_store=audit_store,
            contract_validator=contract_validator,
        )
        rollout_scope_controller = RolloutScopeController(
            release_registry=release_registry,
            rollout_scope_audit_adapter=rollout_scope_audit_adapter,
        )
        rollback_trigger_audit_adapter = RollbackTriggerAuditAdapter(
            audit_event_store=audit_store,
            contract_validator=contract_validator,
        )
        rollback_trigger_guard = RollbackTriggerGuard(
            release_registry=release_registry,
            rollback_trigger_audit_adapter=rollback_trigger_audit_adapter,
        )
        release_watch_discipline_audit_adapter = ReleaseWatchDisciplineAuditAdapter(
            audit_event_store=audit_store,
            contract_validator=contract_validator,
        )
        release_watch_discipline = ReleaseWatchDiscipline(
            release_registry=release_registry,
            release_watch_discipline_audit_adapter=(
                release_watch_discipline_audit_adapter
            ),
        )
        release_confirmation_audit_adapter = ReleaseConfirmationAuditAdapter(
            audit_event_store=audit_store,
            contract_validator=contract_validator,
        )
        release_confirmation = ReleaseConfirmation(
            release_registry=release_registry,
            release_confirmation_audit_adapter=release_confirmation_audit_adapter,
        )
        production_entitlement_check_audit_adapter = (
            ProductionEntitlementCheckAuditAdapter(
                audit_event_store=audit_store,
                contract_validator=contract_validator,
            )
        )
        production_entitlement_check = ProductionEntitlementCheck(
            release_registry=release_registry,
            production_entitlement_check_audit_adapter=(
                production_entitlement_check_audit_adapter
            ),
        )
        contained_rollback_audit_adapter = ContainedRollbackAuditAdapter(
            audit_event_store=audit_store,
            contract_validator=contract_validator,
        )
        contained_rollback = ContainedRollback(
            release_registry=release_registry,
            contained_rollback_audit_adapter=contained_rollback_audit_adapter,
        )
        release_audit_trace_audit_adapter = ReleaseAuditTraceAuditAdapter(
            audit_event_store=audit_store,
            contract_validator=contract_validator,
        )
        release_audit_trace = ReleaseAuditTrace(
            release_registry=release_registry,
            release_audit_trace_audit_adapter=release_audit_trace_audit_adapter,
        )
        transition_validator = TransitionValidator(
            state_model_registry=state_model_registry,
            authority_resolution_service=authority_resolution_service,
        )
        transition_audit_adapter = CaseTransitionAuditAdapter(audit_store)
        state_manager = CaseStateManager(
            state_model_registry=state_model_registry,
            transition_validator=transition_validator,
            router_service=router_service,
            review_trigger_service=review_trigger_service,
            human_review_packet_builder=human_review_packet_builder,
            review_resolution_service=review_resolution_service,
            recommendation_service=recommendation_service,
            policy_output_service=policy_output_service,
            portfolio_output_service=portfolio_output_service,
            action_instruction_service=action_instruction_service,
            execution_request_service=execution_request_service,
            execution_dispatch_service=execution_dispatch_service,
            execution_outcome_service=execution_outcome_service,
            post_mortem_judgment_service=post_mortem_service,
            policy_learning_evidence_admission_service=policy_learning_service,
            policy_learning_update_threshold_service=(
                policy_learning_update_threshold_service
            ),
            policy_learning_update_approval_service=(
                policy_learning_update_approval_service
            ),
            policy_learning_update_preparation_service=(
                policy_learning_update_preparation_service
            ),
            policy_learning_update_mutation_planning_service=(
                policy_learning_update_mutation_planning_service
            ),
            policy_learning_update_mutation_execution_service=(
                policy_learning_update_mutation_execution_service
            ),
            promotion_readiness_gate=promotion_readiness_gate,
            rollout_scope_controller=rollout_scope_controller,
            rollback_trigger_guard=rollback_trigger_guard,
            release_watch_discipline=release_watch_discipline,
            release_confirmation=release_confirmation,
            production_entitlement_check=production_entitlement_check,
            contained_rollback=contained_rollback,
            release_audit_trace=release_audit_trace,
            transition_audit_adapter=transition_audit_adapter,
        )

        feature_registry = FeatureRegistry(
            owner_registry=JsonFeatureOwnerRegistry(registry_root / "feature_owners.json"),
            repository=InMemoryFeatureDefinitionRepository(),
            contract_validator=contract_validator,
            audit_event_store=audit_store,
        )
        raw_pipeline = RawIngestionPipeline(
            source_registry=JsonIngestionSourceRegistry(registry_root / "ingestion_sources.json"),
            repository=InMemoryRawRecordRepository(),
            contract_validator=contract_validator,
            audit_event_store=audit_store,
        )
        case_orchestrator = CaseEpisodeOrchestrator(
            case_type_registry=JsonCaseTypeRegistry(registry_root / "case_episode_registry.json"),
            repository=InMemoryCaseEpisodeRepository(),
            contract_validator=contract_validator,
            audit_event_store=audit_store,
            feature_lookup=feature_registry,
            state_manager=state_manager,
        )

        correlation_id = str(uuid4())
        actor_id = "bootstrap"
        ready_post_mortem_context = {
            "evidence_quality": "strong_reconstructible_evidence",
            "confidence_posture": "confident_for_attribution",
            "rationale_snapshot": (
                "Recommendation intent, execution realization, and observed outcome "
                "remain aligned enough to preserve the disciplined path."
            ),
            "evidence_basis_summary": (
                "Case, recommendation, execution, and outcome lineage remain "
                "complete enough to support strong attribution."
            ),
            "learning_direction": "preserve_current_path",
            "secondary_contributing_factors": ["stable_execution_conditions"],
        }
        blocked_post_mortem_context = {
            "evidence_quality": "mixed_evidence_requires_caution",
            "confidence_posture": "cautious_for_review_only",
        }
        fallback_post_mortem_context = {
            "evidence_quality": "immature_observation_horizon",
            "confidence_posture": "insufficient_for_confident_judgment",
            "rationale_snapshot": (
                "The governed observation horizon remains immature, so the platform "
                "must preserve insufficient-evidence posture rather than claim a "
                "confident attribution."
            ),
            "evidence_basis_summary": (
                "Outcome lineage is preserved, but the deferred observation posture "
                "does not yet support strong attribution."
            ),
            "learning_direction": "defer_learning_until_evidence_matures",
            "evidence_gaps": ["mature_realized_execution_observation"],
        }
        ready_policy_learning_admission_context = {
            "learning_scope_reference": "learning-scope:bootstrap-store-001",
            "candidate_update_direction": "preserve_current_path",
            "comparability_judgment": "comparable_case_set_confirmed",
            "commercial_interpretability_summary": (
                "The admitted evidence preserves decision-loop lineage, stable store "
                "scope, and commercially interpretable realized consequence."
            ),
            "proposed_update_scope": "scope:bootstrap-store-001",
            "comparable_case_set_reference": "case-set:bootstrap-store-001:stable-window",
            "memory_object_reference": "decision-memory:bootstrap-store-001:episode-cluster",
        }
        blocked_policy_learning_admission_context = {
            "candidate_update_direction": "preserve_current_path"
        }
        fallback_policy_learning_admission_context = {
            "learning_scope_reference": "learning-scope:bootstrap-store-001",
            "candidate_update_direction": "defer_adaptation_pending_more_evidence",
            "comparability_judgment": "comparable_case_set_pending_more_cases",
            "commercial_interpretability_summary": (
                "The evidence is structurally interpretable, but the observation horizon "
                "is still immature for update-threshold review."
            ),
            "proposed_update_scope": "scope:bootstrap-store-001",
            "restriction_summary": "defer_learning_until_evidence_matures",
            "comparable_case_set_reference": "case-set:bootstrap-store-001:pending-horizon",
        }
        accepted_policy_learning_update_threshold_context = {
            "policy_behavior_change": "narrow_price_response_band",
            "update_severity": "local_policy_adjustment",
            "update_scope": "scope:bootstrap-store-001",
            "evidence_base_summary": (
                "Repeated comparable cases, strong attribution, and bounded local scope support a governed local adjustment."
            ),
            "evidence_completeness": "strong",
            "evidence_consistency": "strong",
            "evidence_comparability": "strong",
            "attribution_quality": "strong",
            "scope_legitimacy": "strong",
            "transfer_validity": "strong",
            "magnitude_alignment": "strong",
            "repetition_posture": "repeated_comparable_cases",
            "commercial_significance": "high",
            "governance_sensitivity": "moderate",
        }
        below_threshold_policy_learning_update_threshold_context = {
            **accepted_policy_learning_update_threshold_context,
            "update_severity": "broad_policy_change",
            "evidence_consistency": "moderate",
            "transfer_validity": "moderate",
            "magnitude_alignment": "moderate",
            "repetition_posture": "single_case_only",
            "unresolved_competing_explanations": [
                "execution_noise_not_fully_excluded"
            ],
        }
        narrowed_policy_learning_update_threshold_context = {
            **accepted_policy_learning_update_threshold_context,
            "update_scope": "scope:bootstrap-store-001:promo-window",
            "evidence_consistency": "moderate",
            "transfer_validity": "moderate",
            "magnitude_alignment": "moderate",
            "repetition_posture": "limited_repetition",
            "local_contradiction_posture": (
                "local_scope_contradiction_requires_narrowing"
            ),
            "narrowed_scope_reference": "scope:bootstrap-store-001:promo-window",
        }
        deferred_policy_learning_update_threshold_context = {
            **accepted_policy_learning_update_threshold_context,
            "update_severity": "broad_policy_change",
            "update_scope": "scope:network:banner-a",
            "evidence_base_summary": (
                "The evidence is meaningful enough to preserve, but the observation horizon and case repetition remain too weak for present change."
            ),
            "evidence_completeness": "moderate",
            "evidence_consistency": "weak",
            "evidence_comparability": "moderate",
            "attribution_quality": "weak",
            "scope_legitimacy": "moderate",
            "transfer_validity": "weak",
            "magnitude_alignment": "weak",
            "repetition_posture": "single_case_only",
            "commercial_significance": "moderate",
            "governance_sensitivity": "high",
            "monitoring_recommendation": (
                "continue_monitoring_and_accumulate_comparable_cases"
            ),
            "unresolved_competing_explanations": [
                "regime_shift_not_yet_excluded",
                "execution_variance_not_fully_separated",
            ],
        }
        approved_policy_learning_update_approval_context = {
            "candidate_update_reference": (
                "candidate-update:bootstrap-store-001:price-band"
            ),
            "approval_summary": (
                "Threshold evidence and governance controls support preparation of a bounded policy update package."
            ),
            "change_control_reference": (
                "change-control:bootstrap-store-001:price-band"
            ),
            "preparation_scope_reference": "scope:bootstrap-store-001",
            "preparation_boundary_summary": (
                "Approval covers preparation only; actual mutation, deployment, and monitoring remain separately governed."
            ),
            "governance_readiness": "strong",
            "change_control_readiness": "strong",
            "boundary_control_strength": "strong",
            "preparation_readiness": "strong",
        }
        restricted_policy_learning_update_approval_context = {
            **approved_policy_learning_update_approval_context,
            "preparation_scope_reference": "scope:bootstrap-store-001:promo-window",
            "governance_readiness": "moderate",
            "change_control_readiness": "moderate",
            "boundary_control_strength": "moderate",
            "preparation_readiness": "moderate",
            "restriction_summary": (
                "Preparation is limited to the narrowed local scope supported by the governed threshold evidence."
            ),
            "preparation_scope_restriction_reference": (
                "scope:bootstrap-store-001:promo-window"
            ),
        }
        deferred_policy_learning_update_approval_context = {
            **approved_policy_learning_update_approval_context,
            "governance_readiness": "moderate",
            "change_control_readiness": "weak",
            "boundary_control_strength": "moderate",
            "preparation_readiness": "weak",
            "additional_governance_requirements": [
                "governance_board_recheck",
                "policy_risk_review",
            ],
            "unresolved_governance_gaps": [
                "cross_region_change_control_pending"
            ],
            "follow_up_review_reference": "review:bootstrap-policy-governance:001",
        }
        rejected_policy_learning_update_approval_context = {
            **approved_policy_learning_update_approval_context,
            "governance_readiness": "weak",
            "change_control_readiness": "weak",
            "boundary_control_strength": "moderate",
            "preparation_readiness": "weak",
        }
        prepared_policy_learning_update_preparation_context = {
            "preparation_package_reference": (
                "preparation-package:bootstrap-store-001:price-band"
            ),
            "preparation_summary": (
                "Approved update evidence has been packaged for bounded policy-mutation planning."
            ),
            "mutation_planning_scope_reference": "scope:bootstrap-store-001",
            "preparation_artifact_boundary_summary": (
                "Preparation package supports mutation planning only; actual mutation, deployment, and monitoring remain separately governed."
            ),
            "artifact_readiness": "strong",
            "planning_readiness": "strong",
            "prerequisite_readiness": "strong",
        }
        restricted_policy_learning_update_preparation_context = {
            **prepared_policy_learning_update_preparation_context,
            "mutation_planning_scope_reference": (
                "scope:bootstrap-store-001:promo-window"
            ),
            "artifact_readiness": "moderate",
            "planning_readiness": "moderate",
            "prerequisite_readiness": "moderate",
            "restriction_summary": (
                "Prepared package remains limited to the narrowed local scope approved upstream."
            ),
            "preparation_scope_restriction_reference": (
                "scope:bootstrap-store-001:promo-window"
            ),
        }
        deferred_policy_learning_update_preparation_context = {
            **prepared_policy_learning_update_preparation_context,
            "artifact_readiness": "moderate",
            "planning_readiness": "moderate",
            "prerequisite_readiness": "weak",
            "preparation_prerequisite_reference": (
                "preparation-prerequisites:bootstrap-store-001:price-band"
            ),
            "outstanding_preparation_prerequisites": [
                "change_window_confirmation",
                "rollback_validation",
            ],
            "follow_up_review_reference": "review:bootstrap-preparation-readiness:001",
        }
        rejected_policy_learning_update_preparation_context = {
            **prepared_policy_learning_update_preparation_context,
            "artifact_readiness": "weak",
            "planning_readiness": "weak",
            "prerequisite_readiness": "weak",
        }
        prepared_policy_learning_update_mutation_planning_context = {
            "mutation_plan_reference": (
                "mutation-plan:bootstrap-store-001:price-band"
            ),
            "mutation_planning_summary": (
                "Prepared update package has been translated into a bounded mutation plan candidate."
            ),
            "mutation_plan_scope_reference": "scope:bootstrap-store-001",
            "mutation_planning_boundary_summary": (
                "Mutation planning remains bounded to plan formulation only; execution, rollout, deployment, and monitoring remain separately governed."
            ),
            "mutation_planning_scope_reference": "scope:bootstrap-store-001",
            "artifact_readiness": "strong",
            "planning_readiness": "strong",
            "prerequisite_readiness": "strong",
            "mutation_readiness": "strong",
            "safeguard_readiness": "strong",
            "rollback_readiness": "strong",
        }
        restricted_policy_learning_update_mutation_planning_context = {
            **prepared_policy_learning_update_mutation_planning_context,
            "mutation_planning_scope_reference": (
                "scope:bootstrap-store-001:promo-window"
            ),
            "artifact_readiness": "moderate",
            "planning_readiness": "moderate",
            "prerequisite_readiness": "moderate",
            "mutation_readiness": "moderate",
            "safeguard_readiness": "moderate",
            "rollback_readiness": "moderate",
            "restriction_summary": (
                "Mutation planning remains limited to the narrowed local scope carried forward from preparation."
            ),
            "mutation_scope_restriction_reference": (
                "scope:bootstrap-store-001:promo-window"
            ),
        }
        deferred_policy_learning_update_mutation_planning_context = {
            **prepared_policy_learning_update_mutation_planning_context,
            "artifact_readiness": "moderate",
            "planning_readiness": "moderate",
            "prerequisite_readiness": "moderate",
            "mutation_readiness": "moderate",
            "safeguard_readiness": "moderate",
            "rollback_readiness": "moderate",
            "mutation_planning_prerequisite_reference": (
                "mutation-planning-prerequisites:bootstrap-store-001:price-band"
            ),
            "outstanding_mutation_planning_prerequisites": [
                "change_window_confirmation",
                "rollback_validation",
            ],
            "follow_up_review_reference": (
                "review:bootstrap-mutation-planning-readiness:001"
            ),
        }
        rejected_policy_learning_update_mutation_planning_context = {
            **prepared_policy_learning_update_mutation_planning_context,
            "artifact_readiness": "weak",
            "planning_readiness": "weak",
            "prerequisite_readiness": "weak",
            "mutation_readiness": "weak",
            "safeguard_readiness": "weak",
            "rollback_readiness": "weak",
        }
        executed_policy_learning_update_mutation_execution_context = {
            "policy_mutation_payload": (
                "mutation-payload:bootstrap-store-001:price-band:v1"
            ),
            "policy_mutation_execution_reference": (
                "policy-mutation-execution:bootstrap-store-001:price-band"
            ),
            "mutated_policy_reference": (
                "policy-version:bootstrap-store-001:price-band:v2"
            ),
            "mutation_execution_summary": (
                "The governed mutation plan has been executed against the bounded policy asset without widening into rollout, deployment, or retraining semantics."
            ),
            "mutation_execution_scope_reference": "scope:bootstrap-store-001",
            "mutation_execution_boundary_summary": (
                "Mutation execution remains bounded to the policy asset mutation itself; rollout, deployment, retraining, model update, and monitoring remain separately governed."
            ),
            "mutation_readiness": "strong",
            "safeguard_readiness": "strong",
            "rollback_readiness": "strong",
            "execution_readiness": "strong",
            "verification_readiness": "strong",
            "rollback_execution_readiness": "strong",
        }
        restricted_policy_learning_update_mutation_execution_context = {
            **executed_policy_learning_update_mutation_execution_context,
            "mutation_execution_scope_reference": (
                "scope:bootstrap-store-001:promo-window"
            ),
            "mutation_readiness": "moderate",
            "safeguard_readiness": "moderate",
            "rollback_readiness": "moderate",
            "execution_readiness": "moderate",
            "verification_readiness": "moderate",
            "rollback_execution_readiness": "moderate",
            "restriction_summary": (
                "Mutation execution remains limited to the narrowed local scope carried forward from mutation planning."
            ),
            "mutation_execution_scope_restriction_reference": (
                "scope:bootstrap-store-001:promo-window"
            ),
        }
        deferred_policy_learning_update_mutation_execution_context = {
            **executed_policy_learning_update_mutation_execution_context,
            "mutation_readiness": "moderate",
            "safeguard_readiness": "moderate",
            "rollback_readiness": "moderate",
            "execution_readiness": "moderate",
            "verification_readiness": "moderate",
            "rollback_execution_readiness": "moderate",
            "mutation_execution_prerequisite_reference": (
                "mutation-execution-prerequisites:bootstrap-store-001:price-band"
            ),
            "outstanding_mutation_execution_prerequisites": [
                "validation_checkpoint_confirmation",
                "rollback_rehearsal_confirmation",
            ],
            "follow_up_review_reference": (
                "review:bootstrap-mutation-execution-readiness:001"
            ),
        }
        rejected_policy_learning_update_mutation_execution_context = {
            **executed_policy_learning_update_mutation_execution_context,
            "mutation_readiness": "weak",
            "safeguard_readiness": "weak",
            "rollback_readiness": "weak",
            "execution_readiness": "weak",
            "verification_readiness": "weak",
            "rollback_execution_readiness": "weak",
        }
        ready_promotion_readiness_context = {
            "promotion_candidate_reference": (
                "promotion-candidate:bootstrap-store-001:price-band"
            ),
            "promotion_readiness_summary": (
                "The mutated policy candidate has explicit readiness evidence, bounded entitlement, and reversible promotion posture without widening into rollout-scope execution or rollback-trigger control."
            ),
            "readiness_evidence_reference": (
                "promotion-evidence:bootstrap-store-001:price-band"
            ),
            "promotion_threshold_reference": (
                "promotion-threshold:shared_control_plane:bootstrap-price-band"
            ),
            "production_entitlement_boundary": (
                "entitlement-boundary:shared_control_plane:bootstrap-price-band"
            ),
            "rollback_posture_reference": (
                "rollback-posture:bootstrap-store-001:price-band"
            ),
            "release_watch_window": "watch-window:24h",
            "release_confirmation_threshold_reference": (
                "release-confirmation-threshold:shared_control_plane:bootstrap-price-band"
            ),
            "promotion_scope_reference": "scope:bootstrap-store-001",
            "promotion_boundary_summary": (
                "Promotion readiness remains bounded to entitlement and readiness evidence; rollout-scope control, rollback-trigger control, and live watch execution remain downstream runtime concerns."
            ),
            "validation_readiness": "strong",
            "scope_transfer_readiness": "strong",
            "exposure_control_readiness": "strong",
            "security_posture_readiness": "strong",
            "performance_posture_readiness": "strong",
            "rollback_posture_readiness": "strong",
            "operational_reversibility_readiness": "strong",
            "confirmation_readiness": "strong",
        }
        local_scope_promotion_readiness_context = {
            **ready_promotion_readiness_context,
            "production_entitlement_boundary": (
                "entitlement-boundary:shared_control_plane:bootstrap-price-band:local-only"
            ),
            "promotion_scope_reference": "scope:bootstrap-store-001:promo-window",
            "validation_readiness": "moderate",
            "scope_transfer_readiness": "moderate",
            "exposure_control_readiness": "moderate",
            "security_posture_readiness": "moderate",
            "performance_posture_readiness": "moderate",
            "rollback_posture_readiness": "moderate",
            "operational_reversibility_readiness": "moderate",
            "confirmation_readiness": "moderate",
            "restriction_summary": (
                "Promotion readiness remains limited to the narrowed local scope carried forward from bounded mutation execution."
            ),
            "promotion_scope_restriction_reference": (
                "scope:bootstrap-store-001:promo-window"
            ),
        }
        deferred_promotion_readiness_context = {
            **ready_promotion_readiness_context,
            "validation_readiness": "moderate",
            "scope_transfer_readiness": "moderate",
            "exposure_control_readiness": "moderate",
            "security_posture_readiness": "moderate",
            "performance_posture_readiness": "moderate",
            "rollback_posture_readiness": "moderate",
            "operational_reversibility_readiness": "moderate",
            "confirmation_readiness": "moderate",
            "promotion_prerequisite_reference": (
                "promotion-prerequisites:bootstrap-store-001:price-band"
            ),
            "outstanding_promotion_prerequisites": [
                "release-approval-review",
                "watch-coverage-confirmation",
            ],
            "follow_up_review_reference": "review:promotion-readiness:bootstrap",
        }
        rejected_promotion_readiness_context = {
            **ready_promotion_readiness_context,
            "validation_readiness": "weak",
            "scope_transfer_readiness": "weak",
            "exposure_control_readiness": "weak",
            "security_posture_readiness": "weak",
            "performance_posture_readiness": "weak",
            "rollback_posture_readiness": "weak",
            "operational_reversibility_readiness": "weak",
            "confirmation_readiness": "weak",
        }
        ready_rollout_scope_context = {
            "rollout_scope_boundary_reference": (
                "rollout-scope:bootstrap-store-001:full"
            ),
            "exposure_boundary_reference": (
                "exposure-boundary:bootstrap-store-001:full"
            ),
            "rollout_boundary_summary": (
                "Rollout scope remains explicit, bounded, and exposure-controlled without widening into rollback-trigger control or post-release watch execution."
            ),
        }
        conditional_rollout_scope_context = {
            "rollout_scope_boundary_reference": (
                "rollout-scope:bootstrap-store-001:promo-window"
            ),
            "exposure_boundary_reference": (
                "exposure-boundary:bootstrap-store-001:promo-window"
            ),
            "rollout_boundary_summary": (
                "Conditional production exposure remains explicitly narrowed to the approved local scope while broader entitlement stays ungranted."
            ),
        }
        deferred_rollout_scope_context = {
            **ready_rollout_scope_context,
            "rollout_scope_prerequisite_reference": (
                "rollout-prerequisites:bootstrap-store-001:price-band"
            ),
            "outstanding_rollout_scope_prerequisites": [
                "release-watch-observer-confirmation",
                "exposure-review-cadence-confirmation",
            ],
            "follow_up_review_reference": "review:rollout-scope:bootstrap",
        }
        rejected_rollout_scope_context = {
            **ready_rollout_scope_context,
            "restriction_summary": (
                "Exposure remains narrowed to a local production window."
            ),
            "promotion_scope_restriction_reference": (
                "scope:bootstrap-store-001:promo-window"
            ),
        }
        ready_rollback_trigger_context = {
            "rollback_trigger_reference": (
                "rollback-trigger:bootstrap-store-001:price-band"
            ),
            "rollback_plan_reference": (
                "rollback-plan:bootstrap-store-001:price-band"
            ),
        }
        deferred_rollback_trigger_context = {
            **ready_rollback_trigger_context,
            "rollback_trigger_prerequisite_reference": (
                "rollback-trigger-prerequisites:bootstrap-store-001:price-band"
            ),
            "outstanding_rollback_trigger_prerequisites": [
                "named-watch-response-threshold",
                "release-owner-escalation-confirmation",
            ],
            "follow_up_review_reference": "review:rollback-trigger:bootstrap",
        }
        rejected_rollback_trigger_context = {
            **ready_rollback_trigger_context,
            "restriction_summary": (
                "Exposure remains narrowed to a local production window."
            ),
            "promotion_scope_restriction_reference": (
                "scope:bootstrap-store-001:promo-window"
            ),
        }
        ready_release_watch_discipline_context = {
            "release_watch_discipline_summary": (
                "Post-release watch discipline remains explicit through named watch and confirmation windows, explicit response thresholds, and a named owning surface without widening into watch execution or monitoring."
            ),
            "release_confirmation_window": (
                "release-confirmation-window:bootstrap-store-001:t-plus-7d"
            ),
            "release_response_threshold_reference": (
                "release-response-threshold:bootstrap-store-001:price-band"
            ),
            "release_watch_owner_reference": (
                "release-owner:bootstrap-store-001:price-band"
            ),
            "release_escalation_path_reference": (
                "release-escalation-path:bootstrap-store-001:price-band"
            ),
        }
        deferred_release_watch_discipline_context = {
            **ready_release_watch_discipline_context,
            "release_watch_prerequisite_reference": (
                "release-watch-prerequisites:bootstrap-store-001:price-band"
            ),
            "outstanding_release_watch_prerequisites": [
                "release-watch-owner-confirmation",
                "release-confirmation-window-confirmation",
            ],
            "follow_up_review_reference": (
                "review:release-watch-discipline:bootstrap"
            ),
        }
        rejected_release_watch_discipline_context = {
            **ready_release_watch_discipline_context,
            "restriction_summary": (
                "Exposure remains narrowed to a local production window."
            ),
            "promotion_scope_restriction_reference": (
                "scope:bootstrap-store-001:promo-window"
            ),
        }
        ready_release_confirmation_context = {
            "release_confirmation_judgment": (
                "release-confirmed:bootstrap-store-001:price-band"
            ),
            "release_confirmation_threshold_evidence_reference": (
                "release-confirmation-evidence:bootstrap-store-001:price-band"
            ),
            "release_confirmation_authority_reference": (
                "release-confirmation-authority:bootstrap-store-001:price-band"
            ),
        }
        conditional_release_confirmation_context = {
            **ready_release_confirmation_context,
            "restriction_summary": (
                "Confirmation remains bounded to the approved local production window."
            ),
            "promotion_scope_restriction_reference": (
                "scope:bootstrap-store-001:promo-window"
            ),
        }
        deferred_release_confirmation_context = {
            **ready_release_confirmation_context,
            "release_confirmation_prerequisite_reference": (
                "release-confirmation-prerequisites:bootstrap-store-001:price-band"
            ),
            "outstanding_release_confirmation_prerequisites": [
                "confirmation-authority-signoff",
                "threshold-evidence-reconciliation",
            ],
            "follow_up_review_reference": (
                "review:release-confirmation:bootstrap"
            ),
        }
        rejected_release_confirmation_context = {
            **ready_release_confirmation_context,
            "restriction_summary": (
                "Confirmation remains narrowed to a local production window."
            ),
            "promotion_scope_restriction_reference": (
                "scope:bootstrap-store-001:promo-window"
            ),
        }
        ready_production_entitlement_check_context = {
            "production_entitlement_judgment": (
                "production-entitlement-approved:bootstrap-store-001:price-band"
            ),
            "production_entitlement_evidence_reference": (
                "production-entitlement-evidence:bootstrap-store-001:price-band"
            ),
            "production_entitlement_authority_reference": (
                "production-entitlement-authority:bootstrap-store-001:price-band"
            ),
        }
        conditional_production_entitlement_check_context = {
            **ready_production_entitlement_check_context,
            "restriction_summary": (
                "Production entitlement remains bounded to the approved local production window."
            ),
            "promotion_scope_restriction_reference": (
                "scope:bootstrap-store-001:promo-window"
            ),
        }
        deferred_production_entitlement_check_context = {
            **ready_production_entitlement_check_context,
            "production_entitlement_prerequisite_reference": (
                "production-entitlement-prerequisites:bootstrap-store-001:price-band"
            ),
            "outstanding_production_entitlement_prerequisites": [
                "entitlement-authority-signoff",
                "broader-use-evidence-reconciliation",
            ],
            "follow_up_review_reference": (
                "review:production-entitlement-check:bootstrap"
            ),
        }
        rejected_production_entitlement_check_context = {
            **ready_production_entitlement_check_context,
            "restriction_summary": (
                "Production entitlement remains narrowed to a local production window."
            ),
            "promotion_scope_restriction_reference": (
                "scope:bootstrap-store-001:promo-window"
            ),
        }
        ready_contained_rollback_context = {
            "contained_rollback_judgment": (
                "contained-rollback:bootstrap-store-001:price-band"
            ),
            "rollback_execution_reference": (
                "rollback-execution:bootstrap-store-001:price-band"
            ),
            "containment_evidence_reference": (
                "containment-evidence:bootstrap-store-001:price-band"
            ),
            "bounded_exposure_reference": (
                "bounded-exposure:bootstrap-store-001:price-band"
            ),
            "downstream_effects_boundary_reference": (
                "downstream-effects-boundary:bootstrap-store-001:price-band"
            ),
            "release_lineage_reconstruction_reference": (
                "release-lineage:bootstrap-store-001:price-band:reconstructible"
            ),
            "contained_rollback_authority_reference": (
                "contained-rollback-authority:bootstrap-store-001:price-band"
            ),
        }
        conditional_contained_rollback_context = {
            **ready_contained_rollback_context,
            "restriction_summary": (
                "Rollback containment remains bounded to the approved local production window."
            ),
            "promotion_scope_restriction_reference": (
                "scope:bootstrap-store-001:promo-window"
            ),
        }
        deferred_contained_rollback_context = {
            **ready_contained_rollback_context,
            "contained_rollback_prerequisite_reference": (
                "contained-rollback-prerequisites:bootstrap-store-001:price-band"
            ),
            "outstanding_contained_rollback_prerequisites": [
                "lineage-reconstruction-confirmation",
                "downstream-effects-boundary-review",
            ],
            "follow_up_review_reference": "review:contained-rollback:bootstrap",
        }
        rejected_contained_rollback_context = {
            **ready_contained_rollback_context,
            "restriction_summary": (
                "Rollback containment remains narrowed to a local production window."
            ),
            "promotion_scope_restriction_reference": (
                "scope:bootstrap-store-001:promo-window"
            ),
        }
        ready_release_audit_trace_context = {
            "release_audit_trace_judgment": (
                "release-audit-trace:bootstrap-store-001:price-band"
            ),
            "release_control_lineage_reference": (
                "release-control-lineage:bootstrap-store-001:price-band"
            ),
            "invalid_release_state_visibility_reference": (
                "invalid-release-state-visibility:bootstrap-store-001:price-band"
            ),
            "invalid_exposure_visibility_reference": (
                "invalid-exposure-visibility:bootstrap-store-001:price-band"
            ),
            "no_silent_promotion_preservation_reference": (
                "no-silent-promotion-preservation:bootstrap-store-001:price-band"
            ),
            "release_audit_trace_authority_reference": (
                "release-audit-trace-authority:bootstrap-store-001:price-band"
            ),
        }
        deferred_release_audit_trace_context = {
            **ready_release_audit_trace_context,
            "release_audit_trace_prerequisite_reference": (
                "release-audit-trace-prerequisites:bootstrap-store-001:price-band"
            ),
            "outstanding_release_audit_trace_prerequisites": [
                "later-final-disposition-reference",
                "invalid-release-state-visibility-confirmation",
            ],
            "later_final_disposition_reference": (
                "final-disposition:bootstrap-store-001:price-band"
            ),
            "follow_up_review_reference": "review:release-audit-trace:bootstrap",
        }
        rejected_release_audit_trace_context = {
            **ready_release_audit_trace_context,
            "restriction_summary": (
                "Trace remains narrowed to a bounded conditional production exposure."
            ),
            "promotion_scope_restriction_reference": (
                "scope:bootstrap-store-001:promo-window"
            ),
        }

        feature = feature_registry.register_feature(
            FeatureDefinition(
                name="shared.control.revenue_delta",
                namespace="shared.control",
                owner_id="shared_control_plane",
                description="Expected revenue delta used to seed the first shared case flow.",
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
            correlation_id=correlation_id,
            actor_id=actor_id,
        )

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
            correlation_id=correlation_id,
            actor_id=actor_id,
        )
        raw_record = ingestion_result.accepted_records[0]

        episode = case_orchestrator.open_episode(
            case_type="shared_control_plane_case",
            case_key=f"case:{raw_record.source_record_id}",
            raw_record_ids=(raw_record.raw_record_id,),
            feature_names=(feature.name,),
            correlation_id=correlation_id,
            actor_id=actor_id,
            actor_role="case_operator",
            threshold_context={"impact_score": 0.15},
        )

        try:
            case_orchestrator.record_handoff(
                episode.episode_id,
                to_stage="case_orchestration",
                transition_name="promote_to_case_assessment",
                reason="This direct jump should fail because feature review has not been completed.",
                correlation_id=correlation_id,
                actor_id=actor_id,
                actor_role="case_operator",
            )
        except InvalidTransitionError:
            pass

        feature_review_episode = case_orchestrator.record_handoff(
            episode.episode_id,
            to_stage="feature_registry",
            transition_name="promote_to_feature_review",
            reason="Delegated authority advances the case into feature review.",
            correlation_id=correlation_id,
            actor_id=actor_id,
            actor_role="assistant_case_operator",
        )

        try:
            case_orchestrator.record_handoff(
                feature_review_episode.episode_id,
                to_stage="case_orchestration",
                transition_name="promote_to_case_assessment",
                reason="Delegated authority should be blocked above its ceiling.",
                correlation_id=correlation_id,
                actor_id=actor_id,
                actor_role="assistant_case_operator",
            )
        except TransitionBlockedError:
            pass

        try:
            case_orchestrator.interrupt_episode(
                feature_review_episode.episode_id,
                transition_name="promote_to_case_assessment",
                reason="A shadow delegate should not act without explicit delegation policy.",
                correlation_id=correlation_id,
                actor_id=actor_id,
                actor_role="shadow_case_delegate",
            )
        except (TransitionBlockedError, InvalidTransitionError):
            pass

        assessed_episode = case_orchestrator.record_handoff(
            feature_review_episode.episode_id,
            to_stage="case_orchestration",
            transition_name="promote_to_case_assessment",
            reason="Direct authority advances the case into governed assessment.",
            correlation_id=correlation_id,
            actor_id=actor_id,
            actor_role="case_operator",
            threshold_context={"impact_score": 0.76},
            packet_context={
                "review_focus": "Assess whether the elevated impact score warrants accountable manual review."
            },
            review_resolution_class_id="resolved_with_action",
            review_resolution_context={
                "review_summary": "A governed reviewer confirmed that accountable downstream action preparation is warranted.",
                "resolution_rationale": "The case crossed the required review threshold and preserved enough context to fix an action-routing disposition.",
                "recommendation_reference": "bootstrap-recommendation-placeholder-001",
            },
            recommendation_class_id="recommend_act_now",
            recommendation_context={
                "recommendation_summary": "Act now while preserving the advisory-only recommendation boundary.",
                "action_path_reference": "action-path:bootstrap-direct-action-001",
                "scope_reference": "scope:store:001",
                "confidence_summary": "high_confidence",
                "constraint_summary": "inventory_and_margin_checked",
                "uncertainty_summary": "remaining_regime_uncertainty_is_bounded",
                "failure_state_context": "no_active_failure_state_detected",
            },
            policy_output_class_id="policy_shaped_allowance",
            policy_output_context={
                "policy_summary": "Preserve bounded allowance for downstream action preparation while keeping commitment and instruction separate.",
                "policy_output_reference": "policy-output:bootstrap-allowance-001",
                "policy_rationale": "Review and recommendation lineage justify a bounded policy allowance for downstream preparation.",
                "action_boundary_summary": "Policy-shaped allowance only; downstream commitment and instruction remain separately governed.",
                "allowance_reference": "allowance:bootstrap-store-001:price-adjustment-window",
            },
            portfolio_output_class_id="portfolio_bounded_allocation",
            portfolio_output_context={
                "portfolio_summary": "Preserve bounded allocation posture for downstream portfolio planning while keeping commitment and instruction separate.",
                "portfolio_output_reference": "portfolio-output:bootstrap-allocation-001",
                "portfolio_rationale": "Policy allowance lineage justifies bounded allocation posture for downstream planning.",
                "action_boundary_summary": "Allocative only; downstream commitment and instruction remain separately governed.",
                "allocation_reference": "allocation:bootstrap-store-001:price-adjustment-window",
                "allocation_weight_reference": "allocation-weight:bootstrap-store-001:0.72",
            },
            action_instruction_class_id="direct_action_instruction",
            action_instruction_context={
                "instruction_summary": "Issue a governed downstream preparation instruction while keeping execution separate from instruction legitimacy.",
                "action_instruction_reference": "action-instruction:bootstrap-direct-001",
                "upstream_commitment_reference": "commitment-placeholder:bootstrap-direct-001",
                "instruction_authority_reference": "instruction-authority:case-operator",
                "executable_scope_reference": "scope:bootstrap-store-001:price-adjustment-window",
                "intended_action_reference": "intended-action:bootstrap-price-adjustment-001",
                "action_delivery_channel": "downstream_preparation_handoff",
            },
            execution_request_class_id="direct_dispatch_request",
            execution_request_context={
                "execution_request_summary": "Prepare a governed dispatch request while keeping execution separate from request legitimacy.",
                "execution_request_reference": "execution-request:bootstrap-direct-001",
                "execution_target_reference": "execution-target:bootstrap-price-adjustment-001",
                "execution_scope_reference": "scope:bootstrap-store-001:price-adjustment-window",
                "execution_timing_reference": "timing:bootstrap-price-adjustment-window",
                "execution_request_channel": "governed_dispatch_handoff",
                "execution_priority_reference": "dispatch-priority:bootstrap-high",
            },
            execution_dispatch_class_id="direct_dispatch_boundary",
            execution_dispatch_context={
                "dispatch_summary": "Materialize a governed execution-dispatch boundary while keeping broker placement and actual execution separate.",
                "dispatch_reference": "execution-dispatch:bootstrap-direct-001",
                "dispatch_channel": "governed_dispatch_boundary_handoff",
                "dispatch_payload_reference": "dispatch-boundary-payload:bootstrap-direct-001",
                "dispatch_window_reference": "dispatch-window:bootstrap-price-adjustment-window",
                "dispatch_priority_reference": "dispatch-priority:bootstrap-high",
            },
            execution_outcome_class_id="favorable_realized_outcome",
            execution_outcome_context={
                "observation_basis": "post_dispatch_observation",
                "observation_horizon_reference": "horizon:bootstrap-t-plus-7d",
                "comparison_basis": "dispatch_target_vs_observed_execution",
                "feedback_maturity_posture": "stabilized_observation",
                "feedback_reuse_boundary": "governed_post_mortem_and_memory_only",
                "tenant_scope_reference": "tenant:bootstrap-store-001",
                "executed_action_reference": "execution-target:bootstrap-price-adjustment-001",
                "realized_outcome_reference": "outcome:bootstrap-revenue-improvement-001",
                "outcome_summary": "The governed dispatch intent was realized within the expected observation horizon.",
                "decision_scope_reference": "scope:bootstrap-store-001:price-adjustment-window",
                "reporting_scope_reference": "reporting:bootstrap-store-001:weekly",
                "execution_condition_references": [
                    "condition:bootstrap-inventory-available",
                    "condition:bootstrap-margin-threshold-respected"
                ]
            },
            post_mortem_judgment_class_id="correct_recommendation_correct_execution",
            post_mortem_judgment_context=ready_post_mortem_context,
            policy_learning_evidence_class_id="policy_learning_review_candidate",
            policy_learning_evidence_admission_context=(
                ready_policy_learning_admission_context
            ),
            policy_learning_update_threshold_class_id="policy_update_candidate",
            policy_learning_update_threshold_context=(
                accepted_policy_learning_update_threshold_context
            ),
            policy_learning_update_approval_class_id=(
                "policy_update_preparation_candidate"
            ),
            policy_learning_update_approval_context=(
                approved_policy_learning_update_approval_context
            ),
            policy_learning_update_preparation_class_id=(
                "policy_mutation_planning_candidate"
            ),
            policy_learning_update_preparation_context=(
                prepared_policy_learning_update_preparation_context
            ),
            policy_learning_update_mutation_planning_class_id=(
                "policy_mutation_plan_candidate"
            ),
            policy_learning_update_mutation_planning_context=(
                prepared_policy_learning_update_mutation_planning_context
            ),
            policy_learning_update_mutation_execution_class_id=(
                "policy_mutation_execution_candidate"
            ),
            policy_learning_update_mutation_execution_context=(
                executed_policy_learning_update_mutation_execution_context
            ),
            promotion_readiness_class_id=(
                "full_scope_production_promotion_candidate"
            ),
            promotion_readiness_context=ready_promotion_readiness_context,
            rollout_scope_class_id="full_scope_production_promotion_candidate",
            rollout_scope_context=ready_rollout_scope_context,
            rollback_trigger_class_id="full_scope_production_promotion_candidate",
            rollback_trigger_context=ready_rollback_trigger_context,
            release_watch_discipline_class_id=(
                "full_scope_production_promotion_candidate"
            ),
            release_watch_discipline_context=ready_release_watch_discipline_context,
            release_confirmation_class_id=(
                "full_scope_production_promotion_candidate"
            ),
            release_confirmation_context=ready_release_confirmation_context,
            production_entitlement_check_class_id=(
                "full_scope_production_promotion_candidate"
            ),
            production_entitlement_check_context=(
                ready_production_entitlement_check_context
            ),
            contained_rollback_class_id=(
                "full_scope_production_promotion_candidate"
            ),
            contained_rollback_context=ready_contained_rollback_context,
            release_audit_trace_class_id=(
                "full_scope_production_promotion_candidate"
            ),
            release_audit_trace_context=ready_release_audit_trace_context,
        )
        interrupted_episode = case_orchestrator.interrupt_episode(
            assessed_episode.episode_id,
            transition_name="interrupt_case_assessment",
            reason="External review input temporarily interrupts the active case.",
            correlation_id=correlation_id,
            actor_id=actor_id,
            actor_role="case_operator",
        )

        try:
            case_orchestrator.resume_episode(
                interrupted_episode.episode_id,
                transition_name="resume_case_assessment",
                reason="Observer is not allowed to resume the case.",
                correlation_id=correlation_id,
                actor_id=actor_id,
                actor_role="observer",
            )
        except TransitionBlockedError:
            pass

        resumed_episode = case_orchestrator.resume_episode(
            interrupted_episode.episode_id,
            transition_name="resume_case_assessment",
            reason="Required authority restores the case to active assessment.",
            correlation_id=correlation_id,
            actor_id=actor_id,
            actor_role="case_operator",
        )
        final_episode = case_orchestrator.fallback_episode(
            resumed_episode.episode_id,
            to_stage="feature_registry",
            transition_name="fallback_to_feature_review",
            reason="Assessment detects missing detail and legitimately falls back to feature review.",
            correlation_id=correlation_id,
            actor_id=actor_id,
            actor_role="case_supervisor",
        )

        router_service.resolve(
            RouterResolutionRequest(
                router_rule_id="tie_break_case_route",
                semantic_scope="shared_control_plane",
                state_model_name=final_episode.state_model_name,
                transition_name="promote_to_case_assessment",
                transition_class="forward_progression",
                source_stage="feature_registry",
                target_stage="case_orchestration",
                correlation_id=correlation_id,
                episode_id=final_episode.episode_id,
                actor_id=actor_id,
            )
        )
        router_service.resolve(
            RouterResolutionRequest(
                router_rule_id="unresolved_case_route",
                semantic_scope="shared_control_plane",
                state_model_name=final_episode.state_model_name,
                transition_name="promote_to_case_assessment",
                transition_class="forward_progression",
                source_stage="feature_registry",
                target_stage="case_orchestration",
                correlation_id=correlation_id,
                episode_id=final_episode.episode_id,
                actor_id=actor_id,
            )
        )
        router_service.resolve(
            RouterResolutionRequest(
                router_rule_id="fallback_resolution_case_route",
                semantic_scope="shared_control_plane",
                state_model_name=final_episode.state_model_name,
                transition_name="promote_to_case_assessment",
                transition_class="forward_progression",
                source_stage="feature_registry",
                target_stage="case_orchestration",
                correlation_id=correlation_id,
                episode_id=final_episode.episode_id,
                actor_id=actor_id,
            )
        )
        router_service.resolve(
            RouterResolutionRequest(
                router_rule_id="default_case_route",
                semantic_scope="shared_control_plane",
                state_model_name=final_episode.state_model_name,
                transition_name="router_probe",
                transition_class="fallback",
                source_stage="case_orchestration",
                target_stage="raw_ingestion",
                correlation_id=correlation_id,
                episode_id=final_episode.episode_id,
                actor_id=actor_id,
            )
        )
        optional_packet_decision = review_trigger_service.evaluate(
            ReviewTriggerRequest(
                semantic_scope="shared_control_plane",
                state_model_name=final_episode.state_model_name,
                transition_name="promote_to_case_assessment",
                transition_class="forward_progression",
                source_stage="feature_registry",
                target_stage="case_orchestration",
                actor_role="case_operator",
                authority_resolution_kind="direct",
                authority_review_required=False,
                router_rule_id="default_case_route",
                route_name="primary_case_path",
                routing_resolution_status="resolved",
                routing_conflict_class="precedence_required_conflict",
                routing_candidate_count=2,
                routing_review_required=False,
                decision_context={"impact_score": 0.55},
                correlation_id=correlation_id,
                episode_id=final_episode.episode_id,
                actor_id=actor_id,
            )
        )
        review_trigger_service.evaluate(
            ReviewTriggerRequest(
                semantic_scope="shared_control_plane",
                state_model_name=final_episode.state_model_name,
                transition_name="promote_to_case_assessment",
                transition_class="forward_progression",
                source_stage="feature_registry",
                target_stage="case_orchestration",
                actor_role="case_operator",
                authority_resolution_kind="direct",
                authority_review_required=False,
                router_rule_id="default_case_route",
                route_name="primary_case_path",
                routing_resolution_status="resolved",
                routing_conflict_class="precedence_required_conflict",
                routing_candidate_count=2,
                routing_review_required=False,
                decision_context={"impact_score": 0.20},
                correlation_id=correlation_id,
                episode_id=final_episode.episode_id,
                actor_id=actor_id,
            )
        )
        review_trigger_service.evaluate(
            ReviewTriggerRequest(
                semantic_scope="shared_control_plane",
                state_model_name=final_episode.state_model_name,
                transition_name="promote_to_case_assessment",
                transition_class="forward_progression",
                source_stage="feature_registry",
                target_stage="case_orchestration",
                actor_role="case_operator",
                authority_resolution_kind="direct",
                authority_review_required=False,
                router_rule_id="default_case_route",
                route_name="primary_case_path",
                routing_resolution_status="resolved",
                routing_conflict_class="precedence_required_conflict",
                routing_candidate_count=2,
                routing_review_required=False,
                decision_context={},
                correlation_id=correlation_id,
                episode_id=final_episode.episode_id,
                actor_id=actor_id,
            )
        )
        fallback_packet_decision = review_trigger_service.evaluate(
            ReviewTriggerRequest(
                semantic_scope="shared_control_plane",
                state_model_name=final_episode.state_model_name,
                transition_name="promote_to_case_assessment",
                transition_class="forward_progression",
                source_stage="feature_registry",
                target_stage="case_orchestration",
                actor_role="case_operator",
                authority_resolution_kind="direct",
                authority_review_required=False,
                router_rule_id="default_case_route",
                route_name="review_gate_path",
                routing_resolution_status="resolved",
                routing_conflict_class="precedence_required_conflict",
                routing_candidate_count=2,
                routing_review_required=True,
                decision_context={"impact_score": 0.60},
                correlation_id=correlation_id,
                episode_id=final_episode.episode_id,
                actor_id=actor_id,
            )
        )
        optional_packet = human_review_packet_builder.build(
            HumanReviewPacketBuildRequest(
                semantic_scope="shared_control_plane",
                case_type=final_episode.case_type,
                case_key=final_episode.case_key,
                state_model_name=final_episode.state_model_name,
                episode_id=final_episode.episode_id,
                transition_name="promote_to_case_assessment",
                transition_class="forward_progression",
                source_stage="feature_registry",
                target_stage="case_orchestration",
                actor_role="case_operator",
                authority_resolution_kind="direct",
                authority_review_required=False,
                router_rule_id="default_case_route",
                route_name="primary_case_path",
                routing_resolution_status="resolved",
                routing_review_required=False,
                review_decision=optional_packet_decision,
                packet_context={
                    "review_focus": "Assess whether optional review remains proportionate at the moderate impact band.",
                    "impact_score": 0.55,
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        human_review_packet_builder.build(
            HumanReviewPacketBuildRequest(
                semantic_scope="shared_control_plane",
                case_type=final_episode.case_type,
                case_key=final_episode.case_key,
                state_model_name=final_episode.state_model_name,
                episode_id=final_episode.episode_id,
                transition_name="promote_to_case_assessment",
                transition_class="forward_progression",
                source_stage="feature_registry",
                target_stage="case_orchestration",
                actor_role="case_operator",
                authority_resolution_kind="direct",
                authority_review_required=False,
                router_rule_id="default_case_route",
                route_name="primary_case_path",
                routing_resolution_status="resolved",
                routing_review_required=False,
                review_decision=optional_packet_decision,
                packet_context={},
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        fallback_packet = human_review_packet_builder.build(
            HumanReviewPacketBuildRequest(
                semantic_scope="shared_control_plane",
                case_type=final_episode.case_type,
                case_key=final_episode.case_key,
                state_model_name=final_episode.state_model_name,
                episode_id=final_episode.episode_id,
                transition_name="promote_to_case_assessment",
                transition_class="forward_progression",
                source_stage="feature_registry",
                target_stage="case_orchestration",
                actor_role="case_operator",
                authority_resolution_kind="direct",
                authority_review_required=False,
                router_rule_id="default_case_route",
                route_name="review_gate_path",
                routing_resolution_status="resolved",
                routing_review_required=True,
                review_decision=fallback_packet_decision,
                packet_context={
                    "review_focus": "Send the review-gate case into the manual triage placeholder with explicit fallback lineage.",
                    "impact_score": 0.60,
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        clarification_resolution = review_resolution_service.resolve(
            ReviewResolutionRequest(
                packet=optional_packet,
                resolution_class_id="returned_for_clarification",
                reviewer_role="case_operator",
                resolution_context={
                    "review_summary": "The optional review packet remains materially ambiguous.",
                    "resolution_rationale": "Further clarification is required before a valid settlement may stand.",
                    "clarification_reference": "clarification-placeholder-001",
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        review_resolution_service.resolve(
            ReviewResolutionRequest(
                packet=optional_packet,
                resolution_class_id="returned_for_clarification",
                reviewer_role="case_operator",
                resolution_context={
                    "review_summary": "The optional review packet remains materially ambiguous.",
                    "resolution_rationale": "Further clarification is required before a valid settlement may stand.",
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        fallback_resolution = review_resolution_service.resolve(
            ReviewResolutionRequest(
                packet=fallback_packet,
                resolution_class_id="manual_fallback_resolution",
                reviewer_role="case_operator",
                resolution_context={
                    "review_summary": "Fallback packet is preserved for later manual triage.",
                    "resolution_rationale": "The fallback path remains explicit until a later governed reviewer resolves the case.",
                    "fallback_reference": "manual-triage-placeholder-001",
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        clarification_recommendation = recommendation_service.recommend(
            RecommendationRequest(
                review_resolution=clarification_resolution,
                recommendation_class_id="recommend_gather_more_information",
                recommender_role="case_operator",
                recommendation_context={
                    "recommendation_summary": "Gather more information before stronger downstream action is considered.",
                    "action_path_reference": "action-path:bootstrap-clarification-001",
                    "scope_reference": "scope:store:001",
                    "confidence_summary": "moderate_confidence",
                    "constraint_summary": "scope_and_evidence_must_be_clarified",
                    "uncertainty_summary": "important_customer_scope_gap_remains",
                    "failure_state_context": "no_failure_state_detected",
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        recommendation_service.recommend(
            RecommendationRequest(
                review_resolution=clarification_resolution,
                recommendation_class_id="recommend_gather_more_information",
                recommender_role="case_operator",
                recommendation_context={
                    "recommendation_summary": "Gather more information before stronger downstream action is considered."
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        fallback_recommendation = recommendation_service.recommend(
            RecommendationRequest(
                review_resolution=fallback_resolution,
                recommendation_class_id="abstain_from_strong_recommendation",
                recommender_role="case_operator",
                recommendation_context={
                    "recommendation_summary": "Preserve abstention until stronger downstream evidence exists.",
                    "action_path_reference": "action-path:bootstrap-manual-triage-001",
                    "scope_reference": "scope:store:001",
                    "confidence_summary": "low_confidence",
                    "constraint_summary": "manual_triage_required_before_stronger_advice",
                    "uncertainty_summary": "evidence_and_scope_remain_open",
                    "failure_state_context": "fallback_manual_triage_active",
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        clarification_policy_output = policy_output_service.generate(
            PolicyOutputRequest(
                recommendation=clarification_recommendation,
                policy_output_class_id="policy_shaped_information_requirement",
                policy_author_role="case_operator",
                policy_output_context={
                    "policy_summary": "Preserve clarification-first policy posture until ambiguity is resolved.",
                    "policy_output_reference": "policy-output:bootstrap-clarification-001",
                    "policy_rationale": "Clarification remains required before stronger policy posture is legitimate.",
                    "action_boundary_summary": "Policy-shaped information requirement only; further governance remains required before action.",
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        policy_output_service.generate(
            PolicyOutputRequest(
                recommendation=clarification_recommendation,
                policy_output_class_id="policy_shaped_information_requirement",
                policy_author_role="case_operator",
                policy_output_context={
                    "policy_summary": "Preserve clarification-first policy posture until ambiguity is resolved."
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        fallback_policy_output = policy_output_service.generate(
            PolicyOutputRequest(
                recommendation=fallback_recommendation,
                policy_output_class_id="policy_shaped_suppression",
                policy_author_role="case_operator",
                policy_output_context={
                    "policy_summary": "Preserve fallback suppression posture until a later governed reviewer revisits the case.",
                    "policy_output_reference": "policy-output:bootstrap-fallback-001",
                    "policy_rationale": "Fallback handling remains explicit until stronger downstream evidence or authority changes the bounded policy posture.",
                    "action_boundary_summary": "Policy-shaped suppression only; no downstream instruction is authorized by this output.",
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        clarification_portfolio_output = portfolio_output_service.generate(
            PortfolioOutputRequest(
                policy_output=clarification_policy_output,
                portfolio_output_class_id="portfolio_ranked_preference",
                portfolio_author_role="case_operator",
                portfolio_output_context={
                    "portfolio_summary": "Preserve ranked clarification preference for downstream portfolio ordering.",
                    "portfolio_output_reference": "portfolio-output:bootstrap-clarification-001",
                    "portfolio_rationale": "Policy output lineage supports explicit ranked clarification priority before stronger downstream handling.",
                    "action_boundary_summary": "Allocative only; downstream commitment and instruction remain separately governed.",
                    "preference_rank_reference": "clarification-rank:bootstrap-store-001:1",
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        portfolio_output_service.generate(
            PortfolioOutputRequest(
                policy_output=clarification_policy_output,
                portfolio_output_class_id="portfolio_ranked_preference",
                portfolio_author_role="case_operator",
                portfolio_output_context={
                    "portfolio_summary": "Preserve ranked clarification preference for downstream portfolio ordering."
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        fallback_portfolio_output = portfolio_output_service.generate(
            PortfolioOutputRequest(
                policy_output=fallback_policy_output,
                portfolio_output_class_id="portfolio_suppression_hold",
                portfolio_author_role="case_operator",
                portfolio_output_context={
                    "portfolio_summary": "Preserve fallback suppression hold posture until a later governed reviewer revisits the case.",
                    "portfolio_output_reference": "portfolio-output:bootstrap-fallback-001",
                    "portfolio_rationale": "Fallback policy output remains explicit until stronger downstream evidence or authority changes the bounded portfolio posture.",
                    "action_boundary_summary": "Policy-shaped suppression only; no downstream instruction is authorized by this output.",
                    "suppression_reference": "suppression:bootstrap-manual-triage-001",
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        clarification_action_instruction = action_instruction_service.generate(
            ActionInstructionRequest(
                portfolio_output=clarification_portfolio_output,
                action_instruction_class_id="prerequisite_bounded_instruction",
                instruction_author_role="case_operator",
                action_instruction_context={
                    "instruction_summary": "Preserve a governed clarification instruction posture until the missing prerequisite is satisfied.",
                    "action_instruction_reference": "action-instruction:bootstrap-clarification-001",
                    "upstream_commitment_reference": "commitment-placeholder:bootstrap-clarification-001",
                    "instruction_authority_reference": "instruction-authority:case-operator",
                    "executable_scope_reference": "scope:bootstrap-store-001:clarification-loop",
                    "intended_action_reference": "intended-action:bootstrap-clarification-request-001",
                    "action_delivery_channel": "manual_clarification_handoff",
                    "blocking_condition_reference": "clarification-gap:bootstrap-store-001",
                    "clarification_reference": "clarification-placeholder-001",
                    "blocking_condition_kind": "prerequisite",
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        action_instruction_service.generate(
            ActionInstructionRequest(
                portfolio_output=clarification_portfolio_output,
                action_instruction_class_id="prerequisite_bounded_instruction",
                instruction_author_role="case_operator",
                action_instruction_context={
                    "instruction_summary": "Preserve a governed clarification instruction posture until the missing prerequisite is satisfied."
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        fallback_action_instruction = action_instruction_service.generate(
            ActionInstructionRequest(
                portfolio_output=fallback_portfolio_output,
                action_instruction_class_id="suppression_hold_instruction",
                instruction_author_role="case_operator",
                action_instruction_context={
                    "instruction_summary": "Preserve a governed suppression-hold instruction posture until a later governed reviewer revisits the case.",
                    "action_instruction_reference": "action-instruction:bootstrap-fallback-001",
                    "upstream_commitment_reference": "commitment-placeholder:bootstrap-fallback-001",
                    "instruction_authority_reference": "instruction-authority:case-operator",
                    "executable_scope_reference": "scope:bootstrap-store-001:manual-triage-hold",
                    "intended_action_reference": "intended-action:bootstrap-manual-hold-001",
                    "action_delivery_channel": "manual_triage_handoff",
                    "fallback_reference": "manual-triage-placeholder-001",
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        clarification_execution_request = execution_request_service.generate(
            ExecutionRequestRequest(
                action_instruction=clarification_action_instruction,
                execution_request_class_id="prerequisite_dispatch_request",
                execution_request_author_role="case_operator",
                execution_request_context={
                    "execution_request_summary": "Preserve a governed clarification dispatch request until the prerequisite gap is resolved.",
                    "execution_request_reference": "execution-request:bootstrap-clarification-001",
                    "execution_target_reference": "execution-target:bootstrap-clarification-request-001",
                    "execution_scope_reference": "scope:bootstrap-store-001:clarification-loop",
                    "execution_timing_reference": "timing:bootstrap-clarification-window",
                    "execution_request_channel": "manual_clarification_handoff",
                    "execution_priority_reference": "dispatch-priority:bootstrap-clarification",
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        execution_request_service.generate(
            ExecutionRequestRequest(
                action_instruction=clarification_action_instruction,
                execution_request_class_id="prerequisite_dispatch_request",
                execution_request_author_role="case_operator",
                execution_request_context={
                    "execution_request_summary": "This request should block because the bounded execution-request context is incomplete."
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        fallback_execution_request = execution_request_service.generate(
            ExecutionRequestRequest(
                action_instruction=fallback_action_instruction,
                execution_request_class_id="hold_dispatch_request",
                execution_request_author_role="case_operator",
                execution_request_context={
                    "execution_request_summary": "Preserve a governed hold-only execution request until a later reviewer revisits the case.",
                    "execution_request_reference": "execution-request:bootstrap-fallback-001",
                    "execution_target_reference": "execution-target:bootstrap-manual-triage-001",
                    "execution_scope_reference": "scope:bootstrap-store-001:manual-triage-hold",
                    "execution_timing_reference": "timing:bootstrap-manual-triage-window",
                    "execution_request_channel": "manual_triage_handoff",
                    "execution_priority_reference": "dispatch-priority:bootstrap-hold",
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        clarification_execution_dispatch = execution_dispatch_service.generate(
            ExecutionDispatchBoundaryRequest(
                execution_request=clarification_execution_request,
                execution_dispatch_class_id="conditioned_dispatch_boundary",
                execution_dispatch_author_role="case_operator",
                execution_dispatch_context={
                    "dispatch_summary": "Preserve a governed clarification dispatch boundary until the prerequisite gap is resolved.",
                    "dispatch_reference": "execution-dispatch:bootstrap-clarification-001",
                    "dispatch_channel": "manual_clarification_boundary_handoff",
                    "dispatch_payload_reference": "dispatch-boundary-payload:bootstrap-clarification-001",
                    "dispatch_window_reference": "dispatch-window:bootstrap-clarification-loop",
                    "dispatch_priority_reference": "dispatch-priority:bootstrap-clarification",
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        execution_dispatch_service.generate(
            ExecutionDispatchBoundaryRequest(
                execution_request=clarification_execution_request,
                execution_dispatch_class_id="conditioned_dispatch_boundary",
                execution_dispatch_author_role="case_operator",
                execution_dispatch_context={
                    "dispatch_summary": "This dispatch boundary should block because the bounded dispatch context is incomplete."
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        fallback_execution_dispatch = execution_dispatch_service.generate(
            ExecutionDispatchBoundaryRequest(
                execution_request=fallback_execution_request,
                execution_dispatch_class_id="hold_dispatch_boundary",
                execution_dispatch_author_role="case_operator",
                execution_dispatch_context={
                    "dispatch_summary": "Preserve a governed hold-only execution-dispatch boundary until a later reviewer revisits the case.",
                    "dispatch_reference": "execution-dispatch:bootstrap-hold-001",
                    "dispatch_channel": "manual_hold_boundary_handoff",
                    "dispatch_hold_reference": "dispatch-hold:bootstrap-manual-triage-001",
                    "dispatch_window_reference": "dispatch-window:bootstrap-manual-triage-window",
                    "dispatch_priority_reference": "dispatch-priority:bootstrap-hold",
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        clarification_execution_outcome = execution_outcome_service.generate(
            ExecutionOutcomeCaptureRequest(
                execution_dispatch=clarification_execution_dispatch,
                execution_outcome_class_id="negative_realized_outcome",
                execution_outcome_author_role="case_operator",
                execution_outcome_context={
                    "observation_basis": "clarification_outcome_observation",
                    "observation_horizon_reference": "horizon:bootstrap-clarification-closure",
                    "comparison_basis": "dispatch_target_vs_observed_execution",
                    "feedback_maturity_posture": "stabilized_observation",
                    "feedback_reuse_boundary": "governed_post_mortem_and_memory_only",
                    "tenant_scope_reference": "tenant:bootstrap-store-001",
                    "executed_action_reference": "execution-target:bootstrap-clarification-resolution-001",
                    "realized_outcome_reference": "outcome:bootstrap-clarification-loss-001",
                    "outcome_summary": "The conditioned dispatch resolved through a different realized path and preserved the negative outcome explicitly rather than silently neutralizing it.",
                    "decision_scope_reference": "scope:bootstrap-store-001:clarification-loop",
                    "execution_condition_references": [
                        "condition:bootstrap-clarification-lag"
                    ]
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        post_mortem_service.generate(
            PostMortemJudgmentRequest(
                execution_outcome=clarification_execution_outcome,
                post_mortem_judgment_class_id="correct_recommendation_weak_execution",
                post_mortem_author_role="case_operator",
                post_mortem_context=blocked_post_mortem_context,
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        accepted_policy_learning_resolution = review_resolution_service.resolve(
            ReviewResolutionRequest(
                packet=optional_packet,
                resolution_class_id="resolved_with_action",
                reviewer_role="case_operator",
                resolution_context={
                    "review_summary": (
                        "A governed reviewer confirmed that accountable downstream action preparation is warranted."
                    ),
                    "resolution_rationale": (
                        "The case crossed the required review threshold and preserved enough context to fix an action-routing disposition."
                    ),
                    "recommendation_reference": (
                        "bootstrap-recommendation-placeholder-primary-probe-001"
                    ),
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        accepted_policy_learning_recommendation = recommendation_service.recommend(
            RecommendationRequest(
                review_resolution=accepted_policy_learning_resolution,
                recommendation_class_id="recommend_act_now",
                recommender_role="case_operator",
                recommendation_context={
                    "recommendation_summary": (
                        "Act now while preserving the advisory-only recommendation boundary."
                    ),
                    "action_path_reference": "action-path:bootstrap-direct-action-probe-001",
                    "scope_reference": "scope:store:001",
                    "confidence_summary": "high_confidence",
                    "constraint_summary": "inventory_and_margin_checked",
                    "uncertainty_summary": "remaining_regime_uncertainty_is_bounded",
                    "failure_state_context": "no_active_failure_state_detected",
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        accepted_policy_learning_policy_output = policy_output_service.generate(
            PolicyOutputRequest(
                recommendation=accepted_policy_learning_recommendation,
                policy_output_class_id="policy_shaped_allowance",
                policy_author_role="case_operator",
                policy_output_context={
                    "policy_summary": (
                        "Preserve bounded allowance for downstream action preparation while keeping commitment and instruction separate."
                    ),
                    "policy_output_reference": "policy-output:bootstrap-allowance-probe-001",
                    "policy_rationale": (
                        "Review and recommendation lineage justify a bounded policy allowance for downstream preparation."
                    ),
                    "action_boundary_summary": (
                        "Policy-shaped allowance only; downstream commitment and instruction remain separately governed."
                    ),
                    "allowance_reference": (
                        "allowance:bootstrap-store-001:price-adjustment-window-probe"
                    ),
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        accepted_policy_learning_portfolio_output = portfolio_output_service.generate(
            PortfolioOutputRequest(
                policy_output=accepted_policy_learning_policy_output,
                portfolio_output_class_id="portfolio_bounded_allocation",
                portfolio_author_role="case_operator",
                portfolio_output_context={
                    "portfolio_summary": (
                        "Preserve bounded allocation posture for downstream portfolio planning while keeping commitment and instruction separate."
                    ),
                    "portfolio_output_reference": (
                        "portfolio-output:bootstrap-allocation-probe-001"
                    ),
                    "portfolio_rationale": (
                        "Policy allowance lineage justifies bounded allocation posture for downstream planning."
                    ),
                    "action_boundary_summary": (
                        "Allocative only; downstream commitment and instruction remain separately governed."
                    ),
                    "allocation_reference": (
                        "allocation:bootstrap-store-001:price-adjustment-window-probe"
                    ),
                    "allocation_weight_reference": (
                        "allocation-weight:bootstrap-store-001:0.71"
                    ),
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        accepted_policy_learning_action_instruction = (
            action_instruction_service.generate(
                ActionInstructionRequest(
                    portfolio_output=accepted_policy_learning_portfolio_output,
                    action_instruction_class_id="direct_action_instruction",
                    instruction_author_role="case_operator",
                    action_instruction_context={
                        "instruction_summary": (
                            "Issue a governed downstream preparation instruction while keeping execution separate from instruction legitimacy."
                        ),
                        "action_instruction_reference": (
                            "action-instruction:bootstrap-direct-probe-001"
                        ),
                        "upstream_commitment_reference": (
                            "commitment-placeholder:bootstrap-direct-probe-001"
                        ),
                        "instruction_authority_reference": (
                            "instruction-authority:case-operator"
                        ),
                        "executable_scope_reference": (
                            "scope:bootstrap-store-001:price-adjustment-window"
                        ),
                        "intended_action_reference": (
                            "intended-action:bootstrap-price-adjustment-probe-001"
                        ),
                        "action_delivery_channel": "downstream_preparation_handoff",
                    },
                    correlation_id=correlation_id,
                    actor_id=actor_id,
                )
            )
        )
        accepted_policy_learning_execution_request = (
            execution_request_service.generate(
                ExecutionRequestRequest(
                    action_instruction=accepted_policy_learning_action_instruction,
                    execution_request_class_id="direct_dispatch_request",
                    execution_request_author_role="case_operator",
                    execution_request_context={
                        "execution_request_summary": (
                            "Prepare a governed dispatch request while keeping execution separate from request legitimacy."
                        ),
                        "execution_request_reference": (
                            "execution-request:bootstrap-direct-probe-001"
                        ),
                        "execution_target_reference": (
                            "execution-target:bootstrap-price-adjustment-probe-001"
                        ),
                        "execution_scope_reference": (
                            "scope:bootstrap-store-001:price-adjustment-window"
                        ),
                        "execution_timing_reference": (
                            "timing:bootstrap-price-adjustment-window"
                        ),
                        "execution_request_channel": "governed_dispatch_handoff",
                        "execution_priority_reference": "dispatch-priority:bootstrap-high",
                    },
                    correlation_id=correlation_id,
                    actor_id=actor_id,
                )
            )
        )
        accepted_policy_learning_execution_dispatch = (
            execution_dispatch_service.generate(
                ExecutionDispatchBoundaryRequest(
                    execution_request=accepted_policy_learning_execution_request,
                    execution_dispatch_class_id="direct_dispatch_boundary",
                    execution_dispatch_author_role="case_operator",
                    execution_dispatch_context={
                        "dispatch_summary": (
                            "Materialize a governed execution-dispatch boundary while keeping broker placement and actual execution separate."
                        ),
                        "dispatch_reference": (
                            "execution-dispatch:bootstrap-direct-probe-001"
                        ),
                        "dispatch_channel": "governed_dispatch_boundary_handoff",
                        "dispatch_payload_reference": (
                            "dispatch-boundary-payload:bootstrap-direct-probe-001"
                        ),
                        "dispatch_window_reference": (
                            "dispatch-window:bootstrap-price-adjustment-window"
                        ),
                        "dispatch_priority_reference": "dispatch-priority:bootstrap-high",
                    },
                    correlation_id=correlation_id,
                    actor_id=actor_id,
                )
            )
        )
        accepted_policy_learning_execution_outcome = (
            execution_outcome_service.generate(
                ExecutionOutcomeCaptureRequest(
                    execution_dispatch=accepted_policy_learning_execution_dispatch,
                    execution_outcome_class_id="favorable_realized_outcome",
                    execution_outcome_author_role="case_operator",
                    execution_outcome_context={
                        "observation_basis": "post_dispatch_observation",
                        "observation_horizon_reference": "horizon:bootstrap-t-plus-7d",
                        "comparison_basis": "dispatch_target_vs_observed_execution",
                        "feedback_maturity_posture": "stabilized_observation",
                        "feedback_reuse_boundary": "governed_post_mortem_and_memory_only",
                        "tenant_scope_reference": "tenant:bootstrap-store-001",
                        "executed_action_reference": (
                            "execution-target:bootstrap-price-adjustment-probe-001"
                        ),
                        "realized_outcome_reference": (
                            "outcome:bootstrap-revenue-improvement-probe-001"
                        ),
                        "outcome_summary": (
                            "The governed dispatch intent was realized within the expected observation horizon."
                        ),
                        "decision_scope_reference": (
                            "scope:bootstrap-store-001:price-adjustment-window"
                        ),
                        "reporting_scope_reference": (
                            "reporting:bootstrap-store-001:weekly"
                        ),
                        "execution_condition_references": [
                            "condition:bootstrap-inventory-available",
                            "condition:bootstrap-margin-threshold-respected",
                        ],
                    },
                    correlation_id=correlation_id,
                    actor_id=actor_id,
                )
            )
        )
        execution_outcome_service.generate(
            ExecutionOutcomeCaptureRequest(
                execution_dispatch=clarification_execution_dispatch,
                execution_outcome_class_id="negative_realized_outcome",
                execution_outcome_author_role="case_operator",
                execution_outcome_context={
                    "observation_basis": "clarification_outcome_observation",
                    "observation_horizon_reference": "horizon:bootstrap-clarification-closure"
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        fallback_execution_outcome = execution_outcome_service.generate(
            ExecutionOutcomeCaptureRequest(
                execution_dispatch=fallback_execution_dispatch,
                execution_outcome_class_id="deferred_realized_outcome",
                execution_outcome_author_role="case_operator",
                execution_outcome_context={
                    "observation_basis": "hold_boundary_observation",
                    "observation_horizon_reference": "horizon:bootstrap-pending-review",
                    "comparison_basis": "dispatch_hold_vs_later_observation",
                    "feedback_maturity_posture": "preliminary_observation",
                    "feedback_reuse_boundary": "local_operational_reuse_only",
                    "tenant_scope_reference": "tenant:bootstrap-store-001",
                    "non_execution_reference": "non-execution:bootstrap-manual-triage-hold",
                    "realized_outcome_reference": "outcome:bootstrap-deferred-observation-001",
                    "outcome_summary": "The hold-only dispatch remains explicitly deferred rather than silently favorable or neutral.",
                    "decision_scope_reference": "scope:bootstrap-store-001:manual-triage-hold"
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        fallback_policy_learning_post_mortem = post_mortem_service.generate(
            PostMortemJudgmentRequest(
                execution_outcome=fallback_execution_outcome,
                post_mortem_judgment_class_id=(
                    "insufficient_evidence_for_confident_judgment"
                ),
                post_mortem_author_role="case_operator",
                post_mortem_context=fallback_post_mortem_context,
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        accepted_policy_learning_post_mortem = post_mortem_service.generate(
            PostMortemJudgmentRequest(
                execution_outcome=accepted_policy_learning_execution_outcome,
                post_mortem_judgment_class_id=(
                    "correct_recommendation_correct_execution"
                ),
                post_mortem_author_role="case_operator",
                post_mortem_context=ready_post_mortem_context,
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        restricted_policy_learning_post_mortem = post_mortem_service.generate(
            PostMortemJudgmentRequest(
                execution_outcome=clarification_execution_outcome,
                post_mortem_judgment_class_id="correct_recommendation_weak_execution",
                post_mortem_author_role="case_operator",
                post_mortem_context=ready_post_mortem_context,
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        _blocked_policy_learning_evidence = policy_learning_service.generate(
            PolicyLearningEvidenceAdmissionRequest(
                post_mortem_judgment=fallback_policy_learning_post_mortem,
                policy_learning_evidence_class_id="policy_learning_review_candidate",
                policy_learning_evidence_author_role="case_operator",
                policy_learning_evidence_admission_context=(
                    blocked_policy_learning_admission_context
                ),
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        admitted_policy_learning_evidence = policy_learning_service.generate(
            PolicyLearningEvidenceAdmissionRequest(
                post_mortem_judgment=accepted_policy_learning_post_mortem,
                policy_learning_evidence_class_id="policy_learning_review_candidate",
                policy_learning_evidence_author_role="case_operator",
                policy_learning_evidence_admission_context=(
                    ready_policy_learning_admission_context
                ),
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        restricted_policy_learning_evidence = policy_learning_service.generate(
            PolicyLearningEvidenceAdmissionRequest(
                post_mortem_judgment=restricted_policy_learning_post_mortem,
                policy_learning_evidence_class_id=(
                    "restricted_policy_learning_review_candidate"
                ),
                policy_learning_evidence_author_role="case_operator",
                policy_learning_evidence_admission_context=(
                    ready_policy_learning_admission_context
                ),
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        deferred_policy_learning_evidence = policy_learning_service.generate(
            PolicyLearningEvidenceAdmissionRequest(
                post_mortem_judgment=fallback_policy_learning_post_mortem,
                policy_learning_evidence_class_id=(
                    "deferred_policy_learning_review_candidate"
                ),
                policy_learning_evidence_author_role="case_operator",
                policy_learning_evidence_admission_context=(
                    fallback_policy_learning_admission_context
                ),
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        approved_policy_learning_update_threshold = (
            policy_learning_update_threshold_service.generate(
                PolicyLearningUpdateThresholdRequest(
                    policy_learning_evidence_admission=admitted_policy_learning_evidence,
                    policy_learning_update_threshold_class_id="policy_update_candidate",
                    policy_learning_update_threshold_author_role="case_operator",
                    policy_learning_update_threshold_context=(
                        accepted_policy_learning_update_threshold_context
                    ),
                    correlation_id=correlation_id,
                    actor_id=actor_id,
                )
            )
        )
        policy_learning_update_threshold_service.generate(
            PolicyLearningUpdateThresholdRequest(
                policy_learning_evidence_admission=admitted_policy_learning_evidence,
                policy_learning_update_threshold_class_id="policy_update_candidate",
                policy_learning_update_threshold_author_role="case_operator",
                policy_learning_update_threshold_context=(
                    below_threshold_policy_learning_update_threshold_context
                ),
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        restricted_policy_learning_update_threshold = (
            policy_learning_update_threshold_service.generate(
                PolicyLearningUpdateThresholdRequest(
                    policy_learning_evidence_admission=restricted_policy_learning_evidence,
                    policy_learning_update_threshold_class_id=(
                        "narrowed_policy_update_candidate"
                    ),
                    policy_learning_update_threshold_author_role="case_operator",
                    policy_learning_update_threshold_context=(
                        narrowed_policy_learning_update_threshold_context
                    ),
                    correlation_id=correlation_id,
                    actor_id=actor_id,
                )
            )
        )
        policy_learning_update_threshold_service.generate(
            PolicyLearningUpdateThresholdRequest(
                policy_learning_evidence_admission=restricted_policy_learning_evidence,
                policy_learning_update_threshold_class_id=(
                    "narrowed_policy_update_candidate"
                ),
                policy_learning_update_threshold_author_role="case_operator",
                policy_learning_update_threshold_context=(
                    narrowed_policy_learning_update_threshold_context
                ),
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        deferred_policy_learning_update_threshold = (
            policy_learning_update_threshold_service.generate(
                PolicyLearningUpdateThresholdRequest(
                    policy_learning_evidence_admission=deferred_policy_learning_evidence,
                    policy_learning_update_threshold_class_id=(
                        "deferred_policy_update_candidate"
                    ),
                    policy_learning_update_threshold_author_role="case_operator",
                    policy_learning_update_threshold_context=(
                        deferred_policy_learning_update_threshold_context
                    ),
                    correlation_id=correlation_id,
                    actor_id=actor_id,
                )
            )
        )
        policy_learning_update_threshold_service.generate(
            PolicyLearningUpdateThresholdRequest(
                policy_learning_evidence_admission=deferred_policy_learning_evidence,
                policy_learning_update_threshold_class_id=(
                    "deferred_policy_update_candidate"
                ),
                policy_learning_update_threshold_author_role="case_operator",
                policy_learning_update_threshold_context=(
                    deferred_policy_learning_update_threshold_context
                ),
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        policy_learning_update_threshold_service.generate(
            PolicyLearningUpdateThresholdRequest(
                policy_learning_evidence_admission=admitted_policy_learning_evidence,
                policy_learning_update_threshold_class_id="policy_update_candidate",
                policy_learning_update_threshold_author_role="case_operator",
                policy_learning_update_threshold_context={},
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        approved_policy_learning_update_approval = (
            policy_learning_update_approval_service.generate(
            PolicyLearningUpdateApprovalRequest(
                policy_learning_update_threshold=approved_policy_learning_update_threshold,
                policy_learning_update_approval_class_id=(
                    "policy_update_preparation_candidate"
                ),
                policy_learning_update_approval_author_role="case_operator",
                policy_learning_update_approval_context=(
                    approved_policy_learning_update_approval_context
                ),
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        )
        restricted_policy_learning_update_approval = (
            policy_learning_update_approval_service.generate(
            PolicyLearningUpdateApprovalRequest(
                policy_learning_update_threshold=(
                    restricted_policy_learning_update_threshold
                ),
                policy_learning_update_approval_class_id=(
                    "restricted_policy_update_preparation_candidate"
                ),
                policy_learning_update_approval_author_role="case_operator",
                policy_learning_update_approval_context=(
                    restricted_policy_learning_update_approval_context
                ),
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        )
        policy_learning_update_approval_service.generate(
            PolicyLearningUpdateApprovalRequest(
                policy_learning_update_threshold=(
                    deferred_policy_learning_update_threshold
                ),
                policy_learning_update_approval_class_id=(
                    "deferred_policy_update_preparation_candidate"
                ),
                policy_learning_update_approval_author_role="case_operator",
                policy_learning_update_approval_context=(
                    deferred_policy_learning_update_approval_context
                ),
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        prepared_policy_learning_update_preparation = (
            policy_learning_update_preparation_service.generate(
            PolicyLearningUpdatePreparationRequest(
                policy_learning_update_approval=approved_policy_learning_update_approval,
                policy_learning_update_preparation_class_id=(
                    "policy_mutation_planning_candidate"
                ),
                policy_learning_update_preparation_author_role="case_operator",
                policy_learning_update_preparation_context=(
                    prepared_policy_learning_update_preparation_context
                ),
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        )
        restricted_policy_learning_update_preparation = (
            policy_learning_update_preparation_service.generate(
            PolicyLearningUpdatePreparationRequest(
                policy_learning_update_approval=(
                    restricted_policy_learning_update_approval
                ),
                policy_learning_update_preparation_class_id=(
                    "restricted_policy_mutation_planning_candidate"
                ),
                policy_learning_update_preparation_author_role="case_operator",
                policy_learning_update_preparation_context=(
                    restricted_policy_learning_update_preparation_context
                ),
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        )
        policy_learning_update_preparation_service.generate(
            PolicyLearningUpdatePreparationRequest(
                policy_learning_update_approval=approved_policy_learning_update_approval,
                policy_learning_update_preparation_class_id=(
                    "deferred_policy_mutation_planning_candidate"
                ),
                policy_learning_update_preparation_author_role="case_operator",
                policy_learning_update_preparation_context=(
                    deferred_policy_learning_update_preparation_context
                ),
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        policy_learning_update_preparation_service.generate(
            PolicyLearningUpdatePreparationRequest(
                policy_learning_update_approval=approved_policy_learning_update_approval,
                policy_learning_update_preparation_class_id=(
                    "policy_mutation_planning_candidate"
                ),
                policy_learning_update_preparation_author_role="case_operator",
                policy_learning_update_preparation_context={
                    "preparation_package_reference": (
                        "preparation-package:bootstrap-store-001:price-band"
                    )
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        policy_learning_update_preparation_service.generate(
            PolicyLearningUpdatePreparationRequest(
                policy_learning_update_approval=approved_policy_learning_update_approval,
                policy_learning_update_preparation_class_id=(
                    "policy_mutation_planning_candidate"
                ),
                policy_learning_update_preparation_author_role="case_operator",
                policy_learning_update_preparation_context=(
                    rejected_policy_learning_update_preparation_context
                ),
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        policy_learning_update_preparation_service.generate(
            PolicyLearningUpdatePreparationRequest(
                policy_learning_update_approval=approved_policy_learning_update_approval,
                policy_learning_update_preparation_class_id=(
                    "policy_mutation_planning_candidate"
                ),
                policy_learning_update_preparation_author_role="case_operator",
                policy_learning_update_preparation_context={
                    **prepared_policy_learning_update_preparation_context,
                    "policy_mutation_payload": "mutate-policy:bootstrap-price-floor",
                    "model_deployment_reference": "deploy:model:bootstrap-001",
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        prepared_policy_learning_update_mutation_planning = (
            policy_learning_update_mutation_planning_service.generate(
            PolicyLearningUpdateMutationPlanningRequest(
                policy_learning_update_preparation=(
                    prepared_policy_learning_update_preparation
                ),
                policy_learning_update_mutation_planning_class_id=(
                    "policy_mutation_plan_candidate"
                ),
                policy_learning_update_mutation_planning_author_role="case_operator",
                policy_learning_update_mutation_planning_context=(
                    prepared_policy_learning_update_mutation_planning_context
                ),
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        )
        restricted_policy_learning_update_mutation_planning = (
            policy_learning_update_mutation_planning_service.generate(
            PolicyLearningUpdateMutationPlanningRequest(
                policy_learning_update_preparation=(
                    restricted_policy_learning_update_preparation
                ),
                policy_learning_update_mutation_planning_class_id=(
                    "restricted_policy_mutation_plan_candidate"
                ),
                policy_learning_update_mutation_planning_author_role="case_operator",
                policy_learning_update_mutation_planning_context=(
                    restricted_policy_learning_update_mutation_planning_context
                ),
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        )
        policy_learning_update_mutation_planning_service.generate(
            PolicyLearningUpdateMutationPlanningRequest(
                policy_learning_update_preparation=(
                    prepared_policy_learning_update_preparation
                ),
                policy_learning_update_mutation_planning_class_id=(
                    "deferred_policy_mutation_plan_candidate"
                ),
                policy_learning_update_mutation_planning_author_role="case_operator",
                policy_learning_update_mutation_planning_context=(
                    deferred_policy_learning_update_mutation_planning_context
                ),
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        direct_ready_policy_learning_update_mutation_execution = (
            policy_learning_update_mutation_execution_service.generate(
            PolicyLearningUpdateMutationExecutionRequest(
                policy_learning_update_mutation_planning=(
                    prepared_policy_learning_update_mutation_planning
                ),
                policy_learning_update_mutation_execution_class_id=(
                    "policy_mutation_execution_candidate"
                ),
                policy_learning_update_mutation_execution_author_role="case_operator",
                policy_learning_update_mutation_execution_context=(
                    executed_policy_learning_update_mutation_execution_context
                ),
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        )
        direct_restricted_policy_learning_update_mutation_execution = (
            policy_learning_update_mutation_execution_service.generate(
            PolicyLearningUpdateMutationExecutionRequest(
                policy_learning_update_mutation_planning=(
                    restricted_policy_learning_update_mutation_planning
                ),
                policy_learning_update_mutation_execution_class_id=(
                    "restricted_policy_mutation_execution_candidate"
                ),
                policy_learning_update_mutation_execution_author_role="case_operator",
                policy_learning_update_mutation_execution_context=(
                    restricted_policy_learning_update_mutation_execution_context
                ),
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        )
        policy_learning_update_mutation_execution_service.generate(
            PolicyLearningUpdateMutationExecutionRequest(
                policy_learning_update_mutation_planning=(
                    prepared_policy_learning_update_mutation_planning
                ),
                policy_learning_update_mutation_execution_class_id=(
                    "deferred_policy_mutation_execution_candidate"
                ),
                policy_learning_update_mutation_execution_author_role="case_operator",
                policy_learning_update_mutation_execution_context=(
                    deferred_policy_learning_update_mutation_execution_context
                ),
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        direct_ready_promotion_readiness = promotion_readiness_gate.generate(
            PromotionReadinessGateRequest(
                policy_learning_update_mutation_execution=(
                    direct_ready_policy_learning_update_mutation_execution
                ),
                promotion_readiness_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                promotion_readiness_author_role="case_operator",
                promotion_readiness_context=ready_promotion_readiness_context,
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        direct_conditional_promotion_readiness = promotion_readiness_gate.generate(
            PromotionReadinessGateRequest(
                policy_learning_update_mutation_execution=(
                    direct_restricted_policy_learning_update_mutation_execution
                ),
                promotion_readiness_class_id="local_scope_release_candidate",
                promotion_readiness_author_role="case_operator",
                promotion_readiness_context=local_scope_promotion_readiness_context,
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        promotion_readiness_gate.generate(
            PromotionReadinessGateRequest(
                policy_learning_update_mutation_execution=(
                    direct_ready_policy_learning_update_mutation_execution
                ),
                promotion_readiness_class_id=(
                    "deferred_promotion_readiness_candidate"
                ),
                promotion_readiness_author_role="case_operator",
                promotion_readiness_context=deferred_promotion_readiness_context,
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        promotion_readiness_gate.generate(
            PromotionReadinessGateRequest(
                policy_learning_update_mutation_execution=(
                    direct_ready_policy_learning_update_mutation_execution
                ),
                promotion_readiness_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                promotion_readiness_author_role="case_operator",
                promotion_readiness_context={
                    "promotion_candidate_reference": (
                        "promotion-candidate:bootstrap-store-001:price-band"
                    )
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        promotion_readiness_gate.generate(
            PromotionReadinessGateRequest(
                policy_learning_update_mutation_execution=(
                    direct_ready_policy_learning_update_mutation_execution
                ),
                promotion_readiness_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                promotion_readiness_author_role="case_operator",
                promotion_readiness_context=rejected_promotion_readiness_context,
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        promotion_readiness_gate.generate(
            PromotionReadinessGateRequest(
                policy_learning_update_mutation_execution=(
                    direct_ready_policy_learning_update_mutation_execution
                ),
                promotion_readiness_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                promotion_readiness_author_role="case_operator",
                promotion_readiness_context={
                    **ready_promotion_readiness_context,
                    "policy_rollout_reference": (
                        "policy-rollout:bootstrap-store-001:price-band"
                    ),
                    "rollback_trigger_reference": (
                        "rollback-trigger:bootstrap-store-001:price-band"
                    ),
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        direct_ready_rollout_scope = rollout_scope_controller.generate(
            RolloutScopeControllerRequest(
                promotion_readiness=direct_ready_promotion_readiness,
                rollout_scope_class_id="full_scope_production_promotion_candidate",
                rollout_scope_author_role="case_operator",
                rollout_scope_context=ready_rollout_scope_context,
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        direct_conditional_rollout_scope = rollout_scope_controller.generate(
            RolloutScopeControllerRequest(
                promotion_readiness=direct_conditional_promotion_readiness,
                rollout_scope_class_id="conditional_production_release",
                rollout_scope_author_role="case_operator",
                rollout_scope_context=conditional_rollout_scope_context,
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        rollout_scope_controller.generate(
            RolloutScopeControllerRequest(
                promotion_readiness=direct_ready_promotion_readiness,
                rollout_scope_class_id="deferred_release_state",
                rollout_scope_author_role="case_operator",
                rollout_scope_context=deferred_rollout_scope_context,
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        rollout_scope_controller.generate(
            RolloutScopeControllerRequest(
                promotion_readiness=direct_ready_promotion_readiness,
                rollout_scope_class_id="full_scope_production_promotion_candidate",
                rollout_scope_author_role="case_operator",
                rollout_scope_context={
                    "rollout_scope_boundary_reference": (
                        "rollout-scope:bootstrap-store-001:full"
                    )
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        direct_ready_rollback_trigger = rollback_trigger_guard.generate(
            RollbackTriggerGuardRequest(
                rollout_scope=direct_ready_rollout_scope,
                rollback_trigger_class_id="full_scope_production_promotion_candidate",
                rollback_trigger_author_role="case_operator",
                rollback_trigger_context=ready_rollback_trigger_context,
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        direct_conditional_rollback_trigger = rollback_trigger_guard.generate(
            RollbackTriggerGuardRequest(
                rollout_scope=direct_conditional_rollout_scope,
                rollback_trigger_class_id="conditional_production_release",
                rollback_trigger_author_role="case_operator",
                rollback_trigger_context=ready_rollback_trigger_context,
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        rollback_trigger_guard.generate(
            RollbackTriggerGuardRequest(
                rollout_scope=direct_ready_rollout_scope,
                rollback_trigger_class_id="deferred_release_state",
                rollback_trigger_author_role="case_operator",
                rollback_trigger_context=deferred_rollback_trigger_context,
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        rollback_trigger_guard.generate(
            RollbackTriggerGuardRequest(
                rollout_scope=direct_ready_rollout_scope,
                rollback_trigger_class_id="full_scope_production_promotion_candidate",
                rollback_trigger_author_role="case_operator",
                rollback_trigger_context={
                    "rollback_trigger_reference": (
                        "rollback-trigger:bootstrap-store-001:price-band"
                    )
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        direct_ready_release_watch_discipline = release_watch_discipline.generate(
            ReleaseWatchDisciplineRequest(
                rollback_trigger=direct_ready_rollback_trigger,
                release_watch_discipline_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_watch_discipline_author_role="case_operator",
                release_watch_discipline_context=ready_release_watch_discipline_context,
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        direct_conditional_release_watch_discipline = release_watch_discipline.generate(
            ReleaseWatchDisciplineRequest(
                rollback_trigger=direct_conditional_rollback_trigger,
                release_watch_discipline_class_id="conditional_production_release",
                release_watch_discipline_author_role="case_operator",
                release_watch_discipline_context=ready_release_watch_discipline_context,
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        release_watch_discipline.generate(
            ReleaseWatchDisciplineRequest(
                rollback_trigger=direct_ready_rollback_trigger,
                release_watch_discipline_class_id="deferred_release_state",
                release_watch_discipline_author_role="case_operator",
                release_watch_discipline_context=(
                    deferred_release_watch_discipline_context
                ),
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        direct_ready_release_confirmation = release_confirmation.generate(
            ReleaseConfirmationRequest(
                release_watch_discipline=direct_ready_release_watch_discipline,
                release_confirmation_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_confirmation_author_role="case_operator",
                release_confirmation_context=ready_release_confirmation_context,
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        direct_conditional_release_confirmation = release_confirmation.generate(
            ReleaseConfirmationRequest(
                release_watch_discipline=direct_conditional_release_watch_discipline,
                release_confirmation_class_id="conditional_production_release",
                release_confirmation_author_role="case_operator",
                release_confirmation_context=conditional_release_confirmation_context,
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        release_confirmation.generate(
            ReleaseConfirmationRequest(
                release_watch_discipline=direct_ready_release_watch_discipline,
                release_confirmation_class_id="deferred_release_state",
                release_confirmation_author_role="case_operator",
                release_confirmation_context=deferred_release_confirmation_context,
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        release_confirmation.generate(
            ReleaseConfirmationRequest(
                release_watch_discipline=direct_ready_release_watch_discipline,
                release_confirmation_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_confirmation_author_role="case_operator",
                release_confirmation_context={
                    "release_confirmation_judgment": (
                        "release-confirmed:bootstrap-store-001:price-band"
                    )
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        release_confirmation.generate(
            ReleaseConfirmationRequest(
                release_watch_discipline=direct_ready_release_watch_discipline,
                release_confirmation_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_confirmation_author_role="case_operator",
                release_confirmation_context=rejected_release_confirmation_context,
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        release_confirmation.generate(
            ReleaseConfirmationRequest(
                release_watch_discipline=direct_ready_release_watch_discipline,
                release_confirmation_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_confirmation_author_role="case_operator",
                release_confirmation_context={
                    **ready_release_confirmation_context,
                    "release_observation_reference": (
                        "release-observation:bootstrap-store-001:price-band"
                    ),
                    "contained_rollback_reference": (
                        "contained-rollback:bootstrap-store-001:price-band"
                    ),
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        direct_ready_production_entitlement_check = production_entitlement_check.generate(
            ProductionEntitlementCheckRequest(
                release_confirmation=direct_ready_release_confirmation,
                production_entitlement_check_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                production_entitlement_check_author_role="case_operator",
                production_entitlement_check_context=(
                    ready_production_entitlement_check_context
                ),
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        direct_conditional_production_entitlement_check = (
            production_entitlement_check.generate(
                ProductionEntitlementCheckRequest(
                    release_confirmation=direct_conditional_release_confirmation,
                    production_entitlement_check_class_id=(
                        "conditional_production_release"
                    ),
                    production_entitlement_check_author_role="case_operator",
                    production_entitlement_check_context=(
                        conditional_production_entitlement_check_context
                    ),
                    correlation_id=correlation_id,
                    actor_id=actor_id,
                )
            )
        )
        production_entitlement_check.generate(
            ProductionEntitlementCheckRequest(
                release_confirmation=direct_ready_release_confirmation,
                production_entitlement_check_class_id="deferred_release_state",
                production_entitlement_check_author_role="case_operator",
                production_entitlement_check_context=(
                    deferred_production_entitlement_check_context
                ),
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        production_entitlement_check.generate(
            ProductionEntitlementCheckRequest(
                release_confirmation=direct_ready_release_confirmation,
                production_entitlement_check_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                production_entitlement_check_author_role="case_operator",
                production_entitlement_check_context={
                    **ready_production_entitlement_check_context,
                    "contained_rollback_reference": (
                        "contained-rollback:bootstrap-store-001:price-band"
                    ),
                    "monitoring_admission_reference": (
                        "monitoring-admission:bootstrap-store-001:price-band"
                    ),
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        production_entitlement_check.generate(
            ProductionEntitlementCheckRequest(
                release_confirmation=direct_ready_release_confirmation,
                production_entitlement_check_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                production_entitlement_check_author_role="case_operator",
                production_entitlement_check_context=(
                    rejected_production_entitlement_check_context
                ),
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        production_entitlement_check.generate(
            ProductionEntitlementCheckRequest(
                release_confirmation=direct_ready_release_confirmation,
                production_entitlement_check_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                production_entitlement_check_author_role="case_operator",
                production_entitlement_check_context={
                    "production_entitlement_judgment": (
                        "production-entitlement-approved:bootstrap-store-001:price-band"
                    )
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        direct_ready_contained_rollback = contained_rollback.generate(
            ContainedRollbackRequest(
                production_entitlement_check=direct_ready_production_entitlement_check,
                contained_rollback_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                contained_rollback_author_role="case_operator",
                contained_rollback_context=ready_contained_rollback_context,
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        direct_conditional_contained_rollback = contained_rollback.generate(
            ContainedRollbackRequest(
                production_entitlement_check=(
                    direct_conditional_production_entitlement_check
                ),
                contained_rollback_class_id="conditional_production_release",
                contained_rollback_author_role="case_operator",
                contained_rollback_context=conditional_contained_rollback_context,
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        direct_deferred_contained_rollback = contained_rollback.generate(
            ContainedRollbackRequest(
                production_entitlement_check=direct_ready_production_entitlement_check,
                contained_rollback_class_id="deferred_release_state",
                contained_rollback_author_role="case_operator",
                contained_rollback_context=deferred_contained_rollback_context,
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        contained_rollback.generate(
            ContainedRollbackRequest(
                production_entitlement_check=direct_ready_production_entitlement_check,
                contained_rollback_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                contained_rollback_author_role="case_operator",
                contained_rollback_context={
                    "contained_rollback_judgment": (
                        "contained-rollback:bootstrap-store-001:price-band"
                    )
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        contained_rollback.generate(
            ContainedRollbackRequest(
                production_entitlement_check=direct_ready_production_entitlement_check,
                contained_rollback_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                contained_rollback_author_role="case_operator",
                contained_rollback_context=rejected_contained_rollback_context,
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        contained_rollback.generate(
            ContainedRollbackRequest(
                production_entitlement_check=direct_ready_production_entitlement_check,
                contained_rollback_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                contained_rollback_author_role="case_operator",
                contained_rollback_context={
                    **ready_contained_rollback_context,
                    "release_closure_reference": (
                        "release-closure:bootstrap-store-001:price-band"
                    ),
                    "monitoring_admission_reference": (
                        "monitoring-admission:bootstrap-store-001:price-band"
                    ),
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        release_audit_trace.generate(
            ReleaseAuditTraceRequest(
                contained_rollback=direct_ready_contained_rollback,
                release_audit_trace_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_audit_trace_author_role="case_operator",
                release_audit_trace_context=ready_release_audit_trace_context,
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        release_audit_trace.generate(
            ReleaseAuditTraceRequest(
                contained_rollback=direct_conditional_contained_rollback,
                release_audit_trace_class_id="conditional_production_release",
                release_audit_trace_author_role="case_operator",
                release_audit_trace_context=ready_release_audit_trace_context,
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        release_audit_trace.generate(
            ReleaseAuditTraceRequest(
                contained_rollback=direct_deferred_contained_rollback,
                release_audit_trace_class_id="deferred_release_state",
                release_audit_trace_author_role="case_operator",
                release_audit_trace_context=deferred_release_audit_trace_context,
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        release_audit_trace.generate(
            ReleaseAuditTraceRequest(
                contained_rollback=direct_ready_contained_rollback,
                release_audit_trace_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_audit_trace_author_role="case_operator",
                release_audit_trace_context={
                    "release_audit_trace_judgment": (
                        "release-audit-trace:bootstrap-store-001:price-band"
                    )
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        release_audit_trace.generate(
            ReleaseAuditTraceRequest(
                contained_rollback=direct_ready_contained_rollback,
                release_audit_trace_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_audit_trace_author_role="case_operator",
                release_audit_trace_context=rejected_release_audit_trace_context,
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        release_audit_trace.generate(
            ReleaseAuditTraceRequest(
                contained_rollback=direct_ready_contained_rollback,
                release_audit_trace_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_audit_trace_author_role="case_operator",
                release_audit_trace_context={
                    **ready_release_audit_trace_context,
                    "runtime_verification_reference": (
                        "runtime-verification:bootstrap-store-001:price-band"
                    ),
                    "monitoring_admission_reference": (
                        "monitoring-admission:bootstrap-store-001:price-band"
                    ),
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        release_watch_discipline.generate(
            ReleaseWatchDisciplineRequest(
                rollback_trigger=direct_ready_rollback_trigger,
                release_watch_discipline_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_watch_discipline_author_role="case_operator",
                release_watch_discipline_context={
                    "release_confirmation_window": (
                        "release-confirmation-window:bootstrap-store-001:t-plus-7d"
                    )
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        release_watch_discipline.generate(
            ReleaseWatchDisciplineRequest(
                rollback_trigger=direct_ready_rollback_trigger,
                release_watch_discipline_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_watch_discipline_author_role="case_operator",
                release_watch_discipline_context=(
                    rejected_release_watch_discipline_context
                ),
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        release_watch_discipline.generate(
            ReleaseWatchDisciplineRequest(
                rollback_trigger=direct_ready_rollback_trigger,
                release_watch_discipline_class_id=(
                    "full_scope_production_promotion_candidate"
                ),
                release_watch_discipline_author_role="case_operator",
                release_watch_discipline_context={
                    **ready_release_watch_discipline_context,
                    "release_observation_reference": (
                        "release-observation:bootstrap-store-001:price-band"
                    ),
                    "monitor_alert_reference": (
                        "monitor-alert:bootstrap-store-001:price-band"
                    ),
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        rollback_trigger_guard.generate(
            RollbackTriggerGuardRequest(
                rollout_scope=direct_ready_rollout_scope,
                rollback_trigger_class_id="full_scope_production_promotion_candidate",
                rollback_trigger_author_role="case_operator",
                rollback_trigger_context=rejected_rollback_trigger_context,
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        rollback_trigger_guard.generate(
            RollbackTriggerGuardRequest(
                rollout_scope=direct_ready_rollout_scope,
                rollback_trigger_class_id="full_scope_production_promotion_candidate",
                rollback_trigger_author_role="case_operator",
                rollback_trigger_context={
                    **ready_rollback_trigger_context,
                    "release_observation_reference": (
                        "release-observation:bootstrap-store-001:price-band"
                    ),
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        rollout_scope_controller.generate(
            RolloutScopeControllerRequest(
                promotion_readiness=direct_ready_promotion_readiness,
                rollout_scope_class_id="full_scope_production_promotion_candidate",
                rollout_scope_author_role="case_operator",
                rollout_scope_context=rejected_rollout_scope_context,
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        rollout_scope_controller.generate(
            RolloutScopeControllerRequest(
                promotion_readiness=direct_ready_promotion_readiness,
                rollout_scope_class_id="full_scope_production_promotion_candidate",
                rollout_scope_author_role="case_operator",
                rollout_scope_context={
                    **ready_rollout_scope_context,
                    "rollback_trigger_reference": (
                        "rollback-trigger:bootstrap-store-001:price-band"
                    ),
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        policy_learning_update_mutation_execution_service.generate(
            PolicyLearningUpdateMutationExecutionRequest(
                policy_learning_update_mutation_planning=(
                    prepared_policy_learning_update_mutation_planning
                ),
                policy_learning_update_mutation_execution_class_id=(
                    "policy_mutation_execution_candidate"
                ),
                policy_learning_update_mutation_execution_author_role="case_operator",
                policy_learning_update_mutation_execution_context={
                    "policy_mutation_execution_reference": (
                        "policy-mutation-execution:bootstrap-store-001:price-band"
                    )
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        policy_learning_update_mutation_execution_service.generate(
            PolicyLearningUpdateMutationExecutionRequest(
                policy_learning_update_mutation_planning=(
                    prepared_policy_learning_update_mutation_planning
                ),
                policy_learning_update_mutation_execution_class_id=(
                    "policy_mutation_execution_candidate"
                ),
                policy_learning_update_mutation_execution_author_role="case_operator",
                policy_learning_update_mutation_execution_context=(
                    rejected_policy_learning_update_mutation_execution_context
                ),
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        policy_learning_update_mutation_execution_service.generate(
            PolicyLearningUpdateMutationExecutionRequest(
                policy_learning_update_mutation_planning=(
                    prepared_policy_learning_update_mutation_planning
                ),
                policy_learning_update_mutation_execution_class_id=(
                    "policy_mutation_execution_candidate"
                ),
                policy_learning_update_mutation_execution_author_role="case_operator",
                policy_learning_update_mutation_execution_context={
                    **executed_policy_learning_update_mutation_execution_context,
                    "policy_rollout_reference": (
                        "policy-rollout:bootstrap-store-001:price-band"
                    ),
                    "model_update_execution_reference": (
                        "model-update:bootstrap-policy-001"
                    ),
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        policy_learning_update_mutation_planning_service.generate(
            PolicyLearningUpdateMutationPlanningRequest(
                policy_learning_update_preparation=(
                    prepared_policy_learning_update_preparation
                ),
                policy_learning_update_mutation_planning_class_id=(
                    "policy_mutation_plan_candidate"
                ),
                policy_learning_update_mutation_planning_author_role="case_operator",
                policy_learning_update_mutation_planning_context={
                    "mutation_plan_reference": (
                        "mutation-plan:bootstrap-store-001:price-band"
                    )
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        policy_learning_update_mutation_planning_service.generate(
            PolicyLearningUpdateMutationPlanningRequest(
                policy_learning_update_preparation=(
                    prepared_policy_learning_update_preparation
                ),
                policy_learning_update_mutation_planning_class_id=(
                    "policy_mutation_plan_candidate"
                ),
                policy_learning_update_mutation_planning_author_role="case_operator",
                policy_learning_update_mutation_planning_context=(
                    rejected_policy_learning_update_mutation_planning_context
                ),
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        policy_learning_update_mutation_planning_service.generate(
            PolicyLearningUpdateMutationPlanningRequest(
                policy_learning_update_preparation=(
                    prepared_policy_learning_update_preparation
                ),
                policy_learning_update_mutation_planning_class_id=(
                    "policy_mutation_plan_candidate"
                ),
                policy_learning_update_mutation_planning_author_role="case_operator",
                policy_learning_update_mutation_planning_context={
                    **prepared_policy_learning_update_mutation_planning_context,
                    "policy_mutation_payload": "mutate-policy:bootstrap-price-floor",
                    "model_deployment_reference": "deploy:model:bootstrap-001",
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        policy_learning_update_approval_service.generate(
            PolicyLearningUpdateApprovalRequest(
                policy_learning_update_threshold=approved_policy_learning_update_threshold,
                policy_learning_update_approval_class_id=(
                    "policy_update_preparation_candidate"
                ),
                policy_learning_update_approval_author_role="case_operator",
                policy_learning_update_approval_context={
                    "candidate_update_reference": (
                        "candidate-update:bootstrap-store-001:price-band"
                    )
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        policy_learning_update_approval_service.generate(
            PolicyLearningUpdateApprovalRequest(
                policy_learning_update_threshold=approved_policy_learning_update_threshold,
                policy_learning_update_approval_class_id=(
                    "policy_update_preparation_candidate"
                ),
                policy_learning_update_approval_author_role="case_operator",
                policy_learning_update_approval_context=(
                    rejected_policy_learning_update_approval_context
                ),
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        policy_learning_update_approval_service.generate(
            PolicyLearningUpdateApprovalRequest(
                policy_learning_update_threshold=approved_policy_learning_update_threshold,
                policy_learning_update_approval_class_id=(
                    "policy_update_preparation_candidate"
                ),
                policy_learning_update_approval_author_role="case_operator",
                policy_learning_update_approval_context={
                    **approved_policy_learning_update_approval_context,
                    "policy_mutation_payload": "mutate-policy:bootstrap-price-floor",
                    "model_deployment_reference": "deploy:model:bootstrap-001",
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )
        policy_learning_update_threshold_service.generate(
            PolicyLearningUpdateThresholdRequest(
                policy_learning_evidence_admission=admitted_policy_learning_evidence,
                policy_learning_update_threshold_class_id="policy_update_candidate",
                policy_learning_update_threshold_author_role="case_operator",
                policy_learning_update_threshold_context={
                    **accepted_policy_learning_update_threshold_context,
                    "policy_mutation_payload": "mutate-policy:bootstrap-price-floor",
                    "model_retraining_reference": "model-train:bootstrap-001",
                },
                correlation_id=correlation_id,
                actor_id=actor_id,
            )
        )

        events = audit_store.list_events()
        authority_success_count = sum(
            event.event_type == "decision.authority.authority_resolution_succeeded"
            for event in events
        )
        authority_blocked_count = sum(
            event.event_type == "decision.authority.authority_resolution_blocked"
            for event in events
        )
        delegation_event_count = sum(
            event.event_type == "decision.authority.delegation_applied" for event in events
        )
        scope_violation_count = sum(
            event.event_type == "decision.authority.authority_scope_violation"
            for event in events
        )
        fallback_authority_count = sum(
            event.event_type == "decision.authority.authority_fallback_applied"
            for event in events
        )
        router_success_count = sum(
            event.event_type == "decision.router.router_resolution_succeeded" for event in events
        )
        router_blocked_count = sum(
            event.event_type == "decision.router.router_resolution_blocked" for event in events
        )
        conflict_classification_count = sum(
            event.event_type == "decision.router.conflict_classified" for event in events
        )
        tie_break_count = sum(
            event.event_type == "decision.router.tie_break_applied" for event in events
        )
        unresolved_conflict_count = sum(
            event.event_type == "decision.router.unresolved_conflict_detected" for event in events
        )
        fallback_route_count = sum(
            event.event_type == "decision.router.fallback_route_applied" for event in events
        )
        review_required_count = sum(
            event.event_type == "decision.review.review_trigger_required" for event in events
        )
        review_optional_count = sum(
            event.event_type == "decision.review.review_trigger_optional" for event in events
        )
        threshold_blocked_count = sum(
            event.event_type == "decision.review.threshold_evaluation_blocked" for event in events
        )
        threshold_not_triggered_count = sum(
            event.event_type == "decision.review.threshold_not_triggered" for event in events
        )
        calibration_profile_count = sum(
            event.event_type == "decision.review.calibration_profile_applied" for event in events
        )
        fallback_review_mode_count = sum(
            event.event_type == "decision.review.fallback_review_mode_applied" for event in events
        )
        review_packet_built_count = sum(
            event.event_type == "decision.review.human_review_packet_built" for event in events
        )
        review_packet_blocked_count = sum(
            event.event_type == "decision.review.human_review_packet_build_blocked"
            for event in events
        )
        review_packet_ready_count = sum(
            event.event_type == "decision.review.human_review_packet_ready_for_handoff"
            for event in events
        )
        review_packet_missing_context_count = sum(
            event.event_type == "decision.review.human_review_packet_missing_context"
            for event in events
        )
        review_packet_fallback_template_count = sum(
            event.event_type == "decision.review.human_review_packet_fallback_template_applied"
            for event in events
        )
        review_resolution_recorded_count = sum(
            event.event_type == "decision.review.review_resolution_recorded" for event in events
        )
        review_resolution_blocked_count = sum(
            event.event_type == "decision.review.review_resolution_blocked" for event in events
        )
        review_resolution_ready_count = sum(
            event.event_type == "decision.review.review_resolution_ready_for_disposition"
            for event in events
        )
        review_resolution_missing_context_count = sum(
            event.event_type == "decision.review.review_resolution_missing_context"
            for event in events
        )
        review_resolution_fallback_count = sum(
            event.event_type == "decision.review.review_resolution_fallback_applied"
            for event in events
        )
        recommendation_recorded_count = sum(
            event.event_type == "decision.output.recommendation_recorded"
            for event in events
        )
        recommendation_blocked_count = sum(
            event.event_type == "decision.output.recommendation_blocked"
            for event in events
        )
        recommendation_ready_count = sum(
            event.event_type == "decision.output.recommendation_ready_for_downstream_use"
            for event in events
        )
        recommendation_missing_context_count = sum(
            event.event_type == "decision.output.recommendation_missing_context"
            for event in events
        )
        recommendation_fallback_template_count = sum(
            event.event_type == "decision.output.recommendation_fallback_template_applied"
            for event in events
        )
        policy_output_recorded_count = sum(
            event.event_type == "decision.output.policy_output_recorded" for event in events
        )
        policy_output_blocked_count = sum(
            event.event_type == "decision.output.policy_output_blocked" for event in events
        )
        policy_output_ready_count = sum(
            event.event_type == "decision.output.policy_output_ready_for_downstream_use"
            for event in events
        )
        policy_output_missing_context_count = sum(
            event.event_type == "decision.output.policy_output_missing_context"
            for event in events
        )
        policy_output_fallback_template_count = sum(
            event.event_type == "decision.output.policy_output_fallback_template_applied"
            for event in events
        )
        portfolio_output_recorded_count = sum(
            event.event_type == "decision.output.portfolio_output_recorded"
            for event in events
        )
        portfolio_output_blocked_count = sum(
            event.event_type == "decision.output.portfolio_output_blocked"
            for event in events
        )
        portfolio_output_ready_count = sum(
            event.event_type == "decision.output.portfolio_output_ready_for_downstream_use"
            for event in events
        )
        portfolio_output_missing_context_count = sum(
            event.event_type == "decision.output.portfolio_output_missing_context"
            for event in events
        )
        portfolio_output_fallback_template_count = sum(
            event.event_type == "decision.output.portfolio_output_fallback_template_applied"
            for event in events
        )
        action_instruction_recorded_count = sum(
            event.event_type == "decision.output.action_instruction_recorded"
            for event in events
        )
        action_instruction_blocked_count = sum(
            event.event_type == "decision.output.action_instruction_blocked"
            for event in events
        )
        action_instruction_ready_count = sum(
            event.event_type == "decision.output.action_instruction_ready_for_downstream_use"
            for event in events
        )
        action_instruction_missing_context_count = sum(
            event.event_type == "decision.output.action_instruction_missing_context"
            for event in events
        )
        action_instruction_fallback_template_count = sum(
            event.event_type == "decision.output.action_instruction_fallback_template_applied"
            for event in events
        )
        execution_request_recorded_count = sum(
            event.event_type == "execution_request_recorded" for event in events
        )
        execution_request_blocked_count = sum(
            event.event_type == "execution_request_blocked" for event in events
        )
        execution_request_ready_count = sum(
            event.event_type == "execution_request_ready_for_downstream_use"
            for event in events
        )
        execution_request_missing_context_count = sum(
            event.event_type == "execution_request_missing_context" for event in events
        )
        execution_request_fallback_template_count = sum(
            event.event_type == "execution_request_fallback_template_applied"
            for event in events
        )
        execution_dispatch_recorded_count = sum(
            event.event_type == "execution_dispatch_recorded" for event in events
        )
        execution_dispatch_blocked_count = sum(
            event.event_type == "execution_dispatch_blocked" for event in events
        )
        execution_dispatch_ready_count = sum(
            event.event_type == "execution_dispatch_ready_for_downstream_use"
            for event in events
        )
        execution_dispatch_missing_context_count = sum(
            event.event_type == "execution_dispatch_missing_context" for event in events
        )
        execution_dispatch_fallback_template_count = sum(
            event.event_type == "execution_dispatch_fallback_template_applied"
            for event in events
        )
        execution_outcome_recorded_count = sum(
            event.event_type == "execution_outcome_recorded" for event in events
        )
        execution_outcome_blocked_count = sum(
            event.event_type == "execution_outcome_blocked" for event in events
        )
        execution_outcome_ready_count = sum(
            event.event_type == "execution_outcome_ready_for_downstream_use"
            for event in events
        )
        execution_outcome_missing_context_count = sum(
            event.event_type == "execution_outcome_missing_context" for event in events
        )
        execution_outcome_fallback_template_count = sum(
            event.event_type == "execution_outcome_fallback_template_applied"
            for event in events
        )
        post_mortem_recorded_count = sum(
            event.event_type == "decision.post_mortem.post_mortem_judgment_recorded"
            for event in events
        )
        post_mortem_blocked_count = sum(
            event.event_type == "decision.post_mortem.post_mortem_judgment_blocked"
            for event in events
        )
        post_mortem_ready_count = sum(
            event.event_type
            == "decision.post_mortem.post_mortem_judgment_ready_for_downstream_use"
            for event in events
        )
        post_mortem_missing_context_count = sum(
            event.event_type
            == "decision.post_mortem.post_mortem_judgment_missing_context"
            for event in events
        )
        post_mortem_fallback_template_count = sum(
            event.event_type
            == "decision.post_mortem.post_mortem_judgment_fallback_template_applied"
            for event in events
        )
        policy_learning_recorded_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_evidence_admission_recorded"
            for event in events
        )
        policy_learning_blocked_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_evidence_admission_blocked"
            for event in events
        )
        policy_learning_admitted_for_update_consideration_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_evidence_admission_admitted_for_update_consideration"
            for event in events
        )
        policy_learning_missing_context_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_evidence_admission_missing_context"
            for event in events
        )
        policy_learning_rejected_for_learning_use_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_evidence_admission_rejected_for_learning_use"
            for event in events
        )
        policy_learning_deferred_pending_more_evidence_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_evidence_admission_deferred_pending_more_evidence"
            for event in events
        )
        policy_learning_fallback_template_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_evidence_admission_fallback_template_applied"
            for event in events
        )
        policy_learning_prohibited_overlap_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_evidence_admission_prohibited_overlap_blocked"
            for event in events
        )
        policy_learning_update_threshold_recorded_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_threshold_recorded"
            for event in events
        )
        policy_learning_update_threshold_blocked_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_threshold_blocked"
            for event in events
        )
        policy_learning_update_threshold_accepted_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_threshold_accepted"
            for event in events
        )
        policy_learning_update_threshold_accepted_with_narrowed_scope_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_threshold_accepted_with_narrowed_scope"
            for event in events
        )
        policy_learning_update_threshold_deferred_for_continued_monitoring_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_threshold_deferred_for_continued_monitoring"
            for event in events
        )
        policy_learning_update_threshold_missing_context_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_threshold_missing_context"
            for event in events
        )
        policy_learning_update_threshold_rejected_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_threshold_rejected"
            for event in events
        )
        policy_learning_update_threshold_fallback_template_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_threshold_fallback_template_applied"
            for event in events
        )
        policy_learning_update_threshold_prohibited_overlap_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_threshold_prohibited_overlap_blocked"
            for event in events
        )
        policy_learning_update_approval_recorded_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_approval_recorded"
            for event in events
        )
        policy_learning_update_approval_blocked_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_approval_blocked"
            for event in events
        )
        policy_learning_update_approval_approved_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_approval_approved_for_policy_update_preparation"
            for event in events
        )
        policy_learning_update_approval_approved_with_restrictions_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_approval_approved_with_restrictions"
            for event in events
        )
        policy_learning_update_approval_deferred_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_approval_deferred_pending_additional_governance"
            for event in events
        )
        policy_learning_update_approval_missing_context_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_approval_missing_context"
            for event in events
        )
        policy_learning_update_approval_rejected_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_approval_rejected_for_policy_update_use"
            for event in events
        )
        policy_learning_update_approval_prohibited_overlap_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_approval_prohibited_overlap_blocked"
            for event in events
        )
        policy_learning_update_approval_fallback_template_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_approval_fallback_template_applied"
            for event in events
        )
        policy_learning_update_preparation_recorded_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_preparation_recorded"
            for event in events
        )
        policy_learning_update_preparation_blocked_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_preparation_blocked"
            for event in events
        )
        policy_learning_update_preparation_prepared_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_preparation_prepared_for_policy_mutation_planning"
            for event in events
        )
        policy_learning_update_preparation_prepared_with_restrictions_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_preparation_prepared_with_restrictions"
            for event in events
        )
        policy_learning_update_preparation_deferred_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_preparation_deferred_pending_preparation_prerequisites"
            for event in events
        )
        policy_learning_update_preparation_missing_context_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_preparation_missing_context"
            for event in events
        )
        policy_learning_update_preparation_rejected_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_preparation_rejected_for_preparation_use"
            for event in events
        )
        policy_learning_update_preparation_prohibited_overlap_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_preparation_prohibited_overlap_blocked"
            for event in events
        )
        policy_learning_update_preparation_fallback_template_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_preparation_fallback_template_applied"
            for event in events
        )
        policy_learning_update_mutation_planning_recorded_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_mutation_planning_recorded"
            for event in events
        )
        policy_learning_update_mutation_planning_blocked_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_mutation_planning_blocked"
            for event in events
        )
        policy_learning_update_mutation_planning_ready_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_mutation_planning_ready_for_policy_mutation_planning"
            for event in events
        )
        policy_learning_update_mutation_planning_ready_with_restrictions_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_mutation_planning_ready_for_policy_mutation_planning_with_restrictions"
            for event in events
        )
        policy_learning_update_mutation_planning_deferred_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_mutation_planning_deferred_pending_mutation_planning_prerequisites"
            for event in events
        )
        policy_learning_update_mutation_planning_missing_context_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_mutation_planning_missing_context"
            for event in events
        )
        policy_learning_update_mutation_planning_rejected_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_mutation_planning_rejected_for_mutation_planning_use"
            for event in events
        )
        policy_learning_update_mutation_planning_prohibited_overlap_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_mutation_planning_prohibited_overlap_blocked"
            for event in events
        )
        policy_learning_update_mutation_planning_fallback_template_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_mutation_planning_fallback_template_applied"
            for event in events
        )
        policy_learning_update_mutation_execution_recorded_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_mutation_execution_recorded"
            for event in events
        )
        policy_learning_update_mutation_execution_blocked_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_mutation_execution_blocked"
            for event in events
        )
        policy_learning_update_mutation_execution_ready_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_mutation_execution_ready_for_policy_mutation_execution"
            for event in events
        )
        policy_learning_update_mutation_execution_ready_with_restrictions_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_mutation_execution_ready_for_policy_mutation_execution_with_restrictions"
            for event in events
        )
        policy_learning_update_mutation_execution_deferred_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_mutation_execution_deferred_pending_mutation_execution_prerequisites"
            for event in events
        )
        policy_learning_update_mutation_execution_missing_context_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_mutation_execution_missing_context"
            for event in events
        )
        policy_learning_update_mutation_execution_rejected_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_mutation_execution_rejected_for_mutation_execution_use"
            for event in events
        )
        policy_learning_update_mutation_execution_prohibited_overlap_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_mutation_execution_prohibited_overlap_blocked"
            for event in events
        )
        policy_learning_update_mutation_execution_fallback_template_count = sum(
            event.event_type
            == "decision.policy_learning.policy_learning_update_mutation_execution_fallback_template_applied"
            for event in events
        )
        promotion_readiness_recorded_count = sum(
            event.event_type == "runtime.release.promotion_readiness_recorded"
            for event in events
        )
        promotion_readiness_blocked_count = sum(
            event.event_type == "runtime.release.promotion_readiness_blocked"
            for event in events
        )
        promotion_readiness_ready_for_rollout_scope_control_count = sum(
            event.event_type
            == "runtime.release.promotion_readiness_ready_for_rollout_scope_control"
            for event in events
        )
        promotion_readiness_conditionally_ready_for_rollout_scope_control_count = sum(
            event.event_type
            == "runtime.release.promotion_readiness_conditionally_ready_for_rollout_scope_control"
            for event in events
        )
        promotion_readiness_deferred_count = sum(
            event.event_type
            == "runtime.release.promotion_readiness_deferred_pending_promotion_readiness_evidence"
            for event in events
        )
        promotion_readiness_missing_context_count = sum(
            event.event_type
            == "runtime.release.promotion_readiness_missing_context"
            for event in events
        )
        promotion_readiness_rejected_count = sum(
            event.event_type
            == "runtime.release.promotion_readiness_rejected_for_promotion_use"
            for event in events
        )
        promotion_readiness_prohibited_overlap_count = sum(
            event.event_type
            == "runtime.release.promotion_readiness_prohibited_overlap_blocked"
            for event in events
        )
        promotion_readiness_fallback_template_count = sum(
            event.event_type
            == "runtime.release.promotion_readiness_fallback_template_applied"
            for event in events
        )
        rollout_scope_recorded_count = sum(
            event.event_type == "runtime.release.rollout_scope_recorded"
            for event in events
        )
        rollout_scope_blocked_count = sum(
            event.event_type == "runtime.release.rollout_scope_blocked"
            for event in events
        )
        rollout_scope_ready_for_rollback_trigger_guard_count = sum(
            event.event_type
            == "runtime.release.rollout_scope_ready_for_rollback_trigger_guard"
            for event in events
        )
        rollout_scope_conditionally_ready_for_rollback_trigger_guard_count = sum(
            event.event_type
            == "runtime.release.rollout_scope_conditionally_ready_for_rollback_trigger_guard"
            for event in events
        )
        rollout_scope_deferred_count = sum(
            event.event_type
            == "runtime.release.rollout_scope_deferred_pending_rollout_scope_evidence"
            for event in events
        )
        rollout_scope_missing_context_count = sum(
            event.event_type == "runtime.release.rollout_scope_missing_context"
            for event in events
        )
        rollout_scope_rejected_count = sum(
            event.event_type
            == "runtime.release.rollout_scope_rejected_for_rollout_scope_use"
            for event in events
        )
        rollout_scope_prohibited_overlap_count = sum(
            event.event_type
            == "runtime.release.rollout_scope_prohibited_overlap_blocked"
            for event in events
        )
        rollout_scope_fallback_template_count = sum(
            event.event_type
            == "runtime.release.rollout_scope_fallback_template_applied"
            for event in events
        )
        rollback_trigger_recorded_count = sum(
            event.event_type == "runtime.release.rollback_trigger_recorded"
            for event in events
        )
        rollback_trigger_blocked_count = sum(
            event.event_type == "runtime.release.rollback_trigger_blocked"
            for event in events
        )
        rollback_trigger_ready_for_release_watch_discipline_count = sum(
            event.event_type
            == "runtime.release.rollback_trigger_ready_for_release_watch_discipline"
            for event in events
        )
        rollback_trigger_conditionally_ready_for_release_watch_discipline_count = sum(
            event.event_type
            == "runtime.release.rollback_trigger_conditionally_ready_for_release_watch_discipline"
            for event in events
        )
        rollback_trigger_deferred_count = sum(
            event.event_type
            == "runtime.release.rollback_trigger_deferred_pending_rollback_trigger_evidence"
            for event in events
        )
        rollback_trigger_missing_context_count = sum(
            event.event_type == "runtime.release.rollback_trigger_missing_context"
            for event in events
        )
        rollback_trigger_rejected_count = sum(
            event.event_type
            == "runtime.release.rollback_trigger_rejected_for_rollback_trigger_use"
            for event in events
        )
        rollback_trigger_prohibited_overlap_count = sum(
            event.event_type
            == "runtime.release.rollback_trigger_prohibited_overlap_blocked"
            for event in events
        )
        rollback_trigger_fallback_template_count = sum(
            event.event_type
            == "runtime.release.rollback_trigger_fallback_template_applied"
            for event in events
        )
        release_watch_discipline_recorded_count = sum(
            event.event_type == "runtime.release.release_watch_discipline_recorded"
            for event in events
        )
        release_watch_discipline_blocked_count = sum(
            event.event_type == "runtime.release.release_watch_discipline_blocked"
            for event in events
        )
        release_watch_discipline_ready_for_release_confirmation_count = sum(
            event.event_type
            == "runtime.release.release_watch_discipline_ready_for_release_confirmation"
            for event in events
        )
        release_watch_discipline_conditionally_ready_for_release_confirmation_count = sum(
            event.event_type
            == "runtime.release.release_watch_discipline_conditionally_ready_for_release_confirmation"
            for event in events
        )
        release_watch_discipline_deferred_count = sum(
            event.event_type
            == "runtime.release.release_watch_discipline_deferred_pending_release_watch_discipline_evidence"
            for event in events
        )
        release_watch_discipline_missing_context_count = sum(
            event.event_type
            == "runtime.release.release_watch_discipline_missing_context"
            for event in events
        )
        release_watch_discipline_rejected_count = sum(
            event.event_type
            == "runtime.release.release_watch_discipline_rejected_for_release_watch_discipline_use"
            for event in events
        )
        release_watch_discipline_prohibited_overlap_count = sum(
            event.event_type
            == "runtime.release.release_watch_discipline_prohibited_overlap_blocked"
            for event in events
        )
        release_watch_discipline_fallback_template_count = sum(
            event.event_type
            == "runtime.release.release_watch_discipline_fallback_template_applied"
            for event in events
        )
        release_confirmation_recorded_count = sum(
            event.event_type == "runtime.release.release_confirmation_recorded"
            for event in events
        )
        release_confirmation_blocked_count = sum(
            event.event_type == "runtime.release.release_confirmation_blocked"
            for event in events
        )
        release_confirmation_confirmed_count = sum(
            event.event_type
            == "runtime.release.release_confirmation_confirmed_for_broader_trusted_production_use"
            for event in events
        )
        release_confirmation_conditionally_confirmed_count = sum(
            event.event_type
            == "runtime.release.release_confirmation_conditionally_confirmed_for_bounded_production_use"
            for event in events
        )
        release_confirmation_deferred_count = sum(
            event.event_type
            == "runtime.release.release_confirmation_deferred_pending_release_confirmation_evidence"
            for event in events
        )
        release_confirmation_missing_context_count = sum(
            event.event_type == "runtime.release.release_confirmation_missing_context"
            for event in events
        )
        release_confirmation_rejected_count = sum(
            event.event_type
            == "runtime.release.release_confirmation_rejected_for_release_confirmation_use"
            for event in events
        )
        release_confirmation_prohibited_overlap_count = sum(
            event.event_type
            == "runtime.release.release_confirmation_prohibited_overlap_blocked"
            for event in events
        )
        release_confirmation_fallback_template_count = sum(
            event.event_type
            == "runtime.release.release_confirmation_fallback_template_applied"
            for event in events
        )
        production_entitlement_check_recorded_count = sum(
            event.event_type
            == "runtime.release.production_entitlement_check_recorded"
            for event in events
        )
        production_entitlement_check_blocked_count = sum(
            event.event_type
            == "runtime.release.production_entitlement_check_blocked"
            for event in events
        )
        production_entitlement_check_approved_count = sum(
            event.event_type
            == "runtime.release.production_entitlement_check_approved_for_broader_trusted_production_entitlement"
            for event in events
        )
        production_entitlement_check_conditionally_approved_count = sum(
            event.event_type
            == "runtime.release.production_entitlement_check_conditionally_approved_for_bounded_production_entitlement"
            for event in events
        )
        production_entitlement_check_deferred_count = sum(
            event.event_type
            == "runtime.release.production_entitlement_check_deferred_pending_production_entitlement_evidence"
            for event in events
        )
        production_entitlement_check_missing_context_count = sum(
            event.event_type
            == "runtime.release.production_entitlement_check_missing_context"
            for event in events
        )
        production_entitlement_check_rejected_count = sum(
            event.event_type
            == "runtime.release.production_entitlement_check_rejected_for_production_entitlement_use"
            for event in events
        )
        production_entitlement_check_prohibited_overlap_count = sum(
            event.event_type
            == "runtime.release.production_entitlement_check_prohibited_overlap_blocked"
            for event in events
        )
        production_entitlement_check_fallback_template_count = sum(
            event.event_type
            == "runtime.release.production_entitlement_check_fallback_template_applied"
            for event in events
        )
        contained_rollback_recorded_count = sum(
            event.event_type == "runtime.release.contained_rollback_recorded"
            for event in events
        )
        contained_rollback_blocked_count = sum(
            event.event_type == "runtime.release.contained_rollback_blocked"
            for event in events
        )
        contained_rollback_bounded_exposure_preserved_count = sum(
            event.event_type
            == "runtime.release.contained_rollback_bounded_exposure_preserved"
            for event in events
        )
        contained_rollback_partial_reversal_bounded_count = sum(
            event.event_type
            == "runtime.release.contained_rollback_partial_reversal_bounded"
            for event in events
        )
        contained_rollback_deferred_count = sum(
            event.event_type
            == "runtime.release.contained_rollback_deferred_pending_contained_rollback_evidence"
            for event in events
        )
        contained_rollback_missing_context_count = sum(
            event.event_type == "runtime.release.contained_rollback_missing_context"
            for event in events
        )
        contained_rollback_rejected_count = sum(
            event.event_type
            == "runtime.release.contained_rollback_rejected_for_contained_rollback_use"
            for event in events
        )
        contained_rollback_prohibited_overlap_count = sum(
            event.event_type
            == "runtime.release.contained_rollback_prohibited_overlap_blocked"
            for event in events
        )
        contained_rollback_fallback_template_count = sum(
            event.event_type
            == "runtime.release.contained_rollback_fallback_template_applied"
            for event in events
        )
        release_audit_trace_recorded_count = sum(
            event.event_type == "runtime.release.release_audit_trace_recorded"
            for event in events
        )
        release_audit_trace_blocked_count = sum(
            event.event_type == "runtime.release.release_audit_trace_blocked"
            for event in events
        )
        release_audit_trace_lineage_preserved_count = sum(
            event.event_type
            == "runtime.release.release_audit_trace_release_control_lineage_preserved"
            for event in events
        )
        release_audit_trace_invalid_release_state_visible_count = sum(
            event.event_type
            == "runtime.release.release_audit_trace_invalid_release_state_visible"
            for event in events
        )
        release_audit_trace_invalid_exposure_visible_count = sum(
            event.event_type
            == "runtime.release.release_audit_trace_invalid_exposure_visible"
            for event in events
        )
        release_audit_trace_no_silent_promotion_preserved_count = sum(
            event.event_type
            == "runtime.release.release_audit_trace_no_silent_promotion_preserved"
            for event in events
        )
        release_audit_trace_deferred_count = sum(
            event.event_type
            == "runtime.release.release_audit_trace_deferred_pending_release_audit_trace_evidence"
            for event in events
        )
        release_audit_trace_missing_context_count = sum(
            event.event_type
            == "runtime.release.release_audit_trace_missing_context"
            for event in events
        )
        release_audit_trace_rejected_count = sum(
            event.event_type
            == "runtime.release.release_audit_trace_rejected_for_release_audit_trace_use"
            for event in events
        )
        release_audit_trace_prohibited_overlap_count = sum(
            event.event_type
            == "runtime.release.release_audit_trace_prohibited_overlap_blocked"
            for event in events
        )
        release_audit_trace_fallback_template_count = sum(
            event.event_type
            == "runtime.release.release_audit_trace_fallback_template_applied"
            for event in events
        )
        blocked_transition_count = sum(
            event.event_type == "decision.case.transition_blocked" for event in events
        )
        invalid_transition_count = sum(
            event.event_type == "decision.case.transition_invalid" for event in events
        )

        return BootstrapArtifacts(
            feature_name=feature.name,
            raw_record_id=raw_record.raw_record_id,
            episode_id=final_episode.episode_id,
            final_state=final_episode.current_state,
            final_stage=final_episode.current_stage,
            authority_success_count=authority_success_count,
            authority_blocked_count=authority_blocked_count,
            delegation_event_count=delegation_event_count,
            scope_violation_count=scope_violation_count,
            fallback_authority_count=fallback_authority_count,
            router_success_count=router_success_count,
            router_blocked_count=router_blocked_count,
            conflict_classification_count=conflict_classification_count,
            tie_break_count=tie_break_count,
            unresolved_conflict_count=unresolved_conflict_count,
            fallback_route_count=fallback_route_count,
            review_required_count=review_required_count,
            review_optional_count=review_optional_count,
            threshold_blocked_count=threshold_blocked_count,
            threshold_not_triggered_count=threshold_not_triggered_count,
            calibration_profile_count=calibration_profile_count,
            fallback_review_mode_count=fallback_review_mode_count,
            review_packet_built_count=review_packet_built_count,
            review_packet_blocked_count=review_packet_blocked_count,
            review_packet_ready_count=review_packet_ready_count,
            review_packet_missing_context_count=review_packet_missing_context_count,
            review_packet_fallback_template_count=review_packet_fallback_template_count,
            review_resolution_recorded_count=review_resolution_recorded_count,
            review_resolution_blocked_count=review_resolution_blocked_count,
            review_resolution_ready_count=review_resolution_ready_count,
            review_resolution_missing_context_count=review_resolution_missing_context_count,
            review_resolution_fallback_count=review_resolution_fallback_count,
            recommendation_recorded_count=recommendation_recorded_count,
            recommendation_blocked_count=recommendation_blocked_count,
            recommendation_ready_count=recommendation_ready_count,
            recommendation_missing_context_count=recommendation_missing_context_count,
            recommendation_fallback_template_count=recommendation_fallback_template_count,
            policy_output_recorded_count=policy_output_recorded_count,
            policy_output_blocked_count=policy_output_blocked_count,
            policy_output_ready_count=policy_output_ready_count,
            policy_output_missing_context_count=policy_output_missing_context_count,
            policy_output_fallback_template_count=policy_output_fallback_template_count,
            portfolio_output_recorded_count=portfolio_output_recorded_count,
            portfolio_output_blocked_count=portfolio_output_blocked_count,
            portfolio_output_ready_count=portfolio_output_ready_count,
            portfolio_output_missing_context_count=portfolio_output_missing_context_count,
            portfolio_output_fallback_template_count=portfolio_output_fallback_template_count,
            action_instruction_recorded_count=action_instruction_recorded_count,
            action_instruction_blocked_count=action_instruction_blocked_count,
            action_instruction_ready_count=action_instruction_ready_count,
            action_instruction_missing_context_count=(
                action_instruction_missing_context_count
            ),
            action_instruction_fallback_template_count=(
                action_instruction_fallback_template_count
            ),
            execution_request_recorded_count=execution_request_recorded_count,
            execution_request_blocked_count=execution_request_blocked_count,
            execution_request_ready_count=execution_request_ready_count,
            execution_request_missing_context_count=(
                execution_request_missing_context_count
            ),
            execution_request_fallback_template_count=(
                execution_request_fallback_template_count
            ),
            execution_dispatch_recorded_count=execution_dispatch_recorded_count,
            execution_dispatch_blocked_count=execution_dispatch_blocked_count,
            execution_dispatch_ready_count=execution_dispatch_ready_count,
            execution_dispatch_missing_context_count=(
                execution_dispatch_missing_context_count
            ),
            execution_dispatch_fallback_template_count=(
                execution_dispatch_fallback_template_count
            ),
            execution_outcome_recorded_count=execution_outcome_recorded_count,
            execution_outcome_blocked_count=execution_outcome_blocked_count,
            execution_outcome_ready_count=execution_outcome_ready_count,
            execution_outcome_missing_context_count=(
                execution_outcome_missing_context_count
            ),
            execution_outcome_fallback_template_count=(
                execution_outcome_fallback_template_count
            ),
            post_mortem_recorded_count=post_mortem_recorded_count,
            post_mortem_blocked_count=post_mortem_blocked_count,
            post_mortem_ready_count=post_mortem_ready_count,
            post_mortem_missing_context_count=post_mortem_missing_context_count,
            post_mortem_fallback_template_count=post_mortem_fallback_template_count,
            policy_learning_recorded_count=policy_learning_recorded_count,
            policy_learning_blocked_count=policy_learning_blocked_count,
            policy_learning_admitted_for_update_consideration_count=(
                policy_learning_admitted_for_update_consideration_count
            ),
            policy_learning_missing_context_count=(
                policy_learning_missing_context_count
            ),
            policy_learning_rejected_for_learning_use_count=(
                policy_learning_rejected_for_learning_use_count
            ),
            policy_learning_deferred_pending_more_evidence_count=(
                policy_learning_deferred_pending_more_evidence_count
            ),
            policy_learning_fallback_template_count=(
                policy_learning_fallback_template_count
            ),
            policy_learning_prohibited_overlap_count=(
                policy_learning_prohibited_overlap_count
            ),
            policy_learning_update_threshold_recorded_count=(
                policy_learning_update_threshold_recorded_count
            ),
            policy_learning_update_threshold_blocked_count=(
                policy_learning_update_threshold_blocked_count
            ),
            policy_learning_update_threshold_accepted_count=(
                policy_learning_update_threshold_accepted_count
            ),
            policy_learning_update_threshold_accepted_with_narrowed_scope_count=(
                policy_learning_update_threshold_accepted_with_narrowed_scope_count
            ),
            policy_learning_update_threshold_deferred_for_continued_monitoring_count=(
                policy_learning_update_threshold_deferred_for_continued_monitoring_count
            ),
            policy_learning_update_threshold_missing_context_count=(
                policy_learning_update_threshold_missing_context_count
            ),
            policy_learning_update_threshold_rejected_count=(
                policy_learning_update_threshold_rejected_count
            ),
            policy_learning_update_threshold_fallback_template_count=(
                policy_learning_update_threshold_fallback_template_count
            ),
            policy_learning_update_threshold_prohibited_overlap_count=(
                policy_learning_update_threshold_prohibited_overlap_count
            ),
            policy_learning_update_approval_recorded_count=(
                policy_learning_update_approval_recorded_count
            ),
            policy_learning_update_approval_blocked_count=(
                policy_learning_update_approval_blocked_count
            ),
            policy_learning_update_approval_approved_count=(
                policy_learning_update_approval_approved_count
            ),
            policy_learning_update_approval_approved_with_restrictions_count=(
                policy_learning_update_approval_approved_with_restrictions_count
            ),
            policy_learning_update_approval_deferred_count=(
                policy_learning_update_approval_deferred_count
            ),
            policy_learning_update_approval_missing_context_count=(
                policy_learning_update_approval_missing_context_count
            ),
            policy_learning_update_approval_rejected_count=(
                policy_learning_update_approval_rejected_count
            ),
            policy_learning_update_approval_prohibited_overlap_count=(
                policy_learning_update_approval_prohibited_overlap_count
            ),
            policy_learning_update_approval_fallback_template_count=(
                policy_learning_update_approval_fallback_template_count
            ),
            policy_learning_update_preparation_recorded_count=(
                policy_learning_update_preparation_recorded_count
            ),
            policy_learning_update_preparation_blocked_count=(
                policy_learning_update_preparation_blocked_count
            ),
            policy_learning_update_preparation_prepared_count=(
                policy_learning_update_preparation_prepared_count
            ),
            policy_learning_update_preparation_prepared_with_restrictions_count=(
                policy_learning_update_preparation_prepared_with_restrictions_count
            ),
            policy_learning_update_preparation_deferred_count=(
                policy_learning_update_preparation_deferred_count
            ),
            policy_learning_update_preparation_missing_context_count=(
                policy_learning_update_preparation_missing_context_count
            ),
            policy_learning_update_preparation_rejected_count=(
                policy_learning_update_preparation_rejected_count
            ),
            policy_learning_update_preparation_prohibited_overlap_count=(
                policy_learning_update_preparation_prohibited_overlap_count
            ),
            policy_learning_update_preparation_fallback_template_count=(
                policy_learning_update_preparation_fallback_template_count
            ),
            policy_learning_update_mutation_planning_recorded_count=(
                policy_learning_update_mutation_planning_recorded_count
            ),
            policy_learning_update_mutation_planning_blocked_count=(
                policy_learning_update_mutation_planning_blocked_count
            ),
            policy_learning_update_mutation_planning_ready_count=(
                policy_learning_update_mutation_planning_ready_count
            ),
            policy_learning_update_mutation_planning_ready_with_restrictions_count=(
                policy_learning_update_mutation_planning_ready_with_restrictions_count
            ),
            policy_learning_update_mutation_planning_deferred_count=(
                policy_learning_update_mutation_planning_deferred_count
            ),
            policy_learning_update_mutation_planning_missing_context_count=(
                policy_learning_update_mutation_planning_missing_context_count
            ),
            policy_learning_update_mutation_planning_rejected_count=(
                policy_learning_update_mutation_planning_rejected_count
            ),
            policy_learning_update_mutation_planning_prohibited_overlap_count=(
                policy_learning_update_mutation_planning_prohibited_overlap_count
            ),
            policy_learning_update_mutation_planning_fallback_template_count=(
                policy_learning_update_mutation_planning_fallback_template_count
            ),
            policy_learning_update_mutation_execution_recorded_count=(
                policy_learning_update_mutation_execution_recorded_count
            ),
            policy_learning_update_mutation_execution_blocked_count=(
                policy_learning_update_mutation_execution_blocked_count
            ),
            policy_learning_update_mutation_execution_ready_count=(
                policy_learning_update_mutation_execution_ready_count
            ),
            policy_learning_update_mutation_execution_ready_with_restrictions_count=(
                policy_learning_update_mutation_execution_ready_with_restrictions_count
            ),
            policy_learning_update_mutation_execution_deferred_count=(
                policy_learning_update_mutation_execution_deferred_count
            ),
            policy_learning_update_mutation_execution_missing_context_count=(
                policy_learning_update_mutation_execution_missing_context_count
            ),
            policy_learning_update_mutation_execution_rejected_count=(
                policy_learning_update_mutation_execution_rejected_count
            ),
            policy_learning_update_mutation_execution_prohibited_overlap_count=(
                policy_learning_update_mutation_execution_prohibited_overlap_count
            ),
            policy_learning_update_mutation_execution_fallback_template_count=(
                policy_learning_update_mutation_execution_fallback_template_count
            ),
            promotion_readiness_recorded_count=promotion_readiness_recorded_count,
            promotion_readiness_blocked_count=promotion_readiness_blocked_count,
            promotion_readiness_ready_for_rollout_scope_control_count=(
                promotion_readiness_ready_for_rollout_scope_control_count
            ),
            promotion_readiness_conditionally_ready_for_rollout_scope_control_count=(
                promotion_readiness_conditionally_ready_for_rollout_scope_control_count
            ),
            promotion_readiness_deferred_count=promotion_readiness_deferred_count,
            promotion_readiness_missing_context_count=(
                promotion_readiness_missing_context_count
            ),
            promotion_readiness_rejected_count=promotion_readiness_rejected_count,
            promotion_readiness_prohibited_overlap_count=(
                promotion_readiness_prohibited_overlap_count
            ),
            promotion_readiness_fallback_template_count=(
                promotion_readiness_fallback_template_count
            ),
            rollout_scope_recorded_count=rollout_scope_recorded_count,
            rollout_scope_blocked_count=rollout_scope_blocked_count,
            rollout_scope_ready_for_rollback_trigger_guard_count=(
                rollout_scope_ready_for_rollback_trigger_guard_count
            ),
            rollout_scope_conditionally_ready_for_rollback_trigger_guard_count=(
                rollout_scope_conditionally_ready_for_rollback_trigger_guard_count
            ),
            rollout_scope_deferred_count=rollout_scope_deferred_count,
            rollout_scope_missing_context_count=(
                rollout_scope_missing_context_count
            ),
            rollout_scope_rejected_count=rollout_scope_rejected_count,
            rollout_scope_prohibited_overlap_count=(
                rollout_scope_prohibited_overlap_count
            ),
            rollout_scope_fallback_template_count=(
                rollout_scope_fallback_template_count
            ),
            rollback_trigger_recorded_count=rollback_trigger_recorded_count,
            rollback_trigger_blocked_count=rollback_trigger_blocked_count,
            rollback_trigger_ready_for_release_watch_discipline_count=(
                rollback_trigger_ready_for_release_watch_discipline_count
            ),
            rollback_trigger_conditionally_ready_for_release_watch_discipline_count=(
                rollback_trigger_conditionally_ready_for_release_watch_discipline_count
            ),
            rollback_trigger_deferred_count=rollback_trigger_deferred_count,
            rollback_trigger_missing_context_count=(
                rollback_trigger_missing_context_count
            ),
            rollback_trigger_rejected_count=rollback_trigger_rejected_count,
            rollback_trigger_prohibited_overlap_count=(
                rollback_trigger_prohibited_overlap_count
            ),
            rollback_trigger_fallback_template_count=(
                rollback_trigger_fallback_template_count
            ),
            release_watch_discipline_recorded_count=(
                release_watch_discipline_recorded_count
            ),
            release_watch_discipline_blocked_count=(
                release_watch_discipline_blocked_count
            ),
            release_watch_discipline_ready_for_release_confirmation_count=(
                release_watch_discipline_ready_for_release_confirmation_count
            ),
            release_watch_discipline_conditionally_ready_for_release_confirmation_count=(
                release_watch_discipline_conditionally_ready_for_release_confirmation_count
            ),
            release_watch_discipline_deferred_count=(
                release_watch_discipline_deferred_count
            ),
            release_watch_discipline_missing_context_count=(
                release_watch_discipline_missing_context_count
            ),
            release_watch_discipline_rejected_count=(
                release_watch_discipline_rejected_count
            ),
            release_watch_discipline_prohibited_overlap_count=(
                release_watch_discipline_prohibited_overlap_count
            ),
            release_watch_discipline_fallback_template_count=(
                release_watch_discipline_fallback_template_count
            ),
            release_confirmation_recorded_count=release_confirmation_recorded_count,
            release_confirmation_blocked_count=release_confirmation_blocked_count,
            release_confirmation_confirmed_count=release_confirmation_confirmed_count,
            release_confirmation_conditionally_confirmed_count=(
                release_confirmation_conditionally_confirmed_count
            ),
            release_confirmation_deferred_count=release_confirmation_deferred_count,
            release_confirmation_missing_context_count=(
                release_confirmation_missing_context_count
            ),
            release_confirmation_rejected_count=release_confirmation_rejected_count,
            release_confirmation_prohibited_overlap_count=(
                release_confirmation_prohibited_overlap_count
            ),
            release_confirmation_fallback_template_count=(
                release_confirmation_fallback_template_count
            ),
            production_entitlement_check_recorded_count=(
                production_entitlement_check_recorded_count
            ),
            production_entitlement_check_blocked_count=(
                production_entitlement_check_blocked_count
            ),
            production_entitlement_check_approved_count=(
                production_entitlement_check_approved_count
            ),
            production_entitlement_check_conditionally_approved_count=(
                production_entitlement_check_conditionally_approved_count
            ),
            production_entitlement_check_deferred_count=(
                production_entitlement_check_deferred_count
            ),
            production_entitlement_check_missing_context_count=(
                production_entitlement_check_missing_context_count
            ),
            production_entitlement_check_rejected_count=(
                production_entitlement_check_rejected_count
            ),
            production_entitlement_check_prohibited_overlap_count=(
                production_entitlement_check_prohibited_overlap_count
            ),
            production_entitlement_check_fallback_template_count=(
                production_entitlement_check_fallback_template_count
            ),
            contained_rollback_recorded_count=contained_rollback_recorded_count,
            contained_rollback_blocked_count=contained_rollback_blocked_count,
            contained_rollback_bounded_exposure_preserved_count=(
                contained_rollback_bounded_exposure_preserved_count
            ),
            contained_rollback_partial_reversal_bounded_count=(
                contained_rollback_partial_reversal_bounded_count
            ),
            contained_rollback_deferred_count=contained_rollback_deferred_count,
            contained_rollback_missing_context_count=(
                contained_rollback_missing_context_count
            ),
            contained_rollback_rejected_count=contained_rollback_rejected_count,
            contained_rollback_prohibited_overlap_count=(
                contained_rollback_prohibited_overlap_count
            ),
            contained_rollback_fallback_template_count=(
                contained_rollback_fallback_template_count
            ),
            release_audit_trace_recorded_count=release_audit_trace_recorded_count,
            release_audit_trace_blocked_count=release_audit_trace_blocked_count,
            release_audit_trace_lineage_preserved_count=(
                release_audit_trace_lineage_preserved_count
            ),
            release_audit_trace_invalid_release_state_visible_count=(
                release_audit_trace_invalid_release_state_visible_count
            ),
            release_audit_trace_invalid_exposure_visible_count=(
                release_audit_trace_invalid_exposure_visible_count
            ),
            release_audit_trace_no_silent_promotion_preserved_count=(
                release_audit_trace_no_silent_promotion_preserved_count
            ),
            release_audit_trace_deferred_count=release_audit_trace_deferred_count,
            release_audit_trace_missing_context_count=(
                release_audit_trace_missing_context_count
            ),
            release_audit_trace_rejected_count=release_audit_trace_rejected_count,
            release_audit_trace_prohibited_overlap_count=(
                release_audit_trace_prohibited_overlap_count
            ),
            release_audit_trace_fallback_template_count=(
                release_audit_trace_fallback_template_count
            ),
            blocked_transition_count=blocked_transition_count,
            invalid_transition_count=invalid_transition_count,
            audit_event_count=len(events),
        )
