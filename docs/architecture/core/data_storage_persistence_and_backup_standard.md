# Data Storage, Persistence, and Backup Standard for the Fourth Form Retail Decision Intelligence Platform

## Purpose of This Document

This document defines the shared platform standard for data storage, persistence, backup, restore legitimacy, retention, archival, and deletion across all current and future implementation, pipeline, storage, automation, and operational handling work.

It exists because the platform now has governed standards for canon structure, lifecycle composition, intervention policy, commercial value, code architecture, security and data protection, performance and scalability, interface governance, evidence, state, execution outcome, observation maturity, failure handling, capability boundaries, chronology, and platform approval authority, but it still lacks one shared core control for how storage roles, persistent artifacts, backup copies, restore legitimacy, archival posture, and deletion discipline must be governed so that the platform preserves durable truth and durable knowledge without turning every copy into a competing store.

Without a shared standard, the platform will drift into caches treated as durable persistence, backups treated as operational truth, live operational storage being inferred from whichever copy is most convenient, compounding artifacts being discarded because they can theoretically be rebuilt, restore paths being used without legitimate recovery basis, archives being pulled back into live operations because they are available, retention becoming uncontrolled hoarding, deletion happening by silent disappearance, and multi-store growth multiplying ambiguous duplicate stores with no clear control role.

This document is therefore a control document for data storage, persistence, and backup discipline.

It defines what counts as source-of-truth storage, what makes a persisted artifact legitimate, what backup is and is not, what restore legitimacy requires, how retention and archival classes must remain explicit, how deletion must remain governed, how persistence worth keeping differs from disposable duplication, and how compounding knowledge and data assets must remain durable enough that the platform does not repeatedly lose its own hard-won state.

It is the canonical data storage, persistence, and backup standard for the platform. Future shared platform code, pipelines, storage design, derived-artifact handling, backup behavior, restore behavior, archival behavior, retention logic, deletion logic, automation behavior, and domain-local operational handling must align with it unless a formal decision record explicitly revises it.

## Role of This Document in the Platform

This document governs the cross-platform storage, persistence, backup, and deletion posture by which the wider architecture canon remains durably reconstructible over time.

The system layers overview defines persistent graph-backed memory, persistent decision memory, reusable state artifacts, and compounding learning surfaces, but it does not define one shared rule for which storage surfaces count as source-of-truth, which artifacts deserve governed persistence, which copies count only as backup, when restoration is legitimate, or how archival and deletion must remain distinct. The canon navigation and reading-order standard and the canon change-control and quality-gate standard define where this document belongs and how it must enter the canon, but they do not define one shared storage-control posture for live platform artifacts. The commercial value creation and realisation standard defines why weak-value work must be retired, but it does not define how persistent compounding assets should be preserved when they remain worth keeping. The code architecture and modularity standard governs code structure and explicitly does not govern storage role, persistence legitimacy, or backup boundaries. The security and data protection standard governs access posture, secret handling, privileged write paths, destructive authority, and anti-convenience security discipline, but it does not define one shared rule for what should persist, what may be cached only, what belongs in backup lineage, or when archive and deletion are legitimate. The performance, efficiency, and scalability standard governs workload shape, batching, rebuild avoidance, and reuse-before-rebuild discipline, but it does not define one shared storage rule for which artifacts are supposed to exist durably in the first place. The interface standards govern cross-domain coordination and versioned dependency exposure, but they do not define internal storage ownership, persistence worth keeping, backup lineage, or restore legitimacy. The shared evidence, state, chronology, output, execution, and post-mortem standards define object meanings and lineage expectations, but they do not define one shared engineering and operational rule for where those governed artifacts should live durably, when they may be archived, how they are recovered, or when deletion is legitimate. The platform entitlement and scope boundary model defines tenant, reporting, learning, and role-sensitive scope, but it does not define one shared rule for storage role, artifact persistence class, or backup-versus-source-of-truth distinction.

In practical terms, this document governs storage control posture, persistence control posture, backup and recovery control posture, source-of-truth ownership, governed persistent artifacts, cache boundaries, archival boundaries, deletion boundaries, restore legitimacy, backup lineage, artifact persistence lineage, redundant duplicate storage risk, and persistent compounding asset preservation.

