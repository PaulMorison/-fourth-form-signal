# Prompt Asset and Instruction Library Governance Standard for the Fourth Form Retail Decision Intelligence Platform

## Purpose of This Document

This document defines the shared platform standard for prompt assets, instruction assets, reusable prompt templates, governed prompt fragments, system-message fragments, evaluation prompts, execution prompts, prompt scope boundaries, prompt admission, prompt versioning, prompt lineage, prompt supersession, prompt deprecation, prompt retirement, library containment, and no silent prompt drift across all current and future platform domains.

It exists because the platform now has governing standards for canon navigation, canon change control, lifecycle composition, code architecture, build order, testing and validation gates, implementation-agent quality, research governance, decision-mode control, glossary usage, dependency and interface governance, shared briefing surfaces, shared human-review handoff, shared assumption handling, shared rationale tracing, and approval authority, but it does not yet have one shared rule for when prompts and reusable instruction assets become durable governed assets rather than local wording conveniences. Without such a rule, the platform will drift into reusable wording treated as architecture without governance, copied prompts whose scope is never declared, system-message fragments mistaken for canonical standards, evaluation prompts mistaken for production instructions, local prompt mutations that silently change downstream behavior, superseded prompts that disappear without lineage, deprecated prompts that remain in live use because their status is invisible, and domain-local prompt notes quietly becoming cross-platform control surfaces without admission discipline.

This document is therefore a control document for prompt asset and instruction library governance.

It defines the core concepts, canonical prompt asset classes, shared prompt and instruction grammar, prompt asset admission rules, naming, scope, and legibility rules, reuse, versioning, and lineage rules, evaluation and readiness rules, supersession, deprecation, and retirement rules, library boundary and containment rules, domain inheritance rules, domain extension rules, governance linkage, failure modes, and non-negotiables that all current and future domains must follow when creating, admitting, revising, reusing, deprecating, superseding, or retiring governed prompt assets and instruction assets.

It is the canonical prompt asset and instruction library governance standard for the platform. Future implementation-agent prompts, reusable instruction assets, shared prompt templates, governed prompt fragments, system-message fragments, evaluation prompts, execution prompts, library-contained prompts, and prompt-library lineage records must align with it when preserving governed prompt asset entry, explicit naming discipline, prompt scope declaration, prompt lineage, prompt versioning, prompt reuse boundary, prompt collision prevention, prompt drift detection, evaluation-ready prompt, admission-ready prompt, deprecation marker, superseded prompt, retired prompt, library audit trace, and no silent prompt drift unless a formal decision record explicitly revises it.

## Role of This Document in the Platform

This document governs the shared control layer that sits between local prompt usage on one side and durable governed prompt-library reuse on the other.

The canon navigation and reading-order standard defines where this control belongs and how overlap is resolved, but it does not define what makes a prompt or instruction asset legitimate for shared reuse. The canon change-control and quality-gate standard governs canonical document admission and revision, but it does not define prompt-library admission or anti-drift prompt revision discipline. The end-to-end decision lifecycle composition standard governs serious decision episode composition, but it does not define when a prompt asset is fit to guide implementation activity. The code architecture and modularity standard governs code structure and replaceability, but it does not govern prompt asset legitimacy. The implementation-agent and code-generation quality standard governs generated-code quality and generated-change legitimacy, but it does not govern how shared prompts themselves are admitted, named, versioned, superseded, or retired. The testing, regression, and validation gate standard governs proof that changed behavior is safe enough to trust, but it does not define prompt-library entry or prompt drift handling. The research and experimentation governance standard governs exploratory trials and their containment, but it does not define when prompts become governed reusable library assets. The decision-mode and intervention-policy standard governs allowed intervention posture, but it does not define reusable prompt-library control. The glossary and canonical term usage standard governs canonical vocabulary, but it does not define how prompts preserve vocabulary while remaining governed assets. The build order and implementation sequence standard governs prerequisite-first construction, but it does not define prompt-library sequencing or prompt dependency legitimacy by itself. The policy-learning evidence admission and update-threshold standard governs evidence-to-adaptation legitimacy, but it does not define prompt admission or prompt versioning. The governed dependency registry and interface versioning standard and the cross-domain coordination and interface contract govern dependency and interface meanings, but they do not define prompt-library boundary control. The shared briefing, human-review, assumption, and rationale object standards govern shared object meaning, but they do not define prompt asset legitimacy or library containment. Domain-local notebooks, scratchpads, or temporary prompt notes may still exist where local work demands them, but they do not become governed prompt assets merely because they were useful once.

