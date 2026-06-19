# Promotions Runtime

The promotions runtime remains split by owned layer and entrypoint:

- `python -m runtime.promotions.run_promotions_operator smoke --run-id <run_id> --as-of-date YYYY-MM-DD --artifact-root <governed_root> [--local-inspection-root <local_root>] [--mode smoke_synthetic|smoke_patched_extraction]`
- `python -m runtime.promotions.run_promotions_operator live --run-id <run_id> --as-of-date YYYY-MM-DD --artifact-root <governed_root> [--local-inspection-root <local_root>] [--query-timeout-seconds N] [--enable-landed-batches true|false] [--batch-row-count N] [--enable-chunked-fetch true|false] [--chunk-row-count N] [--resume-completed-partitions true|false] [--stage-temp-chunk-files true|false] [--partition-strategy store_number|supplier_number|store_sku_hash_bucket|promotion_name_hash_bucket|promotion_row_key_hash_bucket --partition-count N] [--run-preflight] [--planner-only]`
- `python -m runtime.promotions.run_promotions_operator inspect --run-id <run_id> --as-of-date YYYY-MM-DD --artifact-root <governed_root> [--mode live_sql|diagnostic_topn] [--query-timeout-seconds N] [--enable-landed-batches true|false] [--batch-row-count N] [--enable-chunked-fetch true|false] [--chunk-row-count N] [--resume-completed-partitions true|false] [--stage-temp-chunk-files true|false] [--planner-only] [--run-preflight] [--run-row-count-probe] [--run-extraction] [--test-connection] [--save-rendered-sql] [--partition-strategy ... --partition-count N --partition-index I]`
- `python -m runtime.promotions.print_promotions_run_artifacts --run-id <run_id> --artifact-root <governed_root>`
- `python -m runtime.promotions.promotions_pipeline_runner --mode extract_only`
- `python -m runtime.promotions.promotions_pipeline_runner --mode build_dataset`
- `python -m runtime.promotions.train_models`
- `python -m runtime.promotions.score_promotions --model-run-id <train_run_id>`
- `python -m runtime.promotions.backtest_promotion_cohorts --dataset-run-id <train_run_id>`
- `python -m runtime.promotions.run_promotions_decision_surface --dataset-run-id <train_run_id> --model-run-id <train_run_id>`
- `python -m runtime.promotions.run_promotions_policy_slice_replay --current-csv-path <current_code_replay.csv> --baseline-csv-path <baseline_governed.csv> --output-root <review_output_dir> --replay-mode future_stage12`
- `python -m runtime.promotions.run_promotions_operational_cycle --run-id <run_id> --as-of-date YYYY-MM-DD [--enable-landed-batches true|false] [--batch-row-count N] [--enable-chunked-fetch true|false] [--chunk-row-count N] [--resume-completed-partitions true|false] [--stage-temp-chunk-files true|false] [--partition-strategy store_number|supplier_number|store_sku_hash_bucket|promotion_name_hash_bucket|promotion_row_key_hash_bucket --partition-count N] [--run-preflight] [--max-candidate-promotion-rows N] [--max-candidate-store-sku N] [--max-window-span-days-total N] [--max-window-span-days-max N] [--planner-only]`
- `python -m runtime.promotions.inspect_promotions_sql_extraction --selection-mode completed --as-of-date YYYY-MM-DD [--test-connection] [--save-rendered-sql] [--run-row-count-probe] [--run-preflight] [--planner-only] [--run-extraction] [--extraction-mode live_sql|diagnostic_topn] [--limit-promotions N] [--promotion-name-like TEXT] [--store-number N] [--supplier-number N] [--enable-landed-batches true|false] [--batch-row-count N] [--enable-chunked-fetch true|false] [--chunk-row-count N] [--resume-completed-partitions true|false] [--stage-temp-chunk-files true|false] [--partition-strategy store_number|supplier_number|store_sku_hash_bucket|promotion_name_hash_bucket|promotion_row_key_hash_bucket --partition-count N --partition-index I] [--max-candidate-promotion-rows N] [--max-candidate-store-sku N] [--max-window-span-days-total N] [--max-window-span-days-max N]`
- `python -m runtime.promotions.run_promotions_system_smoke --run-id <run_id> --mode smoke_synthetic --as-of-date YYYY-MM-DD`
- `python -m runtime.promotions.audit_promotions_operational_cycle --run-id <run_id>`

