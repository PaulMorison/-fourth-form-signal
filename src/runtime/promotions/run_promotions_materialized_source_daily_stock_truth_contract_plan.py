from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Sequence

import pandas as pd


OUTPUT_FOLDER_NAME = "materialized_source_daily_stock_truth_contract_plan"
SOURCE_CONTRACT_FOLDER_NAME = "materialized_source_actual_outcome_source_contract_plan"
MAPPING_FEASIBILITY_FOLDER_NAME = "materialized_source_actual_outcome_mapping_feasibility_plan"
SOURCE_MATERIALIZED_FOLDER_NAME = "source_materialized_promotions"
DAILY_STOCK_TRUTH_EXTRACT_FOLDER_NAME = "materialized_source_daily_stock_truth"

SOURCE_CONTRACT_SUMMARY_FILE_NAME = "actual_outcome_source_contract_summary.csv"
MAPPING_SUMMARY_FILE_NAME = "actual_outcome_mapping_feasibility_summary.csv"
MAPPING_BLOCKERS_FILE_NAME = "actual_outcome_mapping_blockers.csv"
PROMOTION_SOURCE_ROWS_FILE_NAME = "promotion_source_rows.csv"
OPERATOR_AUDIT_FILE_NAME = "operator_audit_source.csv"
ACTUAL_OUTCOME_FILE_NAME = "actual_outcome_source.csv"
DAILY_STOCK_TRUTH_EXTRACT_FILE_NAME = "daily_stock_truth_rows.csv"

SUMMARY_FILE_NAME = "daily_stock_truth_contract_summary.csv"
SCHEMA_FILE_NAME = "daily_stock_truth_contract_schema.csv"
SOURCE_REQUIREMENTS_FILE_NAME = "daily_stock_truth_contract_source_requirements.csv"
ROLLUP_RULES_FILE_NAME = "daily_stock_truth_contract_rollup_rules.csv"
VALIDATION_GATES_FILE_NAME = "daily_stock_truth_contract_validation_gates.csv"
BUILD_SEQUENCE_FILE_NAME = "daily_stock_truth_contract_build_sequence.csv"
VALIDATION_FILE_NAME = "daily_stock_truth_contract_validation.csv"
MEMO_FILE_NAME = "daily_stock_truth_contract_memo.md"

STATUS_READY = "DAILY_STOCK_TRUTH_CONTRACT_READY"

DAILY_EXTRACT_GRAIN = "store_number + sku_number + calendar_date"
FINAL_ROLLUP_GRAIN = "store_number + promotion_start_date + promotion_name + sku_number"

IDENTITY_FIELDS: tuple[str, ...] = (
    "store_number",
    "sku_number",
    "calendar_date",
)

STOCK_EVIDENCE_FIELDS: tuple[str, ...] = (
    "day_open_soh_units",
    "day_close_soh_units",
    "stock_movement_in_units",
    "stock_movement_out_units",
    "explicit_oos_flag",
    "explicit_sufficient_stock_flag",
    "availability_flag",
)

PROVENANCE_FIELDS: tuple[str, ...] = (
    "stockout_signal_source_table",
    "stockout_signal_event_type",
    "stockout_signal_recorded_at_utc",
    "extract_run_id",
)

COMPLETENESS_CONFIDENCE_FIELDS: tuple[str, ...] = (
    "snapshot_completeness_flag",
    "inventory_event_completeness_flag",
    "availability_signal_quality_flag",
    "actual_stockout_flag_confidence",
    "actual_stockout_flag_source",
    "actual_stockout_flag_basis",
    "actual_stockout_observed_at_grain",
)

SUMMARY_COLUMNS: tuple[str, ...] = (
    "metric_name",
    "metric_value",
    "metric_display",
    "notes",
)

SCHEMA_COLUMNS: tuple[str, ...] = (
    "field_name",
    "required_flag",
    "field_group",
    "data_type",
    "null_allowed_flag",
    "notes",
)

SOURCE_REQUIREMENTS_COLUMNS: tuple[str, ...] = (
    "source_name",
    "source_role",
    "required_flag",
    "source_status",
    "notes",
)

ROLLUP_RULES_COLUMNS: tuple[str, ...] = (
    "rule_order",
    "rule_name",
    "rule_scope",
    "rule_condition",
    "rule_outcome",
    "rule_notes",
)

