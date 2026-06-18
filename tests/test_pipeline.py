"""
Pipeline correctness tests.
Run with: python3 tests/test_pipeline.py

Requires the pipeline to have already been run:
    python3 engine/main.py examples/aws-basic/generated.tf examples/aws-basic/output

All checks print PASS/FAIL and exit 1 if any fail.
"""
import sys
import os
import re

# Add engine/ to path so we can import the parser directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))

from parser import parse_hcl, ResourceBlock

# ---------------------------------------------------------------------------
# Load files
# ---------------------------------------------------------------------------

ROOT    = os.path.join(os.path.dirname(__file__), "..")
EXAMPLE = os.path.join(ROOT, "examples", "aws-basic")
OUTPUT  = os.path.join(EXAMPLE, "output")

_missing = [
    p for p in [
        os.path.join(EXAMPLE, "generated.tf"),
        os.path.join(OUTPUT, "networking.tf"),
        os.path.join(OUTPUT, "compute.tf"),
    ]
    if not os.path.isfile(p)
]
if _missing:
    print("ERROR: fixture files not found — run the pipeline first:")
    print("  python3 engine/main.py examples/aws-basic/generated.tf examples/aws-basic/output")
    for p in _missing:
        print(f"  missing: {p}")
    sys.exit(1)

with open(os.path.join(EXAMPLE, "generated.tf")) as f:
    original = parse_hcl(f.read())

with open(os.path.join(OUTPUT, "networking.tf")) as f:
    net = parse_hcl(f.read())

with open(os.path.join(OUTPUT, "compute.tf")) as f:
    comp = parse_hcl(f.read())

output_blocks = net.blocks + comp.blocks
original_resources = [b for b in original.blocks if isinstance(b, ResourceBlock)]
output_resources   = [b for b in output_blocks  if isinstance(b, ResourceBlock)]

passed = 0
failed = 0


