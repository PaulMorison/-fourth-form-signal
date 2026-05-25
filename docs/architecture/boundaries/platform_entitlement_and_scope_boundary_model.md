# Platform Entitlement and Scope Boundary Model for the Fourth Form Retail Decision Intelligence Platform

## Purpose of This Document

This document defines the shared platform model for entitlement, scope boundaries, tenant isolation, learning scope, reporting scope, decision scope, and benchmark-safe boundary logic.

It exists because the platform is intended to operate across multiple stores, client groups, banners, brands, and future domains while remaining tenant-safe and commercially useful. If these boundary concepts are left to local interpretation, each domain will slowly develop its own slightly different meaning of tenant, client scope, learning rights, reporting rights, role-sensitive access, and benchmark-safe comparison. That drift would make the platform harder to govern, harder to explain, and less safe to expand.

This document is therefore a control document for boundary logic, entitlement design, and shared scope structure.

It defines the shared boundary objects of the platform, the hierarchy among them, the difference between learning, reporting, and decision scope, the platform-level model for role-sensitive access and benchmark-safe comparison, the way current and future domains must inherit those rules, and the governance sensitivity of any change to those definitions.

It is the canonical shared boundary and entitlement control document for the platform. Future domains, reporting rules, learning rules, decision-scope logic, benchmark-safe comparison behavior, and tenant-boundary changes must align with it unless a formal decision record explicitly revises it.

## Role of This Document in the Platform

This document governs the shared platform boundary model that all current and future domains must use when defining what the system may learn from, what it may decide for, what it may show, and who is entitled to receive which forms of output.

The architecture document establishes that the platform must distinguish learning scope, reporting scope, and decision scope. The Domain 01 domain model applies that distinction to Promotional Allocation. The reporting and benchmark-safe output contract governs how Domain 01 packages client-facing outputs. The change-governance and approval-authority documents establish that boundary changes are high-sensitivity governance events. This document sits above those domain-local applications and defines the shared platform-level model that they inherit.

In practical terms, this document governs five things.

- The shared objects used to define boundary structure across the platform.
- The hierarchy and interpretation of those objects.
- The difference among learning scope, reporting scope, decision scope, role-sensitive access scope, and benchmark-safe comparison scope.
- The inheritance rules that domains must obey when implementing local boundary logic.
- The governance rules and traceability expectations attached to boundary-sensitive change.

This document therefore governs entitlement and boundary coherence as part of platform control.

## Core Thesis

In the Fourth Form platform, tenant boundaries, entitlement logic, and scope definitions must be modeled once at the shared platform level and then inherited by every domain, because the platform cannot remain coherent or tenant-safe if learning rights, reporting rights, decision targeting, role-sensitive access, or benchmark-safe comparison rules are allowed to vary by local convenience.

That is the core thesis.

The platform may support broad learning, local decisioning, and governed comparative output at the same time, but only if those boundary conditions remain explicit, stable, and shared.

## What This Model Is and Is Not

This model is a shared control structure for defining who the platform is operating for, what populations it may learn from, what populations it may report on, what unit a decision is being made for, and what comparative views are allowed.

It is not any of the following.

- It is not a user-interface permissions note added after domain logic is complete.
- It is not a domain-local access-control convention that each team may rewrite independently.
- It is not a generic security model detached from commercial structure.
- It is not a rule that treats learning rights as if they automatically create reporting rights.
- It is not a benchmarking feature description detached from governance boundaries.
- It is not a loose set of similar words whose exact meanings may shift from one document to another.

A real boundary model means the platform can answer the following questions without ambiguity.

- Which tenant governs a given entity or output.
- Which client group or operating population a given output is for.
- Which stores, groups, banners, brands, or histories are in learning scope.
- Which stores, groups, banners, brands, or aggregates are in reporting scope.
- Which exact unit is the decision being produced for.
- Which roles may see which parts of that output.
- Which kinds of comparison are safe enough to show.

## Why a Shared Boundary Model Is Necessary

This boundary model cannot be left to each domain independently because the same platform may eventually support many decision areas while still operating under one shared governance discipline.

If each domain invents its own meaning of client group, reporting scope, learning entitlement, or benchmark-safe comparison, several failures follow.

