# plm-bom-pipeline

Synthetic PLM data — parts, multi-level BOMs and ECR/ECO/ECN change control — generated deterministically for testing analytics.

This repository contains a small, standard-library-only Python generator for a fictional bicycle manufacturer's product lifecycle data. It writes 3 product families, 18 products, exactly 2,000 parts, revision histories with effectivity dates, five-level bills of material, ECR → ECO → ECN change records with approvals, suppliers and a synthetic ERP BOM extract. Every file is derived from one integer seed, all tables are sorted by primary key, and dates come from fixed arithmetic rather than the clock — so the same seed produces byte-identical files. Seven independently switchable defects model common PLM data-quality problems.

## Built from scratch on synthetic data

All companies, products, suppliers, costs, dates and change records are fabricated. No client or production data is used. The generator models generic PLM concepts only.

## Quickstart

Requires Python 3.11+. Runtime code uses only the Python standard library; `pytest` is the only development dependency.

```bash
make data    # clean dataset  -> data/raw
make messy   # all defects    -> data/raw-messy
make test    # run the test suite
```

Equivalent CLI invocations:

```bash
python -m generator --out data/raw --seed 42 --defects none
python -m generator --out data/raw-messy --seed 42 --defects all
python -m generator --out data/raw --defects cyclic_bom,orphan_parts
```

The Makefile uses `python3` by default (`make PYTHON=python data` is supported). Output directories are ignored by git.

## dbt models

The dbt project in `dbt/` reads the generated CSVs in place with DuckDB and builds a staging and intermediate layer into `data/plm.duckdb` (gitignored). Sources use dbt-duckdb's `external_location`, so there is no separate load step.

```bash
python3 -m venv .venv-dbt
. .venv-dbt/bin/activate
pip install -r requirements-dbt.txt

make dbt        # generate data, then build staging + intermediate + tests
make dbt-docs   # generate the dbt docs site
```

`make dbt` runs `dbt build --select staging intermediate` from the repository root (it also passes absolute `PLM_RAW_DIR` and `PLM_DUCKDB_PATH` paths). To run dbt directly, the same command works from the repository root:

```bash
dbt build --select staging intermediate --project-dir dbt --profiles-dir dbt
dbt build --select int_bom_explosion --project-dir dbt --profiles-dir dbt \
  --vars '{as_of_date: "2025-01-01"}'
dbt docs generate --project-dir dbt --profiles-dir dbt
```

Layers:

- **staging** — one typed, renamed view per CSV (`stg_*`), enums lower-cased.
- **intermediate** — `int_current_revisions` (released revision per part as of the `as_of_date` var, default `2026-06-01`), `int_bom_explosion` (recursive BOM explosion with a cycle guard and accumulated quantities) and `int_where_used` (direct parent and product usage).

The `int_bom_explosion` unit test is a hand-checked three-level fixture with known quantities; run it with `dbt test --select int_bom_explosion --project-dir dbt --profiles-dir dbt`.

## What is generated

| File | Rows (clean, seed 42) | Contents |
|---|---|---|
| `families.csv` | 3 | Road, Mountain and City families |
| `products.csv` | 18 | Products and their top-level assembly |
| `parts.csv` | 2,000 | Assemblies, components and raw materials |
| `part_revisions.csv` | 2,502 | Released, in-work and superseded revisions |
| `boms.csv` | 1,982 | Multi-level parent/child BOM lines |
| `changes.csv` | 75 | ECR, ECO and ECN records |
| `change_approvals.csv` | 150 | Approval decisions per change |
| `suppliers.csv` | 40 | Fictional suppliers |
| `part_suppliers.csv` | 2,849 | Sourcing price and lead time |
| `erp_bom.csv` | 1,982 | Synthetic ERP BOM extract for later reconciliation |
| `defects.json` | — | Manifest of enabled defects and the exact rows they touched |

See [`docs/data-model.md`](docs/data-model.md) for keys, relationships, effectivity semantics and each defect switch.

## Roadmap

Milestone 1 is the deterministic generator and its test suite. Milestone 2 adds the dbt staging and intermediate layers. Later milestones add defect-specific data quality tests, marts and a report over the synthetic dataset.
