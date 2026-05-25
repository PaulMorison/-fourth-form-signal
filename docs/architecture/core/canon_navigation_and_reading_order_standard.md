# Canon Navigation and Reading-Order Standard for the Fourth Form Retail Decision Intelligence Platform

## Purpose of This Document

This document defines the shared platform standard for navigating the architecture canon, reading the canon in coherent order, placing future standards into the correct architecture folder, and resolving apparent overlap among canonical architecture documents.

It exists because the platform now has canonical core architecture documents, shared object standards, boundary controls, interface controls, reusable domain-pattern guidance, and domain-local contracts, but it still lacks one shared meaning for how those documents should be approached as one governed canon rather than as an unordered document set. Without a navigation standard, the platform will drift into contributors reading downstream documents before foundational ones, local summaries being mistaken for controlling authority, folder placement being treated as cosmetic rather than structural, overlapping standards being resolved by personal preference rather than canon rule, and canonical additions appearing in the repository without consistent memory or placement discipline.

This document is therefore a control document for canon navigation and reading-order discipline.

It defines the core concepts, canon structure, reading order, dependency order, placement rules, overlap and conflict-resolution rules, canon extension rules, and governance linkage that all contributors must follow when approaching, extending, interpreting, or organizing the architecture canon.

It is the canonical navigation and reading-order standard for the architecture canon. Future contributors, architects, engineers, reviewers, and AI coding tools must align with it when interpreting canon structure, placing new architecture standards, resolving apparent overlap, and updating repo memory for canonical additions unless a formal decision record explicitly revises it.

## Role of This Document in the Platform

This document governs how the architecture canon is approached as one governed control system rather than as a loose collection of files.

The system layers overview defines the structural interpretation of the platform, but it does not define the default reading sequence through the wider canon. The future domain admission and domain readiness standard defines when a new domain may join the platform, but it does not define one shared meaning for how a contributor should move through foundational standards, shared object standards, boundary controls, interface controls, and domain-local contracts in reading order. The cross-domain coordination and interface contract defines how admitted domains interact, but it does not define one shared meaning for which documents control overlapping concerns when multiple standards touch the same object, stage, scope, or output. The shared decision case and decision memory object standard defines the shared grammar for decision episodes, but it does not define one shared meaning for how architecture folders convey control role or how a new canonical document should be placed. The shared recommendation record standard, the shared progression-gate and stage-transition standard, the shared review resolution and case disposition standard, the shared reopen, revisit, and reinstatement standard, and the shared observation-horizon and measurement-window standard each stabilize critical shared meanings, but none of them defines one shared cross-canon rule for when navigation guidance may summarize those standards and when it must defer to the controlling document instead. The platform governance roles and approval authority matrix defines who may approve consequential canon change, but it does not define one shared architecture-facing reading order or placement discipline for the canon itself.

In practical terms, this document governs what counts as a canonical document, what counts as a controlling document, how reading order differs from dependency order, how folder placement conveys control role, how contributors should move from foundational standards to downstream standards, which document class controls when overlap exists, where future standards belong, and how repo memory should reflect canonical additions.

This document therefore governs canon navigation as part of platform coherence.

## Core Thesis

In the Fourth Form platform, the architecture canon must remain navigable as one governed control system whose foundational standards, operational control standards, shared object standards, boundary standards, interface standards, domain-pattern documents, and domain-local contracts are read in coherent order, placed according to control role, and interpreted under explicit conflict-resolution rules strong enough that navigation guidance helps contributors find authority without claiming that authority for itself.

That is the core thesis.

Navigation guidance is not the same thing as object authority. A document that helps readers find standards does not redefine those standards. Folder placement is not merely cosmetic; it conveys control role. Foundational documents should be read before downstream operational documents. Shared object standards should generally control object meaning when overlap exists. Domain-local documents must not silently override shared standards. Governance and decision records control consequential revisions to canon meaning. Future standards must be placed according to control role, not convenience. Repo memory must be updated when a canonical standard is added. Reading order and dependency order are related but not identical.

## What This Standard Is and Is Not

This standard is the shared platform rule for how the architecture canon is organized, approached, extended, and interpreted when multiple architecture documents coexist.

