# Shared Observation-Horizon and Measurement-Window Standard for the Fourth Form Retail Decision Intelligence Platform

## Purpose of This Document

This document defines the shared platform standard for observation-horizon context and measurement-window context across all current and future domains.

It exists because the platform now has governed standards for execution deviation and outcome structure, post-mortem judgment, decision materiality and urgency, stage progression, review resolution, reopened handling, recommendation and commitment boundary discipline, state snapshot timing, uncertainty and confidence, evidence provenance, policy-learning admission, and governance authority, but it still lacks one shared meaning for when observation begins, when it remains early, when it becomes mature, when a measurement window expires, when a window may be extended or restarted, when judgment is permitted, and when learning is legitimately allowed.

Without a shared standard, the platform will drift into domain-specific observation horizons, visible outcomes treated as if they were already mature outcomes, early signals treated as if they were final outcomes, post-mortem judgments issued before sufficient horizon has elapsed, closed cases treated as if they were automatically learning-ready, mismatched observation windows compared as though they were equivalent, extension and restart history erased from lineage, horizon mismatch collapsed into recommendation weakness, premature judgment normalized as review discipline, and policy-learning behavior that begins adapting from immature observations as though they were mature evidence.

This document is therefore a control document for shared observation-horizon and measurement-window discipline.

It defines the core concepts, shared object meanings, shared grammar, minimum metadata requirements, lineage rules, inheritance rules, extension rules, and governance linkage that all domains must follow when preserving observation timing, measurement timing, horizon maturity, provisional status, expiration, extension, restart, post-mortem readiness, learning readiness, cross-case comparability, and later policy-learning reuse.

It is the canonical shared observation-horizon and measurement-window standard for the platform. Future domain workflow contracts, execution observation, outcome formation, review resolution, post-mortem judgment, reopened handling, evidence preservation, policy-learning reuse, and cross-domain comparison logic must align with it unless a formal decision record explicitly revises it.

## Role of This Document in the Platform

This document governs the shared temporal-maturity grammar that sits between execution and outcome reality on one side and post-mortem judgment, learning admission, and policy adaptation on the other.

The shared execution deviation and outcome object standard defines what happened in reality and preserves that outcome objects operate within a defined scope and observation horizon, but it does not define one shared meaning for when observation is early, mature, expired, extended, or restarted. The shared post-mortem and attribution judgment standard defines attribution quality and insufficient evidence judgment, but it does not define one shared meaning for when a horizon is mature enough to support a judgment. The shared decision materiality, priority, and urgency standard defines urgency horizon, deferral tolerance, and safe-to-wait or unsafe-to-wait posture, but it does not define one shared meaning for observation maturity or measurement-window closure. The shared progression-gate and stage-transition standard defines readiness movement and learning-ready posture, but it does not define one shared meaning for the temporal maturity that entitles downstream judgment or learning review. The shared review resolution and case disposition standard defines closure, expiration, unresolved disposition, and downstream settlement, but it does not define one shared meaning for the rule that a closed case may still have an immature observation horizon. The shared reopen, revisit, and reinstatement standard defines governed re-entry and qualified finality, but it does not define one shared meaning for window extension, observation restart, or preservation of immature observation through later re-entry. The shared recommendation, commitment, and action-instruction boundary standard defines advisory, binding, and executable boundaries, but it does not define one shared meaning for the later observation horizon that governs whether downstream judgment may treat outcomes as mature. The shared state snapshot and local operating context standard defines timing state and state horizon for decision-time reality, but it does not define one shared meaning for post-decision observation horizon. The shared uncertainty and confidence context standard defines uncertainty and confidence posture, but it does not define one shared meaning for observation maturity and does not permit maturity to be mistaken for confidence. The shared evidence bundle and signal provenance standard defines source provenance and evidence structure, but it does not define one shared meaning for when an observed signal is early, mature, or mismatched to the relevant horizon. The policy-learning evidence admission and update-threshold standard defines learning-grade evidence and evidence-admission discipline, but it depends on one stable way to distinguish immature observations from learning-ready observations. The platform governance roles and approval authority matrix defines consequential change authority for the canon itself; this document defines the shared temporal maturity semantics that future domains must preserve whenever observation timing, judgment timing, and learning timing are linked.

In practical terms, this document governs what observation-horizon context is, what measurement-window context is, how observation start point and observation end condition are preserved, how early observation differs from provisional observation, how mature observation differs from expired observation window, how judgment-ready observation differs from learning-ready observation, how window extension and restarted window where relevant remain traceable, what shared grammar all domains must use, what minimum metadata must be preserved, and how later systems may or may not reuse that history without casually inferring maturity after the fact.

