from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.runtime.promotions.run_promotions_materialized_source_operator_audit_remediation_plan import (
    APPROVED_JOIN_KEY,
    RECOMMENDED_OPERATOR_AUDIT_FILE_NAME,
    build_promotions_materialized_source_operator_audit_remediation_plan,
    write_promotions_materialized_source_operator_audit_remediation_plan,
)


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def _build_packet_root(tmp_path: Path) -> Path:
    packet_root = tmp_path / "packet_root"
    source_root = packet_root / "tmp" / "last5_promotions_diagnostic_packets" / "source_materialized_promotions"
    source_folder = source_root / "promotion_772-2026-05-07-2026-05-20-allocation-report-wk45-46-baby-you-box"
    source_folder.mkdir(parents=True, exist_ok=True)

    _write_csv(
        source_folder / "promotion_source_manifest.csv",
        pd.DataFrame(
            [
                {
                    "store_number": "772",
                    "promotion_start_date": "2026-05-07",
                    "promotion_end_date": "2026-05-20",
                    "promotion_name": "Allocation Report - WK45&46 BABY & YOU BOX",
                }
            ]
        ),
    )
    _write_csv(source_folder / "promotion_source_rows.csv", pd.DataFrame([{"store_number": "772"}]))
    _write_csv(source_folder / "promotion_source_summary.csv", pd.DataFrame([{"metric_name": "X", "metric_value": 1, "metric_display": "1", "notes": "n"}]))

    stage_1_root = packet_root / "tmp" / "promotions_local_inspection" / "promotion_772-2026-05-07-2026-05-20-allocation-report-wk45-46-baby-you-box" / "materialized_source_join_key_validation"
    stage_2_root = packet_root / "tmp" / "promotions_local_inspection" / "promotion_772-2026-05-07-2026-05-20-allocation-report-wk45-46-baby-you-box" / "materialized_source_join_spec_pack"
    queue_root = packet_root / "tmp" / "last5_promotions_diagnostic_packets" / "materialized_source_multi_promotion_reconstruction_queue"
    isolation_root = packet_root / "tmp" / "last5_promotions_diagnostic_packets" / "materialized_source_promotion_isolation_plan"

    _write_csv(
        stage_1_root / "materialized_source_join_key_validation_summary.csv",
        pd.DataFrame(
            [
                {"metric_name": "OPERATOR_SOURCE_STATUS", "metric_value": "JOIN_SOURCE_NOT_AVAILABLE", "metric_display": "JOIN_SOURCE_NOT_AVAILABLE", "notes": "n"},
                {"metric_name": "ACTUAL_SOURCE_STATUS", "metric_value": "JOIN_BLOCKED_MISSING_KEYS", "metric_display": "JOIN_BLOCKED_MISSING_KEYS", "notes": "n"},
            ]
        ),
    )
    _write_csv(
        stage_2_root / "materialized_source_join_spec_summary.csv",
        pd.DataFrame(
            [
                {"metric_name": "SPEC_STATUS", "metric_value": "SPEC_BLOCKED_MISSING_SOURCE", "metric_display": "SPEC_BLOCKED_MISSING_SOURCE", "notes": "n"},
                {"metric_name": "OPERATOR_SOURCE_INCLUDED_FLAG", "metric_value": 0, "metric_display": "0", "notes": "n"},
            ]
        ),
    )
    _write_csv(
        queue_root / "multi_promotion_reconstruction_queue_by_promotion.csv",
        pd.DataFrame(
            [
                {
                    "promotion_key": "772|2026-05-07|2026-05-20|Allocation Report - WK45&46 BABY & YOU BOX",
                    "queue_status": "PROMOTION_RECONSTRUCTION_READY_TO_START",
                    "execution_mode_recommendation": "PLANNER_ONLY",
                }
            ]
        ),
    )
    _write_csv(
        isolation_root / "promotion_isolation_plan_summary.csv",
        pd.DataFrame(
            [
                {"metric_name": "ISOLATION_PLAN_STATUS", "metric_value": "PROMOTION_ISOLATION_PLAN_READY_RUNTIME_CHANGES_REQUIRED", "metric_display": "PROMOTION_ISOLATION_PLAN_READY_RUNTIME_CHANGES_REQUIRED", "notes": "n"},
                {"metric_name": "SHARED_ROOT_RISK_STATUS", "metric_value": "SHARED_ROOT_RISK_CONFIRMED", "metric_display": "SHARED_ROOT_RISK_CONFIRMED", "notes": "n"},
            ]
        ),
    )
    return packet_root


