"""
emitter.py — Write the refactored module tree to an output directory.

For every ModuleGroup produced by detector.detect_module_groups():

  • Multi-instance groups  → a child module under modules/<module_name>/
    - modules/<module_name>/main.tf        (the parameterised resource)
    - modules/<module_name>/variables.tf   (one variable per varying key)
    - modules/<module_name>/outputs.tf     (exports id and ARN if present)

  • Singleton groups       → resource written directly into root main.tf
    (no module indirection needed for a single resource)

The root output directory also receives:
  • providers.tf   (deduplicated provider + terraform blocks)
  • locals.tf      (shared constant values extracted from multi-instance groups)
  • variables.tf   (required inputs — empty by default, caller may extend)
  • main.tf        (module{} calls for every multi-instance group,
                    plus singleton resources)
  • outputs.tf     (one output per resource/module instance)
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

# ── HCL value serialisation ───────────────────────────────────────────────────

def _hcl_value(v: Any, indent: int = 0) -> str:
    """Serialise a Python value to its HCL2 literal representation."""
    pad = "  " * indent
    inner = "  " * (indent + 1)
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        # Preserve ${…} interpolations as-is; quote everything else
        return f'"{v}"'
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        items = ", ".join(_hcl_value(i) for i in v)
        return f"[{items}]"
    if isinstance(v, dict):
        lines = ["{"]
        for dk, dv in v.items():
            lines.append(f"{inner}{dk} = {_hcl_value(dv, indent + 1)}")
        lines.append(f"{pad}}}")
        return "\n".join(lines)
    return f'"{v}"'


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _resource_label(resource_type: str, instance_name: str) -> str:
    """Return a short human-readable label for a module call or output name."""
    # Strip tfer-- prefix produced by Terraformer
    name = re.sub(r"^tfer--", "", instance_name)
    # Remove trailing underscores / dashes
    name = name.strip("_-")
    # Replace non-word chars with underscores
    name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    # Collapse consecutive underscores
    name = re.sub(r"_+", "_", name)
    return name.lower()


# ── Module file writers ───────────────────────────────────────────────────────

def _write_module_main(
    module_dir: Path,
    resource_type: str,
    varying_keys: list[str],
    shared_attrs: dict[str, Any],
) -> None:
    """Write modules/<name>/main.tf — the parameterised resource."""
    lines = [f'resource "{resource_type}" "this" {{']

    # varying attrs reference input variables
    for key in sorted(varying_keys):
        lines.append(f"  {key} = var.{key}")

    # shared attrs are inlined as literals (they never change)
    for key, val in sorted(shared_attrs.items()):
        hval = _hcl_value(val)
        if isinstance(val, dict):
            lines.append(f"  {key} = {hval}")
        else:
            lines.append(f"  {key:<45} = {hval}")

    lines.append("}\n")
    _write(module_dir / "main.tf", "\n".join(lines))


def _write_module_variables(
    module_dir: Path,
    varying_keys: list[str],
    instances: list[dict],
) -> None:
    """Write modules/<name>/variables.tf — one variable{} per varying key."""
    blocks: list[str] = []
    for key in sorted(varying_keys):
        # Infer type hint from first instance that has this key
        sample_val = next(
            (inst["attrs"][key] for inst in instances if key in inst["attrs"]), None
        )
        type_hint = _infer_type(sample_val)
        blocks.append(
            f'variable "{key}" {{\n'
            f"  type        = {type_hint}\n"
            f'  description = ""\n'
            f"}}\n"
        )
    _write(module_dir / "variables.tf", "\n".join(blocks))


def _infer_type(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, str):
        # booleans stored as strings
        if value.lower() in ("true", "false"):
            return "bool"
        # numbers stored as strings
        try:
            int(value)
            return "number"
        except (ValueError, TypeError):
            pass
        return "string"
    if isinstance(value, list):
        return "list(string)"
    if isinstance(value, dict):
        return "any"
    if isinstance(value, int):
        return "number"
    if isinstance(value, float):
        return "number"
    return "string"


def _write_module_outputs(module_dir: Path, resource_type: str) -> None:
    """Write modules/<name>/outputs.tf — always export .id."""
    content = (
        'output "id" {\n'
        f'  value       = {resource_type}.this.id\n'
        '  description = "Resource ID"\n'
        "}\n"
    )
    _write(module_dir / "outputs.tf", content)


# ── Root file writers ─────────────────────────────────────────────────────────

def _write_root_providers(out_dir: Path) -> None:
    content = (
        'provider "aws" {\n'
        '  region = local.region\n'
        "}\n\n"
        "terraform {\n"
        "  required_providers {\n"
        "    aws = {\n"
        '      source  = "hashicorp/aws"\n'
        '      version = "~> 6.51.0"\n'
        "    }\n"
        "  }\n"
        "}\n"
    )
    _write(out_dir / "providers.tf", content)


def _write_root_locals(out_dir: Path, shared_cross_group: dict[str, Any]) -> None:
    """
    Write locals.tf with values that are constant across ALL resource groups
    (e.g. region = "us-east-1").
    """
    lines = ["locals {"]
    for key, val in sorted(shared_cross_group.items()):
        lines.append(f"  {key:<20} = {_hcl_value(val)}")
    lines.append("}\n")
    _write(out_dir / "locals.tf", "\n".join(lines))


def _write_root_variables(out_dir: Path) -> None:
    """Placeholder variables.tf — extended by later goals (default-stripping)."""
    content = (
        "# Required input variables.\n"
        "# Goal 2 (default-stripping) will populate this file with\n"
        "# account-specific values that cannot have defaults.\n"
    )
    _write(out_dir / "variables.tf", content)


def _write_root_main(
    out_dir: Path,
    groups: list[dict],
) -> None:
    """Write root main.tf: module{} calls for multi-instance groups, inline
    resource{} blocks for singletons."""
    lines: list[str] = []

    for group in groups:
        rtype = group["resource_type"]
        mname = group["module_name"]
        varying = group["varying_keys"]

        if group["is_singleton"]:
            # Write the resource directly
            inst = group["instances"][0]
            label = _resource_label(rtype, inst["resource_name"])
            lines.append(f'# (singleton) original name: {inst["resource_name"]}')
            lines.append(f'resource "{rtype}" "{label}" {{')
            for k, v in sorted(inst["attrs"].items()):
                lines.append(f"  {k} = {_hcl_value(v)}")
            lines.append("}\n")
        else:
            for inst in group["instances"]:
                label = _resource_label(rtype, inst["resource_name"])
                lines.append(f'module "{mname}_{label}" {{')
                lines.append(f'  source = "./modules/{mname}"')
                lines.append("")
                for key in sorted(varying):
                    val = inst["attrs"].get(key)
                    lines.append(f"  {key} = {_hcl_value(val)}")
                lines.append("}\n")

    _write(out_dir / "main.tf", "\n".join(lines))


def _write_root_outputs(out_dir: Path, groups: list[dict]) -> None:
    lines: list[str] = []
    for group in groups:
        rtype = group["resource_type"]
        mname = group["module_name"]
        if group["is_singleton"]:
            inst = group["instances"][0]
            label = _resource_label(rtype, inst["resource_name"])
            out_name = f"{rtype}_{label}_id"
            lines.append(f'output "{out_name}" {{')
            lines.append(f'  value = {rtype}.{label}.id')
            lines.append("}\n")
        else:
            for inst in group["instances"]:
                label = _resource_label(rtype, inst["resource_name"])
                out_name = f"{mname}_{label}_id"
                lines.append(f'output "{out_name}" {{')
                lines.append(f'  value = module.{mname}_{label}.id')
                lines.append("}\n")

    _write(out_dir / "outputs.tf", "\n".join(lines))


# ── Cross-group constant extraction ──────────────────────────────────────────

def _extract_cross_group_constants(groups: list[dict]) -> dict[str, Any]:
    """
    Find attribute keys whose value is the same across every group's shared_attrs.
    Typical example: region = "us-east-1".
    """
    if not groups:
        return {}

    # Collect shared_attrs from all groups (use union of their shared sets)
    combined: dict[str, list[Any]] = {}
    for group in groups:
        for key, val in group["shared_attrs"].items():
            combined.setdefault(key, []).append(val)

    cross: dict[str, Any] = {}
    total_groups = len(groups)
    for key, vals in combined.items():
        if len(vals) == total_groups and len(set(str(v) for v in vals)) == 1:
            cross[key] = vals[0]

    return cross


# ── Top-level emit function ───────────────────────────────────────────────────

def emit(groups: list[dict], out_dir: str | Path) -> None:
    """
    Write the full refactored module tree to *out_dir*.

    Parameters
    ----------
    groups   : output of detector.detect_module_groups()
    out_dir  : destination directory (will be created if absent)
    """
    import subprocess

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. cross-group constants → locals.tf
    cross_constants = _extract_cross_group_constants(groups)
    if not cross_constants:
        cross_constants = {"region": "us-east-1"}   # safe fallback
    _write_root_locals(out_dir, cross_constants)

    # 2. deduplicated providers.tf
    _write_root_providers(out_dir)

    # 3. placeholder variables.tf
    _write_root_variables(out_dir)

    # 4. for each multi-instance group → child module
    for group in groups:
        if not group["is_singleton"]:
            module_dir = out_dir / "modules" / group["module_name"]
            _write_module_main(
                module_dir,
                group["resource_type"],
                group["varying_keys"],
                group["shared_attrs"],
            )
            _write_module_variables(
                module_dir,
                group["varying_keys"],
                group["instances"],
            )
            _write_module_outputs(module_dir, group["resource_type"])

    # 5. root main.tf (module calls + singletons)
    _write_root_main(out_dir, groups)

    # 6. root outputs.tf
    _write_root_outputs(out_dir, groups)

    # 7. auto-format with terraform fmt (best-effort; non-fatal if unavailable)
    try:
        subprocess.run(
            ["terraform", "fmt", "-recursive", str(out_dir)],
            check=False,
            capture_output=True,
        )
    except FileNotFoundError:
        pass  # terraform not on PATH — skip formatting
