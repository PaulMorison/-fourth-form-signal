# Shared Decision Materiality, Priority, and Urgency Standard for the Fourth Form Retail Decision Intelligence Platform

## Purpose of This Document

This document defines the shared platform standard for decision materiality, priority, and urgency across all current and future domains.

It exists because the platform cannot remain one governed decision system if domains use terms such as important, urgent, critical, severe, priority, defer, timing pressure, review speed, escalation speed, or safe to wait without one shared meaning for how consequential a case is, how quickly it must move, how much delay is acceptable, when review must be urgent even if direct action is not justified, and how later systems should judge whether the platform moved with the right timing discipline.

Without a shared standard, the platform will drift into domain-specific timing semantics, materiality confused with urgency, priority confused with recommendation, severity used as a loose synonym for everything that feels uncomfortable, waiting used casually instead of governed deferment, review queues that preserve local habit instead of shared timing discipline, escalation records that preserve that a case moved upward but not how urgently it needed to move, post-mortem review that cannot tell whether the platform moved fast enough or delayed too long, and policy-learning behavior that begins adapting from noisy urgency history rather than governed timing evidence.

This document is therefore a control document for shared decision materiality, priority, and urgency structure.

It defines the core concepts, shared object meanings, shared grammar, minimum metadata requirements, lineage rules, inheritance rules, extension rules, and governance linkage that all domains must follow when preserving how consequential a case is, how it should be ordered relative to other governed work, how much timing pressure applies, and whether action, review, escalation, or revisit may responsibly wait.

It is the canonical shared decision materiality, priority, and urgency standard for the platform. Future domain workflow contracts, recommendation records, escalation and abstention handling, approval and override review, execution comparison, post-mortem judgment, and policy-learning reuse must align with it unless a formal decision record explicitly revises it.

## Role of This Document in the Platform

This document governs the shared significance-and-timing grammar that sits between formed decision cases and the later layers that recommend, wait, escalate, abstain, approve, execute, judge, and learn.

The shared decision intake and case formation standard defines how a governed decision episode legitimately begins. The shared state snapshot and local operating context standard defines what local reality looked like when the case was handled. The shared evidence bundle and signal provenance standard defines what materially counted as evidence and where it came from. The shared uncertainty and confidence context standard defines what weakened clarity and confidence. The shared constraint and feasibility context standard defines what bounded valid action. The shared action-path and candidate action set standard defines the serious paths that were available. The shared decision rationale and explanation trace standard defines how those conditions were interpreted into a disciplined thesis. The shared recommendation record standard defines which path became preferred. The shared escalation and abstention standard defines governed non-action outcomes where stronger direct action was not justified. The shared approval and override standard defines how human intervention may later preserve, qualify, or replace the original platform position. The shared execution deviation and outcome standard and the shared post-mortem standard define how realized reality is later compared with the original position and later judged. The policy-learning evidence admission and update-threshold standard defines when timing history and case-importance history are strong enough to influence future behavior. This document governs the materiality context, priority context, and urgency context that connect those layers by preserving how consequential a case was, how it should have been ordered, how much timing pressure existed, what delay was tolerable, and whether action, review, escalation, or revisit could responsibly wait.

In practical terms, this document governs what materiality context is, what priority context is, what urgency context is, how they differ from confidence, uncertainty, recommendation, and feasibility, what shared grammar all domains must use, what minimum metadata must be preserved, and how later decision-loop stages may reuse timing and significance history without losing meaning.

This document therefore governs importance and timing discipline as part of platform coherence.

## Core Thesis

In the Fourth Form platform, materiality context, priority context, and urgency context must remain first-class governed decision-support context whose significance, ordering force, timing pressure, urgency horizon, deferral tolerance, safe-to-wait conditions, unsafe-to-wait conditions, and lineage remain explicit enough that the platform can distinguish what matters most from what must move fastest, can justify action now versus wait without collapsing that question into confidence or feasibility, can preserve urgent review or escalation even where direct action is not justified, and can later judge whether it handled timing discipline responsibly.

That is the core thesis.

Materiality, priority, and urgency are governed decision-support context, not UI labels. Materiality is not the same thing as urgency. Priority is not the same thing as urgency. Materiality is not the same thing as confidence. Urgency is not the same thing as uncertainty. Priority is not the same thing as recommendation. High urgency does not automatically justify high confidence. Weak evidence may still produce high review urgency. Safe-to-wait is a governed condition, not casual delay. Unsafe-to-wait must remain explicit when delay materially increases downside. Materiality, priority, and urgency must remain distinct from action feasibility and constraint validity.

