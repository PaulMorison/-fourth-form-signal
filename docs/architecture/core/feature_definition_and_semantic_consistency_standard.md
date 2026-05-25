# Feature Definition and Semantic Consistency Standard for the Fourth Form Retail Decision Intelligence Platform

## Purpose

This document defines the shared platform standard for canonical feature meaning, feature identity and semantic scope, feature naming legitimacy, feature formula and derivation legitimacy, denominator and unit discipline, time-basis and window semantics, inherited versus domain-extended feature semantics, feature drift visibility, cross-run and cross-store semantic comparability, and promotion-safe feature use boundaries across all current and future domains.

It exists because the platform now has governed standards for raw-data update and feature-generation pipeline control, dataset and feature-set version governance, training data split and evaluation protocol governance, canonical metric and KPI governance, glossary discipline, testing and validation, policy-learning evidence admission, and shared state-snapshot structure, but it still lacks one shared rule for how features themselves become semantically legitimate, stable, comparable, extendable, supersedable, invalidatable, and safe for repeated reuse without silent meaning drift or naming-based false confidence.

Without such a rule, the platform will drift into computed columns being treated as governed features merely because they exist, reused feature names carrying new meanings without review, formula changes being mistaken for harmless implementation edits, denominator and unit changes hiding under stable labels, time basis shifting under similar window language, inherited features being mutated locally while still presented as shared platform features, model success being mistaken for canonical feature legitimacy, invalidated features continuing to circulate because they still appear in old tables, and downstream evaluation, metrics, post-mortem work, and learning reuse resting on features whose meanings no longer hold still.

This document is therefore a control document for feature definition and semantic consistency governance.

It defines the scope, governance posture, governing definitions, feature identity rules, semantic consistency rules, formula, unit, and denominator rules, time-basis rules, inheritance rules, comparability rules, promotion and usage boundaries, failure modes, governance linkage, implementation implications, and non-negotiables that all current and future domains must follow when defining, naming, deriving, inheriting, extending, reusing, superseding, deprecating, retiring, invalidating, or auditing governed features.

It is the canonical feature definition and semantic consistency standard for the platform. Future governed features, canonical feature definitions, feature registries, feature-bearing datasets, feature reuse across runs and stores, feature extensions, semantic drift reviews, promotion-facing feature packages, and domain-local feature extensions must align with it when preserving governed feature, canonical feature definition, feature identity, feature semantic scope, feature legitimacy, formula legitimacy, denominator legitimacy, unit legitimacy, time-basis legitimacy, window legitimacy, inherited feature, domain-extended feature, feature lineage, feature drift, semantic drift, non-comparable feature pair, comparability-safe feature pair, superseded feature, deprecated feature, retired feature, invalidated feature, promotion-safe feature use, and feature audit trace unless a formal decision record explicitly revises it.

## Why This Standard Exists

The platform’s compounding edge depends not only on data movement, feature generation, model execution, evaluation, and metrics, but also on disciplined control over what a feature means when it is named, reused, compared, or cited later. Feature semantics sit underneath model quality, evaluation validity, metric consistency, and cross-domain trust. If feature meaning drifts quietly, the stack begins to lie cleanly.

Surface stability is too weak. A feature can keep the same name and lose the same meaning. A formula can keep returning values and still stop representing the concept it claims to represent. A denominator can remain numerically stable and still become illegitimate for the interpretation being claimed. If the platform cannot state what a governed feature means, what its semantic scope is, how its formula, unit, denominator, and time basis remain legitimate, and how later runs or stores can compare it safely, then downstream trust weakens even while the data still looks orderly.

The platform therefore needs one shared standard so that feature semantics accumulate as governed capital rather than as a pile of locally useful but semantically unstable columns, transformations, notebook aliases, and model inputs.

## Scope

