# Promotions runtime resilience and operator trust contract

## Purpose

This document defines the governed runtime contract for the promotions operational cycle where live SQL extraction, model-input inspection, and store-facing operator outputs meet. It exists to prevent a long cycle from failing on one transient Azure SQL login timeout, prevent model-quality features from becoming invisible, and keep the Stage 11 CSV useful to a store operator without leaking internal implementation fields.

## Inputs

- `PromotionMssqlSettings` is the source of truth for live SQL server, database, schema, tables, driver, authentication mode, connect timeout, connect retry policy, query timeout, encryption, and certificate posture.
- The settings may be provided by CLI flags, `.env` values, process environment values, or governed defaults. Source labels must remain visible through `safe_summary()` and the operational-cycle run context.
- Completed and future extraction both consume the same SQL settings object. Stage 6 must not maintain a parallel retry policy.
- Stage 11 consumes the governed decision-surface frame and may retain internal identifiers only in master, manager-summary, manifest, reconciliation, and feature-inspection artifacts.
- Model-input inspection consumes the exact model input frame written by the training or scoring path.

## Outputs

- SQL extraction telemetry must include `connect_timeout_seconds`, `connect_retry_attempts`, `connect_retry_backoff_seconds`, `connect_attempt_count`, and per-attempt records with classification and outcome.
- Operational-cycle manifests and operator progress logs must expose the resolved SQL retry settings without exposing secrets.
- Stage 11 store-promotion CSVs must project exactly `STORE_FACING_OUTPUT_COLUMNS` in the code-owned order.
- Model-input inspection must write the exact filtered parquet, rounded sample CSV, null profile, constant-column profile, feature list, and metadata JSON.
- Model-input CSV diagnosis export must write full, row-aligned CSVs under the governed promotions `inspection/<run_id>/` tree, including completed/future raw source views, completed/future exact model-feature views, and a column dictionary. The feature CSVs are pre-scale, human-readable views of the exact model input parquet written by training/scoring.
- Model-input quality audit must write governed review artifacts under the promotions artifact tree, including cleaned training/scoring model-input CSVs for operator-selected filters, feature-audit CSV/JSON outputs, a leakage-review CSV, and a human-readable audit summary.

## Data Grain

- Completed and future extraction retain one row per promotion/store/SKU candidate unless a stage-specific artifact explicitly declares a different grain.
- Stage 11 operator CSVs are one row per store, promotion, and SKU. Visible operator files intentionally omit internal grouping keys such as `store_number` and `promotion_header_key`; those keys remain in manifests and diagnostic artifacts.
- Model-input inspection is one row per model row after any explicit inspection filter.
- Model-input CSV diagnosis export preserves the row grain of the source model-input artifacts and may only reduce rows through explicit operator filters such as store, promotion name, promotion header key, or promotion row key.
- Model-input cleanup and audit may remove feature columns from the trained model only when the row grain is preserved and the removal reason is explicit, governed, and written to audit artifacts. Identifiers required for traceability must remain available in metadata or review exports.
- Stage 3 completed-base extraction must fail loud before finalizing parquet when advice-source `sku_number` cannot derive a valid integer `sku_number_key`. Bad source rows must be diagnosed with source context rather than filtered, repaired, or deferred to Stage 4/5.
- Train-ready dataset assembly must treat `sku_number_key` as the governed SKU identity and `sku_number` as a display projection from that key. Raw source text in `sku_number` may be retained only before the train-ready contract boundary; Stage 4 must not persist non-SKU text such as timestamps into the display field when a valid governed key exists.

## Required Schema

