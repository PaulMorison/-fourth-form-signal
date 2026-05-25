# Decision Surface and Dashboard Governance Standard for the Fourth Form Retail Decision Intelligence Platform

## Purpose

This document defines the shared platform standard for decision surfaces, dashboards, score views, operational views, and executive views across all current and future domains.

It exists because the platform now has governed standards for canon navigation, canon change control, lifecycle composition, commercial value creation and realisation, glossary discipline, canonical metric and KPI governance, observability, release readiness, decision mode, shared briefing and summary surfaces, shared human-review packets, shared rationale trace, shared comparison sets, shared observation windows, shared post-mortem judgment, benchmark-safe comparison boundaries, cross-domain coordination, and governance authority, but it still lacks one shared rule for how a surfaced decision view becomes canonical, how view scope and audience remain explicit, how view-to-metric lineage remains reconstructible, how score and status views remain trustworthy, how aggregation and drill-down stay legitimate, how cross-surface consistency is preserved, and how the platform prevents persuasive presentation from quietly redefining underlying metric or decision meaning.

Without such a rule, the platform will drift into dashboards being mistaken for governing truth, executive views stripping qualifiers that still matter, operational views mixing metrics with different aggregation bases, drill-down paths broadening visibility beyond audience legitimacy, benchmark visibility being mistaken for benchmark-safe exposure, summary views becoming the de facto source of metric meaning, local product views being promoted into canon because they look useful, and cosmetic polish being mistaken for semantic trustworthiness.

This document is therefore a control document for decision surface and dashboard governance.

It defines the control role, scope, governed decision surface classes, surface admission discipline, audience and exposure legitimacy, metric-to-surface lineage, aggregation and drill-down discipline, cross-surface consistency rules, inheritance and domain extension rules, revision and retirement handling, minimum metadata requirements, governance linkage, failure modes, non-negotiables, implementation notes, and adjacent-standard boundaries that all current and future domains must follow when creating, changing, inheriting, extending, exposing, comparing, superseding, deprecating, retiring, or trusting governed decision surfaces.

It is the canonical decision surface and dashboard governance standard for the platform. Future domains, workflow contracts, dashboards, score views, executive views, operational views, briefing surfaces, benchmark-safe comparative outputs, review-facing surfaces, post-mortem communications, and domain-local reporting logic must align with it when preserving governed decision surface, governed dashboard, governed score surface, governed executive view, governed operational view, surface scope declaration, audience legitimacy, view lineage, surface comparability, aggregation legitimacy, drill-down legitimacy, inherited surface, domain-extended surface, superseded surface, retired surface, deprecated surface, surface drift detection, cosmetic trust risk, human review trigger where relevant, no silent surface mutation, no silent aggregation drift, no silent label redefinition, surface audit trace, and surface admission threshold unless a formal decision record explicitly revises it.

## Control Role

This document governs the shared control layer that sits between canonical metrics, controlled decision objects, and role-specific surface consumption on the other side.

The canonical metric and KPI governance standard governs formula legitimacy, KPI admission, denominator legitimacy, and metric meaning, but it does not govern how surfaced views present those metrics or how surface lineage remains explicit. The shared briefing, digest, and summary surface standard governs the shared summarization layer, but it does not define one platform-wide rule for when a dashboard or score view becomes a governed decision surface. The shared human-review-packet and intervention-handoff standard governs review-packet sufficiency, but it does not govern recurring operational or executive views. The shared decision rationale and explanation trace standard governs rationale meaning and explanation derivation, but it does not govern how a dashboard or status surface packages those artifacts. The shared comparison-set and analog-reference standard and the benchmark-safe comparison standard govern comparative object meaning and exposure safety, but they do not define one shared rule for dashboard scope, cross-surface consistency, or drill-down legitimacy. The shared observation-horizon and measurement-window standard governs timing maturity, but it does not govern what a surface may imply about maturity. The shared post-mortem and attribution judgment standard governs attribution quality, but it does not govern how post-mortem views remain surface-faithful. The observability standard governs operational telemetry and signals, but it does not define business decision surfaces or executive views. The glossary standard governs vocabulary ownership, but it does not govern surface lineage. The decision-mode and intervention-policy standard governs what intervention posture is legitimate, but it does not govern how a view must preserve that posture honestly.

