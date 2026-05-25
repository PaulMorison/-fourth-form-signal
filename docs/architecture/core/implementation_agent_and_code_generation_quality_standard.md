# Implementation-Agent and Code-Generation Quality Standard for the Fourth Form Retail Decision Intelligence Platform

## Purpose of This Document

This document defines the shared platform standard for implementation-agent behavior, code-generation quality, AI-assisted refactoring discipline, automated coding workflow quality, and generated-change legitimacy across all current and future shared platform code, domain-local implementation, pipeline logic, orchestration paths, generated tests, refactors, structural rewrites, and maintenance changes.

It exists because the platform now has governing standards for canon navigation, canon change control, code architecture and modularity, build order, testing and validation gates, performance, security, automation posture, commercial value realization, decision-mode control, lifecycle composition, policy-learning evidence admission, interface versioning, cross-domain coordination, failure-state handling, human-review handoff, and approval authority, but it does not yet have one shared rule for how implementation agents and code-generation tools must behave when they turn instructions into code. Without such a rule, the platform will drift into oversized generated modules, vague naming, hidden fixes, buried constants, arbitrary abstraction, brittle glue code, prompt-following without architectural judgment, low-quality "just make it work" patches, and locally successful output that quietly damages future innovation speed.

This document is therefore a control document for implementation-agent and code-generation quality.

It defines the core concepts, canonical implementation expectations, shared implementation grammar, minimum output quality requirements, prompt-to-code discipline rules, review and correction rules, failure-classification and escalation rules, lineage rules, inheritance rules, extension rules, and governance linkage that implementation agents, human reviewers, and future automated coding workflows must follow.

It is the canonical implementation-agent and code-generation quality standard for the platform. Future AI-assisted implementation agents, code-generation tools, automated coding workflows, generated refactors, generated tests, and generated maintenance changes must align with it when preserving replaceability, module legibility, surfaced configuration, reviewable change units, explicit implementation lineage, anti-slop posture, and bounded architectural judgment unless a formal decision record explicitly revises it.

## Role of This Document in the Platform

This document governs the quality-control layer that sits between platform architecture on one side and code produced by implementation agents, code-generation tools, and automated coding workflows on the other.

The canon navigation and reading-order standard defines where shared controls belong and how contributors should resolve overlap, but it does not define how implementation agents must behave when generating code inside those boundaries. The canon change-control and quality-gate standard governs how canonical documents enter and revise the canon, but it does not define how generated implementation must preserve code quality before that implementation is trusted. The code architecture and modularity standard governs what modularity, replaceability, surfaced configuration, and repository legibility mean, but it does not govern the operating discipline of implementation agents while they generate or revise code. The build order and implementation sequence standard governs prerequisite-first build legitimacy, but it does not govern how implementation agents must avoid premature downstream generation. The testing, regression, and validation gate standard governs what proof is needed before changed behavior is trusted, but it does not govern how generated code must be structured so that it is reviewable, correctable, and fit for such validation. The performance, efficiency, and scalability standard governs workload-shape legitimacy, but it does not govern how generated code must expose assumptions rather than bury them. The security and data-protection standard governs security posture, but it does not govern the implementation-agent discipline required to avoid secret burying, unsafe convenience patterns, or opaque generated write paths. The automation and low-admin operating model standard governs governed automation posture, but it does not govern implementation quality inside generated automation code. The commercial value creation and realisation standard governs value pathways, but it does not govern how generated code must preserve clean replacement boundaries so future value-improving change remains cheap enough to perform. The decision-mode and intervention-policy standard governs what intervention postures are legitimate, but it does not govern how generated code must preserve reversible and intelligible implementation surfaces. The end-to-end decision lifecycle composition standard governs how serious decision episodes compose, but it does not govern how generated code must preserve small-part implementation discipline while supporting that composition. The policy-learning evidence admission and update-threshold standard governs when evidence may influence adaptation, but it does not govern code-generation quality. The governed dependency registry and interface versioning standard governs dependency and interface change meaning, but it does not govern how generated code must avoid brittle glue code while consuming those interfaces. The cross-domain coordination and interface contract governs cross-domain coordination semantics, but it does not govern the implementation-agent discipline used to express them in code. The shared exception, anomaly, and failure-state standard governs failure-state meaning after structural problems are elevated, but it does not govern how generated implementation quality problems are classified before they become governed failure objects. The shared human-review packet and intervention handoff standard governs the review packet and intervention handoff structure, but it does not govern the implementation discipline that should trigger such a handoff in the first place.

