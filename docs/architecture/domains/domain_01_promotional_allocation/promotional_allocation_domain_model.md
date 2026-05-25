# Promotional Allocation Domain Model for the Fourth Form Retail Decision Intelligence Platform

## Purpose of This Document

This document defines the promotional allocation domain model for the first practical wedge of the Fourth Form retail decision intelligence platform.

It exists to translate the broader system thesis and high-level architecture into a precise domain structure for promotion decision intelligence. Its purpose is not to describe a marketing workflow in general terms. Its purpose is to define the domain objects, scopes, relationships, and control boundaries that future data models, Python components, simulations, recommendation workflows, and post-decision learning systems must rely on.

This is a control document for domain structure.

If the domain model is vague, the architecture will drift into ad hoc data schemas, one-off promotion logic, unclear boundaries between store and network decisions, and unsafe reporting behavior across stores, brands, or client groups. This document exists to prevent that drift.

## Domain Model Role in the Platform

The platform architecture defines the system stack. This document populates that stack for the promotional allocation wedge.

It defines what the architecture is operating on when the domain is promotion decision intelligence. It gives precise meaning to the promotional entities, local state objects, decision objects, constraints, outcomes, and boundary objects that must flow through the shared layers of ingestion, canonical structure, state interpretation, graph-backed memory, causal reasoning, simulation, optimization, explanation, and post-decision learning.

In practical terms, this document is the bridge between architectural intent and domain implementation.

It should be usable by founders, architects, analysts, engineers, and AI coding tools as the canonical structural reference for the first wedge.

## Why Promotional Allocation Is the First Domain

Promotional allocation is the correct first proving ground because it is repeated, high-stakes, measurable, and commercially legible.

Promotion decisions are not isolated marketing events. They influence units, margin, stock flow, customer response, substitution, execution quality, timing distortion, and downstream planning quality. They also expose the exact kinds of failure the broader platform is meant to detect: false continuation, distorted interpretation, partial observability, local optimization failure, regime mismatch, and lagged recognition.

Promotional allocation is especially important because it contains both network-level structure and store-level variation.

One promotion framework may apply across many stores, yet the right action can still vary materially by local stock reality, local demand context, local execution state, or client boundary. That makes promotional allocation an ideal first domain for proving the platform's broader thesis: learn broadly where allowed, decide locally where necessary, explain clearly, and remain governed throughout.

## Domain Boundaries

This domain includes the following.

- Definition of network-level promotional structures.
- Translation of network promotions into store-level decision objects.
- Evaluation of which stores, store groups, client groups, or banners should participate, under what conditions, and with what level of support.
- Representation of store-level local state, including stock reality, demand context, and execution readiness.
- Promotion recommendation, override, execution, outcome capture, and post-mortem learning.
- Tenant boundaries, reporting rights, and learning permissions relevant to promotion decision intelligence.

This domain does not attempt to fully define every adjacent commercial function.

- It does not define the entire enterprise pricing architecture outside promotion decisions.
- It does not define creative production or marketing asset generation.
- It does not define supplier negotiation workflows except where supplier terms become decision constraints or payoff inputs.
- It does not replace broader assortment, replenishment, or category strategy, although those domains may provide important inputs and constraints.

The domain is therefore specific, but not narrow. It covers the promotion decision loop end to end.

## Core Domain Thesis

The core thesis of this domain is that promotional allocation is not the problem of asking whether a promotion works in the abstract. It is the problem of deciding where, when, and under what local conditions a network promotion should be activated, adjusted, withheld, or reviewed in order to improve durable commercial value.

This means the domain model must represent three realities at once.

First, promotions often originate as network structures, not as isolated store decisions.

Second, local store conditions can materially change the right answer.

Third, the system may learn from broad network evidence where governance permits, while still keeping reporting and recommendation output strictly scoped to the paying client store, client group, or authorized operating unit.

The domain model therefore separates network structure, local realization, and governed output as distinct concepts.

## Multi-Store, Multi-Brand, and Tenant Model

Multi-store, multi-brand, and tenant-aware operation is a first-class design condition of this domain. It is not a later enhancement.

The platform must support multiple stores, multiple client groups, and multiple retail banners or brands from the beginning. It must also support the fact that one promotion framework may govern many stores while the right decision still varies locally.

In this domain, the following distinctions matter.

**Store** is the local operating unit at which stock, execution, demand context, and realized outcomes are observed.