This document therefore governs what counts as a governed decision surface, when a dashboard or score view may claim shared authority, what audience and exposure posture a surface may carry, what must remain visible when aggregation or labels change, how drill-down remains legitimate, and how the platform prevents dashboard theater, surface drift, and cosmetic trust from outrunning underlying governance.

## Scope

This standard governs decision surface classes, dashboard scope discipline, view-to-metric lineage, view audience legitimacy, role-appropriate information exposure, score and status surface legitimacy, cross-surface consistency, comparability discipline across surfaces, drill-down legitimacy, aggregation legitimacy, anti-surface-drift controls, anti-cosmetic-trust controls, promotion of a surface into governed canonical use, and the separation between useful local views and governed shared decision surfaces.

not every useful dashboard belongs in governed canonical decision surfaces.

decision surfaces must have named scope, audience, and metric lineage.

aggregation changes must remain explicit and lineage-safe.

score surfaces must not silently redefine underlying metrics.

canonical surface admission must be stricter than local presentation usefulness.

This standard applies whenever a surfaced view claims shared authority across domains, shared outputs, governance reviews, benchmark-safe comparative surfaces, executive reporting, operational decision handling, review support, post-mortem communication, or other recurring decision-support contexts where readers are expected to trust the surface repeatedly rather than treat it as a disposable local convenience.

## Out of Scope

this standard is not a dashboard design guide.

this standard is not a BI tooling note.

this standard is not a local reporting template.

this standard is not permission for uncontrolled dashboard sprawl.

this standard is not permission to promote persuasive views into canon without governed lineage.

This standard is not metric formula ownership. This standard is not KPI admission ownership. This standard is not dashboard visual design aesthetics. This standard is not BI vendor or tooling choice. This standard is not observability telemetry design. This standard is not prompt-asset governance. This standard is not glossary ownership. This standard is not benchmark-safe exposure boundary ownership. This standard is not post-mortem judgment ownership. This standard is not a local product UI note. This standard does not give a surface permission to rename, recolor, reorder, compress, or package information in ways that mutate the underlying metric, rationale, or decision posture while still claiming canonical authority.

Metric ownership remains with the canonical metric and KPI governance standard. Benchmark-safe exposure ownership remains with the comparison boundary standards. Summarization object meaning remains with the shared briefing and review-packet object standards. Glossary ownership remains with the glossary standard. Decision mode meaning remains with the decision-mode standard. This document governs the surfaced decision layer that sits above those authorities without replacing them.

## Why This Standard Exists

The platform needs one shared decision-surface and dashboard-governance standard because surfaced information strongly influences what humans trust, compare, escalate, and act on, but trust collapses quickly when the platform cannot tell which surfaces are local, which are canonical, which audiences they serve, which metrics they derive from, what aggregation posture they use, what drill-down rights they imply, and whether one surface still means the same thing as another.

If surface governance is left local, several failures follow. One team promotes a score view into shared use because executives like it even though its metric lineage is unclear. Another relabels a stable metric in a dashboard and later readers assume the renamed label is a new indicator. Another changes an aggregation layer and calls it a design refinement even though the meaning changed materially. Another exposes a drill-down path that quietly broadens audience scope. Another shows benchmark-safe comparative output and treats visibility as if it proved exposure legitimacy. Another makes one operational surface look consistent with another by copying colors and layout while underlying definitions diverge. Another shows early observation as if it were mature status because the surface is visually clean. Another lets local useful views multiply until the platform can no longer say which surfaces deserve governed trust.

The platform therefore needs one shared standard so that every current and future domain inherits one coherent rule for governed decision surface, governed dashboard, governed score surface, governed executive view, governed operational view, surface scope declaration, audience legitimacy, view lineage, surface comparability, aggregation legitimacy, drill-down legitimacy, inherited surface, domain-extended surface, superseded surface, deprecated surface, retired surface, surface drift detection, cosmetic trust risk, human review trigger where relevant, no silent surface mutation, no silent aggregation drift, no silent label redefinition, surface audit trace, and surface admission threshold rather than improvising local dashboard habits.

## Core Distinctions

a decision surface is not the same thing as a metric by itself.

a dashboard is not the same thing as a KPI definition.

visual clarity is not the same thing as semantic legitimacy.

a score surface is not the same thing as durable value by itself.

local usefulness is not the same thing as canonical surface admission.

cross-surface similarity is not the same thing as cross-surface consistency.

