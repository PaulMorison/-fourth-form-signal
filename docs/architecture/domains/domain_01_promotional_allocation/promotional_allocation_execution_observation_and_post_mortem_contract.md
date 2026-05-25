# Governed Execution Observation and Post-Mortem Contract for Promotional Allocation Domain 01

## Purpose of This Document

This document defines how Promotional Allocation observes execution, captures deviations, evaluates realized outcomes, and produces governed post-mortem learning artifacts after a recommendation has been issued.

It exists because a decision platform does not become trustworthy merely by producing disciplined recommendations. It becomes trustworthy only when it can compare what it expected with what actually happened, distinguish recommendation weakness from execution weakness, assess overrides seriously, and convert realized reality into reusable institutional learning.

Without explicit control at this stage, the platform drifts into recommendation without accountability, shallow outcome review, vague retrospectives, weak override assessment, and learning behavior that becomes anecdotal instead of structural.

This document is therefore a control document for execution observation, outcome interpretation, and post-decision learning.

It defines what must be observed after recommendation issuance, how deviations must be recorded, what a valid outcome object must contain, what a valid post-mortem object must contain, how post-mortem judgments must be categorized, how hidden failure states must still be reviewed after action, and how learning must be handed back into the core platform.

It is the canonical execution observation and post-mortem contract for Domain 01. Future execution tracking, outcome attribution, override review, and post-decision learning logic for promotional allocation must align with it unless a formal decision record explicitly revises it.

## Role of This Document in the Platform

This document governs the back half of the Domain 01 decision loop.

The domain model defines the decision and outcome objects. The simulation document defines how counterfactual consequences should be estimated before commitment. The workflow document defines how a recommendation package is formed and handed forward. This document governs what happens after recommendation issuance: what evidence is captured, how observed reality is interpreted, how recommendation quality is judged against execution reality, and how learning is converted into durable artifacts for future cycles.

In practical terms, this document governs five things.

- What post-recommendation evidence must be observed.
- How execution deviation must be recorded.
- What makes an outcome object valid.
- What makes a promotion post-mortem object valid.
- How learning flows back into memory, causal reasoning, simulation calibration, policy learning, and workflow refinement.

This document therefore governs accountability after action, attribution discipline, and institutional learning quality.

## Core Thesis

In Promotional Allocation, disciplined post-decision learning requires the platform to observe what was recommended, what was approved, what was actually executed, what operating conditions truly occurred, and what commercial outcomes followed, so that recommendation quality, execution quality, override quality, and environmental change can be judged separately and translated into governed learning artifacts.

That is the core thesis.

The platform must learn from reality, not merely from the consistency of its own reasoning.

## What This Contract Is and Is Not

A governed execution-observation and post-mortem contract is a controlled framework for capturing realized reality after a recommendation, attributing the gap between expectation and outcome, and converting that gap into reusable learning.

It is not any of the following.

- It is not a generic after-action commentary process.
- It is not a dashboard of realized results disconnected from the original recommendation and execution path.
- It is not a hindsight exercise that erases what the system knew at decision time.
- It is not a simple win-loss scorecard for recommendations.
- It is not a process that treats positive headline results as proof that the decision was sound.
- It is not a reporting mechanism that exposes broader network learning context beyond tenant entitlement.

The contract is governed only if it preserves the original decision context, records what actually happened in execution, distinguishes different sources of miss or success, and produces learning objects that future decisions can reuse.

## Execution Observation at a Glance

After a recommendation package is issued, Domain 01 should move through the following major stages.

1. The issued recommendation package is fixed as the reference point for later observation.
2. Approval and override behavior are recorded.
3. The action actually executed is captured.
4. The operating conditions that actually occurred during execution are observed.
5. Realized outcomes are observed across the relevant horizon.
6. Distortion effects and hidden failure-state signals are reviewed, not just headline performance.
7. Execution deviations are recorded against the original recommendation.
8. Outcome objects are assembled for the relevant scope.
9. A governed post-mortem object is produced.
10. Learning is handed back into memory, causal reasoning, simulation, policy learning, and workflow refinement.

