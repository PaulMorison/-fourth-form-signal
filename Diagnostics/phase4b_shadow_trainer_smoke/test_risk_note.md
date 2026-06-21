# Shadow Trainer Test Risk Note

**Captured:** Phase 4B shadow implementation checkpoint (pre formal shadow eval).

## Dedicated shadow tests

- **Result:** 11/11 passed (`tests/unit/test_promotions_trainer_sufficient_stock_shadow.py`)

## Broader filter

- **Command:** `pytest tests/unit -q -k "trainer or shadow or sufficient_stock or target_mode"`
- **Result:** 82 passed, **4 failed**

## Failing tests

| Test | Touches shadow sufficient-stock code? | Pre-shadow reproduction |
|---|---|---|
| `test_promotions_target_mode_candidate.py::PromotionTargetModeCandidateTests::test_dual_contract_mode_writes_comparison_gate_and_shadow_artifacts` | **No** — dual-contract historical allocation gate assertion | **Not proven** — appears pre-existing/data-dependent (gate boolean on synthetic slice) |
| `test_promotions_target_mode_multi_slice.py::PromotionTargetModeMultiSliceTests::test_manifest_input_evaluation_records_gate_and_slice_audit` | **No** — multi-slice stability gate categorical evidence | **Not proven** — appears pre-existing/data-dependent |
| `test_promotions_target_mode_multi_slice.py::PromotionTargetModeMultiSliceTests::test_multi_slice_manifest_source_fails_loud_when_child_row_diagnostics_missing` | **No** — multi-slice manifest resolution | **Not proven** — appears pre-existing/data-dependent |
| `test_promotions_target_mode_multi_slice.py::PromotionTargetModeMultiSliceTests::test_multi_slice_manifest_source_resolves_child_run_manifests_and_runtime_manifest` | **No** — multi-slice manifest resolution | **Not proven** — appears pre-existing/data-dependent |

## Assessment

- None of the four failures exercise `units_target_mode=sufficient_stock_shadow` or `_train_and_persist_sufficient_stock_shadow_units`.
- P0 shadow safety tests pass; failures **do not block** proposing formal shadow eval, but should be triaged separately before any production trainer change.