- `PromotionMssqlSettings` must carry non-secret connection controls and preserve field-level source labels.
- Store-facing CSVs must include the action block first: priority, SKU, action, order units, discount, forecast, stock position, stockout probability, confidence, capital-at-risk, risk-reward, timing, and model reason. Promotion-level trust/backtest diagnostics must remain in the later promotion-level support block after row-level evidence.
- Store-facing CSVs must include evidence and quality support fields for same-discount history, same-or-better-discount history, discount-response summary, historical-promo response summary, backtest trust, cover, stockout/overstock risk, leftover risk, and data-quality flags.
- Model-input metadata must list engineered feature names, target column names, discount-related feature names, same-discount history feature names, intermittent-demand feature names, high-null warning columns, constant columns, and suspected leakage columns.
- Model-input CSV diagnosis exports must keep traceability identifiers at the front of raw and feature CSVs when present. The column dictionary must include `column_name`, `column_role`, `source_module`, `description`, `nullable_flag`, `example_value`, `whether_used_in_training`, and `whether_used_in_scoring`.
- Model-input preparation must apply governed text normalization, explicit feature/target/metadata/leakage separation, duplicate-content feature removal, duplicate-name detection, constant-feature removal, and mixed-type numeric-key validation before the final training/scoring frame is handed to the model.
- The engineered feature allowlist must be deliberate: registered `feature_*` outputs plus the code-owned raw numeric and categorical model-input allowlists. Leakage-risk, audit-only, and downstream decision columns must never reach training features by accident.
- Probability-style and uncertainty-style demand features must be derived from real comparable-history evidence already available at the promotions feature boundary. When comparable evidence is missing, probability fields must remain missing or be explicitly flagged as low-evidence rather than backfilled with fabricated certainty.
- The governed promotions probability layer lives under `src/state/promotions/feature_engineering/demand/probability/` and must remain modular across `ft_probability_poisson_features.py`, `ft_probability_negative_binomial_features.py`, `ft_probability_bayesian_poisson_features.py`, `ft_probability_zero_inflated_features.py`, `ft_probability_hypothesis_test_features.py`, `ft_probability_companion_features.py`, and `ft_probability_overallocation_summary.py`. Poisson is only for stable low-volume demand, Negative Binomial is only for materially over-dispersed lumpy demand, Bayesian Poisson is for sparse evidence that should shrink toward an explainable prior plus recent evidence, Zero Inflated is only for genuinely zero-heavy history, the hypothesis-test layer turns lift evidence into effect-size-plus-stability diagnostics, the companion layer captures basket dependence, and the summary layer collapses those review surfaces into the smaller model-use contract.
- The governed basket and mission context layer lives under `src/state/promotions/feature_engineering/demand/ft_basket_context_feature_bundle.py` plus the supporting `ft_basket_context_features.py`, `ft_companion_item_features.py`, `ft_transaction_mission_features.py`, `ft_stock_constrained_demand_features.py`, and `ft_basket_probability_features.py` modules. It must derive only from strictly prior completed same-store same-SKU history plus the completed transaction-aggregate seam; it must not fabricate companion-category, buyer-level, or direct inventory-history features when those sources are absent.
- The final model-input boundary must split probability outputs into model-use versus review-only columns. The model-use subset is the summary layer plus the stability/repeatability signals: consensus expected units, consensus zero-sale risk, consensus tail risk, overallocation risk, demand-confidence, model-use flag, units-lift stability, and same-discount repeatability. Low-level model-specific expected units, priors/posteriors, dispersion or zero-inflation detail, p-values, and companion-detail diagnostics may remain in engineered and audit surfaces, but they must not silently enter the trained schema unless a later governed review explicitly promotes them.
- Promotions probability features must use the same leakage-safe comparable-history boundary as prior-promo memory: same store, same SKU, strictly completed prior promotions only, with no cross-store or cross-SKU pooling unless a separate governed contract explicitly permits it.
- Blank probability outputs mean the corresponding distributional assumption was not supported by the available comparable history. Blank does not mean zero risk or zero demand. Raw p-values alone are not sufficient evidence; they must travel with sample size, effect size, confidence-interval width, and bounded stability/repeatability signals so the model and the reviewer can distinguish weak evidence from meaningful signal.
- Basket-context model-use features must keep their evidence and missingness surfaces visible at the final model-input seam. Bounded basket rates and basket-probability fields must stay on 0..1, while basket history counts remain explicit numeric evidence rather than being collapsed into hidden internal state. Basket dependence matters directly for over-allocation risk because a SKU that usually sells inside larger baskets or with concentrated companions can underperform sharply when those basket conditions are absent, even when simple same-SKU promo history looks adequate.
- Allocation-discipline features must compare the current allocation basis only to model-use probability summary evidence, not to low-level review-only distribution parameters or realised promotion outcomes. Probability-backed allocation excess units, excess percentage, sell-through percentage, and excess capital-at-risk must remain one row per promotion/store/SKU and must remain blank when probability model-use evidence is not available.
- Allocation-aware units forecast calibration may only cap a raw units prediction downward when probability model-use evidence is available and allocation discipline is material. The cap must use probability expected units expanded by tail risk and low-confidence slack, and it must never increase a forecast or depend on realised promo outcomes.
- Training metrics must include decision-quality allocation outcomes, not only generic model scores. The governed model family must write validation/test excess-unit MAE, excess-capital-at-risk MAE, over-allocation false-positive cost proxy, over-allocation false-negative excess-capital proxy, and probability calibration-band summaries alongside the existing classifier and regressor metrics.

