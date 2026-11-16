# Data model

The generator models a fictional bicycle manufacturer. It is deliberately generic PLM: product families, a part master, revision-controlled bills of material, engineering change control and sourcing. Every row is synthetic.

## Domain shape

- **Families** — Road, Mountain and City.
- **Products** — 18 finished bicycles, six per family. Each product points at one top-level assembly part.
- **Parts** — exactly 2,000: 558 assemblies, 648 components and 794 raw materials. Raw materials carry a base unit of measure such as `M`, `KG`, `L` or `EA`; assemblies and components are `EA`.
- **BOM hierarchy** — a product top assembly fans out through three subsystem assemblies, nine subassemblies, eighteen modules, thirty-six components and thirty-six raw-material leaves. A further 146 raw materials are spread across the components, so the products differ slightly in part count. The longest path is five BOM edges (six part levels) from product top to raw material.
- **Revisions** — every part has a released base revision. Some parts also have an older obsolete revision or a future in-work revision.
- **Change control** — requirements (`ECR`), implementation orders (`ECO`) and notices (`ECN`) form a parent chain, with approval rows for each change.
- **Sourcing** — 40 suppliers, each part sourced from one to three of them.

## Determinism

- One integer seed drives every random choice through `random.Random`; the default is `42`.
- No `datetime.now()` or other wall-clock input is used. Dates are fixed offsets from `2021-01-04` (entity creation) and `2023-01-02` (change process).
- Every table is sorted by its primary key before writing. CSV files use `\n` line endings; JSON is written with sorted keys and two-space indentation.
- Running twice with the same seed produces byte-identical files. Running with a different seed changes the values.
- Defect injection uses a separate random stream from base-data generation, so enabling a defect does not perturb the clean rows around it.

## Entities

### `families.csv`

| Column | Notes |
|---|---|
| `family_id` (PK) | `F001`, `F002`, `F003` |
| `family_name` | Road, Mountain, City |

### `products.csv`

| Column | Notes |
|---|---|
| `product_id` (PK) | `PRD-001` … `PRD-018` |
| `family_id` (FK → families) | Product family |
| `name` | Model name such as `Aurora 2022` |
| `model_year` | 2022–2024 |
| `top_level_part_id` (FK → parts) | Root assembly of the product BOM |

### `parts.csv`

| Column | Notes |
|---|---|
| `part_id` (PK) | `PART-0001` … `PART-2000` |
| `part_number` | Unique business key, e.g. `PN-RD-00001` |
| `name` | Part description |
| `part_type` | `assembly`, `component` or `raw_material` |
| `family_id` (FK → families) | Owning family |
| `uom` | Base unit of measure |
| `lifecycle_state` | `draft`, `released` or `obsolete`. Clean data uses `released` for most parts and `draft` where the latest revision is `in_work`; superseded revision history carries the `obsolete` status. |
| `standard_cost` | Decimal string with two places |
| `created_at` | ISO date |

### `part_revisions.csv`

| Column | Notes |
|---|---|
| `revision_id` (PK) | `REV-00001` … |
| `part_id` (FK → parts) | Owning part |
| `revision_code` | `A`, `B`, `C`, … in chronological order |
| `status` | `in_work`, `released` or `obsolete` |
| `effective_from` | ISO date; start of the effectivity window |
| `effective_to` | ISO date; empty string means open-ended |

Clean data has exactly one released revision per part. Additional obsolete revisions model superseded history; additional `in_work` revisions model pending changes. BOM lines always reference a released revision in clean data.

### `boms.csv`

| Column | Notes |
|---|---|
| `bom_line_id` (PK) | `BOM-000001` … |
| `parent_part_id` (FK → parts) | Parent assembly |
| `parent_revision_id` (FK → part_revisions) | Revision of the parent used by this line |
| `child_part_id` (FK → parts) | Child part |
| `child_revision_id` (FK → part_revisions) | Revision of the child used by this line |
| `quantity` | Positive decimal string in clean data |
| `uom` | Unit of measure for the quantity; equals the child part base `uom` in clean data |
| `find_number` | Position within the parent, in steps of 10 |
| `effectivity_start` | ISO date; inherited from the parent revision |
| `effectivity_end` | ISO date; empty string means open-ended |