- A tenant boundary that is treated strictly in one domain may be weakened in another.
- A reporting concept in one domain may be used as a learning concept in another.
- Cross-domain coordination becomes unsafe because the same boundary terms no longer mean the same thing.
- Future engineers and AI coding tools begin implementing inconsistent access and comparison behavior across the platform.
- Governance approvals become harder because the platform loses one shared reference for what a boundary change actually is.

The platform therefore needs a single shared model so that every domain inherits the same boundary grammar even when their local business objects differ.

## Core Boundary Objects

The platform uses the following core boundary objects.

### Entitlement object

The entitlement object is the governed statement of what a recipient population may view, at what level of detail, in which output forms, under which role conditions, and with which comparison privileges.

An entitlement object is not inferred from the mere existence of data. It is an explicit governance object.

### Tenant

The tenant is the top-level governance and security boundary that controls data-sharing rules, access rights, reporting entitlements, comparison permissions, and permitted learning behavior.

The tenant is the strongest default boundary in the platform.

### Client group

The client group is the commercial or contractual population for which outputs, reporting views, and recommendation packages are assembled.

A client group may represent one store, many stores, a managed subnetwork, or a brand-specific operating population. It is not assumed to be identical to the tenant.

### Store

The store is the local operating unit in which commercial conditions, stock reality, execution reality, and realized outcomes are observed.

Store is a foundational boundary object because local conditions often matter materially even when the platform learns from broader network history.

### Store group

The store group is a governed grouping of stores used for management, rollout, comparison, learning, simulation, reporting, or other defined platform purposes.

Store-group meaning must be explicit. A store group is not merely any temporary collection of stores.

### Banner or brand

The banner or brand is the retail trading identity whose proposition, promotion conventions, customer response norms, and valid comparison logic shape how learning transfer and reporting should be interpreted.

Banner and brand are boundary-relevant because cross-brand comparison is not automatically meaningful or safe.

### Decision scope

Decision scope is the exact operating unit for which the platform is producing a recommendation, escalation, abstention, simulation-first package, or other decision artifact.

Decision scope is an action-targeting object, not a visibility object.

### Reporting scope

Reporting scope is the exact set of stores, groups, client populations, banners, brands, or aggregates that a recipient is entitled to view in client-facing output, reporting views, explanation surfaces, and benchmark-safe comparative context.

Reporting scope is a visibility object, not a learning object.

### Learning scope

Learning scope is the set of stores, groups, banners, brands, outcomes, and historical decision records that the platform is permitted to use for model improvement, policy learning, calibration, simulation support, or other governed learning behavior.

Learning scope is an internal-use object, not a client-facing visibility object.

### Role-sensitive access scope

Role-sensitive access scope is the subset of otherwise valid reporting scope and output detail that a particular role may view inside an already authorized tenant or client-group context.

Role-sensitive access can narrow visibility and explanation depth. It does not create a new tenant right.

### Benchmark-safe comparison scope

Benchmark-safe comparison scope is the governed comparative population and disclosure form that a recipient is entitled to receive, including allowed cohort definition, aggregation level, de-identification expectations, small-cell protection, and valid comparison boundaries.

Benchmark-safe comparison scope is not the same thing as unrestricted reporting scope.

## Boundary Hierarchy

The platform should interpret these boundary objects as an ordered structure rather than as unrelated labels.

First, structural boundary objects define the underlying populations the platform operates across.

- Tenant.
- Client group.
- Banner or brand.
- Store.
- Store group.

Second, scope objects define what the platform is allowed to do with those populations.

- Learning scope defines what may inform internal learning.
- Decision scope defines where an action is being targeted.
- Reporting scope defines what may be shown.
- Role-sensitive access scope defines what a specific role may see inside that reporting scope.
- Benchmark-safe comparison scope defines what governed comparative context may be shown.

These objects relate in the following way.

1. The tenant establishes the highest governing boundary.
2. Within a tenant, one or more client groups define commercial output populations.
3. Within or alongside those client populations, stores and store groups define local and grouped operating units.
4. Banner or brand defines proposition and comparison meaning that may cut across store groupings but remains governance-relevant.
5. Learning, decision, and reporting scope are then defined over those structural objects.
6. Role-sensitive access scope narrows what a given role may see within an already valid reporting scope.
7. Benchmark-safe comparison scope defines the only valid form of comparative extension of reporting scope.

