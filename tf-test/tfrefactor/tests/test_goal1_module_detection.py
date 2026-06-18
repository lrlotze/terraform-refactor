"""
Tests for Goal 1: Detect & Reuse Modules.

Coverage:
  test_parser_*     — parser.py: HCL → IR
  test_detector_*   — detector.py: fingerprinting + shared/varying split
  test_emitter_*    — emitter.py: file-tree output
  test_integration  — full pipeline on the real generated.tf fixture
"""

from __future__ import annotations

import textwrap
import tempfile
from pathlib import Path

import pytest

# ── adjust sys.path so tests can import the package without installing ──────
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tfrefactor.parser import parse_files, _attr_key_fingerprint, _flatten_nested
from tfrefactor.detector import detect_module_groups, _shared_and_varying
from tfrefactor.emitter import emit, _resource_label, _extract_cross_group_constants


# ════════════════════════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════════════════════════

def _write_tf(tmp_path: Path, name: str, content: str) -> Path:
    """Helper: write a .tf file and return its Path."""
    p = tmp_path / name
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


MINIMAL_SUBNET_TF = """\
resource "aws_subnet" "sub_a" {
  cidr_block              = "10.0.1.0/24"
  vpc_id                  = "vpc-aaa"
  map_public_ip_on_launch = true
  region                  = "us-east-1"
}

resource "aws_subnet" "sub_b" {
  cidr_block              = "10.0.2.0/24"
  vpc_id                  = "vpc-bbb"
  map_public_ip_on_launch = true
  region                  = "us-east-1"
}
"""

SINGLETON_TF = """\
resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
  region     = "us-east-1"
}
"""

MIXED_TF = MINIMAL_SUBNET_TF + "\n" + SINGLETON_TF


# ════════════════════════════════════════════════════════════════════════════
# Parser tests
# ════════════════════════════════════════════════════════════════════════════

class TestParser:

    def test_parse_two_subnets(self, tmp_path):
        tf = _write_tf(tmp_path, "sub.tf", MINIMAL_SUBNET_TF)
        resources, meta = parse_files([tf])
        assert len(resources) == 2
        types = {r["resource_type"] for r in resources}
        assert types == {"aws_subnet"}

    def test_resource_attrs_present(self, tmp_path):
        tf = _write_tf(tmp_path, "sub.tf", MINIMAL_SUBNET_TF)
        resources, _ = parse_files([tf])
        names = {r["resource_name"] for r in resources}
        assert names == {"sub_a", "sub_b"}
        sub_a = next(r for r in resources if r["resource_name"] == "sub_a")
        assert sub_a["attrs"]["cidr_block"] == "10.0.1.0/24"

    def test_fingerprint_identical_for_same_schema(self, tmp_path):
        tf = _write_tf(tmp_path, "sub.tf", MINIMAL_SUBNET_TF)
        resources, _ = parse_files([tf])
        fp_a = resources[0]["_fingerprint"]
        fp_b = resources[1]["_fingerprint"]
        assert fp_a == fp_b, "same attribute-key set → same fingerprint"

    def test_fingerprint_differs_for_different_schema(self, tmp_path):
        tf = _write_tf(tmp_path, "mixed.tf", MIXED_TF)
        resources, _ = parse_files([tf])
        subnet_fp = next(r["_fingerprint"] for r in resources if r["resource_type"] == "aws_subnet")
        vpc_fp = next(r["_fingerprint"] for r in resources if r["resource_type"] == "aws_vpc")
        assert subnet_fp != vpc_fp, "different resource types → different fingerprint"

    def test_meta_blocks_collected(self, tmp_path):
        content = """\
provider "aws" {
  region = "us-east-1"
}
resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
  region     = "us-east-1"
}
"""
        tf = _write_tf(tmp_path, "p.tf", content)
        _, meta = parse_files([tf])
        kinds = {m["_kind"] for m in meta}
        assert "provider" in kinds

    def test_flatten_single_item_block(self):
        raw = [{"http_endpoint": "enabled", "http_tokens": "optional"}]
        result = _flatten_nested(raw)
        assert isinstance(result, dict)
        assert result["http_endpoint"] == "enabled"

    def test_source_file_tracked(self, tmp_path):
        tf = _write_tf(tmp_path, "sub.tf", SINGLETON_TF)
        resources, _ = parse_files([tf])
        assert resources[0]["source_file"] == str(tf)


