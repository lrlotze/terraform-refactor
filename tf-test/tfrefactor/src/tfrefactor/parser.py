"""
parser.py — Load one or more .tf files into a normalised intermediate
representation (IR).

IR shape
--------
A list of ResourceBlock dicts:

    {
        "resource_type": "aws_subnet",      # e.g. "aws_subnet"
        "resource_name": "tfer--subnet-07…",# logical name in the .tf
        "attrs": {                          # flat + nested attribute dict
            "cidr_block": "10.0.1.0/24",
            "vpc_id": "${data.terraform_remote_state…}",
            ...
        },
        "source_file": "generated.tf",     # originating file path
    }

Blocks that are not `resource` blocks (provider, data, output, terraform,
locals) are collected separately in a `MetaBlocks` structure so the emitter
can reproduce or consolidate them.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import hcl2

# ── public types ────────────────────────────────────────────────────────────

ResourceBlock = dict  # typed alias for IDE hints
MetaBlocks = dict     # keyed by block kind -> list of raw dicts


# ── helpers ─────────────────────────────────────────────────────────────────

def _flatten_nested(value: Any) -> Any:
    """
    hcl2 wraps single-item nested blocks in a list, e.g.:
        metadata_options { ... }  →  [{"http_endpoint": "enabled", …}]
    Return the first element when the value is a single-element list of dicts.
    """
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict):
        return {k: _flatten_nested(v) for k, v in value[0].items()}
    if isinstance(value, list):
        return [_flatten_nested(v) for v in value]
    if isinstance(value, dict):
        return {k: _flatten_nested(v) for k, v in value.items()}
    return value


def _attr_key_fingerprint(attrs: dict) -> frozenset[str]:
    """
    Return the sorted frozenset of top-level attribute *keys*.
    Two resources with identical fingerprints have the same schema shape
    and are candidates for consolidation into a single reusable module.
    """
    return frozenset(attrs.keys())


# ── main public API ──────────────────────────────────────────────────────────

def parse_files(paths: list[str | Path]) -> tuple[list[ResourceBlock], list[dict]]:
    """
    Parse one or more .tf files.

    Returns
    -------
    resources : list[ResourceBlock]
        All resource{} blocks found, normalised.
    meta      : list[dict]
        All non-resource top-level blocks (provider, data, output, terraform,
        locals).  Each entry carries a ``_kind`` key so the emitter knows
        which HCL keyword to use when re-emitting.
    """
    resources: list[ResourceBlock] = []
    meta: list[dict] = []

    for path in paths:
        path = Path(path)
        with path.open("r", encoding="utf-8") as fh:
            try:
                parsed = hcl2.load(fh)
            except Exception as exc:
                raise ValueError(f"Failed to parse {path}: {exc}") from exc

        source = str(path)

        for block_kind, block_list in parsed.items():
            if block_kind == "resource":
                for resource_type_dict in block_list:
                    for resource_type, instances in resource_type_dict.items():
                        for resource_name, raw_attrs in instances.items():
                            attrs = _flatten_nested(raw_attrs)
                            resources.append(
                                {
                                    "resource_type": resource_type,
                                    "resource_name": resource_name,
                                    "attrs": attrs,
                                    "source_file": source,
                                    "_fingerprint": _attr_key_fingerprint(attrs),
                                }
                            )
            else:
                # provider, data, output, terraform, locals …
                for raw in block_list:
                    meta.append({"_kind": block_kind, "_data": raw, "_source": source})

    return resources, meta


def parse_directory(directory: str | Path) -> tuple[list[ResourceBlock], list[dict]]:
    """Convenience: parse all *.tf files under a directory (non-recursive)."""
    directory = Path(directory)
    tf_files = sorted(directory.glob("*.tf"))
    if not tf_files:
        raise FileNotFoundError(f"No .tf files found in {directory}")
    return parse_files(tf_files)