In clean data each non-top part has exactly one BOM parent, so the BOM is a forest rooted at the product top assemblies. The cyclic defect adds a second edge and breaks that property.

### `changes.csv`

| Column | Notes |
|---|---|
| `change_id` (PK) | `ECR-0001`, `ECO-0001`, `ECN-0001` |
| `change_type` | `ECR`, `ECO` or `ECN` |
| `parent_change_id` (FK → changes) | `ECR` has none (empty); `ECO` points at its `ECR`; `ECN` points at its `ECO` |
| `title` | Change description |
| `status` | `open`, `approved`, `closed` or `rejected` |
| `initiated_at` | ISO date |
| `approved_at` | ISO date or empty |
| `closed_at` | ISO date or empty |
| `affected_part_id` (FK → parts) | Primary part affected by the change |

Normal flow in clean data: each `ECN` references its parent `ECO`, each `ECO` references its parent `ECR`, and every closed `ECO` has an `ECN` child. Closed `ECR`s and `ECN`s follow the same lifecycle.

### `change_approvals.csv`

| Column | Notes |
|---|---|
| `approval_id` (PK) | `APR-00001` … |
| `change_id` (FK → changes) | Change being approved |
| `approver_role` | `engineering`, `quality`, `manufacturing` or `procurement` |
| `decision` | `approved`, `rejected` or `pending` |
| `decided_at` | ISO date; empty while a decision is `pending` |

Each change has two approval rows in the current generator. Closed and approved changes have approved decisions, rejected changes have rejected decisions, and open changes have pending decisions.

### `suppliers.csv`

| Column | Notes |
|---|---|
| `supplier_id` (PK) | `SUP-001` … `SUP-040` |
| `name` | Fictional company name |
| `country` | Fictional sourcing country |

### `part_suppliers.csv`

| Column | Notes |
|---|---|
| `part_id` (FK → parts) | Sourced part |
| `supplier_id` (FK → suppliers) | Supplier |
| `unit_price` | Decimal string with two places |
| `lead_time_days` | Integer |

The pair `(part_id, supplier_id)` is the primary key; each part has one to three suppliers.

### `erp_bom.csv`

A synthetic ERP manufacturing-BOM extract. It has no surrogate IDs:

`parent_part_number`, `child_part_number`, `quantity`, `uom`.

It is derived from the final BOM line set using part numbers, so it reflects the same content (and any injected BOM defects) as `boms.csv`. Later milestones can reconcile PLM and ERP views against it.

### `defects.json`

```json
{
  "seed": 42,
  "enabled_defects": ["cyclic_bom"],
  "defects": {
    "cyclic_bom": {
      "description": "...",
      "records": { "...": "exact ids and values injected" }
    }
  }
}
```

With `--defects none`, `enabled_defects` is empty and `defects` is `{}`. The manifest records every affected record id, and for mutations it also records the previous and injected values where useful.

## Relationships

```text
families 1 ──< products >── 1 parts (top_level_part_id)
families 1 ──< parts
parts    1 ──< part_revisions
parts    1 ──< boms >── 1 parts (child)
parts    1 ──< part_suppliers >── 1 suppliers
changes  1 ──< change_approvals
changes  1 ──< changes (parent_change_id, ECR → ECO → ECN)
parts    1 ──< changes (affected_part_id)
boms          ──> erp_bom (by part_number, generated after defects)
```

## Clean-data guarantees

The test suite asserts all of the following on `--defects none` output:

1. Exactly 3 families, 18 products and 2,000 parts.
2. Every part has at least one revision.
3. Maximum BOM depth is between 5 and 7 edges (currently 5).
4. No BOM cycles.
5. No orphan parts: every part that is not a product top-level assembly has at least one BOM parent.
6. Every released assembly's BOM children reference released revisions.
7. No two released revisions of the same part have overlapping effectivity windows.
8. Every BOM quantity is greater than zero.
9. Every BOM line `uom` equals the child part base `uom`.
10. Every closed `ECO` has at least one `ECN` child referencing it.

