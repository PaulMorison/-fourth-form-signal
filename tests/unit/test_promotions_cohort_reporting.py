from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from models.promotions.cohorts import PromotionArchetypeRanker, PromotionCohortBacktester  # noqa: E402
from runtime.promotions.config import PromotionArtifactPaths  # noqa: E402
from state.promotions.cohorts import PromotionCohortHistoryBuilder  # noqa: E402
from state.promotions.feature_engineering import PromotionFeatureEngineer  # noqa: E402
from state.promotions.targets import PromotionTargetEngineer  # noqa: E402
from surfaces.promotions.reporting.cohort_report_builder import PromotionCohortReportBuilder  # noqa: E402
from tests.unit.promotions_test_data import build_repeating_promotions_base_frame  # noqa: E402


def _build_cohort_dataset() -> object:
    base_frame = build_repeating_promotions_base_frame()
    target_result = PromotionTargetEngineer().engineer(base_frame)
    feature_result = PromotionFeatureEngineer().engineer(target_result.frame)
    return target_result.frame.merge(
        feature_result.frame[["promotion_row_key", *feature_result.feature_columns]],
        on="promotion_row_key",
        how="left",
    )


class PromotionCohortReportingTests(unittest.TestCase):
    def test_report_builder_writes_report_manifest_without_overwriting_runtime_manifest(self) -> None:
        dataset = _build_cohort_dataset()
        history = PromotionCohortHistoryBuilder().build(
            dataset,
            as_of_date="2024-09-01",
            minimum_sample_size=1,
        )
        backtest = PromotionCohortBacktester().backtest(
            dataset,
            as_of_date="2024-09-01",
            minimum_sample_size=1,
            similarity_threshold=0.50,
        )
        rankings = PromotionArchetypeRanker().rank(
            history.archetype_history_frame,
            minimum_sample_size=1,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_paths = PromotionArtifactPaths(root=Path(temp_dir) / "promotions_artifacts")
            artifacts = PromotionCohortReportBuilder().write_reports(
                run_id="reporting-test",
                cohort_history=history,
                backtest_result=backtest,
                ranking_result=rankings,
                artifact_paths=artifact_paths,
            )

            runtime_manifest_path = artifact_paths.cohort_manifest_path("reporting-test")
            report_manifest_path = Path(artifacts.manifest_path)
            self.assertTrue(report_manifest_path.exists())
            self.assertTrue(Path(artifacts.metrics_path).exists())
            self.assertNotEqual(report_manifest_path, runtime_manifest_path)
            self.assertFalse(runtime_manifest_path.exists())
            self.assertIn("archetype_rankings", artifacts.report_paths)
            self.assertIn("nearest_archetype_matches", artifacts.report_paths)
