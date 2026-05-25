# Shared Recommendation, Commitment, and Action-Instruction Boundary Standard for the Fourth Form Retail Decision Intelligence Platform

## Purpose of This Document

This document defines the shared platform standard for recommendation context, commitment context, and action-instruction context across all current and future domains.

It exists because the platform now has governed standards for recommendation, approval, override, authority boundaries, stage progression, review resolution, execution observation, decision rationale, materiality and urgency, exception and failure handling, reopened handling, and policy-learning admission, but it still lacks one shared meaning for where advisory output ends, where binding commitment begins, and where executable instruction becomes legitimate.

Without a shared standard, the platform will drift into domain-specific commitment semantics, advisory recommendation text treated as if it were already binding, approval language used as though it were commitment issuance, commitments formed without preserved authority basis, executable instruction inferred from advisory text, instruction issuance detached from upstream recommendation and commitment lineage, superseded commitments disappearing from history, invalidated instructions being silently replaced, unauthorized instruction states being normalized as workflow convenience, and policy-learning behavior that begins adapting from downstream instruction artifacts as though those artifacts proved upstream decision quality.

This document is therefore a control document for shared recommendation, commitment, and action-instruction boundary structure.

It defines the core concepts, shared object meanings, shared grammar, minimum metadata requirements, lineage rules, inheritance rules, extension rules, and governance linkage that all domains must follow when preserving advisory output, binding commitment, executable instruction, readiness boundaries, authority-sensitive transition, supersession, invalidation, downstream execution linkage, and later post-mortem and policy-learning interpretation.

It is the canonical shared recommendation, commitment, and action-instruction boundary standard for the platform. Future domain workflow contracts, recommendation handling, approval and override review, commitment handling, execution preparation, execution comparison, review resolution, post-mortem judgment, and policy-learning reuse must align with it unless a formal decision record explicitly revises it.

## Role of This Document in the Platform

This document governs the shared boundary grammar that sits between recommendation output on one side and binding decision handling, execution preparation, execution reality, later review, and policy-learning interpretation on the other.

The shared recommendation record standard defines what the platform recommended once a case was recommendation-ready, but it does not define one shared meaning for when a recommendation remains advisory only, when a valid recommendation is still non-committable, or when later binding commitment becomes legitimate. The shared override and approval standard defines what humans accepted, deferred, rejected, escalated, or changed before execution, but it does not define one shared meaning for the distinction between approval and commitment or between commitment and executable instruction. The shared capability, authority, and responsibility boundary standard defines advisory capability, binding authority, approval authority, override authority, and unauthorized action state, but it does not define one shared meaning for commitment context, instruction authority linkage, or the downstream lineage between recommendation, commitment, instruction, and execution. The shared progression-gate and stage-transition standard defines readiness movement and downstream entitlement, but it does not define one shared meaning for commitment readiness, instruction readiness, or the controlled boundary between advisory recommendation and executable instruction. The shared review resolution and case disposition standard defines how reviewed paths resolve, defer, return, close, or remain qualified, but it does not define one shared meaning for commitment supersession, commitment revocation where relevant, or instruction invalidation where relevant. The shared execution deviation and outcome standard defines what later happened in reality, but it depends on one stable way to distinguish recommendation weakness, commitment weakness, instruction weakness, and execution weakness. The shared decision rationale and explanation trace standard defines why a path was justified, but it does not define one shared meaning for the distinction between clear rationale and commitment authority. The shared decision materiality, priority, and urgency standard defines the seriousness and timing posture of a case, but it does not define one shared meaning for when a recommendation is commitment-ready or when a commitment is instruction-ready. The shared exception, anomaly, and failure-state standard defines blocked, invalid, quarantined, and integrity-sensitive handling, but it does not define one shared meaning for instruction blocked pending authority, instruction blocked pending prerequisite, instruction blocked pending timing, or unauthorized instruction state. The shared reopen, revisit, and reinstatement standard defines how prior paths legitimately re-enter governed handling, but it does not define one shared meaning for how superseded commitments and invalidated instructions remain distinct without reopening from scratch. The policy-learning evidence admission and update-threshold standard defines when preserved history is admissible for learning, but it depends on one stable way to distinguish instruction issuance from proof of upstream decision quality. The platform governance roles and approval authority matrix defines consequential change authority for the canon itself; this document defines the shared decision-loop boundary semantics that future domains must preserve whenever advisory output, binding commitment, executable instruction, and later execution are connected.

In practical terms, this document governs what recommendation context is, what commitment context is, what action-instruction context is, how advisory output differs from binding commitment, how binding commitment differs from executable instruction, how readiness differs across those layers, what shared grammar all domains must use, what minimum metadata must be preserved, and how later stages may reuse that history without inventing binding legitimacy after the fact.

