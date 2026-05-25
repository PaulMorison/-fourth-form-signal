# Shared Assumption, Hypothesis, and Inference Register Standard for the Fourth Form Retail Decision Intelligence Platform

## Purpose of This Document

This document defines the shared platform standard for assumption registers, hypothesis registers, and inference registers across all current and future domains.

It exists because the platform now has governed standards for cases, evidence, state, uncertainty, rationale, chronology, review, execution, post-mortem, and policy-learning admission, but it still lacks one shared meaning for how explicit assumptions, actively considered hypotheses, and inferential moves should be preserved when they materially shape decision reasoning. Without a shared standard, assumptions drift into hidden facts, hypotheses disappear once recommendation is issued, inferential steps vanish inside prose, and later review or post-mortem starts reconstructing what the platform must have been assuming rather than preserving what it actually relied on at decision time.

This document is therefore a control document for shared assumption, hypothesis, and inference structure.

It defines the core concepts, shared object meanings, status rules, lineage rules, interaction rules, extension rules, and governance linkage that all domains must follow when preserving explicit assumptions, live hypotheses, and inferential steps as part of governed decision-support structure.

It is the canonical shared assumption, hypothesis, and inference register standard for the platform. Future domain workflow contracts, recommendation logic, rationale formation, review surfaces, execution comparison, post-mortem review, and policy-learning review must align with it unless a formal decision record explicitly revises it.

## Role of This Document in the Platform

This document governs the shared epistemic-support grammar that sits between preserved evidence and state on one side and structured rationale, recommendation, review, and post-mortem on the other.

The shared decision case and decision memory standard defines the governed episode anchor and later reusable memory, but it does not define one shared meaning for the explicit assumptions, active hypotheses, or inferential steps that may sit inside that episode. The shared decision intake and case formation standard defines how a governed case begins, but it does not define one shared meaning for the assumptions or hypotheses the platform may rely on after formation. The shared recommendation record standard defines what the platform recommended, but it does not define one shared meaning for the hypotheses considered before that recommendation or the assumptions relied on beneath it. The shared decision rationale and explanation trace standard defines the broader reasoning structure and explanation derivation, but it does not define one shared meaning for the intermediate inferential steps that connect evidence and state to that rationale. The shared evidence bundle and signal provenance standard defines what materially counted as evidence and where it came from, but it does not define one shared meaning for assumptions that are relied on without being identical to evidence. The shared uncertainty and confidence context standard defines what qualified decision strength, but it does not define one shared meaning for how assumptions qualify confidence without becoming confidence. The shared constraint and feasibility context standard defines what limited valid action, but it does not define one shared meaning for hypotheses or inferential chains. The shared state snapshot and local operating context standard defines what the platform believed the world looked like, but it does not define one shared meaning for the assumptions or hypotheses used to interpret that state. The shared comparison set and analog reference standard defines how historical comparisons support current interpretation, but it does not define one shared meaning for the assumptions or hypotheses that comparison support may strengthen or weaken. The shared decision timeline and event chronology standard defines what happened when, but it does not define one shared meaning for the assumptions or inferential steps active at those times. The shared observation-horizon and measurement-window standard defines maturity for later judgment, but it does not define one shared meaning for how assumptions later hold, weaken, or fail. The shared review resolution and case disposition standard defines how review concludes, but it does not define one shared meaning for what assumptions or hypotheses remained active inside that review. The shared execution deviation and outcome object standard and the shared post-mortem and attribution judgment standard define what later happened and how it was judged, but they do not define one shared meaning for the registers that preserve what the platform assumed, hypothesized, or inferred before those later judgments existed.

In practical terms, this document governs what an assumption register is, what a hypothesis register is, what an inference register is, how assumption differs from evidence, how hypothesis differs from recommendation, how inference differs from rationale, how these registers preserve status over time, and how later decision-loop stages may reuse them without silently converting them into learning admission.

