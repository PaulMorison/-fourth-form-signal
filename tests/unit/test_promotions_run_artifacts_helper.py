from __future__ import annotations

from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.config import PromotionArtifactPaths  # noqa: E402
from runtime.promotions.print_promotions_run_artifacts import (  # noqa: E402
    collect_run_artifact_index,
    render_run_artifact_index,
)


class PromotionRunArtifactsHelperTests(unittest.TestCase):
    def test_collect_run_artifact_index_reads_operator_facing_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "governed_promotions",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            manifest_path = artifact_paths.operational_cycle_manifest_path("helper-run")
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(
                json.dumps(
                    {
                        "operator_progress": {
                            "log_path": str(artifact_paths.operator_log_path("helper-run")),
                            "summary_path": str(artifact_paths.operator_summary_path("helper-run")),
                            "summary_csv_path": str(artifact_paths.operator_summary_csv_path("helper-run")),
                        },
                        "final_outputs": {
                            "store_prediction_download_path": "/tmp/store.csv",
                            "decision_surface_csv_path": "/tmp/decision_surface.csv",
                            "inspection_review_packet_csv_path": "/tmp/review_packet.csv",
                            "audit_summary_json_path": "/tmp/audit.json",
                            "audit_summary_csv_path": "/tmp/audit.csv",
                            "completed_extraction_telemetry_json_path": "/tmp/completed_telemetry.json",
                            "completed_extraction_telemetry_csv_path": "/tmp/completed_telemetry.csv",
                            "completed_sql_diagnostics_summary_path": "/tmp/completed_diagnostics.json",
                            "future_extraction_telemetry_json_path": "/tmp/future_telemetry.json",
                            "future_extraction_telemetry_csv_path": "/tmp/future_telemetry.csv",
                            "future_sql_diagnostics_summary_path": "/tmp/future_diagnostics.json",
                        },
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            index = collect_run_artifact_index(
                run_id="helper-run",
                artifact_paths=artifact_paths,
            )
            stream = StringIO()
            render_run_artifact_index(index, stream=stream)

            rendered = stream.getvalue()
            self.assertEqual(index.run_id, "helper-run")
            self.assertIn("PROMOTIONS RUN ARTIFACTS", rendered)
            self.assertIn("operator_summary_csv_path: ", rendered)
            self.assertIn("decision_surface_csv_path: /tmp/decision_surface.csv", rendered)
            self.assertIn("future_sql_diagnostics_summary_path: /tmp/future_diagnostics.json", rendered)

    def test_collect_run_artifact_index_falls_back_to_operator_summary_for_failed_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(
                root=Path(temp_dir) / "governed_promotions",
                local_inspection_root=Path(temp_dir) / "local_inspection",
            )
            operator_summary_path = artifact_paths.operator_summary_path("failed-run")
            operator_summary_path.parent.mkdir(parents=True, exist_ok=True)
            artifact_paths.operator_summary_csv_path("failed-run").write_text(
                "run_id,status\nfailed-run,failed\n",
                encoding="utf-8",
            )
            artifact_paths.operator_log_path("failed-run").parent.mkdir(parents=True, exist_ok=True)
            artifact_paths.operator_log_path("failed-run").write_text("FAILED STAGE\n", encoding="utf-8")
            artifact_paths.completed_partition_summary_path("failed-run").write_text(
                "{}\n",
                encoding="utf-8",
            )
            artifact_paths.extraction_telemetry_json_path("failed-run").write_text("{}\n", encoding="utf-8")
            artifact_paths.extraction_telemetry_csv_path("failed-run").write_text(
                "phase,duration_seconds\nconnect,1.0\n",
                encoding="utf-8",
            )
            operator_summary_path.write_text(
                json.dumps(
                    {
                        "context": {
                            "as_of_date": "2026-04-30",
                        },
                        "final_outputs": {
                            "operational_cycle_manifest_path": str(
                                artifact_paths.operational_cycle_manifest_path("failed-run")
                            )
                        },
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            index = collect_run_artifact_index(
                run_id="failed-run",
                artifact_paths=artifact_paths,
            )

            self.assertEqual(
                index.operator_summary_json_path,
                str(artifact_paths.operator_summary_path("failed-run")),
            )
            self.assertEqual(
                index.operator_summary_csv_path,
                str(artifact_paths.operator_summary_csv_path("failed-run")),
            )
            self.assertEqual(
                index.completed_sql_telemetry_json_path,
                str(artifact_paths.extraction_telemetry_json_path("failed-run")),
            )
            self.assertEqual(
                index.completed_sql_diagnostics_summary_path,
                str(artifact_paths.completed_partition_summary_path("failed-run")),
            )