# Decision-Mode and Intervention-Policy Standard for the Fourth Form Retail Decision Intelligence Platform

## Purpose of This Document

This document defines the shared platform standard for decision mode and intervention policy across all current and future domains.

It exists because the platform now has governed standards for intake, case formation, recommendation, escalation, abstention, approval, override, commitment, instruction, progression, authority boundary, failure handling, observation maturity, reopened handling, and policy-learning admission, but it still lacks one shared meaning for what intervention posture the platform is currently allowed to occupy, what that posture permits or prohibits, and when the platform may enter, remain in, exit, or step down from a stronger or weaker mode.

Without a shared standard, the platform will drift into mode being treated as vague workflow status, mode being collapsed into stage, authority, recommendation state, or readiness label, recommendation outputs being read as if they implied commitment, review-required handling being hidden inside local workflow language, learning being attempted from immature or integrity-compromised history, and reopened or recovered cases resuming stronger intervention without governed re-entry discipline.

This document is therefore a control document for shared decision-mode and intervention-policy discipline.

It defines the core concepts, shared decision modes, entry and exit rules, object-interaction rules, authority and progression interaction rules, restricted and prohibited mode rules, canon placement rules, and governance linkage that all domains must follow when selecting and governing the intervention posture of the platform.

It is the canonical shared decision-mode and intervention-policy document for the platform. Future domains, workflow contracts, orchestration logic, review logic, commitment logic, instruction logic, execution-observation handling, post-mortem handling, reopened handling, and learning-gating rules must align with it unless a formal decision record explicitly revises it.

## Role of This Document in the Platform

This document governs the shared platform rule for what kind of intervention the system may legitimately perform, prepare, restrict, prohibit, or defer at a given point in governed handling.

The system layers overview defines the platform stack, but it does not define one shared meaning for which intervention posture is active for a case or handling path at a given moment. The canon navigation and reading-order standard defines where this document belongs in the core canon, but it does not define one shared meaning for decision mode itself. The future domain admission and domain readiness standard defines when a new domain may join the platform, but it does not define how an admitted domain must select among intake-only, recommendation, review-required, recovery, post-mortem, or learning-eligible handling. The policy-learning evidence admission and update-threshold standard defines when preserved history is admissible for policy adaptation and when updates may be justified, but it does not define one shared meaning for learning-prohibited mode or learning-eligible mode as intervention posture. The shared decision intake and case formation standard defines intake and case-formation objects, but it does not define when the platform must remain in intake-only mode, move into case-formation mode, or remain in evidence-building mode. The shared recommendation record standard defines recommendation object meaning, but it does not define when recommendation mode, advisory-only mode, commitment-permitted mode, or instruction-permitted mode may legitimately govern the case. The shared escalation and abstention record standard defines governed non-action objects, but review-required mode is not the same thing as escalation record and advisory-only mode is not the same thing as abstention record. The shared approval and override record standard defines human intervention objects, but it does not define when the current mode may or may not permit stronger downstream intervention. The shared review resolution and case disposition standard defines review-exit and closure grammar, but it does not define when post-mortem mode or learning-eligible mode may begin. The shared exception, anomaly, and failure-state standard defines anomaly, failure, quarantine, and recovery structure, but it does not define one shared rule for how recovery mode interacts with other intervention modes. The shared capability, authority, and responsibility boundary standard defines who may bind and who remains accountable, but it does not define one shared meaning for the current intervention posture itself. The shared progression-gate and stage-transition standard defines stage validity and downstream stage entitlement, but it does not define one shared meaning for the mode that governs what the platform is allowed to do inside or across those stages. The shared reopen, revisit, and reinstatement standard defines re-entry structure, but it does not define one shared meaning for reopened, revisited, or reinstated handling mode as current intervention posture. The shared recommendation, commitment, and action-instruction boundary standard defines advisory, binding, and executable object boundaries, but it does not define the higher-order cross-platform rule for when those boundaries may be crossed. The shared observation-horizon and measurement-window standard defines maturity timing, but it does not define one shared meaning for learning-prohibited mode or post-mortem mode as governed intervention posture. The platform governance roles and approval authority matrix defines who approves consequential change, but it does not define the shared operating grammar by which a case moves among stronger or weaker intervention postures during governed handling.

In practical terms, this document governs what active mode means, which modes are shared across the platform, what conditions permit or block entry into stronger or weaker intervention posture, how mode interacts with shared object standards without redefining them, how mode differs from authority, progression, readiness, and recommendation state, and when mode transitions are governance-relevant.

