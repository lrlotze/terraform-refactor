"""
Default Value Remover

Strips attributes from resource blocks whose values exactly match the
defaults registry. Uses registry.is_default() for all decisions — no
heuristics, no guessing.

Additional universal rule (not registry-dependent):
  The 'region' attribute on any resource is a Terraformer artifact that
  echoes the provider region. It is always removed when its value matches
  the provider region string.

Empty nested blocks (all attributes removed) are dropped entirely.
"""

from __future__ import annotations
from copy import deepcopy

from parser import HCLFile, ResourceBlock, ProviderBlock, NestedBlock, Attribute
from registry import is_default


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _provider_region(hcl_file: HCLFile) -> str | None:
    """Extract the region string from the first aws provider block, if present."""
    for block in hcl_file.blocks:
        if isinstance(block, ProviderBlock) and block.provider_name == "aws":
            region_attr = block.attributes.get("region")
            if region_attr is not None:
                return str(region_attr.typed_value)
    return None


def _strip_nested_block(nb: NestedBlock, resource_type: str) -> NestedBlock | None:
    """
    Remove default-valued attributes from a NestedBlock.
    Returns None if the block becomes empty after stripping (so the caller drops it).
    Recurses into sub-nested blocks.
    """
    kept_attrs: dict[str, Attribute] = {}
    for key, attr in nb.attributes.items():
        dot_path = f"{nb.block_type}.{key}"
        if is_default(resource_type, dot_path, attr.typed_value):
            pass  # remove
        else:
            kept_attrs[key] = attr

    kept_nested: list[NestedBlock] = []
    for sub in nb.nested_blocks:
        result = _strip_nested_block(sub, resource_type)
        if result is not None:
            kept_nested.append(result)

    if not kept_attrs and not kept_nested:
        return None

    nb.attributes = kept_attrs
    nb.nested_blocks = kept_nested
    return nb


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# Attributes removed entirely in AWS provider v5 that Terraformer still emits.
# Keyed by resource type → set of attribute names to always drop.
_V5_REMOVED_ATTRS: dict[str, set[str]] = {
    "aws_vpc": {"enable_classiclink", "enable_classiclink_dns_support"},
}


def remove_defaults(hcl_file: HCLFile) -> HCLFile:
    """
    Strip default-valued attributes from all ResourceBlocks in the HCLFile.
    Returns a new HCLFile (does not mutate the input).
    """
    result = deepcopy(hcl_file)
    provider_region = _provider_region(result)

    for block in result.blocks:
        if not isinstance(block, ResourceBlock):
            continue

        rtype = block.resource_type

        # --- Flat attribute removal ---
        kept_attrs: dict[str, Attribute] = {}

        # For aws_instance: if a cpu_options nested block is present, the top-level
        # cpu_core_count and cpu_threads_per_core attributes conflict with it under
        # AWS provider v5 and must be dropped.
        has_cpu_options = (
            rtype == "aws_instance"
            and any(nb.block_type == "cpu_options" for nb in block.nested_blocks)
        )

        for key, attr in block.attributes.items():

            # Universal rule: drop 'region' if it matches the provider region
            if key == "region" and provider_region is not None:
                if str(attr.typed_value) == provider_region:
                    continue  # remove

            # Drop deprecated top-level CPU attrs when cpu_options block is present
            if has_cpu_options and key in ("cpu_core_count", "cpu_threads_per_core"):
                continue  # remove

            # Drop attributes removed entirely in AWS provider v5
            if key in _V5_REMOVED_ATTRS.get(rtype, set()):
                continue  # remove

            if is_default(rtype, key, attr.typed_value):
                pass  # remove
            else:
                kept_attrs[key] = attr

        block.attributes = kept_attrs

        # --- Nested block attribute removal ---
        kept_nested: list[NestedBlock] = []
        for nb in block.nested_blocks:
            stripped = _strip_nested_block(nb, rtype)
            if stripped is not None:
                kept_nested.append(stripped)
            # else: entire block was all defaults → drop it

        block.nested_blocks = kept_nested

    return result