This document therefore governs when prompts and reusable instruction assets become legitimate shared control surfaces, how their meaning remains bounded and visible, and how reuse occurs without allowing silent prompt drift, prompt collision, uncontrolled prompt sprawl, or architecture-by-convenience through copied wording.

## Core Thesis

In the Fourth Form platform, shared prompt assets and instruction assets must remain governed reusable control surfaces whose scope, wording, lineage, admission state, revision visibility, and retirement posture remain explicit enough that reusable language never outruns canonical meaning, implementation discipline, validation discipline, or human reviewability.

That is the core thesis.

a prompt asset is not the same thing as architecture by itself.

prompt reuse is not the same thing as semantic safety.

wording convenience is not the same thing as governed reuse.

a system prompt is not the same thing as a canonical standard.

prompt evaluation is not the same thing as prompt admission.

prompt supersession is not the same thing as silent abandonment.

domain-local prompt usage is not the same thing as shared-library control.

future prompt-library extensions must be placed according to control role, not convenience.

Not every useful prompt belongs in the governed library. Prompts must have named scope and purpose. Reusable prompt fragments must not silently redefine canon meaning. Prompt changes must remain visible. Silent prompt mutation is unacceptable.

## What This Standard Is and Is Not

This standard is the shared platform rule for how prompt assets and instruction assets become governed, how their scope and naming remain explicit, how their reuse stays lineage-safe, how their evaluation and admission remain distinct, and how their supersession, deprecation, retirement, and containment remain visible.

this is not an implementation-agent quality standard.

this is not a glossary replacement.

this is not a prompt-writing style guide.

this is not a domain-local prompt notebook convention.

this is not permission for uncontrolled prompt sprawl.

this is not permission to treat reusable wording as governed architecture automatically.

This standard is not a canon change-control standard. This standard is not a testing-regression standard. This standard is not an interface contract standard. This standard is not an object standard. This standard is not a local convenience memo. This standard is not permission to let system prompts silently redefine platform meaning. This standard is not permission to let fragments, templates, or copied instructions outrun human legibility.

The implementation-agent and code-generation quality standard continues to govern generated-code quality. The glossary and canonical term usage standard continues to govern canonical term meaning. The canon change-control and quality-gate standard continues to govern canonical document admission. The testing, regression, and validation gate standard continues to govern validation sufficiency. The research and experimentation governance standard continues to govern exploratory prompt trials while they remain experimental. The interface and object standards continue to govern their own meanings. This document governs the prompt-library posture that sits around those meanings without redefining them.

## Why a Shared Prompt Asset and Instruction Library Governance Standard Is Necessary

The platform needs one shared prompt asset and instruction library governance standard because implementation agents, code-generation workflows, and future automated coding surfaces depend on reusable language, but reusable language becomes dangerous when it is copied, mutated, or promoted into shared control without explicit scope, explicit naming, explicit lineage, explicit evaluation posture, and explicit retirement posture.

