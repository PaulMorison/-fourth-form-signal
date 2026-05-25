# Simulation and Counterfactual Design for Promotional Allocation Domain 01

## Purpose of This Document

This document defines how simulation and counterfactual reasoning should work for the Promotional Allocation domain.

It exists because simulation is one of the easiest parts of the platform to dilute. Without architectural control, simulation drifts into shallow what-if analysis, uplift theater, scenario graphics without intervention logic, or broad narrative speculation that looks sophisticated but does not improve decision quality.

This document is therefore a control document for simulation design.

It defines what simulation is meant to do, what objects it must operate on, how it must handle multi-store and tenant-aware conditions, what counterfactuals it must support, what outputs it must produce, and what standards it must satisfy before it is allowed to influence governed decision output.

It is the canonical simulation control document for Domain 01. Future simulation logic, counterfactual design, and promotion decision workflows must align with it unless a formal decision record explicitly revises it.

## Role of Simulation in the Platform

Simulation sits between interpreted commercial state and governed action.

In the broader platform, raw reality is first ingested, structured, quality-assessed, interpreted, and tested for failure-state concerns. Causal reasoning and state geometry help the system understand what is probably happening and why. Simulation then uses that interpreted state to examine how candidate actions may deform the system before commitment.

Simulation is therefore not the first step and not the final authority.

It is the disciplined bridge between interpretation and action.

In practical terms, simulation should consume decision context, state interpretation, failure-state signals, graph-backed memory, causal pathways, local constraints, and candidate actions. It should then produce consequence estimates that can be used by decision-focused optimization, constitutional review, and explanation assembly.

Its job is to improve the quality of the decision, not to replace the rest of the stack.

## Why Simulation Is Necessary in Promotional Allocation

Observation and prediction are not enough in promotional allocation because the act of promoting changes the system being observed.

Promotions alter customer response, stock flow, perceived demand, margin quality, substitution patterns, cannibalization, timing, and operational load. The business is not simply forecasting a passive target. It is choosing an intervention that changes the commercial state.

This is intensified by the one-to-many nature of real retail promotion structures.

One network promotion may apply across many stores, but each store may have different stock reality, execution readiness, demand context, override conditions, and operating friction. A network-level average is therefore insufficient. The platform must test what the intervention is likely to do when translated into many local store conditions.

Simulation is necessary because the platform must answer questions that neither historical reporting nor plain prediction can answer responsibly.

- What happens if the promotion runs now rather than later?
- What happens if it runs broadly rather than selectively?
- Which stores should participate and which should be withheld?
- What side effects appear if stock is weaker than expected?
- Does the action create robust payoff or only fragile upside?

Those are simulation questions.

## What Simulation Is and Is Not

Valid simulation in this platform is the disciplined evaluation of candidate promotional actions against plausible future conditions using interpreted state, causal intervention logic, local constraints, and explicit uncertainty.

It is a structured attempt to estimate how the commercial system may respond if one feasible action is taken instead of another.

It is not any of the following.

- It is not a dashboard what-if widget that merely changes one variable and redraws a chart.
- It is not a simple uplift model relabeled as simulation.
- It is not scenario storytelling disconnected from the actual decision objects of the domain.
- It is not a global average forecast applied indiscriminately to all stores.
- It is not a source of decision authority that bypasses constitutional review.
- It is not a visual exercise designed to impress rather than to discipline action.

Simulation is valid only when it remains intervention-aware, domain-grounded, constraint-aware, uncertainty-aware, and post-decision accountable.

## Core Simulation Thesis

Promotional allocation simulation should estimate how a network promotion, translated into store promotion instances under heterogeneous local conditions, is likely to deform commercial state across plausible futures so that the platform can choose robust, feasible, tenant-safe action rather than merely extrapolate visible response.

That is the central thesis.

The simulation is not trying to guess one number. It is trying to improve intervention quality under uncertainty.

## Simulation Unit of Analysis

Simulation in Domain 01 is hierarchical rather than flat.

### Network promotion

The network promotion is the governed promotion framework that may apply across many stores, store groups, or other authorized operating populations. It is the shared intervention structure from which local realizations are derived.

### Promotion instance

The promotion instance is the dated activation of the network promotion for a defined period, product scope, and intended rollout window. It provides the concrete intervention candidate being evaluated.

### Store promotion instance

The store promotion instance is the primary local simulation object. It represents how the promotion instance exists in one store under that store's stock reality, demand context, execution state, and local governance conditions.

