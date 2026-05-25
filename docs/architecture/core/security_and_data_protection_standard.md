# Security and Data Protection Standard for the Fourth Form Retail Decision Intelligence Platform

## Purpose of This Document

This document defines the shared platform standard for security and data protection across all current and future implementation, storage, pipeline, automation, backup, recovery, and operational handling work.

It exists because the platform now has governed standards for canon structure, lifecycle composition, intervention policy, commercial value, code architecture, interface governance, evidence, state, failure handling, capability boundaries, chronology, and platform approval authority, but it still lacks one shared core control for how data, secrets, storage surfaces, write paths, destructive actions, and security-sensitive operational behavior must be governed so that the platform remains trustworthy as it scales.

Without a shared standard, the platform will drift into buried credentials in code and notebooks, hidden write destinations inside scripts and pipelines, ad hoc duplication of governed data across NAS and local files and SQL scratch surfaces, ambiguous source-of-truth ownership, insecure temporary artifacts that become quasi-permanent, convenience automation with production-like destructive access, backups that silently become operational truth, weak retention and destruction discipline, broad observability surfaces that expose more than they should, and later incident review that cannot reconstruct what was read, modified, copied, restored, or deleted.

This document is therefore a control document for security and data protection discipline.

It defines what shared security control posture means, what shared data protection posture means, how data classification and sensitivity handling must remain explicit, how storage boundaries must be preserved across network-attached storage, SQL, raw files, processed data, derived artifacts, backups, and recovery copies, how credentials and secrets must be handled, how least-privilege access and modification authority must remain distinct, how retention and destruction must be governed, how auditability and lineage must remain reconstructible, and how automation must remain safe rather than merely convenient.

It is the canonical security and data protection standard for the platform. Future shared platform code, pipelines, data-storage design, automation, operational tooling, backup behavior, recovery behavior, retention logic, and domain-local operational handling must align with it unless a formal decision record explicitly revises it.

## Role of This Document in the Platform

This document governs the cross-platform security and data-protection posture by which the wider architecture canon remains operationally safe.

The system layers overview defines the structural stack and requires observability, missingness, contradiction, and lineage to remain visible, but it does not define one shared rule for how storage surfaces, destructive paths, backup surfaces, recovery paths, and secret-bearing operational behavior must be governed. The canon navigation and reading-order standard and the canon change-control and quality-gate standard define where this document belongs and how it must enter the canon, but they do not define one shared security-control posture for live data and operational surfaces. The decision-mode and intervention-policy standard governs what the platform may legitimately do with a case, but it does not define how data access, storage modification, or automation access should remain bounded underneath that handling. The commercial value creation and realisation standard defines why work must remain worth keeping, but it does not define how storage integrity, access control, and destructive operations must remain safe while that work evolves. The policy-learning evidence admission and update-threshold standard governs when evidence may influence policy change, but it does not define how the underlying data and artifacts must be stored, copied, backed up, restored, or destroyed. The code architecture and modularity standard governs implementation structure, but it explicitly does not govern security, storage, backup, or automation posture. The cross-domain coordination and governed dependency standards govern interfaces and dependency evolution, but they do not define internal storage ownership, secret handling, destructive access, or backup and recovery boundaries. The shared evidence, state, failure-state, capability-boundary, and chronology standards define object meanings and downstream lineage, but they do not define one shared engineering and operational rule for how security-sensitive storage and access behavior must be controlled beneath those objects. The platform entitlement and scope boundary model defines tenant, reporting, learning, decision, and role-sensitive access scope, but it does not define one shared rule for credential handling, write-path safety, storage ownership, destructive authority, retention, or backup discipline.

In practical terms, this document governs security control posture, data protection posture, sensitivity and storage classification, source-of-truth ownership, privileged write paths, least-privilege access, secret externalization, environment separation where relevant, audit trace expectations, destructive-operation discipline, backup and recovery boundaries, retention and destruction discipline, suspicious-state escalation, and safe automation behavior.

This document therefore governs security and data protection as part of platform coherence.

## Core Thesis

In the Fourth Form platform, security and data protection must remain first-class governed platform controls whose storage ownership, access posture, modification authority, credential handling, backup posture, recovery posture, retention boundary, destruction boundary, and audit trace remain explicit enough that the platform can preserve operational truth, protect sensitive data, and support future change without silently eroding integrity.

That is the core thesis.