## What This Standard Is and Is Not

This standard is the shared platform rule for how the system records, links, preserves, and reuses governed decision materiality, priority, and urgency.

It is not a product prioritisation memo. It is not a backlog-ranking guide. It is not a user-interface scoring convention. It is not an SLA document. It is not a recommendation record by another name. It is not a confidence label. It is not a substitute for constraint and feasibility context. It is not permission for domains to reduce timing discipline to thin urgency badges, severity colors, queue shortcuts, or operator habit. It is not permission for domains to treat high materiality as automatic action-now instruction. It is not permission to treat safe-to-wait as informal procrastination. It is not a way to blur urgent review, urgent escalation, urgent action, and urgent revisit into one undifferentiated pressure label.

A real shared decision-materiality, priority, and urgency standard means the platform can answer the following questions for any material decision episode: how consequential the case was, how consequential direct action was, how consequential review was, which dimensions of commercial, operational, or governance materiality were active, how the case should have been ordered relative to other governed work, how much timing pressure applied, what urgency horizon governed the case, how much deferral was tolerable, whether the case was safe to wait on or unsafe to wait on, whether urgency applied to direct action, review, escalation, approval, or abstention revisit, how later execution and post-mortem should judge timing discipline, and whether the preserved history is strong enough for learning reuse.

## Why a Shared Decision Materiality, Priority, and Urgency Standard Is Necessary

Domains must not define materiality, priority, and urgency independently because the platform cannot preserve disciplined decision timing if one domain uses priority to mean business importance, another uses it to mean queue order, another uses urgency to mean confidence, another uses severity to mean commercial downside, and another treats waiting as an informal pause with no governed deferral tolerance.

If materiality, priority, and urgency grammar is left local, several failures follow. One domain preserves high materiality but not whether the case was safe to wait. One domain preserves urgency for direct action but not review urgency. One domain escalates a case without preserving whether the escalation itself was urgent. One domain treats abstention as low urgency even when revisit must occur quickly. One domain delays because evidence is weak when the correct disciplined response should have been urgent review. One domain preserves only that a recommendation was deferred, while another preserves explicit timing discipline. Post-mortem then cannot tell whether the platform moved too fast, too slowly, or in the right order, and policy-learning begins overreacting to noisy urgency history that was never governed strongly enough to justify reuse.

The platform therefore needs one shared standard so that future domains can extend one governed materiality, priority, and urgency grammar rather than inventing their own local meanings for how important a case is, how quickly it must move, and how much delay is acceptable.

## Core Concepts

The platform uses the following core concepts.

### Materiality context

Materiality context is the governed object context that preserves how consequential a case, action path, review path, or non-action outcome is for the relevant decision scope.

### Priority context

Priority context is the governed object context that preserves how a case, action path, review path, or revisit path should be ordered relative to other governed work within the relevant scope and horizon.

### Urgency context

Urgency context is the governed object context that preserves how quickly a case, action path, review path, escalation path, approval step, or abstention revisit must move before delay becomes materially harmful.

### Decision materiality

Decision materiality is the governed statement of how consequential it is to handle the case correctly at all, regardless of whether the disciplined next step is act now, wait, escalate, abstain, or review.

### Action materiality

Action materiality is the governed statement of how consequential the direct action decision itself is, including the downside or upside attached to acting, withholding, or mis-timing the action path.

### Review materiality

Review materiality is the governed statement of how consequential timely review, challenge, or authority involvement is, even when direct action is not yet justified.

### Commercial materiality

Commercial materiality is the governed statement of how materially the case may affect commercial value, customer outcome, proposition quality, margin exposure, or other business consequence.

### Operational materiality

Operational materiality is the governed statement of how materially the case may affect execution quality, delivery readiness, stock exposure, operating continuity, or other execution-relevant consequence.

### Governance materiality

Governance materiality is the governed statement of how materially the case may affect policy compliance, authority boundaries, reporting safety, controlled scope, or other formal governance obligations.

### Severity

Severity is the governed statement of how serious the downside becomes if the case is mishandled, delayed inappropriately, or routed through the wrong path. Severity may materially influence materiality and urgency, but it is not identical to either.

### Timing pressure

Timing pressure is the governed condition in which delay itself changes the decision quality, downside exposure, operating validity, review legitimacy, or attainable value of the case.

### Timing urgency

Timing urgency is the governed statement of how much speed pressure applies to the case or handling path overall.

### Action urgency