This document therefore governs intervention posture as part of platform coherence.

## Core Thesis

In the Fourth Form platform, decision mode must remain a first-class governed intervention posture that states what the platform may legitimately do with a case or handling path under current authority, progression, feasibility, uncertainty, integrity, review, and observation conditions, so that the system can select, restrict, or prohibit intervention strength without rewriting the underlying object standards.

That is the core thesis.

Mode is not the same thing as stage. Mode is not the same thing as authority. Mode is not the same thing as recommendation state. Mode is not the same thing as readiness. Multiple governed objects may exist inside one mode. Some modes prohibit downstream actions even when those objects already exist. Advisory-only output is not the same thing as commitment-permitted mode. Review-required mode is not the same thing as escalation record. Learning-eligible mode is not the same thing as policy-learning admission by itself. Recovery mode is not the same thing as ordinary workflow delay. Prohibited mode must remain distinguishable from weak confidence alone. Mode transitions are governance-relevant when they materially change what the platform is allowed to do.

## What This Standard Is and Is Not

This standard is the shared platform rule for how the system selects, preserves, constrains, and transitions decision mode.

It is not an ops note. It is not a product specification. It is not a domain-local workflow guide. It is not a UI state model. It is not a substitute for the shared object standards that define intake, case formation, recommendation, escalation, abstention, approval, override, commitment, instruction, review resolution, failure-state handling, reopened handling, or observation maturity. It is not permission to infer binding commitment from advisory recommendation. It is not permission to infer executable instruction from the existence of commitment-like language. It is not permission to treat a recommendation record, escalation record, approval record, override record, or post-mortem object as though that object automatically sets current mode. It is not permission to collapse progression stage, authority boundary, and current intervention posture into one vague status label. It is not permission to use mode language to weaken controlling object meaning already fixed elsewhere in the canon. It is not permission to bypass governance when a mode transition materially changes what the platform is allowed to do.

A real decision-mode and intervention-policy standard means the platform can answer the following questions for any material decision episode: what mode currently governs the case, what interventions are presently permitted, what interventions are presently restricted or prohibited, what conditions must already be true before a stronger mode may be entered, what conditions force step-down into a more restricted mode, how later objects may or may not be used inside the current mode, and how later review, post-mortem, and learning should interpret that posture without inventing it after the fact.

## Why a Decision-Mode and Intervention-Policy Standard Is Necessary

Domains must not define decision modes independently because the platform cannot remain one governed decision system if one domain treats recommendation as though it were already commitment-ready, another treats review-required handling as though it were just an escalation object, another permits instruction because approval authority exists even though current integrity posture still blocks action, another treats post-mortem as though execution completion alone made it legitimate, and another treats learning eligibility as though any closed case were automatically ready for policy reuse.

If decision mode and intervention policy are left local, several failures follow. One domain treats mode as vague workflow status rather than as a control posture. Another collapses mode into stage and assumes later-stage artifacts automatically entitle stronger action. Another collapses mode into authority and assumes the presence of a valid approver overrides evidentiary or integrity restrictions. Another collapses mode into recommendation state and treats recommendation issuance as automatic permission for commitment. Another lets execution observation drift into premature post-mortem judgment because visible outcome is mistaken for mature outcome. Another lets recovery handling appear as ordinary delay rather than integrity-sensitive restriction. Another lets reopened or reinstated cases resume their prior strongest intervention posture automatically, even though re-entry quality is weak. Another lets policy learning adapt from histories that were still learning-prohibited.

The platform therefore needs one shared standard so that every domain can inherit one governed intervention-posture grammar rather than inventing its own local meaning for when the platform may observe, form, recommend, review, commit, instruct, observe execution, judge outcomes, learn, recover, or re-enter governed handling.

## Core Concepts

The platform uses the following core concepts.

### Decision mode

Decision mode is the governed platform posture that states what class of intervention the platform may presently perform, prepare, restrict, prohibit, or defer for a case or handling path.

### Intervention policy

Intervention policy is the governed rule set that maps current authority, progression, uncertainty, feasibility, integrity, review, and observation conditions to permitted, restricted, or prohibited decision modes.

### Active mode

Active mode is the current governing intervention posture for the case or handling path, including any explicit restrictive qualifier required to keep current permissions honest.

### Restricted mode

Restricted mode is a governed posture in which the platform may continue only within narrower boundaries than ordinary recommendation, commitment, instruction, post-mortem, or learning flow would otherwise suggest.