This standard governs canonical feature meaning, feature identity, feature semantic scope, feature naming legitimacy, formula and derivation legitimacy, denominator and unit discipline, time-basis and window semantics, inherited and domain-extended semantics, feature drift visibility, semantic comparability across runs and stores, and promotion-safe feature use boundaries.

not every computed column is a governed feature.

governed features must have named purpose, semantic scope, and interpretation.

reused feature names must not silently change meaning.

formula changes must remain explicit and lineage-safe.

denominator changes must remain explicit and reviewable.

unit changes must remain explicit and reviewable.

time basis must remain explicit where time matters.

window semantics must remain explicit where rolling or period logic matters.

inherited features must remain distinguishable from domain-extended features.

comparability conditions must be explicit before reuse across stores, runs, models, or domains.

feature success in one model must not be confused with canonical feature legitimacy.

invalidated features must remain explicitly invalidated.

superseded features must remain historically identifiable.

semantic drift must remain visible and auditable.

## What This Standard Governs

This standard governs the shared control layer that sits between feature computation activity on one side and trusted reusable feature meaning on the other.

It governs what makes a governed feature legitimate, what makes a canonical feature definition legitimate, how feature identity remains stable, how feature semantic scope remains explicit, what makes feature naming legitimate, when a formula, denominator, unit, time basis, or window remains legitimate, when a feature pair is comparability-safe, when a feature pair is non-comparable, how inherited and domain-extended features remain distinguishable, how superseded, deprecated, retired, and invalidated features remain visible, and how feature drift and semantic drift remain audit-ready.

It also governs feature lineage, feature audit trace posture, cross-run and cross-store semantic comparability, and the separation between technically useful feature computation and semantically legitimate feature reuse.

## What This Standard Does Not Govern

this is not a raw-data pipeline standard.

this is not a dataset-version governance standard.

this is not a training-split or evaluation-protocol standard.

this is not a metric or KPI governance standard.

this is not a glossary replacement.

this is not a testing-regression standard.

this is not a policy-learning admission standard.

this is not permission for silent feature drift or uncontrolled feature sprawl.

This document does not own transformation execution flow, staged processing semantics, rerun control, or rebuild logic, which remain with the raw_data_update_and_feature_generation_pipeline_standard.md standard. It does not own version identity for feature packages, dataset packages, or reusable feature-bearing artifacts, which remain with the dataset_feature_set_and_artifact_version_governance_standard.md standard. It does not own split legitimacy, holdout legitimacy, or evaluation protocol legitimacy, which remain with the training_data_split_and_evaluation_protocol_standard.md standard. It does not own KPI admission, metric definition authority, or metric and denominator governance for canonical metrics, which remain with the canonical_metric_and_kpi_governance_standard.md standard. It does not own broader canonical term discipline, which remains with the glossary_and_canonical_term_usage_standard.md standard. It does not own validation sufficiency, which remains with the testing_regression_and_validation_gate_standard.md standard. It does not own learning admission thresholds, which remain with the policy_learning_evidence_admission_and_update_threshold_standard.md standard. It does not own state object meaning, which remains with the shared_state_snapshot_and_local_operating_context_standard.md standard where relevant.

This file governs feature meaning, semantic legitimacy, and semantic consistency around those adjacent controls without replacing them.

## Core Governance Position

In the Fourth Form platform, feature definition and semantic consistency must remain a first-class platform control whose feature identity, feature semantic scope, formula legitimacy, denominator legitimacy, unit legitimacy, time-basis legitimacy, window legitimacy, inheritance posture, comparability posture, and drift visibility remain explicit enough that the platform can reuse features seriously without mistaking stable labels for stable meaning.

That is the core governance position.

a feature is not the same thing as a column by itself.

a formula is not the same thing as semantic legitimacy.

a reused name is not the same thing as reused meaning.

time-window similarity is not the same thing as time-basis equivalence.

denominator stability is not the same thing as denominator legitimacy.

comparability is not the same thing as superficial naming similarity.

feature usefulness is not the same thing as canonical admission.

