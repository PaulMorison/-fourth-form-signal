# Shared Recommendation Record Standard for the Fourth Form Retail Decision Intelligence Platform

## Purpose of This Document

This document defines the shared platform standard for recommendation records across all current and future domains.

It exists because the platform cannot remain one governed decision system if recommendation artifacts are left as thin status labels, output-only text, presentation cards, or domain-local objects whose meanings change from one workflow to another.

Without a shared standard, the platform will drift into domain-specific recommendation semantics, weak preservation of what action path was actually recommended, missing linkage between recommendation and case scope, missing linkage between recommendation and later approval or override, weak preservation of confidence and uncertainty meaning, and post-mortem or policy-learning review that cannot tell what the system truly recommended at decision time.

This document is therefore a control document for shared recommendation record structure.

It defines the core concepts, shared object meaning, action-class grammar, minimum metadata requirements, lineage rules, inheritance rules, extension rules, and governance linkage that all domains must follow when preserving a governed recommendation.

It is the canonical shared recommendation record standard for the platform. Future domain workflow contracts, recommendation objects, approval review, override comparison, execution comparison, post-mortem judgment, and policy-learning reuse must align with it unless a formal decision record explicitly revises it.

## Role of This Document in the Platform

This document governs the shared recommendation object grammar that sits between decision-case formation and later human review, execution, post-mortem, decision memory, and policy learning.

The shared decision case and decision memory standard defines how decision episodes are anchored and remembered. The shared output metadata standard defines how recommendation packages are delivered with scope and lineage metadata, but not what the recommendation object means by itself. The shared simulation and counterfactual standard defines how simulation-informed reasoning may be preserved. The shared approval and override standard defines how human review may later accept, alter, defer, reject, or replace a recommendation. The shared escalation and abstention standard defines governed non-action outcomes related to recommendation flow. The shared execution deviation and outcome standard defines how realized reality is later compared with the system view. The shared post-mortem standard defines how recommendation quality is later judged. This document governs the recommendation record that connects those layers by preserving exactly what the system recommended, for what scope, under what constraints and uncertainty, and with what lineage.

In practical terms, this document governs what a recommendation record is, which action classes it may take, what minimum metadata it must preserve, how it remains distinct from adjacent objects, and how later decision-loop stages may reuse it without losing meaning.

This document therefore governs recommendation object structure as part of platform coherence.

## Core Thesis

In the Fourth Form platform, a recommendation record must remain a first-class governed decision object that preserves the recommended action path, decision meaning, scope, confidence, constraints, uncertainty, failure-state context, and downstream lineage strongly enough that later approval, override, execution, post-mortem, and policy-learning processes can evaluate what the system actually recommended rather than guessing from presentation output.

That is the core thesis.

Recommendation is a governed decision object, not just presentation output. A recommendation record is not just an output card, label, or explanation paragraph. Its value depends on preserving action-path meaning, scope, and lineage explicitly.

## What This Standard Is and Is Not

This standard is the shared platform rule for how recommendation records are formed, preserved, linked, and reused across domains.

It is not any of the following.

- It is not a generic product specification for user-facing recommendations.
- It is not a domain-local workflow note.
- It is not a presentation-layer schema for cards, screens, or reports.
- It is not a substitute for output-package metadata.
- It is not permission for domains to encode recommendation meaning only in explanation prose.
- It is not a reason to collapse recommendation together with approval, override, escalation, abstention, execution, or outcome.

A real shared recommendation standard means the platform can answer the following questions for any material decision episode.

- What the system actually recommended.
- Which action class that recommendation belonged to.
- Which case, scope, and business objects the recommendation applied to.
- What confidence, constraint, uncertainty, and failure-state context qualified the recommendation.
- How the recommendation linked to simulation, later approval, override, execution, outcome, post-mortem, and memory.

## Why a Shared Recommendation Standard Is Necessary

Domains must not define recommendation records independently because recommendation is one of the central shared meanings of the platform.

If recommendation object grammar is left local, several failures follow. One domain preserves a concrete action path while another preserves only an outcome label. One domain records uncertainty explicitly while another stores confidence without context. One domain preserves direct-action meaning while another blurs recommendation into escalation, abstention, or approval state. Output packages, approval review, execution comparison, post-mortem judgment, and policy-learning reuse then inherit incompatible recommendation semantics that cannot be compared or judged coherently across domains.

The platform therefore needs one shared standard so that future domains can extend one governed recommendation grammar rather than inventing their own local recommendation meanings.