This document therefore governs observation-horizon and measurement-window discipline as part of platform coherence.

## Core Thesis

In the Fourth Form platform, observation-horizon context and measurement-window context must remain first-class governed decision-support context whose observation start point, observation end condition, active window, maturity threshold, extension status, restart status, expiration status, comparability position, judgment-readiness posture, learning-readiness posture, mismatch state, and lineage remain explicit enough that the platform can distinguish early signal from mature outcome, provisional observation from mature observation, post-mortem readiness from execution completion, learning readiness from case closure, observation maturity from confidence, observation horizon from urgency, valid provisional review from premature judgment, and horizon mismatch from recommendation weakness.

That is the core thesis.

Visible outcome is not automatically mature outcome. Early signal is not final outcome. Post-mortem readiness is not the same thing as execution completion. Learning readiness is not the same thing as case closure. A closed case may still have an immature observation horizon. Observation maturity is not the same thing as confidence. Observation horizon is not the same thing as urgency. Horizon mismatch must remain distinguishable from recommendation weakness. Premature judgment must remain distinguishable from valid provisional review. Policy learning must not casually reuse immature observations as if they were mature evidence.

## What This Standard Is and Is Not

This standard is the shared platform rule for how the system records, links, preserves, and reuses governed observation-horizon context and governed measurement-window context.

It is not a workflow note. It is not a stopwatch. It is not a reporting convenience. It is not a confidence score. It is not an urgency model. It is not a substitute for evidence-quality judgment. It is not permission for domains to treat visible outcome as automatically mature outcome. It is not permission for domains to treat early signal as final outcome. It is not permission for domains to treat execution completion as post-mortem readiness. It is not permission for domains to treat case closure as learning readiness. It is not permission to extend a window informally and later pretend that the original horizon was always larger. It is not permission to restart observation from scratch while erasing earlier provisional history. It is not permission to blur horizon mismatch into recommendation weakness or to hide premature judgment inside ordinary review language.

A real shared observation-horizon and measurement-window standard means the platform can answer the following questions for any material decision episode: when observation opened; what start point triggered it; what end condition or maturity threshold governed it; whether the observation remained active, provisional, mature, expired, extended, or restarted; whether early signal or mature outcome was actually observed; whether sufficient horizon elapsed for the judgment being attempted; whether judgment was permitted, conditionally permitted, or prohibited pending maturity; whether learning was permitted, conditionally permitted, or prohibited pending maturity; whether the case remained closed while observation was still immature; whether the observation windows being compared were actually comparable; and whether the preserved history is strong enough for serious post-mortem and policy-learning reuse.

## Why a Shared Observation-Horizon and Measurement-Window Standard Is Necessary

Domains must not define observation-horizon and measurement-window semantics independently because the platform cannot remain one governed decision system if one domain treats visible outcome as mature after two days, another requires ninety days, another extends windows silently, another restarts observation without preserving the original window, another issues post-mortem judgment before sufficient horizon has elapsed, another treats case closure as automatic learning readiness, and another compares cases with incompatible windows as though those observations meant the same thing.

If observation-horizon and measurement-window grammar is left local, several failures follow. One domain preserves observation opened, observation provisional, and observation mature explicitly while another records only that an outcome existed. One domain preserves early signal observed separately from mature outcome observed while another records one undifferentiated result. One domain preserves that judgment was conditionally permitted while another records a strong judgment as if maturity were settled. One domain preserves that the original window expired and was later extended while another rewrites history as if the window had always been long enough. One domain preserves restarted window where relevant while another hides restart inside casual re-entry. One domain preserves horizon mismatch detected while another blames recommendation weakness for what was actually a timing mismatch. One domain preserves that a closed case remained not-yet-learning-ready while another begins adapting policy from immature observations.

The platform therefore needs one shared standard so that future domains can extend one governed temporal-maturity grammar rather than inventing their own local meanings for observation start, observation end, early observation, provisional observation, mature observation, expired observation window, judgment readiness, learning readiness, horizon mismatch, premature judgment state, and window comparability.

## Core Concepts

The platform uses the following core concepts.

### Observation-horizon context

Observation-horizon context is the governed object context that preserves the intended temporal horizon over which an outcome, effect, or consequence must be observed before the platform may treat the relevant episode as mature enough for the judgment or learning claim being attempted.

### Measurement-window context

Measurement-window context is the governed object context that preserves the actual bounded observation window within which signals, outcomes, and consequences are being measured, including whether that window is open, active, provisional, mature, expired, extended, or restarted.