If prompt governance is left local, several failures follow. One contributor treats a useful local prompt as if that alone made it a shared asset. Another copies a system-message fragment into multiple workflows and later changes one copy without realizing the shared meaning diverged. Another stores a prompt in a notebook, scratchpad, or chat transcript and later treats it as if it were library-controlled. Another creates an evaluation prompt that gradually becomes an execution prompt without explicit admission review. Another changes prompt wording after a successful run and loses the ability to explain why later behavior changed. Another reuses a fragment whose wording quietly redefines canonical terms that belong to the glossary instead. Another lets multiple prompt assets claim the same purpose under near-identical names and produces prompt collision. Another retires a prompt informally by stopping use rather than marking its status, and later contributors revive it without realizing it was superseded. Another treats prompt reuse as if reuse alone proved safety. Another lets locally helpful wording accumulate until the platform inherits prompt sprawl rather than governed instruction assets.

The platform therefore needs one shared standard so that every current and future domain inherits one coherent rule for governed prompt asset entry, explicit naming discipline, prompt scope declaration, prompt versioning, prompt reuse boundary, prompt collision prevention, prompt drift detection, evaluation readiness, admission readiness, supersession handling, deprecation handling, retirement handling, library audit trace, and no silent prompt drift rather than improvising local prompt habits.

## Core Concepts

### Prompt asset

Prompt asset is a governed prompt whose wording, scope, purpose, lineage, version state, and reuse status are preserved as a controlled platform artifact.

### Instruction asset

Instruction asset is a governed instruction artifact that tells an implementation agent or related workflow how prompts should be composed, sequenced, constrained, or interpreted within a defined control role.

### Reusable prompt template

Reusable prompt template is a prompt asset designed for repeated use across more than one case, task, contributor, or automation path under an explicit scope boundary and explicit reuse boundary.

### Governed prompt fragment

Governed prompt fragment is a reusable prompt component, including a system-message fragment where relevant, whose wording is controlled strongly enough that it may be inserted into broader prompts without losing lineage, scope, or meaning.

### Prompt scope boundary

Prompt scope boundary is the explicit statement of what task class, control role, domain, agent surface, or workflow condition a prompt asset is permitted to serve.

### Prompt lineage

Prompt lineage is the reconstructible chain linking a prompt asset or instruction asset to its origin, revisions, evaluations, admissions, supersessions, deprecations, retirements, and downstream governed reuse.

### Prompt version

Prompt version is the explicit governed state of a prompt asset or instruction asset at a particular point in its lineage.

### Prompt admission

Prompt admission is the formal gate by which a prompt candidate becomes a governed library asset under explicit naming, explicit scope, explicit lineage, and explicit reuse discipline.

### Prompt supersession

Prompt supersession is the governed condition in which a newer prompt version or successor asset becomes the preferred controlled reference while the older asset remains historically identifiable.

### Prompt deprecation

Prompt deprecation is the governed condition in which a prompt remains historically visible and still interpretable but is no longer recommended for new use.

### Prompt retirement

Prompt retirement is the governed condition in which a prompt asset is removed from active reuse eligibility while remaining visible enough for lineage, audit, and historical interpretation.

### Prompt drift

Prompt drift is the condition in which a prompt asset's meaning, scope, behavior, or implied control role changes through local editing, local copying, or informal reinterpretation without explicit governed revision.

### Prompt collision

Prompt collision is the condition in which multiple prompt assets, fragments, or templates overlap in name, role, scope, or authority strongly enough that contributors cannot tell which one should govern.

### Evaluation prompt

Evaluation prompt is a prompt asset used to test, compare, or judge prompt or implementation behavior rather than to execute ordinary governed work directly.

### Execution prompt

Execution prompt is a prompt asset used to direct actual implementation, refactoring, analysis, or other active governed work within an approved scope boundary.

### Library-contained prompt

Library-contained prompt is a prompt asset that has been admitted into the governed library and remains subject to explicit naming, scope, lineage, status marking, and containment rules.

### No-silent-prompt-drift rule

No-silent-prompt-drift rule is the rule that governed prompt assets may not change wording, meaning, scope, or control role through untraced local mutation, copied divergence, or undocumented replacement.

## Canonical Prompt Asset Classes

### Local prompt candidate

