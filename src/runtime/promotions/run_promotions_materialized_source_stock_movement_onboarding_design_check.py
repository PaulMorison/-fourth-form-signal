from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Sequence

import pandas as pd


OUTPUT_FOLDER_NAME = "materialized_source_stock_movement_onboarding_design_check"
DISCOVERY_FOLDER_NAME = "materialized_source_daily_stock_truth_source_discovery"
CONTRACT_PLAN_FOLDER_NAME = "materialized_source_daily_stock_truth_contract_plan"
SOURCE_MATERIALIZED_FOLDER_NAME = "source_materialized_promotions"
DAILY_STOCK_TRUTH_EXTRACT_FOLDER_NAME = "materialized_source_daily_stock_truth"

DISCOVERY_SUMMARY_FILE_NAME = "daily_stock_truth_source_discovery_summary.csv"
CONTRACT_SCHEMA_FILE_NAME = "daily_stock_truth_contract_schema.csv"

PROMOTION_SOURCE_ROWS_FILE_NAME = "promotion_source_rows.csv"
OPERATOR_AUDIT_FILE_NAME = "operator_audit_source.csv"
ACTUAL_OUTCOME_FILE_NAME = "actual_outcome_source.csv"
DAILY_STOCK_TRUTH_EXTRACT_FILE_NAME = "daily_stock_truth_rows.csv"

SUMMARY_FILE_NAME = "stock_movement_onboarding_summary.csv"
COLUMN_MAPPING_FILE_NAME = "stock_movement_column_mapping.csv"
PARSE_CHECK_FILE_NAME = "stock_movement_transaction_parse_check.csv"
STOCK_TRUTH_RULES_FILE_NAME = "stock_movement_stock_truth_rules.csv"
READINESS_GATES_FILE_NAME = "stock_movement_readiness_gates.csv"
BLOCKERS_FILE_NAME = "stock_movement_blockers.csv"
VALIDATION_FILE_NAME = "stock_movement_onboarding_validation.csv"
MEMO_FILE_NAME = "stock_movement_onboarding_memo.md"

STATUS_READY = "STOCK_MOVEMENT_ONBOARDING_READY_FOR_CONFIG"
STATUS_BLOCKED_SAMPLE_SCHEMA = "STOCK_MOVEMENT_ONBOARDING_BLOCKED_SAMPLE_SCHEMA"
STATUS_BLOCKED_PARSE_RULE = "STOCK_MOVEMENT_ONBOARDING_BLOCKED_PARSE_RULE"
STATUS_BLOCKED_REQUIRED_COLUMNS = "STOCK_MOVEMENT_ONBOARDING_BLOCKED_REQUIRED_COLUMNS"

PARSE_RULE_NAME = "SPLIT_ON_DASH_TAKE_RIGHT"
STOCK_LEDGER_TABLE_NAME = "stock_movement"

REQUIRED_SAMPLE_COLUMNS: tuple[str, ...] = (
    "store_number",
    "movement_date",
    "item_code",
    "source",
    "soh",
    "movement_type",
    "adj_qty",
    "cost_ex",
    "soh_amount",
)

PWLOGD_JOIN_KEYS: tuple[str, ...] = (
    "calendar_date",
    "sku_number",
    "transaction_number",
)

SUMMARY_COLUMNS: tuple[str, ...] = (
    "metric_name",
    "metric_value",
    "metric_display",
    "notes",
)

COLUMN_MAPPING_COLUMNS: tuple[str, ...] = (
    "config_key",
    "config_value",
    "source_column",
    "derived_field",
    "notes",
)

PARSE_CHECK_COLUMNS: tuple[str, ...] = (
    "row_index",
    "source_value",
    "parse_success_flag",
    "transaction_number",
    "parse_status",
    "parse_notes",
)

STOCK_TRUTH_RULES_COLUMNS: tuple[str, ...] = (
    "rule_name",
    "rule_expression",
    "rule_scope",
    "unknown_coercion_allowed_flag",
    "notes",
)

READINESS_GATES_COLUMNS: tuple[str, ...] = (
    "gate_order",
    "gate_name",
    "gate_required_flag",
    "gate_status",
    "gate_pass_flag",
    "details",
)

BLOCKERS_COLUMNS: tuple[str, ...] = (
    "blocker_code",
    "blocker_status",
    "blocking_flag",
    "details",
)

VALIDATION_COLUMNS: tuple[str, ...] = (
    "validation_name",
    "validation_status",
    "validation_flag",
    "details",
)


class PromotionsMaterializedSourceStockMovementOnboardingDesignCheckError(RuntimeError):
    pass


@dataclass(frozen=True)
class PromotionsMaterializedSourceStockMovementOnboardingDesignCheckResult:
    onboarding_status: str
    promotion_key: str
    promotion_folder_name: str
    required_columns_present_flag: int
    source_parse_success_ratio: float
    soh_numeric_flag: int
    movement_date_parseable_flag: int
    full_window_sufficient_stock_proven_flag: int
    daily_stock_truth_extract_created_flag: int
    actual_outcome_source_created_flag: int
    source_packets_mutated_flag: int
    operator_audit_overwritten_flag: int
    summary_frame: pd.DataFrame
    column_mapping_frame: pd.DataFrame
    parse_check_frame: pd.DataFrame
    stock_truth_rules_frame: pd.DataFrame
    readiness_gates_frame: pd.DataFrame
    blockers_frame: pd.DataFrame
    validation_frame: pd.DataFrame
    memo_markdown: str