This standard therefore governs how implementation agents, code-generation tools, and automated coding workflows must behave when producing, modifying, or refactoring code so that generated speed does not become a vector for slop, structural opacity, non-reviewable blast radius, or strategic loss of replaceability.

## Core Thesis

In the Fourth Form platform, implementation agents and code-generation workflows must remain governed implementation servants whose outputs preserve replacement safety, module legibility, surfaced configuration, reviewable change units, and explicit implementation lineage strongly enough that automated speed never outruns engineering quality, architectural judgment, or future innovation speed.

That is the core thesis.

generated code is not the same thing as acceptable code.

speed of output is not the same thing as engineering quality.

modularity is not the same thing as arbitrary fragmentation.

plain language is not the same thing as reduced rigor.

local patch success is not the same thing as long-run replaceability.

passing tests is not the same thing as implementation fitness.

hidden constants are not the same thing as surfaced configuration.

Implementation agents must not be rewarded for producing more code faster if that code becomes harder to replace, harder to review, harder to reason about, or harder to correct later. innovation speed depends on clean replacement boundaries. code that cannot be swapped out easily is a strategic risk.

## What This Standard Is and Is Not

This standard is the shared platform rule for how implementation agents, code-generation tools, and automated coding workflows must produce code that remains legible, reviewable, replaceable, and aligned with governing standards.

This standard is not a substitute for the modularity standard. This standard is not a testing standard. This standard is not a build-order standard. This standard is not a prompt-engineering style note. This standard is not an object standard. This standard is not a local team convention memo. This standard is not a coding-style cheat sheet. This standard is not permission to generate extra abstraction without need. This standard is not permission to sacrifice readability for cleverness. This standard is not permission to bypass approval authority because the output was machine-assisted. This standard is not permission to bury assumptions, patch variables, or convenience constants inside generated logic. This standard is not permission to treat passing tests, local output plausibility, or short-term patch success as proof that the implementation is structurally fit.

The code architecture and modularity standard continues to govern what modularity, replaceability, repository structure, and surfaced configuration mean. The build-order and implementation sequence standard continues to govern what implementation phase is legitimate. The testing, regression, and validation gate standard continues to govern what proof is required before changed behavior is trusted. The security and data-protection standard continues to govern security posture. The performance, efficiency, and scalability standard continues to govern workload legitimacy. The interface and object standards continue to govern their own meanings. This document governs how implementation agents must behave while generating code inside those already-governed meanings.

## Why a Shared Implementation-Agent and Code-Generation Quality Standard Is Necessary

The platform needs one shared implementation-agent and code-generation quality standard because AI-assisted coding changes the speed and volume at which structural mistakes can be produced, copied, and normalized.

If implementation-agent behavior is left local, several failures follow. One contributor accepts a generated 700-line module because it passes tests. Another accepts five tiny files whose fragmentation hides the real dependency path. Another lets an implementation agent bury configuration inside convenience constants because the prompt omitted system structure. Another accepts vague names and silent cross-module coupling because the output looks plausible. Another patches production behavior through hidden flags rather than through surfaced configuration because local output improved. Another lets a generated fix rewrite adjacent code without preserving the original boundary rationale. Another keeps regenerating until the output appears to work, but never asks whether the code remains replaceable, reviewable, or strategically cheap to change later.

