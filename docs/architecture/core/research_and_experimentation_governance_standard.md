# Research and Experimentation Governance Standard for the Fourth Form Retail Decision Intelligence Platform

## Purpose of This Document

This document defines the shared platform standard for research, experiments, pilots, trials, exploratory variants, sandbox execution, production-adjacent experimentation, experiment evaluation, promotion discipline, retirement discipline, containment posture, and anti-pollution control across all current and future platform domains.

It exists because the platform now has governing standards for canon control, lifecycle composition, commercial value creation, code architecture, security, performance, storage, build order, testing and validation, automation, implementation-agent quality, raw-data and feature-generation pipelines, policy-learning evidence admission, decision mode, system layering, interface governance, benchmark-safe comparison, shared assumptions, shared comparison sets, observation windows, failure-state handling, chronology, review resolution, and governance authority, but it does not yet have one shared rule for how research, experiments, pilots, trials, and exploratory variants may operate without allowing weakly proven work to silently become canonical system behavior. Without such a rule, the platform will drift into experiments that never state what they were testing, promising signals mistaken for mature evidence, benchmark comparisons mistaken for legitimate experiment design, sandbox work leaking into governed production, inconclusive work lingering indefinitely, failed experiments disappearing without trace, and exploratory artifacts quietly contaminating durable assets, comparability, and production trust.

This document is therefore a control document for research and experimentation governance.

It defines the core concepts, canonical experiment classes, shared experiment grammar, experiment entry rules, design and comparability rules, sandbox and production separation rules, observation and evaluation rules, promotion, retirement, and containment rules, lineage rules, inheritance rules, extension rules, and governance linkage that all current and future domains must follow when running governed research or experiments.

It is the canonical research and experimentation governance standard for the platform. Future research questions, experiment candidates, governed experiments, exploratory variants, sandbox trials, production-bounded trials, experiment reviews, promotion decisions, retirement decisions, and contained research artifacts must align with it when preserving production trust, comparability, reproducibility, lineage, containment, and anti-contamination discipline unless a formal decision record explicitly revises it.

## Role of This Document in the Platform

This document governs the shared control layer that sits between exploratory work on one side and governed platform behavior on the other.

The canon navigation and reading-order standard defines where this control belongs and how overlap is resolved, but it does not define how research and experiments themselves must operate. The canon change-control and quality-gate standard governs canonical document entry and revision, but it does not define the operating discipline for experiments before any canon change is even proposed. The end-to-end decision lifecycle composition standard governs serious decision episode composition, but it does not define what makes an experiment legitimate, comparable, or containable while it is still exploratory. The commercial value creation and realisation standard governs value pathways and stop-or-retire discipline, but it does not define research entry, variant design, or promotion thresholds for experiments. The code architecture and modularity standard governs code structure, but it does not define experiment governance. The security and data-protection standard governs security posture, but it does not define sandbox legitimacy, baseline integrity, or experiment retirement. The performance, efficiency, and scalability standard governs workload shape and efficiency discipline, but it does not define experiment class meaning. The data storage, persistence, and backup standard governs persistence legitimacy and source-of-truth discipline, but it does not define research artifact isolation or anti-contamination control. The build order and implementation sequence standard governs prerequisite-first build legitimacy, but it does not define when an experiment may begin. The testing, regression, and validation gate standard governs readiness proof for changed behavior, but it does not define what a governed experiment is or when a research result remains too immature for promotion. The automation and low-admin operating model standard governs automation posture, but it does not define experiment entry or experiment containment. The implementation-agent and code-generation quality standard governs how experiment-supporting code must be written, but it does not define experiment legitimacy. The raw-data update and feature-generation pipeline standard governs feature-production posture, but it does not define the governance of trials that may use those features. The policy-learning evidence admission and update-threshold standard governs the stricter gate from evidence into adaptation, but it does not define the governance of experiments before they become learning candidates. The decision-mode and intervention-policy standard governs what intervention posture is permitted, but it does not define the research progression logic that surrounds those modes. The system layers overview shows where experimentation may touch the platform stack, but it does not define one shared experiment-governance posture. The governed dependency registry and interface versioning standard and the cross-domain coordination and interface contract govern dependency and cross-domain consumption semantics, but they do not define when a trial is fit to touch those surfaces. The platform benchmark-safe comparison and cohort construction standard governs benchmark-safe exposure and comparison safety, but it does not define what makes an experiment legitimate. The shared assumption, hypothesis, and inference register standard governs assumption-object meaning, but it does not define experiment entry or promotion. The shared comparison set and analog reference standard governs comparison-object meaning, but it does not define experiment classes. The shared observation-horizon and measurement-window standard governs when ordinary decision outcomes mature for judgment, but it does not define experiment observation-window discipline. The shared exception, anomaly, and failure-state standard governs failure-state meaning after integrity breaks, but it does not define experiment containment rules before that escalation. The shared decision timeline and event chronology standard governs chronology meaning, but it does not define the experiment-governance posture that chronology records. The shared review resolution and case disposition standard governs review closure meaning, but it does not define promotion or retirement thresholds for experiments.