This is the default observation and learning flow for Domain 01.

## What Must Be Observed

Every material promotional decision must generate post-recommendation observation evidence.

At minimum, the platform must observe the following classes of evidence.

### Recommended action

The exact action recommended by the system must be preserved as the primary reference point for later evaluation.

### Final executed action

The action actually carried out in the relevant scope must be captured, including whether the recommendation was followed fully, followed partially, delayed, altered, or not followed.

### Override state

The platform must observe whether override occurred, what form it took, who authorized it, and whether the final action path differed because of that override.

### Execution conditions

The actual operating conditions under which the promotion ran must be captured, including timing, readiness, process compliance, local operational friction, and any meaningful difference between assumed and realized execution conditions.

### Store-specific stock reality at execution

For store-level or local rollout evaluation, the platform must capture what stock reality actually existed at execution time, including availability, replenishment quality, stock exposure, and any stock shortfall or distortion that materially affected outcome interpretation.

### Store-specific execution quality

The platform must observe whether the store actually executed the intervention at the level assumed by the recommendation or simulation, including signage, display, timing, participation quality, and local compliance.

### Realized commercial outcomes

The platform must observe the realized commercial consequences across the relevant horizon, including units, revenue, payoff quality, margin quality, stock consequences, and any other domain-relevant outcome measures.

### Realized distortion effects where observable

Where the evidence permits, the platform must capture realized distortion patterns such as pull-forward, cannibalization, substitution, stock distortion, or apparent uplift without durable strength.

### Review timing and observation windows

The platform must define when the outcome is being observed, what horizon is being judged, and whether the present observation is interim, primary, or later-stage review. Timing matters because early promotional movement may conceal later weakening.

Observation is therefore not one metric drop after execution. It is a governed evidence bundle tied to the original decision episode.

## Observation Scope

Execution and outcome observation in Domain 01 must operate across multiple scopes without collapsing tenant boundaries.

### Store promotion instance scope

The store promotion instance is the primary local observation object. This is the level at which execution conditions, stock reality, local response, and local deviation are most directly visible.

### Store-group scope

Where a decision applies to a coordinated group of stores, the platform must also support governed store-group observation. This is useful for rollout quality, subgroup execution patterns, and aggregate outcome review where the decision scope itself is group-based.

### Client-group scope

Where decision packages are issued for a client group, the platform must support client-group aggregation and client-group post-mortem review within the reporting entitlements of that client context.

### Network learning scope

The platform may also assemble broader learning-scope outcome evidence where governance permits. This broader scope exists for learning, calibration, and policy improvement. It must not be casually exposed in client-facing reporting.

Observation scope therefore has the same structural separation as decision workflow.

Decision scope determines what action was being judged.

Reporting scope determines what post-decision outputs may be shown.

Learning scope determines what broader realized evidence may be reused for future improvement.

These scopes must remain separate.

## Execution Deviation Contract

The platform must record deviation explicitly rather than relying on informal interpretation after the fact.

Every material decision episode in Domain 01 must record the differences between the following.

### What was recommended

The original system recommendation, as issued in the final recommendation package.

### What was approved

The action formally accepted, approved, or authorized for execution, including any human override, deferral, or scope alteration applied before execution.

### What was actually executed

The action actually carried out in practice, including partial execution, timing drift, scope drift, local exclusion, execution shortfall, or operational failure.

### What operating conditions actually occurred

The real execution environment, including stock conditions, readiness, local friction, compliance quality, and any operating deviation from the assumptions embedded in the recommendation or simulation.

The deviation contract should therefore capture at least four classes of gap.

- Recommendation-to-approval gap.
- Approval-to-execution gap.
- Execution-plan-to-execution-condition gap.
- Expected-condition-to-realized-condition gap.

If these gaps are not recorded clearly, the platform cannot distinguish weak recommendation logic from weak delivery reality.

## Outcome Object Contract

Every valid Domain 01 outcome object must contain enough information to support outcome interpretation, later aggregation, and formal post-mortem review.

At minimum, a valid outcome object must contain the following.