**Store group** is an operational or analytical grouping of stores used for coordinated rollout, benchmarking, simulation, learning, or local management. A store may belong to more than one store group depending on purpose.

**Banner / brand** is the retail trading identity under which a set of stores operates. A banner carries proposition logic, brand constraints, and promotion conventions that matter for valid comparison and policy learning.

**Client group** is the contractual or commercial group for which reporting, recommendations, and decision packages are assembled. A client group may represent one store, many stores, a managed subnetwork, or a brand-specific operating group.

**Tenant** is the top-level security and governance boundary that controls access rights, reporting entitlements, data-sharing permissions, and permitted learning behavior. In some deployments, one tenant may correspond to one client group. In others, a tenant may contain multiple client groups. The architecture must not assume they are always the same.

This model allows broader network learning where governance permits, while preserving strict output boundaries for each tenant and client group.

## Learning Scope vs Reporting Scope vs Decision Scope

These three scopes must remain separate architectural and domain concepts.

**Learning scope** is the set of stores, store groups, banners, brands, promotion instances, outcomes, and historical decision records that the platform is permitted to learn from. Learning scope may be broader than the client-facing view when governance permits aggregated network learning.

**Reporting scope** is the set of stores, groups, brands, or aggregates that a specific tenant or client group is permitted to see in dashboards, decision packages, benchmark outputs, and explanation views.

**Decision scope** is the exact unit for which the system is producing a recommendation. In this domain, decision scope may be one store promotion instance, one store group rollout, one client-group allocation decision, or a governed banner-level decision package.

These scopes must never be treated as interchangeable.

The platform may learn from a broader store network while reporting only on the stores or groups that belong to the paying client. It may also produce a decision for a single store even when the underlying learning scope spans many stores.

This separation is essential to tenant-safe operation.

## Priceline One-to-Many Promotion Structure

Priceline is an important early example of a one-to-many promotional structure.

A centrally defined promotion framework may apply across many Priceline stores. That network structure is commercially real and must be represented directly. The system should not pretend that each store's promotion begins as an isolated object.

At the same time, the domain model must preserve store-level realization.

The correct abstraction is therefore not one promotion per store and not one undifferentiated promotion for the whole chain. The correct abstraction is a layered structure.

First, a reusable promotion template defines the commercial pattern.

Second, a network promotion defines the governed promotion framework for a banner, network, or other authorized promotion population.

Third, a promotion instance activates that framework for a specific time window, product set, and target network scope.

Fourth, a store promotion instance represents how that promotion instance exists in one specific store under that store's local stock reality, demand context, execution readiness, and client boundary.

This is the correct one-to-many model for Priceline and a durable model for future brands.

## Core Domain Entities

The following are the core entities of the promotional allocation domain.

### Tenant

The governed security and data-sharing boundary under which access rights, reporting entitlements, and learning permissions are defined.

### Client group

The commercial group for which decision packages and reporting outputs are produced. This is often the paying client context.

### Banner / brand

The retail trading identity whose proposition, rules, and promotion norms shape valid promotion logic.

### Store

The local operating unit in which promotion execution, stock, demand, and outcome are actually realized.

### Store group

A defined grouping of stores used for rollout, management, benchmarking, learning, or simulation.

### Product and product group

The SKU, item family, category, or defined merchandise set affected by a promotion.

### Promotion template

A reusable commercial specification for a promotion pattern, such as discount structure, offer mechanism, participation rules, and timing logic.

### Network promotion

A governed promotion framework intended to operate across many stores, store groups, or other network units within an authorized banner or client structure.

### Promotion instance

A dated activation of a promotion template and network promotion for a specific decision window, product set, and target scope.

### Store promotion instance

The store-level realization of a promotion instance, carrying the local state needed for a real decision.

### Promotion recommendation object

The formal decision object produced by the platform for a promotion scope, with action, explanation, constraints, uncertainty, and expected consequences.

### Promotion post-mortem object

The formal learning object that records what happened after a promotion decision, why it differed from expectation, and what future policy should learn.

## Core Entity Relationships

- A tenant governs one or more client groups and their access rights.
- A client group has reporting rights to one or more stores or store groups.
- A banner / brand contains one or more stores and influences valid promotion logic.
- A store may belong to one banner / brand and may participate in multiple store groups.
- A promotion template defines a reusable promotion pattern.
- A network promotion applies that pattern to an authorized network structure.
- A promotion instance activates a network promotion for a defined time window and merchandise scope.
- A store promotion instance binds that promotion instance to one specific store and its local state.
- A promotion recommendation object targets a defined decision scope and references the relevant store promotion instances.
- A promotion post-mortem object links realized outcomes back to the original decision objects and store promotion instances.