VALIDATION_GATES_COLUMNS: tuple[str, ...] = (
    "gate_order",
    "gate_name",
    "gate_required_flag",
    "gate_scope",
    "pass_criteria",
    "blocking_flag",
)

BUILD_SEQUENCE_COLUMNS: tuple[str, ...] = (
    "step_order",
    "step_name",
    "step_type",
    "runtime_name",
    "execution_rule",
)

VALIDATION_COLUMNS: tuple[str, ...] = (
    "validation_name",
    "validation_status",
    "validation_flag",
    "details",
)

SOURCE_REFERENCE_FILES: tuple[str, ...] = (
    "src/data/promotions/sql/promotion_base_extraction.sql",
    "src/data/promotions/completed_transaction_aggregates_extractor.py",
    "src/data/promotions/completed_window_aggregates_extractor.py",
    "src/runtime/promotions/config.py",
)


class PromotionsMaterializedSourceDailyStockTruthContractPlanError(RuntimeError):
    pass


@dataclass(frozen=True)
class PromotionsMaterializedSourceDailyStockTruthContractPlanResult:
    contract_status: str
    promotion_key: str
    promotion_folder_name: str
    daily_extract_grain: str
    final_rollup_grain: str
    daily_stock_truth_extract_created_flag: int
    actual_outcome_source_created_flag: int
    source_packets_mutated_flag: int
    operator_audit_overwritten_flag: int
    summary_frame: pd.DataFrame
    schema_frame: pd.DataFrame
    source_requirements_frame: pd.DataFrame
    rollup_rules_frame: pd.DataFrame
    validation_gates_frame: pd.DataFrame
    build_sequence_frame: pd.DataFrame
    validation_frame: pd.DataFrame
    memo_markdown: str


@dataclass(frozen=True)
class PromotionsMaterializedSourceDailyStockTruthContractPlanArtifacts:
    output_root: str
    summary_csv_path: str
    schema_csv_path: str
    source_requirements_csv_path: str
    rollup_rules_csv_path: str
    validation_gates_csv_path: str
    build_sequence_csv_path: str
    validation_csv_path: str
    memo_md_path: str


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def _read_csv(path: str | Path, *, allow_empty: bool = False) -> pd.DataFrame:
    csv_path = Path(path)
    if not csv_path.exists():
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceDailyStockTruthContractPlanError(f"CSV not found: {csv_path}")
    try:
        frame = pd.read_csv(csv_path, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceDailyStockTruthContractPlanError(f"CSV is empty: {csv_path}")
    if frame.empty and not allow_empty:
        raise PromotionsMaterializedSourceDailyStockTruthContractPlanError(f"CSV is empty: {csv_path}")
    return frame


def _summary_row(metric_name: str, metric_value: object, notes: str) -> dict[str, object]:
    return {
        "metric_name": metric_name,
        "metric_value": metric_value,
        "metric_display": str(metric_value),
        "notes": notes,
    }


def _validation_row(name: str, flag: int, details: str) -> dict[str, object]:
    return {
        "validation_name": name,
        "validation_status": "PASS" if flag else "FAIL",
        "validation_flag": int(flag),
        "details": details,
    }


def _metric_lookup(frame: pd.DataFrame) -> dict[str, str]:
    if frame.empty:
        return {}
    return dict(zip(frame["metric_name"].astype(str), frame["metric_value"].astype(str)))


def _promotion_parts_from_key(promotion_key: str) -> tuple[str, str, str, str]:
    parts = [part.strip() for part in promotion_key.split("|", maxsplit=3)]
    if len(parts) != 4 or not all(parts):
        raise PromotionsMaterializedSourceDailyStockTruthContractPlanError(
            f"Invalid promotion key format: {promotion_key}"
        )
    return parts[0], parts[1], parts[2], parts[3]


def _slugify(value: str) -> str:
    lowered = value.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered)
    return re.sub(r"-{2,}", "-", slug).strip("-")


def _promotion_folder_from_key(promotion_key: str) -> str:
    store, start_date, end_date, promotion_name = _promotion_parts_from_key(promotion_key)
    return f"promotion_{store}-{start_date}-{end_date}-{_slugify(promotion_name)}"


def _resolve_output_root(packet_root: Path, output_root: str | Path | None) -> Path:
    if output_root is not None:
        return Path(output_root)
    return packet_root / OUTPUT_FOLDER_NAME