### Decision scope

Decision scope is the exact unit for which a recommendation is being assembled. In simulation terms, it defines which store promotion instances, store groups, or governed aggregates are being actively evaluated for action.

### Reporting scope

Reporting scope defines what simulation outputs may be shown to a given client group, store group, operator, or tenant. It limits visibility, not necessarily learning.

### Learning scope

Learning scope defines what broader network history, outcomes, and calibration evidence the simulation layer may use to improve its quality where governance permits. It may be broader than both reporting scope and decision scope.

The unit of analysis is therefore not one chain-wide forecast and not one isolated store case. It is a governed hierarchy of intervention objects and local realizations.

## Multi-Store and One-to-Many Simulation Logic

The simulation layer must be able to take one network promotion and evaluate it across many stores with materially different local conditions.

That is a structural requirement, not a future enhancement.

In a Priceline-like one-to-many structure, the promotion may be centrally defined while local conditions vary sharply. The simulation must therefore represent two realities at once.

First, the shared promotion mechanics, banner rules, timing logic, and network-level intervention structure.

Second, the heterogeneous local store conditions that deform the likely outcome of that shared intervention.

This requires the simulation to operate as a coordinated set of local evaluations linked by a shared network intervention, rather than as one average-chain scenario.

The same promotion instance may therefore produce different simulated consequences across stores because the local commercial terrain is different. Some stores may benefit. Some may create margin drag. Some may expose stock risk. Some may require deferral or exclusion. Some may only be acceptable under local override conditions.

Simulation must preserve that heterogeneity rather than washing it away into one answer.

## Local State Deformation Factors

A network promotion does not determine its own outcome. Local conditions deform it.

At minimum, the simulation must allow outcomes to be materially changed by the following local state factors.

### Store-specific stock reality

On-hand stock, replenishment reliability, stock cover, local availability gaps, and stock exposure must deform the simulated result because a promotion without executable stock is not the same intervention as the same promotion with healthy availability.

### Store-specific demand context

Local response history, customer mix, demand sensitivity, prior promotion saturation, event context, and competitive pressure must deform the expected outcome because the same offer can mean different things in different local commercial states.

### Store-specific execution state

Execution readiness, staffing, compliance reliability, display capability, and local friction must deform the simulation because outcome quality depends partly on whether the store can actually deliver the intervention as assumed.

### Local override conditions

Authorized local exceptions, management knowledge, and local operating constraints must be capable of modifying or conditioning the simulated action set. An override condition is not merely a reporting note. It can change the valid intervention options.

### Banner / brand rules

Banner-specific proposition rules, promotion norms, and brand constraints must deform the intervention logic so that invalid cross-brand transfer does not produce false confidence.

### Client or tenant boundary effects where relevant

Tenant and client boundaries do not usually change physical commercial response directly, but they do affect what evidence may be used, what comparisons may be shown, and what scenario detail may be assembled into client-facing decision packages. Where those boundaries alter available inputs or permissible outputs, they must be respected as real simulation conditions.

## Counterfactual Types

The simulation layer must support a defined set of intervention counterfactuals that matter in real promotional allocation decisions.

### Run vs do not run

Compare the commercial state if the promotion is activated against the state if it is withheld.

### Run broadly vs run selectively

Compare broad network rollout against selective inclusion based on local state, constraints, or risk.

### Run now vs delay

Compare immediate activation with delayed activation where the value of additional clarity, better stock position, or improved readiness may be material.

### Store inclusion vs exclusion

Test whether a specific store, store group, or client group should participate at all under current local conditions.

### Standard network support vs local override

Compare the default network promotion plan with a governed local exception or adjusted support pattern.

### Different allocation depths or support intensities

Compare different levels of support, presence, participation intensity, or promotion depth where those are part of the domain's feasible action space.

### Different stock conditions

Evaluate how the same intervention behaves under stronger or weaker local stock reality, replenishment certainty, or stock disruption assumptions.

### Different execution-readiness assumptions

Compare what happens if execution is strong, partial, or weak rather than assuming perfect operational delivery.

These counterfactual classes should be treated as governed intervention families, not as arbitrary permutations.

## Simulation Outputs

Simulation must produce more than expected uplift.

At minimum, the simulation layer should produce the following outputs in forms usable by optimization, constitutional review, and explanation.

### Expected commercial response