### Observation start point

Observation start point is the governed event, timestamp, trigger, transition, instruction, execution event, or other explicitly defined basis from which the relevant observation horizon begins to run.

### Observation end condition

Observation end condition is the governed condition, timestamp, maturity threshold, event, or rule under which the relevant observation window closes, expires, or becomes mature enough for the specific judgment being attempted.

### Early observation

Early observation is the governed condition in which observation has begun and meaningful signals may already be visible, but the relevant horizon remains too immature for the platform to treat those signals as final outcome.

### Provisional observation

Provisional observation is the governed condition in which observation has enough substance to support bounded interim review, but the relevant horizon, comparability, or linkage remains incomplete enough that mature judgment is not yet fully entitled.

### Mature observation

Mature observation is the governed condition in which sufficient horizon has elapsed and the relevant end condition or maturity threshold has been satisfied strongly enough for the specific judgment being attempted.

### Expired observation window

Expired observation window is the governed condition in which the active measurement window has reached its permitted end or has lapsed beyond its active validity, with no ordinary assumption that maturity, comparability, or learning readiness was therefore automatically achieved.

### Judgment-ready observation

Judgment-ready observation is the governed condition in which the relevant mature observation, outcome-maturity linkage, and post-mortem readiness linkage are strong enough that serious attribution or post-mortem judgment may legitimately proceed.

### Not-yet-judgment-ready observation

Not-yet-judgment-ready observation is the governed condition in which observation may be active, early, or provisional, but the horizon, linkage, comparability, or maturity basis remains insufficient for serious attribution or post-mortem judgment.

### Learning-ready observation

Learning-ready observation is the governed condition in which observation is judgment-ready and the policy-learning maturity linkage, comparability discipline, scope validity, and evidence-admission posture are strong enough for governed learning reuse.

### Not-yet-learning-ready observation

Not-yet-learning-ready observation is the governed condition in which observation may be mature enough for some bounded review, but remains too weak, too local, too incomparable, too unresolved, or otherwise too immature for governed policy-learning reuse.

### Outcome-maturity linkage

Outcome-maturity linkage is the explicit connection between an observed outcome signal and the maturity state of the horizon or window under which that outcome was observed, so later systems can tell whether the signal was early, provisional, or mature.

### Post-mortem readiness linkage

Post-mortem readiness linkage is the explicit connection between observation maturity and the later judgment that post-mortem handling was permitted, conditionally permitted, or prohibited pending maturity.

### Policy-learning maturity linkage

Policy-learning maturity linkage is the explicit connection between observation maturity, post-mortem maturity, scope validity, comparability discipline, and later learning admission, so policy learning does not casually reuse immature observations as if they were mature evidence.

### Observation-window comparability

Observation-window comparability is the governed judgment about whether two or more observed episodes were measured over compatible windows and compatible maturity bases strongly enough to support serious comparison, aggregation, post-mortem comparison, or learning reuse.

### Window extension

Window extension is the governed condition in which an active or recently expired measurement window is deliberately widened or continued under preserved lineage because the original horizon, end condition, or judgment basis has been judged insufficient for the use being attempted.

### Restarted window where relevant

Restarted window where relevant is the governed condition in which observation begins again from a new start point because the original window no longer represents the relevant episode, causal episode, execution path, or measurement basis, while the earlier window remains reconstructible rather than erased.

### Horizon mismatch

Horizon mismatch is the governed condition in which the horizon or window used for one observation, judgment, comparison, or learning claim is materially inconsistent with the horizon needed for that claim.

### Premature judgment state

Premature judgment state is the governed condition in which a serious judgment, attribution claim, comparison claim, or learning-reuse claim is formed before sufficient horizon, mature linkage, or comparability has been preserved.

## Shared Observation-Horizon Context

At platform level, shared observation-horizon context is the formal governed context that preserves the intended temporal horizon over which an outcome, effect, or consequence must be observed before the platform may treat that episode as mature enough for serious downstream interpretation.

It exists because the platform must preserve more than that an outcome object eventually existed. It must preserve what start point opened observation, what end condition or maturity threshold governed the horizon, what use the horizon was intended to support, whether the horizon remained early, provisional, mature, or expired, whether extension or restart occurred, whether judgment-ready observation had or had not been reached, whether learning-ready observation had or had not been reached, whether horizon mismatch existed, and how later post-mortem or policy-learning handling remained anchored to the same governed timing basis.

