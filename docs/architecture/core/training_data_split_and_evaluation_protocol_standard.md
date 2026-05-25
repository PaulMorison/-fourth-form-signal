# Training Data Split and Evaluation Protocol Standard for the Fourth Form Retail Decision Intelligence Platform

## Purpose

This document defines the shared platform standard for governed evaluation protocol design and reuse, governed split scheme legitimacy, governed holdout legitimacy, temporal and causal split discipline, leakage prevention, contamination control, evaluation-window legitimacy, cross-run evaluation comparability, protocol lineage, and promotion-safe evaluation evidence boundaries across all current and future domains.

It exists because the platform now has governed standards for model training and scoring execution, model artifact and model version governance, dataset and feature-set version governance, research and experimentation, testing and validation, release readiness, policy-learning evidence admission, benchmark-safe comparison, and shared observation-horizon semantics, but it still lacks one shared rule for how training, validation, test, holdout, and evaluation windows become legitimate, comparable, reusable, lineage-safe, and promotion-safe without casual holdout reuse, hidden leakage, protocol drift, or evaluation success being mistaken for stronger evidence than it is.

Without such a rule, the platform will drift into train/test splits being treated as governed protocols merely because they exist, validation sets being mistaken for independent holdouts, temporal order being silently broken under randomization convenience, causal contamination being normalized because the metrics still look good, evaluation windows changing under the same label, benchmark comparisons being mistaken for protocol quality, invalid protocols continuing to circulate because they still have old scores attached, and release or learning decisions leaning on evaluation results whose legitimacy was never governed strongly enough.

This document is therefore a control document for training data split and evaluation protocol governance.

It defines the scope, governance posture, governing definitions, split-legitimacy rules, holdout and evaluation-window rules, leakage and contamination rules, protocol identity rules, comparability and reuse rules, promotion and evidence boundaries, failure modes, governance linkage, implementation implications, and non-negotiables that all current and future domains must follow when constructing, naming, reusing, extending, invalidating, superseding, comparing, or citing evaluation protocols.

It is the canonical training data split and evaluation protocol standard for the platform. Future evaluation protocols, split schemes, holdouts, evaluation windows, benchmark-supported comparisons, promotion-facing evidence packages, research-evaluation extensions, and domain-local protocol extensions must align with it when preserving governed evaluation protocol, governed split scheme, governed holdout, protocol legitimacy, split legitimacy, holdout legitimacy, evaluation-window legitimacy, temporal split discipline, causal split discipline, leakage risk, contamination risk, non-comparable protocol pair, comparability-safe protocol pair, protocol identity, protocol lineage, inherited protocol, domain-extended protocol, invalidated protocol, superseded protocol, promotion-safe evaluation evidence, non-promotable evaluation result, and protocol audit trace unless a formal decision record explicitly revises it.

## Why This Standard Exists

The platform’s compounding edge depends not only on running models and versioning assets, but also on disciplined control over how models are evaluated before stronger downstream claims are made. Evaluation is where false confidence becomes cheap. If split discipline, holdout governance, leakage control, and protocol lineage are weak, then execution governance, model-version governance, validation posture, release posture, and later learning interpretation all inherit ambiguity.

Good metrics are too weak by themselves. A score can be reproducible and still be illegitimate. A holdout can exist and still be misused. A temporal split can look orderly and still violate causal boundaries. If the platform cannot state which evaluation protocol was used, what split scheme and holdout were governed, what time and intervention boundaries were respected, what leakage or contamination risks were reviewed, what evaluation window was valid, and which later comparisons remained legitimate, then downstream trust weakens even when the surface metrics look strong.

The platform therefore needs one shared standard so that evaluation accumulates as governed analytical history rather than as a pile of locally useful but semantically unstable notebooks, score tables, split scripts, and benchmark charts.

## Scope

