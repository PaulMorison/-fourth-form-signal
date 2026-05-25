# Shared Action Path and Candidate Action Set Standard for the Fourth Form Retail Decision Intelligence Platform

## Purpose of This Document

This document defines the shared platform standard for candidate action sets and action paths across all current and future domains.

It exists because the platform already depends on action-path meaning in recommendation, simulation, approval, override, execution, and post-mortem review, but it cannot remain one governed decision system if those paths are left as thin prose, local enums, hidden workflow assumptions, or domain-specific labels whose meanings drift from one domain to another.

Without a shared standard, the platform will drift into domain-specific action semantics, candidate sets that are confused with recommendations, alternative paths that disappear once a recommendation is issued, simulation and counterfactual artifacts that compare vague scenarios instead of governed paths, override history that forgets the original preferred path, and post-mortem or policy-learning review that cannot reconstruct what paths were actually available at decision time.

This document is therefore a control document for shared action-path and candidate action-set structure.

It defines the core concepts, shared object meanings, shared status and validity grammar, minimum metadata requirements, lineage rules, inheritance rules, extension rules, and governance linkage that all domains must follow when preserving governed action alternatives for a decision case.

It is the canonical shared action-path and candidate action set standard for the platform. Future domain workflow contracts, recommendation records, simulation logic, approval and override logic, escalation and abstention handling, execution comparison, post-mortem judgment, and policy-learning reuse must align with it unless a formal decision record explicitly revises it.

## Role of This Document in the Platform

This document governs the shared decision-support grammar that sits between decision-case formation and the later layers that choose, compare, alter, execute, and judge actions.

The shared decision case and decision memory standard defines how decision episodes are anchored and remembered. The shared constraint and feasibility context standard defines what makes a path valid, invalid, or conditionally valid. The shared recommendation record standard defines which path becomes preferred. The shared simulation and counterfactual standard defines how paths are compared before commitment. The shared approval and override standard defines how human intervention may later preserve, alter, or replace the selected path. The shared escalation and abstention standard defines governed non-action outcomes where a direct path gives way to review or withheld commitment. The shared execution deviation and outcome standard defines what path was actually executed. The shared post-mortem standard defines how realized paths are later judged against originally available paths. This document governs the candidate action sets and action paths that connect those layers by preserving the serious governed paths that existed for a case before one of them became preferred, altered, deferred, escalated, abstained from, or executed.

In practical terms, this document governs what a candidate action set is, what an action path is, how path status and validity are represented, what minimum metadata these objects must preserve, and how later decision-loop stages may reuse them without losing meaning.

This document therefore governs action-space structure as part of platform coherence.

## Core Thesis

In the Fourth Form platform, candidate action sets and action paths must remain first-class governed decision-support structure whose scope, validity, comparability, and lineage remain explicit enough that the platform can preserve the serious feasible action space of a case, choose one preferred path responsibly, compare alternatives through simulation and human review, observe what path was actually executed, and later judge whether a better path was available.

That is the core thesis.

The platform needs one shared meaning of action path because recommendation, simulation, approval, override, execution, and post-mortem all depend on it. A candidate action set is the governed set of serious action paths available to a case under the relevant constraint and feasibility context. A preferred path is the path the recommendation record chooses from that candidate action set. Alternative paths must remain preservable for later comparison and post-mortem. Invalid paths must not be treated as serious governed options. Conditionally valid paths must preserve their governing conditions explicitly.

## What This Standard Is and Is Not

This standard is the shared platform rule for how the system records, links, preserves, and reuses serious action alternatives for a decision case.

It is not a generic optimization specification. It is not a domain-local workflow note. It is not an output-package schema. It is not permission for domains to reduce action logic to explanation prose or hidden local workflow assumptions. It is not a reason to collapse candidate action sets into recommendations, nor a reason to collapse action paths into approval records, override records, execution records, or post-mortem narratives. It is not a substitute for shared constraint and feasibility context, even though action-path validity must reflect that context directly.

A real shared action-path standard means the platform can answer the following questions for any material decision episode: what serious paths existed for the case, which of those paths were valid, invalid, or conditionally valid, which path became preferred, which paths were deferred, escalated, or abstained from, which paths were compared in simulation or counterfactual reasoning, which path humans later approved or replaced, which path was actually executed, and whether a better governed path was originally available.

## Why a Shared Action-Path Standard Is Necessary