This hierarchy matters because the platform may be learning from a broader population, deciding for a narrower one, and reporting to a narrower still one. Those conditions are legitimate only when modeled explicitly.

## Learning Scope Model

Learning scope is the governed set of historical and current platform artifacts that may be used to improve model behavior, policy behavior, simulation quality, causal interpretation, confidence calibration, or other internal learning functions.

Learning scope may include broader authorized store networks, store groups, client populations, banners, or historical decision records where governance permits. That broader scope is often necessary because local decision quality can improve when the platform learns from more than one isolated store.

However, learning scope is not a grant of visibility. The fact that the platform may learn from broader network history does not mean a recipient may see that history in raw or identifiable form.

The learning scope model must therefore obey the following rules.

- Learning scope must be explicitly defined, not inferred from data availability.
- Learning scope may be broader than decision scope.
- Learning scope may be broader than reporting scope.
- Learning scope may cross store or store-group boundaries only where governance permits.
- Learning scope may cross banner or brand boundaries only when the transfer logic is explicitly governed and commercially defensible.
- Learning scope may support benchmarking or explanation only through authorized aggregate or benchmark-safe forms.
- A domain may narrow learning scope locally, but it may not broaden beyond the shared platform rule without governed approval.

Learning scope is therefore a governed right to internal use, not a right to client-facing disclosure.

## Reporting Scope Model

Reporting scope is the governed visibility boundary for client-facing outputs, explanations, post-mortem packages, reporting views, and any benchmark-safe comparative context shown to a recipient.

Reporting scope is defined by entitlement, not by the full reach of the underlying platform.

Reporting scope may take several legitimate forms.

- Store-level reporting scope.
- Store-group reporting scope.
- Client-group reporting scope.
- Tenant-internal aggregate reporting scope.
- Benchmark-safe comparative reporting scope where explicitly permitted.

The reporting scope model must obey the following rules.

- Reporting scope must be explicit on every material output package.
- Reporting scope may be narrower than learning scope.
- Reporting scope may be broader than decision scope only where the recipient is entitled to group-level or aggregate context.
- Reporting scope must remain tenant-safe unless a separately governed benchmark-safe comparative rule allows broader non-identifiable aggregate form.
- Reporting scope must govern explanation content, not only metric visibility.
- Reporting scope must be interpreted together with role-sensitive access scope where relevant.

Reporting scope is therefore the platform's formal answer to the question of what a given recipient may see.

## Decision Scope Model

Decision scope is the exact operating unit for which the platform is forming a decision artifact.

Depending on the domain, decision scope may be one store, one store promotion instance, one store group rollout, one client-group intervention, one banner-level governed action, or another formally defined operating unit.

Decision scope must remain separate from both learning scope and reporting scope because they answer different questions.

- Learning scope asks what the platform may learn from.
- Decision scope asks what the platform is deciding for.
- Reporting scope asks what the recipient may see.

The decision scope model must obey the following rules.

- Every material recommendation or governed non-recommendation output must state its decision scope explicitly.
- Decision scope may be narrower than the learning population that informed it.
- Decision scope may be narrower than the reporting package that contextualizes it.
- Decision scope must remain reconstructible after the fact.
- A domain may define domain-specific decision objects, but they must map cleanly to this shared scope model.

The platform must therefore never imply that because it learned broadly or reported broadly it was deciding broadly.

## Role-Sensitive Access Model

Role-sensitive access model defines how visibility may vary for different roles operating inside the same tenant or client-group boundary.

This matters because one client or tenant may contain roles with different legitimate needs. A local store operator, a regional operating leader, a central commercial lead, and a governance reviewer may all sit inside one tenant context while still requiring different output detail, comparison depth, and explanation granularity.

Role-sensitive access must obey the following rules.

