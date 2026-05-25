from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from surfaces.promotions.reporting.store_client_resolver import (  # noqa: E402
    PromotionStoreClientMappingError,
    PromotionStoreClientResolver,
)


class PromotionStoreClientResolverTests(unittest.TestCase):
    def test_resolver_returns_mapping_for_active_store(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            mapping_path = Path(temp_dir) / "mapping.csv"
            pd.DataFrame(
                {
                    "client_code": ["priceline"],
                    "client_name": ["Priceline"],
                    "store_number": ["0772"],
                    "store_name": ["Collins Arcade"],
                    "store_slug": ["collins_arcade"],
                    "upload_target_name": ["pos"],
                    "pos_format_name": ["default"],
                    "active_flag": [True],
                }
            ).to_csv(mapping_path, index=False)

            resolved = PromotionStoreClientResolver(mapping_path=mapping_path, strict=True).resolve("0772")
            self.assertEqual(resolved.client_code, "priceline")
            self.assertEqual(resolved.store_slug, "collins_arcade")

    def test_resolver_fails_for_unmapped_store_in_strict_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            mapping_path = Path(temp_dir) / "mapping.csv"
            pd.DataFrame(
                {
                    "client_code": ["priceline"],
                    "client_name": ["Priceline"],
                    "store_number": ["0772"],
                    "store_name": ["Collins Arcade"],
                    "store_slug": ["collins_arcade"],
                    "upload_target_name": ["pos"],
                    "pos_format_name": ["default"],
                    "active_flag": [True],
                }
            ).to_csv(mapping_path, index=False)

            resolver = PromotionStoreClientResolver(mapping_path=mapping_path, strict=True)
            with self.assertRaises(PromotionStoreClientMappingError):
                resolver.resolve("0999")

    def test_resolver_fails_for_inactive_store(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            mapping_path = Path(temp_dir) / "mapping.csv"
            pd.DataFrame(
                {
                    "client_code": ["priceline"],
                    "client_name": ["Priceline"],
                    "store_number": ["0772"],
                    "store_name": ["Collins Arcade"],
                    "store_slug": ["collins_arcade"],
                    "upload_target_name": ["pos"],
                    "pos_format_name": ["default"],
                    "active_flag": [False],
                }
            ).to_csv(mapping_path, index=False)

            resolver = PromotionStoreClientResolver(mapping_path=mapping_path, strict=True)
            with self.assertRaises(PromotionStoreClientMappingError):
                resolver.resolve("0772")
