# Dataset, Feature-Set, and Artifact Version Governance Standard for the Fourth Form Retail Decision Intelligence Platform

## Purpose

This document defines the shared platform standard for governed dataset versions, governed feature-set versions, governed derived artifacts, training-ready packages, scoring-ready packages, and other versioned reusable analytical assets across all current and future domains.

It exists because the platform now has governed standards for canon navigation, canon change control, storage, raw-data and feature-generation pipelines, testing and validation, policy-learning evidence admission, security and data protection, canonical metric governance, research governance, release readiness, shared output metadata, shared evidence provenance, and shared observation maturity, but it still lacks one shared rule for how raw dataset versions, processed dataset versions, feature-set versions, training-ready inputs, scoring-ready inputs, and reusable derived artifacts become identifiable, comparable, reproducible, promotable, supersedable, invalidatable, and retainable without silently mutating meaning across runs or across time.

Without such a rule, the platform will drift into raw datasets being confused with processed datasets, feature sets being confused with one-off pipeline runs, training-ready inputs being mistaken for reusable research truth, scoring-ready packages being reused as if they were training-ready packages, derived artifacts surviving with no explicit legitimacy, version labels being treated as convenient notes rather than stable identity, invalidated artifacts continuing to circulate because they still exist somewhere, and compounding knowledge assets being rebuilt, blurred, or contaminated until their long-run strategic value weakens.

This document is therefore a control document for dataset, feature-set, and artifact version governance.

It defines the scope, governance posture, version classes, version identity rules, lineage rules, promotion rules, supersession rules, invalidation rules, comparability rules, reproducibility rules, cross-run and cross-store integrity rules, failure modes, governance linkage, implementation implications, and non-negotiables that all current and future domains must follow when creating, changing, promoting, reusing, superseding, invalidating, retiring, comparing, or reconstructing governed data and feature assets.

It is the canonical dataset, feature-set, and artifact version governance standard for the platform. Future raw dataset versions, processed dataset versions, feature-set versions, training-ready packages, scoring-ready packages, reusable derived artifacts, validation baselines, research artifacts, release candidates, post-mortem evidence inputs, and policy-learning candidate inputs must align with it when preserving governed dataset version, governed feature-set version, governed derived artifact, version lineage, version legitimacy, artifact legitimacy, invalidated version, superseded version, retired version, comparability-safe version pair, non-comparable version pair, promotion-ready artifact, cross-run reproducibility, cross-store comparability, contamination risk, silent mutation risk, lineage break, and version audit trace unless a formal decision record explicitly revises it.

## Why This Standard Exists

The system’s compounding advantage comes from durable, trustworthy, reusable assets rather than from repeatedly rebuilding, mutating, or contaminating them. The platform cannot compound cleanly if one run, one experiment, one feature recalculation, or one derived asset rewrite can quietly change the meaning of what later runs believe they are reusing.

Silent mutation destroys trust. Unclear version boundaries destroy research value. Invalid but still referenced artifacts are dangerous. Derived assets are strategic capital, not disposable byproducts. If the platform cannot state which version was used, why it was legitimate, how it differed from prior versions, whether it was comparable to later versions, and whether it remained valid after upstream change, then downstream comparison, release, post-mortem reconstruction, and policy-learning reuse become structurally weak.

The platform therefore needs one shared standard so that reusable analytical assets accumulate as governed capital rather than as a pile of locally useful but semantically unstable files, tables, notebooks, or outputs.

## Scope

This standard governs raw dataset versions, processed dataset versions, feature-set versions, training-ready dataset packages, scoring-ready dataset packages, reusable derived artifacts, artifact invalidation, artifact supersession, version lineage, comparability across versions, dataset, feature, and artifact promotion thresholds, backward-traceability, cross-run reproducibility, anti-silent-mutation discipline, and anti-contamination discipline.

raw datasets, processed datasets, feature sets, and derived artifacts must remain distinguishable.

versions must have stable identity, not ad hoc labels.

feature-set changes must not silently rewrite prior research meaning.

old versions may be superseded, but they must remain historically identifiable.

invalidated artifacts must remain visibly invalidated rather than disappearing silently.

not every produced artifact deserves canonical promotion.

comparability across runs must be explicit, not assumed. comparability across stores must be explicit, not assumed.

dataset and feature promotion must be stricter than local usefulness. reproducibility must preserve lineage, scope, and governing assumptions.

artifacts used in experiments must remain distinguishable from canonical reusable artifacts. scoring-ready packages must not be treated as training-ready packages by habit. training-ready packages must not be treated as canonical research truth by default.

## What This Standard Governs

