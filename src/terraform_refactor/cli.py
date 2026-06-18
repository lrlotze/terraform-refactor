import argparse
import sys
from pathlib import Path

from .refactor import run_refactor


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refactor Terraform files into cleaner modules and variable structure."
    )
    parser.add_argument("source", help="Terraform file or directory to refactor")
    parser.add_argument(
        "--output",
        "-o",
        default="refactored",
        help="Directory where refactored files are written",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Analyze and summarize changes without writing files",
    )
    args = parser.parse_args()

    source_path = Path(args.source).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    try:
        run_refactor(source_path, output_path, dry_run=args.dry_run)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