This document therefore governs recommendation, commitment, and instruction boundary structure as part of platform coherence.

## Core Thesis

In the Fourth Form platform, recommendation context, commitment context, and action-instruction context must remain first-class governed decision-loop structure whose advisory posture, binding posture, executable posture, readiness state, authority linkage, prerequisite posture, supersession or invalidation state, executable scope, and lineage remain explicit enough that the platform can distinguish valid recommendation from binding commitment, valid commitment from executable instruction, instruction readiness from execution success, authorized instruction from unauthorized instruction state, and later execution weakness from upstream decision weakness.

That is the core thesis.

Recommendation is not commitment. Commitment is not action instruction. Approval is not automatically commitment. Commitment is not automatically execution. Advisory output is not the same thing as binding action. Recommendation clarity is not the same thing as commitment authority. Clear rationale is not the same thing as commitment authority. Instruction readiness is not the same thing as execution success. Superseding a commitment is not the same thing as reopening from scratch. Invalidating an instruction is not the same thing as post-mortem judgment. Unauthorized instruction state must remain distinguishable from poor but authorized action. Policy learning must not casually treat instruction issuance as proof that upstream recommendation quality was sound. Policy learning must not casually reuse instruction issuance as if it proved upstream decision quality.

## What This Standard Is and Is Not

This standard is the shared platform rule for how the system records, links, preserves, and reuses governed recommendation context, governed commitment context, and governed action-instruction context.

It is not a workflow note. It is not a UI or output-package specification. It is not a local operations procedure. It is not a product handoff document. It is not an execution playbook. It is not a code schema. It is not an approval form. It is not permission for domains to treat advisory language as if it were already binding. It is not permission for domains to treat approval review as though it automatically issued commitment. It is not permission for domains to treat commitment as though it already issued executable instruction. It is not permission for domains to infer action instruction from advisory text. It is not permission to collapse recommendation, commitment, instruction, execution, review, and post-mortem into one undifferentiated history.

A real shared recommendation, commitment, and action-instruction boundary standard means the platform can answer the following questions for any material decision episode: what the platform recommended; whether that recommendation was advisory only or not-yet-committable; whether any later authority permitted, prohibited, deferred, conditioned, issued, superseded, or revoked commitment; whether any later instruction was permitted, prohibited, conditioned, issued, blocked, invalidated, or unauthorized; what authority basis governed those transitions; what prerequisites or timing conditions still mattered; what executable scope became legitimate; what later execution actually followed; what upstream advisory and binding path remained visible; and whether that preserved history is strong enough for serious post-mortem and policy-learning reuse.

## Why a Shared Recommendation, Commitment, and Action-Instruction Boundary Standard Is Necessary

Domains must not define recommendation, commitment, and action-instruction semantics independently because the platform cannot remain one governed decision system if one domain treats recommendation output as implicitly binding, another treats approval as if it already issued commitment, another treats commitment as if it already authorized execution, another allows instructions with no preserved commitment lineage, another silently replaces superseded commitments, and another learns from instruction issuance as though it proved that the upstream recommendation was sound.

If recommendation, commitment, and instruction grammar is left local, several failures follow. One domain preserves advisory status explicitly while another records only that an action was proposed. One domain preserves commitment authority while another preserves only that approval happened. One domain preserves instruction readiness separately while another assumes commitment made downstream execution automatically legitimate. One domain preserves supersession and invalidation lineage while another overwrites prior binding history. One domain records unauthorized instruction state while another hides it inside ordinary workflow completion. Execution comparison, post-mortem review, and policy learning then inherit incompatible semantics for what was merely recommended, what was actually bound, what was actually instructed, and what later happened in reality.

The platform therefore needs one shared standard so that future domains can extend one governed boundary grammar rather than inventing their own local meanings for advisory output, binding commitment, executable instruction, commitment readiness, instruction readiness, supersession, invalidation, and downstream execution legitimacy.

## Core Concepts

The platform uses the following core concepts.

### Recommendation context

Recommendation context is the governed object context that preserves what advisory output existed for a case, what recommendation status applied, whether the case was recommendation-ready, whether the resulting advisory output was non-committable, and how that advisory path linked forward into later commitment review.

### Commitment context

Commitment context is the governed object context that preserves whether and how a recommendation or reviewed path became a binding commitment under explicit authority, scope, conditions, and lineage.

### Action-instruction context

Action-instruction context is the governed object context that preserves whether and how a binding commitment became an executable instruction under explicit instruction authority, executable scope, blocking conditions, invalidation posture, and lineage.