Shared observation-horizon context must preserve, conceptually, all of the following. It must preserve an observation-horizon context ID so the temporal maturity position has stable identity. It must preserve the originating case ID so the horizon remains anchored to the governed episode. It must preserve domain reference, decision scope reference, and tenant or client scope reference where relevant so the horizon does not lose its governed population. It must preserve observation start point and observation end condition so later systems can reconstruct when the horizon began and what legitimately closed it. It must preserve intended horizon reference, maturity reference, and horizon-use reference so later systems can tell what kind of judgment the horizon was meant to support. It must preserve post-mortem readiness linkage and policy-learning maturity linkage where relevant so downstream maturity does not have to be inferred. It must preserve extension, restart, expiration, and mismatch references where relevant so temporal change does not disappear from history. It must preserve lineage or version reference and timestamp so later systems can reconstruct which governed horizon existed at the relevant time.

Observation horizon is not the same thing as urgency. Observation maturity is not the same thing as confidence. A closed case may still have an immature observation horizon. Horizon mismatch must remain distinguishable from recommendation weakness. Premature judgment state must remain distinguishable from valid provisional review.

This is governed object meaning, not code schema. Shared observation-horizon context must remain interpretable as the platform's formal record of temporal maturity requirements rather than as a reporting hint, a dashboard timer, or a local operations convention.

## Shared Measurement-Window Context

At platform level, shared measurement-window context is the formal governed context that preserves the actual bounded observation window within which signals, outcomes, and consequences were or are being measured.

It exists because the platform must preserve more than that something was observed sometime later. It must preserve whether observation opened, whether observation remained active, whether the observed signal was early or mature, whether the active window expired, whether the window was extended, whether observation restarted where relevant, whether the observed result remained provisional, whether comparability held, and how later judgment or learning claims remained tied to the actual measured window rather than to a rewritten story about what the platform always knew.

Shared measurement-window context must preserve, conceptually, all of the following. It must preserve a measurement-window context ID so the active measurement interval has stable identity. It must preserve the originating case ID so the observed window remains anchored to the governed episode. It must preserve related outcome object reference and related execution reference where relevant so later systems can reconstruct what was actually being measured. It must preserve window-open reference, active-window status reference, and window-close or expiration reference where relevant so later systems can tell whether the window was still running, had matured, or had lapsed. It must preserve early-signal reference and mature-outcome reference where relevant so the platform does not later remember all observed signals as equally final. It must preserve comparability reference, extension reference, and restart reference where relevant so later systems can judge whether comparison or reuse was legitimate. It must preserve judgment-readiness reference and learning-readiness reference where relevant so downstream interpretation does not have to guess whether the measured window was sufficient for the claim being attempted. It must preserve lineage or version reference and timestamp so later systems can reconstruct which measured window actually existed at the relevant time.

Visible outcome is not automatically mature outcome. Early signal is not final outcome. Observation expired does not by itself mean observation mature. Window extension is not the same thing as restarted window where relevant. Mature outcome observed must remain distinguishable from early signal observed.

This is governed object meaning, not code schema. Shared measurement-window context must remain interpretable as the platform's formal record of what was actually measured, over what bounded interval, and under what maturity posture, rather than as a local metric extract or casual analytics slice.

## Observation-Horizon and Measurement-Window Grammar

The platform requires one shared cross-domain grammar for observation-horizon and measurement-window handling so that future domains inherit stable meanings for temporal maturity, provisional status, expiration, extension, restart, judgment readiness, learning readiness, and mismatch handling.

### Observation opened

Observation opened is the shared cross-domain condition in which a governed observation start point has occurred and the relevant horizon and measurement window have formally begun.

### Observation active

Observation active is the shared cross-domain condition in which the measurement window remains open and the relevant horizon is still running, whether or not meaningful signals are already visible.

### Observation provisional

Observation provisional is the shared cross-domain condition in which the platform has meaningful observed signals and may perform bounded interim review, but mature observation has not yet been established strongly enough for full downstream judgment.

### Observation mature

Observation mature is the shared cross-domain condition in which sufficient horizon has elapsed and the relevant end condition or maturity threshold has been satisfied strongly enough for the specific judgment being attempted.

### Observation expired

Observation expired is the shared cross-domain condition in which the active measurement window has reached its permitted end or has lapsed beyond active validity, without implying that the resulting history is automatically judgment-ready or learning-ready.

### Observation extended

Observation extended is the shared cross-domain condition in which the relevant measurement window has been deliberately widened or continued under preserved lineage because the original horizon, end condition, or use case remained insufficient.

### Observation restarted where relevant

Observation restarted where relevant is the shared cross-domain condition in which the relevant measurement process begins again from a new governed start point while the earlier window remains reconstructible rather than erased.