This standard governs training, validation, test, and holdout split legitimacy; temporal and causal split discipline; evaluation-window legitimacy; leakage and contamination control; protocol identity and lineage; protocol reuse and comparability; benchmark-supported but bounded comparison; and promotion-safe evaluation evidence boundaries.

not every train/test split is a governed evaluation protocol.

governed evaluation must have named purpose, scope, and comparison intent.

temporal order must remain explicit where time matters.

causal separation must remain explicit where intervention or feedback matters.

holdouts must not be reused casually.

leakage and contamination must remain explicit and reviewable.

evaluation windows must be explicit and lineage-safe.

protocol reuse must preserve comparability conditions.

benchmark use must not silently redefine protocol legitimacy.

protocol success must not be confused with deployment legitimacy.

invalid protocols must remain explicitly invalidated.

superseded protocols must remain historically identifiable.

protocol lineage must remain stable and auditable.

## What This Standard Governs

This standard governs the shared control layer that sits between dataset partitioning and evaluation activity on one side and trusted evaluation evidence on the other.

It governs what makes a governed evaluation protocol legitimate, what makes a governed split scheme legitimate, what makes a governed holdout legitimate, when evaluation windows are legitimate, when a protocol pair is comparability-safe, when a protocol pair is non-comparable, how inherited protocol and domain-extended protocol posture remain explicit, how invalidated and superseded protocols remain visible, how leakage and contamination remain reviewable, and how promotion-safe evaluation evidence stays separate from broader downstream claims.

It also governs protocol identity, protocol lineage, protocol audit trace posture, cross-run evaluation comparability, and the separation between technically reproducible evaluation output and semantically legitimate evaluation evidence.

## What This Standard Does Not Govern

this is not a model-training execution standard.

this is not a model-version governance standard.

this is not a research-governance standard.

this is not a testing-regression standard.

this is not a release-readiness standard.

this is not a policy-learning admission standard.

this is not a benchmark-safe comparison standard.

this is not permission for casual split reuse or silent evaluation drift.

This document does not own run execution control, retry posture, or run lineage for training and scoring runs, which remain with the model_training_and_scoring_execution_governance_standard.md standard. It does not own model identity, model-version lineage, checkpoint lineage, or deployment-safe model identity, which remain with the model_artifact_and_model_version_governance_standard.md standard. It does not own experiment admission, experiment containment, or experiment promotion posture, which remain with the research_and_experimentation_governance_standard.md standard. It does not own broader validation sufficiency, regression-surface control, or release-blocking validation posture, which remain with the testing_regression_and_validation_gate_standard.md standard. It does not own promotion and release posture, which remain with the release_readiness_and_promotion_control_standard.md standard. It does not own learning admission thresholds, which remain with the policy_learning_evidence_admission_and_update_threshold_standard.md standard. It does not own safe cohort construction or benchmark-safe exposure, which remain with the platform_benchmark_safe_comparison_and_cohort_construction_standard.md standard. It does not own post-decision maturity windows, which remain with the shared_observation_horizon_and_measurement_window_standard.md standard.

This file governs evaluation protocol meaning, split legitimacy, holdout legitimacy, and comparability posture around those adjacent controls without replacing them.

## Core Governance Position

In the Fourth Form platform, training data split and evaluation protocol governance must remain a first-class platform control whose split legitimacy, holdout legitimacy, evaluation-window legitimacy, temporal and causal separation discipline, leakage visibility, contamination visibility, comparability posture, reuse posture, and lineage posture remain explicit enough that the platform can trust evaluation evidence without mistaking convenient measurement for legitimate proof.

That is the core governance position.

a training split is not the same thing as an evaluation protocol by itself.

a validation set is not the same thing as a holdout by itself.

a test result is not the same thing as promotion readiness.

reproducibility is not the same thing as evaluation legitimacy.

comparability is not the same thing as superficial similarity.

benchmark comparison is not the same thing as protocol validity.

leakage absence is not the same thing as sufficient evidence by itself.

future evaluation-protocol extensions must be placed according to control role, not convenience.

## Governing Definitions

