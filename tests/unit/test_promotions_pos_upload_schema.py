from __future__ import annotations

from pathlib import Path
import sys
import unittest

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(REPO_ROOT / "src"))

from surfaces.promotions.reporting.pos_upload_schema import (  # noqa: E402
    PromotionPosUploadSchema,
    PromotionPosUploadSchemaValidationError,
)


class PromotionPosUploadSchemaTests(unittest.TestCase):
    def test_pos_schema_validate_passes_for_valid_frame(self) -> None:
        schema = PromotionPosUploadSchema()
        frame = pd.DataFrame(
            {
                "store_number": ["0772"],
                "sku_number": ["1001"],
                "description": ["SKU 1001"],
                "order_quantity": [3],
                "target_soh_on_break_date": [7],
            }
        )
        schema.validate(frame)

    def test_pos_schema_validate_fails_for_negative_quantity(self) -> None:
        schema = PromotionPosUploadSchema()
        frame = pd.DataFrame(
            {
                "store_number": ["0772"],
                "sku_number": ["1001"],
                "description": ["SKU 1001"],
                "order_quantity": [-1],
                "target_soh_on_break_date": [7],
            }
        )
        with self.assertRaises(PromotionPosUploadSchemaValidationError):
            schema.validate(frame)