Domains must not define action paths and candidate action sets independently because path meaning is one of the deepest shared structures of the platform.

If action-path grammar is left local, several failures follow. One domain preserves a serious candidate set while another preserves only the final recommendation. One domain records alternative paths as governed objects while another reduces them to narrative comments. One domain distinguishes invalid paths from deferred paths while another blurs them together. Simulation then compares vague scenarios instead of governed paths, approval and override cannot preserve whether human intervention matched or departed from the preferred path, execution history cannot say what path was actually taken relative to what was available, and post-mortem cannot judge whether a better path existed at decision time.

The platform therefore needs one shared standard so that future domains can extend one governed action grammar rather than inventing their own local meanings for what an action path is.

## Core Concepts

The platform uses the following core concepts.

### Candidate action set

A candidate action set is the governed set of serious action paths available to a decision case under the relevant constraint and feasibility context. A candidate action set is not the same thing as a recommendation. It preserves the serious governed action space from which a recommendation may later choose.

### Action path

An action path is the governed representation of one serious path the platform may evaluate, compare, recommend, defer, escalate, abstain from, approve, override, execute, or later judge. An action path is not the same thing as an output package. It is the underlying governed path object that output, simulation, approval, and execution artifacts may reference.

### Candidate path

Candidate path is an action path that belongs to the candidate action set of the case and is serious enough to be preserved as part of the governed action space.

### Preferred path

Preferred path is the action path the recommendation record chooses from the candidate action set at the point of recommendation.

### Alternative path

Alternative path is an action path that remained in the governed candidate set but did not become the preferred path for that recommendation episode.

### Invalid action path

Invalid action path is an action path that should not be treated as a serious governed option because shared constraint and feasibility context blocked it from valid candidacy.

### Conditionally valid action path

Conditionally valid action path is an action path that may be treated as governed only if explicit conditions, approvals, preconditions, dependencies, or scope restrictions are satisfied.

### Deferred path

Deferred path is an action path whose serious consideration is preserved, but whose governed next state is delay rather than immediate direct selection or execution.

### Escalated path

Escalated path is an action path whose governed next state is accountable review or higher-authority handling rather than immediate direct commitment.

### Abstained path

Abstained path is an action path whose direct selection was withheld because the platform could not justify stronger directional commitment under the current decision conditions.

### Action-path comparability

Action-path comparability is the governed judgment that two or more action paths are structured and scoped coherently enough to support serious simulation, counterfactual comparison, recommendation ranking, or later post-mortem comparison.

### Action-path lineage

Action-path lineage is the reconstructible chain connecting the decision case, candidate action set, path validity state, recommendation choice, simulation comparison, human intervention, realized execution, and later post-mortem or policy-learning reuse.

### Recommendation-path linkage

Recommendation-path linkage is the explicit connection between the action path that became preferred and the recommendation record that selected it.

### Simulation-path linkage

Simulation-path linkage is the explicit connection between action paths and the simulation or counterfactual records that compared or evaluated them.

### Approval-path linkage

Approval-path linkage is the explicit connection between the preferred path and any later approved path that matched, deferred, rejected, escalated, or conditionally handled it.

### Override-path linkage

Override-path linkage is the explicit connection between the original preferred path and any later human-selected path that replaced or materially altered it.

### Execution-path linkage

Execution-path linkage is the explicit connection between the action path selected or changed upstream and the path that was actually executed under realized conditions.

### Post-mortem path comparison

Post-mortem path comparison is the governed later comparison among the realized path, the preferred path, and the originally available governed paths in order to judge whether the chosen path was sound or whether a better serious path was available.

### Policy-learning reuse

Policy-learning reuse is the governed reuse of candidate-set and path history for future policy improvement only when lineage, scope validity, evidence quality, and post-mortem discipline remain strong enough to justify that reuse.

## Shared Candidate Action Set

At platform level, a shared candidate action set is the formal governed object that preserves the serious action space of a decision case before one path becomes preferred or before the case resolves into non-action handling.

It exists because the platform must preserve more than the one path it ultimately preferred. It must preserve which serious paths were available, which alternatives were considered, which paths were blocked by validity rules, and which downstream artifacts later compared or altered those paths.

