from __future__ import annotations

"""Assignment of cohort keys and archetype signatures to promotions rows."""

from dataclasses import dataclass

import pandas as pd

from state.promotions.cohorts.archetype_signature_builder import (
    ARCHETYPE_REGIME_COLUMNS,
    PRIMARY_SIGNATURE_COLUMNS,
    SECONDARY_SIGNATURE_COLUMNS,
    build_archetype_signature_columns,
)
from state.promotions.cohorts.cohort_frame_schema import (
    COHORT_ASSIGNMENT_REQUIRED_COLUMNS,
    coerce_cohort_frame_types,
)
from state.promotions.cohorts.cohort_keys import COHORT_KEY_COLUMNS, compose_cohort_key
from state.promotions.cohorts.cohort_validators import (
    validate_cohort_date_columns,
    validate_required_cohort_columns,
)
from state.promotions.feature_engineering.shared.ft_base_math import ensure_numeric_series, ensure_text_series


@dataclass(frozen=True)
class PromotionCohortAssignmentResult:
    frame: pd.DataFrame
    cohort_key_columns: tuple[str, ...] = COHORT_KEY_COLUMNS
    archetype_dimension_columns: tuple[str, ...] = ARCHETYPE_REGIME_COLUMNS


class PromotionCohortAssigner:
    """Attach deterministic cohort and archetype keys to promotions rows."""

    def assign(self, frame: pd.DataFrame) -> PromotionCohortAssignmentResult:
        """Return a row frame enriched with cohort keys and archetype regimes."""

        working = coerce_cohort_frame_types(frame)
        validate_required_cohort_columns(
            working,
            required_columns=COHORT_ASSIGNMENT_REQUIRED_COLUMNS,
            context="Promotion cohort assignment",
        )
        validate_cohort_date_columns(working)
        archetype_frame = build_archetype_signature_columns(working)
        working = pd.concat(
            [working.drop(columns=list(archetype_frame.columns), errors="ignore"), archetype_frame],
            axis=1,
        )

        department_or_category = ensure_text_series(working, "department").where(
            lambda values: values != "",
            ensure_text_series(working, "category"),
        )
        store_token = ensure_numeric_series(working, "store_number_key").where(
            lambda values: values > 0.0,
            ensure_numeric_series(working, "store_number"),
        )
        supplier_token = ensure_numeric_series(working, "inferred_supplier_number")
        key_frame = pd.DataFrame(
            {
                "cohort_key_promotion_name": compose_cohort_key(
                    "cohort_key_promotion_name",
                    {"promotion_name": ensure_text_series(working, "promotion_name")},
                ),
                "cohort_key_promo_type": compose_cohort_key(
                    "cohort_key_promo_type",
                    {"promo_type": ensure_text_series(working, "promo_type")},
                ),
                "cohort_key_supplier": compose_cohort_key(
                    "cohort_key_supplier",
                    {"supplier": supplier_token},
                ),
                "cohort_key_department": compose_cohort_key(
                    "cohort_key_department",
                    {"department": department_or_category},
                ),
                "cohort_key_store": compose_cohort_key(
                    "cohort_key_store",
                    {"store": store_token},
                ),
                "cohort_key_offer_mechanic": compose_cohort_key(
                    "cohort_key_offer_mechanic",
                    {"offer_mechanic": ensure_text_series(working, "archetype_offer_mechanic_regime")},
                ),
                "cohort_key_name_supplier": compose_cohort_key(
                    "cohort_key_name_supplier",
                    {
                        "promotion_name": ensure_text_series(working, "promotion_name"),
                        "supplier": supplier_token,
                    },
                ),
                "cohort_key_type_department": compose_cohort_key(
                    "cohort_key_type_department",
                    {
                        "promo_type": ensure_text_series(working, "promo_type"),
                        "department": department_or_category,
                    },
                ),
                "cohort_key_type_supplier": compose_cohort_key(
                    "cohort_key_type_supplier",
                    {
                        "promo_type": ensure_text_series(working, "promo_type"),
                        "supplier": supplier_token,
                    },
                ),
                "cohort_key_type_store": compose_cohort_key(
                    "cohort_key_type_store",
                    {
                        "promo_type": ensure_text_series(working, "promo_type"),
                        "store": store_token,
                    },
                ),
                "cohort_key_archetype_primary": compose_cohort_key(
                    "cohort_key_archetype_primary",
                    {
                        column_name.replace("archetype_", "").replace("_regime", ""): ensure_text_series(
                            working,
                            column_name,
                        )
                        for column_name in PRIMARY_SIGNATURE_COLUMNS
                    },
                ),
                "cohort_key_archetype_secondary": compose_cohort_key(
                    "cohort_key_archetype_secondary",
                    {
                        column_name.replace("archetype_", "").replace("_regime", ""): ensure_text_series(
                            working,
                            column_name,
                        )
                        for column_name in SECONDARY_SIGNATURE_COLUMNS
                    },
                ),
            },
            index=working.index,
        )
        working = pd.concat(
            [working.drop(columns=list(key_frame.columns), errors="ignore"), key_frame],
            axis=1,
        )
        return PromotionCohortAssignmentResult(frame=working)