It is not a casual reading guide. It is not a team wiki note. It is not a lightweight onboarding page. It is not a substitute for the controlling object standards, boundary standards, interface standards, or domain-local contracts it points to. It is not permission to restate shared object meaning loosely in summary prose and later treat that summary as authority. It is not permission to resolve overlap by whichever file was opened first. It is not permission to place new standards wherever a contributor finds them convenient. It is not permission to use navigation language to weaken controlling grammar already fixed elsewhere in the canon. It is not permission to treat folder names as visual organization only. It is not permission to add canonical standards without updating repo memory.

A real canon navigation and reading-order standard means the platform can answer the following questions for any architecture document set: which documents are foundational, which are downstream, which folder role a new standard belongs to, which document controls when multiple standards touch the same concern, how a new contributor should read the canon in sequence, how dependency order differs from human reading order, how future canonical additions enter the tree, and how repo memory records that change without ambiguity.

## Why a Canon Navigation and Reading-Order Standard Is Necessary

The architecture canon must not be navigated by local habit, alphabetical order, or whichever file appears first in search results because the platform cannot remain one governed decision system if contributors read downstream contracts before foundational rules, treat object summaries as object authority, treat folder placement as convenience, or add new standards without structural placement discipline.

If canon navigation and reading order are left informal, several failures follow. One contributor reads a domain-local workflow contract before reading the shared object standards and later mistakes local workflow language for platform-wide truth. Another contributor reads an output or interface document and later treats packaging or coordination language as though it defined the underlying object meaning. Another contributor places a new cross-domain control in the objects folder and later readers infer object authority where the real concern was interface or boundary discipline. Another contributor resolves overlap by prose similarity rather than by control role. Another contributor adds a canonical standard but fails to update repo memory, so the canon tail no longer reflects the actual platform controls. Another contributor reads a downstream operational control before the foundational architecture and later treats a narrower control surface as though it were the whole platform structure.

The platform therefore needs one shared standard so that future contributors can approach one governed canon rather than improvising their own local map of which documents matter, which documents control, which documents overlap, and where future standards belong.

## Core Concepts

The platform uses the following core concepts.

### Canonical document

Canonical document is a governed architecture or governance document that belongs to the formal platform canon and is intended to stabilize meaning, structure, control role, or downstream alignment beyond one local implementation moment.

### Controlling document

Controlling document is the canonical document whose scope and control role directly govern a specific concern, object meaning, boundary condition, interface rule, workflow surface, or architectural interpretation when overlap or ambiguity appears.

### Foundational standard

Foundational standard is a canonical document that establishes base platform structure, vocabulary, authority, or architectural interpretation that downstream standards assume but do not redefine.

### Downstream standard

Downstream standard is a canonical document that depends on meanings, structures, or control rules already established by one or more foundational standards and therefore governs a narrower or later concern rather than the base layer itself.

### Operational control standard

Operational control standard is a canonical document that governs a repeated cross-platform decision-loop or governance surface, such as domain admission, learning admission, or canon navigation, rather than defining the shared meaning of one reusable object.

### Shared object standard

Shared object standard is a canonical document that governs the shared platform meaning, grammar, metadata, lineage, and reuse rules for a reusable decision-support object or context across all current and future domains.

### Boundary standard

Boundary standard is a canonical document that governs entitlement, tenant isolation, scope, comparison safety, reporting safety, learning safety, or another cross-platform boundary condition that downstream use must inherit rather than weaken.

### Interface standard

Interface standard is a canonical document that governs how structurally separate domains, modules, or governed artifacts may coordinate, depend on one another, or exchange outputs without collapsing ownership or weakening shared rules.

### Domain-local contract

Domain-local contract is a canonical or governed domain-specific document that defines how one admitted domain implements its local workflow, objects, simulation, reporting, execution observation, or learning logic beneath the shared platform rules.

### Reading order

Reading order is the governed sequence in which contributors should approach canonical documents so that foundational meaning is understood before narrower or downstream controls are interpreted.

### Dependency order

Dependency order is the governed structural order in which some canonical documents rely on meanings, authority, or control rules established by other canonical documents. Dependency order is related to reading order, but it is not identical to it.

### Overlap

Overlap is the condition in which two or more canonical documents touch the same object, stage, scope, output, timing surface, or governance concern without therefore carrying the same controlling authority.