These relationships are essential because the domain must represent both shared structure and local variation without collapsing either.

## Promotion Lifecycle Objects

### Promotion template

The promotion template is the reusable commercial pattern. It defines the basic offer logic, participation assumptions, expected mechanism, and standard structural rules. It exists before any specific timing or store activation is chosen.

### Network promotion

The network promotion is the governed commercial program that applies the template to a broader store network, banner, or authorized operating population. It represents the fact that one promotion framework may exist across many stores.

### Promotion instance

The promotion instance is the activation of the network promotion for a defined period, product set, and intended scope. It is the object the business intends to run in a specific commercial window.

### Store promotion instance

The store promotion instance is the local realization of the promotion instance. This is where the domain stops pretending stores are interchangeable. Each store promotion instance carries store-specific stock reality, demand context, execution state, and local decision status.

### Promotion execution record

The promotion execution record captures what actually happened in the store or decision scope, including whether the recommendation was followed, adjusted, delayed, or overridden.

### Promotion post-mortem object

The promotion post-mortem object closes the lifecycle by connecting expected effects, actual execution conditions, realized outcomes, and causal interpretation for future learning.

## Store-Level Local State Objects

Store-level local state is not a minor adjustment field. It is part of the core decision terrain.

### Store-specific stock reality

This object represents the actual local stock condition relevant to the promotion decision, including on-hand position, in-transit expectations, replenishment reliability, stock cover risk, and availability constraints.

### Store-specific demand context

This object represents the local commercial demand environment, including recent response history, customer mix, seasonal or event context, local competitive pressure, and evidence of promotion sensitivity or saturation.

### Store-specific execution state

This object represents whether the store can actually execute the promotion reliably, including staffing, readiness, local compliance risk, signage or display capability, and any known operating friction.

### Local override state

This object records whether local management has supplied a store-specific exception, challenge, or override that must be considered in the decision process.

### Local historical response profile

This object captures how the store has behaved in comparable promotion contexts, including response quality, margin quality, distortion patterns, and reliability of prior execution.

The domain must treat these local objects as materially decision-relevant. A network promotion is never enough by itself.

## Client and Tenant Boundary Objects

### Tenant object

The tenant object defines the top-level security boundary, access-control regime, reporting entitlement model, and permitted data-sharing rules.

### Client group object

The client group object defines the paying or governed client scope for which outputs are assembled. It may represent one store, a collection of stores, or another contractual operating unit.

### Reporting entitlement object

This object defines what the tenant or client group is permitted to see, including store detail, group aggregates, benchmark-safe comparison outputs, and explanation depth.

### Learning permission object

This object defines what broader network evidence the platform may learn from for model, policy, and simulation improvement. It is the formal boundary that governs aggregated network learning.

### Benchmark-safe comparison object

This object defines a permitted comparison output that uses authorized aggregation, cohorting, or de-identification rules so that comparative insight can be delivered without exposing unauthorized cross-store detail.

These boundary objects are not peripheral. They determine what the platform may learn, what it may show, and what it may decide for a given client context.

## Decision Objects

### Promotion decision case

The promotion decision case is the full context for one decision episode, including decision scope, relevant promotion instances, local state, constraints, uncertainty, alternatives, and timing.

### Promotion recommendation object

The promotion recommendation object is the formal output of the platform. It should contain at least the recommended action, the decision scope, the relevant promotion and store objects, expected payoff quality, key constraints, confidence level, failure-state concerns, and explanation-ready reasoning.

### Allocation decision object

The allocation decision object defines where a promotion should or should not run, at what level of support, and under what conditions. In this domain, allocation may refer to store inclusion, support prioritization, stock-sensitive participation, or rollout priority.

### Local store override object

The local store override object records an authorized departure from the system recommendation because local commercial or operating reality justifies an exception.

### Escalation or abstention object

This object records that the system is not issuing a full immediate recommendation because uncertainty, contradiction, missingness, or governance constraints require waiting, simulation, more information, or human review.

The domain should treat these as first-class decision outcomes, not exceptional failures.

## Constraint Objects

Constraint objects define the real decision envelope. They are not late filters.

### Commercial constraint object