This document therefore governs storage durability as part of platform coherence.

## Core Thesis

In the Fourth Form platform, storage, persistence, backup, restoration, archival, retention, and deletion must remain first-class governed platform controls whose source-of-truth ownership, persistence legitimacy, backup lineage, restore legitimacy, recovery readiness, archival class, retention class, and deletion discipline remain explicit enough that the platform can preserve durable truth, preserve durable compounding assets, and recover serious artifacts without silently turning duplication, caching, or rebuild convenience into the storage model.

That is the core thesis.

storage is not the same thing as backup. persistence is not the same thing as caching. backup is not the same thing as source-of-truth. archival is not the same thing as live operational storage. rebuild capability is not the same thing as rebuild preference. recoverability is not the same thing as ordinary availability. retention is not the same thing as uncontrolled hoarding. deletion is not the same thing as silent disappearance.

## What This Standard Is and Is Not

This standard is the shared platform rule for how the system stores, persists, duplicates for backup, restores, archives, retains, and deletes governed platform artifacts and governed operational data surfaces.

It is not a security and access standard. It is not a credential-handling standard. It is not a performance, batching, or workload-shape standard. It is not a code-structure standard. It is not an interface versioning standard. It is not a workflow contract. It is not a vendor-specific backup runbook. It is not a database administration checklist. It is not permission to persist every intermediate artifact because storage is cheap. It is not permission to discard valuable persistent artifacts merely because they can be rebuilt. It is not permission to treat a cache as durable persistence. It is not permission to treat an archive as live operational storage. It is not permission to let a backup copy become operational truth by convenience. It is not permission to let deletion happen by overwrite, rename, or neglect without explicit lineage. It is not permission to multiply redundant duplicate stores because each local team wants its own convenient copy.

A real data storage, persistence, and backup standard means the platform can answer the following questions for any serious artifact or storage surface.

- Which surface is source-of-truth.
- Which artifacts are legitimate governed persistent artifacts.
- Which artifacts are disposable, rebuildable, cached only, archived only, or backup only.
- Which copies belong in backup lineage rather than operational lineage.
- Whether a restore is legitimate for the exact artifact and scope in question.
- Whether retention and archival posture are explicit rather than accidental.
- Whether deletion will remain visible, lineaged, and governance-legible.

## Why a Shared Data Storage, Persistence, and Backup Standard Is Necessary

The platform needs one shared data storage, persistence, and backup rule because weak storage discipline often arrives through convenience before it appears as obvious platform decay. Drift begins when a reusable derived artifact is dropped because it can be rebuilt later, when a cache survives long enough to be treated as persistence, when the same supposedly authoritative result exists in multiple folders and tables, when a backup copy becomes the easiest live source, when archive is used for ordinary operational lookup, when restore is triggered because the copy exists rather than because restore legitimacy has been established, when retention is interpreted as keeping everything forever, and when deletion occurs through replacement or disappearance without explicit record.

If storage, persistence, and backup discipline are left local, several failures follow. One pipeline preserves compounding assets deliberately while another repeatedly reconstructs already-governed artifacts from raw inputs. One area keeps source-of-truth ownership explicit while another lets the most recently touched copy become de facto truth. One team uses backup to protect recovery while another treats backup as a shadow live store. One domain persists only what remains worth keeping while another hoards disposable outputs indefinitely. One area tests restoration honestly while another assumes recoverability because copies exist somewhere. One group archives for long-horizon preservation while another quietly uses archive as live operational storage. The platform then becomes harder to scale, harder to trust, and harder to reconstruct not because it lacks storage capacity, but because it has lost governed meaning about what each stored surface is for.

The platform therefore needs one shared standard so that every domain, every storage-backed process, every automation path, and every future implementation agent inherits the same storage, persistence, backup, archival, and deletion discipline before convenience copies become structural ambiguity.

## Core Concepts

The platform uses the following core concepts.

### Source-of-truth storage

