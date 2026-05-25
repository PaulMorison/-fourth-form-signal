# Decision Record Template and Change Governance Rules for the Fourth Form Retail Decision Intelligence Platform

## Purpose of This Document

This document defines how consequential changes to the Fourth Form platform are proposed, recorded, governed, approved, superseded, and traced over time.

It exists because this platform is not controlled only by code. It is controlled by strategy, vocabulary, architecture, decision rules, simulation rules, workflow rules, tenant boundaries, learning rules, and the documentation that keeps those elements coherent.

That means changes to foundational documents are not merely writing edits. They may alter what the platform is, how it behaves, what it is allowed to learn from, what it is allowed to show, what it optimizes for, and what future engineers or AI coding tools will build.

Without explicit change governance, the platform will drift silently. Terms will change meaning without notice. Workflow logic will change without constitutional review. Simulation assumptions will move without being surfaced. Tenant boundaries will erode through convenience. AI-assisted edits will accumulate into architecture change without formal approval. Canonical documents will begin to contradict each other without a governed trail explaining why.

This document is therefore a control document for decision records and change governance.

It is the canonical change-control document for the platform. Future revisions to canonical documents, architecture, domain logic, simulation rules, workflow behavior, policy learning, tenant boundaries, and reporting scope must align with it unless a later formal decision record explicitly revises the governance model.

## Role of This Document in the Platform

This document governs how the platform changes without losing coherence.

The strategy and vision documents define what the platform is for. The glossary stabilizes meaning. The architecture defines the shared stack. Domain documents define how that stack is populated in specific decision areas. The constitution governs how the system must behave. This document governs how changes to any of those elements are proposed, evaluated, approved, recorded, and later superseded.

In practical terms, this document governs five things.

- Which changes require a formal decision record.
- What a valid decision record must contain.
- How canonical documents may be revised once a decision is made.
- How conflicts and contradictions must be resolved.
- How change lineage remains reconstructible over time.

This document therefore governs platform evolution as a first-class control discipline.

## Core Governance Thesis

In the Fourth Form platform, consequential change must occur through explicit, reviewable decision records rather than through silent edits, because meaning drift is architecture drift, workflow drift is decision-quality drift, tenant-boundary drift is governance risk, and undocumented change destroys the platform's ability to explain why it behaves the way it does over time.

That is the core governance thesis.

The platform must be able to explain not only what it does now, but why it changed.

## What This Governance Model Is and Is Not

Formal change governance in this platform is a disciplined method for controlling consequential evolution across documentation, architecture, behavior, and governance boundaries.

It is not any of the following.

- It is not bureaucracy for trivial edits.
- It is not a ceremonial record created after decisions have already been implemented informally.
- It is not a substitute for technical rigor in architecture or implementation.
- It is not permission to create conflicting canonical documents as long as each one looks polished.
- It is not a process that allows AI-generated content to become governing truth without human judgment.
- It is not version history alone. A git diff shows what changed. A decision record explains why it changed and what consequences were expected.

This governance model exists to preserve coherence while allowing deliberate evolution.

## Why Decision Records Are Necessary

The platform needs formal decision records because its documentation is part of its control system.

If foundational documents can be changed informally, the platform loses the ability to know which design choices were intentional, which were accidental, which were temporary, and which were later replaced. Over time that produces a dangerous pattern.

- Architecture changes become embedded without explicit acknowledgment.
- Vocabulary shifts alter design assumptions without changing the names used in code or workflow.
- Simulation or workflow behavior changes without a corresponding explanation of why the prior rule was no longer acceptable.
- Tenant and access-boundary changes occur by convenience rather than governance.
- Later engineers or AI coding tools build against the latest wording without understanding what was deliberately chosen versus casually edited.

Formal decision records are therefore necessary because the platform must preserve explicit institutional memory of why consequential choices were made.

## What Kinds of Changes Require a Formal Decision Record

The following categories of change require a formal decision record.

### Architecture changes

Any change to shared architectural layers, layer responsibilities, invariants, control flow, or architectural principles.

### Domain model changes

Any change to domain entities, domain boundaries, domain relationships, outcome objects, decision objects, or domain invariants.

### Glossary meaning changes

Any change that alters the meaning of a controlled vocabulary term or introduces a new term important enough to shape architecture, behavior, or governance.

### Constitution changes

Any change to governing behavioral rules such as uncertainty handling, constraint discipline, explanation requirements, override governance, or valid action classes.

### Workflow changes

Any change to how decision cases move from intake through recommendation, escalation, abstention, override, execution observation, or post-mortem handoff.

### Simulation changes

Any change to simulation role, trigger discipline, counterfactual structure, validity rules, or how simulation evidence influences recommendation behavior.

### Policy-learning changes

Any change to learning inputs, adaptation logic, update thresholds, confidence recalibration rules, override-learning rules, or policy versioning logic.

### Tenant, scope, or access-boundary changes

Any change to learning scope, reporting scope, decision scope, client boundaries, tenant isolation, benchmark-safe comparison rules, or access-control logic.

### Commercial metric or success-measure changes