Local prompt candidate is a prompt that may be useful for one contributor, one temporary task, or one exploratory session but has not yet satisfied governed prompt admission conditions. Not every local prompt candidate should become a library asset.

### Shared execution prompt asset

Shared execution prompt asset is a governed execution prompt intended for repeated use in active implementation, refactoring, analysis, or operationally relevant work under explicit scope and explicit reuse boundaries.

### Shared evaluation prompt asset

Shared evaluation prompt asset is a governed evaluation prompt used to judge prompt behavior, implementation quality, or readiness posture without being mistaken for an execution prompt by itself.

### Reusable prompt template asset

Reusable prompt template asset is a governed template that allows bounded reuse across multiple cases while preserving explicit placeholders, explicit scope, and explicit lineage.

### Governed prompt fragment asset

Governed prompt fragment asset is a reusable fragment, including a system-message fragment where relevant, that is admitted for controlled inclusion inside larger prompts without being mistaken for a full prompt asset by itself.

### Library-contained instruction asset

Library-contained instruction asset is a governed instruction asset that constrains prompt composition, sequencing, admissible behavior, or review posture across more than one prompt asset or workflow.

### System-message fragment asset

System-message fragment asset is a governed prompt fragment intended for insertion into system-level instruction surfaces under explicit scope and explicit versioning, with the understanding that a system prompt is not the same thing as a canonical standard.

## Shared Prompt and Instruction Grammar

### Governed prompt asset entry

Governed prompt asset entry is the condition in which a prompt candidate has named purpose, explicit naming discipline, prompt scope declaration, prompt lineage, prompt versioning posture, reuse boundary, and status visibility strong enough to enter prompt admission review.

### Explicit naming discipline

Explicit naming discipline is the requirement that prompt assets and instruction assets carry names that make their role, scope, and intended use legible enough that collision and misuse become visible before reuse occurs.

### Prompt scope declaration

Prompt scope declaration is the explicit statement of where the prompt may be used, what it is for, what it is not for, and what adjacent governed meanings it must not silently redefine.

### Prompt lineage

Prompt lineage is the reconstructible record connecting prompt origin, status, revisions, evaluations, admissions, supersessions, deprecations, retirements, and downstream governed reuse.

### Prompt versioning

Prompt versioning is the governed practice of making prompt changes explicit enough that later contributors can tell which version was used, which version is current, and what materially changed.

### Prompt reuse boundary

Prompt reuse boundary is the explicit boundary describing which tasks, teams, domains, workflows, or agent surfaces may reuse a prompt asset without fresh admission.

### Prompt collision prevention

Prompt collision prevention is the discipline of naming, scoping, and class separation that keeps overlapping prompts from becoming ambiguous shared authorities.

### Prompt drift detection

Prompt drift detection is the requirement that prompt changes, copied divergence, or unauthorized scope shifts become visible quickly enough that governed meaning does not silently move.

### Evaluation-ready prompt

Evaluation-ready prompt is a prompt candidate whose target behavior, scope, success criteria, and comparison posture are explicit enough to support serious evaluation.

### Admission-ready prompt

Admission-ready prompt is a prompt candidate whose naming, scope, purpose, lineage, human legibility, evaluation evidence, and reuse rationale are explicit enough to justify governed library admission.

### Deprecation marker

Deprecation marker is the explicit status marking that tells future contributors a prompt remains historically visible but should not be selected for new use except under named exceptions.

### Superseded prompt

Superseded prompt is a still-identifiable prior prompt asset that has been replaced by a newer governed asset through explicit lineage rather than disappearance.

### Retired prompt

Retired prompt is a historically visible prompt asset that has been removed from active reuse eligibility and must not be treated as current governed guidance.

### Library audit trace

Library audit trace is the reconstructible trace linking prompt admission, revisions, evaluation evidence, approvals where relevant, supersession, deprecation, retirement, and later usage consequences.

### Human review trigger where relevant

Human review trigger where relevant is the condition in which prompt consequence, ambiguity, canon overlap, scope expansion, or status transition is serious enough that accountable human review must intervene.

