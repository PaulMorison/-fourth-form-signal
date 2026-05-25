# Shared Simulation and Counterfactual Record Standard for the Fourth Form Retail Decision Intelligence Platform

## Purpose of This Document

This document defines the shared platform standard for simulation records and counterfactual records across all current and future domains.

It exists because the platform cannot remain one governed decision system if simulation artifacts are left as domain-local scenario notes, model snapshots, or loosely narrated what-if reasoning with no shared object grammar, no stable lineage, and no reliable linkage to decision cases, recommendation paths, post-mortem review, and policy learning.

Without a shared standard, the platform will drift into domain-specific simulation semantics, weak preservation of assumption sets, counterfactual comparison that does not preserve what was compared against what, simulation outputs reused outside valid scope, post-mortem review that cannot compare expected versus realized outcomes seriously, and policy-learning behavior that overreacts to poorly structured simulation history.

This document is therefore a control document for shared simulation and counterfactual record structure.

It defines the core concepts, shared object meanings, minimum metadata requirements, lineage rules, inheritance rules, extension rules, and governance linkage that all domains must follow when simulation or counterfactual reasoning is preserved as a governed decision-support artifact.

It is the canonical shared simulation and counterfactual record standard for the platform. Future domain simulation logic, counterfactual artifacts, recommendation linkage, post-mortem comparison, and policy-learning reuse must align with it unless a formal decision record explicitly revises it.

## Role of This Document in the Platform

This document governs the shared object grammar for simulation and counterfactual artifacts that sit between decision-case formation and later recommendation, execution, post-mortem, and learning reuse.

The shared decision case and decision memory standard defines how decision episodes are anchored. The shared output metadata standard defines how governed outputs carry scope and lineage. Domain-local workflow contracts define when simulation-first behavior or simulation-informed recommendation is valid. The shared execution deviation and outcome standard defines how realized reality is recorded after action. The shared post-mortem standard defines how simulated expectation may later be judged against realized consequence. The policy-learning evidence admission and update-threshold standard defines when simulation history may legitimately influence future policy behavior. This document governs the simulation records and counterfactual records that connect those layers by preserving what action path was evaluated, under what assumptions, within what scope, against what comparison basis, and with what later reuse meaning.

In practical terms, this document governs what a simulation record is, what a counterfactual record is, what minimum metadata those records must preserve, how they link to recommendation and execution lineage, and how later post-mortem and policy-learning processes may reuse them without losing meaning.

This document therefore governs simulation and counterfactual object structure as part of platform coherence.

## Core Thesis

In the Fourth Form platform, simulation and counterfactual artifacts must be preserved as first-class governed objects whose action path, reference path, assumptions, scope, horizon, comparability basis, and lineage remain explicit enough for later recommendation use, execution comparison, post-mortem review, and policy-learning reuse.

That is the core thesis.

Simulation is a governed decision-support object, not loose scenario narration. A counterfactual record is not a narrative what if. It is a governed comparison object that must preserve what was compared against what.

## What This Standard Is and Is Not

This standard is the shared platform rule for how simulation and counterfactual reasoning is recorded, linked, preserved, and reused across domains.

It is not any of the following.

- It is not a generic data-science experimentation guide.
- It is not a notebook or model-output archive.
- It is not permission for domains to narrate scenario thinking without preserving scope, assumptions, or lineage.
- It is not a substitute for domain-local simulation design or causal reasoning.
- It is not a reporting schema for comparative charts.
- It is not a reason to treat simulation snapshots as if they were self-explanatory once separated from decision context.

A real shared simulation and counterfactual standard means the platform can answer the following questions for any materially simulated decision episode.

- What decision case the simulation belonged to.
- What action path was simulated.
- What reference action path or alternative path the comparison used.
- What assumption set, scope, and horizon governed the simulation.
- How the simulation informed recommendation or simulation-first output.
- How later execution, post-mortem, and policy learning may reuse that artifact.

## Why a Shared Simulation and Counterfactual Standard Is Necessary

Domains must not define simulation records and counterfactual records independently because simulation is one of the easiest places for a decision platform to look rigorous while losing structural meaning.

If simulation artifacts are left local, several failures follow. One domain treats simulation as a formal decision-support record while another treats it as advisory narrative. One domain preserves assumptions while another preserves only a result snapshot. One domain compares action paths seriously while another blurs comparison against an implicit baseline. Recommendation packages, post-mortem objects, and policy-learning review then inherit incompatible simulation artifacts that cannot be reused or compared coherently.

The platform therefore needs one shared standard so that future domains can extend one governed simulation grammar rather than inventing their own simulation object meanings.

