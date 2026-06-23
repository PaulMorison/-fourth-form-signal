# Phase 4B.10 Action Overrun Diagnosis

**Mode:** Read-only scenario analysis on Phase 4B.9 shadow store actions. No production patch.

## Q1–Q3: Stock-basis overrun (550 rows)
- **Realized already > stock_basis:** 46 (8.4% of overruns) — stock_basis quality/context, not pure over-order.
- **True over-order risk (low realized + demand):** 89 (16.2%)
- **Added BUY overruns:** 136 of 550 (24.7%)
- **Existing BUY overruns:** 414

## Q4: Target quality concentration
- Overruns concentrated in **STOCK_CONSTRAINED_REPAIRED** rows (see `overrun_by_target_quality_and_repair_basis.csv`).

## Q5–Q7: Slices & tiny BUY
- Worst slices in `overrun_by_supplier_category_promo_type.csv`.
- Tiny-demand BUYs (341 rows): mainly **floor/gap-driven orders** despite tiny shadow demand + **missing action-level stock cap** on repaired rows.

## Q8–Q10: Action layer behavior (4B.9 eval)
- Action layer caps order by **projected stock gap** (promo demand + floor − projected SOH), **pack rounding**, not by stock_basis or demand_reference.
- `stock_basis_units` is **repair/target evidence**, not a hard order cap in current action path.
- Best cap scenario: **2_clip_stock_basis** → over_stock_basis 550 → 0.

## Q11: BUY threshold
- Best demand threshold scenario: **demand >= 1** → tiny BUY 341 → 0.

## Recommended Phase 4B.11 patch (smallest safe)
Apply **action-level conservative cap** on shadow/repaired path only:
`final_order_units = min(current_order, stock_basis, demand_reference)` when both caps exist; keep realized-sales override as review flag, not automatic overrun.

## Approvals
| Question | Answer |
|---|---|
| Patch next (4B.11)? | **After human review** |
| Stage 11 shadow report? | **NO** |
| Production retrain? | **NO** |
| Live swap? | **NO** |
| Report release? | **NO** |