future feature-semantics extensions must be placed according to control role, not convenience.

## Governing Definitions

### Governed feature

governed feature is a feature whose identity, purpose, semantic scope, interpretation, formula, unit, denominator posture, time basis, window semantics, lineage, and legitimacy are explicit enough for serious downstream reuse, comparison, validation, metric use, post-mortem interpretation, or policy-learning review.

### Canonical feature definition

canonical feature definition is the authoritative governed definition that states what a governed feature means, what scope it applies to, how it is interpreted, and what semantic conditions must remain true for reuse to stay legitimate.

### Feature identity

feature identity is the stable identity linking one governed feature to its canonical feature definition, semantic scope, naming posture, derivation posture, and later lineage rather than reducing it to a column label or local alias.

### Feature semantic scope

feature semantic scope is the explicit statement of what business meaning, population, operating context, and interpretive boundary a governed feature applies to and where that meaning must not be stretched by analogy or convenience.

### Feature legitimacy

feature legitimacy is the governed condition in which a feature has stable identity, named purpose, named semantic scope, named interpretation, legitimate derivation posture, and reconstructible lineage strong enough for serious trust.

### Formula legitimacy

formula legitimacy is the governed condition in which a feature’s derivation logic remains explicit, interpretable, scope-valid, and semantically faithful strongly enough that later users can tell why the feature still means what it claims to mean.

### Denominator legitimacy

denominator legitimacy is the governed condition in which the denominator used by a normalized or ratio-like feature remains explicit, appropriate, and semantically valid for the interpretation being claimed.

### Unit legitimacy

unit legitimacy is the governed condition in which the unit, scale, or measurement basis of a feature remains explicit and appropriate strongly enough that later users can interpret the value honestly.

### Time-basis legitimacy

time-basis legitimacy is the governed condition in which the temporal basis of a feature remains explicit enough that later users can tell what reference time, event time, or period basis the feature is actually expressing.

### Window legitimacy

window legitimacy is the governed condition in which a rolling, bounded, lagged, cumulative, or period-specific feature window remains explicit, scope-valid, and semantically faithful for the use being claimed.

### Inherited feature

inherited feature is a governed feature reused without material semantic change from an earlier legitimate feature whose identity and lineage remain explicit.

### Domain-extended feature

domain-extended feature is a governed feature that extends an inherited feature for a bounded domain need while keeping the extension explicit enough that comparability and semantic review remain possible.

### Feature lineage

feature lineage is the reconstructible chain linking feature identity, canonical feature definition, formula posture, unit posture, denominator posture, time basis, window semantics, inherited or extended status, invalidation, supersession, and later downstream use.

### Feature drift

feature drift is the governed condition in which a feature’s practical behavior, computation basis, or operational interpretation shifts materially enough that later reuse may no longer be semantically safe.

### Semantic drift

semantic drift is the governed condition in which the meaning, scope, interpretation, unit, denominator, time basis, or naming implications of a feature change materially without sufficiently explicit governance visibility.

### Non-comparable feature pair

non-comparable feature pair is a pair of features whose semantic scope, formula posture, unit posture, denominator posture, time basis, window semantics, or lineage differ materially enough that comparison must remain blocked or explicitly qualified.

### Comparability-safe feature pair

comparability-safe feature pair is a pair of features whose semantic scope, interpretation, formula posture, unit posture, denominator posture, time basis, window semantics, and lineage remain explicit enough that comparison is legitimate rather than inferred.

### Superseded feature

superseded feature is a feature whose current canonical role has been replaced by a later governed feature while its historical identity remains visible and reconstructible.

### Deprecated feature

deprecated feature is a feature whose new use is discouraged or bounded while its historical identity and limited transitional visibility remain active.

### Retired feature

retired feature is a feature whose active governed use has ended while its historical existence and semantic trace remain reconstructible.

### Invalidated feature

