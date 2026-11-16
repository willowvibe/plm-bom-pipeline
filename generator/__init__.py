"""Synthetic PLM data generator for a fictional bicycle manufacturer."""

from __future__ import annotations

from .defects import inject_defects, parse_defect_selection
from .model import build_dataset, build_erp_bom
from .writer import EXPECTED_FILES, write_dataset

__all__ = [
    "EXPECTED_FILES",
    "build_dataset",
    "generate",
    "inject_defects",
    "parse_defect_selection",
]


def generate(
    out_dir: str,
    seed: int = 42,
    defects: str | list[str] | None = None,
) -> dict:
    """Generate the dataset into ``out_dir`` and return the defect manifest."""
    dataset = build_dataset(seed)
    manifest = inject_defects(dataset, defects, seed)
    dataset.erp_bom = build_erp_bom(dataset)
    write_dataset(dataset, out_dir, manifest)
    return manifest
