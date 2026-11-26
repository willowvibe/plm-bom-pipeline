"""Switchable data defects.

``inject_defects`` mutates a clean :class:`generator.model.Dataset` and returns
a JSON-serialisable manifest that names every defect and records exactly which
rows were touched.  A separate ``random.Random`` stream is used so that turning
defects on or off never changes the clean base data.
"""

from __future__ import annotations

import random
from collections import defaultdict
from datetime import date, timedelta

from .model import BomLine, Change, Dataset, PartRevision

CANONICAL_DEFECTS = [
    "cyclic_bom",
    "orphan_parts",
    "released_assembly_unreleased_child",
    "overlapping_revision_effectivity",
    "zero_negative_quantity",
    "uom_mismatch",
    "eco_closed_without_ecn",
    "change_dates_out_of_order",
]

DEFECT_DESCRIPTIONS = {
    "cyclic_bom": "A BOM line points from a descendant back to one of its ancestors.",
    "orphan_parts": "Parts with no BOM parent that are not product top-level parts.",
    "released_assembly_unreleased_child": (
        "A released assembly revision uses a child revision that is still in_work."
    ),
    "overlapping_revision_effectivity": (
        "Two released revisions of the same part have overlapping effectivity windows."
    ),
    "zero_negative_quantity": "At least one BOM line has a quantity of zero or less.",
    "uom_mismatch": "At least one BOM line uses a unit of measure that differs from the child part base UoM.",
    "eco_closed_without_ecn": "A closed ECO has no ECN child referencing it.",
    "change_dates_out_of_order": (
        "A change is approved before initiation or closed before approval."
    ),
}


def parse_defect_selection(value: str | list[str] | None) -> list[str]:
    """Normalise a CLI value or list into a canonical defect list."""
    if value is None:
        return []
    if isinstance(value, str):
        raw = value.strip().lower()
        if raw in ("", "none"):
            return []
        if raw == "all":
            return list(CANONICAL_DEFECTS)
        names = [item.strip().lower() for item in raw.split(",") if item.strip()]
    else:
        names = [str(item).strip().lower() for item in value if str(item).strip()]

    unknown = sorted(set(names) - set(CANONICAL_DEFECTS) - {"all", "none"})
    if unknown:
        raise ValueError(
            f"unknown defect(s): {', '.join(unknown)}; "
            f"choose from {', '.join(CANONICAL_DEFECTS)} or 'all'"
        )
    if "none" in names:
        if len(names) > 1:
            raise ValueError("'none' cannot be combined with other defects")
        return []
    if "all" in names:
        return list(CANONICAL_DEFECTS)

    selected = set(names)
    return [name for name in CANONICAL_DEFECTS if name in selected]


def _next_bom_id(dataset: Dataset) -> str:
    highest = max(int(line.bom_line_id.split("-")[1]) for line in dataset.boms)
    return f"BOM-{highest + 1:06d}"


def _next_revision_id(dataset: Dataset) -> str:
    highest = max(int(rev.revision_id.split("-")[1]) for rev in dataset.part_revisions)
    return f"REV-{highest + 1:05d}"


def _released_by_part(dataset: Dataset) -> dict[str, list[PartRevision]]:
    released: dict[str, list[PartRevision]] = defaultdict(list)
    for revision in dataset.part_revisions:
        if revision.status == "released":
            released[revision.part_id].append(revision)
    for revisions in released.values():
        revisions.sort(key=lambda revision: (revision.effective_from, revision.revision_id))
    return released


def _first_released_revision(
    released: dict[str, list[PartRevision]], part_id: str
) -> PartRevision:
    revisions = released.get(part_id)
    if not revisions:
        raise RuntimeError(f"part {part_id} has no released revision")
    return revisions[0]