security is not the same thing as performance. data protection is not the same thing as backup by itself. backup is not the same thing as source-of-truth storage. access capability is not the same thing as authority to modify. automation permission is not the same thing as unrestricted data access. observability is not the same thing as broad data exposure. development convenience is not the same thing as acceptable security posture.

## What This Standard Is and Is Not

This standard is the shared platform rule for how the system stores, accesses, protects, copies, restores, retains, destroys, and audits governed data and security-sensitive operational surfaces.

It is not an object-meaning standard. It is not a domain-local workflow note. It is not an interface versioning standard. It is not a code modularity standard. It is not a performance or efficiency control. It is not a generic compliance checklist. It is not a vendor-specific access runbook. It is not a product-facing permissions page. It is not a local implementation checklist. It is not permission to treat storage choices as engineering convenience only. It is not permission to treat broad access as harmless because the team is trusted. It is not permission to let backups substitute for source ownership. It is not permission to let logs, dashboards, traces, exports, scratch files, or convenience notebooks expose governed data more broadly than entitlement and control posture allow. It is not permission to bury credentials in code, pipelines, SQL files, NAS mounts, temporary directories, or AI-assisted scripts. It is not permission to treat ad hoc restores, ad hoc deletes, or ad hoc raw-file copies as ordinary low-risk operations.

A real security and data protection standard means the platform can answer the following questions for any serious storage or operational surface.

- What data class or sensitivity posture is present.
- Which storage surface is source of truth, which are derived, and which are temporary.
- Which identities may read, write, restore, delete, or rotate that surface.
- Whether a write path is privileged, controlled, and auditable.
- Whether a backup copy is distinct from operational truth.
- Whether retention and destruction boundaries are explicit.
- Whether suspicious access, unsafe write, or unauthorized modification can be reconstructed and escalated.

## Why a Shared Security and Data Protection Standard Is Necessary

The platform needs one shared security and data protection rule because weak security posture and weak data-protection posture often arrive through convenience before they appear as obvious failure. Drift begins when a raw extract is copied to one more NAS folder, when a SQL scratch table becomes the easiest operational truth, when a local notebook receives a secret because that is faster than using a governed access path, when a backup copy is used as though it were current truth, when temporary artifacts stop being temporary, when automation receives broader access than its real purpose requires, when a restore path overwrites live data silently, and when deletion or replacement happens without preserved lineage.

If security and data protection are left local, several failures follow. One team preserves source ownership explicitly while another lets storage truth drift across files and tables. One pipeline writes to governed storage through an explicit privileged path while another writes through hidden destinations embedded in scripts. One domain narrows access to the least privilege necessary while another gives read and write authority together because separation feels slower. One backup posture preserves recovery clearly while another lets archival copies become shadow operational stores. One automation flow uses scoped service identity while another uses shared broad credentials. One team logs enough for audit trace while another cannot later reconstruct who modified what or why. The platform then becomes harder to trust not because the architecture is weak in theory, but because operational truth and operational control have decayed in practice.

The platform therefore needs one shared standard so that every domain, every pipeline, every automation path, and every future implementation agent inherits the same security and data-protection discipline before local convenience becomes structural risk.

## Core Concepts

The platform uses the following core concepts.

### Security control posture

Security control posture is the governed platform position describing how identities, storage surfaces, access rights, write paths, secret-bearing operations, and suspicious conditions are controlled strongly enough to prevent unauthorized exposure, modification, or destructive drift.

### Data protection posture

Data protection posture is the governed platform position describing how governed data remains accurate, durable, reconstructible, recoverable, and properly destroyed when required without confusing protection with duplication alone.

### Sensitivity class

Sensitivity class is the governed statement of how harmful unauthorized exposure, modification, or deletion would be for a data class, storage surface, or derived artifact.

### Source-of-truth storage

Source-of-truth storage is the governed storage surface whose state is the authoritative operational truth for a defined data class, object class, or decision-support artifact at a defined layer.

### Derived storage

Derived storage is the governed storage surface containing transformed, summarized, modeled, aggregated, or otherwise derived artifacts that depend on source-of-truth storage without becoming the primary operational truth for that source.

### Temporary artifact

Temporary artifact is an intentionally short-lived extract, cache, scratch file, working table, staging object, or intermediate output whose existence is bounded by explicit purpose, short-lived handling, and non-source-of-truth status.

### Storage owner

