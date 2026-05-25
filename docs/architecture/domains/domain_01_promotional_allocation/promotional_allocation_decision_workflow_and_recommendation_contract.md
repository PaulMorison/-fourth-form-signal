# Governed Decision Workflow and Recommendation Contract for Promotional Allocation Domain 01

## Purpose of This Document

This document defines how Promotional Allocation moves from decision context to governed recommendation output.

It exists because a decision platform can drift even when the domain model and simulation logic are strong. If the workflow from state to action is left implicit, the platform eventually accumulates ad hoc recommendation behavior, uneven use of simulation, weak escalation discipline, inconsistent override handling, and client-facing outputs that are difficult to trust or operationalize.

This document is therefore a control document for decision workflow and recommendation structure.

It defines how a promotion decision case is created, how it progresses through the platform, when simulation is required, what classes of recommendation are valid, what every recommendation package must contain, how outputs must remain tenant-safe, and what must be handed forward into execution observation and post-decision learning.

It is the canonical workflow and recommendation contract document for Domain 01. Future workflow design, recommendation objects, delivery logic, override handling, and post-mortem integration for promotional allocation must align with it unless a formal decision record explicitly revises it.

## Role of This Document in the Platform

This document governs the operational flow of Domain 01 after the domain objects, interpreted state, and simulation capability already exist.

The strategy and conceptual documents explain why the platform exists. The constitution governs how it must behave under uncertainty and constraint. The architecture defines the system stack. The promotional allocation domain model defines the domain objects. The simulation document governs counterfactual design. This document governs how those components are assembled into a real decision process that ends in a usable, inspectable, client-scoped recommendation package.

In practical terms, this document governs five things.

- How a promotion decision case is formed.
- How the workflow moves from intake through interpretation, simulation, optimization, constitutional review, and recommendation compilation.
- What classes of output are valid when the platform is not ready to recommend immediate action.
- What every recommendation package must contain before it is allowed to influence action.
- How recommendations, overrides, execution records, and post-mortem learning artifacts connect as one reconstructible decision loop.

This document therefore governs workflow discipline, recommendation validity, delivery safety, and operational usability.

## Core Workflow Thesis

In Promotional Allocation, a valid decision should flow from an explicit promotion decision case, through governed context assembly and state interpretation, into constitutionally controlled action evaluation, and finally into a client-scoped recommendation package that is explainable, constraint-aware, uncertainty-aware, reconstructible after the fact, and ready for execution observation and post-mortem learning.

That is the core thesis.

The workflow is not meant to produce the fastest answer. It is meant to produce the most disciplined usable answer the platform can justify under the real decision conditions.

## What This Workflow Is and Is Not

A governed decision workflow in this platform is a controlled progression from decision context to action recommendation in which state interpretation, uncertainty handling, failure-state review, simulation discipline, optimization, constitutional control, explanation, override, and learning all remain visible.

It is not any of the following.

- It is not a score-emission process that turns a model output into an action label.
- It is not a thin ranking layer placed on top of incomplete state interpretation.
- It is not a workflow that assumes every case should end in immediate action.
- It is not a recommendation engine that bypasses simulation under high uncertainty or high consequence.
- It is not a reporting pipeline that leaks broader learning context into unauthorized client-facing output.
- It is not an opaque automation path in which override, escalation, waiting, or abstention are treated as failures instead of valid decision outcomes.

The workflow is governed only if it preserves decision scope, respects the difference between learning scope and reporting scope, and produces outputs fit for serious operating use.

## Decision Workflow at a Glance

Promotional Allocation decisions should move through the following major stages.

