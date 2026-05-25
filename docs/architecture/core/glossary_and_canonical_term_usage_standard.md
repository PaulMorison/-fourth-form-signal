# Glossary and Canonical Term Usage Standard for the Fourth Form Retail Decision Intelligence Platform

## Purpose of This Document

This document defines the shared platform standard for glossary governance and canonical term usage across all current and future architecture documents, governance documents, shared standards, domain contracts, reporting-adjacent explanation surfaces, implementation guidance, and future domain extensions.

It exists because the platform now has governed standards for canon navigation, canon change control, lifecycle composition, decision mode, commercial value, code structure, security, performance, storage, build order, automation posture, policy-learning admission, shared decision objects, shared context objects, shared review objects, shared summary surfaces, scope boundaries, and cross-domain coordination, but it still lacks one shared rule for how canonical terms themselves are admitted, controlled, inherited, extended, deprecated, retired, and used without semantic drift across the canon. Without such a rule, the platform will drift into near-synonym substitution, local shorthand that mutates shared meaning, familiar language that sounds harmless but weakens governance precision, short labels treated as if they carried full definitions, explanation text that quietly loosens controlled distinctions, object terms reused outside their controlling scope, and future domains importing local jargon into shared platform language.

This document is therefore a control document for glossary governance and canonical term usage discipline.

It defines the core concepts, shared controls, vocabulary zones, shared grammar, minimum metadata requirements, lineage rules, inheritance rules, extension rules, and governance linkage that all contributors must follow when preserving canonical wording, controlled synonym discipline, definition authority, cross-document consistency, audience-safe phrasing, and human comprehension without semantic slippage.

It is the canonical glossary and canonical term usage standard for the platform. Future architecture documents, governance records, shared standards, domain contracts, reviewers, engineers, implementation agents, and future domains must align with it when introducing, using, extending, restricting, deprecating, or retiring controlled platform vocabulary unless a formal decision record explicitly revises it.

## Role of This Document in the Platform

This document governs the shared vocabulary-control layer that sits beneath the whole canon and across every platform document that depends on stable meaning.

The canon navigation and reading-order standard defines how the canon is approached and where documents belong, but it does not define one shared rule for how terms inside those documents must stay semantically stable. The canon change-control and quality-gate standard defines how canonical files are added, revised, superseded, deprecated, and retired, but it does not define one shared rule for admitting or governing canonical terms themselves. The end-to-end decision lifecycle composition standard defines how shared objects compose across one governed decision episode, but it does not define one shared rule for how the words naming those objects must remain stable across documents. The shared decision case and decision memory object standard defines what a decision case is, the shared recommendation record standard defines what a recommendation record is, the shared decision rationale and explanation trace standard defines what rationale and explanation trace mean, the shared briefing, digest, and summary surface standard defines what derived summarization surfaces are, and the platform entitlement and scope boundary model defines what tenant, reporting scope, learning scope, and decision scope mean. This document does not replace those authorities. It governs how the platform preserves the canonical wording of those meanings, how it records definition authority, how it handles controlled synonyms and forbidden synonyms, how it keeps near-synonym risk visible, and how it prevents one document from silently redefining another document's controlled vocabulary.

In practical terms, this document governs what counts as a canonical term, who controls a term's authoritative meaning, how glossary records should point to controlling standards, how synonyms and near-synonyms are governed, how ambiguous or colliding terms are resolved, how audience-safe phrasing differs from canonical wording, how deprecated or restricted terms remain visible without remaining current, and how future domains inherit platform vocabulary without importing local jargon into shared canon.

This document therefore governs glossary and canonical term usage as part of platform coherence.

## Core Thesis

In the Fourth Form platform, glossary governance and canonical term usage must remain first-class platform control structure whose definition authority, scope discipline, synonym discipline, ambiguity handling, lineage, inheritance, extension posture, deprecation posture, audience-safe phrasing rules, and resolution path remain explicit enough that the platform can preserve one shared meaning for materially consequential vocabulary across standards, reviews, implementations, explanations, and future domains without making human comprehension depend on guesswork.

