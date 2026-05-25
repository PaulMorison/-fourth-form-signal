from __future__ import annotations

"""Feature-environment audit and contamination diagnostic writer.

Writes three governed inspection artifacts per run:

    promotion_feature_environment_audit.csv
    promotion_feature_environment_audit.json
    promotion_contamination_diagnostic.csv

These artifacts make the prior-promo memory layer and intermittent-demand
cadence layer commercially inspectable without anyone needing to open the
parquet model-input file. The CSVs are sample-row-capped and include the
key environmental fields and the new memory + intermittent feature signals.

Intended caller: post-feature-engineering, pre-model-input, in the dataset
assembler or any debug entrypoint with the engineered frame in hand.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import logging
from pathlib import Path
from typing import Sequence

import pandas as pd


LOGGER = logging.getLogger(__name__)

FEATURE_ENVIRONMENT_SAMPLE_ROWS = 10_000

ENVIRONMENT_AUDIT_COLUMNS: tuple[str, ...] = (
    "store_number",
    "sku_number",
    "promotion_start_date",
    "discount_percent",
    # The user-facing diagnostic names map onto the engineered features:
    "recent_promo_count_14d",       # := count derived from feature_prior_promo_14d_flag (== flag, since flag is 1 if any)
    "recent_promo_count_28d",       # ditto _28d
    "recent_promo_count_56d",       # ditto _56d
    "same_or_better_discount_recent_flag",  # := feature_prior_same_or_better_discount_56d_flag
    "prior_promo_price_memory_score",
    "prior_promo_cannibalisation_risk_score",
    "intermittent_demand_flag",
    "sparse_repeat_purchase_flag",
    "comments",
)


@dataclass(frozen=True)
class FeatureEnvironmentAuditPaths:
    audit_csv_path: str
    audit_json_path: str
    contamination_csv_path: str


def _resolve_first(frame: pd.DataFrame, columns: Sequence[str]) -> pd.Series:
    for column_name in columns:
        if column_name in frame.columns:
            return frame[column_name]
    return pd.Series([pd.NA] * len(frame.index), index=frame.index)


def _build_comments(audit: pd.DataFrame) -> pd.Series:
    pieces: list[pd.Series] = []
    for column_name, label in (
        ("recent_promo_count_56d", "prior_promo_56d"),
        ("same_or_better_discount_recent_flag", "same_or_better_discount_recent"),
        ("intermittent_demand_flag", "intermittent_demand"),
        ("sparse_repeat_purchase_flag", "sparse_repeat_purchase"),
    ):
        if column_name in audit.columns:
            flag = pd.to_numeric(audit[column_name], errors="coerce").fillna(0.0) > 0
            pieces.append(flag.map(lambda flagged, label=label: label if flagged else ""))
    if not pieces:
        return pd.Series([""] * len(audit.index), index=audit.index)
    combined = pd.concat(pieces, axis=1)
    return combined.apply(lambda row: ";".join(part for part in row if part), axis=1)


def build_feature_environment_audit(engineered_frame: pd.DataFrame) -> pd.DataFrame:
    """Construct the per-row environment audit table from an engineered frame."""

    source = engineered_frame
    audit = pd.DataFrame(index=source.index)
    audit["store_number"] = _resolve_first(source, ("store_number", "store_number_key")).values
    audit["sku_number"] = _resolve_first(source, ("sku_number", "sku_number_key")).values
    audit["promotion_start_date"] = _resolve_first(
        source, ("promotion_start_date", "promotion_start_date_date")
    ).values
    audit["discount_percent"] = pd.to_numeric(
        _resolve_first(source, ("discount_percent",)), errors="coerce"
    ).values

    # Flag-driven counts: the engineered flags are 1.0 when at least one prior
    # promo exists in the window. We expose them under the user's requested
    # `recent_promo_count_*d` names and also keep the underlying flag values
    # as a 0/1 truth for direct counting/aggregation.
    for window_days in (14, 28, 56):
        flag_col = f"feature_prior_promo_{window_days}d_flag"
        if flag_col in source.columns:
            audit[f"recent_promo_count_{window_days}d"] = pd.to_numeric(
                source[flag_col], errors="coerce"
            ).fillna(0.0).astype(int).values
        else:
            audit[f"recent_promo_count_{window_days}d"] = 0
    sob_col = "feature_prior_same_or_better_discount_56d_flag"
    audit["same_or_better_discount_recent_flag"] = (
        pd.to_numeric(source[sob_col], errors="coerce").fillna(0.0).astype(int).values
        if sob_col in source.columns
        else 0
    )
    for column_name in (
        "prior_promo_price_memory_score",
        "prior_promo_cannibalisation_risk_score",
        "intermittent_demand_flag",
        "sparse_repeat_purchase_flag",
    ):
        feature_name = f"feature_{column_name}"
        if feature_name in source.columns:
            audit[column_name] = pd.to_numeric(source[feature_name], errors="coerce").values
        else:
            audit[column_name] = pd.NA
    audit["comments"] = _build_comments(audit)
    # Pin the user-requested column order.
    return audit.loc[:, list(ENVIRONMENT_AUDIT_COLUMNS)]


def build_contamination_diagnostic(audit: pd.DataFrame) -> pd.DataFrame:
    """Filter the environment audit to only contamination-prone rows.

    A row is flagged as contamination-prone when ANY of:
      - a prior promo occurred in the last 28 days, OR
      - a same-or-better-discount prior promo occurred in the last 56 days, OR
      - cannibalisation_risk_score >= 0.4
    """

    if audit.empty:
        return audit.copy()
    recent_28 = pd.to_numeric(audit["recent_promo_count_28d"], errors="coerce").fillna(0) > 0
    same_or_better = pd.to_numeric(
        audit["same_or_better_discount_recent_flag"], errors="coerce"
    ).fillna(0) > 0
    cannibal_high = pd.to_numeric(
        audit["prior_promo_cannibalisation_risk_score"], errors="coerce"
    ).fillna(0.0) >= 0.4
    return audit.loc[recent_28 | same_or_better | cannibal_high].copy()


def write_feature_environment_audit_artifacts(
    *,
    engineered_frame: pd.DataFrame,
    inspection_root: Path,
    sample_rows: int = FEATURE_ENVIRONMENT_SAMPLE_ROWS,
) -> FeatureEnvironmentAuditPaths:
    """Write the three governed feature-environment audit artifacts."""

    inspection_root.mkdir(parents=True, exist_ok=True)
    audit = build_feature_environment_audit(engineered_frame)
    sampled = audit.head(sample_rows)
    contamination = build_contamination_diagnostic(audit)

    audit_csv_path = inspection_root / "promotion_feature_environment_audit.csv"
    audit_json_path = inspection_root / "promotion_feature_environment_audit.json"
    contamination_csv_path = inspection_root / "promotion_contamination_diagnostic.csv"

    sampled.to_csv(audit_csv_path, index=False)
    contamination.to_csv(contamination_csv_path, index=False)
    audit_json_path.write_text(
        json.dumps(
            {
                "row_count_total": int(len(audit.index)),
                "row_count_sampled": int(len(sampled.index)),
                "contamination_row_count": int(len(contamination.index)),
                "sample_row_cap": int(sample_rows),
                "generated_at_utc": datetime.now(tz=UTC).isoformat(),
                "columns_in_order": list(ENVIRONMENT_AUDIT_COLUMNS),
                "summary": {
                    "rows_with_prior_promo_14d": int(
                        (pd.to_numeric(audit["recent_promo_count_14d"], errors="coerce").fillna(0) > 0).sum()
                    ),
                    "rows_with_prior_promo_28d": int(
                        (pd.to_numeric(audit["recent_promo_count_28d"], errors="coerce").fillna(0) > 0).sum()
                    ),
                    "rows_with_prior_promo_56d": int(
                        (pd.to_numeric(audit["recent_promo_count_56d"], errors="coerce").fillna(0) > 0).sum()
                    ),
                    "rows_with_same_or_better_discount_recent": int(
                        (pd.to_numeric(audit["same_or_better_discount_recent_flag"], errors="coerce").fillna(0) > 0).sum()
                    ),
                    "rows_intermittent": int(
                        (pd.to_numeric(audit["intermittent_demand_flag"], errors="coerce").fillna(0) > 0).sum()
                    ),
                    "rows_sparse_repeat": int(
                        (pd.to_numeric(audit["sparse_repeat_purchase_flag"], errors="coerce").fillna(0) > 0).sum()
                    ),
                },
            },
            indent=2,
            sort_keys=True,
            default=str,
        ),
        encoding="utf-8",
    )

    LOGGER.info(
        "Wrote feature-environment audit: rows=%s contamination_rows=%s",
        int(len(audit.index)),
        int(len(contamination.index)),
    )
    return FeatureEnvironmentAuditPaths(
        audit_csv_path=str(audit_csv_path),
        audit_json_path=str(audit_json_path),
        contamination_csv_path=str(contamination_csv_path),
    )