1. A promotion decision case is created for a defined decision scope.
2. The platform assembles the relevant promotion objects, local state, graph context, constraint profile, and knowledge-quality condition.
3. The platform interprets the current commercial state.
4. Failure-state logic tests for hidden weakness, distortion, false continuation, local optimization risk, or other governing concerns.
5. Causal review examines the intervention pathways that matter.
6. The workflow decides whether simulation is required, should be bypassed, or should itself be the recommendation.
7. Candidate actions are generated for the specific decision scope.
8. Optimization ranks or selects feasible actions under constraints, uncertainty, and simulation-informed consequences.
9. Constitutional review determines whether the system may recommend, wait, simulate first, gather more information, abstain, or escalate.
10. The decision compiler assembles the final recommendation package and explanation.
11. The package is delivered only within authorized client or tenant scope.
12. Any override is captured without erasing the original system view.
13. Execution is observed and linked back to the original decision case.
14. A governed handoff is made into post-mortem learning.

This sequence is the default control flow for Domain 01.

## Decision Case Creation

The workflow begins with a promotion decision case.

The promotion decision case is the formal object that binds the current decision episode into one governed unit. No recommendation should be produced for Domain 01 unless a decision case exists.

### Decision scope

The case must define the exact decision scope under evaluation. In this domain, decision scope may be one store promotion instance, a defined store group rollout, a client-group allocation decision, or another governed promotional decision unit.

Decision scope must be explicit because the correct action may differ sharply across stores even when the network promotion is shared.

### Promotion instance references

The case must reference the relevant network promotion and promotion instance so the intervention under review is structurally clear. The workflow must not reason about promotion decisions using only informal campaign labels or general calendar context.

### Store promotion instance references

Where the decision involves local rollout, inclusion, exclusion, deferral, or differentiated participation, the case must reference the specific store promotion instances or governed groups of store promotion instances under consideration.

### Tenant and client scope

The case must state the tenant and client scope in which the decision is being made and the reporting scope within which outputs may later be shown. Learning scope may be broader where governance permits, but it must not be silently substituted for client scope.

### Local state context

The case must bind the local state objects that materially shape the decision, including store-specific stock reality, demand context, execution state, relevant local override state, and other domain-valid local signals.

### Constraint profile

The case must include a coherent constraint profile containing commercial, stock and replenishment, financial, execution, banner or brand, and tenant or governance constraints relevant to the scope.

### Current uncertainty and knowledge-quality condition

The case must include the current knowledge-quality state, including missingness, lag, contradiction, freshness, and observability limits. If the platform is partially blind, the decision case must carry that blindness forward explicitly.

The decision case is therefore not a convenience wrapper. It is the formal starting point that makes downstream reasoning inspectable and reconstructible.

## Decision Workflow Stages

### 1. Case intake

The workflow begins by accepting or initiating a promotion decision case for a specific decision window.

At intake, the platform should confirm that the case is real, that the decision scope is defined, that the relevant promotion objects are identifiable, and that the request is within authorized tenant and client boundaries. If those minimum conditions are not met, the workflow should not proceed as though the case were valid.

### 2. Context assembly

Once intake is accepted, the platform assembles the full context required for decision-quality work. That includes promotion objects, local state, graph-backed memory, decision history, relevant store-group or network context, constraint profiles, reporting entitlement context, and current knowledge-quality signals.

Context assembly should also distinguish clearly between what the platform may learn from, what it may use in internal reasoning, and what it may later expose in a client-facing recommendation package.

### 3. State interpretation

The platform then interprets the current commercial state for the defined scope.

This includes reading the state through feature-state objects, distortion-aware signals, surface or manifold geometry, and prior contextual memory. The purpose of this stage is not simply to produce descriptive metrics. The purpose is to determine the commercial condition that action would be acting on.

### 4. Failure-state review

The workflow must then test whether the case is affected by failure-state patterns such as false continuation, stock-distorted interpretation, partial observability, regime mismatch, local optimization failure, or memory weakness.

Failure-state review is not optional extra caution. It changes how aggressively the workflow may move toward recommendation.

### 5. Causal review

The workflow must examine the main causal mechanisms believed to matter for the intervention. In Promotional Allocation, this includes the pathways through which promotion mechanics, customer response, stock availability, execution quality, timing, and margin consequences interact.

Causal review does not require complete certainty. It requires explicit intervention logic strong enough to support explanation and counterfactual reasoning.

### 6. Simulation trigger or bypass decision

The workflow must then determine whether the case requires simulation before recommendation, may bypass simulation responsibly, or should itself produce a simulation-first output.