def _schema_frame() -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    for field in IDENTITY_FIELDS:
        rows.append(
            {
                "field_name": field,
                "required_flag": 1,
                "field_group": "IDENTITY",
                "data_type": "string_or_date",
                "null_allowed_flag": 0,
                "notes": "Required daily stock-truth extract identity field.",
            }
        )

    for field in STOCK_EVIDENCE_FIELDS:
        rows.append(
            {
                "field_name": field,
                "required_flag": 1,
                "field_group": "STOCK_EVIDENCE",
                "data_type": "numeric_or_flag",
                "null_allowed_flag": 0,
                "notes": "Required daily stock-truth evidence field.",
            }
        )

    for field in PROVENANCE_FIELDS:
        rows.append(
            {
                "field_name": field,
                "required_flag": 1,
                "field_group": "PROVENANCE",
                "data_type": "string_or_datetime",
                "null_allowed_flag": 0,
                "notes": "Required stockout evidence provenance field.",
            }
        )

    for field in COMPLETENESS_CONFIDENCE_FIELDS:
        rows.append(
            {
                "field_name": field,
                "required_flag": 1,
                "field_group": "COMPLETENESS_CONFIDENCE",
                "data_type": "flag_or_enum",
                "null_allowed_flag": 0,
                "notes": "Required completeness/confidence or promotion-rollup provenance field.",
            }
        )

    return pd.DataFrame(rows, columns=SCHEMA_COLUMNS)


def _source_requirements_frame(repo_root: Path) -> pd.DataFrame:
    source_refs_exist = all((repo_root / relative_path).exists() for relative_path in SOURCE_REFERENCE_FILES)
    return pd.DataFrame(
        [
            {
                "source_name": "PWLOGD_TABLE",
                "source_role": "REALISED_SALES_REFERENCE_ONLY",
                "required_flag": 1,
                "source_status": "SALES_TRUTH_ONLY_NOT_STOCKOUT_TRUTH",
                "notes": "PWLOGD is strong enough for realised sales but does not provide governed stockout truth by itself.",
            },
            {
                "source_name": "DAILY_STOCK_LEDGER_OR_SOH_SNAPSHOT",
                "source_role": "PRIMARY_STOCK_TRUTH",
                "required_flag": 1,
                "source_status": "REQUIRED_NEW_GOVERNED_SOURCE",
                "notes": "Must provide daily store-SKU opening/closing stock or equivalent stockout truth signals.",
            },
            {
                "source_name": "DAILY_STOCKOUT_EVENT_OR_AVAILABILITY_SOURCE",
                "source_role": "POSITIVE_STOCKOUT_EVIDENCE",
                "required_flag": 1,
                "source_status": "REQUIRED_IF_LEDGER_ALONE_CANNOT_PROVE_OOS",
                "notes": "Needed when ledger snapshots alone cannot distinguish zero sales from true stockout.",
            },
            {
                "source_name": "SOURCE_REFERENCE_FILES_PRESENT",
                "source_role": "CONTEXT_REFERENCE",
                "required_flag": 1,
                "source_status": "YES" if source_refs_exist else "NO",
                "notes": "Reference SQL/runtime files are used for source-scoping context only.",
            },
        ],
        columns=SOURCE_REQUIREMENTS_COLUMNS,
    )