### No silent prompt drift

No silent prompt drift is the rule that governed prompt assets may not be revised, copied, reclassified, superseded, or informally replaced in ways that conceal the fact of change.

These grammar terms exist so the platform can distinguish a locally helpful prompt from a governed shared prompt asset clearly enough to preserve meaning, reuse discipline, and human reviewability. prompt reuse is not the same thing as semantic safety. wording convenience is not the same thing as governed reuse. prompt evaluation is not the same thing as prompt admission.

## Prompt Asset Admission Rules

Not every useful prompt belongs in the governed library. Prompt admission must be stricter than local usefulness. A prompt candidate may not enter the governed library merely because it solved one task, produced one good response, or felt reusable to one contributor.

Governed prompt asset entry requires named purpose, explicit naming discipline, prompt scope declaration, prompt class, prompt reuse boundary, prompt lineage posture, prompt versioning posture, human legibility, and evaluation posture appropriate to the asset's role. Prompts must have named scope and purpose. Shared prompt assets must be understandable by humans, not just runnable by agents.

Prompt candidates that remain too local, too implicit, too context-dependent, too ambiguous, too collision-prone, or too opaque to review must remain outside the governed library. That is not a defect. It is a legitimate local-use state. It becomes a defect only when local usefulness is silently inflated into shared-library legitimacy.

Reusable prompt fragments must not silently redefine canon meaning. A fragment, template, or instruction asset that changes the apparent meaning of canonical terms, canonical boundaries, or canonical authority must be rejected, narrowed, or rewritten before admission. a prompt asset is not the same thing as architecture by itself.

## Naming, Scope, and Legibility Rules

Governed prompt assets must be named strongly enough that contributors can tell what class of asset they are reading, what problem they serve, what scope they inherit, and what they must not be mistaken for. Explicit naming discipline exists to prevent prompt collision and false authority.

Prompt scope declaration must remain visible wherever the asset is stored or referenced. A governed prompt asset must say whether it is an execution prompt, an evaluation prompt, a reusable prompt template, a governed prompt fragment, a system-message fragment asset, or an instruction asset. It must say what domain or cross-domain surface it serves. It must say whether it is local, shared, deprecated, superseded, or retired.

Word choice must remain legible to humans. Shared prompt assets must be understandable by humans, not just runnable by agents. Wording convenience is not the same thing as governed reuse. A prompt that cannot be interpreted clearly by a human reviewer is not ready to govern repeated use.

Naming and scope must also preserve separation from adjacent standards. A prompt name may support architecture, glossary usage, testing posture, or implementation discipline, but it may not pretend to own those meanings. a system prompt is not the same thing as a canonical standard.

## Reuse, Versioning, and Lineage Rules

Prompt reuse must preserve lineage. Copying a prompt into a new surface without preserving its identity, version, or status creates prompt drift risk even when the wording looks only slightly different. prompt reuse is not the same thing as semantic safety.

Every governed prompt asset and instruction asset must carry explicit prompt versioning and prompt lineage strong enough that later contributors can reconstruct what changed, why it changed, what version was used, and what successor or predecessor relationships remain active. Prompt changes must remain visible. Silent prompt mutation is unacceptable.

Prompt reuse boundary must remain explicit. A prompt admitted for one workflow, one class of implementation task, one domain, or one review surface does not automatically become valid for every other case. domain-local prompt usage is not the same thing as shared-library control. Reuse across broader scope requires either explicit permission within the asset's scope declaration or new admission review.

Superseded prompts, deprecated prompts, and retired prompts must remain historically identifiable in prompt lineage. Later contributors must be able to tell whether a prompt was copied from a current asset, from a superseded prompt, from a deprecated prompt, or from a retired prompt. If that difference is invisible, the library has failed its governance role.

## Evaluation and Readiness Rules