This standard governs the shared control layer that sits between produced data and feature assets on one side and trusted reusable platform assets on the other.

It governs what makes a governed dataset version legitimate, what makes a governed feature-set version legitimate, what makes a governed derived artifact legitimate, what kinds of material change require new version identity, how training-ready packages and scoring-ready packages remain distinct, how version lineage remains reconstructible, when version promotion is allowed, how supersession and invalidation remain visible, when a version pair is comparability-safe, when a version pair is non-comparable, and how cross-run reproducibility and cross-store comparability remain governed rather than implied.

It also governs anti-silent-mutation discipline, anti-contamination discipline, promotion-ready artifact posture, backward-traceability, and historical visibility of invalidated, superseded, and retired assets.

## What This Standard Does Not Govern

this is not a storage-and-backup standard.

this is not a pipeline-execution standard.

this is not a validation-gate standard.

this is not a security standard.

this is not a policy-learning admission standard.

this is not permission for uncontrolled artifact sprawl.

this is not permission to silently mutate datasets or feature sets between runs.

This document does not own storage legitimacy, backup posture, restore posture, or deletion discipline, which remain with the data storage, persistence, and backup standard. It does not own pipeline execution meaning, rebuild semantics, staged processing behavior, or feature-generation run behavior, which remain with the raw-data update and feature-generation pipeline standard. It does not own validation sufficiency, blocked validation state, or regression-surface proof, which remain with the testing, regression, and validation gate standard. It does not own policy-learning evidence admission or update thresholds, which remain with the policy-learning evidence admission and update-threshold standard. It does not own security posture, access control, secret handling, or destructive authority, which remain with the security and data protection standard. It does not own metric legitimacy, formula lineage, or KPI admission, which remain with the canonical metric and KPI governance standard. It does not rewrite relevant shared object meanings, including output metadata, evidence provenance, or observation-horizon semantics.

This file governs version meaning and reusable asset legitimacy around those adjacent controls without replacing them.

## Core Governance Position

In the Fourth Form platform, dataset, feature-set, and artifact version governance must remain a first-class platform control whose version identity, version lineage, promotion posture, supersession posture, invalidation posture, comparability posture, reproducibility posture, and anti-contamination posture remain explicit enough that the platform can compound durable knowledge rather than quietly mutating what it thinks it knows.

That is the core governance position.

a dataset version is not the same thing as a storage copy.

a feature set is not the same thing as a pipeline run by itself.

a derived artifact is not the same thing as a canonical reusable asset.

version presence is not the same thing as version legitimacy.

reproducibility is not the same thing as mere rerun ability.

supersession is not the same thing as silent replacement.

invalidated artifacts must remain historically visible.

future version-governance extensions must be placed according to control role, not convenience.

## Governing Definitions

### Governed dataset version

governed dataset version is a raw dataset version or processed dataset version whose identity, scope, lineage, and legitimacy are explicit enough for serious downstream reuse.

### Governed feature-set version

governed feature-set version is a feature-set version whose input basis, transformation basis, scope, lineage, and legitimacy are explicit enough that later users can tell what the feature set means and where that meaning came from.

### Governed derived artifact

governed derived artifact is a reusable produced artifact whose identity, source basis, transformation basis, status, and downstream legitimacy are explicit enough that it may be treated as strategic reusable capital rather than as disposable residue.

### Version lineage

version lineage is the reconstructible chain linking one version to its sources, its transformations where relevant, its predecessor and successor states where relevant, its promotion or invalidation decisions, and its downstream reuse.

### Version legitimacy

version legitimacy is the governed condition in which a version has stable identity, explicit scope, explicit lineage, explicit status, and explicit relation to its source and downstream use strong enough for serious trust.

### Artifact legitimacy

artifact legitimacy is the governed condition in which a derived artifact has earned reuse rights under explicit lineage, explicit version identity, explicit scope, and explicit promotion posture.

### Invalidated version

invalidated version is a version whose ordinary reuse is prohibited because lineage, validity, transformation meaning, scope, or contamination posture is no longer trustworthy enough for governed use.

### Superseded version

superseded version is a version whose active canonical role has been replaced by a later version while its prior identity remains historically visible and reconstructible.

### Retired version

retired version is a version whose active governed use has ended while its historical existence, lineage, and interpretive trace remain reconstructible.

### Comparability-safe version pair

comparability-safe version pair is a pair of versions whose lineage, scope, structure, and semantic posture remain explicit enough that comparison is legitimate rather than inferred.

### Non-comparable version pair

non-comparable version pair is a pair of versions whose lineage, scope, semantic posture, or structural differences are material enough that comparison must remain blocked or explicitly qualified.

