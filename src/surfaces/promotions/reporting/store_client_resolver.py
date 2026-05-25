from __future__ import annotations

"""Store/client mapping resolver for commercial publishing."""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


class PromotionStoreClientMappingError(ValueError):
    """Raised when store/client mapping resolution fails."""


@dataclass(frozen=True)
class PromotionStoreClientMapping:
    client_code: str
    client_name: str
    store_number: str
    store_name: str
    store_slug: str
    upload_target_name: str
    pos_format_name: str
    active_flag: bool


class PromotionStoreClientResolver:
    """Resolve governed client/store mapping rows by store number."""

    REQUIRED_COLUMNS = (
        "client_code",
        "client_name",
        "store_number",
        "store_name",
        "store_slug",
        "upload_target_name",
        "pos_format_name",
        "active_flag",
    )

    def __init__(self, *, mapping_path: Path, strict: bool = True) -> None:
        self._mapping_path = mapping_path
        self._strict = strict
        self._mapping_frame = self._load_mapping(mapping_path)

    def resolve(self, store_number: object) -> PromotionStoreClientMapping:
        store_key = str(store_number).strip()
        if self._mapping_frame.empty:
            if self._strict:
                raise PromotionStoreClientMappingError(
                    "Store/client mapping is required for publishing but mapping source is empty: "
                    f"{self._mapping_path}"
                )
            return self._fallback_mapping(store_key)

        matches = self._mapping_frame.loc[
            self._mapping_frame["store_number"].astype(str).str.strip().eq(store_key)
        ]
        if matches.empty:
            if self._strict:
                raise PromotionStoreClientMappingError(
                    "Unmapped store_number in governed client/store mapping: "
                    f"{store_key}. Mapping file: {self._mapping_path}"
                )
            return self._fallback_mapping(store_key)

        row = matches.iloc[0]
        active_flag = bool(row["active_flag"])
        if not active_flag:
            raise PromotionStoreClientMappingError(
                "Store is mapped but inactive for publishing: "
                f"store_number={store_key}, client_code={row['client_code']}"
            )

        return PromotionStoreClientMapping(
            client_code=str(row["client_code"]),
            client_name=str(row["client_name"]),
            store_number=str(row["store_number"]),
            store_name=str(row["store_name"]),
            store_slug=str(row["store_slug"]),
            upload_target_name=str(row["upload_target_name"]),
            pos_format_name=str(row["pos_format_name"]),
            active_flag=active_flag,
        )

    def _load_mapping(self, mapping_path: Path) -> pd.DataFrame:
        if not mapping_path.exists():
            return pd.DataFrame(columns=self.REQUIRED_COLUMNS)

        if mapping_path.suffix.lower() == ".csv":
            frame = pd.read_csv(
                mapping_path,
                dtype={
                    "client_code": "string",
                    "client_name": "string",
                    "store_number": "string",
                    "store_name": "string",
                    "store_slug": "string",
                    "upload_target_name": "string",
                    "pos_format_name": "string",
                },
            )
        elif mapping_path.suffix.lower() in {".parquet", ".pq"}:
            frame = pd.read_parquet(mapping_path)
        else:
            raise PromotionStoreClientMappingError(
                f"Unsupported mapping format: {mapping_path}"
            )

        missing_columns = [column for column in self.REQUIRED_COLUMNS if column not in frame.columns]
        if missing_columns:
            raise PromotionStoreClientMappingError(
                "Store/client mapping is missing required columns: "
                + ", ".join(missing_columns)
            )

        normalized = frame.loc[:, self.REQUIRED_COLUMNS].copy()
        normalized["active_flag"] = normalized["active_flag"].map(_to_bool)
        return normalized

    def _fallback_mapping(self, store_number: str) -> PromotionStoreClientMapping:
        store_slug = _slug(f"store_{store_number}")
        return PromotionStoreClientMapping(
            client_code="priceline",
            client_name="Priceline",
            store_number=store_number,
            store_name=f"Store {store_number}",
            store_slug=store_slug,
            upload_target_name="priceline_pos",
            pos_format_name="default",
            active_flag=True,
        )


def _to_bool(value: object) -> bool:
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y", "t"}


def _slug(value: str) -> str:
    return "_".join(part for part in value.lower().split() if part)
