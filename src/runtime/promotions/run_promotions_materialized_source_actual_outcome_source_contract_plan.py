from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Sequence

import pandas as pd


OUTPUT_FOLDER_NAME = "materialized_source_actual_outcome_source_contract_plan"
REMEDIATION_FOLDER_NAME = "materialized_source_actual_outcome_remediation_plan"
SOURCE_MATERIALIZED_FOLDER_NAME = "source_materialized_promotions"

REMEDIATION_SUMMARY_FILE_NAME = "actual_outcome_remediation_summary.csv"
REMEDIATION_SCHEMA_FILE_NAME = "actual_outcome_source_schema_diagnosis.csv"
REMEDIATION_CONTRACT_FILE_NAME = "actual_outcome_required_contract.csv"

SOURCE_CONTRACT_SUMMARY_FILE_NAME = "actual_outcome_source_contract_summary.csv"
SOURCE_CONTRACT_SCHEMA_FILE_NAME = "actual_outcome_source_contract_schema.csv"
SOURCE_CONTRACT_GATES_FILE_NAME = "actual_outcome_source_contract_validation_gates.csv"
SOURCE_CONTRACT_TRUTH_FILE_NAME = "actual_outcome_source_contract_source_of_truth.csv"
SOURCE_CONTRACT_BUILD_SEQUENCE_FILE_NAME = "actual_outcome_source_contract_build_sequence.csv"
SOURCE_CONTRACT_VALIDATION_FILE_NAME = "actual_outcome_source_contract_validation.csv"
SOURCE_CONTRACT_MEMO_FILE_NAME = "actual_outcome_source_contract_memo.md"

STATUS_READY = "ACTUAL_OUTCOME_SOURCE_CONTRACT_READY"
SOURCE_TRUTH_RECOMMENDED = "TRANSACTION_AND_SALES_ACTUALS"
SOURCE_TRUTH_REJECTED = "INSPECTION_REVIEW_PACKET"

SUMMARY_COLUMNS: tuple[str, ...] = (
    "metric_name",
    "metric_value",
    "metric_display",
    "notes",
)

CONTRACT_SCHEMA_COLUMNS: tuple[str, ...] = (
    "field_name",
    "required_flag",
    "field_group",
    "data_type",
    "null_allowed_flag",
    "notes",
)

VALIDATION_GATES_COLUMNS: tuple[str, ...] = (
    "gate_order",
    "gate_name",
    "gate_required_flag",
    "gate_scope",
    "pass_criteria",
    "blocking_flag",
)

SOURCE_OF_TRUTH_COLUMNS: tuple[str, ...] = (
    "source_option",
    "recommended_flag",
    "allowed_for_governed_actual_outcome_flag",
    "reason",
)

BUILD_SEQUENCE_COLUMNS: tuple[str, ...] = (
    "step_order",
    "step_name",
    "step_type",
    "runtime_name",
    "output_expectation",
    "notes",
)

VALIDATION_COLUMNS: tuple[str, ...] = (
    "validation_name",
    "validation_status",
    "validation_flag",
    "details",
)

REQUIRED_JOIN_KEYS: tuple[str, ...] = (
    "store_number",
    "promotion_start_date",
    "promotion_name",
    "sku_number",
)

REQUIRED_OUTCOME_FIELDS: tuple[str, ...] = (
    "actual_units",
    "actual_sales_ex_gst",
    "actual_gross_profit",
    "actual_stockout_flag",
    "actual_leftover_units",
    "actual_result_source",
    "actual_result_as_of_date",
)

OPTIONAL_GOVERNANCE_METADATA: tuple[str, ...] = (
    "actual_outcome_window_start_date",
    "actual_outcome_window_end_date",
    "currency_code",
    "data_version_id",
    "extraction_run_id",
    "actual_stockout_flag_confidence",
    "actual_stockout_flag_source",
    "actual_stockout_flag_basis",
    "actual_stockout_observed_at_grain",
)


class PromotionsMaterializedSourceActualOutcomeSourceContractPlanError(RuntimeError):
    pass