Action urgency is the governed statement of how quickly direct action must move if direct action is the legitimate next step.

### Review urgency

Review urgency is the governed statement of how quickly review, challenge, or accountable human handling must move, including cases where direct action is not yet justified.

### Escalation urgency

Escalation urgency is the governed statement of how quickly a case must move into escalation or higher-authority handling once escalation is the disciplined outcome.

### Urgency horizon

Urgency horizon is the governed time horizon over which the urgency position is valid before delay materially degrades outcome quality, review legitimacy, or action value.

### Deferral tolerance

Deferral tolerance is the governed statement of how much delay the case can absorb before timing quality becomes materially weaker.

### Safe-to-wait condition

Safe-to-wait condition is the governed condition in which bounded delay remains legitimate because waiting is unlikely to materially increase downside and is likely to improve clarity, review quality, feasibility, or action quality.

### Unsafe-to-wait condition

Unsafe-to-wait condition is the governed condition in which additional delay materially increases downside, closes a relevant decision window, weakens review legitimacy, or degrades the quality of the attainable outcome.

### Priority position

Priority position is the governed statement of how strongly the case or handling path should rise relative to other governed work competing for attention inside the same relevant scope.

### Materiality qualification

Materiality qualification is the governed statement of how the materiality position is bounded, narrowed, conditional, scope-limited, or otherwise qualified.

### Priority qualification

Priority qualification is the governed statement of how the priority position is bounded by scope, readiness, queue context, authority path, or other conditions that keep priority from being treated as absolute.

### Urgency qualification

Urgency qualification is the governed statement of how the urgency position is bounded, contested, review-specific, action-specific, or otherwise qualified.

### Action-now versus wait justification

Action-now versus wait justification is the governed statement of why immediate action, bounded waiting, urgent review, urgent escalation, or urgent revisit was the disciplined timing posture under the current case conditions.

### Materiality lineage

Materiality lineage is the reconstructible chain connecting the decision case, its materiality context, the later recommendation or non-action outcome shaped by that context, and the later execution, post-mortem, and policy-learning artifacts that reuse it.

### Priority lineage

Priority lineage is the reconstructible chain connecting the decision case, its priority context, the ordering of recommendation or review work that followed, and the later records that judge whether that ordering was sound.

### Urgency lineage

Urgency lineage is the reconstructible chain connecting the decision case, its urgency context, the later action, review, escalation, abstention, approval, execution, post-mortem, and learning artifacts that depended on that timing posture.

### Recommendation-priority linkage

Recommendation-priority linkage is the explicit connection between priority context and the recommendation record or recommendation preparation path whose order of handling it shaped.

### Escalation-urgency linkage

Escalation-urgency linkage is the explicit connection between urgency context and an escalation record stating how quickly escalation had to move once escalation became the disciplined outcome.

### Abstention-urgency linkage

Abstention-urgency linkage is the explicit connection between urgency context and an abstention record stating how quickly the abstained case must be revisited or reviewed even though direct action was withheld.

### Approval-urgency linkage

Approval-urgency linkage is the explicit connection between urgency context and an approval or review step whose speed materially affected whether the case was handled responsibly.

### Execution-timing comparison

Execution-timing comparison is the governed comparison between the preserved timing posture of the original decision and the actual timing, deferral, delay, or acceleration later observed in execution.

### Post-mortem timing review

Post-mortem timing review is the governed later review of whether the platform's original timing discipline, deferral tolerance, safe-to-wait judgment, and unsafe-to-wait judgment were appropriate relative to realized conditions and outcomes.

### Policy-learning reuse

Policy-learning reuse is the governed reuse of materiality, priority, and urgency history for future policy improvement only when lineage, scope validity, attribution quality, and evidence discipline remain strong enough to justify that reuse.

## Shared Materiality Context

At platform level, shared materiality context is the formal governed context that preserves how consequential a decision case, a direct action path, a review path, or a non-action outcome is for the relevant decision scope.

It exists because the platform must preserve more than that a case felt important. It must preserve decision materiality, action materiality, review materiality, the commercial materiality, operational materiality, and governance materiality that shaped that position, any severity that materially increased consequence, and any materiality qualification that kept the case from being treated as universally or timelessly critical.