Storage owner is the governed accountable owner for a storage surface, including its source-of-truth status, write posture, retention boundary, backup relationship, and destructive controls.

### Credential

Credential is the governed authenticator or identity-bearing access mechanism used to prove that a human, service, pipeline, or tool may request access to a system or storage surface.

### Secret

Secret is the governed confidential value whose disclosure would undermine security control posture, including passwords, tokens, keys, certificates, signing material, connection secrets, and similar sensitive values.

### Privileged write path

Privileged write path is the governed path through which a human or service may materially modify source-of-truth storage or another high-consequence governed surface.

### Least-privilege access

Least-privilege access is the governed rule that an identity receives no broader read, write, restore, delete, export, or secret-access capability than is required for its legitimate role.

### Retention boundary

Retention boundary is the governed condition, duration, or lifecycle threshold beyond which a governed data class or artifact may not continue to remain in active or retained storage without explicit preserved justification.

### Destruction boundary

Destruction boundary is the governed condition under which governed data, secrets, backups, temporary artifacts, or derived artifacts must be deleted, revoked, or irreversibly destroyed from the relevant storage surfaces.

### Backup copy

Backup copy is the governed duplicate preserved for recovery, continuity, or archival protection that remains distinct from operational source-of-truth storage.

### Recovery copy

Recovery copy is the governed restored or staged copy used to recover from loss, corruption, or destructive failure under explicit recovery controls and explicit lineage.

### Audit trace

Audit trace is the reconstructible governed record of materially relevant access, modification, restore, retention-transition, destruction, secret-use, or authority-sensitive operational handling.

### Suspicious access state

Suspicious access state is the governed condition in which an access attempt or access pattern is materially inconsistent with expected identity, scope, timing, environment, storage class, or entitlement posture and therefore requires explicit review.

### Unsafe write state

Unsafe write state is the governed condition in which a proposed or active write path is too weakly controlled, too broadly scoped, too ambiguous in destination, or too weakly authorized to be treated as safe continuation.

### Unauthorized modification state

Unauthorized modification state is the governed condition in which governed data, schema, storage content, configuration, or critical artifact has been materially changed without valid authority, valid path control, or valid audit trace.

### Environment separation

Environment separation is the governed distinction that keeps local, development, testing, recovery, and live operational surfaces from being treated as interchangeable where that distinction is materially relevant to security or integrity.

### Destructive operation

Destructive operation is a governed write, overwrite, delete, truncate, revoke, rotate, restore, or replacement action whose consequence can materially alter or erase operational truth, security posture, or future recoverability.

## Shared Security Control Posture

Shared security control posture means the platform treats identities, secrets, access scope, privileged write paths, destructive operations, observability surfaces, and suspicious conditions as governed control surfaces rather than as implementation detail.

Security control posture begins with explicit identity and access discipline. Every materially sensitive storage or operational surface must have a known owner, a known access posture, and a known separation between what may be observed, what may be modified, and what may be destroyed. access capability is not the same thing as authority to modify. A role, script, service, notebook, or agent may be able to connect to a surface without thereby being entitled to write, restore, rotate, or delete it.

Security control posture also requires that secret-bearing behavior remain externalized and governed. Credentials and secrets must remain in explicit, reviewable control surfaces rather than being embedded in code, local files, exported SQL, convenience scripts, agent prompts, temporary artifacts, or undocumented operational rituals. A platform that cannot say where its secrets live or who is using them does not have serious security posture.

Security control posture further requires that broad access not be justified by convenience alone. automation permission is not the same thing as unrestricted data access. Service identities, data-movement jobs, model runners, backup agents, reporting jobs, and implementation tools must operate under the narrowest access that still allows their legitimate task. development convenience is not the same thing as acceptable security posture.

Security control posture also constrains observability. observability is not the same thing as broad data exposure. Logs, traces, dashboards, debugging exports, and instrumentation surfaces may support operations only when they preserve the minimum exposure needed for that purpose and do not become informal disclosure channels for governed data or secrets.

Finally, shared security control posture requires explicit response to suspicious conditions. Suspicious access state, unsafe write state, and unauthorized modification state must remain explicit, traceable, and escalatable. This document governs their security meaning. The shared exception and failure-state standard continues to govern how those states interact with broader recovery, quarantine, and invalid-episode handling.

## Shared Data Protection Posture

Shared data protection posture means the platform treats operational truth, derived artifacts, temporary artifacts, backups, recovery copies, retention, and destruction as distinct governed states rather than as one blurred storage habit.