### Advisory output

Advisory output is the governed decision-support output in which the platform recommends, warns, ranks, routes, or explains a path without by that output alone binding action or issuing executable instruction.

### Binding commitment

Binding commitment is the governed condition in which a valid authority formally binds a decision path, action path, or non-action path for downstream handling under explicit scope and lineage.

### Executable instruction

Executable instruction is the governed condition in which a valid commitment has been translated into an instruction posture that is sufficiently authorized, scoped, and unblocked for legitimate downstream execution handling.

### Recommendation readiness

Recommendation readiness is the governed condition in which the case is mature enough to issue advisory output. Recommendation readiness is not the same thing as the shared commit-ready state or the shared instruction-ready state.

### Commitment readiness

Commitment readiness is the governed condition in which advisory output, review posture, authority posture, scope posture, and prerequisite posture are strong enough that a commitment may legitimately be considered. Commitment readiness is the shared commit-ready state.

### Instruction readiness

Instruction readiness is the governed condition in which a valid commitment, valid instruction authority, executable scope, prerequisite settlement, and timing posture are strong enough that instruction issuance may legitimately be considered. Instruction readiness is the shared instruction-ready state.

### Non-committable recommendation

Non-committable recommendation is the governed condition in which a recommendation may be valid as advisory output while remaining in a not-yet-committable state because authority, prerequisites, scope, timing, or review conditions are still insufficient.

### Non-instruction-ready commitment

Non-instruction-ready commitment is the governed condition in which a binding commitment may legitimately exist while remaining in a not-yet-instruction-ready state because executable prerequisites, timing, instruction authority, or scope conditions are still insufficient.

### Commitment authority

Commitment authority is the governed role basis under which a human authority or other explicitly authorized governed actor may bind a path rather than merely recommend, review, or explain it.

### Commitment authority linkage

Commitment authority linkage is the explicit connection between commitment context and the valid authority boundary that permitted, prohibited, qualified, superseded, revoked, or otherwise governed commitment handling.

### Instruction authority

Instruction authority is the governed role basis under which a valid authority may issue, qualify, block, invalidate, or otherwise govern executable instruction for a bound path.

### Instruction authority linkage

Instruction authority linkage is the explicit connection between action-instruction context and the valid authority boundary that permitted, blocked, qualified, invalidated, or otherwise governed instruction handling.

### Recommendation-to-commitment linkage

Recommendation-to-commitment linkage is the explicit connection between upstream advisory output and the later commitment that adopted, narrowed, changed, deferred, or prohibited that advised path.

### Commitment-to-instruction linkage

Commitment-to-instruction linkage is the explicit connection between a binding commitment and the later instruction path that translated that commitment into executable operational handling.

### Instruction-to-execution linkage

Instruction-to-execution linkage is the explicit connection between issued instruction and the later execution reality, execution deviation, and realized outcome that followed it.

### Superseded commitment

Superseded commitment is the governed condition in which a previously valid commitment is replaced by a later governed commitment under preserved lineage rather than erased from history.

### Invalidated instruction

Invalidated instruction is the governed condition in which a previously issued or prepared instruction is formally withdrawn, blocked, reversed, or rendered non-executable under preserved lineage rather than silently disappearing.

### Unauthorized instruction state

Unauthorized instruction state is the governed condition in which an instruction path, instruction-like act, or execution-preparatory act appears in history without valid instruction authority or valid commitment lineage.

### Commitment breach where relevant

Commitment breach where relevant is the governed condition in which a binding commitment was materially broken, bypassed, or contradicted before legitimate supersession, legitimate revocation, or legitimate execution comparison could explain the change.

## Shared Recommendation Context

At platform level, shared recommendation context is the formal governed context that preserves what advisory output existed for a case and why that output remained advisory unless and until later authority made something stronger legitimate.

It exists because the platform must preserve more than that a recommendation record existed. It must preserve what advisory status applied, whether recommendation readiness was satisfied, whether the recommendation remained non-committable, whether commitment readiness had or had not been reached, what domain and case scope governed that advisory position, what lineage connected that advisory position to later review or commitment handling, and what downstream systems must not infer merely because the advisory output was clear or persuasive.

Shared recommendation context must preserve, conceptually, all of the following. It must preserve a recommendation context ID so the advisory position has stable identity. It must preserve the originating case ID so the advisory position remains anchored to the governed episode. It must preserve a recommendation record reference so later systems can reconstruct what advisory output actually existed. It must preserve an advisory status reference so later systems can tell whether recommendation was issued, withheld, or otherwise bounded. It must preserve commitment-readiness reference where relevant so later systems can tell whether the advisory position was mature enough for commitment review or remained not-yet-committable. It must preserve domain reference so ownership remains explicit. It must preserve lineage or version reference and timestamp so later systems can reconstruct which governed advisory position existed at the relevant time.