This is a governed branch point. The platform should not slide into simulation by habit, and it must not bypass simulation casually when the case is high-stakes, cross-linked, or locally heterogeneous.

### 7. Candidate action generation

For the defined decision scope, the workflow must generate a feasible action set. The set should include not only different promotional activation choices, but also waiting, requesting more information, escalation, and abstention where those are valid governed outcomes.

Candidate actions should be specific enough to be operationally meaningful. Generic labels without scope, timing, or condition do not qualify.

### 8. Optimization

The platform then evaluates and ranks feasible actions using constraint-aware, uncertainty-aware, and where relevant simulation-informed consequence estimates.

Optimization in this domain must seek decision quality and durable commercial value rather than narrow visible movement. An action that is attractive only under fragile assumptions or unrealistic execution should not emerge as the preferred candidate.

### 9. Constitutional review

The constitution layer must then determine whether the preferred action is valid, whether confidence is justified, whether simulation or waiting is required, and whether escalation or abstention is the disciplined outcome.

This stage has authority to block a superficially attractive recommendation if the uncertainty, contradiction, feasibility, failure-state risk, or explanation quality is too weak.

### 10. Recommendation compilation

If the case survives constitutional review, the decision compiler assembles the recommendation package.

This stage converts ranked action logic into a formal recommendation object with explanation, confidence position, supporting evidence, constraints, warnings, alternatives, monitoring conditions, and references to the relevant decision case and versioned inputs.

### 11. Client-scoped delivery

The compiled package must then be rendered only within the reporting scope authorized for the tenant, client group, store group, store, or role receiving it.

Client-scoped delivery is part of recommendation validity. A package that contains unauthorized comparative detail is not a valid final output.

### 12. Override capture

If a human operator overrides the recommendation, the workflow must record the original system recommendation, the chosen action, the role of the override decision-maker, the rationale for the override, and the expected review conditions.

Override capture must preserve both the system view and the human intervention as separate parts of the same decision episode.

### 13. Execution observation

After action, the workflow must observe what actually happened. That includes whether the recommendation was followed, delayed, partially executed, or locally adjusted, as well as the actual execution conditions, stock conditions, and realized outcomes.

Execution observation is required because recommendation validity cannot be judged only on the package issued. It must be linked to the conditions under which the action was actually carried out.

### 14. Post-mortem learning handoff

The final workflow stage is a governed handoff into post-decision learning. The system must pass forward the full decision case, the final recommendation package, any override, execution conditions, observed outcomes, and the references needed to compare expected and realized consequences.

The workflow is not complete until that handoff is possible.

## When Simulation Is Required

Simulation is required when the platform cannot responsibly move from interpreted state to action recommendation without testing how the action may deform the commercial system.

In Domain 01, a decision must pass through simulation before authoritative recommendation when one or more of the following conditions apply.

- The action is high-stakes or materially costly.
- The action is materially irreversible or difficult to unwind.
- The case spans multiple stores, store groups, or other one-to-many structures where local variation may change the correct answer.
- The likely outcome is sensitive to second-order effects such as stock distortion, pull-forward, cannibalization, or execution variability.
- The case contains meaningful contradiction, partial observability, or weak causal coverage that can be better disciplined by counterfactual testing.
- The network promotion appears attractive at aggregate level but the local state suggests heterogeneous risk.
- Store inclusion, exclusion, delay, or differentiated participation are live alternatives.
- A local override condition would materially alter the likely outcome.
- A failure-state pattern suggests that visible movement may not reflect durable payoff quality.

Simulation may be bypassed only when the intervention is sufficiently bounded, the state is sufficiently coherent, the local variation is not material to the decision, the constraints are clear, and the constitution layer permits direct recommendation.

Where simulation is required but cannot yet be run credibly, the valid output is not forced action. It is usually simulation first, gather more information, wait, escalate, or abstain.

## Recommendation Action Classes

The workflow must support a defined set of recommendation action classes.

### Recommend act now

