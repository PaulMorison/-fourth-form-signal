# Phase 4B Sufficient-Stock Demand Target Design

**Mode:** Target/label design only. No SQL, no training, no trainer patches.  
**Branch:** cursor/promotions-actual-outcome-stock-truth  
**Inputs:** Phase 4 raw model flatness diagnostic, code review of target engineering + trainer  
**Output dir:** `Diagnostics/phase4b_sufficient_stock_target_design/`

---

## Executive summary

Phase 4 established that raw model flatness is **learned model behavior** on near-homogeneous sparse features, trained on **realized sales** (`target_actual_units_sold = actual_units_sold`). That label is stockout-contaminated and teaches the units head to predict tiny near-zero totals for sparse SKUs.

Phase 4B defines a **governed sufficient-stock demand target contract** that separates realized sales from training demand, gates rows by stock evidence quality, repairs stock-constrained rows with bounded logic, and excludes contaminated or insufficient-evidence rows rather than training them as zero.

| Decision | Result |
|---|---|
| Patch training code now? | **NO** |
| Patch Stage 11 / demand contract? | **NO** |
| Use feature consensus as target? | **NO** |
| Customer-ready / report release? | **NO** |
| Smallest safe next patch | **4B.1** — new target ft module (design approved first) |

---

## Answers to design questions

### 1. Where is the current units target built?

| Step | Location |
|---|---|
| Label derivation | `src/state/promotions/feature_engineering/targets/ft_target_units_sold.py` → `apply_ft_target_units_sold` |
| Orchestration | `src/state/promotions/targets/target_engineering.py` → `PromotionTargetEngineer.engineer` |
| Dataset persistence | `src/state/promotions/datasets/dataset_assembler.py` |
| Model fit | `src/models/promotions/trainer.py` → `units_tree.fit(..., train_targets['target_actual_units_sold'])` |

### 2. What exact field becomes the units target?

**`actual_units_sold`** (promo-window realized net units from completed window aggregates) → clipped to ≥0 → stored as **`target_actual_units_sold`**.

Note: `actual_units_sold_promo` is an alias of the same value after `completed_dataset_joiner` join.

### 3. What stock/SOH evidence is available today?

**Available now (training dataset):**

- Stock at decision: `current_soh`, `qty_on_order`, `pl_allocation_qty`, `store_adjusted_qty`, `total_units_commited`, `total_stock_available`
- Derived: `stock_basis_units`, `demand_reference_units`, `baseline_expected_units`, `required_implied_units`
- Outcome: `actual_units_sold`, `promo_sales_day_count`, `post_14d_units`, `post_14d_days_with_sales`
- Derived targets: `target_sell_through_pct`, `target_leftover_stock_pct`, `target_stockout_flag`, `target_underallocation_flag`
- Historical proxy features: `feature_stock_constrained_history_flag`, `feature_lost_sales_risk_score`

**Not available today:**

- Intra-promo daily SOH / stockout-day counts
- Packet-level `actual_stockout_flag` (planned in actual_outcome contract, not yet in training rows)

See `available_stock_evidence_fields.csv`.

### 4. Can sufficient-stock demand be built now from existing fields?

**Partially yes**, with explicit limits:

- **Clean target** rows: sufficient stock can be proxied when sell-through is not saturated, leftover stock exists, and stock basis is valid.
- **Repaired target** rows: stock-constrained cases can receive bounded uplift using `post_14d_units`, `demand_reference_units`, and `stock_basis_units` ceilings.
- **Cannot fully prove** full-window sufficient stock without intra-promo availability data — design must fail conservative (exclude or low-weight) when evidence is weak.

### 5. Which cases should be excluded?

- Negative SOH or sales with zero/missing stock basis (integrity contaminated)
- No sales + no selling days + no stock basis (insufficient evidence — **not zero-demand label**)
- Sparse no-history SKUs with zero sales and near-zero baseline (insufficient evidence)
- Unrepairable stockout (no post_14d, no demand_reference ceiling)
- Refund-dominated net units

See `target_exclusion_rules.csv`.

### 6. Which cases can be repaired?

- Stockout flag with post-promo follow-through sales
- Saturated sell-through (≥98% of stock basis) with valid stock basis
- Underallocation (stock basis < 85% demand reference) without stockout flag
- Partial selling window (low `promo_sales_day_count` vs promo duration) with high sell-through

See `stock_constrained_target_repair_rules.csv`.

### 7. Repair rule for stock-constrained sales?

**Principle:** Realized sales is a **lower bound**, not demand truth.

| Scenario | Repair |
|---|---|
| Stockout + post_14d follow-through | `realized + min(post_14d, post_14d*0.5)` capped at `min(demand_reference, stock_basis*1.25)` |
| Stockout + saturated sell-through | `max(realized, min(demand_reference, stock_basis*1.15))` |
| Underallocation only | `max(realized, demand_reference*0.85)` |
| Partial selling days | `max(realized, baseline_expected_units)` capped at demand_reference |