benchmark visibility is not the same thing as benchmark-safe exposure.

future surface-governance extensions must be placed according to control role, not convenience.

These distinctions exist because the platform must preserve one shared discipline for what a surfaced view is allowed to claim, what it is merely allowed to display, what it may compress, what it must keep lineaged, and what kinds of surface change are serious enough to require review, supersession, or retirement rather than casual redesign.

## Governed Decision Surface Classes

### Local useful view

Local useful view is a dashboard, status view, notebook output, spreadsheet surface, or product-facing panel that may be operationally useful inside one narrow setting without thereby qualifying for governed canonical status. local usefulness is not the same thing as canonical surface admission.

### Governed decision surface

governed decision surface is the shared platform condition in which a surfaced view has named purpose, named scope, named audience, explicit view lineage, explicit aggregation posture where relevant, explicit drill-down posture where relevant, explicit consistency expectations, and preserved revision posture strong enough for repeated shared trust.

### Governed dashboard

governed dashboard is a governed decision surface that organizes multiple governed indicators, statuses, references, or linked objects into one recurring surface whose authority depends on explicit scope, audience legitimacy, lineage, and controlled cross-surface consistency rather than on presentation polish by itself.

### Governed score surface

governed score surface is a governed decision surface centered on one or more governed metrics, statuses, bands, or score-like indicators whose displayed summary remains explicitly subordinate to underlying metric lineage and may not claim meaning beyond that lineage.

### Governed executive view

governed executive view is a governed decision surface whose audience legitimacy and compression posture are tailored to executive interpretation while preserving material qualifiers, audience-safe exposure discipline, and traceable linkage back to the underlying governed artifacts.

### Governed operational view

governed operational view is a governed decision surface whose audience legitimacy and surface scope declaration are tailored to active operators, reviewers, or handlers who need decision-relevant clarity without having the view silently rewrite metric meaning, urgency posture, or intervention posture.

## Surface Admission Discipline

Canonical surface admission is a governance question before it becomes a presentation question. A surface enters governed canonical use only when it satisfies a surface admission threshold strong enough to justify cross-domain reuse, recurring executive or operational trust, benchmark-safe comparative use where relevant, governance review use, release or validation reliance where relevant, or durable decision-support use.

not every useful dashboard belongs in governed canonical decision surfaces. A locally helpful view may still remain local when its scope is narrow, its audience is unstable, its aggregation basis is provisional, its labels are transient, or its lineage is too weak for repeated shared trust.

canonical surface admission must be stricter than local presentation usefulness. A governed decision surface must show stronger scope discipline, stronger audience legitimacy, stronger lineage, stronger anti-drift controls, and stronger anti-cosmetic-trust posture than a merely useful local view requires.

cosmetic trust risk is the governance risk that a surface is trusted because it looks polished, coherent, or executive-ready rather than because it preserves stable lineage, stable scope, honest qualifiers, and explicit aggregation posture. cosmetic trust must be treated as a governance risk.

Where a proposed surface materially affects executive interpretation, operational action, release or validation gates, benchmark-safe comparison exposure, post-mortem communication, or cross-domain trust, a human review trigger where relevant must remain available rather than assuming automated promotion into canonical use is enough.

## Audience and Exposure Legitimacy

surface scope declaration is the explicit statement of what a surface covers, what it does not cover, which decisions or statuses it is allowed to inform, and which adjacent meanings it must not silently absorb. audience legitimacy is the governed condition in which a surface's intended readers, role-appropriate exposure, and authority posture are explicit enough that later readers can tell why this audience is allowed to see this surface and what that audience is supposed to do with it.

Decision surfaces must not assume that one clean surface is valid for every audience. A governed executive view may compress operator detail without erasing material uncertainty, material status qualification, or material scope limitation. A governed operational view may show richer path detail, but it must not silently broaden exposure beyond its declared audience legitimacy.

benchmark visibility is not the same thing as benchmark-safe exposure. A surface may show a benchmark-safe comparison only when the governing boundary standards already entitle that exposure. This surface-governance standard does not create that entitlement. It governs how the surface preserves it honestly.

Role-appropriate information exposure must remain explicit wherever a surface touches benchmark-safe comparative context, review-sensitive material, post-mortem communication, or operationally sensitive qualifiers. If a surface cannot state its intended audience and exposure posture clearly, it is not ready for governed canonical admission.

