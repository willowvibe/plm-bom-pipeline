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

Milestone 1 is the deterministic generator and its test suite. Later milestones add dbt models, data tests and a report over the synthetic dataset.