Expected unit, revenue, or demand-response effects under the simulated intervention.

### Payoff quality

The economic quality of the simulated outcome after considering margin, side effects, sustainability, and downstream consequences.

### Margin implications

Expected margin quality, discount cost, and broader economic trade-off associated with the simulated action.

### Stock consequences

Expected availability stress, depletion risk, replenishment exposure, stock distortion, and downstream stock implications.

### Risk of distortion

Expected exposure to pull-forward, cannibalization, substitution, apparent uplift without real strength, or other interpretation hazards.

### Local optimization risk

Evidence that a locally attractive action may damage broader network economics, client goals, or durable commercial health.

### Hidden decay risk

Evidence that the action may preserve visible motion while worsening underlying payoff quality or commercial force.

### Uncertainty-aware outcome range

A bounded range of plausible outcomes reflecting missingness, contradiction, model uncertainty, causal weakness, and execution variability.

### Likely failure-state transitions

An assessment of whether the action makes failure states more or less likely, including false continuation risk, distortion risk, regime fragility, and post-promotion weakness.

Simulation outputs must therefore support decision quality, not just scenario curiosity.

## Simulation and Surface/Manifold Logic

Simulation must use interpreted state geometry rather than treating all stores as flat, interchangeable cases.

The surface and manifold logic of the platform exists to describe commercial terrain: directional pressure, instability, roughness, attractor behavior, and regime deformation. Simulation should operate on that terrain.

In practical terms, this means the same promotion should not be simulated identically for two stores merely because their recent headline metrics look similar. If their state geometry differs, the intervention may behave differently.

Slope matters because it indicates directional commercial pressure.

Curvature matters because some stores are in highly sensitive states where small intervention differences create large response changes.

Roughness matters because weak visibility or unstable conditions should widen uncertainty and reduce confidence.

Basin behavior matters because some stores may sit inside sticky patterns such as repeated promotion dependence.

Deformation matters because the commercial terrain may have shifted and historical analogues may no longer be safe guides.

Simulation should therefore project interventions through the interpreted state surface, not around it.

## Simulation and Causal DAG Logic

Simulation must use causal intervention logic, not merely pattern continuation.

The Causal DAG layer provides a structured view of mechanisms, mediators, confounders, and intervention paths. Simulation should use that structure to ask what changes because the promotion is run, not merely what tended to co-occur historically.

In promotional allocation, this means the simulation should reason along pathways such as these.

- Promotion mechanics affect customer response.
- Customer response affects demand movement.
- Demand movement interacts with stock availability.
- Stock availability alters realized sales, substitution, and distortion.
- Promotion depth and execution quality affect margin and payoff quality.

The DAG is also what helps simulation separate genuine intervention effect from coincident background conditions. Without this, counterfactuals degrade into correlation-based storytelling.

Simulation does not require perfect causal certainty, but it does require explicit intervention logic strong enough to support explanation and post-mortem revision.

## Simulation and Constitution

Simulation must operate under the decision constitution, not beside it.

Its role is to support disciplined action selection, disciplined waiting, disciplined escalation, and disciplined abstention where evidence is weak.

Simulation should help the platform act now when the intervention appears feasible, coherent, and robust under the current state.

It should help the platform recommend waiting when delay has meaningful value of information.

It should help the platform escalate when downside asymmetry is severe, contradiction remains material, or regime change is not well bounded.

It should help the platform avoid fragile upside by showing where attractive-looking scenarios depend on narrow assumptions or unrealistically clean execution.

Simulation is therefore constitutionally useful when it sharpens discipline. It is constitutionally dangerous when it amplifies false confidence.

## Tenant-Safe Simulation Design

Simulation in Domain 01 must be tenant-safe from calibration through output.

The platform may use broader network evidence for simulation calibration where learning scope permits. This is especially important in one-to-many structures such as Priceline, where broader store history may materially improve local scenario quality.

However, broader calibration rights do not imply broader reporting rights.

The simulation design must preserve the separation of learning scope, reporting scope, and decision scope at all times.

This means the following.

- Calibration may use broader authorized network evidence.
- Recommendation outputs must remain client-scoped.
- Explanation artifacts must not reveal unauthorized store-level detail.
- Comparative scenario outputs must be benchmark-safe and respect aggregation rules.
- Cross-store learning may be allowed while cross-store reporting remains restricted.
- Cross-brand transfer must not occur casually and must remain governed by banner validity and access-control policy.