Defines acceptable margin quality, proposition integrity, category role, and brand-consistent promotion behavior.

### Stock and replenishment constraint object

Defines what the local store or network can support without creating stock distortion or execution failure.

### Financial constraint object

Defines budget, funding, acceptable downside, and broader economic limits on promotion activity.

### Execution constraint object

Defines whether the store or network can deliver the promotion with sufficient reliability for the modeled outcome to be meaningful.

### Banner / brand rule constraint object

Defines banner-specific rules, proposition boundaries, and permitted promotion mechanics.

### Tenant and governance constraint object

Defines access-control limits, reporting restrictions, data-sharing rules, approval boundaries, and any constitutional requirement that governs the recommendation.

### Constraint profile object

Bundles the relevant constraint objects for a decision case so that downstream optimization and explanation operate against a coherent constraint set.

## Outcome Objects

### Store promotion outcome object

Captures the realized outcome for a specific store promotion instance, including units, revenue, margin quality, stock consequences, execution deviations, and any evidence of distortion such as pull-forward or cannibalization.

### Store-group or client-group aggregate outcome object

Captures aggregated outcome across a governed reporting scope without breaking tenant boundary rules.

### Network learning outcome object

Captures the broader outcome signal that may feed aggregated network learning when governance permits. This object is for learning, not necessarily for reporting.

### Promotion post-mortem object

Captures the relationship between recommended action, executed action, realized outcome, failure-state findings, causal interpretation, and policy update. This object should explicitly record whether the main error came from weak state reading, distortion, constraint handling, simulation error, or execution deviation.

### Benchmark-safe comparison output

Represents an authorized comparative view that allows useful benchmarking while preserving aggregation and access-control rules.

## Failure Modes Specific to Promotional Allocation

Promotional allocation introduces several failure modes that the domain model must make explicit.

### Network-to-local false transfer

A promotion appears attractive at network level, but local store conditions make it inappropriate or low quality in specific stores.

### Promotion-driven false continuation

Units continue to move during promotional activity, but margin quality, genuine incrementality, or underlying demand health are weakening.

### Stock-distorted interpretation

Observed promotion outcomes are misread because stock availability, replenishment gaps, or shelf-level reality distort the apparent demand signal.

### Execution heterogeneity blindness

Stores are treated as though the promotion executed uniformly when actual store-level execution quality varied materially.

### Over-aggregation of reporting

Network or banner aggregates conceal weak local outcomes that matter to the client store or client group.

### Unauthorized cross-store exposure

The system leaks comparative detail or explanation artifacts that exceed the reporting rights of the tenant or client group.

### Local optimization failure

A store-level recommendation improves local units or revenue but damages broader margin quality, network economics, or customer proposition integrity.

### Banner mixing error

Evidence from one banner or brand is used as though it were automatically transferable to another without respecting proposition and context differences.

### Post-promotion learning loss

The business runs the promotion, but the domain fails to capture a governed post-mortem object, weakening future policy learning.

## State Signals Required for This Domain

The domain requires richer state signals than standard promotional reporting usually provides.

- Network promotion structure and applicable promotion mechanics.
- Store-specific stock reality, replenishment reliability, and availability risk.
- Store-specific demand context, including prior response quality and local demand sensitivity.
- Store-specific execution state and readiness.
- Banner / brand context and proposition rules.
- Product, product-group, and category role context.
- Promotion history, including prior distortion patterns and quality of incrementality.
- Missingness, lag, contradiction, and observability signals.
- Local override history and management exception context.
- Store-group and network comparison context where governance permits.
- Tenant, client-group, reporting scope, learning scope, and decision scope metadata.

Without these signals, the system cannot support the domain responsibly.

## Simulation Requirements for This Domain

The digital twin and simulation design for this domain must be able to evaluate more than expected uplift.

It must simulate how a network promotion behaves when translated into store promotion instances under heterogeneous local conditions. That includes stock effects, execution variability, local demand context, timing effects, cannibalization, substitution, pull-forward, margin quality, and banner-specific rules.

Simulation in this domain must also support questions such as these.

- Which stores should participate at all?
- Which stores should receive the promotion later, differently, or not at all?
- What happens if the network promotion runs broadly but local stock is weak in a subset of stores?
- How does a local store override change the likely outcome?
- What is the difference between network-level attractiveness and store-level payoff quality?

The simulation layer must therefore operate on the one-to-many structure directly. It must be able to take one network promotion and evaluate many store promotion instances with different local state.