# ════════════════════════════════════════════════════════════════════════════
# Detector tests
# ════════════════════════════════════════════════════════════════════════════

class TestDetector:

    def _make_instances(self, attr_list: list[dict]) -> list[dict]:
        return [
            {"resource_name": f"res_{i}", "attrs": a}
            for i, a in enumerate(attr_list)
        ]

    def test_shared_and_varying_basic(self):
        instances = self._make_instances([
            {"cidr_block": "10.0.1.0/24", "region": "us-east-1", "map_public_ip_on_launch": "true"},
            {"cidr_block": "10.0.2.0/24", "region": "us-east-1", "map_public_ip_on_launch": "true"},
        ])
        shared, varying = _shared_and_varying(instances)
        assert shared["region"] == "us-east-1"
        assert shared["map_public_ip_on_launch"] == "true"
        assert "cidr_block" in varying
        assert "region" not in varying

    def test_shared_and_varying_all_differ(self):
        instances = self._make_instances([
            {"cidr_block": "10.0.1.0/24"},
            {"cidr_block": "10.0.2.0/24"},
        ])
        shared, varying = _shared_and_varying(instances)
        assert shared == {}
        assert "cidr_block" in varying

    def test_shared_and_varying_all_same(self):
        instances = self._make_instances([
            {"region": "us-east-1"},
            {"region": "us-east-1"},
        ])
        shared, varying = _shared_and_varying(instances)
        assert shared == {"region": "us-east-1"}
        assert varying == []

    def test_singleton_is_flagged(self, tmp_path):
        tf = _write_tf(tmp_path, "vpc.tf", SINGLETON_TF)
        resources, _ = parse_files([tf])
        groups = detect_module_groups(resources)
        assert len(groups) == 1
        assert groups[0]["is_singleton"] is True

    def test_multi_instance_group_not_singleton(self, tmp_path):
        tf = _write_tf(tmp_path, "sub.tf", MINIMAL_SUBNET_TF)
        resources, _ = parse_files([tf])
        groups = detect_module_groups(resources)
        assert len(groups) == 1
        assert groups[0]["is_singleton"] is False
        assert len(groups[0]["instances"]) == 2

    def test_mixed_file_produces_two_groups(self, tmp_path):
        tf = _write_tf(tmp_path, "mixed.tf", MIXED_TF)
        resources, _ = parse_files([tf])
        groups = detect_module_groups(resources)
        assert len(groups) == 2

    def test_multi_instance_group_first_in_sorted_output(self, tmp_path):
        tf = _write_tf(tmp_path, "mixed.tf", MIXED_TF)
        resources, _ = parse_files([tf])
        groups = detect_module_groups(resources)
        # multi-instance groups should sort before singletons
        assert not groups[0]["is_singleton"]

    def test_varying_keys_are_module_inputs(self, tmp_path):
        tf = _write_tf(tmp_path, "sub.tf", MINIMAL_SUBNET_TF)
        resources, _ = parse_files([tf])
        groups = detect_module_groups(resources)
        g = groups[0]
        # cidr_block and vpc_id differ → must be varying
        assert "cidr_block" in g["varying_keys"]
        assert "vpc_id" in g["varying_keys"]
        # region is identical → must be shared
        assert "region" in g["shared_attrs"]


# ════════════════════════════════════════════════════════════════════════════
# Emitter tests
# ════════════════════════════════════════════════════════════════════════════

