# Platform Governance Roles and Approval Authority Matrix for the Fourth Form Retail Decision Intelligence Platform

## Purpose of This Document

This document defines the governance roles, approval authorities, and review responsibilities for consequential decisions in the Fourth Form platform.

It exists because the platform is controlled not only by implementation, but by strategy, controlled vocabulary, constitution, architecture, domain structure, workflow rules, simulation rules, reporting logic, tenant boundaries, policy-learning rules, and the documents that stabilize those elements over time.

Without explicit approval authority, the platform will drift into unclear ownership, informal approval, tenant-sensitive change by convenience, architecture change with no accountable approver, glossary and constitution change without governance discipline, workflow and simulation revisions approved too casually, and domain expansion with no clear decision rights.

This document is therefore a control document for governance authority and approval structure.

It is the canonical governance authority document for the platform. Future approvals for architecture, glossary, constitution, workflow, simulation, reporting, tenant-boundary, policy-learning, and domain-expansion changes must align with it unless a formal decision record explicitly revises it.

## Role of This Document in the Platform

This document governs who has authority to approve consequential change, who must review it before approval, and which classes of change require stronger governance than ordinary domain-local evolution.

The strategy and vision documents define what the platform is for. The constitution defines how it must behave. The glossary stabilizes meaning. The architecture and domain documents define how the platform is structured and populated. The change-governance document defines when formal decision records are required. The decision-record writing standard defines what an approval-ready record must look like. This document defines which durable governance roles may approve those changes and how accountability is assigned.

In practical terms, this document governs five things.

- The durable governance roles used for consequential approval.
- The responsibilities attached to each role.
- Which roles must review and which roles may finally approve each class of change.
- Which changes are high sensitivity and therefore require stronger approval discipline.
- How approval lineage remains explicit and traceable over time.

This document therefore governs approval authority as part of platform control.

## Core Thesis

Consequential change in the Fourth Form platform must be approved by named human authorities acting in defined governance roles matched to the change class, because the platform cannot remain coherent if shared architecture, tenant boundaries, controlled vocabulary, constitutional behavior, workflow rules, simulation rules, reporting logic, or domain-expansion choices are allowed to change without explicit accountable approval.

That is the core thesis.

If no accountable authority can be named for a change, the change is not governance-ready.

## What This Authority Model Is and Is Not

This authority model is a role-based control system for approving consequential platform change.

It is not any of the following.

- It is not an informal understanding of who usually signs off.
- It is not a generic committee model in which many people comment and no one is accountable.
- It is not an org chart substitute or a title list detached from decision rights.
- It is not permission for implementation convenience to stand in for approval.
- It is not a consensus ritual in which review is treated as equivalent to authority.
- It is not a model in which AI-generated proposals become governing truth because they are fluent.

A real authority model means the platform can answer three questions for every consequential change.

- Which role had authority to approve it.
- Which other roles were required to review it.
- Which human actually acted in those roles.

## Governance Role Model

The platform uses durable governance roles rather than personal names.

These roles may be held by the same human in an early platform phase, but they must remain conceptually separate. If one human temporarily holds multiple roles, the approval record must state which role or roles that person exercised. A change is not implicitly approved merely because one person happened to see it while wearing multiple hats.

The major governance roles are as follows.

### Platform Owner

The Platform Owner holds final accountability for platform identity, long-term coherence, and the approval of changes that alter strategic direction, shared governance discipline, or cross-domain structure.

### Architecture Authority

The Architecture Authority holds approval responsibility for shared architectural layers, invariants, cross-domain interfaces, and the distinction between shared platform change and domain-local change.

### Domain Authority

The Domain Authority holds approval responsibility for one specific business-function domain module, including domain boundaries, domain objects, workflow behavior, simulation usage inside that domain, reporting behavior inside that domain, and domain-local operating logic.

For Domain 01, this is the Promotional Allocation Domain Authority.

### Governance and Boundary Authority

The Governance and Boundary Authority holds approval responsibility for tenant isolation, learning scope, reporting scope, decision scope, benchmark-safe comparison rules, access-boundary discipline, and other governance-sensitive boundary conditions.

### Commercial Authority

The Commercial Authority holds approval responsibility for commercial objective logic, success measures, operating usefulness, business acceptability of recommendation behavior, and major changes to what the platform treats as valuable or risky.

### Implementation Authority

The Implementation Authority holds review responsibility for implementation feasibility, engineering consequence, migration risk, validation approach, and whether the approved change can be carried into actual system behavior without hidden contradiction.

This role is critical, but it does not replace substantive approval authority for strategy, constitution, glossary meaning, tenant boundaries, or shared governance rules.

## Role Responsibilities