Shared materiality context must preserve, conceptually, all of the following. It must preserve a materiality context ID so the significance position has stable identity. It must preserve the originating case ID and a domain reference so ownership remains explicit. It must preserve the decision scope reference and the tenant or client scope reference where relevant so materiality does not lose its governed population. It must preserve materiality position and materiality qualification so later systems can tell not only how consequential the case was judged to be, but how that judgment was bounded. It must preserve decision-materiality, action-materiality, and review-materiality references where relevant so later systems can distinguish the significance of deciding correctly from the significance of acting immediately or reviewing quickly. It must preserve commercial-materiality, operational-materiality, and governance-materiality linkage where those dimensions were materially active. It must preserve severity reference where relevant so serious downside is not left implicit. It must preserve related recommendation, escalation, or abstention linkage where materiality shaped the downstream path. It must preserve lineage or version reference and timestamp so later systems can reconstruct which governed materiality position existed at decision time.

This is governed object meaning, not code schema. Shared materiality context must remain interpretable as significance structure inside the decision basis rather than as a severity badge, client-facing label, or operator intuition.

## Shared Priority Context

At platform level, shared priority context is the formal governed context that preserves how strongly a case, action path, review path, or revisit path should rise relative to other governed work inside the relevant scope and horizon.

It exists because the platform must preserve more than that something was important or urgent. It must preserve how the case should have been ordered relative to other active work, what qualification bounded that ordering, whether recommendation work, review work, or revisit work should move first, and how that ordering related to but remained distinct from materiality and urgency.

Shared priority context must preserve, conceptually, all of the following. It must preserve a priority context ID so the ordering position has stable identity. It must preserve the originating case ID and a domain reference so ownership remains explicit. It must preserve the decision scope reference and the tenant or client scope reference where relevant so priority does not lose its governed population. It must preserve the priority position and priority qualification so later systems can tell not only how high in order the case should have risen, but what bounded that ordering. It must preserve related materiality and urgency linkage where relevant because priority may depend on both without collapsing into either. It must preserve related action-path linkage, recommendation-priority linkage, and review linkage where relevant so later systems can reconstruct what work the priority position actually governed. It must preserve lineage or version reference and timestamp so later systems can reconstruct which governed priority position existed when work ordering mattered.

This is governed object meaning, not code schema. Shared priority context must remain interpretable as governed ordering discipline rather than as product backlog rank, ad hoc queue convenience, or a thin UI ordering label.

## Shared Urgency Context

At platform level, shared urgency context is the formal governed context that preserves how quickly a case, action path, review path, escalation path, approval step, or abstention revisit must move before delay becomes materially harmful.

It exists because the platform must preserve more than that a case moved quickly or slowly. It must preserve timing urgency, action urgency, review urgency, escalation urgency, timing pressure, urgency horizon, deferral tolerance, safe-to-wait condition, unsafe-to-wait condition, urgency qualification, and action-now versus wait justification strongly enough that later systems can reconstruct why immediate action was required, why waiting was legitimate, why review had to be fast even when direct action was not justified, or why escalation had to move urgently despite weak recommendation confidence.

Shared urgency context must preserve, conceptually, all of the following. It must preserve an urgency context ID so the timing position has stable identity. It must preserve the originating case ID and a domain reference so ownership remains explicit. It must preserve the decision scope reference and the tenant or client scope reference where relevant so urgency does not lose its governed population. It must preserve urgency position, urgency qualification, timing-pressure reference, urgency-horizon reference, and deferral-tolerance reference so the timing posture remains inspectable rather than implied. It must preserve safe-to-wait or unsafe-to-wait reference where relevant so the platform does not later remember casual waiting as governed waiting or casual urgency as disciplined urgency. It must preserve action urgency, review urgency, escalation urgency, and approval-urgency linkage where relevant so later systems can tell what exactly needed to move fast. It must preserve action-now versus wait justification so later systems can reconstruct why immediate action, bounded delay, urgent review, or urgent revisit was the disciplined timing path. It must preserve recommendation, escalation, abstention, and approval linkage where relevant so urgency remains connected to the downstream records it shaped. It must preserve lineage or version reference and timestamp so later systems can reconstruct which governed urgency position existed at decision time.

Urgency can apply to review even when direct action is not justified. Escalation may be urgent even when recommendation confidence is weak. Abstention may still carry urgency for revisit or review. High urgency does not automatically justify high confidence, and weak evidence may still produce high review urgency where delayed review would be unsafe.

This is governed object meaning, not code schema. Shared urgency context must remain interpretable as timing discipline inside the decision basis rather than as an emotional alert state, UI badge, or implementation-side queue marker.

## Materiality, Priority, and Urgency Grammar

The platform requires one shared cross-domain grammar for materiality, priority, and urgency so that future domains inherit stable meanings for consequence, ordering, and timing pressure.