Source-of-truth storage is the governed storage surface whose state is the authoritative operational truth for a defined governed data class or artifact class at a defined layer.

### Governed persistent artifact

Governed persistent artifact is a deliberately preserved artifact whose purpose, ownership, lineage, retention class, and downstream reuse legitimacy are explicit enough that future platform behavior may rely on it intentionally.

### Disposable artifact

Disposable artifact is an artifact whose value does not justify durable persistence beyond its bounded immediate use and whose removal does not destroy serious platform truth or serious compounding asset value.

### Rebuildable artifact

Rebuildable artifact is an artifact that can be reconstructed from governed upstream sources, but whose rebuildability does not by itself decide whether the artifact should be discarded or preserved.

### Irrecoverable-value risk

Irrecoverable-value risk is the governed risk that deleting, failing to persist, or weakly backing up an artifact would destroy durable commercial, analytical, operational, or learning value that later rebuild or recovery could not honestly reconstruct.

### Retention class

Retention class is the governed statement of how long an artifact or storage surface must remain available in active or retained form before archival, destruction, or further review becomes legitimate.

### Archival class

Archival class is the governed statement of how an artifact or storage surface is preserved beyond ordinary live operations for historical, regulatory, recovery, or institutional-memory reasons without thereby remaining live operational storage.

### Restore legitimacy

Restore legitimacy is the governed condition in which a restore action is justified by explicit recovery need, explicit authority, explicit source lineage, explicit target understanding, and explicit awareness of what operational truth would be changed.

### Recovery readiness

Recovery readiness is the governed condition in which backup lineage, restore procedure, target clarity, and restoration testing are strong enough that serious recovery is actually plausible rather than merely assumed.

### Backup lineage

Backup lineage is the reconstructible chain linking a backup copy to the source artifact or storage surface it protects, the time and condition of capture, the retention and archival posture that governs it, and any later restore actions derived from it.

### Artifact persistence lineage

Artifact persistence lineage is the reconstructible chain linking a persisted artifact to its upstream source, persistence decision, validity scope, retention class, archival or deletion transitions, and downstream reuse history.

### Persistence worth keeping

Persistence worth keeping is the governed judgment that an artifact should remain durably stored because its preserved existence materially reduces future loss, materially strengthens future interpretation, or materially preserves a compounding asset the platform would be weaker without.

### Redundant duplicate storage risk

Redundant duplicate storage risk is the governed condition in which materially equivalent artifacts or storage surfaces are being kept in more than one place without explicit differentiated role, creating ambiguity, drift, and unnecessary maintenance burden.

### Silent storage drift

Silent storage drift is the governed condition in which a storage surface gradually changes role in practice from cache to persistence, from backup to live truth, from archive to live reference, or from disposable output to quasi-source-of-truth without explicit governance change.

### Restore-tested backup

Restore-tested backup is a backup copy whose recovery path has been exercised strongly enough that the platform has evidence that restoration is feasible, scoped, and operationally intelligible.

### Persistent compounding asset

Persistent compounding asset is a governed artifact whose preserved existence materially reduces future recomputation, preserves institutional memory, or strengthens later interpretation, simulation, review, learning, or audit trace over time.

### Live operational storage

Live operational storage is storage used for current governed platform operations and current operational truth rather than for backup-only, archive-only, or historical preservation-only purpose.

### Cache

Cache is a bounded acceleration surface that may improve local runtime or convenience but does not by itself become governed persistence, governed backup, or governed source-of-truth.

## Shared Storage Control Posture

Shared storage control posture means the platform treats storage role, storage ownership, and live operational truth as governed control surfaces rather than as implementation residue.

Storage control posture begins with explicit source ownership. Every materially consequential data class and artifact class must have an explicit source-of-truth storage surface or an explicit statement that the class is purely derived and non-authoritative. storage is not the same thing as backup. Live operational storage must remain distinguishable from backup-only, archive-only, and cache-only surfaces strongly enough that later contributors can see what the platform currently believes and where that belief lives.