def check(label, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  PASS  {label}")
        passed += 1
    else:
        print(f"  FAIL  {label}" + (f": {detail}" if detail else ""))
        failed += 1


# ---------------------------------------------------------------------------
# 1. Resource count preserved
# ---------------------------------------------------------------------------
print("\n[1] Resource count")
check("12 resource blocks in → 12 out",
      len(original_resources) == len(output_resources),
      f"original={len(original_resources)} output={len(output_resources)}")

# ---------------------------------------------------------------------------
# 2. VPC default-stripping correctness (the most critical test)
# ---------------------------------------------------------------------------
print("\n[2] VPC default-stripping")
vpcs = {b.resource_name: b for b in output_resources if b.resource_type == "aws_vpc"}

# vpc-0b530: enable_dns_hostnames = "false" → equals default → must be REMOVED
vpc_a = vpcs.get("tfer--vpc-0b530d7af19ffa635")
if vpc_a:
    check("enable_dns_hostnames stripped from vpc-0b530 (was false = default)",
          "enable_dns_hostnames" not in vpc_a.attributes)
    check("cidr_block preserved on vpc-0b530",
          "cidr_block" in vpc_a.attributes)
    check("vpc-0b530 has only cidr_block (all other defaults removed)",
          list(vpc_a.attributes.keys()) == ["cidr_block"],
          f"got: {list(vpc_a.attributes.keys())}")
else:
    check("vpc-0b530 found in output", False, "not found")

# vpc-0d6a: enable_dns_hostnames = "true" → differs from default → must be PRESERVED
vpc_b = vpcs.get("tfer--vpc-0d6abae348aa13541")
if vpc_b:
    check("enable_dns_hostnames preserved on vpc-0d6a (was true ≠ default)",
          "enable_dns_hostnames" in vpc_b.attributes and
          vpc_b.attributes["enable_dns_hostnames"].typed_value is True)
    check("cidr_block preserved on vpc-0d6a",
          "cidr_block" in vpc_b.attributes)
    check("vpc-0d6a has exactly cidr_block + enable_dns_hostnames",
          set(vpc_b.attributes.keys()) == {"cidr_block", "enable_dns_hostnames"},
          f"got: {list(vpc_b.attributes.keys())}")
else:
    check("vpc-0d6a found in output", False, "not found")

# ---------------------------------------------------------------------------
# 3. Subnet attribute minimization
# ---------------------------------------------------------------------------
print("\n[3] Subnet attribute minimization")
subnets = [b for b in output_resources if b.resource_type == "aws_subnet"]
check("7 subnets in output", len(subnets) == 7, f"got {len(subnets)}")

for s in subnets:
    allowed = {"cidr_block", "vpc_id", "map_public_ip_on_launch"}
    extra   = set(s.attributes.keys()) - allowed
    check(f"{s.resource_name}: no unexpected attrs",
          not extra, f"extra: {extra}")
    check(f"{s.resource_name}: has cidr_block",
          "cidr_block" in s.attributes)
    check(f"{s.resource_name}: has vpc_id",
          "vpc_id" in s.attributes)

# ---------------------------------------------------------------------------
# 4. Remote-state references fully rewritten
# ---------------------------------------------------------------------------
print("\n[4] Remote-state reference removal")
RAW_REMOTE_STATE = re.compile(r'terraform_remote_state')

remote_state_leaks = []
for b in output_resources:
    for attr in b.attributes.values():
        if RAW_REMOTE_STATE.search(str(attr.typed_value)):
            remote_state_leaks.append(f"{b.resource_type}.{b.resource_name}.{attr.key}")
    for nb in b.nested_blocks:
        for attr in nb.attributes.values():
            if RAW_REMOTE_STATE.search(str(attr.typed_value)):
                remote_state_leaks.append(f"{b.resource_name}.{nb.block_type}.{attr.key}")

check("no terraform_remote_state references remain in output",
      not remote_state_leaks,
      f"leaks: {remote_state_leaks}")

# ---------------------------------------------------------------------------
# 5. Direct reference format
# ---------------------------------------------------------------------------
print("\n[5] Direct reference format")
REF_RE = re.compile(r'^aws_[a-z_]+\.tfer--[\w-]+\.[a-z_]+$')

bad_refs = []
for b in output_resources:
    for key, attr in b.attributes.items():
        v = str(attr.typed_value)
        if "tfer--" in v and not REF_RE.match(v):
            bad_refs.append(f"{b.resource_name}.{key} = {v!r}")

check("all tfer-- references are bare aws_type.name.attr expressions",
      not bad_refs, f"bad: {bad_refs}")

# Specifically check a known vpc_id
subnet_07 = next((b for b in output_resources
                  if b.resource_name == "tfer--subnet-07e44e47643c99518"), None)
if subnet_07:
    vpc_id_val = subnet_07.attributes.get("vpc_id", None)
    check("subnet-07e vpc_id = aws_vpc.tfer--vpc-0b530d7af19ffa635.id",
          vpc_id_val and vpc_id_val.typed_value == "aws_vpc.tfer--vpc-0b530d7af19ffa635.id",
          f"got: {vpc_id_val.typed_value if vpc_id_val else 'MISSING'}")

# Check subnet_id on ec2 instance
instance = next((b for b in output_resources if b.resource_type == "aws_instance"), None)
if instance:
    sid = instance.attributes.get("subnet_id")
    check("aws_instance subnet_id is a direct reference",
          sid and REF_RE.match(str(sid.typed_value)),
          f"got: {sid.typed_value if sid else 'MISSING'}")

# ---------------------------------------------------------------------------
# 6. EC2 instance correctness
# ---------------------------------------------------------------------------
print("\n[6] EC2 instance")
instances = [b for b in output_resources if b.resource_type == "aws_instance"]
check("exactly 1 aws_instance", len(instances) == 1)

if instances:
    inst = instances[0]
    nb_types = [nb.block_type for nb in inst.nested_blocks]

    # Must-have flat attrs
    for must in ["ami", "instance_type", "subnet_id", "availability_zone",
                 "associate_public_ip_address", "private_ip", "vpc_security_group_ids"]:
        check(f"aws_instance has {must}", must in inst.attributes)

    # Must-not-have (defaults stripped)
    for must_not in ["disable_api_stop", "disable_api_termination", "ebs_optimized",
                     "get_password_data", "hibernation", "monitoring",
                     "instance_initiated_shutdown_behavior", "ipv6_address_count",
                     "source_dest_check", "tenancy", "placement_partition_number", "region"]:
        check(f"aws_instance {must_not} stripped",
              must_not not in inst.attributes,
              f"still present with value: {inst.attributes[must_not].typed_value if must_not in inst.attributes else ''}")

    # Nested blocks: all-default blocks must be fully dropped
    for dropped_block in ["primary_network_interface", "capacity_reservation_specification",
                          "enclave_options", "maintenance_options", "metadata_options",
                          "private_dns_name_options"]:
        check(f"aws_instance nested block '{dropped_block}' removed",
              dropped_block not in nb_types,
              f"still present")

    # Instance-type-dependent blocks must be preserved
    for kept_block in ["cpu_options", "credit_specification"]:
        check(f"aws_instance nested block '{kept_block}' preserved (instance-type-dependent)",
              kept_block in nb_types)

    # root_block_device survives (volume_size + volume_type are not defaults)
    check("aws_instance root_block_device preserved",
          "root_block_device" in nb_types)

    rbd = next((nb for nb in inst.nested_blocks if nb.block_type == "root_block_device"), None)
    if rbd:
        check("root_block_device has volume_size", "volume_size" in rbd.attributes)
        check("root_block_device has volume_type", "volume_type" in rbd.attributes)
        check("root_block_device delete_on_termination stripped (= default true)",
              "delete_on_termination" not in rbd.attributes)
        check("root_block_device encrypted stripped (= default false)",
              "encrypted" not in rbd.attributes)

# ---------------------------------------------------------------------------
# 7. Internet gateway region stripped
# ---------------------------------------------------------------------------
print("\n[7] Internet gateway cleanup")
igws = [b for b in output_resources if b.resource_type == "aws_internet_gateway"]
check("2 internet gateways in output", len(igws) == 2)
for igw in igws:
    check(f"igw {igw.resource_name}: region stripped", "region" not in igw.attributes)
    check(f"igw {igw.resource_name}: vpc_id present",  "vpc_id" in igw.attributes)

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
total = passed + failed
print(f"\n{'='*50}")
print(f"Results: {passed}/{total} passed" + (f"  ({failed} FAILED)" if failed else " — all green"))
print(f"{'='*50}")
sys.exit(0 if failed == 0 else 1)