def test_operator_audit_remediation_plan_reports_missing_source_contract(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path)
    expected_path = (
        packet_root
        / "tmp"
        / "last5_promotions_diagnostic_packets"
        / "source_materialized_promotions"
        / "promotion_772-2026-05-07-2026-05-20-allocation-report-wk45-46-baby-you-box"
        / RECOMMENDED_OPERATOR_AUDIT_FILE_NAME
    )

    result = build_promotions_materialized_source_operator_audit_remediation_plan(
        packet_root=packet_root,
        promotion_key="772|2026-05-07|2026-05-20|Allocation Report - WK45&46 BABY & YOU BOX",
    )

    assert result.remediation_status == "OPERATOR_AUDIT_REMEDIATION_REQUIRED"
    assert result.operator_audit_like_file_exists_flag == 0
    assert result.data_materialization_remediation_required_flag == 1
    assert result.code_change_required_flag == 0
    assert result.stage_1_operator_source_status == "JOIN_SOURCE_NOT_AVAILABLE"
    assert result.stage_2_spec_status == "SPEC_BLOCKED_MISSING_SOURCE"
    assert result.required_file_contract_frame.loc[0, "file_name"] == RECOMMENDED_OPERATOR_AUDIT_FILE_NAME
    assert result.required_file_contract_frame.loc[0, "expected_location"] == str(expected_path)
    assert result.summary_frame.loc[result.summary_frame["metric_name"].eq("EXPECTED_OPERATOR_AUDIT_FILE_PATH"), "metric_value"].iloc[0] == str(expected_path)
    assert result.expected_schema_frame["field_name"].tolist()[:4] == ["store_number", "promotion_start_date", "promotion_end_date", "promotion_name"]
    assert f"Expected file path: {expected_path}" in result.memo_markdown
    assert "Stage 3 must not be rerun" in result.memo_markdown


def test_operator_audit_remediation_plan_accepts_valid_candidate_and_requires_stage_1_2_recheck(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path)
    candidate_path = packet_root / "tmp" / "last5_promotions_diagnostic_packets" / "source_materialized_promotions" / RECOMMENDED_OPERATOR_AUDIT_FILE_NAME
    _write_csv(
        candidate_path,
        pd.DataFrame(
            [
                {
                    "store_number": "772",
                    "promotion_start_date": "2026-05-07",
                    "promotion_end_date": "2026-05-20",
                    "promotion_name": "Allocation Report - WK45&46 BABY & YOU BOX",
                    "sku_number": "12345",
                    "sku_description": "Example",
                    "operator_audit_status": "APPROVED",
                    "operator_audit_decision": "APPROVE",
                    "operator_audit_reason": "Ready",
                    "operator_audit_timestamp": "2026-06-01T00:00:00Z",
                    "operator_audit_user": "planner",
                    "approved_join_key": APPROVED_JOIN_KEY,
                }
            ]
        ),
    )

    result = build_promotions_materialized_source_operator_audit_remediation_plan(
        packet_root=packet_root,
        promotion_key="772|2026-05-07|2026-05-20|Allocation Report - WK45&46 BABY & YOU BOX",
    )

    assert result.remediation_status == "OPERATOR_AUDIT_REMEDIATION_READY_FOR_STAGE_1_2_RECHECK"
    assert result.operator_audit_like_file_exists_flag == 1
    assert result.data_materialization_remediation_required_flag == 0
    assert result.validation_frame.loc[result.validation_frame["validation_name"].eq("MATERIALIZATION_REMEDIATION_REQUIRED"), "validation_flag"].iloc[0] == 0
    assert result.validation_frame.loc[result.validation_frame["validation_name"].eq("STAGE_1_2_RECHECK_REQUIRED"), "validation_flag"].iloc[0] == 1


def test_operator_audit_remediation_plan_writes_planner_artifacts(tmp_path: Path) -> None:
    packet_root = _build_packet_root(tmp_path)
    output_root = tmp_path / "output"

    artifacts = write_promotions_materialized_source_operator_audit_remediation_plan(
        packet_root=packet_root,
        promotion_key="772|2026-05-07|2026-05-20|Allocation Report - WK45&46 BABY & YOU BOX",
        output_root=output_root,
    )

    assert Path(artifacts.summary_csv_path).exists()
    assert Path(artifacts.expected_schema_csv_path).exists()
    assert Path(artifacts.required_file_contract_csv_path).exists()
    assert Path(artifacts.remediation_validation_csv_path).exists()
    assert Path(artifacts.memo_md_path).exists()