from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.config import PromotionArtifactPaths  # noqa: E402
from runtime.promotions.local_inspection import write_local_inspection_outputs  # noqa: E402


class PromotionLocalInspectionTests(unittest.TestCase):
    def test_local_inspection_outputs_copy_into_run_scoped_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            artifact_paths = PromotionArtifactPaths(
                root=temp_path / "governed_promotions",
                local_inspection_root=temp_path / "local_inspection",
            )
            source_root = temp_path / "source_outputs"
            source_root.mkdir(parents=True, exist_ok=True)
            nas_store_csv = source_root / "store.csv"
            nas_decision_surface_csv = source_root / "decision_surface.csv"
            nas_review_packet_csv = source_root / "review_packet.csv"
            operational_cycle_manifest = source_root / "operational_cycle_manifest.json"
            audit_summary_json = source_root / "audit_summary.json"
            audit_summary_csv = source_root / "audit_summary.csv"
            operator_log = source_root / "operator_run.log"
            operator_summary_json = source_root / "operator_run_summary.json"
            operator_summary_csv = source_root / "operator_run_summary.csv"
            nas_store_csv.write_text("store_number\n1\n", encoding="utf-8")
            nas_decision_surface_csv.write_text("final_decision_score\n0.91\n", encoding="utf-8")
            nas_review_packet_csv.write_text("predicted_units_first_day\n1.5\n", encoding="utf-8")
            operational_cycle_manifest.write_text("{}\n", encoding="utf-8")
            audit_summary_json.write_text("{}\n", encoding="utf-8")
            audit_summary_csv.write_text("metric,value\nrows_scored,2\n", encoding="utf-8")
            operator_log.write_text("log\n", encoding="utf-8")
            operator_summary_json.write_text("{}\n", encoding="utf-8")
            operator_summary_csv.write_text("run_id,status\nlocal-copy-run,completed\n", encoding="utf-8")

            artifacts = write_local_inspection_outputs(
                run_id="local-copy-run",
                as_of_date="2024-09-01",
                execution_mode="smoke_synthetic",
                artifact_paths=artifact_paths,
                nas_store_prediction_csv_path=str(nas_store_csv),
                nas_decision_surface_csv_path=str(nas_decision_surface_csv),
                nas_review_packet_csv_path=str(nas_review_packet_csv),
                operational_cycle_manifest_path=str(operational_cycle_manifest),
                operator_log_path=str(operator_log),
                audit_summary_json_path=str(audit_summary_json),
                audit_summary_csv_path=str(audit_summary_csv),
                operator_summary_json_path=str(operator_summary_json),
                operator_summary_csv_path=str(operator_summary_csv),
            )

            self.assertIsNotNone(artifacts)
            assert artifacts is not None
            self.assertTrue(Path(artifacts.store_prediction_csv_path).exists())
            self.assertTrue(Path(artifacts.decision_surface_csv_path).exists())
            self.assertTrue(Path(artifacts.review_packet_csv_path).exists())
            self.assertTrue(Path(artifacts.audit_summary_json_path).exists())
            self.assertTrue(Path(artifacts.audit_summary_csv_path).exists())
            self.assertTrue(Path(artifacts.operator_summary_json_path).exists())
            self.assertTrue(Path(artifacts.operator_summary_csv_path).exists())
            self.assertTrue(Path(artifacts.run_summary_path).exists())
            self.assertIn("local-copy-run", Path(artifacts.store_prediction_csv_path).name)
            summary_payload = json.loads(Path(artifacts.run_summary_path).read_text(encoding="utf-8"))
            self.assertEqual(summary_payload["local_store_prediction_csv_path"], artifacts.store_prediction_csv_path)
            self.assertEqual(summary_payload["nas_store_prediction_csv_path"], str(nas_store_csv))
            self.assertEqual(summary_payload["local_operator_summary_csv_path"], artifacts.operator_summary_csv_path)

    def test_local_inspection_preserves_canonical_store_prediction_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            artifact_paths = PromotionArtifactPaths(
                root=temp_path / "governed_promotions",
                local_inspection_root=temp_path / "local_inspection",
            )
            nas_store_csv = (
                artifact_paths.root
                / "promotions"
                / "priceline"
                / "772"
                / "prediction"
                / "2024-09-03"
                / "772_2024-09-03_allocation-report-new-line-25-wk9.csv"
            )
            source_root = temp_path / "source_outputs"
            nas_decision_surface_csv = source_root / "decision_surface.csv"
            nas_review_packet_csv = source_root / "review_packet.csv"
            operational_cycle_manifest = source_root / "operational_cycle_manifest.json"
            audit_summary_json = source_root / "audit_summary.json"
            audit_summary_csv = source_root / "audit_summary.csv"
            operator_log = source_root / "operator_run.log"
            for path, content in (
                (nas_store_csv, "store_number\n772\n"),
                (nas_decision_surface_csv, "final_decision_score\n0.91\n"),
                (nas_review_packet_csv, "predicted_units_first_day\n1.5\n"),
                (operational_cycle_manifest, "{}\n"),
                (audit_summary_json, "{}\n"),
                (audit_summary_csv, "metric,value\nrows_scored,2\n"),
                (operator_log, "log\n"),
            ):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")

            artifacts = write_local_inspection_outputs(
                run_id="local-canonical-run",
                as_of_date="2024-09-03",
                execution_mode="smoke_synthetic",
                artifact_paths=artifact_paths,
                nas_store_prediction_csv_path=str(nas_store_csv),
                nas_decision_surface_csv_path=str(nas_decision_surface_csv),
                nas_review_packet_csv_path=str(nas_review_packet_csv),
                operational_cycle_manifest_path=str(operational_cycle_manifest),
                operator_log_path=str(operator_log),
                audit_summary_json_path=str(audit_summary_json),
                audit_summary_csv_path=str(audit_summary_csv),
            )

            self.assertIsNotNone(artifacts)
            assert artifacts is not None
            self.assertTrue(Path(artifacts.store_prediction_csv_path).exists())
            self.assertIn(
                "/local-canonical-run/promotions/priceline/772/prediction/2024-09-03/772_2024-09-03_allocation-report-new-line-25-wk9.csv",
                artifacts.store_prediction_csv_path,
            )
            self.assertNotIn("System Audit", artifacts.store_prediction_csv_path)
            self.assertNotIn("Store Data", artifacts.store_prediction_csv_path)

    def test_local_inspection_outputs_can_be_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "governed_promotions",
                local_inspection_root=None,
            )

            artifacts = write_local_inspection_outputs(
                run_id="local-copy-disabled",
                as_of_date="2024-09-01",
                execution_mode="smoke_synthetic",
                artifact_paths=artifact_paths,
                nas_store_prediction_csv_path=str(Path(temp_dir) / "store.csv"),
                nas_decision_surface_csv_path=str(Path(temp_dir) / "decision_surface.csv"),
                nas_review_packet_csv_path=str(Path(temp_dir) / "review_packet.csv"),
                operational_cycle_manifest_path=str(Path(temp_dir) / "manifest.json"),
                operator_log_path=str(Path(temp_dir) / "operator.log"),
                audit_summary_json_path=str(Path(temp_dir) / "audit.json"),
                audit_summary_csv_path=str(Path(temp_dir) / "audit.csv"),
            )

            self.assertIsNone(artifacts)