A shared candidate action set must preserve, conceptually, all of the following. It must preserve a candidate action set ID so the action space has stable identity. It must preserve the originating case ID and a domain reference so ownership remains explicit. It must preserve the decision scope reference and the tenant or client scope reference so the action space does not lose its governed population. It must preserve candidate action-path references so the serious action space remains reconstructible. It must preserve the constraint-context reference and the feasibility-context reference because the candidate set is valid only under those governing conditions. It must preserve action-set status or completeness reference where relevant so later systems can tell whether the set was fully assembled, partially assembled, narrowed, reopened, or otherwise materially conditioned. It must preserve lineage or version reference and timestamp so later recommendation, approval, execution, and post-mortem processes can reconstruct which governed action space existed at the time.

This is governed object meaning, not code schema. A candidate action set must remain interpretable as the governed serious action space of the case rather than as a transient implementation artifact.

## Shared Action Path

At platform level, a shared action path is the formal governed object that preserves one serious path within or related to the candidate action set of a decision case.

It exists because the platform must preserve one stable meaning for what path is being compared, recommended, simulated, approved, overridden, executed, deferred, escalated, or later judged. Without that stable meaning, every downstream object starts referring to action path while pointing to something structurally different.

A shared action path must preserve, conceptually, all of the following. It must preserve an action path ID so the path has stable identity. It must preserve the originating case ID and a domain reference. It must preserve an action-path type or class reference so later systems can tell what kind of governed path it represents. It must preserve the decision scope reference and the tenant or client scope reference so the path remains attached to the population it concerns. It must preserve related business-object references so the path remains anchored to the business objects it acts on. It must preserve path-validity reference and path-condition reference where relevant so serious path meaning stays tied to shared constraint and feasibility context. It must preserve candidate-set reference so later systems know which governed action space the path belonged to. It must preserve recommendation, simulation, approval, override, and execution linkage where relevant. It must preserve lineage or version reference and timestamp so later systems can reconstruct which governed path existed at decision time and how it moved through the loop.

This is governed object meaning, not code schema. A shared action path must remain interpretable as one governed decision-support path rather than as prose, status residue, or an untracked local enum.

## Action-Path Status and Validity Grammar

The platform requires one shared cross-domain grammar for path status and validity so that future domains inherit stable meanings for how action paths are handled.

### Valid path

Valid path is an action path that may be treated as a serious governed option under the current shared constraint and feasibility context.

### Invalid path

Invalid path is an action path that must not be treated as a serious governed option because shared constraint or feasibility conditions block it.

### Conditionally valid path

Conditionally valid path is an action path that may be serious only if explicit governing conditions are preserved and later satisfied.

### Preferred path

Preferred path is the valid or conditionally valid path selected by the recommendation record from the candidate action set.

### Alternative path

Alternative path is a serious path preserved alongside the preferred path for later comparison, explanation, simulation, approval review, or post-mortem judgment.

### Deferred path

Deferred path is a path whose governed next state is delay rather than immediate commitment.

### Escalated path

Escalated path is a path whose governed next state is accountable human review or higher-authority handling rather than immediate direct selection.

### Abstained path

Abstained path is a path whose direct selection was withheld because stronger directional commitment was not justified under current conditions.

These are shared cross-domain meanings. Domains may add narrower subtypes beneath them, but they may not silently replace, blur, or reinterpret them with incompatible local-only semantics. Shared path grammar depends on these meanings remaining stable enough that recommendation, simulation, approval, override, execution, post-mortem, and policy-learning logic can interpret path history coherently across domains.

## Minimum Shared Metadata for Candidate Action Sets

Every governed candidate action set must carry minimum shared metadata.

### Candidate action set ID

This is the unique stable identifier for the candidate action set.

### Originating case ID

This is the stable reference to the decision case from which the candidate action set arises.

### Domain reference

This is the stable reference to the domain that owns the candidate action set.

### Decision scope reference

This is the explicit decision scope governing the candidate action set.

### Tenant or client scope reference

This is the tenant boundary and client-population context under which the candidate action set is valid.

### Candidate action-path references

These are the references to the serious governed paths belonging to the candidate action set.

### Constraint-context reference

This is the governed reference to the shared constraint context shaping the candidate action set.

### Feasibility-context reference

This is the governed reference to the shared feasibility context shaping the candidate action set.

### Action-set status or completeness reference where relevant

This is the preserved reference showing whether the candidate action set was complete, provisional, narrowed, reopened, or otherwise materially qualified where that distinction matters.

### Lineage or version reference

This is the lineage and version reference needed to reconstruct the governing context of the candidate action set later.

