"""Command-line entry point: ``csvprof file.csv``."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .inference import DEFAULT_NULL_TOKENS
from .profile import profile_csv
from .report import render_json, render_text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="csvprof",
        description=(
            "Profile a CSV file: infer column types, compute statistics, "
            "and report missing values, duplicates and outliers."
        ),
    )
    parser.add_argument("path", help="CSV file to profile")
    parser.add_argument("--json", action="store_true",
                        help="emit the report as JSON instead of text")
    parser.add_argument("-o", "--output", metavar="FILE",
                        help="write the report to FILE instead of stdout")
    parser.add_argument("--top", type=int, default=5, metavar="N",
                        help="show the N most frequent values per column (default: 5)")
    parser.add_argument("--delimiter", metavar="CHAR",
                        help="column delimiter (default: auto-detected)")
    parser.add_argument("--null-values", metavar="TOKENS",
                        help="comma-separated extra spellings to treat as missing, "
                             "e.g. 'missing,unknown'")
    parser.add_argument("--max-rows", type=int, metavar="N",
                        help="profile only the first N data rows")
    parser.add_argument("--no-outliers", action="store_true",
                        help="skip the outlier-counting pass")
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    null_tokens = None
    if args.null_values:
        extra = {token.strip().lower() for token in args.null_values.split(",")}
        null_tokens = DEFAULT_NULL_TOKENS | extra

    try:
        profile = profile_csv(
            args.path,
            delimiter=args.delimiter,
            null_tokens=null_tokens,
            top_n=args.top,
            max_rows=args.max_rows,
            count_outliers=not args.no_outliers,
        )
    except FileNotFoundError as exc:
        print(f"csvprof: {exc}", file=sys.stderr)
        return 2
    except (ValueError, OSError) as exc:
        print(f"csvprof: {exc}", file=sys.stderr)
        return 2

    text = render_json(profile) if args.json else render_text(profile)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
