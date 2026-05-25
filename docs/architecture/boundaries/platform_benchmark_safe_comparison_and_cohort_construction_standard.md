# Platform Benchmark-Safe Comparison and Cohort Construction Standard for the Fourth Form Retail Decision Intelligence Platform

## Purpose of This Document

This document defines the shared platform standard for benchmark-safe comparison and cohort construction.

It exists because comparative output is useful only when two conditions are true at the same time.

First, the comparison must be commercially meaningful.

Second, the comparison must be safe enough to show.

If either condition fails, the platform drifts into benchmark theater, unsafe comparative exposure, or misleading reporting that looks analytically rich while weakening decision quality and governance discipline.

This document is therefore a control document for comparison safety, cohort construction, aggregation discipline, and reverse-inference protection.

It defines what benchmark-safe comparison means in operational terms, how cohorts must be constructed, what counts as like-for-like comparison, how aggregation thresholds and small-cell protections should work, how reverse-inference risk should be judged, how de-identification should be understood, and how all current and future domains must inherit the same shared comparison logic.

It is the canonical comparison-governance document for the platform. Future benchmark-safe logic, cohort construction rules, aggregation thresholds, reverse-inference protections, and comparative reporting behavior must align with it unless a formal decision record explicitly revises it.

## Role of This Document in the Platform

This document governs how the platform constructs and exposes comparative context across all domains.

The platform entitlement and scope boundary model defines the shared boundary objects, the separation of learning scope, reporting scope, and decision scope, and the benchmark-safe comparison scope concept. The Domain 01 reporting contract governs how Promotional Allocation exposes comparative context inside client-facing output. This document sits between those layers and defines the shared standard for constructing comparison cohorts, testing whether a comparison is like-for-like, deciding when aggregation is sufficient, deciding when suppression is required, and preventing unauthorized inference.

In practical terms, this document governs five things.

- How a valid comparison cohort is formed.
- What makes a comparison benchmark-safe rather than merely technically possible.
- How aggregation, de-identification, and suppression should work.
- How reporting and explanation layers may use comparative context.
- How current and future domains must inherit one shared comparison discipline.

This document therefore governs comparison logic as part of platform control.

## Core Thesis

In the Fourth Form platform, comparative output is valid only when the comparison cohort is constructed through shared governed rules, the comparison remains commercially like-for-like, the disclosure form is protected by aggregation and reverse-inference controls, and the recipient is entitled to receive it; otherwise comparison becomes a governance risk or a source of commercial distortion rather than useful context.

That is the core thesis.

Comparison usefulness and comparison safety must both be true.

## What This Standard Is and Is Not

This standard is the shared method by which the platform decides whether a comparison may be shown, how the comparison cohort should be built, and when comparison must be aggregated, constrained, or suppressed.

It is not any of the following.

- It is not a generic benchmarking feature specification.
- It is not permission to compare any entities the platform happens to contain.
- It is not a cosmetic de-identification layer added after an unsafe cohort is already formed.
- It is not a local domain convention that may be rewritten whenever one team wants a different benchmark view.
- It is not a rule that treats learning scope as though it automatically creates comparison rights.
- It is not a statistical exercise detached from commercial meaning.

A real benchmark-safe comparison standard means the platform can answer the following questions for every comparative output.

- What exact comparison cohort was constructed.
- Why those entities were considered commercially comparable.
- Why the recipient is entitled to receive that comparison.
- Why the aggregation and de-identification form is safe enough.
- Why the output does not enable unauthorized reverse inference.
- Why the domain is using the shared comparison logic rather than a local exception.

## Why a Shared Comparison Standard Is Necessary

Domains must not invent their own comparison logic independently because comparative output is one of the easiest ways for a multi-store, multi-brand, tenant-aware platform to drift into inconsistency.

If each domain defines its own benchmark-safe logic, several failures follow.

- The same tenant boundary may be respected in one domain and weakened in another.
- A cohort treated as like-for-like in one domain may be commercially invalid in another.
- De-identification may become shallow in one output surface while being stricter elsewhere.
- Future engineers and AI coding tools may reproduce whichever local comparison pattern looks most convenient rather than the governed one.
- Users may receive different meanings of benchmark-safe comparison depending on which domain generated the output.

The platform therefore needs one shared comparison standard so that every domain inherits the same safety and comparability logic even when its local business objects differ.

## Core Comparison Concepts

The platform uses the following core comparison concepts.

### Comparison cohort