### Judgment permitted

Judgment permitted is the shared cross-domain condition in which the relevant observation is mature enough, linked enough, and comparable enough that serious post-mortem or attribution judgment may legitimately proceed.

### Judgment conditionally permitted

Judgment conditionally permitted is the shared cross-domain condition in which serious judgment may proceed only with explicitly preserved maturity qualifications, unresolved conditions, or comparability bounds.

### Judgment prohibited pending maturity

Judgment prohibited pending maturity is the shared cross-domain condition in which serious post-mortem or attribution judgment must not proceed because the relevant horizon remains too immature, too mismatched, or too weakly linked for the claim being attempted.

### Learning permitted

Learning permitted is the shared cross-domain condition in which observation is mature enough, judgment is strong enough, comparability is sound enough, and policy-learning maturity linkage is preserved strongly enough for governed learning reuse.

### Learning conditionally permitted

Learning conditionally permitted is the shared cross-domain condition in which learning reuse may proceed only within explicitly preserved scope, comparability, maturity, or update-threshold qualifications.

### Learning prohibited pending maturity

Learning prohibited pending maturity is the shared cross-domain condition in which policy-learning reuse must not proceed because the relevant observation, judgment, comparability, or scope posture remains too immature.

### Early signal observed

Early signal observed is the shared cross-domain condition in which a meaningful signal or visible outcome has appeared before the relevant horizon is mature enough to treat that signal as final outcome.

### Mature outcome observed

Mature outcome observed is the shared cross-domain condition in which the observed outcome has been recorded under a mature observation basis strong enough for the specific downstream interpretation being attempted.

### Insufficient horizon elapsed

Insufficient horizon elapsed is the shared cross-domain condition in which the relevant observation remains too early, too short, or too immature for the judgment, comparison, or learning claim being attempted.

### Horizon mismatch detected

Horizon mismatch detected is the shared cross-domain condition in which the horizon or window used for observation, comparison, judgment, or learning is materially inconsistent with the horizon needed for that use.

### Premature judgment state

Premature judgment state is the shared cross-domain condition in which strong judgment, attribution, comparison, or learning-reuse behavior has been attempted before sufficient horizon, mature linkage, or comparability was preserved.

These are shared cross-domain meanings. Domains may add narrower subtypes beneath them, but they may not silently replace, blur, or reinterpret them with incompatible local labels such as outcome seen means mature, closed means learnable, final enough means judgment-ready, expired means complete, or early trend means attributable. Shared observation-horizon and measurement-window grammar depends on these meanings remaining stable enough that execution observation, post-mortem review, cross-case comparison, and policy-learning reuse can all interpret downstream history coherently across domains.

## Minimum Shared Metadata for Observation-Horizon Context

Every governed observation-horizon context must carry minimum shared metadata.

### Observation-horizon context ID

This is the unique stable identifier for the observation-horizon context.

### Originating case ID

This is the stable reference to the decision case from which the observation-horizon context arises.

### Domain reference

This is the stable reference to the domain that owns the observation-horizon context.

### Decision scope reference

This is the governed reference to the scope or governed population for which the observation horizon is being asserted.

### Tenant or client scope reference where relevant

This is the governed reference to any tenant, client, banner, brand, store, or other scope boundary that qualifies the horizon.

### Related outcome object reference where relevant

This is the governed reference to the outcome object or related realized-outcome artifact to which the horizon is materially attached.

### Observation start point reference

This is the governed reference preserving the event, timestamp, trigger, or basis that opened the observation horizon.

### Observation end condition reference

This is the governed reference preserving the maturity threshold, closure condition, expiration condition, or other basis that legitimately closes the observation horizon.

### Intended observation horizon reference

This is the governed reference preserving the intended temporal horizon, horizon class, or maturity expectation over which the observation is meant to remain meaningful.

### Observation maturity reference

This is the governed reference stating whether the horizon remains early, provisional, mature, expired, extended, restarted, mismatched, or otherwise qualified.

### Post-mortem readiness linkage where relevant

This is the governed linkage preserving whether the relevant observation was not-yet-judgment-ready, judgment-ready, or only conditionally ready for post-mortem use.

### Policy-learning maturity linkage where relevant

This is the governed linkage preserving whether the relevant observation was not-yet-learning-ready, learning-ready, or only conditionally ready for governed policy-learning reuse.

### Extension or restart reference where relevant

This is the governed reference preserving any window extension or restarted window where relevant, including the basis for that change.

### Horizon-mismatch reference where relevant

This is the governed reference stating that horizon mismatch existed or was ruled out for the use being attempted.