## Core Concepts

The platform uses the following core concepts.

### Simulation record

A simulation record is the governed object that preserves one simulated evaluation of a candidate action path under an explicit assumption set, scope, horizon, and decision context.

### Counterfactual record

A counterfactual record is the governed object that preserves a structured comparison between one simulated action path and one reference action path, with explicit comparability basis and decision-use meaning.

### Simulated action path

Simulated action path is the governed action path being evaluated through simulation, whether that path is immediate action, delayed action, selective rollout, override path, simulation-first option, or another domain-valid intervention path.

### Reference action path

Reference action path is the governed comparison path against which the simulated action path is being evaluated. It may be a do-not-run path, a delay path, a narrower rollout path, a standard path, an override path, or another explicitly governed comparator.

### Counterfactual type

Counterfactual type is the governed category describing what comparison family is being tested, such as run versus do not run, act now versus delay, broad rollout versus selective rollout, standard path versus override path, stronger execution assumptions versus weaker execution assumptions, or higher stock availability versus lower stock availability.

### Simulation assumption set

Simulation assumption set is the explicit set of intervention, operating, stock, execution, demand, causal, constraint, or regime assumptions under which the simulated result is meaningful.

### Simulation scope

Simulation scope is the governed decision, reporting, tenant, client, and where relevant learning-scope context that determines what population the simulation concerns and how it may later be reused.

### Simulation horizon

Simulation horizon is the defined time window, outcome horizon, or review horizon within which the simulated consequence is being evaluated.

### Simulation lineage

Simulation lineage is the reconstructible chain connecting the decision case, simulated action path, counterfactual comparison where relevant, related recommendation use, later execution reality, later post-mortem comparison, and later policy-learning reuse.

### Counterfactual comparability

Counterfactual comparability is the governed judgment that the compared action paths are being evaluated under a coherent enough basis that the comparison means something serious rather than merely contrasting unrelated scenarios.

### Recommendation linkage

Recommendation linkage is the explicit connection between simulation or counterfactual artifacts and the recommendation package, simulation-first output, abstention, escalation, or other governed decision output that later used them.

### Execution linkage

Execution linkage is the explicit connection between the simulated expectation and the later executed action path, execution conditions, and realized outcome where action was later taken.

### Post-mortem reuse

Post-mortem reuse is the governed reuse of simulation and counterfactual records as structured evidence for comparing expected versus realized consequence during post-decision judgment.

### Policy-learning reuse

Policy-learning reuse is the governed reuse of simulation and counterfactual history for calibration, threshold refinement, or other policy improvement only when lineage and evidence discipline remain strong enough to support legitimate learning.

## Shared Simulation Record

At platform level, a simulation record is the formal governed object that preserves how one candidate action path was evaluated before commitment or before later comparative review.

It exists because simulation is not just a model output snapshot. The platform must preserve which case the simulation belonged to, what action path it evaluated, what assumptions made the result meaningful, what scope governed the evaluation, what horizon was being considered, and how the result was later used in decisioning.

The shared simulation record must preserve, conceptually, all of the following. It must preserve a simulation record ID so the simulated episode has stable identity. It must preserve the originating case ID so the simulation remains anchored to a governed decision episode. It must preserve a domain reference so ownership remains explicit. It must preserve the simulated action path reference. It must preserve the simulation scope reference and the tenant or client scope reference where relevant so later reuse does not strip boundary meaning away. It must preserve the simulation assumption-set reference and the simulation horizon reference. It must preserve a related recommendation reference where relevant so simulation-informed recommendation remains reconstructible. It must preserve a lineage or version reference and a timestamp so later systems can understand which governed context produced the simulation artifact.

This is governed object meaning, not code schema. A simulation record must remain interpretable as a decision-support object rather than as an isolated result row.

## Shared Counterfactual Record

At platform level, a counterfactual record is the formal governed object that preserves one explicit comparison between a simulated action path and a reference action path.

It exists because a counterfactual record is not just a narrative what if. Its value depends on preserving what was compared against what, what counterfactual type governed the comparison, what comparability basis justified the contrast, and what decision use the comparison later served.

The shared counterfactual record must preserve, conceptually, all of the following. It must preserve a counterfactual record ID so the comparison has stable identity. It must preserve the originating case ID and the domain reference. It must preserve the counterfactual type. It must preserve the simulated action path reference and the reference action path reference. It must preserve a comparability basis reference so later users know why the comparison was valid. It must preserve the simulation scope reference and horizon reference. It must preserve a related recommendation reference where relevant. It must preserve a lineage or version reference and a timestamp.