The platform therefore needs one shared standard so that every implementation agent, every generated refactor, every generated patch, every generated test surface, and every future coding workflow inherits one anti-slop implementation discipline rather than improvising local rules for what counts as good enough code.

## Core Concepts

### Implementation agent

Implementation agent is any AI-assisted coding system, code-generation workflow, or automated implementation surface that produces, modifies, deletes, restructures, or refactors code or code-adjacent artifacts in response to prompts, instructions, plans, or correction loops.

### Code-generation quality

Code-generation quality is the governed standard of structural fitness, legibility, replaceability, boundary respect, naming clarity, surfaced assumptions, and correction-readiness that generated code must satisfy before it is treated as acceptable implementation.

### Output legitimacy

Output legitimacy is the governed condition in which generated code is structurally fit for review because its purpose, placement, boundaries, naming, assumptions, and correction path are explicit enough to judge seriously.

### Replacement safety

Replacement safety is the governed condition in which a generated module, function, class, or component can be swapped, rewritten, or removed without hidden blast radius or silent dependency collapse.

### Module legibility

Module legibility is the governed condition in which a reader can tell what a module is for, why it exists, what it depends on, what it should not do, and where its boundary ends.

### Atomic function

Atomic function is a function whose purpose is narrow enough, explicit enough, and bounded enough that it can be reasoned about, tested, replaced, and reused without dragging hidden state or mixed responsibilities with it.

### Single-purpose module

Single-purpose module is a module whose reason for existing is coherent enough that a plain-language reader can explain its role in one purpose block without falling into a list of unrelated behaviors.

### Single-purpose class

Single-purpose class is a class whose state, methods, and collaboration surface remain narrow enough that the class expresses one bounded responsibility rather than accumulating convenience behavior.

### Surfaced configuration

Surfaced configuration is configuration, thresholding, switching logic, path selection, and operational behavior exposed at a visible configuration seam rather than buried inside implementation details.

### Hidden fix

Hidden fix is any convenience patch, fallback branch, silent override, or opaque variable introduced to make local output appear correct without openly declaring the structural compromise being made.

### Buried constant

Buried constant is any threshold, identifier, path, toggle, selector, or operational assumption embedded deep enough in code that later readers cannot easily see, justify, or replace it.

### Prompt-to-code discipline

Prompt-to-code discipline is the governed requirement that prompts, generated output, and resulting code structure remain connected through explicit control role, scoped intent, bounded assumptions, and architectural judgment rather than naive prompt obedience.

### Reviewable change unit

Reviewable change unit is a generated change bounded tightly enough that a reviewer can understand its purpose, blast radius, assumptions, and correction path without reverse-engineering half the repository.

### Plain-language purpose statement

Plain-language purpose statement is a short human-readable statement at the start of a function or other implementation unit that explains what it does and why it exists without depending on code inference.

### Refactorability

Refactorability is the governed condition in which generated code can be improved, split, simplified, or replaced later without unraveling hidden assumptions or re-learning buried intent.

### Slop risk

Slop risk is the governed risk that generated output becomes verbose, vague, oversized, brittle, arbitrarily abstracted, poorly named, or structurally opaque enough to slow future engineering.

### Implementation lineage

Implementation lineage is the reconstructible chain linking prompt, scope decision, generated change, reviewer judgment, correction loop, and later rollback or replacement so the platform can reconstruct how a piece of code came to exist.

## Canonical Implementation Expectations

### Module length discipline

The platform requires module length discipline. modules should normally remain under 300 lines unless formally justified. That limit is not a vanity metric. It exists to preserve module legibility, change isolation, and replacement safety. Where a module must exceed that normal limit, the reason must be explicit, bounded, and reviewable rather than assumed acceptable because the output was generated quickly.

### Single-purpose rule

The platform requires the single-purpose rule. Every generated module should serve one coherent reason for existence, and every generated file location should reflect that coherence. folders must reflect logical system structure rather than convenience dumping. Generated code may not use folders as overflow bins for output that lacked a clear home.

### Atomic function rule