### Platform Owner responsibilities

The Platform Owner is responsible for the following.

- Preserving platform identity and long-term coherence.
- Approving strategy and vision changes.
- Co-approving high-sensitivity changes that alter shared governance, shared structure, or future platform breadth.
- Resolving escalated approval conflicts that cannot be settled at lower authority levels.
- Making sure consequential change remains traceable and intentionally governed.

### Architecture Authority responsibilities

The Architecture Authority is responsible for the following.

- Preserving shared architectural layers, invariants, and layer responsibilities.
- Determining whether a proposed change is truly domain-local or actually shared-platform in consequence.
- Reviewing glossary, workflow, simulation, reporting, and policy changes for architectural impact.
- Protecting cross-domain extensibility and preventing domain-local exceptions from rewriting the platform silently.
- Co-approving shared architecture and other shared-platform changes.

### Domain Authority responsibilities

The Domain Authority is responsible for the following.

- Preserving the integrity of one domain module.
- Approving domain-local changes that do not alter shared-platform rules.
- Making sure domain workflow, simulation, reporting, post-mortem, and policy behavior remain aligned with platform canon.
- Identifying when a proposed domain change actually affects broader shared rules and therefore requires escalation.
- Protecting the domain from drift into ad hoc feature accumulation.

### Governance and Boundary Authority responsibilities

The Governance and Boundary Authority is responsible for the following.

- Preserving tenant isolation and access-boundary discipline.
- Approving or rejecting changes that alter learning scope, reporting scope, decision scope, benchmark-safe comparison logic, or tenant-safe explanation behavior.
- Reviewing proposed changes for governance sensitivity even when they are described as merely operational or local.
- Protecting the distinction between what the platform may learn from and what it may show.
- Co-approving high-sensitivity reporting, scope, and boundary changes.

### Commercial Authority responsibilities

The Commercial Authority is responsible for the following.

- Preserving commercial usefulness and durable value logic.
- Approving changes to commercial objective hierarchy, success measures, business acceptability, and decision usefulness.
- Reviewing workflow, reporting, simulation, and policy changes for commercial consequence.
- Protecting the platform from technically neat changes that weaken real operating value.
- Co-approving changes whose main consequence is commercial rather than purely structural.

### Implementation Authority responsibilities

The Implementation Authority is responsible for the following.

- Reviewing whether a proposed governed change is implementable, testable, and migration-safe.
- Identifying hidden engineering consequence, sequencing risk, and validation gaps.
- Making sure approved changes can be carried into code, workflow, and data structures coherently.
- Protecting the platform from document approval that cannot actually be executed reliably.
- Recording implementation dependencies and feasibility concerns before approval is treated as execution-ready.

Implementation review is required for many consequential changes, but implementation feasibility does not by itself determine governance legitimacy.

## Approval Authority Matrix

The matrix below defines the default approval pattern for consequential change classes.

The role abbreviations are as follows.

- `PO` = Platform Owner
- `AA` = Architecture Authority
- `DA` = Relevant Domain Authority
- `GBA` = Governance and Boundary Authority
- `CA` = Commercial Authority
- `IA` = Implementation Authority

| Change class | Required review | Final approval | Authority rule |
| --- | --- | --- | --- |
| Strategy and vision changes | `AA`, `CA`; `GBA` if governance boundaries are affected; `IA` if implementation consequences are immediate | `PO` | Platform identity may not be changed by local convenience or implementation preference. |
| Constitution changes | `AA`, `DA`, `GBA`, `CA`, `IA` | `PO` and `CA` and `GBA` | Changes to behavioral discipline under uncertainty and constraint are high sensitivity and require joint strategic, commercial, and governance authority. |
| Glossary meaning changes | `AA`, `DA`; `GBA` if boundary-sensitive; `CA` if commercially material; `IA` if implementation meanings change | `PO` and `AA` | Controlled meaning is a platform asset and may not drift through casual rewording. |
| Shared architecture changes | `DA`, `GBA`, `CA`, `IA` | `PO` and `AA` | Any change to shared layers, invariants, or cross-domain structure is platform-level by definition. |
| Shared platform changes outside one domain | `AA`, `GBA`, `CA`, `IA`, all affected `DA` roles where relevant | `PO` and `AA` | A change that affects more than one domain or the shared decision grammar is not approvable as a local edit. |
| Domain 01 changes that are truly domain-local | `IA`; `AA` if shared surfaces may be touched; `GBA` if scope or tenant implications exist; `CA` if commercial behavior is materially affected | `DA` | Domain-local change may be approved locally only when it does not rewrite shared architecture, constitution, glossary meaning, or governance boundaries. |
| Future domain additions | `AA`, `GBA`, `CA`, `IA`; proposed `DA` if already designated | `PO` and `AA` and `CA` | Adding a domain changes platform breadth and shared operating expectations, so it requires platform-level approval. |
| Simulation rule changes | `CA`, `IA`; `GBA` if scope, tenant, or reporting implications exist; `AA` review is always required | `DA` and `AA` | Simulation rules sit at the boundary between domain logic and shared decision infrastructure. |
| Workflow changes | `CA`, `IA`; `AA` if shared-stage logic changes; `GBA` if output scope, escalation, or entitlement behavior changes | `DA` and `CA` | Workflow governs operating behavior, so domain and commercial authority must both agree. |
| Reporting and benchmark-safe output changes | `CA`, `IA`; `AA` if shared output architecture changes | `DA` and `GBA` | Client-facing output, benchmark-safe comparison, and explanation scope are domain-relevant but governance-sensitive. |
| Tenant, learning, or reporting scope changes | `AA`, `DA`, `CA`, `IA` | `PO` and `GBA` | Scope-boundary changes are high governance risk and may not be approved as minor edits. |
| Policy-learning rule changes | `AA`, `CA`, `IA`; `GBA` review is always required | `DA` and `GBA` | Policy-learning changes affect how the platform evolves over time and therefore require both domain and governance authority. |
| Commercial metric or success-measure changes | `AA`, `DA`, `IA`; `GBA` if reporting or entitlement logic is affected | `PO` and `CA` | Changes to what the platform treats as success alter operating incentives and must be approved accordingly. |