This document therefore governs explicit decision-time epistemic structure as part of platform coherence.

## Core Thesis

In the Fourth Form platform, assumptions, hypotheses, and inferential steps must remain first-class governed decision-support structure whose scope, status, lineage, and reuse limits remain explicit enough that the platform can preserve what it relied on, what it was actively considering, and how it moved from evidence and state to structured reasoning without later rewriting those elements into evidence, recommendation, confidence, or attribution.

That is the core thesis.

The governing distinctions are straightforward: an assumption is not the same thing as evidence. A hypothesis is not the same thing as a recommendation. An inference step is not the same thing as a rationale trace. Assumptions and hypotheses may materially support recommendation, review, and post-mortem interpretation, but assumption or hypothesis reuse is not the same thing as policy-learning admission.

## What This Standard Is and Is Not

This standard is the shared platform rule for how the system records, links, preserves, and reuses explicit assumptions, active hypotheses, and inferential moves that materially shape one decision episode.

It is not a local workflow note. It is not a model-debugging memo. It is not a statistics explainer. It is not a lightweight commentary guide. It is not an evidence bundle. It is not a recommendation record. It is not a confidence score. It is not a rationale trace. It is not a post-mortem object. It is not permission for domains to preserve hidden assumptions in prose and later call them governed structure. It is not permission to smooth away unsupported hypotheses once one path becomes preferred. It is not permission to backfill inferential moves from hindsight after the decision has already been judged. It is not permission to treat explicit assumption history or hypothesis history as automatically reusable learning input.

A real shared assumption, hypothesis, and inference standard means the platform can answer the following questions for any material decision episode: what explicit assumptions were materially relied on, what status those assumptions held, what hypotheses remained open or narrowed or rejected or supported, what inferential steps linked evidence and state to structured reasoning, where inferential gaps or inferential overreach remained active, how those registers changed over time, how review and post-mortem should inspect them, and what reuse limits still govern them.

## Why an Assumption, Hypothesis, and Inference Standard Is Necessary

Domains must not define assumptions, hypotheses, and inferential steps independently because the platform cannot remain one governed decision system if one domain hides assumptions inside rationale prose, another treats hypotheses as informal brainstorming, another records only the winning thesis and not the rejected alternatives, another lets confidence language stand in for inferential quality, and another treats post-mortem hindsight as though it proves what the platform really knew at decision time.

If assumption, hypothesis, and inference grammar is left local, several failures follow. Hidden assumptions get treated as facts. Weak assumptions get presented as strong evidence. Hypotheses disappear once recommendation is issued. Inferential leaps remain untraceable because no inferential chain was preserved. Rejected hypotheses and invalidated assumptions vanish from history, leaving post-mortem to reconstruct them from memory. Confidence language starts masking inferential weakness. Review cannot tell whether disagreement concerns evidence, assumptions, hypotheses, or inference. Learning review starts overreacting to reused assumptions without evidence-admission discipline.

The platform therefore needs one shared standard so that future domains can extend one governed register grammar rather than inventing local meanings for assumptions, hypotheses, inferential steps, and the history of how they changed.

## Core Concepts

The platform uses the following core concepts.

### Assumption register

Assumption register is the governed object that preserves the explicit assumptions materially relied on by the case or downstream decision-support objects.

### Hypothesis register

Hypothesis register is the governed object that preserves actively considered explanatory or decision-relevant hypotheses that remain materially relevant to the case.

### Inference register

Inference register is the governed object that preserves the inferential steps that connect evidence and state readings to structured decision reasoning.

### Active assumption

Active assumption is an explicit assumption that the platform is presently relying on materially for recommendation, review, simulation interpretation, non-action handling, or another governed downstream use.

### Provisional assumption

Provisional assumption is an explicit assumption that is materially relevant and presently usable, but is still visibly tentative, still awaiting stronger support, or still exposed to near-term weakening or invalidation.

