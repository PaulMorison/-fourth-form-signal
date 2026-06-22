# Operator handoff — Store 772 shadow review (Phase 4B.18)

**Status:** SHADOW_NOT_PRODUCTION — wait for human review before any ingestion.

## Open these files (in order)

1. **`README_SHADOW_REVIEW_LOCATION.md`** — priceline prediction folder pointer
2. **`STORE_ACTIONS_SHADOW.csv`** — review shadow actions
3. **`OPERATOR_DECISION_SHEET_SHADOW.csv`** — record decisions (714 rows)

Runtime paths:

- Pointer: `/Users/paulmorison/promotions_runtime_governed/promotions/priceline/772/prediction/README_SHADOW_REVIEW_LOCATION.md`
- Shadow pack: `/Users/paulmorison/promotions_runtime_governed/promotions/772/prediction/`

## Review priority

1. Added BUYs (`ADDED_BUYS_REVIEW_SHADOW.csv`)
2. Tiny-demand BUYs (`TINY_DEMAND_BUYS_REVIEW_SHADOW.csv`)
3. Stock-basis review rows (`STOCK_BASIS_REVIEW_SHADOW.csv`)
4. High-confidence BUYs
5. Low-confidence BUYs

Allowed decisions: **ACCEPT**, **REJECT**, **REDUCE**, **NEEDS_MORE_EVIDENCE**.

## Rules

- **No order should be placed automatically** from shadow files.
- The **completed decision sheet must be returned** before Phase 4B.19 ingestion.
- **Phase 4B.19 is blocked** until explicit approval to ingest feedback.

## Next step

Operator completes and returns **`OPERATOR_DECISION_SHEET_SHADOW.csv`**. Do not ingest until then.