### Conflict-resolution rule

Conflict-resolution rule is the governed rule that determines which document class, control role, or specific controlling document governs when overlap or apparent contradiction exists.

### Canon placement

Canon placement is the governed decision about where a canonical document belongs inside the architecture tree based on control role, scope, and downstream use rather than convenience or author preference.

### Canon extension

Canon extension is the governed addition of a new canonical document, or a formally approved split or refinement of an existing concern, that extends the architecture canon without fragmenting or redefining shared meanings casually.

### Repo-memory canon entry

Repo-memory canon entry is the concise canonical statement recorded in repo memory that names a new canonical document, states its control role, and preserves what future work must align with it.

## Canon Structure Overview

The architecture canon is organized by control role and scope, not by file convenience.

### Core

The core folder contains foundational platform architecture documents and platform-level operational control standards whose scope is broader than any one shared object, boundary surface, interface surface, or single domain. Core is where the platform fixes structural interpretation, cross-platform admission rules, learning-admission controls, and canon-level reading or placement rules. Core therefore governs how the platform is architecturally understood before narrower standards are applied.

### Objects

The objects folder contains shared object standards. These documents stabilize the platform meaning of reusable decision-support objects and contexts such as decision cases, recommendation records, progression gates, review resolution, reopen handling, and observation horizons. Objects therefore govern the underlying meaning of shared artifacts that many workflows, outputs, and domains depend on.

### Boundaries

The boundaries folder contains shared boundary controls. These documents govern entitlement, scope, tenant isolation, benchmark-safe comparison, and other boundary-sensitive rules that must survive downstream use. Boundaries therefore constrain what the platform may show, compare, or reuse even when downstream documents touch the same objects or outputs.

### Interfaces

The interfaces folder contains cross-domain and dependency controls. These documents govern how admitted domains coordinate, what interfaces may exist, how governed dependencies are exposed, and how downstream domains may consume another domain's outputs without absorbing the upstream domain's local logic. Interfaces therefore govern structurally separate coordination, not underlying object meaning.

### Domain-patterns

The domain-patterns folder contains reusable design guidance for how future domains should be structured so that domain growth remains coherent. Domain-patterns therefore sit between foundational platform architecture and concrete domain-local contracts. They are reusable shape controls rather than shared object standards or domain-local implementations.

### Domains

The domains folder contains domain-local architecture contracts for admitted domains. These documents define how one business-function domain applies the shared canon to its own model, workflow, simulation, reporting, execution observation, and learning logic. Domains therefore inherit the wider canon rather than rewriting it.

The current tree is meaningful because it shows control role directly. Core establishes cross-platform interpretation. Objects stabilize shared meanings. Boundaries govern use limits. Interfaces govern cross-domain coordination. Domain-patterns govern reusable domain shape. Domains govern local implementation beneath those shared rules.

## Canon Reading Order

The platform requires a default reading sequence for new contributors so that platform understanding is formed in the right order rather than from downstream fragments.

1. Read the core foundational platform architecture first. Start with the system layers overview so the contributor understands what the platform is, what the shared stack is doing, and what kinds of downstream documents will later appear beneath that structural interpretation.
2. Read the core governance and canon-level control surfaces next. The platform governance roles and approval authority matrix, the future domain admission and domain readiness standard, and this navigation standard should be read early so the contributor understands who controls consequential change, what qualifies as a governed domain, and how the canon itself is meant to be approached.
3. Read the shared object standards next. Start with shared decision case and decision memory, then shared recommendation record, then progression-gate and stage-transition, then review resolution and case disposition, then reopen, revisit, and reinstatement, then observation-horizon and measurement-window, and then the other shared object standards relevant to the contributor's concern. This stage gives the contributor the shared grammar of the decision loop before local workflow or output details appear.
4. Read the shared boundary standards after the object grammar is legible. Entitlement, scope, and benchmark-safe comparison controls should then be read so the contributor can see how downstream use is constrained.
5. Read the shared interface standards after the boundary standards. Cross-domain coordination and governed dependency documents should then be read so the contributor understands how structurally separate domains may interact without rewriting shared object meanings or boundary limits.
6. Read domain-pattern guidance after the shared platform controls. This shows how future domains are meant to be shaped once the contributor already understands the platform-wide structural, object, boundary, and interface rules.
7. Read domain-local contracts last. Only after the contributor has absorbed the shared canon should the Domain 01 model, workflow, simulation, reporting, execution observation, and policy-learning contracts be treated as concrete examples of platform application rather than as platform-wide authority.