### Weak assumption

Weak assumption is an explicit assumption whose support, relevance, scope fit, or interpretive stability is materially limited enough that downstream use must remain visibly cautious.

### Invalidated assumption

Invalidated assumption is an explicit assumption that later evidence, later review, later execution observation, or later governed judgment has shown to be materially unsound for the episode or for the specific use it previously supported.

### Open hypothesis

Open hypothesis is an actively considered explanatory or decision-relevant hypothesis that remains materially live and has not yet been narrowed, rejected, or supported strongly enough to settle its role.

### Narrowed hypothesis

Narrowed hypothesis is a hypothesis whose scope, applicability, or candidate explanation space has been reduced under preserved lineage without yet being fully rejected or fully settled.

### Rejected hypothesis

Rejected hypothesis is a hypothesis that has been materially ruled out for the current episode or current use under preserved lineage and explicit reasoning.

### Supported hypothesis

Supported hypothesis is a hypothesis that has been materially strengthened by the preserved evidence, state reading, inferential chain, or later governed review without thereby becoming identical to recommendation or final judgment.

### Inference step

Inference step is one governed interpretive move that links evidence and state readings to a narrower conclusion, working proposition, explanatory path, or rationale component.

### Inferential chain

Inferential chain is the reconstructible sequence of inference steps by which the platform moved from preserved evidence and state into more structured reasoning.

### Inference sufficiency

Inference sufficiency is the governed judgment that the preserved inferential steps are strong enough for a stated use because the chain is explicit enough, disciplined enough, and well linked enough to support that use honestly.

### Inferential gap

Inferential gap is the governed condition in which a materially necessary reasoning link between evidence or state and a later conclusion is missing, too weak, or too implicit for the intended use. inferential gap must remain explicit.

### Assumption lineage

Assumption lineage is the reconstructible chain connecting an explicit assumption to the case, the evidence and state it interacted with, the downstream objects that relied on it, later review of that assumption, and any later weakening, confirmation, or invalidation.

### Hypothesis lineage

Hypothesis lineage is the reconstructible chain connecting a hypothesis to the case, the evidence and state that bore on it, the inferential steps and rationale components that used it, and the later narrowing, support, rejection, or review that changed its status.

### Inference lineage

Inference lineage is the reconstructible chain connecting evidence and state inputs, the inferential steps taken, the assumptions and hypotheses touched by those steps, the later rationale structure they supported, and the later review or post-mortem inspection that reused them.

### Assumption scope discipline

Assumption scope discipline is the governed rule that an assumption must remain tied to the case, scope, horizon, and use for which it is actually valid rather than being widened by convenience.

### Inferential overreach

Inferential overreach is the governed condition in which the platform or a reviewer claims a stronger conclusion, a broader scope, or a more settled position than the preserved evidence, state, assumptions, and inferential chain can honestly support. inferential overreach must remain explicit.

## Shared Assumption Register

At platform level, a shared assumption register is the formal governed object preserving the explicit assumptions materially relied on by the case or downstream decision-support objects.

It exists because the platform must preserve more than what was observed and more than what was ultimately recommended. It must preserve the explicit propositions, boundary conditions, working premises, and operating expectations that the platform materially relied on while interpreting the case, comparing action paths, recommending action or non-action, preparing review, or later comparing execution reality with prior expectations.

The shared assumption register must preserve, conceptually, all of the following. It must preserve a stable register identity so the assumption set is reconstructible later. It must preserve the originating case reference so the assumption set remains anchored to the governed episode. It must preserve domain reference, decision scope reference, and tenant or client scope reference where relevant so assumptions do not lose their governed population. It must preserve explicit assumption entries and assumption status references so later systems can distinguish active assumptions, provisional assumptions, weak assumptions, invalidated assumptions, and later confirmed or stabilized assumptions where relevant. It must preserve related evidence, state, hypothesis, inference, rationale, recommendation, review, execution, or post-mortem linkage where relevant so later systems can reconstruct what relied on the assumptions. It must preserve assumption lineage, timestamps, and version references so later systems can reconstruct which assumptions existed at decision time and how those assumptions later changed.