invalidated feature is a feature whose ordinary reuse is prohibited because feature legitimacy, formula legitimacy, unit legitimacy, denominator legitimacy, time-basis legitimacy, window legitimacy, or lineage posture has been broken materially enough that governed reuse is unsafe.

### Promotion-safe feature use

promotion-safe feature use is feature use whose identity, semantic scope, legitimacy posture, and interpretive limits are explicit enough that it may be considered through stricter downstream gates without implying that broader canonical admission or unrestricted reuse has already been granted.

### Feature audit trace

feature audit trace is the reconstructible trace linking feature definition, naming decisions, semantic scope, formula changes, denominator changes, unit changes, time-basis changes, window changes, inheritance or extension, invalidation, supersession, and later downstream use.

## Feature Identity Rules

Not every computed column is a governed feature. A feature is not the same thing as a column by itself. A governed feature exists only when feature identity, canonical feature definition, named purpose, named semantic scope, and named interpretation are explicit enough that later users can tell what concept the feature is supposed to represent and what concept it is not.

Governed features must have named purpose, semantic scope, and interpretation. Feature naming legitimacy depends on whether the name remains faithful to the feature’s governed meaning, not on whether the label is short, familiar, or already present in a dataframe. A reused name is not the same thing as reused meaning.

Reused feature names must not silently change meaning. If semantic scope, interpretation, denominator posture, unit posture, or time basis changes materially, feature identity, feature lineage, or both must make that change visible rather than preserving the prior name as if nothing important changed.

## Feature Semantic Consistency Rules

Feature semantic consistency requires that canonical feature definition, feature semantic scope, and interpretation remain stable enough that later users can tell whether two features still mean the same thing. Consistency is a governance property, not a formatting property.

Feature usefulness is not the same thing as canonical admission. A feature may help one model, one analysis, or one notebook and still fail canonical feature legitimacy if its semantic scope, interpretation, or derivation posture is too unstable or too local for serious shared reuse.

Semantic drift must remain visible and auditable. Feature drift and semantic drift are governance defects when they become operationally invisible, because downstream users then continue reusing a feature under a meaning it no longer faithfully preserves.

## Formula, Unit, and Denominator Rules

A formula is not the same thing as semantic legitimacy. Formula legitimacy exists only when the feature derivation remains semantically faithful to the governed meaning being claimed. A mathematically stable computation may still be semantically illegitimate if it changed what the feature is really about.

Formula changes must remain explicit and lineage-safe. Denominator changes must remain explicit and reviewable. Unit changes must remain explicit and reviewable. denominator stability is not the same thing as denominator legitimacy. A denominator that stays numerically stable can still become semantically illegitimate if the governed population or interpretation changed underneath it.

Unit legitimacy and denominator legitimacy must remain visible in feature lineage strongly enough that later users can tell whether a change affected meaning, comparability, or permitted reuse. Hidden denominator drift and hidden unit drift are governance defects even when the feature label and value range still look familiar.

## Time Basis and Window Rules

Time basis must remain explicit where time matters. Time-basis legitimacy requires that later users can tell whether a feature is keyed to event time, observation time, reporting time, as-of time, lagged time, or another governed temporal reference. Similar wording is too weak when semantic interpretation depends on time.

Window semantics must remain explicit where rolling or period logic matters. Window legitimacy exists only when rolling, cumulative, period-bounded, or lagged semantics remain explicit enough that later users can tell what temporal slice the feature represents and what it excludes.

time-window similarity is not the same thing as time-basis equivalence. Two features may both mention seven days, one month, or last period and still remain non-comparable if their time basis or window semantics differ materially. Window and time-basis changes must therefore remain lineage-safe and reviewable.

## Inheritance and Extension Rules

Inherited features must remain distinguishable from domain-extended features. An inherited feature preserves shared meaning under narrower application. A domain-extended feature adds bounded local meaning beneath an inherited parent while keeping that extension explicit enough that later users can tell whether comparability still holds.

