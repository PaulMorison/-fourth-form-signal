# Live Repo vs Canon Gap Report

## Purpose

This report compares the live repository to the implementation shape required by the core canon.

## Live Repo Snapshot

- Present at repo root: `docs/`
- Present inside `docs/`: architecture canon, glossary, governance decisions, vision docs, Domain 01 contracts, one domain-pattern doc
- Missing at repo root: `src/`, `contracts/`, `registries/`, `schemas/`, `stores/`, `tests/`, `ops/`, `migrations/`
- Detected code/config/runtime files in workspace: none

The repo currently expresses architecture intent, governance intent, and one domain’s documentation. It does not yet implement the platform.

## Major Gaps

| Gap area | What canon requires | What currently exists | What is missing | What should be built first | Severity |
| --- | --- | --- | --- | --- | --- |
| Platform control plane | Machine-readable contracts, registries, glossary enforcement, canon quality gates, audit spine | Markdown canon, glossary doc, governance docs | `contracts/`, `registries/`, `schemas/`, audit event store, registry services, canon guards | Stand up `contracts/`, `registries/`, `schemas/`, and `src/platform/` | Blocker |
| Decision case and lifecycle layer | Decision episodes, state transitions, progression, interruption, resume, lineage | Lifecycle canon only | Case store, orchestrator, transition engine, lifecycle validator, event store | Build `src/decision/case/` and `src/decision/lifecycle/` plus `stores/decision_cases` | Blocker |
| Authority and intervention engine | Decision modes, rights, delegation, routing, playbooks, thresholds, action boundaries | Authority matrix doc only | Authority registry, override guard, routing engine, playbook registry, threshold service | Build `src/decision/mode/`, `src/decision/rights/`, `src/decision/router/`, `src/decision/playbooks/`, `src/decision/thresholds/` | Blocker |
| Ingestion and canonicalization stack | Raw source intake, staging, canonical entities, transformation legitimacy, source-of-truth controls | No runtime data pipeline | Connectors, raw event store, staging manager, canonicalization service, storage registry | Build `src/data/ingestion/`, `src/data/canonical/`, `src/data/storage/`, `stores/raw_events` | Blocker |
| Feature, dataset, and metric governance | Feature registry, formulas, dataset versions, metric definitions, semantic drift detection | Definitions exist only in canon | Feature registry, dataset registry, formula validator, metric registry, drift guards | Build `src/state/features/`, `src/state/datasets/`, `src/state/metrics/` | Blocker |
| Training and evaluation discipline | Labels, targets, split protocols, validation gates, regression detection, holdouts | No model or evaluation code | Label derivation service, split validator, holdout guard, regression detector, validation evidence store | Build `src/state/targets/` and `src/models/evaluation/` | Blocker |
| Model run and artifact governance | Training and scoring execution, model artifact registry, checkpoint families, rollback-safe versions | No model execution stack | Run services, artifact registry, deployment version store, rollback checker | Build `src/models/runs/` and `src/models/artifacts/` | Blocker |
| Simulation and experimentation layer | Experiment registry, scenario execution, replay, expected-baseline alignment, simulation outputs | Domain 01 simulation design doc only | Experiment workbench, scenario execution service, baseline registry, replay guard, result registry | Build `src/simulation/` and simulation contracts | Risk |
| Outcome and decision memory spine | Outcomes, feedback realization, decision memory, reusable retrieval, policy-learning evidence | Domain 01 execution/post-mortem and policy-learning docs only | Outcome store, feedback service, decision memory store, evidence admission gate, update threshold engine | Build `src/lifecycle/outcomes/`, `src/lifecycle/memory/`, `src/lifecycle/policy_learning/` | Blocker |
| Operator surfaces | Review queues, decision dashboards, release dashboards, metric surfaces, simulation consoles | No executable surfaces | Operator UI modules, API handlers, reporting exporters, alert feeds | Build `src/surfaces/operator/`, `src/surfaces/admin/`, `src/surfaces/reporting/` | Risk |
| Runtime governance | Environment registry, config registry, secret scopes, release control, rollout and rollback gates | No runtime layer | Config service, environment boundary guards, release registry, rollout controller, rollback triggers | Build `src/runtime/config/`, `src/runtime/deployment/`, `src/runtime/release/` | Blocker |
| Observability and monitoring | Governed logs, traces, health signals, drift detection, signal-quality surfaces | No telemetry or monitoring code | Telemetry emitters, monitor registry, health signals, alert guards, drift services | Build `src/runtime/telemetry/` and `src/models/monitoring/` | Risk |
| Capability lifecycle and value retention | Capability registry, retention decisions, decommission and reactivation logic | Canon docs only | Capability lifecycle service, retention-value service, decommission workflow | Build `src/platform/governance/` capability services | Refinement |
| Test and migration infrastructure | Contract tests, unit tests, lifecycle tests, release tests, migrations | No test or migration folders | Test harness, fixtures, seed registries, schema migration scripts | Build `tests/` and `migrations/` as soon as registries and stores exist | Blocker |

## Repo-Accurate Interpretation of Status

### What is actually implemented today

- Canon source of truth in `docs/architecture/core`
- Shared object canon in `docs/architecture/objects`
- Boundary and interface canon in `docs/architecture/boundaries` and `docs/architecture/interfaces`
- One domain pattern and one domain documentation set
- Governance decision templates and authority matrix
- Canonical glossary and vision docs

### What is only partially implemented today

- Canon navigation and canon change control as human-readable governance, not executable gates
- Glossary as a document, not an enforceable registry
- Domain admission as manual documentation, not an admission workflow
- Authority mapping as a document, not an executable authority service
- System layers as a reference document, not an enforced dependency map

### What is missing today

- All executable platform modules
- All machine-readable contracts
- All registry files
- All persisted event stores and state stores
- All validation code
- All runtime checks and monitors
- All operator-facing surfaces
- All audit output pipelines

## What Should Be Built First

1. `contracts/`, `registries/`, `schemas/`, and `src/platform/` for the control plane
2. `src/decision/case/` and `src/decision/lifecycle/` for case and progression orchestration
3. `src/data/ingestion/`, `src/data/canonical/`, and `src/data/storage/` for trustworthy source data
4. `src/state/features/`, `src/state/datasets/`, `src/state/metrics/`, and `src/state/targets/` for governed reusable state
5. `src/models/evaluation/` and `src/platform/validation/` for leakage-safe validation before model or simulation rollout

## Blocker, Risk, and Refinement View

### Blockers

- No executable control plane
- No decision case orchestration layer
- No ingestion or canonicalization stack
- No state, feature, dataset, or target governance code
- No validation, regression, or evaluation code
- No runtime or release control code
- No persisted stores, registries, or tests

### Risks

- Simulation stack absent despite being central to the architecture thesis
- No operator surfaces for review, escalation, or release control
- No monitoring, telemetry, or drift controls
- No outcome and feedback services to support learning loops

### Refinements

- Capability retention and value-realisation controls can follow once the platform has executable capabilities to retain or retire
- Prompt asset and implementation-agent controls become important once generated code and prompt libraries enter the repo
- Performance tuning follows after first functional end-to-end flows exist

## Implementation Consequence

The canon is structurally complete, but the live repo is still pre-implementation. The next build should not start with a domain-specific model or dashboard. It should start with the shared control plane, decision-case spine, ingestion stack, and state-governance modules that make every later domain and operator surface canon-safe.