Recommendation is not commitment. Advisory output is not the same thing as binding action. Recommendation clarity is not the same thing as commitment authority. Clear rationale is not the same thing as commitment authority. A valid recommendation may still be non-committable. Action instruction must not be inferred from advisory text.

This is governed object meaning, not code schema. Shared recommendation context must remain interpretable as the platform's formal record of advisory position rather than as an implicit commitment placeholder or hidden instruction draft.

## Shared Commitment Context

At platform level, shared commitment context is the formal governed context that preserves whether and how an advisory or reviewed path became binding under explicit authority and explicit conditions.

It exists because the platform must preserve more than that someone approved something. It must preserve what upstream recommendation or reviewed path was being bound, what commitment status applied, what commitment authority existed, what conditions, prerequisites, or review outcomes still mattered, whether commitment readiness had been reached, whether the resulting commitment remained non-instruction-ready, whether any later supersession or revocation occurred, and how later instruction and execution artifacts remained linked to the same governed binding path.

Shared commitment context must preserve, conceptually, all of the following. It must preserve a commitment context ID so the binding position has stable identity. It must preserve the originating case ID so commitment remains anchored to the governed episode. It must preserve upstream recommendation reference so later systems can reconstruct what advisory path the commitment did or did not follow. It must preserve commitment status reference so later systems can tell whether commitment was permitted, prohibited, conditional, issued, deferred, superseded, or otherwise governed. It must preserve commitment authority reference so workflow motion does not get mistaken for binding legitimacy. It must preserve commitment conditions or prerequisites where relevant so later systems can tell what still bounded binding force. It must preserve instruction-readiness reference where relevant so later systems can distinguish valid commitment from executable instruction readiness. It must preserve supersession linkage where relevant so later systems can reconstruct later replacement or formal revocation without erasing earlier binding history. It must preserve lineage or version reference and timestamp so later systems can reconstruct which governed commitment position existed at the relevant time.

Commitment is not action instruction. Approval is not automatically commitment. Commitment is not automatically execution. A valid commitment may still be non-instruction-ready. Superseding a commitment is not the same thing as reopening from scratch. Commitment breach where relevant must remain visible rather than rewritten into ordinary downstream adjustment.

This is governed object meaning, not code schema. Shared commitment context must remain interpretable as the platform's formal record of binding commitment rather than as an approval label, downstream task marker, or informal promise that later systems infer from workflow convenience.

## Shared Action-Instruction Context

At platform level, shared action-instruction context is the formal governed context that preserves whether and how a binding commitment became executable instruction under explicit authority, explicit scope, and explicit blocking posture.

It exists because the platform must preserve more than that downstream execution seemed prepared. It must preserve what upstream recommendation and commitment path existed, what instruction status applied, what instruction authority mattered, what executable scope became legitimate, what prerequisites, authority checks, or timing conditions still blocked issuance, whether instruction readiness had been satisfied, whether any later invalidation occurred, whether any unauthorized instruction state appeared, and how later execution remained reconstructibly linked to the advisory and binding path upstream.

Shared action-instruction context must preserve, conceptually, all of the following. It must preserve an action-instruction context ID so the instruction position has stable identity. It must preserve the originating case ID so instruction remains anchored to the governed episode. It must preserve upstream recommendation reference and upstream commitment reference so later systems can reconstruct the upstream advisory and binding path. It must preserve instruction status reference so later systems can tell whether instruction was permitted, prohibited, conditional, issued, blocked, invalidated, or unauthorized. It must preserve instruction authority reference so downstream execution-preparation behavior does not get mistaken for valid instruction issuance. It must preserve executable scope reference so later systems can tell what population, path, or operational surface the instruction legitimately covered. It must preserve blocking-condition references where relevant so later systems can tell what authority, prerequisite, timing, or integrity limits still mattered. It must preserve invalidation linkage where relevant so later systems can reconstruct how and why instruction later ceased to be valid. It must preserve unauthorized instruction reference where relevant so later systems can distinguish invalid authority from poor but authorized action. It must preserve lineage or version reference and timestamp so later systems can reconstruct which governed instruction position existed at the relevant time.

Commitment is not action instruction. Action instruction must not be inferred from advisory text. Instruction readiness is not the same thing as execution success. Invalidating an instruction is not the same thing as post-mortem judgment. Unauthorized instruction state must remain distinguishable from poor but authorized action.