Domains may extend governed features, but they may not quietly mutate inherited meanings while continuing to present the result as if it were the unchanged shared parent. A reused name is not the same thing as reused meaning. Local convenience does not create authority to reinterpret the canonical feature definition.

Inheritance and extension posture must remain visible in feature lineage, feature audit trace, and downstream references strongly enough that later users can tell whether they are consuming an inherited feature, a domain-extended feature, or a merely local computation that never became a governed feature at all.

## Comparability and Reuse Rules

Comparability conditions must be explicit before reuse across stores, runs, models, or domains. comparability is not the same thing as superficial naming similarity. A comparability-safe feature pair exists only when semantic scope, interpretation, formula posture, denominator posture, unit posture, time basis, window semantics, and lineage remain explicit enough that comparison is legitimate.

A non-comparable feature pair must remain explicitly non-comparable rather than being compared because names match, formulas look similar, or values occupy the same range. Cross-run and cross-store semantic comparability require more than name reuse or pipeline reuse. They require stable semantic meaning.

Feature drift and semantic drift must remain visible and auditable before reuse continues. Reuse is legitimate only when feature lineage remains strong enough that later users can tell whether the reused feature still carries the same governed meaning or only the same apparent label.

## Promotion and Usage Boundaries

Promotion-safe feature use is still not unrestricted canonical admission, unrestricted model reuse, or automatic downstream legitimacy by itself. Promotion-safe feature use means only that the feature preserved enough identity, semantic scope, formula legitimacy, denominator legitimacy, unit legitimacy, time-basis legitimacy, window legitimacy, and lineage for stricter downstream review to take it seriously.

Feature success in one model must not be confused with canonical feature legitimacy. A useful predictor may still remain too narrow, too unstable, too local, or too semantically weak for governed feature reuse. feature usefulness is not the same thing as canonical admission.

Invalidated features must remain explicitly invalidated. Superseded features must remain historically identifiable. Deprecated and retired features must remain distinguishable. Promotion and usage boundaries must therefore remain visible enough that old feature names, successful experiments, or convenient copied code do not quietly broaden feature authority beyond what governance has actually granted.

## Failure Modes

### Reused feature name with changed meaning

The same feature name continues in use after semantic scope or interpretation changed materially, causing later users to trust naming continuity instead of meaning continuity.

### Denominator drift hidden under stable naming

The denominator governing a normalized feature changes materially while the feature keeps the same name and appears comparable when it is not.

### Unit change hidden under same formula label

The computation label remains familiar while the unit or scale changed materially enough to alter the meaning of the feature.

### Time-basis mismatch hidden under similar window wording

Two features appear similar because they mention the same period length, even though their actual time basis differs materially.

### Inherited feature confused with domain-extended feature

A local domain extension is cited as if it were the unchanged inherited shared feature, obscuring the semantic difference that later comparison depends on.

### Semantic drift across runs or stores

Operational behavior, local interpretation, or derivation posture changes across runs or stores while the platform continues treating the feature as if it still carried one stable meaning.

### Non-comparable features compared as if equivalent

Features with materially different scope, units, denominators, or time bases are compared because their names or formulas look close enough.

### Feature usefulness mistaken for canonical legitimacy

A feature that performed well in one model or one workflow is treated as if that success alone proved serious canonical reuse legitimacy.

### Invalidated feature still used as current

An invalidated feature remains present in code or data and continues supporting current claims because its invalidation is not operationally obvious enough.

### Feature lineage break

Changes to name, formula, denominator, unit, time basis, or inheritance posture become too weakly preserved for later reviewers to reconstruct what the feature actually meant.

## Governance Linkage

