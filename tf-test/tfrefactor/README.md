# tfrefactor

AI-assisted Terraform refactoring tool made for the IBM Austin 2026 Bob-a-thon.

Converts Terraformer-generated `.tf` files — which are verbose, flat, and full of
AWS-default noise — into clean, idiomatic Terraform IaC with reusable modules,
deduplicated providers, and parameterised inputs.

---

## Table of contents

1. [Background — what problem this solves](#1-background--what-problem-this-solves)
2. [Repository layout](#2-repository-layout)
3. [Setup](#3-setup)
4. [Pipeline walkthrough — step by step](#4-pipeline-walkthrough--step-by-step)
   - [Step 1 · Parse](#step-1--parse--parsepy)
   - [Step 2 · Detect](#step-2--detect--detectorpy)
   - [Step 3 · Emit](#step-3--emit--emitterpy)
   - [Step 4 · CLI](#step-4--cli--clipy)
5. [Output structure](#5-output-structure)
6. [Concrete before / after examples](#6-concrete-before--after-examples)
7. [Testing — commands and what to check](#7-testing--commands-and-what-to-check)
8. [Known limitations and future goals](#8-known-limitations-and-future-goals)

---

## 1. Background — what problem this solves

[Terraformer](https://github.com/GoogleCloudPlatform/terraformer) is a tool that
reverse-engineers live AWS infrastructure into `.tf` files.  The output is
technically valid Terraform but is not maintainable IaC:

| Problem | Example from the generated files |
|---|---|
| Every AWS default is written out explicitly | `assign_ipv6_address_on_creation = "false"`, `monitoring = "false"` |
| Opaque resource names tied to AWS IDs | `aws_subnet.tfer--subnet-07e44e47643c99518` |
| Structurally identical resources are copied verbatim | 7 `aws_subnet` blocks that differ only in `cidr_block` and `vpc_id` |
| Provider block duplicated in every module directory | 4 × `provider "aws" { region = "us-east-1" }` |
| All resources in one giant flat file | No logical separation |

`tfrefactor` runs a deterministic pipeline over those files and produces a
canonical, modular Terraform layout where identical-structure resources share one
reusable module definition, constants are factored into `locals {}`, and providers
are consolidated to a single block.

---

## 2. Repository layout

```
tfrefactor/
├── requirements.txt              # pinned dependencies (see §3)
├── README.md                     # this file
├── src/
│   └── tfrefactor/
│       ├── __init__.py           # re-exports public API
│       ├── parser.py             # Step 1 — HCL → Python IR
│       ├── detector.py           # Step 2 — fingerprint + group analysis
│       ├── emitter.py            # Step 3 — write refactored file tree
│       └── cli.py                # Step 4 — argparse entry point
└── tests/
    └── test_goal1_module_detection.py
```

The three core modules (`parser`, `detector`, `emitter`) are independent and
testable in isolation.  The CLI is a thin wrapper that wires them together.

---

## 3. Setup

```bash
cd tfrefactor

# Install the two dependencies
pip3 install -r requirements.txt
```

**Why `python-hcl2==4.3.4` is pinned:**
`python-hcl2` v8.x wraps every dict key in extra quotes, producing
`'"aws_subnet"'` instead of `'aws_subnet'`, which breaks all downstream
lookups.  Version 4.3.4 parses cleanly.  Do not upgrade without testing.

---

## 4. Pipeline walkthrough — step by step

The pipeline has four stages.  The diagram below shows data flowing through them:

```
.tf files on disk
      │
      ▼
┌─────────────┐   list[ResourceBlock]   ┌──────────────┐   list[ModuleGroup]
│  parser.py  │ ─────────────────────► │ detector.py  │ ──────────────────►
└─────────────┘                        └──────────────┘
                                                             │
                                                             ▼
                                                      ┌─────────────┐
                                                      │ emitter.py  │ ── refactored/ tree
                                                      └─────────────┘
                                                             ▲
                                                      ┌─────────────┐
                                                      │   cli.py    │ (orchestrates all three)
                                                      └─────────────┘
```

---

### Step 1 · Parse — `parser.py`

**What it does:**
Opens every `.tf` file with `python-hcl2` and converts each `resource {}` block
into a normalised Python dict called a **ResourceBlock**.

**ResourceBlock shape:**
```python
{
    "resource_type": "aws_subnet",
    "resource_name": "tfer--subnet-07e44e47643c99518",
    "attrs": {
        "cidr_block":              "10.0.1.0/24",
        "vpc_id":                  "${data.terraform_remote_state.vpc.outputs…}",
        "assign_ipv6_address_on_creation": "false",
        "map_public_ip_on_launch": "true",
        # … all other top-level attributes …
    },
    "source_file": "/path/to/generated.tf",
    "_fingerprint": frozenset({"cidr_block", "vpc_id", "assign_ipv6…", …})
}
```

**Key internal functions:**

| Function | Purpose |
|---|---|
| `parse_files(paths)` | Main entry point. Returns `(resources, meta)`. |
| `parse_directory(dir)` | Convenience wrapper — globs all `*.tf` in a directory. |
| `_flatten_nested(value)` | `hcl2` wraps single-item blocks in a list: `metadata_options {}` becomes `[{…}]`. This unwraps it to a plain dict so nested attributes are accessible without indexing. |
| `_attr_key_fingerprint(attrs)` | Returns `frozenset(attrs.keys())` — the structural "shape" of a resource, used by the detector to identify matching resources. |

Non-`resource` blocks (`provider`, `data`, `output`, `terraform`, `locals`) are
collected in a separate `meta` list so they can be inspected or reproduced later.

**Example — running the parser directly:**
```bash
cd tfrefactor
python3 - <<'EOF'
import sys; sys.path.insert(0, "src")
from tfrefactor.parser import parse_files
resources, meta = parse_files(["../generated.tf"])
print(f"{len(resources)} resources, {len(meta)} meta blocks")
for r in resources[:3]:
    print(f"  {r['resource_type']}.{r['resource_name']}  ({len(r['attrs'])} attrs)")
EOF
```

Expected output:
```
12 resources, 12 meta blocks
  aws_internet_gateway.tfer--igw-08b3758623655a0a4  (2 attrs)
  aws_internet_gateway.tfer--igw-0eaf698dea923f44f  (2 attrs)
  aws_instance.tfer--i-0353d2dea60f9c1e1_  (26 attrs)
```

---

### Step 2 · Detect — `detector.py`

**What it does:**
Groups all ResourceBlocks by `(resource_type, fingerprint)`.  For every group it
computes which attributes are **shared** (same value across every instance) vs
**varying** (differ in at least one instance).

**Key internal functions:**

| Function | Purpose |
|---|---|
| `detect_module_groups(resources)` | Main entry point. Returns a list of ModuleGroup dicts. |
| `_shared_and_varying(instances)` | Intersects all instance attribute dicts to find constants; the remainder are inputs. |
| `_values_are_equal(a, b)` | Equality that normalises Terraformer's string booleans (`"false"`) to native Python bools so `"false" == False` and both are treated as shared. |
| `_safe_module_name(resource_type)` | Converts `aws_internet_gateway` to the directory-safe name `aws_internet_gateway`. |

**ModuleGroup shape:**
```python
{
    "resource_type": "aws_subnet",
    "module_name":   "aws_subnet",          # becomes the modules/ subdirectory name
    "instances": [
        {"resource_name": "tfer--subnet-01…", "attrs": {…}},
        {"resource_name": "tfer--subnet-02…", "attrs": {…}},
        # … 5 more …
    ],
    "shared_attrs": {                        # inlined as literals in module main.tf
        "assign_ipv6_address_on_creation": "false",
        "enable_dns64":                    "false",
        "map_public_ip_on_launch":         "true",
        "region":                          "us-east-1",
        # … 6 more …
    },
    "varying_keys": ["cidr_block", "vpc_id"],  # become variable{} inputs
    "is_singleton": False,
}
```

**Fingerprint logic explained:**

Two resources share a fingerprint when they have exactly the same set of
top-level attribute *keys* (not values).  The 7 `aws_subnet` blocks in
`generated.tf` all have the same 12 keys so their fingerprint is identical.
The `aws_instance` block has 26 different keys — its fingerprint is unique, so
it stays a singleton.

```
aws_subnet (×7):
  fingerprint = frozenset({
    "assign_ipv6_address_on_creation", "cidr_block", "enable_dns64",
    "enable_lni_at_device_index", "enable_resource_name_dns_a_record_on_launch",
    "enable_resource_name_dns_aaaa_record_on_launch", "ipv6_native",
    "map_customer_owned_ip_on_launch", "map_public_ip_on_launch",
    "private_dns_hostname_type_on_launch", "region", "vpc_id"
  })
  → all 7 land in the same bucket → one ModuleGroup, is_singleton=False

aws_instance (×1):
  fingerprint = frozenset({"ami", "associate_public_ip_address", "availability_zone",
                            "capacity_reservation_specification", …26 keys total…})
  → unique fingerprint → one ModuleGroup, is_singleton=True
```

**Example — running the detector directly:**
```bash
cd tfrefactor
python3 - <<'EOF'
import sys; sys.path.insert(0, "src")
from tfrefactor.parser import parse_files
from tfrefactor.detector import detect_module_groups
resources, _ = parse_files(["../generated.tf"])
groups = detect_module_groups(resources)
for g in groups:
    tag = "singleton" if g["is_singleton"] else f"{len(g['instances'])} instances"
    print(f"  {g['resource_type']:<30} ({tag})")
    if not g["is_singleton"]:
        print(f"    varying : {g['varying_keys']}")
        print(f"    shared  : {list(g['shared_attrs'].keys())[:4]} …")
EOF
```

Expected output:
```
  aws_internet_gateway           (2 instances)
    varying : ['vpc_id']
    shared  : ['region'] …
  aws_subnet                     (7 instances)
    varying : ['cidr_block', 'vpc_id']
    shared  : ['assign_ipv6_address_on_creation', 'enable_dns64', 'enable_lni_at_device_index', 'enable_resource_name_dns_a_record_on_launch'] …
  aws_vpc                        (2 instances)
    varying : ['cidr_block', 'enable_dns_hostnames']
    shared  : ['assign_generated_ipv6_cidr_block', 'enable_dns_support', 'enable_network_address_usage_metrics', 'instance_tenancy'] …
  aws_instance                   (singleton)
```

---

### Step 3 · Emit — `emitter.py`

**What it does:**
Converts the list of ModuleGroups into files on disk.  Every multi-instance group
gets a child module directory; singletons are written inline in the root
`main.tf`.  After writing, it runs `terraform fmt -recursive` on the output
directory to guarantee canonical formatting.

**Key internal functions:**

| Function | Output file | Purpose |
|---|---|---|
| `_write_module_main(...)` | `modules/<name>/main.tf` | Parameterised `resource "…" "this"` block. Varying attrs reference `var.<key>`; shared attrs are inlined as literals. |
| `_write_module_variables(...)` | `modules/<name>/variables.tf` | One `variable {}` block per varying key. Type is inferred from the first instance value via `_infer_type()`. |
| `_write_module_outputs(...)` | `modules/<name>/outputs.tf` | Always exports `.id` so callers can chain references. |
| `_write_root_providers(...)` | `providers.tf` | Single `provider "aws"` + `terraform {}` block, referencing `local.region`. Replaces all duplicated per-module provider blocks. |
| `_write_root_locals(...)` | `locals.tf` | Attributes that are constant across *all* groups (e.g. `region = "us-east-1"`) extracted by `_extract_cross_group_constants()`. |
| `_write_root_variables(...)` | `variables.tf` | Placeholder, populated by Goal 2 (default-stripping). |
| `_write_root_main(...)` | `main.tf` | One `module {}` call per instance for multi-instance groups; inline `resource {}` for singletons. |
| `_write_root_outputs(...)` | `outputs.tf` | One `output {}` per resource/module instance, delegating to `module.<name>.id` or `resource_type.<label>.id`. |

**`_extract_cross_group_constants` logic:**

After computing `shared_attrs` for every group separately, this function finds
attributes that appear in *every* group's `shared_attrs` with the *same value*.
In the generated fixture, `region = "us-east-1"` is shared by all four resource
types, so it ends up in `locals.tf` and is removed from each module's `main.tf`.

**`_infer_type` logic:**

Terraformer emits all values as strings (`"false"`, `"0"`, `"t3.micro"`).
`_infer_type` inspects the first instance's value to decide what HCL type to
declare in `variable {}` blocks:

| Sample value | Inferred type |
|---|---|
| `"true"` / `"false"` | `bool` |
| `"8"` / `"1"` | `number` |
| `"10.0.1.0/24"` | `string` |
| `["sg-abc"]` | `list(string)` |
| `{…}` (nested block) | `any` |

---

### Step 4 · CLI — `cli.py`

**What it does:**
Orchestrates the three steps above behind an `argparse` interface.  Prints a
human-readable summary of detected groups before writing output.

```
usage: python -m tfrefactor.cli <input> [--out <dir>]

positional arguments:
  input       path to a .tf file OR a directory containing .tf files

optional arguments:
  --out DIR   output directory (default: ./refactored)
```

**Summary output explained:**

```
── Module Detection Summary ──────────────────────────────────

  ✓ 3 reusable module(s) detected:

    • aws_subnet  (7 instances)
      varying inputs : cidr_block, vpc_id          ← will become variable{} blocks
      shared (fixed) : assign_ipv6_…, enable_dns64, …  ← inlined as literals

  ℹ  1 singleton resource(s) (written inline to root main.tf):
    • aws_instance.tfer--i-0353d2dea60f9c1e1_
```

The `varying inputs` line lists the attributes that differ per instance — these
will be exposed as required inputs on the module.  The `shared (fixed)` line
lists attributes that are the same for every instance — these are baked into the
module's `main.tf` and do not need to be passed at call time.

---

## 5. Output structure

Running the tool against `generated.tf` produces:

```
refactored/
├── providers.tf              # single provider "aws" + terraform{} block
├── locals.tf                 # region = "us-east-1"
├── variables.tf              # placeholder (Goal 2 will populate this)
├── main.tf                   # module{} calls + singleton resources
├── outputs.tf                # one output per instance / resource
└── modules/
    ├── aws_internet_gateway/
    │   ├── main.tf           # resource "aws_internet_gateway" "this" { vpc_id = var.vpc_id … }
    │   ├── variables.tf      # variable "vpc_id" { type = string }
    │   └── outputs.tf        # output "id" { value = aws_internet_gateway.this.id }
    ├── aws_subnet/
    │   ├── main.tf           # resource "aws_subnet" "this" { cidr_block = var.cidr_block … }
    │   ├── variables.tf      # variable "cidr_block" + variable "vpc_id"
    │   └── outputs.tf
    └── aws_vpc/
        ├── main.tf           # resource "aws_vpc" "this" { cidr_block = var.cidr_block … }
        ├── variables.tf      # variable "cidr_block" + variable "enable_dns_hostnames"
        └── outputs.tf
```

The `aws_instance` is a singleton — it has no module directory; it appears
directly in the root `main.tf`.

---

## 6. Concrete before / after examples

### aws_subnet — before (7 identical blocks, 12 attrs each)

```hcl
# generated.tf (84 lines just for subnets)
resource "aws_subnet" "tfer--subnet-01a84979be17b1c4e" {
  assign_ipv6_address_on_creation                = "false"
  cidr_block                                     = "172.31.32.0/20"
  enable_dns64                                   = "false"
  enable_lni_at_device_index                     = "0"
  enable_resource_name_dns_a_record_on_launch    = "false"
  enable_resource_name_dns_aaaa_record_on_launch = "false"
  ipv6_native                                    = "false"
  map_customer_owned_ip_on_launch                = "false"
  map_public_ip_on_launch                        = "true"
  private_dns_hostname_type_on_launch            = "ip-name"
  region                                         = "us-east-1"
  vpc_id = "${data.terraform_remote_state.vpc.outputs.aws_vpc_tfer--vpc-0d6abae348aa13541_id}"
}
# … 6 more identical-structure blocks …
```

### aws_subnet — after (1 module definition + 7 lightweight calls)

**`refactored/modules/aws_subnet/main.tf`** — the single reusable definition:
```hcl
resource "aws_subnet" "this" {
  cidr_block                                     = var.cidr_block
  vpc_id                                         = var.vpc_id
  assign_ipv6_address_on_creation                = "false"
  enable_dns64                                   = "false"
  enable_lni_at_device_index                     = "0"
  enable_resource_name_dns_a_record_on_launch    = "false"
  enable_resource_name_dns_aaaa_record_on_launch = "false"
  ipv6_native                                    = "false"
  map_customer_owned_ip_on_launch                = "false"
  map_public_ip_on_launch                        = "true"
  private_dns_hostname_type_on_launch            = "ip-name"
  region                                         = "us-east-1"
}
```

**`refactored/modules/aws_subnet/variables.tf`** — only the 2 inputs that vary:
```hcl
variable "cidr_block" {
  type        = string
  description = ""
}

variable "vpc_id" {
  type        = string
  description = ""
}
```

**`refactored/main.tf`** — 7 calls, each just 4 lines:
```hcl
module "aws_subnet_subnet_01a84979be17b1c4e" {
  source = "./modules/aws_subnet"

  cidr_block = "172.31.32.0/20"
  vpc_id     = data.terraform_remote_state.vpc.outputs.aws_vpc_tfer--vpc-0d6abae348aa13541_id
}

module "aws_subnet_subnet_02553d65232c646ec" {
  source = "./modules/aws_subnet"

  cidr_block = "172.31.0.0/20"
  vpc_id     = data.terraform_remote_state.vpc.outputs.aws_vpc_tfer--vpc-0d6abae348aa13541_id
}
# … 5 more …
```

### providers — before (4 duplicate blocks) → after (1 block)

**Before** — copied verbatim into every module directory:
```hcl
# repeated 4 times across generated/aws/*/provider.tf
provider "aws" {
  region = "us-east-1"
}
terraform {
  required_providers {
    aws = { version = "~> 6.51.0" }
  }
}
```

**After** — one canonical `refactored/providers.tf`:
```hcl
provider "aws" {
  region = local.region
}
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.51.0"
    }
  }
}
```

Region is now referenced from `locals.tf` instead of hardcoded:
```hcl
# refactored/locals.tf
locals {
  region = "us-east-1"
}
```

---

## 7. Testing — commands and what to check

### Install and run all tests

```bash
cd tfrefactor
pip3 install -r requirements.txt

# Run the full test suite with verbose output
python3 -m pytest tests/ -v
```

Expected: **38 passed**.

### Run a single test class

```bash
# Parser tests only
python3 -m pytest tests/ -v -k TestParser

# Detector tests only
python3 -m pytest tests/ -v -k TestDetector

# Emitter tests only
python3 -m pytest tests/ -v -k TestEmitter

# Integration tests against the real generated.tf
python3 -m pytest tests/ -v -k TestIntegration
```

### What each test class checks

| Class | Tests | What failure means |
|---|---|---|
| `TestParser` | 7 | HCL is not being parsed, fingerprints are wrong, nested blocks are not being flattened |
| `TestDetector` | 8 | Shared/varying split is incorrect, singletons are not flagged, grouping is broken |
| `TestEmitter` | 13 | Wrong files are being created, module directories are missing, attribute placement is wrong |
| `TestIntegration` | 10 | Full pipeline fails on the real fixture; counts of groups/instances are wrong |

### Run the CLI end-to-end

```bash
cd tfrefactor
PYTHONPATH=src python3 -m tfrefactor.cli ../generated.tf --out ../refactored
```

**Check the summary output:**
- Should report `3 reusable module(s) detected`
- `aws_subnet (7 instances)` with `varying inputs: cidr_block, vpc_id`
- `aws_instance` listed as a singleton

**Check the output files:**
```bash
# File tree — should show 14 files
find ../refactored -type f | sort

# Verify terraform fmt passes (exit 0 = no formatting issues)
terraform fmt -check -recursive ../refactored/
echo "terraform fmt exit code: $?"

# Count module calls in root main.tf — should be 11 (7 subnets + 2 VPCs + 2 IGWs)
grep -c '^module ' ../refactored/main.tf

# Confirm only 1 provider block (was 4)
grep -c 'provider "aws"' ../refactored/providers.tf
```

### Re-run the pipeline cleanly

If you want to regenerate from scratch:
```bash
rm -rf ../refactored/
PYTHONPATH=src python3 -m tfrefactor.cli ../generated.tf --out ../refactored
terraform fmt -check -recursive ../refactored/
```

---

## 8. Known limitations and future goals

| Limitation | Impact | Planned fix |
|---|---|---|
| `enable_lni_at_device_index = "0"` and similar non-boolean defaults are **not stripped** | Module `main.tf` still contains AWS defaults that should be omitted | Goal 2: fetch provider schema via `terraform providers schema -json` and strip attributes that match defaults |
| Resource names still embed AWS IDs (`subnet_01a84979be17b1c4e`) | Names are readable but not semantic | Goal 2 / LLM step: use CIDR / AZ context to generate human names like `subnet_us_east_1a_public` |
| Singleton blocks (e.g. `aws_instance`) still retain all 26 attributes including defaults | EC2 block is noisy | Goal 2 will strip defaults from singletons too |
| `vpc_id` still references `data.terraform_remote_state` — cross-module wiring is not upgraded | Not portable outside the original account | Goal 3: consolidate cross-module references into proper `module.<name>.id` chains |
| `variable {}` blocks have empty `description` fields | Reduces usefulness as documentation | LLM step: generate descriptions from attribute names and resource context |