The platform recommends immediate action when the decision scope is clear, the case is sufficiently interpretable, the preferred action is feasible, and the expected payoff is robust enough to justify commitment now.

### Recommend wait

The platform recommends waiting when a short delay is likely to improve visibility, reduce distortion, clarify feasibility, or protect against premature commitment under weak evidence.

### Recommend simulate first

The platform recommends simulation first when counterfactual testing is the disciplined next step before action can be justified.

### Recommend gather more information

The platform recommends further information gathering when the main obstacle to decision quality is identifiable missing data, unresolved execution reality, or another remediable information gap.

### Escalate for human review

The platform escalates when the trade-off is materially policy-laden, the downside asymmetry is severe, the contradiction remains substantial, or the platform lacks the context needed to govern the case with authority.

### Abstain from strong recommendation

The platform abstains when it cannot justify a strong directional recommendation after considering uncertainty, feasibility, contradiction, and constitutional rules. Abstention is a governed output, not a system failure.

These classes are first-class outputs of the workflow. The system must not behave as though only act now is real and everything else is a degraded substitute.

## Recommendation Contract

Every valid recommendation package in Domain 01 must satisfy a recommendation contract.

The package is valid only if it contains enough information to support operating use, governance, auditability, and later reconstruction.

At minimum, every recommendation package must contain the following.

### Recommendation ID

A unique recommendation identifier linking the package to the decision case, downstream execution records, overrides, and post-mortem artifacts.

### Decision scope

A clear statement of the exact decision scope to which the recommendation applies.

### Client and tenant scope

The tenant, client group, and reporting scope within which the package is valid and may be shown.

### Related promotion objects

References to the relevant network promotion, promotion instance, and where applicable the specific store promotion instances or store groups under recommendation.

### Action recommendation

The recommended action class and the concrete action position for the relevant scope, including participation, withholding, delay, differentiated inclusion, escalation, simulation first, or other governed outcome.

### Confidence statement

A confidence position that reflects not only model strength but also knowledge-quality condition, causal coverage, contradiction, local-state adequacy, and execution realism.

### Explanation summary

A concise explanation of why the recommendation exists, what commercial state was detected, what mechanisms are believed to matter, and why this action outranks the main alternatives.

### Key supporting evidence

The core evidence used to support the recommendation, including relevant state signals, prior outcomes, network or local patterns, and any authorized broader learning context.

### Key constraints

The main commercial, stock, financial, execution, brand, and governance constraints that shaped the recommendation.

### Key uncertainties or contradictions

The uncertainties, missingness, contradictory signals, or observability limits that remain material to interpretation or action.

### Failure-state warnings

Any active warning that the case involves false continuation, distortion, local optimization failure, regime instability, or other failure-state concern.

### Simulation reference where relevant

A reference to the simulation or counterfactual evaluation used, including the fact that simulation was required, run, bypassed with justification, or itself recommended as the next step.

### Alternative actions considered

A summary of the main feasible alternatives considered and why they were not preferred.

### Review conditions and monitoring signals

The conditions under which the recommendation should be revisited, the signals that should be monitored after delivery, and any time-based review trigger.

### Timestamp and version references

The time of recommendation issuance and the version references needed to reconstruct the decision episode, including major input, model, policy, or rule-state identifiers where relevant.

The recommendation contract may include additional fields, but it may not omit these minimum elements and still claim to be valid.

## Client-Scoped Output Rules

Client-facing outputs in Domain 01 must remain scoped to the authorized store, store group, client group, tenant, and role receiving them.

At minimum, the workflow must obey the following rules.

- A recommendation package may reference only the decision scope and reporting scope the recipient is entitled to view.
- Broader learning context may influence the recommendation internally, but it must not be exposed in unauthorized raw or store-identifiable form.
- Explanation detail must be filtered so that supporting evidence remains commercially interpretable without leaking unauthorized cross-store information.
- A client-scoped package must not imply that broader visibility exists if the recipient is not entitled to it.
- Delivery logic must preserve the distinction between internal reasoning context and client-visible output.
- If entitlement is ambiguous, the workflow must default to the safer narrower output.

