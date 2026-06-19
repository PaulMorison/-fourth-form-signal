from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.run_promotions_materialized_source_actual_outcome_source_contract_plan import (  # noqa: E402
    STATUS_READY,
    build_promotions_materialized_source_actual_outcome_source_contract_plan,
    write_promotions_materialized_source_actual_outcome_source_contract_plan,
)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def _promotion_key() -> str:
    return "772|2026-05-07|2026-05-20|Allocation Report - WK45&46 BABY & YOU BOX"


def _promotion_folder_name() -> str:
    return "promotion_772-2026-05-07-2026-05-20-allocation-report-wk45-46-baby-you-box"


def _build_packet_root(tmp_path: Path) -> Path:
    packet_root = tmp_path / "packet_root"
    promotion_folder = _promotion_folder_name()

    remediation_root = packet_root / "materialized_source_actual_outcome_remediation_plan"
    _write_csv(
        remediation_root / "actual_outcome_remediation_summary.csv",
        [
            {
                "metric_name": "REMEDIATION_STATUS",
                "metric_value": "ACTUAL_OUTCOME_REMEDIATION_REQUIRED",
                "metric_display": "ACTUAL_OUTCOME_REMEDIATION_REQUIRED",
                "notes": "required",
            },
            {
                "metric_name": "PROMOTION_FOLDER_NAME",
                "metric_value": promotion_folder,
                "metric_display": promotion_folder,
                "notes": "folder",
            },
            {
                "metric_name": "MISSING_REQUIRED_JOIN_KEYS",
                "metric_value": "sku_number",
                "metric_display": "sku_number",
                "notes": "missing sku",
            },
        ],
    )

    _write_csv(
        remediation_root / "actual_outcome_source_schema_diagnosis.csv",
        [
            {
                "promotion_key": _promotion_key(),
                "promotion_folder_name": promotion_folder,
                "actual_outcome_source_path": str(packet_root / "tmp" / "promotions_local_inspection" / "review_packet.csv"),
                "actual_outcome_source_exists_flag": 1,
                "actual_outcome_source_row_count": 150786,
                "actual_outcome_source_column_count": 22,
                "actual_outcome_source_columns": "promotion_row_key; promotion_name; store_number",
                "missing_required_join_keys": "sku_number",
                "sku_like_columns_found": "",
                "safe_sku_alias_exists_flag": 0,
                "stage1_actual_source_status": "JOIN_BLOCKED_MISSING_KEYS",
            }
        ],
    )

    _write_csv(
        remediation_root / "actual_outcome_required_contract.csv",
        [
            {"contract_field": "store_number", "required_flag": 1, "notes": "required"},
            {"contract_field": "promotion_start_date", "required_flag": 1, "notes": "required"},
            {"contract_field": "promotion_name", "required_flag": 1, "notes": "required"},
            {"contract_field": "sku_number", "required_flag": 1, "notes": "required"},
            {"contract_field": "actual_units", "required_flag": 1, "notes": "required"},
        ],
    )

    source_folder = packet_root / "source_materialized_promotions" / promotion_folder
    _write_csv(
        source_folder / "promotion_source_summary.csv",
        [
            {
                "promotion_key": _promotion_key(),
                "promotion_name": "Allocation Report - WK45&46 BABY & YOU BOX",
                "promotion_start_date": "2026-05-07",
                "promotion_end_date": "2026-05-20",
                "row_count": 3275,
                "sku_count": 3274,
            }
        ],
    )
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
            }
        ],
    )

    return packet_root