This document therefore governs how the platform runs research, experiments, pilots, trials, and exploratory variants without allowing weakly proven work to silently become canonical system behavior.

## Core Thesis

In the Fourth Form platform, research and experimentation must remain governed, question-led, baseline-disciplined, comparability-preserving, contamination-resistant control surfaces whose entry conditions, observation windows, promotion gates, retirement gates, and lineage remain explicit enough that innovation speed does not outrun production trust, decision quality, or durable asset integrity.

That is the core thesis.

experimentation is not the same thing as validation.

research is not the same thing as governed production change.

an experimental result is not the same thing as policy-learning admission.

benchmark comparison is not the same thing as experiment legitimacy.

a promising signal is not the same thing as promotion readiness.

sandbox execution is not the same thing as production entitlement.

inconclusive evidence is not the same thing as failure by itself.

future experimentation extensions must be placed according to control role, not convenience.

Experiments must preserve innovation speed without weakening production trust, lineage, comparability, reproducibility, or decision quality. Successful experiments still require promotion discipline. Promotion to canon must be stricter than experiment success alone.

## What This Standard Is and Is Not

This standard is the shared platform rule for how research and experimentation may enter, run, remain isolated, be observed, be evaluated, be promoted, be retired, or be contained without silently contaminating canonical behavior.

This standard is not a testing-regression standard. This standard is not a policy-learning admission standard. This standard is not a benchmark-safe comparison standard. This standard is not an object standard. This standard is not an implementation-agent instruction document. This standard is not an output packaging standard. This standard is not an ordinary workflow progression guide. This standard is not a workflow guide. This standard is not a domain-local experimentation note. This standard is not a model-research scratchpad. This standard is not a notebook or scratchpad convention. This standard is not permission for silent experimental drift into production. This standard is not permission to keep inconclusive experiments alive indefinitely without governance. This standard is not permission to bypass decision-mode restrictions because a path is labeled experimental. This standard is not permission to let exploratory artifacts contaminate durable assets, shared outputs, or production logic. This standard is not permission to treat interesting research as governed experimentation automatically.

The testing, regression, and validation gate standard continues to govern readiness proof for changed behavior. The policy-learning evidence admission and update-threshold standard continues to govern the stricter gate from evidence into adaptation. The platform benchmark-safe comparison and cohort construction standard continues to govern benchmark-safe exposure and comparison safety. The shared comparison set and analog reference standard continues to govern comparison-object meaning. The shared observation-horizon and measurement-window standard continues to govern ordinary outcome-maturity logic. The review, failure-state, interface, object, and workflow-adjacent standards continue to govern their own meanings. This document governs the experiment-governance posture that sits around those meanings.

## Why a Shared Research and Experimentation Governance Standard Is Necessary

The platform needs one shared research and experimentation governance standard because exploratory work is necessary for improvement, but exploratory work becomes dangerous when it can influence governed behavior without preserving question discipline, comparison discipline, observation discipline, containment posture, and explicit promotion rules.