Prompt evaluation must remain distinct from prompt admission. prompt evaluation is not the same thing as prompt admission. Evaluation asks whether a prompt behaves reliably enough for serious judgment. Admission asks whether a prompt has earned governed reusable status.

Evaluation prompts and execution prompts must remain distinguishable. An evaluation prompt may test prompt behavior, code-generation behavior, or revision quality, but it may not silently become the governing execution prompt for ordinary use without admission review. An execution prompt may support active work, but it does not become evaluation evidence merely because it was used often.

An evaluation-ready prompt must have clear target behavior, clear scope, clear comparison basis where relevant, and clear interpretation posture. An admission-ready prompt must satisfy those evaluation expectations where relevant and must also have explicit naming, explicit scope, explicit lineage, explicit versioning, explicit reuse rationale, explicit human legibility, and status markings strong enough for durable reuse.

Evaluation of prompt assets must remain tied to adjacent controls without being absorbed by them. The testing, regression, and validation gate standard continues to govern whether changed code and changed behavior are safe enough to trust. The implementation-agent and code-generation quality standard continues to govern whether generated code is structurally fit. This document governs when prompt evidence is strong enough for prompt-library admission and reuse.

## Supersession, Deprecation, and Retirement Rules

Prompt supersession must remain explicit. prompt supersession is not the same thing as silent abandonment. When a prompt asset is replaced, the successor must be named, the prior asset must remain historically identifiable, and the supersession reason must remain reconstructible.

Deprecated prompts must remain distinguishable from retired prompts. Deprecation means the prompt is no longer recommended for new use but remains historically interpretable and may still require controlled reference. Retirement means the prompt is no longer eligible for active governed reuse. Deprecated prompts must remain distinguishable from retired prompts because their operational meaning is not the same.

Superseded prompts must remain historically identifiable. Deprecated prompts must remain marked. Retired prompts must remain visible enough for lineage and audit. The library may not erase prior prompt states merely because a newer wording looks better. Silent abandonment destroys prompt lineage, weakens auditability, and creates uncontrolled revival risk.

Status transitions must trigger human review where relevant when the asset affects shared control posture, broad reuse scope, or canon-adjacent meaning. Status change by convenience is unacceptable.

## Library Boundary and Containment Rules

The governed library must remain bounded. Not every useful prompt belongs in the governed library, and not every reusable-looking instruction should become a library-contained prompt. The library exists for durable shared control surfaces, not for every locally successful wording pattern.

Library-contained prompts must remain distinguishable from local prompt notes, local notebooks, local scratchpads, chat transcripts, and experimental prompt candidates. This standard is not a domain-local prompt notebook convention. Experimental prompts may exist under research governance. Local prompts may exist for temporary work. Neither becomes a governed library asset without prompt admission.

Reusable prompt fragments must not silently redefine canon meaning. A governed prompt fragment may support canonical standards, but it may not replace them. a system prompt is not the same thing as a canonical standard. A prompt asset may help an implementation agent follow architecture, glossary, testing, or decision-mode controls, but it does not become the architecture, glossary, testing rule, or decision-mode rule by itself.

Library containment also requires prompt collision prevention, prompt drift detection, visible status markers, and explicit reuse boundaries strong enough that prompt sprawl is actively resisted. This standard is not permission for uncontrolled prompt sprawl. This standard is not permission to treat reusable wording as governed architecture automatically.

## Domain Inheritance Rules

Every domain-local implementation surface, shared-platform workflow, prompt-consuming automation path, and future implementation-agent surface inherits the grammar, naming, scope, lineage, versioning, status marking, and anti-drift rules defined here whenever a prompt or instruction asset is intended for durable shared reuse.

Domains must inherit the rule that prompts must have named scope and purpose. They must inherit the rule that shared prompt assets must be understandable by humans, not just runnable by agents. They must inherit the rule that prompt changes must remain visible. They must inherit the rule that reusable prompt fragments must not silently redefine canon meaning. They must inherit the rule that silent prompt mutation is unacceptable.