def _inject_cyclic_bom(dataset: Dataset, rng: random.Random) -> dict:
    part_type = {part.part_id: part.part_type for part in dataset.parts}
    part_by_id = {part.part_id: part for part in dataset.parts}
    released = _released_by_part(dataset)

    parent_of: dict[str, str] = {}
    for line in dataset.boms:
        parent_of.setdefault(line.child_part_id, line.parent_part_id)

    candidates = [
        line
        for line in dataset.boms
        if part_type.get(line.parent_part_id) == "component"
    ]
    line = rng.choice(candidates)
    ancestor = line.parent_part_id
    seen: set[str] = set()
    while ancestor in parent_of and ancestor not in seen:
        seen.add(ancestor)
        ancestor = parent_of[ancestor]

    if ancestor == line.parent_part_id:
        raise RuntimeError("could not find an ancestor for cyclic_bom")

    ancestor_revision = _first_released_revision(released, ancestor)
    find_number = max(
        int(other.find_number)
        for other in dataset.boms
        if other.parent_part_id == line.parent_part_id
    )
    new_line = BomLine(
        bom_line_id=_next_bom_id(dataset),
        parent_part_id=line.parent_part_id,
        parent_revision_id=line.parent_revision_id,
        child_part_id=ancestor,
        child_revision_id=ancestor_revision.revision_id,
        quantity="1.00",
        uom=part_by_id[ancestor].uom,
        find_number=str(find_number + 10),
        effectivity_start=line.effectivity_start,
        effectivity_end="",
    )
    dataset.boms.append(new_line)
    return {
        "bom_line_id": new_line.bom_line_id,
        "parent_part_id": new_line.parent_part_id,
        "child_part_id": ancestor,
        "ancestor_part_id": ancestor,
    }


def _inject_orphan_parts(dataset: Dataset, rng: random.Random) -> dict:
    incoming: dict[str, list[BomLine]] = defaultdict(list)
    for line in dataset.boms:
        incoming[line.child_part_id].append(line)

    candidates = [
        part
        for part in dataset.parts
        if part.part_type == "raw_material" and len(incoming[part.part_id]) == 1
    ]
    targets = rng.sample(candidates, 2)
    orphan_ids = [part.part_id for part in targets]
    removed_ids = [incoming[part_id][0].bom_line_id for part_id in orphan_ids]
    target_set = set(orphan_ids)
    dataset.boms = [
        line for line in dataset.boms if line.child_part_id not in target_set
    ]
    return {
        "orphan_part_ids": orphan_ids,
        "removed_bom_line_ids": removed_ids,
    }


def _inject_released_assembly_unreleased_child(
    dataset: Dataset, rng: random.Random
) -> dict:
    part_type = {part.part_id: part.part_type for part in dataset.parts}
    revision_status = {
        revision.revision_id: revision.status for revision in dataset.part_revisions
    }
    in_work: dict[str, PartRevision] = {}
    for revision in dataset.part_revisions:
        if revision.status == "in_work":
            in_work.setdefault(revision.part_id, revision)

    candidates = [
        line
        for line in dataset.boms
        if part_type.get(line.parent_part_id) == "assembly"
        and line.child_part_id in in_work
        and revision_status[line.parent_revision_id] == "released"
    ]
    if not candidates:
        raise RuntimeError("no released assembly with an in_work child revision found")

    line = rng.choice(candidates)
    previous_revision_id = line.child_revision_id
    child_revision = in_work[line.child_part_id]
    line.child_revision_id = child_revision.revision_id
    return {
        "bom_line_id": line.bom_line_id,
        "parent_part_id": line.parent_part_id,
        "parent_revision_id": line.parent_revision_id,
        "child_part_id": line.child_part_id,
        "previous_child_revision_id": previous_revision_id,
        "injected_child_revision_id": child_revision.revision_id,
        "injected_child_revision_status": child_revision.status,
    }