### High materiality

High materiality is the shared cross-domain materiality position in which the case, action path, review path, or non-action outcome carries sufficiently large commercial, operational, or governance consequence that weak handling would materially matter.

### Medium materiality

Medium materiality is the shared cross-domain materiality position in which the case is materially consequential, but the consequence is more bounded in scope, reversibility, or downside than a high-materiality case.

### Low materiality

Low materiality is the shared cross-domain materiality position in which the case remains governed and real but the consequence of weak handling is comparatively bounded.

### Qualified materiality

Qualified materiality is the shared cross-domain condition in which the materiality position is real but explicitly bounded by scope, reversibility, observation horizon, or another preserved qualification.

### High priority

High priority is the shared cross-domain priority position in which the case or handling path should rise ahead of most competing governed work in the same relevant scope because delay in ordering would materially weaken responsible handling.

### Medium priority

Medium priority is the shared cross-domain priority position in which the case should be handled seriously but does not outrank the most time-sensitive or consequential competing work in the same relevant scope.

### Low priority

Low priority is the shared cross-domain priority position in which the case remains legitimate governed work but may responsibly remain behind more pressing governed work within the same relevant scope.

### Timing urgency

Timing urgency is the shared cross-domain category for how much speed pressure applies to the case or handling path overall.

### Action urgency

Action urgency is the shared cross-domain category for how much speed pressure applies to direct action where direct action is legitimately under consideration.

### Review urgency

Review urgency is the shared cross-domain category for how much speed pressure applies to review, challenge, or accountable human handling, including cases where the disciplined path is not immediate direct action.

### Escalation urgency

Escalation urgency is the shared cross-domain category for how much speed pressure applies to moving the case into escalation or higher-authority handling once escalation is the disciplined outcome.

### Urgent now

Urgent now is the shared cross-domain urgency position in which further delay is materially unsafe because the downside of waiting, the closure of the decision window, or the degradation of attainable outcome quality is already active.

### Urgent soon

Urgent soon is the shared cross-domain urgency position in which a short bounded delay remains possible, but only within an explicit urgency horizon after which the case becomes materially less safe or less valuable to handle.

### Safe to defer

Safe to defer is the shared cross-domain urgency position in which bounded delay remains legitimate under an explicit urgency horizon and deferral tolerance.

### Safe-to-wait

Safe-to-wait is the shared cross-domain governed condition in which waiting is a legitimate timing choice because the case can absorb bounded delay without material downside increase and because delay is expected to improve clarity, review quality, feasibility understanding, or action quality.

### Unsafe-to-wait

Unsafe-to-wait is the shared cross-domain governed condition in which delay materially increases downside, weakens review legitimacy, closes an action window, or degrades attainable outcome quality.

### Qualified urgency

Qualified urgency is the shared cross-domain condition in which urgency is real but explicitly bounded, path-specific, review-specific, escalation-specific, or otherwise qualified rather than treated as universal immediate-action pressure.

These are shared cross-domain meanings. Domains may add narrower subtypes beneath them, but they may not silently replace, blur, or reinterpret them with incompatible local-only semantics. Shared materiality, priority, and urgency grammar depends on these meanings remaining stable enough that recommendation, waiting, escalation, abstention, approval review, execution comparison, post-mortem judgment, and policy-learning reuse can interpret timing and significance history coherently across domains.

## Minimum Shared Metadata for Materiality Context

Every governed materiality context must carry minimum shared metadata.

### Materiality context ID

This is the unique stable identifier for the materiality context.

### Originating case ID

This is the stable reference to the decision case from which the materiality context arises.

### Domain reference

This is the stable reference to the domain that owns the materiality context.

### Decision scope reference

This is the explicit decision scope governing the materiality context.

### Tenant or client scope reference where relevant

This is the tenant boundary and client-population context under which the materiality context is valid where that concept applies.

### Materiality position reference

This is the governed reference stating the materiality position of the case or handling path.

### Materiality qualification reference

This is the governed reference describing how the materiality position is bounded, narrowed, or otherwise qualified.

### Decision-materiality reference where relevant

This is the governed reference preserving how consequential correct handling of the case was overall.

### Action-materiality reference where relevant

This is the governed reference preserving how consequential the direct action decision was.

### Review-materiality reference where relevant

This is the governed reference preserving how consequential timely review or authority involvement was.

### Commercial-materiality linkage where relevant

This is the governed linkage preserving the commercially material dimensions of the case.

### Operational-materiality linkage where relevant

This is the governed linkage preserving the operationally material dimensions of the case.

