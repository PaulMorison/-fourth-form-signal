# Decision Record Writing Standard and Review Checklist for the Fourth Form Retail Decision Intelligence Platform

## Purpose of This Document

This document defines the writing standard and review checklist for formal decision records in the Fourth Form platform.

It exists because a decision record is only useful if it is strong enough to govern real change. A weak record may exist in form while failing in function. It may contain a title, a date, and fluent prose, yet still fail to expose the real trade-offs, the cross-document consequences, the tenant-boundary implications, or the implementation changes that the platform must later obey.

Without an explicit quality standard, decision records drift into vagueness, shallow rationale, incomplete impact analysis, buried governance risk, and approvals granted because a record sounds polished rather than because it is rigorous.

This document is therefore a control document for decision-record quality and review discipline.

It is the canonical quality standard for formal decision records. Future proposed records should be checked against it before approval.

## Role of This Document in the Platform

This document governs the quality threshold that a formal decision record must meet before it is treated as approval-ready.

The change-governance document defines when formal decision records are required, what statuses they may hold, and how canonical change is controlled over time. This document defines what strong writing looks like inside those records, how reviewers should test them, and what review discipline must occur before a record is treated as strong enough to govern consequential change.

In practical terms, this document governs three things.

- What makes a formal decision record substantively strong.
- How each required decision-record field should be written.
- What reviewers must test before approving a proposed record.

This document therefore governs decision-record quality as part of platform governance quality.

## Core Thesis

A formal decision record is only governance-grade when it captures the real problem, the real options, the chosen change, the rationale, the affected canonical surfaces, the tenant and governance implications, and the expected consequences clearly enough that future humans and AI coding tools can reconstruct why the platform changed and what that change was meant to control.

That is the core thesis.

Good writing quality in this context is not cosmetic. It is part of governance quality.

## What This Standard Is and Is Not

This writing and review standard is a method for judging whether a decision record is strong enough to control consequential change in the platform.

It is not any of the following.

- It is not a style guide for elegant prose detached from technical meaning.
- It is not a template-completion exercise in which every field is filled but no real trade-off is exposed.
- It is not a substitute for architectural or commercial judgment.
- It is not a permissive checklist that treats fluent AI-generated text as evidence of rigor.
- It is not a documentation ritual performed after the real decision has already been made informally.

This standard exists to make sure that decision records are strong enough to govern real platform evolution.

## What Makes a Decision Record Strong

A strong decision record has the following characteristics.

- It identifies a real problem rather than merely announcing a preferred solution.
- It names the affected documents, layers, domains, scopes, or governance surfaces explicitly.
- It presents real options, not decorative alternatives written only to justify the chosen answer.
- It states the chosen decision in clear governing language rather than aspiration or narrative summary.
- It explains why the chosen option is better than the rejected options under the actual platform constraints.
- It surfaces tenant, scope, reporting, learning, or access-boundary implications explicitly rather than burying them.
- It identifies consequences, risks, and implementation implications concretely enough to guide later revision and review.
- It preserves traceability by linking to prior or superseded decisions where relevant.
- It is specific enough that a later reviewer can reconstruct what changed and why.
- It is concise enough that the governing decision is not obscured by excess narration.

A strong record is therefore not simply longer, more formal, or more polished. It is more discriminating, more explicit, and more reconstructible.

## Writing Standard by Section

### Decision ID

Good looks like a unique and stable identifier that can be referenced later without ambiguity.

Weak writing looks like a missing identifier, a reused identifier, or an inconsistent naming pattern that makes traceability harder.

### Title

Good looks like a precise title that states what is being decided and what surface of the platform it governs.

Weak writing looks like a vague title such as an update, refinement, or improvement with no indication of scope or control consequence.

### Status

Good looks like an accurate statement of where the record sits in the governance lifecycle.

Weak writing looks like a status chosen for confidence or momentum rather than for truth, such as marking a decision implemented when the canon is not yet aligned.

### Date

Good looks like a clear date tied to the record's current formal state.

Weak writing looks like an absent date, an ambiguous date, or a date that does not correspond to the status being claimed.

### Owner