## Metric-to-Surface Lineage

decision surfaces must have named scope, audience, and metric lineage. A surface that cannot name what metrics, statuses, objects, or decision artifacts it derives from is not mature enough for shared governed use.

view lineage is the reconstructible chain linking a surface to the governed metrics, governed KPIs, controlled objects, comparison sets, observation windows, or post-mortem artifacts it displays. A decision surface is not the same thing as a metric by itself. A dashboard is not the same thing as a KPI definition.

score surfaces must not silently redefine underlying metrics. A governed score surface may summarize, rank, color, compress, or package metrics, but it may not change the displayed metric meaning through relabeling, hidden transformations, silent scope change, or aggregation change while keeping the same trust posture.

no silent label redefinition is acceptable. no silent surface mutation is acceptable. If a surface changes the wording, grouping, emphasis, or interpretation of an underlying metric, status, or decision state materially enough that readers would understand the displayed information differently, that is a governance-relevant surface change rather than a cosmetic edit.

## Aggregation and Drill-Down Discipline

aggregation legitimacy is the governed condition in which a surface's grouping, roll-up, summarization, status collapse, or score compression remains explicit enough that later readers can tell what population, window, scope, and logic produced the displayed result. drill-down legitimacy is the governed condition in which a surface may move from a broader view into narrower supporting detail without silently broadening scope, audience rights, or semantic meaning.

aggregation changes must remain explicit and lineage-safe. no silent aggregation drift is acceptable. A governed surface may change aggregation posture only when the change is visible enough that readers can tell what moved from one aggregation basis to another and why the old interpretation no longer applies unchanged.

Drill-down paths must remain subordinate to surface scope declaration, audience legitimacy, benchmark-safe exposure boundaries, and underlying object authority. A drill-down path that reveals unauthorized detail, changes metric meaning mid-path, or silently swaps one decision posture for another is illegitimate even if the underlying data technically exists.

Operational roll-ups, executive compressions, and status-band surfaces may be useful, but visual clarity is not the same thing as semantic legitimacy. Aggregation and drill-down must remain honest enough that a reader can tell what the surface is showing, what it is collapsing, and what narrower context still governs interpretation.

## Cross-Surface Consistency

cross-surface similarity is not the same thing as cross-surface consistency. Two surfaces can look similar while carrying different labels, different aggregation bases, different time windows, or different audience qualifiers. Conversely, two surfaces can look different while still being consistent if they preserve shared lineage and explicit declared differences.

surface comparability is the governed condition in which two or more governed decision surfaces can be interpreted together without silently changing metric lineage, status meaning, aggregation basis, audience posture, or decision significance. Cross-surface consistency exists when surfaces preserve shared terms, shared lineage, shared declared qualifiers, and explicit declared differences strongly enough that one surface does not undermine another.

Governed executive views, governed operational views, governed dashboards, and governed score surfaces may compress or arrange information differently for audience fit, but they must remain consistent about what the underlying metric or status means, what window it refers to, what aggregation posture it uses, and what qualifiers remain material.

## Surface Inheritance and Domain Extension

Domains may inherit governed surfaces, but they may not absorb them so fully that shared surface meaning disappears. inherited surface is a governed decision surface reused by a domain without changing its shared meaning, declared audience posture, aggregation identity, or lineage obligations beyond explicitly governed local scope binding.

domain-extended surface is a surface created beneath a shared parent surface for a narrower domain context while preserving explicit subordinate lineage, subordinate scope, and explicit difference from the inherited parent. inherited surfaces must remain distinguishable from domain-extended surfaces.

One domain may need narrower operational detail, narrower score decomposition, or narrower role-specific packaging than another. That narrower view may become a domain-extended surface when it remains explicitly subordinate to the parent surface. It must not quietly mutate the inherited parent and still call itself inherited.

Local useful views may exist beside inherited surfaces and domain-extended surfaces, but they do not gain canonical authority merely because they sit near governed views or reuse some of the same metrics.

## Revision, Supersession, and Retirement

Canonical decision surfaces must remain historically reconstructible across change. Any material change to surface scope declaration, audience posture, metric lineage, aggregation posture, drill-down rights, cross-surface consistency rules, labels, or surface class is a surface-governance event rather than a casual presentation edit.

