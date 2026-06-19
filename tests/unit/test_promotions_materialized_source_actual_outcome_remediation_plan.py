from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.run_promotions_materialized_source_actual_outcome_remediation_plan import (  # noqa: E402
    REMEDIATION_STATUS_REQUIRED,
    build_promotions_materialized_source_actual_outcome_remediation_plan,
    write_promotions_materialized_source_actual_outcome_remediation_plan,
)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def _promotion_key() -> str:
    return "772|2026-05-07|2026-05-20|Allocation Report - WK45&46 BABY & YOU BOX"


def _promotion_folder_name() -> str:
    return "promotion_772-2026-05-07-2026-05-20-allocation-report-wk45-46-baby-you-box"


def _actual_outcome_path(packet_root: Path) -> Path:
    return (
        packet_root
        / "tmp"
        / "promotions_local_inspection"
        / "completed-stage3-operator-wide-20260502a"
        / "completed-stage3-operator-wide-20260502a_inspection_review_packet.csv"
    )


def _build_packet_root(tmp_path: Path) -> Path:
    packet_root = tmp_path / "packet_root"
    promotion_folder = _promotion_folder_name()

    stage1_root = (
        packet_root
        / "promotion_runs"
        / promotion_folder
        / "materialized_source_join_key_validation"
    )
    _write_csv(
        stage1_root / "materialized_source_join_key_validation_summary.csv",
        [
            {
                "metric_name": "ACTUAL_SOURCE_STATUS",
                "metric_value": "JOIN_BLOCKED_MISSING_KEYS",
                "metric_display": "JOIN_BLOCKED_MISSING_KEYS",
                "notes": "actual blocked",
            },
            {
                "metric_name": "JOIN_SAFE_TO_EXECUTE_NEXT_FLAG",
                "metric_value": 0,
                "metric_display": "0",
                "notes": "not safe",
            },
        ],
    )

    actual_source_path = _actual_outcome_path(packet_root)
    _write_csv(
        stage1_root / "materialized_source_join_key_validation_plan.csv",
        [
            {
                "promotion_key": _promotion_key(),
                "promotion_name": "Allocation Report - WK45&46 BABY & YOU BOX",
                "promotion_folder_name": promotion_folder,
                "candidate_source_role": "ACTUAL_OUTCOME",
                "operator_audit_discovery_source": "",
                "operator_audit_source_path": "",
                "candidate_source_path": str(actual_source_path),
                "recommended_join_key": "store_number + promotion_start_date + promotion_name + sku_number",
                "source_row_count": 3275,
                "source_unique_sku_count": 3274,
                "candidate_source_row_count": 150786,
                "candidate_source_unique_sku_count": 0,
                "matched_source_rows": 0,
                "unmatched_source_rows": 3275,
                "match_rate": 0.0,
                "duplicate_key_count_source": 0,
                "duplicate_key_count_candidate": 0,
                "one_to_one_join_safe_flag": 0,
                "many_to_one_join_risk_flag": 0,
                "row_explosion_risk_flag": 0,
                "join_readiness_status": "JOIN_BLOCKED_MISSING_KEYS",
                "safe_to_execute_next_flag": 0,
                "recommended_next_step": "restore keys",
                "reason": "missing sku_number",
            },
            {
                "promotion_key": _promotion_key(),
                "promotion_name": "Allocation Report - WK45&46 BABY & YOU BOX",
                "promotion_folder_name": promotion_folder,
                "candidate_source_role": "OPERATOR_AUDIT",
                "operator_audit_discovery_source": "PROMOTION_SCOPED_GOVERNED_FILE",
                "operator_audit_source_path": str(
                    packet_root
                    / "source_materialized_promotions"
                    / promotion_folder
                    / "operator_audit_source.csv"
                ),
                "candidate_source_path": str(
                    packet_root
                    / "source_materialized_promotions"
                    / promotion_folder
                    / "operator_audit_source.csv"
                ),
                "recommended_join_key": "store_number + promotion_start_date + promotion_name + sku_number",
                "source_row_count": 3275,
                "source_unique_sku_count": 3274,
                "candidate_source_row_count": 3274,
                "candidate_source_unique_sku_count": 3274,
                "matched_source_rows": 3274,
                "unmatched_source_rows": 1,
                "match_rate": 0.999695,
                "duplicate_key_count_source": 0,
                "duplicate_key_count_candidate": 0,
                "one_to_one_join_safe_flag": 0,
                "many_to_one_join_risk_flag": 0,
                "row_explosion_risk_flag": 0,
                "join_readiness_status": "JOIN_READY",
                "safe_to_execute_next_flag": 1,
                "recommended_next_step": "author join spec",
                "reason": "ready",
            },
        ],
    )

    _write_csv(
        actual_source_path,
        [
            {
                "promotion_row_key": "r1",
                "promotion_name": "Allocation Report - WK45&46 BABY & YOU BOX",
                "supplier": "ACME",
                "department": "Beauty",
                "store_number": "772",
                "promotion_start_date": "2026-05-07",
                "promotion_end_date": "2026-05-20",
                "predicted_units_first_day": 10,
                "predicted_sell_through_pct": 0.12,
                "predicted_sales_ex_gst": 100.0,
                "predicted_gross_profit": 35.0,
                "margin_risk_penalty": 0.1,
                "leftover_risk_penalty": 0.2,
                "stockout_risk_penalty": 0.3,
                "overallocation_risk_penalty": 0.4,
                "underallocation_risk_penalty": 0.5,
                "archetype_primary": "A",
                "archetype_secondary": "B",
                "final_decision_score": 0.8,
                "final_confidence_score": 0.6,
                "decision_recommendation": "hold",
                "decision_recommendation_reason": "review",
            },
            {
                "promotion_row_key": "r2",
                "promotion_name": "Allocation Report - WK45&46 BABY & YOU BOX",
                "supplier": "ACME",
                "department": "Beauty",
                "store_number": "772",
                "promotion_start_date": "2026-05-07",
                "promotion_end_date": "2026-05-20",
                "predicted_units_first_day": 11,
                "predicted_sell_through_pct": 0.13,
                "predicted_sales_ex_gst": 101.0,
                "predicted_gross_profit": 36.0,
                "margin_risk_penalty": 0.1,
                "leftover_risk_penalty": 0.2,
                "stockout_risk_penalty": 0.3,
                "overallocation_risk_penalty": 0.4,
                "underallocation_risk_penalty": 0.5,
                "archetype_primary": "A",
                "archetype_secondary": "B",
                "final_decision_score": 0.8,
                "final_confidence_score": 0.6,
                "decision_recommendation": "hold",
                "decision_recommendation_reason": "review",
            },
        ],
    )

    source_folder = packet_root / "source_materialized_promotions" / promotion_folder
    _write_csv(
        source_folder / "promotion_source_rows.csv",
        [
            {
                "store_number": "772",
                "promotion_start_date": "2026-05-07",
                "promotion_name": "Allocation Report - WK45&46 BABY & YOU BOX",
                "sku_number": "1001",
            }
        ],
    )
    _write_csv(
        source_folder / "operator_audit_source.csv",
        [
            {
                "store_number": "772",
                "promotion_start_date": "2026-05-07",
                "promotion_name": "ALLOCATION REPORT - WK45&46 BABY & YOU BOX",
                "sku_number": "1001",
                "operator_audit_status": "PENDING_OPERATOR_REVIEW",
            }
        ],
    )

    _write_csv(
        source_folder / "promotion_source_manifest.csv",
        [
            {
                "store_number": "772",
                "promotion_start_date": "2026-05-07",
                "promotion_end_date": "2026-05-20",
                "promotion_name": "Allocation Report - WK45&46 BABY & YOU BOX",
            }
        ],
    )

    return packet_root