This reading order is serious because contributors who begin from downstream domain-local documents, output surfaces, or cross-domain contracts will tend to overread local or downstream language as if it were foundational truth. Foundational documents should be read before downstream operational documents precisely so later documents are interpreted under the right controlling frame.

## Canon Dependency Order

Reading order is optimized for human comprehension. Dependency order is optimized for structural truth. The two are related, but they are not identical.

1. Governance authority and foundational platform architecture sit at the top of dependency order. Consequential architectural change depends on governance authority, and downstream standards depend on the platform-level structural interpretation fixed by the core architecture.
2. Boundary and admission controls depend on foundational platform architecture and governance, because the platform must first know what it is and how consequential change is governed before it can determine what domains may join and what scope or entitlement rules constrain downstream use.
3. Shared object standards depend on the foundational platform architecture and on the relevant governance and boundary assumptions already being in force. Shared object grammar may later be read before every boundary file, but structurally it still depends on the platform already having one governed architecture and one governed authority model.
4. Interface standards depend on foundational architecture, boundary controls, and shared object meanings. A cross-domain interface cannot be governed coherently unless the platform already knows what its objects mean, what boundaries constrain them, and what kind of cross-domain coordination is structurally allowed.
5. Domain-pattern documents depend on foundational architecture, admission logic, boundary rules, interface rules, and shared object grammar because reusable domain shape presumes those higher-order controls already exist.
6. Domain-local contracts depend on all higher tiers. Domain-local model, workflow, reporting, simulation, execution, and learning documents must inherit foundational structure, governance, shared object meaning, boundary limits, interface rules, and domain-pattern expectations rather than defining them from zero.
7. Navigation guidance depends on the existence of the canon it describes, but it does not therefore outrank the controlling documents it helps readers find. Navigation summarizes structure and control relationships without superseding them.

Dependency order is therefore the order of structural reliance. Reading order is the order most likely to help a new contributor understand that structure without confusing narrower standards for wider authority.

## Folder Role and Placement Rules

Future standards must be placed according to control role, not convenience.

### Core placement rule

Place a new document in core when it governs platform-wide architecture, cross-platform operational control, canon-level interpretation, domain admission, learning admission, or another control concern that is broader than any one reusable object, boundary surface, interface surface, or single domain.

### Objects placement rule

Place a new document in objects when it governs the underlying meaning, grammar, metadata, lineage, or reuse rules of a reusable shared object or context that many domains or workflows will touch.

### Boundaries placement rule

Place a new document in boundaries when it governs entitlement, scope, benchmark-safe comparison, access discipline, reporting safety, learning safety, or another boundary-sensitive rule that downstream use must inherit.

### Interfaces placement rule

Place a new document in interfaces when it governs cross-domain coordination, output consumption across domains, dependency exposure, orchestration surfaces, or versioned interface discipline.

### Domain-patterns placement rule

Place a new document in domain-patterns when it governs reusable structure for how future domains should be shaped but does not itself define one shared object meaning or one specific domain-local implementation.

### Domains placement rule

Place a new document inside the relevant domain folder when it governs one admitted domain's local model, workflow, simulation, reporting, execution observation, or learning logic beneath the shared platform rules.

### Placement integrity rule

Do not place a document according to author convenience, expected search traffic, or a desire to keep related filenames together if that placement would misstate the document's control role. Folder placement is not merely cosmetic; it conveys control role. Misplacement therefore creates structural ambiguity even when the text itself is sound.

### Flat-layout prohibition rule

Do not reintroduce a flat architecture layout under docs/architecture when the concern already belongs to one of the existing control-role folders. The existing tree is canonical because it preserves control role visibly.

## Overlap and Conflict-Resolution Rules

Apparent overlap among canonical documents must be resolved by control role and controlling authority rather than by whichever summary sounds broader.

### Shared object meaning beats navigation summary

When overlap concerns the underlying meaning of a shared object, shared object grammar, shared metadata, or shared lineage, the relevant shared object standard controls. This navigation standard may point to that standard, sequence that standard, and describe its role, but it does not redefine the object's meaning.

