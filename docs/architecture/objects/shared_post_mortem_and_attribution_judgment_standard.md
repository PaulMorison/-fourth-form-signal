# Shared Post-Mortem and Attribution Judgment Standard for the Fourth Form Retail Decision Intelligence Platform

## Purpose of This Document

This document defines the shared platform standard for post-mortem structure and attribution judgment across all current and future domains.

It exists because the platform needs one governed attribution grammar for learning from decisions after execution and outcomes are observed.

Without a shared standard, the platform will drift into domain-specific post-mortem logic with incompatible meanings, inconsistent attribution categories across domains, weak distinction between recommendation error, execution error, override effect, and environmental change, post-mortem narratives that are too vague for learning, learning that depends on local storytelling rather than shared judgment structure, and policy adaptation built on inconsistent attribution language.

This document is therefore a control document for shared post-mortem and attribution judgment structure.

It defines the core concepts, shared post-mortem object meaning, attribution judgment model, core attribution categories, evidence-quality rules, lineage rules, inheritance rules, extension rules, and governance linkage that all domains must follow when judging what happened after action and what should be learned from it.

It is the canonical shared attribution and post-mortem document for the platform. Future domains, post-mortem objects, attribution judgments, and policy-learning handoffs must align with it unless a formal decision record explicitly revises it.

## Role of This Document in the Platform

This document governs the shared attribution grammar that sits above case, recommendation, deviation, execution, and realized outcome objects.

The shared decision case and decision memory standard defines how decision episodes are anchored and remembered. The shared execution deviation and outcome standard defines the governed back-half objects that record what actually happened. Domain-local execution and post-mortem contracts define how a business function observes its own reality. Policy-learning contracts define how repeated evidence may change future behavior. This document governs the common structure by which the platform turns those governed artifacts into comparable attribution judgments and learning-ready post-mortem objects.

In practical terms, this document governs five things.

- What a shared post-mortem object is.
- What a shared attribution judgment is.
- Which attribution categories are shared across the platform.
- How evidence quality must be judged before attribution is treated as strong enough for learning.
- How post-mortem objects connect to decision memory and policy-learning handoff.

This document therefore governs post-decision judgment structure as part of platform learning coherence.

## Core Thesis

In the Fourth Form platform, post-mortem must be a governed attribution process that separates recommendation quality, execution quality, override effect, environmental change, information weakness, and other materially distinct causes so that the platform learns from disciplined judgment rather than from narrative hindsight or headline outcomes alone.

That is the core thesis.

Post-mortem is not narrative hindsight alone. Attribution must separate recommendation, execution, override, and environment. Evidence quality matters.

## What This Standard Is and Is Not

This standard is the shared platform rule for how the system judges what happened after a decision episode and what should be learned from it.

It is not any of the following.

- It is not a retrospective storytelling convention.
- It is not a simple success-or-failure label attached to an outcome.
- It is not permission for domains to invent their own incompatible attribution language.
- It is not a substitute for execution observation, deviation recording, or outcome-object design.
- It is not a process that treats the final outcome as automatic proof that the recommendation was sound or weak.
- It is not a reason to hide uncertainty when the evidence is thin or contradictory.

A real shared attribution standard means the platform can answer the following questions for any material decision episode.

- What the system expected.
- What actually happened in execution and outcome.
- Whether the main issue was recommendation weakness, execution weakness, override consequence, environmental change, or another governed cause.
- How strong the evidence is for that judgment.
- What should be learned next.

## Why a Shared Post-Mortem Standard Is Necessary

Domains must not define attribution logic independently because the platform cannot compound intelligence across domains if each domain explains misses, successes, and overrides in a different judgment grammar.

If post-mortem logic is left local, several failures follow.

- Recommendation error means different things in different domains.
- Override effects are judged inconsistently and become politically distortable.
- Execution failure and environmental change get confused with one another.
- Learning handoffs into policy adaptation become incomparable across domains.
- Future engineering and AI-assisted implementation begin learning the platform from local storytelling rather than shared judgment structure.

The platform therefore needs one shared post-mortem standard so that every domain can extend a common attribution grammar rather than inventing its own learning language.

## Core Concepts