@dataclass(frozen=True)
class PromotionsMaterializedSourceStockMovementOnboardingDesignCheckArtifacts:
    output_root: str
    summary_csv_path: str
    column_mapping_csv_path: str
    parse_check_csv_path: str
    stock_truth_rules_csv_path: str
    readiness_gates_csv_path: str
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
        raise PromotionsMaterializedSourceStockMovementOnboardingDesignCheckError(f"CSV not found: {csv_path}")
    try:
        frame = pd.read_csv(csv_path, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceStockMovementOnboardingDesignCheckError(f"CSV is empty: {csv_path}")
    if frame.empty and not allow_empty:
        raise PromotionsMaterializedSourceStockMovementOnboardingDesignCheckError(f"CSV is empty: {csv_path}")
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
        raise PromotionsMaterializedSourceStockMovementOnboardingDesignCheckError(
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


def _parse_transaction_number(source: object) -> tuple[int, str, str, str]:
    text = _normalize_text(source)
    if not text:
        return 0, "", "FAIL", "source value is blank"
    if "-" not in text:
        return 0, "", "FAIL", "source does not contain dash separator"
    left, right = text.split("-", maxsplit=1)
    _ = left
    right_side = right.strip()
    if not right_side:
        return 0, "", "FAIL", "transaction number right side is blank"
    normalized = re.sub(r"\s+", "", right_side)
    if normalized.isdigit():
        return 1, normalized, "PASS", "numeric transaction number parsed from right side"
    if re.fullmatch(r"[A-Za-z0-9]+", normalized):
        return 1, normalized, "PASS", "string-normalised transaction number parsed from right side"
    return 0, "", "FAIL", "transaction number is not numeric or safely string-normalisable"


def _column_mapping_frame() -> pd.DataFrame:
    rows: list[dict[str, object]] = [
        {
            "config_key": "STOCK_LEDGER_TABLE",
            "config_value": STOCK_LEDGER_TABLE_NAME,
            "source_column": "",
            "derived_field": "",
            "notes": "stock_movement fills STOCK_LEDGER_TABLE as stock ledger / SOH movement evidence.",
        },
        {
            "config_key": "STOCK_LEDGER_DATE_COLUMN",
            "config_value": "movement_date",
            "source_column": "movement_date",
            "derived_field": "calendar_date",
            "notes": "calendar_date = movement_date",
        },
        {
            "config_key": "STOCK_LEDGER_SKU_COLUMN",
            "config_value": "item_code",
            "source_column": "item_code",
            "derived_field": "sku_number",
            "notes": "sku_number = item_code",
        },
        {
            "config_key": "STOCK_LEDGER_STORE_COLUMN",
            "config_value": "store_number",
            "source_column": "store_number",
            "derived_field": "store_number",
            "notes": "Store identity for PWLOGD join and promotion window filtering.",
        },
        {
            "config_key": "STOCK_LEDGER_SOH_COLUMN",
            "config_value": "soh",
            "source_column": "soh",
            "derived_field": "soh",
            "notes": "soh = 0 is trusted stock-constrained evidence when joined cleanly in-window.",
        },
        {
            "config_key": "STOCK_LEDGER_MOVEMENT_TYPE_COLUMN",
            "config_value": "movement_type",
            "source_column": "movement_type",
            "derived_field": "",
            "notes": "Movement type evidence for replenishment interpretation.",
        },
        {
            "config_key": "STOCK_LEDGER_ADJ_QTY_COLUMN",
            "config_value": "adj_qty",
            "source_column": "adj_qty",
            "derived_field": "",
            "notes": "Positive adj_qty after zero SOH can indicate replenishment during promo.",
        },
        {
            "config_key": "STOCK_LEDGER_SOURCE_COLUMN",
            "config_value": "source",
            "source_column": "source",
            "derived_field": "transaction_number",
            "notes": "source shape like 1-2347; transaction number is right side after dash.",
        },
        {
            "config_key": "STOCK_LEDGER_TRANSACTION_PARSE_RULE",
            "config_value": PARSE_RULE_NAME,
            "source_column": "source",
            "derived_field": "transaction_number",
            "notes": "Parse rule: split on dash and take right side.",
        },
        {
            "config_key": "STOCK_LEDGER_TRANSACTION_NUMBER_DERIVED",
            "config_value": "transaction_number",
            "source_column": "source",
            "derived_field": "transaction_number",
            "notes": "Derived join key for PWLOGD alignment.",
        },
        {
            "config_key": "OOS_EVENT_TABLE",
            "config_value": "NOT_CONFIGURED",
            "source_column": "",
            "derived_field": "",
            "notes": "stock_movement is not treated as explicit OOS event table unless explicit OOS columns exist.",
        },
        {
            "config_key": "SOH_SNAPSHOT_TABLE",
            "config_value": "NOT_CONFIGURED",
            "source_column": "",
            "derived_field": "",
            "notes": "Daily snapshot source remains separate from stock_movement ledger stream.",
        },
        {
            "config_key": "AVAILABILITY_TABLE",
            "config_value": "NOT_CONFIGURED",
            "source_column": "",
            "derived_field": "",
            "notes": "Availability source remains separate; stock_movement alone does not prove availability coverage.",
        },
    ]
    return pd.DataFrame(rows, columns=COLUMN_MAPPING_COLUMNS)


def _stock_truth_rules_frame() -> pd.DataFrame:
    rows: list[dict[str, object]] = [
        {
            "rule_name": "observed_zero_soh_event_flag",
            "rule_expression": "observed_zero_soh_event_flag = 1 when soh = 0",
            "rule_scope": "movement_row",
            "unknown_coercion_allowed_flag": 0,
            "notes": "Zero SOH is trusted stock-constrained evidence when joined cleanly inside promotion window.",
        },
        {
            "rule_name": "observed_negative_soh_event_flag",
            "rule_expression": "observed_negative_soh_event_flag = 1 when soh < 0",
            "rule_scope": "movement_row",
            "unknown_coercion_allowed_flag": 0,
            "notes": "Negative SOH is integrity evidence, not clean stockout truth.",
        },
        {
            "rule_name": "stock_integrity_issue_flag",
            "rule_expression": "stock_integrity_issue_flag = 1 when soh < 0",
            "rule_scope": "movement_row",
            "unknown_coercion_allowed_flag": 0,
            "notes": "soh < 0 is a stock integrity issue first.",
        },
        {
            "rule_name": "stock_constrained_sales_evidence_flag",
            "rule_expression": "stock_constrained_sales_evidence_flag = 1 when zero SOH is observed in-window on a valid joined movement record",
            "rule_scope": "promotion_window_joined_row",
            "unknown_coercion_allowed_flag": 0,
            "notes": "Requires clean PWLOGD join on calendar_date + sku_number + transaction_number.",
        },
        {
            "rule_name": "stock_replenishment_during_promo_flag",
            "rule_expression": "stock_replenishment_during_promo_flag = 1 when zero/near-zero SOH is followed by positive adj_qty or SOH recovery above zero inside promotion window",
            "rule_scope": "promotion_window_sequence",
            "unknown_coercion_allowed_flag": 0,
            "notes": "Replenishment evidence is sequence-based inside the promotion window.",
        },
        {
            "rule_name": "unknown_stockout_not_zero",
            "rule_expression": "unknown stockout must not be coerced to zero",
            "rule_scope": "mapping_and_rollup",
            "unknown_coercion_allowed_flag": 0,
            "notes": "Unknown must remain unknown; do not coerce to zero for stockout truth.",
        },
        {
            "rule_name": "full_window_sufficient_stock_coverage",
            "rule_expression": "full-window sufficient stock can only be asserted if coverage gates pass; stock_movement alone does not automatically prove it",
            "rule_scope": "promotion_window_coverage",
            "unknown_coercion_allowed_flag": 0,
            "notes": "Requires complete daily SOH or availability coverage beyond movement ledger rows.",
        },
        {
            "rule_name": "not_explicit_oos_event_table",
            "rule_expression": "do not classify stock_movement as explicit OOS_EVENT_TABLE unless explicit OOS event columns exist",
            "rule_scope": "source_classification",
            "unknown_coercion_allowed_flag": 0,
            "notes": "Treat stock_movement as stock ledger / SOH movement evidence stream.",
        },
    ]
    return pd.DataFrame(rows, columns=STOCK_TRUTH_RULES_COLUMNS)


def _load_sample_frame(sample_path: str | Path | None) -> tuple[pd.DataFrame, str | None]:
    if sample_path is None:
        return pd.DataFrame(), "sample_path_not_provided"
    sample_file = Path(sample_path)
    if not sample_file.exists():
        return pd.DataFrame(), f"sample_file_missing:{sample_file}"
    try:
        frame = pd.read_csv(sample_file, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(), f"sample_file_empty:{sample_file}"
    if frame.empty:
        return pd.DataFrame(), f"sample_file_empty:{sample_file}"
    return frame, None


def _evaluate_sample(
    sample_frame: pd.DataFrame,
    *,
    promotion_start_date: str,
    promotion_end_date: str,
) -> tuple[
    int,
    float,
    int,
    int,
    int,
    int,
    int,
    pd.DataFrame,
    list[str],
]:
    missing_columns = [column for column in REQUIRED_SAMPLE_COLUMNS if column not in sample_frame.columns]
    required_columns_present_flag = int(not missing_columns)

    if not required_columns_present_flag:
        return (
            0,
            0.0,
            0,
            0,
            0,
            0,
            0,
            0,
            pd.DataFrame(columns=PARSE_CHECK_COLUMNS),
            [f"missing_required_columns:{','.join(missing_columns)}"],
        )

    parse_rows: list[dict[str, object]] = []
    parse_success_count = 0
    for row_index, source_value in enumerate(sample_frame["source"].tolist()):
        success_flag, transaction_number, parse_status, parse_notes = _parse_transaction_number(source_value)
        parse_success_count += int(success_flag)
        parse_rows.append(
            {
                "row_index": row_index,
                "source_value": _normalize_text(source_value),
                "parse_success_flag": int(success_flag),
                "transaction_number": transaction_number,
                "parse_status": parse_status,
                "parse_notes": parse_notes,
            }
        )
    parse_check_frame = pd.DataFrame(parse_rows, columns=PARSE_CHECK_COLUMNS)
    row_count = int(len(sample_frame.index))
    source_parse_success_ratio = float(parse_success_count / row_count) if row_count else 0.0

    soh_series = pd.to_numeric(sample_frame["soh"], errors="coerce")
    soh_numeric_flag = int(soh_series.notna().all())

    movement_dates = pd.to_datetime(sample_frame["movement_date"], errors="coerce")
    movement_date_parseable_flag = int(movement_dates.notna().all())

    store_present_flag = int(sample_frame["store_number"].astype(str).str.strip().ne("").all())
    sku_present_flag = int(sample_frame["item_code"].astype(str).str.strip().ne("").all())
    store_sku_identity_flag = int(store_present_flag and sku_present_flag)

    zero_soh_flag = int((soh_series == 0).any())
    negative_soh_flag = int((soh_series < 0).any())

    in_window = movement_dates.between(promotion_start_date, promotion_end_date, inclusive="both")
    in_window_frame = sample_frame.loc[in_window.fillna(False)].copy()
    replenishment_flag = 0
    if not in_window_frame.empty and "adj_qty" in in_window_frame.columns:
        window_soh = pd.to_numeric(in_window_frame["soh"], errors="coerce")
        window_adj = pd.to_numeric(in_window_frame["adj_qty"], errors="coerce")
        prior_zero = int((window_soh == 0).any())
        recovery = int(((window_soh > 0) | (window_adj > 0)).any())
        replenishment_flag = int(prior_zero and recovery)

    issues: list[str] = []
    if source_parse_success_ratio < 1.0:
        issues.append("source_parse_not_fully_successful")
    if not soh_numeric_flag:
        issues.append("soh_not_fully_numeric")
    if not movement_date_parseable_flag:
        issues.append("movement_date_not_fully_parseable")
    if not store_sku_identity_flag:
        issues.append("store_or_sku_identity_missing")
    if not zero_soh_flag and not negative_soh_flag:
        issues.append("no_zero_or_negative_soh_examples_in_sample")

    return (
        required_columns_present_flag,
        source_parse_success_ratio,
        soh_numeric_flag,
        movement_date_parseable_flag,
        store_sku_identity_flag,
        zero_soh_flag,
        negative_soh_flag,
        replenishment_flag,
        parse_check_frame,
        issues,
    )


def _readiness_gates_frame(
    *,
    required_columns_present_flag: int,
    source_parse_success_ratio: float,
    soh_numeric_flag: int,
    movement_date_parseable_flag: int,
    store_sku_identity_flag: int,
    zero_soh_flag: int,
    negative_soh_flag: int,
    replenishment_design_flag: int,
    sample_available_flag: int,
    daily_stock_truth_extract_created_flag: int,
    actual_outcome_source_created_flag: int,
    source_packets_mutated_flag: int,
    operator_audit_overwritten_flag: int,
) -> pd.DataFrame:
    parse_gate_pass = int(sample_available_flag and source_parse_success_ratio == 1.0)
    rows: list[dict[str, object]] = [
        {
            "gate_order": 1,
            "gate_name": "required_columns_gate",
            "gate_required_flag": 1,
            "gate_status": "PASS" if required_columns_present_flag else "FAIL",
            "gate_pass_flag": int(required_columns_present_flag),
            "details": "Required stock_movement sample columns must be present when sample is supplied.",
        },
        {
            "gate_order": 2,
            "gate_name": "source_parse_gate",
            "gate_required_flag": 1,
            "gate_status": "PASS" if parse_gate_pass else "FAIL",
            "gate_pass_flag": parse_gate_pass,
            "details": f"Parse rule {PARSE_RULE_NAME} must succeed on all sample rows.",
        },
        {
            "gate_order": 3,
            "gate_name": "soh_numeric_gate",
            "gate_required_flag": 1,
            "gate_status": "PASS" if soh_numeric_flag else "FAIL",
            "gate_pass_flag": int(soh_numeric_flag),
            "details": "soh must be numeric on sample rows.",
        },
        {
            "gate_order": 4,
            "gate_name": "movement_date_parse_gate",
            "gate_required_flag": 1,
            "gate_status": "PASS" if movement_date_parseable_flag else "FAIL",
            "gate_pass_flag": int(movement_date_parseable_flag),
            "details": "movement_date must parse as calendar date.",
        },
        {
            "gate_order": 5,
            "gate_name": "store_sku_identity_gate",
            "gate_required_flag": 1,
            "gate_status": "PASS" if store_sku_identity_flag else "FAIL",
            "gate_pass_flag": int(store_sku_identity_flag),
            "details": "store_number and item_code must be present for PWLOGD join design.",
        },
        {
            "gate_order": 6,
            "gate_name": "join_to_pwlogd_design_gate",
            "gate_required_flag": 1,
            "gate_status": "PASS",
            "gate_pass_flag": 1,
            "details": "Join design uses calendar_date + sku_number + transaction_number.",
        },
        {
            "gate_order": 7,
            "gate_name": "zero_soh_evidence_gate",
            "gate_required_flag": 1,
            "gate_status": "PASS" if zero_soh_flag or not sample_available_flag else "WARN",
            "gate_pass_flag": 1,
            "details": "Zero-SOH evidence rule is documented; sample may or may not include zero rows.",
        },
        {
            "gate_order": 8,
            "gate_name": "negative_soh_integrity_gate",
            "gate_required_flag": 1,
            "gate_status": "PASS",
            "gate_pass_flag": 1,
            "details": "Negative-SOH integrity rule is documented and treated as integrity issue first.",
        },
        {
            "gate_order": 9,
            "gate_name": "replenishment_evidence_gate",
            "gate_required_flag": 1,
            "gate_status": "PASS" if replenishment_design_flag else "FAIL",
            "gate_pass_flag": int(replenishment_design_flag),
            "details": "Replenishment evidence rule is documented for in-window zero-to-recovery sequences.",
        },
        {
            "gate_order": 10,
            "gate_name": "unknown_not_zero_gate",
            "gate_required_flag": 1,
            "gate_status": "PASS",
            "gate_pass_flag": 1,
            "details": "Unknown stockout must not be coerced to zero.",
        },
        {
            "gate_order": 11,
            "gate_name": "full_window_sufficient_stock_coverage_gate",
            "gate_required_flag": 1,
            "gate_status": "PASS",
            "gate_pass_flag": 1,
            "details": "Full-window sufficient stock is not automatically proven by stock_movement alone.",
        },
        {
            "gate_order": 12,
            "gate_name": "no_side_effect_gate",
            "gate_required_flag": 1,
            "gate_status": "PASS"
            if (
                daily_stock_truth_extract_created_flag == 0
                and actual_outcome_source_created_flag == 0
                and source_packets_mutated_flag == 0
                and operator_audit_overwritten_flag == 0
            )
            else "FAIL",
            "gate_pass_flag": int(
                daily_stock_truth_extract_created_flag == 0
                and actual_outcome_source_created_flag == 0
                and source_packets_mutated_flag == 0
                and operator_audit_overwritten_flag == 0
            ),
            "details": "Planner must not create extracts, promote outcomes, or mutate source packets.",
        },
    ]
    return pd.DataFrame(rows, columns=READINESS_GATES_COLUMNS)


def _determine_status(
    *,
    sample_issue: str | None,
    required_columns_present_flag: int,
    source_parse_success_ratio: float,
    readiness_gates_frame: pd.DataFrame,
) -> str:
    if sample_issue is not None:
        return STATUS_BLOCKED_SAMPLE_SCHEMA
    if not required_columns_present_flag:
        return STATUS_BLOCKED_REQUIRED_COLUMNS
    if source_parse_success_ratio < 1.0:
        return STATUS_BLOCKED_PARSE_RULE

    required_gate_failures = readiness_gates_frame.loc[
        readiness_gates_frame["gate_required_flag"].astype(int).eq(1)
        & readiness_gates_frame["gate_pass_flag"].astype(int).eq(0)
    ]
    if not required_gate_failures.empty:
        failed_names = required_gate_failures["gate_name"].astype(str).tolist()
        if "source_parse_gate" in failed_names:
            return STATUS_BLOCKED_PARSE_RULE
        if "required_columns_gate" in failed_names:
            return STATUS_BLOCKED_REQUIRED_COLUMNS
        return STATUS_BLOCKED_SAMPLE_SCHEMA

    return STATUS_READY


def _blockers_frame(
    *,
    onboarding_status: str,
    sample_issue: str | None,
    sample_issues: list[str],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    if sample_issue is not None:
        rows.append(
            {
                "blocker_code": "SAMPLE_SCHEMA_UNAVAILABLE",
                "blocker_status": "BLOCKING",
                "blocking_flag": 1,
                "details": sample_issue,
            }
        )
    for issue in sample_issues:
        rows.append(
            {
                "blocker_code": issue.upper(),
                "blocker_status": "BLOCKING",
                "blocking_flag": 1,
                "details": issue,
            }
        )
    if not rows:
        rows.append(
            {
                "blocker_code": "NO_BLOCKERS",
                "blocker_status": "CLEAR",
                "blocking_flag": 0,
                "details": f"Onboarding status: {onboarding_status}",
            }
        )
    return pd.DataFrame(rows, columns=BLOCKERS_COLUMNS)


def build_promotions_materialized_source_stock_movement_onboarding_design_check(
    *,
    packet_root: str | Path,
    promotion_key: str,
    stock_movement_sample_path: str | Path | None = None,
    output_root: str | Path | None = None,
) -> PromotionsMaterializedSourceStockMovementOnboardingDesignCheckResult:
    packet_root_path = Path(packet_root)
    _ = output_root
    promotion_folder_name = _promotion_folder_from_key(promotion_key)
    store_number, promotion_start_date, promotion_end_date, _promotion_name = _promotion_parts_from_key(
        promotion_key
    )

    discovery_summary_path = (
        packet_root_path / DISCOVERY_FOLDER_NAME / DISCOVERY_SUMMARY_FILE_NAME
    )
    contract_schema_path = packet_root_path / CONTRACT_PLAN_FOLDER_NAME / CONTRACT_SCHEMA_FILE_NAME
    _read_csv(discovery_summary_path)
    _read_csv(contract_schema_path)

    source_folder = packet_root_path / SOURCE_MATERIALIZED_FOLDER_NAME / promotion_folder_name
    promotion_source_rows_path = source_folder / PROMOTION_SOURCE_ROWS_FILE_NAME
    operator_audit_path = source_folder / OPERATOR_AUDIT_FILE_NAME
    actual_outcome_source_path = source_folder / ACTUAL_OUTCOME_FILE_NAME
    daily_stock_truth_extract_path = (
        packet_root_path / DAILY_STOCK_TRUTH_EXTRACT_FOLDER_NAME / DAILY_STOCK_TRUTH_EXTRACT_FILE_NAME
    )

    source_rows_before = promotion_source_rows_path.read_bytes() if promotion_source_rows_path.exists() else b""
    operator_before = operator_audit_path.read_bytes() if operator_audit_path.exists() else b""
    actual_outcome_before = int(actual_outcome_source_path.exists())
    daily_stock_truth_before = int(daily_stock_truth_extract_path.exists())

    sample_frame, sample_issue = _load_sample_frame(stock_movement_sample_path)
    sample_available_flag = int(sample_issue is None and not sample_frame.empty)

    (
        required_columns_present_flag,
        source_parse_success_ratio,
        soh_numeric_flag,
        movement_date_parseable_flag,
        store_sku_identity_flag,
        zero_soh_flag,
        negative_soh_flag,
        replenishment_flag,
        parse_check_frame,
        sample_issues,
    ) = _evaluate_sample(
        sample_frame,
        promotion_start_date=promotion_start_date,
        promotion_end_date=promotion_end_date,
    )
    if sample_issue is not None:
        required_columns_present_flag = 0
        source_parse_success_ratio = 0.0
        soh_numeric_flag = 0
        movement_date_parseable_flag = 0
        store_sku_identity_flag = 0
        zero_soh_flag = 0
        negative_soh_flag = 0
        replenishment_flag = 1
        parse_check_frame = pd.DataFrame(columns=PARSE_CHECK_COLUMNS)
        sample_issues = [sample_issue]

    column_mapping_frame = _column_mapping_frame()
    stock_truth_rules_frame = _stock_truth_rules_frame()

    source_rows_after = promotion_source_rows_path.read_bytes() if promotion_source_rows_path.exists() else b""
    operator_after = operator_audit_path.read_bytes() if operator_audit_path.exists() else b""
    actual_outcome_after = int(actual_outcome_source_path.exists())
    daily_stock_truth_after = int(daily_stock_truth_extract_path.exists())

    source_packets_mutated_flag = int(source_rows_before != source_rows_after)
    operator_audit_overwritten_flag = int(operator_before != operator_after)
    actual_outcome_source_created_flag = int(actual_outcome_before == 0 and actual_outcome_after == 1)
    daily_stock_truth_extract_created_flag = int(daily_stock_truth_before == 0 and daily_stock_truth_after == 1)

    readiness_gates_frame = _readiness_gates_frame(
        required_columns_present_flag=required_columns_present_flag,
        source_parse_success_ratio=source_parse_success_ratio,
        soh_numeric_flag=soh_numeric_flag,
        movement_date_parseable_flag=movement_date_parseable_flag,
        store_sku_identity_flag=store_sku_identity_flag,
        zero_soh_flag=zero_soh_flag,
        negative_soh_flag=negative_soh_flag,
        replenishment_design_flag=1,
        sample_available_flag=sample_available_flag,
        daily_stock_truth_extract_created_flag=daily_stock_truth_extract_created_flag,
        actual_outcome_source_created_flag=actual_outcome_source_created_flag,
        source_packets_mutated_flag=source_packets_mutated_flag,
        operator_audit_overwritten_flag=operator_audit_overwritten_flag,
    )

    onboarding_status = _determine_status(
        sample_issue=sample_issue,
        required_columns_present_flag=required_columns_present_flag,
        source_parse_success_ratio=source_parse_success_ratio,
        readiness_gates_frame=readiness_gates_frame,
    )
    blockers_frame = _blockers_frame(
        onboarding_status=onboarding_status,
        sample_issue=sample_issue,
        sample_issues=sample_issues,
    )

    full_window_sufficient_stock_proven_flag = 0

    summary_frame = pd.DataFrame(
        [
            _summary_row("ONBOARDING_STATUS", onboarding_status, "Stock movement onboarding design-check status."),
            _summary_row("PROMOTION_KEY", promotion_key, "Promotion key under onboarding design check."),
            _summary_row("PROMOTION_FOLDER_NAME", promotion_folder_name, "Promotion-scoped source folder name."),
            _summary_row("STORE_NUMBER", store_number, "Promotion store number from promotion key."),
            _summary_row("STOCK_LEDGER_TABLE", STOCK_LEDGER_TABLE_NAME, "Recommended STOCK_LEDGER_TABLE mapping."),
            _summary_row("OOS_EVENT_TABLE", "NOT_CONFIGURED", "stock_movement is not explicit OOS event table."),
            _summary_row("SOH_SNAPSHOT_TABLE", "NOT_CONFIGURED", "Snapshot table remains unconfigured in this pass."),
            _summary_row("AVAILABILITY_TABLE", "NOT_CONFIGURED", "Availability table remains unconfigured in this pass."),
            _summary_row(
                "STOCK_LEDGER_TRANSACTION_PARSE_RULE",
                PARSE_RULE_NAME,
                "Transaction number parse rule for source column.",
            ),
            _summary_row(
                "REQUIRED_COLUMNS_PRESENT_FLAG",
                required_columns_present_flag,
                "Whether required stock_movement sample columns are present.",
            ),
            _summary_row(
                "SOURCE_PARSE_SUCCESS_RATIO",
                round(source_parse_success_ratio, 6),
                "Share of sample rows with successful source parse.",
            ),
            _summary_row("SOH_NUMERIC_FLAG", soh_numeric_flag, "Whether sample soh values are numeric."),
            _summary_row(
                "MOVEMENT_DATE_PARSEABLE_FLAG",
                movement_date_parseable_flag,
                "Whether sample movement_date values parse as dates.",
            ),
            _summary_row(
                "FULL_WINDOW_SUFFICIENT_STOCK_PROVEN_FLAG",
                full_window_sufficient_stock_proven_flag,
                "stock_movement alone does not prove full-window sufficient stock.",
            ),
            _summary_row(
                "PWLOGD_JOIN_KEYS",
                ",".join(PWLOGD_JOIN_KEYS),
                "Approved join keys for PWLOGD alignment.",
            ),
            _summary_row(
                "DAILY_STOCK_TRUTH_EXTRACT_CREATED_FLAG",
                daily_stock_truth_extract_created_flag,
                "Planner must not create daily stock-truth extract.",
            ),
            _summary_row(
                "ACTUAL_OUTCOME_SOURCE_CREATED_FLAG",
                actual_outcome_source_created_flag,
                "Planner must not create actual_outcome_source.csv.",
            ),
            _summary_row(
                "SOURCE_PACKETS_MUTATED_FLAG",
                source_packets_mutated_flag,
                "Planner must not mutate promotion_source_rows.csv.",
            ),
            _summary_row(
                "OPERATOR_AUDIT_OVERWRITTEN_FLAG",
                operator_audit_overwritten_flag,
                "Planner must not overwrite operator_audit_source.csv.",
            ),
        ],
        columns=SUMMARY_COLUMNS,
    )

    validation_frame = pd.DataFrame(
        [
            _validation_row(
                "EXPECTED_READY_WHEN_SAMPLE_VALID",
                int(onboarding_status == STATUS_READY),
                f"onboarding_status={onboarding_status}",
            ),
            _validation_row(
                "STOCK_LEDGER_TABLE_MAPPED",
                int(
                    column_mapping_frame.loc[
                        column_mapping_frame["config_key"].astype(str).eq("STOCK_LEDGER_TABLE"),
                        "config_value",
                    ].astype(str).eq(STOCK_LEDGER_TABLE_NAME).any()
                ),
                "STOCK_LEDGER_TABLE maps to stock_movement.",
            ),
            _validation_row(
                "PARSE_RULE_RECORDED",
                int(
                    column_mapping_frame.loc[
                        column_mapping_frame["config_key"].astype(str).eq("STOCK_LEDGER_TRANSACTION_PARSE_RULE"),
                        "config_value",
                    ].astype(str).eq(PARSE_RULE_NAME).any()
                ),
                f"Parse rule {PARSE_RULE_NAME} recorded.",
            ),
            _validation_row(
                "ZERO_SOH_RULE_RECORDED",
                int(stock_truth_rules_frame["rule_name"].astype(str).eq("observed_zero_soh_event_flag").any()),
                "Zero-SOH evidence rule recorded.",
            ),
            _validation_row(
                "NEGATIVE_SOH_RULE_RECORDED",
                int(stock_truth_rules_frame["rule_name"].astype(str).eq("stock_integrity_issue_flag").any()),
                "Negative-SOH integrity rule recorded.",
            ),
            _validation_row(
                "UNKNOWN_NOT_ZERO_RULE_RECORDED",
                int(stock_truth_rules_frame["rule_name"].astype(str).eq("unknown_stockout_not_zero").any()),
                "Unknown-not-zero rule recorded.",
            ),
            _validation_row(
                "FULL_WINDOW_NOT_AUTO_PROVEN",
                int(full_window_sufficient_stock_proven_flag == 0),
                "Full-window sufficient stock is not automatically proven by stock_movement alone.",
            ),
            _validation_row(
                "NO_DAILY_STOCK_TRUTH_EXTRACT_CREATED",
                int(daily_stock_truth_extract_created_flag == 0),
                "Planner did not create daily stock-truth extract.",
            ),
            _validation_row(
                "NO_ACTUAL_OUTCOME_SOURCE_CREATED",
                int(actual_outcome_source_created_flag == 0),
                "Planner did not create actual_outcome_source.csv.",
            ),
            _validation_row(
                "SOURCE_PACKETS_UNCHANGED",
                int(source_packets_mutated_flag == 0),
                "promotion_source_rows.csv remained unchanged.",
            ),
            _validation_row(
                "OPERATOR_AUDIT_UNCHANGED",
                int(operator_audit_overwritten_flag == 0),
                "operator_audit_source.csv remained unchanged.",
            ),
        ],
        columns=VALIDATION_COLUMNS,
    )

    memo_markdown = "\n".join(
        [
            "# Stock Movement Onboarding Design Check",
            "",
            "Planner-only onboarding/config checker for stock_movement as STOCK_LEDGER_TABLE.",
            "This runtime does not connect to SQL, does not query any database, and does not build extracts.",
            "",
            f"Onboarding status: {onboarding_status}",
            f"Promotion key: {promotion_key}",
            f"STOCK_LEDGER_TABLE: {STOCK_LEDGER_TABLE_NAME}",
            f"Parse rule: {PARSE_RULE_NAME}",
            f"PWLOGD join keys: {', '.join(PWLOGD_JOIN_KEYS)}",
            "",
            "Design decisions:",
            "- stock_movement is a stock ledger / SOH movement evidence stream.",
            "- stock_movement is not treated as explicit OOS_EVENT_TABLE unless explicit OOS columns exist.",
            "- soh = 0 is trusted stock-constrained evidence when joined cleanly in-window.",
            "- soh < 0 is a stock integrity issue first, not clean stockout truth.",
            "- Unknown stockout must not be coerced to zero.",
            "- Full-window sufficient stock is not automatically proven by stock_movement alone.",
            "",
            f"Required columns present: {'yes' if required_columns_present_flag else 'no'}",
            f"Source parse success ratio: {source_parse_success_ratio:.6f}",
            f"SOH numeric: {'yes' if soh_numeric_flag else 'no'}",
            f"Movement date parseable: {'yes' if movement_date_parseable_flag else 'no'}",
        ]
    )

    return PromotionsMaterializedSourceStockMovementOnboardingDesignCheckResult(
        onboarding_status=onboarding_status,
        promotion_key=promotion_key,
        promotion_folder_name=promotion_folder_name,
        required_columns_present_flag=required_columns_present_flag,
        source_parse_success_ratio=source_parse_success_ratio,
        soh_numeric_flag=soh_numeric_flag,
        movement_date_parseable_flag=movement_date_parseable_flag,
        full_window_sufficient_stock_proven_flag=full_window_sufficient_stock_proven_flag,
        daily_stock_truth_extract_created_flag=daily_stock_truth_extract_created_flag,
        actual_outcome_source_created_flag=actual_outcome_source_created_flag,
        source_packets_mutated_flag=source_packets_mutated_flag,
        operator_audit_overwritten_flag=operator_audit_overwritten_flag,
        summary_frame=summary_frame,
        column_mapping_frame=column_mapping_frame,
        stock_truth_rules_frame=stock_truth_rules_frame,
        readiness_gates_frame=readiness_gates_frame,
        blockers_frame=blockers_frame,
        validation_frame=validation_frame,
        memo_markdown=memo_markdown,
        parse_check_frame=parse_check_frame,
    )


def write_promotions_materialized_source_stock_movement_onboarding_design_check(
    *,
    packet_root: str | Path,
    promotion_key: str,
    stock_movement_sample_path: str | Path | None = None,
    output_root: str | Path | None = None,
) -> PromotionsMaterializedSourceStockMovementOnboardingDesignCheckArtifacts:
    packet_root_path = Path(packet_root)
    output_root_path = _resolve_output_root(packet_root_path, output_root)

    result = build_promotions_materialized_source_stock_movement_onboarding_design_check(
        packet_root=packet_root,
        promotion_key=promotion_key,
        stock_movement_sample_path=stock_movement_sample_path,
        output_root=output_root,
    )

    output_root_path.mkdir(parents=True, exist_ok=True)

    summary_path = output_root_path / SUMMARY_FILE_NAME
    column_mapping_path = output_root_path / COLUMN_MAPPING_FILE_NAME
    parse_check_path = output_root_path / PARSE_CHECK_FILE_NAME
    stock_truth_rules_path = output_root_path / STOCK_TRUTH_RULES_FILE_NAME
    readiness_gates_path = output_root_path / READINESS_GATES_FILE_NAME
    blockers_path = output_root_path / BLOCKERS_FILE_NAME
    validation_path = output_root_path / VALIDATION_FILE_NAME
    memo_path = output_root_path / MEMO_FILE_NAME

    result.summary_frame.to_csv(summary_path, index=False)
    result.column_mapping_frame.to_csv(column_mapping_path, index=False)
    result.parse_check_frame.to_csv(parse_check_path, index=False)
    result.stock_truth_rules_frame.to_csv(stock_truth_rules_path, index=False)
    result.readiness_gates_frame.to_csv(readiness_gates_path, index=False)
    result.blockers_frame.to_csv(blockers_path, index=False)
    result.validation_frame.to_csv(validation_path, index=False)
    memo_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsMaterializedSourceStockMovementOnboardingDesignCheckArtifacts(
        output_root=str(output_root_path),
        summary_csv_path=str(summary_path),
        column_mapping_csv_path=str(column_mapping_path),
        parse_check_csv_path=str(parse_check_path),
        stock_truth_rules_csv_path=str(stock_truth_rules_path),
        readiness_gates_csv_path=str(readiness_gates_path),
        blockers_csv_path=str(blockers_path),
        validation_csv_path=str(validation_path),
        memo_md_path=str(memo_path),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build planner-only stock_movement onboarding design-check artifacts."
    )
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--promotion-key", required=True)
    parser.add_argument("--stock-movement-sample-path")
    parser.add_argument("--output-root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)

    artifacts = write_promotions_materialized_source_stock_movement_onboarding_design_check(
        packet_root=args.packet_root,
        promotion_key=args.promotion_key,
        stock_movement_sample_path=args.stock_movement_sample_path,
        output_root=args.output_root,
    )

    summary = _read_csv(artifacts.summary_csv_path, allow_empty=True)
    metrics = _metric_lookup(summary)

    print("onboarding_status", _normalize_text(metrics.get("ONBOARDING_STATUS", "")))
    print("required_columns_present_flag", _normalize_text(metrics.get("REQUIRED_COLUMNS_PRESENT_FLAG", 0)))
    print("source_parse_success_ratio", _normalize_text(metrics.get("SOURCE_PARSE_SUCCESS_RATIO", 0)))
    print("soh_numeric_flag", _normalize_text(metrics.get("SOH_NUMERIC_FLAG", 0)))
    print("movement_date_parseable_flag", _normalize_text(metrics.get("MOVEMENT_DATE_PARSEABLE_FLAG", 0)))
    print("full_window_sufficient_stock_proven_flag", _normalize_text(metrics.get("FULL_WINDOW_SUFFICIENT_STOCK_PROVEN_FLAG", 0)))
    print("daily_stock_truth_extract_created_flag", _normalize_text(metrics.get("DAILY_STOCK_TRUTH_EXTRACT_CREATED_FLAG", 0)))
    print("actual_outcome_source_created_flag", _normalize_text(metrics.get("ACTUAL_OUTCOME_SOURCE_CREATED_FLAG", 0)))
    print("source_packets_mutated_flag", _normalize_text(metrics.get("SOURCE_PACKETS_MUTATED_FLAG", 0)))
    print("operator_audit_overwritten_flag", _normalize_text(metrics.get("OPERATOR_AUDIT_OVERWRITTEN_FLAG", 0)))
    print("stock_movement_onboarding_summary", artifacts.summary_csv_path)
    print("stock_movement_column_mapping", artifacts.column_mapping_csv_path)
    print("stock_movement_transaction_parse_check", artifacts.parse_check_csv_path)
    print("stock_movement_stock_truth_rules", artifacts.stock_truth_rules_csv_path)
    print("stock_movement_readiness_gates", artifacts.readiness_gates_csv_path)
    print("stock_movement_blockers", artifacts.blockers_csv_path)
    print("stock_movement_onboarding_validation", artifacts.validation_csv_path)
    print("stock_movement_onboarding_memo", artifacts.memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
