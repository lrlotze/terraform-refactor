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
# Static group map — resource type → output file group name
# Covers both AWS (aws_*) and Azure (azurerm_*) resource types.
# Extend this dict to support additional resource types or providers.
# ---------------------------------------------------------------------------

RESOURCE_GROUP_MAP: dict[str, str] = {
    # -------------------------------------------------------------------------
    # AWS — Networking
    # -------------------------------------------------------------------------
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

    # AWS — Compute
    "aws_instance":                     "compute",
    "aws_launch_template":              "compute",
    "aws_launch_configuration":         "compute",
    "aws_autoscaling_group":            "compute",
    "aws_autoscaling_policy":           "compute",
    "aws_key_pair":                     "compute",
    "aws_placement_group":              "compute",
    "aws_spot_instance_request":        "compute",

    # AWS — Storage
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

    # AWS — Database
    "aws_db_instance":                  "database",
    "aws_db_subnet_group":              "database",
    "aws_db_parameter_group":           "database",
    "aws_db_option_group":              "database",
    "aws_rds_cluster":                  "database",
    "aws_elasticache_cluster":          "database",
    "aws_elasticache_subnet_group":     "database",
    "aws_elasticache_parameter_group":  "database",
    "aws_dynamodb_table":               "database",

    # AWS — IAM
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

    # AWS — DNS
    "aws_route53_zone":                 "dns",
    "aws_route53_record":               "dns",
    "aws_route53_health_check":         "dns",

    # AWS — Load Balancing
    "aws_lb":                           "lb",
    "aws_alb":                          "lb",
    "aws_lb_listener":                  "lb",
    "aws_alb_listener":                 "lb",
    "aws_lb_listener_rule":             "lb",
    "aws_lb_target_group":              "lb",
    "aws_alb_target_group":             "lb",
    "aws_lb_target_group_attachment":   "lb",

    # AWS — Monitoring / Alerting
    "aws_cloudwatch_metric_alarm":      "monitoring",
    "aws_cloudwatch_log_group":         "monitoring",
    "aws_cloudwatch_log_stream":        "monitoring",
    "aws_cloudwatch_dashboard":         "monitoring",
    "aws_sns_topic":                    "monitoring",
    "aws_sns_topic_subscription":       "monitoring",

    # AWS — Secrets / Config
    "aws_secretsmanager_secret":        "secrets",
    "aws_secretsmanager_secret_version": "secrets",
    "aws_ssm_parameter":                "secrets",

    # -------------------------------------------------------------------------
    # Azure — Foundation
    # -------------------------------------------------------------------------
    "azurerm_resource_group":                   "foundation",
    "azurerm_management_lock":                  "foundation",

    # Azure — Networking
    "azurerm_virtual_network":                  "networking",
    "azurerm_subnet":                           "networking",
    "azurerm_network_interface":                "networking",
    "azurerm_public_ip":                        "networking",
    "azurerm_network_security_group":           "networking",
    "azurerm_network_security_rule":            "networking",
    "azurerm_network_watcher":                  "networking",
    "azurerm_route_table":                      "networking",
    "azurerm_route":                            "networking",
    "azurerm_subnet_route_table_association":   "networking",
    "azurerm_subnet_network_security_group_association": "networking",
    "azurerm_private_endpoint":                 "networking",
    "azurerm_private_dns_zone":                 "networking",
    "azurerm_private_dns_zone_virtual_network_link": "networking",
    "azurerm_application_gateway":              "networking",
    "azurerm_firewall":                         "networking",
    "azurerm_firewall_policy":                  "networking",
    "azurerm_virtual_network_peering":          "networking",

    # Azure — Compute
    "azurerm_linux_virtual_machine":            "compute",
    "azurerm_windows_virtual_machine":          "compute",
    "azurerm_virtual_machine":                  "compute",
    "azurerm_virtual_machine_scale_set":        "compute",
    "azurerm_linux_virtual_machine_scale_set":  "compute",
    "azurerm_windows_virtual_machine_scale_set": "compute",
    "azurerm_managed_disk":                     "compute",
    "azurerm_virtual_machine_data_disk_attachment": "compute",
    "azurerm_ssh_public_key":                   "compute",
    "azurerm_image":                            "compute",

    # Azure — Storage
    "azurerm_storage_account":                  "storage",
    "azurerm_storage_container":                "storage",
    "azurerm_storage_blob":                     "storage",
    "azurerm_storage_queue":                    "storage",
    "azurerm_storage_table":                    "storage",
    "azurerm_storage_share":                    "storage",

    # Azure — Database
    "azurerm_sql_server":                       "database",
    "azurerm_sql_database":                     "database",
    "azurerm_mssql_server":                     "database",
    "azurerm_mssql_database":                   "database",
    "azurerm_postgresql_server":                "database",
    "azurerm_postgresql_database":              "database",
    "azurerm_mysql_server":                     "database",
    "azurerm_mysql_database":                   "database",
    "azurerm_cosmosdb_account":                 "database",
    "azurerm_cosmosdb_sql_database":            "database",
    "azurerm_redis_cache":                      "database",

    # Azure — App / Container
    "azurerm_app_service":                      "app",
    "azurerm_app_service_plan":                 "app",
    "azurerm_linux_web_app":                    "app",
    "azurerm_windows_web_app":                  "app",
    "azurerm_function_app":                     "app",
    "azurerm_linux_function_app":               "app",
    "azurerm_container_registry":               "app",
    "azurerm_kubernetes_cluster":               "app",
    "azurerm_kubernetes_cluster_node_pool":     "app",
    "azurerm_container_group":                  "app",

    # Azure — IAM
    "azurerm_role_assignment":                  "iam",
    "azurerm_role_definition":                  "iam",
    "azurerm_user_assigned_identity":           "iam",

    # Azure — Security / Secrets
    "azurerm_key_vault":                        "secrets",
    "azurerm_key_vault_secret":                 "secrets",
    "azurerm_key_vault_key":                    "secrets",
    "azurerm_key_vault_certificate":            "secrets",

    # Azure — Monitoring
    "azurerm_monitor_action_group":             "monitoring",
    "azurerm_monitor_metric_alert":             "monitoring",
    "azurerm_monitor_diagnostic_setting":       "monitoring",
    "azurerm_log_analytics_workspace":          "monitoring",
    "azurerm_application_insights":             "monitoring",

    # Azure — Load Balancing
    "azurerm_load_balancer":                    "lb",
    "azurerm_lb_backend_address_pool":          "lb",
    "azurerm_lb_probe":                         "lb",
    "azurerm_lb_rule":                          "lb",
    "azurerm_lb_nat_rule":                      "lb",

    # Azure — Messaging / Events
    "azurerm_eventhub_namespace":               "messaging",
    "azurerm_eventhub":                         "messaging",
    "azurerm_servicebus_namespace":             "messaging",
    "azurerm_servicebus_queue":                 "messaging",
    "azurerm_servicebus_topic":                 "messaging",

    # Azure — Data / Analytics
    "azurerm_data_factory":                     "data",
    "azurerm_databricks_workspace":             "data",
    "azurerm_synapse_workspace":                "data",
    "azurerm_purview_account":                  "data",
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