### Decision case reference

A link to the original promotion decision case.

### Recommendation reference

A link to the recommendation package that preceded execution.

### Executed action reference

A reference to the action that was actually carried out or observed in practice.

### Tenant and client scope

The tenant, client group, and reporting scope within which the outcome object is valid and may be shown.

### Store promotion instance reference where relevant

The relevant store promotion instance or other scoped promotional entity being observed.

### Observation horizon

The horizon over which the outcome is being measured, including whether the record is interim, primary, or later-stage outcome observation.

### Realized units, revenue, and margin quality where relevant

The main realized commercial outputs relevant to the scope, including visible movement and quality of payoff.

### Stock consequences

Observed stock effects, including stock depletion, stock stress, replenishment consequences, availability gaps, or any stock pattern that materially alters outcome interpretation.

### Execution notes or execution condition state

The execution conditions that actually occurred, including compliance quality, readiness, scope fidelity, timing quality, and any local operating friction that affected interpretation.

### Distortion indicators where observable

Observable evidence of pull-forward, substitution, cannibalization, stock distortion, or other mechanisms that may make visible results misleading.

### Realized failure-state signals

Any observed signal that false continuation, hidden decay, local optimization failure, execution heterogeneity, or post-promotion weakness may be present.

### Uncertainty notes where outcome interpretation remains weak

Any unresolved missingness, lag, contradiction, or observability limits that still weaken confident interpretation of the outcome.

The outcome object is therefore not merely a realized metric record. It is a structured post-decision reality object.

## Post-Mortem Object Contract

Every material promotional decision should produce a promotion post-mortem object strong enough to support governed learning.

At minimum, a valid promotion post-mortem object must contain the following.

### What the system expected

The key expected consequences recorded at decision time, including expected action effect, expected payoff quality, expected risk conditions, and where relevant simulation expectations.

### What actually happened

The realized execution path and the observed commercial outcome across the relevant horizon.

### What changed in execution

A clear statement of how actual execution conditions, scope, timing, stock reality, or local operating conditions differed from what the recommendation or simulation assumed.

### Whether override occurred

A recorded statement of whether human override took place and whether it changed the action path.

### Whether the recommendation was followed

A clear statement of whether the recommendation was followed fully, partially, or not at all.

### Primary attribution judgment

A governed judgment about whether the main issue arose from state reading, simulation quality, causal understanding, constraint logic, execution failure, regime shift, or local context gap.

### Outcome judgment category

A classification selected from the governed post-mortem judgment categories defined in this document.

### Evidence quality for the judgment

A statement of how strong or weak the post-mortem evidence is, especially where outcome attribution remains uncertain.

### What the system should learn next

A structured learning direction identifying what should be updated or reviewed in memory, causal reasoning, simulation calibration, workflow rules, or policy logic.

The post-mortem object must preserve enough structure that future decisions can reuse it as institutional memory rather than treat it as narrative commentary.

## Post-Mortem Judgment Categories

Post-mortem judgments in Domain 01 must use a governed set of categories.

### Correct recommendation, correct execution

The recommendation was sound for the decision-time evidence, the action was executed materially as intended, and the outcome broadly aligned with disciplined expectation.

### Correct recommendation, weak execution

The recommendation was sound, but poor execution quality, timing failure, scope drift, or local operating weakness materially degraded the outcome.

### Correct recommendation, regime changed

The recommendation was sound under the decision-time state, but the environment shifted materially enough after commitment that the realized outcome diverged.

### Weak recommendation, good execution

Execution was materially sound, but the recommendation itself was weak relative to the state, constraints, or feasible alternatives.

### Weak recommendation, weak causal logic

The recommendation failed because the platform's intervention reasoning was materially incomplete, distorted, or mis-specified.

### Weak recommendation, poor local-state capture

The recommendation failed because important local stock, demand, execution, or exception context was absent or underrepresented.

### Weak recommendation, simulation miss

The recommendation relied on simulation that materially misjudged outcome behavior, local deformation, or uncertainty.

### Weak recommendation, constraint miss

