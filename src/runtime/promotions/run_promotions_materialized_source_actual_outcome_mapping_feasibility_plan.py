from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Sequence

import pandas as pd


OUTPUT_FOLDER_NAME = "materialized_source_actual_outcome_mapping_feasibility_plan"
SOURCE_CONTRACT_FOLDER_NAME = "materialized_source_actual_outcome_source_contract_plan"
SOURCE_MATERIALIZED_FOLDER_NAME = "source_materialized_promotions"

SOURCE_CONTRACT_SUMMARY_FILE_NAME = "actual_outcome_source_contract_summary.csv"
SOURCE_CONTRACT_SCHEMA_FILE_NAME = "actual_outcome_source_contract_schema.csv"
PROMOTION_SOURCE_ROWS_FILE_NAME = "promotion_source_rows.csv"
OPERATOR_AUDIT_FILE_NAME = "operator_audit_source.csv"
ACTUAL_OUTCOME_FILE_NAME = "actual_outcome_source.csv"

SUMMARY_FILE_NAME = "actual_outcome_mapping_feasibility_summary.csv"
FIELD_MAP_FILE_NAME = "actual_outcome_mapping_field_map.csv"
DERIVATION_RULES_FILE_NAME = "actual_outcome_mapping_derivation_rules.csv"
BLOCKERS_FILE_NAME = "actual_outcome_mapping_blockers.csv"
VALIDATION_FILE_NAME = "actual_outcome_mapping_validation.csv"
MEMO_FILE_NAME = "actual_outcome_mapping_memo.md"

STATUS_READY = "ACTUAL_OUTCOME_MAPPING_READY"
STATUS_BLOCKED_DERIVATION = "ACTUAL_OUTCOME_MAPPING_BLOCKED_DERIVATION_FIELDS_MISSING"
STATUS_BLOCKED_REQUIRED = "ACTUAL_OUTCOME_MAPPING_BLOCKED_REQUIRED_FIELDS_MISSING"
STATUS_BLOCKED_SOURCE_NOT_FOUND = "ACTUAL_OUTCOME_MAPPING_BLOCKED_SOURCE_NOT_FOUND"

DIRECT_MAPPINGS: tuple[tuple[str, str], ...] = (
    ("store_number", "store_number"),
    ("promotion_start_date", "promotion_start_date"),
    ("promotion_name", "promotion_name"),
    ("sku_number", "sku_number"),
    ("actual_units", "actual_units_sold"),
    ("actual_sales_ex_gst", "actual_sales_ex_gst"),
    ("actual_gross_profit", "gross_profit_promo_dollars"),
    ("actual_result_source", "realised_sales_source_table_name"),
    ("actual_result_as_of_date", "extraction_as_of_date"),
)

DERIVATION_FIELDS: tuple[str, ...] = ("actual_stockout_flag", "actual_leftover_units")

TRUSTED_STOCKOUT_SIGNAL_COLUMNS: tuple[str, ...] = (
    "actual_stockout_indicator",
    "stockout_flag",
    "out_of_stock_flag",
    "oos_flag",
    "stockout_evidence_flag",
)

TRUSTED_SUFFICIENT_STOCK_SIGNAL_COLUMNS: tuple[str, ...] = (
    "sufficient_stock_window_flag",
    "explicit_sufficient_stock_flag",
    "stock_available_through_window_flag",
)

LEFTOVER_DERIVATION_PRIMARY_COLUMNS: tuple[str, ...] = (
    "ending_soh",
    "ending_stock_on_hand",
    "final_soh",
    "promo_ending_soh",
    "estimated_stock_left_after_promo",
)

LEFTOVER_DERIVATION_SECONDARY_COLUMNS: tuple[str, ...] = (
    "pl_allocation_qty",
    "actual_units_sold",
)

SUMMARY_COLUMNS: tuple[str, ...] = (
    "metric_name",
    "metric_value",
    "metric_display",
    "notes",
)

FIELD_MAP_COLUMNS: tuple[str, ...] = (
    "target_field",
    "source_field",
    "mapping_type",
    "mapping_status",
    "mapping_notes",
)