That is the core thesis.

a glossary is not the same thing as redefining standards.

canonical term usage is not the same thing as local writing preference.

synonym convenience is not the same thing as semantic equivalence.

familiar language is not the same thing as governed language.

short labels are not the same thing as controlled meanings.

explanation readability is not the same thing as terminological looseness.

local shorthand is not the same thing as canonical usage.

The platform should preserve human comprehension without semantic slippage. It should use words people can understand, but it should not let readability, familiarity, brevity, or presentation convenience quietly mutate the meaning of a governed term.

## What This Standard Is and Is Not

This standard is the shared platform rule for how glossary records are formed and how canonical terms must be used, inherited, extended, restricted, deprecated, and retired across the platform.

It is not a substitute for the controlling standards that define shared objects, boundary conditions, or interface meaning. It is not a navigation guide. It is not a canon-admission gate by itself. It is not a style note about personal prose preference. It is not a copy-editing guide. It is not permission to rewrite an object definition in lighter wording and later treat that wording as authoritative. It is not permission to introduce local jargon because the intended meaning feels obvious. It is not permission to smooth over a distinction between two terms because a reader might prefer one of them. It is not permission to shorten a governed term and then assume the shortened form carries full authoritative meaning. It is not permission to let audience-safe phrasing replace canonical wording inside the governing canon. It is not permission to settle a semantic conflict by whichever term sounds more natural.

A real glossary and canonical term usage standard means the platform can answer the following questions for any materially consequential term: what the canonical term is; which document holds definition authority for it; what scope the term applies to; what controlled synonyms are allowed if any; what synonyms are forbidden if any; what near-synonym risk still exists; what wording is required in canonical documents; what audience-safe phrasing may be used without changing meaning; whether the term is inherited, extended, deprecated, or restricted; how ambiguity or collision must be resolved; and what future documents must align with that meaning.

## Why a Shared Glossary and Canonical Term Usage Standard Is Necessary

The platform needs one shared standard for glossary and canonical term usage because the canon cannot remain one governed control system if its words begin to drift even while its file structure still looks disciplined.

If glossary governance and canonical term usage are left informal, several failures follow. One document uses decision case while another says case object and a third says workflow case as if they were equivalent. One document says reporting scope while another casually says visibility boundary or client scope even though those are not always the same thing. One document says recommendation while another says suggestion or proposal and later review logic treats those local substitutions as harmless. One summary surface introduces softer audience-safe wording and a later contributor imports that softer wording back into the governing canon as if it were now the canonical term. One future domain shortens or relabels a shared term to fit local habit and later readers infer that the local wording created a new platform concept. One contributor tries to solve ambiguity by redefining a shared term locally rather than resolving authority through the controlling standard. The platform then becomes harder to review, harder to implement consistently, harder to explain precisely, and easier to misgovern even when nobody intended a semantic change.

The platform therefore needs one shared standard so that future contributors, reviewers, engineers, agents, and domains inherit one governed vocabulary discipline rather than improvising their own local map of which words matter, which words are merely convenient, and which words are allowed to vary.

## Core Concepts

The platform uses the following core concepts.

### Canonical term

Canonical term is the governed platform term whose wording and meaning are treated as the shared default for one materially consequential concept across the canon.

### Controlled synonym

Controlled synonym is a non-primary term that may be used only under explicitly governed conditions because its meaning is treated as equivalent enough to the canonical term for a stated audience, scope, or derived surface without changing the underlying controlled concept.

### Forbidden synonym

Forbidden synonym is a term or wording variant that must not be used for a given concept because it would materially blur, weaken, or distort the controlled meaning of the canonical term.

### Near-synonym risk

Near-synonym risk is the governed risk that two terms appear similar enough in ordinary language that contributors may treat them as interchangeable even though the canon preserves a materially different meaning for each.

### Definition authority

Definition authority is the controlling canonical document whose scope legitimately owns the authoritative meaning of a term.

### Term scope

Term scope is the explicit statement of where a term applies, what layer or control role it belongs to, and where that term must not be stretched by analogy or convenience.

