# Commercial gap analysis (Phase 5A)

**Review date:** 2026-06-22  
**Scope:** Promotions system — code, runtime, shadow packs, diagnostics  
**Future promotion cutoff:** 2026-06-20

## Dimension scores (current system)

| Dimension | Score /10 | Notes |
|-----------|-----------|-------|
| Future promotion relevance | 1 | Shadow packs use Feb–Apr 2026 promos; live runtime has Jul 2026 folders — no unified future pack |
| Promotion separation | 4 | 4B.20/21 separated by promo; production still multi-promo per run folder |
| All-SKU visibility | 5 | 4B.21 includes all SKUs; production allocation reports bury HOLD in wide files |
| Order clarity | 3 | BUY/HOLD visible but order math hidden behind jargon and wide schemas |
| Demand-window clarity | 2 | `expected_promo_demand` without window; pre-promo vs promo-period split only in recent scripts |
| Stock-position clarity | 4 | Fields exist in old reports but inconsistent naming and not in primary shadow path until 4B.20+ |
| Explanation quality | 3 | Split reasons in 4B.21; production uses compressed `reason_short` / audit notes |
| Data quality labelling | 5 | Shadow labels good; confidence/quality scores ad-hoc in scripts not production |
| Completed-promotion review | 4 | 4B.21 completed folders exist but use same historical promos as future demo |
| Audit trail | 8 | Excellent engineering diagnostics; wrong audience for store buyer |
| User confidence (no-skill operator) | 2 | Requires Paul to explain which folder, which file, which date |
| Commercial sales value | 3 | Strong model R&D; weak product packaging |

### Aggregate scores

| Metric | Score |
|--------|-------|
| **Current commercial usability** | **14 / 100** |
| **Reorganised potential** (existing parts structured correctly) | **78 / 100** |

Potential rationale: sufficient-stock target repair, shadow action cap, stock contract, enriched demand fields, and 4B.21 report schema are **~80% of needed logic**. Failure is **productisation**: paths, dates, naming, single workflow, future/completed split, and one promotion = one folder from 2026-06-20 onward.

## Why not higher than 14 today

- No authoritative pack for **live future promotions** (≥ 2026-06-20).
- Six overlapping output locations with different conventions.
- Production Stage 11 output is an audit dump, not an order plan.
- Buyer workflow is diagnostic-first, not action-first.
- Completed promos incorrectly presented as order-planning examples.

## Why potential is ~78 (not 98)

- Actuals pipeline for completed review not fully productised.
- Capital/GP fields partial in enriched data.
- Production publisher rewrite still required (high risk).
- Operator feedback ingestion not closed loop.
- Multi-store / multi-banner scale not addressed.

## Gap to 80/100 (priority order)

1. Anchor future packs on **promotion_start_date ≥ 2026-06-20** from live scoring output.
2. Single runtime root with `future/` and `completed/` only.
3. One promotion folder = six lowercase files (4B.21 schema).
4. Rewrite publisher to emit commercial pack directly (not post-hoc scripts).
5. Archive all phase4b shadow delivery folders from repo index.
6. Kill 600-column allocation report as **primary** store file (keep as audit_trail only).