The platform uses the following core concepts.

### Post-mortem object

A post-mortem object is the governed object that records the judged relationship between expected consequence, execution reality, realized outcome, attribution conclusion, evidence quality, and learning direction for one decision episode.

### Attribution judgment

An attribution judgment is the governed judgment about the primary reason the realized outcome did or did not align with disciplined expectation.

### Evidence quality

Evidence quality is the judged strength, completeness, coherence, and interpretability of the evidence supporting an attribution judgment.

### Recommendation error

Recommendation error is the condition in which the system chose or endorsed the wrong action relative to the decision-time evidence, constraints, and feasible alternatives.

### Execution error

Execution error is the condition in which the recommendation may have been sound, but the realized execution path, timing, scope fidelity, operating conditions, or delivery quality materially degraded the result.

### Override effect

Override effect is the judged consequence of human intervention on the action path relative to the original system recommendation and realized conditions.

### Environmental or regime change

Environmental or regime change is the condition in which the world changed materially after commitment, making the realized outcome diverge from what disciplined decision-time reasoning could reasonably have expected.

### Information gap

Information gap is the condition in which the decision or later attribution was materially weakened by missing, delayed, contradictory, or inaccessible information.

### Constraint miss

Constraint miss is the condition in which the system failed to represent a real commercial, operational, financial, stock, execution, or governance constraint strongly enough before recommendation.

### Causal misunderstanding

Causal misunderstanding is the condition in which the system misread the mechanisms connecting action to outcome and therefore used the wrong intervention logic.

### Simulation miss

Simulation miss is the condition in which simulation-informed expectation materially misrepresented likely consequences, local deformation, second-order effects, or uncertainty.

### Insufficient evidence judgment

Insufficient evidence judgment is the governed conclusion that the evidence base is too weak, incomplete, contradictory, or immature to support a strong attribution conclusion.

## Shared Post-Mortem Object

At platform level, a post-mortem object is the formal object that closes one governed decision episode by stating what was expected, what happened, why the platform judges that gap or alignment the way it does, how strong the supporting evidence is, and what should be learned next.

It exists because the platform must learn from structured judgment rather than from informal commentary after the fact.

The shared post-mortem object must contain, conceptually, all of the following.

- A stable identity for the judged post-mortem episode.
- A link to the originating decision case.
- A link to the relevant recommendation path.
- Where relevant, links to override state, execution deviation objects, and outcome objects.
- A statement of expected consequence versus realized consequence.
- A governed attribution judgment.
- An explicit evidence-quality position.
- A learning direction strong enough for decision memory and policy-learning handoff.

The post-mortem object is therefore not a narrative appendix. It is the governed judgment object of the decision episode.

## Shared Attribution Judgment Model

At platform level, an attribution judgment is the disciplined answer to the question of why the realized outcome aligned with or diverged from the platform's disciplined expectation.

The shared attribution judgment model must contain, conceptually, all of the following.

- One primary attribution category.
- Optional secondary contributing factors where the primary category alone would be misleading.
- An explicit distinction among recommendation quality, execution quality, override consequence, environmental change, information weakness, and other relevant governed causes.
- An evidence-quality judgment showing how strong the attribution basis really is.
- A scope reference showing which decision population or operating unit the judgment concerns.
- A learning consequence showing what the platform should update, preserve, test further, or avoid overlearning from.

This model requires discipline because real decisions often contain multiple pressures, but not every multi-factor story justifies a blurred judgment. The platform should prefer one primary governed attribution category with explicit secondary contributors only when needed.

## Core Attribution Categories

The platform should support the following shared attribution categories.

### Correct recommendation, correct execution

The recommendation was sound for the decision-time evidence, execution was materially aligned with intent, and the realized outcome broadly aligned with disciplined expectation.

### Correct recommendation, weak execution

The recommendation was sound, but execution quality, timing, scope fidelity, operating discipline, or realized delivery conditions materially weakened the outcome.

### Correct recommendation, environment changed

The recommendation was sound under the decision-time state, but the relevant environment or regime changed materially enough after commitment to alter the realized outcome.

### Weak recommendation, good execution