def _rollup_rules_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "rule_order": 1,
                "rule_name": "DAILY_GRAIN_REQUIREMENT",
                "rule_scope": "daily_extract",
                "rule_condition": "Build daily rows at store_number + sku_number + calendar_date.",
                "rule_outcome": "daily_stock_truth_row",
                "rule_notes": "Required recommended daily extract grain.",
            },
            {
                "rule_order": 2,
                "rule_name": "PROMOTION_WINDOW_JOIN",
                "rule_scope": "promotion_window",
                "rule_condition": "Join daily rows to promotion window by store, sku, and calendar_date between promotion_start_date and promotion_end_date inclusive.",
                "rule_outcome": "daily_rows_scoped_to_promotion",
                "rule_notes": "Rollup input scoping rule.",
            },
            {
                "rule_order": 3,
                "rule_name": "STOCKOUT_POSITIVE_RULE",
                "rule_scope": "promotion_rollup",
                "rule_condition": "If any in-window day has explicit_oos_flag=1, or stockout_event_flag=1, or governed availability says unavailable with valid source quality.",
                "rule_outcome": "actual_stockout_flag=1",
                "rule_notes": "Do not use low sales, low cover, current SOH alone, low SOH alone, or allocation-minus-sales as proof.",
            },
            {
                "rule_order": 4,
                "rule_name": "SUFFICIENT_STOCK_RULE",
                "rule_scope": "promotion_rollup",
                "rule_condition": "Only if every in-window day has explicit_sufficient_stock_flag=1 and no positive day exists, with full-window completeness.",
                "rule_outcome": "actual_stockout_flag=0",
                "rule_notes": "Full-window completeness is required for zero.",
            },
            {
                "rule_order": 5,
                "rule_name": "UNKNOWN_RULE",
                "rule_scope": "promotion_rollup",
                "rule_condition": "If no positive evidence exists and no full-window sufficient-stock evidence exists, or stock ledger/availability coverage is incomplete.",
                "rule_outcome": "actual_stockout_flag=UNKNOWN",
                "rule_notes": "Unknown must not be coerced to 0.",
            },
            {
                "rule_order": 6,
                "rule_name": "ROLLUP_PRECEDENCE",
                "rule_scope": "promotion_rollup",
                "rule_condition": "Apply precedence: positive > sufficient-stock > unknown.",
                "rule_outcome": "deterministic_stockout_rollup",
                "rule_notes": "Preserve source, basis, confidence, and observed grain.",
            },
            {
                "rule_order": 7,
                "rule_name": "CONFIDENCE_MAPPING",
                "rule_scope": "promotion_rollup",
                "rule_condition": "HIGH=explicit stockout event table or explicit full-window sufficient-stock evidence; MEDIUM=complete daily SOH + governed availability coverage; LOW=partial/mixed-source reconstruction; UNKNOWN=insufficient evidence.",
                "rule_outcome": "actual_stockout_flag_confidence",
                "rule_notes": "LOW should generally remain blocked.",
            },
        ],
        columns=ROLLUP_RULES_COLUMNS,
    )


def _validation_gates_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "gate_order": 1,
                "gate_name": "DAILY_GRAIN_GATE",
                "gate_required_flag": 1,
                "gate_scope": "daily_extract",
                "pass_criteria": "Daily stock-truth extract is exactly store_number + sku_number + calendar_date.",
                "blocking_flag": 1,
            },
            {
                "gate_order": 2,
                "gate_name": "POSITIVE_STOCKOUT_TRUTH_GATE",
                "gate_required_flag": 1,
                "gate_scope": "promotion_rollup",
                "pass_criteria": "actual_stockout_flag=1 is only from explicit governed stockout evidence.",
                "blocking_flag": 1,
            },
            {
                "gate_order": 3,
                "gate_name": "SUFFICIENT_STOCK_TRUTH_GATE",
                "gate_required_flag": 1,
                "gate_scope": "promotion_rollup",
                "pass_criteria": "actual_stockout_flag=0 requires full-window explicit sufficient-stock evidence with no positive day.",
                "blocking_flag": 1,
            },
            {
                "gate_order": 4,
                "gate_name": "UNKNOWN_NOT_ZERO_GATE",
                "gate_required_flag": 1,
                "gate_scope": "promotion_rollup",
                "pass_criteria": "Unknown stockout is never coerced to 0.",
                "blocking_flag": 1,
            },
            {
                "gate_order": 5,
                "gate_name": "WEAK_PROXY_FORBIDDEN_GATE",
                "gate_required_flag": 1,
                "gate_scope": "rule_engine",
                "pass_criteria": "Low sales, low cover, current SOH alone, low SOH alone, allocation-minus-sales are forbidden stockout proofs.",
                "blocking_flag": 1,
            },
            {
                "gate_order": 6,
                "gate_name": "PROVENANCE_GATE",
                "gate_required_flag": 1,
                "gate_scope": "row_level",
                "pass_criteria": "Source table, event type, recorded timestamp, and extract run id are populated.",
                "blocking_flag": 1,
            },
            {
                "gate_order": 7,
                "gate_name": "COMPLETENESS_CONFIDENCE_GATE",
                "gate_required_flag": 1,
                "gate_scope": "row_level",
                "pass_criteria": "Snapshot/inventory/availability completeness flags and confidence mapping are populated.",
                "blocking_flag": 1,
            },
            {
                "gate_order": 8,
                "gate_name": "PLANNER_SAFETY_GATE",
                "gate_required_flag": 1,
                "gate_scope": "packet",
                "pass_criteria": "Planner does not create daily extract, does not create actual_outcome_source.csv, and does not mutate source packets.",
                "blocking_flag": 1,
            },
        ],
        columns=VALIDATION_GATES_COLUMNS,
    )