Client scope is therefore part of recommendation compilation, not a cosmetic permission check added after the package has already been formed.

## Benchmark-Safe Comparative Output Rules

Comparative output is allowed in Domain 01 only in benchmark-safe form.

The purpose of comparative output is to provide useful context without unauthorized exposure of other stores, groups, banners, or clients.

Comparative output is valid only when it obeys the following rules.

- The comparison uses authorized aggregation, cohorting, or de-identification consistent with reporting entitlement.
- The comparison does not reveal unauthorized store identity, client identity, or sensitive local commercial detail.
- The comparison respects banner and brand boundaries so that invalid cross-brand transfer is not presented as meaningful benchmark evidence.
- The comparison preserves like-for-like commercial meaning rather than mixing incomparable stores, conditions, or decision types.
- The comparison is presented as supporting context, not as permission to infer unauthorized specifics.
- The comparison remains clearly separate from broader learning scope that is not itself reportable.

Allowed comparative output may include entitlement-safe aggregate ranges, cohort-relative positioning, or other governed benchmark-safe forms.

Disallowed comparative output includes direct unauthorized store-to-store exposure, de-anonymized ranking views outside entitlement, or explanation text that allows the recipient to infer another client's identifiable situation.

## Escalation, Abstention, and Waiting Rules

The workflow must not force a strong immediate recommendation when the disciplined outcome is to wait, escalate, or abstain.

### Waiting

Waiting is appropriate when a short delay is likely to improve visibility, clarify local stock or execution reality, reduce distortion, or avoid avoidable irreversible commitment.

### Escalation

Escalation is appropriate when the trade-off is materially policy-governed, the downside asymmetry is severe, the contradiction remains high after analysis, a human relationship or governance consideration dominates, or the platform lacks context essential to legitimate action.

### Abstention

Abstention is appropriate when the platform cannot justify a strong directional recommendation even after using the valid workflow stages available to it.

The system should prefer these governed outputs over false decisiveness.

In practical terms, the workflow should move away from immediate action recommendation when one or more of the following are true.

- Decision-critical information is missing and cannot yet be reasonably inferred.
- Failure-state concern is high and the action would commit the business before that concern is disciplined.
- The expected upside is fragile relative to the downside if the interpretation is wrong.
- Local variation within the scope makes a single immediate answer unreliable.
- The action depends on execution conditions that are not credibly satisfied.
- The explanation cannot yet meet serious operating-use standard.

## Human Override Workflow

Human override is permitted in Domain 01, but it must be governed and reconstructible.

The override workflow should operate as follows.

### Override initiation

An authorized human operator may challenge or replace the system recommendation when they possess relevant local context, policy authority, relationship context, or commercially material information not adequately represented in the system.

### Override recording

The workflow must record the original system recommendation, the chosen action, the identity or role of the override decision-maker, the stated reason for the override, the evidence or context not represented by the system, and the review horizon against which the override should later be assessed.

### Parallel record preservation

The system recommendation must remain preserved. Override must not erase the original recommendation, its warnings, or its explanation.

### Delivery update

If a package is updated because of override, the workflow must distinguish clearly between the system-generated recommendation and the final executed decision.

### Learning linkage

Every override must be linked into execution observation and post-mortem learning so the platform can assess whether override improved, degraded, or merely altered the outcome under the actual execution conditions.

Override is therefore neither a failure of automation nor a discretionary note. It is a governed part of the decision loop.

## Recommendation Explainability Standard

No recommendation package in Domain 01 is fit for serious operating use unless it can be explained in clear commercial terms.

At minimum, explanation quality must make the following inspectable.

- What decision is being made and for what scope.
- What the platform believes the current commercial state is.
- What local conditions materially influenced the recommendation.
- What broader authorized evidence mattered, if any.
- What contradiction, missingness, or observability limits remain.
- What causal pathways or mechanisms are believed to matter most.
- What constraints limited or changed the feasible action set.
- Why the preferred action outranks the main alternatives.
- What would cause the recommendation to be reviewed or reversed.

An explanation that merely states a score, a confidence label, or a predicted uplift is not sufficient.