- Role-sensitive access may narrow reporting scope, output detail, explanation detail, and comparison granularity.
- Role-sensitive access may not broaden visibility beyond the underlying tenant and client-group entitlement.
- Role-sensitive access must be explicit and governable rather than improvised inside individual views.
- Role-sensitive access should apply to explanation artifacts, benchmark-safe context, historical detail, and post-mortem views, not just to top-level metrics.
- If role entitlement is ambiguous, the narrower interpretation controls until clarified.

Role-sensitive access is therefore a structured narrowing layer inside reporting scope, not a separate excuse to bypass shared boundaries.

## Benchmark-Safe Comparison Boundary Model

Benchmark-safe comparison is the only valid shared-platform model for exposing comparative context beyond a recipient's immediate local view.

At the platform level, benchmark-safe comparison means comparative context that remains commercially useful while preserving tenant safety, de-identification, aggregation discipline, and valid comparison semantics.

The benchmark-safe comparison boundary model must obey the following rules.

- Comparative output must be permitted by entitlement.
- Comparative output must use an explicitly governed benchmark-safe comparison scope.
- Comparative output must preserve like-for-like commercial meaning rather than mixing incomparable populations.
- Comparative output must use aggregation, cohorting, or de-identification sufficient to prevent unauthorized identification or reverse inference.
- Comparative output must obey banner, brand, client-group, and tenant boundary constraints.
- Comparative output may support explanation, but it must not reveal unauthorized raw peer detail.
- Domain modules may define narrower comparison rules, but they must inherit this shared logic rather than rewrite it.

Benchmark-safe comparison is therefore not a visualization preference. It is a platform-level boundary rule.

## Cross-Store and Cross-Group Boundary Rules

Cross-store and cross-group use is permitted only in governed forms and for specific purposes.

For learning, broader authorized store and store-group populations may be used where governance permits and where the learning purpose is defensible.

For decisioning, the platform must be explicit about whether it is deciding for one store, one grouped rollout, one client-group population, or another governed unit.

For reporting and explanation, cross-store and cross-group behavior must obey the following rules.

- Direct identifiable cross-store exposure is not allowed outside explicit entitlement.
- Cross-store reporting should default to aggregate or governed grouped form unless named-store visibility is clearly entitled.
- Cross-group reporting must make clear which group population is being referenced.
- Cross-store comparison must not allow reverse inference of another store's local condition.
- A one-to-many network structure such as Priceline may justify broad learning or coordinated rollout logic, but it does not justify one-size-fits-all client-facing reporting.

Cross-store and cross-group use is therefore legitimate only when the purpose, scope, and disclosure form are all governed explicitly.

## Cross-Banner and Cross-Brand Boundary Rules

Banner and brand boundaries affect learning, reporting, transfer, and comparison because proposition logic, customer behavior, and promotion norms may differ materially across them.

The platform must therefore obey the following rules.

- Cross-banner reporting is not valid by default.
- Cross-brand comparison is not valid by default.
- Cross-banner or cross-brand learning transfer requires explicit governance and commercial defensibility.
- Cross-banner or cross-brand explanation must not present borrowed evidence as though it were directly local fact.
- Benchmark-safe comparison across banners or brands, if permitted at all, must remain aggregated, conditional, and clearly marked as limited context rather than direct equivalence.
- Domains may not treat banner or brand boundaries casually simply because data structures appear similar.

Banner and brand boundaries are therefore both commercial meaning boundaries and governance boundaries.

## Domain Inheritance Rules

Every domain module must inherit this shared platform boundary model.

The following rules apply.

- A domain may define local boundary objects only if they map cleanly onto the shared platform objects defined here.
- A domain may narrow a boundary rule for safety or commercial specificity.
- A domain may not broaden a shared tenant, learning, reporting, decision, comparison, or role-sensitive access rule by local convenience.
- A domain may define domain-specific output packages, recommendation objects, or simulation scopes, but the scope meanings inside those objects must use this shared model.
- A domain that appears to require a different shared boundary rule must escalate that need through formal decision governance rather than rewriting the rule locally.
- Cross-domain coordination must use these shared boundary meanings as the common control layer.

Domain 01 Promotional Allocation already uses this model in domain-local form. Future domains must do the same.

## High-Sensitivity Boundary Changes