### Prohibited mode

Prohibited mode is a governed posture in which a stronger downstream class of intervention is not legitimate under current conditions even if related objects, confidence statements, or operator preference already exist.

### Advisory-only mode

Advisory-only mode is the governed posture in which the platform may observe, analyze, simulate, explain, and recommend, but may not by that posture alone bind commitment or issue executable instruction.

### Simulation-first mode

Simulation-first mode is the governed posture in which structured simulation, counterfactual evaluation, or equivalent pre-commitment testing must occur before a stronger intervention posture may be entered.

### Review-required mode

Review-required mode is the governed posture in which accountable review or higher-authority handling must occur before stronger downstream intervention may proceed.

### Commitment-permitted mode

Commitment-permitted mode is the governed posture in which current authority, scope, progression, feasibility, and integrity conditions are strong enough that binding commitment may legitimately be considered or issued.

### Instruction-permitted mode

Instruction-permitted mode is the governed posture in which current commitment lineage, instruction authority, executable scope, prerequisite settlement, and integrity posture are strong enough that executable instruction may legitimately be considered or issued.

### Recovery mode

Recovery mode is the governed posture in which anomaly handling, failure handling, quarantine handling, integrity-sensitive review, recovery settlement, or reinstatement-preparation governs the case strongly enough that ordinary stronger intervention may not proceed as though nothing were wrong.

### Learning-eligible mode

Learning-eligible mode is the governed posture in which observation maturity, post-mortem maturity, scope validity, comparability discipline, and integrity posture are strong enough that the case may enter governed learning review.

### Mode transition

Mode transition is the governed change from one active mode or materially different restrictive posture to another when current conditions materially change what the platform is allowed to do.

### Mode conflict

Mode conflict is the governed condition in which two candidate modes or qualifiers imply incompatible intervention permissions, in which case the stricter posture governs until the conflict is explicitly resolved.

### Mode override where relevant

Mode override where relevant is the governed act by which a valid authority path or integrity-sensitive control path explicitly replaces the otherwise default mode selection for the current case or handling path under preserved rationale and lineage.

### Learning-prohibited mode

Learning-prohibited mode is the governed posture in which policy-learning reuse, update consideration, or other stronger learning action must not proceed under current observation, evidence, scope, integrity, or attribution conditions.

## Shared Decision Modes

The platform uses shared decision modes as governed intervention postures rather than as a replacement for stage grammar or object grammar. Some modes are primary handling modes. Some are cross-cutting restrictive or enabling qualifiers. The point is not to force every case into one simplistic linear status ladder. The point is to preserve what the platform may legitimately do now.

### Intake-only mode

Intake-only mode is the posture in which materially relevant signals may be received, preserved, and evaluated for seriousness, but the platform must not yet treat the matter as a legitimately formed case or as a basis for stronger downstream intervention.

### Case-formation mode

Case-formation mode is the posture in which the platform is determining whether intake has legitimately crossed into governed case identity, initial scope, and initial business-object structure. It permits disciplined case-formation handling, but it does not by itself permit recommendation, commitment, or instruction.

### Evidence-building mode

Evidence-building mode is the posture in which the platform is actively building or reconciling the evidence, rationale basis, uncertainty context, feasibility context, or missing linkage required before a stronger intervention posture may be justified.

### Recommendation mode

Recommendation mode is the posture in which the platform may legitimately form and preserve a recommendation record or equivalent advisory position for the case. Recommendation mode permits governed recommendation output, but it does not by itself imply binding commitment, executable instruction, or learning eligibility.

### Simulation-first mode

Simulation-first mode is the posture in which the disciplined next step is simulation or counterfactual testing before stronger intervention. It may coexist with strong advisory analysis, but it blocks premature commitment or instruction while simulation remains the required next move.

### Advisory-only mode

Advisory-only mode is the posture in which the platform may recommend, explain, compare, or warn, but any resulting output remains advisory only under current authority and intervention policy. Advisory-only output is not the same thing as commitment-permitted mode.

### Review-required mode

Review-required mode is the posture in which accountable human review, higher-authority handling, conflict resolution, or other governed review path must occur before stronger intervention may continue. Review-required mode is not the same thing as escalation record, even though an escalation record may exist inside it.

### Commitment-permitted mode

Commitment-permitted mode is the posture in which a case may legitimately cross from advisory or reviewed handling into binding commitment under preserved authority, scope, progression, and integrity conditions. It governs commitment permission, not commitment object meaning.