@dataclass(frozen=True)
class PromotionsMaterializedSourceActualOutcomeSourceContractPlanResult:
    contract_status: str
    promotion_key: str
    promotion_folder_name: str
    governed_destination_path: str
    source_of_truth_recommendation: str
    promotion_outcome_window_start: str
    promotion_outcome_window_end: str
    canonical_grain: str
    validation_gate_count: int
    actual_outcome_source_created_flag: int
    source_packets_mutated_flag: int
    operator_audit_overwritten_flag: int
    summary_frame: pd.DataFrame
    contract_schema_frame: pd.DataFrame
    validation_gates_frame: pd.DataFrame
    source_of_truth_frame: pd.DataFrame
    build_sequence_frame: pd.DataFrame
    validation_frame: pd.DataFrame
    memo_markdown: str


@dataclass(frozen=True)
class PromotionsMaterializedSourceActualOutcomeSourceContractPlanArtifacts:
    output_root: str
    summary_csv_path: str
    contract_schema_csv_path: str
    validation_gates_csv_path: str
    source_of_truth_csv_path: str
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
        raise PromotionsMaterializedSourceActualOutcomeSourceContractPlanError(f"CSV not found: {csv_path}")
    try:
        frame = pd.read_csv(csv_path, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceActualOutcomeSourceContractPlanError(f"CSV is empty: {csv_path}")
    if frame.empty and not allow_empty:
        raise PromotionsMaterializedSourceActualOutcomeSourceContractPlanError(f"CSV is empty: {csv_path}")
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
        raise PromotionsMaterializedSourceActualOutcomeSourceContractPlanError(
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


def _contract_schema_frame() -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    for field in REQUIRED_JOIN_KEYS:
        rows.append(
            {
                "field_name": field,
                "required_flag": 1,
                "field_group": "JOIN_KEY_REQUIRED",
                "data_type": "string",
                "null_allowed_flag": 0,
                "notes": "Required approved join key field.",
            }
        )

    for field in REQUIRED_OUTCOME_FIELDS:
        dtype = "numeric"
        if field == "actual_stockout_flag":
            dtype = "boolean_or_0_1"
        elif field in {"actual_result_source", "actual_result_as_of_date"}:
            dtype = "string_or_date"
        rows.append(
            {
                "field_name": field,
                "required_flag": 1,
                "field_group": "OUTCOME_REQUIRED",
                "data_type": dtype,
                "null_allowed_flag": 0,
                "notes": "Required governed outcome field.",
            }
        )

    for field in OPTIONAL_GOVERNANCE_METADATA:
        rows.append(
            {
                "field_name": field,
                "required_flag": 0,
                "field_group": "GOVERNANCE_METADATA_OPTIONAL",
                "data_type": "string_or_date",
                "null_allowed_flag": 1,
                "notes": "Optional governance metadata for traceability.",
            }
        )

    return pd.DataFrame(rows, columns=CONTRACT_SCHEMA_COLUMNS)


def _validation_gates_frame() -> pd.DataFrame:
    rows = [
        {
            "gate_order": 1,
            "gate_name": "SCHEMA_GATE",
            "gate_required_flag": 1,
            "gate_scope": "file",
            "pass_criteria": "All required columns are present.",
            "blocking_flag": 1,
        },
        {
            "gate_order": 2,
            "gate_name": "KEY_COMPLETENESS_GATE",
            "gate_required_flag": 1,
            "gate_scope": "row",
            "pass_criteria": "No blank store_number, promotion_start_date, promotion_name, sku_number.",
            "blocking_flag": 1,
        },
        {
            "gate_order": 3,
            "gate_name": "KEY_UNIQUENESS_GATE",
            "gate_required_flag": 1,
            "gate_scope": "dataset",
            "pass_criteria": "No duplicates at canonical governed grain.",
            "blocking_flag": 1,
        },
        {
            "gate_order": 4,
            "gate_name": "NUMERIC_QUALITY_GATE",
            "gate_required_flag": 1,
            "gate_scope": "row",
            "pass_criteria": "actual_units, actual_sales_ex_gst, actual_gross_profit, actual_leftover_units parse as numeric.",
            "blocking_flag": 1,
        },
        {
            "gate_order": 5,
            "gate_name": "BOOLEAN_QUALITY_GATE",
            "gate_required_flag": 1,
            "gate_scope": "row",
            "pass_criteria": "actual_stockout_flag is valid boolean or 0/1.",
            "blocking_flag": 1,
        },
        {
            "gate_order": 6,
            "gate_name": "STOCKOUT_TRUTH_GATE",
            "gate_required_flag": 1,
            "gate_scope": "row",
            "pass_criteria": "actual_stockout_flag=1 requires explicit governed stockout evidence, actual_stockout_flag=0 requires explicit sufficient-stock evidence, and unknown must not be silently coerced to 0.",
            "blocking_flag": 1,
        },
        {
            "gate_order": 7,
            "gate_name": "STOCKOUT_PROVENANCE_GATE",
            "gate_required_flag": 1,
            "gate_scope": "row",
            "pass_criteria": "When actual_stockout_flag is known, actual_stockout_flag_source, actual_stockout_flag_basis, and actual_stockout_flag_confidence must be populated with governed values.",
            "blocking_flag": 1,
        },
        {
            "gate_order": 8,
            "gate_name": "PROVENANCE_GATE",
            "gate_required_flag": 1,
            "gate_scope": "row",
            "pass_criteria": "actual_result_source and actual_result_as_of_date populated.",
            "blocking_flag": 1,
        },
        {
            "gate_order": 9,
            "gate_name": "WINDOW_GATE",
            "gate_required_flag": 1,
            "gate_scope": "dataset",
            "pass_criteria": "Outcome window equals promotion window unless explicitly overridden.",
            "blocking_flag": 1,
        },
        {
            "gate_order": 10,
            "gate_name": "COVERAGE_GATE",
            "gate_required_flag": 1,
            "gate_scope": "dataset",
            "pass_criteria": "Stage 1 can validate approved join key without row explosion risk.",
            "blocking_flag": 1,
        },
        {
            "gate_order": 11,
            "gate_name": "SAFETY_GATE",
            "gate_required_flag": 1,
            "gate_scope": "packet",
            "pass_criteria": "promotion_source_rows.csv and operator_audit_source.csv remain unchanged.",
            "blocking_flag": 1,
        },
        {
            "gate_order": 12,
            "gate_name": "PROMOTION_GATE",
            "gate_required_flag": 1,
            "gate_scope": "planner",
            "pass_criteria": "Planner does not create governed actual_outcome_source.csv.",
            "blocking_flag": 1,
        },
    ]
    return pd.DataFrame(rows, columns=VALIDATION_GATES_COLUMNS)


def _source_of_truth_frame() -> pd.DataFrame:
    rows = [
        {
            "source_option": SOURCE_TRUTH_RECOMMENDED,
            "recommended_flag": 1,
            "allowed_for_governed_actual_outcome_flag": 1,
            "reason": "Use POS or transaction or sales or inventory actuals for SKU-level truth.",
        },
        {
            "source_option": SOURCE_TRUTH_REJECTED,
            "recommended_flag": 0,
            "allowed_for_governed_actual_outcome_flag": 0,
            "reason": "Inspection review packet lacks SKU-level identity for governed actual outcomes.",
        },
    ]
    return pd.DataFrame(rows, columns=SOURCE_OF_TRUTH_COLUMNS)


def _build_sequence_frame() -> pd.DataFrame:
    rows = [
        {
            "step_order": 1,
            "step_name": "ACTUAL_OUTCOME_SOURCE_CONTRACT_PLAN",
            "step_type": "planner",
            "runtime_name": "run_promotions_materialized_source_actual_outcome_source_contract_plan.py",
            "output_expectation": "Contract schema, validation gates, source-of-truth, build sequence.",
            "notes": "Planner-only, no governed source creation.",
        },
        {
            "step_order": 2,
            "step_name": "ACTUAL_OUTCOME_SOURCE_BUILDER",
            "step_type": "builder",
            "runtime_name": "run_promotions_materialized_source_actual_outcome_build_source.py",
            "output_expectation": "Draft SKU-level actual_outcome source candidate.",
            "notes": "Build from transaction and sales actuals.",
        },
        {
            "step_order": 3,
            "step_name": "ACTUAL_OUTCOME_SOURCE_READINESS",
            "step_type": "readiness",
            "runtime_name": "run_promotions_materialized_source_actual_outcome_promotion_readiness.py",
            "output_expectation": "Readiness decision for governed promotion.",
            "notes": "Apply all contract validation gates.",
        },
        {
            "step_order": 4,
            "step_name": "ACTUAL_OUTCOME_SOURCE_PROMOTION",
            "step_type": "controlled_promotion",
            "runtime_name": "run_promotions_materialized_source_actual_outcome_promote_source.py",
            "output_expectation": "Governed actual_outcome_source.csv in promotion folder.",
            "notes": "Controlled copy only after readiness approval.",
        },
        {
            "step_order": 5,
            "step_name": "RERUN_STAGE1_ONLY",
            "step_type": "validation",
            "runtime_name": "run_promotions_materialized_source_join_key_validator.py",
            "output_expectation": "Re-evaluate Stage 1 with governed ACTUAL_OUTCOME source.",
            "notes": "Stage 1 only.",
        },
        {
            "step_order": 6,
            "step_name": "RERUN_STAGE2_STAGE3_CONDITIONAL",
            "step_type": "conditional_followup",
            "runtime_name": "stage2_stage3_rerun",
            "output_expectation": "Stage 2 and Stage 3 rerun only when Stage 1 is safe.",
            "notes": "Do not proceed if Stage 1 remains blocked.",
        },
    ]
    return pd.DataFrame(rows, columns=BUILD_SEQUENCE_COLUMNS)


def build_promotions_materialized_source_actual_outcome_source_contract_plan(
    *,
    packet_root: str | Path,
    promotion_key: str,
    output_root: str | Path | None = None,
) -> PromotionsMaterializedSourceActualOutcomeSourceContractPlanResult:
    packet_root_path = Path(packet_root)
    remediation_root = packet_root_path / REMEDIATION_FOLDER_NAME

    remediation_summary = _read_csv(remediation_root / REMEDIATION_SUMMARY_FILE_NAME)
    remediation_schema = _read_csv(remediation_root / REMEDIATION_SCHEMA_FILE_NAME)
    remediation_contract = _read_csv(remediation_root / REMEDIATION_CONTRACT_FILE_NAME)

    summary_metrics = _metric_lookup(remediation_summary)

    promotion_folder_name = _normalize_text(summary_metrics.get("PROMOTION_FOLDER_NAME")) or _promotion_folder_from_key(promotion_key)
    source_root = packet_root_path / SOURCE_MATERIALIZED_FOLDER_NAME / promotion_folder_name

    promotion_summary_path = source_root / "promotion_source_summary.csv"
    promotion_rows_path = source_root / "promotion_source_rows.csv"
    operator_audit_path = source_root / "operator_audit_source.csv"
    governed_destination_path = source_root / "actual_outcome_source.csv"

    promotion_summary = _read_csv(promotion_summary_path)
    _ = _read_csv(promotion_rows_path)

    summary_row = promotion_summary.iloc[0]
    promotion_window_start = _normalize_text(summary_row.get("promotion_start_date"))
    promotion_window_end = _normalize_text(summary_row.get("promotion_end_date"))

    source_rows_before = promotion_rows_path.read_bytes() if promotion_rows_path.exists() else b""
    operator_before = operator_audit_path.read_bytes() if operator_audit_path.exists() else b""
    governed_exists_before = int(governed_destination_path.exists())

    contract_schema = _contract_schema_frame()
    validation_gates = _validation_gates_frame()
    source_truth = _source_of_truth_frame()
    build_sequence = _build_sequence_frame()

    source_rows_after = promotion_rows_path.read_bytes() if promotion_rows_path.exists() else b""
    operator_after = operator_audit_path.read_bytes() if operator_audit_path.exists() else b""
    governed_exists_after = int(governed_destination_path.exists())

    source_packets_mutated_flag = int(source_rows_before != source_rows_after)
    operator_audit_overwritten_flag = int(operator_before != operator_after)
    actual_outcome_source_created_flag = int((not governed_exists_before) and governed_exists_after)

    contract_status = STATUS_READY
    canonical_grain = "store_number + promotion_start_date + promotion_name + sku_number"
    gate_count = int(len(validation_gates.index))

    summary_frame = pd.DataFrame(
        [
            _summary_row("CONTRACT_STATUS", contract_status, "Planner-only ACTUAL_OUTCOME source-contract status."),
            _summary_row("PROMOTION_KEY", promotion_key, "Promotion key for governed contract plan."),
            _summary_row("PROMOTION_FOLDER_NAME", promotion_folder_name, "Promotion folder for governed destination."),
            _summary_row("GOVERNED_DESTINATION_PATH", str(governed_destination_path), "Canonical governed ACTUAL_OUTCOME destination."),
            _summary_row("SOURCE_OF_TRUTH_RECOMMENDATION", SOURCE_TRUTH_RECOMMENDED, "Recommended governed source-of-truth for ACTUAL_OUTCOME."),
            _summary_row("PROMOTION_OUTCOME_WINDOW_START", promotion_window_start, "Inclusive promotion outcome window start date."),
            _summary_row("PROMOTION_OUTCOME_WINDOW_END", promotion_window_end, "Inclusive promotion outcome window end date."),
            _summary_row("CANONICAL_GRAIN", canonical_grain, "Canonical governed row grain."),
            _summary_row("VALIDATION_GATE_COUNT", gate_count, "Number of required contract validation gates."),
            _summary_row("ACTUAL_OUTCOME_SOURCE_CREATED_FLAG", actual_outcome_source_created_flag, "Planner must not create actual_outcome_source.csv."),
            _summary_row("SOURCE_PACKETS_MUTATED_FLAG", source_packets_mutated_flag, "Planner must not mutate promotion_source_rows.csv."),
            _summary_row("OPERATOR_AUDIT_OVERWRITTEN_FLAG", operator_audit_overwritten_flag, "Planner must not overwrite operator_audit_source.csv."),
            _summary_row("REMEDIATION_STATUS_USED", _normalize_text(summary_metrics.get("REMEDIATION_STATUS")), "Remediation planner status consumed as input."),
            _summary_row("REMEDIATION_MISSING_JOIN_KEYS", _normalize_text(summary_metrics.get("MISSING_REQUIRED_JOIN_KEYS")), "Missing join keys from remediation diagnosis."),
        ],
        columns=SUMMARY_COLUMNS,
    )

    required_fields_covered = int(
        set(REQUIRED_JOIN_KEYS).issubset(set(contract_schema.loc[contract_schema["required_flag"].eq(1), "field_name"].astype(str)))
        and set(REQUIRED_OUTCOME_FIELDS).issubset(set(contract_schema.loc[contract_schema["required_flag"].eq(1), "field_name"].astype(str)))
    )
    optional_fields_covered = int(
        set(OPTIONAL_GOVERNANCE_METADATA).issubset(set(contract_schema["field_name"].astype(str)))
    )
    rejection_present = int(
        source_truth.loc[
            source_truth["source_option"].astype(str).eq(SOURCE_TRUTH_REJECTED),
            "allowed_for_governed_actual_outcome_flag",
        ].astype(int).eq(0).any()
    )

    validation_frame = pd.DataFrame(
        [
            _validation_row("CONTRACT_STATUS_READY", int(contract_status == STATUS_READY), f"contract_status={contract_status}"),
            _validation_row("REQUIRED_FIELDS_PRESENT", required_fields_covered, "Required join and outcome fields are present in contract schema."),
            _validation_row("OPTIONAL_METADATA_PRESENT", optional_fields_covered, "Optional governance metadata fields are present in contract schema."),
            _validation_row("INSPECTION_PACKET_REJECTED", rejection_present, "Inspection review packet is rejected as governed ACTUAL_OUTCOME truth."),
            _validation_row("VALIDATION_GATES_DEFINED", int(gate_count >= 10), f"validation_gate_count={gate_count}"),
            _validation_row("BUILD_SEQUENCE_DEFINED", int(len(build_sequence.index) == 6), "Planner/build/readiness/promotion/Stage1/conditional Stage2-3 sequence defined."),
            _validation_row("NO_GOVERNED_ACTUAL_SOURCE_CREATED", int(actual_outcome_source_created_flag == 0), f"actual_outcome_source_created_flag={actual_outcome_source_created_flag}"),
            _validation_row("PROMOTION_SOURCE_ROWS_UNCHANGED", int(source_packets_mutated_flag == 0), f"source_packets_mutated_flag={source_packets_mutated_flag}"),
            _validation_row("OPERATOR_AUDIT_UNCHANGED", int(operator_audit_overwritten_flag == 0), f"operator_audit_overwritten_flag={operator_audit_overwritten_flag}"),
            _validation_row("REMEDIATION_INPUTS_READ", int(not remediation_schema.empty and not remediation_contract.empty), "Remediation summary, schema diagnosis, and required contract were consumed."),
        ],
        columns=VALIDATION_COLUMNS,
    )

    memo_markdown = "\n".join(
        [
            "# ACTUAL_OUTCOME Source Contract Plan",
            "",
            "Planner-only governed source-contract artifact.",
            "No ACTUAL_OUTCOME source file is built or promoted by this runtime.",
            "",
            f"Promotion key: {promotion_key}",
            f"Contract status: {contract_status}",
            f"Governed destination path: {governed_destination_path}",
            f"Source-of-truth recommendation: {SOURCE_TRUTH_RECOMMENDED}",
            f"Rejected source: {SOURCE_TRUTH_REJECTED}",
            f"Promotion outcome window: {promotion_window_start} to {promotion_window_end}",
            f"Canonical grain: {canonical_grain}",
            f"Validation gate count: {gate_count}",
            "",
            "Do not build or promote actual_outcome_source.csv until builder and readiness gates are implemented and approved.",
        ]
    )

    return PromotionsMaterializedSourceActualOutcomeSourceContractPlanResult(
        contract_status=contract_status,
        promotion_key=promotion_key,
        promotion_folder_name=promotion_folder_name,
        governed_destination_path=str(governed_destination_path),
        source_of_truth_recommendation=SOURCE_TRUTH_RECOMMENDED,
        promotion_outcome_window_start=promotion_window_start,
        promotion_outcome_window_end=promotion_window_end,
        canonical_grain=canonical_grain,
        validation_gate_count=gate_count,
        actual_outcome_source_created_flag=actual_outcome_source_created_flag,
        source_packets_mutated_flag=source_packets_mutated_flag,
        operator_audit_overwritten_flag=operator_audit_overwritten_flag,
        summary_frame=summary_frame,
        contract_schema_frame=contract_schema,
        validation_gates_frame=validation_gates,
        source_of_truth_frame=source_truth,
        build_sequence_frame=build_sequence,
        validation_frame=validation_frame,
        memo_markdown=memo_markdown,
    )


def write_promotions_materialized_source_actual_outcome_source_contract_plan(
    *,
    packet_root: str | Path,
    promotion_key: str,
    output_root: str | Path | None = None,
) -> PromotionsMaterializedSourceActualOutcomeSourceContractPlanArtifacts:
    packet_root_path = Path(packet_root)
    output_root_path = _resolve_output_root(packet_root_path, output_root)

    result = build_promotions_materialized_source_actual_outcome_source_contract_plan(
        packet_root=packet_root,
        promotion_key=promotion_key,
        output_root=output_root,
    )

    output_root_path.mkdir(parents=True, exist_ok=True)

    summary_path = output_root_path / SOURCE_CONTRACT_SUMMARY_FILE_NAME
    schema_path = output_root_path / SOURCE_CONTRACT_SCHEMA_FILE_NAME
    gates_path = output_root_path / SOURCE_CONTRACT_GATES_FILE_NAME
    truth_path = output_root_path / SOURCE_CONTRACT_TRUTH_FILE_NAME
    sequence_path = output_root_path / SOURCE_CONTRACT_BUILD_SEQUENCE_FILE_NAME
    validation_path = output_root_path / SOURCE_CONTRACT_VALIDATION_FILE_NAME
    memo_path = output_root_path / SOURCE_CONTRACT_MEMO_FILE_NAME

    result.summary_frame.to_csv(summary_path, index=False)
    result.contract_schema_frame.to_csv(schema_path, index=False)
    result.validation_gates_frame.to_csv(gates_path, index=False)
    result.source_of_truth_frame.to_csv(truth_path, index=False)
    result.build_sequence_frame.to_csv(sequence_path, index=False)
    result.validation_frame.to_csv(validation_path, index=False)
    memo_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsMaterializedSourceActualOutcomeSourceContractPlanArtifacts(
        output_root=str(output_root_path),
        summary_csv_path=str(summary_path),
        contract_schema_csv_path=str(schema_path),
        validation_gates_csv_path=str(gates_path),
        source_of_truth_csv_path=str(truth_path),
        build_sequence_csv_path=str(sequence_path),
        validation_csv_path=str(validation_path),
        memo_md_path=str(memo_path),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a planner-only ACTUAL_OUTCOME governed source-contract artifact for a promotion."
    )
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--promotion-key", required=True)
    parser.add_argument("--output-root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    artifacts = write_promotions_materialized_source_actual_outcome_source_contract_plan(
        packet_root=args.packet_root,
        promotion_key=args.promotion_key,
        output_root=args.output_root,
    )
    summary = _read_csv(artifacts.summary_csv_path, allow_empty=True)
    metrics = _metric_lookup(summary)

    print("contract_status", _normalize_text(metrics.get("CONTRACT_STATUS", "")))
    print("governed_destination_path", _normalize_text(metrics.get("GOVERNED_DESTINATION_PATH", "")))
    print("required_join_keys", "; ".join(REQUIRED_JOIN_KEYS))
    print("required_outcome_fields", "; ".join(REQUIRED_OUTCOME_FIELDS))
    print("optional_governance_metadata", "; ".join(OPTIONAL_GOVERNANCE_METADATA))
    print("source_of_truth_recommendation", _normalize_text(metrics.get("SOURCE_OF_TRUTH_RECOMMENDATION", "")))
    print("promotion_outcome_window_start", _normalize_text(metrics.get("PROMOTION_OUTCOME_WINDOW_START", "")))
    print("promotion_outcome_window_end", _normalize_text(metrics.get("PROMOTION_OUTCOME_WINDOW_END", "")))
    print("grain", _normalize_text(metrics.get("CANONICAL_GRAIN", "")))
    print("validation_gate_count", _normalize_text(metrics.get("VALIDATION_GATE_COUNT", 0)))
    print("actual_outcome_source_created_flag", _normalize_text(metrics.get("ACTUAL_OUTCOME_SOURCE_CREATED_FLAG", 0)))
    print("source_packets_mutated_flag", _normalize_text(metrics.get("SOURCE_PACKETS_MUTATED_FLAG", 0)))
    print("operator_audit_overwritten_flag", _normalize_text(metrics.get("OPERATOR_AUDIT_OVERWRITTEN_FLAG", 0)))
    print("actual_outcome_source_contract_summary", artifacts.summary_csv_path)
    print("actual_outcome_source_contract_schema", artifacts.contract_schema_csv_path)
    print("actual_outcome_source_contract_validation_gates", artifacts.validation_gates_csv_path)
    print("actual_outcome_source_contract_source_of_truth", artifacts.source_of_truth_csv_path)
    print("actual_outcome_source_contract_build_sequence", artifacts.build_sequence_csv_path)
    print("actual_outcome_source_contract_validation", artifacts.validation_csv_path)
    print("actual_outcome_source_contract_memo", artifacts.memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
