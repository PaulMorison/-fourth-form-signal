# Operator Feedback Instructions — SHADOW NOT PRODUCTION

**Store:** 772  
**Review pack:** `shadow_review_20260622_phase4b13`  
**Status:** SHADOW — not production ordering

## What to do
1. Open **`08_OPERATOR_DECISION_SHEET.csv`** (primary worksheet).
2. For each row, set **`review decision`** to exactly one of:
   - `ACCEPT`
   - `REJECT`
   - `REDUCE`
   - `NEEDS_MORE_EVIDENCE`
3. If **`REDUCE`**, enter **`operator recommended units`** (see schema in `12_OPERATOR_FEEDBACK_SCHEMA.csv`).
4. Add brief **`operator notes`** where useful.
5. Save the completed sheet. Do **not** rename required column headers.

## Review priority
1. **Added BUYs** (`02_ADDED_BUYS_REVIEW.csv` / `pilot_queue=added_buy`)
2. **Tiny-demand BUYs** (`04_TINY_DEMAND_BUYS_REVIEW.csv`)
3. **Stock-basis review** (`05_STOCK_BASIS_REVIEW.csv`)
4. **High-confidence BUYs** (`06_HIGH_CONFIDENCE_BUYS.csv`)
5. **Low-confidence BUYs** (`07_LOW_CONFIDENCE_BUYS.csv`)

## Important
- **Do not place orders** from this file. This is human review only.
- **Not a customer-facing report.** Not approved for production ordering.
- **No automatic ordering** will run from your entries until a separate ingestion step is approved.
- When complete, return the filled `08_OPERATOR_DECISION_SHEET.csv` for Phase 4B.16 ingestion (not yet enabled).