### Stage 11 operator CSV schema contract

- Purpose: one operator-actionable row per `store + promotion + sku` with no mixed-grain ambiguity.
- Inputs: Stage 8 decision-surface row outputs plus governed completed-promotion backtest summary and per-row forecast diagnostics.
- Output: per-store and per-store-promotion CSVs projected from `STORE_FACING_OUTPUT_COLUMNS` in code-owned order.
- Row-level historical evidence and promotion-level backtest evidence are both visible in the same row, but they must remain explicitly scoped and must never be presented under interchangeable names.
- Row-level evidence fields must reflect row-level SKU evidence and must appear before the promotion-level trust/backtest block in the exported CSV.
- Promotion-level backtest diagnostics may repeat across rows because the file grain stays `store + promotion + sku`, but their wording and placement must keep them clearly promotion-level rather than SKU-specific judgment.
- Required operator decision block fields:
	- `recommended_action`
	- `execution_readiness_status`
	- `primary_review_reason`
	- `recommended_order_units`
	- `projected_promotional_units`
	- `projected_stock_gap_units`
	- `stockout_probability_percent`
	- `model_confidence_percent`
- Required operator support fields:
	- `discount_percent`
	- `historical_promo_events_same_discount`
	- `historical_units_same_discount_avg`
	- `historical_promo_events_same_or_better_discount`
	- `historical_units_same_or_better_discount_avg`
	- `discount_response_summary`
	- `historical_promo_response_summary`
	- `promotion_backtest_comparable_event_count`
	- `promotion_backtest_within_10pct_flag`
	- `promotion_backtest_mean_absolute_pct_error`
	- `promotion_backtest_bias_class`
	- `forecast_trust_band`
	- `forecast_trust_summary`
	- `model_reason_summary`

### Stage 11 grain rules

- Historical discount response counts and averages are row-level (`store + promotion + sku`).
- `historical_promo_response_summary` and `discount_response_summary` are row-level narratives and must be derived from the same row-level numeric history fields they describe.
- Completed-promotion backtest trust evidence is promotion/run-level in Stage 11 and must use explicit names prefixed with `promotion_backtest_`.
- `forecast_trust_summary` is a promotion/run-level narrative derived from the completed-promotion backtest summary and must say that scope explicitly rather than implying SKU-level backtest evidence.
- Promotion-level trust and backtest diagnostics must be grouped after row-level evidence in the CSV presentation so repeated values do not visually read as per-SKU verdicts.
- Promotion/run-level evidence must never be emitted under row-level names such as `backtest_*`.
- If true row-level backtest evidence is not available, the runtime must not synthesize, emit, or imply `sku_backtest_*` fields.
- When no completed-promotion comparables exist, `promotion_backtest_comparable_event_count` must be `0`, `promotion_backtest_mean_absolute_pct_error` must be blank, `promotion_backtest_within_10pct_flag` must be blank, and `promotion_backtest_bias_class` must be `NO_COMPARABLE_EVENTS`.
- Zero-filled promotion-level backtest error or threshold fields are invalid when comparable count is zero because they read as measured failure rather than absence of evidence.