Storage control posture also requires that convenience copies not acquire meaning accidentally. Local exports, raw file drops, copied tables, NAS folders, scratch schemas, and restored surfaces must not silently become operational truth because they are present and available. When storage role changes, governance must name the change. Silent storage drift is a defect, not an organic convenience.

Storage control posture further requires explicit role separation among live operational storage, archival class, backup lineage, and disposable artifacts. archival is not the same thing as live operational storage. A platform that reads history from archive may do so deliberately, but it must not thereby blur archive into ordinary operational storage.

Finally, shared storage control posture requires that storage design remain reconstructible under scale. When the platform expands from one store to many stores or from one operating path to many, duplicate copies and shadow stores must not multiply without explicit differentiated role. Multi-store growth is not permission to create one more ambiguous truth surface per process.

## Shared Persistence Control Posture

Shared persistence control posture means the platform treats durable artifact preservation as a governed judgment about long-term value rather than as a side effect of whatever happened to remain on disk.

Persistence control posture begins with one serious rule: persistence is not the same thing as caching. A cache may accelerate current work, but it does not by itself become a governed persistent artifact simply because rebuilding it later would be inconvenient. Governed persistence exists only where artifact purpose, lineage, retention class, and downstream reuse legitimacy remain explicit.

Persistence control posture also requires that rebuildability not erase the case for durable persistence. rebuild capability is not the same thing as rebuild preference. Some artifacts can technically be rebuilt and still remain worth keeping because their durable presence preserves compounding value, review trace, institutional memory, or careful processing that the platform should not casually repeat or risk losing.

Persistence control posture further requires discriminating among governed persistent artifacts, rebuildable artifacts, disposable artifacts, and caches. The platform must not hoard disposable outputs indefinitely, but it must not discard persistence worth keeping merely because a raw upstream source exists somewhere. Persistent compounding assets should remain durable enough that future cycles inherit prior work rather than repeatedly acting as if the platform has forgotten what it already knows.

Finally, shared persistence control posture requires anti-duplication discipline. A second persistent copy is legitimate only when it has a materially different role, materially different recovery purpose, or materially different archival or access class. Otherwise it is redundant duplicate storage risk, not healthy resilience.

## Shared Backup and Recovery Control Posture

Shared backup and recovery control posture means the platform treats backup copies, recovery readiness, restoration, and recoverability as governed control surfaces rather than as reassuring folklore about there being copies somewhere.

Backup control posture begins with one non-negotiable boundary: backup is not the same thing as source-of-truth. Backup lineage exists to support recovery, continuity, and protected historical preservation. It does not by itself define current truth, current operational ownership, or permission to treat the backup copy as ordinary live storage.

Backup control posture also requires explicit restore legitimacy. A restore action is not legitimate merely because a backup exists. Restore legitimacy requires explicit recovery need, explicit target clarity, explicit authority, explicit awareness of source and target lineage, and explicit awareness of what present operational truth would be changed.

Backup control posture further requires recovery readiness that is stronger than optimism. recoverability is not the same thing as ordinary availability. A surface may be available now and still be weakly recoverable later. A backup may exist and still be operationally useless if it is untested, weakly scoped, weakly retained, or impossible to restore coherently at the needed granularity. Restore-tested backup is therefore materially stronger than a copy whose restoration has never been exercised.

Finally, shared backup and recovery control posture requires that archival posture and backup posture remain distinct. Some archived artifacts may support historical reconstruction without being suitable for rapid recovery. Some backups may support recovery without thereby becoming the archive of institutional history. Those roles may overlap in parts, but they must not collapse into one vague storage habit.

## Data Storage, Persistence, and Backup Grammar

The platform requires one shared grammar for data storage, persistence, and backup so that future domains, pipelines, and operational surfaces use the same control meanings.

### Source-of-truth governed

Source-of-truth governed is the shared condition in which a storage surface is explicitly declared as the current authoritative operational truth for a defined governed artifact or data class.

### Persistent and governed

Persistent and governed is the shared condition in which an artifact is deliberately preserved because its role, lineage, retention class, and downstream reuse legitimacy are explicit enough for serious later use.

### Rebuildable but not preferred for routine reconstruction

