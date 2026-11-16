"""Tests for the deterministic synthetic PLM generator."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from generator import generate  # noqa: E402
from generator.writer import EXPECTED_FILES  # noqa: E402


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def read_rows(out_dir: Path, filename: str) -> list[dict[str, str]]:
    with (out_dir / filename).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_manifest(out_dir: Path) -> dict:
    return json.loads((out_dir / "defects.json").read_text(encoding="utf-8"))


def generate_into(
    tmp_path: Path,
    *,
    seed: int = 42,
    defects: list[str] | None = None,
    tag: str,
) -> Path:
    out_dir = tmp_path / tag
    generate(str(out_dir), seed=seed, defects=defects)
    return out_dir


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_adjacency(boms: list[dict[str, str]]) -> dict[str, list[str]]:
    adjacency: dict[str, list[str]] = defaultdict(list)
    for line in boms:
        adjacency[line["parent_part_id"]].append(line["child_part_id"])
    return adjacency


def has_bom_cycle(boms: list[dict[str, str]]) -> bool:
    adjacency = build_adjacency(boms)
    state: dict[str, int] = {}

    def visit(node: str) -> bool:
        state[node] = 1
        for child in adjacency.get(node, []):
            if state.get(child) == 1:
                return True
            if state.get(child, 0) == 0 and visit(child):
                return True
        state[node] = 2
        return False

    return any(state.get(node, 0) == 0 and visit(node) for node in list(adjacency))


def max_bom_depth(products: list[dict[str, str]], boms: list[dict[str, str]]) -> int:
    adjacency = build_adjacency(boms)
    roots = [product["top_level_part_id"] for product in products]
    best = 0
    stack = [(root, 0, frozenset({root})) for root in roots]
    while stack:
        node, depth, path = stack.pop()
        best = max(best, depth)
        for child in adjacency.get(node, []):
            if child not in path:
                stack.append((child, depth + 1, path | {child}))
    return best


def orphan_part_ids(
    parts: list[dict[str, str]],
    boms: list[dict[str, str]],
    products: list[dict[str, str]],
) -> list[str]:
    top_level = {product["top_level_part_id"] for product in products}
    children = {line["child_part_id"] for line in boms}
    return [
        part["part_id"]
        for part in parts
        if part["part_id"] not in top_level and part["part_id"] not in children
    ]


def released_parent_unreleased_children(
    parts: list[dict[str, str]],
    revisions: list[dict[str, str]],
    boms: list[dict[str, str]],
) -> list[dict[str, str]]:
    part_type = {part["part_id"]: part["part_type"] for part in parts}
    status = {revision["revision_id"]: revision["status"] for revision in revisions}
    violations = []
    for line in boms:
        if (
            part_type[line["parent_part_id"]] == "assembly"
            and status[line["parent_revision_id"]] == "released"
            and status[line["child_revision_id"]] != "released"
        ):
            violations.append(line)
    return violations


def overlapping_revision_parts(revisions: list[dict[str, str]]) -> list[str]:
    released: dict[str, list[dict[str, str]]] = defaultdict(list)
    for revision in revisions:
        if revision["status"] == "released":
            released[revision["part_id"]].append(revision)

    bad = []
    for part_id, revisions_for_part in released.items():
        ordered = sorted(
            revisions_for_part, key=lambda revision: revision["effective_from"]
        )
        for previous, current in zip(ordered, ordered[1:]):
            if (
                previous["effective_to"] == ""
                or current["effective_from"] < previous["effective_to"]
            ):
                bad.append(part_id)
                break
    return bad


def nonpositive_quantity_lines(boms: list[dict[str, str]]) -> list[dict[str, str]]:
    return [line for line in boms if float(line["quantity"]) <= 0]


def uom_mismatch_lines(
    boms: list[dict[str, str]], parts: list[dict[str, str]]
) -> list[dict[str, str]]:
    base_uom = {part["part_id"]: part["uom"] for part in parts}
    return [
        line for line in boms if line["uom"] != base_uom[line["child_part_id"]]
    ]


def closed_ecos_without_ecn(
    changes: list[dict[str, str]],
) -> list[dict[str, str]]:
    ecn_parents = {
        change["parent_change_id"]
        for change in changes
        if change["change_type"] == "ECN"
    }
    return [
        change
        for change in changes
        if change["change_type"] == "ECO"
        and change["status"] == "closed"
        and change["change_id"] not in ecn_parents
    ]


def assert_listed(manifest: dict, name: str) -> dict:
    assert name in manifest["enabled_defects"]
    assert name in manifest["defects"]
    return manifest["defects"][name]["records"]


# ----------------------------------------------------------------------
# Determinism
# ----------------------------------------------------------------------
def test_determinism_same_seed_is_byte_identical(tmp_path: Path) -> None:
    modes = [("clean", None), ("all-defects", ["all"])]
    for label, defects in modes:
        first = generate_into(
            tmp_path, seed=42, defects=defects, tag=f"{label}-first"
        )
        second = generate_into(
            tmp_path, seed=42, defects=defects, tag=f"{label}-second"
        )
        for filename in EXPECTED_FILES:
            assert sha256(first / filename) == sha256(second / filename), (
                label,
                filename,
            )


def test_different_seed_changes_output(tmp_path: Path) -> None:
    seed_42 = generate_into(tmp_path, seed=42, tag="seed-42")
    seed_43 = generate_into(tmp_path, seed=43, tag="seed-43")

    assert sha256(seed_42 / "parts.csv") != sha256(seed_43 / "parts.csv")
    assert sha256(seed_42 / "boms.csv") != sha256(seed_43 / "boms.csv")


def test_part_weights_positive_and_deterministic(tmp_path: Path) -> None:
    first = generate_into(tmp_path, tag="weight-first")
    second = generate_into(tmp_path, tag="weight-second")

    parts = read_rows(first, "parts.csv")
    assert len(parts) == 2000
    for part in parts:
        assert part["weight_kg"], part["part_id"]
        assert float(part["weight_kg"]) > 0, part["part_id"]
        assert len(part["weight_kg"].split(".")[-1]) == 3, part["part_id"]

    assert sha256(first / "parts.csv") == sha256(second / "parts.csv")


# ----------------------------------------------------------------------
# Shape and clean-data invariants
# ----------------------------------------------------------------------
def test_counts_and_shape(tmp_path: Path) -> None:
    out_dir = generate_into(tmp_path, tag="shape")
    parts = read_rows(out_dir, "parts.csv")
    families = read_rows(out_dir, "families.csv")
    products = read_rows(out_dir, "products.csv")
    revisions = read_rows(out_dir, "part_revisions.csv")
    boms = read_rows(out_dir, "boms.csv")

    assert len(parts) == 2000
    assert len(families) == 3
    assert {family["family_name"] for family in families} == {
        "Road",
        "Mountain",
        "City",
    }
    assert len(products) >= 15

    parts_with_revision = {revision["part_id"] for revision in revisions}
    assert {part["part_id"] for part in parts} <= parts_with_revision

    depth = max_bom_depth(products, boms)
    assert 5 <= depth <= 7, f"max BOM depth was {depth}"


def test_clean_data_invariants(tmp_path: Path) -> None:
    out_dir = generate_into(tmp_path, tag="clean")
    parts = read_rows(out_dir, "parts.csv")
    products = read_rows(out_dir, "products.csv")
    revisions = read_rows(out_dir, "part_revisions.csv")
    boms = read_rows(out_dir, "boms.csv")
    changes = read_rows(out_dir, "changes.csv")
    approvals = read_rows(out_dir, "change_approvals.csv")

    assert not has_bom_cycle(boms)
    assert orphan_part_ids(parts, boms, products) == []
    assert released_parent_unreleased_children(parts, revisions, boms) == []
    assert overlapping_revision_parts(revisions) == []
    assert nonpositive_quantity_lines(boms) == []
    assert uom_mismatch_lines(boms, parts) == []
    assert closed_ecos_without_ecn(changes) == []

    # Normal ECR -> ECO -> ECN flow and valid approval references.
    changes_by_id = {change["change_id"]: change for change in changes}
    for change in changes:
        if change["change_type"] == "ECO":
            parent = changes_by_id[change["parent_change_id"]]
            assert parent["change_type"] == "ECR"
        elif change["change_type"] == "ECN":
            parent = changes_by_id[change["parent_change_id"]]
            assert parent["change_type"] == "ECO"
    assert {approval["change_id"] for approval in approvals} <= set(changes_by_id)

    part_ids = {part["part_id"] for part in parts}
    assert {product["top_level_part_id"] for product in products} <= part_ids


# ----------------------------------------------------------------------
# One test per defect switch
# ----------------------------------------------------------------------
def test_defect_cyclic_bom(tmp_path: Path) -> None:
    clean = generate_into(tmp_path, tag="cyclic-clean")
    assert not has_bom_cycle(read_rows(clean, "boms.csv"))
    assert "cyclic_bom" not in read_manifest(clean)["defects"]

    messy = generate_into(tmp_path, defects=["cyclic_bom"], tag="cyclic-messy")
    boms = read_rows(messy, "boms.csv")
    assert has_bom_cycle(boms)

    records = assert_listed(read_manifest(messy), "cyclic_bom")
    line = next(
        line for line in boms if line["bom_line_id"] == records["bom_line_id"]
    )
    assert line["parent_part_id"] == records["parent_part_id"]
    assert line["child_part_id"] == records["child_part_id"]
    assert records["child_part_id"] == records["ancestor_part_id"]


def test_defect_orphan_parts(tmp_path: Path) -> None:
    clean = generate_into(tmp_path, tag="orphan-clean")
    assert (
        orphan_part_ids(
            read_rows(clean, "parts.csv"),
            read_rows(clean, "boms.csv"),
            read_rows(clean, "products.csv"),
        )
        == []
    )
    assert "orphan_parts" not in read_manifest(clean)["defects"]

    messy = generate_into(tmp_path, defects=["orphan_parts"], tag="orphan-messy")
    parts = read_rows(messy, "parts.csv")
    boms = read_rows(messy, "boms.csv")
    products = read_rows(messy, "products.csv")
    orphans = orphan_part_ids(parts, boms, products)
    assert orphans

    records = assert_listed(read_manifest(messy), "orphan_parts")
    assert set(records["orphan_part_ids"]) <= set(orphans)
    remaining_bom_ids = {line["bom_line_id"] for line in boms}
    assert not (set(records["removed_bom_line_ids"]) & remaining_bom_ids)


def test_defect_released_assembly_unreleased_child(tmp_path: Path) -> None:
    clean = generate_into(tmp_path, tag="released-clean")
    assert (
        released_parent_unreleased_children(
            read_rows(clean, "parts.csv"),
            read_rows(clean, "part_revisions.csv"),
            read_rows(clean, "boms.csv"),
        )
        == []
    )
    assert "released_assembly_unreleased_child" not in read_manifest(clean)["defects"]

    messy = generate_into(
        tmp_path,
        defects=["released_assembly_unreleased_child"],
        tag="released-messy",
    )
    violations = released_parent_unreleased_children(
        read_rows(messy, "parts.csv"),
        read_rows(messy, "part_revisions.csv"),
        read_rows(messy, "boms.csv"),
    )
    assert violations

    records = assert_listed(
        read_manifest(messy), "released_assembly_unreleased_child"
    )
    assert records["bom_line_id"] in {
        line["bom_line_id"] for line in violations
    }
    revision_status = {
        revision["revision_id"]: revision["status"]
        for revision in read_rows(messy, "part_revisions.csv")
    }
    assert revision_status[records["injected_child_revision_id"]] == "in_work"


def test_defect_overlapping_revision_effectivity(tmp_path: Path) -> None:
    clean = generate_into(tmp_path, tag="overlap-clean")
    assert overlapping_revision_parts(read_rows(clean, "part_revisions.csv")) == []
    assert "overlapping_revision_effectivity" not in read_manifest(clean)["defects"]

    messy = generate_into(
        tmp_path,
        defects=["overlapping_revision_effectivity"],
        tag="overlap-messy",
    )
    revisions = read_rows(messy, "part_revisions.csv")
    assert overlapping_revision_parts(revisions)

    records = assert_listed(
        read_manifest(messy), "overlapping_revision_effectivity"
    )
    assert records["part_id"] in overlapping_revision_parts(revisions)
    by_id = {revision["revision_id"]: revision for revision in revisions}
    for revision_id in records["revision_ids"]:
        assert by_id[revision_id]["part_id"] == records["part_id"]
        assert by_id[revision_id]["status"] == "released"


def test_defect_zero_negative_quantity(tmp_path: Path) -> None:
    clean = generate_into(tmp_path, tag="quantity-clean")
    assert nonpositive_quantity_lines(read_rows(clean, "boms.csv")) == []
    assert "zero_negative_quantity" not in read_manifest(clean)["defects"]

    messy = generate_into(
        tmp_path, defects=["zero_negative_quantity"], tag="quantity-messy"
    )
    boms = read_rows(messy, "boms.csv")
    assert nonpositive_quantity_lines(boms)

    records = assert_listed(read_manifest(messy), "zero_negative_quantity")
    by_id = {line["bom_line_id"]: line for line in boms}
    for record in records["bom_lines"]:
        line = by_id[record["bom_line_id"]]
        assert float(line["quantity"]) <= 0
        assert line["quantity"] == record["injected_quantity"]


def test_defect_uom_mismatch(tmp_path: Path) -> None:
    clean = generate_into(tmp_path, tag="uom-clean")
    assert (
        uom_mismatch_lines(
            read_rows(clean, "boms.csv"), read_rows(clean, "parts.csv")
        )
        == []
    )
    assert "uom_mismatch" not in read_manifest(clean)["defects"]

    messy = generate_into(tmp_path, defects=["uom_mismatch"], tag="uom-messy")
    parts = read_rows(messy, "parts.csv")
    boms = read_rows(messy, "boms.csv")
    assert uom_mismatch_lines(boms, parts)

    records = assert_listed(read_manifest(messy), "uom_mismatch")
    line = next(
        line for line in boms if line["bom_line_id"] == records["bom_line_id"]
    )
    base_uom = {part["part_id"]: part["uom"] for part in parts}
    assert line["uom"] == records["injected_uom"]
    assert line["uom"] != base_uom[records["child_part_id"]]
    assert records["expected_uom"] == base_uom[records["child_part_id"]]


def test_defect_eco_closed_without_ecn(tmp_path: Path) -> None:
    clean = generate_into(tmp_path, tag="eco-clean")
    assert closed_ecos_without_ecn(read_rows(clean, "changes.csv")) == []
    assert "eco_closed_without_ecn" not in read_manifest(clean)["defects"]

    messy = generate_into(
        tmp_path, defects=["eco_closed_without_ecn"], tag="eco-messy"
    )
    changes = read_rows(messy, "changes.csv")
    without_ecn = closed_ecos_without_ecn(changes)
    assert without_ecn

    records = assert_listed(read_manifest(messy), "eco_closed_without_ecn")
    assert records["change_id"] in {
        change["change_id"] for change in without_ecn
    }
    assert records["injected_status"] == "closed"


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def test_cli_smoke(tmp_path: Path) -> None:
    out_dir = tmp_path / "cli-output"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "generator",
            "--out",
            str(out_dir),
            "--seed",
            "7",
            "--defects",
            "all",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    for filename in EXPECTED_FILES:
        assert (out_dir / filename).exists(), filename

    manifest = read_manifest(out_dir)
    assert manifest["enabled_defects"] == [
        "cyclic_bom",
        "orphan_parts",
        "released_assembly_unreleased_child",
        "overlapping_revision_effectivity",
        "zero_negative_quantity",
        "uom_mismatch",
        "eco_closed_without_ecn",
    ]