### Governed evaluation protocol

governed evaluation protocol is an evaluation design whose purpose, scope, comparison intent, split scheme, holdout posture, evaluation-window posture, leakage and contamination controls, identity, lineage, and legitimacy are explicit enough for serious downstream review, comparison, validation, release consideration, or policy-learning interpretation.

### Governed split scheme

governed split scheme is the governed partitioning design that specifies how training, validation, test, holdout, and other evaluation partitions are formed and why that partitioning is legitimate for the intended comparison claim.

### Governed holdout

governed holdout is a bounded evaluation partition whose intended independence, reuse limits, purpose, scope, and lineage are explicit enough that it may serve as serious evidence without being casually recycled.

### Protocol legitimacy

protocol legitimacy is the governed condition in which an evaluation protocol has stable identity, named purpose, named scope, named comparison intent, explicit split scheme, explicit evaluation windows, explicit contamination controls, and reconstructible lineage strong enough for serious trust.

### Split legitimacy

split legitimacy is the governed condition in which a split scheme preserves the separation, scope, ordering, and comparison meaning required for the claim being attempted.

### Holdout legitimacy

holdout legitimacy is the governed condition in which a holdout remains sufficiently independent, sufficiently bounded, sufficiently preserved, and sufficiently lineaged for the use being claimed.

### Evaluation-window legitimacy

evaluation-window legitimacy is the governed condition in which the window of data admitted into evaluation is explicit, scope-valid, lineaged, and appropriate for the evaluation claim without being confused with downstream outcome-maturity windows.

### Temporal split discipline

temporal split discipline is the governed requirement that time order remain explicit where temporal ordering changes the meaning or legitimacy of evaluation.

### Causal split discipline

causal split discipline is the governed requirement that intervention, feedback, policy influence, and other causal pathways remain separated explicitly where they would otherwise contaminate evaluation meaning.

### Leakage risk

leakage risk is the governed risk that information from outside the legitimate evaluation boundary enters training, validation, testing, or holdout use strongly enough to weaken protocol legitimacy.

### Contamination risk

contamination risk is the governed risk that split boundaries, evaluation windows, reused holdouts, benchmark reuse, or protocol extensions blur strongly enough that downstream trust weakens even if obvious leakage is not present.

### Non-comparable protocol pair

non-comparable protocol pair is a pair of protocols whose scope, split scheme, holdout posture, evaluation window, contamination posture, or lineage differ materially enough that comparison must remain blocked or explicitly qualified.

### Comparability-safe protocol pair

comparability-safe protocol pair is a pair of protocols whose purpose, scope, split scheme, evaluation window, holdout posture, and lineage remain explicit enough that comparison is legitimate rather than inferred.

### Protocol identity

protocol identity is the stable identity linking one governed evaluation protocol to its named purpose, named scope, comparison intent, split scheme, holdout posture, and later lineage rather than reducing it to a notebook name, seed value, or run folder.

### Protocol lineage

protocol lineage is the reconstructible chain linking protocol identity, purpose, scope, split scheme, holdout posture, evaluation window, inherited or extended status, invalidation, supersession, and later downstream use.

### Inherited protocol

inherited protocol is a governed evaluation protocol reused without material semantic change from an earlier legitimate protocol whose identity and lineage remain explicit.

### Domain-extended protocol

domain-extended protocol is a governed evaluation protocol that extends an inherited protocol for a bounded domain need while keeping the extension explicit enough that comparability and reuse conditions remain reviewable.

### Invalidated protocol

invalidated protocol is a protocol whose ordinary reuse or citation is prohibited because split legitimacy, holdout legitimacy, evaluation-window legitimacy, leakage posture, contamination posture, or lineage posture has been broken materially enough that governed reuse is unsafe.

### Superseded protocol

superseded protocol is a protocol whose current canonical role has been replaced by a later governed protocol while its historical identity remains visible and reconstructible.

### Promotion-safe evaluation evidence