## Core Concepts

The platform uses the following core concepts.

### Recommendation record

A recommendation record is the governed object that preserves what the system recommended for a particular decision case, under an explicit scope, action class, and decision context.

### Recommendation path

Recommendation path is the specific governed path of action, wait, simulation-first, information gathering, escalation, or abstention that the system identified as the preferred decision output for the case at that point in time.

### Action recommendation

Action recommendation is the substantive recommended course of action expressed by the recommendation record, including both the shared action class and the concrete recommended path within the domain's feasible action space.

### Recommendation action class

Recommendation action class is the shared cross-domain category that identifies the kind of governed decision output the recommendation represents.

### Direct-action recommendation

Direct-action recommendation is a recommendation whose preferred path is to take or withhold concrete action rather than to route first into review, abstention, or further decision preparation.

### Confidence statement

Confidence statement is the governed expression of how strongly the platform stands behind the recommendation, taking into account not only modeled support but also knowledge quality, causal coverage, contradiction, and execution realism.

### Constraint context

Constraint context is the governed reference to the commercial, operational, financial, stock, governance, brand, or other constraints that materially shaped the recommendation.

### Uncertainty context

Uncertainty context is the governed reference to the missingness, contradiction, regime instability, observability weakness, or other uncertainty conditions that materially qualify the recommendation.

### Failure-state warning

Failure-state warning is the governed reference to any active warning that the case may be distorted by false continuation, local optimization risk, stock blindness, regime mismatch, or another materially relevant failure pattern.

### Recommendation scope

Recommendation scope is the set of decision, reporting, tenant, client, and related business-object references that determines what population the recommendation concerns and how it may later be shown or reused.

### Recommendation lineage

Recommendation lineage is the reconstructible chain connecting the decision case, simulation or counterfactual inputs where relevant, the recommendation path itself, later approval or override, later execution, later outcomes, later post-mortem judgment, and later memory or policy-learning reuse.

### Simulation linkage

Simulation linkage is the explicit connection between the recommendation record and any simulation or counterfactual artifacts that materially informed it.

### Approval linkage

Approval linkage is the explicit connection between the recommendation record and any later approval record that accepted, deferred, rejected, escalated, or conditionally handled it.

### Override linkage

Override linkage is the explicit connection between the recommendation record and any later override record that replaced or materially altered the original recommended path.

### Execution linkage

Execution linkage is the explicit connection between the recommendation record and the later executed path, execution conditions, execution deviations, and realized outcomes.

### Post-mortem reuse

Post-mortem reuse is the governed reuse of recommendation records as evidence for judging recommendation quality after execution and outcomes are observed.

### Decision-memory reuse

Decision-memory reuse is the governed reuse of recommendation records inside decision memory objects, case comparison, retrieval, explanation, and later policy-learning review where lineage and evidence discipline remain intact.

## Shared Recommendation Record

At platform level, a recommendation record is the formal governed object that preserves what the system actually recommended for a governed decision case.

It exists because a recommendation record is not the same thing as an output package, although an output package may carry it. The output package governs delivery, scope metadata, and presentation context. The recommendation record governs the underlying decision object itself: what action was preferred, why it was preferred, what decision scope it applied to, and what constraints, uncertainty, and warnings qualified that preference.

The shared recommendation record must preserve, conceptually, all of the following. It must preserve a recommendation record ID so the recommendation has stable identity. It must preserve the originating case ID and a domain reference so ownership remains explicit. It must preserve the recommendation action class and the recommended action path reference so later systems can reconstruct what the platform actually preferred. It must preserve decision scope, reporting scope where relevant, tenant or client scope, and related business-object references so decision meaning is not detached from its governed context. It must preserve a confidence statement reference, a constraint-context reference, an uncertainty-context reference, and a failure-state warning reference where relevant so the recommendation is not remembered as if it were unconditional. It must preserve simulation or counterfactual reference where relevant. It must preserve lineage or version reference and timestamp so later processes know which governed context produced it.

This is governed object meaning, not code schema. A recommendation record must remain interpretable as a first-class decision object, not as presentation residue.

## Recommendation Action Classes

The platform requires one shared cross-domain action-class grammar for recommendation records.

At minimum, the shared governed action classes are recommend act now, recommend wait, recommend simulate first, recommend gather more information, escalate for review, and abstain from strong recommendation.