Data protection posture begins with explicit source ownership. Every governed data class and materially consequential artifact must have a declared source-of-truth storage surface, declared derived surfaces where relevant, declared temporary surfaces where relevant, and declared backup and recovery relationships. backup is not the same thing as source-of-truth storage. A platform that cannot say where current truth lives has already weakened its data protection posture.

Data protection posture also requires that copying, transformation, and restoration remain controlled. data protection is not the same thing as backup by itself. Backups may protect recoverability, but they do not by themselves define ownership, current operational truth, write authority, or valid deletion posture. Likewise, duplicated files, copied tables, exported CSVs, replicated NAS folders, and shadow marts are not protection merely because they exist. Uncontrolled duplication is often a form of protection failure rather than protection success.

Data protection posture further requires explicit destructive discipline. Source-of-truth data must not be silently overwritten, casually deleted, or replaced through convenience restore paths. Destructive operations may occur only through explicit authority, explicit audit trace, and explicit awareness of source ownership, backup posture, retention status, and recovery consequences.

Data protection posture also requires environment and storage clarity. Where live operational surfaces, testing surfaces, local experimentation, recovery staging, and derived analytics coexist, the platform must preserve enough separation that local convenience cannot blur operational truth, entitlements, or destructive consequences.

Finally, shared data protection posture requires that lifecycle handling remain explicit. Retention boundary and destruction boundary must be preserved distinctly. Temporary artifacts must expire or be destroyed explicitly. Derived storage must preserve lineage to source-of-truth storage. Recovery copies must remain explicit recovery surfaces rather than becoming shadow operational truth.

## Security and Data Protection Grammar

The platform requires one shared grammar for security and data protection so that future domains, pipelines, and operational surfaces use the same control meanings.

### Sensitivity-qualified storage

Sensitivity-qualified storage is the shared condition in which a storage surface or artifact carries an explicit sensitivity class and explicit control expectations rather than being treated as neutral by default.

### Source-of-truth governed

Source-of-truth governed is the shared condition in which a storage surface is explicitly declared as authoritative operational truth for a defined governed data class.

### Derived but not authoritative

Derived but not authoritative is the shared condition in which a storage surface may be used operationally or analytically only as a derivative of authoritative truth rather than as independent source ownership.

### Temporary only

Temporary only is the shared condition in which an artifact is permitted solely for bounded intermediate use and must not become durable operational truth, durable export surface, or durable secret-bearing surface.

### Read permitted

Read permitted is the shared condition in which an identity may inspect a governed surface within explicit scope and sensitivity boundaries.

### Write permitted

Write permitted is the shared condition in which an identity may modify a governed surface only through an explicit controlled path and within explicit modification scope.

### Privileged write required

Privileged write required is the shared condition in which any modification to a governed surface must pass through a privileged write path with stronger authority and stronger audit trace than ordinary read access.

### Delete prohibited pending governance

Delete prohibited pending governance is the shared condition in which destruction or removal of governed data remains blocked until retention, authority, recovery, and audit conditions have been satisfied.

### Backup only

Backup only is the shared condition in which a copy exists for recovery or archival protection and must not be treated as operational source ownership.

### Recovery pending

Recovery pending is the shared condition in which a recovery copy exists or a restore is being considered, but operational truth has not been redefined by convenience.

### Suspicious access state

Suspicious access state is the shared condition in which access posture is materially inconsistent with expected control rules and must be explicitly reviewed.

### Unsafe write state

Unsafe write state is the shared condition in which a write path, destination, authority basis, or control posture is too weak for safe continuation.

### Unauthorized modification state

Unauthorized modification state is the shared condition in which change has occurred outside valid modification authority, valid privileged path, or valid audit trace.

These are shared platform meanings. Domains may add narrower subtypes beneath them, but they may not silently replace them with local-only language such as quick copy, scratch truth, temporary prod access, harmless restore, or one-off admin write. Shared grammar depends on these meanings remaining stable enough that auditability, recovery, retention, post-mortem review, and future incident handling can interpret platform history coherently.

## Minimum Shared Control Requirements

Every materially consequential storage, pipeline, automation, and operational surface must satisfy the following minimum shared control requirements.

### Explicit sensitivity and ownership

Every governed data class, source-of-truth store, derived store, backup surface, recovery surface, and temporary artifact class must preserve explicit sensitivity posture and explicit accountable storage ownership.