Rebuildable but not preferred for routine reconstruction is the shared condition in which an artifact could be rebuilt from upstream sources but should not be routinely discarded or repeatedly reconstructed merely because that rebuild is technically possible.

### Disposable only

Disposable only is the shared condition in which an artifact has bounded immediate value only and must not survive as durable persistence through inertia.

### Cache only

Cache only is the shared condition in which a surface may improve local runtime or convenience but must not be treated as governed persistence, governed backup, or governed truth.

### Backup only

Backup only is the shared condition in which a copy exists for recovery or continuity and must not be treated as live operational truth.

### Archive only

Archive only is the shared condition in which a stored artifact remains preserved for historical, regulatory, or institutional-memory reasons but is not live operational storage.

### Restore legitimacy confirmed

Restore legitimacy confirmed is the shared condition in which a proposed restore has satisfied explicit recovery need, explicit authority, explicit source and target clarity, and explicit awareness of what current state would be changed.

### Recovery readiness insufficient

Recovery readiness insufficient is the shared condition in which copies may exist but backup lineage, testing, or restore procedure remain too weak for confident serious recovery.

### Redundant duplicate storage risk active

Redundant duplicate storage risk active is the shared condition in which materially equivalent copies are being preserved in more than one place without explicit differentiated role.

### Silent storage drift detected

Silent storage drift detected is the shared condition in which a surface has begun operating as truth, persistence, backup, archive, or cache in ways not explicitly declared.

### Irrecoverable-value risk active

Irrecoverable-value risk active is the shared condition in which failure to persist, back up, archive, or govern deletion would likely destroy durable value the platform could not honestly reconstruct later.

These are shared platform meanings. Domains may add narrower subtypes beneath them, but they may not silently replace them with local-only language such as just keep a copy, cache but we depend on it, backup so it is fine to operate from it, archive because nobody needs it right now, or delete because rebuild is possible. Shared grammar depends on these meanings remaining stable enough that later recovery, review, performance work, security review, and governance can interpret platform storage history coherently.

## Minimum Shared Control Requirements

Every materially consequential storage surface and artifact class must satisfy the following minimum shared control requirements.

### Explicit source-of-truth declaration

Every materially consequential governed data class and governed artifact class must preserve exactly which surface is authoritative current truth and must preserve enough role clarity that no backup, cache, or archive can compete with it by convenience.

### Explicit artifact role declaration

Every materially consequential artifact must preserve whether it is persistent and governed, rebuildable, disposable, backup only, archive only, cache only, or another explicitly governed role.

### Explicit persistence-worth-keeping judgment

Every materially consequential persistent artifact must preserve why it remains worth keeping, what compounding value it protects, and what irrecoverable-value risk would follow from weak persistence.

### Explicit backup lineage and recovery posture

Every materially consequential backup surface must preserve what it protects, what lineage connects it to source truth, what retention or archival class governs it, and what recovery posture or testing status applies.

### Explicit restore legitimacy rule

Every materially consequential restore path must preserve what conditions establish restore legitimacy, who may authorize it, what target it may affect, and what later lineage must record the action.

### Explicit cache and temporary role clarity

Every cache and other disposable or temporary surface must preserve enough bounded role clarity that it cannot drift into quasi-persistence or quasi-truth through habit.

### Explicit retention and archival classification

Every materially consequential storage surface and artifact class must preserve retention class and archival class strongly enough that long-lived storage is intentional rather than accidental.

### Explicit deletion posture

Every materially consequential artifact class must preserve what deletion means, when deletion is legitimate, what prior lineage must be satisfied, and how deletion remains visible after it occurs.

### Explicit duplicate-storage review

Every materially consequential artifact class must remain reviewable strongly enough that later contributors can tell whether multiple copies exist for legitimate differentiated role or only because storage sprawl went unchallenged.

### Explicit lineage for lifecycle transitions

Every materially consequential transition among live truth, persistence, backup, archive, restore, and deletion must preserve enough lineage that later review can reconstruct what changed and why.

## Source-of-Truth, Persistence, and Caching Rules

Source-of-truth, persistence, and caching must remain separate governed states rather than one convenience gradient.