Domains may keep local prompt candidates, experimental prompts, notebooks, or scratchpad prompts outside the governed library where local work requires them. domain-local prompt usage is not the same thing as shared-library control. Domains may strengthen prompt governance locally with stricter naming, stricter evaluation evidence, stricter review triggers, or narrower reuse boundaries. They may not weaken the shared grammar or redefine prompt admission, prompt versioning, prompt deprecation, prompt retirement, or no-silent-prompt-drift rule.

## Domain Extension Rules

Valid domain extension may add narrower local prompt classes, stricter metadata requirements, stricter evaluation evidence, narrower reuse boundaries, stronger human review triggers, stronger deprecation handling, or stronger retirement controls where domain complexity demands them.

Invalid domain extension includes treating ad hoc prompt folders as if they were the governed library, weakening version visibility because local teams prefer speed, letting system-message fragments substitute for canonical standards, turning evaluation prompts into execution prompts without admission review, or treating copied wording as if reuse alone proved safety. future prompt-library extensions must be placed according to control role, not convenience.

If an extension changes shared prompt asset meaning, shared admission grammar, shared status semantics, shared lineage expectations, or shared anti-drift rules across the platform, it belongs in core. If it changes implementation-agent quality, glossary authority, testing gates, interface meaning, object meaning, research containment, or policy-learning admission, it belongs in those controlling standards instead of here. Extension is allowed. Redefinition is not.

## Governance Linkage

The canon navigation and reading-order standard should treat this file as the controlling reference for where prompt-library governance belongs in the architecture canon without redefining placement rules. The canon change-control and quality-gate standard should treat it as the controlling reference for how prompt assets enter durable governed reuse without replacing canonical document admission rules. The code architecture and modularity standard should treat it as the controlling reference for how prompts may support modular code generation without redefining architectural meaning. The implementation-agent and code-generation quality standard should treat it as the controlling reference for prompt-asset legitimacy, lineage, and anti-drift discipline without replacing generated-code quality rules. The testing, regression, and validation gate standard should treat it as the controlling reference for why prompt evaluation must remain distinct from downstream validation while still respecting validation evidence. The research and experimentation governance standard should treat it as the controlling reference for how experimental prompts differ from admitted library prompts without replacing research containment rules. The decision-mode and intervention-policy standard should treat it as the controlling reference for why prompts must not silently instruct implementation agents to outrun governed intervention posture. The glossary and canonical term usage standard should treat it as the controlling reference for how prompt assets preserve canonical wording without redefining canonical vocabulary authority. The build order and implementation sequence standard should treat it as the controlling reference for why foundational prompt assets should stabilize before downstream prompt assets depend on them. The policy-learning evidence admission and update-threshold standard should treat it as the controlling reference for why prompt revision based on accumulated evidence still requires explicit admission and versioning rather than silent mutation. The governed dependency registry and interface versioning standard and the cross-domain coordination and interface contract should treat it as the controlling reference for how prompt assets may reference shared interfaces without redefining interface semantics. The shared briefing, digest, and summary surface standard, the shared human review packet and intervention handoff standard, the shared assumption, hypothesis, and inference register standard, and the shared decision rationale and explanation trace standard should treat it as the controlling reference for how prompts may help populate those surfaces without redefining their object semantics.

Changes to shared prompt asset classes, shared prompt admission grammar, shared prompt status meanings, shared lineage requirements, shared anti-drift rules, or shared prompt-library boundary rules are consequential shared-platform changes. Under the governance authority matrix, the stricter applicable approval path governs. In practice this means Architecture Authority review is materially relevant, Implementation Authority review is materially relevant, Governance and Boundary Authority review is materially relevant where prompt reuse threatens shared meaning or containment, affected Domain Authority review is materially relevant where domain inheritance or extension is touched, and Platform Owner plus the governing approval path controls when the platform-wide prompt-library discipline itself is altered.

## Failure Modes in Prompt Asset and Instruction Library Governance

### Silent prompt drift without lineage