Any change to what the platform treats as meaningful payoff, decision quality evidence, commercial success, or primary outcome hierarchy.

### Cross-domain coordination changes

Any change that affects how future domains interact with the shared platform, reuse shared logic, or coordinate across domain boundaries.

If a change affects what the platform means, how it behaves, what it is allowed to do, or how future implementation should interpret the canon, it requires a decision record.

## What Kinds of Changes Do Not Require a Formal Decision Record

Not every edit requires formal decision governance.

The following changes usually do not require a formal decision record.

- Spelling, grammar, punctuation, and formatting corrections that do not alter meaning.
- Cross-reference fixes or path fixes that do not alter control logic.
- Rewording for clarity when the governing meaning remains unchanged.
- Section ordering changes that improve readability without changing substance.
- Additional examples that illustrate an already-governed rule without expanding, narrowing, or changing it.
- Non-canonical implementation notes that do not alter a controlled concept or rule.

If there is genuine doubt about whether an edit changes meaning, the safer default is to treat it as governance-relevant and create a decision record.

## Decision Record Lifecycle

Every formal decision record should move through a governed lifecycle.

### Proposal

The change is identified, scoped, and written as a formal proposal before the canon is revised.

### Review

The proposal is examined for architectural consequence, vocabulary impact, workflow consequence, tenant sensitivity, and cross-document consistency.

### Approval

The decision is accepted as the governing direction, even if implementation or document revision has not yet completed.

### Implementation

The affected documents, artifacts, and later code or workflow elements are brought into alignment with the approved decision.

### Verification

The record is checked against the actual revisions to ensure the change was applied to the correct documents, scopes, and behaviors.

### Supersession

If a later decision replaces the earlier one, the earlier record remains preserved but is explicitly marked as superseded.

### Archival

Records that are rejected, historically preserved, or no longer actively governing may be archived while still remaining traceable.

The purpose of this lifecycle is to ensure that consequential change is surfaced before it becomes governing reality.

## Decision Record Template

Every formal decision record must contain the following fields.

### Decision ID

A unique identifier for the record.

### Title

A precise title that states what the decision governs.

### Status

The current lifecycle state of the record.

### Date

The date the record entered its current formal state.

### Owner

The responsible human owner for the decision.

### Affected documents, layers, or domains

The canonical documents, architectural layers, domain modules, or platform scopes affected by the decision.

### Problem being addressed

The design, governance, behavioral, or commercial problem that made the decision necessary.

### Options considered

The main alternatives considered before choosing a direction.

### Chosen decision

The actual governing decision being adopted.

### Rationale

Why this decision was chosen over the alternatives.

### Expected consequences

The expected architectural, behavioral, commercial, governance, or implementation consequences of the decision.

### Risks

The risks created, accepted, or mitigated by the decision.

### Tenant or governance implications

Any effect on learning scope, reporting scope, access control, tenant boundaries, or governance sensitivity.

### Implementation implications

Which documents, workflows, code areas, or operational rules must change because of the decision.

### Rollback or reconsideration conditions

The conditions under which the decision should be reviewed, revised, or reversed.

### Supersedes or superseded by references

Explicit links to earlier decisions replaced by this one or later decisions that replace it.

These fields are the minimum structure for a governing decision record.

## Status Model

The following statuses are valid for formal decision records.

### Proposed

The record has been created as a formal candidate decision but is not yet governing.

### Approved

The decision has been accepted as the governing direction, but aligned implementation or document revision may still be in progress.

### Implemented

The decision has been applied to the affected canonical documents, architecture, or governed platform behavior.

### Superseded

The decision was once governing but has been explicitly replaced by a later formal decision.

### Rejected

The proposal was considered and not accepted as governing direction.

### Archived

The record is retained for traceability and historical understanding but is not an active governing decision.

No other informal status should be treated as authoritative.

## Canonical Document Revision Rules

Once a decision record exists for a consequential change, canonical documents must be revised in disciplined alignment with that record.

At minimum, the following rules apply.

- Canonical documents must not be revised in ways that contradict an approved decision record.
- If a consequential canonical revision is proposed before the decision is approved, the revision should remain aligned to proposed status and not be treated as final canon.
- When a decision is implemented, all affected canonical documents should be updated coherently rather than leaving partial contradiction in the canon.
- Canonical documents should not silently absorb a changed rule without corresponding decision lineage when the change is governance-relevant.
- If an approved decision implies changes across multiple documents, those documents should be treated as one governed revision set.

Canonical documents are therefore downstream expressions of governed decisions, not independent sources of contradictory truth.

## Conflict Resolution Rules

When two documents appear to conflict, the conflict must be surfaced and resolved deliberately.

The default conflict-resolution rules are as follows.

1. Check whether a formal decision record explains the difference.
2. If one document reflects a later approved or implemented decision record and the other does not, the later governed decision controls.
3. If the glossary meaning conflicts with another document's casual usage, the glossary controls until formally revised.
4. If the constitution conflicts with a domain or workflow document, the conflict must be treated as governance-critical and resolved through formal decision record rather than local reinterpretation.
5. If two canonical documents conflict with no formal decision trail, the conflict must be treated as unresolved and should not be silently patched by whichever editor touches it next.

