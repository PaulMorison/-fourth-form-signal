# Phase 4B.6 Shadow Failure Diagnosis

## Root causes

### Repaired-row error (shadow MAE 8.08 vs legacy 0.94)
- Shadow learns `sufficient_stock_demand_units_target`; on repaired rows target >> actual (mean target error vs actual elevated).
- **REPAIR_UNDERALLOCATION** sets target ≈ `0.85 * demand_reference` with **no stock_basis cap** — dominant in top tail (newlines, normal catalogue, online promotion).
- Model fits repaired labels (mean ~demand-scale) while actuals often near zero/low → high MAE vs realized sales.

### Stock-basis overrun (57.2% shadow > stock_basis)
- **Target labels already exceed stock_basis** on many repaired rows before modeling (especially underallocation + post14 with tiny stock_basis e.g. 2–6 units vs demand 35–165).
- Shadow GB regressor tracks elevated repaired targets → predictions scale to target mean/p50 (~5–6) vs legacy ~0.01 p50.
- Overrun concentrated in **STOCK_CONSTRAINED_REPAIRED** (1380 test rows) and **REPAIR_UNDERALLOCATION** basis.

## Scenario findings (diagnostic proxy)
- **Best ceiling scenario:** `clean_only_shadow` — lowest repaired-over-stock-basis among caps.
- Weight-only reduction (0.20–0.30 max) does **not** remove stock overrun; targets still above stock_basis.
- **Clean-only shadow** removes repaired train signal — useful comparator baseline for Phase 4B.7.

## Recommended Phase 4B.7 patch (design only)
1. **Target module:** cap all repaired paths at `min(demand_reference, stock_basis_units)` (or conservative blend) — especially `REPAIR_UNDERALLOCATION`.
2. **Optional:** reduce repaired weights to ≤0.20 after cap.
3. **Shadow trainer:** add clean-only mode for first re-eval; keep repaired diagnostic-only until capped targets pass gates.

## Decisions
| Question | Answer |
|---|---|
| Patch target rules next? | **YES (Phase 4B.7)** — after review |
| Re-run shadow eval next? | **YES** — after 4B.7, not before |
| Production retrain? | **NO** |
| Live swap? | **NO** |
| Report release? | **NO** |

## Repair basis overrun (repaired test rows)
         target_repair_basis  rows  target_over_sb  shadow_over_sb
 REPAIR_POST14_FOLLOWTHROUGH    66        0.969697        0.893939
REPAIR_SATURATED_SELLTHROUGH   129        0.806202        0.759690
      REPAIR_UNDERALLOCATION  1185        1.000000        0.898734