def _build_sequence_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "step_order": 1,
                "step_name": "DAILY_STOCK_TRUTH_CONTRACT_PLAN",
                "step_type": "planner",
                "runtime_name": "run_promotions_materialized_source_daily_stock_truth_contract_plan.py",
                "execution_rule": "Define governed daily stock-truth source contract artifacts.",
            },
            {
                "step_order": 2,
                "step_name": "DAILY_STOCK_TRUTH_SOURCE_DISCOVERY_CONFIG_CHECK",
                "step_type": "discovery",
                "runtime_name": "run_promotions_materialized_source_daily_stock_truth_source_discovery.py",
                "execution_rule": "Validate governed daily source availability and configuration.",
            },
            {
                "step_order": 3,
                "step_name": "DAILY_STOCK_TRUTH_EXTRACTOR",
                "step_type": "extractor",
                "runtime_name": "run_promotions_materialized_source_daily_stock_truth_extractor.py",
                "execution_rule": "Build daily stock-truth evidence rows.",
            },
            {
                "step_order": 4,
                "step_name": "DAILY_STOCK_TRUTH_READINESS_CHECKER",
                "step_type": "readiness",
                "runtime_name": "run_promotions_materialized_source_daily_stock_truth_readiness.py",
                "execution_rule": "Validate stock-truth completeness, provenance, confidence, and unknown handling.",
            },
            {
                "step_order": 5,
                "step_name": "ACTUAL_OUTCOME_MAPPING_FEASIBILITY_RERUN",
                "step_type": "planner",
                "runtime_name": "run_promotions_materialized_source_actual_outcome_mapping_feasibility_plan.py",
                "execution_rule": "Rerun ACTUAL_OUTCOME mapping feasibility after daily stock-truth readiness passes.",
            },
            {
                "step_order": 6,
                "step_name": "ACTUAL_OUTCOME_SOURCE_BUILDER_CONDITIONAL",
                "step_type": "builder",
                "runtime_name": "run_promotions_materialized_source_actual_outcome_build_source.py",
                "execution_rule": "Build ACTUAL_OUTCOME source only if mapping becomes ready.",
            },
        ],
        columns=BUILD_SEQUENCE_COLUMNS,
    )