This is governed object meaning, not code schema. Shared action-instruction context must remain interpretable as the platform's formal record of executable instruction posture rather than as an implementation task queue, downstream job dispatch flag, or local operations shorthand.

## Recommendation, Commitment, and Instruction Grammar

The platform requires one shared cross-domain grammar for recommendation, commitment, and instruction so that future domains inherit stable meanings for advisory output, binding force, executable posture, blocking posture, supersession, invalidation, and unauthorized downstream handling.

### Recommendation issued

Recommendation issued is the shared cross-domain condition in which advisory output has been formally produced under preserved recommendation context.

### Recommendation withheld

Recommendation withheld is the shared cross-domain condition in which advisory output is not yet legitimately issued because recommendation readiness, evidence quality, scope validity, or another governing condition remains insufficient.

### Commitment permitted

Commitment permitted is the shared cross-domain condition in which a path may legitimately enter commitment handling because the relevant authority, scope, readiness, and lineage conditions are preserved strongly enough.

### Commitment prohibited

Commitment prohibited is the shared cross-domain condition in which a path must not enter binding commitment under the present authority, prerequisite, scope, or lineage conditions.

### Commitment conditionally permitted

Commitment conditionally permitted is the shared cross-domain condition in which a path may enter binding commitment only if explicitly preserved authority, review, prerequisite, scope, or timing conditions are satisfied and remain visible.

### Commitment issued

Commitment issued is the shared cross-domain condition in which a valid authority has formally bound a path under preserved commitment lineage.

### Commitment deferred

Commitment deferred is the shared cross-domain condition in which advisory output or reviewed handling remains under consideration, but binding commitment is intentionally postponed because readiness, authority, timing, or prerequisite conditions remain unresolved.

### Commitment superseded

Commitment superseded is the shared cross-domain condition in which a previously valid commitment has been replaced by a later governed commitment while the earlier commitment remains reconstructible.

### Instruction permitted

Instruction permitted is the shared cross-domain condition in which a valid commitment may legitimately progress into executable instruction because instruction authority, executable scope, prerequisite posture, timing posture, and lineage conditions are preserved strongly enough.

### Instruction prohibited

Instruction prohibited is the shared cross-domain condition in which a bound path must not progress into executable instruction under the present authority, prerequisite, scope, or lineage conditions.

### Instruction conditionally permitted

Instruction conditionally permitted is the shared cross-domain condition in which executable instruction may be issued only if explicitly preserved authority, prerequisite, scope, timing, or integrity conditions are satisfied and remain visible.

### Instruction issued

Instruction issued is the shared cross-domain condition in which executable instruction has been formally created under preserved commitment-to-instruction lineage.

### Instruction invalidated

Instruction invalidated is the shared cross-domain condition in which a previously issued or prepared instruction has been formally withdrawn, blocked, reversed, or rendered non-executable under preserved lineage.

### Instruction blocked pending authority

Instruction blocked pending authority is the shared cross-domain condition in which instruction cannot legitimately proceed because the relevant instruction authority, retained authority settlement, or accountable review remains unresolved.

### Instruction blocked pending prerequisite

Instruction blocked pending prerequisite is the shared cross-domain condition in which instruction cannot legitimately proceed because required conditions, dependencies, approvals, inputs, or governing prerequisites remain unsatisfied.

### Instruction blocked pending timing

Instruction blocked pending timing is the shared cross-domain condition in which instruction cannot legitimately proceed because the timing window, urgency posture, sequencing rule, or safe-to-act condition has not yet matured.

### Recommendation advisory only

Recommendation advisory only is the shared cross-domain condition in which a recommendation is valid as advisory output but remains in a not-yet-committable state with no binding force and no implicit instruction entitlement.

### Commitment binding but not yet executable

Commitment binding but not yet executable is the shared cross-domain condition in which a valid commitment exists but remains in a not-yet-instruction-ready state because instruction readiness has not yet been satisfied.

### Executable instruction ready

Executable instruction ready is the shared cross-domain condition in which instruction readiness is satisfied strongly enough that a valid instruction may legitimately enter downstream execution handling.

### Unauthorized instruction state

Unauthorized instruction state is the shared cross-domain condition in which instruction-like handling appears without valid instruction authority or without valid commitment-to-instruction lineage.

These are shared cross-domain meanings. Domains may add narrower subtypes beneath them, but they may not silently replace, blur, or reinterpret them with incompatible local labels such as approved means go, recommendation accepted means committed, send to ops means instructed, or active means executable. Shared recommendation, commitment, and instruction grammar depends on these meanings remaining stable enough that recommendation handling, approval review, execution comparison, post-mortem judgment, and policy-learning reuse can all interpret downstream history coherently across domains.