Changes to this model are high-sensitivity governance events because they can alter what the platform is allowed to learn from, what it is allowed to show, how benchmark-safe comparison works, or where tenant isolation begins and ends.

The following changes are high sensitivity.

- Redefining tenant, client group, store group, or banner or brand boundary meaning.
- Broadening or narrowing learning scope rules.
- Broadening or narrowing reporting scope rules.
- Changing the distinction among learning scope, reporting scope, and decision scope.
- Changing role-sensitive access interpretation.
- Changing benchmark-safe comparison boundary logic.
- Changing cross-store, cross-group, cross-banner, or cross-brand transfer rules.
- Allowing a domain to override a shared platform boundary rule.

At minimum, such changes require the following.

- Formal decision record.
- Cross-document impact review.
- Review under the platform change-governance model.
- Approval under the platform governance authority matrix.
- Coherent revision of every affected canonical document.

Boundary drift is governance risk and must be treated accordingly.

## Traceability and Governance Linkage

This model is directly linked to platform change governance and approval authority.

Any consequential revision to this document or any domain-local exception to it must be governed through the formal decision-record process defined in the platform change-governance document.

Any high-sensitivity boundary change must be reviewed and approved in line with the platform governance roles and approval authority matrix, especially where tenant boundaries, learning scope, reporting scope, benchmark-safe comparison logic, or cross-domain implications are affected.

Traceability should allow the platform to answer the following.

- Which decision record introduced or revised a boundary rule.
- Which roles reviewed and approved that revision.
- Which domains, outputs, simulations, workflows, or policies were affected.
- Which earlier rule was superseded.
- Which output objects and explanation surfaces are expected to carry the relevant scope fields.

The platform must preserve not only the current boundary rule, but the lineage of how that rule became governing.

## Failure Modes in Boundary Design

Weak boundary design creates direct platform risk.

### Learning and reporting confusion

The platform begins exposing information simply because it learned from it, collapsing internal learning rights into client-facing reporting rights.

### Tenant leakage

Outputs, explanations, benchmark views, or post-mortem packages expose information across tenant boundaries that should have remained isolated.

### Unsafe comparison

Comparative outputs are shown without sufficient aggregation, de-identification, cohort discipline, or reverse-inference protection.

### Inconsistent domain scope logic

Different domains use the same boundary terms in different ways, making cross-domain governance and implementation inconsistent.

### Role-insensitive exposure

The platform assumes that everyone inside one tenant or client group should see the same detail, ignoring legitimate role differences.

### Banner contamination

Learning, comparison, or explanation crosses banner or brand boundaries without sufficient commercial or governance justification.

### Unauthorized reuse across domains

One domain quietly reuses another domain's boundary assumptions or comparison rules without a shared-platform decision.

### One-to-many reporting drift

The platform treats a network structure that spans many stores as though it automatically justifies undifferentiated client-facing reporting across those stores.

These are not minor access-control defects. They are ways the platform can lose coherence, trust, and governance legitimacy.

## Non-Negotiables

1. Learning scope, reporting scope, and decision scope are distinct.
2. Tenant-safe boundaries are platform-level controls, not domain-local conveniences.
3. Benchmark-safe comparison must inherit from one shared platform boundary logic.
4. Multi-store and multi-brand operation are first-class platform conditions.
5. Role-sensitive access may narrow visibility but must not broaden entitlement beyond governed scope.
6. Future domains must inherit this model rather than redefining it.
7. A domain may narrow shared boundary rules but may not broaden them without formal governance.
8. Boundary drift is governance risk.
9. Client-facing output must remain scoped to authorized recipients even when the platform has learned from broader authorized history.
10. If a boundary rule changes, the change must be formally traceable.

## Closing Statement

This document protects the platform from boundary drift disguised as local convenience.

Fourth Form is building a decision intelligence platform that must learn broadly where governance permits, decide precisely where action is required, and report only within the boundaries that recipients are entitled to see. That balance is only possible if the platform uses one shared model for tenant isolation, scope definition, role-sensitive access, and benchmark-safe comparison.

If this model remains intact, current and future domains can expand without rewriting the platform's most sensitive control surfaces.

If it weakens, the platform will begin to lose coherence exactly where governance failure is hardest to reverse.