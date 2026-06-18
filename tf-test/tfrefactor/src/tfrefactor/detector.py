"""
detector.py — Similarity detection: group resources that share the same
attribute-key fingerprint (same schema shape) and identify which attributes
are *shared* (constant across all instances) vs *varying* (differ per instance).

Public API
----------
detect_module_groups(resources) → list[ModuleGroup]

ModuleGroup
-----------
{
    "resource_type":  "aws_subnet",
    "module_name":    "aws_subnet",          # safe snake_case module dir name
    "instances": [
        {
            "resource_name": "tfer--subnet-07…",
            "attrs":         { … full attr dict … },
        },
        …
    ],
    "shared_attrs":  { attr_key: value, … }, # identical across ALL instances
    "varying_keys":  [ "cidr_block", "vpc_id", … ],  # differ per instance
    "is_singleton":  False,                  # True if only 1 resource found
}

Singleton resources (no duplicates) are still returned so the emitter can
handle them uniformly; they will not generate a module but will be inlined
in the root main.tf (or emitted as a trivial single-resource module).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .parser import ResourceBlock


# ── helpers ──────────────────────────────────────────────────────────────────

def _safe_module_name(resource_type: str) -> str:
    """
    Convert a resource type like 'aws_internet_gateway' into a safe directory
    name, stripping provider prefix where unambiguous.
    e.g.  aws_subnet           → aws_subnet
          aws_internet_gateway → aws_internet_gateway
    """
    return resource_type.lower().replace("-", "_")


def _values_are_equal(a: Any, b: Any) -> bool:
    """Deep equality, treating string booleans as equivalent to native bools."""
    # normalise "true"/"false" strings so "false" == False
    def norm(v: Any) -> Any:
        if isinstance(v, str) and v.lower() in ("true", "false"):
            return v.lower() == "true"
        return v

    return norm(a) == norm(b)


def _shared_and_varying(
    instances: list[dict],
) -> tuple[dict[str, Any], list[str]]:
    """
    Given a list of instance dicts (each with an 'attrs' key), return:
      shared_attrs  – attributes whose value is identical across every instance
      varying_keys  – attributes that differ in at least one instance
    """
    if not instances:
        return {}, []

    # Start from the first instance's attrs as the candidate shared set
    candidate_shared: dict[str, Any] = dict(instances[0]["attrs"])

    for inst in instances[1:]:
        attrs = inst["attrs"]
        # Remove keys from candidate_shared if they differ in this instance
        to_remove = []
        for key, val in candidate_shared.items():
            if key not in attrs or not _values_are_equal(attrs[key], val):
                to_remove.append(key)
        for key in to_remove:
            del candidate_shared[key]

    # varying = any key that appears in any instance but is NOT shared
    all_keys: set[str] = set()
    for inst in instances:
        all_keys.update(inst["attrs"].keys())

    varying_keys = sorted(all_keys - set(candidate_shared.keys()))

    return candidate_shared, varying_keys


# ── main public API ───────────────────────────────────────────────────────────

def detect_module_groups(resources: list[ResourceBlock]) -> list[dict]:
    """
    Group resources by (resource_type, fingerprint) and analyse each group.

    Resources of the same type that share the exact same set of attribute keys
    are considered candidates for a shared module.  Resources of the same type
    but with *different* attribute-key sets get their own separate group (e.g.
    an aws_instance with extra blocks vs a minimal one).

    Returns a list of ModuleGroup dicts (see module docstring).
    """
    # bucket: (resource_type, frozenset_of_keys) → [ResourceBlock, …]
    buckets: dict[tuple, list[ResourceBlock]] = defaultdict(list)

    for res in resources:
        key = (res["resource_type"], res["_fingerprint"])
        buckets[key].append(res)

    groups: list[dict] = []

    for (resource_type, _fingerprint), bucket in buckets.items():
        instances = [
            {"resource_name": r["resource_name"], "attrs": r["attrs"]}
            for r in bucket
        ]
        shared_attrs, varying_keys = _shared_and_varying(instances)

        groups.append(
            {
                "resource_type": resource_type,
                "module_name": _safe_module_name(resource_type),
                "instances": instances,
                "shared_attrs": shared_attrs,
                "varying_keys": varying_keys,
                "is_singleton": len(instances) == 1,
            }
        )

    # Stable sort: multi-instance groups first, then alphabetical by type
    groups.sort(key=lambda g: (g["is_singleton"], g["resource_type"]))
    return groups