The platform requires the atomic function rule. functions should be atomic and easy to replace. A function that mixes orchestration, data access, formatting, state mutation, fallback logic, and error interpretation in one body is not made legitimate by being generated automatically.

### Small-class rule

The platform requires the small-class rule. classes should stay small and single-purpose. Generated classes may not become containers for unrelated convenience methods just because the implementation agent found that shape easy to emit.

### Plain-language function preamble

The platform requires a plain-language function preamble. every function should begin with a 1-3 line plain-language purpose statement. plain language is not the same thing as reduced rigor. The purpose statement exists so later humans and later agents can understand the function boundary before reading the implementation details.

### Plain-language module purpose block

The platform requires a plain-language module purpose block. every module should begin with a 10-20 line plain-language purpose/value block. That block should explain what the module is for, what value path it serves, what it depends on, what it must not absorb, and why its placement is legitimate. This is how module legibility survives code generation volume.

### Surfaced constants and meaningful names

The platform requires surfaced constants and meaningful names. constants and configuration must be surfaced rather than buried deep in code. names must be logical and understandable to humans. meaningful names are part of structural control, not cosmetic polish. hidden constants are not the same thing as surfaced configuration. no buried fix variables are allowed when the real requirement is surfaced constants, explicit configuration, or explicit exception handling.

### Swap-in / swap-out replaceability

The platform requires swap-in / swap-out replaceability. innovation speed depends on clean replacement boundaries. local patch success is not the same thing as long-run replaceability. code that cannot be swapped out easily is a strategic risk. Generated code must preserve anti-monolith discipline, anti-glue-code discipline, and anti-slop posture so future change remains cheap enough to perform.

## Shared Implementation Grammar

### Implementation quality insufficiency

Implementation quality insufficiency is the governed condition in which generated output appears locally useful but remains too oversized, too tangled, too vague, too hidden, too assumption-heavy, or too poorly bounded to qualify as acceptable implementation.

### Human review trigger

Human review trigger is the governed condition in which ambiguity, boundary conflict, structural slop risk, large blast radius, or unresolved quality insufficiency requires accountable human judgment before the generated change may proceed.

### Implementation rollback trigger

Implementation rollback trigger is the governed condition in which generated code that has already been applied must be reversed, narrowed, or replaced because later review shows that the implementation was structurally unfit even if it appeared locally successful at first.

### Agent correction loop

Agent correction loop is the governed cycle in which generated output is reviewed, specific structural problems are named, the implementation agent is directed to correct those problems within a bounded reviewable change unit, and the resulting revision remains linked to the prior attempt rather than erasing it.

These grammar terms exist so future contributors can distinguish code that merely works from code that is fit to stay. generated code is not the same thing as acceptable code. speed of output is not the same thing as engineering quality.

## Minimum Output Quality Requirements

Every generated change must satisfy minimum output quality requirements before it is treated as legitimate implementation.

Generated output must preserve a reviewable change unit. It must preserve clear purpose, bounded scope, meaningful names, surfaced configuration, explicit module placement, and visible correction paths. It must not introduce a hidden fix, a buried constant, or silent boundary expansion just because the prompt was underspecified. It must not use cleverness to hide structural weakness. It must not create arbitrary abstraction, convenience dumping, or brittle glue code in place of bounded architecture.

Low-quality "just make it work" patches are unacceptable. Implementation agents must slow down rather than guess when ambiguity risks slop. Passing tests, passing linters, or producing plausible output cannot rescue structurally weak code. passing tests is not the same thing as implementation fitness.

The platform requires all of the following to remain visible in generated output: module purpose, function purpose, file placement rationale where non-obvious, surfaced constants, explicit configuration seams, meaningful names, clear responsibility boundaries, and an intelligible path for future refactoring or replacement.

## Prompt-to-Code Discipline Rules

Prompt-to-code discipline must remain strict enough that implementation agents do not mistake obedience for judgment.

