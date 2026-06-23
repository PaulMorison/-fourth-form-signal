# Phase 5A executive review memo

## Scores

| Metric | Score |
|--------|-------|
| **Current commercial usability** | **14 / 100** |
| **Reorganised potential** | **78 / 100** |

## Why the system is not commercially usable yet

The promotions stack is a strong **research and diagnostics platform** packaged as if it were a **store product**. Model logic (sufficient-stock targets, action caps, demand contracts) is ahead of reporting. The store sees:

- Multiple conflicting folder roots
- Historical promotions (Feb–Apr 2026) in shadow order packs while live runtime has Jul 2026+ promos
- 600-column allocation reports as the de facto action file
- Uppercase shadow filenames alongside lowercase pilot files
- No single index for "what do I order this week?"

A no-skill operator cannot act without verbal guidance. That is a **product failure**, not a model failure.

## Most valuable existing parts

1. **`sufficient_stock_demand_target.py`** — target repair with stock/demand ceiling
2. **`shadow_store_action_eval.py`** — conservative action cap (550→60 overruns)
3. **`allocation_stock_contract.py`** — order/gap math tied to demand windows
4. **Enriched training parquet** — discount, capital, actuals, stock fields
5. **4B.21 `order_plan_all_skus.csv` schema** — correct commercial shape (wrong date window)

## Biggest structural problems

1. **Date window mismatch** — order packs not anchored on ≥ 2026-06-20 future promos
2. **Six output layers** — priceline, 772/prediction, mirrors, three shadow pack generations
3. **Stage 11 builder** — audit-first, not buyer-first
4. **Future/completed conflation** — same promos in both families in 4B.21 pilot
5. **Script-sprawl** — commercial packs built by tmp post-processors, not publisher

## Fastest path to 80/100

1. Approve target architecture (this memo + `target_commercial_architecture.md`).
2. Phase 5B: implement `commercial_report_builder` in publisher path.
3. Generate packs only for **promotion_start_date ≥ 2026-06-20** from live scoring.
4. Archive all phase4b shadow delivery folders; single runtime root.
5. Gate publish on scorecard ≥ 95.

## What to do next (Phase 5B — after approval)

- Implement publisher-integrated commercial pack writer
- Wire Jul 2026+ priceline promotions into `future/` folders
- Move Feb–Apr shadow pilots to `archive/`
- Add integration test + scorecard gate
- Update operator handoff to new paths only

## What not to do next

- Do not retrain or live-swap models to "fix" reporting
- Do not build more tmp post-hoc pack scripts
- Do not add another parallel folder naming scheme
- Do not use completed promotions as primary order-planning examples
- Do not delete production priceline files
- Do not release customer reports or place orders

## Governance confirmation (this phase)

| Item | Status |
|------|--------|
| Code changed | **NO** |
| Files deleted | **NO** |
| Runtime mutated | **NO** |
| Orders placed | **NO** |
| Retrain run | **NO** |
| Live model changed | **NO** |
| Customer report release | **NO** |

## Recommended store entry (after 5B)

`commercial_reports/read_me_first.md` → `future_promotions_index.csv` → `future/<promo>/order_plan_all_skus.csv`

**Current interim entry (pre-5B):** priceline date folder allocation report — commercially weak; use only with caution.