The platform copies or edits prompt assets locally until materially different wording is in active use, but the library cannot reconstruct what changed, when it changed, or why it changed.

### Wording convenience treated as governed reuse

The platform promotes a locally helpful wording pattern into shared use without explicit naming, scope, status, or admission discipline, and later contributors mistake convenience for authority.

### System-message fragments mistaken for canonical standards

The platform begins treating system-message fragments or reusable instruction fragments as if they owned canonical meaning, and prompt wording quietly overrides standards that should remain controlled elsewhere.

### Prompt evaluation confused with prompt admission

The platform observes that a prompt performed well in limited evaluation and then treats that prompt as governed reusable library property even though scope, naming, lineage, and status discipline remain incomplete.

### Prompt collision through weak naming and weak scope

The platform allows multiple prompt assets to claim similar names, similar roles, or similar authority boundaries, and contributors can no longer tell which prompt is current or legitimate.

### Reusable fragments redefining canon meaning

The platform reuses fragments whose wording quietly shifts glossary meaning, architecture boundary meaning, testing posture, or decision-mode posture, and copied fragments become vectors for semantic drift.

### Supersession by disappearance

The platform stops using one prompt and starts using another without marking supersession, deprecation, or retirement, and historical interpretation becomes guesswork instead of lineage.

### Domain-local prompts leaking into shared control

The platform copies prompts from notebooks, scratchpads, transcripts, or local folders into broader reuse without admission review, and domain-local convenience silently becomes shared-library behavior.

### Prompt reuse outrunning reuse boundary

The platform reuses a prompt outside its declared scope because the wording looked generally applicable, and downstream tasks inherit assumptions or constraints that were never admitted for them.

### Uncontrolled prompt sprawl

The platform stores too many near-duplicate prompts, too many weakly bounded fragments, and too many under-governed instruction assets, until the library becomes a cluttered convenience store rather than a governed control surface.

## Non-Negotiables

1. Not every useful prompt belongs in the governed library, and prompt admission must remain stricter than local usefulness.

2. Every governed prompt asset and instruction asset must have explicit naming discipline, prompt scope declaration, named purpose, and status visibility before shared reuse is legitimate.

3. Shared prompt assets must be understandable by humans, not just runnable by agents, because opaque prompt wording is not fit to govern repeated use.

4. Reusable prompt fragments must not silently redefine canon meaning, and a prompt asset is not the same thing as architecture by itself.

5. Prompt reuse must preserve prompt lineage, prompt versioning, and prompt reuse boundary, because prompt reuse is not the same thing as semantic safety.

6. Prompt changes must remain visible, silent prompt mutation is unacceptable, and the no-silent-prompt-drift rule applies to prompts, templates, fragments, and instruction assets alike.

7. Evaluation prompts and execution prompts must remain distinguishable, because prompt evaluation is not the same thing as prompt admission.

8. Superseded prompts must remain historically identifiable, deprecated prompts must remain distinguishable from retired prompts, and prompt supersession is not the same thing as silent abandonment.

9. Domain-local prompt usage is not the same thing as shared-library control, and future prompt-library extensions must be placed according to control role, not convenience.

10. A system prompt is not the same thing as a canonical standard, wording convenience is not the same thing as governed reuse, and this standard is not permission for uncontrolled prompt sprawl.

## Closing Statement

The Fourth Form platform depends on reusable language, but reusable language only becomes trustworthy when its role, scope, lineage, and status remain explicit enough that shared prompts stay governed rather than folkloric. Prompt assets and instruction assets are legitimate platform control surfaces only when admission, reuse, supersession, deprecation, retirement, and anti-drift posture remain visible.

This standard therefore keeps prompt-library reuse useful without allowing prompts to masquerade as architecture, glossary authority, testing proof, or local convenience writ large. If the discipline defined here remains strong, the platform gains reusable prompt leverage without semantic drift. If it weakens, copied wording will quietly become an uncontrolled architecture of its own.