### Term inheritance

Term inheritance is the governed rule that downstream documents and future domains inherit canonical wording and meaning from the controlling authority rather than redefining those terms locally.

### Term extension

Term extension is the governed addition of narrower subordinate wording or narrower domain-local terminology beneath an existing canonical term without redefining the shared meaning of the parent term.

### Term admission

Term admission is the governed act by which a proposed term becomes an accepted canonical term under explicit definition authority, explicit scope, and explicit downstream inheritance expectations.

### Term collision

Term collision is the condition in which two different concepts, authorities, or scopes are given the same or materially similar wording strongly enough that the canon risks losing semantic separation.

### Term drift

Term drift is the condition in which the wording or apparent meaning of a canonical term changes gradually across documents, versions, or domains without explicit governed approval.

### Term ambiguity

Term ambiguity is the condition in which the platform cannot determine from usage alone which governed meaning a term is intended to carry.

### Term resolution

Term resolution is the governed settlement of ambiguity, collision, near-synonym conflict, or drift through the semantic resolution path rather than through local wording preference.

### Inherited term

Inherited term is a canonical term whose wording and meaning are carried into a downstream document unchanged under the authority of the original controlling document.

### Extended term

Extended term is a narrower term introduced beneath a canonical parent term for a legitimate narrower scope while remaining explicitly subordinate to the parent's controlled meaning.

### Deprecated term

Deprecated term is a formerly governed term whose prior meaning remains visible in lineage but whose current use is no longer preferred for new canonical work.

### Restricted term

Restricted term is a term whose use is allowed only within an explicitly governed audience, document class, or historical context because broader use would create semantic confusion or governance risk.

### Term retirement

Term retirement is the governed end-state in which a term no longer remains active as current canonical vocabulary while its historical lineage and interpretive trace remain reconstructible.

### Audience-safe phrasing

Audience-safe phrasing is wording allowed for explanation, reporting, or derived communication surfaces when it preserves the underlying controlled meaning and does not pretend to replace canonical wording.

### Canonical wording requirement

Canonical wording requirement is the governed rule that certain terms must appear in their exact canonical form inside the controlling canon, governance text, or other specified document classes.

### Semantic resolution path

Semantic resolution path is the governed path by which ambiguity, collision, near-synonym conflict, or drift is resolved through controlling authority rather than through local prose preference.

### Glossary maintenance discipline

Glossary maintenance discipline is the governed rule that glossary records, synonym posture, deprecation posture, and authority linkage must remain synchronized with the controlling standards that own the relevant terms.

## Canonical Term Governance

At platform level, canonical term governance is the formal control posture by which the platform admits, records, maintains, and governs shared vocabulary.

The glossary must preserve canonical terms as references to authoritative meaning, not as independent rival definitions. a glossary is not the same thing as redefining standards. Where a shared object standard, boundary standard, interface standard, or core standard already owns the authoritative meaning of a term, the glossary record must preserve that authority explicitly rather than rewriting the term in slightly different words. The glossary may stabilize wording, record scope, record synonym discipline, and point to the authoritative source. It must not seize authority from the source document.

Canonical term governance requires definition authority for every materially consequential term. A term cannot become a serious canonical term merely because it appears often. Frequency of use is not the same thing as authority. A term becomes canonical when its meaning is controlled, its scope is explicit, its authority is named, its downstream use is inheritable, and its ambiguity posture is governed strongly enough that later contributors do not need to infer what it probably meant.

Canonical term governance also requires explicit term admission, glossary maintenance discipline, term resolution, and term retirement posture. A new term should be admitted only when the concept is durable, cross-document, materially consequential, and not already controlled adequately by an existing canonical term. Glossary maintenance discipline requires that glossary records stay synchronized with controlling definitions, current restriction posture, and current deprecation posture rather than drifting into paraphrase. Term resolution requires that ambiguity, collision, or near-synonym conflict be settled through definition authority and semantic resolution path before the canon treats the wording as stable. A term may be deprecated or restricted when the platform still needs historical visibility or audience-limited usage, but no longer wants that term treated as current default canonical wording. A term may be retired only when its governed use no longer needs to remain active and its lineage remains reconstructible through the relevant canonical records.

