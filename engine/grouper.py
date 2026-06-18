"""
Resource Grouper

Maps each ResourceBlock to a logical output file group using a static
deterministic lookup table. No inference, no AI — pure dict lookup.

Ungrouped resource types fall into the "misc" group.
Provider and terraform blocks are assigned to the "provider" group.
"""

from __future__ import annotations
from parser import HCLFile, ResourceBlock, ProviderBlock, TerraformBlock, Block


# ---------------------------------------------------------------------------
# Static group map — AWS resource type → output file group name
# Extend this dict to support additional resource types.
# ---------------------------------------------------------------------------

RESOURCE_GROUP_MAP: dict[str, str] = {
    # Networking
    "aws_vpc":                          "networking",
    "aws_subnet":                       "networking",
    "aws_internet_gateway":             "networking",
    "aws_route_table":                  "networking",
    "aws_route":                        "networking",
    "aws_route_table_association":      "networking",
    "aws_security_group":               "networking",
    "aws_security_group_rule":          "networking",
    "aws_network_acl":                  "networking",
    "aws_network_acl_rule":             "networking",
    "aws_eip":                          "networking",
    "aws_nat_gateway":                  "networking",
    "aws_vpc_peering_connection":       "networking",
    "aws_vpn_gateway":                  "networking",
    "aws_customer_gateway":             "networking",
    "aws_vpn_connection":               "networking",
    "aws_flow_log":                     "networking",

    # Compute
    "aws_instance":                     "compute",
    "aws_launch_template":              "compute",
    "aws_launch_configuration":         "compute",
    "aws_autoscaling_group":            "compute",
    "aws_autoscaling_policy":           "compute",
    "aws_key_pair":                     "compute",
    "aws_placement_group":              "compute",
    "aws_spot_instance_request":        "compute",

    # Storage
    "aws_s3_bucket":                    "storage",
    "aws_s3_bucket_policy":             "storage",
    "aws_s3_bucket_acl":                "storage",
    "aws_s3_bucket_versioning":         "storage",
    "aws_s3_object":                    "storage",
    "aws_ebs_volume":                   "storage",
    "aws_ebs_snapshot":                 "storage",
    "aws_volume_attachment":            "storage",
    "aws_efs_file_system":              "storage",
    "aws_efs_mount_target":             "storage",

    # Database
    "aws_db_instance":                  "database",
    "aws_db_subnet_group":              "database",
    "aws_db_parameter_group":           "database",
    "aws_db_option_group":              "database",
    "aws_rds_cluster":                  "database",
    "aws_elasticache_cluster":          "database",
    "aws_elasticache_subnet_group":     "database",
    "aws_elasticache_parameter_group":  "database",
    "aws_dynamodb_table":               "database",

    # IAM
    "aws_iam_role":                     "iam",
    "aws_iam_policy":                   "iam",
    "aws_iam_role_policy":              "iam",
    "aws_iam_role_policy_attachment":   "iam",
    "aws_iam_instance_profile":         "iam",
    "aws_iam_user":                     "iam",
    "aws_iam_user_policy":              "iam",
    "aws_iam_group":                    "iam",
    "aws_iam_group_membership":         "iam",
    "aws_iam_access_key":               "iam",

    # DNS
    "aws_route53_zone":                 "dns",
    "aws_route53_record":               "dns",
    "aws_route53_health_check":         "dns",

    # Load Balancing
    "aws_lb":                           "lb",
    "aws_alb":                          "lb",
    "aws_lb_listener":                  "lb",
    "aws_alb_listener":                 "lb",
    "aws_lb_listener_rule":             "lb",
    "aws_lb_target_group":              "lb",
    "aws_alb_target_group":             "lb",
    "aws_lb_target_group_attachment":   "lb",

    # Monitoring / Alerting
    "aws_cloudwatch_metric_alarm":      "monitoring",
    "aws_cloudwatch_log_group":         "monitoring",
    "aws_cloudwatch_log_stream":        "monitoring",
    "aws_cloudwatch_dashboard":         "monitoring",
    "aws_sns_topic":                    "monitoring",
    "aws_sns_topic_subscription":       "monitoring",

    # Secrets / Config
    "aws_secretsmanager_secret":        "secrets",
    "aws_secretsmanager_secret_version": "secrets",
    "aws_ssm_parameter":                "secrets",
}

FALLBACK_GROUP = "misc"
PROVIDER_GROUP = "provider"


def group_resources(hcl_file: HCLFile) -> dict[str, list[Block]]:
    """
    Assign each block in the HCLFile to a named group.

    Returns a dict mapping group_name → list of blocks.
    Groups are only present in the dict if they contain at least one block.

    Assignment rules (in priority order):
      1. ProviderBlock / TerraformBlock  → "provider"
      2. ResourceBlock with known type   → RESOURCE_GROUP_MAP[resource_type]
      3. ResourceBlock with unknown type → FALLBACK_GROUP ("misc")
      4. All other blocks (Data, Output) → FALLBACK_GROUP
         (noise_remover should have already removed outputs and remote-state data)
    """
    groups: dict[str, list[Block]] = {}

    def add(group: str, block: Block) -> None:
        groups.setdefault(group, []).append(block)

    for block in hcl_file.blocks:
        if isinstance(block, (ProviderBlock, TerraformBlock)):
            add(PROVIDER_GROUP, block)

        elif isinstance(block, ResourceBlock):
            group = RESOURCE_GROUP_MAP.get(block.resource_type, FALLBACK_GROUP)
            add(group, block)

        else:
            # Data blocks that survived noise removal, or anything else
            add(FALLBACK_GROUP, block)

    return groups
