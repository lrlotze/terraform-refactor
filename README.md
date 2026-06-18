# terraform-refactor

A deterministic Terraform refactoring engine that transforms noisy, Terraformer-generated `.tf` files into clean, modular, production-ready Terraform configuration — **without changing infrastructure behavior**.

Supports both **AWS** (`hashicorp/aws`) and **Azure** (`hashicorp/azurerm`) providers.

## Install (Bob AI skills)

Install once, then use from any workspace by telling Bob *"convert my AWS infrastructure to Terraform"* or *"refactor my generated.tf"*.

```bash
git clone https://github.com/lucaslotze/terraform-refactor ~/tools/terraform-refactor
cd ~/tools/terraform-refactor
./install.sh
```

This installs two Bob skills globally (`~/.bob/skills/`):

| Skill | Trigger phrase | What it does |
|---|---|---|
| `aws-to-iac` | *"convert my AWS to Terraform"* | Runs Terraformer against live AWS, then refactors the output to clean IaC |
| `tf-refactor` | *"refactor my generated.tf"* | Refactors existing Terraformer output you already have (AWS or Azure) |

The engine is symlinked from the cloned repo — run `git pull` at any time to pick up updates. No reinstall needed.

**Prerequisites:** `python3`, `terraform`, `terraformer`, cloud credentials configured (AWS or Azure).

## Use Case

