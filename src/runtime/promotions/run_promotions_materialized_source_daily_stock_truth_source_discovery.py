from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Sequence

import pandas as pd


OUTPUT_FOLDER_NAME = "materialized_source_daily_stock_truth_source_discovery"
CONTRACT_PLAN_FOLDER_NAME = "materialized_source_daily_stock_truth_contract_plan"
SOURCE_MATERIALIZED_FOLDER_NAME = "source_materialized_promotions"
DAILY_STOCK_TRUTH_EXTRACT_FOLDER_NAME = "materialized_source_daily_stock_truth"

CONTRACT_SUMMARY_FILE_NAME = "daily_stock_truth_contract_summary.csv"
CONTRACT_SCHEMA_FILE_NAME = "daily_stock_truth_contract_schema.csv"
CONTRACT_SOURCE_REQUIREMENTS_FILE_NAME = "daily_stock_truth_contract_source_requirements.csv"

PROMOTION_SOURCE_ROWS_FILE_NAME = "promotion_source_rows.csv"
OPERATOR_AUDIT_FILE_NAME = "operator_audit_source.csv"
ACTUAL_OUTCOME_FILE_NAME = "actual_outcome_source.csv"
DAILY_STOCK_TRUTH_EXTRACT_FILE_NAME = "daily_stock_truth_rows.csv"

SUMMARY_FILE_NAME = "daily_stock_truth_source_discovery_summary.csv"
CANDIDATE_INVENTORY_FILE_NAME = "daily_stock_truth_source_candidate_inventory.csv"
GAP_ANALYSIS_FILE_NAME = "daily_stock_truth_source_gap_analysis.csv"
REQUIRED_CONFIG_FILE_NAME = "daily_stock_truth_source_required_config.csv"
VALIDATION_FILE_NAME = "daily_stock_truth_source_discovery_validation.csv"
MEMO_FILE_NAME = "daily_stock_truth_source_discovery_memo.md"

STATUS_READY = "DAILY_STOCK_TRUTH_SOURCE_READY"
STATUS_CONFIG_REQUIRED = "DAILY_STOCK_TRUTH_SOURCE_CONFIG_REQUIRED"
STATUS_NOT_FOUND = "DAILY_STOCK_TRUTH_SOURCE_NOT_FOUND"

CONTRACT_READY_STATUS = "DAILY_STOCK_TRUTH_CONTRACT_READY"

SUMMARY_COLUMNS: tuple[str, ...] = (
    "metric_name",
    "metric_value",
    "metric_display",
    "notes",
)

CANDIDATE_COLUMNS: tuple[str, ...] = (
    "candidate_name",
    "candidate_type",
    "source_scope",
    "source_path",
    "supports_sales_truth_flag",
    "supports_stock_truth_flag",
    "configured_stock_truth_flag",
    "evidence",
    "notes",
)

GAP_COLUMNS: tuple[str, ...] = (
    "gap_name",
    "required_flag",
    "present_flag",
    "gap_status",
    "details",
)

REQUIRED_CONFIG_COLUMNS: tuple[str, ...] = (
    "config_key",
    "required_flag",
    "configured_flag",
    "purpose",
    "recommended_example",
)

VALIDATION_COLUMNS: tuple[str, ...] = (
    "validation_name",
    "validation_status",
    "validation_flag",
    "details",
)

SOURCE_REFERENCE_FILES: tuple[str, ...] = (
    "src/runtime/promotions/config.py",
    "src/data/promotions/sql/promotion_base_extraction.sql",
    "src/data/promotions/completed_transaction_aggregates_extractor.py",
    "src/data/promotions/completed_window_aggregates_extractor.py",
)

REQUIRED_CONFIG_KEYS: tuple[tuple[str, str, str], ...] = (
    ("STOCK_LEDGER_TABLE", "Daily stock movement and balances source.", "inventory.stock_ledger_daily"),
    ("SOH_SNAPSHOT_TABLE", "Daily opening/closing SOH snapshot source.", "inventory.soh_snapshot_daily"),
    ("AVAILABILITY_TABLE", "Governed availability signal source.", "inventory.channel_availability_daily"),
    ("OOS_EVENT_TABLE", "Explicit out-of-stock event source.", "inventory.oos_event_log"),
    (
        "STOCK_TRUTH_SOURCE_PRIORITY",
        "Priority order across stock-truth source families.",
        "OOS_EVENT_TABLE,SOH_SNAPSHOT_TABLE,AVAILABILITY_TABLE",
    ),
)