### Lineage or version reference

This is the lineage and version reference needed to reconstruct the governing observation-horizon context later.

### Timestamp

This is the time at which the observation-horizon context was formed or fixed.

These are minimum shared metadata elements. Domains may extend them, but they may not omit or redefine them when the object is claimed as a governed platform observation-horizon context.

## Minimum Shared Metadata for Measurement-Window Context

Every governed measurement-window context must carry minimum shared metadata.

### Measurement-window context ID

This is the unique stable identifier for the measurement-window context.

### Originating case ID

This is the stable reference to the decision case from which the measurement-window context arises.

### Domain reference

This is the stable reference to the domain that owns the measurement-window context.

### Decision scope reference

This is the governed reference to the scope or governed population for which the measured window applies.

### Tenant or client scope reference where relevant

This is the governed reference to any tenant, client, banner, brand, store, or other scope boundary that qualifies the measured window.

### Related outcome object reference where relevant

This is the governed reference to the outcome object or related observed artifact being measured inside the window.

### Window-open reference

This is the governed reference preserving when and how the active measurement window opened.

### Window-close or expiration reference where relevant

This is the governed reference preserving when and how the active measurement window closed, expired, or otherwise ceased to remain active.

### Measurement status reference

This is the governed reference stating whether observation is opened, active, provisional, mature, expired, extended, restarted, or otherwise qualified.

### Early-signal reference where relevant

This is the governed reference preserving that early signal observed occurred without implying mature outcome.

### Mature-outcome reference where relevant

This is the governed reference preserving that mature outcome observed occurred under a mature observation basis.

### Observation-window comparability reference where relevant

This is the governed reference preserving whether the measured window is comparable, non-comparable, or only conditionally comparable to the other windows being used.

### Judgment-readiness reference where relevant

This is the governed reference preserving whether the measured window is not-yet-judgment-ready, judgment-ready, or only conditionally ready for serious judgment.

### Learning-readiness reference where relevant

This is the governed reference preserving whether the measured window is not-yet-learning-ready, learning-ready, or only conditionally ready for governed learning reuse.

### Extension or restart linkage where relevant

This is the governed linkage preserving any extension, expiration, or restarted window where relevant so temporal change remains reconstructible.

### Lineage or version reference

This is the lineage and version reference needed to reconstruct the governing measurement-window context later.

### Timestamp

This is the time at which the measurement-window context was formed or fixed.

These are minimum shared metadata elements. Domains may extend them, but they may not omit or redefine them when the object is claimed as a governed platform measurement-window context.

## Lineage Rules

Observation-horizon and measurement-window artifacts must preserve reconstructible lineage across the back half of the decision loop.

- Outcome objects must preserve outcome-maturity linkage strongly enough that later systems can tell whether a visible result was an early signal, a provisional observation, or a mature outcome observed under the relevant horizon.
- Post-mortem handling must preserve post-mortem readiness linkage strongly enough that later systems can tell whether judgment was permitted, judgment conditionally permitted, or judgment prohibited pending maturity at the time the judgment was formed.
- Policy-learning handling must preserve policy-learning maturity linkage strongly enough that later systems can tell whether learning was permitted, learning conditionally permitted, or learning prohibited pending maturity at the time the learning claim was attempted.
- Downstream horizons must remain explicit. If post-mortem review, comparative reporting, or policy-learning reuse depends on a longer, narrower, or otherwise different horizon than the original observation basis, that downstream horizon must remain reconstructible rather than assumed.
- Provisional observation and mature observation must remain distinguishable in lineage. Later mature outcome observed must not erase the earlier fact that serious review once relied on provisional history.
- Observation immaturity must survive review resolution, case disposition, closure, expiration, reopen, revisit, and reinstatement. A closed case may still have an immature observation horizon, and later systems must be able to see that rather than infer maturity from closure alone.
- Window extension and restarted window where relevant must remain traceable. Later systems must be able to reconstruct the original start point, the original end condition, the basis for extension or restart, and the relationship between the earlier and later windows.
- Horizon mismatch and premature judgment state must remain reconstructible. Later mature observation must not overwrite the earlier fact that a judgment, comparison, or learning claim was once made on a mismatched or immature horizon.
- Review, post-mortem, and policy-learning artifacts must remain able to distinguish horizon mismatch from recommendation weakness, commitment weakness, instruction weakness, execution weakness, and evidence weakness.
- Policy learning must not overlearn from mature-looking history whose maturity lineage is weak. Learning reuse requires preserved observation maturity, preserved post-mortem readiness, preserved comparability, preserved scope validity, and preserved admission discipline.

