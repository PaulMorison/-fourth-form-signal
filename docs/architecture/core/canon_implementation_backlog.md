# Canon Implementation Backlog

## Purpose

This backlog converts the core canon into buildable implementation work. It now sits above a live shared control-plane spine with executable source, registries, schemas, tests, and a verified runtime/release chain through `release_audit_trace`, while large parts of the canon still remain unimplemented.

## Scoring Model

- Dependency level: `Foundation`, `Core`, `Dependent`, `Late`
- Implementation difficulty: `Low`, `Medium`, `High`, `Very High`
- Operational importance: `Low`, `Medium`, `High`, `Critical`
- Risk if missing: `Low`, `Medium`, `High`, `Severe`
- Priority classes: `P0 critical`, `P1 high`, `P2 medium`, `P3 low`

## Verified Runtime/Release Boundary Snapshot

| Boundary or seam | Live status | Canon-backed note |
| --- | --- | --- |
| `promotion_readiness` | Implemented | Verified live in `src/runtime/release/promotion_readiness_gate.py` with focused tests and bootstrap wiring. |
| `rollout_scope` | Implemented | Verified live in `src/runtime/release/rollout_scope_controller.py` with focused tests and bootstrap wiring. |
| `rollback_trigger` | Implemented | Verified live in `src/runtime/release/rollback_trigger_guard.py` with focused tests and bootstrap wiring. |
| `release_watch_discipline` | Implemented | Verified live in `src/runtime/release/release_watch_discipline.py` with focused tests and bootstrap wiring. |
| `release_confirmation` | Implemented | Verified live in `src/runtime/release/release_confirmation.py` with focused tests and bootstrap wiring. |
| `production_entitlement_check` | Implemented | Verified live in `src/runtime/release/production_entitlement_check.py` with focused tests and bootstrap wiring. |
| `contained_rollback` | Implemented | Verified live in `src/runtime/release/contained_rollback.py` with focused tests and bootstrap wiring. |
| `release_audit_trace` | Implemented | Verified live in `src/runtime/release/release_audit_trace.py`; this is the current verified end-state of the runtime/release chain. |
| Next downstream boundary after `release_audit_trace` | Not approved as an exact module name | Canon allows later final-disposition references to be preserved by `release_audit_trace`, but the next downstream runtime/release module is not named unambiguously in the live docs and should not be invented here. |
| Release closure or final disposition meaning | Unresolved downstream authority | Explicitly outside `release_audit_trace`; closure meaning remains separate from the trace layer. |
| Runtime verification | Unresolved downstream authority | Explicitly outside `production_entitlement_check`, `contained_rollback`, and `release_audit_trace`. |
| Monitoring admission | Unresolved downstream authority | Explicitly outside the currently implemented release-control chain and separate from monitoring-governance ownership. |
| Reopen, revisit, and reinstatement | Unresolved neighboring authority | Governed by the shared reopen standard, not by the current runtime/release module chain. |

## Backlog

