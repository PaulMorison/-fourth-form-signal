from __future__ import annotations

from datetime import UTC, date, datetime
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from runtime.promotions.config import (  # noqa: E402
    PromotionArtifactPaths,
    PromotionMssqlSettings,
    PromotionPipelineSettings,
)
from runtime.promotions.run_promotions_system_smoke import (  # noqa: E402
    _build_parser,
    _build_settings,
    run_system_smoke,
)
from runtime.promotions.smoke_support import smoke_synthetic_default_as_of_date  # noqa: E402
from surfaces.promotions.reporting.store_prediction_download_builder import (  # noqa: E402
    COMMERCIAL_SCHEMA_COLUMNS,
)


class PromotionSystemSmokeTests(unittest.TestCase):
    def _build_cli_args(
        self,
        temp_dir: str,
        *extra_args: str,
    ):
        return _build_parser().parse_args(
            [
                "--server",
                "test-server",
                "--database",
                "test-database",
                "--schema",
                "dbo",
                "--promotion-advice-table",
                "dbo.promotions",
                "--pwlogd-table",
                "dbo.PwlogD",
                "--artifact-root",
                str(Path(temp_dir) / "governed_promotions"),
                "--local-inspection-root",
                str(Path(temp_dir) / "local_inspection"),
                *extra_args,
            ]
        )

    def _build_cli_settings(
        self,
        temp_dir: str,
        *extra_args: str,
    ) -> PromotionPipelineSettings:
        return _build_settings(self._build_cli_args(temp_dir, *extra_args))

    def _run_smoke(
        self,
        temp_dir: str,
        *extra_args: str,
    ):
        args = self._build_cli_args(temp_dir, *extra_args)
        settings = _build_settings(args)
        artifacts = run_system_smoke(
            settings=settings,
            run_id="system-smoke-run",
            score_run_id="system-smoke-run-score",
            decision_surface_run_id="system-smoke-run-decision-surface",
            execution_mode=args.mode,
            target_mode=getattr(args, "target_mode", None),
        )
        manifest_payload = json.loads(Path(artifacts.manifest_path).read_text(encoding="utf-8"))
        training_manifest_payload = json.loads(
            Path(artifacts.model_manifest_path).read_text(encoding="utf-8")
        )
        return args, settings, artifacts, manifest_payload, training_manifest_payload

    def test_smoke_run_writes_full_operator_review_package_without_manual_as_of_date(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            _, settings, artifacts, manifest_payload, training_manifest_payload = self._run_smoke(
                temp_dir,
                "--mode",
                "smoke_synthetic",
            )
            self.assertEqual(settings.as_of_date, smoke_synthetic_default_as_of_date())

            self.assertTrue(Path(artifacts.manifest_path).exists())
            self.assertTrue(Path(artifacts.nas_bootstrap_summary_path).exists())
            self.assertTrue(Path(artifacts.store_prediction_download_path).exists())
            self.assertTrue(Path(artifacts.store_prediction_master_csv_path).exists())
            self.assertTrue(Path(artifacts.inspection_review_packet_csv_path).exists())
            self.assertTrue(Path(artifacts.local_store_prediction_download_path).exists())
            self.assertTrue(Path(artifacts.local_run_summary_path).exists())
            self.assertTrue(Path(artifacts.audit_manifest_path).exists())
            self.assertTrue(Path(artifacts.operator_log_path).exists())
            self.assertTrue(Path(artifacts.operator_summary_csv_path).exists())
            self.assertEqual(manifest_payload["execution_mode"], "smoke_synthetic")
            self.assertEqual(
                manifest_payload["final_outputs"]["nas_store_prediction_download_path"],
                artifacts.store_prediction_download_path,
            )
            self.assertEqual(
                manifest_payload["final_outputs"]["inspection_review_packet_csv_path"],
                artifacts.inspection_review_packet_csv_path,
            )
            self.assertEqual(
                manifest_payload["final_outputs"]["local_inspection_csv_path"],
                artifacts.local_store_prediction_download_path,
            )
            self.assertEqual(manifest_payload["as_of_date"], "2024-09-01")
            self.assertEqual(training_manifest_payload["target_mode"], "current_trainer_contract")
            self.assertEqual(manifest_payload["model_bundle"]["target_mode"], "current_trainer_contract")
            self.assertIsNone(manifest_payload["runtime_settings"]["requested_target_mode"])
            self.assertEqual(
                manifest_payload["runtime_settings"]["resolved_target_mode"],
                "current_trainer_contract",
            )
            self.assertNotIn(
                "target_mode_comparison_summary_json",
                training_manifest_payload["artifact_files"],
            )
            store_download_header = (
                Path(artifacts.store_prediction_master_csv_path)
                .read_text(encoding="utf-8")
                .splitlines()[0]
                .split(",")
            )
            self.assertEqual(store_download_header, list(COMMERCIAL_SCHEMA_COLUMNS))

    def test_smoke_run_accepts_dual_contract_target_mode_and_persists_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            _, _, artifacts, manifest_payload, training_manifest_payload = self._run_smoke(
                temp_dir,
                "--mode",
                "smoke_synthetic",
                "--target-mode",
                "dual_contract_diagnostics",
            )

            self.assertEqual(training_manifest_payload["target_mode"], "dual_contract_diagnostics")
            self.assertEqual(manifest_payload["model_bundle"]["target_mode"], "dual_contract_diagnostics")
            self.assertEqual(
                manifest_payload["runtime_settings"]["requested_target_mode"],
                "dual_contract_diagnostics",
            )
            self.assertEqual(
                manifest_payload["runtime_settings"]["resolved_target_mode"],
                "dual_contract_diagnostics",
            )
            self.assertIn(
                "target_mode_comparison_summary_json",
                training_manifest_payload["artifact_files"],
            )
            self.assertTrue(Path(artifacts.store_prediction_master_csv_path).exists())
            self.assertEqual(
                Path(artifacts.store_prediction_master_csv_path)
                .read_text(encoding="utf-8")
                .splitlines()[0]
                .split(","),
                list(COMMERCIAL_SCHEMA_COLUMNS),
            )

    def test_smoke_run_accepts_historical_candidate_target_mode_and_persists_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            _, _, _, manifest_payload, training_manifest_payload = self._run_smoke(
                temp_dir,
                "--mode",
                "smoke_synthetic",
                "--target-mode",
                "historical_allocation_candidate",
            )

            self.assertEqual(
                training_manifest_payload["target_mode"],
                "historical_allocation_candidate",
            )
            self.assertEqual(
                manifest_payload["model_bundle"]["target_mode"],
                "historical_allocation_candidate",
            )
            self.assertEqual(
                manifest_payload["runtime_settings"]["requested_target_mode"],
                "historical_allocation_candidate",
            )
            self.assertEqual(
                manifest_payload["runtime_settings"]["resolved_target_mode"],
                "historical_allocation_candidate",
            )
            self.assertIn(
                "target_mode_comparison_summary_json",
                training_manifest_payload["artifact_files"],
            )

    def test_smoke_cli_rejects_invalid_target_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(SystemExit):
                self._build_cli_args(
                    temp_dir,
                    "--mode",
                    "smoke_synthetic",
                    "--target-mode",
                    "silent_primary_switch",
                )

    def test_smoke_build_settings_preserves_explicit_as_of_date_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self._build_cli_settings(
                temp_dir,
                "--mode",
                "smoke_synthetic",
                "--as-of-date",
                "2025-01-15",
            )

            self.assertEqual(settings.as_of_date, date(2025, 1, 15))

    def test_non_synthetic_modes_do_not_inherit_smoke_fixture_date(self) -> None:
        default_runtime_date = datetime(2026, 5, 23, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("runtime.promotions.config.datetime", wraps=datetime) as mock_datetime:
                mock_datetime.now.return_value = default_runtime_date
                for mode in ("live_sql", "smoke_patched_extraction"):
                    with self.subTest(mode=mode):
                        settings = self._build_cli_settings(
                            temp_dir,
                            "--mode",
                            mode,
                        )
                        self.assertEqual(settings.as_of_date, default_runtime_date.date())
                        self.assertNotEqual(
                            settings.as_of_date,
                            smoke_synthetic_default_as_of_date(),
                        )
