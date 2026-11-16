"""Entity construction for the synthetic bicycle PLM dataset.

Everything is built from a single ``random.Random(seed)`` instance and fixed
date constants.  No wall-clock time is used anywhere, so the same seed always
produces the same dataset.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from datetime import date, timedelta

BASE_DATE = date(2021, 1, 4)
CHANGE_BASE_DATE = date(2023, 1, 2)

TOTAL_PARTS = 2000
PRODUCT_COUNT = 18
EXTRA_RAW_MATERIALS = 146

FAMILIES = [
    ("F001", "Road"),
    ("F002", "Mountain"),
    ("F003", "City"),
]

FAMILY_CODE = {"F001": "RD", "F002": "MTN", "F003": "CTY"}

PRODUCT_NAMES = {
    "F001": ["Aurora", "Velocity", "Gravel", "Endurance", "Tempo", "Aero"],
    "F002": ["Summit", "Ridge", "Trailblazer", "Boulder", "Crest", "Switchback"],
    "F003": ["Metro", "Voyage", "Commuter", "Urbane", "Breeze", "Transit"],
}

SUBSYSTEMS = ["Frame", "Drivetrain", "Brakes", "Wheels", "Cockpit", "Suspension"]

COMPONENT_NAMES = [
    "Bearing",
    "Axle",
    "Spacer",
    "Bolt Kit",
    "Pulley",
    "Cable",
    "Bracket",
    "Seal",
    "Spring",
    "Hub",
    "Rim",
    "Spoke Set",
    "Chain",
    "Cassette",
    "Derailleur",
    "Brake Pad",
    "Rotor",
    "Lever",
    "Grip",
    "Saddle",
]

MATERIALS = [
    ("6061 Aluminum Tube", "M"),
    ("4130 Steel Tube", "M"),
    ("Carbon Fiber Sheet", "KG"),
    ("Bearing Grease", "KG"),
    ("Brake Cable", "M"),
    ("Stainless Fastener M5", "EA"),
    ("Powder Coat", "KG"),
    ("Rubber Compound", "KG"),
    ("Copper Wire", "M"),
    ("Sealant", "L"),
    ("Alloy Plate", "KG"),
    ("Nylon Resin", "KG"),
]

QUANTITIES = ["1.00", "1.00", "2.00", "2.00", "3.00", "4.00", "0.50", "1.50", "2.50"]

SUPPLIER_PREFIXES = [
    "Apex",
    "Northwind",
    "Precision",
    "Summit",
    "Kinetic",
    "Cascade",
    "Orion",
    "Vector",
    "Pioneer",
    "Titan",
]
SUPPLIER_SUFFIXES = [
    "Metals",
    "Composites",
    "Components",
    "Fasteners",
    "Polymers",
    "Machining",
]
COUNTRIES = [
    "Germany",
    "USA",
    "China",
    "Taiwan",
    "Japan",
    "Vietnam",
    "India",
    "Italy",
    "Netherlands",
    "Spain",
    "Poland",
    "Mexico",
]

ECR_TITLES = [
    "Reduce frame tube wall thickness",
    "Qualify alternate brake lever supplier",
    "Update wheel bearing seal material",
    "Change drivetrain cassette tooth count",
    "Replace painted finish with powder coat",
    "Consolidate cockpit fastener sizes",
    "Improve suspension spring rate",
    "Add torque specification to hub assembly",
    "Revise brake rotor mounting pattern",
    "Substitute alloy plate grade",
]

APPROVER_ROLES = ["engineering", "quality", "manufacturing", "procurement"]

# Plausible weight range in kilograms per part type. Weights are derived from a
# stable hash of the part id rather than the shared random stream so that
# adding the column cannot perturb any pre-existing value.
WEIGHT_RANGES_KG = {
    "raw_material": (0.02, 2.0),
    "component": (0.1, 3.0),
    "assembly": (1.0, 10.0),
}


@dataclass
class Family:
    family_id: str
    family_name: str


@dataclass
class Product:
    product_id: str
    family_id: str
    name: str
    model_year: int
    top_level_part_id: str


@dataclass
class Part:
    part_id: str
    part_number: str
    name: str
    part_type: str
    family_id: str
    uom: str
    lifecycle_state: str
    standard_cost: str
    weight_kg: str
    created_at: str


@dataclass
class PartRevision:
    revision_id: str
    part_id: str
    revision_code: str
    status: str
    effective_from: str
    effective_to: str


@dataclass
class BomLine:
    bom_line_id: str
    parent_part_id: str
    parent_revision_id: str
    child_part_id: str
    child_revision_id: str
    quantity: str
    uom: str
    find_number: str
    effectivity_start: str
    effectivity_end: str


@dataclass
class Change:
    change_id: str
    change_type: str
    parent_change_id: str
    title: str
    status: str
    initiated_at: str
    approved_at: str
    closed_at: str
    affected_part_id: str


@dataclass
class ChangeApproval:
    approval_id: str
    change_id: str
    approver_role: str
    decision: str
    decided_at: str


@dataclass
class Supplier:
    supplier_id: str
    name: str
    country: str


@dataclass
class PartSupplier:
    part_id: str
    supplier_id: str
    unit_price: str
    lead_time_days: int


@dataclass
class ErpBomLine:
    parent_part_number: str
    child_part_number: str
    quantity: str
    uom: str


@dataclass
class Dataset:
    families: list[Family]
    products: list[Product]
    parts: list[Part]
    part_revisions: list[PartRevision]
    boms: list[BomLine]
    changes: list[Change]
    change_approvals: list[ChangeApproval]
    suppliers: list[Supplier]
    part_suppliers: list[PartSupplier]
    erp_bom: list[ErpBomLine] = field(default_factory=list)


def _money(value: float) -> str:
    return f"{value:.2f}"


def _iso(value: date) -> str:
    return value.isoformat()


def _weight_kg(part_id: str, part_type: str) -> str:
    """Deterministic weight in kilograms, independent of the random stream."""
    low, high = WEIGHT_RANGES_KG[part_type]
    digest = hashlib.sha256(f"{part_id}|weight".encode("utf-8")).digest()
    fraction = int.from_bytes(digest[:8], "big") / 2**64
    return f"{low + fraction * (high - low):.3f}"


def build_dataset(seed: int) -> Dataset:
    """Build the full clean dataset for ``seed``."""
    rng = random.Random(seed)

    families = [Family(family_id=fid, family_name=name) for fid, name in FAMILIES]
    products: list[Product] = []
    parts: list[Part] = []
    topology: list[tuple[Part, Part, int, str | None]] = []
    top_part_ids: list[str] = []
    family_shared_materials: dict[str, list[Part]] = {
        family.family_id: [] for family in families
    }
    shared_raw_ids: list[str] = []

    part_seq = 0

    def new_part(
        family_id: str,
        name: str,
        part_type: str,
        uom: str,
        cost_lo: float,
        cost_hi: float,
    ) -> Part:
        nonlocal part_seq
        part_seq += 1
        if part_seq > TOTAL_PARTS:
            raise RuntimeError("part budget exceeded")
        created = BASE_DATE + timedelta(days=rng.randrange(0, 1100))
        part_id = f"PART-{part_seq:04d}"
        part = Part(
            part_id=part_id,
            part_number=f"PN-{FAMILY_CODE[family_id]}-{part_seq:05d}",
            name=name,
            part_type=part_type,
            family_id=family_id,
            uom=uom,
            lifecycle_state="released",
            standard_cost=_money(rng.uniform(cost_lo, cost_hi)),
            weight_kg=_weight_kg(part_id, part_type),
            created_at=_iso(created),
        )
        parts.append(part)
        return part

    # ------------------------------------------------------------------
    # Product trees: 18 products x 103 parts, plus 146 shared-ish raw
    # materials attached to existing components.  1854 + 146 = 2000.
    # ------------------------------------------------------------------
    all_l4_parts: list[Part] = []

    for product_index in range(PRODUCT_COUNT):
        family = families[product_index // 6]
        family_id = family.family_id
        base_name = PRODUCT_NAMES[family_id][product_index % 6]
        model_year = 2022 + (product_index % 3)
        product_name = f"{base_name} {model_year}"

        top = new_part(
            family_id,
            f"{product_name} Frame Assembly",
            "assembly",
            "EA",
            260.0,
            520.0,
        )
        top_part_ids.append(top.part_id)

        level1: list[Part] = []
        for j in range(3):
            subsystem = SUBSYSTEMS[(product_index + j) % len(SUBSYSTEMS)]
            level1.append(
                new_part(
                    family_id,
                    f"{product_name} {subsystem} Subassembly",
                    "assembly",
                    "EA",
                    70.0,
                    210.0,
                )
            )

        level2: list[Part] = []
        for parent in level1:
            for k in range(3):
                level2.append(
                    new_part(
                        family_id,
                        f"{parent.name} Subassembly {k + 1}",
                        "assembly",
                        "EA",
                        35.0,
                        110.0,
                    )
                )

        level3: list[Part] = []
        for parent in level2:
            for k in range(2):
                level3.append(
                    new_part(
                        family_id,
                        f"{parent.name} Module {k + 1}",
                        "assembly",
                        "EA",
                        15.0,
                        55.0,
                    )
                )

        level4: list[Part] = []
        component_offset = product_index * 7
        for parent in level3:
            for k in range(2):
                component_name = COMPONENT_NAMES[
                    (component_offset + len(level4)) % len(COMPONENT_NAMES)
                ]
                level4.append(
                    new_part(
                        family_id,
                        f"{component_name} for {parent.name}",
                        "component",
                        "EA",
                        2.0,
                        85.0,
                    )
                )
        all_l4_parts.extend(level4)

        level5: list[Part] = []
        material_offset = product_index * 5
        for idx, parent in enumerate(level4):
            material_name, material_uom = MATERIALS[
                (material_offset + idx) % len(MATERIALS)
            ]
            level5.append(
                new_part(
                    family_id,
                    f"{material_name} for {parent.name}",
                    "raw_material",
                    material_uom,
                    0.50,
                    32.0,
                )
            )

        for j, child in enumerate(level1):
            topology.append((top, child, 10 * (j + 1), None))
        for j, parent in enumerate(level1):
            for k, child in enumerate(level2[j * 3 : (j + 1) * 3]):
                topology.append((parent, child, 10 * (k + 1), None))
        for j, parent in enumerate(level2):
            for k, child in enumerate(level3[j * 2 : (j + 1) * 2]):
                topology.append((parent, child, 10 * (k + 1), None))
        for j, parent in enumerate(level3):
            for k, child in enumerate(level4[j * 2 : (j + 1) * 2]):
                topology.append((parent, child, 10 * (k + 1), None))
        for j, parent in enumerate(level4):
            topology.append((parent, level5[j], 10, None))

        # The first product in each family contributes its first three
        # level-5 raw materials as family-wide shared materials. Every other
        # product links three distinct level-4 components to them, making
        # those raw materials reachable from all six products in the family.
        if product_index % 6 == 0:
            family_shared_materials[family_id] = level5[:3]
            shared_raw_ids.extend(material.part_id for material in level5[:3])
        else:
            for material_index, shared_material in enumerate(
                family_shared_materials[family_id]
            ):
                topology.append(
                    (
                        level4[material_index],
                        shared_material,
                        30 + 10 * material_index,
                        "20" if material_index == 1 else "10",
                    )
                )

        products.append(
            Product(
                product_id=f"PRD-{product_index + 1:03d}",
                family_id=family_id,
                name=product_name,
                model_year=model_year,
                top_level_part_id=top.part_id,
            )
        )

    # Extra raw materials, each attached to a different existing component.
    # Components are spread evenly across all products so the extra parts do
    # not skew the family distribution.
    for extra_index in range(EXTRA_RAW_MATERIALS):
        component_index = (
            extra_index * len(all_l4_parts)
        ) // EXTRA_RAW_MATERIALS
        component = all_l4_parts[component_index]
        material_name, material_uom = MATERIALS[
            (extra_index * 3) % len(MATERIALS)
        ]
        raw = new_part(
            component.family_id,
            f"{material_name} Grade {extra_index + 1}",
            "raw_material",
            material_uom,
            0.50,
            32.0,
        )
        topology.append((component, raw, 20, None))

    if len(parts) != TOTAL_PARTS:
        raise RuntimeError(f"expected {TOTAL_PARTS} parts, got {len(parts)}")

    # ------------------------------------------------------------------
    # Revisions: every part has a released base revision.  Some parts get
    # an older obsolete revision, some get a future in-work revision.
    # ------------------------------------------------------------------
    revisions: list[PartRevision] = []
    base_revision: dict[str, str] = {}
    base_effective_from: dict[str, str] = {}
    revision_seq = 0

    def new_revision(
        part_id: str,
        code: str,
        status: str,
        effective_from: date,
        effective_to: date | None,
    ) -> PartRevision:
        nonlocal revision_seq
        revision_seq += 1
        revision = PartRevision(
            revision_id=f"REV-{revision_seq:05d}",
            part_id=part_id,
            revision_code=code,
            status=status,
            effective_from=_iso(effective_from),
            effective_to=_iso(effective_to) if effective_to else "",
        )
        revisions.append(revision)
        return revision

    for part in parts:
        part_created = date.fromisoformat(part.created_at)
        base_from = part_created + timedelta(days=rng.randrange(30, 180))
        next_code = ord("A")

        if rng.random() < 0.10:
            new_revision(
                part.part_id,
                chr(next_code),
                "obsolete",
                base_from - timedelta(days=365),
                base_from - timedelta(days=1),
            )
            next_code += 1

        base = new_revision(
            part.part_id,
            chr(next_code),
            "released",
            base_from,
            None,
        )
        base_revision[part.part_id] = base.revision_id
        base_effective_from[part.part_id] = base.effective_from
        next_code += 1

        if rng.random() < 0.15:
            new_revision(
                part.part_id,
                chr(next_code),
                "in_work",
                base_from + timedelta(days=rng.randrange(180, 540)),
                None,
            )
            part.lifecycle_state = "draft"

    # ------------------------------------------------------------------
    # BOM lines use the released base revision on both ends.
    # ------------------------------------------------------------------
    boms: list[BomLine] = []
    for line_index, (
        parent,
        child,
        find_number,
        quantity_override,
    ) in enumerate(topology, start=1):
        quantity = (
            quantity_override
            if quantity_override is not None
            else rng.choice(QUANTITIES)
        )
        boms.append(
            BomLine(
                bom_line_id=f"BOM-{line_index:06d}",
                parent_part_id=parent.part_id,
                parent_revision_id=base_revision[parent.part_id],
                child_part_id=child.part_id,
                child_revision_id=base_revision[child.part_id],
                quantity=quantity,
                uom=child.uom,
                find_number=f"{find_number}",
                effectivity_start=base_effective_from[parent.part_id],
                effectivity_end="",
            )
        )

    # ------------------------------------------------------------------
    # ECR -> ECO -> ECN change control.
    # ------------------------------------------------------------------
    changes: list[Change] = []
    ecrs: list[Change] = []
    affected_part_ids = [part.part_id for part in parts]

    if len(shared_raw_ids) != 9:
        raise RuntimeError(
            f"expected 9 family-shared raw materials, got {len(shared_raw_ids)}"
        )

    for i in range(40):
        initiated = CHANGE_BASE_DATE + timedelta(days=i * 6)
        status = ["closed", "approved", "open", "rejected"][i % 4]
        approved = initiated + timedelta(days=2) if status in ("closed", "approved") else None
        closed = initiated + timedelta(days=9) if status == "closed" else None
        # Every third ECR targets a family-shared raw material, so its ECO and
        # ECN children inherit an affected part reachable from several
        # products. The remaining ECRs draw from the full part list.
        affected_part_id = (
            rng.choice(shared_raw_ids)
            if i % 3 == 0
            else rng.choice(affected_part_ids)
        )
        ecr = Change(
            change_id=f"ECR-{i + 1:04d}",
            change_type="ECR",
            parent_change_id="",
            title=f"{ECR_TITLES[i % len(ECR_TITLES)]} ({i + 1})",
            status=status,
            initiated_at=_iso(initiated),
            approved_at=_iso(approved) if approved else "",
            closed_at=_iso(closed) if closed else "",
            affected_part_id=affected_part_id,
        )
        ecrs.append(ecr)
        changes.append(ecr)

    eco_candidates = [ecr for ecr in ecrs if ecr.status in ("approved", "closed")]

    for eco_index, ecr in enumerate(eco_candidates):
        initiated = date.fromisoformat(
            ecr.approved_at or ecr.initiated_at
        ) + timedelta(days=4)
        if eco_index < 15:
            status = "closed" if eco_index < 12 else "approved"
            approved = initiated + timedelta(days=5)
            closed = initiated + timedelta(days=25) if status == "closed" else None
        else:
            status = "approved" if eco_index < 18 else "open"
            approved = initiated + timedelta(days=5) if status == "approved" else None
            closed = None

        eco = Change(
            change_id=f"ECO-{eco_index + 1:04d}",
            change_type="ECO",
            parent_change_id=ecr.change_id,
            title=f"Implement: {ecr.title}",
            status=status,
            initiated_at=_iso(initiated),
            approved_at=_iso(approved) if approved else "",
            closed_at=_iso(closed) if closed else "",
            affected_part_id=ecr.affected_part_id,
        )
        changes.append(eco)

        if eco_index < 15:
            ecn_initiated = (approved or initiated) + timedelta(days=3)
            ecn_status = "closed" if status == "closed" else "approved"
            ecn_approved = ecn_initiated + timedelta(days=2)
            ecn_closed = ecn_initiated + timedelta(days=7) if ecn_status == "closed" else None
            ecn = Change(
                change_id=f"ECN-{eco_index + 1:04d}",
                change_type="ECN",
                parent_change_id=eco.change_id,
                title=f"Release change: {eco.title}",
                status=ecn_status,
                initiated_at=_iso(ecn_initiated),
                approved_at=_iso(ecn_approved),
                closed_at=_iso(ecn_closed) if ecn_closed else "",
                affected_part_id=eco.affected_part_id,
            )
            changes.append(ecn)

    # One or two completed approval rows per change.
    approvals: list[ChangeApproval] = []
    approval_seq = 0
    for change_index, change in enumerate(changes):
        initiated = date.fromisoformat(change.initiated_at)
        for k in range(2):
            approval_seq += 1
            role = APPROVER_ROLES[(change_index + k) % len(APPROVER_ROLES)]
            if change.status == "rejected":
                decision = "rejected"
                decided = initiated + timedelta(days=1 + k)
            elif change.status == "open":
                decision = "pending"
                decided = None
            else:
                decision = "approved"
                decided = initiated + timedelta(days=1 + k)
            approvals.append(
                ChangeApproval(
                    approval_id=f"APR-{approval_seq:05d}",
                    change_id=change.change_id,
                    approver_role=role,
                    decision=decision,
                    decided_at=_iso(decided) if decided else "",
                )
            )

    # ------------------------------------------------------------------
    # Suppliers and sourced parts.
    # ------------------------------------------------------------------
    suppliers: list[Supplier] = []
    for i in range(40):
        supplier_name = (
            f"{SUPPLIER_PREFIXES[i // len(SUPPLIER_SUFFIXES)]} "
            f"{SUPPLIER_SUFFIXES[i % len(SUPPLIER_SUFFIXES)]}"
        )
        suppliers.append(
            Supplier(
                supplier_id=f"SUP-{i + 1:03d}",
                name=supplier_name,
                country=COUNTRIES[i % len(COUNTRIES)],
            )
        )

    supplier_ids = [supplier.supplier_id for supplier in suppliers]
    part_suppliers: list[PartSupplier] = []
    for idx, part in enumerate(parts):
        source_count = 1
        if idx % 3 == 0:
            source_count += 1
        if idx % 11 == 0:
            source_count += 1
        for supplier_id in rng.sample(supplier_ids, source_count):
            unit_price = float(part.standard_cost) * rng.uniform(0.65, 1.15)
            part_suppliers.append(
                PartSupplier(
                    part_id=part.part_id,
                    supplier_id=supplier_id,
                    unit_price=_money(unit_price),
                    lead_time_days=rng.randrange(3, 91),
                )
            )

    return Dataset(
        families=families,
        products=products,
        parts=parts,
        part_revisions=revisions,
        boms=boms,
        changes=changes,
        change_approvals=approvals,
        suppliers=suppliers,
        part_suppliers=part_suppliers,
    )


def build_erp_bom(dataset: Dataset) -> list[ErpBomLine]:
    """Derive the synthetic ERP mBOM extract from the current BOM lines."""
    part_number = {part.part_id: part.part_number for part in dataset.parts}
    return [
        ErpBomLine(
            parent_part_number=part_number[line.parent_part_id],
            child_part_number=part_number[line.child_part_id],
            quantity=line.quantity,
            uom=line.uom,
        )
        for line in dataset.boms
    ]