### Foundational structure beats downstream interpretation

When overlap concerns the structural interpretation of the platform as a whole, the foundational core architecture controls. Downstream operational, object, interface, or domain-local documents must inherit that architecture rather than revising it implicitly.

### Boundary control beats downstream use convenience

When overlap concerns entitlement, scope, benchmark-safe comparison, reporting safety, or learning safety, the relevant boundary standard controls even if a downstream object, interface, output, or domain-local document also touches that same artifact.

### Interface control governs cross-domain interaction form

When overlap concerns how one domain consumes another domain's outputs, what interface surface exists, or how dependencies are exposed across domain boundaries, the relevant interface standard controls the interaction form. It does not therefore redefine the underlying meaning of the shared objects crossing that interface.

### Domain-local workflow cannot override shared object grammar

When a domain-local contract uses a shared object, stage, closure state, reopen class, or observation class, the shared platform standard for that concern controls the meaning. Domain-local workflow may extend the concern locally where extension is allowed, but it must not silently override the shared grammar.

### Output packaging does not redefine underlying object meaning

When overlap concerns how an object is carried inside an output package or interface payload, packaging and delivery controls may govern transport, scope metadata, and exposure behavior, but they do not redefine the underlying object meaning. Underlying object meaning remains with the controlling shared object standard.

### Governance documents beat informal interpretation

When overlap or ambiguity concerns whether canon meaning may be revised, who may approve that revision, or whether a change is consequential, governance documents and formal decision records control. Informal interpretation, code convenience, and local habit do not.

### Navigation documents must point rather than loosely restate

When a navigation document describes another controlling standard, it should point readers to the controlling standard, name its control role, and distinguish it from adjacent documents. It should not restate the controlling grammar loosely and later let that loose restatement compete with the real authority.

### Stricter control rule

If a concern genuinely spans multiple document classes and the apparent controlling document is unclear, the stricter governance or control requirement governs until a formal decision record clarifies the canon. Ambiguity is not permission for contributors to choose the weaker standard.

## Canon Change and Extension Rules

The architecture canon may grow, but it must grow without fragmenting control meaning.

1. Add a new canonical standard only when the concern is materially consequential, cross-cutting, or structurally durable enough that leaving it as local workflow language would create drift.
2. Before adding a new standard, identify the controlling concern precisely. If the concern is foundational architecture, place it in core. If it is reusable object meaning, place it in objects. If it is scope or entitlement control, place it in boundaries. If it is cross-domain interaction or dependency exposure, place it in interfaces. If it is reusable domain shape, place it in domain-patterns. If it is one admitted domain's local implementation, place it in that domain folder.
3. A new standard must state what adjacent standards already control and what this new standard does and does not control. Canon extension must reduce ambiguity, not create duplicated authority.
4. A new navigation or summary document must reinforce that navigation guidance is not the same thing as object authority and that a document helping readers find standards does not redefine those standards.
5. Consequential revisions to canon meaning must go through formal governance and decision-record discipline. Canon extension is not permission to revise existing authority implicitly through placement or wording.
6. Repo memory must be updated when a canonical standard is added. The update must occur in the same governed change as the new standard or immediately alongside it, and the repo-memory canon entry must be concise, structurally accurate, and placed with related canon entries without extra blank-line drift.
7. Repo-memory canon entry discipline matters because repo memory is the durable compact map of what the canon contains. A missing repo-memory update means the canon and the memory of the canon have diverged.

Canon extension is therefore allowed, but it must preserve one readable tree, one visible control-role structure, and one reconstructible memory of what became canonical and why.

## Governance Linkage

This standard is directly governance-linked because navigation discipline, placement discipline, and conflict-resolution discipline affect how contributors interpret the architecture canon, where new authority surfaces are created, and whether consequential canon change remains reviewable.

The system layers overview should be treated as the controlling reference for the structural interpretation of the platform as a whole. The future domain admission and domain readiness standard should be treated as the controlling reference for when a new business-function domain may enter the canon as governed platform scope. The shared object standards should be treated as the controlling references for the underlying meanings of their respective objects, contexts, stages, and lineages. The boundary standards should be treated as the controlling references for scope, entitlement, and comparison constraints. The interface standards should be treated as the controlling references for cross-domain coordination and governed dependency behavior. Domain-pattern documents should be treated as the controlling reusable guidance for shaping future domains. Domain-local contracts should be treated as local inheritors of the wider canon rather than as platform-wide truth.

