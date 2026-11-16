"""Deterministic CSV and manifest writing."""

from __future__ import annotations

import csv
import json
from dataclasses import fields
from pathlib import Path
from typing import Any, Callable

from .model import (
    BomLine,
    Change,
    ChangeApproval,
    Dataset,
    ErpBomLine,
    Family,
    Part,
    PartRevision,
    PartSupplier,
    Product,
    Supplier,
)

MANIFEST_FILENAME = "defects.json"

TABLE_SPECS: list[tuple[str, type, Callable[[Any], tuple]]] = [
    ("families.csv", Family, lambda row: (row.family_id,)),
    ("products.csv", Product, lambda row: (row.product_id,)),
    ("parts.csv", Part, lambda row: (row.part_id,)),
    ("part_revisions.csv", PartRevision, lambda row: (row.revision_id,)),
    ("boms.csv", BomLine, lambda row: (row.bom_line_id,)),
    ("changes.csv", Change, lambda row: (row.change_id,)),
    ("change_approvals.csv", ChangeApproval, lambda row: (row.approval_id,)),
    ("suppliers.csv", Supplier, lambda row: (row.supplier_id,)),
    (
        "part_suppliers.csv",
        PartSupplier,
        lambda row: (row.part_id, row.supplier_id),
    ),
    (
        "erp_bom.csv",
        ErpBomLine,
        lambda row: (
            row.parent_part_number,
            row.child_part_number,
            row.uom,
            row.quantity,
        ),
    ),
]

TABLE_FILENAMES = [spec[0] for spec in TABLE_SPECS]
EXPECTED_FILES = TABLE_FILENAMES + [MANIFEST_FILENAME]


def _write_csv(
    path: Path,
    rows: list[Any],
    row_type: type,
    sort_key: Callable[[Any], tuple],
) -> None:
    fieldnames = [item.name for item in fields(row_type)]
    ordered = sorted(rows, key=sort_key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            lineterminator="\n",
        )
        writer.writeheader()
        for row in ordered:
            writer.writerow({name: getattr(row, name) for name in fieldnames})


def write_dataset(dataset: Dataset, out_dir: str | Path, manifest: dict) -> list[Path]:
    """Write every table and the defect manifest, returning the paths."""
    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)

    tables = {
        "families.csv": dataset.families,
        "products.csv": dataset.products,
        "parts.csv": dataset.parts,
        "part_revisions.csv": dataset.part_revisions,
        "boms.csv": dataset.boms,
        "changes.csv": dataset.changes,
        "change_approvals.csv": dataset.change_approvals,
        "suppliers.csv": dataset.suppliers,
        "part_suppliers.csv": dataset.part_suppliers,
        "erp_bom.csv": dataset.erp_bom,
    }

    written: list[Path] = []
    for filename, row_type, sort_key in TABLE_SPECS:
        path = output / filename
        _write_csv(path, tables[filename], row_type, sort_key)
        written.append(path)

    manifest_path = output / MANIFEST_FILENAME
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    written.append(manifest_path)
    return written
