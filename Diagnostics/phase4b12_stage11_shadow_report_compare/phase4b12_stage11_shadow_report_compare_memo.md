# Phase 4B.12 Stage 11 Shadow Report Comparison

**Mode:** Isolated manager-style action comparison. **NOT PRODUCTION. NOT CUSTOMER RELEASE.**

## Legacy vs 4B.11 capped shadow
| Metric | Legacy | Shadow 4B.11 |
|---|---|---|
| BUY count | 802 | 1,172 |
| HOLD count | 1,194 | 893 |
| Total order units | 2,193 | 2,893 |
| Total expected demand | 1,955.0 | 4,577.9 |
| Order > stock_basis | 250 | 60 |
| Order > demand_reference | 111 | 21 |
| Tiny demand + BUY | 456 | 295 |
| p90 / p99 / max order | 3.0 / 6.0 / 24.0 | |

## Change quality
- Added BUYs: **462**
- Removed BUYs: **92**
- Caps applied: **552** | Units removed: **1,171**
- Zero-order BUY: **0**
- Top 100 readability: **100.0%**
- Manager summary reconciles: **YES**
- Internal leakage: **NONE**

## Gate: **PASS**

## Approvals
| Question | Answer |
|---|---|
| Customer report release? | **NO** |
| Production retrain? | **NO** |
| Live swap? | **NO** |