Good looks like an accountable human owner who can answer questions about the decision.

Weak writing looks like no owner, an overly vague group label, or a nominal owner with no actual accountability.

### Affected documents, layers, or domains

Good looks like an explicit list of the canonical documents, architectural layers, domains, or scopes affected by the change.

Weak writing looks like broad phrases such as several documents or platform-wide impact with no explicit mapping.

### Problem being addressed

Good looks like a clear statement of the real design, governance, behavioral, or commercial problem that must be resolved.

Weak writing looks like a solution disguised as a problem, or a generic statement that gives no reason the decision is necessary now.

### Options considered

Good looks like real alternatives that were genuinely plausible and materially different in consequence.

Weak writing looks like missing alternatives, decorative strawman alternatives, or options that do not surface meaningful trade-offs.

### Chosen decision

Good looks like a crisp governing statement that a later reader can apply without guessing what was actually approved.

Weak writing looks like a broad direction, a preference, or an aspiration that leaves the governing rule unclear.

### Rationale

Good looks like a defensible explanation of why the chosen decision is preferable in light of strategy, constitution, architecture, domain logic, governance sensitivity, and commercial consequence.

Weak writing looks like preference language, novelty language, or fluency that does not expose the real reasoning.

### Expected consequences

Good looks like explicit downstream consequences for documents, architecture, workflow, simulation, policy, governance, implementation, or operator behavior.

Weak writing looks like generic optimism, missing second-order effects, or one-sided statements that mention only benefits.

### Risks

Good looks like the real downside, uncertainty, trade-off cost, or governance exposure created or accepted by the decision.

Weak writing looks like no risks, trivial risks, or risk language so vague that it cannot guide future review.

### Tenant or governance implications

Good looks like an explicit statement of whether the decision changes learning scope, reporting scope, decision scope, access-control assumptions, tenant boundaries, benchmark-safe logic, or approval sensitivity.

Weak writing looks like this field being buried, skipped, or dismissed with no meaningful test of whether governance surfaces are affected.

### Implementation implications

Good looks like a concrete statement of which documents, modules, workflows, layers, or later engineering work must change because of the decision.

Weak writing looks like a hand-wave that assumes implementation will work itself out later.

### Rollback or reconsideration conditions

Good looks like explicit conditions under which the decision should be reviewed, revised, or reversed.

Weak writing looks like review later, revisit if needed, or no reconsideration logic at all.

### Supersedes or superseded by references

Good looks like precise links to earlier or later records that explain the lineage of change.

Weak writing looks like a blank field when the decision clearly replaces or modifies prior governed direction.

## Review Checklist

Before approval, reviewers should be able to answer yes to the following questions.

- Is the real problem clearly stated?
- Does the record identify the actual governing surface being changed?
- Are the affected documents, layers, domains, or scopes named explicitly?
- Are the options materially real rather than decorative?
- Is the chosen decision written clearly enough to govern later revision?
- Does the rationale expose the real trade-offs?
- Are expected consequences concrete rather than aspirational?
- Are real risks acknowledged?
- Are tenant, reporting, learning, decision-scope, or access-boundary implications surfaced explicitly?
- Are implementation implications concrete enough to guide later updates?
- Are rollback or reconsideration conditions meaningful?
- Does the record link to any superseded or related decisions where relevant?
- Would a future reader understand why the platform changed from this record alone?

If the answer to several of these questions is no, the record is not approval-ready.

## Cross-Document Impact Review

Reviewers must test whether a proposed decision affects multiple canonical documents, even if the draft appears local at first glance.

At minimum, reviewers should ask the following.

- Does this change alter platform identity, strategic framing, or commercial objective?
- Does it alter glossary meaning or controlled terminology?
- Does it change constitutional behavior or valid action discipline?
- Does it affect shared architecture, domain invariants, workflow stages, simulation rules, post-mortem logic, policy learning, tenant boundaries, or reporting scope?
- Does it introduce a new term, rule, or structure that other canonical documents will need to reflect?

If the answer to any of these is yes, the reviewer should identify every canonical document likely affected and require the record to state that impact explicitly.

