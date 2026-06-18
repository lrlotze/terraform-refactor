"""
Noise Remover

Removes Terraformer-specific structural noise from a parsed HCLFile:
  - Duplicate provider blocks (keep first)
  - Duplicate terraform blocks (keep first)
  - All output blocks (Terraformer cross-module ID exports)
  - All data "terraform_remote_state" blocks
  - Rewrites ${data.terraform_remote_state.*} references to direct resource refs
  - Removes primary_network_interface nested block (computed, hard-coded ENI ID)
  - Removes placement_partition_number = 0 (computed attribute)

Safety rules:
  - If a data block is NOT terraform_remote_state, it is preserved
  - Reference rewriting only proceeds if the rewritten target exists in the file
  - If rewriting would produce a dangling reference, the original is preserved + warning printed
"""

from __future__ import annotations
import re
from copy import deepcopy

from parser import (
    HCLFile, Block, ResourceBlock, ProviderBlock, TerraformBlock,
    OutputBlock, DataBlock, NestedBlock, Attribute,
)


# ---------------------------------------------------------------------------
# Reference rewriter
# ---------------------------------------------------------------------------

# Matches: "${data.terraform_remote_state.<alias>.outputs.<rtype>_<rname>_id}"
# Also matches without ${ } wrapper when used bare (rare but possible)
_REMOTE_STATE_REF_RE = re.compile(
    r'\$\{data\.terraform_remote_state\.\w+\.outputs\.'
    r'(aws_[a-z_]+)_(tfer--[\w-]+)_id\}'
)

# Also handle bare (non-interpolated) references just in case
_REMOTE_STATE_BARE_RE = re.compile(
    r'data\.terraform_remote_state\.\w+\.outputs\.'
    r'(aws_[a-z_]+)_(tfer--[\w-]+)_id'
)


def _known_resources(hcl: HCLFile) -> set[str]:
    """Return set of 'resource_type.resource_name' for all ResourceBlocks."""
    return {
        f"{b.resource_type}.{b.resource_name}"
        for b in hcl.blocks
        if isinstance(b, ResourceBlock)
    }


def _rewrite_ref(value: str, known: set[str]) -> str:
    """
    Rewrite a single attribute value string, replacing remote-state references
    with direct resource references.

    e.g.  "${data.terraform_remote_state.vpc.outputs.aws_vpc_tfer--vpc-abc_id}"
          → "aws_vpc.tfer--vpc-abc.id"

    If the rewritten reference does not correspond to a known resource, the
    original value is preserved and a warning is printed.
    """
    def replacer(m: re.Match) -> str:
        rtype = m.group(1)     # e.g. aws_vpc
        rname = m.group(2)     # e.g. tfer--vpc-0b530d7af19ffa635
        candidate = f"{rtype}.{rname}"
        if candidate not in known:
            print(f"  [WARN] Reference rewrite: '{candidate}' not found in parsed resources — preserving original ref")
            return m.group(0)
        return f"{rtype}.{rname}.id"

    rewritten = _REMOTE_STATE_REF_RE.sub(replacer, value)

    # Also handle bare (non-${ }) form
    def bare_replacer(m: re.Match) -> str:
        rtype = m.group(1)
        rname = m.group(2)
        candidate = f"{rtype}.{rname}"
        if candidate not in known:
            print(f"  [WARN] Reference rewrite (bare): '{candidate}' not found — preserving original ref")
            return m.group(0)
        return f"{rtype}.{rname}.id"

    rewritten = _REMOTE_STATE_BARE_RE.sub(bare_replacer, rewritten)
    return rewritten