def _inject_overlapping_revision_effectivity(
    dataset: Dataset, rng: random.Random
) -> dict:
    released = _released_by_part(dataset)
    part_id = rng.choice(sorted(released))
    base = released[part_id][0]

    codes = [
        revision.revision_code
        for revision in dataset.part_revisions
        if revision.part_id == part_id
    ]
    next_code = chr(max(ord(code) for code in codes) + 1)
    start = date.fromisoformat(base.effective_from) + timedelta(days=15)
    new_revision = PartRevision(
        revision_id=_next_revision_id(dataset),
        part_id=part_id,
        revision_code=next_code,
        status="released",
        effective_from=start.isoformat(),
        effective_to="",
    )
    dataset.part_revisions.append(new_revision)
    return {
        "part_id": part_id,
        "revision_ids": [base.revision_id, new_revision.revision_id],
        "windows": [
            [base.effective_from, base.effective_to],
            [new_revision.effective_from, new_revision.effective_to],
        ],
    }


def _inject_zero_negative_quantity(dataset: Dataset, rng: random.Random) -> dict:
    positive_lines = [line for line in dataset.boms if float(line.quantity) > 0]
    targets = rng.sample(positive_lines, 2)
    records = []
    for line, quantity in zip(targets, ["0.00", "-3.00"]):
        previous = line.quantity
        line.quantity = quantity
        records.append(
            {
                "bom_line_id": line.bom_line_id,
                "previous_quantity": previous,
                "injected_quantity": quantity,
            }
        )
    return {"bom_lines": records}


def _inject_uom_mismatch(
    dataset: Dataset, rng: random.Random, exclude_line_ids: set[str] | None = None
) -> dict:
    excluded = exclude_line_ids or set()
    candidates = [
        line for line in dataset.boms if line.bom_line_id not in excluded
    ]
    line = rng.choice(candidates)
    part_uom = {part.part_id: part.uom for part in dataset.parts}
    expected_uom = part_uom[line.child_part_id]
    injected_uom = "KG" if expected_uom != "KG" else "EA"
    line.uom = injected_uom
    return {
        "bom_line_id": line.bom_line_id,
        "child_part_id": line.child_part_id,
        "expected_uom": expected_uom,
        "injected_uom": injected_uom,
    }


def _inject_eco_closed_without_ecn(dataset: Dataset, rng: random.Random) -> dict:
    ecn_parents = {
        change.parent_change_id
        for change in dataset.changes
        if change.change_type == "ECN"
    }
    candidates = [
        change
        for change in dataset.changes
        if change.change_type == "ECO"
        and change.status != "closed"
        and change.change_id not in ecn_parents
    ]

    if candidates:
        eco = rng.choice(candidates)
        previous_status = eco.status
        initiated = date.fromisoformat(eco.initiated_at)
        eco.status = "closed"
        if not eco.approved_at:
            eco.approved_at = (initiated + timedelta(days=3)).isoformat()
        eco.closed_at = (initiated + timedelta(days=15)).isoformat()
        return {
            "change_id": eco.change_id,
            "parent_change_id": eco.parent_change_id,
            "previous_status": previous_status,
            "injected_status": "closed",
            "has_ecn_child": False,
        }

    # Fallback: construct a closed ECO (and its parent ECR) from scratch.
    parts = dataset.parts
    affected_part_id = rng.choice(parts).part_id
    ecr_number = 1 + max(
        int(change.change_id.split("-")[1])
        for change in dataset.changes
        if change.change_type == "ECR"
    )
    eco_number = 1 + max(
        int(change.change_id.split("-")[1])
        for change in dataset.changes
        if change.change_type == "ECO"
    )
    initiated = date(2025, 1, 6)
    ecr = Change(
        change_id=f"ECR-{ecr_number:04d}",
        change_type="ECR",
        parent_change_id="",
        title="Fallback closed change without ECN",
        status="approved",
        initiated_at=initiated.isoformat(),
        approved_at=(initiated + timedelta(days=2)).isoformat(),
        closed_at="",
        affected_part_id=affected_part_id,
    )
    eco = Change(
        change_id=f"ECO-{eco_number:04d}",
        change_type="ECO",
        parent_change_id=ecr.change_id,
        title=f"Implement: {ecr.title}",
        status="closed",
        initiated_at=(initiated + timedelta(days=6)).isoformat(),
        approved_at=(initiated + timedelta(days=9)).isoformat(),
        closed_at=(initiated + timedelta(days=20)).isoformat(),
        affected_part_id=affected_part_id,
    )
    dataset.changes.extend([ecr, eco])
    return {
        "change_id": eco.change_id,
        "parent_change_id": eco.parent_change_id,
        "previous_status": "new",
        "injected_status": "closed",
        "has_ecn_child": False,
    }