def build_promotions_materialized_source_daily_stock_truth_contract_plan(
    *,
    packet_root: str | Path,
    promotion_key: str,
    output_root: str | Path | None = None,
) -> PromotionsMaterializedSourceDailyStockTruthContractPlanResult:
    packet_root_path = Path(packet_root)
    source_contract_root = packet_root_path / SOURCE_CONTRACT_FOLDER_NAME
    mapping_root = packet_root_path / MAPPING_FEASIBILITY_FOLDER_NAME

    _ = _read_csv(source_contract_root / SOURCE_CONTRACT_SUMMARY_FILE_NAME)
    mapping_summary = _read_csv(mapping_root / MAPPING_SUMMARY_FILE_NAME)
    mapping_blockers = _read_csv(mapping_root / MAPPING_BLOCKERS_FILE_NAME)

    promotion_folder_name = _promotion_folder_from_key(promotion_key)
    source_folder = packet_root_path / SOURCE_MATERIALIZED_FOLDER_NAME / promotion_folder_name

    promotion_source_rows_path = source_folder / PROMOTION_SOURCE_ROWS_FILE_NAME
    operator_audit_path = source_folder / OPERATOR_AUDIT_FILE_NAME
    actual_outcome_source_path = source_folder / ACTUAL_OUTCOME_FILE_NAME
    daily_stock_truth_extract_path = packet_root_path / DAILY_STOCK_TRUTH_EXTRACT_FOLDER_NAME / DAILY_STOCK_TRUTH_EXTRACT_FILE_NAME

    source_rows_before = promotion_source_rows_path.read_bytes() if promotion_source_rows_path.exists() else b""
    operator_before = operator_audit_path.read_bytes() if operator_audit_path.exists() else b""
    actual_outcome_before = int(actual_outcome_source_path.exists())
    daily_stock_truth_before = int(daily_stock_truth_extract_path.exists())

    schema_frame = _schema_frame()
    source_requirements_frame = _source_requirements_frame(Path(__file__).resolve().parents[3])
    rollup_rules_frame = _rollup_rules_frame()
    validation_gates_frame = _validation_gates_frame()
    build_sequence_frame = _build_sequence_frame()

    source_rows_after = promotion_source_rows_path.read_bytes() if promotion_source_rows_path.exists() else b""
    operator_after = operator_audit_path.read_bytes() if operator_audit_path.exists() else b""
    actual_outcome_after = int(actual_outcome_source_path.exists())
    daily_stock_truth_after = int(daily_stock_truth_extract_path.exists())

    source_packets_mutated_flag = int(source_rows_before != source_rows_after)
    operator_audit_overwritten_flag = int(operator_before != operator_after)
    actual_outcome_source_created_flag = int(actual_outcome_before == 0 and actual_outcome_after == 1)
    daily_stock_truth_extract_created_flag = int(daily_stock_truth_before == 0 and daily_stock_truth_after == 1)

    mapping_metrics = _metric_lookup(mapping_summary)
    mapping_status = _normalize_text(mapping_metrics.get("MAPPING_FEASIBILITY_STATUS"))
    mapping_blocker = ""
    if not mapping_blockers.empty:
        mapping_blocker = _normalize_text(mapping_blockers.iloc[0].get("blocker_code"))

    summary_frame = pd.DataFrame(
        [
            _summary_row("CONTRACT_STATUS", STATUS_READY, "Planner-only daily stock-truth contract status."),
            _summary_row("PROMOTION_KEY", promotion_key, "Promotion key under stock-truth contract design."),
            _summary_row("PROMOTION_FOLDER_NAME", promotion_folder_name, "Promotion-scoped source folder name."),
            _summary_row("DAILY_EXTRACT_GRAIN", DAILY_EXTRACT_GRAIN, "Required daily stock-truth grain."),
            _summary_row("FINAL_ROLLUP_GRAIN", FINAL_ROLLUP_GRAIN, "Required final ACTUAL_OUTCOME rollup grain."),
            _summary_row("MAPPING_FEASIBILITY_STATUS_USED", mapping_status, "Input from ACTUAL_OUTCOME mapping feasibility summary."),
            _summary_row("MAPPING_BLOCKER_USED", mapping_blocker, "Input from ACTUAL_OUTCOME mapping blockers."),
            _summary_row("VALIDATION_GATE_COUNT", int(len(validation_gates_frame.index)), "Total validation gates for governed stock-truth contract."),
            _summary_row("DAILY_STOCK_TRUTH_EXTRACT_CREATED_FLAG", daily_stock_truth_extract_created_flag, "Planner must not create daily stock-truth extract."),
            _summary_row("ACTUAL_OUTCOME_SOURCE_CREATED_FLAG", actual_outcome_source_created_flag, "Planner must not create actual_outcome_source.csv."),
            _summary_row("SOURCE_PACKETS_MUTATED_FLAG", source_packets_mutated_flag, "Planner must not mutate promotion_source_rows.csv."),
            _summary_row("OPERATOR_AUDIT_OVERWRITTEN_FLAG", operator_audit_overwritten_flag, "Planner must not overwrite operator_audit_source.csv."),
        ],
        columns=SUMMARY_COLUMNS,
    )

    field_names = set(schema_frame["field_name"].astype(str))
    rule_names = set(rollup_rules_frame["rule_name"].astype(str))
    gate_names = set(validation_gates_frame["gate_name"].astype(str))

    validation_frame = pd.DataFrame(
        [
            _validation_row("CONTRACT_STATUS_READY", 1, "Contract status constant is ready."),
            _validation_row("SCHEMA_INCLUDES_DAILY_GRAIN_KEYS", int(set(IDENTITY_FIELDS).issubset(field_names)), "Daily grain keys are present."),
            _validation_row("SCHEMA_INCLUDES_STOCK_EVIDENCE_FIELDS", int(set(STOCK_EVIDENCE_FIELDS).issubset(field_names)), "Required stock evidence fields are present."),
            _validation_row("SCHEMA_INCLUDES_PROVENANCE_FIELDS", int(set(PROVENANCE_FIELDS).issubset(field_names)), "Required provenance fields are present."),
            _validation_row("SCHEMA_INCLUDES_COMPLETENESS_CONFIDENCE_FIELDS", int(set(COMPLETENESS_CONFIDENCE_FIELDS).issubset(field_names)), "Required completeness/confidence fields are present."),
            _validation_row("ROLLUP_RULES_INCLUDE_POSITIVE_SUFFICIENT_UNKNOWN", int({"STOCKOUT_POSITIVE_RULE", "SUFFICIENT_STOCK_RULE", "UNKNOWN_RULE"}.issubset(rule_names)), "Rollup rules include positive, sufficient-stock, and unknown logic."),
            _validation_row("VALIDATION_FORBIDS_UNKNOWN_TO_ZERO", int("UNKNOWN_NOT_ZERO_GATE" in gate_names), "Unknown-to-zero coercion is forbidden by validation gate."),
            _validation_row(
                "PWLOGD_SALES_ONLY_NOT_STOCKOUT_TRUTH",
                int(
                    source_requirements_frame.loc[
                        source_requirements_frame["source_name"].astype(str).eq("PWLOGD_TABLE"),
                        "source_status",
                    ].astype(str).eq("SALES_TRUTH_ONLY_NOT_STOCKOUT_TRUTH").any()
                ),
                "PWLOGD is explicitly sales truth only and not stockout truth.",
            ),
            _validation_row("NO_DAILY_STOCK_TRUTH_EXTRACT_CREATED", int(daily_stock_truth_extract_created_flag == 0), "Planner did not create daily stock-truth extract."),
            _validation_row("NO_ACTUAL_OUTCOME_SOURCE_CREATED", int(actual_outcome_source_created_flag == 0), "Planner did not create actual_outcome_source.csv."),
            _validation_row("SOURCE_PACKETS_UNCHANGED", int(source_packets_mutated_flag == 0), "promotion_source_rows.csv remained unchanged."),
            _validation_row("OPERATOR_AUDIT_UNCHANGED", int(operator_audit_overwritten_flag == 0), "operator_audit_source.csv remained unchanged."),
        ],
        columns=VALIDATION_COLUMNS,
    )

    memo_markdown = "\n".join(
        [
            "# Daily Stock Truth Contract Plan",
            "",
            "Planner-only governed stock-truth source contract for ACTUAL_OUTCOME stockout evidence.",
            "",
            f"Contract status: {STATUS_READY}",
            f"Daily extract grain: {DAILY_EXTRACT_GRAIN}",
            f"Final rollup grain: {FINAL_ROLLUP_GRAIN}",
            f"Upstream mapping status: {mapping_status}",
            f"Upstream mapping blocker: {mapping_blocker}",
            "",
            "Stockout-positive rule: set actual_stockout_flag=1 when any trusted in-window positive stockout evidence exists.",
            "Sufficient-stock rule: set actual_stockout_flag=0 only with explicit full-window sufficient-stock evidence and no positive stockout day.",
            "Unknown rule: keep unknown when evidence is incomplete/insufficient; unknown is never coerced to 0.",
            "",
            "Confidence mapping:",
            "- HIGH: explicit stockout event table or explicit full-window sufficient-stock evidence.",
            "- MEDIUM: complete daily SOH snapshot and governed availability coverage.",
            "- LOW: partial/mixed-source reconstruction; generally remains blocked.",
            "- UNKNOWN: insufficient evidence.",
            "",
            "Planner safety: no daily extract build, no ACTUAL_OUTCOME source build, no source packet mutation, no operator audit overwrite.",
        ]
    )

    return PromotionsMaterializedSourceDailyStockTruthContractPlanResult(
        contract_status=STATUS_READY,
        promotion_key=promotion_key,
        promotion_folder_name=promotion_folder_name,
        daily_extract_grain=DAILY_EXTRACT_GRAIN,
        final_rollup_grain=FINAL_ROLLUP_GRAIN,
        daily_stock_truth_extract_created_flag=daily_stock_truth_extract_created_flag,
        actual_outcome_source_created_flag=actual_outcome_source_created_flag,
        source_packets_mutated_flag=source_packets_mutated_flag,
        operator_audit_overwritten_flag=operator_audit_overwritten_flag,
        summary_frame=summary_frame,
        schema_frame=schema_frame,
        source_requirements_frame=source_requirements_frame,
        rollup_rules_frame=rollup_rules_frame,
        validation_gates_frame=validation_gates_frame,
        build_sequence_frame=build_sequence_frame,
        validation_frame=validation_frame,
        memo_markdown=memo_markdown,
    )


