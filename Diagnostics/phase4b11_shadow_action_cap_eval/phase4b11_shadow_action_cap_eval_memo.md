# Phase 4B.11 Shadow Action-Cap Evaluation

**Cap rule:** `final_order_units = min(uncapped_order_units, stock_basis_units, demand_reference_units)` after pack rounding (shadow eval only).

## Metrics
| Metric | Legacy | 4B.9 Shadow | 4B.11 Shadow |
|---|---|---|---|
| BUY count | 802 | 1,263 | 1,172 |
| Total order units | 2,193 | 4,064 | 2,893 |
| Order > stock_basis | 250 | 550 | 60 |
| Order > demand_reference | 111 | 119 | 21 |
| Tiny demand + BUY | 456 | 341 | 295 |
| p99 / max order | 6.0 / 91.0 | 10.0 / 55.0 | 6.0 / 24.0 |

## Cap audit
- Caps applied: **552**
- Units removed: **1,171**
- Realized exceeds cap (review): **165**
- Zero-order BUY: **0**

## Gate: **PASS**

## Approvals
| Question | Answer |
|---|---|
| Stage 11 shadow report next? | **YES — after review** |
| Production retrain? | **NO** |
| Live swap? | **NO** |
| Report release? | **NO** |