Counterfactual records may include governed forms such as run versus do not run, act now versus delay, broad rollout versus selective rollout, standard path versus override path, stronger execution assumptions versus weaker execution assumptions, and higher stock availability versus lower stock availability. Domains may extend these governed forms where their operating reality requires it, but they may not redefine the shared meaning of counterfactual comparison itself.

## Minimum Shared Metadata for Simulation Records

Every governed simulation record must carry minimum shared metadata.

### Simulation record ID

This is the unique stable identifier for the simulation record.

### Originating case ID

This is the stable reference to the decision case from which the simulation record arises.

### Domain reference

This is the stable reference to the domain that owns the simulation record.

### Simulated action path reference

This is the reference to the action path being evaluated through simulation.

### Simulation scope reference

This is the explicit simulation scope governing the record.

### Tenant or client scope reference where relevant

This is the tenant boundary and client-population context under which the simulation record is valid where that concept applies.

### Simulation assumption-set reference

This is the governed reference to the assumption set that makes the simulated evaluation interpretable.

### Simulation horizon reference

This is the governed reference to the outcome or review horizon under which the simulation result is being considered.

### Related recommendation reference where relevant

This is the recommendation package, simulation-first package, or equivalent governed decision output that later used the simulation record where that link exists.

### Lineage or version reference

This is the lineage and version reference needed to reconstruct the governing context of the simulation record later.

### Timestamp

This is the time at which the simulation record was formed or fixed.

These are minimum shared metadata elements. Domains may extend them, but they may not omit or redefine them when the object is claimed as a governed platform simulation record.

## Minimum Shared Metadata for Counterfactual Records

Every governed counterfactual record must carry minimum shared metadata.

### Counterfactual record ID

This is the unique stable identifier for the counterfactual record.

### Originating case ID

This is the stable reference to the decision case from which the counterfactual record arises.

### Domain reference

This is the stable reference to the domain that owns the counterfactual record.

### Counterfactual type

This is the governed counterfactual family under which the comparison is being made.

### Simulated action path reference

This is the reference to the evaluated action path being compared.

### Reference action path reference

This is the reference to the comparison path against which the simulated action path is being judged.

### Comparability basis reference

This is the governed reference to the basis that makes the counterfactual comparison valid enough to interpret seriously.

### Simulation scope reference

This is the explicit simulation scope governing the counterfactual record.

### Horizon reference

This is the governed reference to the time horizon or consequence horizon of the comparison.

### Related recommendation reference where relevant

This is the recommendation package, simulation-first package, or equivalent governed decision output that later used the counterfactual record where that link exists.

### Lineage or version reference

This is the lineage and version reference needed to reconstruct the governing context of the counterfactual record later.

### Timestamp

This is the time at which the counterfactual record was formed or fixed.

These are minimum shared metadata elements. Domains may extend them, but they may not omit or redefine them when the object is claimed as a governed platform counterfactual record.

## Lineage Rules

Simulation records must link back to decision cases. Counterfactual records must link back to simulation or decision context strongly enough that later systems can reconstruct what evaluation belonged to which decision episode.

Recommendation packages may reference simulation and counterfactual records where those artifacts materially informed a recommendation, simulation-first package, abstention, escalation, or other governed decision output. That recommendation linkage must preserve which simulated action path or counterfactual comparison influenced the decision and under what scope and assumption conditions.

Post-mortem objects may later compare simulated expectation with realized outcomes, but that comparison is valid only when simulation lineage, execution linkage, and realized outcome lineage remain strong enough to compare expected versus realized consequence honestly. Weak simulation lineage weakens post-mortem quality directly.

Policy learning may reuse simulation records only with preserved lineage and evidence discipline. Simulation history must not be reused as policy-learning evidence merely because it exists. Reuse must respect the shared evidence-admission and update-threshold standard, including preserved lineage, observation maturity, and adequate post-mortem interpretation where that is required.

Simulation lineage therefore connects backward to case and forward to recommendation, execution, post-mortem, and possible policy-learning reuse. If those links break, the simulation artifact stops functioning as a governed decision object.

## Domain Inheritance Rules

All admitted domains must inherit this shared simulation and counterfactual grammar.

At minimum, every domain-local simulation document, workflow contract, recommendation logic, and post-mortem design that uses simulation must align with the following rules. Simulation and counterfactual artifacts are first-class governed objects. A simulation record is not just a model output snapshot. A counterfactual record is not just a narrative what if. Simulation must preserve scope, assumptions, and lineage explicitly. Counterfactual comparison must preserve comparability rules explicitly. Simulation must remain reusable in recommendation, post-mortem, and policy learning without losing meaning.

