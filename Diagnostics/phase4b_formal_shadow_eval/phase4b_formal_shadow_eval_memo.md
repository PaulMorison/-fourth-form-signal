# Phase 4B Formal Shadow Evaluation

**Mode:** Local enriched slices only. No production retrain. No live model swap.

## Inputs
- Combined deduplicated rows: **11,261** (recent5k + hard5k enriched)
- Test rows evaluated: **2,140**

## Flat / tiny shares
| | Legacy | Shadow |
|---|---|---|
| Flat share | 0.7% | 2.1% |
| Tiny (≤1) | 71.2% | 32.5% |

## Weighted MAE vs target_actual_units_sold
- Clean+repaired legacy: 0.610
- Clean+repaired shadow: 3.630
- Delta: 3.020

## Tail / stock-basis risk (test set)
- Shadow > stock_basis: 1225 (57.2%)
- Shadow > demand_reference: 108 (5.0%)
- Shadow > 2× demand_reference: 74 (3.5%)
- Shadow p99/max: 37.2 / 117.4

## Gate: **FAIL**

## Decisions
| Question | Answer |
|---|---|
| Production retrain approved? | **NO** |
| Live swap approved? | **NO** |
| Report release? | **NO** |
| Next step | Human review of gate summary and top-tail rows; triage weighted MAE trade-off if shadow higher |