### Governance-materiality linkage where relevant

This is the governed linkage preserving the governance-sensitive dimensions of the case.

### Related recommendation, escalation, or abstention linkage where relevant

This is the governed linkage connecting materiality context to the downstream recommendation, escalation, or abstention objects it materially shaped.

### Lineage or version reference

This is the lineage and version reference needed to reconstruct the governing context of the materiality position later.

### Timestamp

This is the time at which the materiality context was formed or fixed.

These are minimum shared metadata elements. Domains may extend them, but they may not omit or redefine them when the object is claimed as a governed platform materiality context.

## Minimum Shared Metadata for Priority Context

Every governed priority context must carry minimum shared metadata.

### Priority context ID

This is the unique stable identifier for the priority context.

### Originating case ID

This is the stable reference to the decision case from which the priority context arises.

### Domain reference

This is the stable reference to the domain that owns the priority context.

### Decision scope reference

This is the explicit decision scope governing the priority context.

### Tenant or client scope reference where relevant

This is the tenant boundary and client-population context under which the priority context is valid where that concept applies.

### Priority position reference

This is the governed reference stating the ordering position of the case or handling path.

### Priority qualification reference

This is the governed reference describing how the priority position is bounded, conditioned, or otherwise qualified.

### Related action-path linkage where relevant

This is the governed linkage connecting the priority context to the action paths whose ordering it shaped.

### Related recommendation linkage where relevant

This is the governed linkage connecting the priority context to recommendation preparation or recommendation handling where priority materially shaped order.

### Related review linkage where relevant

This is the governed linkage connecting the priority context to review or approval handling where priority materially shaped order.

### Lineage or version reference

This is the lineage and version reference needed to reconstruct the governing context of the priority position later.

### Timestamp

This is the time at which the priority context was formed or fixed.

These are minimum shared metadata elements. Domains may extend them, but they may not omit or redefine them when the object is claimed as a governed platform priority context.

## Minimum Shared Metadata for Urgency Context

Every governed urgency context must carry minimum shared metadata.

### Urgency context ID

This is the unique stable identifier for the urgency context.

### Originating case ID

This is the stable reference to the decision case from which the urgency context arises.

### Domain reference

This is the stable reference to the domain that owns the urgency context.

### Decision scope reference

This is the explicit decision scope governing the urgency context.

### Tenant or client scope reference where relevant

This is the tenant boundary and client-population context under which the urgency context is valid where that concept applies.

### Urgency position reference

This is the governed reference stating the urgency position of the case or handling path.

### Urgency qualification reference

This is the governed reference describing how the urgency position is bounded, path-specific, or otherwise qualified.

### Urgency horizon reference

This is the governed reference preserving the time horizon over which the urgency position remains valid.

### Deferral tolerance reference

This is the governed reference preserving how much delay the case can absorb before timing quality degrades materially.

### Safe-to-wait or unsafe-to-wait reference where relevant

This is the governed reference preserving whether waiting remained legitimate or materially unsafe.

### Recommendation, escalation, abstention, or approval linkage where relevant

This is the governed linkage connecting urgency context to the downstream recommendation, escalation, abstention, or approval objects it materially shaped.

### Lineage or version reference

This is the lineage and version reference needed to reconstruct the governing context of the urgency position later.

### Timestamp

This is the time at which the urgency context was formed or fixed.

These are minimum shared metadata elements. Domains may extend them, but they may not omit or redefine them when the object is claimed as a governed platform urgency context.

## Lineage Rules

Decision cases may carry materiality context, priority context, and urgency context directly because significance and timing discipline are part of the decision basis rather than later commentary.

The following lineage rules apply.

- Materiality lineage must preserve how decision materiality, action materiality, review materiality, and any commercial, operational, or governance materiality shaped later recommendation, escalation, abstention, approval, execution comparison, post-mortem review, and learning reuse.
- Priority lineage must preserve how the case or handling path was ordered relative to other governed work and whether that ordering shaped recommendation preparation, review progression, or revisit progression.
- Urgency lineage must preserve how timing urgency, action urgency, review urgency, escalation urgency, urgency horizon, deferral tolerance, and safe-to-wait or unsafe-to-wait posture shaped later handling.
- Recommendation records must preserve recommendation-priority linkage and any related action-now versus wait justification where priority and urgency materially shaped the recommendation path.
- Escalation records must preserve escalation-urgency linkage so later systems can tell not only that escalation occurred but how quickly escalation needed to move once it became the disciplined outcome.
- Abstention records must preserve abstention-urgency linkage so later systems can tell not only that direct action was withheld but how quickly the case needed review or revisit afterward.
- Approval records must preserve approval-urgency linkage where approval timing materially affected whether the case was handled responsibly.
- Execution deviation and outcome objects must preserve execution-timing comparison so later systems can compare decision-time timing posture with realized delay, acceleration, drift, or handling speed.
- Post-mortem objects must preserve post-mortem timing review so later systems can judge whether the platform moved too fast, too slowly, or with appropriate timing discipline relative to the case conditions and realized outcomes.
- Decision memory objects must preserve materiality, priority, and urgency history strongly enough that later retrieval, explanation, case comparison, and learning review can reconstruct not only what the platform did, but how consequential and time-pressured the case was judged to be.

