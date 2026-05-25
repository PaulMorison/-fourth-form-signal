from __future__ import annotations

"""Lifecycle state application for governed case episodes.

Canon ownership:
- Applies validated lifecycle transitions to case episodes.
- Keeps state legitimacy, routing legitimacy, review-trigger legitimacy, and
    audit emission explicit and separate from orchestration-stage meaning.
"""

from dataclasses import dataclass
from typing import Mapping

from decision.case.case_transition_audit_adapter import CaseTransitionAuditAdapter
from decision.output import (
    ActionInstructionRequest,
    ActionInstructionService,
    PortfolioOutputRequest,
    PortfolioOutputService,
    PolicyOutputRequest,
    PolicyOutputService,
    RecommendationRequest,
    RecommendationService,
)
from decision.policy_learning import (
    PolicyLearningEvidenceAdmissionRequest,
    PolicyLearningEvidenceAdmissionService,
    PolicyLearningUpdateApprovalRequest,
    PolicyLearningUpdateApprovalService,
    PolicyLearningUpdateMutationExecutionRequest,
    PolicyLearningUpdateMutationExecutionService,
    PolicyLearningUpdateMutationPlanningRequest,
    PolicyLearningUpdateMutationPlanningService,
    PolicyLearningUpdatePreparationRequest,
    PolicyLearningUpdatePreparationService,
    PolicyLearningUpdateThresholdRequest,
    PolicyLearningUpdateThresholdService,
)
from runtime.release import (
    ContainedRollback,
    ContainedRollbackRequest,
    ProductionEntitlementCheck,
    ProductionEntitlementCheckRequest,
    PromotionReadinessGate,
    PromotionReadinessGateRequest,
    ReleaseConfirmation,
    ReleaseConfirmationRequest,
    ReleaseAuditTrace,
    ReleaseAuditTraceRequest,
    ReleaseWatchDiscipline,
    ReleaseWatchDisciplineRequest,
    RollbackTriggerGuard,
    RollbackTriggerGuardRequest,
    RolloutScopeController,
    RolloutScopeControllerRequest,
)
from decision.post_mortem import (
    PostMortemJudgmentRequest,
    PostMortemJudgmentService,
)
from execution import (
    ExecutionDispatchBoundaryRequest,
    ExecutionDispatchBoundaryService,
    ExecutionOutcomeCaptureRequest,
    ExecutionOutcomeCaptureService,
    ExecutionRequestRequest,
    ExecutionRequestService,
)
from decision.review import (
    HumanReviewPacketBuildRequest,
    HumanReviewPacketBuilder,
    ReviewResolutionRequest,
    ReviewResolutionService,
    ReviewTriggerRequest,
    ReviewTriggerService,
)
from decision.router.router_service import (
    RouterResolutionRequest,
    RouterService,
)
from state.lifecycle.state_model_registry import StateModelRegistry
from state.lifecycle.transition_validator import (
    InvalidTransitionError,
    TransitionBlockedError,
    TransitionEvaluation,
    TransitionValidationRequest,
    TransitionValidator,
)


@dataclass(frozen=True)
class StateInitializationResult:
    state_model_name: str
    current_state: str
    resulting_status: str
    route_name: str | None
    routing_review_required: bool
    review_outcome: str
    review_mode: str | None
    review_threshold_id: str | None
    review_playbook_reference: str | None
    review_packet_status: str | None
    review_packet_handoff_ready: bool | None
    review_packet_id: str | None
    review_packet_template_id: str | None
    review_packet_reason_class: str | None
    review_packet_scope: str | None
    review_packet_handoff_channel: str | None
    review_resolution_status: str | None
    review_resolution_id: str | None
    review_resolution_class_id: str | None
    review_resolution_outcome: str | None
    review_resolution_state: str | None
    review_disposition_class_id: str | None
    review_disposition_state: str | None
    review_closure_state: str | None
    review_closure_quality: str | None
    review_resolution_terminality: bool | None
    recommendation_status: str | None
    recommendation_id: str | None
    recommendation_class_id: str | None
    recommendation_template_id: str | None
    recommendation_action_class: str | None
    recommendation_advisory_status: str | None
    recommendation_commitment_readiness: str | None
    policy_output_status: str | None
    policy_output_id: str | None
    policy_output_class_id: str | None
    policy_output_template_id: str | None
    policy_output_bounded_policy_posture: str | None
    policy_output_action_boundary_posture: str | None
    policy_output_promotion_safe_use: str | None
    portfolio_output_status: str | None
    portfolio_output_id: str | None
    portfolio_output_class_id: str | None
    portfolio_output_template_id: str | None
    portfolio_output_allocation_posture: str | None
    portfolio_output_weight_posture: str | None
    portfolio_output_action_boundary_posture: str | None
    portfolio_output_promotion_safe_use: str | None
    action_instruction_status: str | None
    action_instruction_id: str | None
    action_instruction_class_id: str | None
    action_instruction_template_id: str | None
    action_instruction_instruction_status: str | None
    action_instruction_bounded_action_posture: str | None
    action_instruction_execution_boundary_posture: str | None
    action_instruction_promotion_safe_use: str | None
    execution_request_status: str | None
    execution_request_id: str | None
    execution_request_class_id: str | None
    execution_request_template_id: str | None
    execution_request_readiness: str | None
    execution_request_action_boundary_posture: str | None
    execution_dispatch_status: str | None
    execution_dispatch_id: str | None
    execution_dispatch_class_id: str | None
    execution_dispatch_template_id: str | None
    execution_dispatch_readiness: str | None
    execution_dispatch_boundary_posture: str | None
    execution_outcome_status: str | None
    execution_outcome_id: str | None
    execution_outcome_class_id: str | None
    execution_outcome_template_id: str | None
    execution_outcome_realized_result_class: str | None
    execution_outcome_feedback_capture_readiness: str | None
    execution_outcome_expected_relation: str | None
    execution_outcome_comparison_posture: str | None
    post_mortem_judgment_status: str | None
    post_mortem_judgment_id: str | None
    post_mortem_judgment_class_id: str | None
    post_mortem_judgment_template_id: str | None
    post_mortem_primary_attribution_category: str | None
    post_mortem_evidence_quality: str | None
    post_mortem_confidence_posture: str | None
    post_mortem_learning_direction: str | None
    post_mortem_comparison_posture: str | None
    policy_learning_evidence_admission_status: str | None
    policy_learning_evidence_admission_id: str | None
    policy_learning_evidence_class_id: str | None
    policy_learning_evidence_template_id: str | None
    policy_learning_evidence_admission_context: Mapping[str, object] | None
    policy_learning_update_threshold_status: str | None
    policy_learning_update_threshold_id: str | None
    policy_learning_update_threshold_class_id: str | None
    policy_learning_update_threshold_template_id: str | None
    policy_learning_update_threshold_context: Mapping[str, object] | None
    policy_learning_update_approval_status: str | None
    policy_learning_update_approval_class_id: str | None
    policy_learning_update_approval_context: Mapping[str, object] | None
    policy_learning_update_preparation_status: str | None
    policy_learning_update_preparation_class_id: str | None
    policy_learning_update_preparation_context: Mapping[str, object] | None
    policy_learning_update_mutation_planning_status: str | None
    policy_learning_update_mutation_planning_class_id: str | None
    policy_learning_update_mutation_planning_context: Mapping[str, object] | None
    policy_learning_update_mutation_execution_status: str | None
    policy_learning_update_mutation_execution_class_id: str | None
    policy_learning_update_mutation_execution_context: Mapping[str, object] | None
    promotion_readiness_status: str | None
    promotion_readiness_class_id: str | None
    promotion_readiness_context: Mapping[str, object] | None
    rollout_scope_status: str | None
    rollout_scope_class_id: str | None
    rollout_scope_context: Mapping[str, object] | None
    rollback_trigger_status: str | None
    rollback_trigger_class_id: str | None
    rollback_trigger_context: Mapping[str, object] | None
    release_watch_discipline_status: str | None
    release_watch_discipline_class_id: str | None
    release_watch_discipline_context: Mapping[str, object] | None
    release_confirmation_status: str | None
    release_confirmation_class_id: str | None
    release_confirmation_context: Mapping[str, object] | None
    production_entitlement_check_status: str | None
    production_entitlement_check_class_id: str | None
    production_entitlement_check_context: Mapping[str, object] | None
    contained_rollback_status: str | None
    contained_rollback_class_id: str | None
    contained_rollback_context: Mapping[str, object] | None
    release_audit_trace_status: str | None
    release_audit_trace_class_id: str | None
    release_audit_trace_context: Mapping[str, object] | None