Execution was materially sound, but the recommendation itself was weak relative to the state, constraints, or feasible alternatives.

### Weak recommendation, weak causal logic

The recommendation failed because the platform's intervention reasoning was materially incomplete, distorted, or mis-specified.

### Weak recommendation, poor local-state capture

The recommendation failed because materially relevant local context, local state, or decision-time reality was absent or underrepresented.

### Weak recommendation, simulation miss

The recommendation relied on simulation or counterfactual expectation that materially misrepresented likely consequence, local deformation, or uncertainty.

### Weak recommendation, constraint miss

The recommendation treated the action as more feasible, acceptable, or commercially valid than real constraints allowed.

### Override improved outcome

The override materially improved the realized outcome or exposed a meaningful missing-context problem relative to the original system recommendation under the realized conditions.

### Override worsened outcome

The override materially degraded the realized outcome or displaced a sound system recommendation under the realized conditions.

### Insufficient evidence for confident judgment

The available evidence is too weak, incomplete, contradictory, or immature to support a strong attribution judgment.

These categories are shared because future domains need one common attribution language even when their local business objects differ.

## Evidence-Quality Rules

The platform must judge evidence quality explicitly before treating attribution as strong enough for learning.

At minimum, evidence quality should consider the following.

- Whether the originating case, recommendation, deviation, and outcome lineage is complete enough to reconstruct the episode.
- Whether the observation horizon is mature enough to support the judgment being made.
- Whether execution reality is observed clearly enough to separate recommendation weakness from delivery weakness.
- Whether override behavior is preserved clearly enough to judge override consequence seriously.
- Whether materially relevant information was missing, delayed, contradictory, or inaccessible at decision time or review time.
- Whether the outcome signal is strong enough to support interpretation rather than superficial reading.
- Whether the judgment is being made within a valid governed scope and not from unauthorized or incomparable evidence.
- Whether the available evidence supports one disciplined attribution more strongly than competing explanations.

The following rules also apply.

- Strong attribution should not be claimed when execution reality is ambiguous.
- Strong recommendation-error judgment should not be claimed when material execution deviation remains unresolved.
- Strong override-effect judgment should not be claimed unless the original recommendation, approved action, executed action, and realized outcome are all preserved.
- Environmental-change judgment should not be used as a convenience label when recommendation or execution weakness is the real unresolved issue.
- When evidence is weak, contradictory, or immature, insufficient evidence is the correct governed judgment rather than a weaker imitation of confidence.

Evidence quality is therefore not a cosmetic note. It determines whether attribution is fit to inform policy learning.

## Lineage Rules

Post-mortem objects must preserve reconstructible lineage back to case, recommendation, deviation, and outcome, and forward to memory and policy learning.

The following rules apply.

- Every post-mortem object must remain linked to the originating decision case.
- Every post-mortem object must remain linked to the relevant recommendation path.
- Where relevant, the post-mortem object must link to override records, execution deviation objects, and outcome objects rather than substituting narrative summary for those links.
- Attribution judgment must remain interpretable in light of the exact deviation and outcome objects it relied on.
- Decision memory objects must preserve the post-mortem object as the governed attribution layer of the decision episode.
- Policy-learning handoff must preserve which post-mortem objects, judgment categories, and evidence-quality positions supported a later adaptation proposal.
- Version lineage must preserve enough governed context to reconstruct what policy, rule state, workflow assumptions, or observation context were in force when the post-mortem judgment was formed.

Broken lineage turns post-mortem into commentary rather than governed learning input. This standard requires the opposite.

## Domain Inheritance Rules

All current and future domains must inherit this shared attribution grammar.

The following rules apply.

- Every material decision domain must produce post-mortem objects strong enough to support governed attribution.
- Every material decision domain must map its local post-decision judgment into this shared attribution model.
- Domain-local execution and post-mortem contracts must use these shared category meanings even when they add local operational nuance.
- Future domain admission should test whether the candidate domain can produce governed post-mortem objects and shared attribution judgments before it is treated as admission-ready.
- Cross-domain learning must not rely on incompatible local attribution language that cannot be mapped cleanly to this shared grammar.

This standard therefore applies across Domain 01 and all later admitted domains.