## Business Rules

- Omitted SQL connect retry settings are not valid evidence of an intentional no-retry policy. The governed default is two retry attempts with a five-second backoff, producing at most three connect/login attempts per SQL operation.
- Explicit CLI or environment values override the governed defaults. An explicit zero retry count is allowed only as a deliberate operator override and must remain visible in source labels and telemetry.
- Only transient login/connect timeout and transient connectivity classifications may be retried. Authentication failures, driver/config failures, and unknown failures remain terminal and fail loud.
- Query execution timeout is separate from connect/login timeout. Query execution failures must not be retried by the connect retry loop.
- Stage 6 future extraction must use the shared SQL executor and shared settings; no Stage 6-specific retry shim or fallback pipeline is permitted.
- Live-proof completed-extraction fallback may narrow completed scope with bounded diagnostic query options after a full-scope preflight rejection. When the narrowed fallback is not `live_sql`, the runtime must keep using the shared SQL executor and resolved settings but must bypass completed landed-batch slicing, because landed completed batching owns only `live_sql` batch windows.
- `proof_slice` completed fallback must remain bounded while preserving enough completed promotion start-date diversity for the existing time-aware training split. It must not be a plain top-N alias when live ordering clusters thousands of rows under one promotion date.
- The store-facing discount value must represent the governed discount when available and a price-derived fallback when the governed mapping is missing or zero. Fallback rows must carry a review data-quality flag rather than silently showing a false zero discount.
- Operator-visible forecasts must be accompanied by confidence, backtest, discount-history, and stockout/cover context so high recommended orders are reviewable.
- Action and readiness semantics are separate and must not conflict:
	- `recommended_action=ORDER` implies `execution_readiness_status=READY`.
	- `recommended_action=REVIEW` implies `execution_readiness_status=REVIEW_REQUIRED`.
	- `recommended_action=HOLD` or `DO_NOT_ORDER` implies `execution_readiness_status=BLOCKED`.
- Historical narrative must be numerically consistent:
	- positive `historical_promo_events_same_discount` cannot produce a no-history narrative.
	- zero same-discount plus positive same-or-better events must produce a broader-history narrative.
	- `historical_promo_response_summary="No matching promo history available"` is valid only when both history event counts are zero.
	- positive history counts with average units equal to zero must be surfaced as zero-sales history, not as missing history.
	- rows marked with thin or insufficient history must surface that caution explicitly in the narrative rather than collapsing back to missing-history wording.
- `primary_review_reason` is a single dominant operator-readable reason; longer narrative remains optional support only.
- Review-quality flags must encode precise causes. Discount-review rows must distinguish missing governed discount mapping from governed-vs-price discount conflict; a broad catch-all discount-review flag is not sufficient.

## Configuration Source of Truth

- Runtime defaults live in `src/runtime/promotions/config.py` beside the environment and CLI source maps.
- SQL execution behavior lives in `src/data/promotions/mssql_query_executor.py`.
- Operational-cycle orchestration lives in `src/runtime/promotions/run_promotions_operational_cycle.py` and must only pass through the resolved settings.
- Store-facing output ownership lives in `src/surfaces/promotions/reporting/store_prediction_download_builder.py`.
- Model-input inspection ownership lives in `src/state/promotions/datasets/model_input_export.py`, `src/runtime/promotions/inspect_promotions_model_input.py`, and `src/runtime/promotions/export_promotions_model_inputs.py`.

## Failure Conditions