### Instruction-permitted mode

Instruction-permitted mode is the posture in which a bound path may legitimately cross into executable instruction under preserved instruction authority, executable scope, prerequisite settlement, and integrity conditions. It governs instruction permission, not instruction object meaning.

### Execution-observation mode

Execution-observation mode is the posture in which downstream execution reality, deviation, and outcome evidence are being observed under an active observation horizon and measurement window. It permits governed observation and bounded interim review, but it does not by itself imply post-mortem readiness or learning eligibility.

### Post-mortem mode

Post-mortem mode is the posture in which the platform may legitimately perform governed attribution judgment and post-mortem interpretation because the relevant observation maturity, lineage, and judgment conditions are strong enough for that use.

### Learning-prohibited mode

Learning-prohibited mode is the posture in which policy-learning reuse, adaptation review, or update pressure must remain blocked because observation maturity, evidence sufficiency, scope validity, integrity quality, attribution quality, or comparability remains too weak.

### Learning-eligible mode

Learning-eligible mode is the posture in which the case may legitimately enter governed learning review because relevant maturity, attribution, scope, and integrity conditions are strong enough for that narrower purpose. Learning-eligible mode is not the same thing as policy-learning admission by itself.

### Recovery / anomaly-handling mode

Recovery / anomaly-handling mode is the posture in which anomaly review, failure-state handling, quarantine handling, recovery settlement, or integrity-sensitive manual review governs the case strongly enough that ordinary stronger intervention must step aside until safe continuation is restored.

### Reopened / revisited / reinstated handling mode

Reopened / revisited / reinstated handling mode is the posture in which a previously closed, deferred, abstained, blocked, quarantined, or otherwise interrupted case has re-entered governed handling under preserved re-entry lineage. It may operate through full reopen, bounded revisit, or reinstatement after blocked or quarantined state, but it must not be treated as ordinary forward progression.

These shared modes are not one simplistic ladder. The platform may move from evidence-building mode into recommendation mode while remaining advisory-only, from instruction-permitted mode into recovery mode when integrity fails, or from execution-observation mode into post-mortem mode while remaining learning-prohibited. The governing rule is always the most restrictive valid posture that keeps current permission honest.

## Mode Entry and Exit Rules

### General entry rule

No mode may be entered casually. Before a mode is entered, the platform must already have a reconstructible basis showing why that posture is legitimate under the controlling standards already in force. Intake-only mode requires materially relevant intake worth governed handling. Case-formation mode requires legitimate front-door evaluation of whether intake should become a case. Evidence-building mode requires unresolved evidence, rationale, uncertainty, or feasibility work strong enough to justify remaining upstream of stronger intervention. Recommendation mode requires a legitimately formed case and recommendation-ready handling strong enough for governed advisory output. Simulation-first mode requires that simulation or counterfactual evaluation is the disciplined next step rather than optional polish. Advisory-only mode requires that current authority or policy posture still prohibits stronger binding action even if recommendation is legitimate. Review-required mode requires unresolved accountable review. Commitment-permitted mode requires that authority, scope, progression, feasibility, and integrity conditions are strong enough for commitment consideration. Instruction-permitted mode requires that commitment lineage, instruction authority, executable scope, prerequisite settlement, and integrity posture are strong enough for executable instruction consideration. Execution-observation mode requires that instruction, execution, or realized observation has actually become the current governed concern. Post-mortem mode requires that observation maturity and lineage are strong enough for governed attribution. Learning-eligible mode requires that observation maturity, post-mortem maturity, scope validity, and integrity quality are strong enough for governed learning review. Recovery mode requires anomaly, failure, quarantine, or integrity-sensitive handling strong enough that ordinary stronger intervention is no longer safe. Reopened, revisited, or reinstated handling mode requires valid re-entry under the controlling reopen, revisit, or reinstatement rules.

### Entry-blocking rule

Mode entry is blocked whenever the controlling preconditions for that mode are absent or whenever a stricter blocking posture already governs the case. Missing authority blocks commitment-permitted mode and instruction-permitted mode. Unresolved review blocks stronger binding modes even when recommendation objects already exist. Integrity compromise blocks commitment-permitted, instruction-permitted, post-mortem, and learning-eligible handling whenever recovery posture must govern first. Evidence too weak blocks recommendation mode where advisory output would be structurally misleading and blocks stronger modes whenever recommendation-ready or review-ready posture is not real. Observation horizon immaturity blocks post-mortem mode for serious attribution and blocks learning-eligible mode for governed learning review. Active quarantine blocks ordinary stronger intervention. Insufficient re-entry quality blocks reopened, revisited, or reinstated handling mode. Mode conflict also blocks optimistic mode entry until the conflict is settled explicitly.