Recommend act now is the class in which the preferred path is immediate direct action under the current decision conditions. Recommend wait is the class in which the disciplined preferred path is delay rather than immediate commitment. Recommend simulate first is the class in which structured evaluation is the preferred next step before action is justified. Recommend gather more information is the class in which the preferred next step is additional evidence gathering rather than commitment. Escalate for review is the class in which the recommendation path itself is to move into accountable human or higher-authority review. Abstain from strong recommendation is the class in which the system preserves that it cannot justify a stronger directional recommendation under current conditions.

These are shared governed action classes. Domains may add narrower subtypes beneath them where needed, but they may not silently replace, blur, or reinterpret these classes into incompatible local status semantics. Shared recommendation grammar depends on these classes remaining stable enough that later approval review, override comparison, execution comparison, and post-mortem judgment can distinguish what kind of recommendation was actually made.

## Minimum Shared Metadata for Recommendation Records

Every governed recommendation record must carry minimum shared metadata.

### Recommendation record ID

This is the unique stable identifier for the recommendation record.

### Originating case ID

This is the stable reference to the decision case from which the recommendation record arises.

### Domain reference

This is the stable reference to the domain that owns the recommendation record.

### Recommendation action class

This is the shared governed action class under which the recommendation is made.

### Recommended action path reference

This is the reference to the concrete recommended path preserved by the recommendation record.

### Decision scope reference

This is the explicit decision scope governing the recommendation record.

### Reporting scope reference where relevant

This is the reporting scope reference governing later display or delivery where that concept is relevant.

### Tenant or client scope reference

This is the tenant boundary and client-population context under which the recommendation record is valid.

### Related business-object references

These are the references to the material domain business objects the recommendation concerns.

### Confidence statement reference

This is the governed reference to the recommendation's confidence position.

### Constraint-context reference

This is the governed reference to the constraints materially shaping the recommendation.

### Uncertainty-context reference

This is the governed reference to the uncertainties materially qualifying the recommendation.

### Failure-state warning reference where relevant

This is the governed warning reference where an active failure-state concern materially qualifies the recommendation.

### Simulation or counterfactual reference where relevant

This is the governed reference to simulation or counterfactual artifacts that materially informed the recommendation.

### Lineage or version reference

This is the lineage and version reference needed to reconstruct the governing context of the recommendation record later.

### Timestamp

This is the time at which the recommendation record was formed or fixed.

These are minimum shared metadata elements. Domains may extend them, but they may not omit or redefine them when the object is claimed as a governed platform recommendation record.

## Lineage Rules

Every recommendation record must link back to a decision case. Without that case linkage, the recommendation loses its governed decision context and cannot be interpreted honestly.

Approval records may later act on recommendation records. Approval linkage must preserve whether the recommendation was accepted, deferred, rejected, escalated, or conditionally handled. Override records may later replace or alter recommendation paths, and override linkage must preserve the relationship between the original recommendation path and the later human-selected path.

Escalation and abstention records may reference recommendation paths where relevant. Execution deviation and outcome objects may later compare against recommendation records so the platform can distinguish what was recommended from what was approved, executed, and realized. Post-mortem objects may later judge recommendation quality, including whether the recommendation was sound, weak, incomplete, distorted by failure-state blindness, or weakened by simulation miss or constraint miss.

Decision memory and policy learning may reuse recommendation records only with preserved lineage and evidence discipline. Recommendation history must not be treated as policy-learning evidence merely because many recommendation records exist. Reuse must preserve linkage to case, execution, outcome, post-mortem, and other relevant downstream evidence so the platform does not learn from recommendation frequency alone.

Recommendation lineage therefore connects case, recommendation, approval or override where relevant, execution comparison, post-mortem judgment, and memory or policy-learning reuse into one reconstructible chain. If that chain breaks, the recommendation record becomes too weak for serious reuse.

## Domain Inheritance Rules

All admitted domains must inherit this shared recommendation grammar.

At minimum, every domain-local workflow contract, recommendation object design, output logic, approval review flow, execution comparison design, post-mortem design, and policy-learning reuse logic that depends on recommendation must align with the following rules. A recommendation record is a first-class governed object. It is not just presentation output. It is not the same thing as an output package. It must remain distinct from approval, override, escalation, abstention, execution, and outcome. It must preserve what action was preferred and why. Confidence, uncertainty, constraints, and failure-state context are part of recommendation meaning.

Domain-local workflow contracts must therefore inherit this standard rather than invent their own recommendation object semantics. Domains may add narrower local meaning beneath the shared grammar, but they may not redefine the shared meanings of recommendation record, action class, action path, confidence statement, lineage, or reuse.