Observation-horizon context and measurement-window context therefore connect execution reality, outcome visibility, temporal maturity, post-mortem entitlement, comparison legitimacy, and policy-learning admissibility into one reconstructible chain. If that chain breaks, the platform can no longer tell whether a later judgment was timely, premature, comparable, or learnable.

## Domain Inheritance Rules

All admitted domains must inherit this shared observation-horizon and measurement-window grammar.

At minimum, every domain-local workflow contract, execution-observation design, outcome-object design, review-resolution design, post-mortem design, reopened handling, comparative reporting logic, and policy-learning reuse logic that depends on temporal maturity must align with the following rules. Visible outcome is not automatically mature outcome. Early signal is not final outcome. Post-mortem readiness is not the same thing as execution completion. Learning readiness is not the same thing as case closure. A closed case may still have an immature observation horizon. Observation maturity is not the same thing as confidence. Observation horizon is not the same thing as urgency. Horizon mismatch must remain distinguishable from recommendation weakness. Premature judgment must remain distinguishable from valid provisional review. Policy learning must not casually reuse immature observations as if they were mature evidence.

Domain-local contracts must therefore inherit this standard rather than inventing their own incompatible meanings for observation-horizon context, measurement-window context, observation start point, observation end condition, early observation, provisional observation, mature observation, expired observation window, judgment-ready observation, learning-ready observation, window extension, restarted window where relevant, horizon mismatch, or premature judgment state.

## Domain Extension Rules

Domains may extend this standard where their operating reality requires richer horizon classes, narrower maturity thresholds, more specific observation start points, more specific end conditions, stronger comparability tests, more detailed early-signal taxonomies, stronger extension controls, more explicit restart conditions, or tighter learning-readiness checks.

Valid domain extension may include narrower lag categories, more specific partial-maturity states, stronger domain-local expiry rules, more detailed maturity-by-outcome-type logic, richer post-closure observation handling, more explicit cross-case comparability classes, or stronger conditions before learning-ready observation may be claimed.

Domain extension is invalid when it does any of the following. Treats visible outcome as automatically mature outcome. Treats early signal as final outcome. Treats execution completion as automatic post-mortem readiness. Treats case closure as automatic learning readiness. Treats observation maturity as the same thing as confidence. Treats observation horizon as the same thing as urgency. Collapses horizon mismatch into recommendation weakness. Treats premature judgment as valid simply because some outcome was visible. Hides extension or restart history inside ordinary reporting logic. Allows policy learning to reuse immature observations as if they were mature evidence. Uses local labels to replace observation opened, observation provisional, observation mature, observation expired, judgment prohibited pending maturity, learning prohibited pending maturity, horizon mismatch detected, or premature judgment state.

Extension is allowed. Redefinition of shared meaning is not.

## Governance Linkage

This standard is directly governance-linked because the platform cannot claim disciplined post-decision learning if it does not preserve one stable meaning for observation maturity, measurement-window legitimacy, judgment readiness, learning readiness, and temporal mismatch.

The shared execution deviation and outcome object standard should treat this file as the controlling reference for observation-horizon context, measurement-window context, outcome-maturity linkage, and the rule that visible outcome is not automatically mature outcome. The shared post-mortem and attribution judgment standard should treat it as the controlling reference for post-mortem readiness linkage, judgment-ready observation, not-yet-judgment-ready observation, insufficient horizon elapsed, and the rule that post-mortem readiness is not the same thing as execution completion. The shared decision materiality, priority, and urgency standard should treat it as the controlling reference for the distinction between observation horizon and urgency horizon, and for the rule that observation horizon is not the same thing as urgency. The shared progression-gate and stage-transition standard should treat it as the controlling reference for the temporal maturity basis that distinguishes judgment-ready observation from learning-ready observation and for the rule that learning readiness is not the same thing as case closure. The shared review resolution and case disposition standard should treat it as the controlling reference for the rule that a closed case may still have an immature observation horizon and for the requirement that immaturity survive closure, expiration, and unresolved disposition. The shared reopen, revisit, and reinstatement standard should treat it as the controlling reference for extension lineage, restarted window where relevant, qualified finality of observation, and preservation of immature or provisional observation through later re-entry. The shared recommendation, commitment, and action-instruction boundary standard should treat it as the controlling reference for the later observation horizon that governs whether downstream outcome judgment may be treated as mature and for the rule that horizon mismatch must remain distinguishable from recommendation weakness. The shared state snapshot and local operating context standard should treat it as the controlling reference for post-decision observation horizon, while continuing to own decision-time timing state and state horizon. The shared uncertainty and confidence context standard should treat it as the controlling reference for the rule that observation maturity is not the same thing as confidence and that temporal sufficiency does not by itself prove evidential strength. The shared evidence bundle and signal provenance standard should treat it as the controlling reference for early signal observed, mature outcome observed, and the rule that provenance-rich evidence may still remain immature if the horizon is too short. The policy-learning evidence admission and update-threshold standard should treat it as the controlling reference for learning-ready observation, not-yet-learning-ready observation, policy-learning maturity linkage, observation-window comparability, and the rule that policy learning must not casually reuse immature observations as if they were mature evidence. Review and approval should align with the platform governance roles and approval authority matrix, especially where shared workflow behavior, post-mortem entitlement, comparative reporting, cross-domain comparability, or policy-learning reuse behavior are affected.