### Exit-permission rule

No mode may be exited merely because a later object now exists or because time has passed. Exit is permitted only when the current mode's governing reason no longer controls and the candidate next mode has satisfied its own entry basis. Intake-only mode may exit when legitimate case-formation handling begins or when intake is validly abstained, rejected, or closed. Case-formation mode may exit into evidence-building mode, recommendation mode, review-required mode, or non-entry closure only when case-formation judgment has actually settled. Evidence-building mode may exit only when its unresolved evidentiary basis has been materially improved or when the case is validly stepped down into abstention, review-required, or recovery posture. Recommendation mode may exit into advisory-only, simulation-first, review-required, commitment-permitted, or more restricted posture only when that next posture is explicitly justified. Commitment-permitted mode may exit into instruction-permitted mode only when executable prerequisites are settled; otherwise it may remain binding but not yet executable. Execution-observation mode may exit into post-mortem mode only when judgment is permitted. Post-mortem mode may exit into learning-eligible mode only when learning review is legitimate. Recovery mode may exit only when the relevant anomaly, integrity, quarantine, or recovery posture has been explicitly settled strongly enough for ordinary governed continuation or for explicit invalidation.

### Re-entry rule

Re-entry into a stronger or previously occupied mode is never automatic. Re-entry is allowed only when preserved lineage, preserved authority basis, preserved review basis, preserved integrity basis, and preserved re-entry quality together justify that return under the controlling progression, reopen, revisit, reinstatement, and failure-handling standards. A reopened case must not resume its prior strongest mode automatically. A revisited case must not be treated as though full reopen occurred unless it actually did. A reinstated case must not be treated as though recovery itself proved recommendation readiness, commitment readiness, or instruction readiness. Re-entry must preserve why it is legitimate now, not merely the fact that the case once occupied a stronger posture.

### Mandatory step-down rule

The platform must step down into a more restricted mode whenever the basis for stronger intervention materially weakens. It must step down from recommendation or commitment posture into evidence-building, advisory-only, or review-required posture when uncertainty, contradiction, or feasibility weakness grows materially. It must step down from commitment-permitted mode or instruction-permitted mode into review-required mode when accountable review becomes necessary. It must step down into recovery mode when integrity degrades, quarantine activates, or structural failure handling becomes necessary. It must step down from post-mortem mode or learning-eligible mode into learning-prohibited posture when observation maturity, attribution quality, or scope validity proves weaker than assumed. It must step down from reopened or reinstated handling into a more restricted posture when re-entry quality is not sufficient. Stronger mode may not be preserved by inertia once the controlling basis has weakened.

## Mode Interaction with Object Standards

Decision mode governs what the platform may legitimately do with shared objects. It does not redefine what those objects mean.

Intake-only mode and case-formation mode govern how the platform may use intake context and case-formation context. They do not redefine intake signal, intake candidate, case-ready state, or formed case meaning. Evidence-building mode governs whether the platform remains upstream of stronger intervention while evidence, rationale, uncertainty, or feasibility structure is still being assembled. It does not redefine evidence bundles, rationale traces, uncertainty context, or feasibility context.

Recommendation mode, simulation-first mode, and advisory-only mode govern what the platform may do with recommendation records. Recommendation record meaning remains controlled by the shared recommendation standard. A recommendation record may exist while the current mode remains advisory-only, simulation-first, or review-required. Mode is not the same thing as recommendation state. The existence of a recommendation object does not by itself move the platform into commitment-permitted mode or instruction-permitted mode.

Review-required mode governs whether the current case must pass through accountable review before stronger downstream intervention. Escalation records and abstention records remain controlled by the shared escalation and abstention standard. Review-required mode is not the same thing as escalation record, and advisory-only or evidence-building posture is not the same thing as abstention record. The mode governs current intervention posture; the object standards govern what escalation and abstention actually mean.

Approval records and override records remain controlled by the shared approval and override standard. Their existence may influence mode selection, but they do not define mode meaning. A valid approval record may exist while the current mode still blocks instruction because executable prerequisites remain unresolved. A valid override record may exist while the current mode still remains review-required because further accountable handling is still necessary.