The recommendation treated the action as more feasible or acceptable than real commercial, stock, execution, financial, or governance constraints allowed.

### Override improved outcome

The override materially improved the outcome relative to the original system recommendation under the realized conditions.

### Override worsened outcome

The override materially degraded the outcome relative to what the original recommendation would likely have achieved or protected against.

### Insufficient evidence for confident judgment

The available post-decision evidence is too weak, incomplete, or contradictory to support a strong attribution judgment.

These categories are meant to govern attribution quality, not to reduce learning to simplistic pass-fail labels.

## Override Outcome Assessment

Overrides must be judged seriously after the fact without erasing the original system view.

The platform should evaluate override outcomes by preserving three separate references.

- The original system recommendation.
- The overridden approved action.
- The action actually executed under real conditions.

Post-mortem review of override should then ask the following.

- Did the override change the decision scope, timing, or participation logic?
- Did the override rely on local context the system did not possess?
- Did the override improve execution feasibility or commercial result?
- Did the override merely benefit from luck under weak reasoning?
- Did the override expose a recurring system blind spot that should be learned structurally?

Override assessment must not turn the final outcome into proof that the override was automatically justified. A favorable result may still have come from a weak decision path. Likewise, an override that worsened outcome may still reveal a legitimate missing context problem if the system had not represented the local reality adequately.

Override review should therefore judge both outcome consequence and information consequence.

## Execution vs Recommendation Failure Distinction

The platform must distinguish different sources of miss rather than collapsing all poor outcomes into recommendation error.

### Recommendation error

The system chose the wrong action given the decision-time evidence, even if execution later matched the recommendation.

### Execution error

The recommended action may have been sound, but the action was delivered poorly, partially, late, or under materially weaker execution conditions than assumed.

### Environment shift

The recommendation may have been sound at decision time, but the relevant regime, demand context, stock reality, or operating environment changed materially after commitment.

### Information gap

The recommendation quality was weakened because materially relevant information was missing, delayed, contradictory, or outside the system's accessible context.

### Causal misunderstanding

The system misread the mechanisms connecting the promotion to the outcome, producing the wrong intervention logic.

### Simulation miss

The system relied on counterfactual estimates that materially misrepresented local deformation, second-order effects, or uncertainty.

### Constraint miss

The system failed to represent a real commercial, operational, stock, financial, or governance constraint strongly enough before recommendation.

These categories should be applied explicitly in post-mortem review so the platform learns the right lesson from the right source of miss.

## Hidden Failure-State Observation

Post-decision review in Domain 01 must continue looking for hidden failure states even when headline performance appears acceptable.

### False continuation

The post-mortem must assess whether visible promotional movement continued while underlying payoff quality, demand health, or durable commercial force weakened.

### Hidden decay

The review must assess whether the decision preserved visible activity while deeper commercial weakening continued beneath the surface.

### Stock-distorted interpretation

The review must test whether apparent outcome quality was materially shaped by stock artifacts, replenishment distortion, or availability constraints rather than genuine commercial improvement.

### Local optimization failure

The review must assess whether local success was achieved at the expense of broader network economics, margin quality, proposition integrity, or later commercial health.

### Execution heterogeneity

The review must assess whether store-level execution variation materially changed the realized outcome pattern across the one-to-many structure.

### Post-promotion weakness

The review must assess whether apparently positive short-term results were followed by weakening conditions after the promotion window, indicating fragile uplift or distortion rather than durable value.

The purpose of post-decision review is therefore not only to record outcomes. It is to interpret whether the outcome itself may still be misleading.

## Tenant-Safe Learning Rules

Post-mortem learning in Domain 01 may use broader realized evidence where governance permits, but client-facing reporting must remain scoped and safe.

At minimum, the platform must obey the following rules.

- Learning scope and reporting scope must remain distinct after action just as they do before action.
- Broader network outcome evidence may be used for calibration, causal revision, policy learning, and simulation improvement only where learning permission allows.
- Client-facing post-mortem outputs must remain restricted to the authorized store, store group, or client group reporting scope.
- Comparative outcome review must remain benchmark-safe, aggregated, and entitlement-aware.
- Cross-store learning may be permitted while cross-store reporting remains restricted.
- Cross-brand transfer in learning must remain governed by brand validity and access-control policy.