### Promotion-ready artifact

promotion-ready artifact is a dataset version, feature-set version, or derived artifact whose legitimacy, lineage, scope, and validation posture are strong enough that it may be considered for broader governed reuse.

### Training-ready package

training-ready package is a governed assembled input package whose scope, lineage, version basis, and assumptions are explicit enough for model training or comparable analytical learning work.

### Scoring-ready package

scoring-ready package is a governed assembled input package whose scope, lineage, version basis, and runtime use posture are explicit enough for scoring, inference, or equivalent downstream use.

### Cross-run reproducibility

cross-run reproducibility is the governed condition in which a later run can reconstruct the relevant version identity, lineage, scope, and governing assumptions strongly enough to reproduce the prior analytical basis rather than merely rerunning some pipeline.

### Cross-store comparability

cross-store comparability is the governed condition in which dataset or feature versions remain semantically comparable across stores or other local units under explicit scope, lineage, and transformation discipline.

### Contamination risk

contamination risk is the governed risk that version boundaries, scope boundaries, source boundaries, or store boundaries are blurred strongly enough that downstream trust weakens.

### Silent mutation risk

silent mutation risk is the governed risk that a version changes materially while retaining the same identity or while looking close enough to be mistaken for the same thing.

### Lineage break

lineage break is the governed condition in which version linkage becomes too weak, too incomplete, or too rewritten for serious downstream reconstruction.

### Version audit trace

version audit trace is the reconstructible trace linking version creation, version change, promotion, supersession, invalidation, retirement, and downstream reuse.

## Dataset Version Classes

### Raw dataset version

Raw dataset version is a governed dataset version representing raw intake or raw-preserving state whose identity, scope, provenance, and downstream relation remain explicit enough that it is not mistaken for a storage copy alone. a dataset version is not the same thing as a storage copy.

### Processed dataset version

Processed dataset version is a governed dataset version representing transformed or staged data whose processing meaning, scope, lineage, and relation to raw input remain explicit enough that it is not mistaken for raw truth.

### Active dataset version

Active dataset version is a governed dataset version currently permitted for ordinary downstream governed reuse.

### Historical dataset version

Historical dataset version is a previously active or otherwise preserved dataset version retained for reconstruction, comparison, audit, or post-mortem use.

### Experimental dataset version

Experimental dataset version is a dataset version produced under research or experiment posture and not yet promoted into canonical reusable status by that fact alone.

## Feature-Set Version Classes

### Canonical feature-set version

Canonical feature-set version is a governed feature-set version whose downstream meaning, scope, and reuse posture are explicit enough for repeated shared platform use.

### Experimental feature-set version

Experimental feature-set version is a feature-set version created for bounded research, experiment, or exploration and not yet promoted into governed canonical use.

### Training-bounded feature-set version

Training-bounded feature-set version is a governed feature-set version explicitly prepared for training-ready packaging under bounded assumptions, bounded scope, and bounded comparability posture.

### Scoring-bounded feature-set version

Scoring-bounded feature-set version is a governed feature-set version explicitly prepared for scoring-ready packaging under bounded runtime or inference posture.

Feature-set changes must not silently rewrite prior research meaning. a feature set is not the same thing as a pipeline run by itself. A run may produce a feature set, but the resulting governed feature-set version earns separate meaning only when its identity, lineage, scope, and legitimacy remain explicit.

## Derived Artifact Version Classes

### Reusable derived artifact version

Reusable derived artifact version is a governed derived artifact version whose downstream reuse is legitimate because its identity, lineage, scope, and status remain explicit enough for repeated serious use.

### Local produced artifact

Local produced artifact is a produced artifact that may be useful for one bounded purpose but has not earned canonical reusable status. not every produced artifact deserves canonical promotion.

### Promotion-ready derived artifact

Promotion-ready derived artifact is a governed derived artifact whose lineage, scope, assumptions, and legitimacy posture are strong enough that canonical promotion may be considered.

### Invalidated derived artifact version

Invalidated derived artifact version is a governed derived artifact whose ordinary reuse is prohibited while its historical visibility and interpretive trace remain preserved.

### Superseded or retired derived artifact version

Superseded or retired derived artifact version is a governed derived artifact whose active role has changed or ended while its historical identity remains reconstructible.

a derived artifact is not the same thing as a canonical reusable asset. Canonical reusable status must be earned through governance rather than inherited from production alone.

## Version Identity and Lineage Rules

Versions must have stable identity, not ad hoc labels. Stable identity must remain strong enough that later readers can tell whether they are looking at the same governed version, a successor version, an invalidated version, or a merely local artifact that never entered governed reuse. version presence is not the same thing as version legitimacy.

