from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from data.promotions.extracted_dataset_writer import (  # noqa: E402
    PromotionExtractionWriter,
)
from data.promotions.promotion_base_extractor import (  # noqa: E402
    PromotionExtractionManifest,
)
from runtime.promotions.config import PromotionArtifactPaths  # noqa: E402


def _build_manifest(run_id: str, columns: tuple[str, ...]) -> PromotionExtractionManifest:
    return PromotionExtractionManifest(
        run_id=run_id,
        selection_mode="completed",
        query_version="v1",
        as_of_date="2026-05-13",
        extracted_at_utc="2026-05-16T00:00:00+00:00",
        row_count=2,
        column_count=len(columns),
        duplicate_promotion_row_keys=0,
        advice_source_table="advice",
        realised_sales_source_table="sales",
        columns=columns,
    )


class PromotionExtractionWriterAtomicTests(unittest.TestCase):
    def _make_paths(self, root: Path) -> PromotionArtifactPaths:
        return PromotionArtifactPaths(root=root)

    def test_final_files_exist_after_write(self) -> None:
        frame = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
        manifest = _build_manifest("run-atomic-ok", tuple(frame.columns))
        with tempfile.TemporaryDirectory() as tmp:
            artifact_paths = self._make_paths(Path(tmp))
            result = PromotionExtractionWriter().write(
                base_frame=frame,
                manifest=manifest,
                artifact_paths=artifact_paths,
            )
            self.assertTrue(result.base_path.exists())
            self.assertTrue(result.manifest_path.exists())
            # No leftover *.tmp siblings.
            tmp_base = result.base_path.with_suffix(result.base_path.suffix + ".tmp")
            tmp_manifest = result.manifest_path.with_suffix(
                result.manifest_path.suffix + ".tmp"
            )
            self.assertFalse(tmp_base.exists())
            self.assertFalse(tmp_manifest.exists())
            roundtrip = pd.read_parquet(result.base_path)
            pd.testing.assert_frame_equal(roundtrip, frame)

    def test_partial_parquet_never_visible_at_final_path_on_failure(self) -> None:
        frame = pd.DataFrame({"a": [1, 2]})
        manifest = _build_manifest("run-atomic-fail", tuple(frame.columns))
        with tempfile.TemporaryDirectory() as tmp:
            artifact_paths = self._make_paths(Path(tmp))
            base_path = artifact_paths.extracted_base_path("run-atomic-fail")
            # Force the manifest write step to fail AFTER the parquet temp was
            # written but BEFORE the atomic rename moves it into place. With
            # the atomic contract the final base_path must NOT exist.
            real_write_text = Path.write_text

            def _raise_on_manifest(self: Path, *args, **kwargs):  # type: ignore[no-untyped-def]
                if self.name.endswith("extraction_manifest.json.tmp"):
                    raise RuntimeError("simulated manifest write failure")
                return real_write_text(self, *args, **kwargs)

            with patch.object(Path, "write_text", _raise_on_manifest):
                with self.assertRaises(RuntimeError):
                    PromotionExtractionWriter().write(
                        base_frame=frame,
                        manifest=manifest,
                        artifact_paths=artifact_paths,
                    )
            # Final parquet must not exist — only the tmp parquet may linger.
            self.assertFalse(base_path.exists())


if __name__ == "__main__":
    unittest.main()
