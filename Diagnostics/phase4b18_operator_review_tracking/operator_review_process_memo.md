# Phase 4B.18 — Operator Human Review Process (Store 772)

**Status:** SHADOW_NOT_PRODUCTION — no automatic ordering.

## Runtime paths

| Role | Path |
|------|------|
| Production runtime (unchanged) | `/Users/paulmorison/promotions_runtime_governed/promotions/priceline/772/prediction` |
| Shadow governed outputs | `/Users/paulmorison/promotions_runtime_governed/promotions/772/prediction` |
| Priceline shadow mirror | `.../priceline/772/prediction/shadow_review_20260622_phase4b16/` |

## Buyer workflow

1. Open **`README_SHADOW_REVIEW_LOCATION.md`** in the priceline prediction folder first.
2. Read **`README_SHADOW_NOT_PRODUCTION.md`** in the shadow folder.
3. Review actions in **`STORE_ACTIONS_SHADOW.csv`**.
4. Record decisions in **`OPERATOR_DECISION_SHEET_SHADOW.csv`**.

Allowed decisions: `ACCEPT`, `REJECT`, `REDUCE`, `NEEDS_MORE_EVIDENCE`.

## Governance

- **No orders are placed automatically** from shadow files.
- **Model status:** `SHADOW_NOT_PRODUCTION`
- **Human review required:** YES
- **Production ordering approved:** NO
- **Customer report release approved:** NO

## Before ingestion

- The completed decision sheet must be reviewed before any feedback ingestion.
- **Phase 4B.19** will ingest completed operator feedback **only after explicit approval**.
- Do not ingest feedback until the operator returns a completed decision sheet.

## Tracking

Use `operator_review_tracking_template.csv` to log review progress and outcomes when the operator begins and completes the pilot.