@dataclass(frozen=True)
class CaseStateTransitionResult:
    transition_name: str
    from_state: str
    to_state: str
    transition_class: str
    resulting_status: str
    occurred_at_reason: str
    next_interruption_reason: str | None
    route_name: str | None
    routing_resolution_status: str
    routing_review_required: bool
    review_outcome: str
    review_mode: str | None
    review_threshold_id: str | None
    review_playbook_reference: str | None
    review_packet_status: str | None
    review_packet_handoff_ready: bool | None
    review_packet_id: str | None
    review_packet_template_id: str | None
    review_packet_reason_class: str | None
    review_packet_scope: str | None
    review_packet_handoff_channel: str | None
    review_resolution_status: str | None
    review_resolution_id: str | None
    review_resolution_class_id: str | None
    review_resolution_outcome: str | None
    review_resolution_state: str | None
    review_disposition_class_id: str | None
    review_disposition_state: str | None
    review_closure_state: str | None
    review_closure_quality: str | None
    review_resolution_terminality: bool | None
    recommendation_status: str | None
    recommendation_id: str | None
    recommendation_class_id: str | None
    recommendation_template_id: str | None
    recommendation_action_class: str | None
    recommendation_advisory_status: str | None
    recommendation_commitment_readiness: str | None
    policy_output_status: str | None
    policy_output_id: str | None
    policy_output_class_id: str | None
    policy_output_template_id: str | None
    policy_output_bounded_policy_posture: str | None
    policy_output_action_boundary_posture: str | None
    policy_output_promotion_safe_use: str | None
    portfolio_output_status: str | None
    portfolio_output_id: str | None
    portfolio_output_class_id: str | None
    portfolio_output_template_id: str | None
    portfolio_output_allocation_posture: str | None
    portfolio_output_weight_posture: str | None
    portfolio_output_action_boundary_posture: str | None
    portfolio_output_promotion_safe_use: str | None
    action_instruction_status: str | None
    action_instruction_id: str | None
    action_instruction_class_id: str | None
    action_instruction_template_id: str | None
    action_instruction_instruction_status: str | None
    action_instruction_bounded_action_posture: str | None
    action_instruction_execution_boundary_posture: str | None
    action_instruction_promotion_safe_use: str | None
    execution_request_status: str | None
    execution_request_id: str | None
    execution_request_class_id: str | None
    execution_request_template_id: str | None
    execution_request_readiness: str | None
    execution_request_action_boundary_posture: str | None
    execution_dispatch_status: str | None
    execution_dispatch_id: str | None
    execution_dispatch_class_id: str | None
    execution_dispatch_template_id: str | None
    execution_dispatch_readiness: str | None
    execution_dispatch_boundary_posture: str | None
    execution_outcome_status: str | None
    execution_outcome_id: str | None
    execution_outcome_class_id: str | None
    execution_outcome_template_id: str | None
    execution_outcome_realized_result_class: str | None
    execution_outcome_feedback_capture_readiness: str | None
    execution_outcome_expected_relation: str | None
    execution_outcome_comparison_posture: str | None
    post_mortem_judgment_status: str | None
    post_mortem_judgment_id: str | None
    post_mortem_judgment_class_id: str | None
    post_mortem_judgment_template_id: str | None
    post_mortem_primary_attribution_category: str | None
    post_mortem_evidence_quality: str | None
    post_mortem_confidence_posture: str | None
    post_mortem_learning_direction: str | None
    post_mortem_comparison_posture: str | None
    policy_learning_evidence_admission_status: str | None
    policy_learning_evidence_admission_id: str | None
    policy_learning_evidence_class_id: str | None
    policy_learning_evidence_template_id: str | None
    policy_learning_evidence_admission_context: Mapping[str, object] | None
    policy_learning_update_threshold_status: str | None
    policy_learning_update_threshold_id: str | None
    policy_learning_update_threshold_class_id: str | None
    policy_learning_update_threshold_template_id: str | None
    policy_learning_update_threshold_context: Mapping[str, object] | None
    policy_learning_update_approval_status: str | None
    policy_learning_update_approval_class_id: str | None
    policy_learning_update_approval_context: Mapping[str, object] | None
    policy_learning_update_preparation_status: str | None
    policy_learning_update_preparation_class_id: str | None
    policy_learning_update_preparation_context: Mapping[str, object] | None
    policy_learning_update_mutation_planning_status: str | None
    policy_learning_update_mutation_planning_class_id: str | None
    policy_learning_update_mutation_planning_context: Mapping[str, object] | None
    policy_learning_update_mutation_execution_status: str | None
    policy_learning_update_mutation_execution_class_id: str | None
    policy_learning_update_mutation_execution_context: Mapping[str, object] | None
    promotion_readiness_status: str | None
    promotion_readiness_class_id: str | None
    promotion_readiness_context: Mapping[str, object] | None
    rollout_scope_status: str | None
    rollout_scope_class_id: str | None
    rollout_scope_context: Mapping[str, object] | None
    rollback_trigger_status: str | None
    rollback_trigger_class_id: str | None
    rollback_trigger_context: Mapping[str, object] | None
    release_watch_discipline_status: str | None
    release_watch_discipline_class_id: str | None
    release_watch_discipline_context: Mapping[str, object] | None
    release_confirmation_status: str | None
    release_confirmation_class_id: str | None
    release_confirmation_context: Mapping[str, object] | None
    production_entitlement_check_status: str | None
    production_entitlement_check_class_id: str | None
    production_entitlement_check_context: Mapping[str, object] | None
    contained_rollback_status: str | None
    contained_rollback_class_id: str | None
    contained_rollback_context: Mapping[str, object] | None
    release_audit_trace_status: str | None
    release_audit_trace_class_id: str | None
    release_audit_trace_context: Mapping[str, object] | None