This matrix defines the default rule. If a change spans multiple rows, the stricter approval requirement controls.

## Review vs Approval Distinction

Required review and final approval are not the same thing.

Required review means a role must examine the proposal, test its consequences in that role's area of responsibility, and explicitly surface concern, objection, or acceptance before the proposal is approval-ready.

Final approval means a role with decision authority accepts accountability for making that change governing.

The distinction matters for three reasons.

- A change may be technically feasible yet still fail governance review.
- A change may be commercially attractive yet still fail architectural review.
- A change may receive many comments and still have no accountable approver.

The following rules apply.

- Silence is not approval.
- Familiarity is not approval.
- Merge activity is not approval.
- Review completion is not approval.
- Approval cannot bypass required review for the relevant change class.

A proposal that has not received its required reviews remains incomplete. A proposal that has not received final approval remains non-governing even if implementation work has begun.

## High-Sensitivity Change Classes

Some change classes require stronger governance because they can alter what the platform is allowed to do, show, learn from, or optimize for.

The following are high-sensitivity change classes.

### Tenant-boundary changes

Any change to tenant isolation, access boundaries, or what one client or role may view relative to another.

### Reporting-scope changes

Any change to store-level, store-group, client-group, or tenant-scoped reporting entitlement.

### Learning-scope changes

Any change to what data, outcomes, or history may be used for learning or policy improvement.

### Benchmark-safe comparison changes

Any change to benchmark-safe comparison rules, aggregation logic, de-identification thresholds, cross-store comparison permissibility, or cross-banner comparison behavior.

### Constitution changes

Any change to the governing behavioral discipline of the platform under uncertainty, constraint, escalation, abstention, or explanation.

### Shared architecture changes

Any change to shared layers, architectural invariants, cross-domain interfaces, or the shared decision grammar.

These classes require stronger approval discipline because they can cause platform-wide drift while still looking local in wording.

At minimum, high-sensitivity changes must satisfy the following.

- A formal decision record is required.
- Cross-document review is required.
- Joint approval is required.
- Implementation convenience may not be used as the deciding argument.
- The prior governed rule remains in force until the new change is formally approved.

## Cross-Domain Approval Rules

The platform is intended to expand beyond Domain 01 into many future domains. Cross-domain approval must therefore preserve shared structure without blocking legitimate growth.

The following rules apply.

- A new business function must be added as a domain module, not as a miscellaneous feature inside an existing domain.
- A future domain addition requires platform-level approval, not only local enthusiasm from one domain or implementation team.
- A change that appears local to one domain but alters shared vocabulary, shared architecture, shared governance, or shared output discipline must be reclassified as platform-level.
- One domain authority may not approve a rule that another domain will be expected to obey unless the change has passed platform-level approval.
- A domain-specific exception that rewrites a shared rule is not a local exception. It is a shared-rule change.

For future domain additions, the minimum approval expectation is formal decision record plus approval by `PO`, `AA`, and `CA`, with governance and implementation review. If the proposed domain has already identified a named domain authority, that role should review the proposal before approval.

Cross-domain growth must increase breadth without weakening structural coherence.

## Conflict and Escalation Rules

When required approvers disagree, the change is not approved by default.