promotion-safe evaluation evidence is evaluation evidence whose protocol identity, split legitimacy, holdout legitimacy, evaluation-window legitimacy, lineage, and interpretive limits are explicit enough that it may be considered through stricter downstream gates without implying that promotion has already been granted.

### Non-promotable evaluation result

non-promotable evaluation result is an evaluation result that must remain bounded, conditional, or excluded from downstream promotion review because protocol legitimacy is too weak or too compromised for serious reuse.

### Protocol audit trace

protocol audit trace is the reconstructible trace linking protocol creation, split decisions, holdout formation, evaluation-window choices, inherited or extended reuse, invalidation, supersession, and later downstream citation or comparison.

## Split Legitimacy Rules

Not every train/test split is a governed evaluation protocol. A governed split scheme becomes part of a governed evaluation protocol only when its purpose, scope, comparison intent, boundary logic, and lineage are explicit enough that later users can tell what claim the split was built to support and what claim it was not.

Governed evaluation must have named purpose, scope, and comparison intent. A training split is not the same thing as an evaluation protocol by itself. Split legitimacy depends on what comparison is being attempted, what scope is being claimed, what partitions are being protected, and what downstream use is being contemplated.

Temporal order must remain explicit where time matters. Causal separation must remain explicit where intervention or feedback matters. A random-looking partition does not become legitimate merely because it is reproducible if the partition has erased the temporal or causal structure that gave the evaluation claim its meaning.

## Holdout and Evaluation Window Rules

Holdouts must not be reused casually. A validation set is not the same thing as a holdout by itself. Governed holdout legitimacy requires explicit purpose, explicit reuse limits, explicit scope, and explicit relation to the rest of the protocol strong enough that later readers can tell whether the holdout remained materially independent for the claim being made.

Evaluation windows must be explicit and lineage-safe. Evaluation-window legitimacy exists only when the relevant temporal slice, admission boundary, and reason for that window remain explicit enough that later users can interpret the result honestly. This standard governs evaluation-window legitimacy for protocol design. It does not redefine post-decision observation maturity, which remains owned elsewhere.

Changed evaluation windows must not hide under the same protocol identity. If the admitted evaluation period, holdout period, or comparison period changes materially, protocol identity, protocol lineage, or both must make that change visible rather than rewriting history as if the same governed protocol still applied unchanged.

## Leakage and Contamination Rules

Leakage and contamination must remain explicit and reviewable. Leakage risk exists when information from outside the legitimate evaluation boundary enters the wrong partition or evaluation stage strongly enough to weaken split legitimacy. Contamination risk exists when repeated reuse, feedback coupling, boundary confusion, benchmark substitution, or silent protocol changes weaken evaluation meaning even when obvious leakage is hard to prove.

Leakage absence is not the same thing as sufficient evidence by itself. A protocol may avoid one obvious leakage path and still remain non-legitimate if its holdout was reused casually, its evaluation window drifted, its comparison intent blurred, or its causal separation broke.

Temporal split discipline and causal split discipline must remain visible in protocol lineage strongly enough that later reviewers can tell whether feature preparation, label formation, intervention timing, or feedback exposure materially compromised the protocol. Hidden contamination is a governance defect even when the resulting metric looks good.

## Protocol Identity and Lineage Rules

Protocol identity must remain stable enough that later users can tell whether they are looking at one governed evaluation protocol, an inherited protocol, a domain-extended protocol, an invalidated protocol, or a superseded protocol. Protocol identity must not collapse into seed values, convenience filenames, model-run names, or notebook memory.

Protocol lineage must remain stable and auditable. Protocol lineage must preserve the named purpose, named scope, comparison intent, governed split scheme, governed holdout, evaluation-window legitimacy posture, inherited or extended status, invalidation status, supersession status, and downstream citation strong enough that later reviewers can reconstruct why one evaluation result was considered serious.