Raw-data pipeline governance owns transformation execution flow, and that ownership remains with the raw_data_update_and_feature_generation_pipeline_standard.md standard. Dataset and artifact version governance owns version identity of feature packages, and that ownership remains with the dataset_feature_set_and_artifact_version_governance_standard.md standard. Evaluation protocol governance owns split and protocol legitimacy, and that ownership remains with the training_data_split_and_evaluation_protocol_standard.md standard. Metric governance owns KPI and metric governance, and that ownership remains with the canonical_metric_and_kpi_governance_standard.md standard. Glossary governance owns broader canonical term discipline, and that ownership remains with the glossary_and_canonical_term_usage_standard.md standard. Testing governance owns validation sufficiency, and that ownership remains with the testing_regression_and_validation_gate_standard.md standard. Policy-learning governance owns learning admission thresholds, and that ownership remains with the policy_learning_evidence_admission_and_update_threshold_standard.md standard. State snapshot governance owns state object meaning where relevant, and that ownership remains with the shared_state_snapshot_and_local_operating_context_standard.md standard.

This standard governs what those adjacent controls reuse when they need stable feature meaning, canonical feature definition, semantic scope clarity, feature naming legitimacy, formula, denominator, unit, and time-basis legitimacy, inheritance posture, comparability conditions, invalidation visibility, and audit-ready feature lineage for serious downstream use. It is the controlling reference for feature semantics governance. It is not the controlling reference for transformation execution flow, feature-package version identity, evaluation protocol legitimacy, KPI governance, broader glossary discipline, validation sufficiency, learning admission thresholds, or shared state object meaning.

## Implementation Implications

Implementation work must treat governed feature definitions, feature identity, semantic scope, formula legitimacy, denominator posture, unit posture, time basis, window semantics, and lineage as first-class controlled surfaces rather than as comments, notebook assumptions, or incidental column names. Feature-bearing code, datasets, registries, model inputs, evaluation packages, and post-mortem references must preserve enough semantic structure that later users can tell what a feature means without reverse-engineering it from one pipeline step or one model artifact.

Reused feature names must not silently change meaning. Formula, denominator, unit, and time-basis changes must remain explicit and lineage-safe. Inherited features must remain distinguishable from domain-extended features. Semantic drift must remain visible and auditable. Implementation may choose concrete mechanisms, but it may not choose mechanisms that hide semantic change behind stable labels, copied formulas, or locally remembered conventions.

The platform’s compounding advantage depends on feature meaning remaining more stable than the models, analyses, and experiments that consume features. Implementation should therefore favor lineage-legible, semantics-preserving, drift-resistant feature handling over convenience behaviors that make one pipeline or one model easier while weakening long-run trust.

## Non-Negotiables

1. Not every computed column is a governed feature, because technical computation alone is too weak to grant semantic legitimacy.

2. Governed features must have named purpose, semantic scope, and interpretation, because feature reuse becomes unsafe when later users cannot tell what concept the feature is supposed to represent.

3. Reused feature names must not silently change meaning, because a reused name is not the same thing as reused meaning and naming continuity does not settle semantic continuity.

4. Formula changes must remain explicit and lineage-safe, because a formula is not the same thing as semantic legitimacy and hidden derivation changes rewrite feature meaning.

5. Denominator changes must remain explicit and reviewable, because denominator stability is not the same thing as denominator legitimacy and hidden denominator drift destroys trustworthy interpretation.

6. Unit changes must remain explicit and reviewable, because stable labels and stable formulas do not preserve meaning when the measurement basis changed.

7. Time basis must remain explicit where time matters, and window semantics must remain explicit where rolling or period logic matters, because time-window similarity is not the same thing as time-basis equivalence.

8. Inherited features must remain distinguishable from domain-extended features, because shared semantic trust fails when local extension quietly impersonates the inherited parent.

9. Comparability conditions must be explicit before reuse across stores, runs, models, or domains, because comparability is not the same thing as superficial naming similarity.

10. Feature success in one model must not be confused with canonical feature legitimacy, and invalidated or superseded features must remain historically visible, because feature usefulness is not the same thing as canonical admission and semantic drift must remain visible and auditable.