All completed-extraction entrypoints also accept `--completed-sales-history-start-date YYYY-MM-DD`. The governed default is `2024-01-01`, because there are no valid promotion advice rows before that date.

## Operator Runbook

Smoke observation run:

```bash
python -m runtime.promotions.run_promotions_operator smoke \
	--run-id promotions-operator-smoke-YYYYMMDDTHHMMSSZ \
	--as-of-date YYYY-MM-DD \
	--artifact-root /absolute/governed/promotions_root \
	--local-inspection-root /absolute/local/promotions_review \
	--mode smoke_synthetic
```

Live observation run:

```bash
python -m runtime.promotions.run_promotions_operator live \
	--run-id promotions-operator-live-YYYYMMDDTHHMMSSZ \
	--as-of-date YYYY-MM-DD \
	--artifact-root /absolute/governed/promotions_root \
	--local-inspection-root /absolute/local/promotions_review \
	--query-timeout-seconds 60 \
	--enable-landed-batches true \
	--batch-row-count 1000 \
	--enable-chunked-fetch true \
	--chunk-row-count 5000 \
	--resume-completed-partitions true \
	--stage-temp-chunk-files true \
	--auto-repartition-completed true \
	--max-completed-repartition-attempts 3 \
	--max-completed-partition-count 512 \
	--partition-strategy promotion_row_key_hash_bucket \
	--partition-count 16
```

Planner or SQL inspector run:

```bash
python -m runtime.promotions.run_promotions_operator inspect \
	--run-id promotions-operator-inspect-YYYYMMDDTHHMMSSZ \
	--as-of-date YYYY-MM-DD \
	--artifact-root /absolute/governed/promotions_root \
	--planner-only
```

```bash
python -m runtime.promotions.run_promotions_operator inspect \
	--run-id promotions-operator-inspect-YYYYMMDDTHHMMSSZ \
	--as-of-date YYYY-MM-DD \
	--artifact-root /absolute/governed/promotions_root \
	--run-row-count-probe \
	--save-rendered-sql \
	--mode diagnostic_topn \
	--limit-promotions 25
```

Latest artifact lookup after a run:

```bash
python -m runtime.promotions.print_promotions_run_artifacts \
	--run-id promotions-operator-live-YYYYMMDDTHHMMSSZ \
	--artifact-root /absolute/governed/promotions_root
```

Diagnostics-only policy slice replay:

```bash
python -m runtime.promotions.run_promotions_policy_slice_replay \
	--current-csv-path /absolute/current_code_replay.csv \
	--baseline-csv-path /absolute/baseline_governed.csv \
	--output-root /absolute/local/promotions_policy_replay \
	--run-id promotions-policy-replay-YYYYMMDDTHHMMSSZ \
	--replay-mode future_stage12
```

This runner compares persisted governed baseline artifacts with current-code replay artifacts without rerunning extraction or training. It writes analyst evidence only: summary JSON, action delta CSV, Stage 12 publishability delta CSV, policy-reason delta CSV, review-only delta CSV, row deltas, and a runtime manifest. It does not create a publish tree or change the store-facing commercial CSV.

Buy/order widening is based on governed action classes only: any replay row becomes BUY/ORDER when its governed baseline row was not BUY/ORDER, or the current slice has a net increase in BUY/ORDER rows. Positive quantities or technical forecasts do not create BUY/ORDER widening. A long extraction/training rerun should be preceded by this replay when policy allocation logic changes, because it proves whether capital and units were removed without expanding BUY/ORDER decisions, review-only rows, or Stage 12 publishability unexpectedly.

Good behavior looks like this:

- The terminal prints `START STAGE N/12`, stage details, periodic `HEARTBEAT STAGE N/12` lines, and `FINISH STAGE N/12` with elapsed seconds.
- Stage 3 and stage 6 heartbeat subphases move through SQL render, connect, execute, fetch, and write phases instead of repeating one stagnant message forever.
- Stage 3 now prints the active completed partition strategy/count, the current repartition attempt number, and any accepted or rejected automatic repartition decision before continuing or failing.
- Stage 3 startup also prints the resolved completed-extraction landed-batch and chunk settings. Landed-batch runs log batch reuse and rebuild messages so operators can see when the runtime resumed from the first incomplete batch, rebuilt one corrupt batch, or skipped a fully finalized parent partition.
- Completed stages print row counts when known plus explicit output paths.
- Stage 12 prints the final governed manifest, operator summary JSON/CSV, store download CSV, decision surface CSV, inspection review packet CSV, and audit summary JSON/CSV paths.
- Failed runs after NAS bootstrap still print a `FINAL OUTPUTS` block and persist `manifests/<run_id>/operational_cycle_manifest.json` plus the operator summary/log artifacts so the run can be inspected without rerunning immediately.

A SQL timeout looks like this:

- The terminal prints one `FAILED STAGE` block with the exact stage, exact subphase, exception type, short reason, telemetry path, diagnostics path, operator log path, and manifest root.
- When completed-promotions preflight recommends a larger partitioning, the runtime retries automatically within the governed limits instead of stopping on the first rejection, and writes `completed_partition_retries.json` plus `completed_partition_retries.csv` for that history.
- For live extraction failures, the block also includes rendered SQL paths and a ready-to-rerun inspector suggestion.
- The governed run folder still contains `operator_run_summary.json`, `operator_run_summary.csv`, `operator_stage_timings.csv`, and `operational_cycle_manifest.json` so the failure can be reviewed without rerunning immediately.
- Failures before stage 1 surface a `FATAL OPERATOR CLI ERROR` block that includes the reconstructed command received so the operator can rerun the same command exactly.

Inspect outputs here:

- Governed run manifest: `manifests/<run_id>/operational_cycle_manifest.json`
- Operator summaries: `manifests/<run_id>/operator_run_summary.json` and `manifests/<run_id>/operator_run_summary.csv`
- Completed repartition history: `manifests/<run_id>/completed_partition_retries.json` and `logs/<run_id>/completed_partition_retries.csv`
- Operator log and stage timings: `logs/<run_id>/operator_run.log` and `logs/<run_id>/operator_stage_timings.csv`
- Store-facing output: `prediction/store_downloads/<run_id>/store_prediction_download_<as_of_date>.csv`
- Decision surface CSV: `artefacts/decision_surface/<decision_surface_run_id>/promotion_decision_surface.csv`
- Inspection review packet CSV: `inspection/<decision_surface_run_id>/inspection_promotion_review_packet.csv`
- Audit summaries: `audit/operational_cycles/<run_id>/operational_cycle_run_summary.json` and `audit/operational_cycles/<run_id>/operational_cycle_run_summary.csv`
- Fast local review pack: `<local_inspection_root>/<run_id>/`

The operational-cycle runner composes the existing extract, dataset, training, scoring, and decision-surface layers without moving their ownership. It now uses the completed training artifact for historical cohort context, the future scored rows for live decision-surface outputs, and writes a top-level manifest at `manifests/<run_id>/operational_cycle_manifest.json` that links extraction, dataset, model, technical prediction artifacts, decision-surface artifacts, the store download, audit outputs, and operator traces produced by that cycle.

Governed NAS root layout:

- `cleaned_data/`
- `training/`
- `training/datasets/`
- `training/models/`
- `prediction/`
- `prediction/scoring/`
- `prediction/store_downloads/`
- `artefacts/`
- `artefacts/decision_surface/`
- `artefacts/cohorts/`
- `artefacts/reports/`
- `logs/`
- `manifests/`
- `inspection/`
- `audit/`
- `audit/operational_cycles/`

These module entrypoints assume the repo has been installed into the active environment, for example with `python -m pip install -e .` from the repository root. Using `PYTHONPATH=src` is not supported in this repo because the `src/platform` package can shadow Python's standard-library `platform` module.

Primary environment contract:

- `PROMOTIONS_MSSQL_SERVER`
- `PROMOTIONS_MSSQL_DATABASE`
- `PROMOTIONS_MSSQL_USERNAME`
- `PROMOTIONS_MSSQL_PASSWORD`
- `PROMOTIONS_MSSQL_DRIVER`
- `PROMOTIONS_MSSQL_QUERY_TIMEOUT_SECONDS`
- `PROMOTIONS_MSSQL_ENCRYPT`
- `PROMOTIONS_MSSQL_TRUST_SERVER_CERTIFICATE`
- `PROMOTIONS_SCHEMA`
- `PROMOTIONS_ADVICE_TABLE`
- `PROMOTIONS_PWLOGD_TABLE`
- `PROMOTIONS_NAS_ROOT`
- `PROMOTIONS_LOCAL_INSPECTION_ROOT`
- `PROMOTIONS_ENABLE_LOCAL_INSPECTION_COPY`
- `PROMOTIONS_COMPLETED_ENABLE_LANDED_BATCHES`
- `PROMOTIONS_COMPLETED_BATCH_ROW_COUNT`
- `PROMOTIONS_COMPLETED_ENABLE_CHUNKED_FETCH`
- `PROMOTIONS_COMPLETED_CHUNK_ROW_COUNT`
- `PROMOTIONS_COMPLETED_RESUME_COMPLETED_PARTITIONS`
- `PROMOTIONS_COMPLETED_STAGE_TEMP_CHUNK_FILES`
- `PROMOTIONS_COMPLETED_SALES_HISTORY_START_DATE`

`PROMOTIONS_SQL_*` environment names are still accepted for compatibility by `runtime.promotions.config`, and `PROMOTIONS_ARTIFACT_ROOT` remains a compatibility alias for `PROMOTIONS_NAS_ROOT`, but new runs should use the `PROMOTIONS_MSSQL_*` names plus `PROMOTIONS_NAS_ROOT`.

`PROMOTIONS_NAS_ROOT` must resolve to an absolute governed path outside the repository root. The operational cycle and the smoke entrypoint both fail at the NAS bootstrap stage if the configured root resolves inside the repo.

Live-run failure behavior:

- Missing required env values fail early in `runtime.promotions.config` before any SQL execution.
- MSSQL connection failures are surfaced from `data.promotions.mssql_query_executor` with an explicit connection, authentication, driver, or network message.
- Live SQL schema or table mismatches are surfaced with an explicit query-compatibility message covering `PROMOTIONS_SCHEMA`, `PROMOTIONS_ADVICE_TABLE`, and `PROMOTIONS_PWLOGD_TABLE`.
- Stage 3 and stage 6 failures now include the current extraction subphase plus direct links to `extraction_telemetry.json`, `extraction_telemetry.csv`, `sql_diagnostics_summary.json`, `sql_diagnostics_summary.txt`, `rendered_sql.sql`, and `rendered_sql_parameters.json` when those artifacts were written.
- Timeout failures also echo the applied timeout seconds, the selection mode, and a ready-to-rerun inspector command for a bounded diagnostic retry.
- Partitioned completed-extraction failures also surface the failed partition index, the configured partition strategy and count, and the current `completed_partition_summary.json` path so the operator can distinguish one bad child partition from a whole-run failure.
- Stage 3 can now fail before heavy SQL execution when the completed preflight planner returns `TOO_WIDE_REPARTITION_REQUIRED` or `INVALID_PARTITION_KEY`. Those failures surface the planner verdict, reason, recommended partition strategy/count when available, and direct links to `extraction_preflight_summary.json`, `extraction_preflight_summary.csv`, `rendered_preflight_sql.sql`, and `rendered_preflight_sql_parameters.json`.

Operational notes:

- The training dataset and model bundle use the primary `run_id`.
- Future extraction and scoring default to `<run_id>-score` unless `--score-run-id` is supplied.
- Decision-surface outputs default to `<run_id>-decision-surface` unless `--decision-surface-run-id` is supplied.
- The operational cycle and smoke entrypoint accept `--local-inspection-root` and `--disable-local-inspection-copy` so operators can keep NAS as system-of-record while also writing one easy local review copy under `tmp/promotions_local_inspection/` by default.
- The operational cycle and smoke entrypoint both bootstrap the governed NAS structure first and persist `nas_bootstrap_summary.json` under `manifests/<run_id>/`.
- The operational cycle prints a clean 12-stage operator trace to stdout with `START STAGE`, `HEARTBEAT STAGE`, `FINISH STAGE`, and `FAILED STAGE` markers, and persists `operator_run.log`, `operator_run_summary.json`, `operator_run_summary.csv`, and `operator_stage_timings.csv` for every run under `logs/` and `manifests/`.
- During live SQL extraction, the stage-3 and stage-6 heartbeats distinguish `SQL query render in progress`, `SQL connecting`, `SQL executing`, `SQL fetch in progress`, and `writing extracted parquet and manifest` so operators can tell whether latency is upstream in SQL Server or downstream in artifact persistence.
- Each extraction run now persists governed SQL observability artifacts alongside the parquet and manifest: `manifests/<run_id>/rendered_sql.sql`, `manifests/<run_id>/rendered_sql_parameters.json`, `manifests/<run_id>/extraction_telemetry.json`, `logs/<run_id>/extraction_telemetry.csv`, `manifests/<run_id>/sql_diagnostics_summary.json`, and `logs/<run_id>/sql_diagnostics_summary.txt`.
- The completed extractor now also persists transaction-scope preflight planner artifacts: `manifests/<run_id>/rendered_preflight_sql.sql`, `manifests/<run_id>/rendered_preflight_sql_parameters.json`, `manifests/<run_id>/extraction_preflight_summary.json`, and `logs/<run_id>/extraction_preflight_summary.csv`.
- Extraction telemetry and SQL diagnostics now also record the extraction mode, diagnostic filter summary, candidate promotion row count, estimated sales-window summary, partition strategy/count/index when applicable, and the rendered SQL artifact paths used for that run.
- The completed preflight planner measures the same candidate store/SKU/date window scope that drives `promotion_base_v4` rather than relying on detached heuristics. Its current hard-stop metrics are candidate promotion rows, candidate store/SKU pairs, total candidate window span days, and max candidate window span days.
- Planner verdicts are explicit: `SAFE_TO_EXTRACT` means the observed completed-scope metrics stayed within the configured thresholds, `TOO_WIDE_REPARTITION_REQUIRED` means at least one threshold was exceeded and the planner is recommending a new partition strategy/count, and `INVALID_PARTITION_KEY` means the chosen partition key does not exist in the live advice projection.
- The completed-promotions SQL is now rendered as `promotion_base_v4`. The completed path narrows `PwlogD` by candidate store/SKU/date windows before the heavier aggregations and pre-aggregates transactions before live transaction counting, which keeps the optimization inside the governing SQL/extraction seam instead of adding a parallel pipeline.
- `store_sku_hash_bucket` is the transaction-scope strategy. It hashes the same store and sku keys that drive `candidate_store_sku_windows` and the `PwlogD` join, which is the most direct way to reduce overlapping transaction scope across child partitions.
- `promotion_row_key_hash_bucket` is the promotion-grain hash strategy. It buckets the same store, sku, promotion window, promotional_sku_id, and promotion_name identity that the extraction later uses to build `promotion_row_key`, which avoids the severe live skew seen with single-column bucketing on the current advice set.
- When `--partition-strategy` and `--partition-count` are supplied to `run_promotions_operational_cycle`, stage 3 stays inside the same extraction seam but loops across governed child partitions, writes one child parquet+manifest set per partition under deterministic child run ids, combines those child frames back into the parent `cleaned_data/extracted/<run_id>/promotion_base.parquet`, and keeps the downstream dataset, training, scoring, decision-surface, and audit path unchanged.
- When completed landed batching is enabled, each full-scope or partitioned completed extraction is split into deterministic child batch run ids. Each batch now lands a lightweight completed base stage first, then separate completed window and transaction aggregate stages, and only then assembles the finalized batch parquet and manifest under the normal governed run folders.
- Landed completed batches are scoped by stable row-number windows over the `advice_source` set. That keeps each SQL session bounded to one shorter stage query per batch instead of one long-lived monolithic completed cursor.
- All completed `PwlogD` reads inside the staged path apply the governed lower bound `Calendar_Date >= completed_sales_history_start_date`. The default is `2024-01-01`, but operators can override it explicitly through the CLI or `PROMOTIONS_COMPLETED_SALES_HISTORY_START_DATE`.
- When completed chunking is enabled inside the landed-batch path, each child batch still fetches SQL rows with bounded `fetchmany` batches, persists chunk progress under `manifests/<child_batch_run_id>/extraction_partition_progress.json`, and only becomes reusable after `manifests/<child_batch_run_id>/extraction_partition_completion.json` is written alongside the finalized parquet and manifest.
- Partitioned stage 3 writes `manifests/<run_id>/completed_partition_summary.json` as the operator-facing ledger for the whole completed set. That summary records the configured strategy/count, per-partition candidate and extracted row counts, success or failure status, phase timings when present, and links to the child parquet, manifest, rendered SQL, telemetry, and diagnostics artifacts.
- Each partition summary row now also records the preflight verdict, preflight reason, recommended partition strategy/count, candidate store/SKU and window-span metrics, child preflight artifact paths, fetch mode, chunk mode, batch counts, chunk counts, cumulative rows written, total landed rows, completion state, partition completion state, resume state, and whether that child was skipped because a trustworthy finalized completion marker already existed.
- Resume semantics are explicit and fail closed: a finalized parent partition is reused only when the parent parquet, parent manifest, parent completion marker, and every expected finalized child batch marker still exist; an incomplete partition resumes from the first incomplete batch instead of restarting from zero; and one corrupt or incomplete batch is discarded and rebuilt without deleting the other finalized batch artifacts.
- The combined parent completed manifest now preserves child lineage through `child_partition_manifest_paths` plus the partition strategy/count metadata, so the full completed-set artifact remains first-class rather than an implicit merge.
- The landed parent completed manifest also preserves `fetch_mode`, `chunk_mode`, `batch_count`, `finalized_batch_count`, `resumed_batch_count`, `rebuilt_batch_count`, `total_landed_rows`, `completion_state`, `child_batch_manifest_paths`, `child_batch_parquet_paths`, `completed_sales_history_start_date`, and staged child-stage lineage, and stage 4 reads the finalized parent parquet from disk before dataset assembly so no downstream stage depends on a live completed-extraction cursor or in-memory extraction frame.
- The full operational cycle intentionally rejects `--partition-index`; a single child partition is not allowed to masquerade as a full completed-set run. Use the inspector for single-partition retries and diagnostics.
- `--planner-only` on `run_promotions_operational_cycle` delegates to the inspector for one completed preflight probe and exits before the 12-stage run starts. It supports the full completed scope and explicit single-partition checks, but it intentionally rejects `--partition-count` without `--partition-index` because planner-only mode cannot stand in for the full partition loop.
- `PROMOTIONS_MSSQL_QUERY_TIMEOUT_SECONDS` is optional. When set, the runtime attempts to apply that timeout to the underlying DBAPI connection before query execution and records both the requested timeout and whether it was applied in the extraction telemetry.
- The live decision surface now runs on the future scored rows while calibrating against historical cohort context from the training artifact.
- The decision-surface inspection package includes `inspection_promotion_review_packet` with promotion_row_key, promotion_name, supplier, department, store_number, promotion_start_date, promotion_end_date, predicted_units_first_day, predicted_sell_through_pct, predicted_sales_ex_gst, predicted_gross_profit, leftover_risk_penalty, stockout_risk_penalty, overallocation_risk_penalty, underallocation_risk_penalty, archetype_primary, archetype_secondary, final_decision_score, final_confidence_score, decision_recommendation, and decision_recommendation_reason.
- The operational cycle writes a store-facing download CSV under `prediction/store_downloads/<run_id>/` with operator-friendly columns including store_number, promotion_name, promo_type, supplier_number, inferred_supplier_number, supplier_name, department_number, sku_number, barcode, description, soh_units, on_order_units, allocation_units, promo_start_date, promo_end_date, predicted_units_first_day, predicted_units_full_promo, predicted_sales_ex_gst, predicted_sell_through_pct, predicted_leftover_units, recommended_order_units_to_min_base_stock, minimum_base_stock_target_units, final_decision_score, final_confidence_score, decision_recommendation, and decision_recommendation_reason, while preserving compatibility aliases used by existing audits and reviews.
- `predicted_units_first_day` is a transparent derived field rather than a separately trained target: `predicted_units_sold / max(live_promo_window_days or promo_days, 1)`. The derivation is recorded in scoring and local-inspection manifest metadata.
- The default minimum base-stock target for the store download is 2 units unless a stronger authoritative stock floor is already present in the data.
- Each run can also write a local inspection package under `tmp/promotions_local_inspection/<run_id>/` containing a run-scoped store CSV copy, decision-surface CSV copy, review-packet CSV copy, audit summary JSON/CSV copies, operator summary JSON/CSV copies when available, and a compact run summary JSON with the key NAS and local links.
- The post-run audit writes `operational_cycle_run_summary.json`, `operational_cycle_run_summary.csv`, `operational_cycle_audit_manifest.json`, `top_predicted_opportunities`, `top_margin_traps`, `top_leftover_risks`, `top_stockout_risks`, `top_row_vs_cohort_disagreements`, and grouped supplier, department, and store summaries.
- The top-level operational-cycle manifest now includes `execution_mode`, `nas_root`, `local_inspection_root`, `nas_bootstrap`, `store_outputs`, `local_inspection`, `audit`, `operator_progress`, and `final_outputs` so the operator can jump directly to the NAS store CSV, local inspection CSV, operator review packet, audit summary, operator log, and manifest.
- A live MSSQL-backed run requires reachable SQL Server access and the configured advice and `pwlogD` tables.