Cross-document effects should be surfaced before approval, not discovered later through contradiction.

## Tenant and Scope Review

Reviewers must treat tenant and scope implications as high-sensitivity review surfaces.

At minimum, reviewers should test the following.

- Does the decision change learning scope?
- Does it change reporting scope?
- Does it change decision scope?
- Does it alter access-control logic or entitlement assumptions?
- Does it affect benchmark-safe comparison rules?
- Does it change what may be learned from versus what may be shown?

If a record touches any of these areas, the tenant or governance implications field is not optional and must not be shallow.

Tenant-boundary implications must never be buried inside general rationale or implementation notes.

## Cross-Domain Review

Reviewers must test whether a proposed decision is truly local to one domain or whether it changes the shared platform structure.

At minimum, reviewers should ask the following.

- Does this decision affect only Domain 01, or would another future domain be expected to obey it as well?
- Does it alter the shared decision grammar?
- Does it alter shared architecture, shared vocabulary, shared governance, or shared output discipline?
- Does it create a domain-specific exception that would effectively rewrite a platform-level rule?

If a decision changes the shared platform rather than only one domain, the record must state that fact explicitly and reviewers should not allow it to masquerade as a local edit.

## AI-Assisted Drafting Rules

AI may help draft a decision record, but it must not substitute for real review.

AI can help with structure, summarization, option framing, and identification of potentially affected surfaces. It cannot be trusted by default to identify the true governance consequence of a change.

The following rules apply.

- AI-generated fluency is not evidence of decision quality.
- AI-drafted records must be reviewed for missing trade-offs, buried tenant implications, false certainty, and cross-document blind spots.
- AI must not be allowed to infer that there are no governance implications unless a human reviewer has actually tested that claim.
- AI-assisted drafting should accelerate rigor, not replace it.

AI-generated polish must never be confused with design rigor.

## Common Failure Patterns

Weak decision records often fail in recurring ways.

- The title is too vague to say what is actually being governed.
- The problem statement announces a preferred solution rather than exposing a real problem.
- The options are fake and do not surface genuine trade-offs.
- The rationale sounds polished but does not show why the chosen option is better under the platform's actual constraints.
- The affected documents are under-scoped, causing later contradiction in the canon.
- Tenant or reporting implications are omitted because they are inconvenient to surface.
- Risks are treated as an afterthought.
- Implementation implications are vague enough that no one can tell what must change next.
- Rollback logic is missing, so the decision cannot be reviewed intelligently later.
- The record is AI-fluent but governance-thin.

These failure patterns make a record present without making it strong.

## Approval Readiness Test

A decision record is ready for approval only when all of the following are true.

- The governing change is explicit.
- The problem being solved is real and clearly stated.
- The options and rationale expose real trade-offs.
- Cross-document impact has been checked.
- Tenant and scope implications have been checked.
- Cross-domain impact has been checked.
- The decision can be implemented without guessing what was intended.
- The record supports future reconstruction of why the platform changed.

If any of these conditions is weak, the record should remain in proposal review rather than move to approval.

## Non-Negotiables

1. A decision record is only useful if it captures real trade-offs and consequences.
2. Good writing quality is part of governance quality.
3. Tenant-boundary implications must never be buried.
4. Cross-document effects must be surfaced explicitly.
5. Cross-domain effects must be surfaced explicitly.
6. AI-generated polish must not be confused with design rigor.
7. A filled template is not the same as a strong record.
8. Approval must follow review discipline, not fluency or speed.
9. Decision records must support future reconstruction of why the platform changed.
10. Weak records must not control consequential change.

## Closing Statement

This document protects the platform from approving records that look complete while failing to govern real change.

Fourth Form is building a decision intelligence platform whose coherence depends on explicit reasoning, explicit boundaries, and explicit change lineage. If decision records are weak, the platform will still accumulate text, but it will stop preserving judgment.

If this standard remains intact, decision records can serve their actual purpose: to control consequential evolution with enough clarity and rigor that the platform remains explainable as it grows.

If it weakens, change will still happen, but the record of why it happened will no longer be strong enough to govern what comes next.