Cross-document consistency is not optional. If one document uses a term in its canonical sense and another document uses the same wording for a different meaning, the canon already has a governance problem even if readers can usually infer the intent. The platform must prefer semantic clarity over local prose convenience.

## Controlled Synonym and Near-Synonym Discipline

Controlled synonym and near-synonym discipline exists because everyday language tempts contributors to relax distinctions precisely where the canon needs them to stay sharp.

canonical term usage is not the same thing as local writing preference. A contributor may prefer one wording for rhythm, brevity, or familiarity, but preference does not create authority. Where canonical wording is required, local preference yields. Where audience-safe phrasing is permitted, the contributor may choose a controlled variant only if the underlying meaning remains traceable and unweakened.

synonym convenience is not the same thing as semantic equivalence. Two words may feel close enough in general English while still carrying different controlled meanings in the platform. A controlled synonym is therefore a governed exception, not an open invitation to substitute freely.

familiar language is not the same thing as governed language. A term that sounds ordinary or friendly may still be invalid when it blurs a sharper governed distinction. short labels are not the same thing as controlled meanings. A shortened form may help a heading, a label, or a derived communication surface, but it does not automatically carry the full authoritative meaning of the canonical term unless the glossary explicitly says so.

Near-synonym risk must remain explicit wherever adjacent terms are likely to collapse into one another under casual reading. If the platform uses decision scope, reporting scope, and learning scope, then scope alone is too weak when the governing distinction matters. If the platform uses recommendation, review resolution, disposition, and instruction, then action language alone is too weak when object authority matters. If the platform uses summary surface and recommendation, then concise communication must not be allowed to collapse those meanings.

Forbidden synonyms should be named where the risk is serious enough that silence would invite drift. Restricted terms should remain visibly restricted. Controlled synonyms should be limited to the audiences and document classes for which they remain safe. explanation readability is not the same thing as terminological looseness. local shorthand is not the same thing as canonical usage.

## Canonical Vocabulary Zones

The platform requires one shared zoning model for vocabulary so that terms remain connected to their controlling role rather than floating as loose language across the tree.

### Foundational vocabulary zone

The foundational vocabulary zone contains platform-wide terms governed by core standards because those terms shape how the whole canon is read, interpreted, and extended. These are terms whose meanings influence many downstream standards even when those standards do not own the meanings themselves.

### Shared object vocabulary zone

The shared object vocabulary zone contains terms whose authoritative meanings belong to shared object standards because those terms govern reusable decision-support objects, object states, and object contexts across many domains.

### Boundary vocabulary zone

The boundary vocabulary zone contains terms whose authoritative meanings belong to boundary standards because those terms govern entitlement, scope, comparison safety, access limitation, or another use-limiting condition.

### Interface vocabulary zone

The interface vocabulary zone contains terms whose authoritative meanings belong to interface standards because those terms govern cross-domain coordination, dependency exposure, interface discipline, or output consumption across structurally separate domains.

### Domain-pattern and domain-local vocabulary zone

The domain-pattern and domain-local vocabulary zone contains terms that may legitimately exist beneath shared platform vocabulary for reusable domain shape or one admitted domain's narrower operating logic, provided those terms do not redefine inherited canonical terms.

### Audience-safe wording zone

The audience-safe wording zone contains approved explanatory or presentation-facing phrasing that may appear in derived communication surfaces when the underlying canonical term remains traceable and the wording does not create semantic slippage.

### Deprecated and restricted vocabulary zone

The deprecated and restricted vocabulary zone contains terms that remain visible for lineage, backward interpretation, audience-limited use, or explicitly bounded historical reference without remaining current shared canonical wording.

## Glossary and Term Usage Grammar

The platform requires one shared cross-canon grammar for glossary and term usage so that future standards, reviewers, and domains inherit stable usage states rather than inventing their own semantic statuses.