## Minimum Shared Metadata for Recommendation Context

Every governed recommendation context must carry minimum shared metadata.

### Recommendation context ID

This is the unique stable identifier for the recommendation context.

### Originating case ID

This is the stable reference to the decision case from which the recommendation context arises.

### Recommendation record reference

This is the governed reference to the recommendation record preserved inside the recommendation context.

### Advisory status reference

This is the governed reference stating whether recommendation was issued, withheld, advisory only, or otherwise bounded.

### Commitment-readiness reference where relevant

This is the governed reference stating whether the advisory position was commitment-ready or remained non-committable.

### Domain reference

This is the stable reference to the domain that owns the recommendation context.

### Lineage or version reference

This is the lineage and version reference needed to reconstruct the governing recommendation context later.

### Timestamp

This is the time at which the recommendation context was formed or fixed.

These are minimum shared metadata elements. Domains may extend them, but they may not omit or redefine them when the object is claimed as a governed platform recommendation context.

## Minimum Shared Metadata for Commitment Context

Every governed commitment context must carry minimum shared metadata.

### Commitment context ID

This is the unique stable identifier for the commitment context.

### Originating case ID

This is the stable reference to the decision case from which the commitment context arises.

### Upstream recommendation reference

This is the governed reference to the advisory recommendation path from which commitment handling later proceeded.

### Commitment status reference

This is the governed reference stating whether commitment was permitted, prohibited, conditional, issued, deferred, superseded, revoked where relevant, or otherwise bounded.

### Commitment authority reference

This is the governed reference to the role, authority class, or retained-authority boundary under which commitment could legitimately be formed or denied.

### Commitment conditions or prerequisites where relevant

These are the governed references to any conditions, dependencies, approvals, scope qualifiers, or other prerequisites that still bounded commitment handling.

### Instruction-readiness reference where relevant

This is the governed reference stating whether the binding commitment had reached instruction readiness or remained non-instruction-ready.

### Supersession linkage where relevant

This is the governed linkage to any later superseding commitment or formal revocation that changed the binding path without erasing the earlier commitment.

### Lineage or version reference

This is the lineage and version reference needed to reconstruct the governing commitment context later.

### Timestamp

This is the time at which the commitment context was formed or fixed.

These are minimum shared metadata elements. Domains may extend them, but they may not omit or redefine them when the object is claimed as a governed platform commitment context.

## Minimum Shared Metadata for Action-Instruction Context

Every governed action-instruction context must carry minimum shared metadata.

### Action-instruction context ID

This is the unique stable identifier for the action-instruction context.

### Originating case ID

This is the stable reference to the decision case from which the action-instruction context arises.

### Upstream recommendation reference

This is the governed reference to the upstream advisory recommendation path to which instruction lineage remains anchored.

### Upstream commitment reference

This is the governed reference to the binding commitment from which instruction handling later proceeded.

### Instruction status reference

This is the governed reference stating whether instruction was permitted, prohibited, conditional, issued, blocked, invalidated, executable, or unauthorized.

### Instruction authority reference

This is the governed reference to the role, authority class, or retained-authority boundary under which instruction could legitimately be issued, blocked, or invalidated.

### Executable scope reference

This is the governed reference to the population, path, operational layer, or delivery surface for which instruction became or did not become executable.

### Blocking-condition references where relevant

These are the governed references to any authority, prerequisite, timing, integrity, or scope conditions that blocked legitimate instruction issuance.

### Invalidation linkage where relevant

This is the governed linkage to any later instruction invalidation, withdrawal, or reversal that changed executable posture without erasing earlier instruction history.

### Unauthorized instruction reference where relevant

This is the governed reference stating that an instruction-like state appeared without valid authority or valid upstream commitment lineage.

### Lineage or version reference

This is the lineage and version reference needed to reconstruct the governing action-instruction context later.

### Timestamp

This is the time at which the action-instruction context was formed or fixed.

These are minimum shared metadata elements. Domains may extend them, but they may not omit or redefine them when the object is claimed as a governed platform action-instruction context.

## Lineage Rules

Recommendation, commitment, and instruction artifacts must preserve reconstructible lineage across the middle and back half of the decision loop.

