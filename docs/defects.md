# Defects and their tests

The generator has eight independent defect switches (`--defects <name>`, or
commas to combine, or `all`). Each defect mutates a small, recorded set of rows
and writes the exact ids and values to `defects.json`. The dbt project has one
singular test per defect in `dbt/tests/`.

Each singular test returns **zero rows** on clean data. On a dataset with a
single defect enabled it is the **only** failing test. The generic staging,
intermediate and mart tests are deliberately written so that this holds: they
assert keys, relationships and enum values, not invariants such as positive
quantities, PLM/ERP equality or universal part usage.

## Defect-to-test map

| Defect switch | What it mutates | Catching test | What the test returns |
|---|---|---|---|
| `cyclic_bom` | Appends a BOM line whose parent is a component and whose child is one of that component's ancestors. The BOM is no longer acyclic. | `assert_no_cyclic_bom` | Recursively walks `stg_boms` from every line, records an edge whose child is already on the walked path, and returns distinct `(start_part_id, parent_part_id, child_part_id)` closing edges. A depth guard stops the walk. |
| `orphan_parts` | Removes the only incoming BOM line from two raw materials, leaving them with no parent and no product top-level role. | `assert_no_orphan_parts` | Returns parts with no row in `stg_boms.child_part_id` and no match in `stg_products.top_level_part_id`. |
| `released_assembly_unreleased_child` | Repoints one BOM line of a released assembly at a child revision whose status is `in_work`. | `assert_no_released_assembly_unreleased_child` | Returns BOM lines whose parent part is an `assembly`, whose parent revision is `released`, and whose child revision is not `released`. |
| `overlapping_revision_effectivity` | Adds a second released revision of one part with an open-ended window starting 15 days after the existing released revision. | `assert_no_overlapping_revision_effectivity` | Returns released revision pairs of the same part whose windows overlap (`a.start < b.end and b.start < a.end`, with an empty `effective_to` treated as `9999-12-31`). Windows that only touch do not count. |
| `zero_negative_quantity` | Rewrites two positive BOM line quantities to `0.00` and `-3.00`. | `assert_no_zero_or_negative_quantity` | Returns `stg_boms` rows whose quantity is `<= 0`. |
| `uom_mismatch` | Rewrites one BOM line's `uom` so it differs from the child part's base `uom`. | `assert_no_uom_mismatch` | Returns BOM lines where `stg_boms.uom <> stg_parts.uom` for the child part. |
| `eco_closed_without_ecn` | Marks an ECO that has no ECN child as `closed` and fills in approval and close dates. | `assert_no_eco_closed_without_ecn` | Returns changes with `change_type = 'eco'` and `status = 'closed'` that have no child change of type `ecn` referencing them. |
| `change_dates_out_of_order` | Rewrites `approved_at` to three days before `initiated_at` on one non-ECO change and `closed_at` to two days before `approved_at` on another non-ECO change. | `assert_no_change_dates_out_of_order` | Returns `stg_changes` rows where `approved_at < initiated_at` or `closed_at < approved_at`. |

The generator switch `zero_negative_quantity` maps to the test
`assert_no_zero_or_negative_quantity`; every other test is
`assert_no_<switch>` exactly.

## Two-pass defect verification

```bash
make verify-defects DBT=.venv-dbt/bin/dbt
```

`scripts/verify_defects.py` runs ten cases: clean, each of the eight defects
on its own, and `all`. For each case it generates a fresh dataset with
`python -m generator --out <temp> --defects <case>`, then runs two builds
against that same generated data and DuckDB file:

1. **Attribution pass** — a full `dbt build --project-dir dbt --profiles-dir
   dbt` with a temporary `PLM_RAW_DIR`, `PLM_DUCKDB_PATH` and `--target-path`.
   The script reads `run_results.json`, collects every node with status `fail`
   or `error`, and asserts the expected failure set: none for clean, exactly
   `assert_no_<defect>` for a single defect, and exactly the eight singular
   tests for `all`.
2. **Built-in pass** — the same build with the eight singular tests excluded
   (`--exclude "assert_no_..."`) and a second temporary `--target-path`, using
   the same generated raw data and DuckDB file. Excluding the singular tests
   removes dbt's build gate, so every model and every generic, unit and mart
   test runs. The script asserts zero failures and zero errors, that all 20
   model nodes are `success` (no skipped models), and that all 188 remaining
   nodes pass (196 total nodes minus the 8 excluded tests).

Both temporary target directories and the generated data are removed
afterwards. The script prints one row per case with the attribution failure
count, the expected failure set and the built-in pass count, and exits nonzero
if either pass fails. Recorded output for seed 42:

```text
dataset                             failures  expected                                      built-ins  result
-------------------------------------------------------------------------------------------------------------
clean                               0         0                                             188/188    PASS
cyclic_bom                          1         assert_no_cyclic_bom                          188/188    PASS
orphan_parts                        1         assert_no_orphan_parts                        188/188    PASS
released_assembly_unreleased_child  1         assert_no_released_assembly_unreleased_child  188/188    PASS
overlapping_revision_effectivity    1         assert_no_overlapping_revision_effectivity    188/188    PASS
zero_negative_quantity              1         assert_no_zero_or_negative_quantity           188/188    PASS
uom_mismatch                        1         assert_no_uom_mismatch                        188/188    PASS
eco_closed_without_ecn              1         assert_no_eco_closed_without_ecn              188/188    PASS
change_dates_out_of_order           1         assert_no_change_dates_out_of_order           188/188    PASS
all                                 8         8 (one per defect test)                       188/188    PASS
```

The built-in pass is what proves the generic, unit and mart tests stay green
on defective data. A full build alone cannot prove it: a failed singular test
gates the intermediate and mart nodes downstream of the affected staging
model, so those nodes are `skipped`, not `pass`. A single-defect build skips
up to 77 nodes (15 for `change_dates_out_of_order`); `all` skips 94. Excluding
the eight singular tests lets all 188 built-in nodes run: 20 models succeed
and 168 tests pass (167 data tests plus the `int_bom_explosion` unit test) on
every dataset. No built-in test needed loosening for the defects.
