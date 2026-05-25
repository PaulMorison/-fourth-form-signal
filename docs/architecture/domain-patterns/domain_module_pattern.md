# Domain Module Pattern for the Fourth Form Retail Decision Intelligence Platform

## Purpose of This Document

This document defines how the Fourth Form platform should support many business functions using one shared core system architecture.

It exists to prevent two equally damaging forms of drift.

The first is the giant mixed-domain platform in which promotions, markdowns, assortment, replenishment, pricing, local intervention, and every later business function are blended into one unstable domain mass. That produces conceptual confusion, weak boundaries, brittle implementation, and poor learning discipline.

The second is the fragmented platform in which every business function becomes a separate one-off solution with its own logic, vocabulary, workflows, and governance exceptions. That destroys architectural coherence, duplicates effort, and weakens institutional learning.

This document establishes the pattern that avoids both failures: one shared core platform architecture, many structurally separate domain modules, one common decision grammar, one constitution, one learning discipline.

## Why This Pattern Is Necessary

The platform is being built to support more than one business function.

Promotions are the first wedge because they are repeated, measurable, high-stakes, and rich in commercial learning. They are not the terminal scope of the platform. If the platform succeeds, it may eventually support 20 or more retail business functions across decisions such as markdowns, pricing, assortment and ranging, inventory deployment, replenishment policy, local commercial intervention, and scenario-based planning.

That scale cannot be supported safely by improvisation.

If every new function is added as an ad hoc extension of the promotions domain, the system becomes a distorted promotion-centric architecture pretending to be a general platform.

If every new function is added as a standalone application, the system becomes a loose federation of tools rather than a decision intelligence platform.

The pattern defined here is necessary because the platform must scale in breadth without losing structural coherence.

## Core Platform vs Domain Module Distinction

The Fourth Form platform has two structural levels.

The first level is the core platform.

The core platform contains the shared decision architecture: reality ingestion, canonical entity structure, knowledge-quality handling, graph-backed memory, state interpretation, failure-state logic, causal reasoning, simulation, policy learning, decision-focused optimization, constitutional control, explanation, execution feedback, and post-decision learning.

The second level is the domain module.

A domain module is a business-function-specific application of the shared platform. It defines the domain thesis, domain entities, domain boundaries, local state objects, decision objects, constraint objects, outcome objects, reporting rules, and post-mortem logic required for one decision area.

The distinction is simple but critical.

The core platform defines how the system thinks.

The domain module defines what the system is thinking about in one business function.

The core platform should not be rewritten per domain. The domain module should not attempt to re-specify the shared platform.

## Shared Decision Grammar Across All Domains

All domain modules must use the same decision grammar.

That does not mean every domain uses the same business objects. It means every domain expresses its business objects in the same architectural language so that governance, explanation, learning, and cross-domain comparison remain possible.

At minimum, every domain module must support the following shared decision grammar.

- A defined decision context.
- A defined decision scope.
- Explicit local state and broader context.
- A feasible action set.
- A structured constraint profile.
- A recommendation object.
- A confidence position shaped by uncertainty and causal coverage.
- An explanation package.
- An execution record.
- An outcome object.
- A post-mortem learning artifact.
- A governed override pathway.

This grammar is what allows multiple domains to remain separate while still behaving as one system.

## What Must Be Shared Across All Domains

The following must be shared across all domain modules.

### Shared architecture stack

Every domain must use the same core system stack defined in the platform architecture. No domain may bypass the layered decision flow and still claim to be part of the platform.

### Shared decision constitution

Every domain must obey the same retail decision constitution. No business function is exempt from uncertainty discipline, constraint discipline, explanation discipline, failure-state discipline, override governance, or post-decision learning.

### Shared controlled vocabulary

Every domain must use the controlled vocabulary defined by the core glossary unless a narrower domain term is explicitly added and governed.

### Shared governance model

Every domain must operate under the same governance expectations for access rights, reporting scope, learning permissions, auditability, and tenant-safe behavior.

### Shared learning loop

Every domain must close the decision loop from recommendation to action to outcome to post-mortem learning. No domain may behave as though decision output alone is enough.

### Shared output discipline

Every domain must produce decision objects, constraint objects, outcome objects, and post-mortem learning artifacts in a form that is reconstructible after the fact.

### Shared explanation standard

Every domain must support explanations strong enough for serious operating use. Black-box behavior is not allowed simply because the business function is new or technically difficult.

## What Must Be Domain-Specific

The following must be defined separately inside each domain module.

### Domain thesis

What commercial problem this domain exists to solve and what hidden failure patterns matter most inside it.

### Domain boundaries

What is and is not part of the business function.

### Domain entities and relationships

The specific business objects, their identities, and how they relate to each other.

### Domain state signals

The local state, operating conditions, and interpretive signals required for serious decision support in that function.

### Domain constraints

The commercial, operational, financial, execution, and governance limits that matter specifically in that decision area.

### Domain simulation needs

What the digital twin must represent in order to compare actions responsibly in that function.

### Domain outcome logic

What counts as success, failure, distortion, local optimization failure, and useful learning in that business function.

### Domain reporting logic

What explanations, packages, reporting views, and tenant-safe outputs are needed for that function.

The domain module should be specific where the core platform is general.

## Standard Structure of a Business-Function Domain Module

Every new business-function domain module should follow a standard internal structure.