class CaseStateManager:
    """Coordinates validation, routing, and auditing for state changes."""

    def __init__(
        self,
        *,
        state_model_registry: StateModelRegistry,
        transition_validator: TransitionValidator,
        router_service: RouterService,
        review_trigger_service: ReviewTriggerService,
        human_review_packet_builder: HumanReviewPacketBuilder,
        review_resolution_service: ReviewResolutionService | None = None,
        recommendation_service: RecommendationService | None = None,
        policy_output_service: PolicyOutputService | None = None,
        portfolio_output_service: PortfolioOutputService | None = None,
        action_instruction_service: ActionInstructionService | None = None,
        execution_request_service: ExecutionRequestService | None = None,
        execution_dispatch_service: ExecutionDispatchBoundaryService | None = None,
        execution_outcome_service: ExecutionOutcomeCaptureService | None = None,
        post_mortem_judgment_service: PostMortemJudgmentService | None = None,
        policy_learning_evidence_admission_service: (
            PolicyLearningEvidenceAdmissionService | None
        ) = None,
        policy_learning_update_threshold_service: (
            PolicyLearningUpdateThresholdService | None
        ) = None,
        policy_learning_update_approval_service: (
            PolicyLearningUpdateApprovalService | None
        ) = None,
        policy_learning_update_preparation_service: (
            PolicyLearningUpdatePreparationService | None
        ) = None,
        policy_learning_update_mutation_planning_service: (
            PolicyLearningUpdateMutationPlanningService | None
        ) = None,
        policy_learning_update_mutation_execution_service: (
            PolicyLearningUpdateMutationExecutionService | None
        ) = None,
        promotion_readiness_gate: PromotionReadinessGate | None = None,
        rollout_scope_controller: RolloutScopeController | None = None,
        rollback_trigger_guard: RollbackTriggerGuard | None = None,
        release_watch_discipline: ReleaseWatchDiscipline | None = None,
        release_confirmation: ReleaseConfirmation | None = None,
        production_entitlement_check: ProductionEntitlementCheck | None = None,
        contained_rollback: ContainedRollback | None = None,
        release_audit_trace: ReleaseAuditTrace | None = None,
        transition_audit_adapter: CaseTransitionAuditAdapter,
    ) -> None:
        self._state_model_registry = state_model_registry
        self._transition_validator = transition_validator
        self._router_service = router_service
        self._review_trigger_service = review_trigger_service
        self._human_review_packet_builder = human_review_packet_builder
        self._review_resolution_service = review_resolution_service
        self._recommendation_service = recommendation_service
        self._policy_output_service = policy_output_service
        self._portfolio_output_service = portfolio_output_service
        self._action_instruction_service = action_instruction_service
        self._execution_request_service = execution_request_service
        self._execution_dispatch_service = execution_dispatch_service
        self._execution_outcome_service = execution_outcome_service
        self._post_mortem_judgment_service = post_mortem_judgment_service
        self._policy_learning_evidence_admission_service = (
            policy_learning_evidence_admission_service
        )
        self._policy_learning_update_threshold_service = (
            policy_learning_update_threshold_service
        )
        self._policy_learning_update_approval_service = (
            policy_learning_update_approval_service
        )
        self._policy_learning_update_preparation_service = (
            policy_learning_update_preparation_service
        )
        self._policy_learning_update_mutation_planning_service = (
            policy_learning_update_mutation_planning_service
        )
        self._policy_learning_update_mutation_execution_service = (
            policy_learning_update_mutation_execution_service
        )
        self._promotion_readiness_gate = promotion_readiness_gate
        self._rollout_scope_controller = rollout_scope_controller
        self._rollback_trigger_guard = rollback_trigger_guard
        self._release_watch_discipline = release_watch_discipline
        self._release_confirmation = release_confirmation
        self._production_entitlement_check = production_entitlement_check
        self._contained_rollback = contained_rollback
        self._release_audit_trace = release_audit_trace
        self._transition_audit_adapter = transition_audit_adapter

    def initialize_case_state(
        self,
        *,
        case_type: str,
        case_key: str,
        state_model_name: str,
        correlation_id: str,
        episode_id: str,
        actor_id: str,
        actor_role: str,
        route_target_stage: str,
        threshold_context: Mapping[str, object] | None,
        packet_context: Mapping[str, object] | None,
        reason: str,
        review_resolution_class_id: str | None = None,
        review_resolution_context: Mapping[str, object] | None = None,
        recommendation_class_id: str | None = None,
        recommendation_context: Mapping[str, object] | None = None,
        policy_output_class_id: str | None = None,
        policy_output_context: Mapping[str, object] | None = None,
        portfolio_output_class_id: str | None = None,
        portfolio_output_context: Mapping[str, object] | None = None,
        action_instruction_class_id: str | None = None,
        action_instruction_context: Mapping[str, object] | None = None,
        execution_request_class_id: str | None = None,
        execution_request_context: Mapping[str, object] | None = None,
        execution_dispatch_class_id: str | None = None,
        execution_dispatch_context: Mapping[str, object] | None = None,
        execution_outcome_class_id: str | None = None,
        execution_outcome_context: Mapping[str, object] | None = None,
        post_mortem_judgment_class_id: str | None = None,
        post_mortem_judgment_context: Mapping[str, object] | None = None,
        policy_learning_evidence_class_id: str | None = None,
        policy_learning_evidence_admission_context: Mapping[str, object] | None = None,
        policy_learning_update_threshold_class_id: str | None = None,
        policy_learning_update_threshold_context: Mapping[str, object] | None = None,
        policy_learning_update_approval_class_id: str | None = None,
        policy_learning_update_approval_context: Mapping[str, object] | None = None,
        policy_learning_update_preparation_class_id: str | None = None,
        policy_learning_update_preparation_context: Mapping[str, object] | None = None,
        policy_learning_update_mutation_planning_class_id: str | None = None,
        policy_learning_update_mutation_planning_context: Mapping[str, object] | None = None,
        policy_learning_update_mutation_execution_class_id: str | None = None,
        policy_learning_update_mutation_execution_context: Mapping[str, object] | None = None,
        promotion_readiness_class_id: str | None = None,
        promotion_readiness_context: Mapping[str, object] | None = None,
        rollout_scope_class_id: str | None = None,
        rollout_scope_context: Mapping[str, object] | None = None,
        rollback_trigger_class_id: str | None = None,
        rollback_trigger_context: Mapping[str, object] | None = None,
        release_watch_discipline_class_id: str | None = None,
        release_watch_discipline_context: Mapping[str, object] | None = None,
        release_confirmation_class_id: str | None = None,
        release_confirmation_context: Mapping[str, object] | None = None,
        production_entitlement_check_class_id: str | None = None,
        production_entitlement_check_context: Mapping[str, object] | None = None,
        contained_rollback_class_id: str | None = None,
        contained_rollback_context: Mapping[str, object] | None = None,
        release_audit_trace_class_id: str | None = None,
        release_audit_trace_context: Mapping[str, object] | None = None,
    ) -> StateInitializationResult:
        model = self._state_model_registry.get_state_model(state_model_name)
        transition_result = self.apply_transition(
            case_type=case_type,
            case_key=case_key,
            state_model_name=state_model_name,
            current_state="__entry__",
            current_status="active",
            transition_name=model.entry_transition_name,
            source_stage="__entry__",
            target_stage=route_target_stage,
            correlation_id=correlation_id,
            episode_id=episode_id,
            actor_id=actor_id,
            actor_role=actor_role,
            threshold_context=threshold_context,
            packet_context=packet_context,
            reason=reason,
            review_resolution_class_id=review_resolution_class_id,
            review_resolution_context=review_resolution_context,
            recommendation_class_id=recommendation_class_id,
            recommendation_context=recommendation_context,
            policy_output_class_id=policy_output_class_id,
            policy_output_context=policy_output_context,
            portfolio_output_class_id=portfolio_output_class_id,
            portfolio_output_context=portfolio_output_context,
            action_instruction_class_id=action_instruction_class_id,
            action_instruction_context=action_instruction_context,
            execution_request_class_id=execution_request_class_id,
            execution_request_context=execution_request_context,
            execution_dispatch_class_id=execution_dispatch_class_id,
            execution_dispatch_context=execution_dispatch_context,
            execution_outcome_class_id=execution_outcome_class_id,
            execution_outcome_context=execution_outcome_context,
            post_mortem_judgment_class_id=post_mortem_judgment_class_id,
            post_mortem_judgment_context=post_mortem_judgment_context,
            policy_learning_evidence_class_id=policy_learning_evidence_class_id,
            policy_learning_evidence_admission_context=(
                policy_learning_evidence_admission_context
            ),
            policy_learning_update_threshold_class_id=(
                policy_learning_update_threshold_class_id
            ),
            policy_learning_update_threshold_context=(
                policy_learning_update_threshold_context
            ),
            policy_learning_update_approval_class_id=(
                policy_learning_update_approval_class_id
            ),
            policy_learning_update_approval_context=(
                policy_learning_update_approval_context
            ),
            policy_learning_update_preparation_class_id=(
                policy_learning_update_preparation_class_id
            ),
            policy_learning_update_preparation_context=(
                policy_learning_update_preparation_context
            ),
            policy_learning_update_mutation_planning_class_id=(
                policy_learning_update_mutation_planning_class_id
            ),
            policy_learning_update_mutation_planning_context=(
                policy_learning_update_mutation_planning_context
            ),
            policy_learning_update_mutation_execution_class_id=(
                policy_learning_update_mutation_execution_class_id
            ),
            policy_learning_update_mutation_execution_context=(
                policy_learning_update_mutation_execution_context
            ),
            promotion_readiness_class_id=promotion_readiness_class_id,
            promotion_readiness_context=promotion_readiness_context,
            rollout_scope_class_id=rollout_scope_class_id,
            rollout_scope_context=rollout_scope_context,
            rollback_trigger_class_id=rollback_trigger_class_id,
            rollback_trigger_context=rollback_trigger_context,
            release_watch_discipline_class_id=release_watch_discipline_class_id,
            release_watch_discipline_context=release_watch_discipline_context,
            release_confirmation_class_id=release_confirmation_class_id,
            release_confirmation_context=release_confirmation_context,
            production_entitlement_check_class_id=(
                production_entitlement_check_class_id
            ),
            production_entitlement_check_context=production_entitlement_check_context,
            contained_rollback_class_id=contained_rollback_class_id,
            contained_rollback_context=contained_rollback_context,
            release_audit_trace_class_id=release_audit_trace_class_id,
            release_audit_trace_context=release_audit_trace_context,
        )
        return StateInitializationResult(
            state_model_name=state_model_name,
            current_state=transition_result.to_state,
            resulting_status=transition_result.resulting_status,
            route_name=transition_result.route_name,
            routing_review_required=transition_result.routing_review_required,
            review_outcome=transition_result.review_outcome,
            review_mode=transition_result.review_mode,
            review_threshold_id=transition_result.review_threshold_id,
            review_playbook_reference=transition_result.review_playbook_reference,
            review_packet_status=transition_result.review_packet_status,
            review_packet_handoff_ready=transition_result.review_packet_handoff_ready,
            review_packet_id=transition_result.review_packet_id,
            review_packet_template_id=transition_result.review_packet_template_id,
            review_packet_reason_class=transition_result.review_packet_reason_class,
            review_packet_scope=transition_result.review_packet_scope,
            review_packet_handoff_channel=transition_result.review_packet_handoff_channel,
            review_resolution_status=transition_result.review_resolution_status,
            review_resolution_id=transition_result.review_resolution_id,
            review_resolution_class_id=transition_result.review_resolution_class_id,
            review_resolution_outcome=transition_result.review_resolution_outcome,
            review_resolution_state=transition_result.review_resolution_state,
            review_disposition_class_id=transition_result.review_disposition_class_id,
            review_disposition_state=transition_result.review_disposition_state,
            review_closure_state=transition_result.review_closure_state,
            review_closure_quality=transition_result.review_closure_quality,
            review_resolution_terminality=transition_result.review_resolution_terminality,
            recommendation_status=transition_result.recommendation_status,
            recommendation_id=transition_result.recommendation_id,
            recommendation_class_id=transition_result.recommendation_class_id,
            recommendation_template_id=transition_result.recommendation_template_id,
            recommendation_action_class=transition_result.recommendation_action_class,
            recommendation_advisory_status=transition_result.recommendation_advisory_status,
            recommendation_commitment_readiness=(
                transition_result.recommendation_commitment_readiness
            ),
            policy_output_status=transition_result.policy_output_status,
            policy_output_id=transition_result.policy_output_id,
            policy_output_class_id=transition_result.policy_output_class_id,
            policy_output_template_id=transition_result.policy_output_template_id,
            policy_output_bounded_policy_posture=(
                transition_result.policy_output_bounded_policy_posture
            ),
            policy_output_action_boundary_posture=(
                transition_result.policy_output_action_boundary_posture
            ),
            policy_output_promotion_safe_use=(
                transition_result.policy_output_promotion_safe_use
            ),
            portfolio_output_status=transition_result.portfolio_output_status,
            portfolio_output_id=transition_result.portfolio_output_id,
            portfolio_output_class_id=transition_result.portfolio_output_class_id,
            portfolio_output_template_id=transition_result.portfolio_output_template_id,
            portfolio_output_allocation_posture=(
                transition_result.portfolio_output_allocation_posture
            ),
            portfolio_output_weight_posture=(
                transition_result.portfolio_output_weight_posture
            ),
            portfolio_output_action_boundary_posture=(
                transition_result.portfolio_output_action_boundary_posture
            ),
            portfolio_output_promotion_safe_use=(
                transition_result.portfolio_output_promotion_safe_use
            ),
            action_instruction_status=transition_result.action_instruction_status,
            action_instruction_id=transition_result.action_instruction_id,
            action_instruction_class_id=transition_result.action_instruction_class_id,
            action_instruction_template_id=(
                transition_result.action_instruction_template_id
            ),
            action_instruction_instruction_status=(
                transition_result.action_instruction_instruction_status
            ),
            action_instruction_bounded_action_posture=(
                transition_result.action_instruction_bounded_action_posture
            ),
            action_instruction_execution_boundary_posture=(
                transition_result.action_instruction_execution_boundary_posture
            ),
            action_instruction_promotion_safe_use=(
                transition_result.action_instruction_promotion_safe_use
            ),
            execution_request_status=transition_result.execution_request_status,
            execution_request_id=transition_result.execution_request_id,
            execution_request_class_id=transition_result.execution_request_class_id,
            execution_request_template_id=(
                transition_result.execution_request_template_id
            ),
            execution_request_readiness=(
                transition_result.execution_request_readiness
            ),
            execution_request_action_boundary_posture=(
                transition_result.execution_request_action_boundary_posture
            ),
            execution_dispatch_status=transition_result.execution_dispatch_status,
            execution_dispatch_id=transition_result.execution_dispatch_id,
            execution_dispatch_class_id=(
                transition_result.execution_dispatch_class_id
            ),
            execution_dispatch_template_id=(
                transition_result.execution_dispatch_template_id
            ),
            execution_dispatch_readiness=(
                transition_result.execution_dispatch_readiness
            ),
            execution_dispatch_boundary_posture=(
                transition_result.execution_dispatch_boundary_posture
            ),
            execution_outcome_status=transition_result.execution_outcome_status,
            execution_outcome_id=transition_result.execution_outcome_id,
            execution_outcome_class_id=transition_result.execution_outcome_class_id,
            execution_outcome_template_id=(
                transition_result.execution_outcome_template_id
            ),
            execution_outcome_realized_result_class=(
                transition_result.execution_outcome_realized_result_class
            ),
            execution_outcome_feedback_capture_readiness=(
                transition_result.execution_outcome_feedback_capture_readiness
            ),
            execution_outcome_expected_relation=(
                transition_result.execution_outcome_expected_relation
            ),
            execution_outcome_comparison_posture=(
                transition_result.execution_outcome_comparison_posture
            ),
            post_mortem_judgment_status=(
                transition_result.post_mortem_judgment_status
            ),
            post_mortem_judgment_id=transition_result.post_mortem_judgment_id,
            post_mortem_judgment_class_id=(
                transition_result.post_mortem_judgment_class_id
            ),
            post_mortem_judgment_template_id=(
                transition_result.post_mortem_judgment_template_id
            ),
            post_mortem_primary_attribution_category=(
                transition_result.post_mortem_primary_attribution_category
            ),
            post_mortem_evidence_quality=(
                transition_result.post_mortem_evidence_quality
            ),
            post_mortem_confidence_posture=(
                transition_result.post_mortem_confidence_posture
            ),
            post_mortem_learning_direction=(
                transition_result.post_mortem_learning_direction
            ),
            post_mortem_comparison_posture=(
                transition_result.post_mortem_comparison_posture
            ),
            policy_learning_evidence_admission_status=(
                transition_result.policy_learning_evidence_admission_status
            ),
            policy_learning_evidence_admission_id=(
                transition_result.policy_learning_evidence_admission_id
            ),
            policy_learning_evidence_class_id=(
                transition_result.policy_learning_evidence_class_id
            ),
            policy_learning_evidence_template_id=(
                transition_result.policy_learning_evidence_template_id
            ),
            policy_learning_evidence_admission_context=(
                transition_result.policy_learning_evidence_admission_context
            ),
            policy_learning_update_threshold_status=(
                transition_result.policy_learning_update_threshold_status
            ),
            policy_learning_update_threshold_id=(
                transition_result.policy_learning_update_threshold_id
            ),
            policy_learning_update_threshold_class_id=(
                transition_result.policy_learning_update_threshold_class_id
            ),
            policy_learning_update_threshold_template_id=(
                transition_result.policy_learning_update_threshold_template_id
            ),
            policy_learning_update_threshold_context=(
                transition_result.policy_learning_update_threshold_context
            ),
            policy_learning_update_approval_status=(
                transition_result.policy_learning_update_approval_status
            ),
            policy_learning_update_approval_class_id=(
                transition_result.policy_learning_update_approval_class_id
            ),
            policy_learning_update_approval_context=(
                transition_result.policy_learning_update_approval_context
            ),
            policy_learning_update_preparation_status=(
                transition_result.policy_learning_update_preparation_status
            ),
            policy_learning_update_preparation_class_id=(
                transition_result.policy_learning_update_preparation_class_id
            ),
            policy_learning_update_preparation_context=(
                transition_result.policy_learning_update_preparation_context
            ),
            policy_learning_update_mutation_planning_status=(
                transition_result.policy_learning_update_mutation_planning_status
            ),
            policy_learning_update_mutation_planning_class_id=(
                transition_result.policy_learning_update_mutation_planning_class_id
            ),
            policy_learning_update_mutation_planning_context=(
                transition_result.policy_learning_update_mutation_planning_context
            ),
            policy_learning_update_mutation_execution_status=(
                transition_result.policy_learning_update_mutation_execution_status
            ),
            policy_learning_update_mutation_execution_class_id=(
                transition_result.policy_learning_update_mutation_execution_class_id
            ),
            policy_learning_update_mutation_execution_context=(
                transition_result.policy_learning_update_mutation_execution_context
            ),
            promotion_readiness_status=transition_result.promotion_readiness_status,
            promotion_readiness_class_id=(
                transition_result.promotion_readiness_class_id
            ),
            promotion_readiness_context=transition_result.promotion_readiness_context,
            rollout_scope_status=transition_result.rollout_scope_status,
            rollout_scope_class_id=transition_result.rollout_scope_class_id,
            rollout_scope_context=transition_result.rollout_scope_context,
            rollback_trigger_status=transition_result.rollback_trigger_status,
            rollback_trigger_class_id=transition_result.rollback_trigger_class_id,
            rollback_trigger_context=transition_result.rollback_trigger_context,
            release_watch_discipline_status=(
                transition_result.release_watch_discipline_status
            ),
            release_watch_discipline_class_id=(
                transition_result.release_watch_discipline_class_id
            ),
            release_watch_discipline_context=(
                transition_result.release_watch_discipline_context
            ),
            release_confirmation_status=transition_result.release_confirmation_status,
            release_confirmation_class_id=(
                transition_result.release_confirmation_class_id
            ),
            release_confirmation_context=transition_result.release_confirmation_context,
            production_entitlement_check_status=(
                transition_result.production_entitlement_check_status
            ),
            production_entitlement_check_class_id=(
                transition_result.production_entitlement_check_class_id
            ),
            production_entitlement_check_context=(
                transition_result.production_entitlement_check_context
            ),
            contained_rollback_status=transition_result.contained_rollback_status,
            contained_rollback_class_id=(
                transition_result.contained_rollback_class_id
            ),
            contained_rollback_context=transition_result.contained_rollback_context,
            release_audit_trace_status=transition_result.release_audit_trace_status,
            release_audit_trace_class_id=(
                transition_result.release_audit_trace_class_id
            ),
            release_audit_trace_context=(
                transition_result.release_audit_trace_context
            ),
        )

    def apply_transition(
        self,
        *,
        case_type: str,
        case_key: str,
        state_model_name: str,
        current_state: str,
        current_status: str,
        transition_name: str,
        source_stage: str,
        target_stage: str,
        correlation_id: str,
        episode_id: str,
        actor_id: str,
        actor_role: str,
        threshold_context: Mapping[str, object] | None = None,
        packet_context: Mapping[str, object] | None = None,
        reason: str,
        review_resolution_class_id: str | None = None,
        review_resolution_context: Mapping[str, object] | None = None,
        recommendation_class_id: str | None = None,
        recommendation_context: Mapping[str, object] | None = None,
        policy_output_class_id: str | None = None,
        policy_output_context: Mapping[str, object] | None = None,
        portfolio_output_class_id: str | None = None,
        portfolio_output_context: Mapping[str, object] | None = None,
        action_instruction_class_id: str | None = None,
        action_instruction_context: Mapping[str, object] | None = None,
        execution_request_class_id: str | None = None,
        execution_request_context: Mapping[str, object] | None = None,
        execution_dispatch_class_id: str | None = None,
        execution_dispatch_context: Mapping[str, object] | None = None,
        execution_outcome_class_id: str | None = None,
        execution_outcome_context: Mapping[str, object] | None = None,
        post_mortem_judgment_class_id: str | None = None,
        post_mortem_judgment_context: Mapping[str, object] | None = None,
        policy_learning_evidence_class_id: str | None = None,
        policy_learning_evidence_admission_context: Mapping[str, object] | None = None,
        policy_learning_update_threshold_class_id: str | None = None,
        policy_learning_update_threshold_context: Mapping[str, object] | None = None,
        policy_learning_update_approval_class_id: str | None = None,
        policy_learning_update_approval_context: Mapping[str, object] | None = None,
        policy_learning_update_preparation_class_id: str | None = None,
        policy_learning_update_preparation_context: Mapping[str, object] | None = None,
        policy_learning_update_mutation_planning_class_id: str | None = None,
        policy_learning_update_mutation_planning_context: Mapping[str, object] | None = None,
        policy_learning_update_mutation_execution_class_id: str | None = None,
        policy_learning_update_mutation_execution_context: Mapping[str, object] | None = None,
        promotion_readiness_class_id: str | None = None,
        promotion_readiness_context: Mapping[str, object] | None = None,
        rollout_scope_class_id: str | None = None,
        rollout_scope_context: Mapping[str, object] | None = None,
        rollback_trigger_class_id: str | None = None,
        rollback_trigger_context: Mapping[str, object] | None = None,
        release_watch_discipline_class_id: str | None = None,
        release_watch_discipline_context: Mapping[str, object] | None = None,
        release_confirmation_class_id: str | None = None,
        release_confirmation_context: Mapping[str, object] | None = None,
        production_entitlement_check_class_id: str | None = None,
        production_entitlement_check_context: Mapping[str, object] | None = None,
        contained_rollback_class_id: str | None = None,
        contained_rollback_context: Mapping[str, object] | None = None,
        release_audit_trace_class_id: str | None = None,
        release_audit_trace_context: Mapping[str, object] | None = None,
    ) -> CaseStateTransitionResult:
        request = TransitionValidationRequest(
            case_type=case_type,
            state_model_name=state_model_name,
            current_state=current_state,
            current_status=current_status,
            transition_name=transition_name,
            actor_role=actor_role,
            correlation_id=correlation_id,
            episode_id=episode_id,
            actor_id=actor_id,
        )
        model = self._state_model_registry.get_state_model(state_model_name)
        review_packet = None
        review_resolution = None
        recommendation = None
        policy_output = None
        portfolio_output = None
        action_instruction = None
        execution_request = None
        execution_dispatch = None
        execution_outcome = None
        post_mortem_judgment = None
        policy_learning_evidence_admission = None
        policy_learning_update_threshold = None
        policy_learning_update_approval = None
        policy_learning_update_preparation = None
        policy_learning_update_mutation_planning = None
        policy_learning_update_mutation_execution = None
        promotion_readiness = None
        rollout_scope = None
        rollback_trigger = None
        release_watch_discipline = None
        release_confirmation = None
        production_entitlement_check = None
        contained_rollback = None
        release_audit_trace = None
        try:
            evaluation = self._transition_validator.validate_transition(request)
            router_resolution = self._router_service.resolve(
                RouterResolutionRequest(
                    router_rule_id=evaluation.router_rule_id,
                    semantic_scope=model.semantic_scope,
                    state_model_name=state_model_name,
                    transition_name=transition_name,
                    transition_class=evaluation.transition_class,
                    source_stage=source_stage,
                    target_stage=target_stage,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                )
            )
            review_decision = self._review_trigger_service.evaluate(
                ReviewTriggerRequest(
                    semantic_scope=model.semantic_scope,
                    state_model_name=state_model_name,
                    transition_name=transition_name,
                    transition_class=evaluation.transition_class,
                    source_stage=source_stage,
                    target_stage=target_stage,
                    actor_role=actor_role,
                    authority_resolution_kind=evaluation.authority_resolution_kind,
                    authority_review_required=evaluation.review_required,
                    router_rule_id=router_resolution.router_rule_id,
                    route_name=router_resolution.route_name,
                    routing_resolution_status=router_resolution.resolution_status,
                    routing_conflict_class=router_resolution.conflict_class,
                    routing_candidate_count=router_resolution.candidate_count,
                    routing_review_required=router_resolution.review_required,
                    decision_context=dict(threshold_context or {}),
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                )
            )
            if review_decision.requires_packet():
                review_packet = self._human_review_packet_builder.build(
                    HumanReviewPacketBuildRequest(
                        semantic_scope=model.semantic_scope,
                        case_type=case_type,
                        case_key=case_key,
                        state_model_name=state_model_name,
                        episode_id=episode_id,
                        transition_name=transition_name,
                        transition_class=evaluation.transition_class,
                        source_stage=source_stage,
                        target_stage=target_stage,
                        actor_role=actor_role,
                        authority_resolution_kind=evaluation.authority_resolution_kind,
                        authority_review_required=evaluation.review_required,
                        router_rule_id=router_resolution.router_rule_id,
                        route_name=router_resolution.route_name,
                        routing_resolution_status=router_resolution.resolution_status,
                        routing_review_required=router_resolution.review_required,
                        review_decision=review_decision,
                        packet_context=dict(packet_context or {}),
                        correlation_id=correlation_id,
                        actor_id=actor_id,
                    )
                )
        except InvalidTransitionError as error:
            self._transition_audit_adapter.record_transition_outcome(
                error.evaluation,
                correlation_id=correlation_id,
                episode_id=episode_id,
                actor_id=actor_id,
                reason=reason,
            )
            raise
        except TransitionBlockedError as error:
            self._transition_audit_adapter.record_transition_outcome(
                error.evaluation,
                correlation_id=correlation_id,
                episode_id=episode_id,
                actor_id=actor_id,
                reason=reason,
            )
            raise

        if not router_resolution.accepted:
            self._raise_blocked_transition(
                evaluation=evaluation,
                blocked_reason=router_resolution.reason,
                current_status=current_status,
                correlation_id=correlation_id,
                episode_id=episode_id,
                actor_id=actor_id,
                reason=reason,
                router_resolution=router_resolution,
            )

        if review_decision.outcome_kind == "blocked":
            self._raise_blocked_transition(
                evaluation=evaluation,
                blocked_reason=review_decision.reason,
                current_status=current_status,
                correlation_id=correlation_id,
                episode_id=episode_id,
                actor_id=actor_id,
                reason=reason,
                router_resolution=router_resolution,
            )

        if review_packet is not None and review_packet.packet_status == "blocked":
            self._raise_blocked_transition(
                evaluation=evaluation,
                blocked_reason=review_packet.reason,
                current_status=current_status,
                correlation_id=correlation_id,
                episode_id=episode_id,
                actor_id=actor_id,
                reason=reason,
                router_resolution=router_resolution,
            )

        if review_resolution_class_id is not None:
            if self._review_resolution_service is None:
                raise RuntimeError("Review resolution service is not configured.")
            if review_packet is None:
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason="Review resolution requires a governed human review packet.",
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )
            review_resolution = self._review_resolution_service.resolve(
                ReviewResolutionRequest(
                    packet=review_packet,
                    resolution_class_id=review_resolution_class_id,
                    reviewer_role=actor_role,
                    resolution_context=dict(review_resolution_context or {}),
                    correlation_id=correlation_id,
                    actor_id=actor_id,
                )
            )
            if review_resolution.resolution_status == "blocked":
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=review_resolution.reason,
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )

        if recommendation_class_id is not None:
            if self._recommendation_service is None:
                raise RuntimeError("Recommendation service is not configured.")
            if review_resolution is None:
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason="Recommendation generation requires a governed review resolution.",
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )
            recommendation = self._recommendation_service.recommend(
                RecommendationRequest(
                    review_resolution=review_resolution,
                    recommendation_class_id=recommendation_class_id,
                    recommender_role=actor_role,
                    recommendation_context=dict(recommendation_context or {}),
                    correlation_id=correlation_id,
                    actor_id=actor_id,
                )
            )
            if recommendation.recommendation_status == "blocked":
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=recommendation.reason,
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )

        if policy_output_class_id is not None:
            if self._policy_output_service is None:
                raise RuntimeError("Policy output service is not configured.")
            if recommendation is None:
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason="Policy output generation requires a governed recommendation record.",
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )
            policy_output = self._policy_output_service.generate(
                PolicyOutputRequest(
                    recommendation=recommendation,
                    policy_output_class_id=policy_output_class_id,
                    policy_author_role=actor_role,
                    policy_output_context=dict(policy_output_context or {}),
                    correlation_id=correlation_id,
                    actor_id=actor_id,
                )
            )
            if policy_output.policy_output_status == "blocked":
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=policy_output.reason,
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )

        if portfolio_output_class_id is not None:
            if self._portfolio_output_service is None:
                raise RuntimeError("Portfolio output service is not configured.")
            if policy_output is None:
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=(
                        "Portfolio output generation requires a governed policy output record."
                    ),
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )
            portfolio_output = self._portfolio_output_service.generate(
                PortfolioOutputRequest(
                    policy_output=policy_output,
                    portfolio_output_class_id=portfolio_output_class_id,
                    portfolio_author_role=actor_role,
                    portfolio_output_context=dict(portfolio_output_context or {}),
                    correlation_id=correlation_id,
                    actor_id=actor_id,
                )
            )
            if portfolio_output.portfolio_output_status == "blocked":
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=portfolio_output.reason,
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )

        if action_instruction_class_id is not None:
            if self._action_instruction_service is None:
                raise RuntimeError("Action instruction service is not configured.")
            if portfolio_output is None:
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=(
                        "Action instruction generation requires a governed portfolio output record."
                    ),
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )
            action_instruction = self._action_instruction_service.generate(
                ActionInstructionRequest(
                    portfolio_output=portfolio_output,
                    action_instruction_class_id=action_instruction_class_id,
                    instruction_author_role=actor_role,
                    action_instruction_context=dict(action_instruction_context or {}),
                    correlation_id=correlation_id,
                    actor_id=actor_id,
                )
            )
            if action_instruction.action_instruction_status == "blocked":
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=action_instruction.reason,
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )

        if execution_request_class_id is not None:
            if self._execution_request_service is None:
                raise RuntimeError("Execution request service is not configured.")
            if action_instruction is None:
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=(
                        "Execution request generation requires a governed action instruction record."
                    ),
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )
            execution_request = self._execution_request_service.generate(
                ExecutionRequestRequest(
                    action_instruction=action_instruction,
                    execution_request_class_id=execution_request_class_id,
                    execution_request_author_role=actor_role,
                    execution_request_context=dict(execution_request_context or {}),
                    correlation_id=correlation_id,
                    actor_id=actor_id,
                )
            )
            if execution_request.execution_request_status == "blocked":
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=execution_request.reason,
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )

        if execution_dispatch_class_id is not None:
            if self._execution_dispatch_service is None:
                raise RuntimeError("Execution dispatch service is not configured.")
            if execution_request is None:
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=(
                        "Execution dispatch generation requires a governed execution request record."
                    ),
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )
            execution_dispatch = self._execution_dispatch_service.generate(
                ExecutionDispatchBoundaryRequest(
                    execution_request=execution_request,
                    execution_dispatch_class_id=execution_dispatch_class_id,
                    execution_dispatch_author_role=actor_role,
                    execution_dispatch_context=dict(execution_dispatch_context or {}),
                    correlation_id=correlation_id,
                    actor_id=actor_id,
                )
            )
            if execution_dispatch.execution_dispatch_status == "blocked":
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=execution_dispatch.reason,
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )

        if execution_outcome_class_id is not None:
            if self._execution_outcome_service is None:
                raise RuntimeError("Execution outcome service is not configured.")
            if execution_dispatch is None:
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=(
                        "Execution outcome capture requires a governed execution dispatch boundary record."
                    ),
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )
            execution_outcome = self._execution_outcome_service.generate(
                ExecutionOutcomeCaptureRequest(
                    execution_dispatch=execution_dispatch,
                    execution_outcome_class_id=execution_outcome_class_id,
                    execution_outcome_author_role=actor_role,
                    execution_outcome_context=dict(execution_outcome_context or {}),
                    correlation_id=correlation_id,
                    actor_id=actor_id,
                )
            )
            if execution_outcome.execution_outcome_status == "blocked":
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=execution_outcome.reason,
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )

        if post_mortem_judgment_class_id is not None:
            if self._post_mortem_judgment_service is None:
                raise RuntimeError("Post-mortem judgment service is not configured.")
            if execution_outcome is None:
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=(
                        "Post-mortem judgment requires a governed execution outcome record."
                    ),
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )
            post_mortem_judgment = self._post_mortem_judgment_service.generate(
                PostMortemJudgmentRequest(
                    execution_outcome=execution_outcome,
                    post_mortem_judgment_class_id=post_mortem_judgment_class_id,
                    post_mortem_author_role=actor_role,
                    post_mortem_context=dict(post_mortem_judgment_context or {}),
                    correlation_id=correlation_id,
                    actor_id=actor_id,
                )
            )
            if post_mortem_judgment.post_mortem_status == "blocked":
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=post_mortem_judgment.reason,
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )

        if policy_learning_evidence_class_id is not None:
            if self._policy_learning_evidence_admission_service is None:
                raise RuntimeError(
                    "Policy-learning evidence admission service is not configured."
                )
            if post_mortem_judgment is None:
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=(
                        "Policy-learning evidence admission requires a governed "
                        "post-mortem judgment record."
                    ),
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )
            policy_learning_evidence_admission = (
                self._policy_learning_evidence_admission_service.generate(
                    PolicyLearningEvidenceAdmissionRequest(
                        post_mortem_judgment=post_mortem_judgment,
                        policy_learning_evidence_class_id=(
                            policy_learning_evidence_class_id
                        ),
                        policy_learning_evidence_author_role=actor_role,
                        policy_learning_evidence_admission_context=dict(
                            policy_learning_evidence_admission_context or {}
                        ),
                        correlation_id=correlation_id,
                        actor_id=actor_id,
                    )
                )
            )
            if (
                policy_learning_evidence_admission.policy_learning_evidence_admission_status
                in {
                    "blocked_missing_context",
                    "blocked_insufficient_evidence",
                    "prohibited_overlap_blocked",
                }
            ):
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=policy_learning_evidence_admission.reason,
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )

        if policy_learning_update_threshold_class_id is not None:
            if self._policy_learning_update_threshold_service is None:
                raise RuntimeError(
                    "Policy-learning update-threshold service is not configured."
                )
            if policy_learning_evidence_admission is None:
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=(
                        "Policy-learning update-threshold review requires a governed "
                        "policy-learning evidence-admission record."
                    ),
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )
            policy_learning_update_threshold = (
                self._policy_learning_update_threshold_service.generate(
                    PolicyLearningUpdateThresholdRequest(
                        policy_learning_evidence_admission=(
                            policy_learning_evidence_admission
                        ),
                        policy_learning_update_threshold_class_id=(
                            policy_learning_update_threshold_class_id
                        ),
                        policy_learning_update_threshold_author_role=actor_role,
                        policy_learning_update_threshold_context=dict(
                            policy_learning_update_threshold_context or {}
                        ),
                        correlation_id=correlation_id,
                        actor_id=actor_id,
                    )
                )
            )
            if (
                policy_learning_update_threshold.policy_learning_update_threshold_status
                in {
                    "blocked_missing_context",
                    "blocked_below_threshold",
                    "prohibited_overlap_blocked",
                }
            ):
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=policy_learning_update_threshold.reason,
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )

        if policy_learning_update_approval_class_id is not None:
            if self._policy_learning_update_approval_service is None:
                raise RuntimeError(
                    "Policy-learning update-approval service is not configured."
                )
            if policy_learning_update_threshold is None:
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=(
                        "Policy-learning update approval requires a governed "
                        "policy-learning update-threshold record."
                    ),
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )

            policy_learning_update_approval = (
                self._policy_learning_update_approval_service.generate(
                    PolicyLearningUpdateApprovalRequest(
                        policy_learning_update_threshold=(
                            policy_learning_update_threshold
                        ),
                        policy_learning_update_approval_class_id=(
                            policy_learning_update_approval_class_id
                        ),
                        policy_learning_update_approval_author_role=actor_role,
                        policy_learning_update_approval_context=dict(
                            policy_learning_update_approval_context or {}
                        ),
                        correlation_id=correlation_id,
                        actor_id=actor_id,
                    )
                )
            )
            if (
                policy_learning_update_approval.policy_learning_update_approval_status
                in {
                    "blocked_missing_context",
                    "rejected_for_policy_update_use",
                    "prohibited_overlap_blocked",
                }
                or policy_learning_update_approval.policy_learning_update_approval_outcome
                == "deferred_pending_additional_governance"
            ):
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=policy_learning_update_approval.reason,
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )

        if policy_learning_update_preparation_class_id is not None:
            if self._policy_learning_update_preparation_service is None:
                raise RuntimeError(
                    "Policy-learning update-preparation service is not configured."
                )
            if policy_learning_update_approval is None:
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=(
                        "Policy-learning update preparation requires a governed "
                        "policy-learning update-approval record."
                    ),
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )
            policy_learning_update_preparation = (
                self._policy_learning_update_preparation_service.generate(
                    PolicyLearningUpdatePreparationRequest(
                        policy_learning_update_approval=(
                            policy_learning_update_approval
                        ),
                        policy_learning_update_preparation_class_id=(
                            policy_learning_update_preparation_class_id
                        ),
                        policy_learning_update_preparation_author_role=actor_role,
                        policy_learning_update_preparation_context=dict(
                            policy_learning_update_preparation_context or {}
                        ),
                        correlation_id=correlation_id,
                        actor_id=actor_id,
                    )
                )
            )
            if (
                policy_learning_update_preparation.policy_learning_update_preparation_status
                in {
                    "blocked_missing_context",
                    "rejected_for_preparation_use",
                    "prohibited_overlap_blocked",
                }
                or policy_learning_update_preparation.policy_learning_update_preparation_outcome
                == "deferred_pending_preparation_prerequisites"
            ):
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=policy_learning_update_preparation.reason,
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )

        if policy_learning_update_mutation_planning_class_id is not None:
            if self._policy_learning_update_mutation_planning_service is None:
                raise RuntimeError(
                    "Policy-learning update-mutation-planning service is not configured."
                )
            if policy_learning_update_preparation is None:
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=(
                        "Policy-learning update mutation planning requires a governed "
                        "policy-learning update-preparation record."
                    ),
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )
            policy_learning_update_mutation_planning = (
                self._policy_learning_update_mutation_planning_service.generate(
                    PolicyLearningUpdateMutationPlanningRequest(
                        policy_learning_update_preparation=(
                            policy_learning_update_preparation
                        ),
                        policy_learning_update_mutation_planning_class_id=(
                            policy_learning_update_mutation_planning_class_id
                        ),
                        policy_learning_update_mutation_planning_author_role=actor_role,
                        policy_learning_update_mutation_planning_context=dict(
                            policy_learning_update_mutation_planning_context or {}
                        ),
                        correlation_id=correlation_id,
                        actor_id=actor_id,
                    )
                )
            )
            if (
                policy_learning_update_mutation_planning.policy_learning_update_mutation_planning_status
                in {
                    "blocked_missing_context",
                    "rejected_for_mutation_planning_use",
                    "prohibited_overlap_blocked",
                }
                or policy_learning_update_mutation_planning.policy_learning_update_mutation_planning_outcome
                == "deferred_pending_mutation_planning_prerequisites"
            ):
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=policy_learning_update_mutation_planning.reason,
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )

        if policy_learning_update_mutation_execution_class_id is not None:
            if self._policy_learning_update_mutation_execution_service is None:
                raise RuntimeError(
                    "Policy-learning update-mutation-execution service is not configured."
                )
            if policy_learning_update_mutation_planning is None:
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=(
                        "Policy-learning update mutation execution requires a governed "
                        "policy-learning update-mutation-planning record."
                    ),
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )
            policy_learning_update_mutation_execution = (
                self._policy_learning_update_mutation_execution_service.generate(
                    PolicyLearningUpdateMutationExecutionRequest(
                        policy_learning_update_mutation_planning=(
                            policy_learning_update_mutation_planning
                        ),
                        policy_learning_update_mutation_execution_class_id=(
                            policy_learning_update_mutation_execution_class_id
                        ),
                        policy_learning_update_mutation_execution_author_role=actor_role,
                        policy_learning_update_mutation_execution_context=dict(
                            policy_learning_update_mutation_execution_context or {}
                        ),
                        correlation_id=correlation_id,
                        actor_id=actor_id,
                    )
                )
            )
            if (
                policy_learning_update_mutation_execution.policy_learning_update_mutation_execution_status
                in {
                    "blocked_missing_context",
                    "rejected_for_mutation_execution_use",
                    "prohibited_overlap_blocked",
                }
                or policy_learning_update_mutation_execution.policy_learning_update_mutation_execution_outcome
                == "deferred_pending_mutation_execution_prerequisites"
            ):
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=policy_learning_update_mutation_execution.reason,
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )

        if promotion_readiness_class_id is not None:
            if self._promotion_readiness_gate is None:
                raise RuntimeError(
                    "Promotion-readiness gate is not configured."
                )
            if policy_learning_update_mutation_execution is None:
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=(
                        "Promotion readiness requires a governed policy-learning "
                        "update-mutation-execution record."
                    ),
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )
            promotion_readiness = self._promotion_readiness_gate.generate(
                PromotionReadinessGateRequest(
                    policy_learning_update_mutation_execution=(
                        policy_learning_update_mutation_execution
                    ),
                    promotion_readiness_class_id=promotion_readiness_class_id,
                    promotion_readiness_author_role=actor_role,
                    promotion_readiness_context=dict(
                        promotion_readiness_context or {}
                    ),
                    correlation_id=correlation_id,
                    actor_id=actor_id,
                )
            )
            if (
                promotion_readiness.promotion_readiness_status
                in {
                    "blocked_missing_context",
                    "rejected_for_promotion_use",
                    "prohibited_overlap_blocked",
                }
                or promotion_readiness.promotion_readiness_outcome
                == "deferred_pending_promotion_readiness_evidence"
            ):
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=promotion_readiness.reason,
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )

        if rollout_scope_class_id is not None:
            if self._rollout_scope_controller is None:
                raise RuntimeError("Rollout-scope controller is not configured.")
            if promotion_readiness is None:
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=(
                        "Rollout-scope control requires a governed promotion-readiness "
                        "record."
                    ),
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )
            rollout_scope = self._rollout_scope_controller.generate(
                RolloutScopeControllerRequest(
                    promotion_readiness=promotion_readiness,
                    rollout_scope_class_id=rollout_scope_class_id,
                    rollout_scope_author_role=actor_role,
                    rollout_scope_context=dict(rollout_scope_context or {}),
                    correlation_id=correlation_id,
                    actor_id=actor_id,
                )
            )
            if (
                rollout_scope.rollout_scope_status
                in {
                    "blocked_missing_context",
                    "rejected_for_rollout_scope_use",
                    "prohibited_overlap_blocked",
                }
                or rollout_scope.rollout_scope_outcome
                == "deferred_pending_rollout_scope_evidence"
            ):
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=rollout_scope.reason,
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )

        if rollback_trigger_class_id is not None:
            if self._rollback_trigger_guard is None:
                raise RuntimeError("Rollback-trigger guard is not configured.")
            if rollout_scope is None:
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=(
                        "Rollback-trigger guard requires a governed rollout-scope "
                        "record."
                    ),
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )
            rollback_trigger = self._rollback_trigger_guard.generate(
                RollbackTriggerGuardRequest(
                    rollout_scope=rollout_scope,
                    rollback_trigger_class_id=rollback_trigger_class_id,
                    rollback_trigger_author_role=actor_role,
                    rollback_trigger_context=dict(rollback_trigger_context or {}),
                    correlation_id=correlation_id,
                    actor_id=actor_id,
                )
            )
            if (
                rollback_trigger.rollback_trigger_status
                in {
                    "blocked_missing_context",
                    "rejected_for_rollback_trigger_use",
                    "prohibited_overlap_blocked",
                }
                or rollback_trigger.rollback_trigger_outcome
                == "deferred_pending_rollback_trigger_evidence"
            ):
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=rollback_trigger.reason,
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )

        if release_watch_discipline_class_id is not None:
            if self._release_watch_discipline is None:
                raise RuntimeError("Release-watch discipline is not configured.")
            if rollback_trigger is None:
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=(
                        "Release-watch discipline requires a governed "
                        "rollback-trigger record."
                    ),
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )
            release_watch_discipline = self._release_watch_discipline.generate(
                ReleaseWatchDisciplineRequest(
                    rollback_trigger=rollback_trigger,
                    release_watch_discipline_class_id=(
                        release_watch_discipline_class_id
                    ),
                    release_watch_discipline_author_role=actor_role,
                    release_watch_discipline_context=dict(
                        release_watch_discipline_context or {}
                    ),
                    correlation_id=correlation_id,
                    actor_id=actor_id,
                )
            )
            if (
                release_watch_discipline.release_watch_discipline_status
                in {
                    "blocked_missing_context",
                    "rejected_for_release_watch_discipline_use",
                    "prohibited_overlap_blocked",
                }
                or release_watch_discipline.release_watch_discipline_outcome
                == "deferred_pending_release_watch_discipline_evidence"
            ):
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=release_watch_discipline.reason,
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )

        if release_confirmation_class_id is not None:
            if self._release_confirmation is None:
                raise RuntimeError("Release confirmation is not configured.")
            if release_watch_discipline is None:
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=(
                        "Release confirmation requires a governed "
                        "release-watch-discipline record."
                    ),
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )
            release_confirmation = self._release_confirmation.generate(
                ReleaseConfirmationRequest(
                    release_watch_discipline=release_watch_discipline,
                    release_confirmation_class_id=release_confirmation_class_id,
                    release_confirmation_author_role=actor_role,
                    release_confirmation_context=dict(
                        release_confirmation_context or {}
                    ),
                    correlation_id=correlation_id,
                    actor_id=actor_id,
                )
            )
            if (
                release_confirmation.release_confirmation_status
                in {
                    "blocked_missing_context",
                    "rejected_for_release_confirmation_use",
                    "prohibited_overlap_blocked",
                }
                or release_confirmation.release_confirmation_outcome
                == "deferred_pending_release_confirmation_evidence"
            ):
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=release_confirmation.reason,
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )

        if production_entitlement_check_class_id is not None:
            if self._production_entitlement_check is None:
                raise RuntimeError(
                    "Production entitlement check is not configured."
                )
            if release_confirmation is None:
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=(
                        "Production entitlement check requires a governed "
                        "release-confirmation record."
                    ),
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )
            production_entitlement_check = self._production_entitlement_check.generate(
                ProductionEntitlementCheckRequest(
                    release_confirmation=release_confirmation,
                    production_entitlement_check_class_id=(
                        production_entitlement_check_class_id
                    ),
                    production_entitlement_check_author_role=actor_role,
                    production_entitlement_check_context=dict(
                        production_entitlement_check_context or {}
                    ),
                    correlation_id=correlation_id,
                    actor_id=actor_id,
                )
            )
            if (
                production_entitlement_check.production_entitlement_check_status
                in {
                    "blocked_missing_context",
                    "rejected_for_production_entitlement_use",
                    "prohibited_overlap_blocked",
                }
                or production_entitlement_check.production_entitlement_check_outcome
                == "deferred_pending_production_entitlement_evidence"
            ):
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=production_entitlement_check.reason,
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )

        if contained_rollback_class_id is not None:
            if self._contained_rollback is None:
                raise RuntimeError("Contained rollback is not configured.")
            if production_entitlement_check is None:
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=(
                        "Contained rollback requires a governed "
                        "production-entitlement-check record."
                    ),
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )
            contained_rollback = self._contained_rollback.generate(
                ContainedRollbackRequest(
                    production_entitlement_check=production_entitlement_check,
                    contained_rollback_class_id=contained_rollback_class_id,
                    contained_rollback_author_role=actor_role,
                    contained_rollback_context=dict(contained_rollback_context or {}),
                    correlation_id=correlation_id,
                    actor_id=actor_id,
                )
            )
            if (
                contained_rollback.contained_rollback_status
                in {
                    "blocked_missing_context",
                    "rejected_for_contained_rollback_use",
                    "prohibited_overlap_blocked",
                }
                or contained_rollback.contained_rollback_outcome
                == "deferred_pending_contained_rollback_evidence"
            ):
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=contained_rollback.reason,
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )

        if release_audit_trace_class_id is not None:
            if self._release_audit_trace is None:
                raise RuntimeError("Release audit trace is not configured.")
            if contained_rollback is None:
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=(
                        "Release audit trace requires a governed contained-rollback record."
                    ),
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )
            release_audit_trace = self._release_audit_trace.generate(
                ReleaseAuditTraceRequest(
                    contained_rollback=contained_rollback,
                    release_audit_trace_class_id=release_audit_trace_class_id,
                    release_audit_trace_author_role=actor_role,
                    release_audit_trace_context=dict(
                        release_audit_trace_context or {}
                    ),
                    correlation_id=correlation_id,
                    actor_id=actor_id,
                )
            )
            if (
                release_audit_trace.release_audit_trace_status
                in {
                    "blocked_missing_context",
                    "rejected_for_release_audit_trace_use",
                    "prohibited_overlap_blocked",
                }
                or release_audit_trace.release_audit_trace_outcome
                == "deferred_pending_release_audit_trace_evidence"
            ):
                self._raise_blocked_transition(
                    evaluation=evaluation,
                    blocked_reason=release_audit_trace.reason,
                    current_status=current_status,
                    correlation_id=correlation_id,
                    episode_id=episode_id,
                    actor_id=actor_id,
                    reason=reason,
                    router_resolution=router_resolution,
                )

        self._transition_audit_adapter.record_transition_outcome(
            evaluation,
            correlation_id=correlation_id,
            episode_id=episode_id,
            actor_id=actor_id,
            reason=reason,
            router_resolution=router_resolution,
        )
        next_interruption_reason = reason if evaluation.resulting_status == "interrupted" else None
        return CaseStateTransitionResult(
            transition_name=evaluation.transition_name,
            from_state=evaluation.from_state,
            to_state=evaluation.to_state,
            transition_class=evaluation.transition_class,
            resulting_status=evaluation.resulting_status,
            occurred_at_reason=reason,
            next_interruption_reason=next_interruption_reason,
            route_name=router_resolution.route_name,
            routing_resolution_status=router_resolution.resolution_status,
            routing_review_required=router_resolution.review_required,
            review_outcome=review_decision.outcome_kind,
            review_mode=review_decision.review_mode,
            review_threshold_id=review_decision.threshold_id,
            review_playbook_reference=review_decision.playbook_reference,
            review_packet_status=review_packet.packet_status if review_packet is not None else None,
            review_packet_handoff_ready=(
                review_packet.handoff_ready if review_packet is not None else None
            ),
            review_packet_id=review_packet.packet_id if review_packet is not None else None,
            review_packet_template_id=(
                review_packet.packet_template_id if review_packet is not None else None
            ),
            review_packet_reason_class=(
                review_packet.reason_class if review_packet is not None else None
            ),
            review_packet_scope=review_packet.packet_scope if review_packet is not None else None,
            review_packet_handoff_channel=(
                review_packet.handoff_channel if review_packet is not None else None
            ),
            review_resolution_status=(
                review_resolution.resolution_status if review_resolution is not None else None
            ),
            review_resolution_id=(
                review_resolution.resolution_id if review_resolution is not None else None
            ),
            review_resolution_class_id=(
                review_resolution.resolution_class_id if review_resolution is not None else None
            ),
            review_resolution_outcome=(
                review_resolution.review_outcome if review_resolution is not None else None
            ),
            review_resolution_state=(
                review_resolution.resolution_state if review_resolution is not None else None
            ),
            review_disposition_class_id=(
                review_resolution.disposition_class_id if review_resolution is not None else None
            ),
            review_disposition_state=(
                review_resolution.disposition_state if review_resolution is not None else None
            ),
            review_closure_state=(
                review_resolution.closure_state if review_resolution is not None else None
            ),
            review_closure_quality=(
                review_resolution.closure_quality if review_resolution is not None else None
            ),
            review_resolution_terminality=(
                review_resolution.terminality if review_resolution is not None else None
            ),
            recommendation_status=(
                recommendation.recommendation_status if recommendation is not None else None
            ),
            recommendation_id=(
                recommendation.recommendation_id if recommendation is not None else None
            ),
            recommendation_class_id=(
                recommendation.recommendation_class_id if recommendation is not None else None
            ),
            recommendation_template_id=(
                recommendation.recommendation_template_id if recommendation is not None else None
            ),
            recommendation_action_class=(
                recommendation.action_class if recommendation is not None else None
            ),
            recommendation_advisory_status=(
                recommendation.advisory_status if recommendation is not None else None
            ),
            recommendation_commitment_readiness=(
                recommendation.commitment_readiness if recommendation is not None else None
            ),
            policy_output_status=(
                policy_output.policy_output_status if policy_output is not None else None
            ),
            policy_output_id=(
                policy_output.policy_output_id if policy_output is not None else None
            ),
            policy_output_class_id=(
                policy_output.policy_output_class_id if policy_output is not None else None
            ),
            policy_output_template_id=(
                policy_output.policy_output_template_id if policy_output is not None else None
            ),
            policy_output_bounded_policy_posture=(
                policy_output.bounded_policy_posture if policy_output is not None else None
            ),
            policy_output_action_boundary_posture=(
                policy_output.action_boundary_posture if policy_output is not None else None
            ),
            policy_output_promotion_safe_use=(
                policy_output.promotion_safe_use if policy_output is not None else None
            ),
            portfolio_output_status=(
                portfolio_output.portfolio_output_status
                if portfolio_output is not None
                else None
            ),
            portfolio_output_id=(
                portfolio_output.portfolio_output_id if portfolio_output is not None else None
            ),
            portfolio_output_class_id=(
                portfolio_output.portfolio_output_class_id
                if portfolio_output is not None
                else None
            ),
            portfolio_output_template_id=(
                portfolio_output.portfolio_output_template_id
                if portfolio_output is not None
                else None
            ),
            portfolio_output_allocation_posture=(
                portfolio_output.allocation_posture if portfolio_output is not None else None
            ),
            portfolio_output_weight_posture=(
                portfolio_output.weight_posture if portfolio_output is not None else None
            ),
            portfolio_output_action_boundary_posture=(
                portfolio_output.action_boundary_posture
                if portfolio_output is not None
                else None
            ),
            portfolio_output_promotion_safe_use=(
                portfolio_output.promotion_safe_use if portfolio_output is not None else None
            ),
            action_instruction_status=(
                action_instruction.action_instruction_status
                if action_instruction is not None
                else None
            ),
            action_instruction_id=(
                action_instruction.action_instruction_id
                if action_instruction is not None
                else None
            ),
            action_instruction_class_id=(
                action_instruction.action_instruction_class_id
                if action_instruction is not None
                else None
            ),
            action_instruction_template_id=(
                action_instruction.action_instruction_template_id
                if action_instruction is not None
                else None
            ),
            action_instruction_instruction_status=(
                action_instruction.instruction_status
                if action_instruction is not None
                else None
            ),
            action_instruction_bounded_action_posture=(
                action_instruction.bounded_action_posture
                if action_instruction is not None
                else None
            ),
            action_instruction_execution_boundary_posture=(
                action_instruction.execution_boundary_posture
                if action_instruction is not None
                else None
            ),
            action_instruction_promotion_safe_use=(
                action_instruction.promotion_safe_use
                if action_instruction is not None
                else None
            ),
            execution_request_status=(
                execution_request.execution_request_status
                if execution_request is not None
                else None
            ),
            execution_request_id=(
                execution_request.execution_request_id
                if execution_request is not None
                else None
            ),
            execution_request_class_id=(
                execution_request.execution_request_class_id
                if execution_request is not None
                else None
            ),
            execution_request_template_id=(
                execution_request.execution_request_template_id
                if execution_request is not None
                else None
            ),
            execution_request_readiness=(
                execution_request.execution_request_readiness
                if execution_request is not None
                else None
            ),
            execution_request_action_boundary_posture=(
                execution_request.action_boundary_posture
                if execution_request is not None
                else None
            ),
            execution_dispatch_status=(
                execution_dispatch.execution_dispatch_status
                if execution_dispatch is not None
                else None
            ),
            execution_dispatch_id=(
                execution_dispatch.execution_dispatch_id
                if execution_dispatch is not None
                else None
            ),
            execution_dispatch_class_id=(
                execution_dispatch.execution_dispatch_class_id
                if execution_dispatch is not None
                else None
            ),
            execution_dispatch_template_id=(
                execution_dispatch.execution_dispatch_template_id
                if execution_dispatch is not None
                else None
            ),
            execution_dispatch_readiness=(
                execution_dispatch.execution_dispatch_readiness
                if execution_dispatch is not None
                else None
            ),
            execution_dispatch_boundary_posture=(
                execution_dispatch.dispatch_boundary_posture
                if execution_dispatch is not None
                else None
            ),
            execution_outcome_status=(
                execution_outcome.execution_outcome_status
                if execution_outcome is not None
                else None
            ),
            execution_outcome_id=(
                execution_outcome.execution_outcome_id
                if execution_outcome is not None
                else None
            ),
            execution_outcome_class_id=(
                execution_outcome.execution_outcome_class_id
                if execution_outcome is not None
                else None
            ),
            execution_outcome_template_id=(
                execution_outcome.execution_outcome_template_id
                if execution_outcome is not None
                else None
            ),
            execution_outcome_realized_result_class=(
                execution_outcome.realized_result_class
                if execution_outcome is not None
                else None
            ),
            execution_outcome_feedback_capture_readiness=(
                execution_outcome.feedback_capture_readiness
                if execution_outcome is not None
                else None
            ),
            execution_outcome_expected_relation=(
                execution_outcome.expected_relation
                if execution_outcome is not None
                else None
            ),
            execution_outcome_comparison_posture=(
                execution_outcome.comparison_posture
                if execution_outcome is not None
                else None
            ),
            post_mortem_judgment_status=(
                post_mortem_judgment.post_mortem_status
                if post_mortem_judgment is not None
                else None
            ),
            post_mortem_judgment_id=(
                post_mortem_judgment.post_mortem_judgment_id
                if post_mortem_judgment is not None
                else None
            ),
            post_mortem_judgment_class_id=(
                post_mortem_judgment.post_mortem_judgment_class_id
                if post_mortem_judgment is not None
                else None
            ),
            post_mortem_judgment_template_id=(
                post_mortem_judgment.post_mortem_judgment_template_id
                if post_mortem_judgment is not None
                else None
            ),
            post_mortem_primary_attribution_category=(
                post_mortem_judgment.primary_attribution_category
                if post_mortem_judgment is not None
                else None
            ),
            post_mortem_evidence_quality=(
                post_mortem_judgment.evidence_quality
                if post_mortem_judgment is not None
                else None
            ),
            post_mortem_confidence_posture=(
                post_mortem_judgment.confidence_posture
                if post_mortem_judgment is not None
                else None
            ),
            post_mortem_learning_direction=(
                post_mortem_judgment.learning_direction
                if post_mortem_judgment is not None
                else None
            ),
            post_mortem_comparison_posture=(
                post_mortem_judgment.comparison_posture
                if post_mortem_judgment is not None
                else None
            ),
            policy_learning_evidence_admission_status=(
                policy_learning_evidence_admission.policy_learning_evidence_admission_status
                if policy_learning_evidence_admission is not None
                else None
            ),
            policy_learning_evidence_admission_id=(
                policy_learning_evidence_admission.policy_learning_evidence_admission_id
                if policy_learning_evidence_admission is not None
                else None
            ),
            policy_learning_evidence_class_id=(
                policy_learning_evidence_admission.policy_learning_evidence_class_id
                if policy_learning_evidence_admission is not None
                else None
            ),
            policy_learning_evidence_template_id=(
                policy_learning_evidence_admission.policy_learning_evidence_template_id
                if policy_learning_evidence_admission is not None
                else None
            ),
            policy_learning_evidence_admission_context=(
                policy_learning_evidence_admission.to_transport_context()
                if policy_learning_evidence_admission is not None
                else None
            ),
            policy_learning_update_threshold_status=(
                policy_learning_update_threshold.policy_learning_update_threshold_status
                if policy_learning_update_threshold is not None
                else None
            ),
            policy_learning_update_threshold_id=(
                policy_learning_update_threshold.policy_learning_update_threshold_id
                if policy_learning_update_threshold is not None
                else None
            ),
            policy_learning_update_threshold_class_id=(
                policy_learning_update_threshold.policy_learning_update_threshold_class_id
                if policy_learning_update_threshold is not None
                else None
            ),
            policy_learning_update_threshold_template_id=(
                policy_learning_update_threshold.policy_learning_update_threshold_template_id
                if policy_learning_update_threshold is not None
                else None
            ),
            policy_learning_update_threshold_context=(
                policy_learning_update_threshold.to_transport_context()
                if policy_learning_update_threshold is not None
                else None
            ),
            policy_learning_update_approval_status=(
                policy_learning_update_approval.policy_learning_update_approval_status
                if policy_learning_update_approval is not None
                else None
            ),
            policy_learning_update_approval_class_id=(
                policy_learning_update_approval.policy_learning_update_approval_class_id
                if policy_learning_update_approval is not None
                else None
            ),
            policy_learning_update_approval_context=(
                policy_learning_update_approval.to_transport_context()
                if policy_learning_update_approval is not None
                else None
            ),
            policy_learning_update_preparation_status=(
                policy_learning_update_preparation.policy_learning_update_preparation_status
                if policy_learning_update_preparation is not None
                else None
            ),
            policy_learning_update_preparation_class_id=(
                policy_learning_update_preparation.policy_learning_update_preparation_class_id
                if policy_learning_update_preparation is not None
                else None
            ),
            policy_learning_update_preparation_context=(
                policy_learning_update_preparation.to_transport_context()
                if policy_learning_update_preparation is not None
                else None
            ),
            policy_learning_update_mutation_planning_status=(
                policy_learning_update_mutation_planning.policy_learning_update_mutation_planning_status
                if policy_learning_update_mutation_planning is not None
                else None
            ),
            policy_learning_update_mutation_planning_class_id=(
                policy_learning_update_mutation_planning.policy_learning_update_mutation_planning_class_id
                if policy_learning_update_mutation_planning is not None
                else None
            ),
            policy_learning_update_mutation_planning_context=(
                policy_learning_update_mutation_planning.to_transport_context()
                if policy_learning_update_mutation_planning is not None
                else None
            ),
            policy_learning_update_mutation_execution_status=(
                policy_learning_update_mutation_execution.policy_learning_update_mutation_execution_status
                if policy_learning_update_mutation_execution is not None
                else None
            ),
            policy_learning_update_mutation_execution_class_id=(
                policy_learning_update_mutation_execution.policy_learning_update_mutation_execution_class_id
                if policy_learning_update_mutation_execution is not None
                else None
            ),
            policy_learning_update_mutation_execution_context=(
                policy_learning_update_mutation_execution.to_transport_context()
                if policy_learning_update_mutation_execution is not None
                else None
            ),
            promotion_readiness_status=(
                promotion_readiness.promotion_readiness_status
                if promotion_readiness is not None
                else None
            ),
            promotion_readiness_class_id=(
                promotion_readiness.promotion_readiness_class_id
                if promotion_readiness is not None
                else None
            ),
            promotion_readiness_context=(
                promotion_readiness.to_transport_context()
                if promotion_readiness is not None
                else None
            ),
            rollout_scope_status=(
                rollout_scope.rollout_scope_status
                if rollout_scope is not None
                else None
            ),
            rollout_scope_class_id=(
                rollout_scope.rollout_scope_class_id
                if rollout_scope is not None
                else None
            ),
            rollout_scope_context=(
                rollout_scope.to_transport_context()
                if rollout_scope is not None
                else None
            ),
            rollback_trigger_status=(
                rollback_trigger.rollback_trigger_status
                if rollback_trigger is not None
                else None
            ),
            rollback_trigger_class_id=(
                rollback_trigger.rollback_trigger_class_id
                if rollback_trigger is not None
                else None
            ),
            rollback_trigger_context=(
                rollback_trigger.to_transport_context()
                if rollback_trigger is not None
                else None
            ),
            release_watch_discipline_status=(
                release_watch_discipline.release_watch_discipline_status
                if release_watch_discipline is not None
                else None
            ),
            release_watch_discipline_class_id=(
                release_watch_discipline.release_watch_discipline_class_id
                if release_watch_discipline is not None
                else None
            ),
            release_watch_discipline_context=(
                release_watch_discipline.to_transport_context()
                if release_watch_discipline is not None
                else None
            ),
            release_confirmation_status=(
                release_confirmation.release_confirmation_status
                if release_confirmation is not None
                else None
            ),
            release_confirmation_class_id=(
                release_confirmation.release_confirmation_class_id
                if release_confirmation is not None
                else None
            ),
            release_confirmation_context=(
                release_confirmation.to_transport_context()
                if release_confirmation is not None
                else None
            ),
            production_entitlement_check_status=(
                production_entitlement_check.production_entitlement_check_status
                if production_entitlement_check is not None
                else None
            ),
            production_entitlement_check_class_id=(
                production_entitlement_check.production_entitlement_check_class_id
                if production_entitlement_check is not None
                else None
            ),
            production_entitlement_check_context=(
                production_entitlement_check.to_transport_context()
                if production_entitlement_check is not None
                else None
            ),
            contained_rollback_status=(
                contained_rollback.contained_rollback_status
                if contained_rollback is not None
                else None
            ),
            contained_rollback_class_id=(
                contained_rollback.contained_rollback_class_id
                if contained_rollback is not None
                else None
            ),
            contained_rollback_context=(
                contained_rollback.to_transport_context()
                if contained_rollback is not None
                else None
            ),
            release_audit_trace_status=(
                release_audit_trace.release_audit_trace_status
                if release_audit_trace is not None
                else None
            ),
            release_audit_trace_class_id=(
                release_audit_trace.release_audit_trace_class_id
                if release_audit_trace is not None
                else None
            ),
            release_audit_trace_context=(
                release_audit_trace.to_transport_context()
                if release_audit_trace is not None
                else None
            ),
        )

    def _raise_blocked_transition(
        self,
        *,
        evaluation: TransitionEvaluation,
        blocked_reason: str,
        current_status: str,
        correlation_id: str,
        episode_id: str,
        actor_id: str,
        reason: str,
        router_resolution=None,
    ) -> None:
        blocked_evaluation = TransitionEvaluation(
            accepted=False,
            outcome_kind="blocked",
            reason=blocked_reason,
            transition_name=evaluation.transition_name,
            state_model_name=evaluation.state_model_name,
            from_state=evaluation.from_state,
            to_state=evaluation.from_state,
            transition_class=evaluation.transition_class,
            router_rule_id=evaluation.router_rule_id,
            authority_rule_id=evaluation.authority_rule_id,
            actor_role=evaluation.actor_role,
            authority_resolution_kind=evaluation.authority_resolution_kind,
            resolved_role=evaluation.resolved_role,
            review_required=evaluation.review_required,
            resulting_status=current_status,
            grant_source_role=evaluation.grant_source_role,
        )
        self._transition_audit_adapter.record_transition_outcome(
            blocked_evaluation,
            correlation_id=correlation_id,
            episode_id=episode_id,
            actor_id=actor_id,
            reason=reason,
            router_resolution=router_resolution,
        )
        raise TransitionBlockedError(blocked_evaluation)
