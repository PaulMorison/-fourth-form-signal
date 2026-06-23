# Phase 5B.9 evidence-weighted promotional demand

- Report quality score: 100/100
- Total selected promo-period demand: 6,290 units
- Baseline floor applied: 0
- Same-discount suppression cases: 221
- Best-seller escalation: 0
- BUY suppressed below baseline: 0
- DO_NOT_BUY on active best sellers (baseline>=5): 0
- REVIEW zero-order promo gap>10: 20

## Why same-discount fallback was under-ordering
Same-discount history was selected even when credible baseline-period demand (28+ source days) was materially higher, suppressing promo demand for active best sellers.

## How demand is selected now
Flat model placeholders are rejected. Model forecast is used only when non-flat and not below credible baseline. Same-discount history is blocked when baseline exceeds it. Baseline-period demand governs floors (>=3 units) and best-seller repair (>=5 units, escalation at >=10).

## Where demand is still unsafe
SKUs with no credible evidence remain VERY_LOW/WEAK with REVIEW or DO_NOT_BUY. Conflicting sources are flagged and routed to review.

## What remains below 98+
Residual REVIEW volume from stock-target conflicts, partial raw-model budgets, and SKUs lacking 56+ day baseline still cap the commercial release score.