### Source-of-truth ownership rule

Every materially consequential governed data class and artifact class must have one explicit source-of-truth storage surface for its relevant layer. No copied table, copied file, shadow NAS folder, restored directory, or exported artifact may become truth simply because it was the easiest surface to reach. Silent promotion from copy to source-of-truth is a storage failure.

### Persistence legitimacy rule

A governed persistent artifact must preserve explicit purpose, explicit lineage, explicit retention class, and explicit downstream legitimacy. Persistence should exist where durable value truly compounds, not where local convenience simply prefers not to think about deletion.

### Cache-boundary rule

persistence is not the same thing as caching. A cache may be rebuilt, invalidated, or discarded according to acceleration needs. Governed persistence exists to preserve durable value, durable truth, or durable compounding asset meaning. A cache that later becomes required by routine operations has already signaled silent storage drift.

### Rebuild-preference rule

rebuild capability is not the same thing as rebuild preference. If a rebuildable artifact remains a persistent compounding asset, or if repeated reconstruction would risk loss of hard-won processing, hard-won curation, or hard-won learning trace, then discard-by-default is structurally weak even when rebuild is technically possible.

### Disposable-artifact rule

Disposable artifacts must not survive as quasi-persistence merely because no one cleaned them up. Disposable status is a real storage role, not a polite hope that somebody will delete the artifact later.

### Redundant-duplicate rule

Where materially equivalent persistent copies exist in more than one place, the differentiated role must remain explicit. If no differentiated role exists, the platform should treat the situation as redundant duplicate storage risk, not as resilience.

### Persistent-compounding-asset rule

When an artifact materially preserves later interpretation, later simulation, later review, later learning, or later audit trace, it should be treated as a persistent compounding asset and governed accordingly. The platform should not repeatedly reconstruct such value from raw foundations merely because the raw foundations still exist.

## Backup, Restore, Retention, Archival, and Deletion Rules

Backup, restore, retention, archival, and deletion must remain explicit, lineaged, and distinct enough that the platform can preserve what matters without preserving everything forever.

### Backup-role rule

storage is not the same thing as backup. Backup exists to protect recovery and continuity for explicitly governed surfaces. It is not a substitute for deciding what should persist, what is current truth, or what belongs in archive.

### Restore-legitimacy rule

Backup copies may be restored only where restore legitimacy has been established. Restore legitimacy requires an explicit recovery basis, explicit source and target lineage, explicit awareness of what live operational state would be changed, and explicit authority to do so. A copy being available is not sufficient reason to restore it.

### Recovery-readiness rule

recoverability is not the same thing as ordinary availability. A surface may look healthy today while its backups remain untested, badly scoped, or incoherent for real recovery. Restore-tested backup and explicit recovery readiness are therefore materially stronger than optimistic copy existence.

### Archival-boundary rule

archival is not the same thing as live operational storage. Archived artifacts may remain preserved for historical, regulatory, institutional-memory, or deep-recovery reasons, but they must not be allowed to function as ordinary live operational stores without explicit governance change.

### Retention-boundary rule

retention is not the same thing as uncontrolled hoarding. Retention class must define how long an artifact remains live, retained, or eligible for archive. Keeping everything forever is not storage discipline. It is refusal to govern deletion and archival honestly.

### Deletion-boundary rule

deletion is not the same thing as silent disappearance. Deletion must remain an explicit lineaged state transition, not an accidental result of overwrite, replacement, path reuse, or cleanup drift. The platform must be able to say what was deleted, from where, under what authority, and after what retention and archival conditions were satisfied.

### Archive-versus-backup rule

Archive and backup may both preserve copies, but they do not mean the same thing. Archive preserves long-horizon historical posture. Backup protects recoverability. Either one may be badly governed if it is allowed to masquerade as live operational truth.

## Lineage Rules

Storage and persistence lineage must remain reconstructible enough that later review can tell what the platform knew, where it preserved that knowledge, how it protected it, and how it later moved or removed it.