If research and experimentation are left local, several failures follow. One team runs a variant because it feels interesting but never names the question it is testing. Another compares a new path against an unstable baseline and treats the result as meaningful anyway. Another treats benchmark-safe comparison exposure as if that alone made the experiment legitimate. Another lets sandbox code and sandbox data touch governed production paths because the pilot looked promising. Another promotes a successful trial into ordinary behavior without formal promotion discipline. Another keeps inconclusive experiments alive indefinitely because no retirement threshold exists. Another deletes failed experiments from active view and loses the lessons they carried. Another lets research artifacts remain mixed with durable assets so later contributors cannot tell what is canonical and what was exploratory. Another treats experimental success as if it were already policy-learning admission. Another preserves only the result and loses the lineage of question, hypothesis, baseline, variant, and observation window that made the result interpretable.

The platform therefore needs one shared standard so that every current and future domain inherits one coherent rule for governed experiment entry, experiment isolation, comparability-preserving measurement, observation-window discipline, promotion gates, retirement gates, containment, and no silent canon promotion rather than improvising local research habits.

## Core Concepts

### Experiment candidate

Experiment candidate is a proposed piece of research or trial work that has not yet satisfied governed experiment entry conditions.

### Governed experiment

Governed experiment is an experiment candidate that has met the platform's entry rules strongly enough to run under explicit scope, explicit baseline, explicit variant definition, explicit observation discipline, and explicit containment posture.

### Research question

Research question is the named question the platform is trying to answer through exploratory work.

### Experimental hypothesis

Experimental hypothesis is the explicit claim being tested about expected difference, effect, or explanation under governed experiment conditions.

### Experimental variant

Experimental variant is the explicitly defined alternative path, treatment, parameterization, policy, or behavior being compared against a baseline condition.

### Baseline condition

Baseline condition is the explicit reference condition against which experimental variants are judged.

### Experiment scope boundary

Experiment scope boundary is the explicit statement of population, timing, decision surface, entitlement reach, and operational surface within which the experiment is permitted to operate.

### Comparability condition

Comparability condition is the governed condition in which baseline and variant remain structurally comparable enough that observed differences can be interpreted seriously.

### Sandbox condition

Sandbox condition is the explicit condition in which research or experimentation remains isolated from governed production entitlement, canonical outputs, and durable shared assets except through explicitly controlled interfaces.

### Production contamination risk

Production contamination risk is the risk that exploratory logic, data, artifacts, or interpretations silently affect governed production behavior, durable assets, or downstream trust surfaces without explicit promotion.

### Experiment observation window

Experiment observation window is the explicit window during which experiment outcomes may be observed for research evaluation.

### Experiment evaluation threshold

Experiment evaluation threshold is the explicit minimum threshold for interpreting an experiment as promising, weak, failed, inconclusive, or promotion-worthy within research governance.

### Promotion threshold

Promotion threshold is the stricter threshold an experiment must meet before it may enter governed promotion review toward canon-aligned behavior.

### Retirement threshold

Retirement threshold is the threshold at which weak, stale, redundant, or commercially unhelpful experiments must be stopped, recorded, and retired.

### Inconclusive experiment state

Inconclusive experiment state is the governed condition in which evidence is too mixed, too weak, too immature, or too confounded to justify promotion or clean rejection yet.

### Contained experiment artifact

Contained experiment artifact is any output, code, data, report, model, or other artifact preserved as explicitly exploratory and explicitly prevented from silently becoming canonical production truth.

## Canonical Experiment Classes

### Research-only candidate

Research-only candidate is exploratory work still asking whether the platform should even invest in a governed experiment. Not all interesting research should become governed experiments.

### Sandbox governed experiment

Sandbox governed experiment is a governed experiment operating under sandbox condition, with explicit question, explicit baseline, explicit variant, and explicit containment strong enough that production contamination is prevented.

### Production-bounded governed experiment

Production-bounded governed experiment is a governed experiment allowed to touch governed production surfaces only within an explicit scope boundary, explicit entitlement posture, explicit monitoring, and explicit promotion or retirement path.

### Promotion-readiness experiment

Promotion-readiness experiment is a governed experiment whose design, observation maturity, comparability, and commercial interpretation are strong enough to justify formal promotion review without yet guaranteeing promotion.

## Shared Experiment Grammar

### Governed experiment entry

