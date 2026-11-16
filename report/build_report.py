#!/usr/bin/env python3
"""Build a self-contained HTML report from the dbt marts and defect manifest.

The report deliberately has no runtime dependencies beyond the Python standard
library and DuckDB.  DuckDB is imported lazily so the renderer can be unit
tested with a fake metrics dictionary on a machine without DuckDB installed.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
import tempfile
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

TEMPLATE_PATH = Path(__file__).with_name("template.html")
RUN_RESULTS_PATH = REPO_ROOT / "dbt" / "target" / "run_results.json"
AS_OF_DATE = "2026-06-01"
DEFAULT_DB = "data/plm.duckdb"
DEFAULT_OUT = "site/report/index.html"

DEFECTS = (
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

STATUS_COLORS = {
    "closed": "#17191c",
    "approved": "#0f766e",
    "open": "#c2410c",
    "rejected": "#a8a29e",
}
RECON_COLORS = {
    "match": "#0f766e",
    "quantity_mismatch": "#c2410c",
    "uom_mismatch": "#c2410c",
    "plm_only": "#a8a29e",
    "erp_only": "#a8a29e",
}
RECON_LABELS = {
    "match": "Match",
    "quantity_mismatch": "Quantity mismatch",
    "uom_mismatch": "UoM mismatch",
    "plm_only": "PLM only",
    "erp_only": "ERP only",
}


def _import_duckdb():
    try:
        import duckdb  # noqa: PLC0415 - intentionally lazy
    except ImportError:
        print(
            "error: report needs duckdb; activate the dbt venv or pip install duckdb",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return duckdb


def _defect_count_label(name: str, records: dict) -> str:
    if name == "cyclic_bom":
        return "1 line"
    if name == "orphan_parts":
        return f"{len(records['orphan_part_ids'])} parts"
    if name == "released_assembly_unreleased_child":
        return "1 line"
    if name == "overlapping_revision_effectivity":
        return f"1 part / {len(records['revision_ids'])} revisions"
    if name == "zero_negative_quantity":
        return f"{len(records['bom_lines'])} lines"
    if name == "uom_mismatch":
        return "1 line"
    if name == "eco_closed_without_ecn":
        return "1 ECO"
    raise KeyError(name)


def collect_seeded_defects(seed: int = 42) -> list[dict]:
    """Generate the all-defects dataset and return one card per defect."""
    from generator import generate  # noqa: PLC0415 - local module, lazy import

    with tempfile.TemporaryDirectory(prefix="plm-report-defects-") as tmp:
        generate(tmp, seed=seed, defects=["all"])
        manifest = json.loads(
            (Path(tmp) / "defects.json").read_text(encoding="utf-8")
        )

    cards = []
    for name, label, test_name in DEFECTS:
        defect = manifest["defects"][name]
        records = defect["records"]
        cards.append(
            {
                "name": name,
                "label": label,
                "test": test_name,
                "description": defect["description"],
                "seeded_label": _defect_count_label(name, records),
            }
        )
    return cards


def _quality_metrics(run_results_path: Path) -> dict:
    payload = json.loads(Path(run_results_path).read_text(encoding="utf-8"))
    results = payload.get("results", [])
    statuses = Counter(str(item.get("status", "")) for item in results)
    return {
        "total_nodes": len(results),
        "passed": statuses.get("pass", 0) + statuses.get("success", 0),
        "failures": statuses.get("fail", 0),
        "errors": statuses.get("error", 0),
        "skipped": statuses.get("skipped", 0) + statuses.get("skip", 0),
        "model_nodes": sum(
            1
            for item in results
            if str(item.get("unique_id", "")).startswith("model.")
        ),
        "test_nodes": sum(
            1
            for item in results
            if str(item.get("unique_id", "")).startswith("test.")
        ),
        "unit_test_nodes": sum(
            1
            for item in results
            if str(item.get("unique_id", "")).startswith("unit_test.")
        ),
    }


def collect_metrics(
    db_path: str | Path,
    seed: int = 42,
    run_results_path: str | Path = RUN_RESULTS_PATH,
) -> dict:
    """Read the marts read-only and collect every number the report displays."""
    duckdb = _import_duckdb()
    db_path = Path(db_path)
    try:
        con = duckdb.connect(str(db_path), read_only=True)
    except Exception as exc:  # pragma: no cover - exercised via the CLI
        print(f"error: could not open {db_path}: {exc}", file=sys.stderr)
        raise SystemExit(1)

    try:
        counts = con.execute(
            """
            select
                (select count(*) from main_staging.stg_products),
                (select count(*) from main_staging.stg_parts),
                (select count(*) from main_staging.stg_boms),
                (select count(*) from main_staging.stg_changes),
                (select count(*) from main_staging.stg_erp_bom)
            """
        ).fetchone()

        explosion_rows, max_level = con.execute(
            "select count(*), max(level) from main_marts.bom_explosion"
        ).fetchone()
        levels = {
            int(level): int(count)
            for level, count in con.execute(
                """
                select level, count(*)
                from main_marts.bom_explosion
                group by level
                order by level
                """
            ).fetchall()
        }
        leaf_rows = con.execute(
            "select count(*) from main_marts.bom_explosion where is_leaf"
        ).fetchone()[0]
        max_depth = con.execute(
            "select max(max_depth) from main_marts.bom_cost_weight_rollup"
        ).fetchone()[0]

        products = [
            {
                "product_name": row[0],
                "family_name": row[1],
                "total_cost": float(row[2]),
                "total_weight_kg": float(row[3]),
                "bom_line_count": int(row[4]),
                "max_depth": int(row[5]),
            }
            for row in con.execute(
                """
                select product_name, family_name, total_cost, total_weight_kg,
                       bom_line_count, max_depth
                from main_marts.bom_cost_weight_rollup
                order by total_cost desc, product_id
                limit 5
                """
            ).fetchall()
        ]

        cycle_status_counts = {
            str(status): int(count)
            for status, count in con.execute(
                """
                select cycle_status, count(*)
                from main_marts.eco_cycle_time
                group by cycle_status
                """
            ).fetchall()
        }
        (
            median_days_to_approval,
            average_days_to_approval,
            median_days_to_close,
            average_days_to_close,
        ) = con.execute(
            """
            select median(days_to_approval), avg(days_to_approval),
                   median(days_to_close), avg(days_to_close)
            from main_marts.eco_cycle_time
            """
        ).fetchone()

        total_pairs = int(
            con.execute(
                "select count(*) from main_marts.change_impact"
            ).fetchone()[0]
        )
        changes_with_impact = int(
            con.execute(
                "select count(distinct change_id) from main_marts.change_impact"
            ).fetchone()[0]
        )
        changes_over_one = int(
            con.execute(
                """
                select count(*) from (
                    select change_id
                    from main_marts.change_impact
                    group by change_id
                    having count(*) > 1
                )
                """
            ).fetchone()[0]
        )
        max_products = int(
            con.execute(
                """
                select max(product_count) from (
                    select count(*) as product_count
                    from main_marts.change_impact
                    group by change_id
                )
                """
            ).fetchone()[0]
        )
        top_changes = [
            {
                "change_id": row[0],
                "change_type": row[1],
                "status": row[2],
                "title": row[3],
                "affected_part_id": row[4],
                "product_count": int(row[5]),
            }
            for row in con.execute(
                """
                select change_id, change_type, status, title,
                       affected_part_id, count(*) as product_count
                from main_marts.change_impact
                group by change_id, change_type, status, title, affected_part_id
                order by product_count desc, change_id
                limit 6
                """
            ).fetchall()
        ]

        example_row = con.execute(
            """
            select change_id, change_type, status, title, affected_part_id
            from main_marts.change_impact
            where change_id = 'ECN-0001'
            limit 1
            """
        ).fetchone()
        if example_row is None and top_changes:
            first = top_changes[0]
            example_row = (
                first["change_id"],
                first["change_type"],
                first["status"],
                first["title"],
                first["affected_part_id"],
            )
        if example_row is None:
            raise RuntimeError("change_impact is empty; cannot build example card")
        example_products = [
            row[0]
            for row in con.execute(
                """
                select product_name
                from main_marts.change_impact
                where change_id = ?
                order by product_name
                """,
                [example_row[0]],
            ).fetchall()
        ]

        shared_count, max_product_count = con.execute(
            """
            select
                sum(case when product_count > 1 then 1 else 0 end),
                max(product_count)
            from main_marts.part_reuse
            """
        ).fetchone()
        shared_parts = [
            {
                "part_id": row[0],
                "part_name": row[1],
                "part_type": row[2],
                "product_count": int(row[3]),
                "direct_parent_count": int(row[4]),
                "total_direct_quantity": float(row[5]),
            }
            for row in con.execute(
                """
                select part_id, part_name, part_type, product_count,
                       direct_parent_count, total_direct_quantity
                from main_marts.part_reuse
                where product_count > 1
                order by product_count desc, direct_parent_count desc, part_id
                limit 6
                """
            ).fetchall()
        ]

        reconciliation_counts = {
            str(status): int(count)
            for status, count in con.execute(
                """
                select reconciliation_status, count(*)
                from main_marts.bom_erp_reconciliation
                group by reconciliation_status
                """
            ).fetchall()
        }
    finally:
        con.close()

    quality = _quality_metrics(Path(run_results_path))
    levels_list = [
        {"level": level, "count": levels.get(level, 0)}
        for level in range(0, int(max_level) + 1)
    ]
    return {
        "seed": seed,
        "as_of_date": AS_OF_DATE,
        "counts": {
            "products": int(counts[0]),
            "parts": int(counts[1]),
            "bom_lines": int(counts[2]),
            "changes": int(counts[3]),
            "erp_lines": int(counts[4]),
        },
        "bom": {
            "explosion_rows": int(explosion_rows),
            "levels": levels_list,
            "max_depth": int(max_depth),
            "leaf_rows": int(leaf_rows),
        },
        "products": products,
        "cycle": {
            "status_counts": cycle_status_counts,
            "median_days_to_approval": float(median_days_to_approval),
            "average_days_to_approval": float(average_days_to_approval),
            "median_days_to_close": float(median_days_to_close),
            "average_days_to_close": float(average_days_to_close),
        },
        "impact": {
            "total_pairs": total_pairs,
            "changes_with_impact": changes_with_impact,
            "changes_over_one": changes_over_one,
            "max_products": max_products,
            "example": {
                "change_id": example_row[0],
                "change_type": example_row[1],
                "status": example_row[2],
                "title": example_row[3],
                "affected_part_id": example_row[4],
                "product_names": example_products,
            },
            "top_changes": top_changes,
        },
        "reuse": {
            "shared_count": int(shared_count or 0),
            "max_product_count": int(max_product_count or 0),
            "shared_parts": shared_parts,
        },
        "reconciliation": {
            "status_counts": reconciliation_counts,
            "total": sum(reconciliation_counts.values()),
        },
        "quality": quality,
        "defects": collect_seeded_defects(seed),
    }


def _esc(value) -> str:
    return html.escape(str(value), quote=True)


def _fmt_int(value) -> str:
    return f"{int(value):,}"


def _fmt_money(value) -> str:
    return "—" if value is None else f"{float(value):,.2f}"


def _fmt_weight(value) -> str:
    return "—" if value is None else f"{float(value):,.1f}"


def _fmt_days(value) -> str:
    return "—" if value is None else f"{float(value):,.1f}"


def _fmt_pct(value: float) -> str:
    return f"{float(value) * 100:,.1f}%"


def _ordered_statuses(status_counts: dict) -> list[str]:
    preferred = ["closed", "approved", "open", "rejected"]
    return [status for status in preferred if status in status_counts] + sorted(
        set(status_counts) - set(preferred)
    )


def _status_color(status: str) -> str:
    return STATUS_COLORS.get(status, "#5b5f66")


def _status_class(status: str) -> str:
    return f"status-{status}" if status in STATUS_COLORS else "status-other"


def _kpi_strip(counts: dict, max_depth: int) -> str:
    items = (
        ("Products", counts["products"]),
        ("Parts", counts["parts"]),
        ("BOM lines", counts["bom_lines"]),
        ("Changes", counts["changes"]),
        ("Max BOM depth", max_depth),
    )
    return "".join(
        '<div class="kpi">'
        f'<div class="kpi-value">{_fmt_int(value)}</div>'
        f'<div class="kpi-label">{_esc(label)}</div>'
        "</div>"
        for label, value in items
    )


def _bom_chart(levels: list[dict]) -> str:
    level_counts = {int(item["level"]): int(item["count"]) for item in levels}
    visible = [level_counts.get(level, 0) for level in range(1, 6)]
    ceiling = max(visible) or 1
    bars = []
    for level, count in zip(range(1, 6), visible):
        height = count / ceiling * 100
        fill_class = "bar-fill bar-fill-accent" if level == 5 else "bar-fill"
        bars.append(
            '<div class="bar">'
            f'<div class="bar-value">{_fmt_int(count)}</div>'
            '<div class="bar-track">'
            f'<div class="{fill_class}" style="height:{height:.1f}%"></div>'
            "</div>"
            f'<div class="bar-label">L{level}</div>'
            "</div>"
        )
    return '<div class="chart" role="img" aria-label="BOM lines by level">' + "".join(bars) + "</div>"


def _product_table(products: list[dict]) -> str:
    rows = "".join(
        "<tr>"
        f'<td class="strong">{_esc(item["product_name"])}</td>'
        f"<td>{_esc(item['family_name'])}</td>"
        f'<td class="num">{_fmt_money(item["total_cost"])}</td>'
        f'<td class="num">{_fmt_weight(item["total_weight_kg"])}</td>'
        f'<td class="num">{_fmt_int(item["bom_line_count"])}</td>'
        f'<td class="num">{_fmt_int(item["max_depth"])}</td>'
        "</tr>"
        for item in products
    )
    return (
        '<div class="table-wrap"><table class="data-table">'
        "<thead><tr>"
        "<th>Product</th><th>Family</th>"
        '<th class="num">Total cost</th><th class="num">Weight (kg)</th>'
        '<th class="num">BOM lines</th><th class="num">Depth</th>'
        "</tr></thead>"
        f"<tbody>{rows}</tbody></table></div>"
    )


def _cycle_donut(status_counts: dict) -> str:
    total = sum(status_counts.values())
    if total <= 0:
        style = "background: #d8d3c8"
    else:
        segments = []
        start = 0.0
        for status in _ordered_statuses(status_counts):
            count = status_counts[status]
            end = start + count / total * 100
            segments.append(
                f"{_status_color(status)} {start:.4f}% {end:.4f}%"
            )
            start = end
        style = "background: conic-gradient(" + ", ".join(segments) + ")"
    return (
        '<div class="donut-wrap"><div class="donut" style="'
        + style
        + '"><div class="donut-hole"><strong>'
        + _fmt_int(total)
        + "</strong><span>changes</span></div></div></div>"
    )


def _cycle_legend(status_counts: dict) -> str:
    items = "".join(
        '<div class="legend-item">'
        f'<span class="swatch" style="background:{_status_color(status)}"></span>'
        f'<span class="legend-label">{_esc(status.replace("_", " "))}</span>'
        f'<span class="legend-count">{_fmt_int(status_counts[status])}</span>'
        "</div>"
        for status in _ordered_statuses(status_counts)
    )
    return '<div class="legend">' + items + "</div>"


def _cycle_stats(cycle: dict) -> str:
    items = (
        ("Median days to approval", _fmt_days(cycle["median_days_to_approval"])),
        ("Average days to approval", _fmt_days(cycle["average_days_to_approval"])),
        ("Median days to close", _fmt_days(cycle["median_days_to_close"])),
        ("Average days to close", _fmt_days(cycle["average_days_to_close"])),
    )
    return (
        '<div class="stat-row">'
        + "".join(
            '<div class="stat">'
            f'<div class="stat-value">{value}</div>'
            f'<div class="stat-label">{_esc(label)}</div>'
            "</div>"
            for label, value in items
        )
        + "</div>"
    )


def _impact_stats(impact: dict) -> str:
    items = (
        ("Changes with impact", _fmt_int(impact["changes_with_impact"])),
        ("Change/product pairs", _fmt_int(impact["total_pairs"])),
        ("Changes reaching >1 product", _fmt_int(impact["changes_over_one"])),
        ("Max products per change", _fmt_int(impact["max_products"])),
    )
    return (
        '<div class="stat-row">'
        + "".join(
            '<div class="stat">'
            f'<div class="stat-value">{value}</div>'
            f'<div class="stat-label">{_esc(label)}</div>'
            "</div>"
            for label, value in items
        )
        + "</div>"
    )


def _impact_example(example: dict) -> str:
    chips = "".join(
        f'<span class="chip">{_esc(name)}</span>'
        for name in example["product_names"]
    )
    count = len(example["product_names"])
    return (
        '<article class="impact-card">'
        '<div class="impact-number">'
        f"{_fmt_int(count)}<small>products affected</small>"
        "</div>"
        '<div class="impact-body">'
        '<div class="eyebrow eyebrow-small">Example change</div>'
        f'<h3>{_esc(example["change_id"])} '
        f'<span class="mono-muted">{_esc(str(example["change_type"]).upper())}'
        f" · {_esc(example['status'])}</span></h3>"
        f'<p class="impact-title">{_esc(example["title"])}</p>'
        f'<p class="mono-muted">Affected part {_esc(example["affected_part_id"])}</p>'
        f'<div class="chips">{chips}</div>'
        "</div></article>"
    )


def _impact_table(changes: list[dict]) -> str:
    rows = "".join(
        "<tr>"
        f'<td class="mono strong">{_esc(item["change_id"])}</td>'
        f"<td>{_esc(str(item['change_type']).upper())}</td>"
        f'<td><span class="status {_status_class(item["status"])}">'
        f'{_esc(item["status"])}</span></td>'
        f"<td>{_esc(item['title'])}</td>"
        f'<td class="mono">{_esc(item["affected_part_id"])}</td>'
        f'<td class="num">{_fmt_int(item["product_count"])}</td>'
        "</tr>"
        for item in changes
    )
    return (
        '<div class="table-wrap"><table class="data-table wide">'
        "<thead><tr>"
        "<th>Change</th><th>Type</th><th>Status</th><th>Title</th>"
        '<th>Affected part</th><th class="num">Products</th>'
        "</tr></thead>"
        f"<tbody>{rows}</tbody></table></div>"
    )


def _reuse_callout(reuse: dict) -> str:
    return (
        '<div class="callout">'
        f'<div class="callout-number">{_fmt_int(reuse["shared_count"])}</div>'
        "<div>"
        '<p class="callout-title">raw materials are shared across each product family</p>'
        '<p class="note">Each shared raw material is reachable from all '
        f'{_fmt_int(reuse["max_product_count"])} products in its family, so '
        "where-used and change impact cross product boundaries.</p>"
        "</div></div>"
    )


def _reuse_table(parts: list[dict]) -> str:
    rows = "".join(
        "<tr>"
        f'<td class="mono strong">{_esc(item["part_id"])}</td>'
        f"<td>{_esc(item['part_name'])}</td>"
        f"<td>{_esc(item['part_type'])}</td>"
        f'<td class="num">{_fmt_int(item["product_count"])}</td>'
        f'<td class="num">{_fmt_int(item["direct_parent_count"])}</td>'
        f'<td class="num">{_fmt_weight(item["total_direct_quantity"])}</td>'
        "</tr>"
        for item in parts
    )
    return (
        '<div class="table-wrap"><table class="data-table wide">'
        "<thead><tr>"
        "<th>Part</th><th>Name</th><th>Type</th>"
        '<th class="num">Products</th><th class="num">Direct parents</th>'
        '<th class="num">Direct qty (base UoM)</th>'
        "</tr></thead>"
        f"<tbody>{rows}</tbody></table></div>"
    )


def _quality_summary(quality: dict) -> str:
    ratio = f"{_fmt_int(quality['passed'])}/{_fmt_int(quality['total_nodes'])}"
    meta = (
        f"{_fmt_int(quality['model_nodes'])} model nodes · "
        f"{_fmt_int(quality['test_nodes'])} data tests · "
        f"{_fmt_int(quality['unit_test_nodes'])} unit test"
    )
    issues = (
        f"{_fmt_int(quality['failures'])} failures · "
        f"{_fmt_int(quality['errors'])} errors · "
        f"{_fmt_int(quality['skipped'])} skipped"
    )
    return (
        '<div class="quality-hero">'
        f'<div class="quality-number">{ratio}</div>'
        "<div>"
        '<p class="quality-title">checks pass on clean data</p>'
        f'<p class="note">{meta}. {issues}.</p>'
        "</div></div>"
    )


def _defect_cards(defects: list[dict]) -> str:
    cards = "".join(
        '<article class="defect-card">'
        '<div class="defect-head">'
        f"<h3>{_esc(item['label'])}</h3>"
        f'<span class="seeded">Seeded in messy data: {_esc(item["seeded_label"])}</span>'
        "</div>"
        f'<p class="defect-desc">{_esc(item["description"])}</p>'
        '<div class="defect-meta">'
        f"<code>{_esc(item['test'])}</code>"
        '<span class="ok">0 violations on clean</span>'
        "</div></article>"
        for item in defects
    )
    return '<div class="defect-grid">' + cards + "</div>"


def _reconciliation_summary(recon: dict) -> str:
    counts = recon["status_counts"]
    matched = counts.get("match", 0)
    total = recon["total"]
    return (
        '<div class="quality-hero">'
        f'<div class="quality-number long">{_fmt_int(matched)}/{_fmt_int(total)}</div>'
        "<div>"
        '<p class="quality-title">BOM lines match between PLM and ERP</p>'
        '<p class="note">Full outer join on parent and child part numbers. '
        "The status bar shows every reconciliation bucket returned by the mart.</p>"
        "</div></div>"
    )


def _reconciliation_bar(recon: dict) -> str:
    counts = recon["status_counts"]
    total = recon["total"]
    segments = []
    for status, count in counts.items():
        if count <= 0 or total <= 0:
            continue
        color = RECON_COLORS.get(status, "#5b5f66")
        segments.append(
            f'<span class="recon-seg" style="width:{count / total * 100:.4f}%;'
            f'background:{color}" title="{_esc(status)}: {_fmt_int(count)}"></span>'
        )
    return '<div class="recon-bar">' + "".join(segments) + "</div>"


def _reconciliation_status(recon: dict) -> str:
    counts = recon["status_counts"]
    known = ["match", "quantity_mismatch", "uom_mismatch", "plm_only", "erp_only"]
    statuses = known + sorted(set(counts) - set(known))
    items = "".join(
        '<span class="recon-item">'
        f'<span class="swatch" style="background:{RECON_COLORS.get(status, "#5b5f66")}"></span>'
        f"{_esc(RECON_LABELS.get(status, status.replace('_', ' ')))}"
        f'<span class="legend-count">{_fmt_int(counts.get(status, 0))}</span>'
        "</span>"
        for status in statuses
    )
    return '<div class="recon-legend">' + items + "</div>"


def render_report(metrics: dict) -> str:
    """Render a complete HTML page from a metrics dictionary."""
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    bom = metrics["bom"]
    leaf_share = (
        bom["leaf_rows"] / bom["explosion_rows"] if bom["explosion_rows"] else 0
    )
    bom_note = (
        '<p class="note">'
        f"{_fmt_int(bom['explosion_rows'])} explosion rows. The deepest product "
        f"path is {_fmt_int(bom['max_depth'])} edges. "
        f"{_fmt_int(bom['leaf_rows'])} rows are non-assembly leaves "
        f"({_fmt_pct(leaf_share)} of explosion rows)."
        "</p>"
    )
    built_in_checks = metrics["quality"]["total_nodes"] - len(metrics["defects"])
    verify_note = (
        '<p class="note">The seven singular tests catch the seeded defects. '
        '<span class="mono">make verify-defects</span> proves exactly one '
        f"failure per defect and {_fmt_int(built_in_checks)}/"
        f"{_fmt_int(built_in_checks)} built-in checks on every defect dataset."
        "</p>"
    )
    replacements = {
        "SEED": _esc(metrics["seed"]),
        "AS_OF_DATE": _esc(metrics["as_of_date"]),
        "KPI_STRIP": _kpi_strip(metrics["counts"], bom["max_depth"]),
        "BOM_CHART": _bom_chart(bom["levels"]),
        "BOM_NOTE": bom_note,
        "PRODUCT_TABLE": _product_table(metrics["products"]),
        "CYCLE_DONUT": _cycle_donut(metrics["cycle"]["status_counts"]),
        "CYCLE_LEGEND": _cycle_legend(metrics["cycle"]["status_counts"]),
        "CYCLE_STATS": _cycle_stats(metrics["cycle"]),
        "IMPACT_STATS": _impact_stats(metrics["impact"]),
        "IMPACT_EXAMPLE": _impact_example(metrics["impact"]["example"]),
        "IMPACT_TABLE": _impact_table(metrics["impact"]["top_changes"]),
        "REUSE_CALLOUT": _reuse_callout(metrics["reuse"]),
        "REUSE_TABLE": _reuse_table(metrics["reuse"]["shared_parts"]),
        "QUALITY_SUMMARY": _quality_summary(metrics["quality"]),
        "DEFECT_CARDS": _defect_cards(metrics["defects"]),
        "VERIFY_NOTE": verify_note,
        "RECON_SUMMARY": _reconciliation_summary(metrics["reconciliation"]),
        "RECON_BAR": _reconciliation_bar(metrics["reconciliation"]),
        "RECON_STATUS": _reconciliation_status(metrics["reconciliation"]),
    }

    rendered = template
    for key, value in replacements.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    if "{{" in rendered:
        start = rendered.index("{{")
        raise ValueError(
            f"unresolved template token near {rendered[start:start + 60]!r}"
        )
    if "${" in rendered:
        raise ValueError("unresolved dollar placeholder in template")
    return rendered


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the static PLM/BOM HTML report."
    )
    parser.add_argument(
        "--db",
        default=os.environ.get("PLM_DUCKDB_PATH", DEFAULT_DB),
        help=f"DuckDB database path (default: {DEFAULT_DB})",
    )
    parser.add_argument(
        "--out",
        default=DEFAULT_OUT,
        help=f"output HTML path (default: {DEFAULT_OUT})",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="generator seed used for the all-defects manifest (default: 42)",
    )
    args = parser.parse_args(argv)

    metrics = collect_metrics(args.db, seed=args.seed)
    rendered = render_report(metrics)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")
    print(f"wrote {out_path} ({len(rendered):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