### Explicit source-of-truth declaration

Every materially consequential data class must preserve exactly which storage surface is authoritative operational truth, and that declaration must remain explicit enough that derived surfaces, exports, and recovery copies cannot compete with it by convenience.

### Explicit read, write, and delete posture

Every materially consequential storage surface must preserve whether read is permitted, whether write is permitted, whether privileged write is required, whether delete is prohibited pending governance, and who may perform those actions.

### Explicit credential and secret externalization

Every credential and secret used for governed platform access must remain externalized, reviewable, rotatable where relevant, and absent from code, static local files, and convenience operational artifacts.

### Explicit audit trace for material control actions

Every privileged write, destructive operation, recovery action, retention transition, destruction action, and materially sensitive secret-use surface must preserve enough audit trace that later review can reconstruct who acted, what changed, when it changed, and under what authority.

### Explicit environment and storage separation where relevant

Where local, testing, recovery, and live operational surfaces coexist, their identities, write paths, and secrets must remain separated strongly enough that convenience tooling cannot casually act on the wrong environment.

### Explicit automation scope

Every service identity, scheduled job, pipeline, agent, automation script, and operational helper must preserve explicit access scope, explicit write scope where relevant, and explicit prohibition against broader access than its legitimate task requires.

### Explicit retention and destruction posture

Every materially consequential data class and artifact class must preserve retention boundary and destruction boundary strongly enough that data does not remain forever by neglect or disappear by convenience.

### Explicit backup and recovery distinction

Every backup and recovery surface must preserve whether it is backup only, recovery pending, or restored under governance, and that distinction must remain visible enough that backup handling does not silently redefine operational truth.

### Explicit suspicious-state escalation

Every suspicious access state, unsafe write state, and unauthorized modification state must remain visible enough that the platform can escalate, contain, review, and later reconstruct the condition rather than smoothing it away into routine operations.

## Environment and Storage Boundary Rules

Environment and storage boundaries must remain explicit enough that the platform can tell where truth lives, where derivative work lives, where temporary work lives, and which surfaces may be modified under which controls.

### Source-of-truth ownership rule

Every materially consequential data class must have explicit source-of-truth storage ownership. No raw file landing zone, SQL schema, NAS folder, export bucket, processed mart, or analytics cache may become source-of-truth by habit or by search convenience. no ambiguous storage ownership.

### NAS, raw-file, and landing-zone rule

Network-attached storage, raw-file landing zones, file drops, exports, and shared folders must not become shadow operational truth merely because they are easy to access. If a NAS path or raw-file surface is source-of-truth storage, that ownership must be declared explicitly. If it is not, then derived or temporary status must remain explicit and write authority must remain bounded accordingly.

### SQL and structured-store rule

SQL databases, tables, schemas, and equivalent structured stores must not be used as informal scratch truth when they hold governed operational data. Separate structured stores may exist for source-of-truth storage, derived storage, temporary staging, recovery staging, and reporting access, but each role must remain explicit and must not blur through convenience queries or convenience scripts.

### Processed, derived, and export-surface rule

Processed datasets, feature stores, aggregates, summaries, model outputs, post-mortem extracts, and other derived artifacts must preserve lineage to their authoritative upstream surfaces and must not silently compete with source-of-truth ownership. no uncontrolled data copying.

### Temporary-artifact rule

Temporary artifacts must remain bounded in location, duration, secret exposure, and allowed use. Insecure temporary artifacts are structurally weak because they turn short-lived convenience into ungoverned storage. Temporary artifacts must not hold buried secrets, must not become durable reporting surfaces, and must not silently survive past their stated retention boundary.

### Hidden-destination prohibition rule

Every materially consequential write destination must be explicit. no hidden write destinations. Pipelines, scripts, local tools, SQL jobs, restore jobs, and agent-assisted operational helpers must not conceal write targets in environment side channels, undocumented defaults, or convenience branches.

### Overwrite and delete boundary rule

no silent overwrite of governed data. no casual deletion of source-of-truth data. Source-of-truth data and other governed storage surfaces may be modified or destroyed only through explicit governed paths, explicit authority, explicit audit trace, and explicit awareness of backup, retention, and recovery posture.

### Environment-separation rule

Where development, testing, recovery, and live operational environments all exist, they must not share secrets, destructive permissions, or ambiguous write paths in ways that make accidental live modification plausible. Production-like access from convenience scripts, ad hoc notebooks, and local experimentation is structurally weak even when no incident has yet occurred.