surface drift detection is the requirement that materially changed surface meaning, audience posture, aggregation posture, label behavior, or lineage becomes visible before trust is weakened. surface drift must remain explicit and reviewable.

superseded surface is a surface whose canonical use has been replaced by another surface or another definition while its prior identity remains historically visible. superseded surfaces must remain historically identifiable.

deprecated surface is a surface whose new use is discouraged or bounded while its historical meaning and transitional visibility remain active. retired surface is a surface whose active canonical use has ended while its lineage remains reconstructible for historical interpretation. retired surfaces must remain distinguishable from deprecated surfaces.

no silent surface mutation, no silent aggregation drift, and no silent label redefinition remain binding across revision, supersession, deprecation, and retirement.

## Minimum Metadata Requirements

Every governed decision surface must preserve enough metadata to keep surface meaning reconstructible and surface audit trace intact.

### Identity and status

Each governed surface must preserve stable identity, current status, current class, current owner, and whether it is a governed decision surface, governed dashboard, governed score surface, governed executive view, governed operational view, inherited surface, domain-extended surface, superseded surface, deprecated surface, or retired surface.

### Scope and audience posture

Each governed surface must preserve surface scope declaration, intended audience, audience legitimacy, intended use, role-appropriate exposure posture, and explicit statement of what the surface does not prove or authorize by itself.

### Lineage and metric posture

Each governed surface must preserve view lineage, underlying metric and object references where relevant, cross-surface consistency references where relevant, no silent label redefinition controls, and explicit statement of what underlying authorities still govern the displayed content.

### Aggregation and drill-down posture

Each governed surface must preserve aggregation legitimacy, drill-down legitimacy, surface comparability conditions where relevant, window and refresh posture where relevant, and links to benchmark-safe exposure dependencies where comparative content is involved.

### Lifecycle and audit posture

Each governed surface must preserve surface audit trace, surface admission threshold reference, surface drift detection posture, and links to supersession, deprecation, retirement, or restriction decisions where relevant.

## Governance Linkage

This standard is directly governance-linked because it affects what surfaced information the platform is allowed to treat as trustworthy, what executive and operational views readers are entitled to rely on, what comparative or review-facing views remain semantically honest, and what recurring dashboards deserve continued canonical life.

Changes to governed decision surfaces, surface admission thresholds, surface scope declaration, audience legitimacy, aggregation posture, drill-down rights, cross-surface consistency rules, inherited versus domain-extended status, score-surface meaning, supersession posture, deprecation posture, retirement posture, or label behavior are consequential platform changes. Review and approval must therefore align with the governance authority matrix at the stricter applicable path, with Architecture Authority, Commercial Authority, Platform Owner, affected Domain Authority, Governance and Boundary Authority, and Implementation Authority involved where the change materially touches their control surface.

Cross-domain coordination must treat canonical decision surfaces as governed dependencies when one domain consumes another domain's surfaced view. Release, validation, benchmark-safe exposure, post-mortem communication, and executive operational reporting must treat this document as the controlling reference for whether a surface is trustworthy enough to be reused without redefining surface legitimacy locally.

## Failure Modes

### Dashboard theater

The platform treats a polished dashboard as if it proved that underlying metrics, statuses, and decision qualifiers were governance-sufficient even though surface lineage or qualifier discipline is weak.

### Cosmetic trust capture

Readers trust a surface because it looks coherent, executive-ready, or operationally clean even though cosmetic trust risk has outrun actual semantic legitimacy.

### Silent label rewrite

The label or status name on a recurring surface changes materially while the trust posture stays the same and later readers assume nothing important changed.

### Silent aggregation drift

The roll-up, grouping, or status-collapse basis changes quietly and historical comparison weakens without explicit notice.

### Drill-down overreach

The surface allows narrower inspection that silently broadens scope, exposure, or decision meaning beyond what the audience was entitled to see.

### Cross-surface conflict masked by visual similarity

Two surfaces look aligned because they share layout or labels even though underlying lineage, windows, or aggregation bases diverged materially.

### Benchmark halo

The surface treats visible benchmark comparison as if that alone proved benchmark-safe exposure and semantic legitimacy.

### Executive compression without qualifiers

An executive view strips uncertainty, scope limitation, or maturity qualification strongly enough that the compressed surface misrepresents the underlying situation.

### Inheritance blur

One domain mutates an inherited surface locally and continues to present it as if it were the shared parent surface.