Commitment context and action-instruction context remain controlled by the shared recommendation, commitment, and action-instruction boundary standard. Commitment-permitted mode governs when commitment handling may legitimately occur. Instruction-permitted mode governs when instruction handling may legitimately occur. Neither mode redefines commitment meaning or instruction meaning. A commitment object may exist while current mode still blocks instruction. An instruction-preparatory artifact may exist while current mode still prohibits executable instruction because authority, timing, integrity, or prerequisite posture remains unresolved.

Execution-observation mode governs how the platform occupies the back half while execution, deviation, and realized outcome are being observed. It does not redefine execution deviation objects or outcome objects. Post-mortem mode governs when those back-half objects may legitimately support attribution judgment. It does not redefine the post-mortem object itself. Learning-eligible mode and learning-prohibited mode govern whether preserved history may enter learning review. They do not redefine policy-learning admission, update threshold, or post-mortem attribution categories.

Reopened, revisited, or reinstated handling mode governs how the platform re-enters handling under preserved lineage. It does not redefine reopen context, revisit context, reinstatement context, or failure-state context. Recovery mode governs how anomaly, failure, quarantine, and recovery handling constrain the use of shared objects. It does not redefine those failure-state objects.

Multiple objects may exist inside one mode. Some modes prohibit downstream actions even when those objects already exist. The controlling object standards continue to define the objects. This standard defines whether the current platform posture may legitimately use them for stronger intervention.

## Mode Interaction with Authority, Readiness, and Progression

Mode is not the same thing as authority. Authority states who may bind, approve, override, instruct, retry, quarantine, or close. Mode states what class of intervention is currently legitimate. Authority may permit an action that current mode still prohibits. A valid approver may exist while the case remains advisory-only because commitment-permitted mode has not been reached. A valid instruction authority may exist while instruction-permitted mode remains blocked by integrity, timing, or prerequisite posture.

Mode is not the same thing as progression stage. Stage states where the case sits in governed handling. Mode states what intervention posture currently governs action within or across that stage. A case may be in a later stage while the current mode still blocks stronger intervention. A later stage object may exist while current mode still blocks stronger intervention. A recommendation record may exist while the case remains review-required. A commitment object may exist while the case remains not yet instruction-permitted. A closed case may still remain learning-prohibited.

Mode is not the same thing as readiness. Readiness, gate satisfaction, and downstream entitlement are inputs to mode selection, but they are not the same thing as the resulting intervention posture. Recommendation-ready is not automatically commitment-permitted. Commitment-ready is not automatically instruction-permitted. Judgment-ready is not automatically learning-eligible. Mode policy constrains what downstream objects may legitimately do. It uses readiness and progression signals, but it does not collapse into them.

Mode is not the same thing as recommendation state. Recommendation state preserves what advisory position exists. Mode preserves what stronger or weaker intervention posture currently governs the case. Recommendation may be strong while mode remains advisory-only. Recommendation may exist while mode remains simulation-first. Recommendation may exist while mode remains review-required.

The platform must therefore interpret authority, readiness, progression, and recommendation state as distinct but interacting control surfaces. Shared capability and authority boundaries determine who may bind. Shared progression gates determine whether the next stage is entitled to proceed. Shared readiness signals determine whether the current basis is mature enough for a narrower purpose. This standard determines what intervention posture the platform may legitimately occupy once those other control surfaces are taken seriously together.

## Restricted and Prohibited Modes

When the following conditions exist, the platform must prefer the stricter mode and must preserve the restricted or prohibited posture explicitly rather than smoothing it away into ordinary workflow language.

### Integrity is compromised

When integrity is compromised, the platform must enter recovery mode or another equally restrictive integrity-sensitive posture. Commitment-permitted mode, instruction-permitted mode, post-mortem mode, and learning-eligible mode must be treated as blocked or prohibited until integrity settlement is explicit. Instruction during integrity failure is not legitimate ordinary continuation.

### Authority is missing

When valid authority is missing, the platform may remain in advisory-only mode, evidence-building mode, or review-required mode where appropriate, but commitment-permitted mode and instruction-permitted mode must not be entered merely because the analytical basis is strong. Authority absence is a real restriction, not a documentation detail.

### Evidence is too weak

When evidence is too weak, the platform must remain in evidence-building mode, advisory-only mode, abstention-adjacent posture, or review-required mode as appropriate. Recommendation mode may be withheld, and stronger binding modes must remain prohibited. Weak evidence is not permission to force a stronger intervention posture for convenience.