Changes to shared observation meaning, measurement-window grammar, maturity thresholds, extension or restart semantics, mismatch handling, post-mortem readiness linkage, or learning-readiness linkage are consequential platform changes. They must go through formal governance rather than domain-local adjustment.

## Failure Modes in Observation-Horizon and Measurement-Window Design

Weak observation-horizon and measurement-window design creates direct platform risk.

### Visible outcome treated as mature outcome

The platform preserves that some result was visible, but local workflow behavior, reporting language, or post-mortem language causes that result to be treated as if mature observation had already been achieved.

### Early signal mistaken for final outcome

The platform records early movement, early uplift, early decline, or early execution response as though the relevant horizon had already closed, even though the observed signal remains provisional.

### Post-mortem issued before sufficient horizon elapsed

The platform presents serious attribution or post-mortem judgment even though insufficient horizon elapsed, outcome-maturity linkage remains weak, or the active window remains provisional.

### Closed case treated as learning-ready despite immature horizon

The platform records that the case closed, resolved, expired, or otherwise dispositioned, and later systems infer that the observation was therefore mature enough for policy-learning reuse even though learning-readiness linkage was never earned.

### Observation-window comparability inferred where mismatch actually exists

The platform compares cases observed over materially different windows or different maturity bases as though those observations belonged in one coherent comparative set.

### Window extension hidden from lineage

The platform later treats an extended window as if it were the original window, making it impossible to tell whether the original end condition was insufficient for the judgment or learning claim being attempted.

### Restarted window erasing earlier provisional history

The platform records that observation restarted, but later systems can no longer reconstruct the earlier start point, the earlier provisional state, or why restart rather than extension became necessary.

### Horizon mismatch collapsed into recommendation weakness

The platform observes weak or surprising later outcomes and blames recommendation quality even though the real defect was that the horizon used for observation, comparison, or judgment was mismatched to the claim being made.

### Premature judgment normalized as review discipline

The platform records a provisional review or urgent review path, but later systems remember that path as if it were a fully entitled mature judgment rather than a bounded provisional view or a premature judgment state.

### Policy learning overreacting to immature observations

The platform begins adapting future behavior from visible outcomes, early signals, or short-horizon results whose maturity, comparability, attribution quality, or scope validity remain too weak for serious learning.

These failures are not minor reporting defects. They are ways the platform loses temporal discipline, weakens post-mortem legitimacy, and begins learning from history whose maturity was never actually governed.

## Non-Negotiables

1. Visible outcome is not automatically mature outcome.
2. Early signal is not final outcome.
3. Post-mortem readiness is not the same thing as execution completion.
4. Learning readiness is not the same thing as case closure.
5. A closed case may still have an immature observation horizon.
6. Observation maturity is not the same thing as confidence.
7. Observation horizon is not the same thing as urgency.
8. Horizon mismatch must remain distinguishable from recommendation weakness.
9. Premature judgment must remain distinguishable from valid provisional review.
10. Policy learning must not casually reuse immature observations as if they were mature evidence.

## Closing Statement

This standard protects the platform from collapsing visible outcomes into mature evidence by local convenience.

That protection matters because a serious decision platform must preserve not only what later happened, what later review concluded, and what policy later learned, but also when observation actually opened, when it remained provisional, when sufficient horizon truly elapsed, when the measured window expired, when extension or restart changed the temporal basis, when serious judgment was or was not yet entitled, when a closed case remained immature, and when policy learning had not yet earned the right to treat observed history as mature evidence. Future domains need one shared observation-horizon and measurement-window grammar robust enough that domains can use very different commercial lags, decay patterns, and outcome cycles while still preserving one stable meaning for early observation, mature observation, judgment readiness, learning readiness, horizon mismatch, and premature judgment state across the platform.