class PromotionsMaterializedSourceActualOutcomeRemediationPlanTests(unittest.TestCase):
    def test_reports_remediation_required_when_stage1_missing_sku_number(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            result = build_promotions_materialized_source_actual_outcome_remediation_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            self.assertEqual(result.remediation_status, REMEDIATION_STATUS_REQUIRED)

    def test_records_source_path_and_existence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            result = build_promotions_materialized_source_actual_outcome_remediation_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            self.assertTrue(result.actual_outcome_source_path.endswith("completed-stage3-operator-wide-20260502a_inspection_review_packet.csv"))
            self.assertEqual(result.actual_outcome_source_exists_flag, 1)
            self.assertEqual(result.actual_outcome_source_row_count, 2)
            self.assertEqual(result.actual_outcome_source_column_count, 22)

    def test_records_missing_required_join_key_sku_number(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            result = build_promotions_materialized_source_actual_outcome_remediation_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            self.assertIn("sku_number", result.missing_required_join_keys)

    def test_records_no_safe_sku_alias_when_none_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            result = build_promotions_materialized_source_actual_outcome_remediation_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            self.assertEqual(result.sku_like_columns_found, ())
            self.assertEqual(result.safe_sku_alias_exists_flag, 0)

    def test_writes_required_source_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            artifacts = write_promotions_materialized_source_actual_outcome_remediation_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            contract = pd.read_csv(artifacts.required_contract_csv_path, keep_default_na=False, low_memory=False)
            fields = list(contract["contract_field"].astype(str))
            self.assertEqual(fields, [
                "store_number",
                "promotion_start_date",
                "promotion_name",
                "sku_number",
                "actual_units",
                "actual_sales_ex_gst",
                "actual_gross_profit",
                "actual_stockout_flag",
                "actual_leftover_units",
                "actual_result_source",
                "actual_result_as_of_date",
            ])

    def test_does_not_mutate_promotion_source_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            source_rows = packet_root / "source_materialized_promotions" / _promotion_folder_name() / "promotion_source_rows.csv"
            before = source_rows.read_bytes()
            result = build_promotions_materialized_source_actual_outcome_remediation_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            self.assertEqual(result.source_packets_mutated_flag, 0)
            self.assertEqual(source_rows.read_bytes(), before)

    def test_does_not_overwrite_operator_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            operator_path = packet_root / "source_materialized_promotions" / _promotion_folder_name() / "operator_audit_source.csv"
            before = operator_path.read_bytes()
            result = build_promotions_materialized_source_actual_outcome_remediation_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            self.assertEqual(result.operator_audit_overwritten_flag, 0)
            self.assertEqual(operator_path.read_bytes(), before)

    def test_does_not_create_actual_outcome_governed_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            governed_path = packet_root / "source_materialized_promotions" / _promotion_folder_name() / "actual_outcome_source.csv"
            self.assertFalse(governed_path.exists())
            result = build_promotions_materialized_source_actual_outcome_remediation_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            self.assertEqual(result.actual_outcome_governed_file_created_flag, 0)
            self.assertFalse(governed_path.exists())

    def test_candidate_search_reports_no_ready_promotion_scoped_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            artifacts = write_promotions_materialized_source_actual_outcome_remediation_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            candidates = pd.read_csv(artifacts.candidate_search_csv_path, keep_default_na=False, low_memory=False)
            if candidates.empty:
                self.assertTrue(True)
            else:
                self.assertFalse(candidates["contains_all_required_join_keys_flag"].astype(int).eq(1).any())


if __name__ == "__main__":
    unittest.main()