Invalid protocols must remain explicitly invalidated. Superseded protocols must remain historically identifiable. Protocol audit trace must remain strong enough that later users can tell whether an apparently strong result came from the current governed protocol, a superseded protocol, or an invalidated protocol that should no longer support serious claims.

## Comparability and Reuse Rules

Comparability must be explicit, not assumed. comparability is not the same thing as superficial similarity. A comparability-safe protocol pair exists only when the named purpose, named scope, comparison intent, split scheme, holdout posture, evaluation window, and contamination posture remain explicit enough that comparison is legitimate. A non-comparable protocol pair must remain explicitly non-comparable rather than being compared because the metrics share a chart or the protocol names look similar.

Protocol reuse must preserve comparability conditions. An inherited protocol may preserve comparability when reused without material semantic change. A domain-extended protocol may still be legitimate, but its extension must remain explicit enough that later users can tell whether comparability was preserved, qualified, or broken.

Benchmark use must not silently redefine protocol legitimacy. benchmark comparison is not the same thing as protocol validity. Benchmark context may help interpretation, but benchmark exposure, benchmark performance, or benchmark cohort selection does not by itself settle whether the protocol itself was legitimate.

Reproducibility is not the same thing as evaluation legitimacy. A repeated result under the same flawed protocol may still reproduce a flawed evaluation design. Reuse discipline therefore requires stable protocol identity and explicit comparability conditions, not mere rerun ability.

## Promotion and Evidence Boundaries

A test result is not the same thing as promotion readiness. Protocol success must not be confused with deployment legitimacy. Evaluation output may be persuasive and still remain weaker than the downstream evidence threshold required for release, deployment, or policy update.

Promotion-safe evaluation evidence is still not production entitlement, release legitimacy, or learning admission by itself. Promotion-safe evaluation evidence means only that the evidence preserved enough protocol legitimacy, split legitimacy, holdout legitimacy, evaluation-window legitimacy, and lineage for stricter downstream review to take it seriously. Non-promotable evaluation results must remain explicitly bounded from those stronger downstream uses.

Benchmark use must not silently redefine protocol legitimacy, and holdout performance must not silently become broader proof than the protocol was designed to support. Promotion and evidence boundaries must therefore remain visible enough that strong evaluation does not quietly become release posture, deployment posture, or learning admission by narrative convenience.

## Failure Modes

### Leakage hidden inside feature preparation

Feature preparation or label preparation introduces information across split boundaries while the protocol still presents itself as clean evaluation.

### Reused holdout mistaken for independent evidence

Repeated exposure of the same holdout is cited as if it were still materially independent evidence for a fresh claim.

### Benchmark comparison mistaken for valid protocol design

Strong benchmark-relative performance is treated as if it proved the split scheme, holdout posture, or evaluation window were legitimate.

### Temporal split violation hidden under randomization

Random partitioning obscures a material time-order violation and later users mistake the reproducible split for a temporally legitimate protocol.

### Contaminated evaluation reused as trusted evidence

Evaluation results whose split boundaries, holdout independence, or reuse posture were compromised continue to circulate as if they remained governed evidence.

### Changed evaluation window hidden under same protocol label

The effective evaluation period changes materially while the protocol continues to use the same apparent identity, making results look comparable when they are not.

### Protocol drift across runs

The split scheme, holdout posture, or comparison intent changes gradually across runs while the platform continues to present the evaluations as if one stable protocol were still in force.

### Non-comparable protocols compared as if equivalent

Metrics from materially different protocols are placed side by side without preserving the differences that make the comparison unsafe.

### Successful evaluation mistaken for promotion readiness

Good evaluation output is treated as if it already settled release or deployment posture even though downstream gates own stricter questions.

### Invalidated protocol still cited as current

An invalidated protocol continues to support current claims because its prior scores remain visible and its invalidation was not made operationally obvious enough.

## Governance Linkage