DERIVATION_RULE_COLUMNS: tuple[str, ...] = (
    "target_field",
    "rule_name",
    "rule_expression",
    "support_columns_found",
    "derivation_safe_flag",
    "rule_notes",
)

BLOCKERS_COLUMNS: tuple[str, ...] = (
    "blocker_code",
    "blocker_field",
    "severity",
    "blocker_details",
)

VALIDATION_COLUMNS: tuple[str, ...] = (
    "validation_name",
    "validation_status",
    "validation_flag",
    "details",
)


class PromotionsMaterializedSourceActualOutcomeMappingFeasibilityPlanError(RuntimeError):
    pass


@dataclass(frozen=True)
class PromotionsMaterializedSourceActualOutcomeMappingFeasibilityPlanResult:
    mapping_feasibility_status: str
    promotion_key: str
    promotion_folder_name: str
    source_candidate_path: str
    source_row_count: int
    actual_outcome_source_created_flag: int
    source_packets_mutated_flag: int
    operator_audit_overwritten_flag: int
    summary_frame: pd.DataFrame
    field_map_frame: pd.DataFrame
    derivation_rules_frame: pd.DataFrame
    blockers_frame: pd.DataFrame
    validation_frame: pd.DataFrame
    memo_markdown: str


@dataclass(frozen=True)
class PromotionsMaterializedSourceActualOutcomeMappingFeasibilityPlanArtifacts:
    output_root: str
    summary_csv_path: str
    field_map_csv_path: str
    derivation_rules_csv_path: str
    blockers_csv_path: str
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
        raise PromotionsMaterializedSourceActualOutcomeMappingFeasibilityPlanError(f"CSV not found: {csv_path}")
    try:
        frame = pd.read_csv(csv_path, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceActualOutcomeMappingFeasibilityPlanError(f"CSV is empty: {csv_path}")
    if frame.empty and not allow_empty:
        raise PromotionsMaterializedSourceActualOutcomeMappingFeasibilityPlanError(f"CSV is empty: {csv_path}")
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
        raise PromotionsMaterializedSourceActualOutcomeMappingFeasibilityPlanError(
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


def _lower_columns(frame: pd.DataFrame) -> dict[str, str]:
    return {column.lower(): column for column in frame.columns}


def _derive_stockout_support(columns_lower: dict[str, str]) -> tuple[int, str, int, list[str], int, list[str]]:
    positive_found = [columns_lower[name] for name in TRUSTED_STOCKOUT_SIGNAL_COLUMNS if name in columns_lower]
    sufficient_found = [columns_lower[name] for name in TRUSTED_SUFFICIENT_STOCK_SIGNAL_COLUMNS if name in columns_lower]
    ready_flag = int(bool(positive_found) and bool(sufficient_found))
    if ready_flag:
        return ready_flag, "TRUSTED_SIGNAL_PRESENT", 0, positive_found, 0, sufficient_found
    return 0, "NO_TRUSTED_SIGNAL", 1, positive_found, 0, sufficient_found


def _derive_leftover_support(columns_lower: dict[str, str]) -> tuple[int, list[str]]:
    primary_found = [columns_lower[name] for name in LEFTOVER_DERIVATION_PRIMARY_COLUMNS if name in columns_lower]
    if primary_found:
        return 1, primary_found
    secondary_found = [columns_lower[name] for name in LEFTOVER_DERIVATION_SECONDARY_COLUMNS if name in columns_lower]
    if len(secondary_found) == len(LEFTOVER_DERIVATION_SECONDARY_COLUMNS):
        return 1, secondary_found
    return 0, secondary_found


def _source_row_count(source_path: Path) -> int:
    with source_path.open("r", encoding="utf-8", errors="ignore") as handle:
        count = sum(1 for _ in handle)
    return max(count - 1, 0)


def build_promotions_materialized_source_actual_outcome_mapping_feasibility_plan(
    *,
    packet_root: str | Path,
    promotion_key: str,
    output_root: str | Path | None = None,
) -> PromotionsMaterializedSourceActualOutcomeMappingFeasibilityPlanResult:
    packet_root_path = Path(packet_root)
    source_contract_root = packet_root_path / SOURCE_CONTRACT_FOLDER_NAME

    contract_summary = _read_csv(source_contract_root / SOURCE_CONTRACT_SUMMARY_FILE_NAME)
    _ = _read_csv(source_contract_root / SOURCE_CONTRACT_SCHEMA_FILE_NAME)
    _ = _metric_lookup(contract_summary)

    promotion_folder_name = _promotion_folder_from_key(promotion_key)
    source_folder = packet_root_path / SOURCE_MATERIALIZED_FOLDER_NAME / promotion_folder_name
    source_candidate_path = source_folder / PROMOTION_SOURCE_ROWS_FILE_NAME
    operator_audit_path = source_folder / OPERATOR_AUDIT_FILE_NAME
    governed_destination_path = source_folder / ACTUAL_OUTCOME_FILE_NAME

    source_rows_before = source_candidate_path.read_bytes() if source_candidate_path.exists() else b""
    operator_before = operator_audit_path.read_bytes() if operator_audit_path.exists() else b""
    governed_exists_before = int(governed_destination_path.exists())

    blockers_rows: list[dict[str, object]] = []

    if not source_candidate_path.exists():
        status = STATUS_BLOCKED_SOURCE_NOT_FOUND
        source_frame = pd.DataFrame()
        source_row_count = 0
    else:
        source_frame = _read_csv(source_candidate_path)
        source_row_count = _source_row_count(source_candidate_path)
        columns_lower = _lower_columns(source_frame)

        field_map_rows: list[dict[str, object]] = []
        missing_direct: list[str] = []

        for target_field, source_field in DIRECT_MAPPINGS:
            mapped = source_field.lower() in columns_lower
            field_map_rows.append(
                {
                    "target_field": target_field,
                    "source_field": source_field,
                    "mapping_type": "DIRECT",
                    "mapping_status": "MAPPED" if mapped else "MISSING",
                    "mapping_notes": "Direct source-to-contract field mapping.",
                }
            )
            if not mapped:
                missing_direct.append(target_field)
                blockers_rows.append(
                    {
                        "blocker_code": "MISSING_DIRECT_FIELD",
                        "blocker_field": target_field,
                        "severity": "BLOCKER",
                        "blocker_details": f"Required direct source column missing: {source_field}",
                    }
                )

        (
            stockout_supported,
            stockout_support_status,
            stockout_unknown_required,
            stockout_positive_columns,
            stockout_ready_flag,
            stockout_sufficient_columns,
        ) = _derive_stockout_support(columns_lower)
        leftover_supported, leftover_columns = _derive_leftover_support(columns_lower)

        field_map_rows.append(
            {
                "target_field": "actual_stockout_flag",
                "source_field": "; ".join(stockout_positive_columns + stockout_sufficient_columns),
                "mapping_type": "DERIVED",
                "mapping_status": "DERIVABLE" if stockout_supported else "MISSING_DERIVATION_SUPPORT",
                "mapping_notes": "Requires explicit governed stockout evidence for 1 and explicit sufficient-stock evidence for 0; unknown must not be coerced to 0.",
            }
        )
        field_map_rows.append(
            {
                "target_field": "actual_leftover_units",
                "source_field": "; ".join(leftover_columns),
                "mapping_type": "DERIVED",
                "mapping_status": "DERIVABLE" if leftover_supported else "MISSING_DERIVATION_SUPPORT",
                "mapping_notes": "Requires ending-stock column or allocation-minus-sales support columns.",
            }
        )

        if not stockout_supported:
            blockers_rows.append(
                {
                    "blocker_code": "TRUSTED_STOCKOUT_SIGNAL_MISSING",
                    "blocker_field": "actual_stockout_flag",
                    "severity": "BLOCKER",
                    "blocker_details": "No trusted stockout truth signal and sufficient-stock signal pair found; unknown stockout must not be coerced to 0.",
                }
            )
        if not leftover_supported:
            blockers_rows.append(
                {
                    "blocker_code": "DERIVATION_SUPPORT_MISSING",
                    "blocker_field": "actual_leftover_units",
                    "severity": "BLOCKER",
                    "blocker_details": "No safe leftover derivation support columns found.",
                }
            )

        if missing_direct:
            status = STATUS_BLOCKED_REQUIRED
        elif not stockout_supported or not leftover_supported:
            status = STATUS_BLOCKED_DERIVATION
        else:
            status = STATUS_READY

    if not source_candidate_path.exists():
        field_map_frame = pd.DataFrame(
            [
                {
                    "target_field": target_field,
                    "source_field": source_field,
                    "mapping_type": "DIRECT",
                    "mapping_status": "SOURCE_NOT_FOUND",
                    "mapping_notes": "Source candidate file missing.",
                }
                for target_field, source_field in DIRECT_MAPPINGS
            ]
            + [
                {
                    "target_field": field,
                    "source_field": "",
                    "mapping_type": "DERIVED",
                    "mapping_status": "SOURCE_NOT_FOUND",
                    "mapping_notes": "Source candidate file missing.",
                }
                for field in DERIVATION_FIELDS
            ],
            columns=FIELD_MAP_COLUMNS,
        )
        derivation_rules_frame = pd.DataFrame(
            [
                {
                    "target_field": "actual_stockout_flag",
                    "rule_name": "STOCKOUT_DERIVATION",
                    "rule_expression": "BLOCKED_SOURCE_NOT_FOUND",
                    "support_columns_found": "",
                    "derivation_safe_flag": 0,
                    "rule_notes": "Cannot evaluate derivation safety without source file.",
                },
                {
                    "target_field": "actual_leftover_units",
                    "rule_name": "LEFTOVER_DERIVATION",
                    "rule_expression": "BLOCKED_SOURCE_NOT_FOUND",
                    "support_columns_found": "",
                    "derivation_safe_flag": 0,
                    "rule_notes": "Cannot evaluate derivation safety without source file.",
                },
            ],
            columns=DERIVATION_RULE_COLUMNS,
        )
        blockers_rows.append(
            {
                "blocker_code": "SOURCE_NOT_FOUND",
                "blocker_field": "promotion_source_rows.csv",
                "severity": "BLOCKER",
                "blocker_details": f"Source candidate not found at {source_candidate_path}",
            }
        )
    else:
        columns_lower = _lower_columns(source_frame)
        (
            stockout_supported,
            stockout_support_status,
            stockout_unknown_required,
            stockout_positive_columns,
            stockout_ready_flag,
            stockout_sufficient_columns,
        ) = _derive_stockout_support(columns_lower)
        leftover_supported, leftover_columns = _derive_leftover_support(columns_lower)

        field_map_frame = pd.DataFrame(field_map_rows, columns=FIELD_MAP_COLUMNS)
        derivation_rules_frame = pd.DataFrame(
            [
                {
                    "target_field": "actual_stockout_flag",
                    "rule_name": "STOCKOUT_DERIVATION",
                    "rule_expression": "Set 1 only from trusted realized stockout signal, set 0 only from explicit sufficient-stock signal, otherwise preserve unknown and never coerce to 0.",
                    "support_columns_found": "; ".join(stockout_positive_columns + stockout_sufficient_columns),
                    "derivation_safe_flag": int(stockout_supported),
                    "rule_notes": "Safe only when both trusted stockout-positive and trusted sufficient-stock signals exist; low sales, low cover, allocation-minus-sales, and current SOH alone are not stockout truth.",
                },
                {
                    "target_field": "actual_leftover_units",
                    "rule_name": "LEFTOVER_DERIVATION",
                    "rule_expression": "Prefer ending stock-on-hand; fallback to max(pl_allocation_qty - actual_units_sold, 0) when both columns exist.",
                    "support_columns_found": "; ".join(leftover_columns),
                    "derivation_safe_flag": int(leftover_supported),
                    "rule_notes": "Safe only when explicit ending-stock column exists or allocation-and-sales columns both exist.",
                },
            ],
            columns=DERIVATION_RULE_COLUMNS,
        )

    blockers_frame = pd.DataFrame(blockers_rows, columns=BLOCKERS_COLUMNS)

    source_rows_after = source_candidate_path.read_bytes() if source_candidate_path.exists() else b""
    operator_after = operator_audit_path.read_bytes() if operator_audit_path.exists() else b""
    governed_exists_after = int(governed_destination_path.exists())

    source_packets_mutated_flag = int(source_rows_before != source_rows_after)
    operator_audit_overwritten_flag = int(operator_before != operator_after)
    actual_outcome_source_created_flag = int((not governed_exists_before) and governed_exists_after)

    direct_mapped_count = int(field_map_frame.loc[field_map_frame["mapping_type"].eq("DIRECT") & field_map_frame["mapping_status"].eq("MAPPED")].shape[0])

    summary_frame = pd.DataFrame(
        [
            _summary_row("MAPPING_FEASIBILITY_STATUS", status, "Planner-only ACTUAL_OUTCOME mapping feasibility status."),
            _summary_row("PROMOTION_KEY", promotion_key, "Promotion key under assessment."),
            _summary_row("PROMOTION_FOLDER_NAME", promotion_folder_name, "Promotion-scoped source folder."),
            _summary_row("SOURCE_CANDIDATE_PATH", str(source_candidate_path), "Local source seed candidate path."),
            _summary_row("SOURCE_CANDIDATE_EXISTS_FLAG", int(source_candidate_path.exists()), "Whether promotion_source_rows.csv exists."),
            _summary_row("SOURCE_CANDIDATE_ROW_COUNT", source_row_count, "Source candidate row count."),
            _summary_row("DIRECT_MAPPINGS_AVAILABLE_COUNT", direct_mapped_count, "Count of successful direct mappings."),
            _summary_row("DERIVATION_FIELDS", "; ".join(DERIVATION_FIELDS), "Fields that require derivation rules."),
            _summary_row("ACTUAL_STOCKOUT_FLAG_SUPPORT", stockout_support_status if source_candidate_path.exists() else "SOURCE_NOT_FOUND", "Trusted stockout support assessment."),
            _summary_row("ACTUAL_STOCKOUT_UNKNOWN_REQUIRED", stockout_unknown_required if source_candidate_path.exists() else 1, "Unknown stockout must be preserved when trusted signal is absent."),
            _summary_row("ACTUAL_STOCKOUT_READY_FLAG", stockout_ready_flag if source_candidate_path.exists() else 0, "Whether stockout can be mapped without coercing unknown to zero."),
            _summary_row(
                "DERIVATION_SUPPORT_STOCKOUT_FLAG",
                int(
                    derivation_rules_frame.loc[
                        derivation_rules_frame["target_field"].astype(str).eq("actual_stockout_flag"),
                        "derivation_safe_flag",
                    ].astype(int).max()
                    if not derivation_rules_frame.empty
                    else 0
                ),
                "Safe stockout derivation support found.",
            ),
            _summary_row(
                "DERIVATION_SUPPORT_LEFTOVER_UNITS",
                int(
                    derivation_rules_frame.loc[
                        derivation_rules_frame["target_field"].astype(str).eq("actual_leftover_units"),
                        "derivation_safe_flag",
                    ].astype(int).max()
                    if not derivation_rules_frame.empty
                    else 0
                ),
                "Safe leftover derivation support found.",
            ),
            _summary_row("BLOCKER_COUNT", int(blockers_frame.shape[0]), "Total blocker rows."),
            _summary_row("ACTUAL_OUTCOME_SOURCE_CREATED_FLAG", actual_outcome_source_created_flag, "Planner must not create actual_outcome_source.csv."),
            _summary_row("SOURCE_PACKETS_MUTATED_FLAG", source_packets_mutated_flag, "Planner must not mutate promotion_source_rows.csv."),
            _summary_row("OPERATOR_AUDIT_OVERWRITTEN_FLAG", operator_audit_overwritten_flag, "Planner must not overwrite operator_audit_source.csv."),
        ],
        columns=SUMMARY_COLUMNS,
    )

    validation_frame = pd.DataFrame(
        [
            _validation_row("SOURCE_CANDIDATE_FOUND", int(source_candidate_path.exists()), f"source_candidate_path={source_candidate_path}"),
            _validation_row(
                "DIRECT_MAPPINGS_COVERED",
                int(
                    field_map_frame.loc[
                        field_map_frame["mapping_type"].eq("DIRECT") & field_map_frame["mapping_status"].eq("MAPPED")
                    ].shape[0]
                    == len(DIRECT_MAPPINGS)
                ),
                "All required direct mappings are present.",
            ),
            _validation_row(
                "DERIVATION_FIELDS_RECORDED",
                int(
                    set(field_map_frame.loc[field_map_frame["mapping_type"].eq("DERIVED"), "target_field"].astype(str))
                    == set(DERIVATION_FIELDS)
                ),
                "Both required derivation fields are recorded.",
            ),
            _validation_row(
                "UNKNOWN_STOCKOUT_NOT_COERCED_TO_ZERO",
                int(not (stockout_unknown_required == 0 and stockout_ready_flag == 0)),
                f"actual_stockout_flag_support={stockout_support_status if source_candidate_path.exists() else 'SOURCE_NOT_FOUND'}",
            ),
            _validation_row("NO_ACTUAL_OUTCOME_SOURCE_CREATED", int(actual_outcome_source_created_flag == 0), "Planner-only runtime creates no governed ACTUAL_OUTCOME file."),
            _validation_row("SOURCE_PACKETS_UNCHANGED", int(source_packets_mutated_flag == 0), "Source packet remains unchanged."),
            _validation_row("OPERATOR_AUDIT_UNCHANGED", int(operator_audit_overwritten_flag == 0), "Operator audit source remains unchanged."),
            _validation_row(
                "READY_STATUS_ONLY_WHEN_SAFE",
                int(
                    (status == STATUS_READY)
                    == (
                        field_map_frame.loc[
                            field_map_frame["mapping_type"].eq("DIRECT") & field_map_frame["mapping_status"].eq("MAPPED")
                        ].shape[0]
                        == len(DIRECT_MAPPINGS)
                        and derivation_rules_frame["derivation_safe_flag"].astype(int).eq(1).all()
                    )
                ),
                f"mapping_feasibility_status={status}",
            ),
        ],
        columns=VALIDATION_COLUMNS,
    )

    memo_markdown = "\n".join(
        [
            "# ACTUAL_OUTCOME Mapping Feasibility Plan",
            "",
            "Planner-only feasibility assessment over local source seed candidate.",
            "No ACTUAL_OUTCOME source file is built or promoted by this runtime.",
            "",
            f"Promotion key: {promotion_key}",
            f"Mapping feasibility status: {status}",
            f"Source candidate: {source_candidate_path}",
            f"Source row count: {source_row_count}",
            f"Stockout support status: {stockout_support_status if source_candidate_path.exists() else 'SOURCE_NOT_FOUND'}",
            "",
            "Direct mappings are evaluated for required contract fields.",
            "Derivation fields are assessed for safe support evidence only; unknown stockout must not be coerced to 0.",
            "Inspection review packet is not used as ACTUAL_OUTCOME source-of-truth.",
        ]
    )

    return PromotionsMaterializedSourceActualOutcomeMappingFeasibilityPlanResult(
        mapping_feasibility_status=status,
        promotion_key=promotion_key,
        promotion_folder_name=promotion_folder_name,
        source_candidate_path=str(source_candidate_path),
        source_row_count=source_row_count,
        actual_outcome_source_created_flag=actual_outcome_source_created_flag,
        source_packets_mutated_flag=source_packets_mutated_flag,
        operator_audit_overwritten_flag=operator_audit_overwritten_flag,
        summary_frame=summary_frame,
        field_map_frame=field_map_frame,
        derivation_rules_frame=derivation_rules_frame,
        blockers_frame=blockers_frame,
        validation_frame=validation_frame,
        memo_markdown=memo_markdown,
    )


def write_promotions_materialized_source_actual_outcome_mapping_feasibility_plan(
    *,
    packet_root: str | Path,
    promotion_key: str,
    output_root: str | Path | None = None,
) -> PromotionsMaterializedSourceActualOutcomeMappingFeasibilityPlanArtifacts:
    packet_root_path = Path(packet_root)
    output_root_path = _resolve_output_root(packet_root_path, output_root)

    result = build_promotions_materialized_source_actual_outcome_mapping_feasibility_plan(
        packet_root=packet_root,
        promotion_key=promotion_key,
        output_root=output_root,
    )

    output_root_path.mkdir(parents=True, exist_ok=True)

    summary_path = output_root_path / SUMMARY_FILE_NAME
    field_map_path = output_root_path / FIELD_MAP_FILE_NAME
    derivation_rules_path = output_root_path / DERIVATION_RULES_FILE_NAME
    blockers_path = output_root_path / BLOCKERS_FILE_NAME
    validation_path = output_root_path / VALIDATION_FILE_NAME
    memo_path = output_root_path / MEMO_FILE_NAME

    result.summary_frame.to_csv(summary_path, index=False)
    result.field_map_frame.to_csv(field_map_path, index=False)
    result.derivation_rules_frame.to_csv(derivation_rules_path, index=False)
    result.blockers_frame.to_csv(blockers_path, index=False)
    result.validation_frame.to_csv(validation_path, index=False)
    memo_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsMaterializedSourceActualOutcomeMappingFeasibilityPlanArtifacts(
        output_root=str(output_root_path),
        summary_csv_path=str(summary_path),
        field_map_csv_path=str(field_map_path),
        derivation_rules_csv_path=str(derivation_rules_path),
        blockers_csv_path=str(blockers_path),
        validation_csv_path=str(validation_path),
        memo_md_path=str(memo_path),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build planner-only ACTUAL_OUTCOME mapping feasibility artifacts for a promotion source candidate."
    )
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--promotion-key", required=True)
    parser.add_argument("--output-root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    artifacts = write_promotions_materialized_source_actual_outcome_mapping_feasibility_plan(
        packet_root=args.packet_root,
        promotion_key=args.promotion_key,
        output_root=args.output_root,
    )

    summary = _read_csv(artifacts.summary_csv_path, allow_empty=True)
    metrics = _metric_lookup(summary)

    print("mapping_feasibility_status", _normalize_text(metrics.get("MAPPING_FEASIBILITY_STATUS", "")))
    print("source_candidate_path", _normalize_text(metrics.get("SOURCE_CANDIDATE_PATH", "")))
    print("source_candidate_row_count", _normalize_text(metrics.get("SOURCE_CANDIDATE_ROW_COUNT", 0)))
    print("direct_mappings_available_count", _normalize_text(metrics.get("DIRECT_MAPPINGS_AVAILABLE_COUNT", 0)))
    print("derivation_fields", _normalize_text(metrics.get("DERIVATION_FIELDS", "")))
    print("actual_stockout_flag_support", _normalize_text(metrics.get("ACTUAL_STOCKOUT_FLAG_SUPPORT", "")))
    print("actual_stockout_unknown_required", _normalize_text(metrics.get("ACTUAL_STOCKOUT_UNKNOWN_REQUIRED", 0)))
    print("actual_stockout_ready_flag", _normalize_text(metrics.get("ACTUAL_STOCKOUT_READY_FLAG", 0)))
    print("derivation_support_stockout_flag", _normalize_text(metrics.get("DERIVATION_SUPPORT_STOCKOUT_FLAG", 0)))
    print("derivation_support_leftover_units", _normalize_text(metrics.get("DERIVATION_SUPPORT_LEFTOVER_UNITS", 0)))
    print("blocker_count", _normalize_text(metrics.get("BLOCKER_COUNT", 0)))
    print("actual_outcome_source_created_flag", _normalize_text(metrics.get("ACTUAL_OUTCOME_SOURCE_CREATED_FLAG", 0)))
    print("source_packets_mutated_flag", _normalize_text(metrics.get("SOURCE_PACKETS_MUTATED_FLAG", 0)))
    print("operator_audit_overwritten_flag", _normalize_text(metrics.get("OPERATOR_AUDIT_OVERWRITTEN_FLAG", 0)))
    print("actual_outcome_mapping_feasibility_summary", artifacts.summary_csv_path)
    print("actual_outcome_mapping_field_map", artifacts.field_map_csv_path)
    print("actual_outcome_mapping_derivation_rules", artifacts.derivation_rules_csv_path)
    print("actual_outcome_mapping_blockers", artifacts.blockers_csv_path)
    print("actual_outcome_mapping_validation", artifacts.validation_csv_path)
    print("actual_outcome_mapping_memo", artifacts.memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
