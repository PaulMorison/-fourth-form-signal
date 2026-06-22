# Phase 4B.9 Shadow Store-Action Evaluation

**Mode:** Read-only allocation-contract actions on 4B.7 formal shadow test rows. No production change.

## Rows evaluated: **2,140**

## Action summary
| Metric | Legacy | 4B.7 Shadow |
|---|---|---|
| BUY count | 802 | 1,263 |
| HOLD count | 1,194 | 821 |
| Total order units | 2,193 | 4,064 |
| Tiny demand rows | 1,357 | 727 |
| Tiny demand + BUY | 456 | 341 |
| Order > stock_basis | 250 | 550 |
| Order > demand_reference | 111 | 119 |
| Order > 2× demand_reference | 103 | 106 |
| p99 / max order | 6.0 / 91.0 | 10.0 / 55.0 |

## BUY changes
- Shadow added BUY: **466**
- Shadow removed BUY: **5**

## Gate: **FAIL**

## Recommendations
| Question | Answer |
|---|---|
| Shadow improves store-action usefulness? | **REVIEW** |
| Stage 11 shadow report comparison next? | **NO — tune first** |
| Production retrain? | **NO** |
| Live swap? | **NO** |
| Report release? | **NO** |