def _rewrite_attrs(attrs: dict[str, Attribute], known: set[str]) -> None:
    """Rewrite remote-state refs in all attribute values (mutates in place)."""
    for attr in attrs.values():
        if isinstance(attr.typed_value, str):
            new_val = _rewrite_ref(attr.typed_value, known)
            if new_val != attr.typed_value:
                # Strip surrounding quotes that were part of the original interpolation
                # string storage (e.g. '"${...}"' → 'aws_vpc.xxx.id').
                # After rewriting, the value is a bare Terraform reference expression,
                # not a string literal, so we store it without extra quotes.
                if (new_val.startswith('"') and new_val.endswith('"')
                        and "${" not in new_val):
                    new_val = new_val[1:-1]
                attr.typed_value = new_val
                # raw_value stores the final HCL text (without outer quotes — the
                # renderer will add them when it calls _render_value).
                attr.raw_value = new_val


def _rewrite_nested(nested_blocks: list[NestedBlock], known: set[str]) -> None:
    """Recursively rewrite remote-state refs inside nested blocks."""
    for nb in nested_blocks:
        _rewrite_attrs(nb.attributes, known)
        _rewrite_nested(nb.nested_blocks, known)


# ---------------------------------------------------------------------------
# Noise removal helpers
# ---------------------------------------------------------------------------

def _remove_primary_network_interface(resource: ResourceBlock) -> None:
    """
    Drop the primary_network_interface nested block from aws_instance.
    It contains a hard-coded ENI ID which is a computed attribute, not
    a user-managed configuration value.
    """
    resource.nested_blocks = [
        nb for nb in resource.nested_blocks
        if nb.block_type != "primary_network_interface"
    ]


def _remove_placement_partition_number(resource: ResourceBlock) -> None:
    """
    Drop placement_partition_number from aws_instance.
    It is a computed attribute that cannot be set in HCL configuration
    unless using a placement group with partition strategy.
    """
    resource.attributes.pop("placement_partition_number", None)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def remove_noise(hcl_file: HCLFile) -> HCLFile:
    """
    Remove Terraformer-specific noise from a parsed HCLFile.
    Returns a new HCLFile (does not mutate the input).
    """
    result = deepcopy(hcl_file)

    # --- Step 1: Build set of known resources (for ref rewriting safety check) ---
    known = _known_resources(result)

    # --- Step 2: Rewrite remote-state references in all resource attributes ---
    for block in result.blocks:
        if isinstance(block, ResourceBlock):
            _rewrite_attrs(block.attributes, known)
            _rewrite_nested(block.nested_blocks, known)

    # --- Step 3: Filter blocks ---
    seen_providers: set[str] = set()
    seen_terraform = False
    clean_blocks: list[Block] = []

    for block in result.blocks:

        # Keep only the first provider block per provider name
        if isinstance(block, ProviderBlock):
            if block.provider_name not in seen_providers:
                seen_providers.add(block.provider_name)
                clean_blocks.append(block)
            else:
                print(f"  [INFO] Dropping duplicate provider \"{block.provider_name}\"")
            continue

        # Keep only the first terraform block
        if isinstance(block, TerraformBlock):
            if not seen_terraform:
                seen_terraform = True
                clean_blocks.append(block)
            else:
                print("  [INFO] Dropping duplicate terraform block")
            continue

        # Drop all output blocks (Terraformer ID exports)
        if isinstance(block, OutputBlock):
            print(f"  [INFO] Dropping output \"{block.output_name}\"")
            continue

        # Drop terraform_remote_state data blocks; keep other data blocks
        if isinstance(block, DataBlock):
            if block.data_type == "terraform_remote_state":
                print(f"  [INFO] Dropping data.terraform_remote_state.{block.data_name}")
                continue
            else:
                clean_blocks.append(block)
            continue

        # Resource blocks — apply instance-specific computed-attr cleanup
        if isinstance(block, ResourceBlock):
            if block.resource_type == "aws_instance":
                _remove_primary_network_interface(block)
                _remove_placement_partition_number(block)
            clean_blocks.append(block)
            continue

        # Keep anything else
        clean_blocks.append(block)

    result.blocks = clean_blocks
    return result