The comparison cohort is the actual governed set of entities, cases, or aggregates used to generate one specific comparative output.

It is the realized comparison population for a particular view, explanation, or output package.

### Benchmark-safe comparison

Benchmark-safe comparison is comparative output that is commercially useful, entitlement-valid, aggregated or de-identified to a safe degree, and protected against unauthorized identification or reverse inference.

Benchmark-safe comparison is the only valid comparative form in the platform.

### Cohort construction

Cohort construction is the governed method by which the platform selects, filters, and groups entities into a comparison cohort.

Cohort construction is not just data selection. It is part of governance and commercial meaning.

### Aggregation threshold

The aggregation threshold is the minimum safe disclosure floor a comparison cohort must satisfy before the platform may expose a comparative result in a given form.

This threshold is not merely a row count. It includes population size, uniqueness risk, heterogeneity, role sensitivity, and the likelihood of reverse inference.

### Small-cell risk

Small-cell risk is the risk that a comparison cohort is so small, so narrow, or so structurally distinctive that a recipient can identify or infer unauthorized underlying entities or local conditions.

### Reverse-inference risk

Reverse-inference risk is the risk that a recipient can reconstruct unauthorized detail from an aggregate or de-identified comparison by combining the output with existing local knowledge, repeated views, or other contextual clues.

### De-identification

De-identification is the deliberate removal, abstraction, grouping, or transformation of comparison detail so that unauthorized underlying entities cannot be identified directly or inferred indirectly with material confidence.

### Like-for-like comparison

Like-for-like comparison is comparison among entities or cases that are sufficiently similar in commercial meaning, operating context, scope, and domain logic that the resulting comparison is informative rather than misleading.

### Comparison scope

Comparison scope is the governed boundary within which a comparison cohort may be constructed for a particular recipient and output form.

Comparison scope is derived from entitlement and benchmark-safe comparison scope, not from raw data availability.

### Comparison suppression

Comparison suppression is the required withholding, coarsening, or removal of a comparative output when the cohort is not safe enough or not meaningful enough to show.

Suppression is a valid governed outcome, not a system failure.

## Cohort Construction Rules

Valid comparison cohorts must be constructed through explicit governed rules rather than ad hoc selection.

At minimum, cohort construction must test the following.

### Commercial comparability

The cohort should compare entities or cases with materially comparable commercial conditions, proposition logic, outcome meaning, and operational significance.

A cohort that mixes fundamentally different commercial realities may be large but still invalid.

### Scope comparability

The cohort should compare like scope with like scope.

Store-level cases should not be treated as directly equivalent to client-group aggregates or tenant-level summaries unless the output explicitly operates at that broader governed level.

### Domain comparability

The cohort should compare the same domain object type or the same governed decision context.

One domain's business objects must not be casually compared with another domain's objects as though they were semantically interchangeable.

### Brand and banner comparability

The cohort should remain within the same banner or brand by default unless a broader comparison is explicitly governed, commercially defensible, and presented in an appropriately limited form.

### Store-group and tenant boundary logic

The cohort must respect store-group definitions, client-group entitlement, and tenant boundaries.

The fact that stores can be grouped analytically does not mean any grouping is safe to expose. A valid cohort must be both governance-valid and commercially coherent.

The platform should therefore build cohorts by governed eligibility rules, not by convenience filters.

## Like-for-Like Comparison Rules

For a comparison to be meaningful rather than merely possible, all of the following must be true.

- The underlying entities or cases serve comparable commercial functions.
- The comparison uses the same relevant domain logic and outcome meaning.
- The reporting scope and disclosure form are comparable.
- The comparison does not mix materially different banners or brands without explicit qualification and governance.
- The time window, operating context, and decision context are sufficiently aligned for interpretation.
- The result would still make commercial sense to an informed operator if the underlying entities were known only in abstract form.

If these conditions are weak, the comparison may still be technically computable, but it is not like-for-like and should not be treated as benchmark-safe evidence.

## Aggregation and Small-Cell Rules

Aggregation is required whenever direct identifiable comparison would violate entitlement or create material disclosure risk.

The platform must treat aggregation as a governed safety mechanism rather than as a cosmetic presentation choice.

The following rules apply.

- Comparative output should use the coarsest form necessary to make the comparison safe while preserving commercial usefulness.
- A cohort that does not satisfy the aggregation threshold for the requested output form must not be shown in that form.
- Where a finer-grained comparison would create small-cell risk, the platform should either broaden aggregation, reduce detail, or suppress the comparison entirely.
- Aggregation must not be used to conceal that the underlying cohort is commercially incoherent.
- A larger cohort is not automatically safe if it still contains structurally unique or easily inferable members.