Version identity must preserve enough explicit structure that raw dataset versions, processed dataset versions, feature-set versions, training-ready packages, scoring-ready packages, and reusable derived artifacts do not collapse into one blurred artifact story. Raw datasets, processed datasets, feature sets, and derived artifacts must remain distinguishable.

Version lineage must remain reconstructible across material changes, promotions, supersessions, invalidations, retirements, and downstream reuse. A lineage break is a governance defect because backward-traceability, post-mortem reconstruction, research interpretation, and policy-learning review all depend on reconstructible version history.

Artifacts used in experiments must remain distinguishable from canonical reusable artifacts. Training-ready packages must not be treated as canonical research truth by default, and scoring-ready packages must not be treated as training-ready packages by habit.

## Promotion, Supersession, and Invalidation Rules

Dataset and feature promotion must be stricter than local usefulness. Promotion requires more than successful production, more than a completed run, and more than local familiarity. A promotion-ready artifact must preserve version legitimacy, artifact legitimacy, lineage, scope, assumptions, and comparability posture strongly enough that later reuse is justified rather than convenient.

Supersession is not the same thing as silent replacement. Old versions may be superseded, but they must remain historically identifiable. invalidated artifacts must remain visibly invalidated rather than disappearing silently. invalidated artifacts must remain historically visible.

Retirement ends active governed use but does not erase historical meaning. A retired version remains distinct from a superseded version because retirement ends governed active life without necessarily naming a direct successor. An invalidated version remains distinct from both because invalidation is a legitimacy judgment, not merely a lifecycle transition.

Not every produced artifact deserves canonical promotion, and not every active artifact deserves long-run retention as strategic reusable capital. But once an artifact has entered governed reuse, silent disappearance, silent replacement, and silent mutation are unacceptable.

## Comparability and Reproducibility Rules

Comparability across runs must be explicit, not assumed. comparability across stores must be explicit, not assumed. A comparability-safe version pair exists only when lineage, scope, assumptions, structure, and transformation meaning remain stable enough that comparison is legitimate. A non-comparable version pair must remain explicitly non-comparable rather than being compared through convenience.

Cross-run reproducibility must remain stronger than simple rerun ability. reproducibility is not the same thing as mere rerun ability. A rerun that cannot re-establish the relevant version identity, lineage, scope, and governing assumptions has not preserved serious reproducibility.

Cross-store comparability must remain explicit enough that multi-store reuse, training, scoring, evaluation, and post-mortem interpretation do not quietly compare versions whose scope or transformation meaning diverged materially. Feature-set changes must not silently rewrite prior research meaning, because research interpretation depends on semantically stable comparability, not just on labels that look close enough.

## Cross-Run and Cross-Store Integrity Rules

Cross-run reproducibility and cross-store comparability must remain bounded by anti-contamination discipline. Contamination risk exists when versions, stores, scopes, training inputs, scoring inputs, or derived artifacts cross boundaries strongly enough that later users can no longer tell what belongs to what.

Cross-run integrity requires that a later run can identify the relevant dataset version, feature-set version, derived artifact version, package status, and governing assumptions without guessing. Cross-store integrity requires that one store's asset state does not quietly stand in for another store's asset state or population meaning unless the version is explicitly governed for that comparability.

Silent mutation risk and contamination risk must remain explicit because the platform’s long-run edge depends on compounding clean, reusable, lineage-safe assets rather than on operating with semantically blurred reuse. A version that is valid in one scope, one run, or one store must not be treated as universally reusable by habit alone.

## Failure Modes

### Silent mutation

The platform changes a dataset, feature set, or derived artifact materially while retaining the same apparent identity and later users mistake the changed asset for the prior one.

### Lineage break

Version history becomes too weak or too rewritten for later review to reconstruct what changed, why it changed, and what downstream work depended on it.

### Reused but invalid artifact

An invalidated version continues to circulate in training, scoring, research, or post-mortem work because it still exists physically and its invalid status is not carried clearly enough.

### Version collision

Different assets or materially different meanings carry identities that are too similar or too weakly differentiated for later users to tell them apart safely.

### Comparability illusion

Two versions are treated as if they were comparable because labels or outputs look close enough even though scope, transformation meaning, or lineage changed materially.

### Training and scoring package confusion

Scoring-ready packages are reused as if they were training-ready packages, or training-ready packages are reused as if they were runtime scoring packages, until downstream interpretation weakens.

### Feature drift behind same label

Feature-set meaning changes materially while the feature-set identity or feature labels look stable enough that research and downstream evaluation silently inherit a different meaning.

### Cross-store contamination