Prompts used for shared-platform code generation must make the control role explicit, the scope explicit, the affected boundary explicit where relevant, and the expected implementation surface explicit. A prompt that says only "make this work" is structurally inadequate. A prompt that omits whether the requested code belongs in core, interface, object, boundary, or domain-local implementation leaves too much room for slop. An implementation agent must slow down rather than guess when ambiguity risks slop.

Implementation agents may narrow output, emit explicit uncertainty, or trigger human review when scope, placement, authority, or boundary meaning is unclear. They may not silently choose the most convenient structure and then rely on later cleanup. This is not a prompt-engineering style note. It is a control rule for how prompt-following must remain subordinate to architecture and quality.

Prompt-to-code discipline also prohibits false rigor. plain language is not the same thing as reduced rigor. Clear purpose blocks and clear function preambles exist so that later humans can review generated code without decoding hidden intent from raw syntax. This standard does not permit implementation agents to sacrifice readability for cleverness, and it does not permit them to generate extra abstraction without need simply because abstraction looks sophisticated.

## Review and Correction Rules

Generated code must enter review as a bounded, legible, reviewable change unit rather than as an unstructured mass of altered files.

Review must judge more than whether the output compiles or passes a narrow validation slice. Review must judge whether the generated code preserved module length discipline, the single-purpose rule, the atomic function rule, the small-class rule, surfaced constants, meaningful names, logical folder placement, and swap-in / swap-out replaceability. Review must also judge whether the prompt-to-code discipline was adequate or whether the implementation agent filled gaps through guesswork.

When review finds structural weakness, the correct response is not to hide the weakness inside a quick follow-up patch. The correct response is to enter an agent correction loop or human-directed correction path that names the issue explicitly and preserves implementation lineage. Hidden fixes are prohibited. Buried fix variables are prohibited. Review may narrow the scope, split the change, or reject the change entirely when implementation quality insufficiency remains active.

## Failure Classification and Escalation Rules

Implementation quality problems must be classified strongly enough that the platform can tell whether the generated code needs local correction, human review, blocked application, or rollback.

Implementation quality insufficiency covers oversized modules, incoherent class growth, non-atomic functions, vague naming, buried constants, hidden fixes, non-reviewable blast radius, brittle glue code, arbitrary fragmentation, and other structurally unfit output. Some cases may be corrected locally inside a bounded agent correction loop. Some cases should trigger human review immediately because the change touches shared boundaries, introduces broad blast radius, or suggests that the prompt itself was governance-inadequate.

Human review trigger should be treated as mandatory where control-role ambiguity, cross-domain consequence, shared-platform boundary risk, or repeated agent misjudgment remains active. implementation rollback trigger should be treated as mandatory where generated output has already landed and later review shows strategic replaceability damage, hidden boundary expansion, hidden configuration, or other material slop risk.

This section does not redefine failure-state object meaning or human-review packet meaning. Where structural implementation failure must be elevated into governed failure-state handling or governed review-handoff objects, the shared exception, anomaly, and failure-state standard and the shared human-review packet and intervention handoff standard continue to govern those structures.

## Lineage and Auditability Rules

Implementation lineage must remain reconstructible from prompt through generated output, review judgment, correction loop, and later rollback or replacement where relevant.

The platform must be able to reconstruct what was asked for, what control role was assumed, what boundaries were named, what files changed, what purpose blocks and function preambles were introduced, what quality issues were found, what correction loop occurred, and why the final implementation was accepted, rejected, narrowed, or rolled back. Auditability is part of implementation fitness, not a clerical afterthought.

Generated code may be machine-assisted, but it may not be provenance-free. The implementation lineage must remain explicit enough that later reviewers can tell whether a structural weakness arose from the prompt, from the implementation agent, from reviewer negligence, or from a later change that damaged an originally clean boundary.

## Domain Inheritance Rules

Every domain-local implementation surface, shared-platform service, automation path, pipeline change, generated test suite, and refactor path inherits the quality discipline defined here.

