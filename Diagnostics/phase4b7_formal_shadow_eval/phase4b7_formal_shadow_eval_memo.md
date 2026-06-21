# Phase 4B.7 Formal Shadow Evaluation

**Mode:** Local enriched slices with 4B.7 re-engineered targets. No production retrain. No live swap.

## Target inputs (re-engineered)
- Combined rows: **11,261**
- Trainable share: **69.7%**
- Repaired share: **48.4%**
- Test rows: **2,140**

## Legacy vs 4B.7 shadow (test set)
| Metric | Legacy | 4B.7 Shadow |
|---|---|---|
| Flat share | 0.6% | 0.3% |
| Tiny (≤1) | 63.4% | 34.0% |
| Mean / p50 | 0.91 / 0.04 | 2.14 / 1.64 |
| p90 / p99 / max | 2.1 / 6.2 / 88.7 | 4.1 / 11.8 / 53.4 |

## Prior failed shadow vs 4B.7 shadow
| Metric | Prior (4B) | 4B.7 Shadow | Delta |
|---|---|---|---|
| Flat share | 2.1% | 0.3% | -1.8% |
| Tiny share | 32.5% | 34.0% | +1.5% |
| WMAE clean+repaired | 3.630 | 1.124 | -2.506 |
| WMAE repaired | 8.082 | 2.267 | -5.815 |
| > stock_basis share | 57.2% | 24.9% | -32.3% |
| > 2× demand share | 3.5% | 8.1% | +4.6% |

## Gate: **PASS**

## Decisions
| Question | Answer |
|---|---|
| Production retrain approved? | **NO** |
| Live swap approved? | **NO** |
| Report release? | **NO** |
| Next step | Human review of gate summary; tune acceptance thresholds if near-miss |