Conflict must lead to explicit governance, not quiet winner-picking by convenience.

## AI-Assisted Change Governance

AI-assisted edits, suggestions, summaries, and architecture proposals are allowed, but they do not bypass formal control.

AI productivity becomes governance risk when generated content is treated as authoritative merely because it is fluent, fast, or structurally plausible.

The following rules apply.

- AI-generated changes must be evaluated as proposed content, not governing truth.
- If an AI-assisted edit changes a canonical rule, boundary, meaning, or behavior, it must be governed by the same decision-record discipline as any human-authored proposal.
- AI-generated wording must be checked for unintended change in meaning, not only for readability.
- AI must not silently reconcile conflicts among canonical documents by inventing compromise language without explicit approval.
- AI-assisted edits should preserve traceability by linking consequential changes to formal decision records.

AI may accelerate disciplined change. It must not replace disciplined change.

## Tenant and Governance Sensitivity

Changes to learning scope, reporting scope, decision scope, access-control rules, or tenant isolation require especially strong governance.

These changes are high sensitivity because they can alter what the platform is allowed to learn from, what clients are allowed to see, and how recommendation logic behaves across governed boundaries.

The following should therefore be treated as high-governance changes.

- Broadening or narrowing learning scope.
- Broadening or narrowing reporting scope.
- Changing benchmark-safe comparison rules.
- Changing which stores, brands, client groups, or tenants may be compared, learned from, or exposed in output.
- Changing the distinction between internal learning context and client-facing reporting context.

Tenant-boundary drift is not an implementation detail. It is governance risk and must be treated accordingly.

## Cross-Domain Change Rules

The platform is intended to expand beyond Promotional Allocation into many future domains. Cross-domain change must therefore be governed without breaking the shared platform structure.

The following rules apply.

- New business functions must be added as domain modules, not as miscellaneous features inside existing domains.
- Cross-domain coordination changes must preserve the shared core architecture and shared decision grammar.
- A change that appears local to one domain but alters shared vocabulary, shared architecture, or shared governance must be treated as platform-level change.
- Domain-specific exceptions must not become hidden rewrites of the shared platform.
- If a future domain requires a genuine shared-rule change, that change must be governed explicitly at the platform level rather than absorbed inside one domain document.

Cross-domain growth should increase breadth without weakening structural coherence.

## Traceability Requirements

The platform must preserve decision lineage over time.

At minimum, traceability should allow the platform to answer the following questions.

- Which formal decision introduced a given architectural, workflow, simulation, policy, or governance rule?
- Which canonical documents were changed because of that decision?
- Which earlier decision did it replace, if any?
- Which future decision later revised or superseded it?
- Which domains, layers, scopes, or tenant rules were affected?
- Under which governance status did the change occur?

Traceability matters because the platform must be able to explain not only its present state, but its change lineage.

## Failure Modes in Change Governance

Weak change governance creates direct platform risk.

### Silent terminology drift

Terms keep the same names while their meanings shift across documents, causing architecture and implementation to detach from intended design.

### Hidden architecture change

Shared structural assumptions change through scattered edits without any formal record explaining why.

### Workflow inconsistency

Different workflow documents begin to imply different action rules, escalation rules, or explanation requirements.

### Simulation-rule drift

Simulation triggers, validity rules, or counterfactual assumptions change informally and later become embedded in implementation without governance review.

### Undocumented scope expansion

Learning scope, reporting scope, or domain scope broadens quietly through document edits or implementation convenience.

### Tenant-boundary erosion

Access-control or reporting-boundary logic weakens over time because no formal governance process marks those changes as high sensitivity.

### Policy-learning drift

Adaptation behavior changes through accumulated local edits without a reconstructible trail showing why confidence, thresholds, or policy rules changed.

### Conflicting canonical documents

Multiple canonical documents begin to disagree with one another because revisions were made locally without a platform-level decision trail.

These failure modes are not documentation defects alone. They are ways the platform can lose coherence while still appearing productive.

## Non-Negotiables

1. Documentation is part of the control system of the platform.
2. Canonical documents must not be changed casually.
3. Meaning drift is architecture drift.
4. Workflow drift is decision-quality drift.
5. Tenant-boundary drift is governance risk.
6. Consequential changes must be governed through formal decision records.
7. AI-assisted productivity must not bypass formal control.
8. Conflicts among canonical documents must be surfaced explicitly rather than absorbed silently.
9. The platform must preserve change lineage over time.
10. The platform must be able to explain not only what it does now, but why it changed.

## Closing Statement

This document protects the platform from evolving by convenience instead of by governed judgment.

Fourth Form is building a decision intelligence system whose coherence depends on the alignment of vocabulary, architecture, workflow, simulation, learning logic, tenant boundaries, and commercial purpose. If those elements change silently, the platform may continue to grow while losing the very discipline that makes it valuable.

Formal decision records are therefore not administrative overhead. They are how the platform preserves coherence while evolving.

If this governance model remains intact, the platform can change deliberately without forgetting why it changed.

If it weakens, the platform will eventually stop knowing what it is enforcing and why.