The shared assumption register is not a hidden comment field and not a substitute for evidence. an assumption is not the same thing as evidence. The register preserves what the platform explicitly relied on, not merely what it observed.

This is governed object meaning, not code schema. Shared assumption register must remain interpretable as the platform's formal record of relied-on assumptions rather than as scattered narrative residue.

## Shared Hypothesis Register

At platform level, a shared hypothesis register is the formal governed object preserving actively considered explanatory or decision-relevant hypotheses that remain materially relevant to the case.

It exists because the platform must preserve more than one winning story. It must preserve which explanatory or decision-relevant possibilities were actively live, which were narrowed, which were supported, which were rejected, and how those possibilities materially shaped later recommendation, review, non-action handling, or post-mortem review.

The shared hypothesis register must preserve, conceptually, all of the following. It must preserve a stable register identity so the hypothesis set is reconstructible later. It must preserve the originating case reference so the hypotheses remain anchored to the governed episode. It must preserve domain reference, decision scope reference, and tenant or client scope reference where relevant so hypotheses do not lose their governed population. It must preserve open-hypothesis, narrowed-hypothesis, rejected-hypothesis, and supported-hypothesis entries where materially relevant. It must preserve links to evidence, state, assumptions, inferential steps, rationale, recommendation, review, execution comparison, or post-mortem review where relevant so later systems can reconstruct how those hypotheses mattered. It must preserve hypothesis lineage, timestamps, and version references so later systems can reconstruct which hypotheses were live at what point and how their status changed over time.

The shared hypothesis register is not a recommendation record and not a substitute for rationale. a hypothesis is not the same thing as a recommendation. A supported hypothesis may materially strengthen one path or weaken another without becoming the recommendation by itself.

This is governed object meaning, not code schema. Shared hypothesis register must remain interpretable as the platform's formal record of materially live explanatory or decision-relevant possibilities rather than as brainstorming commentary.

## Shared Inference Register

At platform level, a shared inference register is the formal governed object preserving the inferential steps that connect evidence and state readings to structured decision reasoning.

It exists because the platform must preserve more than raw evidence, more than a state snapshot, and more than a final rationale thesis. It must preserve the intermediate interpretive moves by which evidence and state were taken to support, weaken, narrow, or reject assumptions and hypotheses strongly enough that later review can inspect how the platform moved from what it saw to what it reasoned.

The shared inference register must preserve, conceptually, all of the following. It must preserve a stable register identity so the inferential chain is reconstructible later. It must preserve the originating case reference so the inferential steps remain anchored to the governed episode. It must preserve domain reference, decision scope reference, and tenant or client scope reference where relevant so inference does not lose its governed population. It must preserve explicit inference-step entries and inferential-chain relations so later systems can inspect how reasoning moved. It must preserve links to evidence, state, assumption, hypothesis, rationale, recommendation, review, execution comparison, and post-mortem inspection where relevant. It must preserve inference sufficiency posture and any inferential gap or inferential overreach qualification where relevant so later systems do not overread the chain. It must preserve inference lineage, timestamps, and version references so later systems can reconstruct which inferential structure existed at decision time.

The shared inference register does not replace rationale. an inference step is not the same thing as a rationale trace. The inference register preserves the connective reasoning moves that help form the broader rationale structure without becoming the whole rationale by itself.

This is governed object meaning, not code schema. Shared inference register must remain interpretable as the platform's formal record of inferential movement rather than as a thin explanation note.

## Assumption, Hypothesis, and Inference Rules

Explicit assumptions and hypotheses must be governed strongly enough that later systems do not have to guess what the platform relied on. If a downstream decision-support object materially depends on an assumption, that assumption must be surfaced into governed structure rather than left implicit inside prose, code habit, or local operating memory. Hidden assumptions treated as facts are a design failure, not a harmless omission.

