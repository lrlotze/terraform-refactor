"""
Emitter

Renders grouped blocks back to HCL files and writes them to the output directory.
One .tf file per group. provider.tf is written first.

Each file gets a header comment identifying the group.
"""

from __future__ import annotations
import os
from parser import Block
from parser import render_block


# Group names that get a descriptive header comment
_GROUP_DESCRIPTIONS: dict[str, str] = {
    # Shared / generic
    "provider":   "Terraform provider configuration and version constraints",
    "misc":       "Uncategorised resources",

    # AWS
    "networking": "VPC, subnets, internet gateways, and other network resources",
    "compute":    "EC2 / virtual machine instances and related compute resources",
    "storage":    "S3 buckets, EBS volumes, and other storage resources",
    "database":   "RDS, ElastiCache, Cosmos DB, and other database resources",
    "iam":        "IAM roles, policies, and identity resources",
    "dns":        "Route53 zones, DNS records, and private DNS resources",
    "lb":         "Load balancers, target groups, and listeners",
    "monitoring": "CloudWatch, Azure Monitor alarms, log groups, and alerting resources",
    "secrets":    "Key Vault, Secrets Manager, and SSM Parameter Store resources",

    # Azure-specific
    "foundation": "Resource groups and subscription-level management resources",
    "app":        "App Service, Function Apps, AKS, and container resources",
    "messaging":  "Event Hub, Service Bus, and messaging resources",
    "data":       "Data Factory, Databricks, Synapse, and analytics resources",
}


def _file_header(group: str) -> str:
    desc = _GROUP_DESCRIPTIONS.get(group, f"{group} resources")
    return f"# {desc}\n"


def emit(groups: dict[str, list[Block]], output_dir: str) -> None:
    """
    Write one .tf file per group into output_dir.

    Args:
        groups:     dict of group_name → list[Block], as returned by group_resources()
        output_dir: directory path to write output files into (created if needed)
    """
    os.makedirs(output_dir, exist_ok=True)

    # Determine write order: provider first, then alphabetical, misc last
    def sort_key(name: str) -> tuple[int, str]:
        if name == "provider":
            return (0, name)
        if name == "misc":
            return (2, name)
        return (1, name)

    ordered = sorted(groups.keys(), key=sort_key)

    written: list[str] = []
    for group in ordered:
        blocks = groups[group]
        if not blocks:
            continue

        filename = f"{group}.tf"
        filepath = os.path.join(output_dir, filename)

        rendered_blocks = []
        for block in blocks:
            rendered_blocks.append(render_block(block))

        content = _file_header(group) + "\n" + "\n\n".join(rendered_blocks) + "\n"

        with open(filepath, "w") as f:
            f.write(content)

        written.append(filename)

    print(f"  [INFO] Wrote {len(written)} file(s) to {output_dir}: {', '.join(written)}")