Dry-run and explain workflow:

- Use `python -m runtime.promotions.inspect_promotions_sql_extraction --selection-mode completed --as-of-date YYYY-MM-DD` to resolve the live config, render the governed SQL template, and print the active query-window summary without running the full operational cycle.
- Add `--save-rendered-sql` to persist `rendered_sql.sql` and `rendered_sql_parameters.json` under `manifests/<run_id>/` without starting downstream stages.
- Add `--test-connection` when you want the inspector to perform only a connectivity check (`SELECT 1`) using the same MSSQL settings and optional query timeout as the live extractor.
- Add `--run-row-count-probe` to execute only the lightweight candidate-promotion count probe for the selected query shape.
- Add `--run-preflight` to execute the transaction-scope planner probe without running the full extraction. The inspector writes the preflight SQL, parameter JSON, summary JSON, and summary CSV under the governed run paths.
- Add `--planner-only` to force the inspector into preflight-only mode. It disables the row-count probe and heavy extraction, prints the planner verdict and recommendation, and is the preferred live check before trying a new completed partition plan.
- Add `--run-extraction` to run the extractor by itself, persist the governed parquet, manifest, and SQL observability artifacts, and stop before dataset, training, scoring, decision-surface, or audit stages.
- Add `--enable-landed-batches`, `--batch-row-count`, `--enable-chunked-fetch`, `--chunk-row-count`, `--resume-completed-partitions`, and `--stage-temp-chunk-files` when you need the inspector to exercise the same landed-batch completed-extraction path, per-batch progress markers, and finalized completion markers that the live stage-3 runtime uses.
- Add `--max-candidate-promotion-rows`, `--max-candidate-store-sku`, `--max-window-span-days-total`, and `--max-window-span-days-max` when you want to override the default completed preflight thresholds for one diagnostic session without changing code.
- Add `--extraction-mode diagnostic_topn --limit-promotions N` when you want a bounded completed-promotions diagnostic run. Optional `--promotion-name-like`, `--store-number`, and `--supplier-number` filters further narrow the advice rows before the heavier joined sales windows are materialized.
- Add `--partition-strategy`, `--partition-count`, and `--partition-index` when you want the inspector to render, probe, or extract one governed completed partition using the same partition contract as stage 3. The inspector requires all three flags together because a single-partition probe must be explicit about both the strategy and the selected child partition.
- The recommended live diagnosis flow for partition mode is: first run the inspector with `--planner-only` or `--run-preflight` for a chosen partition, then use `--run-row-count-probe` if you want one extra bounded cardinality check, then rerun with `--run-extraction` only for partitions the planner marks `SAFE_TO_EXTRACT`, and only then enable the same strategy/count on the full operational cycle.
- The inspector is intentionally separate from `run_promotions_operational_cycle` so operators can diagnose SQL rendering and connectivity without writing governed run artifacts or starting downstream model, scoring, decision-surface, or audit stages.