Domains must inherit module length discipline, the single-purpose rule, the atomic function rule, the small-class rule, surfaced configuration, meaningful names, reviewable change units, and implementation lineage. They must inherit the rule that implementation agents slow down rather than guess when ambiguity risks slop. They must inherit the rule that passing tests does not rescue structurally weak generated code. They must inherit the rule that replacement safety matters because future innovation speed depends on clean boundaries.

Domains may strengthen the discipline with stricter local limits, stronger human review triggers, stricter lineage requirements, or stronger rollback posture. They may not weaken the shared grammar or redefine implementation quality insufficiency, human review trigger, implementation rollback trigger, or agent correction loop.

## Domain Extension Rules

Valid domain extension may add stricter local purpose-block expectations, narrower module-length thresholds, stronger naming requirements, narrower blast-radius limits, or stronger human review rules where local complexity demands them.

Invalid domain extension includes treating generated code as exempt from the core standards because it was machine-assisted, weakening replaceability requirements because local output appears to work, accepting convenience dumping as if it were architecture, or turning the shared discipline into a prompt library or local style note.

future implementation-agent extensions must be placed according to control role, not convenience.

If an extension changes shared implementation-agent quality grammar, shared output legitimacy rules, shared correction-loop meaning, or shared lineage expectations across the platform, it belongs in core. If it changes interface meaning, object meaning, build-order meaning, testing-gate meaning, security posture, or policy-learning admission, it belongs in those controlling standards instead of here. Extension is allowed. Redefinition is not.

## Governance Linkage

The canon navigation and reading-order standard should treat this file as the controlling reference for how implementation-agent discipline fits within the architecture canon without redefining placement rules. The canon change-control and quality-gate standard should treat it as the controlling reference for how shared implementation-agent quality rules must be validated before they enter canon-adjacent use without replacing canon-entry approval rules. The code architecture and modularity standard should treat it as the controlling reference for how implementation agents must respect modularity, replaceability, surfaced configuration, and anti-monolith discipline without redefining those meanings. The build order and implementation sequence standard should treat it as the controlling reference for how implementation agents must avoid premature downstream generation without redefining phase legitimacy. The testing, regression, and validation gate standard should treat it as the controlling reference for why passing tests does not rescue structurally weak implementation and why generated test code must remain reviewable enough for valid validation later. The performance, efficiency, and scalability standard should treat it as the controlling reference for why generated code must surface assumptions rather than bury workload cost. The security and data-protection standard should treat it as the controlling reference for why generated code must avoid opaque security-sensitive convenience patterns without redefining security posture. The automation and low-admin operating model standard should treat it as the controlling reference for why generated automation code must remain bounded, legible, and rollback-capable without redefining automation posture. The commercial value creation and realisation standard should treat it as the controlling reference for why replacement boundaries are economically material. The decision-mode and intervention-policy standard should treat it as the controlling reference for why implementation agents may not silently create execution logic that outruns governed intervention posture. The end-to-end decision lifecycle composition standard should treat it as the controlling reference for why generated code must preserve lifecycle-supporting boundaries without redefining lifecycle meaning. The policy-learning evidence admission and update-threshold standard should treat it as the controlling reference for why generated implementation must preserve traceability and future evidence usefulness without redefining admission thresholds. The governed dependency registry and interface versioning standard and the cross-domain coordination and interface contract should treat it as the controlling reference for why generated integrations must remain legible and non-brittle without redefining interface meaning. The shared exception, anomaly, and failure-state standard and the shared human-review packet and intervention handoff standard should treat it as the controlling reference for when implementation-quality problems must escalate without redefining those objects.

Changes to shared implementation-agent quality grammar, shared output legitimacy rules, shared review-and-correction rules, shared lineage requirements, or shared rollback triggers are consequential shared-platform changes. Under the governance authority matrix, the stricter applicable approval path governs. In practice this means Architecture Authority review is materially relevant, Implementation Authority review is materially relevant, affected Domain Authority review is materially relevant where domain-local extensions are touched, Governance and Boundary Authority review is materially relevant where generated changes threaten boundary meaning, Commercial Authority review is materially relevant where strategic replaceability or future innovation speed is materially affected, and Platform Owner plus the governing approval path controls when the platform-wide implementation discipline itself is altered.