Explicit versus implicit assumptions must therefore be handled strictly. Implicit assumptions may exist in early reasoning, but if they materially shape recommendation, escalation, abstention, commitment, instruction, review, execution comparison, or post-mortem interpretation, they must be surfaced and preserved explicitly. Assumption scope discipline must govern that surfacing so the assumption is preserved only for the scope, horizon, and use it actually supports.

Weak versus active assumptions must remain distinct. An active assumption is materially relied on now. A weak assumption may still be present and may still matter, but downstream use must remain visibly qualified because the support for that assumption is materially limited. evidence weakness is not identical to assumption weakness. Strong evidence may still be interpreted through a weak assumption, and weak evidence may still bear on an otherwise stable assumption.

Provisional versus stabilized assumptions must also remain distinct. A provisional assumption may be necessary for disciplined handling now while still being visibly tentative. A stabilized assumption is one whose status has strengthened enough within the episode or later governed review that the platform can treat it as less fragile for that episode, though not as timeless truth. Assumptions may later be confirmed, but later confirmation must not retroactively erase the fact that the assumption was once provisional or weak.

Assumption invalidation must preserve history rather than erase it. When later evidence, execution reality, review, or post-mortem shows that an assumption no longer holds, the register must preserve that invalidated status under lineage rather than rewriting the earlier record. invalidated assumptions must remain historically visible.

Open versus narrowed hypotheses must remain explicit. An open hypothesis is materially live. A narrowed hypothesis remains live but within a reduced explanation or decision space. A supported hypothesis may become more compelling without thereby becoming the recommendation. A rejected hypothesis is one the platform has materially ruled out for the current episode or use, but rejected versus merely unsupported hypotheses must remain distinct. Unsupported hypotheses must remain visible where materially relevant. A hypothesis that is not yet supported is not automatically rejected, and a rejected hypothesis is not automatically proof a competing hypothesis is true.

Hypotheses and assumptions change over time, and those status changes must be preserved rather than flattened. The registers must show when an assumption strengthened, weakened, stabilized, or invalidated, and when a hypothesis remained open, narrowed, supported, or rejected. Status change is part of lineage, not a reason to overwrite earlier states.

Inference sufficiency must be judged for the use being attempted. A short inferential chain may be sufficient for bounded review orientation while remaining insufficient for strong recommendation or strong post-mortem attribution. A register that preserves the visible steps from evidence and state into a narrow conclusion may support one downstream use while remaining too thin for another.

Inferential weakness must remain explicit. inferential gap must remain explicit. inferential overreach must remain explicit. When the platform or a reviewer cannot honestly show how the preserved evidence, state, assumptions, and hypotheses justify the conclusion claimed, the register must preserve that gap rather than smoothing it into narrative certainty. When the conclusion claimed outruns the preserved chain, inferential overreach must be recorded rather than hidden inside strong confidence language.

Inferential steps must preserve rejected and abandoned paths where materially relevant. If one inferential line was considered and later rejected, the platform should preserve that where doing so materially supports review, post-mortem, or later explanation of why the final line prevailed.

## Interaction with Evidence, Rationale, Confidence, Review, and Post-Mortem

The interaction rules are strict because these registers sit near several adjacent controlling objects without replacing any of them.

The first distinction is foundational: an assumption is not the same thing as evidence. Evidence may support, weaken, or invalidate an assumption, but the assumption register preserves what the platform relied on, while the evidence bundle preserves what was observed, sourced, and admitted as evidence.

The second distinction is equally important: a hypothesis is not the same thing as a recommendation. A hypothesis may support, weaken, or contest candidate paths, but the recommendation record preserves the preferred path, not the whole live hypothesis set.