## Access, Credential, and Secret Handling Rules

Access posture must remain explicit, narrowed, and distinguishable from modification authority.

### Least-privilege access rule

Every human and service identity must receive the narrowest read, write, restore, delete, export, and secret-access capability that still permits its legitimate role. Over-broad default access is not a neutral baseline. It is an unresolved control weakness.

### Capability-versus-modification rule

access capability is not the same thing as authority to modify. A user, service, or automation path may be able to see, query, or inspect a governed surface without being entitled to change it. Read posture, write posture, destructive posture, and recovery posture must remain separate enough that broad inspection access does not silently become modification power.

### Credential and secret rule

no buried secrets in code. Credentials and secrets must not be embedded in code, infrastructure templates without proper secret externalization, SQL scripts, notebook cells, command history, raw files, NAS shares, exported archives, temporary artifacts, or agent instructions. Credentials and secrets must remain externalized, rotatable where relevant, and bounded by accountable ownership.

### Privileged-write-path rule

Material modification to source-of-truth storage, schema-bearing structures, governed derived surfaces, destructive operations, and recovery actions must use explicit privileged write paths. Privileged write paths must remain narrow, auditable, and separable from ordinary read access and ordinary analytical access.

### Automation-scope rule

automation permission is not the same thing as unrestricted data access. Service identities, scheduled jobs, ETL, reporting exporters, backup agents, restore tooling, and AI-assisted operational helpers must not receive broader access than the exact storage class and action class they legitimately require. no convenience scripts with production-like destructive access.

### Observability-narrowing rule

observability is not the same thing as broad data exposure. Logs, metrics, traces, dashboards, debug captures, and operational summaries must reveal only what is necessary for serious operations, troubleshooting, or governance review. Sensitive raw payloads, secrets, and broad governed data extracts must not be disclosed simply because instrumentation can technically carry them.

### Suspicious-access escalation rule

Suspicious access state must trigger explicit review, narrowed continuation, containment, or stronger failure-state handling where relevant. This standard governs that suspicious state is security-relevant. The shared failure-state standard continues to govern whether the broader episode enters degraded, blocked, quarantined, or invalid handling.

## Backup, Recovery, Retention, and Destruction Rules

Backup, recovery, retention, and destruction must remain separate governed states rather than one blurred storage habit.

### Backup-discipline rule

data protection is not the same thing as backup by itself. backup is not the same thing as source-of-truth storage. Backup copies exist to support recovery, continuity, or archival protection. They do not by themselves define current operational truth, current write authority, or permission for convenience restore.

### Recovery-discipline rule

Recovery copies and restore paths must preserve explicit lineage to the source surface, the backup source, the recovery objective, and the authority under which restore occurs. A recovery copy must not silently become current operational truth merely because it is the fastest available surface.

### Retention-boundary rule

Retention boundary must be explicit for source-of-truth storage, derived storage, temporary artifacts, backups, recovery copies, logs, and secret-bearing operational material where relevant. Data must not remain indefinitely in every surface by neglect, fear of deletion, or storage convenience.

### Destruction-boundary rule

Destruction boundary must be explicit, reviewable, and auditable. Destroying data, destroying secrets, revoking credentials, removing temporary artifacts, or retiring backups must preserve enough record that later review can reconstruct what was removed, under what authority, and whether retention and recovery obligations were satisfied first.

### Backup-versus-operational-truth rule

no backup strategy that blurs operational truth and archival recovery. Backup posture may support resilience, but it must not create competing operational stores, uncontrolled restore habits, or ambiguity about which surface is current truth.

### Destructive-access rule

Delete, truncate, restore-overwrite, schema-replacement, and similar destructive acts must not be available through broad default roles, convenience notebooks, broad service credentials, or operational shortcuts. Destructive capability belongs only in explicit privileged paths with explicit audit trace.

## Lineage Rules

Security and data protection lineage must remain reconstructible enough that later review can distinguish safe handling from convenience drift.

Every materially consequential governed surface must preserve lineage to its storage owner, source-of-truth status, derived status where relevant, backup relationship where relevant, recovery relationship where relevant, retention boundary, and destruction boundary. Every materially consequential privileged write must preserve lineage to the acting identity, the authorized path, the modified surface, and the resulting state. Every materially consequential restore must preserve lineage to the source backup and the recovery decision that justified it. Every materially consequential destruction act must preserve lineage to the retention and destruction posture that permitted it.