Tenant-safe simulation is therefore not a presentation concern added at the end. It is part of simulation design itself.

## Validity Requirements

Simulation output should influence a recommendation only when it satisfies a credible validity threshold.

At minimum, that threshold requires the following.

- The decision scope is explicit.
- The relevant network promotion, promotion instance, and store promotion instances are correctly identified.
- Local state inputs are materially sufficient for the stores being simulated.
- Knowledge-quality signals are visible and materially reflected in uncertainty.
- Causal coverage is strong enough to justify intervention reasoning at the required level.
- Constraint profiles are complete enough that infeasible actions are not being treated as valid scenarios.
- Banner or brand transfer assumptions are defensible.
- Tenant and reporting boundaries are preserved.
- The simulation is explainable in commercial terms.
- The scenario can later be evaluated against realized outcomes through a post-mortem object.

If these conditions are weak, the simulation may still be useful for exploration, but it is not strong enough to drive authoritative recommendation behavior.

## Failure Modes in Simulation Design

Poor simulation design introduces its own failure modes.

### Network averaging error

The system averages across stores so aggressively that local differences disappear, producing a chain-level answer that is wrong for many stores.

### False local precision

The system presents narrow store-level outcome claims even when local evidence is weak, contradictory, or heavily borrowed from broader network priors.

### Hidden stock distortion

The simulation ignores local stock reality or replenishment weakness, so the intervention appears better than it could be in practice.

### Execution blindness

The simulation assumes clean, uniform execution across stores and therefore overstates likely payoff quality.

### Tenant leakage

Simulation outputs, comparative views, or explanation traces expose unauthorized cross-store detail or reveal information outside reporting entitlement.

### Invalid cross-brand transfer

Evidence or calibration from one banner or brand is used as though it were safely transferable to another when proposition logic or customer response patterns differ materially.

### Overconfident what-if storytelling

The platform presents scenario outputs as though they are strong intervention evidence when they are actually weakly grounded exploratory narratives.

### Simulation without post-mortem learning

The system simulates actions repeatedly but does not compare them rigorously to realized outcomes, causing simulation quality to stagnate or degrade invisibly.

These are not minor implementation errors. They are ways simulation can actively damage decision quality.

## Post-Decision Learning for Simulation

Simulation quality must improve from realized outcomes.

Every materially simulated promotion decision should create a learning trail that links the simulated scenarios, the chosen action, the executed action, the realized local conditions, and the observed outcomes.

At minimum, post-decision learning for simulation should do the following.

- Compare expected and realized outcomes at the correct decision scope.
- Record how actual stock, execution, and local demand conditions differed from simulated assumptions.
- Identify whether the main miss came from state interpretation, causal structure, stock assumptions, execution assumptions, brand transfer assumptions, or regime change.
- Update calibration using permitted learning scope.
- Improve uncertainty ranges and confidence behavior where prior simulation was too narrow or too broad.
- Feed revised understanding back into the graph, causal, policy, and simulation layers.

Simulation without disciplined post-mortem learning is not acceptable in this platform.

## Non-Negotiables

1. Simulation is the bridge between interpretation and action, not a decorative analytics layer.
2. Simulation must operate on the actual domain objects of Domain 01: network promotion, promotion instance, and store promotion instance.
3. One network promotion must be simulatable across many stores with heterogeneous local state.
4. Local stock reality, demand context, execution state, and override conditions must materially affect simulated outcomes.
5. Simulation must represent uncertainty, contradiction, and weak observability rather than hiding them.
6. Simulation must use causal intervention logic where action consequences are being evaluated.
7. Simulation must remain constraint-aware and constitutionally governed.
8. The platform may learn broadly where governance permits, but outputs must remain tenant-safe and client-scoped.
9. Benchmarking or comparative scenario outputs must remain benchmark-safe and access-controlled.
10. Simulation must be accountable to post-decision learning and formal post-mortem review.

## Closing Statement

Simulation protects the platform from acting on attractive stories that have not been tested against the actual structure of the commercial system.

In Domain 01, that protection matters because promotions can create visible movement while concealing distortion, stock stress, margin weakness, and false continuation underneath. A disciplined simulation layer helps the platform see those risks before commitment, compare feasible alternatives under real local conditions, and act with stronger constitutional discipline.

If simulation remains faithful to this design, it will improve decision quality.

If it drifts into shallow what-if analysis, it will create confidence without control.