Tenant-safe learning is not a reporting cleanup step. It is part of the learning contract itself.

## Learning Handoff Rules

Post-decision learning in Domain 01 must be handed back into the core platform in structured form.

### Graph-backed memory

The system must add new outcome relationships, execution context, override context, and decision-to-outcome links so future retrieval preserves what happened in this decision episode.

### Persistent decision memory

The system must store the decision case, recommendation package, override state, execution deviation record, outcome object, and post-mortem object as a reusable historical decision episode.

### Causal DAG revision

The system must use post-mortem evidence to strengthen, weaken, or qualify the intervention pathways it currently assumes matter.

### Simulation calibration

The system must compare simulated expectations with realized outcomes and update calibration, uncertainty ranges, local deformation handling, and scenario validity accordingly.

### Policy learning

The system must use governed post-mortem outcomes to refine policy behavior, especially where repeated decisions reveal execution-sensitive patterns, local context gaps, or systematic override effects.

### Recommendation workflow refinement

The system must use post-mortem evidence to improve simulation-trigger rules, escalation thresholds, abstention discipline, explanation quality, and other workflow behaviors where repeated misses indicate structural weakness.

Learning handoff is complete only when these updates are possible in structured form.

## Observation and Post-Mortem Failure Modes

Weak observation and post-mortem discipline creates direct platform risk.

### No distinction between recommendation and execution failure

The platform treats every poor outcome as a recommendation failure or every good outcome as a recommendation success, preventing accurate learning.

### No structured override review

Overrides are recorded superficially or not at all, so the platform cannot tell whether humans are correcting real blind spots or introducing avoidable degradation.

### No tenant-safe learning boundary

Broader outcome evidence is reused or exposed without clear distinction between learning permission and reporting entitlement.

### Vague post-mortems

Post-mortem review produces narrative explanation without formal fields, governed categories, or reusable attribution structure.

### No reusable learning artifacts

Outcome review occurs informally, but the system does not create durable outcome objects or post-mortem objects that future decisions can query or learn from.

### False confidence from headline results alone

The platform treats visible units or revenue movement as sufficient proof of success while ignoring margin weakness, distortion, post-promotion weakness, or broader commercial damage.

### Over-aggregation of observed outcomes

One-to-many promotion outcomes are averaged so aggressively that store-level execution heterogeneity and local failure patterns disappear.

### Post-decision blindness

The platform produces recommendations repeatedly but fails to observe, interpret, and learn from what happened after action in a structured and governed way.

These are not minor reporting issues. They are ways the platform can remain active while becoming institutionally unintelligent.

## Non-Negotiables

1. The platform must learn from realized reality, not only from modeled expectations.
2. Recommendation quality and execution quality must be judged separately.
3. A good recommendation may still fail under weak execution.
4. A weak recommendation may still look good temporarily.
5. Every material decision must produce structured observation evidence.
6. Every material decision must support an outcome object and a governed post-mortem object.
7. Override outcomes must be evaluated without erasing the original system recommendation.
8. Hidden failure states must still be reviewed after apparently positive outcomes.
9. Learning scope and reporting scope must remain distinct after action.
10. Tenant-safe learning is mandatory.
11. Post-mortem judgments must use governed categories rather than informal narrative alone.
12. Learning handoff must update memory, causal reasoning, simulation, policy, and workflow discipline.

## Closing Statement

This document protects the platform from becoming a system that recommends intelligently in theory but learns weakly in practice.

In Domain 01, that risk is especially serious because one network promotion can produce many local execution realities, many local outcome patterns, and many ways for apparent success to conceal deeper weakness.

If this contract remains intact, Promotional Allocation can learn from action with discipline, preserve the difference between decision quality and delivery quality, evaluate overrides honestly, and compound institutional intelligence over time.

If it weakens, the platform will produce recommendations faster than it becomes wiser.