**Never:** feature consensus, unconstrained uplift, or inflation beyond governed ceilings.

### 8. Stockout-contaminated rows: weight down, exclude, or repair?

| Evidence | Action |
|---|---|
| Clean sufficient stock | Use realized as target, weight **1.0** |
| Repairable stock constraint | Repaired target, weight **0.30–0.50** |
| Integrity failure | **Exclude**, weight **0.0** |
| Insufficient evidence | **Exclude**, weight **0.0** — do not train as zero |

### 9. Negative SOH handling?

Set `stock_integrity_issue_flag = 1`, assign `INVENTORY_INTEGRITY_CONTAMINATED`, **exclude from training** (weight 0). Do not coerce negative SOH to zero for target purposes.

### 10. Sparse promo history handling?

Do **not** train zero-sales sparse-history rows as zero-demand labels (this reinforces the flat GBM leaf seen in Phase 4). Mark `INSUFFICIENT_EVIDENCE`, exclude (weight 0). Model may still predict from features at inference; target layer must not teach collapse.

### 11. Feature consensus usage?

**Diagnostic and escalation only.** Never input to `sufficient_stock_demand_units_target`. May appear in demand-collapse warnings (Patch B) but not as training label or repair formula input.

### 12. Smallest safe Phase 4B implementation sequence?

1. **4B.1** — New `apply_ft_sufficient_stock_demand_target` module (pure target logic + tests)
2. **4B.2** — Wire into `PromotionTargetEngineer` parallel to legacy column
3. **4B.3** — Target quality slice inventory diagnostics
4. **4B.4** — Trainer target-mode flag (shadow only)
5. **4B.5** — Sample weights
6. **4B.6** — Backtest gate before any production retrain

See `phase4b_implementation_sequence.csv`.

---

## Proposed target contract (summary)

| Column | Purpose |
|---|---|
| `realized_sales_units` | Observed sales (audit + lower bound) |
| `stock_constrained_flag` | Realized likely understates demand |
| `stock_integrity_issue_flag` | Unreliable inventory record |
| `sufficient_stock_observed_flag` | Realized ≈ demand evidence |
| `sufficient_stock_demand_units_target` | **New units training label** |
| `target_quality_label` | Quality bucket |
| `target_weight` | Training sample weight |

Full schema: `sufficient_stock_target_schema.csv`.

### Clean target rule

Use **`realized_sales_units`** as `sufficient_stock_demand_units_target` when:

- `stock_integrity_issue_flag = 0`
- `stock_basis_units > 0`
- `target_stockout_flag = 0` and `target_underallocation_flag = 0`
- `target_sell_through_pct < 0.85` OR `target_leftover_stock_pct >= 0.05`

Weight: **1.0** (0.85 for borderline sell-through 0.85–0.98).

### Repaired target rule

When `stock_constrained_flag = 1` and integrity clean, apply bounded repair formulas in `stock_constrained_target_repair_rules.csv`. Weight: **0.30–0.50**.

### Exclusion rule

Integrity contaminated, insufficient evidence, or unrepairable stockout → `target_weight = 0`, label `EXCLUDED_FROM_TARGET` or `INSUFFICIENT_EVIDENCE`. **Do not impute zero.**

### Target weighting rule

Only `CLEAN_REALIZED_DEMAND` and `STOCK_CONSTRAINED_REPAIRED` rows contribute to units-head loss. Weights scale by repair confidence (see `target_weighting_rules.csv`).

---

## Relationship to Phase 4 findings

| Phase 4 finding | Phase 4B response |
|---|---|
| Model learns flat ~0.05 baseline | Stop training sparse/zero rows as zero; exclude insufficient evidence |
| Target = realized sales | Introduce sufficient-stock target with quality gating |
| Stockout contamination YES | Repair or exclude stock-constrained rows |
| Feature consensus > raw on 892 SKUs | Keep as warning; never as target |
| Stage 11 / demand contract clean | No further Stage 11 patches for this issue |

---

## Risks

See `phase4b_risk_review.csv`. Top risks: repair inflation (mitigate with ceilings), heuristic stockout mislabel (mitigate with slice review + future packet fields), over-exclusion reducing training rows (monitor by slice).

---

## Decision

| Question | Answer |
|---|---|
| Patch training next? | **NO** — approve design first |
| Release report? | **NO** |
| Next implementation step | **4B.1** target ft module |

## Artifacts

- `current_units_target_trace.csv`
- `available_stock_evidence_fields.csv`
- `target_quality_rules.csv`
- `stock_constrained_target_repair_rules.csv`
- `target_exclusion_rules.csv`
- `target_weighting_rules.csv`
- `sufficient_stock_target_schema.csv`
- `phase4b_implementation_sequence.csv`
- `phase4b_risk_review.csv`