Every materially consequential source-of-truth surface must preserve lineage to its owning artifact class and its storage role. Every governed persistent artifact must preserve artifact persistence lineage to upstream source, persistence decision, retention class, archival transitions where relevant, and deletion state where relevant. Every backup must preserve backup lineage to what it protects, when it was captured, how it was classified, and whether it was later restore-tested or restored. Every restore must preserve lineage to the backup source, the recovery decision, the target, and the resulting operational state. Every archived artifact must preserve lineage to the live or retained state from which it was archived. Every deletion must preserve lineage to the prior retained or archived state that permitted the deletion.

Lineage therefore constrains more than history. It constrains legitimacy. A restored artifact with weak lineage is weaker than a backed-up artifact with strong lineage. A persistent artifact with weak lineage is weaker than a smaller but clearly lineaged artifact. A deleted artifact without preserved transition record has not been governed honestly.

This document governs storage-role lineage, persistence lineage, backup lineage, archive lineage, restore legitimacy lineage, and deletion lineage. The shared chronology standard continues to govern chronology meaning, and the shared object standards continue to govern the object meanings carried through those lines.

## Domain Inheritance Rules

Every current and future domain must inherit this standard as a minimum shared storage, persistence, and backup control layer.

Domain-local workflow contracts, storage surfaces, feature stores, decision memory stores, post-mortem stores, output packages, backups, archives, and automation paths may narrow these controls but must not weaken them. Every domain must preserve explicit source-of-truth ownership, explicit artifact role clarity, explicit backup lineage, explicit restore legitimacy, explicit retention and archival classes, and explicit deletion posture for materially consequential artifacts.

Domains may define narrower persistence-worth-keeping criteria, narrower retention classes, narrower archival classes, narrower backup cadences, or stricter restore prerequisites where local reality requires them. They may not redefine cache as persistence, backup as truth, archive as live operational storage, or deletion as something that may happen by disappearance.

This shared rule sits beneath domain-local operating logic and beside the security, performance, and boundary standards. Security continues to govern access posture and destructive authority. Performance continues to govern workload shape, rebuild avoidance, and reuse-before-rebuild efficiency. This standard governs which artifacts and surfaces those adjacent controls are actually operating over in storage reality.

## Domain Extension Rules

Valid domain extension may include richer artifact-role taxonomies, narrower persistence-worth-keeping tests, stricter backup-testing discipline, stricter restore prerequisites, or narrower retention and archival classes where domain-local reality requires them.

Invalid domain extension occurs when a domain introduces local-only meanings for source-of-truth storage, governed persistent artifact, cache, backup copy, archival class, retention class, restore legitimacy, or deletion that are incompatible with this shared grammar. Invalid extension also occurs when local convenience copies, scratch tables, export folders, archives, or restored surfaces begin functioning as live truth or live persistence without explicit governance change.

future storage extensions must be placed according to control role, not convenience.

If a change defines shared access and credential posture, it belongs in the security and data protection standard, not here. If a change defines rebuild avoidance, workload shape, memory or batching preference, it belongs in the performance, efficiency, and scalability standard, not here. If a change defines code modularity or repository structure, it belongs in the code architecture and modularity standard, not here. If a change defines shared object meaning, it belongs in the objects canon, not here. If a change defines cross-domain interface exposure or versioning, it belongs in the interfaces canon, not here. If a change defines one domain's local operational storage ritual beneath this shared rule, it belongs in that domain's contract or local operational guidance, not here.

## Governance Linkage

This standard is directly governance-linked because it affects what the platform treats as current truth, what it preserves durably, what it duplicates for recovery, what it archives, what it restores, and what it is willing to delete.

Changes to shared source-of-truth ownership rules, shared persistence legitimacy rules, shared backup boundaries, shared restore legitimacy rules, shared archival class rules, shared retention class rules, shared deletion discipline, or shared duplicate-storage posture are consequential shared-platform changes. Where those changes materially affect learning scope, reporting scope, role-sensitive visibility, destructive state transitions, or cross-domain operational dependency, the stricter approval path in the governance authority matrix controls. In practice this means Architecture Authority review is materially relevant, Governance and Boundary Authority review is materially relevant where scope or visibility implications arise, Implementation Authority review is materially relevant because storage changes are operationally consequential, affected Domain Authority review is materially relevant wherever domain-local persistent surfaces change, and Platform Owner approval remains necessary wherever the change alters shared platform behavior. Commercial Authority review is also materially relevant where persistent compounding assets, discard-by-rebuild posture, or long-horizon archival decisions materially affect value retention.