### Canonical wording required

Canonical wording required is the shared cross-canon condition in which the exact canonical term must be used because the document class, governance sensitivity, or semantic risk is too serious to allow looser wording.

### Controlled synonym allowed

Controlled synonym allowed is the shared cross-canon condition in which a governed synonym may be used for a stated audience, context, or derived surface without replacing the canonical term as definition authority.

### Audience-safe phrasing allowed

Audience-safe phrasing allowed is the shared cross-canon condition in which explanatory wording may be used for comprehension or presentation safety only if the controlled meaning remains intact and traceable.

### Restricted term allowed only in bounded scope

Restricted term allowed only in bounded scope is the shared cross-canon condition in which a term may appear only in a specified audience, legacy context, or narrowly governed document class.

### Deprecated term allowed only for lineage or historical reference

Deprecated term allowed only for lineage or historical reference is the shared cross-canon condition in which a term remains visible for interpretation of prior canon or prior artifacts but must not be used as new default canonical wording.

### Forbidden synonym prohibited

Forbidden synonym prohibited is the shared cross-canon condition in which a wording variant must not be used because it would materially weaken or distort the governed distinction the platform is trying to preserve.

### Semantic review required

Semantic review required is the shared cross-canon condition in which ambiguity, near-synonym risk, collision, or drift is serious enough that the term cannot be accepted or reused casually.

### Semantic resolution required

Semantic resolution required is the shared cross-canon condition in which the platform must resolve wording conflict through definition authority, control role, and governed review rather than by local stylistic choice.

## Minimum Shared Metadata for Canonical Term Records

Every materially consequential canonical term must preserve a canonical term record strongly enough that later contributors can reconstruct what the term means, who owns it, where it applies, and how it may be used.

At minimum, a canonical term record must preserve, conceptually, all of the following. It must preserve a stable term identity so the record is reconstructible over time. It must preserve the exact canonical wording so later documents cannot infer the primary wording loosely. It must preserve the authoritative definition strongly enough that the record conveys the controlled meaning without inventing a second competing authority. It must preserve definition-authority linkage so later contributors can identify which standard owns the meaning. It must preserve control-role classification and term-scope statement so the term is not stretched beyond its legitimate layer. It must preserve inherited-term or extended-term posture where relevant so downstream use remains interpretable. It must preserve controlled-synonym references, forbidden-synonym references, and near-synonym-risk references where relevant so the platform can govern substitution explicitly. It must preserve canonical-wording-requirement posture and audience-safe-phrasing posture where relevant so later writers know when exact wording is required and when bounded paraphrase is allowed. It must preserve lineage or version reference and timestamp so later contributors can reconstruct which governed meaning applied at the relevant time.

## Minimum Shared Metadata for Deprecated or Restricted Term Records

Every deprecated or restricted term must preserve a deprecated or restricted term record strongly enough that later contributors can reconstruct why the term still appears, why it is no longer current, and how it may still be interpreted safely.

At minimum, a deprecated or restricted term record must preserve, conceptually, all of the following. It must preserve a stable term identity and the exact wording of the deprecated or restricted term so later readers can identify it without guesswork. It must preserve status posture showing whether the term is deprecated, restricted, or both. It must preserve the superseding canonical term where relevant so the current preferred wording is explicit. It must preserve the reason for restriction or deprecation strongly enough that later contributors can tell whether the issue was ambiguity, collision, scope drift, audience risk, or another governed concern. It must preserve bounded-usage conditions where relevant so readers know whether the term remains valid only in lineage review, historical interpretation, audience-safe surfaces, imported legacy material, or another narrow context. It must preserve forbidden-expansion posture where relevant so later contributors know the term may not be broadened back into current canon by convenience. It must preserve definition-authority linkage, lineage or version reference, and timestamp so later systems can reconstruct when and why the status changed.

## Lineage Rules

Term lineage must remain reconstructible across admission, clarification, extension, restriction, deprecation, and retirement. The platform must be able to connect a term's wording, authoritative meaning, controlling document, later usages, later changes, and later restrictions without inventing semantic history after the fact.