- Missing required SQL server, database, or source-table settings fail before extraction.
- Negative retry attempts or negative retry backoff fail configuration validation.
- Exhausted transient connect/login attempts fail with classified telemetry and per-attempt records.
- Authentication and configuration failures are terminal after one attempt even when retries are configured.
- Store-facing schema drift fails tests that compare emitted columns to `STORE_FACING_OUTPUT_COLUMNS`.
- Store-facing export fails loud on operator-contradiction or mixed-grain defects, including:
	- no-history narrative with positive history counts
	- `REVIEW` with `data_quality_flag=OK`
	- `ORDER` with `data_quality_flag` in `REVIEW_*` or `COLLAPSED_FORECAST`
	- invalid action/readiness pair
	- duplicate row grain within a per-store-promotion CSV
	- promotion-level trust summary wording that stops stating promotion-level scope explicitly
	- row-level naming of promotion/run-level backtest evidence
- Missing model-input inspection filter columns fail loud.
- Model-input CSV diagnosis export fails loud when required source artifacts are missing, when raw/source and exact feature row counts do not align, or when an export target already exists without an explicit overwrite request.
- Final model contract validation fails on duplicate columns, target leakage, raw advice leakage, all-null columns, unexpected object dtypes, infinities, or missing required governed engineered features.
- Stage 3 completed-base extraction fails before parquet finalization when advice-source SKU identity is broken: missing `sku_number`/`sku_number_key`, null derived keys, non-numeric keys, non-finite keys, or fractional keys. The failure must identify the advice source table and representative raw rows; it must not drop or coerce the rows silently.
- Governed numeric identity is carried by the `*_key` fields used for joins and model context. `sku_number_key` and `store_number_key` must be integer numeric identities when present and must not contain null, blank, non-numeric, non-finite, or fractional values in train-ready datasets. Decimal-like whole-number strings such as `12345.0` are valid only because they resolve exactly to an integer identity. Display fields such as `sku_number` and `promotional_sku_id` may remain text for traceability and presentation; they must not be treated as strict numeric model keys.
- Stage 4 must derive the train-ready `sku_number` display value from valid `sku_number_key` rather than trusting raw source `sku_number`. If the key cannot produce a valid integer display value, the dataset must fail loud on the governed key defect instead of preserving or promoting dirty display text.
- Mixed-type governed numeric key fields such as `sku_number_key`, `store_number_key`, and `inferred_supplier_number` must fail loud before model-input training/scoring proceeds. Invalid display-only identifiers must not be silently promoted into governed numeric identity.

## Logging Expectations

- Operator progress must show resolved SQL retry settings at run start and on SQL connect failures.
- Failure summaries must include current SQL subphase, retry attempts, backoff, connect attempt count, and Stage 6 plan/guardrail paths when the failure occurs in Stage 6.
- Model-input inspection metadata must make feature-group presence inspectable without opening the full parquet.
- Documentation and reports must describe the current operator CSV contract without stale column counts.

## Test Expectations

- Environment/config tests must verify governed retry defaults, explicit zero overrides, and env/CLI override preservation.
- MSSQL executor tests must verify transient retry success/exhaustion, no retry for auth/config/unknown failures, and no connect retry on query timeout.
- Operational-cycle tests must verify manifests and progress retain resolved retry settings.
- Store download tests must verify exact operator column order and absence of internal diagnostic columns.
- Model-input inspection tests must verify metadata feature groups, high-null warnings, constant columns, suspected leakage visibility, full CSV diagnosis outputs, row-count preservation, identifier presence, exact model-feature export, dictionary coherence, promotion filtering, and completed/future separation.
- Model-input quality tests must verify duplicate-content feature removal, constant-feature removal, mixed-type numeric-key detection, leakage classification, feature/target/metadata separation, evidence-driven probability features, and governed audit/export artifact writing for a selected promotion/store slice.

## Extension Points

- New SQL retry classifications may be added only in the connection classifier with tests proving retry or terminal behavior.
- New operator fields must be added through `STORE_FACING_OUTPUT_COLUMNS`, tests, and this contract's schema description.
- New governed feature groups must be added to model-input metadata through explicit name selection rules and tests.
- New model-input cleanup or removal rules must update the governed audit outputs and the operator-readable summary so removed columns and reasons stay inspectable.
- Any retry policy change must update this document before code changes and must preserve explicit override visibility.