- Recommendation must remain traceable into any later commitment. Recommendation-to-commitment linkage must preserve whether the eventual commitment adopted, qualified, deferred, rejected, or materially changed the advisory path.
- Commitment must remain traceable into any later instruction. Commitment-to-instruction linkage must preserve whether executable instruction followed the binding path directly, only conditionally, after later review, or not at all.
- Instruction must remain traceable into execution. Instruction-to-execution linkage must preserve whether later execution followed the issued instruction, deviated from it, or proceeded despite later invalidation or unauthorized posture.
- No downstream binding action may erase the upstream advisory path. Recommendation context must remain visible even when commitment and instruction later become stronger and more operationally consequential.
- Superseded commitments and invalidated instructions must remain reconstructible. Later binding or executable artifacts must not overwrite prior commitment or instruction history merely because a newer governed path replaced it.
- Unauthorized instruction state must remain explicit. Later execution, later review, and later post-mortem must be able to distinguish instruction weakness from invalid authority.
- Post-mortem must be able to distinguish recommendation weakness, commitment weakness, instruction weakness, and execution weakness. Downstream artifacts must not collapse those questions into one blurred historical judgment.
- Policy learning must not overlearn from commitment or instruction artifacts without preserved upstream lineage. Commitment issuance and instruction issuance are not by themselves proof that upstream recommendation quality, authority discipline, or operational judgment were sound.

Recommendation-to-commitment lineage, commitment-to-instruction lineage, and instruction-to-execution lineage therefore connect advisory judgment, binding decision, executable preparation, later execution reality, later review, and later learning admissibility into one reconstructible chain. If that chain breaks, the platform can no longer tell whether downstream action was legitimately advised, legitimately bound, legitimately instructed, or merely appeared to move forward through local convenience.

## Domain Inheritance Rules

All admitted domains must inherit this shared recommendation, commitment, and action-instruction boundary grammar.

At minimum, every domain-local workflow contract, recommendation-handling design, approval and override review flow, commitment handling, instruction handling, execution comparison design, review-resolution handling, post-mortem design, and policy-learning reuse logic that depends on downstream binding behavior must align with the following rules. Recommendation is not commitment. Commitment is not action instruction. Approval is not automatically commitment. Commitment is not automatically execution. Advisory output is not the same thing as binding action. Recommendation clarity is not the same thing as commitment authority. Clear rationale is not the same thing as commitment authority. Instruction readiness is not the same thing as execution success. A valid recommendation may still be non-committable. A valid commitment may still be non-instruction-ready. Action instruction must not be inferred from advisory text.

Domain-local workflow contracts must therefore inherit this standard rather than inventing their own incompatible meanings for recommendation context, commitment context, action-instruction context, commitment readiness, instruction readiness, supersession, invalidation, unauthorized instruction state, or executable legitimacy.

## Domain Extension Rules

Domains may extend this standard where their operating reality requires richer advisory-status taxonomies, narrower commitment-authority categories, stronger commitment-readiness tests, more detailed prerequisite classes, richer instruction-blocking categories, more precise executable-scope structure, stronger supersession or revocation controls, or tighter invalidation semantics.

Valid domain extension may include narrower commitment-condition classes, more explicit instruction-timing rules, richer unauthorized-instruction diagnostics, stronger readiness maturity checks, more detailed commitment-breach categories where relevant, or more precise execution-comparison linkage beneath the shared grammar.

Domain extension is invalid when it does any of the following. Treats recommendation as commitment. Treats commitment as action instruction. Treats approval as automatically issuing commitment. Treats commitment as automatically authorizing execution. Infers action instruction from advisory text. Treats clear rationale as a substitute for commitment authority. Treats instruction readiness as proof of execution success. Treats commitment supersession as the same thing as reopening from scratch. Treats instruction invalidation as the same thing as post-mortem judgment. Hides unauthorized instruction inside ordinary workflow history. Allows superseded commitments or invalidated instructions to disappear from lineage. Uses local workflow labels to replace recommendation issued, commitment issued, instruction issued, recommendation advisory only, commitment binding but not yet executable, executable instruction ready, or unauthorized instruction state.

Extension is allowed. Redefinition of shared meaning is not.

## Governance Linkage

This standard is directly governance-linked because the platform cannot claim disciplined decisioning if it does not preserve one stable meaning for advisory output, binding commitment, executable instruction, and the authority-sensitive boundaries between them.