def write_promotions_materialized_source_daily_stock_truth_contract_plan(
    *,
    packet_root: str | Path,
    promotion_key: str,
    output_root: str | Path | None = None,
) -> PromotionsMaterializedSourceDailyStockTruthContractPlanArtifacts:
    packet_root_path = Path(packet_root)
    output_root_path = _resolve_output_root(packet_root_path, output_root)

    result = build_promotions_materialized_source_daily_stock_truth_contract_plan(
        packet_root=packet_root,
        promotion_key=promotion_key,
        output_root=output_root,
    )

    output_root_path.mkdir(parents=True, exist_ok=True)

    summary_path = output_root_path / SUMMARY_FILE_NAME
    schema_path = output_root_path / SCHEMA_FILE_NAME
    source_requirements_path = output_root_path / SOURCE_REQUIREMENTS_FILE_NAME
    rollup_rules_path = output_root_path / ROLLUP_RULES_FILE_NAME
    validation_gates_path = output_root_path / VALIDATION_GATES_FILE_NAME
    build_sequence_path = output_root_path / BUILD_SEQUENCE_FILE_NAME
    validation_path = output_root_path / VALIDATION_FILE_NAME
    memo_path = output_root_path / MEMO_FILE_NAME

    result.summary_frame.to_csv(summary_path, index=False)
    result.schema_frame.to_csv(schema_path, index=False)
    result.source_requirements_frame.to_csv(source_requirements_path, index=False)
    result.rollup_rules_frame.to_csv(rollup_rules_path, index=False)
    result.validation_gates_frame.to_csv(validation_gates_path, index=False)
    result.build_sequence_frame.to_csv(build_sequence_path, index=False)
    result.validation_frame.to_csv(validation_path, index=False)
    memo_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsMaterializedSourceDailyStockTruthContractPlanArtifacts(
        output_root=str(output_root_path),
        summary_csv_path=str(summary_path),
        schema_csv_path=str(schema_path),
        source_requirements_csv_path=str(source_requirements_path),
        rollup_rules_csv_path=str(rollup_rules_path),
        validation_gates_csv_path=str(validation_gates_path),
        build_sequence_csv_path=str(build_sequence_path),
        validation_csv_path=str(validation_path),
        memo_md_path=str(memo_path),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build planner-only daily stock-truth source contract artifacts for ACTUAL_OUTCOME stockout evidence."
    )
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--promotion-key", required=True)
    parser.add_argument("--output-root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)

    artifacts = write_promotions_materialized_source_daily_stock_truth_contract_plan(
        packet_root=args.packet_root,
        promotion_key=args.promotion_key,
        output_root=args.output_root,
    )

    summary = _read_csv(artifacts.summary_csv_path, allow_empty=True)
    metrics = _metric_lookup(summary)

    print("contract_status", _normalize_text(metrics.get("CONTRACT_STATUS", "")))
    print("daily_extract_grain", _normalize_text(metrics.get("DAILY_EXTRACT_GRAIN", "")))
    print("final_rollup_grain", _normalize_text(metrics.get("FINAL_ROLLUP_GRAIN", "")))
    print("validation_gate_count", _normalize_text(metrics.get("VALIDATION_GATE_COUNT", 0)))
    print("daily_stock_truth_extract_created_flag", _normalize_text(metrics.get("DAILY_STOCK_TRUTH_EXTRACT_CREATED_FLAG", 0)))
    print("actual_outcome_source_created_flag", _normalize_text(metrics.get("ACTUAL_OUTCOME_SOURCE_CREATED_FLAG", 0)))
    print("source_packets_mutated_flag", _normalize_text(metrics.get("SOURCE_PACKETS_MUTATED_FLAG", 0)))
    print("operator_audit_overwritten_flag", _normalize_text(metrics.get("OPERATOR_AUDIT_OVERWRITTEN_FLAG", 0)))
    print("daily_stock_truth_contract_summary", artifacts.summary_csv_path)
    print("daily_stock_truth_contract_schema", artifacts.schema_csv_path)
    print("daily_stock_truth_contract_source_requirements", artifacts.source_requirements_csv_path)
    print("daily_stock_truth_contract_rollup_rules", artifacts.rollup_rules_csv_path)
    print("daily_stock_truth_contract_validation_gates", artifacts.validation_gates_csv_path)
    print("daily_stock_truth_contract_build_sequence", artifacts.build_sequence_csv_path)
    print("daily_stock_truth_contract_validation", artifacts.validation_csv_path)
    print("daily_stock_truth_contract_memo", artifacts.memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