The following escalation rules apply.

1. The proposal must first be classified correctly as domain-local, shared-platform, or high-sensitivity.
2. If there is disagreement about whether the change is local or shared, `AA` and `GBA` must review the classification.
3. If the disagreement concerns tenant, learning, reporting, or benchmark-safe boundaries, the narrower safer boundary remains in force until resolved.
4. If required reviewers identify unresolved material risk, the proposal should return to revision rather than moving forward with partial assent.
5. If final approvers disagree, the proposal remains unapproved and must be escalated to `PO` for explicit resolution or rejection.
6. If `PO` is already one of the disagreeing approvers, the disagreement must still be recorded explicitly rather than hidden inside a final edit.

The purpose of escalation is not to force speed. It is to prevent silent authority collapse when a change crosses real governance boundaries.

## AI-Assisted Proposal Handling

AI may assist with drafting, summarization, option framing, cross-document impact spotting, or proposal structure. AI may not approve consequential change.

The following rules apply.

- AI-generated proposals enter the governance process as proposed content, not approved content.
- AI may help identify likely approvers and affected documents, but a human authority must confirm that mapping.
- AI may not be recorded as a decision owner, reviewer, or approver.
- AI-generated fluency must not be mistaken for governance rigor.
- High-sensitivity proposals drafted with AI must still receive the same review and approval discipline as any other proposal.
- AI must not be allowed to silently reconcile authority conflict by inventing compromise language without human approval.

AI may accelerate disciplined governance work. It may not bypass human authority.

## Traceability Requirements

Approval authority is only real if it remains reconstructible later.

At minimum, every consequential approved change must record the following.

- Decision record ID.
- Change class.
- The canonical documents, domains, layers, or scopes affected.
- Which roles were required to review the proposal.
- Which roles gave final approval.
- Which human acted in each role.
- The date of each review and approval action.
- Any dissent, objection, or escalation that materially shaped the decision.
- Any concentrated-role condition in which one human acted in more than one role.
- Any superseded approval lineage later replaced by a new decision.

If one human acts in multiple roles, each role action should still be logged separately so that later reviewers can see which authority basis was used.

The platform must be able to explain not only what was approved, but who approved it, under which authority model, and with what review context.

## Failure Modes in Governance Authority

Weak or ambiguous approval authority creates direct platform risk.

### Architecture changes by convenience

Shared structure is altered because it seems easier to implement something one way, even though no architecture authority explicitly approved the shift.

### Tenant-boundary erosion

Reporting scope, learning scope, or explanation detail broadens gradually because no governance authority treats the boundary as a high-risk control surface.

### Domain drift

Local feature growth quietly rewrites shared platform logic because domain-local approval was used where shared-platform approval was actually required.

### Conflicting approvals

Different roles believe they approved different interpretations of the same proposal because review, approval, and authority class were never made explicit.

### No clear owner for high-risk changes

Everyone assumes someone else is accountable for scope, constitution, glossary, architecture, or benchmark-safe logic, so the change proceeds without real authority.

### Review inflation with no decision owner

Many people comment on a proposal, but no one is actually obligated to decide whether it becomes governing.

### Implementation-led governance bypass

Engineering feasibility becomes the de facto approver for changes that should have been judged primarily on constitutional, boundary, or platform-coherence grounds.

### AI-fluent but authority-thin proposals

AI-generated proposals appear polished enough that missing approvers, weak review, or hidden governance consequence go unnoticed.

These failure modes are not administrative defects alone. They are ways the platform can lose coherence while still appearing busy and productive.

## Non-Negotiables

1. Governance authority must be explicit, not implied.
2. Review and approval are not the same thing.
3. Every consequential change must have a named human approver operating in a defined role.
4. High-sensitivity changes require stronger approval discipline than ordinary domain-local changes.
5. Tenant-boundary changes are governance risk, not minor edits.
6. Shared-platform changes are different from domain-local changes and must be approved accordingly.
7. AI may propose but not approve.
8. Implementation Authority does not replace substantive governance authority.
9. If one human holds multiple roles, those roles must still be recorded separately in approval lineage.
10. If no accountable approval path can be named, the change must not become governing canon.

## Closing Statement

This document protects the platform from evolving through informal authority, hidden ownership, and convenience-driven approval.

Fourth Form is building a decision intelligence platform whose coherence depends on explicit control over strategy, meaning, architecture, workflow, simulation, reporting, tenant boundaries, policy learning, and future domain growth. That coherence cannot survive if the platform does not know who had the right to approve which changes and under what discipline.

If this authority model remains intact, the platform can grow across many domains without losing accountability.

If it weakens, the platform will continue to change while becoming less able to justify why those changes were legitimate.