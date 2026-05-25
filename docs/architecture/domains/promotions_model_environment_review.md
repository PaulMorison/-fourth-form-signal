# Promotions Model Environment Review

> Scope: pre-promo non-promo demand vs live-promo demand vs post-promo demand
> vs prior-promo memory separation. Whether rolling 2-week schedules
> contaminate the baseline window. Whether a promotion week is incorrectly
> treated as clean baseline. What a next pass should change.

This review answers six concrete questions about the promotions modelling
environment as it stands today. It is the model-environment counterpart to
`docs/commercial/promotions_store_facing_commercial_hardening_report.md`,
written so an operator can decide whether the per-promotion CSV the model
emits is anchored to the right slice of history.

## 1. What windows does the model treat as "baseline" non-promo demand?

Baseline non-promo demand is constructed from the SKU-store sales history
in the period preceding each scoring point, with explicit exclusion of any
day flagged as falling inside an active promotion window
(`promotion_start_date_date` ≤ day ≤ `promotional_end_date_date`).

Active windows are read from the canonical promotions header (priceline /
store 772 in the current operating client). Days inside an active window
are excluded from baseline aggregation; they cannot be silently averaged
into the "what does this SKU do at full price" signal.

The fallback if the header is incomplete is `is_in_promotion_window=0`
treated as baseline, which is the expected loud-fail surface (governance
catches missing header coverage upstream of training).

## 2. What windows does the model treat as "live-promo" demand?

Live-promo demand is the sales density observed strictly inside the
`promotion_start_date_date .. promotional_end_date_date` window of
each tagged promotion. It is the only window from which `promo_uplift_*`
features and the `actual_sales_ex_gst_promo` regression target are derived.

## 3. What windows does the model treat as "post-promo" demand?

Post-promo demand is the 7- and 14-day window immediately after
`promotional_end_date_date`. It is currently used for two purposes:
(a) `post_promo_dip_rate` (a feature input that captures how much the
SKU drops after the promo finishes); (b) the upcoming Stage 9.5 backtest
calibration looks at this window to confirm leftover-sell-through claims.

This window is **excluded** from baseline. A SKU that goes 50% off the
day before another promo starts must not appear as "baseline = high".

## 4. What is "prior-promo memory" and how does it reach the final input?

Prior-promo memory is the set of features built by
`src/state/promotions/feature_engineering/demand/ft_prior_promo_memory.py` and confirmed
present in the final scoring frame by
`tests/unit/test_promotions_prior_promo_memory_features.py`. The features:

- `prior_promo_response_ratio` — observed uplift on the most recent
  comparable prior promotion at the same store and SKU.
- `prior_promo_count` — how many prior promotions on this SKU at this
  store the model can actually anchor to (a confidence weight).
- `prior_promo_recency_days` — how stale the most recent comparable
  promotion is.
- `intermittent_demand_cadence_days` — average gap between non-zero
  sales days outside promo windows.
- `intermittent_demand_zero_day_share` — share of days with zero
  sales in the baseline window.

These features are fail-loud asserted on the final model input (see the
training pipeline's required-feature check in
`src/state/promotions/datasets/model_input_export.py`). A scoring frame that drops them is
rejected before predictions are written.

## 4.1. What is the governed probability feature layer and why does it exist?

The governed probability feature layer is built under
`src/state/promotions/feature_engineering/demand/probability/` and wired into the
feature registry through a single bundle module. Its purpose is not to replace
the main model with a standalone distributional forecast. Its purpose is to make
uncertainty explicit enough that the main model can learn safer ordering
decisions, especially for low-volume, lumpy, sparse-history, and zero-heavy
promotion rows.

The layer now has seven explicit modules:

- `ft_probability_poisson_features.py`: stable low-volume comparable history where a simple count process is still defensible.
- `ft_probability_negative_binomial_features.py`: materially over-dispersed lumpy history where Poisson variance assumptions break.
- `ft_probability_bayesian_poisson_features.py`: sparse evidence where the platform should shrink older history and a weak governed prior together with the most recent pre-decision evidence.
- `ft_probability_zero_inflated_features.py`: strictly prior comparable history with a genuine excess-zero pattern rather than ordinary low demand.
- `ft_probability_hypothesis_test_features.py`: effect size, p-value, sample size, confidence-interval width, stability, and repeatability surfaces for uplift-style evidence.
- `ft_probability_companion_features.py`: basket dependence and companion-risk surfaces derived from the completed transaction seam.
- `ft_probability_overallocation_summary.py`: the smaller model-use layer that combines the lower-level evidence into consensus expected units, consensus zero-sale risk, consensus tail risk, overallocation risk, and demand confidence.