### Observation horizon is immature

When the observation horizon is immature, the platform may remain in execution-observation mode or in a tightly qualified review posture, but serious post-mortem mode and learning-eligible mode must remain blocked unless the relevant maturity rules explicitly permit narrower provisional handling. Learning-prohibited mode should remain explicit whenever the relevant observation basis is still immature.

### Execution is blocked

When execution is blocked, the platform must step down from instruction-permitted mode into review-required mode, evidence-building mode, or recovery mode depending on whether the blocking basis is authority, feasibility, timing, dependency, or integrity. It must not behave as though instruction remained valid merely because it was once close to issuance.

### Review resolution is incomplete

When review resolution is incomplete, review-required mode must remain active. Commitment-permitted mode and instruction-permitted mode must remain prohibited unless the unresolved review basis has been explicitly settled or narrowly bounded under a governing rule that still keeps current permissions honest.

### Quarantine is active

When quarantine is active, recovery mode governs. Ordinary recommendation, commitment, instruction, post-mortem, and learning handling must remain blocked except to the extent that containment, integrity review, or bounded anomaly interpretation is itself the governed purpose. Quarantine is not a mild pause. It is a restrictive control posture.

### Re-entry quality is not sufficient

When re-entry quality is not sufficient, reopened, revisited, or reinstated handling mode must not be entered as though resumed handling were legitimate. The case must remain closed, deferred, quarantined, unresolved, or otherwise restricted under the controlling re-entry and failure-handling rules. Reopened cases resuming the wrong mode automatically is a control failure, not a workflow convenience.

Restricted and prohibited posture must remain explicit because prohibited mode must remain distinguishable from weak confidence alone. Weak confidence may justify evidence-building, advisory-only, or abstention-adjacent posture. Prohibited mode means the stronger intervention is not legitimate under current governance, authority, integrity, maturity, or re-entry conditions.

## Canon Placement and Extension Rules

This document belongs in the core architecture folder because it defines a platform-level operational control surface broader than any one shared object, boundary surface, interface surface, or single domain.

Future mode additions must be placed according to control role, not convenience. A future mode subtype belongs in core only when it governs cross-domain intervention posture, not when it merely adds domain-local workflow detail or rewrites object meaning already controlled elsewhere. A future object standard may describe object-specific state or lineage that mode policy later depends on, but it must not claim cross-platform mode authority merely because that object is frequently used during a certain posture. Domain-local documents may define narrower local submodes only when they inherit the shared platform meanings in this file, declare themselves subordinate to those meanings, and avoid redefining what shared modes permit or prohibit.

Any future canonical extension to shared decision mode must identify the parent shared mode or shared restriction it extends, the exact intervention class it permits, restricts, or prohibits, the entry and exit rules it depends on, the object standards it touches without redefining, the authority and progression surfaces it relies on, and the failure or re-entry conditions that force step-down. If a future canonical mode standard is added, repo memory must be updated in the same governed change so the canon tail remains structurally accurate.

Navigation documents may point to this standard, summarize its role, and sequence it in reading order, but they must not redefine the controlled meaning of shared decision modes. Shared object standards continue to control object meaning. This file controls shared mode policy.

## Governance Linkage

This standard is directly governance-linked because mode selection and mode transition change what the platform is allowed to do.

Consequential changes to shared mode meaning, shared entry and exit rules, advisory-only semantics, review-required semantics, commitment-permitted semantics, instruction-permitted semantics, recovery semantics, post-mortem posture, learning-prohibited semantics, learning-eligible semantics, or reopened and reinstated handling posture are shared platform changes. They must therefore be reviewed and approved under the platform governance authority model for shared architecture and shared cross-platform control changes.

At operating-history level, mode transitions are governance-relevant when they materially change what the platform is allowed to do. Transition from advisory-only mode into commitment-permitted mode, from commitment-permitted mode into instruction-permitted mode, from execution-observation mode into post-mortem mode, from learning-prohibited mode into learning-eligible mode, or from ordinary handling into recovery mode materially changes the platform's intervention rights and obligations. Those transitions must therefore be explicit or reconstructible through preserved lineage rather than hidden inside local workflow shorthand.

Domain-local workflow contracts must not silently override this standard. Shared object standards should treat this file as the controlling reference for cross-platform mode policy whenever they need to distinguish object meaning from current intervention posture. Policy-learning admission rules, authority-boundary rules, progression-gate rules, and reopened-handling rules should all treat this file as the controlling reference for when the platform may or may not select a stronger or weaker mode.