Importing external infrastructure into Terraform (e.g. via [Terraformer](https://github.com/GoogleCloudPlatform/terraformer)) produces bloated files filled with:
- Dozens of explicit attributes that equal provider defaults
- Duplicate `provider` and `terraform` blocks (one per resource type)
- `output` blocks for every resource ID (cross-module Terraformer exports)
- `data "terraform_remote_state"` cross-references between split modules
- Hard-coded cloud resource IDs in computed attributes
- All resources in a single flat file with no logical organization

This tool transforms that output into clean, split `.tf` files that `terraform plan` will verify produce **zero infrastructure changes**.

## How It Works

The full flow produces three runtime artifacts that do not exist in the repo — they are created on each run:

| Path | Created by | Purpose |
|---|---|---|
| `generated/` | Terraformer | Raw per-resource-type directories, each with its own `.tf`, `variables.tf`, `outputs.tf`, `provider.tf`, and `terraform.tfstate` files |
| `generated/generated.tf` | Pre-processing step | Single merged `.tf` file built by concatenating all resource files from `generated/` — this is the engine's input |
| `output/` | This engine | Clean, split, production-ready `.tf` files (one per logical group) plus a merged `terraform.tfstate` |

The engine itself runs a staged, **deterministic** pipeline against `generated.tf`:

```
generated/<provider>/**/*.tf  (Terraformer raw output)
  → merge             cat resource files → generated/generated.tf
  → [1] Parse          HCL → typed Python object model
  → [2] Denoise        remove Terraformer artifacts (duplicates, outputs, remote-state refs)
  → [3] Strip defaults remove attributes whose values exactly match provider defaults
  → [4] Group          assign each resource to a logical file (networking, compute, ...)
  → [5] Emit           write one clean .tf file per group → output/
  → [6] State          merge per-module .tfstate files → output/terraform.tfstate
```

**Key principle: `SAFETY > CORRECTNESS > CLEANLINESS`**
If there is any uncertainty about whether an attribute is safe to remove, it is preserved.

## Usage

### AWS

**Step 1 — Run Terraformer** to import live AWS infrastructure into `generated/`:
```bash
terraformer import aws --resources=vpc,subnet,igw,ec2_instance,sg,route_table \
  --regions=us-east-1 --path-output=./generated
```

**Step 2 — Merge** the Terraformer resource files into a single input file:
```bash
find ./generated/aws -name "*.tf" \
  -not -name "variables.tf" -not -name "outputs.tf" -not -name "provider.tf" \
  | sort | xargs cat > ./generated/generated.tf
```

**Step 3 — Run the engine** to produce clean IaC in `output/`:
```bash
python3 engine/main.py ./generated/generated.tf ./output --state-dir ./generated/aws

# Dry-run (prints plan without writing files)
python3 engine/main.py ./generated/generated.tf ./output --dry-run
```

**Step 4 — Validate:**
```bash
cd ./output
terraform fmt .
terraform init
terraform plan   # should show: No changes.
```

### Azure

**Step 1 — Run Terraformer** to import live Azure infrastructure into `generated/`:
```bash
# Authenticate first
az login

terraformer import azure --resources=resource_group,virtual_network,subnet,virtual_machine,network_interface,network_security_group \
  --regions=eastus --path-output=./generated
```

**Step 2 — Merge** the Terraformer resource files:
```bash
find ./generated/azurerm -name "*.tf" \
  -not -name "variables.tf" -not -name "outputs.tf" -not -name "provider.tf" \
  | sort | xargs cat > ./generated/generated.tf
```

**Step 3 — Run the engine:**
```bash
python3 engine/main.py ./generated/generated.tf ./output --state-dir ./generated/azurerm
```

**Step 4 — Validate:**
```bash
cd ./output
terraform fmt .
terraform init
terraform plan   # should show: No changes.
```

## Output Files

### AWS output files

| File | Contents |
|---|---|
| `provider.tf` | `provider "aws"` and `terraform {}` blocks (de-duplicated) |
| `networking.tf` | VPCs, subnets, internet gateways, route tables, security groups |
| `compute.tf` | EC2 instances, launch templates, autoscaling groups |
| `storage.tf` | S3 buckets, EBS volumes |
| `database.tf` | RDS instances, ElastiCache clusters |
| `iam.tf` | IAM roles, policies, instance profiles |
| `dns.tf` | Route53 zones and records |
| `lb.tf` | Load balancers, target groups, listeners |
| `monitoring.tf` | CloudWatch alarms, log groups, SNS topics |
| `secrets.tf` | Secrets Manager and SSM Parameter Store resources |
| `misc.tf` | Any resource type not in the grouping map (fallback) |

### Azure output files

| File | Contents |
|---|---|
| `provider.tf` | `provider "azurerm"` and `terraform {}` blocks (de-duplicated) |
| `foundation.tf` | Resource groups, virtual networks, subnets, NSGs, route tables, public IPs |
| `app.tf` | Virtual machines, network interfaces, scale sets, App Service plans and apps |
| `messaging.tf` | Service Bus namespaces/queues/topics, Event Hubs, storage accounts and queues |
| `data.tf` | SQL servers/databases, Cosmos DB, Redis, PostgreSQL, MySQL, Storage containers/blobs |
| `misc.tf` | Any resource type not in the grouping map (fallback) |

Only files with at least one resource are written.

## What Gets Removed

### Terraformer noise (always removed)
- All `output` blocks — these are Terraformer cross-module ID exports, not real outputs
- Duplicate `provider` blocks — one is kept, the rest dropped
- Duplicate `terraform { required_providers {} }` blocks — one is kept
- All `data "terraform_remote_state"` blocks — replaced with direct resource references
- `primary_network_interface` nested block on `aws_instance` — computed, hard-coded ENI ID
- `placement_partition_number` on `aws_instance` — read-only computed attribute

### AWS provider v5 deprecated attributes (always removed)
- `enable_classiclink` and `enable_classiclink_dns_support` on `aws_vpc` — removed in provider v5, Terraformer still emits them

### Default values (removed only when exactly matching registry)
Cross-referenced against [`engine/defaults_registry.json`](engine/defaults_registry.json).

The special sentinel value `"__DROP__"` marks attributes that must always be removed regardless
of their current value (e.g. deprecated attributes that Terraformer emits but providers reject).

#### AWS defaults

| Resource | Removed attributes (when matching default) |
|---|---|
| `aws_subnet` | `assign_ipv6_address_on_creation`, `enable_dns64`, `enable_lni_at_device_index`, `enable_resource_name_dns_a_record_on_launch`, `enable_resource_name_dns_aaaa_record_on_launch`, `ipv6_native`, `map_customer_owned_ip_on_launch`, `private_dns_hostname_type_on_launch` |
| `aws_vpc` | `assign_generated_ipv6_cidr_block`, `enable_dns_support`, `enable_dns_hostnames` (if false), `enable_network_address_usage_metrics`, `instance_tenancy`, `ipv6_netmask_length` |
| `aws_instance` | `disable_api_stop/termination`, `ebs_optimized`, `get_password_data`, `hibernation`, `instance_initiated_shutdown_behavior`, `ipv6_address_count`, `monitoring`, `source_dest_check`, `tenancy`; `cpu_core_count`/`cpu_threads_per_core` (when `cpu_options` block present); nested: `capacity_reservation_specification`, `enclave_options`, `maintenance_options`, `metadata_options`, `private_dns_name_options`, `root_block_device` (partial) |
| Any resource | `region` (when matches provider region — always a Terraformer artifact) |

#### Azure defaults

| Resource | Removed attributes (when matching default) |
|---|---|
| `azurerm_virtual_network` | `dns_servers`, `edge_zone`, `flow_timeout_in_minutes` |
| `azurerm_subnet` | `private_endpoint_network_policies`, `private_link_service_network_policies_enabled`, `service_endpoint_policy_ids`, `service_endpoints` |
| `azurerm_network_security_group` | `tags` (empty map) |
| `azurerm_public_ip` | `allocation_method`, `idle_timeout_in_minutes`, `ip_version`, `sku`, `sku_tier`, `zones` |
| `azurerm_network_interface` | `enable_accelerated_networking`, `enable_ip_forwarding` (always `__DROP__` — deprecated in favour of the `ip_configuration` block) |
| `azurerm_linux_virtual_machine` | `allow_extension_operations`, `encryption_at_host_enabled`, `eviction_policy`, `extensions_time_budget`, `patch_assessment_mode`, `patch_mode`, `priority`, `provision_vm_agent`, `secure_boot_enabled`, `vtpm_enabled`, `zone` |
| `azurerm_windows_virtual_machine` | `allow_extension_operations`, `encryption_at_host_enabled`, `enable_automatic_updates`, `eviction_policy`, `extensions_time_budget`, `hotpatching_enabled`, `patch_assessment_mode`, `patch_mode`, `priority`, `provision_vm_agent`, `secure_boot_enabled`, `vtpm_enabled`, `zone` |
| `azurerm_storage_account` | `access_tier`, `allow_nested_items_to_be_public`, `cross_tenant_replication_enabled`, `default_to_oauth_authentication`, `edge_zone`, `infrastructure_encryption_enabled`, `is_hns_enabled`, `large_file_share_enabled`, `min_tls_version`, `nfsv3_enabled`, `public_network_access_enabled`, `sftp_enabled`, `shared_access_key_enabled`, `table_encryption_key_type` |

## What Is Preserved (by design)

- `cpu_options` (`core_count`, `threads_per_core`) — instance-type-dependent
- `credit_specification` (`cpu_credits`) — instance-type-dependent
- `volume_type = "gp2"` — not in registry; removing it could silently change disk type on re-apply
- `volume_size` — not a default; always configuration
- `associate_public_ip_address` — subnet-dependent, not a global default
- `availability_zone` — placement decision, not a default
- `private_ip` — explicit configuration
- All attributes not listed in the defaults registry

## Architecture

```
engine/                      Python package — the refactoring pipeline
  main.py                    CLI entry point, pipeline orchestration
  parser.py                  HCL tokeniser, block parser, type coercer, renderer
  noise_remover.py           Terraformer artifact removal + reference rewriter
  default_remover.py         Registry-driven attribute stripping
  registry.py                Loads defaults_registry.json, type-aware is_default()
  grouper.py                 Static RESOURCE_GROUP_MAP + group assignment (AWS + Azure)
  emitter.py                 Renders groups to .tf files
  state_merger.py            Merges Terraformer v3/v4 state files; multi-provider aware
  defaults_registry.json     Curated defaults: resource_type → attribute → default_value

examples/
  aws-basic/
    main.tf                  Hand-written reference — minimal clean AWS config
    generated/aws/           (runtime) raw Terraformer output — produced by Terraformer
    output/                  (runtime) refactored output — produced by the engine
  azure-basics/
    main.tf                  Hand-written reference — minimal clean Azure config
    generated/azurerm/       (runtime) raw Terraformer output — produced by Terraformer
    output/                  (runtime) refactored output — produced by the engine
```

## Extending the Defaults Registry

Edit [`engine/defaults_registry.json`](engine/defaults_registry.json) to add coverage for more resource types:

```json
{
  "aws_s3_bucket": {
    "force_destroy": false,
    "object_lock_enabled": false
  },
  "azurerm_key_vault": {
    "enable_rbac_authorization": false,
    "enabled_for_deployment": false
  }
}
```

Values must be standard JSON types: `true`/`false` for booleans, numbers without quotes, strings with quotes.
Use `"__DROP__"` as the value to unconditionally remove an attribute regardless of its value (e.g. deprecated attributes that Terraformer still emits but the provider rejects).

Cross-check every entry against the provider docs before adding:
- [Terraform AWS provider docs](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [Terraform AzureRM provider docs](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs)

## Extending the Grouping Map

Edit `RESOURCE_GROUP_MAP` in [`engine/grouper.py`](engine/grouper.py) to add new resource types. Any type not in the map falls into `misc.tf`. The map covers both `aws_*` and `azurerm_*` prefixes.

## Known Limitations

- Resource labels are not renamed (e.g. `tfer--subnet-07e44e47643c99518` is preserved)
- No `variables.tf` generation
- AWS: `cpu_options` and `credit_specification` are preserved (instance-type-dependent defaults)
- AWS: `volume_type = "gp2"` is preserved (safe default ambiguity)
- Azure: `features {}` block in `provider "azurerm"` is preserved as-is from Terraformer output

## Contributors

- Lucas Lotze
- Christopher Myers
- Brian Thompson
- Austin Wu
- Joe Yang
- Brian Yee
