# terraform-refactor

A deterministic Terraform refactoring engine that transforms noisy, Terraformer-generated `.tf` files into clean, modular, production-ready Terraform configuration — **without changing infrastructure behavior**.

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
| `tf-refactor` | *"refactor my generated.tf"* | Refactors existing Terraformer output you already have |

The engine is symlinked from the cloned repo — run `git pull` at any time to pick up updates. No reinstall needed.

**Prerequisites:** `python3`, `terraform`, `terraformer`, AWS credentials configured.

## Use Case

Importing external infrastructure into Terraform (e.g. via [Terraformer](https://github.com/GoogleCloudPlatform/terraformer)) produces bloated files filled with:
- Dozens of explicit attributes that equal provider defaults
- Duplicate `provider` and `terraform` blocks (one per resource type)
- `output` blocks for every resource ID (cross-module Terraformer exports)
- `data "terraform_remote_state"` cross-references between split modules
- Hard-coded AWS resource IDs in computed attributes
- All resources in a single flat file with no logical organization

This tool transforms that output into clean, split `.tf` files that `terraform plan` will verify produce **zero infrastructure changes**.

## How It Works

The engine runs a staged, **deterministic** pipeline:

```
generated.tf
  → [1] Parse          HCL → typed Python object model
  → [2] Denoise        remove Terraformer artifacts (duplicates, outputs, remote-state refs)
  → [3] Strip defaults remove attributes whose values exactly match provider defaults
  → [4] Group          assign each resource to a logical file (networking, compute, ...)
  → [5] Emit           write one clean .tf file per group
  → [6] State          (optional) merge per-module .tfstate files into a single terraform.tfstate
```

**Key principle: `SAFETY > CORRECTNESS > CLEANLINESS`**  
If there is any uncertainty about whether an attribute is safe to remove, it is preserved.

## Usage

```bash
python3 engine/main.py <input.tf> <output_dir>

# Also merge Terraformer state files so terraform plan works immediately
python3 engine/main.py <input.tf> <output_dir> --state-dir <terraformer_generated_dir>

# Dry-run (prints plan without writing files)
python3 engine/main.py <input.tf> <output_dir> --dry-run

# Run against the included example
python3 engine/main.py examples/aws-basic/generated.tf examples/aws-basic/output \
  --state-dir examples/aws-basic/generated/aws
```

After running, validate and format:
```bash
cd examples/aws-basic/output
terraform fmt .
terraform init
terraform plan   # should show: No changes.
```

## Output Files

| File | Contents |
|---|---|
| `provider.tf` | Single `provider "aws"` + `terraform {}` block |
| `networking.tf` | VPCs, subnets, internet gateways, route tables, security groups |
| `compute.tf` | EC2 instances, launch templates, autoscaling groups |
| `storage.tf` | S3 buckets, EBS volumes |
| `database.tf` | RDS instances, ElastiCache clusters |
| `iam.tf` | IAM roles, policies, instance profiles |
| `dns.tf` | Route53 zones and records |
| `lb.tf` | Load balancers, target groups, listeners |
| `misc.tf` | Any resource type not in the grouping map (fallback) |

Only files with at least one resource are written.

## What Gets Removed

### Terraformer noise (always removed)
- All `output` blocks — these are Terraformer cross-module ID exports, not real outputs
- Duplicate `provider "aws"` blocks — one is kept, the rest dropped
- Duplicate `terraform { required_providers {} }` blocks — one is kept
- All `data "terraform_remote_state"` blocks — replaced with direct resource references
- `primary_network_interface` nested block on `aws_instance` — computed, hard-coded ENI ID
- `placement_partition_number` on `aws_instance` — read-only computed attribute

### Default values (removed only when exactly matching registry)
Cross-referenced against [`engine/defaults_registry.json`](engine/defaults_registry.json):

| Resource | Removed attributes (when matching default) |
|---|---|
| `aws_subnet` | `assign_ipv6_address_on_creation`, `enable_dns64`, `enable_lni_at_device_index`, `enable_resource_name_dns_a_record_on_launch`, `enable_resource_name_dns_aaaa_record_on_launch`, `ipv6_native`, `map_customer_owned_ip_on_launch`, `private_dns_hostname_type_on_launch` |
| `aws_vpc` | `assign_generated_ipv6_cidr_block`, `enable_dns_support`, `enable_dns_hostnames` (if false), `enable_network_address_usage_metrics`, `instance_tenancy`, `ipv6_netmask_length` |
| `aws_instance` | `disable_api_stop/termination`, `ebs_optimized`, `get_password_data`, `hibernation`, `instance_initiated_shutdown_behavior`, `ipv6_address_count`, `monitoring`, `source_dest_check`, `tenancy`; nested: `capacity_reservation_specification`, `enclave_options`, `maintenance_options`, `metadata_options`, `private_dns_name_options`, `root_block_device` (partial) |
| Any resource | `region` (when matches provider region — always a Terraformer artifact) |

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
  grouper.py                 Static RESOURCE_GROUP_MAP + group assignment
  emitter.py                 Renders groups to .tf files
  state_merger.py            Merges Terraformer v3 state files into a single v4 state
  defaults_registry.json     Curated defaults: resource_type → attribute → default_value

tests/
  test_pipeline.py           71 correctness assertions against the aws-basic example

examples/
  aws-basic/
    generated.tf             Messy Terraformer input (test fixture)
    main.tf                  Hand-written reference showing minimal clean config
    generated/aws/           Terraformer per-module state files (source of truth for IDs)
```

## Extending the Defaults Registry

Edit [`engine/defaults_registry.json`](engine/defaults_registry.json) to add coverage for more resource types:

```json
{
  "aws_s3_bucket": {
    "force_destroy": false,
    "object_lock_enabled": false
  }
}
```

Values must be Python-native types: `true`/`false` for booleans, numbers without quotes, strings with quotes. Cross-check every entry against the [Terraform AWS provider docs](https://registry.terraform.io/providers/hashicorp/aws/latest/docs) before adding.

## Extending the Grouping Map

Edit `RESOURCE_GROUP_MAP` in [`engine/grouper.py`](engine/grouper.py) to add new resource types. Any type not in the map falls into `misc.tf`.

## Testing

```bash
# Run the pipeline against the included example
python3 engine/main.py examples/aws-basic/generated.tf examples/aws-basic/output \
  --state-dir examples/aws-basic/generated/aws

# Run the correctness test suite (71 assertions)
python3 tests/test_pipeline.py
```

## Known Limitations

- Resource labels are not renamed (e.g. `tfer--subnet-07e44e47643c99518` is preserved)
- No `variables.tf` generation
- `cpu_options` and `credit_specification` are preserved (instance-type-dependent defaults)
- `volume_type = "gp2"` is preserved (safe default ambiguity)

## Contributors

- Lucas Lotze
- Christopher Myers
- Brian Thompson
- Austin Wu
- Joe Yang
- Brian Yee