Policy learning may reuse materiality, priority, and urgency history only with preserved lineage and evidence discipline. Timing history must not be treated as reusable policy signal merely because many cases carried urgent language, because a domain culture tends to escalate quickly, or because a small number of memorable cases later appeared time-sensitive in hindsight. Reuse must preserve linkage to case, state, evidence, rationale, recommendation or non-action outcome, approval path where relevant, execution reality, post-mortem timing review, and valid learning scope so the platform does not overlearn from noisy urgency history or from local priority habits that were never justified strongly enough to govern future behavior.

Materiality lineage, priority lineage, and urgency lineage therefore connect decision conditions, ordering discipline, timing posture, downstream action or non-action handling, realized execution timing, later attribution, and possible policy-learning reuse into one reconstructible chain. If that chain breaks, later systems can no longer tell whether the platform handled the case with the right importance and timing discipline or merely remembers that something happened quickly or slowly.

## Domain Inheritance Rules

All admitted domains must inherit this shared materiality, priority, and urgency grammar.

At minimum, every domain-local workflow contract, recommendation design, escalation and abstention handling, approval review flow, execution comparison design, post-mortem design, and policy-learning reuse logic that depends on case significance or timing discipline must align with the following rules. Materiality context, priority context, and urgency context are first-class governed decision-support context, not UI labels. Materiality is not urgency. Priority is not urgency. Materiality is not confidence. Urgency is not uncertainty. Priority is not recommendation. High urgency does not automatically justify high confidence. Weak evidence may still produce high review urgency. Safe-to-wait is a governed condition rather than casual delay. Unsafe-to-wait must remain explicit when delay materially increases downside. Materiality, priority, and urgency must remain distinct from action feasibility and constraint validity.

Urgency can apply to review even when direct action is not justified. Escalation may be urgent even when recommendation confidence is weak. Abstention may still carry urgency for revisit or review. Timing discipline must be reviewable in post-mortem. Policy learning must not casually reuse urgency history without lineage and evidence discipline.

Domain-local workflow contracts must therefore inherit this standard rather than inventing their own incompatible meanings for materiality, priority, urgency, severity, deferral tolerance, safe-to-wait, or action-now versus wait justification.

## Domain Extension Rules

Domains may extend this standard where their operating reality requires richer materiality dimensions, narrower priority classes, more specific urgency horizons, stronger deferral-tolerance rules, more precise review-urgency categories, or more detailed severity handling.

Valid domain extension may include narrower commercial or operational materiality subtypes, more specific review-priority or escalation-priority handling, more precise urgency-horizon classes, stronger override-review timing rules, more detailed timing-pressure markers, or more specific action-now versus wait justification structure.

Domain extension is invalid when it does any of the following. Collapses materiality, priority, and urgency into one undifferentiated score. Treats high materiality as automatic immediate action. Treats urgency as a substitute for confidence. Treats priority as a substitute for recommendation. Treats weak evidence as reason to ignore urgent review or escalation need. Replaces safe-to-wait discipline with casual backlog delay. Replaces urgency context with untracked UI badges or operator urgency notes. Preserves recommendation or non-action history without timing discipline strong enough for post-mortem review. Reuses urgency history for policy learning without preserved lineage, attribution quality, and evidence discipline. Uses domain-local convenience to rewrite the shared meanings of materiality, priority, urgency, deferral tolerance, safe-to-wait, unsafe-to-wait, or timing review.

Extension is allowed. Redefinition of shared meaning is not.

## Governance Linkage

This standard is directly governance-linked because the platform cannot claim disciplined decision timing if it does not preserve one stable meaning for consequence, ordering, and urgency.

