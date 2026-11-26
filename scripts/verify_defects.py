#!/usr/bin/env python3
"""Prove one-to-one defect attribution for the dbt data-quality tests.

For clean data, each of the eight seeded defects on its own, and all eight
together, this script runs two passes against the same generated data:

Pass 1 - full ``dbt build``: collect every failed or errored node and check
that zero failures occur on clean data, exactly one failure named
``assert_no_<defect>`` occurs per single defect, and exactly eight failures
(one per defect test) occur when all defects are enabled.

Pass 2 - ``dbt build`` with the eight singular defect tests excluded: prove
that the built-in generic, unit and mart tests still pass on defective data.
A full build gates downstream nodes after a failed test, so pass 1 alone could
let a built-in test hide behind a ``skipped`` status. Pass 2 removes that gate
and requires every built-in node to pass and every model to run successfully.

Usage:

    python scripts/verify_defects.py --dbt /path/to/dbt

Exits nonzero if either pass deviates from its expectation.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Canonical generator switch -> singular test that must be the only failure
# when that switch is enabled on its own.
DEFECT_TESTS = {
    "cyclic_bom": "assert_no_cyclic_bom",
    "orphan_parts": "assert_no_orphan_parts",
    "released_assembly_unreleased_child": (
        "assert_no_released_assembly_unreleased_child"
    ),
    "overlapping_revision_effectivity": (
        "assert_no_overlapping_revision_effectivity"
    ),
    "zero_negative_quantity": "assert_no_zero_or_negative_quantity",
    "uom_mismatch": "assert_no_uom_mismatch",
    "eco_closed_without_ecn": "assert_no_eco_closed_without_ecn",
    "change_dates_out_of_order": "assert_no_change_dates_out_of_order",
}

SINGULAR_TESTS = sorted(DEFECT_TESTS.values())
EXCLUDE_SELECTION = " ".join(SINGULAR_TESTS)

FAILING_STATUSES = {"fail", "error"}
PASSING_STATUSES = {"pass", "success"}


def node_name(result: dict) -> str:
    """Return the test name from a dbt run_results entry."""
    unique_id = result.get("unique_id", "")
    parts = unique_id.split(".")
    if len(parts) >= 3:
        return parts[2]
    return unique_id or result.get("name", "<unknown>")


def read_results(target_path: Path) -> tuple[list[dict], str | None]:
    """Return (all results, error message) from run_results.json."""
    run_results = target_path / "run_results.json"
    if not run_results.exists():
        return [], f"missing {run_results} (dbt did not write run results)"
    try:
        payload = json.loads(run_results.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [], f"could not read run_results.json: {exc}"
    return payload.get("results", []), None


def failing(results: list[dict]) -> list[dict]:
    return [r for r in results if r.get("status") in FAILING_STATUSES]


def run_dataset(dbt: str, dataset: str, defects: str) -> dict:
    """Generate, build both passes and evaluate one dataset."""
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"plm-verify-{dataset}-"))
    raw_dir = tmp_dir / "raw"
    db_path = tmp_dir / "plm.duckdb"
    target_path = tmp_dir / "target"
    builtin_target_path = tmp_dir / "target-builtins"
    row = {
        "dataset": dataset,
        "failures": "?",
        "expected": "?",
        "builtin_passing": "?",
        "builtin_total": "?",
        "result": "FAIL",
        "names": [],
        "detail": "",
    }

    try:
        generate = subprocess.run(
            [
                sys.executable,
                "-m",
                "generator",
                "--out",
                str(raw_dir),
                "--seed",
                "42",
                "--defects",
                defects,
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if generate.returncode != 0:
            row["detail"] = (
                f"generator failed ({generate.returncode}): "
                f"{generate.stderr.strip()}"
            )
            return row

        env = os.environ.copy()
        env["PLM_RAW_DIR"] = str(raw_dir)
        env["PLM_DUCKDB_PATH"] = str(db_path)

        # --------------------------------------------------------------
        # Pass 1: full build, exactly the expected singular failures.
        # --------------------------------------------------------------
        build = subprocess.run(
            [
                dbt,
                "build",
                "--project-dir",
                "dbt",
                "--profiles-dir",
                "dbt",
                "--target-path",
                str(target_path),
            ],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )

        first_results, error = read_results(target_path)
        if error:
            row["detail"] = error
            return row

        first_failed = failing(first_results)
        names = sorted(node_name(result) for result in first_failed)
        row["names"] = names
        row["failures"] = str(len(names))

        if dataset == "clean":
            expected_count = 0
            expected_names: set[str] = set()
            row["expected"] = "0"
        elif dataset == "all":
            expected_names = set(DEFECT_TESTS.values())
            expected_count = len(expected_names)
            row["expected"] = f"{expected_count} (one per defect test)"
        else:
            expected_names = {DEFECT_TESTS[dataset]}
            expected_count = 1
            row["expected"] = next(iter(expected_names))

        attribution_ok = (
            len(names) == expected_count and set(names) == expected_names
        )
        detail_parts = []
        if not attribution_ok:
            detail_parts.append(
                f"full build exit {build.returncode}; expected "
                f"{sorted(expected_names) or 'no failures'}, got "
                f"{names or 'none'}"
            )

        # --------------------------------------------------------------
        # Pass 2: built-ins only. Excluding the singular tests removes the
        # build gate, so every model and generic/unit/mart test must run.
        # --------------------------------------------------------------
        expected_builtins = len(first_results) - len(SINGULAR_TESTS)
        second_build = subprocess.run(
            [
                dbt,
                "build",
                "--project-dir",
                "dbt",
                "--profiles-dir",
                "dbt",
                "--target-path",
                str(builtin_target_path),
                "--exclude",
                EXCLUDE_SELECTION,
            ],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )

        builtin_results, builtin_error = read_results(builtin_target_path)
        if builtin_error:
            row["builtin_passing"] = "?"
            row["builtin_total"] = "?"
            detail_parts.append(f"built-in pass: {builtin_error}")
            builtin_ok = False
        else:
            builtin_failed = failing(builtin_results)
            non_passing = [
                r
                for r in builtin_results
                if r.get("status") not in PASSING_STATUSES
            ]
            model_nodes = [
                r
                for r in builtin_results
                if r.get("unique_id", "").startswith("model.")
            ]
            models_ok = bool(model_nodes) and all(
                r.get("status") == "success" for r in model_nodes
            )
            count_ok = len(builtin_results) == expected_builtins
            builtin_ok = (
                not builtin_failed
                and not non_passing
                and models_ok
                and count_ok
            )
            row["builtin_passing"] = str(
                len(builtin_results) - len(non_passing)
            )
            row["builtin_total"] = str(len(builtin_results))

            if not builtin_ok:
                problems = []
                if builtin_failed:
                    problems.append(
                        "failed: "
                        + ", ".join(
                            sorted(node_name(r) for r in builtin_failed)
                        )
                    )
                if non_passing:
                    problems.append(
                        "not passing: "
                        + ", ".join(
                            sorted(
                                f"{node_name(r)}={r.get('status')}"
                                for r in non_passing
                            )
                        )
                    )
                if not models_ok:
                    bad_models = sorted(
                        f"{node_name(r)}={r.get('status')}"
                        for r in model_nodes
                        if r.get("status") != "success"
                    )
                    problems.append(
                        "model nodes not successful: "
                        + (", ".join(bad_models) or "none found")
                    )
                if not count_ok:
                    problems.append(
                        f"expected {expected_builtins} built-in nodes, got "
                        f"{len(builtin_results)}"
                    )
                detail_parts.append(
                    f"built-in build exit {second_build.returncode}: "
                    + "; ".join(problems)
                )

        row["result"] = "PASS" if attribution_ok and builtin_ok else "FAIL"
        row["detail"] = "; ".join(detail_parts)
        return row
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def dataset_cases() -> list[tuple[str, str]]:
    """(label, generator --defects value) for every case to verify."""
    cases = [("clean", "none")]
    cases.extend((name, name) for name in DEFECT_TESTS)
    cases.append(("all", "all"))
    return cases


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify exactly-one-failure defect attribution and that built-in "
            "tests pass on every defect dataset."
        )
    )
    parser.add_argument(
        "--dbt",
        default="dbt",
        help="dbt executable to run (default: dbt)",
    )
    args = parser.parse_args(argv)

    rows = []
    for label, defects in dataset_cases():
        print(f"verifying {label} ...", file=sys.stderr, flush=True)
        rows.append(run_dataset(args.dbt, label, defects))

    width_dataset = max(len("dataset"), *(len(row["dataset"]) for row in rows))
    width_failures = max(len("failures"), *(len(row["failures"]) for row in rows))
    width_expected = max(len("expected"), *(len(row["expected"]) for row in rows))
    width_builtin = max(
        len("built-ins"),
        *(
            len(f"{row['builtin_passing']}/{row['builtin_total']}")
            for row in rows
        ),
    )
    header = (
        f"{'dataset':<{width_dataset}}  "
        f"{'failures':<{width_failures}}  "
        f"{'expected':<{width_expected}}  "
        f"{'built-ins':<{width_builtin}}  "
        f"{'result'}"
    )
    print()
    print(header)
    print("-" * len(header))
    for row in rows:
        builtin = f"{row['builtin_passing']}/{row['builtin_total']}"
        print(
            f"{row['dataset']:<{width_dataset}}  "
            f"{row['failures']:<{width_failures}}  "
            f"{row['expected']:<{width_expected}}  "
            f"{builtin:<{width_builtin}}  "
            f"{row['result']}"
        )

    mismatches = [row for row in rows if row["result"] != "PASS"]
    if mismatches:
        print()
        for row in mismatches:
            print(f"MISMATCH {row['dataset']}: {row['detail']}")
        return 1

    print()
    print(
        "OK: clean has 0 failures; each defect fails exactly its own test; "
        "the built-in tests pass on every dataset."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