Blank outputs in this layer are deliberate. A blank probability or blank fitted
distribution parameter means the row did not satisfy the evidence requirements
for that distributional assumption. It does not mean "zero risk".

The final model-input boundary now keeps a smaller model-use subset and leaves
the rest as review-only diagnostics. The model-use subset is intentionally the
summary layer plus the bounded stability signals: consensus expected units,
consensus zero-sale risk, consensus tail risk, overallocation risk, demand
confidence, model-use flag, units-lift stability, and same-discount
repeatability. Low-level model-specific expected units, priors/posteriors,
dispersion or zero-inflation detail, raw p-values, and companion-detail
diagnostics remain useful for audit, but they are no longer allowed to reach
the trained schema by default.

Raw p-values are not promoted on their own. They are review-only because they
need sample size, effect size, interval width, and stability context; otherwise
they invite false precision in thin-history rows.

The strongest model-use outputs are intended to help reduce over-allocation:

- consensus expected units
- consensus zero-sale risk
- consensus tail risk against the current order threshold
- overallocation risk
- demand confidence
- units-lift stability and same-discount repeatability

## 4.1.1. How does probability evidence become allocation discipline?

The probability summary is not enough on its own. The ordering decision also
needs to know whether the current stock or allocation sits materially above the
probability-supported expected demand. That comparison is owned by the governed
allocation discipline feature layer, wired after the probability bundle so it
can only read model-use probability summary outputs.

The layer's business use is narrow: reduce over-allocation by exposing excess
units and capital at risk when the order is high relative to consensus expected
demand, while leaving legitimate upside rows visible through sell-through and
under-allocation signals. Its grain remains one promotion/store/SKU row. Its
sources are the current row's allocation basis, effective unit cost, and the
model-use probability consensus fields derived from strictly prior comparable
history. It must not read realised promo outcomes or review-only distribution
parameters.

When probability evidence is absent or the probability model-use flag is not
set, the probability-specific allocation comparisons remain blank rather than
being backfilled with a false zero-risk value. Bounded score outputs must stay on
0..1 and raw unit/capital outputs remain numeric diagnostics.

Training metrics must judge the same decision problem. In addition to generic
regression and classifier metrics, the model family should report excess-unit
MAE, excess-capital-at-risk MAE, and false-positive / false-negative allocation
cost proxies for validation and test splits. These metrics are decision-quality
evidence; they are not new operator presentation fields.

The units forecast may be capped only under the same governed evidence rule:
probability model-use evidence is present, the allocation discipline score is
material, and the raw units prediction exceeds a probability-supported upper
demand bound. The cap is one-way; it may reduce an over-confident forecast
toward probability-supported demand, but it must not inflate a forecast or
hide legitimate upside. The upper bound is the probability expected units
expanded by tail risk and low-confidence slack.

## 4.1.2. What is the governed same-discount demand evidence layer?

The promotions system now needs an explicit layer for strict same-store,
same-SKU, same-discount demand evidence instead of relying on a single broad
history blob. That ownership belongs in feature modules under the demand family,
not in Stage 11/12 presentation logic.

The governed rules are narrow:

- only prior completed promotions may contribute evidence
- prior `promotional_end_date_date` must be strictly earlier than the candidate
  `promotion_start_date_date`
- same-discount evidence must stay separate from same-or-better-discount
  evidence
- no pooling across stores and no pooling across SKUs
- missing same-discount history must emit explicit no-history flags rather than
  fake zero-risk precision

The strongest model-use outputs from this layer should answer simple audit
questions: how many same-discount events exist, what units and uplift were seen
before, how recently did they happen, and how stable was the response?

## 4.1.3. What is the governed non-promotional baseline orientation layer?

The baseline layer used for promo demand should not be a vague rolling average
that still carries promo contamination. The governed baseline-orientation layer
must isolate normal non-promotional demand for the same store and same SKU,
using only history that was outside promo windows and strictly available before
the candidate promotion.

This layer exists to answer a different question from promo memory: what would
this SKU likely sell without the discount? The core outputs are non-promo daily
demand level, recent-vs-medium trend, sales-day density, sparse-history flags,
and a clear distinction between no-history, low-history, and stable-history
rows. These baseline signals are the anchor for uplift decomposition and launch
stock sizing.