Domain-local simulation documents must therefore inherit this standard rather than invent their own object grammar. Domains may become more specific, but they may not redefine the shared meanings of simulation record, counterfactual record, comparability, lineage, or reuse.

## Domain Extension Rules

Domains may extend this standard where their operating reality requires richer simulation assumption sets, more specific horizon types, more detailed counterfactual taxonomies, or more domain-specific comparability rules.

Valid domain extension may include additional metadata fields, narrower action-path taxonomies, richer operating-condition references, more specific horizon logic, or stricter post-mortem comparison rules.

Domain extension is invalid when it does any of the following. Redefines simulation as loose scenario narration. Redefines counterfactual records as informal storytelling. Removes explicit assumption-set meaning. Treats unrelated scenarios as comparable without governed basis. Breaks simulation scope discipline. Replaces lineage with explanation-only prose. Allows domain-local convenience to rewrite shared simulation semantics.

Extension is allowed. Redefinition of shared meaning is not.

## Governance Linkage

This standard is directly governance-linked because simulation artifacts influence recommendation behavior, later post-mortem judgment, and possible policy-learning reuse.

The shared decision case and memory standard should treat this file as the controlling reference for simulation lineage. The shared output metadata standard should treat it as the controlling reference when simulation-informed output packages reference governed simulation or counterfactual artifacts. The shared post-mortem standard should treat it as the controlling reference when expected versus realized comparison depends on prior simulation. The policy-learning evidence admission and update-threshold standard should treat it as the controlling reference when simulation history is proposed for learning reuse.

Changes to shared simulation meaning, counterfactual meaning, comparability rules, lineage expectations, or reuse rules are consequential platform changes. They must go through formal governance rather than domain-local adjustment.

## Failure Modes in Simulation and Counterfactual Record Design

Weak simulation and counterfactual record design creates direct platform risk.

### Simulation treated as narrative instead of governed object

The platform preserves scenario commentary but not the governed object needed to reconstruct what action path, assumptions, and scope were actually evaluated.

### Broken linkage to decision case

Simulation artifacts cannot be tied back to the originating decision case, so later recommendation, post-mortem, and learning logic cannot interpret them reliably.

### Unclear assumptions

The platform preserves a simulated result without preserving the simulation assumption set strongly enough to understand why the result looked the way it did.

### Counterfactuals without valid comparability

The platform compares action paths that do not share a valid comparability basis, producing contrasts that look useful but are not governed enough for serious decision use.

### Simulation results reused outside valid scope

Simulation artifacts are consumed in decisioning, reporting, or learning outside the tenant, client, decision, or learning scope under which they were valid.

### Domain-local simulation semantics drifting apart

Different domains begin using simulation record and counterfactual record to mean different things, destroying shared post-mortem and learning reuse across the platform.

### Post-mortem unable to compare expected versus realized because simulation records were too weak

The platform later wants to judge simulation miss or recommendation quality, but the original simulation artifacts do not preserve enough structure to support honest comparison.

### Policy-learning overreacting to poorly structured simulation history

Simulation history is reused for policy adaptation even though the lineage, comparability, post-mortem interpretation, or evidence quality is too weak to justify that reuse.

These failure modes are not minor documentation defects. They are ways simulation can appear sophisticated while becoming ungoverned and unreliable.

## Non-Negotiables

1. Simulation and counterfactual artifacts are first-class governed objects.
2. A simulation record is not just a model output snapshot.
3. A counterfactual record is not just a narrative what if.
4. Simulation must preserve scope, assumptions, and lineage explicitly.
5. Counterfactual comparison must preserve what was compared against what.
6. Counterfactual use requires explicit comparability basis.
7. Recommendation, execution, and post-mortem linkage must remain reconstructible.
8. Simulation history must not be reused for policy learning without evidence discipline.
9. Domain-local simulation documents may extend this standard, but they may not redefine it.
10. Shared simulation grammar must remain stable enough for future domains to inherit.

## Closing Statement

This document protects simulation from becoming loose scenario narrative and protects counterfactual comparison from becoming unstructured what-if storytelling.

That protection matters because simulation must remain a governed part of decision intelligence, not a decorative analytic side channel. Counterfactual value depends on preserved structure and lineage. Future domains need one shared simulation grammar so that recommendation linkage, post-mortem comparison, and policy-learning reuse remain coherent as the platform expands.

If this standard remains intact, future domains can reason counterfactually without drifting into incompatible local artifact design. If it weakens, simulation history will become harder to trust precisely when the platform most needs it for disciplined decision support.