| ID | Short title | Owning canon doc(s) | Why it matters | Dependency level | Implementation difficulty | Operational importance | Risk if missing | Priority |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B01 | Platform contract and registry spine | `system_layers_overview.md`; `canon_navigation_and_reading_order_standard.md`; `glossary_and_canonical_term_usage_standard.md`; `code_architecture_and_modularity_standard.md` | Every later module depends on explicit contracts, stable registries, and machine-checkable ownership. | Foundation | High | Critical | Severe | P0 critical |
| B02 | Canon quality and governance control plane | `canon_change_control_and_quality_gate_standard.md`; `future_domain_admission_and_domain_readiness_standard.md` | The repo already has canon, so implementation drift will begin immediately unless change control and domain admission gates are executable. | Foundation | Medium | High | High | P1 high |
| B03 | Decision case and lifecycle orchestrator | `decision_case_orchestration_and_episode_governance_standard.md`; `decision_state_transition_and_case_progression_governance_standard.md`; `end_to_end_decision_lifecycle_composition_standard.md` | Without a governed case spine there is no place to attach evidence, recommendations, outcomes, or audit trails. | Foundation | Very High | Critical | Severe | P0 critical |
| B04 | Decision rights, mode, routing, and playbook engine | `decision_rights_and_authority_delegation_standard.md`; `decision_mode_and_intervention_policy_standard.md`; `decision_router_and_conflict_resolution_governance_standard.md`; `decision_playbook_and_intervention_pattern_governance_standard.md` | The system cannot produce safe decisions until authority, routing, and intervention logic are executable and reviewable. | Core | Very High | Critical | Severe | P0 critical |
| B05 | Raw ingestion and canonicalization pipeline | `raw_data_update_and_feature_generation_pipeline_standard.md`; `data_storage_persistence_and_backup_standard.md`; `security_and_data_protection_standard.md` | All later reasoning depends on trustworthy, lineaged, protected source data. | Foundation | Very High | Critical | Severe | P0 critical |
| B06 | Feature, dataset, and artifact governance stack | `feature_definition_and_semantic_consistency_standard.md`; `dataset_feature_set_and_artifact_version_governance_standard.md` | Reusable state and model inputs cannot be trusted until features and datasets have stable identities and versions. | Core | High | Critical | Severe | P0 critical |
| B07 | Target, split, evaluation, and validation stack | `training_target_and_label_governance_standard.md`; `training_data_split_and_evaluation_protocol_standard.md`; `testing_regression_and_validation_gate_standard.md` | This is the minimum discipline required to train or validate anything without silent leakage. | Core | High | Critical | Severe | P0 critical |
| B08 | Model run and artifact control plane | `model_training_and_scoring_execution_governance_standard.md`; `model_artifact_and_model_version_governance_standard.md`; `release_readiness_and_promotion_control_standard.md` | Training and scoring need governed execution, version identity, and rollback-safe release gates. | Core | High | High | High | P1 high |
| B09 | Objective, threshold, and policy output engine | `objective_function_and_optimization_target_governance_standard.md`; `threshold_trigger_and_calibration_governance_standard.md`; `portfolio_and_policy_output_governance_standard.md` | This layer turns state into governed actions; without it the platform is only an analysis stack. | Core | Very High | Critical | Severe | P0 critical |
| B10 | Simulation and counterfactual execution plane | `expected_baseline_and_counterfactual_alignment_governance_standard.md`; `research_and_experimentation_governance_standard.md`; `simulation_and_scenario_execution_governance_standard.md`; `simulation_result_and_scenario_output_governance_standard.md` | Simulation is central to the canon’s decision thesis, not an optional add-on. | Dependent | Very High | High | High | P1 high |
| B11 | Metrics, signal quality, and drift monitoring | `canonical_metric_and_kpi_governance_standard.md`; `signal_quality_and_evidence_strength_surface_standard.md`; `model_monitoring_and_post_deployment_drift_governance_standard.md`; `observability_logging_and_operational_telemetry_standard.md` | Operator trust and automated safety checks depend on governed metrics, surfaces, and live drift visibility. | Dependent | High | High | High | P1 high |
| B12 | Outcome, feedback, and post-decision memory spine | `outcome_capture_and_feedback_realisation_standard.md`; `decision_memory_retrieval_and_reuse_governance_standard.md`; `policy_learning_evidence_admission_and_update_threshold_standard.md` | Learning, reuse, and accountable iteration are impossible without governed outcomes and reusable decision memory. | Core | High | Critical | Severe | P0 critical |
| B13 | Human review and decision surfaces | `human_review_and_escalation_operating_model_standard.md`; `decision_surface_and_dashboard_governance_standard.md` | The canon requires accountable human review and governed operator surfaces before high-stakes action can be trusted. | Dependent | High | High | High | P1 high |
| B14 | Runtime config, environment, and deployment controls | `runtime_configuration_and_secret_scope_standard.md`; `deployment_environment_and_runtime_boundary_standard.md`; `release_readiness_and_promotion_control_standard.md` | Secure environment separation, config discipline, and promotion control are prerequisites for any live runtime. | Core | High | Critical | Severe | P0 critical |
| B15 | Capability lifecycle and retention controls | `capability_retention_and_decommission_governance_standard.md`; `commercial_value_creation_and_realisation_standard.md` | The platform needs an explicit way to keep, freeze, retire, or decommission capabilities as it grows. | Dependent | Medium | High | Medium | P2 medium |
| B16 | Low-admin and code-generation governance | `automation_and_low_admin_operating_model_standard.md`; `implementation_agent_and_code_generation_quality_standard.md`; `prompt_asset_and_instruction_library_governance_standard.md` | Automation and generated code will accumulate quickly; without controls they will degrade the repo before the platform is stable. | Late | Medium | Medium | Medium | P2 medium |
| B17 | Performance and scale guardrails | `performance_efficiency_and_scalability_standard.md` | Efficient workload boundaries should be instrumented before scale, but only after the core control plane exists. | Dependent | Medium | Medium | Medium | P2 medium |

## Top 10 Implementation Priorities

1. Build the platform contract and registry spine.
2. Build the decision case and lifecycle orchestrator.
3. Build the raw ingestion and canonicalization pipeline.
4. Build the feature, dataset, and artifact governance stack.
5. Build the target, split, evaluation, and validation stack.
6. Build the decision rights, mode, routing, and playbook engine.
7. Build the objective, threshold, and policy output engine.
8. Build the outcome, feedback, and post-decision memory spine.
9. Build runtime config, environment, and release controls.
10. Build metrics, signal quality, observability, and drift monitoring.

## Top 10 Operator-Surface Priorities

1. Decision operations cockpit for case state, handoffs, and lifecycle transitions.
2. Human review queue with escalation paths, authority context, and backlog risk.
3. Raw ingestion and feature-job operations dashboard.
4. Feature, dataset, and artifact catalog with promotion and invalidation history.
5. Validation and regression dashboard with release-gate evidence.
6. Objective, threshold, and policy-output review console.
7. Outcome and feedback realization dashboard.
8. Decision memory browser with reuse-boundary visibility.
9. Drift, degradation, and signal-quality monitoring surface.
10. Release, rollout, rollback, and environment boundary dashboard.

## Top 10 Governance-Enforcement Priorities

1. Contract schema validation for every registry-backed object.
2. Decision-state transition guard and lifecycle phase legality checker.
3. Authority delegation, override, and ceiling or floor enforcement.
4. Feature definition, dataset version, and target-label semantic drift guards.
5. Training split leakage and holdout misuse detection.
6. Threshold, trigger, and calibration drift detection.
7. Output action-boundary and promotion-boundary enforcement.
8. Cross-domain decision-memory reuse boundary enforcement.
9. Runtime config secret-scope and environment-crossing enforcement.
10. Canon change, supersession, and repo-memory sync gating.

## First-Wave Build Order

1. B01 Platform contract and registry spine
2. B03 Decision case and lifecycle orchestrator
3. B05 Raw ingestion and canonicalization pipeline
4. B06 Feature, dataset, and artifact governance stack
5. B07 Target, split, evaluation, and validation stack
6. B04 Decision rights, mode, routing, and playbook engine
7. B09 Objective, threshold, and policy output engine
8. B12 Outcome, feedback, and post-decision memory spine
9. B14 Runtime config, environment, and deployment controls
10. B11 Metrics, signal quality, and drift monitoring

Any attempt to start with dashboards, simulation polish, or prompt libraries before items 1 through 8 will create operator-facing motion without governed platform substance.