Governed experiment entry is the governed condition in which an experiment candidate has a named research question or experimental hypothesis, explicit scope, explicit baseline, explicit variant definition, explicit observation plan, and explicit containment posture.

### Explicit baseline

Explicit baseline is the requirement that every governed experiment state what reference condition it is comparing against rather than relying on vague prior behavior.

### Explicit variant definition

Explicit variant definition is the requirement that every experimental variant remain named, bounded, lineage-safe, and distinguishable from other variants and from the baseline.

### Experiment isolation

Experiment isolation is the governed separation that keeps exploratory execution, assets, and interpretations from silently contaminating canonical behavior or durable assets.

### Comparability-preserving measurement

Comparability-preserving measurement is measurement structured strongly enough that baseline and variant may be compared without hidden scope drift or confound confusion.

### Observation-window discipline

Observation-window discipline is the requirement that experiment observation start, maturity, expiry, and interpretation windows remain explicit rather than implicit.

### Promotion gate

Promotion gate is the formal gate at which experiment evidence is reviewed for possible advancement toward governed canon-aligned behavior.

### Retirement gate

Retirement gate is the formal gate at which weak, stale, redundant, or commercially unhelpful experiments are explicitly stopped and recorded.

### Containment rule

Containment rule is the rule that exploratory work, exploratory outputs, and exploratory artifacts remain contained unless and until they pass explicit promotion discipline.

### Experiment lineage

Experiment lineage is the reconstructible chain linking question, hypothesis, baseline, variants, scope, observation windows, evaluation, review, promotion, retirement, containment, and later consequences.

### Anti-contamination rule

Anti-contamination rule is the rule that production contamination must be prevented explicitly rather than assumed absent.

### Reproducibility expectation

Reproducibility expectation is the expectation that a governed experiment preserve enough design clarity, variant clarity, and measurement clarity that later review can reconstruct what was actually run.

### Reversible trial posture

Reversible trial posture is the requirement that governed trials remain stoppable, narrowable, and removable without silently rewriting ordinary production behavior.

### Human review trigger where relevant

Human review trigger where relevant is the condition in which experiment scope, exposure, ambiguity, promotion pressure, or contamination risk is serious enough that accountable human review must intervene.

### Failed experiment containment

Failed experiment containment is the requirement that failed experiments remain visible, recorded, and prevented from silently reappearing as canonical assumptions.

### Inconclusive experiment handling

Inconclusive experiment handling is the requirement that inconclusive experiments remain visible, contained, and actively governed rather than being treated as either success or disappearance.

### Research artifact isolation

Research artifact isolation is the requirement that research artifacts remain distinguishable from canonical assets, canonical outputs, and durable operational truth.

### No silent canon promotion

No silent canon promotion is the rule that experiments may not become canonical behavior, canonical assumptions, or canonical assets without explicit promotion discipline.

These grammar terms exist so the platform can distinguish exploratory work from governed production clearly enough to preserve trust. experimentation is not the same thing as validation. research is not the same thing as governed production change. an experimental result is not the same thing as policy-learning admission.

## Experiment Entry Rules

Experiments must start from a named question or hypothesis. A governed experiment may not begin merely because an idea appears interesting or because a model notebook produced a promising chart. governed experiment entry requires a named research question or experimental hypothesis, explicit scope boundary, explicit baseline, explicit variant definition, and explicit containment posture.

Not all interesting research should become governed experiments. Research-only candidates may remain isolated research artifacts when the platform is still clarifying the question, the baseline, the feasible scope boundary, the commercial relevance, or the comparability condition. That is a legitimate state. It is not a defect. It becomes a defect only when the platform treats underdefined research as governed experimentation anyway.

Every governed experiment must have an explicit baseline. Variants must be explicit and lineage-safe. Experiment candidates lacking baseline clarity, scope clarity, entitlement clarity, or containment clarity must remain outside governed experimentation until those deficiencies are resolved.

## Experiment Design and Comparability Rules

Experiment design must preserve explicit baseline, explicit variant definition, comparability-preserving measurement, and reproducibility expectation strongly enough that later review can interpret what the experiment actually tested.