The platform governance roles and approval authority matrix should be treated as the controlling reference for who may approve consequential revisions to canon structure, placement rules, folder roles, shared architecture meaning, or shared grammar. Formal decision-record governance should be treated as the controlling path for consequential canon revisions, especially where a change would alter control role, overlapping authority, or the meaning of an existing canonical standard.

Changes to canon structure, folder-role meaning, reading-order expectations, conflict-resolution rules, repo-memory canon-entry discipline, or the relationship among foundational and downstream standards are consequential platform changes. They must go through formal governance rather than domain-local adjustment.

## Failure Modes in Canon Navigation Design

Weak canon navigation design creates direct platform risk.

### Duplicated authority

The platform allows multiple documents to appear to control the same concern because navigation language, placement, or summary prose duplicates authority instead of pointing to the controlling standard.

### Navigation document drifting into object redefinition

The platform creates a navigation or summary document that begins as reading guidance but gradually restates object grammar, stage grammar, or boundary grammar loosely enough that readers treat the summary as authority.

### Inconsistent placement

The platform places new standards by convenience rather than by control role, so later readers infer the wrong kind of authority from the folder path alone.

### New standards added without canon memory update

The platform adds a canonical standard to the tree, but repo memory is not updated, so the compact record of canon authority no longer matches the actual canon.

### Contributors reading downstream documents before foundational ones

The platform leaves reading order informal, so contributors begin from downstream workflow, output, or domain-local documents and later mistake narrower language for foundational truth.

### Domain-local documents mistaken for platform-wide truth

The platform allows a domain-local contract to become the de facto explanation of a concern that is actually controlled by a shared object, boundary, interface, or foundational standard.

### Boundary and interface controls being treated as optional afterthoughts

The platform describes objects or workflows clearly but leaves readers unclear about where scope, entitlement, comparison, or cross-domain interaction rules actually control downstream use.

### Conflict resolved by personal interpretation instead of control role

The platform allows overlap to be settled by whichever contributor sounds more confident, whichever file appears more recent, or whichever summary is easier to read rather than by explicit canon rules.

### Repo tree slowly flattening again

The platform begins adding architecture files outside the control-role folders, weakening the visible distinction among foundational controls, shared object standards, boundary rules, interface rules, domain-pattern guidance, and domain-local contracts.

### Navigation guidance weakening governance discipline

The platform treats reading aids or summary documents as if they can revise the canon without formal approval, letting informal interpretation bypass governance and decision-record control.

These failure modes are not minor documentation defects. They are ways the platform can keep producing architecture text while losing the ability to tell which documents control, how those documents relate, and where future authority should live.

## Non-Negotiables

1. Navigation guidance is not the same thing as object authority.
2. A document that helps readers find standards does not redefine those standards.
3. Folder placement is not merely cosmetic; it conveys control role.
4. Foundational documents must be approached before downstream operational and domain-local documents.
5. Reading order and dependency order are related but not identical.
6. Shared object standards should generally control object meaning when overlap exists.
7. Domain-local documents must not silently override shared standards.
8. Output packaging, interface summary, or navigation summary must not redefine underlying object meaning.
9. Future standards must be placed according to control role, not convenience, and repo memory must be updated when a canonical standard is added.
10. Consequential revisions to canon meaning, placement, or conflict rules must go through formal governance and decision-record discipline.

## Closing Statement

This standard protects the architecture canon from collapsing into an unordered file library, a flat document list, or a summary culture in which readers can no longer tell what controls what.

That protection matters because a serious decision platform must preserve not only durable object meanings, boundary rules, interface rules, workflow contracts, and domain-local implementations, but also the order in which contributors should approach those documents, the structural dependencies among them, the folder roles that signal their control function, the conflict rules that decide which document governs when overlap exists, and the repo memory that records what became canonical. Future contributors need one shared canon navigation and reading-order grammar robust enough that the platform can keep adding standards without losing the visible structure of authority that makes the canon governable in the first place.