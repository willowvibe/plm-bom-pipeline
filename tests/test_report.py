"""The renderer must work on a plain dictionary, without DuckDB."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from report.build_report import render_report  # noqa: E402


def _fake_metrics():
    shared_parts = [
        {
            "part_id": f"PART-{index:04d}",
            "part_name": f"Shared raw material {index}",
            "part_type": "raw_material",
            "product_count": 6,
            "direct_parent_count": 6,
            "total_direct_quantity": 50.0 + index,
        }
        for index in range(1, 7)
    ]
    top_changes = [
        {
            "change_id": f"ECN-{index:04d}",
            "change_type": "ecn",
            "status": "closed",
            "title": f"Release change {index}",
            "affected_part_id": "PART-0069",
            "product_count": 6,
        }
        for index in range(1, 7)
    ]
    defects = [
        {
            "name": name,
            "label": label,
            "test": test_name,
            "description": f"Seeded {label.lower()} description.",
            "seeded_label": "1 line",
        }
        for name, label, test_name in (
            ("cyclic_bom", "Cyclic BOM", "assert_no_cyclic_bom"),
            ("orphan_parts", "Orphan parts", "assert_no_orphan_parts"),
            (
                "released_assembly_unreleased_child",
                "Released assembly with unreleased child",
                "assert_no_released_assembly_unreleased_child",
            ),
            (
                "overlapping_revision_effectivity",
                "Overlapping revision effectivity",
                "assert_no_overlapping_revision_effectivity",
            ),
            (
                "zero_negative_quantity",
                "Zero or negative quantity",
                "assert_no_zero_or_negative_quantity",
            ),
            ("uom_mismatch", "UoM mismatch", "assert_no_uom_mismatch"),
            (
                "eco_closed_without_ecn",
                "Closed ECO without ECN",
                "assert_no_eco_closed_without_ecn",
            ),
        )
    ]
    return {
        "seed": 42,
        "as_of_date": "2026-06-01",
        "counts": {
            "products": 18,
            "parts": 2000,
            "bom_lines": 2027,
            "changes": 75,
            "erp_lines": 2027,
        },
        "bom": {
            "explosion_rows": 2045,
            "levels": [
                {"level": 0, "count": 18},
                {"level": 1, "count": 54},
                {"level": 2, "count": 162},
                {"level": 3, "count": 324},
                {"level": 4, "count": 648},
                {"level": 5, "count": 839},
            ],
            "max_depth": 5,
            "leaf_rows": 1487,
        },
        "products": [
            {
                "product_name": "<script>alert('xss')</script> Trail 2024",
                "family_name": "Road",
                "total_cost": 128774.6125,
                "total_weight_kg": 4521.8093,
                "bom_line_count": 113,
                "max_depth": 5,
            },
            {
                "product_name": "Switchback 2024",
                "family_name": "Mountain",
                "total_cost": 104674.3363,
                "total_weight_kg": 5400.3578,
                "bom_line_count": 113,
                "max_depth": 5,
            },
        ],
        "cycle": {
            "status_counts": {
                "approved": 19,
                "closed": 34,
                "open": 12,
                "rejected": 10,
            },
            "median_days_to_approval": 2.0,
            "average_days_to_approval": 3.018867924528302,
            "median_days_to_close": 9.0,
            "average_days_to_close": 13.941176470588236,
        },
        "impact": {
            "total_pairs": 205,
            "changes_with_impact": 75,
            "changes_over_one": 26,
            "max_products": 6,
            "example": {
                "change_id": "ECN-0001",
                "change_type": "ecn",
                "status": "closed",
                "title": "Release change: Implement: Reduce frame tube wall thickness (1)",
                "affected_part_id": "PART-0069",
                "product_names": [
                    "Aero 2024",
                    "Aurora 2022",
                    "Endurance 2022",
                    "Gravel 2024",
                    "Tempo 2023",
                    "Velocity 2023",
                ],
            },
            "top_changes": top_changes,
        },
        "reuse": {
            "shared_count": 9,
            "max_product_count": 6,
            "shared_parts": shared_parts,
        },
        "reconciliation": {"status_counts": {"match": 2027}, "total": 2027},
        "quality": {
            "total_nodes": 195,
            "passed": 195,
            "failures": 0,
            "errors": 0,
            "skipped": 0,
            "model_nodes": 20,
            "test_nodes": 174,
            "unit_test_nodes": 1,
        },
        "defects": defects,
    }


def test_render_report_from_fake_metrics():
    rendered = render_report(_fake_metrics())

    assert "{{" not in rendered
    assert "${" not in rendered
    assert "$" not in rendered
    assert "<script" not in rendered
    assert "&lt;script&gt;" in rendered

    headings = (
        "From PLM exports to tested BOM intelligence",
        "BOM structure",
        "Change control",
        "Change impact",
        "Part reuse",
        "Data quality",
        "PLM ↔ ERP reconciliation",
    )
    for heading in headings:
        assert heading in rendered

    for value in (
        "2,000",
        "2,027",
        "2,045",
        "205",
        "26",
        "195/195",
        "188/188",
        "2,027/2,027",
        "ECN-0001",
        "PART-0069",
        "assert_no_cyclic_bom",
        "72.7%",
    ):
        assert value in rendered

    assert rendered.count('class="defect-card"') == 7
    assert rendered.count('class="chip"') == 6
    assert "0 violations on clean" in rendered

    assert "<link" not in rendered
    assert "<img" not in rendered
    assert "http://" not in rendered
    assert "https://" not in rendered