## Failure Modes in Decision-Mode Design

The platform must actively prevent the following failure modes.

### Treating mode as vague workflow status

When mode is treated as thin status language rather than as intervention policy, contributors begin reading local workflow labels as if they carried shared authority. The result is conceptual drift disguised as ordinary handling.

### Collapsing mode into stage

When mode is collapsed into stage, later-stage artifacts are mistaken for permission to act more strongly. The platform then treats stage occupancy as if it automatically proved intervention legitimacy.

### Collapsing mode into authority

When mode is collapsed into authority, the presence of a valid approver or valid authority boundary is treated as though it overrides evidentiary, integrity, progression, or maturity restrictions. It does not.

### Collapsing mode into recommendation state

When mode is collapsed into recommendation state, recommendation issuance is mistaken for permission to commit or instruct. Recommendation object existence then begins laundering stronger intervention without real mode discipline.

### Allowing commitment in advisory-only mode

When commitment is allowed while advisory-only mode still governs, the platform destroys the boundary between advisory output and binding action and later cannot tell whether commitment was valid.

### Allowing learning in non-learning-ready mode

When learning proceeds while the case is still learning-prohibited, the platform begins adapting from immature, incomparable, or integrity-weakened history as though it were safe learning evidence.

### Allowing instruction during integrity failure

When instruction is allowed during integrity-sensitive recovery posture, the platform turns failure handling into hidden continuation and later loses the boundary between safe action and structurally compromised action.

### Treating review-required mode as though escalation object alone satisfies it

When review-required mode is treated as though the existence of an escalation record settles the matter, the platform forgets that accountable review resolution, not object existence alone, is what permits stronger downstream intervention.

### Domain-local modes overriding shared policy

When domain-local documents invent local mode names or local mode permissions that contradict the shared platform meanings, the canon fragments and cross-domain intervention policy stops meaning the same thing.

### Reopened cases resuming the wrong mode automatically

When reopened, revisited, or reinstated cases resume their prior strongest posture automatically, the platform erases re-entry quality, hides unresolved integrity or review conditions, and treats resumed handling as stronger than it really is.

### Treating prohibited mode as mere low confidence

When prohibited posture is reduced to weak confidence language, the platform loses the distinction between analytically cautious recommendation and governance-level prohibition. That collapse makes stricter control invisible.

### Failing to record governance-relevant mode transitions

When transitions into stronger or weaker intervention posture are left implicit, later review, post-mortem, and learning can no longer reconstruct when the platform actually gained or lost permission to act.

## Non-Negotiables

1. Every material decision episode must preserve explicit or reconstructible mode lineage whenever current intervention posture materially changes what the platform is allowed to do.
2. Mode is not the same thing as stage, and no domain-local stage label may be treated as shared mode authority.
3. Mode is not the same thing as authority, and valid authority may not bypass an active restricted or prohibited mode.
4. Mode is not the same thing as recommendation state, and no recommendation record, approval record, override record, or later-stage object may be treated as automatic mode promotion.
5. Advisory-only output is not the same thing as commitment-permitted mode, and commitment must not occur while advisory-only mode still governs.
6. Review-required mode is not the same thing as escalation record, and accountable review resolution must not be inferred from escalation existence alone.
7. Learning-eligible mode is not the same thing as policy-learning admission by itself, and learning reuse must still satisfy observation maturity, attribution quality, scope validity, comparability discipline, and evidence-admission rules.
8. Recovery mode is not the same thing as ordinary workflow delay, and instruction or learning must not continue through active integrity-sensitive recovery posture as though nothing were wrong.
9. Prohibited mode must remain distinguishable from weak confidence alone, and when mode conflict exists the stricter legitimate posture must govern until explicit resolution occurs.
10. Future mode additions must be placed according to control role, not convenience, and no domain-local extension may redefine the shared platform meaning of a mode.

## Closing Statement

The Fourth Form platform can intervene responsibly only if it preserves not just which objects exist, which stages have been visited, or which authorities are present, but what the system is actually allowed to do now.

This standard therefore fixes the shared decision-mode and intervention-policy grammar for the platform. It ensures that intervention posture remains explicit, that stronger action is never laundered through object existence or workflow convenience, that restricted and prohibited handling remain visible when they matter most, and that future domains inherit one coherent cross-platform rule for when the system may observe, recommend, review, commit, instruct, judge, learn, recover, and re-enter governed handling.