## Defect switches

Each switch is applied independently. The tests generate clean data, assert the condition is absent, then generate with only that switch and assert the condition is present and recorded in `defects.json`.

| Switch | What is injected | Invariant violated | Manifest records |
|---|---|---|---|
| `cyclic_bom` | Adds a BOM line from a component back to one of its ancestors. | The BOM must be acyclic. | New `bom_line_id`, `parent_part_id`, `child_part_id` / `ancestor_part_id`. |
| `orphan_parts` | Removes the only incoming BOM line from two raw materials. | Every non-top part must have a BOM parent. | `orphan_part_ids` and removed `removed_bom_line_ids`. |
| `released_assembly_unreleased_child` | Repoints one released assembly's BOM line at a child revision that is `in_work`. | A released assembly may only consume released child revisions. | `bom_line_id`, parent/child ids, previous and injected child revision ids. |
| `overlapping_revision_effectivity` | Adds a second released revision whose open effectivity window overlaps the part's existing released revision. | Released revisions of one part must not overlap. | `part_id`, both `revision_ids`, both windows. |
| `zero_negative_quantity` | Sets two positive BOM quantities to `0.00` and `-3.00`. | BOM quantities must be positive. | Each `bom_line_id` with previous and injected quantity. |
| `uom_mismatch` | Changes one BOM line's `uom` so it differs from the child part base `uom`. | BOM quantity UoM must match the child part base UoM. | `bom_line_id`, `child_part_id`, expected and injected UoM. |
| `eco_closed_without_ecn` | Marks an ECO that has no ECN child as `closed` and sets its close date. | Every closed ECO must have an ECN child. | `change_id`, `parent_change_id`, previous and injected status, `has_ecn_child: false`. |

`--defects all` enables all seven. Selected defects can be combined with a comma-separated list, for example `--defects cyclic_bom,uom_mismatch`.

## Effectivity and date conventions

- Empty `effective_to` / `effectivity_end` means open-ended.
- Two windows overlap when the later start is strictly before the earlier end, or when the earlier window is open-ended. Windows that touch at a single date do not overlap.
- Clean revisions start after the part's creation date; obsolete prior revisions end one day before the base revision starts; in-work revisions start 180–540 days after the base revision.

## dbt layers

The `dbt/` project reads the generated CSVs in place through dbt-duckdb `external_location` (`PLM_RAW_DIR`, default `data/raw`) and writes views to `data/plm.duckdb`.

- **Staging** (`models/staging/stg_*.sql`, views) — one model per CSV. Columns are renamed, strings trimmed, enums lower-cased, dates and numerics cast, and empty date strings become `NULL`.
- **`int_current_revisions`** — the released revision of each part effective on the `as_of_date` dbt var (default `2026-06-01`). It keeps revisions where `as_of_date` falls between `effective_from` and `coalesce(effective_to, '9999-12-31')` and resolves overlapping released revisions by latest `effective_from`, then `revision_code`.
- **`int_bom_explosion`** — a recursive CTE from each product top-level part. It follows BOM lines whose effectivity window contains `as_of_date` and whose parent revision is the current released revision, and emits `product_id`, `level`, `path`, `parent_part_id`, `child_part_id`, `quantity` and `accumulated_quantity`. The traversal carries a path list so a cyclic BOM cannot loop.
- **`int_where_used`** — one row per `(child_part_id, parent_part_id, product_id)`: the immediate parent usage plus every product that reaches the part.

Build with `make dbt` or `dbt build --select staging intermediate --project-dir dbt --profiles-dir dbt` from the repository root.

## Assumptions and limitations

- The dataset is entirely synthetic; no client, production or real supplier data is used.
- Clean BOMs have single-parent parts, which keeps the forest easy to traverse. Real PLM commonly reuses components under many assemblies.
- `erp_bom.csv` is a faithful part-number projection of the PLM BOM, not an independently corrupted ERP system. Reconciliation defects across the two systems are a later-milestone concern.
- `lifecycle_state = obsolete` is part of the schema, but the clean generator currently expresses obsolescence through superseded revision statuses; only `released` and `draft` part lifecycles occur in generated rows.