Glossary lineage must preserve when a term was admitted, what authority owned it, what downstream documents inherited it, what controlled synonyms or forbidden synonyms were attached to it, what ambiguity or collision risks were identified, and what later deprecation, restriction, or retirement actions changed its status. A term that cannot be lineaged cleanly is a term that cannot be governed cleanly.

Lineage must also preserve the difference between stable meaning and stable wording. Sometimes wording may narrow, expand, or be replaced while the underlying control concept remains structurally continuous. Sometimes wording remains the same while the controlled meaning shifts materially. Both kinds of change must remain visible. Term drift must never be mistaken for continuity merely because the word stayed familiar.

## Domain Inheritance Rules

Every downstream standard, domain-pattern document, and domain-local contract that depends on shared platform vocabulary must inherit canonical terms from their controlling authorities unless a narrower extension is explicitly allowed.

Domains must inherit the rule that shared canonical terms keep their platform meanings even when local business objects differ. They must inherit the rule that audience-safe phrasing does not rewrite canonical wording. They must inherit the rule that local shorthand cannot displace shared canonical usage. They must inherit the rule that if a platform term appears to be insufficient, the answer is governed extension or governed semantic resolution, not local redefinition.

Inherited term use must preserve enough explicitness that a reader can still tell when a domain is using shared platform language and when it is using narrower local language beneath that shared authority. Domains may narrow. They may not silently re-own shared meanings.

## Domain Extension Rules

Valid domain extension may introduce narrower subordinate wording, narrower domain-specific labels, or narrower operational subtypes beneath a canonical term when the extension preserves the parent meaning explicitly and does not create collision with another shared term.

Invalid domain extension includes treating a local label as if it replaced a canonical term, stretching a shared term outside its controlled scope because the wording feels close enough, importing local jargon into shared canon without governed admission, or trying to solve ambiguity by giving a narrower domain term broader platform authority than its control role justifies.

future glossary extensions must be placed according to control role, not convenience.

If an extension changes shared vocabulary governance, synonym discipline, metadata rules, deprecation rules, or cross-canon term usage across many documents, it belongs in the shared core canon. If it changes the underlying meaning of a shared object term, a boundary term, or an interface term, it belongs in the controlling object, boundary, or interface standard rather than here. If it changes only one domain's narrower wording beneath inherited platform vocabulary, it belongs in that domain contract and must not redefine the shared glossary grammar.

## Governance Linkage

The canon navigation and reading-order standard should treat this file as the controlling reference for why canonical terms and their control roles must remain legible across the tree without redefining placement rules themselves. The canon change-control and quality-gate standard should treat it as the controlling reference for term-level admission, extension, deprecation, and retirement discipline without replacing canon-file change control. The end-to-end decision lifecycle composition standard should treat it as the controlling reference for why lifecycle terminology must remain stable without redefining lifecycle composition meaning. The shared decision case and decision memory object standard, the shared recommendation record standard, the shared decision rationale and explanation trace standard, the shared evidence bundle and signal provenance standard, the shared uncertainty and confidence context standard, the shared constraint and feasibility context standard, the shared state snapshot and local operating context standard, the shared progression-gate and stage-transition standard, the shared review resolution and case disposition standard, the shared briefing, digest, and summary surface standard, and the shared assumption, hypothesis, and inference register standard should treat it as the controlling reference for how their terms are recorded and reused canonically without surrendering definition authority over their own object meanings.

The platform entitlement and scope boundary model should treat it as the controlling reference for how boundary vocabulary is preserved canonically without redefining entitlement or scope rules. The cross-domain coordination and interface contract should treat it as the controlling reference for how interface vocabulary remains stable without redefining interface coordination semantics. The governance authority matrix should treat glossary, terminology, and canonical-wording changes as consequential shared-platform changes when those changes materially alter controlled meaning, cross-document inheritance, or downstream governance interpretation.