## 4.1.4. What is the governed uplift decomposition layer?

Promo demand must now be decomposed into:

- baseline units expected anyway during the promo window
- incremental discount-driven uplift supported by prior comparable evidence
- uncertainty and instability around that uplift

This layer may use strict prior completed promotion evidence and current-row
baseline orientation outputs, but it must not learn from realised outcomes on
the candidate row. Any realised uplift diagnostics on the candidate itself are
review-only.

Weak uplift evidence must reduce confidence explicitly. The governed failure
mode is not "zero uplift"; it is "insufficient support to justify aggressive
uplift-backed stock".

## 4.1.5. What is the governed elasticity layer?

Elasticity in this codebase is not an academic demand-curve exercise. It is a
store+SKU-specific summary of whether deeper discount has historically produced
more uplift for prior completed promotions, and whether that response is stable
enough to trust.

Simple, auditable slope-based estimation is preferred. The governed outputs are
event count, response slope, magnitude, fit quality, direction consistency,
instability, and confidence. If the history is thin, confidence must fall and
the stable summary features must stay conservative. Raw unstable parameters may
exist for review, but not as model-use features by default.

## 4.1.6. How should launch demand differ from total-window demand?

Lead-up demand, launch demand, and full-promo holding demand are different stock
problems and must not be flattened into a single daily number.

- lead-up depletion should be baseline-led
- launch stock should be based on baseline demand plus supported uplift for the
  early promo window
- full-window pressure should not auto-justify launch stock when uplift support
  is weak

If launch support is weak but full-window pressure is high, the governed action
is to escalate to review rather than auto-ordering against total-window demand.
This rule belongs in the evidence-aware allocation and order-sizing path, not in
presentation-only logic.

## 4.1.7. What is the governed order-decision diagnostics layer?

The baseline/uplift/elasticity pass improves prediction structure, but it does
not by itself explain why the system still over-orders on particular rows. That
diagnostic gap must be closed inside the existing demand and allocation path,
not by creating a parallel review framework.

The governed order-decision diagnostics layer sits after uplift decomposition
and allocation discipline and is derived only from already-governed features.
Its job is to expose compact, leakage-safe reasons why a row remains risky to
over-order. The intended outputs are interpretable flags and compact scores,
for example:

- weak same-discount support
- weak elasticity confidence
- weak uplift support
- falling baseline trend
- launch-vs-total support conflict
- large stock-vs-supported-demand gap
- sparse or low-quality history

This layer is diagnostic, not predictive. It must not invent new raw-history
joins, new outcome semantics, or a second decision policy. If the row is risky,
the diagnostics must say which governed evidence seam is weak and how many weak
drivers are active.

## 4.1.8. What is the governed allocation decision scoreboard?

The trainer and backtest path must now persist a governed allocation decision
scoreboard so the next hardening pass can target real failure modes instead of
arguing from anecdotes.

The scoreboard belongs beside the existing allocation outcome metrics and test
set prediction artifacts. It should decompose excess-units and excess-capital
error into readable governed buckets such as:

- same-discount history strength: `no_history`, `low_history`,
  `adequate_history`, `strong_history`
- elasticity confidence: `low_confidence`, `medium_confidence`,
  `high_confidence`
- uplift confidence: `low_confidence`, `medium_confidence`,
  `high_confidence`
- base-demand trend: `falling_base`, `flat_base`, `growing_base`
- launch-vs-total conflict: `no_conflict`, `moderate_conflict`,
  `high_conflict`

The scoreboard must also report driver combinations, worst over-allocation
patterns, evidence coverage, and the volume of rows forced onto weak fallback
logic. This is not optional reporting fluff; it is the governed feedback loop
for deciding which evidence seam still fails commercially.

## 4.1.9. How should live scoring and Stage 11 reporting surface diagnostics?

Live scoring must persist compact per-row diagnostics describing which evidence
sources were present, whether sizing was mainly baseline-led, uplift-led, or
fallback-led, whether a review escalation was caused by evidence conflict, and
which mechanism actually capped the row.

Stage 11 reporting must not clutter the operator CSV with these internals. The
governed approach is to keep the store-facing CSV stable and write separate
diagnostic summary artifacts for commercial and operator review. The reporting
question is aggregate operational trust, not per-row model debugging in the
store file.