The third distinction protects the reasoning layer: an inference step is not the same thing as a rationale trace. The inference register preserves intermediate interpretive moves. The rationale trace preserves the broader structured reasoning and decision thesis those moves help support.

Evidence weakness is not identical to assumption weakness. Confidence may depend on assumptions without turning assumptions into confidence. A strong evidence line may still be interpreted through a fragile assumption, and a low-confidence case may still contain one or more assumptions that are locally strong but globally insufficient for the recommendation or non-action posture being considered.

These registers also interact with review and post-mortem under preserved lineage. Review may inspect whether assumptions were explicit enough, whether hypotheses were kept live honestly, and whether inferential steps were sufficient for the review outcome claimed. An invalidated assumption is not automatically proof the original case was illegitimate. A rejected hypothesis is not automatically proof a competing hypothesis is true.

Post-mortem inspection must remain historically disciplined. post-mortem may review assumptions and hypotheses without retroactively rewriting what the platform knew at decision time. The post-mortem layer may judge that an assumption later failed, that a hypothesis was too narrow, or that an inferential chain contained overreach, but it must do so against the preserved registers rather than rewriting those registers into what later became obvious.

These registers may support later learning review, but reuse is bounded. assumption or hypothesis reuse is not the same thing as policy-learning admission. Learning admission still depends on the separate controlling standard for evidence admission, comparability, attribution quality, and update threshold.

The extension boundary is also strict: future assumption extensions must be placed according to control role, not convenience.

## Canon Placement and Extension Rules

This document belongs in the shared objects layer because it governs reusable shared registers and reusable shared grammar for decision-time assumptions, hypotheses, and inferential steps across all domains. It does not merely govern one local model note, one interface payload, or one reporting surface.

future assumption extensions must be placed according to control role, not convenience.

If an extension changes shared assumption meaning, hypothesis meaning, inferential-step meaning, status grammar, lineage grammar, or reuse rules across domains, it belongs in the shared objects layer or the shared core canon as appropriate. If it changes transport behavior or cross-domain delivery semantics, it belongs in the interface canon. If it changes entitlement, reporting exposure, or learning-scope exposure for these registers, it belongs in the boundary canon. If it changes only one domain's local operating ritual, it belongs in the relevant domain contract and must not redefine the shared grammar.

This standard does not authorize local documents to redefine evidence meaning, recommendation meaning, rationale meaning, confidence meaning, review-resolution meaning, execution meaning, post-mortem meaning, or policy-learning admission meaning. Those meanings remain with their controlling standards.

## Governance Linkage

The shared decision case and decision memory standard should treat this file as the controlling reference for preserving explicit assumption, hypothesis, and inference history inside one governed episode. The shared evidence bundle and signal provenance standard should treat it as the controlling reference for why preserved evidence remains distinct from the assumptions and hypotheses that later rely on it. The shared state snapshot and local operating context standard should treat it as the controlling reference for how state readings interact with assumptions and hypotheses without becoming them. The shared uncertainty and confidence context standard should treat it as the controlling reference for why confidence may depend on assumptions and inferential quality without replacing them. The shared decision rationale and explanation trace standard should treat it as the controlling reference for how inferential steps and inferential chains sit beneath broader rationale structure without collapsing into the rationale trace itself. The shared recommendation record standard should treat it as the controlling reference for why supported or narrowed hypotheses remain distinct from the recommendation path. The shared comparison set and analog reference standard should treat it as the controlling reference for how historical comparisons may strengthen or weaken assumptions and hypotheses without silently becoming recommendation or learning admission. The shared decision timeline and event chronology standard should treat it as the controlling reference for how these registers preserve decision-time epistemic structure alongside event sequence rather than replacing it. The shared review resolution and case disposition standard should treat it as the controlling reference for how review may inspect assumptions and hypotheses without redefining review outcome meaning. The shared execution deviation and outcome object standard and the shared post-mortem and attribution judgment standard should treat it as the controlling reference for how execution reality and later judgment may inspect assumption and hypothesis quality without rewriting decision-time structure. The policy-learning evidence admission and update-threshold standard should treat it as the controlling reference for why assumption or hypothesis reuse remains distinct from learning admission.