KEYWORD_GROUPS: tuple[tuple[str, str], ...] = (
    ("stock_ledger", r"stock\s*ledger|ledger\s*stock|inventory\s*ledger"),
    ("stock_movement", r"stock\s*movement|movement\s*in|movement\s*out"),
    ("soh_snapshot", r"soh\s*snapshot|snapshot\s*soh|stock\s*on\s*hand|daily\s*soh"),
    ("inventory_snapshot", r"inventory\s*snapshot"),
    ("availability", r"availability|online\s*availability|unavailable"),
    ("oos_event", r"oos\s*event|out\s*of\s*stock|stockout\s*event"),
    ("missed_sales", r"missed\s*sales"),
    ("pwlogd", r"pwlogd|pwlog"),
)


class PromotionsMaterializedSourceDailyStockTruthSourceDiscoveryError(RuntimeError):
    pass


@dataclass(frozen=True)
class PromotionsMaterializedSourceDailyStockTruthSourceDiscoveryResult:
    discovery_status: str
    promotion_key: str
    promotion_folder_name: str
    pwlogd_sales_only_flag: int
    daily_stock_truth_extract_created_flag: int
    actual_outcome_source_created_flag: int
    source_packets_mutated_flag: int
    operator_audit_overwritten_flag: int
    summary_frame: pd.DataFrame
    candidate_inventory_frame: pd.DataFrame
    gap_analysis_frame: pd.DataFrame
    required_config_frame: pd.DataFrame
    validation_frame: pd.DataFrame
    memo_markdown: str