Small-cell protection therefore requires two tests.

First, is the cohort large and heterogeneous enough for the intended disclosure form?

Second, even if the cohort is large enough in count, does it remain too narrow or distinctive for safe exposure?

If either answer is no, comparison suppression or a safer disclosure form is required.

## Reverse-Inference Protection Rules

The platform must assume that recipients may combine comparative outputs with local knowledge, prior views, timing clues, or repeated filtered queries to infer unauthorized detail.

Reverse-inference protection therefore requires more than removal of names.

The following rules apply.

- Comparative output must be assessed for what a reasonable informed recipient could infer, not only for what is explicitly displayed.
- Repeated slices that allow a recipient to isolate one underlying entity should be treated as unsafe even if each slice is individually aggregated.
- Comparative deltas, ranks, and narrow bands should be treated as potentially identifying when the underlying cohort is thin.
- A cohort that is commercially distinctive or locally obvious may require stronger suppression than a generic cohort of the same size.
- Explanation text must not add clues that allow a benchmark-safe comparison to become effectively de-anonymized.

Reverse-inference risk is therefore a governance risk, not just a statistical edge case.

## De-Identification Rules

In this platform, de-identification means more than removing names, codes, or labels.

Shallow de-identification gets three things wrong.

- It assumes hidden identifiers are enough even when the cohort is structurally obvious.
- It ignores the recipient's existing local knowledge.
- It treats aggregation as sufficient even when contextual clues make the source easily inferable.

Real de-identification in this platform should therefore do the following.

- Remove direct identifiers where those are not entitled.
- Use aggregation, cohorting, ranges, bands, or anonymized relative positioning where required.
- Prevent disclosure forms that isolate one or a very small number of members.
- Avoid explanation text that reveals the identity or commercial condition of the hidden members.
- Be evaluated together with reverse-inference risk rather than as a separate box-checking exercise.

De-identification is valid only when the output remains safe after considering direct, indirect, and contextual disclosure routes.

## Cross-Store Comparison Rules

Cross-store comparison is allowed only in governed form.

The following rules apply.

- Cross-store comparison must remain within an authorized comparison scope.
- Named-store comparison is valid only where explicit entitlement allows it.
- Where named-store comparison is not entitled, cross-store comparison should use aggregate, anonymized, or cohort-relative forms.
- Cross-store cohorts must preserve like-for-like commercial meaning rather than mixing incompatible store contexts.
- One-to-many structures such as Priceline may justify broad learning and coordinated rollout logic, but they do not justify unsafe cross-store exposure.

Cross-store comparison is therefore legitimate only when both comparison usefulness and comparison safety remain intact.

## Cross-Group Comparison Rules

Cross-store-group and cross-client-group comparison is allowed only where the recipient is entitled to receive that broader governed view.

The following rules apply.

- Cross-group comparison must use clearly defined governed groups rather than improvised collections.
- Group-level comparison must not obscure whether the comparison is among store groups, client groups, or another governed population.
- Cross-client-group comparison requires especially strong aggregation and de-identification discipline because the recipient may otherwise infer protected commercial detail.
- If one group is structurally dominant or unusually distinctive, broader aggregation or suppression may be required even when nominal cohort size appears sufficient.
- Group comparison must remain like-for-like in commercial meaning, not merely similar in count.

Cross-group comparison is therefore not automatically safer than cross-store comparison. In some cases it can create stronger inference risk.

## Cross-Banner and Cross-Brand Comparison Rules

Cross-banner and cross-brand comparison is invalid by default and only conditionally allowable in narrow governed forms.

The following rules apply.

- Comparison should remain within one banner or brand unless a broader comparison is explicitly justified.
- Cross-banner or cross-brand comparison must not imply direct equivalence where proposition logic, customer response, or operating context differs materially.
- If broader comparison is allowed, it should use heavily aggregated, clearly qualified, and commercially limited forms.
- Cross-banner explanation must not present another banner's behavior as if it were directly transferable local evidence.
- A comparison that is statistically tidy but commercially misleading is invalid even if disclosure risk is low.

Cross-banner and cross-brand comparison therefore requires two tests.

First, is it safe?

Second, is it commercially honest?

If either test fails, the comparison is not benchmark-safe.