The security and data protection standard should treat this file as the controlling reference for source-of-truth ownership, persistence role, backup lineage, archive boundaries, and deletion legitimacy whenever access-safe operational behavior still depends on those storage meanings. The performance, efficiency, and scalability standard should treat it as the controlling reference for what persisted artifacts exist legitimately in the first place whenever reuse-before-rebuild discipline is applied. The shared state, evidence, output, execution, post-mortem, and chronology standards should treat it as the controlling reference whenever their governed artifacts depend on durable storage role, archive posture, restore legitimacy, or deletion discipline without redefining those storage meanings themselves.

## Failure Modes in Data Storage, Persistence, and Backup Design

Weak storage and persistence design creates direct platform risk.

### Backup mistaken for source-of-truth

A backup copy, restored copy, or protective duplicate begins functioning as current operational truth because it is available and convenient.

### Cache promoted into persistence

A local acceleration layer, temporary store, or convenience surface quietly becomes required by operations even though its role was never governed as persistence.

### Rebuild preference destroying compounding value

The platform discards governed artifacts because they can be rebuilt, and later loses durable curation, durable lineage, or durable interpretive value that honest rebuilding does not restore.

### Silent storage drift across copies

Files, tables, folders, or marts gradually change role from cache to persistence, persistence to shadow truth, or archive to live storage without governance ever naming the transition.

### Archive used as live operational storage

Historical or archival surfaces are pulled back into ordinary platform operation because they are present, even though their retention, indexing, and lineage posture were never intended for live truth.

### Redundant duplicate storage sprawl

The same controlled result exists durably in many places with no differentiated role, and the platform can no longer tell which one should be trusted or maintained.

### Restore without legitimacy

Restoration happens because copies exist, not because recovery need, target clarity, source lineage, and operational consequences were all made explicit first.

### Retention by hoarding instinct

Artifacts remain forever because deletion feels risky and storage feels cheap, even though their role, class, and future usefulness were never governed honestly.

### Deletion by silent disappearance

Artifacts vanish through overwrite, replacement, directory cleanup, path reuse, or neglected expiry with no explicit lineaged deletion state.

### Recovery readiness assumed but untested

A platform believes it is recoverable because backups exist somewhere, but restore testing, scope clarity, or operational restore procedure have never been exercised seriously.

These failure modes are not minor storage untidiness. They are ways the platform can keep running while losing the ability to say where truth lives, what knowledge it has preserved, and what it could honestly recover after serious failure.

## Non-Negotiables

1. storage is not the same thing as backup.
2. persistence is not the same thing as caching.
3. backup is not the same thing as source-of-truth.
4. archival is not the same thing as live operational storage.
5. rebuild capability is not the same thing as rebuild preference.
6. recoverability is not the same thing as ordinary availability.
7. retention is not the same thing as uncontrolled hoarding.
8. deletion is not the same thing as silent disappearance.
9. source-of-truth ownership, persistence legitimacy, backup lineage, restore legitimacy, and deletion lineage must remain explicit for materially consequential artifacts.
10. future storage extensions must be placed according to control role, not convenience.

## Closing Statement

The Fourth Form platform cannot remain a serious decision system if it forgets what should persist, mistakes copies for truth, or lets deletion and restoration happen as side effects of convenience.

This standard therefore fixes the shared platform rule for how storage, persistence, backup, archival, retention, restoration, and deletion must remain explicit, lineaged, and governance-legible across code, pipelines, storage surfaces, automation, and future scale. It protects the platform from shadow truth, cache drift, archive misuse, restore illegitimacy, uncontrolled hoarding, and silent disappearance. And it ensures that the platform preserves the durable assets it should keep while removing what it no longer needs under explicit governed discipline rather than by accident.