Changes to shared assumption meaning, shared hypothesis meaning, inferential-step meaning, status rules, lineage rules, or reuse rules are consequential shared-platform changes. Under the governance authority matrix, such changes should be treated as shared platform or shared architecture changes, with governance and boundary review where explanation scope, review scope, reporting scope, or learning scope are materially affected.

## Failure Modes in Assumption, Hypothesis, and Inference Design

### Hidden assumptions treated as facts

The platform materially relies on assumptions that never enter governed structure, and later users mistake those hidden assumptions for observed fact.

### Weak assumptions presented as strong evidence

The platform or a reviewer describes an assumption as though it were evidence, masking the fact that the underlying basis was interpretive or provisional.

### Hypotheses disappearing once recommendation is issued

The platform preserves only the preferred path and loses the live hypothesis set that materially shaped why other interpretations or paths were not chosen.

### Inferential leaps with no preserved chain

The platform moves from evidence and state to a strong conclusion, but no inferential chain survives to show how that movement happened.

### Rejected hypotheses erased from history

Once a hypothesis is ruled out, the register overwrites it instead of preserving why it mattered and why it was rejected.

### Invalidated assumptions rewritten instead of preserved

Later evidence or post-mortem makes an assumption fail, and the platform quietly rewrites the assumption history instead of preserving the invalidated state.

### Confidence masking inferential weakness

Strong or weak confidence language is used as a substitute for preserving whether the inferential chain was actually sufficient.

### Post-mortem rewriting assumptions instead of judging them

Later hindsight replaces the original assumption and hypothesis registers instead of inspecting their preserved decision-time status.

### Learning overreacting to reused assumptions without admission discipline

Repeated assumption or hypothesis patterns are treated as though they were automatically learnable even though evidence admission and update-threshold rules were never satisfied.

### Assumption registers turned into vague prose instead of governed objects

The register becomes an informal narrative note with no explicit entries, statuses, lineage, or controlled links to the case and downstream objects.

## Non-Negotiables

1. Every governed assumption register must preserve the explicit assumptions materially relied on by the case or downstream decision-support objects, together with status, scope, and lineage.
2. an assumption is not the same thing as evidence, and evidence weakness is not identical to assumption weakness.
3. Every governed hypothesis register must preserve open, narrowed, rejected, and supported hypotheses where materially relevant, even when one path later becomes preferred.
4. a hypothesis is not the same thing as a recommendation, and a rejected hypothesis is not automatically proof a competing hypothesis is true.
5. Every governed inference register must preserve inference steps and inferential chains linking evidence and state readings to structured reasoning.
6. an inference step is not the same thing as a rationale trace, and inferential gap must remain explicit.
7. inferential overreach must remain explicit, and confidence may depend on assumptions without turning assumptions into confidence.
8. invalidated assumptions must remain historically visible, and unsupported hypotheses must remain visible where materially relevant.
9. post-mortem may review assumptions and hypotheses without retroactively rewriting what the platform knew at decision time, and assumption or hypothesis reuse is not the same thing as policy-learning admission.
10. future assumption extensions must be placed according to control role, not convenience, and domain-local habits must not redefine the shared grammar.

## Closing Statement

The platform needs governed assumption, hypothesis, and inference registers because decision quality depends not only on what was observed and what was recommended, but also on what was relied on, what remained live, and how the platform moved from evidence and state into structured reasoning. When these registers remain explicit, status-bearing, and historically visible, review and post-mortem can judge them honestly without rewriting them, and learning review can inspect them without silently promoting them into admitted policy-learning evidence.

That separation is what keeps decision-time epistemic structure usable without letting it dissolve into narrative convenience or hindsight authority.