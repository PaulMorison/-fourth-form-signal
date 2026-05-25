# Implementation Module Blueprint

## Purpose

This blueprint translates the core canon into a concrete codebase shape. It started as a documentation-only target picture, but the live repo now implements the shared control-plane spine and the observed runtime/release pattern through `src/runtime/release/release_audit_trace.py`, so the runtime/release subtree below should be read as part observed pattern and part remaining blueprint.

## Top-Level Folders

```text
contracts/
registries/
schemas/
src/
  platform/
  data/
  state/
  graph/
  decision/
  models/
  simulation/
  lifecycle/
  runtime/
  surfaces/
tests/
  contract/
  unit/
  integration/
  lifecycle/
  release/
ops/
  dashboards/
  runbooks/
  alerts/
migrations/
```

## Folder Ownership

| Folder | Ownership |
| --- | --- |
| `contracts/` | Canon-backed external and internal interfaces, registry payloads, lifecycle records, and runtime event contracts |
| `registries/` | Checked-in seed registries and canonical manifests for layers, terms, domains, states, objectives, thresholds, environments, and release gates |
| `schemas/` | JSON Schema or equivalent validation schemas for every contract and persisted record |
| `src/platform/` | Canon, glossary, governance, audit, and control-plane services |
| `src/data/` | Raw ingestion, staging, canonicalization, storage ownership, and signal-quality input controls |
| `src/state/` | Feature definitions, dataset versions, metrics, labels, targets, and state bundles |
| `src/graph/` | Graph-backed memory and relationship retrieval services |
| `src/decision/` | Case orchestration, state transitions, authority, routing, playbooks, objectives, thresholds, and outputs |
| `src/models/` | Training runs, scoring runs, model artifacts, evaluation protocols, and drift monitors |
| `src/simulation/` | Experiment registry, scenario execution, replay, expected-baseline alignment, and simulation outputs |
| `src/lifecycle/` | Outcomes, feedback realization, decision memory, policy-learning evidence, and lifecycle composition |
| `src/runtime/` | Configuration, secrets, environments, release control, telemetry, and runtime monitors |
| `src/surfaces/` | Operator-facing dashboards, review queues, admin consoles, and reporting surfaces |

## Proposed Source Tree