## 4.1.10. How should the new scoreboard change live policy?

The scoreboard exists to drive a small, explicit hardening layer on top of the
existing calibrated demand output. The governed policy must not create a second
decision framework, replace the trained model, or silently rewrite history. It
must consume the existing row-level order diagnostics and apply named,
auditable, conservative adjustments only in the worst evidence buckets.

The intended order of operations is:

- raw model units
- calibrated units from allocation discipline
- explicit policy adjustment overlay derived from the governed diagnostics
- Stage 11 recommendation and review handling

That sequencing matters. The policy layer is not allowed to pretend it is part
of model fitting. Its job is to reduce known over-ordering failure modes after
the calibrated forecast already exists.

The governed policy outputs should stay compact and explicit:

- adjusted supported total units
- adjusted launch units
- adjusted order cap units
- review override flag and reason
- policy adjustment reason and strength

The policy rules must be simple, named, and tied to real failure buckets the
scoreboard already surfaces, especially:

- weak same-discount history with weak uplift support
- weak elasticity confidence
- falling base demand with high launch-vs-total conflict
- large stock-vs-supported-demand gap
- sparse history with multiple weak evidence drivers

If a row remains commercially unsafe after the conservative cap, the governed
action is explicit review escalation rather than hidden extra precision.

## 4.1.11. What should the next trainer and Stage 11 artifacts show?

Once the policy layer exists, diagnostics must compare three states rather than
two:

- raw model output
- calibrated output
- policy-adjusted output

Backtest and training artifacts should report excess-units and excess-capital
error for all three states overall and for the worst governed buckets. That is
how the platform proves the policy is actually reducing over-ordering in the
rows it claims to target.

Stage 11 must continue to keep the operator CSV stable. Any policy action
counts, units removed, capital-at-risk reduced, forced-review counts, and top
policy reasons belong in separate diagnostic summary artifacts, not in the
store-facing file.

## 4.1.12. How should the policy layer be measured before any further tightening?

The next governed pass is measurement, not another modelling redesign. The
policy layer must prove three things with artifact evidence before any further
rule tightening is allowed:

- whether policy-adjusted output improves excess-units and excess-capital error versus both raw and calibrated states
- which named policy buckets still remain commercially bad after policy
- whether one dominant residual failure mode exists strongly enough to justify one narrow correction

That measurement must reuse the existing out-of-sample allocation diagnostic row
table owned by trainer. The compact comparison artifact should report total
rows scored, policy-adjusted rows, policy-forced reviews, units removed,
capital-at-risk removed, and raw vs calibrated vs policy-adjusted excess error
metrics overall and by the named policy buckets.

The ranking artifact should then sort the named policy buckets by remaining
policy-adjusted excess-capital error, show the incremental policy improvement
versus calibrated output, surface the top policy reason in each bucket, and
mark whether a bucket still remains materially bad after policy.

Residual analysis must stay separate from the store-facing CSV. For the single
worst remaining bucket only, the platform should persist a top-row residual
artifact showing remaining excess-capital error, whether policy fired, the
named policy reason, review override state, and the supporting evidence fields
that explain why the bucket still fails. If no bucket remains materially bad
after policy, the residual artifact should record a null bucket and no residual
rows rather than pretend a failure remains.

No further policy change is allowed without this evidence. If the ranking and
residual artifact do not show one dominant failure mode, the governed outcome is
to stop after measurement rather than quietly stack extra caps.

## 4.2. What is the governed basket and mission context layer and why does it exist?

The governed basket and mission context layer sits beside the prior-promo and
probability layers and uses the completed transaction-aggregate seam to answer a
different question: does this SKU usually move alone, as part of a larger
basket, or as part of a highly companion-dependent mission?

It is built from strictly prior completed same-store same-SKU promotions only.
The layer intentionally stays within the columns the governed transaction seam
really exposes today: transaction counts, solo-vs-multi-item counts, basket
size and basket value summaries, weekend/pay-cycle transaction counts, top
companion SKU shares, companion concentration, and a conservative stock-
constrained proxy derived from stock basis plus early sell-through. It does not
invent buyer-level mission features, companion-category semantics, or direct
in-stock-rate measures because those sources are not yet present.

The strongest basket-facing outputs are intended to reduce over-ordering when a
SKU is not genuinely a standalone demand line:

- basket attach rate vs solo purchase rate
- basket dependency score and companion over-allocation risk
- top companion concentration and companion absence risk
- transaction rate and weekend/pay-cycle mission sensitivity
- stock-constrained history flag plus lost-sales risk proxy
- basket history evidence counts and missingness flag

Basket dependence matters because a SKU that usually moves inside multi-item
baskets or concentrated companion missions can look healthy in raw prior unit
history while still being fragile at execution time. That fragility is now
allowed to influence the probability summary through the companion-risk path
without forcing the raw basket diagnostics directly into training.

## 5. Does a rolling 2-week promo schedule contaminate the baseline?

Risk: yes, if header coverage is incomplete. A SKU that is on promo 1 in
1 weeks (because the retailer runs constant rolling promos) may have
*zero* genuine baseline days in the recent window. The current
mitigation is:

- `is_in_promotion_window` excludes promo days from baseline.
- `intermittent_demand_zero_day_share` and
  `prior_promo_count` reach the model so it can express low confidence
  when baseline coverage is thin.
- `demand_evidence_class` (and `commercial_publishability_split.json`)
  surfaces `sparse_repeat_purchase` and `cold_start_new_line` as
  governed buckets so artificially-collapsed forecasts do not
  silently propagate to publish.

What the model does NOT yet do:
- Quantify what fraction of the 56-day pre-promo window was free of
  any promo for the candidate SKU. This is what the next pass should
  add as an explicit `pre_promo_clean_days_share` feature so the
  operator can see "we sized this off 47/56 clean days" vs "we sized
  this off 4/56 clean days, treat with care".

## 6. Is a promotion week ever incorrectly treated as clean baseline?

Two failure modes have been observed in earlier hardening passes:

1. **Header gap on a comparable prior promo**. If the same SKU ran a
   non-Priceline-tagged promo 30 days ago that the header set never
   recorded, it can leak into baseline. Mitigated by the loud-fail on
   `final_required_engineered_features` (the missing
   `prior_promo_count > 0` flag forces the row into the
   `cold_start_new_line` evidence class instead of `actionable_forecast`).
2. **Boundary-day rounding**. A promo that runs `Mon → Sun` and the
   next that runs `Sat → Fri` overlapping by 2 days. Currently both
   days are excluded from baseline (correct), but units sold those days
   are NOT double-counted into either promo's uplift. The trainer
   passes through `actual_sales_ex_gst_promo` per the canonical join
   keys; a day belongs to exactly one promo or to baseline.

## Concrete recommendations for the next pass

1. **Add `pre_promo_clean_days_share`** to the engineered feature set,
   exposed in the final model input and surfaced in the model
   environment audit. Operators get a direct readable answer to "how
   much real baseline did this forecast use?".
2. **Add `pre_promo_overlap_days_count`** capturing how many days in the
   56-day window overlap any other promo (rolling-promo contamination
   indicator).
3. **Promote `intermittent_demand_zero_day_share` to a fail-loud
   gate** when `> 0.85` AND `prior_promo_count == 0`: that combination
   should hard-fail to `cold_start_new_line` rather than `low_nonzero`.
4. **Tag the per-promo CSV's `data_quality_flag`** with a new value
   `LOW_BASELINE_COVERAGE` when `pre_promo_clean_days_share < 0.5`.
   Today such rows surface as `REVIEW_FORECAST` with no specific
   reason — the operator can see that something is off but not why.
5. **Materialise the model environment review as a per-run governed
   artifact** (`promotion_model_environment_review.json`) summarising
   per-promotion: clean baseline day count, prior-promo memory anchor
   count, zero-day share, and the resulting evidence class. This
   review document then becomes machine-checkable rather than
   prose-only.

## Status today

- Baseline / live-promo / post-promo separation is enforced by
  `is_in_promotion_window` and tested in
  `tests/unit/test_promotions_feature_engineering.py`.
- Prior-promo memory features and intermittent-cadence features are
  tested for presence in the final scoring frame
  (`tests/unit/test_promotions_prior_promo_memory_features.py`,
  `tests/unit/test_promotions_intermittent_demand_features.py`).
- Required-engineered-feature check on the final model input is wired
  to fail loud
  (`tests/unit/test_promotions_feature_environment_audit.py`).
- The new `pre_promo_clean_days_share` and the
  `LOW_BASELINE_COVERAGE` data-quality flag are pending — see
  recommendations 1 and 4 above.