benchmark comparison is not the same thing as experiment legitimacy. A benchmark-safe cohort comparison may contribute useful perspective, but it does not by itself make a design legitimate. Experiment legitimacy requires a research question, scope boundary, baseline, variant, comparability condition, observation-window discipline, and contamination control.

Experimental variants must remain explicit and lineage-safe. Baseline and variant must remain structurally comparable enough that observed differences can be interpreted without hidden scope drift, hidden entitlement drift, or hidden definition drift. Experiments must preserve comparability and observation discipline. Shared assumptions, comparison sets, and chronology should be preserved through their controlling object standards, but this standard governs the experiment-design discipline that decides whether those objects were used legitimately.

## Sandbox and Production Separation Rules

Sandbox and governed production must remain explicitly separate. sandbox execution is not the same thing as production entitlement. Sandbox condition exists to let the platform explore without silently granting production legitimacy to exploratory work.

Production contamination must be prevented explicitly. The anti-contamination rule requires experiment isolation, research artifact isolation, explicit boundary marking, explicit entitlement constraints, and explicit reversal posture before any production-adjacent experiment may operate. Research artifacts must remain distinguishable from canonical assets. This is not permission for silent experimental drift into production.

Production-bounded experiments require stronger controls than sandbox experiments. They require narrower scope, clearer baseline preservation, clearer exit criteria, clearer chronology, clearer review posture, and stronger containment if integrity weakens. Contained experiment artifacts may be preserved for learning or later review, but they may not silently become governed production truth.

## Experiment Observation and Evaluation Rules

Observation-window discipline is mandatory. Every governed experiment must have an explicit experiment observation window, explicit evaluation threshold, and explicit statement of what counts as mature enough for interpretation.

A promising signal is not the same thing as promotion readiness. Inconclusive evidence is not the same thing as failure by itself. Experiment success and failure interpretation must therefore remain explicit. Successful experiments still require promotion discipline. Inconclusive experiments must remain visible and contained. Failed experiments must not silently disappear.

Experiment observation and evaluation remain distinct from both ordinary outcome observation and policy-learning admission. The shared observation-horizon and measurement-window standard continues to govern ordinary outcome maturity. This section governs experiment observation maturity. The policy-learning standard continues to govern whether mature experimental evidence is strong enough to influence adaptation.

## Promotion, Retirement, and Containment Rules

Promotion, retirement, and containment must remain explicit enough that exploratory work cannot drift into canon by convenience.

Promotion gate requires more than experiment success alone. Promotion to canon must be stricter than experiment success alone. Promotion threshold must consider design legitimacy, comparability fidelity, observation maturity, contamination risk, commercial value, reproducibility expectation, decision-quality impact, and compatibility with adjacent standards. no silent canon promotion is allowed.

Retirement gate requires experiments that are weak, stale, redundant, structurally compromised, or commercially unhelpful to be explicitly retired rather than left lingering. This is not permission to keep inconclusive experiments alive indefinitely without governance. Inconclusive experiment handling may justify contained continuation for bounded time or bounded scope, but not indefinite drift. Failed experiment containment must remain explicit. failed experiments must not silently disappear.

Containment rule applies whenever promotion is denied, retirement is delayed, integrity weakens, or ambiguity remains material. Contained experiment artifacts must remain visible, reconstructible, and non-canonical until a later decision explicitly revises their status.

## Lineage and Auditability Rules

Experiment lineage must remain reconstructible from question through final disposition. The platform must be able to tell what research question was being asked, what hypothesis was being tested, what baseline and variants existed, what scope boundary applied, what observation window was used, what evaluation threshold governed interpretation, what confounds remained visible, what review occurred, and why the experiment was promoted, retired, contained, or marked inconclusive.

Lineage and auditability must preserve production trust. The platform must be able to reconstruct whether a later canonical change came from explicit promotion, whether a research artifact remained contained correctly, whether a failed or inconclusive experiment was retired responsibly, and whether contamination controls held.

Chronology, review resolution, assumption registration, comparison references, failure-state escalation, and related shared objects continue to govern their own meanings. This standard governs the experiment lineage that must connect into those objects cleanly enough that later review remains serious.

## Domain Inheritance Rules