Changes to canonical term governance, shared vocabulary zones, canonical-wording rules, synonym discipline, deprecation rules, or semantic-resolution rules are consequential shared-platform changes. Under the governance authority matrix, the stricter applicable approval path governs. In practice this means Architecture Authority review is materially relevant, Implementation Authority review is materially relevant where code naming or downstream implementation behavior is affected, affected Domain Authority review is materially relevant where inherited platform vocabulary is used locally, Governance and Boundary Authority review is materially relevant where scope or boundary language is touched, and the Platform Owner with the relevant approval path controls when the change alters platform-wide governed meaning.

## Failure Modes in Glossary and Canonical Term Usage Design

### Glossary treated as rival authority

The glossary restates or paraphrases authoritative definitions loosely enough that contributors begin using the glossary wording instead of the controlling standard as the real source of meaning.

### Near-synonym collapse

Two materially distinct controlled terms are treated as interchangeable because they sound close enough in ordinary language.

### Familiar shorthand becomes platform truth

Local shorthand or habitual short labels spread through reviews, notes, or code comments until they begin to displace canonical wording in the governing canon.

### Audience-safe wording imported back into canon

Derived explanatory phrasing that was safe for a specific audience is later copied back into the authoritative canon as if it were now the governing term.

### Silent term drift across documents

The wording or practical meaning of a term changes gradually across documents and revisions without any explicit governed resolution.

### Term collision across control roles

The same wording is used for different concepts owned by different control roles, leaving readers unable to tell which authority governs the term in context.

### Definition authority omitted

A term is treated as canonical even though no controlling standard is named as the legitimate owner of the term's meaning.

### Deprecated term treated as current

Historical or restricted wording remains visible for lineage, but later contributors mistake that visibility for permission to use the term as current canonical default.

### Readability used as excuse for looseness

Contributors relax terminology in the name of clarity and later discover that the underlying governed distinction has been erased.

### Local extension mistaken for shared vocabulary

One domain's narrower term is adopted beyond its legitimate scope until it begins to look like platform-wide vocabulary without ever passing governed admission.

## Non-Negotiables

1. a glossary is not the same thing as redefining standards, and no glossary record may seize definition authority from the controlling canonical document that already owns a term's meaning.
2. canonical term usage is not the same thing as local writing preference, and materially consequential documents must use canonical wording wherever canonical wording requirement applies.
3. synonym convenience is not the same thing as semantic equivalence, and no synonym may be treated as controlled merely because it feels close enough in ordinary language.
4. familiar language is not the same thing as governed language, and no contributor may prefer ordinary wording over sharper governed wording when the distinction materially affects control meaning.
5. short labels are not the same thing as controlled meanings, and no abbreviation, shorthand label, or compressed wording may be treated as carrying full canonical authority unless the glossary explicitly permits it.
6. explanation readability is not the same thing as terminological looseness, and audience-safe phrasing may never weaken, blur, or replace the controlled meaning of the canonical term it helps explain.
7. local shorthand is not the same thing as canonical usage, and domain-local habit must never displace inherited platform vocabulary in the shared canon.
8. Every materially consequential canonical term must preserve explicit definition authority, explicit term scope, explicit synonym posture, and explicit lineage strongly enough that later contributors can resolve meaning without guesswork.
9. Deprecated and restricted terms must remain visible enough for lineage and historical interpretation, but they must not remain available as silent current defaults for new canonical work.
10. future glossary extensions must be placed according to control role, not convenience, and no domain-local terminology habit may redefine the shared glossary and canonical-term-usage grammar.

## Closing Statement

This standard fixes the shared platform rule for how glossary governance and canonical term usage must remain explicit, lineaged, control-role-aware, and semantically disciplined across core architecture, shared objects, boundaries, interfaces, domain contracts, reviews, explanations, and future platform growth. It protects the platform from silent drift in meaning, convenience synonymy, local jargon masquerading as authority, audience-safe wording that mutates into canonical wording, and ambiguity that forces readers to infer governance from tone rather than from controlled language. And it keeps future scale possible by ensuring that the platform continues to use the same words with the same meanings in the places where those meanings actually matter.