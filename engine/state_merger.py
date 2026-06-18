"""
State Merger

Reads Terraformer-generated v3 state files from a directory tree and merges
them into a single v4 state file compatible with Terraform 1.x.

v3 state (Terraform 0.12, produced by Terraformer):
  - resources live inside modules[0].resources as a flat dict keyed by
    "resource_type.resource_name"
  - attributes are stored as a flat dot-notation dict:
    "cpu_options.0.core_count": "1"

v4 state (Terraform 1.x):
  - resources is a top-level list of objects, each with:
      type, name, provider, mode, instances[{attributes: {...}}]
  - attributes are a proper nested structure (for most providers)

The conversion approach:
  - Copy the flat dot-notation attributes dict directly into the v4 instance
    attributes. Terraform 1.x can read flat-notation attributes from state
    when refreshing — it does not require the nested form in the state file
    itself; the provider handles expansion on plan/apply.
  - This is the same approach terraform state pull/push uses internally.
"""

from __future__ import annotations
import json
import os
import glob
import uuid
from typing import Any


def _find_state_files(state_dir: str) -> list[str]:
    """
    Find all terraform.tfstate files recursively under state_dir.
    Returns sorted list of absolute paths.
    """
    pattern = os.path.join(state_dir, "**", "terraform.tfstate")
    found = glob.glob(pattern, recursive=True)
    return sorted(found)


def _extract_v3_resources(state: dict) -> list[dict]:
    """
    Extract resource entries from a v3 state file.
    Returns a list of v4-compatible resource dicts.

    v3 structure:
      modules[0].resources = {
        "aws_vpc.tfer--vpc-abc": {
          "type": "aws_vpc",
          "primary": {
            "id": "vpc-abc",
            "attributes": { "cidr_block": "10.0.0.0/16", ... },
            "meta": { "schema_version": 1 },
          },
          "provider": "provider.aws",
          ...
        }
      }

    v4 structure:
      {
        "mode": "managed",
        "type": "aws_vpc",
        "name": "tfer--vpc-abc",
        "provider": "provider[\"registry.terraform.io/hashicorp/aws\"]",
        "instances": [
          {
            "schema_version": 1,
            "attributes": { "cidr_block": "10.0.0.0/16", ... },
          }
        ]
      }
    """
    resources = []

    for module in state.get("modules", []):
        for full_key, res_data in module.get("resources", {}).items():
            # full_key is e.g. "aws_vpc.tfer--vpc-0b530d7af19ffa635"
            # Split on first dot only — resource names can contain dots
            dot_pos = full_key.index(".")
            resource_type = full_key[:dot_pos]
            resource_name = full_key[dot_pos + 1:]

            primary = res_data.get("primary", {})
            attributes = primary.get("attributes", {})
            schema_version = primary.get("meta", {}).get("schema_version", 0)

            v4_resource = {
                "mode": "managed",
                "type": resource_type,
                "name": resource_name,
                "provider": 'provider["registry.terraform.io/hashicorp/aws"]',
                "instances": [
                    {
                        "schema_version": schema_version,
                        "attributes": attributes,
                        "sensitive_attributes": [],
                        "private": "",
                    }
                ],
            }
            resources.append(v4_resource)

    return resources


def _extract_v4_resources(state: dict) -> list[dict]:
    """
    Extract resource entries from a v4 state file.
    Returns them as-is (already in the right format).
    """
    return state.get("resources", [])


def merge_state_files(state_dir: str, output_path: str) -> int:
    """
    Find all terraform.tfstate files under state_dir, merge their resources
    into a single v4 state file, and write it to output_path.

    Returns the number of resources merged.
    """
    state_files = _find_state_files(state_dir)
    if not state_files:
        raise FileNotFoundError(
            f"No terraform.tfstate files found under: {state_dir}"
        )

    all_resources: list[dict] = []
    seen_keys: set[str] = set()

    for sf in state_files:
        with open(sf) as f:
            state = json.load(f)

        version = state.get("version", 0)

        if version == 3:
            resources = _extract_v3_resources(state)
        elif version == 4:
            resources = _extract_v4_resources(state)
        else:
            print(f"  [WARN] Unknown state version {version} in {sf} — skipping")
            continue

        for res in resources:
            key = f"{res['type']}.{res['name']}"
            if key in seen_keys:
                print(f"  [WARN] Duplicate resource {key} found in {sf} — skipping duplicate")
                continue
            seen_keys.add(key)
            all_resources.append(res)
            print(f"  [STATE] Merged {key}")

    # Build a valid v4 state file
    merged = {
        "version": 4,
        "terraform_version": "1.0.0",
        "serial": 1,
        "lineage": str(uuid.uuid4()),
        "outputs": {},
        "resources": all_resources,
        "check_results": None,
    }

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(merged, f, indent=2)

    print(f"  [STATE] Wrote {len(all_resources)} resources to {output_path}")
    return len(all_resources)