class TestEmitter:

    def _groups_for(self, tmp_path: Path, tf_content: str) -> list[dict]:
        tf = _write_tf(tmp_path, "in.tf", tf_content)
        resources, _ = parse_files([tf])
        return detect_module_groups(resources)

    def test_resource_label_strips_tfer_prefix(self):
        label = _resource_label("aws_subnet", "tfer--subnet-07e44e47643c99518")
        assert label.startswith("subnet")
        assert "tfer" not in label
        assert "--" not in label

    def test_resource_label_is_valid_identifier(self):
        label = _resource_label("aws_subnet", "tfer--subnet-07e44e47643c99518")
        assert label.replace("_", "").isalnum()

    def test_emit_creates_module_dir(self, tmp_path):
        out = tmp_path / "out"
        groups = self._groups_for(tmp_path, MINIMAL_SUBNET_TF)
        emit(groups, out)
        assert (out / "modules" / "aws_subnet").is_dir()

    def test_emit_module_main_tf_exists(self, tmp_path):
        out = tmp_path / "out"
        groups = self._groups_for(tmp_path, MINIMAL_SUBNET_TF)
        emit(groups, out)
        assert (out / "modules" / "aws_subnet" / "main.tf").exists()

    def test_emit_module_variables_tf_has_varying_keys(self, tmp_path):
        out = tmp_path / "out"
        groups = self._groups_for(tmp_path, MINIMAL_SUBNET_TF)
        emit(groups, out)
        var_text = (out / "modules" / "aws_subnet" / "variables.tf").read_text()
        assert 'variable "cidr_block"' in var_text
        assert 'variable "vpc_id"' in var_text

    def test_emit_module_outputs_tf_has_id(self, tmp_path):
        out = tmp_path / "out"
        groups = self._groups_for(tmp_path, MINIMAL_SUBNET_TF)
        emit(groups, out)
        out_text = (out / "modules" / "aws_subnet" / "outputs.tf").read_text()
        assert 'output "id"' in out_text

    def test_emit_root_providers_tf_exists(self, tmp_path):
        out = tmp_path / "out"
        groups = self._groups_for(tmp_path, MINIMAL_SUBNET_TF)
        emit(groups, out)
        assert (out / "providers.tf").exists()
        prov_text = (out / "providers.tf").read_text()
        assert 'provider "aws"' in prov_text
        # only ONE provider block (deduplication)
        assert prov_text.count('provider "aws"') == 1

    def test_emit_root_locals_has_region(self, tmp_path):
        out = tmp_path / "out"
        groups = self._groups_for(tmp_path, MINIMAL_SUBNET_TF)
        emit(groups, out)
        locals_text = (out / "locals.tf").read_text()
        assert "region" in locals_text
        assert "us-east-1" in locals_text

    def test_emit_root_main_has_module_calls(self, tmp_path):
        out = tmp_path / "out"
        groups = self._groups_for(tmp_path, MINIMAL_SUBNET_TF)
        emit(groups, out)
        main_text = (out / "main.tf").read_text()
        assert 'module "aws_subnet_' in main_text
        # Two module calls for two subnets
        assert main_text.count('module "aws_subnet_') == 2

    def test_emit_root_main_no_module_for_singleton(self, tmp_path):
        out = tmp_path / "out"
        groups = self._groups_for(tmp_path, SINGLETON_TF)
        emit(groups, out)
        main_text = (out / "main.tf").read_text()
        # singleton → resource block, not module call
        assert 'resource "aws_vpc"' in main_text
        assert "module" not in main_text

    def test_emit_root_outputs_tf_exists(self, tmp_path):
        out = tmp_path / "out"
        groups = self._groups_for(tmp_path, MINIMAL_SUBNET_TF)
        emit(groups, out)
        assert (out / "outputs.tf").exists()

    def test_emit_shared_attrs_not_in_module_variables(self, tmp_path):
        out = tmp_path / "out"
        groups = self._groups_for(tmp_path, MINIMAL_SUBNET_TF)
        emit(groups, out)
        var_text = (out / "modules" / "aws_subnet" / "variables.tf").read_text()
        # region is shared — should NOT appear as a variable
        assert 'variable "region"' not in var_text

    def test_emit_shared_attrs_inlined_in_module_main(self, tmp_path):
        out = tmp_path / "out"
        groups = self._groups_for(tmp_path, MINIMAL_SUBNET_TF)
        emit(groups, out)
        main_text = (out / "modules" / "aws_subnet" / "main.tf").read_text()
        # region is shared — should appear as a literal in the resource
        assert "us-east-1" in main_text


# ════════════════════════════════════════════════════════════════════════════
# Integration test — real generated.tf fixture
# ════════════════════════════════════════════════════════════════════════════