## Domain Inheritance Rules

All current and future domains must inherit this shared comparison standard.

The following rules apply.

- A domain may define domain-specific cohort features only if they sit inside this shared comparison logic.
- A domain may narrow comparison rules where local commercial or governance sensitivity requires it.
- A domain may not broaden benchmark-safe comparison permissions, cohort-construction rules, aggregation logic, or de-identification expectations by local convenience.
- A domain may define domain-local explanation or reporting outputs, but any comparative logic inside those outputs must obey this shared standard.
- A domain that appears to require a different shared comparison rule must escalate that need through formal decision governance rather than rewriting the rule locally.

Future domains must therefore inherit this standard rather than improvising their own benchmark logic.

## Reporting and Explanation Linkage

This standard directly governs reporting views and explanation content.

The following rules apply.

- Comparative reporting may only use cohorts constructed under this standard.
- Benchmark-safe comparison shown in client-facing output must be consistent with reporting scope and role-sensitive access scope.
- Explanation content must not add detail that defeats aggregation or de-identification.
- Comparative explanation should make clear when the benchmark is aggregated, anonymized, banner-limited, or conditionally comparable.
- Learning-derived comparative context may appear in reporting or explanation only if it has been transformed into a valid benchmark-safe form.

Reporting and explanation are therefore downstream consumers of this standard, not alternative comparison authorities.

## Governance and Approval Sensitivity

Changes to this standard are high-sensitivity governance events because they can alter what comparative output the platform is allowed to expose and how safe exposure is judged.

At minimum, the following change classes are high sensitivity.

- Changes to benchmark-safe comparison rules.
- Changes to cohort-construction rules.
- Changes to aggregation thresholds or suppression logic.
- Changes to de-identification expectations.
- Changes to reverse-inference protection rules.
- Changes to cross-store, cross-group, cross-banner, or cross-brand comparison permissibility.

These changes must not be treated as local reporting refinements. They are platform-level control changes.

Consequential revisions should therefore require formal decision record, cross-document review, and approval under the stricter applicable platform governance rules, because this standard affects shared platform comparison behavior rather than one domain only.

## Failure Modes in Comparison Design

Weak comparison design creates direct platform risk.

### Unsafe cohort construction

The platform forms cohorts from whatever data is available without testing whether the members are entitlement-valid, commercially coherent, or inference-safe.

### False like-for-like comparison

The platform compares entities that are superficially similar but commercially different enough that the resulting benchmark misleads the recipient.

### Benchmark theater

Comparative views look sophisticated and data-rich, but the underlying cohort logic is weak, unsafe, or commercially empty.

### Reverse inference

Recipients reconstruct unauthorized peer-store, peer-group, or peer-client detail from aggregated or supposedly de-identified outputs.

### Small-cell leakage

The cohort is too small or too distinctive, so the output effectively reveals underlying entities even though names are omitted.

### Brand contamination

Cross-brand comparison is shown as though it were straightforwardly valid when proposition differences make the interpretation misleading.

### Comparison-scope drift

Comparison rights quietly broaden over time because domains or views treat benchmark-safe comparison as a flexible convenience feature rather than a governed boundary.

### One-to-many exposure drift

The existence of one network structure across many stores is treated as justification for broad comparative exposure that the recipients were never entitled to receive.

These are not merely analytics defects. They are governance failures and decision-quality risks.

## Non-Negotiables

1. Benchmark-safe comparison must be consistent across the platform.
2. Learning scope does not create comparison rights.
3. Comparison usefulness and comparison safety must both be true.
4. Like-for-like commercial meaning matters.
5. Small-cell risk is a governance risk.
6. Reverse-inference risk is a governance risk.
7. De-identification must be judged against actual inference risk, not only direct identifier removal.
8. Future domains must inherit this standard rather than improvising local comparison logic.
9. One-to-many retail structures do not justify unsafe comparison exposure.
10. If a comparison cannot be shown safely and honestly, it must be suppressed.

## Closing Statement

This document protects the platform from turning comparison into an unsafe or commercially hollow feature.

Fourth Form is building a decision intelligence platform that must provide useful comparative context without leaking unauthorized detail, distorting commercial meaning, or allowing convenience to override governance. That requires one shared standard for cohort construction, aggregation discipline, de-identification, and suppression.

If this standard remains intact, current and future domains can expose comparative context that is both useful and safe.

If it weakens, the platform will begin to lose trust at exactly the point where comparison appears most helpful.