Versioned assets leak meaning or reuse posture across stores without explicit cross-store comparability, contaminating downstream evaluation and decision trust.

### Experiment artifact mistaken for canonical artifact

An experimental version or locally useful artifact is treated as a canonical reusable asset because it was useful once or because it looks mature enough.

### Superseded artifact treated as active

An explicitly superseded artifact continues to be handled as active because supersession remained visible only in theory and not in actual reuse posture.

## Governance Linkage

The data storage, persistence, and backup standard continues to own persistence legitimacy, source-of-truth role, backup role, archive posture, retention posture, and deletion posture. The raw-data update and feature-generation pipeline standard continues to own staged execution, rebuild legitimacy, checkpoint meaning, invalidation triggers from pipeline behavior, and compounding data-asset accumulation. The testing, regression, and validation gate standard continues to own validation sufficiency, regression control, blocked validation state, conditional pass posture, and validation lineage. The policy-learning evidence admission and update-threshold standard continues to own what evidence may influence policy change and when update thresholds are met. The security and data protection standard continues to own access posture, secret handling, destructive authority, and sensitive data controls. The canonical metric and KPI governance standard continues to own metric meaning, formula lineage, denominator legitimacy, and metric lifecycle meaning. Relevant shared object standards continue to own output metadata, evidence provenance, and observation maturity meanings.

This standard governs what those adjacent controls reuse when they need stable version identity, version lineage, version legitimacy, artifact legitimacy, comparability posture, reproducibility posture, supersession visibility, invalidation visibility, and retirement visibility for governed data and feature assets. It is the controlling reference for version governance. It is not the controlling reference for storage, pipeline execution, validation, security, policy-learning admission, or metric legitimacy.

Changes to governed version classes, stable identity rules, lineage requirements, promotion posture, supersession posture, invalidation posture, comparability posture, or reproducibility posture are consequential shared-platform changes. Under the governance authority matrix, the stricter applicable approval path governs. In practice this means Architecture Authority review is materially relevant, Implementation Authority review is materially relevant, Data and governance-relevant review is materially relevant where reusable data assets or cross-domain reuse are affected, and Platform Owner plus the applicable approval path controls when shared version-governance meaning is altered.

## Implementation Implications

Implementation work must treat version identity as a first-class governed surface rather than as a naming convenience. Raw dataset versions, processed dataset versions, feature-set versions, training-ready packages, scoring-ready packages, and governed derived artifacts must be stored, referenced, promoted, superseded, invalidated, and retired in ways that preserve stable identity and reconstructible lineage rather than relying on local folder names, local run names, or remembered context.

Cross-run reproducibility must preserve lineage, scope, and governing assumptions. Backward-traceability must remain strong enough that later reviewers, researchers, release decisions, post-mortem reviewers, and policy-learning reviewers can reconstruct which versioned assets were used and why. Implementation may choose concrete mechanisms, but it may not choose mechanisms that make silent mutation, silent replacement, or silent invalidation ordinary.

The platform’s compounding advantage depends on durable, trustworthy, reusable assets. Implementation should therefore favor version-legible, lineage-safe, contamination-resistant asset handling over convenience behaviors that make one run easier while weakening long-run reuse.

## Non-Negotiables

1. Raw datasets, processed datasets, feature sets, and derived artifacts must remain distinguishable, because the platform cannot preserve trust if these asset classes blur into one another.

2. Versions must have stable identity, not ad hoc labels, because later reuse, comparison, release, post-mortem reconstruction, and policy-learning review all depend on stable identification rather than remembered context.

3. Feature-set changes must not silently rewrite prior research meaning, because research value compounds only when later readers can tell whether the feature set is still the same governed analytical object.

4. Old versions may be superseded, but they must remain historically identifiable, because supersession is not the same thing as silent replacement and later interpretation depends on preserved history.

5. Invalidated artifacts must remain visibly invalidated rather than disappearing silently, because physically present but semantically unmarked artifacts are more dangerous than clearly absent ones.

6. Not every produced artifact deserves canonical promotion, because local usefulness and one-run convenience are too weak to justify long-run governed reuse.

7. Comparability across runs must be explicit, not assumed, because labels and local familiarity do not prove that two versions still mean the same thing.

8. Comparability across stores must be explicit, not assumed, because store-level differences can silently contaminate downstream reuse unless cross-store comparability is governed.

9. Scoring-ready packages must not be treated as training-ready packages by habit, because runtime readiness and training readiness are different governed asset roles.

10. Training-ready packages must not be treated as canonical research truth by default, because a package assembled for training is still a governed versioned asset with scope, lineage, and assumption boundaries rather than universal truth.