class TestIntegration:
    """Run the full pipeline against the actual generated.tf in the repo root."""

    @pytest.fixture
    def fixture_tf(self) -> Path:
        p = Path(__file__).parent.parent.parent / "generated.tf"
        if not p.exists():
            pytest.skip("generated.tf not found — run from tf-test root")
        return p

    def test_parses_correct_resource_count(self, fixture_tf):
        resources, _ = parse_files([fixture_tf])
        # 7 subnets + 2 VPCs + 2 IGWs + 1 EC2 = 12
        assert len(resources) == 12

    def test_detects_subnet_group(self, fixture_tf):
        resources, _ = parse_files([fixture_tf])
        groups = detect_module_groups(resources)
        subnet_group = next(
            (g for g in groups if g["resource_type"] == "aws_subnet"), None
        )
        assert subnet_group is not None
        assert len(subnet_group["instances"]) == 7
        assert not subnet_group["is_singleton"]

    def test_detects_vpc_group(self, fixture_tf):
        resources, _ = parse_files([fixture_tf])
        groups = detect_module_groups(resources)
        vpc_group = next(
            (g for g in groups if g["resource_type"] == "aws_vpc"), None
        )
        assert vpc_group is not None
        assert len(vpc_group["instances"]) == 2

    def test_detects_igw_group(self, fixture_tf):
        resources, _ = parse_files([fixture_tf])
        groups = detect_module_groups(resources)
        igw_group = next(
            (g for g in groups if g["resource_type"] == "aws_internet_gateway"), None
        )
        assert igw_group is not None
        assert len(igw_group["instances"]) == 2

    def test_ec2_instance_is_singleton(self, fixture_tf):
        resources, _ = parse_files([fixture_tf])
        groups = detect_module_groups(resources)
        ec2_group = next(
            (g for g in groups if g["resource_type"] == "aws_instance"), None
        )
        assert ec2_group is not None
        assert ec2_group["is_singleton"] is True

    def test_subnet_cidr_block_is_varying(self, fixture_tf):
        resources, _ = parse_files([fixture_tf])
        groups = detect_module_groups(resources)
        subnet_group = next(g for g in groups if g["resource_type"] == "aws_subnet")
        assert "cidr_block" in subnet_group["varying_keys"]

    def test_subnet_boolean_defaults_are_shared(self, fixture_tf):
        resources, _ = parse_files([fixture_tf])
        groups = detect_module_groups(resources)
        subnet_group = next(g for g in groups if g["resource_type"] == "aws_subnet")
        # These 8 booleans are identical across all 7 subnets → shared
        shared_keys = set(subnet_group["shared_attrs"].keys())
        expected_shared = {
            "assign_ipv6_address_on_creation",
            "enable_dns64",
            "enable_resource_name_dns_a_record_on_launch",
            "enable_resource_name_dns_aaaa_record_on_launch",
            "ipv6_native",
            "map_customer_owned_ip_on_launch",
            "map_public_ip_on_launch",
        }
        assert expected_shared.issubset(shared_keys)

    def test_full_emit_produces_all_expected_files(self, fixture_tf, tmp_path):
        resources, _ = parse_files([fixture_tf])
        groups = detect_module_groups(resources)
        out = tmp_path / "refactored"
        emit(groups, out)

        # Root files
        for fname in ["providers.tf", "locals.tf", "main.tf", "outputs.tf", "variables.tf"]:
            assert (out / fname).exists(), f"Missing root file: {fname}"

        # Module directories for every multi-instance type
        for rtype in ["aws_subnet", "aws_vpc", "aws_internet_gateway"]:
            assert (out / "modules" / rtype).is_dir(), f"Missing module dir: {rtype}"
            for fname in ["main.tf", "variables.tf", "outputs.tf"]:
                assert (out / "modules" / rtype / fname).exists(), f"Missing {rtype}/{fname}"

    def test_root_main_has_seven_subnet_calls(self, fixture_tf, tmp_path):
        resources, _ = parse_files([fixture_tf])
        groups = detect_module_groups(resources)
        out = tmp_path / "refactored"
        emit(groups, out)
        main_text = (out / "main.tf").read_text()
        # 7 subnet module calls
        calls = [l for l in main_text.splitlines() if l.strip().startswith('module "aws_subnet_')]
        assert len(calls) == 7

    def test_root_providers_deduplicated(self, fixture_tf, tmp_path):
        resources, _ = parse_files([fixture_tf])
        groups = detect_module_groups(resources)
        out = tmp_path / "refactored"
        emit(groups, out)
        prov_text = (out / "providers.tf").read_text()
        # only one provider "aws" block
        assert prov_text.count('provider "aws"') == 1