Execution governance owns run execution control, and that ownership remains with the model_training_and_scoring_execution_governance_standard.md standard. Model-version governance owns model identity and model-version lineage, and that ownership remains with the model_artifact_and_model_version_governance_standard.md standard. Research governance owns experiment admission and containment, and that ownership remains with the research_and_experimentation_governance_standard.md standard. Testing governance owns broader validation sufficiency, and that ownership remains with the testing_regression_and_validation_gate_standard.md standard. Release governance owns promotion and release posture, and that ownership remains with the release_readiness_and_promotion_control_standard.md standard. Policy-learning governance owns learning admission thresholds, and that ownership remains with the policy_learning_evidence_admission_and_update_threshold_standard.md standard. Benchmark-safe comparison owns safe cohort and benchmark exposure, and that ownership remains with the platform_benchmark_safe_comparison_and_cohort_construction_standard.md standard. Observation-horizon governance owns maturity windows, and that ownership remains with the shared_observation_horizon_and_measurement_window_standard.md standard.

This standard governs what those adjacent controls reuse when they need stable evaluation protocol meaning, split legitimacy, holdout legitimacy, evaluation-window legitimacy, explicit comparability conditions, invalidation visibility, supersession visibility, and audit-ready protocol lineage for serious evaluation evidence. It is the controlling reference for evaluation protocol governance. It is not the controlling reference for run execution control, model-version lineage, experiment admission, broader validation sufficiency, release posture, learning admission thresholds, safe benchmark exposure, or post-decision maturity windows.

## Implementation Implications

Implementation work must treat governed evaluation protocol, governed split scheme, governed holdout, evaluation-window legitimacy, and protocol lineage as first-class controlled surfaces rather than as side effects of notebook code or one-off scripts. Training, validation, test, and holdout partitions must be created, named, reused, invalidated, superseded, and cited in ways that preserve stable protocol identity and reconstructible lineage rather than relying on remembered context, copied cells, or local conventions.

Protocol reuse must preserve comparability conditions. Leakage and contamination must remain explicit and reviewable. Holdouts must not be reused casually. Benchmark use must not silently redefine protocol legitimacy. Implementation may choose concrete mechanisms, but it may not choose mechanisms that make evaluation-window changes, inherited-versus-domain-extended protocol changes, invalidation status, or protocol audit trace disappear behind local files, dashboards, or run metadata.

The platform’s compounding advantage depends on treating evaluation protocol discipline as strategic control rather than as supporting detail. Implementation should therefore favor lineage-legible, drift-resistant, contamination-resistant protocol handling over convenience behaviors that make one model comparison easier while weakening long-run trust.

## Non-Negotiables

1. Not every train/test split is a governed evaluation protocol, because partition presence alone is too weak to justify serious evaluation claims.

2. Governed evaluation must have named purpose, scope, and comparison intent, because protocol meaning collapses when later users cannot tell what claim the evaluation was built to support.

3. Temporal order must remain explicit where time matters, and causal separation must remain explicit where intervention or feedback matters, because split legitimacy fails when time and causality are erased for convenience.

4. Holdouts must not be reused casually, because a validation set is not the same thing as a holdout by itself and repeated holdout exposure destroys independent-evidence claims.

5. Leakage and contamination must remain explicit and reviewable, because hidden split compromise turns strong-looking metrics into false confidence.

6. Evaluation windows must be explicit and lineage-safe, because changing the admitted evaluation period without visible lineage rewrites protocol meaning.

7. Protocol reuse must preserve comparability conditions, because comparability is not the same thing as superficial similarity and inherited-versus-extended reuse must stay visible.

8. Benchmark use must not silently redefine protocol legitimacy, because benchmark comparison is not the same thing as protocol validity.

9. Protocol success must not be confused with deployment legitimacy, because a test result is not the same thing as promotion readiness and evaluation evidence is weaker than downstream production entitlement.

10. Invalid protocols must remain explicitly invalidated, superseded protocols must remain historically identifiable, and protocol lineage must remain stable and auditable, because evaluation trust fails when the platform cannot tell which protocol still governs the evidence it cites.