Recommendation quality includes explanation quality. If the explanation is too shallow for operating challenge, audit, or post-mortem reconstruction, the recommendation is not complete.

## Workflow Failure Modes

Poor workflow design introduces its own failure modes even when the underlying models and domain objects are strong.

### Recommendation without proper scope control

The platform issues a package whose decision scope, reporting scope, or tenant scope is ambiguous, causing the recommendation to be misapplied or shown to the wrong audience.

### Simulation bypass under high uncertainty

The workflow allows immediate recommendation even though the case is high-stakes, locally heterogeneous, or materially distorted, producing false confidence where counterfactual testing was required.

### Premature action under false continuation

The workflow interprets visible promotional movement as sufficient strength and recommends continuation or rollout even though payoff quality, local stock health, or underlying demand condition is weakening.

### Weak override recording

The platform allows human override but fails to preserve the original recommendation, the override rationale, or the later review horizon, breaking institutional learning.

### Client output contaminated by broader learning scope

The system uses broader authorized network learning internally and then leaks that broader scope into client-facing explanation or comparative output beyond entitlement.

### Explanation too shallow for operating use

The recommendation package is technically generated but does not explain the state, evidence, mechanisms, alternatives, or review conditions strongly enough for serious operational challenge.

### Action set collapse

The workflow behaves as though only act now recommendations are valid, suppressing waiting, simulation first, escalation, information gathering, or abstention even when those are the disciplined outputs.

### Non-reconstructible recommendation object

The package lacks identifiers, scope references, version references, or evidence structure sufficient to reconstruct what the system knew and why it recommended what it did.

These failure modes are not presentation defects. They are direct risks to decision quality, tenant safety, and learning quality.

## Post-Decision Handoff Requirements

The workflow must hand forward enough information for execution observation and post-mortem learning to evaluate what happened after the recommendation.

At minimum, the handoff must include the following.

- The decision case identifier and full decision scope.
- The recommendation package identifier and final package content.
- The related promotion objects and relevant store promotion instance references.
- The action recommended and the alternatives considered.
- The confidence statement and explanation summary.
- The key constraints, uncertainties, contradictions, and failure-state warnings present at decision time.
- The simulation reference, including whether simulation was run, bypassed, or recommended.
- Any human override and its recorded rationale.
- The review conditions and monitoring signals attached to the recommendation.
- The timestamp and version references required for later reconstruction.

This handoff should allow execution observation to determine what action was actually taken, whether execution conditions matched assumptions, how outcomes evolved, and where the main gap between expectation and reality arose.

If the workflow cannot support this handoff, it has not produced a complete decision artifact.

## Non-Negotiables

1. Domain 01 is a decision workflow, not a score-emission process.
2. No recommendation may exist without an explicit promotion decision case.
3. Decision scope, learning scope, and reporting scope must remain distinct.
4. One network promotion may map to many store promotion instances, and the workflow must preserve that local variation.
5. High-stakes, locally heterogeneous, or materially distorted cases must not bypass simulation casually.
6. Waiting, simulation first, gather more information, escalation, and abstention are valid recommendation outputs.
7. Recommendation packages must remain tenant-safe and client-scoped at delivery.
8. Comparative output is valid only in benchmark-safe form.
9. Every recommendation package must be reconstructible after the fact.
10. Recommendation quality includes explanation quality.
11. Human override must be recorded without erasing the original system view.
12. Every material recommendation must connect to execution observation and post-mortem learning.

## Closing Statement

This workflow protects the platform from becoming a technically polished recommendation machine that cannot show how it moved from state to action, cannot defend when it chose to wait, cannot explain when it abstained, and cannot safely separate broad learning from client-facing output.

In Domain 01, that protection matters because one network promotion can create many local commercial realities, and the cost of collapsing them into one fast answer is hidden error with operational consequences.

If this workflow remains intact, Promotional Allocation can produce recommendations that are governed, usable, inspectable, tenant-safe, and learnable.

If it weakens, the platform will start sounding decisive before it becomes genuinely disciplined.