## Domain Extension Rules

Domains may extend this shared attribution grammar locally, but they must not redefine its shared meanings.

The following rules apply.

- A domain may add local post-mortem fields, local causal notes, local operational factors, local evidence signals, or local subcategories beneath the shared attribution categories.
- A domain may add domain-specific secondary contributors where its business function requires more precise structured judgment.
- A domain may add local learning-direction detail relevant to workflow, simulation, execution operations, or policy behavior.
- A domain may not redefine what recommendation error means.
- A domain may not redefine what execution error, override effect, environmental change, information gap, constraint miss, causal misunderstanding, simulation miss, or insufficient evidence mean.
- A domain may not omit evidence-quality judgment merely because a local team feels sure of its story.
- A domain may not replace the shared attribution model with unstructured retrospective narrative.

Domains may therefore enrich the judgment body, but not rewrite the shared attribution grammar.

## Governance Linkage

This standard is directly linked to platform change governance, approval authority, and policy-learning contracts.

Changes to attribution category meaning, evidence-quality expectations, post-mortem object structure, or learning handoff rules are consequential platform changes because they alter how the platform explains past decisions and how it justifies future policy adaptation.

The following governance rules apply.

- Consequential revisions to this standard should be handled through the formal decision-record process.
- Changes that affect shared attribution language, evidence thresholds, policy-learning inputs, or cross-domain comparability are high-sensitivity governance events.
- Review and approval should align with the platform governance roles and approval authority matrix, especially where shared architecture, workflow, policy-learning behavior, tenant boundaries, or reporting implications are affected.
- Domain-local post-mortem contracts must not silently override this shared attribution standard.
- Shared decision-memory logic, shared execution and outcome logic, and policy-learning contracts should treat this standard as a controlling reference for judgment structure.

Shared attribution grammar is therefore part of governance, not merely retrospective practice.

## Failure Modes in Attribution Design

Weak attribution design creates direct platform risk.

### Narrative-only post-mortems

The platform records commentary after the fact, but not enough structured judgment for future retrieval, comparison, or policy learning.

### Inconsistent error categories

Different domains use different meanings for recommendation weakness, execution weakness, environmental change, or override effect, making cross-domain learning incoherent.

### Override mythology

Override becomes politically or culturally privileged in explanation without disciplined evidence about whether it improved or worsened outcomes.

### False confidence in weak evidence

The platform presents strong attribution conclusions even though the evidence base is thin, immature, contradictory, or operationally ambiguous.

### Unstructured learning signals

Policy-learning inputs inherit vague storytelling instead of governed judgment categories, weakening adaptation quality.

### Cross-domain attribution mismatch

One domain's post-mortem language cannot be compared to another's, so the platform cannot learn coherently above domain-local narratives.

### Outcome-result collapse

The platform treats a favorable or unfavorable headline outcome as proof of one cause without separating recommendation quality, execution quality, override effect, and environmental change.

These failure modes are not minor retrospective defects. They are ways the platform loses judgment discipline, learning quality, and cross-domain coherence.

## Non-Negotiables

1. Post-mortem is not narrative hindsight alone.
2. Attribution must separate recommendation, execution, override, and environment.
3. Evidence quality must be explicit.
4. Insufficient evidence is a valid governed judgment.
5. Post-mortem objects must remain linked to case, recommendation, deviation, and outcome.
6. Policy learning must inherit structured attribution, not local storytelling.
7. Domains may extend this grammar locally, but they may not redefine its shared meanings.
8. Domain-local post-mortem contracts must not silently override this standard.
9. If attribution cannot distinguish plausible competing causes honestly, it is not strong enough to drive confident learning.
10. Shared attribution grammar is necessary for cross-domain learning coherence.

## Closing Statement

This document protects the platform from confusing retrospective storytelling with governed learning.

Fourth Form is building a retail decision intelligence platform that must learn from what happened after action without collapsing recommendation quality, execution quality, override consequence, and environmental change into one vague explanation.

If this standard remains intact, future domains can produce post-mortem judgments that are comparable, reusable, and policy-relevant across the platform.

If it weakens, the platform will still remember outcomes, but it will no longer remember them with disciplined attribution.