## Policy-Learning Requirements for This Domain

Policy learning in this domain must be permission-aware, multi-level, and commercially grounded.

It must support aggregated network learning where governance permits. Aggregated network learning means the platform may learn from a broader pool of authorized stores, store groups, banners, or prior promotion instances in order to improve policy quality, while still preserving strict client-facing reporting boundaries.

The policy-learning design must therefore do the following.

- Learn from repeated promotion instances across allowed store networks.
- Preserve banner-specific and brand-specific differences instead of forcing false equivalence.
- Preserve store-level heterogeneity so that network learning does not erase local conditions.
- Learn from local store overrides and whether they improved or degraded outcomes.
- Update policy quality from promotion post-mortem objects, not just from raw performance metrics.
- Respect learning permission boundaries defined by tenant governance.

This domain should never allow broad pooled learning to become an excuse for unauthorized cross-store exposure or shallow recommendation logic.

## Reporting and Explanation Requirements

Reporting and explanation outputs in this domain must remain tenant-safe, client-scoped, and commercially interpretable.

Every client-facing recommendation package should make clear the following.

- What the decision scope is.
- Which promotion instance or store promotion instance is being discussed.
- What local state materially influenced the recommendation.
- What broader network evidence informed the recommendation, if any.
- Whether that broader evidence was used for learning only or is also reportable at aggregate level.
- Which constraints limited or changed the action.
- Why the recommended action is preferred over the main alternatives.
- What uncertainty, contradiction, or local execution risk remains.

Any comparative output must use benchmark-safe comparison logic. That means comparisons must respect aggregation rules, de-identification where required, access-control policy, and tenant boundaries. Useful comparison is allowed. Unauthorized exposure is not.

## Governance and Access-Control Requirements

Governance and access control are first-class domain concerns.

The domain model must support the following.

- Tenant isolation for data, explanation artifacts, recommendation packages, and reporting outputs.
- Explicit reporting entitlements by tenant, client group, store, store group, banner, or authorized role.
- Explicit learning permissions that define where aggregated network learning is allowed.
- Separation between what the system may learn from and what it may show.
- Auditability of overrides, access decisions, and comparative output rules.
- Restriction of cross-store reporting even when cross-store learning is allowed.
- Restriction of cross-brand transfer where banner or brand logic makes such transfer invalid or unauthorized.

The system may learn broadly only where governance permits. It may report broadly only where entitlement permits. These are different tests and must remain different.

## Domain Invariants

- Multi-store, multi-brand, and tenant-aware design are first-class conditions of the domain.
- A network promotion is not the same object as a store promotion instance.
- A store promotion instance is the primary local realization object for decision and outcome evaluation.
- Learning scope, reporting scope, and decision scope are distinct and must not be collapsed.
- The system may learn from broader network evidence where permitted, but client-facing outputs must remain scoped to the authorized store, store group, or client group.
- Local store conditions can materially override network defaults.
- Store-specific stock reality, demand context, and execution state are core decision inputs, not optional annotations.
- Promotion recommendation objects must remain reconstructible after the fact.
- Promotion post-mortem objects are required for institutional learning.
- Benchmark-safe comparison is the only valid form of comparative client-facing cross-store output.

## What This Domain Model Enables

If implemented correctly, this domain model enables a disciplined first wedge for the wider platform.

It enables tenant-safe promotional allocation across many stores.

It enables one-to-many promotion structures such as Priceline without erasing local store reality.

It enables aggregated network learning where governance permits while preserving client-scoped reporting.

It enables clear domain objects for Python engineering, modular architecture, simulation design, and decision workflow implementation.

It enables richer failure-state detection by making distortion, stock reality, execution state, and local context first-class objects.

It enables promotion post-mortem learning that improves future policy rather than merely storing historical results.

It also creates a reusable pattern for other retail domains in which network structure, local conditions, and tenant-safe output must coexist.

## Closing Statement

Promotional allocation is the first wedge because it forces the platform to prove its core claim under real commercial conditions: learn from the broader retail system where allowed, detect hidden weakness early, decide with local discipline, respect constraints, and explain clearly.

This domain model protects that claim at the level where architecture becomes implementation.

If this model remains intact, the platform can build promotion decision intelligence without collapsing into shallow campaign analytics, unsafe cross-store reporting, or one-off chain logic.

If it is weakened, the first wedge will drift before the broader platform is even built.