Every current and future domain-local research path, sandbox trial, production-bounded experiment, pilot, exploratory variant, and promotion-candidate trial inherits the rules fixed here.

Domains must inherit governed experiment entry, explicit baseline, explicit variant definition, experiment isolation, comparability-preserving measurement, observation-window discipline, promotion gate, retirement gate, containment rule, experiment lineage, anti-contamination rule, reproducibility expectation, reversible trial posture, human review trigger where relevant, failed experiment containment, inconclusive experiment handling, research artifact isolation, and no silent canon promotion.

Domains may strengthen the discipline with stricter local scope limits, stricter promotion thresholds, stricter review triggers, stricter containment posture, or stricter retirement timing where local consequence requires it. They may not weaken the shared grammar or redefine experiment candidate, governed experiment, baseline condition, sandbox condition, production contamination risk, experiment observation window, promotion threshold, retirement threshold, inconclusive experiment state, or contained experiment artifact.

## Domain Extension Rules

Valid domain extension may add stricter local experiment classes, stricter sandbox restrictions, stronger baseline rules, stricter observation maturity requirements, or stronger retirement discipline where domain risk justifies them.

Invalid domain extension includes treating a notebook convention as if it rewrote platform experiment governance, using benchmark-safe comparison logic as a substitute for experiment legitimacy, treating experimental success as if it automatically changed policy, keeping underdefined experiments alive indefinitely, or letting exploratory artifacts drift into ordinary workflow and production logic by convenience.

future experimentation extensions must be placed according to control role, not convenience.

If an extension changes shared experiment-governance meaning, shared promotion logic, shared retirement logic, shared containment grammar, shared anti-contamination posture, or shared experiment-lineage expectations across the platform, it belongs in core. If it changes testing criteria, policy-learning admission criteria, benchmark-safe comparison rules, object meaning, interface meaning, or domain-local notebook practice, it belongs in those controlling standards instead of here. Extension is allowed. Redefinition is not.

## Governance Linkage

The canon navigation and reading-order standard should treat this file as the controlling reference for how research and experimentation governance fits into the core canon without redefining placement rules. The canon change-control and quality-gate standard should treat it as the controlling reference for how changes to shared experiment-governance meaning must be reviewed before canonical entry. The end-to-end decision lifecycle composition standard should treat it as the controlling reference for how experimental work must still preserve serious episode coherence where it touches real decision surfaces. The commercial value creation and realisation standard should treat it as the controlling reference for why research progression and retirement remain economically material. The code architecture and modularity standard should treat it as the controlling reference for the research-governance posture that experimental code must implement without redefining code quality. The security and data-protection standard should treat it as the controlling reference for why sandbox and production remain explicitly separate without redefining security posture. The performance, efficiency, and scalability standard should treat it as the controlling reference for experiment-governance meaning beneath performance constraints without redefining workload-shape policy. The data storage, persistence, and backup standard should treat it as the controlling reference for research artifact isolation without redefining persistence legitimacy. The build order and implementation sequence standard should treat it as the controlling reference for how experiments respect phase legitimacy without redefining build order. The testing, regression, and validation gate standard should treat it as the controlling reference for why experimentation does not replace validation. The automation and low-admin operating model standard should treat it as the controlling reference for how experiments remain governed when automation is present without redefining automation posture. The implementation-agent and code-generation quality standard should treat it as the controlling reference for why experimental code remains subject to quality discipline without redefining implementation quality. The raw-data update and feature-generation pipeline standard should treat it as the controlling reference for how experimental data paths remain governed without redefining pipeline semantics. The policy-learning evidence admission and update-threshold standard should treat it as the controlling reference for why experimental evidence remains distinct from learning admission until the stricter learning gate is met. The decision-mode and intervention-policy standard should treat it as the controlling reference for why experiments inherit intervention governance without redefining mode meaning. The system layers overview should treat it as the controlling reference for how experimentation may touch multiple layers without becoming a free-floating local practice. The interface standards should treat it as the controlling reference for how experiments remain governed around cross-domain surfaces without redefining interface meaning. The platform benchmark-safe comparison and cohort construction standard should treat it as the controlling reference for why benchmark-safe comparison is adjacent but not sufficient for experiment legitimacy. The relevant shared object standards should treat it as the controlling reference for how experiment-governance lineage feeds into their objects without redefining object meaning.