## Domain Extension Rules

Domains may extend this standard where their operating reality requires richer action-path structure, narrower action-class subtypes, more specific confidence or uncertainty references, or more domain-specific business-object references.

Valid domain extension may include additional metadata fields, narrower direct-action subtypes, richer explanation-supporting references, more specific failure-state warning taxonomies, or stricter lineage expectations.

Domain extension is invalid when it does any of the following. Reduces recommendation to thin status labels. Blurs recommendation with approval or execution. Removes action-path meaning. Preserves confidence without corresponding uncertainty or constraint context. Drops simulation linkage where simulation materially informed the recommendation. Replaces governed recommendation structure with explanation prose or local presentation artifacts. Uses domain-local convenience to rewrite shared recommendation semantics.

Extension is allowed. Redefinition of shared meaning is not.

## Governance Linkage

This standard is directly governance-linked because recommendation is one of the central governed decision objects of the platform.

The shared decision case and memory standard should treat this file as the controlling reference for recommendation lineage. The shared output metadata standard should treat it as the controlling reference for what recommendation object an output package may carry. The shared simulation and counterfactual standard should treat it as the controlling reference for simulation linkage into recommendation. The shared approval and override standard, the shared escalation and abstention standard, the shared execution deviation and outcome standard, and the shared post-mortem standard should all treat it as the controlling reference for recommendation comparison and downstream judgment.

Changes to shared recommendation meaning, action-class grammar, required context, lineage expectations, or reuse rules are consequential platform changes. They must go through formal governance rather than domain-local adjustment.

## Failure Modes in Recommendation Record Design

Weak recommendation record design creates direct platform risk.

### Recommendation reduced to thin status labels

The platform preserves that something was recommended but not what action path was actually preferred, why it was preferred, or how it should later be compared.

### Recommendation meaning drifting across domains

Different domains begin using recommendation record to mean different things, destroying shared judgment and reuse across the platform.

### Broken linkage from case to recommendation

Recommendation records cannot be tied back to the originating decision case, so later approval review, execution comparison, and post-mortem judgment lose decision context.

### Recommendation confused with approval or execution

The platform begins treating what was recommended as though it were what was approved or what actually happened, collapsing distinct parts of the decision loop into one ambiguous record.

### Confidence preserved without uncertainty or constraint context

The recommendation retains a confidence label but loses the context needed to interpret how conditional, fragile, or bounded that confidence really was.

### Simulation-informed recommendation with no preserved simulation linkage

The platform later claims a recommendation was simulation-informed, but the relevant simulation or counterfactual artifacts cannot be reconstructed.

### Post-mortem unable to judge recommendation quality because recommendation record was too weak

The platform later wants to judge whether the recommendation itself was sound, but the record is too thin to compare seriously with execution and realized outcomes.

### Policy-learning overreacting to recommendation history that was poorly structured

The platform attempts to learn from recommendation history even though action-path meaning, downstream lineage, or evidence discipline is too weak to justify that reuse.

These failure modes are not minor documentation defects. They are ways a decision platform can appear to preserve recommendations while actually forgetting what it recommended.

## Non-Negotiables

1. A recommendation record is a first-class governed decision object.
2. A recommendation record is not just an output card, label, or explanation paragraph.
3. Recommendation must preserve what action path was actually recommended.
4. Recommendation must remain distinct from approval, override, escalation, abstention, execution, and outcome.
5. Confidence, uncertainty, constraints, and failure-state context are part of recommendation meaning.
6. Every recommendation record must remain linked to a decision case.
7. Simulation linkage must be preserved where simulation materially informed recommendation.
8. Post-mortem and policy-learning reuse require preserved lineage and evidence discipline.
9. Domain-local workflow contracts may extend this standard, but they may not redefine it.
10. Future domains need one shared recommendation grammar to remain coherent.

## Closing Statement

This document protects recommendation from collapsing into presentation output or thin workflow status.

That protection matters because recommendation must remain a governed decision object whose value depends on preserved action-path meaning, scope, and lineage. Future domains need one shared recommendation grammar to avoid drift in how the platform records what it actually preferred, how later humans acted on it, and how later learning judges whether that preference was sound.

If this standard remains intact, future domains can issue recommendations in different business settings while still preserving one shared recommendation object meaning across the platform. If it weakens, recommendation history will become harder to compare, harder to judge, and harder to learn from precisely when the platform most depends on it.