### Timestamp

This is the time at which the candidate action set was formed or fixed.

These are minimum shared metadata elements. Domains may extend them, but they may not omit or redefine them when the object is claimed as a governed platform candidate action set.

## Minimum Shared Metadata for Action Paths

Every governed action path must carry minimum shared metadata.

### Action path ID

This is the unique stable identifier for the action path.

### Originating case ID

This is the stable reference to the decision case from which the action path arises.

### Domain reference

This is the stable reference to the domain that owns the action path.

### Action-path type or class reference

This is the governed reference identifying what kind of path the action path represents.

### Decision scope reference

This is the explicit decision scope governing the action path.

### Tenant or client scope reference

This is the tenant boundary and client-population context under which the action path is valid.

### Related business-object references

These are the references to the material business objects the action path concerns.

### Path-validity reference

This is the governed reference showing whether the path was valid, invalid, or conditionally valid under shared constraint and feasibility context.

### Path-condition reference where relevant

This is the governed reference to the conditions that materially qualified the action path where conditional validity, deferred handling, escalation, or other qualification applies.

### Candidate-set reference

This is the governed reference tying the action path back to the candidate action set it belonged to.

### Recommendation, simulation, approval, override, or execution linkage where relevant

This is the governed reference linking the action path to the downstream or comparative artifacts that later used it.

### Lineage or version reference

This is the lineage and version reference needed to reconstruct the governing context of the action path later.

### Timestamp

This is the time at which the action path was formed or fixed.

These are minimum shared metadata elements. Domains may extend them, but they may not omit or redefine them when the object is claimed as a governed platform action path.

## Lineage Rules

Decision cases may carry candidate action sets directly because the case must preserve the serious governed action space available at decision time. Recommendation records must preserve which path became preferred and how that preferred path related to the broader candidate set. Simulation and counterfactual records must preserve which paths were compared and under what action-path comparability basis those comparisons were treated as serious.

Approval and override records must preserve how human intervention changed the selected path, including whether the approved path matched the preferred path or whether an override replaced it with another governed path. Escalation and abstention records may preserve when a preferred direct path gave way to non-action handling, including where a direct path remained visible but was deferred, escalated, or abstained from under current conditions. Execution and outcome objects must preserve which path was actually executed so realized reality can be compared not only with the preferred path but also with the serious paths originally available. Post-mortem objects must be able to compare the realized path against originally available and preferred paths in order to judge whether the chosen path was sound or whether a better serious path existed.

Policy learning may reuse path history only with preserved lineage and evidence discipline. Action-path history must not be treated as reusable policy signal merely because many paths were generated or because one path was often chosen. Reuse must preserve linkage to case, candidate set, shared constraint and feasibility context, recommendation choice, human intervention where relevant, execution reality, post-mortem judgment, and valid scope so the platform does not overlearn from weakly preserved path history.

Action-path lineage therefore connects case, candidate action set, path validity, recommendation choice, simulation comparison, human intervention, realized execution, post-mortem path comparison, and possible policy-learning reuse into one reconstructible chain. If that chain breaks, later systems cannot tell what was truly available, what was chosen, and whether the platform or a human actor passed over a better governed path.

## Domain Inheritance Rules

All admitted domains must inherit this shared action-path grammar.

At minimum, every domain-local workflow contract, candidate-action generator, recommendation design, simulation design, counterfactual design, approval review flow, override logic, escalation and abstention handling, execution comparison design, post-mortem design, and policy-learning reuse logic that depends on action alternatives must align with the following rules. A candidate action set is not the same thing as a recommendation. An action path is not the same thing as an output package. Action-path validity must reflect shared constraint and feasibility context. Invalid paths must not be treated as serious options. Conditionally valid paths must preserve their conditions explicitly.

Future domains may extend this grammar, but they may not redefine its shared meanings. Domain-local contracts must therefore inherit this standard rather than invent their own incompatible path semantics.

## Domain Extension Rules

Domains may extend this standard where their operating reality requires richer action-path types, narrower path-status subtypes, more specific comparability rules, or additional business-object references.

Valid domain extension may include richer path taxonomies, more specific path-condition references, narrower non-action subtypes, or stricter action-path comparability requirements. Domain extension is invalid when it hides action paths inside prose or workflow logic, confuses candidate sets with recommendations, treats invalid paths as serious governed options, reduces simulation comparison to vague scenario descriptions, loses the original preferred path during override handling, or rewrites the shared status grammar into incompatible local-only semantics.

