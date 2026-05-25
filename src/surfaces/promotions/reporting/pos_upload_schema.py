from __future__ import annotations

"""POS upload schema and validation for promotions publishing."""

from dataclasses import dataclass

import pandas as pd


class PromotionPosUploadSchemaValidationError(ValueError):
    """Raised when POS upload schema validation fails."""


@dataclass(frozen=True)
class PromotionPosUploadSchema:
    required_columns: tuple[str, ...] = (
        "store_number",
        "sku_number",
        "description",
        "order_quantity",
        "target_soh_on_break_date",
    )

    def build_frame(self, review_frame: pd.DataFrame) -> pd.DataFrame:
        order_quantity_source = (
            review_frame["upload_ready_order_units"]
            if "upload_ready_order_units" in review_frame.columns
            else review_frame["recommended_order_quantity"]
        )
        return pd.DataFrame(
            {
                "store_number": review_frame["store_number"].astype(str),
                "sku_number": review_frame["sku_number"].astype(str),
                "description": review_frame["sku_description"].astype(str),
                "order_quantity": pd.to_numeric(
                    order_quantity_source,
                    errors="coerce",
                ),
                "target_soh_on_break_date": pd.to_numeric(
                    review_frame["target_soh_on_break_date"],
                    errors="coerce",
                ),
            }
        )

    def validate(self, frame: pd.DataFrame) -> None:
        missing_columns = [column for column in self.required_columns if column not in frame.columns]
        if missing_columns:
            raise PromotionPosUploadSchemaValidationError(
                "POS upload schema missing required columns: " + ", ".join(missing_columns)
            )

        for column in self.required_columns:
            if frame[column].isna().any() or (frame[column].astype(str).str.strip() == "").any():
                raise PromotionPosUploadSchemaValidationError(
                    f"POS upload contains null/empty values in required column: {column}"
                )

        quantities = pd.to_numeric(frame["order_quantity"], errors="coerce")
        if quantities.isna().any():
            raise PromotionPosUploadSchemaValidationError(
                "POS upload order_quantity contains non-numeric values."
            )
        if (quantities < 0).any():
            raise PromotionPosUploadSchemaValidationError(
                "POS upload order_quantity must be non-negative."
            )
        if not (quantities == quantities.round(0)).all():
            raise PromotionPosUploadSchemaValidationError(
                "POS upload order_quantity must be integer-valued."
            )
