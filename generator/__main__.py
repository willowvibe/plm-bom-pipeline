"""CLI entry point: ``python -m generator``."""

from __future__ import annotations

import argparse

from . import generate
from .defects import CANONICAL_DEFECTS, parse_defect_selection
from .writer import EXPECTED_FILES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m generator",
        description="Generate deterministic synthetic PLM data for a bicycle manufacturer.",
    )
    parser.add_argument(
        "--out",
        default="data/raw",
        help="output directory (default: data/raw)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="integer seed for all randomness (default: 42)",
    )
    parser.add_argument(
        "--defects",
        default="none",
        help=(
            "defects to inject: 'none', 'all', or a comma-separated list from "
            + ", ".join(CANONICAL_DEFECTS)
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        selection = parse_defect_selection(args.defects)
    except ValueError as exc:
        parser.error(str(exc))

    manifest = generate(args.out, seed=args.seed, defects=selection)
    enabled = ",".join(manifest["enabled_defects"]) or "none"
    print(f"seed={args.seed} defects={enabled} out={args.out}")
    print(f"wrote {len(EXPECTED_FILES)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