def _inject_change_dates_out_of_order(
    dataset: Dataset, rng: random.Random
) -> dict:
    """Move one approval date before initiation and one close date before approval."""
    # Exclude all ECOs (broader than needed, but simpler) to avoid
    # coordinating with the ECO selected by _inject_eco_closed_without_ecn.
    approval_candidates = [
        change
        for change in dataset.changes
        if change.change_type != "ECO"
        and change.initiated_at
        and change.approved_at
    ]

    close_candidates = [
        change
        for change in dataset.changes
        if change.change_type != "ECO"
        and change.approved_at
        and change.closed_at
    ]

    approval_change = rng.choice(approval_candidates)

    close_candidates = [
        change
        for change in close_candidates
        if change.change_id != approval_change.change_id
    ]
    close_change = rng.choice(close_candidates)

    old_approved_at = approval_change.approved_at
    new_approved_at = (
        date.fromisoformat(approval_change.initiated_at)
        - timedelta(days=3)
    ).isoformat()
    approval_change.approved_at = new_approved_at

    old_closed_at = close_change.closed_at
    new_closed_at = (
        date.fromisoformat(close_change.approved_at)
        - timedelta(days=2)
    ).isoformat()
    close_change.closed_at = new_closed_at

    return {
        "approval_before_initiation": {
            "change_id": approval_change.change_id,
            "previous_approved_at": old_approved_at,
            "injected_approved_at": new_approved_at,
            "initiated_at": approval_change.initiated_at,
        },
        "close_before_approval": {
            "change_id": close_change.change_id,
            "previous_closed_at": old_closed_at,
            "injected_closed_at": new_closed_at,
            "approved_at": close_change.approved_at,
        },
    }


def inject_defects(
    dataset: Dataset, selection: str | list[str] | None, seed: int
) -> dict:
    """Apply the selected defects and return the manifest."""
    enabled = parse_defect_selection(selection)
    rng = random.Random(seed + 104729)
    manifest = {
        "seed": seed,
        "enabled_defects": enabled,
        "defects": {},
    }

    injectors = {
        "cyclic_bom": _inject_cyclic_bom,
        "orphan_parts": _inject_orphan_parts,
        "released_assembly_unreleased_child": _inject_released_assembly_unreleased_child,
        "overlapping_revision_effectivity": _inject_overlapping_revision_effectivity,
        "zero_negative_quantity": _inject_zero_negative_quantity,
        "uom_mismatch": _inject_uom_mismatch,
        "eco_closed_without_ecn": _inject_eco_closed_without_ecn,
        "change_dates_out_of_order": _inject_change_dates_out_of_order,
    }

    zeroed_line_ids: set[str] = set()
    for name in enabled:
        if name == "uom_mismatch":
            records = _inject_uom_mismatch(dataset, rng, zeroed_line_ids)
        else:
            records = injectors[name](dataset, rng)
        manifest["defects"][name] = {
            "description": DEFECT_DESCRIPTIONS[name],
            "records": records,
        }
        if name == "zero_negative_quantity":
            zeroed_line_ids = {
                record["bom_line_id"] for record in records["bom_lines"]
            }

    return manifest