Audit trace must therefore connect who accessed, who modified, who restored, who deleted, what surface was affected, what authority or privileged path allowed that act, and what later state resulted. Security review, post-mortem review, and future corrective control design all depend on that trace remaining reconstructible.

Lineage also constrains copying and replacement. Derived artifacts must preserve lineage to authoritative upstream truth. Recovery copies must preserve lineage to backup source and restore decision. Later copied or restored surfaces must not erase the earlier fact that the platform once held a different active truth. Silent replacement destroys security lineage as well as data lineage.

This document governs the shared lineage expectations for security-sensitive operational handling. The shared decision timeline and event chronology standard remains the controlling object standard for chronology meaning, and the shared evidence, state, and failure-state standards remain the controlling object standards for their own object lineages.

## Domain Inheritance Rules

Every current and future domain must inherit this standard as a minimum shared control layer.

Domain-local workflow contracts, storage designs, reporting exports, learning pipelines, local automation, post-mortem tooling, local SQL handling, raw-file handling, backup handling, and recovery handling may narrow these controls but must not weaken them. Every domain must preserve explicit storage ownership, explicit access posture, explicit write and delete posture, explicit secret handling, explicit backup and recovery distinction, explicit retention and destruction rules, and explicit audit trace for materially consequential control actions.

Domain-local contracts may define narrower sensitivity classes, narrower environment separations, narrower privileged write approvals, narrower retention windows, or stricter recovery discipline. They may not redefine source-of-truth ownership casually, broaden access beyond least privilege, treat backups as operational truth, or treat convenience automation as an acceptable excuse for broad destructive access.

This shared rule sits beneath domain-local operating logic and beside the shared boundary model. The boundary model continues to govern tenant, learning, reporting, decision, and role-sensitive access scope. This standard governs how security and data-protection discipline must preserve those inherited boundaries in storage and operational practice.

## Domain Extension Rules

Valid domain extension may include richer sensitivity taxonomies, narrower storage-surface classes, stricter retention windows, narrower destructive authority, stricter secret-rotation discipline, stronger suspicious-state escalation rules, or more restrictive automation controls where local operating reality requires them.

Invalid domain extension occurs when a domain introduces local-only meanings for source-of-truth storage, derived storage, temporary artifacts, backup copy, recovery copy, least-privilege access, privileged write path, suspicious access state, unsafe write state, or unauthorized modification state that are incompatible with this shared grammar. Invalid extension also occurs when local storage habits, convenience scripts, notebook practice, shared NAS usage, or ad hoc SQL behavior are allowed to override shared control posture in practice.

future security extensions must be placed according to control role, not convenience.

If a change defines shared object meaning for evidence, state, failure, chronology, or authority, it belongs in the relevant objects canon, not here. If a change defines tenant or reporting entitlement, learning scope, or role-sensitive visibility semantics, it belongs in the boundary canon, not here. If a change defines cross-domain interface semantics or dependency versioning, it belongs in the interfaces canon, not here. If a change defines code modularity, it belongs in the code-architecture standard, not here. If a change defines one domain's local operational ritual beneath this shared security rule, it belongs in that domain's contract or operational guidance, not here.

## Governance Linkage

This standard is directly governance-linked because it affects what the platform may expose, modify, restore, delete, retain, destroy, or automate across shared storage and shared operational surfaces.

Changes to shared security control posture, shared data protection posture, source-of-truth ownership rules, privileged write-path rules, least-privilege rules, backup and recovery boundaries, retention and destruction rules, broad observability restrictions, or automation access discipline are consequential shared-platform changes. Where those changes materially affect tenant boundaries, learning scope, reporting scope, role-sensitive access, or destructive operational posture, the stricter approval path in the governance authority matrix controls. In practice this means Governance and Boundary Authority review is materially relevant, Architecture Authority review is materially relevant, Implementation Authority review is materially relevant, affected Domain Authority review is materially relevant, and Platform Owner approval remains necessary wherever the change alters shared platform behavior or high-sensitivity boundary posture. Commercial Authority review is also materially relevant where the change alters operating feasibility, customer-visible handling, or the commercial cost of retention, recovery, or access discipline.