The shared recommendation record standard should treat this file as the controlling reference for action-now versus wait justification and recommendation-priority linkage. The shared escalation and abstention standard should treat it as the controlling reference for escalation-urgency linkage, abstention-urgency linkage, revisit urgency, and review urgency where non-action was the disciplined path. The shared approval and override standard should treat it as the controlling reference for approval-urgency linkage where review timing materially shaped the episode. The shared execution deviation and outcome standard and the shared post-mortem standard should treat it as the controlling reference for execution-timing comparison and post-mortem timing review. The policy-learning evidence admission and update-threshold standard should treat it as the controlling reference for when materiality, priority, and urgency history are strong enough to count as disciplined learning input rather than noisy timing narrative.

Changes to shared materiality meaning, priority grammar, urgency grammar, urgency-horizon expectations, deferral-tolerance rules, safe-to-wait discipline, unsafe-to-wait discipline, review-urgency meaning, escalation-urgency meaning, or timing-review expectations are consequential platform changes. They must go through formal governance rather than domain-local adjustment.

Review and approval should align with the platform governance roles and approval authority matrix, especially where shared workflow behavior, escalation behavior, abstention behavior, reporting-scope behavior, or policy-learning behavior are affected.

## Failure Modes in Materiality, Priority, and Urgency Design

Weak materiality, priority, and urgency design creates direct platform risk.

### Everything becomes urgent

The platform treats most cases as urgent, destroying the distinction between urgent now, urgent soon, and safe to defer and making real urgency harder to see.

### False urgency from weak evidence

The platform mistakes noisy signals, thin narrative pressure, or local operator anxiety for governed urgency and begins moving cases fast without disciplined basis.

### High materiality confused with immediate action

The platform treats consequential cases as though high consequence automatically means act now, even where the disciplined path should be urgent review, urgent escalation, or bounded waiting.

### Weak evidence causing delay when review should have been urgent

The platform sees weak evidence and delays everything, even though the correct governed response should have been urgent review or urgent escalation rather than passive waiting.

### Safe-to-wait used as casual procrastination

The platform records that a case was safe to wait without preserving urgency horizon, deferral tolerance, or action-now versus wait justification strongly enough to distinguish governed waiting from drift.

### Urgency lost during handoff or escalation

The platform records that a case moved into approval, escalation, or revisit handling but loses the original urgency posture, so downstream handlers cannot tell how quickly they were expected to act.

### Recommendation history with no preserved timing discipline

The platform later knows what it recommended but cannot reconstruct whether it recommended act now, wait, review quickly, or revisit soon under a disciplined timing basis.

### Post-mortem unable to judge whether the platform moved fast enough

Later review has execution and outcome history but lacks preserved urgency horizon, deferral tolerance, or timing posture strong enough to judge whether the platform moved too slowly, too quickly, or appropriately.

### Policy learning overreacting to noisy urgency signals

The platform begins adapting future behavior from repeated urgent language, local queue culture, or a few memorable accelerated cases even though the underlying urgency lineage and evidence discipline are too weak.

### Domains drifting into incompatible local urgency semantics

Different domains begin using materiality, priority, urgency, severity, defer, safe to wait, or critical review to mean different things, making cross-domain timing discipline structurally unreliable.

These failure modes are not minor documentation defects. They are ways a decision platform can appear disciplined about timing while actually forgetting how it justified speed, order, and delay.

## Non-Negotiables

1. Materiality context, priority context, and urgency context are first-class governed decision-support context.
2. Materiality is not the same thing as urgency.
3. Priority is not the same thing as urgency.
4. Materiality is not the same thing as confidence.
5. Urgency is not the same thing as uncertainty.
6. Priority is not the same thing as recommendation.
7. High urgency does not automatically justify high confidence.
8. Weak evidence may still produce high review urgency.
9. Safe-to-wait is a governed condition, not casual delay.
10. Unsafe-to-wait must remain explicit when delay materially increases downside.
11. Materiality, priority, and urgency must remain distinct from action feasibility and constraint validity.
12. Policy learning must not casually reuse urgency history without lineage and evidence discipline.

## Closing Statement

This document protects decision materiality, priority, and urgency from collapsing into thin labels, queue shortcuts, or local workflow habit.

That protection matters because a serious decision platform must preserve not only what it recommended or withheld, but how consequential the case was, how urgently it needed action or review, how much waiting was legitimate, whether escalation had to move quickly, and how later post-mortem and learning can judge timing discipline without drifting into hindsight narrative. Future domains need one shared materiality, priority, and urgency grammar to avoid drift in how the platform decides what matters, what moves first, and what cannot safely wait.