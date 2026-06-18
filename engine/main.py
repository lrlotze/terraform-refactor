"""
Terraform Refactoring Engine — Main Entry Point

Usage:
    python3 engine/main.py <input.tf> <output_dir>
    python3 engine/main.py <input.tf> <output_dir> --dry-run
    python3 engine/main.py <input.tf> <output_dir> --state-dir <terraformer_generated_dir>

Pipeline stages (in order):
    1. Parse     — HCL → Python object model
    2. Denoise   — remove Terraformer noise (duplicates, outputs, remote-state refs)
    3. Defaults  — strip attributes whose values match provider defaults
    4. Group     — assign each resource to a logical file group
    5. Emit      — write one .tf file per group to output_dir
    6. State     — (optional) merge Terraformer state files into output/terraform.tfstate
"""

from __future__ import annotations
import sys
import os

# Allow running from any working directory
sys.path.insert(0, os.path.dirname(__file__))

from parser import parse_hcl, HCLFile, ResourceBlock
from noise_remover import remove_noise
from default_remover import remove_defaults
from grouper import group_resources
from emitter import emit
from state_merger import merge_state_files


def _count_resources(hcl: HCLFile) -> dict[str, int]:
    counts: dict[str, int] = {}
    for block in hcl.blocks:
        if isinstance(block, ResourceBlock):
            counts[block.resource_type] = counts.get(block.resource_type, 0) + 1
    return counts


def run(input_path: str, output_dir: str, dry_run: bool = False, state_dir: str = None) -> None:
    print(f"\n=== Terraform Refactoring Engine ===")
    print(f"Input:  {input_path}")
    print(f"Output: {output_dir}")
    if state_dir:
        print(f"State:  {state_dir}")
    if dry_run:
        print("Mode:   dry-run (no files written)\n")
    else:
        print()

    # ------------------------------------------------------------------
    # Stage 1: Parse
    # ------------------------------------------------------------------
    print("[1/6] Parsing HCL...")
    with open(input_path, "r") as f:
        text = f.read()

    hcl = parse_hcl(text)
    total_blocks = len(hcl.blocks)
    resource_counts_before = _count_resources(hcl)
    print(f"      Parsed {total_blocks} top-level blocks "
          f"({sum(resource_counts_before.values())} resource blocks)")
    for rtype, count in sorted(resource_counts_before.items()):
        print(f"        {rtype}: {count}")

    # ------------------------------------------------------------------
    # Stage 2: Noise removal
    # ------------------------------------------------------------------
    print("\n[2/6] Removing Terraformer noise...")
    hcl = remove_noise(hcl)
    resource_counts_after_noise = _count_resources(hcl)
    remaining = len(hcl.blocks)
    print(f"      {remaining} blocks remain after noise removal "
          f"({sum(resource_counts_after_noise.values())} resource blocks)")

    # ------------------------------------------------------------------
    # Stage 3: Default value removal
    # ------------------------------------------------------------------
    print("\n[3/6] Stripping default-valued attributes...")
    hcl = remove_defaults(hcl)
    # Count total attributes across all resource blocks for reporting
    total_attrs = sum(
        len(b.attributes) + sum(len(nb.attributes) for nb in b.nested_blocks)
        for b in hcl.blocks
        if isinstance(b, ResourceBlock)
    )
    print(f"      {total_attrs} attributes remain across "
          f"{sum(_count_resources(hcl).values())} resource blocks")

    # ------------------------------------------------------------------
    # Stage 4: Group
    # ------------------------------------------------------------------
    print("\n[4/6] Grouping resources...")
    groups = group_resources(hcl)
    for group, blocks in sorted(groups.items()):
        resource_blocks = [b for b in blocks if isinstance(b, ResourceBlock)]
        print(f"      {group}.tf: {len(resource_blocks)} resource block(s), "
              f"{len(blocks) - len(resource_blocks)} other block(s)")

    # ------------------------------------------------------------------
    # Stage 5: Emit (skipped in dry-run)
    # ------------------------------------------------------------------
    if dry_run:
        print("\n[DRY RUN] Skipping file write.")
        return

    print(f"\n[5/6] Writing output files to {output_dir}...")
    emit(groups, output_dir)

    # ------------------------------------------------------------------
    # Stage 6: State merging (optional)
    # ------------------------------------------------------------------
    if state_dir:
        print(f"\n[6/6] Merging Terraformer state files from {state_dir}...")
        state_output = os.path.join(output_dir, "terraform.tfstate")
        try:
            count = merge_state_files(state_dir, state_output)
            print(f"      Merged {count} resources into state file")
        except Exception as e:
            print(f"  [ERROR] State merge failed: {e}")
            print(f"  [INFO]  Continuing without state file — you can import manually")

    print("\n=== Done ===")
    print(f"Output directory: {os.path.abspath(output_dir)}")
    if state_dir:
        print(f"Next steps:")
        print(f"  cd {output_dir}")
        print(f"  terraform init")
        print(f"  terraform plan   # should show 0 changes")
    else:
        print("Run 'terraform fmt <output_dir>' to apply canonical formatting.")
        print("Use --state-dir to include a merged terraform.tfstate for instant validation.")


def main() -> None:
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    args = [a for a in args if a != "--dry-run"]

    state_dir = None
    if "--state-dir" in args:
        idx = args.index("--state-dir")
        if idx + 1 >= len(args):
            print("Error: --state-dir requires a directory argument")
            sys.exit(1)
        state_dir = args[idx + 1]
        args = args[:idx] + args[idx + 2:]  # remove both --state-dir and its value

    if len(args) != 2:
        print("Usage: python backend/main.py <input.tf> <output_dir> [--dry-run] [--state-dir <dir>]")
        sys.exit(1)

    input_path, output_dir = args[0], args[1]

    if not os.path.isfile(input_path):
        print(f"Error: input file not found: {input_path}")
        sys.exit(1)

    if state_dir and not os.path.isdir(state_dir):
        print(f"Error: state directory not found: {state_dir}")
        sys.exit(1)

    run(input_path, output_dir, dry_run=dry_run, state_dir=state_dir)


if __name__ == "__main__":
    main()