```text
src/
  platform/
    canon/
      navigation_index_service.py
      document_placement_validator.py
      canon_quality_gate.py
      supersession_registry_service.py
      repo_memory_sync_guard.py
    glossary/
      term_registry_service.py
      synonym_resolution_service.py
      term_usage_linter.py
    governance/
      domain_admission_gate.py
      domain_readiness_scorecard.py
      value_pathway_registry.py
      capability_lifecycle_service.py
    audit/
      audit_event_store.py
      audit_event_schema_registry.py
      audit_export_service.py
      lineage_trace_service.py
    validation/
      contract_schema_validator.py
      registry_integrity_checker.py
      module_boundary_linter.py
      seam_explicitness_checker.py
      codegen_output_guard.py

  data/
    ingestion/
      raw_ingestion_pipeline.py
      source_connector_registry.py
      staging_manager.py
      ingestion_lineage_service.py
    canonical/
      entity_resolution_service.py
      ontology_mapping_service.py
      transformation_legitimacy_guard.py
    quality/
      signal_quality_service.py
      evidence_strength_surface.py
      data_freshness_monitor.py
      contradiction_detector.py
    storage/
      storage_registry.py
      persistence_guard.py
      backup_lineage_tracker.py
      restore_legitimacy_validator.py

  state/
    features/
      feature_registry.py
      formula_validator.py
      semantic_drift_guard.py
      feature_generation_service.py
      state_bundle_builder.py
    datasets/
      dataset_version_registry.py
      feature_set_registry.py
      artifact_promotion_gate.py
      supersession_controller.py
    metrics/
      metric_registry.py
      kpi_formula_service.py
      time_window_validator.py
      comparability_checker.py
    targets/
      target_registry.py
      label_derivation_guard.py
      temporal_alignment_checker.py
      leakage_risk_scanner.py

  graph/
    memory/
      graph_memory_store.py
      relationship_index_service.py
      context_retrieval_service.py
      graph_lineage_service.py

  decision/
    case/
      case_episode_orchestrator.py
      case_repository.py
      handoff_guard.py
      interruption_state_service.py
      resume_controller.py
    lifecycle/
      state_registry.py
      transition_guard.py
      progression_manager.py
      lifecycle_coherence_guard.py
    mode/
      mode_registry.py
      intervention_policy_service.py
      mode_entry_gate.py
      mode_exit_guard.py
    rights/
      authority_registry.py
      delegation_guard.py
      override_authorizer.py
      ceiling_floor_guard.py
    router/
      router_service.py
      conflict_detector.py
      precedence_rule_engine.py
      tie_break_resolver.py
    playbooks/
      playbook_registry.py
      trigger_guard.py
      pattern_sequence_validator.py
      playbook_version_service.py
    objectives/
      objective_registry.py
      optimization_target_service.py
      tradeoff_weighting_guard.py
      objective_activation_gate.py
    thresholds/
      threshold_registry.py
      trigger_definition_service.py
      calibration_guard.py
      threshold_drift_monitor.py
    outputs/
      portfolio_output_service.py
      policy_output_service.py
      allocation_weight_guard.py
      action_boundary_guard.py
      output_registry.py
    review/
      review_registry.py
      escalation_path_service.py
      threshold_guard.py
      backlog_risk_monitor.py

  models/
    runs/
      training_run_service.py
      scoring_run_service.py
      replay_legitimacy_guard.py
      run_lineage_tracker.py
    artifacts/
      model_registry.py
      checkpoint_family_service.py
      promotion_candidate_gate.py
      rollback_safety_checker.py
    evaluation/
      protocol_registry.py
      split_scheme_validator.py
      holdout_guard.py
      regression_detector.py
      validation_evidence_store.py
    monitoring/
      monitor_registry.py
      drift_detection_service.py
      degradation_classifier.py
      alert_legitimacy_guard.py

  simulation/
    research/
      experiment_registry.py
      baseline_variant_guard.py
      sandbox_isolation_service.py
      promotion_retirement_gate.py
    scenarios/
      expected_state_registry.py
      baseline_registry.py
      alignment_validator.py
      counterfactual_reuse_guard.py
    execution/
      scenario_execution_service.py
      simulation_run_registry.py
      replay_validator.py
      containment_guard.py
    results/
      result_registry.py
      output_semantic_guard.py
      promotion_boundary_guard.py
      reuse_validator.py

  lifecycle/
    outcomes/
      outcome_registry.py
      feedback_realisation_service.py
      expected_actual_comparator.py
      result_classifier.py
    memory/
      decision_memory_store.py
      retrieval_service.py
      reuse_boundary_guard.py
      query_auditor.py
    policy_learning/
      evidence_admission_service.py
      case_set_comparability_guard.py
      update_threshold_engine.py
      update_decision_auditor.py
    composition/
      lifecycle_registry.py
      object_composition_validator.py
      lineage_preserver.py
      prerequisite_qualifier_guard.py

  runtime/
    config/
      config_registry.py
      secret_scope_guard.py
      config_override_gate.py
      config_drift_monitor.py
    deployment/
      environment_registry.py
      environment_boundary_guard.py
      crossing_gate.py
      bleed_detector.py
    release/
      release_registry.py
      promotion_readiness_gate.py
      rollout_scope_controller.py
      rollback_trigger_guard.py
      release_watch_discipline.py
      release_confirmation.py
      production_entitlement_check.py
      contained_rollback.py
      release_audit_trace.py
    telemetry/
      log_event_registry.py
      trace_emitter.py
      health_signal_registry.py
      alert_delivery_service.py

  surfaces/
    operator/
      decision_ops_surface.py
      review_queue_surface.py
      release_ops_surface.py
      metrics_surface.py
      simulation_surface.py
      outcome_surface.py
    admin/
      registry_admin_surface.py
      threshold_config_surface.py
      environment_admin_surface.py
      prompt_library_surface.py
    reporting/
      audit_report_exporter.py
      drift_report_exporter.py
      value_realisation_reporter.py
      governance_compliance_reporter.py
```

## Contract Files

The following contract groups should exist before application code stabilizes:

```text
contracts/
  canon/
    document_index.yaml
    placement_rules.yaml
    change_request.yaml
  glossary/
    term_definition.yaml
    term_usage_rule.yaml
  decision/
    case_episode.yaml
    state_transition.yaml
    decision_mode.yaml
    authority_rule.yaml
    delegation_record.yaml
    router_rule.yaml
    conflict_resolution.yaml
    playbook.yaml
    intervention_pattern.yaml
  output/
    portfolio_output.yaml
    policy_output.yaml
    allocation_weight.yaml
  training/
    target_definition.yaml
    label_derivation.yaml
  evaluation/
    protocol.yaml
    split_scheme.yaml
  models/
    training_run.yaml
    scoring_run.yaml
    model_artifact.yaml
    checkpoint_family.yaml
  simulation/
    experiment_definition.yaml
    variant_spec.yaml
    scenario_run.yaml
    expected_state.yaml
    baseline_definition.yaml
    simulation_result.yaml
  outcomes/
    outcome_record.yaml
    feedback_record.yaml
  policy_learning/
    evidence_bundle.yaml
    update_threshold.yaml
  runtime/
    config_class.yaml
    secret_scope.yaml
    environment_class.yaml
    release_candidate.yaml
  telemetry/
    log_event.yaml
    health_signal.yaml
```

## Registry Names

These registries should be explicit, separate files or managed stores, and never implicit code constants:

- `registries/system_layers.yaml`
- `registries/canonical_terms.yaml`
- `registries/canon_index.yaml`
- `registries/module_manifests.yaml`
- `registries/admitted_domains.yaml`
- `registries/decision_states.yaml`
- `registries/decision_modes.yaml`
- `registries/decision_rights.yaml`
- `registries/delegations.yaml`
- `registries/playbooks.yaml`
- `registries/objective_functions.yaml`
- `registries/thresholds.yaml`
- `registries/triggers.yaml`
- `registries/metrics.yaml`
- `registries/dataset_versions.yaml`
- `registries/feature_set_versions.yaml`
- `registries/training_targets.yaml`
- `registries/evaluation_protocols.yaml`
- `registries/model_artifacts.yaml`
- `registries/checkpoint_families.yaml`
- `registries/monitors.yaml`
- `registries/experiments.yaml`
- `registries/expected_states.yaml`
- `registries/baselines.yaml`
- `registries/result_classes.yaml`
- `registries/release_candidates.yaml`
- `registries/environments.yaml`

## Core Persisted Stores

```text
stores/
  raw_events/
  staging_batches/
  decision_cases/
  progression_events/
  run_events/
  outcomes/
  feedback_records/
  decision_memory/
  policy_learning_evidence/
  monitor_events/
  simulation_runs/
  experiment_results/
  release_events/
  security_events/
  telemetry_events/
  audit_events/
```

## Validation Layers

Validation should be layered and explicit:

1. `schemas/`: static schema validation for every contract and persisted record.
2. `src/platform/validation/`: cross-cutting governance validators.
3. Domain-specific validators inside `src/data/`, `src/state/`, `src/decision/`, `src/models/`, `src/simulation/`, and `src/lifecycle/`.
4. Runtime guardrails inside `src/runtime/` and `src/platform/audit/`.

Critical validators to implement first:

- `contract_schema_validator.py`
- `registry_integrity_checker.py`
- `transition_guard.py`
- `delegation_guard.py`
- `semantic_drift_guard.py`
- `split_scheme_validator.py`
- `label_derivation_guard.py`
- `calibration_guard.py`
- `output_semantic_guard.py`
- `reuse_boundary_guard.py`
- `secret_scope_guard.py`
- `promotion_readiness_gate.py`

## Orchestration Layers

The platform should orchestrate in narrow layers, not one global engine:

- `src/data/ingestion/raw_ingestion_pipeline.py`
- `src/decision/case/case_episode_orchestrator.py`
- `src/decision/router/router_service.py`
- `src/models/runs/training_run_service.py`
- `src/simulation/execution/scenario_execution_service.py`
- `src/lifecycle/outcomes/feedback_realisation_service.py`
- `src/lifecycle/policy_learning/evidence_admission_service.py`
- `src/runtime/release/rollout_scope_controller.py`

## Monitoring Layers

Monitoring should be split by concern:

- `src/runtime/telemetry/health_signal_registry.py`
- `src/models/monitoring/drift_detection_service.py`
- `src/decision/review/backlog_risk_monitor.py`
- `src/runtime/config/config_drift_monitor.py`
- `src/decision/thresholds/threshold_drift_monitor.py`
- `src/platform/audit/lineage_trace_service.py`

## Lifecycle Controllers

The minimum lifecycle controllers are:

- `case_episode_orchestrator.py`
- `progression_manager.py`
- `mode_entry_gate.py`
- `mode_exit_guard.py`
- `outcome_registry.py`
- `feedback_realisation_service.py`
- `decision_memory_store.py`
- `evidence_admission_service.py`
- `update_threshold_engine.py`

## Operator and Reporting Surfaces

These are the first concrete surfaces the codebase should expose:

- `surfaces/operator/decision_ops_surface.py`
- `surfaces/operator/review_queue_surface.py`
- `surfaces/operator/metrics_surface.py`
- `surfaces/operator/simulation_surface.py`
- `surfaces/operator/outcome_surface.py`
- `surfaces/operator/release_ops_surface.py`
- `surfaces/admin/registry_admin_surface.py`
- `surfaces/admin/threshold_config_surface.py`
- `surfaces/admin/environment_admin_surface.py`
- `surfaces/reporting/governance_compliance_reporter.py`
- `surfaces/reporting/drift_report_exporter.py`
- `surfaces/reporting/value_realisation_reporter.py`

## Narrow-Ownership Rules

Keep the following ownership boundaries explicit:

- `src/data/` owns ingestion, staging, canonicalization, and data-quality intake controls.
- `src/state/` owns reusable state definitions, feature semantics, metrics, datasets, and labels.
- `src/decision/` owns decisioning, authority, routing, thresholds, objectives, and outputs.
- `src/models/` owns runs, artifacts, evaluation, and model monitoring.
- `src/simulation/` owns experiments, scenarios, replay, expected-baseline alignment, and simulation outputs.
- `src/lifecycle/` owns outcomes, memory, feedback, policy learning, and end-to-end lifecycle composition.
- `src/runtime/` owns environments, config, release control, telemetry, and runtime boundaries.
- `src/platform/` owns canon-facing governance, registries, glossary, audit, and cross-cutting validation.

Anything that cuts across those boundaries should be expressed as a contract or registry, not as a direct import shortcut.