At minimum, a serious domain module should define the following.

1. Domain purpose and role in the platform.
2. Domain boundaries.
3. Domain thesis.
4. Domain entities.
5. Domain relationships.
6. Domain local-state objects.
7. Domain decision objects.
8. Domain constraint objects.
9. Domain outcome objects.
10. Domain failure modes.
11. Required state signals.
12. Simulation requirements.
13. Policy-learning requirements.
14. Reporting and explanation requirements.
15. Governance and access-control requirements.
16. Domain invariants.

This pattern should be treated as structural discipline, not template bureaucracy. It ensures that each domain is complete enough to support architecture, data design, implementation, simulation, recommendation behavior, and post-decision learning without ambiguity.

## How Promotions Fits as Domain 01

Promotions is Domain 01.

That means promotional allocation is the first domain-specific population of the shared platform, not a special exception to it.

Promotions already demonstrates the required pattern.

- It uses the shared system architecture rather than defining its own stack.
- It obeys the shared constitution.
- It uses the controlled platform vocabulary.
- It defines domain-specific entities such as network promotion, promotion instance, store promotion instance, recommendation object, and promotion post-mortem object.
- It preserves a full decision loop with constraints, explanation, execution, and learning.
- It supports multi-store, multi-brand, and tenant-aware operation as part of the domain model rather than as an afterthought.

Promotions is therefore the first proof of the domain module pattern. It should become the reference for how later domains are added, not the container into which later domains are squeezed.

## How Future Domains Should Be Added

Future business functions should be added as new domain modules, not as ad hoc features embedded inside existing domains.

The correct expansion pattern is deliberate.

First, define the business function as a decision domain rather than as a feature request.

Second, write the domain module document using the shared domain structure.

Third, map the domain objects into the shared architecture layers.

Fourth, define domain-specific state signals, constraints, decision objects, outcome objects, and post-mortem logic.

Fifth, validate that the new domain obeys the constitution and uses the controlled vocabulary.

Sixth, only then begin implementation.

This is how the platform can grow to 20 or more business functions without becoming structurally confused.

## Rules for Preventing Cross-Domain Drift

Cross-domain drift occurs when domain boundaries weaken and business logic begins leaking from one function into another without clear governance.

The platform must prevent this through explicit rules.

### No hidden domain borrowing

One domain may not quietly reuse another domain's assumptions, constraints, or explanations without making that reuse explicit and governed.

### No ad hoc feature insertion

New business functions must not be inserted as miscellaneous features inside an existing domain merely because some data or workflow appears similar.

### No vocabulary slippage

Shared terms must retain their glossary meaning across domains. Domain-specific extensions should be added deliberately, not casually improvised.

### No governance bypass

No domain may bypass the core governance model, even if its workflows appear lower risk or more operationally urgent.

### No special-case learning loop

Every domain must support recommendation, execution observation, outcome capture, and post-mortem learning. A domain that stops at scoring is not platform-complete.

### No constitution exceptions by convenience

If a domain appears to require a different behavioral rule, that issue must be resolved through governed constitutional design, not through a quiet implementation shortcut.

## How Cross-Domain Coordination May Work Later

Domains must remain structurally separate, but they do not need to remain intellectually isolated.

Over time, the platform may need coordinated reasoning across domains. A promotion decision may interact with replenishment constraints. A markdown domain may interact with assortment logic. A local intervention domain may depend on both pricing and stock conditions.

Cross-domain coordination should therefore happen through governed interfaces, not through domain merger.

The correct long-term pattern is that separate domain modules expose clear decision objects, state artifacts, constraints, and outcomes that can be referenced by other domains through the shared architecture.

This allows coordination without collapse.

The platform may later support cross-domain orchestration, but only if each participating domain remains structurally legible in its own right.

## Architectural Invariants

The following invariants must remain true as the platform expands.

- The core architecture remains shared across all domains.
- Each business function remains a separate domain module.
- Every domain uses the same decision grammar.
- Every domain obeys the same constitution.
- Every domain uses controlled vocabulary.
- Every domain produces decision objects, constraint objects, outcome objects, and post-mortem learning artifacts.
- No domain bypasses explanation, governance, or post-decision learning.
- Domain expansion happens by addition of modules, not by uncontrolled enlargement of prior domains.
- Cross-domain coordination happens through interfaces and governed composition, not through conceptual merger.

## Non-Negotiables

1. The platform may eventually support 20 or more business functions, but each must remain structurally separate.
2. All business functions must use the same core architecture stack.
3. All business functions must obey the same decision constitution.
4. All business functions must use controlled vocabulary as a governing reference.
5. All business functions must produce governed decision outputs, constraint structures, outcome records, and post-mortem learning artifacts.
6. No business function may bypass the core governance model.
7. No new function may be added as an ad hoc feature inside an existing domain when it is structurally a new decision area.
8. Promotions is Domain 01, not the architectural container for every later function.

## Closing Statement

This pattern protects the platform from two predictable failures: the monolith that confuses every business function into one unstable domain, and the fragmented portfolio of one-off tools that never becomes a real decision system.

Fourth Form is building one retail decision intelligence platform with many business-function domains. The architecture is shared. The domains are separate. The decision grammar is common. The constitution is binding. The learning loop is universal.

If this pattern holds, the platform can grow in scope without losing coherence.

If it is broken, expansion will look productive for a while and then harden into drift.