Changes to shared experiment classes, shared experiment-entry meaning, shared containment posture, shared promotion or retirement thresholds, shared anti-contamination rules, shared sandbox or production separation rules, or shared experiment-lineage expectations are consequential shared-platform changes. Under the governance authority matrix, the stricter applicable approval path governs. In practice this means Architecture Authority review is materially relevant, Research and Implementation Authority review is materially relevant, affected Domain Authority review is materially relevant, Governance and Boundary Authority review is materially relevant where exposure or entitlement boundaries are touched, Commercial Authority review is materially relevant where experiments may alter value pathways or capability retention, and Platform Owner plus the governing approval path controls when platform-wide experimentation governance itself is altered.

## Failure Modes in Research and Experimentation Design

### Questionless trialing

The platform runs experiments without a named research question or hypothesis, so later reviewers cannot tell what the work was even trying to prove.

### Baseline drift

The baseline condition changes silently while the experiment continues, making results look meaningful when comparability has already been lost.

### Variant ambiguity

Experimental variants are not explicitly defined, so later observers cannot distinguish one treatment from another or from ordinary behavior.

### Benchmark-legitimacy confusion

The platform mistakes benchmark comparison exposure for actual experiment legitimacy and therefore ignores missing scope, baseline, or containment discipline.

### Sandbox leakage

Sandbox logic, sandbox data, or sandbox artifacts quietly cross into governed production surfaces without explicit entitlement, promotion, or contamination review.

### Promising-signal inflation

An early or interesting signal is treated as if it were sufficient for promotion, even though observation maturity, reproducibility, or commercial meaning remains weak.

### Inconclusive drift

Inconclusive experiments remain active indefinitely because no retirement or containment decision is ever forced.

### Failed-experiment disappearance

Experiments fail or weaken materially, but the platform lets them vanish from active memory and therefore loses the lessons they carried.

### Hidden canon promotion

An experimental path becomes ordinary production behavior through convenience, habit, or copied code without explicit promotion review.

### Lost experiment lineage

The platform cannot later reconstruct question, hypothesis, baseline, variants, observation windows, evaluation, or disposition, so neither learning nor governance can trust what happened.

## Non-Negotiables

1. experimentation is not the same thing as validation, and no experiment may be treated as having replaced testing, regression, or validation discipline.
2. research is not the same thing as governed production change, and not all interesting research should become governed experiments.
3. every governed experiment must start from a named question or hypothesis, must have an explicit baseline, and must preserve explicit variant definition with lineage safety.
4. benchmark comparison is not the same thing as experiment legitimacy, and comparability-preserving measurement plus observation-window discipline are mandatory for governed interpretation.
5. sandbox execution is not the same thing as production entitlement, and production contamination must be prevented explicitly through experiment isolation, research artifact isolation, and anti-contamination control.
6. an experimental result is not the same thing as policy-learning admission, and successful experiment results still require stricter downstream gates before they influence governed learning or canon.
7. a promising signal is not the same thing as promotion readiness, and promotion to canon must be stricter than experiment success alone through an explicit promotion gate.
8. inconclusive evidence is not the same thing as failure by itself, but inconclusive experiments must remain visible, contained, and governed rather than left to drift indefinitely.
9. failed experiments must not silently disappear, and failed experiment containment, retirement gate discipline, reversible trial posture, and experiment lineage are mandatory.
10. future experimentation extensions must be placed according to control role, not convenience, and no notebook practice, local research habit, or domain-local convention may redefine the shared experimentation governance grammar.

## Closing Statement

This standard fixes the shared platform rule for how research, experiments, pilots, trials, and exploratory variants may operate without allowing weakly proven work to silently become canonical system behavior. It protects the platform from questionless trialing, baseline drift, sandbox leakage, hidden canon promotion, inconclusive drift, and research artifact contamination. And it keeps future innovation possible by ensuring that experiments remain explicit, comparable, reproducible, containable, and promotion-governed before the platform asks anyone to trust them.