@dataclass(frozen=True)
class PromotionsMaterializedSourceDailyStockTruthSourceDiscoveryArtifacts:
    output_root: str
    summary_csv_path: str
    candidate_inventory_csv_path: str
    gap_analysis_csv_path: str
    required_config_csv_path: str
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
        raise PromotionsMaterializedSourceDailyStockTruthSourceDiscoveryError(f"CSV not found: {csv_path}")
    try:
        frame = pd.read_csv(csv_path, keep_default_na=False, low_memory=False)
    except pd.errors.EmptyDataError:
        if allow_empty:
            return pd.DataFrame()
        raise PromotionsMaterializedSourceDailyStockTruthSourceDiscoveryError(f"CSV is empty: {csv_path}")
    if frame.empty and not allow_empty:
        raise PromotionsMaterializedSourceDailyStockTruthSourceDiscoveryError(f"CSV is empty: {csv_path}")
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
        raise PromotionsMaterializedSourceDailyStockTruthSourceDiscoveryError(
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


def _scan_text_for_matches(text: str) -> list[tuple[str, str]]:
    matches: list[tuple[str, str]] = []
    lowered = text.lower()
    for name, pattern in KEYWORD_GROUPS:
        found = re.search(pattern, lowered, flags=re.IGNORECASE)
        if found:
            matches.append((name, found.group(0)))
    return matches


def _candidate_row(
    *,
    candidate_name: str,
    candidate_type: str,
    source_scope: str,
    source_path: str,
    supports_sales_truth_flag: int,
    supports_stock_truth_flag: int,
    configured_stock_truth_flag: int,
    evidence: str,
    notes: str,
) -> dict[str, object]:
    return {
        "candidate_name": candidate_name,
        "candidate_type": candidate_type,
        "source_scope": source_scope,
        "source_path": source_path,
        "supports_sales_truth_flag": supports_sales_truth_flag,
        "supports_stock_truth_flag": supports_stock_truth_flag,
        "configured_stock_truth_flag": configured_stock_truth_flag,
        "evidence": evidence,
        "notes": notes,
    }


def _discover_candidates(repo_root: Path) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for relative_path in SOURCE_REFERENCE_FILES:
        path = repo_root / relative_path
        if not path.exists():
            rows.append(
                _candidate_row(
                    candidate_name="SOURCE_FILE_MISSING",
                    candidate_type="missing_reference",
                    source_scope="reference_file",
                    source_path=relative_path,
                    supports_sales_truth_flag=0,
                    supports_stock_truth_flag=0,
                    configured_stock_truth_flag=0,
                    evidence="missing_file",
                    notes="Required reference file is missing for discovery scan.",
                )
            )
            continue

        text = path.read_text(encoding="utf-8", errors="ignore")
        hits = _scan_text_for_matches(text)
        for hit_name, evidence in hits:
            is_pwlogd = int(hit_name == "pwlogd")
            stock_truth = int(
                hit_name
                in {
                    "stock_ledger",
                    "stock_movement",
                    "soh_snapshot",
                    "inventory_snapshot",
                    "availability",
                    "oos_event",
                }
            )
            configured_stock_truth = 0
            if stock_truth and relative_path.endswith("config.py"):
                configured_stock_truth = int(
                    any(
                        key in text
                        for key in (
                            "STOCK_LEDGER_TABLE",
                            "SOH_SNAPSHOT_TABLE",
                            "AVAILABILITY_TABLE",
                            "OOS_EVENT_TABLE",
                        )
                    )
                )
            rows.append(
                _candidate_row(
                    candidate_name=hit_name.upper(),
                    candidate_type="keyword_match",
                    source_scope="code_or_sql_reference",
                    source_path=relative_path,
                    supports_sales_truth_flag=is_pwlogd,
                    supports_stock_truth_flag=stock_truth,
                    configured_stock_truth_flag=configured_stock_truth,
                    evidence=evidence,
                    notes="Keyword-based discovery evidence from local config/runtime/sql reference.",
                )
            )

    if rows:
        frame = pd.DataFrame(rows, columns=CANDIDATE_COLUMNS)
        return frame.drop_duplicates().reset_index(drop=True)
    return pd.DataFrame(
        [
            _candidate_row(
                candidate_name="NO_CANDIDATES_FOUND",
                candidate_type="none",
                source_scope="scan",
                source_path="",
                supports_sales_truth_flag=0,
                supports_stock_truth_flag=0,
                configured_stock_truth_flag=0,
                evidence="",
                notes="No source candidates detected from the discovery keyword scan.",
            )
        ],
        columns=CANDIDATE_COLUMNS,
    )


def _required_config_frame(candidate_inventory_frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    config_candidates = candidate_inventory_frame.loc[
        candidate_inventory_frame["source_path"].astype(str).str.endswith("config.py")
    ]
    config_text = " ".join(config_candidates["evidence"].astype(str).tolist()) + " " + " ".join(
        config_candidates["candidate_name"].astype(str).tolist()
    )

    for key, purpose, example in REQUIRED_CONFIG_KEYS:
        configured_flag = int(key.lower() in config_text.lower())
        rows.append(
            {
                "config_key": key,
                "required_flag": 1,
                "configured_flag": configured_flag,
                "purpose": purpose,
                "recommended_example": example,
            }
        )
    return pd.DataFrame(rows, columns=REQUIRED_CONFIG_COLUMNS)


def _gap_analysis_frame(
    *,
    required_config_frame: pd.DataFrame,
    candidate_inventory_frame: pd.DataFrame,
    pwlogd_sales_only_flag: int,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    configured_any_stock_truth = int(required_config_frame["configured_flag"].astype(int).eq(1).any())
    candidate_stock_truth = int(candidate_inventory_frame["supports_stock_truth_flag"].astype(int).eq(1).any())

    rows.append(
        {
            "gap_name": "PWLOGD_SALES_ONLY_GAP",
            "required_flag": 1,
            "present_flag": pwlogd_sales_only_flag,
            "gap_status": "PASS" if pwlogd_sales_only_flag else "FAIL",
            "details": "PWLOGD must be treated as sales truth only, not stockout truth.",
        }
    )
    rows.append(
        {
            "gap_name": "CONFIGURED_STOCK_TRUTH_SOURCE_GAP",
            "required_flag": 1,
            "present_flag": configured_any_stock_truth,
            "gap_status": "PASS" if configured_any_stock_truth else "MISSING",
            "details": "Configured stock-truth source key(s) are required before extractor build.",
        }
    )
    rows.append(
        {
            "gap_name": "STOCK_TRUTH_CANDIDATE_IN_CODE_GAP",
            "required_flag": 1,
            "present_flag": candidate_stock_truth,
            "gap_status": "PASS" if candidate_stock_truth else "MISSING",
            "details": "Discovery should find stock-related candidates in code/sql references.",
        }
    )
    return pd.DataFrame(rows, columns=GAP_COLUMNS)


def _determine_status(
    *,
    contract_ready_flag: int,
    required_config_frame: pd.DataFrame,
    candidate_inventory_frame: pd.DataFrame,
) -> str:
    configured_any_stock_truth = int(required_config_frame["configured_flag"].astype(int).eq(1).any())
    candidate_stock_truth = int(candidate_inventory_frame["supports_stock_truth_flag"].astype(int).eq(1).any())

    if contract_ready_flag and configured_any_stock_truth:
        return STATUS_READY
    if contract_ready_flag and (candidate_stock_truth or not configured_any_stock_truth):
        return STATUS_CONFIG_REQUIRED
    return STATUS_NOT_FOUND


def build_promotions_materialized_source_daily_stock_truth_source_discovery(
    *,
    packet_root: str | Path,
    promotion_key: str,
    output_root: str | Path | None = None,
) -> PromotionsMaterializedSourceDailyStockTruthSourceDiscoveryResult:
    packet_root_path = Path(packet_root)
    contract_root = packet_root_path / CONTRACT_PLAN_FOLDER_NAME
    repo_root = Path(__file__).resolve().parents[3]
    promotion_folder_name = _promotion_folder_from_key(promotion_key)
    source_folder = packet_root_path / SOURCE_MATERIALIZED_FOLDER_NAME / promotion_folder_name

    contract_summary = _read_csv(contract_root / CONTRACT_SUMMARY_FILE_NAME)
    _ = _read_csv(contract_root / CONTRACT_SCHEMA_FILE_NAME)
    contract_requirements = _read_csv(contract_root / CONTRACT_SOURCE_REQUIREMENTS_FILE_NAME)

    contract_metrics = _metric_lookup(contract_summary)
    contract_status = _normalize_text(contract_metrics.get("CONTRACT_STATUS"))
    contract_ready_flag = int(contract_status == CONTRACT_READY_STATUS)

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

    candidate_inventory_frame = _discover_candidates(repo_root)
    required_config_frame = _required_config_frame(candidate_inventory_frame)
    pwlogd_sales_only_flag = int(
        contract_requirements.loc[
            contract_requirements["source_name"].astype(str).eq("PWLOGD_TABLE"),
            "source_status",
        ].astype(str).eq("SALES_TRUTH_ONLY_NOT_STOCKOUT_TRUTH").any()
        or candidate_inventory_frame["candidate_name"].astype(str).eq("PWLOGD").any()
    )
    gap_analysis_frame = _gap_analysis_frame(
        required_config_frame=required_config_frame,
        candidate_inventory_frame=candidate_inventory_frame,
        pwlogd_sales_only_flag=pwlogd_sales_only_flag,
    )
    discovery_status = _determine_status(
        contract_ready_flag=contract_ready_flag,
        required_config_frame=required_config_frame,
        candidate_inventory_frame=candidate_inventory_frame,
    )

    source_rows_after = promotion_source_rows_path.read_bytes() if promotion_source_rows_path.exists() else b""
    operator_after = operator_audit_path.read_bytes() if operator_audit_path.exists() else b""
    actual_outcome_after = int(actual_outcome_source_path.exists())
    daily_stock_truth_after = int(daily_stock_truth_extract_path.exists())

    source_packets_mutated_flag = int(source_rows_before != source_rows_after)
    operator_audit_overwritten_flag = int(operator_before != operator_after)
    actual_outcome_source_created_flag = int(actual_outcome_before == 0 and actual_outcome_after == 1)
    daily_stock_truth_extract_created_flag = int(daily_stock_truth_before == 0 and daily_stock_truth_after == 1)

    missing_config_keys = required_config_frame.loc[
        required_config_frame["configured_flag"].astype(int).eq(0),
        "config_key",
    ].astype(str).tolist()
    stock_candidates = candidate_inventory_frame.loc[
        candidate_inventory_frame["supports_stock_truth_flag"].astype(int).eq(1),
        "candidate_name",
    ].astype(str).tolist()

    summary_frame = pd.DataFrame(
        [
            _summary_row("DISCOVERY_STATUS", discovery_status, "Daily stock-truth source discovery status."),
            _summary_row("PROMOTION_KEY", promotion_key, "Promotion key under source discovery/config check."),
            _summary_row("PROMOTION_FOLDER_NAME", promotion_folder_name, "Promotion-scoped source folder name."),
            _summary_row("CONTRACT_STATUS_USED", contract_status, "Input contract status from stock-truth contract planner."),
            _summary_row("PWLOGD_SALES_ONLY_FLAG", pwlogd_sales_only_flag, "PWLOGD is treated as sales-only truth source."),
            _summary_row("STOCK_TRUTH_CANDIDATE_COUNT", int(len(stock_candidates)), "Count of stock-truth candidate hits found in code/config scan."),
            _summary_row("MISSING_CONFIG_COUNT", int(len(missing_config_keys)), "Count of missing recommended stock-truth configuration keys."),
            _summary_row("MISSING_CONFIG_KEYS", ",".join(missing_config_keys), "Comma-separated missing required config keys."),
            _summary_row("DAILY_STOCK_TRUTH_EXTRACT_CREATED_FLAG", daily_stock_truth_extract_created_flag, "Planner must not create daily stock-truth extract."),
            _summary_row("ACTUAL_OUTCOME_SOURCE_CREATED_FLAG", actual_outcome_source_created_flag, "Planner must not create actual_outcome_source.csv."),
            _summary_row("SOURCE_PACKETS_MUTATED_FLAG", source_packets_mutated_flag, "Planner must not mutate promotion_source_rows.csv."),
            _summary_row("OPERATOR_AUDIT_OVERWRITTEN_FLAG", operator_audit_overwritten_flag, "Planner must not overwrite operator_audit_source.csv."),
        ],
        columns=SUMMARY_COLUMNS,
    )

    validation_frame = pd.DataFrame(
        [
            _validation_row("EXPECTED_STATUS_CONFIG_REQUIRED", int(discovery_status == STATUS_CONFIG_REQUIRED), f"discovery_status={discovery_status}"),
            _validation_row("PWLOGD_SALES_ONLY", int(pwlogd_sales_only_flag == 1), "PWLOGD appears as sales-only reference and not stockout truth."),
            _validation_row("MISSING_STOCK_TRUTH_CONFIG_REPORTED", int(len(missing_config_keys) > 0), "Missing stock-truth config keys are reported."),
            _validation_row("REQUIRED_CONFIG_WRITTEN", int(required_config_frame.empty is False), "Required config recommendations are emitted."),
            _validation_row("NO_DAILY_STOCK_TRUTH_EXTRACT_CREATED", int(daily_stock_truth_extract_created_flag == 0), "Planner did not create daily stock-truth extract."),
            _validation_row("NO_ACTUAL_OUTCOME_SOURCE_CREATED", int(actual_outcome_source_created_flag == 0), "Planner did not create actual_outcome_source.csv."),
            _validation_row("SOURCE_PACKETS_UNCHANGED", int(source_packets_mutated_flag == 0), "promotion_source_rows.csv remained unchanged."),
            _validation_row("OPERATOR_AUDIT_UNCHANGED", int(operator_audit_overwritten_flag == 0), "operator_audit_source.csv remained unchanged."),
        ],
        columns=VALIDATION_COLUMNS,
    )

    memo_markdown = "\n".join(
        [
            "# Daily Stock Truth Source Discovery",
            "",
            "Planner-only source discovery/config check for governed daily stock-truth capability.",
            "This runtime does not connect to SQL, does not query any database, and does not build extracts.",
            "No ACTUAL_OUTCOME file creation is performed.",
            "",
            f"Discovery status: {discovery_status}",
            f"Contract input status: {contract_status}",
            f"PWLOGD sales-only flag: {pwlogd_sales_only_flag}",
            "",
            "Current finding: sales truth references exist (PWLOGD), but governed stock-truth configuration keys are still required.",
            "This pass is source discovery/config check only.",
        ]
    )

    return PromotionsMaterializedSourceDailyStockTruthSourceDiscoveryResult(
        discovery_status=discovery_status,
        promotion_key=promotion_key,
        promotion_folder_name=promotion_folder_name,
        pwlogd_sales_only_flag=pwlogd_sales_only_flag,
        daily_stock_truth_extract_created_flag=daily_stock_truth_extract_created_flag,
        actual_outcome_source_created_flag=actual_outcome_source_created_flag,
        source_packets_mutated_flag=source_packets_mutated_flag,
        operator_audit_overwritten_flag=operator_audit_overwritten_flag,
        summary_frame=summary_frame,
        candidate_inventory_frame=candidate_inventory_frame,
        gap_analysis_frame=gap_analysis_frame,
        required_config_frame=required_config_frame,
        validation_frame=validation_frame,
        memo_markdown=memo_markdown,
    )


def write_promotions_materialized_source_daily_stock_truth_source_discovery(
    *,
    packet_root: str | Path,
    promotion_key: str,
    output_root: str | Path | None = None,
) -> PromotionsMaterializedSourceDailyStockTruthSourceDiscoveryArtifacts:
    packet_root_path = Path(packet_root)
    output_root_path = _resolve_output_root(packet_root_path, output_root)

    result = build_promotions_materialized_source_daily_stock_truth_source_discovery(
        packet_root=packet_root,
        promotion_key=promotion_key,
        output_root=output_root,
    )

    output_root_path.mkdir(parents=True, exist_ok=True)

    summary_path = output_root_path / SUMMARY_FILE_NAME
    candidate_inventory_path = output_root_path / CANDIDATE_INVENTORY_FILE_NAME
    gap_analysis_path = output_root_path / GAP_ANALYSIS_FILE_NAME
    required_config_path = output_root_path / REQUIRED_CONFIG_FILE_NAME
    validation_path = output_root_path / VALIDATION_FILE_NAME
    memo_path = output_root_path / MEMO_FILE_NAME

    result.summary_frame.to_csv(summary_path, index=False)
    result.candidate_inventory_frame.to_csv(candidate_inventory_path, index=False)
    result.gap_analysis_frame.to_csv(gap_analysis_path, index=False)
    result.required_config_frame.to_csv(required_config_path, index=False)
    result.validation_frame.to_csv(validation_path, index=False)
    memo_path.write_text(result.memo_markdown, encoding="utf-8")

    return PromotionsMaterializedSourceDailyStockTruthSourceDiscoveryArtifacts(
        output_root=str(output_root_path),
        summary_csv_path=str(summary_path),
        candidate_inventory_csv_path=str(candidate_inventory_path),
        gap_analysis_csv_path=str(gap_analysis_path),
        required_config_csv_path=str(required_config_path),
        validation_csv_path=str(validation_path),
        memo_md_path=str(memo_path),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build planner-only daily stock-truth source discovery/config check artifacts."
    )
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--promotion-key", required=True)
    parser.add_argument("--output-root")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)

    artifacts = write_promotions_materialized_source_daily_stock_truth_source_discovery(
        packet_root=args.packet_root,
        promotion_key=args.promotion_key,
        output_root=args.output_root,
    )

    summary = _read_csv(artifacts.summary_csv_path, allow_empty=True)
    metrics = _metric_lookup(summary)

    print("discovery_status", _normalize_text(metrics.get("DISCOVERY_STATUS", "")))
    print("pwlogd_sales_only_flag", _normalize_text(metrics.get("PWLOGD_SALES_ONLY_FLAG", 0)))
    print("stock_truth_candidate_count", _normalize_text(metrics.get("STOCK_TRUTH_CANDIDATE_COUNT", 0)))
    print("missing_config_count", _normalize_text(metrics.get("MISSING_CONFIG_COUNT", 0)))
    print("daily_stock_truth_extract_created_flag", _normalize_text(metrics.get("DAILY_STOCK_TRUTH_EXTRACT_CREATED_FLAG", 0)))
    print("actual_outcome_source_created_flag", _normalize_text(metrics.get("ACTUAL_OUTCOME_SOURCE_CREATED_FLAG", 0)))
    print("source_packets_mutated_flag", _normalize_text(metrics.get("SOURCE_PACKETS_MUTATED_FLAG", 0)))
    print("operator_audit_overwritten_flag", _normalize_text(metrics.get("OPERATOR_AUDIT_OVERWRITTEN_FLAG", 0)))
    print("daily_stock_truth_source_discovery_summary", artifacts.summary_csv_path)
    print("daily_stock_truth_source_candidate_inventory", artifacts.candidate_inventory_csv_path)
    print("daily_stock_truth_source_gap_analysis", artifacts.gap_analysis_csv_path)
    print("daily_stock_truth_source_required_config", artifacts.required_config_csv_path)
    print("daily_stock_truth_source_discovery_validation", artifacts.validation_csv_path)
    print("daily_stock_truth_source_discovery_memo", artifacts.memo_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
