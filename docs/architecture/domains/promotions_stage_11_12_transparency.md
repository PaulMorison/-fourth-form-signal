# Promotions Stage 11 / Stage 12 transparency note

This document records the relationship between the Stage 11 store-facing
prediction download and the Stage 12 commercial publication step, so an
operator reading the artifact tree (or the run summary) is never confused
about which file is the authoritative ordering source.

## Stage 11 — store-facing prediction download (always emitted)

Stage 11 runs on every governed operational cycle. For every (`store`,
`promotion`) it writes a self-contained CSV pack into the governed
artifact root:

- `<store>_<promo-start>_<promo-name>.csv` — the **operator** file. It
  projects exactly the current `STORE_FACING_OUTPUT_COLUMNS` contract from
  `store_prediction_download_builder.py` in code-owned order. This file is
  what a store manager opens to decide whether and how much to order.
- `<…>_manager-summary.csv` — one-row commercial roll-up for the same
  promotion (estimated dollars, risk-weighted exposure, recommended-order
  totals, discount summary).
- `<…>_feature-inspection.csv` — full intermediate frame plus upstream
  model `feature_*` columns and decision-score diagnostics. Analysts use
  this to audit *why* a row received its action; operators ignore it.
- A master `promotions_master.csv` joining the operator rows across all
  promotions for a single sort/triage view.

Stage 11 is **deterministic given an as-of-date and a decision-surface
frame**. It does not depend on whether downstream commercial publication
emits a fresh notice in the same cycle.

## Stage 12 — commercial publication (governed NOOP when no fresh candidates)

Stage 12 takes the Stage 11 artifacts and decides whether to *publish* a
fresh commercial notice for downstream subscribers. When every candidate
in the cycle has already been published in a prior cycle, Stage 12 emits
a **governed NOOP** — the run is still complete and successful; it
simply does not republish unchanged content. The cycle log surfaces this
explicitly with the message:

> Commercial cycle completed with governed NOOP because all N candidates
> were already published in prior cycles. No fresh publication
> opportunity.

A NOOP at Stage 12 **does not** invalidate the Stage 11 artifacts. The
operator CSVs remain the authoritative store-facing source for the
cycle, regardless of whether Stage 12 publishes anything new.

`NOOP_ALREADY_PUBLISHED` is reserved for the all-duplicate case. If a
cycle contains both registry duplicates and fresh rows that are validly
non-publishable, such as review-only rows, Stage 12 must not report that
all candidates were already published. The publication summary must keep
the full cycle candidate count separate from the post-registry POS/review
candidate count, expose the duplicate count, and classify the cycle as a
valid no-publishable-rows NOOP when the fresh rows are review-only or
otherwise legitimately excluded.

Downstream freshness, replay-safety, and action-instruction diagnostics
must preserve that same distinction. A mixed duplicate plus review-only
cycle is not duplicate-only replay: duplicate rows are prior-publication
evidence, while the post-registry review-only rows remain the governing
freshness class and replay guidance. Registry duplicate counts must never
be subtracted from post-registry exclusion counts when deriving legitimate
non-publishable row counts.

The governed publishability split must remain row-conserving at the fresh
publication grain. Registry duplicates are their own prior-publication
tier, post-registry review-only rows are the review tier, and residual
policy-excluded rows are only the non-review post-registry exclusions. A
split must not add the full post-registry exclusion count on top of the
same rows already counted as review-only.

For a true all-duplicate NOOP, the full source/candidate count equals the
registry duplicate skip count and the post-registry POS/review candidate
count is zero. Duplicate rows may still carry store-facing review signals
from Stage 11, but those signals are not Stage 12 skip reasons once the
registry duplicate policy has already removed every row from fresh
publication consideration.

## How to verify which file is authoritative

1. Locate the governed run id (printed at the top of the cycle log and
   recorded in `promotions_runtime_governed/manifests/.../manifest.json`).
2. Open the Stage 11 manifest CSV. Each row records the artifact's
   `file_type`. The store-operator file always has `file_type =
   store_promotion`.
3. The Stage 12 publication status is reported separately in the cycle
   summary under `publication_opportunity_message`.