## Failure Modes in Implementation-Agent and Code-Generation Design

### Velocity theater

The platform celebrates rapid generation volume even though the generated code is oversized, weakly named, poorly bounded, and strategically costly to replace.

### Convenience dumping

Generated files are placed wherever it was easy to emit them rather than where logical system structure says they belong, creating folder sprawl and silent boundary erosion.

### Hidden-fix patching

An implementation agent introduces a hidden fix, fallback branch, or buried variable that makes local output appear correct while concealing the underlying structural problem.

### Buried-constant sprawl

Thresholds, selectors, paths, and toggles are embedded deep in generated logic, making later review, replacement, and environment adaptation slower and more fragile.

### Arbitrary fragmentation

Code is split across many files or layers that add movement without adding clarity, so modularity language is used to justify confusion rather than legibility.

### Glue-code creep

Generated output accumulates brittle adapters, pass-through wrappers, and convenience branches that preserve local success while weakening long-run replaceability.

### Prompt-obedience without judgment

The implementation agent follows an underspecified prompt literally, never slowing down when ambiguity risks slop, and therefore emits code whose structure is convenient rather than legitimate.

### Test-pass complacency

Generated code passes tests and is therefore treated as fit, even though the implementation remains structurally opaque, oversized, or strategically hard to replace.

### Cleverness over readability

Generated code optimizes for compact clever output, dense abstraction, or syntactic sophistication at the expense of human comprehension and correction readiness.

### Lost implementation lineage

Later reviewers cannot reconstruct what prompt created the code, why the structure was chosen, what corrections occurred, or why the change was accepted, so future correction becomes slower and less trustworthy.

## Non-Negotiables

1. generated code is not the same thing as acceptable code, and no machine-assisted output may be treated as legitimate implementation until output legitimacy, reviewability, and control-role fit are visible.
2. speed of output is not the same thing as engineering quality, and implementation agents must slow down rather than guess when ambiguity risks slop.
3. modularity is not the same thing as arbitrary fragmentation, and no generated abstraction may be added without clear single-purpose justification and clear boundary value.
4. hidden constants are not the same thing as surfaced configuration, and constants and configuration must be surfaced with no buried fix variables and no hidden fixes.
5. passing tests is not the same thing as implementation fitness, and no passing test suite may excuse oversized, vague, tangled, or strategically non-replaceable code.
6. modules should normally remain under 300 lines unless formally justified, classes should stay small and single-purpose, and functions should be atomic and easy to replace.
7. every function should begin with a 1-3 line plain-language purpose statement, every module should begin with a 10-20 line plain-language purpose/value block, and names must be logical and understandable to humans.
8. folders must reflect logical system structure rather than convenience dumping, low-quality "just make it work" patches are unacceptable, and code generation must preserve anti-monolith discipline, anti-glue-code discipline, and anti-slop posture.
9. every generated change must remain a reviewable change unit with implementation lineage, a human review trigger where required, an agent correction loop where correction is legitimate, and an implementation rollback trigger where structural weakness is material.
10. future implementation-agent extensions must be placed according to control role, not convenience, and no domain-local or tool-local practice may redefine the shared implementation-agent and code-generation quality grammar.

## Closing Statement

This standard fixes the shared platform rule for how implementation agents, code-generation tools, and automated coding workflows must behave when turning instruction into code. It protects the platform from slop, oversized modules, buried constants, hidden fixes, brittle glue code, vague naming, prompt-following without architectural judgment, and implementation shortcuts that quietly destroy future innovation speed. And it keeps future improvement possible by requiring generated code to remain small-part, reviewable, replaceable, and reconstructible before the platform asks anyone to trust it.