### Lifecycle amnesia

Superseded, deprecated, and retired surfaces lose their historical identifiability and later readers can no longer tell which surface used to mean what.

## Non-Negotiables

1. Not every useful dashboard belongs in governed canonical decision surfaces, and anything that cannot justify repeated shared trust, stable audience legitimacy, and stable lineage must remain local rather than being promoted into canon by convenience.

2. Decision surfaces must have named scope, audience, and metric lineage, because a surface that cannot state what it covers, who it is for, and what governed artifacts it derives from is not ready for canonical use.

3. Aggregation changes must remain explicit and lineage-safe, because no silent aggregation drift is acceptable where a surface claims recurring cross-surface trust.

4. Score surfaces must not silently redefine underlying metrics, because a governed score view may summarize metrics but may not rewrite what those metrics mean.

5. Inherited surfaces must remain distinguishable from domain-extended surfaces, because downstream reuse cannot stay coherent if one domain mutates a shared surface and still calls it inherited.

6. Canonical surface admission must be stricter than local presentation usefulness, because a governed surface carries stronger trust, stronger exposure consequence, and stronger anti-drift obligations than an ordinary local view.

7. Cosmetic trust must be treated as a governance risk, because polished presentation can weaken judgment faster than it creates clarity when lineage and qualifiers are weak.

8. Surface drift must remain explicit and reviewable, because no silent surface mutation is acceptable once a surface claims canonical authority across domains, outputs, or governance surfaces.

9. Superseded surfaces must remain historically identifiable, because later interpretation, review, and comparison depend on reconstructible surface lineage rather than erased prior views.

10. Retired surfaces must remain distinguishable from deprecated surfaces, because bounded transition, historical visibility, and ended canonical use are not the same lifecycle state.

## Implementation Notes

Canonical decision surfaces should be implemented as first-class governed surface definitions consumed by dashboards, operational views, executive views, score views, benchmark-safe packets, review-facing surfaces, and post-mortem communication layers rather than as scattered local screens whose semantic rules live only in presentation code, spreadsheet logic, or tool-specific configuration.

Visual design, layout polish, tool selection, and UI composition may change without becoming this standard's concern when those changes remain genuinely cosmetic. But once a change affects audience legitimacy, labels, aggregation posture, drill-down behavior, lineage visibility, or how a reader interprets the displayed status or metric, the change has crossed into governed surface territory and must be treated accordingly. Local product views may still exist, but they must not claim canonical authority merely because they are useful or persuasive.

## Relationship to Adjacent Standards

This standard works with adjacent standards without replacing them. The canonical metric and KPI governance standard governs metric meaning, formula legitimacy, KPI admission, and denominator legitimacy, while this file governs whether a surfaced view remains faithful to that meaning. The shared briefing, digest, and summary surface standard governs shared summarization objects, while this file governs recurring decision surfaces and dashboards that consume those objects. The shared human-review-packet and intervention-handoff standard governs packet sufficiency and intervention handoff, while this file governs surfaced views that may orient readers to those packets without replacing them. The shared decision rationale and explanation trace standard governs rationale meaning, while this file governs how a surface packages that rationale honestly. The benchmark-safe comparison and comparison-set standards govern safe comparative meaning and exposure, while this file governs whether a surface preserves those rules honestly. The decision-mode and intervention-policy standard governs permitted intervention posture, while this file governs whether a surface represents that posture faithfully. The observability standard governs telemetry and signal design, while this file governs decision-facing surface use rather than operational signal admission. The glossary standard governs controlled vocabulary, while this file governs surface legitimacy rather than vocabulary ownership.

Future surface-related extensions must respect control role. Shared dashboard and decision-surface governance belongs here. Reusable shared surface objects belong in the shared objects canon. Exposure-boundary rules belong in boundary standards. Cross-domain dependency rules belong in interface standards. Domain-specific product UI notes, local scorecards, and one-off reporting conventions belong in domain documents rather than in this core control file.

## Closing Position

The platform does not remain trustworthy because it can display many numbers and statuses. It remains trustworthy because it can say which surfaces deserve shared authority, which audiences may rely on them, what metrics and objects they derive from, what they aggregate, what they hide, what they allow readers to drill into, what changed over time, what remains merely local, and when a surface should be superseded, deprecated, or retired rather than defended by visual polish.

That is the governing position of this standard.