If Stage 11 succeeded but Stage 12 was a NOOP, the per-store CSVs are
still the correct ordering source; nothing more is needed.

## Current operator contract boundaries

The operator CSV is intentionally not the diagnostic grain. It omits
internal grouping and execution fields such as `store_number`,
`promotion_header_key`, buy/watch/do-not-buy flags, raw source price fields,
and model score internals. Those values remain available in the master,
manager-summary, manifest, reconciliation, and feature-inspection artifacts.

The visible store-promotion file must include discount, same-discount and
same-or-better history, discount-response summary, historical-promo response
summary, backtest trust, stockout/cover, overstock/leftover, and data-quality
fields so an operator can challenge high recommended orders without opening
analyst-only diagnostics.

Backtest trust in Stage 11 is currently promotion/run-level evidence derived
from the governed completed-promotion backtest summary. Those fields must be
named explicitly as promotion-level diagnostics (`promotion_backtest_*`) and
must not be emitted under row-level names. The narrative field
`forecast_trust_summary` must also state that the evidence is promotion-level
or model-level, not SKU-level.

Row-level evidence remains separate. `historical_*`,
`historical_promo_response_summary`, and `discount_response_summary` are
store/SKU evidence derived from strict prior completed promotions for that
same store and SKU. Those fields may vary row by row inside one promotion file
even when the `promotion_backtest_*` fields remain constant across the file.

The CSV presentation order is part of that contract. Row-level evidence fields
must appear before the promotion-level trust block so a store operator sees
SKU-specific history before repeated promotion-level diagnostics.

Legacy row-level `backtest_*` names are not allowed. `sku_backtest_*` fields
are also not allowed unless a real Stage 11 owner-path per-SKU backtest
artifact exists and is explicitly wired into the builder.

Promotion-level trust fields may be constant across all SKU rows for one
promotion because the file stays at `store + promotion + sku` grain. That is
allowed only when the fields stay explicitly promotion-level by both naming and
placement: `forecast_trust_*` and `promotion_backtest_*` must remain grouped as
promotion-level diagnostics rather than scattered among row-level history.

When no completed-promotion comparables exist for the promotion-level
backtest summary, Stage 11 must represent absence honestly:

- `promotion_backtest_comparable_event_count = 0`
- `promotion_backtest_mean_absolute_pct_error` is blank
- `promotion_backtest_within_10pct_flag` is blank
- `promotion_backtest_bias_class = NO_COMPARABLE_EVENTS`

Zero-filled no-comparable backtest metrics are misleading because they read as
observed underperformance instead of missing comparable evidence.

Historical response wording is row-level and mutually exclusive:

- `No matching promo history available` only when both same-discount and
  same-or-better event counts are zero.
- `Matching promo history exists but sold 0.0 units on average` when matching
  history exists but the average units are zero.
- `Matching promo history shows ...` when matching history exists and the
  average units are positive.
- Thin or insufficient history must be called out explicitly instead of being
  disguised as missing history.

Stage 11 `data_quality_flag` values must stay precise. Discount-related review
rows must distinguish missing governed discount mapping from a governed-vs-price
discount conflict; Stage 11 must not collapse both causes into one noisy bucket
when the builder can already tell them apart.

The store-facing row contract must expose one clear decision, one readiness
state, and one primary review reason per row:

- `recommended_action` is the commercial decision (`ORDER`, `REVIEW`, `HOLD`,
  `DO_NOT_ORDER`).
- `execution_readiness_status` is execution posture (`READY`,
  `REVIEW_REQUIRED`, `BLOCKED`).
- `primary_review_reason` is the single dominant reason when review is
  required.

Contradictory rows are not allowed in emitted operator CSVs. In particular,
`ORDER` must not coexist with review-only quality flags, `REVIEW` must not
present as quality `OK`, and historical narrative text must agree with numeric
history counts.

For the SQL extraction side of this cycle, Stage 6 inherits the governed
runtime resilience contract in
`promotions_runtime_resilience_and_operator_trust_contract.md`: omitted
connect retry settings resolve to the bounded default retry policy, while
explicit zero remains a visible operator override.
