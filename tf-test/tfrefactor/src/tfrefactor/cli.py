"""
cli.py — Command-line entry point.

Usage
-----
    python -m tfrefactor.cli <input_path> [--out <output_dir>]

<input_path> may be:
  • A single .tf file (e.g. generated.tf)
  • A directory containing .tf files

The tool will print a summary of detected groups and write the refactored
tree to <output_dir> (default: ./refactored).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .parser import parse_files, parse_directory
from .detector import detect_module_groups
from .emitter import emit


def _print_summary(groups: list[dict]) -> None:
    print("\n── Module Detection Summary ─────────────────────────────────")
    multi = [g for g in groups if not g["is_singleton"]]
    single = [g for g in groups if g["is_singleton"]]

    if multi:
        print(f"\n  ✓ {len(multi)} reusable module(s) detected:\n")
        for g in multi:
            n = len(g["instances"])
            vk = ", ".join(g["varying_keys"][:5])
            extra = f" … +{len(g['varying_keys'])-5}" if len(g["varying_keys"]) > 5 else ""
            print(f"    • {g['module_name']}  ({n} instances)")
            print(f"      varying inputs : {vk}{extra}")
            sk = list(g["shared_attrs"].keys())[:4]
            print(f"      shared (fixed) : {', '.join(sk)}{' …' if len(g['shared_attrs'])>4 else ''}")
    else:
        print("\n  (no multi-instance groups found)")

    if single:
        print(f"\n  ℹ  {len(single)} singleton resource(s) (written inline to root main.tf):")
        for g in single:
            print(f"    • {g['resource_type']}.{g['instances'][0]['resource_name']}")

    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Detect reusable modules in Terraformer-generated .tf files."
    )
    parser.add_argument("input", help=".tf file or directory containing .tf files")
    parser.add_argument(
        "--out", default="refactored", help="Output directory (default: ./refactored)"
    )
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    if input_path.is_dir():
        resources, meta = parse_directory(input_path)
    elif input_path.suffix == ".tf":
        resources, meta = parse_files([input_path])
    else:
        print(f"ERROR: {input_path} is not a .tf file or directory", file=sys.stderr)
        return 1

    print(f"Parsed {len(resources)} resource(s) from {args.input}")

    groups = detect_module_groups(resources)
    _print_summary(groups)

    out_dir = Path(args.out)
    emit(groups, out_dir)
    print(f"✓ Refactored output written to: {out_dir.resolve()}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