Domain extension is also invalid when it preserves execution history without enough path lineage to say what was actually taken relative to what was available, or when it reduces action-path structure to local enums that later shared objects cannot interpret. Extension is allowed. Redefinition of shared meaning is not.

## Governance Linkage

This standard is directly governance-linked because the platform cannot claim disciplined decisioning if it does not preserve one stable meaning for what serious action paths existed for a case.

The shared decision case and memory standard should treat this file as the controlling reference for how candidate action sets and action paths are anchored to cases. The shared constraint and feasibility context standard should treat it as the controlling reference for how path validity reflects governed constraint and feasibility conditions. The shared recommendation record standard should treat it as the controlling reference for preferred-path selection. The shared simulation and counterfactual standard should treat it as the controlling reference for simulation-path and reference-path linkage. The shared approval and override standard, the shared escalation and abstention standard, and the shared execution deviation and outcome standard should all treat it as the controlling reference for preserving path changes, non-action handling, and realized execution-path comparison. The shared post-mortem standard and the policy-learning evidence admission and update-threshold standard should treat it as the controlling reference for later path comparison and disciplined reuse.

Changes to shared path meaning, candidate-set meaning, path-status grammar, comparability rules, lineage expectations, or reuse rules are consequential platform changes. They must go through formal governance rather than domain-local adjustment.

## Failure Modes in Action-Path Design

Weak action-path design creates direct platform risk.

### Action paths hidden inside prose or workflow logic

The platform behaves as though serious paths existed, but those paths were never preserved as governed objects and cannot be reconstructed later.

### Candidate sets confused with recommendations

The platform preserves only the chosen path and forgets the serious governed action space from which that path was chosen.

### Invalid paths treated as serious options

Paths blocked by shared constraint and feasibility context are allowed to remain in the governed serious action space as though they were legitimate options.

### Simulation comparing vague scenarios rather than governed paths

Simulation appears rigorous, but it is comparing narrative descriptions instead of stable action paths with preserved scope, validity, and comparability.

### Override losing the original preferred path

Human intervention is recorded, but the original preferred path disappears, making later attribution and post-mortem comparison structurally weak.

### Execution history unable to say what path was actually taken relative to what was available

The platform observes execution, but it cannot reconstruct whether the executed path matched the preferred path, an alternative path, or a newly improvised path outside the original governed candidate set.

### Post-mortem unable to judge whether a better path was originally available

The platform later wants to judge whether the chosen path was sound, but the candidate set and alternative paths were too weakly preserved to support serious comparison.

### Domains drifting into incompatible local action-path semantics

Different domains begin using incompatible meanings for candidate sets, alternatives, deferred paths, or path validity, destroying shared decision-loop comparison across the platform.

These failure modes are not minor documentation defects. They are ways a decision platform can appear to preserve action choice while actually forgetting what options it really had.

## Non-Negotiables

1. The platform must preserve one shared meaning of action path.
2. A candidate action set is not the same thing as a recommendation.
3. An action path is not the same thing as an output package.
4. Invalid paths must not be treated as serious governed options.
5. Conditionally valid paths must preserve their governing conditions explicitly.
6. Alternative paths must remain preservable for later comparison.
7. Simulation and counterfactual artifacts must reference governed action paths, not vague scenarios.
8. Approval, override, and execution history must preserve path linkage explicitly.
9. Post-mortem and policy-learning reuse require preserved action-path lineage and evidence discipline.
10. Future domains need one shared action-path grammar to remain coherent.

## Closing Statement

This document protects candidate action sets and action paths from collapsing into narrative workflow residue, local enums, or hidden implementation assumptions.

That protection matters because action paths and candidate action sets must remain governed decision-support structure whose value depends on preserved scope, validity, and lineage. Future domains need one shared action-path grammar to avoid drift in how the platform represents serious available paths, how it selects a preferred path, how later humans alter or approve that path, how execution compares with what was available, and how later post-mortem and policy-learning processes judge whether a better path existed.

If this standard remains intact, future domains can extend action-path logic for their own business realities while still preserving one shared meaning for candidate action sets and action paths across the platform. If it weakens, recommendation discipline, simulation discipline, human-intervention traceability, execution comparison, and post-mortem judgment will all become harder to trust at once.