The platform entitlement and scope boundary model should treat this file as the controlling reference for how boundary-sensitive access and storage behavior remain safe in operational practice without redefining entitlement objects themselves. The code architecture and modularity standard should treat it as the controlling reference whenever security, storage, backup, or secret handling must remain outside structural code-modularity rules. The cross-domain coordination and governed dependency standards should treat it as the controlling reference whenever operational interfaces, exports, or automation paths touch storage, secrets, or destructive behavior. The shared evidence, state, chronology, failure-state, and capability-boundary standards should treat it as the controlling reference whenever their governed objects depend on secure storage, auditable modification, safe restore, or secure disclosure posture without redefining those control semantics themselves.

## Failure Modes in Security and Data Protection Design

Weak security and data-protection design creates direct platform risk.

### Buried credentials and secrets

Credentials, tokens, passwords, keys, or connection secrets are embedded in code, notebooks, scripts, SQL files, NAS folders, local files, or temporary artifacts, making access posture unreviewable and rotation fragile.

### Ambiguous source-of-truth storage

Multiple tables, files, folders, marts, or copied extracts appear to hold operational truth, and the platform can no longer say which surface actually governs current state.

### Backup mistaken for operational truth

A backup copy, restored copy, archive, or copied recovery surface begins to function as current truth because it is convenient, fast, or already available.

### Hidden write destinations

Pipelines, scripts, restores, or SQL routines write to storage surfaces that are not clearly declared, making modification scope and incident review unreliable.

### Uncontrolled data copying

Governed data is duplicated across NAS shares, local files, notebooks, scratch tables, exports, or derived stores without clear ownership, expiry, or access narrowing.

### Insecure temporary artifacts

Short-lived files, caches, staging tables, and exported working sets survive too long, retain secrets or sensitive data, and become shadow stores with no explicit retention or destruction posture.

### Over-broad access and broad observability leakage

Roles, services, logs, traces, dashboards, or exports expose materially more data than the legitimate task requires, and sensitive surfaces become widely visible under the banner of convenience or troubleshooting.

### Silent overwrite or destructive restore

Operational truth is overwritten, replaced, or restored without preserved lineage, preserved audit trace, or explicit awareness of backup and recovery consequences.

### Casual deletion of governed data

Source-of-truth or high-consequence derived data is deleted because cleanup felt harmless, storage felt crowded, or a local operator assumed recovery would be easy later.

### Convenience automation with destructive access

One-off scripts, notebooks, ad hoc SQL, local tools, or agent-generated helpers receive production-like write or delete capability and begin acting on live operational surfaces without serious path control.

### Recovery without explicit boundary discipline

Recovery actions occur with weak lineage, weak authority, or weak environment separation, creating fresh ambiguity about what is current truth and what still exists only for recovery.

### Suspicious access normalized as ordinary operations

Irregular access, broad exports, odd timing, mismatched identity use, or unusual write posture is treated as routine noise rather than as suspicious access state requiring explicit review.

These failure modes are not minor operational untidiness. They are ways the platform can keep moving while losing the ability to trust its data, its storage posture, its secrets, and its own operational history.

## Non-Negotiables

1. security is not the same thing as performance.
2. data protection is not the same thing as backup by itself.
3. backup is not the same thing as source-of-truth storage, and no backup strategy may blur operational truth and archival recovery.
4. access capability is not the same thing as authority to modify.
5. automation permission is not the same thing as unrestricted data access.
6. observability is not the same thing as broad data exposure.
7. development convenience is not the same thing as acceptable security posture.
8. no buried secrets in code, no hidden write destinations, and no ambiguous storage ownership are permitted for governed platform surfaces.
9. no uncontrolled data copying, no silent overwrite of governed data, no casual deletion of source-of-truth data, and no convenience scripts with production-like destructive access are permitted.
10. future security extensions must be placed according to control role, not convenience.

## Closing Statement

The Fourth Form platform cannot remain a serious decision system if its data, secrets, storage surfaces, backups, and destructive paths are governed by convenience rather than by explicit control posture.

This standard therefore fixes the shared platform rule for how security and data protection must remain explicit, narrow, reconstructible, and durable across code, storage, pipelines, automation, backups, recovery, retention, and destruction. It protects the platform from buried secrets, shadow truth, uncontrolled writes, unsafe automation, ambiguous recovery, and convenience-led erosion of operational integrity. And it keeps future scale possible by ensuring that trust in platform data and platform operations is preserved as a governed asset rather than treated as a side effect of good intentions.