The shared recommendation record standard should treat this file as the controlling reference for the distinction between recommendation issuance and later commitment readiness. The shared override and approval record standard should treat it as the controlling reference for the distinction between approval review and actual commitment issuance, and for the rule that approval is not automatically commitment. The shared capability, authority, and responsibility boundary standard should treat it as the controlling reference for commitment authority linkage, instruction authority linkage, and unauthorized instruction state. The shared progression-gate and stage-transition standard should treat it as the controlling reference for the distinction between recommendation readiness, commitment readiness, instruction readiness, and downstream execution entitlement. The shared review resolution and case disposition standard should treat it as the controlling reference for commitment deferral, commitment supersession, commitment revocation where relevant, instruction prohibition, instruction invalidation, and later case settlement that must not erase prior binding history. The shared execution deviation and outcome standard should treat it as the controlling reference for recommendation-to-commitment lineage, commitment-to-instruction lineage, instruction-to-execution lineage, and the later distinction between instruction weakness and execution weakness. The shared decision rationale and explanation trace standard should treat it as the controlling reference for the distinction between clear rationale and commitment authority, and for the rule that advisory explanation must not be mistaken for executable instruction. The shared decision materiality, priority, and urgency standard should treat it as the controlling reference for commitment timing posture, instruction timing posture, safe-to-defer commitment handling, and safe-to-delay instruction handling. The shared exception, anomaly, and failure-state standard should treat it as the controlling reference for instruction blocked pending authority, instruction blocked pending prerequisite, instruction blocked pending timing, invalidated instruction, and unauthorized instruction state. The shared reopen, revisit, and reinstatement standard should treat it as the controlling reference for the rule that superseding a commitment is not the same thing as reopening from scratch and that invalidated instruction history must remain reconstructible when later governed re-entry occurs. The policy-learning evidence admission and update-threshold standard should treat it as the controlling reference for the rule that commitment or instruction issuance must not casually be treated as proof that upstream recommendation quality was sound. Review and approval should align with the platform governance roles and approval authority matrix, especially where shared workflow behavior, binding semantics, execution-preparation semantics, post-mortem interpretation, or policy-learning reuse behavior are affected.

## Failure Modes in Recommendation, Commitment, and Instruction Design

Weak recommendation, commitment, and instruction design creates direct platform risk.

### Advisory recommendation treated as executable instruction

The platform preserves that advice existed, but local workflow behavior or local phrasing causes that advice to be treated as if it already authorized operational action.

### Commitments issued without proper authority

The platform records that a path became binding, but it fails to preserve the valid commitment authority that made that transition legitimate.

### Instruction issued without valid commitment lineage

The platform issues or appears to issue executable instruction, but later systems cannot reconstruct the commitment path that legitimately authorized that instruction.

### Approval mistaken for executable instruction

The platform records that review occurred, but downstream handling mistakes approval review or approval status for commitment issuance or for instruction issuance.

### Commitment supersession erasing the prior path

The platform records only the latest commitment, so later review can no longer reconstruct what earlier binding path was superseded, why it was superseded, or whether the supersession itself was legitimate.

### Invalidated instruction disappearing from history

The platform later treats an instruction as if it never existed rather than preserving that it was once issued or prepared and later invalidated under explicit governed conditions.

### Unauthorized instruction normalized as workflow

The platform records instruction-like downstream activity as ordinary operations history even though valid instruction authority or valid commitment lineage did not exist.

### Execution comparison unable to tell whether the failure was recommendation, commitment, instruction, or execution

The platform observes poor downstream reality, but broken boundary grammar prevents later systems from isolating whether the original advice was weak, whether the binding commitment was flawed, whether the instruction layer was defective, or whether execution departed from legitimate instruction.

### Policy learning overreacting to instruction artifacts without preserved upstream trace

The platform begins adapting future behavior from commitment or instruction frequency, from instruction issuance, or from execution-like downstream artifacts without preserved advisory lineage, authority discipline, or post-mortem support.

## Non-Negotiables

1. Recommendation is not commitment.
2. Commitment is not action instruction.
3. Approval is not automatically commitment.
4. Commitment is not automatically execution.
5. Advisory output is not the same thing as binding action.
6. Clear rationale is not the same thing as commitment authority.
7. Action instruction must not be inferred from advisory text.
8. A valid recommendation may still be non-committable, and a valid commitment may still be non-instruction-ready.
9. Instruction lineage must preserve the upstream recommendation and commitment path, and superseded commitments and invalidated instructions must remain reconstructible.
10. Policy learning must not casually treat instruction issuance as proof that upstream recommendation quality was sound.

## Closing Statement

This standard protects the platform from collapsing advisory intelligence into binding behavior by local convenience.

That protection matters because a serious decision platform must preserve not only what it recommended, what review occurred, what later happened in execution, and what should be learned, but also when the system remained advisory only, when a valid authority actually bound a path, when that binding path became or failed to become executable instruction, when commitment was superseded without erasing the original path, when instruction was invalidated without disappearing from history, and how later post-mortem and policy learning should interpret those boundaries without inventing legitimacy after the fact. Future domains need one shared recommendation, commitment, and action-instruction grammar robust enough that recommendation can stay advisory until valid authority deliberately makes it binding and binding can stay distinct from execution until valid instruction deliberately makes it executable.