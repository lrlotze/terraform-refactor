"""
Defaults Registry

Loads defaults_registry.json and exposes is_default() for attribute comparison.
Type-aware: registry stores Python-native types; comparison is exact-match only.
"""

from __future__ import annotations
import json
import os
from typing import Any


_REGISTRY: dict | None = None
_REGISTRY_PATH = os.path.join(os.path.dirname(__file__), "defaults_registry.json")


def load_registry() -> dict:
    """Load and cache the defaults registry from JSON."""
    global _REGISTRY
    if _REGISTRY is None:
        with open(_REGISTRY_PATH, "r") as f:
            data = json.load(f)
        # Strip metadata keys
        _REGISTRY = {k: v for k, v in data.items() if not k.startswith("_")}
    return _REGISTRY


def is_default(resource_type: str, attr_path: str, typed_value: Any) -> bool:
    """
    Return True iff the attribute value exactly matches the registered default.

    Args:
        resource_type: e.g. "aws_vpc"
        attr_path:     flat key e.g. "enable_dns_support",
                       or dot-path for nested e.g. "metadata_options.http_endpoint"
        typed_value:   the Python-typed value from the parser (bool, int, str, etc.)

    Returns:
        True  → safe to remove (value matches registered default)
        False → preserve (unknown default, or value differs from default)

    Safety: any exception returns False (preserve).
    """
    try:
        registry = load_registry()
        resource_defaults = registry.get(resource_type)
        if resource_defaults is None:
            return False

        if attr_path not in resource_defaults:
            return False

        default_val = resource_defaults[attr_path]

        # Strict type + value equality — no cross-type coercion here.
        # The parser already coerced typed_value; registry stores Python natives.
        # bool must be checked before int because isinstance(True, int) is True in Python.
        if type(default_val) != type(typed_value):
            return False

        return default_val == typed_value

    except Exception:
        # Safety rule: on any error, preserve the attribute
        return False