class PromotionsMaterializedSourceActualOutcomeSourceContractPlanTests(unittest.TestCase):
    def test_returns_ready_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            result = build_promotions_materialized_source_actual_outcome_source_contract_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            self.assertEqual(result.contract_status, STATUS_READY)

    def test_contract_schema_includes_required_join_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            result = build_promotions_materialized_source_actual_outcome_source_contract_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            fields = set(result.contract_schema_frame["field_name"].astype(str))
            self.assertTrue({"store_number", "promotion_start_date", "promotion_name", "sku_number"}.issubset(fields))

    def test_contract_schema_includes_required_outcome_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            result = build_promotions_materialized_source_actual_outcome_source_contract_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            fields = set(result.contract_schema_frame["field_name"].astype(str))
            self.assertTrue({
                "actual_units",
                "actual_sales_ex_gst",
                "actual_gross_profit",
                "actual_stockout_flag",
                "actual_leftover_units",
                "actual_result_source",
                "actual_result_as_of_date",
            }.issubset(fields))

    def test_contract_schema_includes_optional_governance_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            result = build_promotions_materialized_source_actual_outcome_source_contract_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            fields = set(result.contract_schema_frame["field_name"].astype(str))
            self.assertTrue({
                "actual_outcome_window_start_date",
                "actual_outcome_window_end_date",
                "currency_code",
                "data_version_id",
                "extraction_run_id",
                "actual_stockout_flag_confidence",
                "actual_stockout_flag_source",
                "actual_stockout_flag_basis",
                "actual_stockout_observed_at_grain",
            }.issubset(fields))

    def test_source_of_truth_rejects_inspection_review_packet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            artifacts = write_promotions_materialized_source_actual_outcome_source_contract_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            truth = pd.read_csv(artifacts.source_of_truth_csv_path, keep_default_na=False, low_memory=False)
            rejected = truth.loc[truth["source_option"].astype(str).eq("INSPECTION_REVIEW_PACKET")].iloc[0]
            self.assertEqual(int(rejected["allowed_for_governed_actual_outcome_flag"]), 0)

    def test_validation_gates_include_required_gate_families(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            artifacts = write_promotions_materialized_source_actual_outcome_source_contract_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            gates = pd.read_csv(artifacts.validation_gates_csv_path, keep_default_na=False, low_memory=False)
            gate_names = set(gates["gate_name"].astype(str))
            self.assertTrue({
                "SCHEMA_GATE",
                "KEY_COMPLETENESS_GATE",
                "KEY_UNIQUENESS_GATE",
                "NUMERIC_QUALITY_GATE",
                "STOCKOUT_TRUTH_GATE",
                "STOCKOUT_PROVENANCE_GATE",
                "PROVENANCE_GATE",
                "WINDOW_GATE",
                "COVERAGE_GATE",
                "SAFETY_GATE",
            }.issubset(gate_names))

    def test_build_sequence_mirrors_planner_build_readiness_promotion_separation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            artifacts = write_promotions_materialized_source_actual_outcome_source_contract_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            sequence = pd.read_csv(artifacts.build_sequence_csv_path, keep_default_na=False, low_memory=False)
            step_names = list(sequence["step_name"].astype(str))
            self.assertEqual(step_names, [
                "ACTUAL_OUTCOME_SOURCE_CONTRACT_PLAN",
                "ACTUAL_OUTCOME_SOURCE_BUILDER",
                "ACTUAL_OUTCOME_SOURCE_READINESS",
                "ACTUAL_OUTCOME_SOURCE_PROMOTION",
                "RERUN_STAGE1_ONLY",
                "RERUN_STAGE2_STAGE3_CONDITIONAL",
            ])

    def test_does_not_create_actual_outcome_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            destination = packet_root / "source_materialized_promotions" / _promotion_folder_name() / "actual_outcome_source.csv"
            self.assertFalse(destination.exists())
            result = build_promotions_materialized_source_actual_outcome_source_contract_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            self.assertEqual(result.actual_outcome_source_created_flag, 0)
            self.assertFalse(destination.exists())

    def test_does_not_mutate_promotion_source_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_root = _build_packet_root(Path(tmp_dir))
            source_rows = packet_root / "source_materialized_promotions" / _promotion_folder_name() / "promotion_source_rows.csv"
            before = source_rows.read_bytes()
            result = build_promotions_materialized_source_actual_outcome_source_contract_plan(
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
            result = build_promotions_materialized_source_actual_outcome_source_contract_plan(
                packet_root=packet_root,
                promotion_key=_promotion_key(),
            )
            self.assertEqual(result.operator_audit_overwritten_flag, 0)
            self.assertEqual(operator_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
