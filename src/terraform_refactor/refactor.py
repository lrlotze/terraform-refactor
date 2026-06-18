from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .llm import analyze_terraform
from .parser import load_tf_files

_DEFAULT_RESOURCE_DEFAULTS = {
    "aws_subnet": {
        "map_public_ip_on_launch": "false",
    },
    "aws_instance": {
        "associate_public_ip_address": "false",
        "disable_api_termination": "false",
        "ebs_optimized": "false",
    },
    "aws_internet_gateway": {
        "tags": "{}",
    },
}


def run_refactor(source: Path, output: Path, dry_run: bool = False) -> None:
    files = load_tf_files(source)
    if not files:
        raise ValueError(f"No Terraform files found in source: {source}")

    output.mkdir(parents=True, exist_ok=True)
    summary: list[str] = [f"Analyzing {len(files)} Terraform file(s) from {source}"]

    for tf_path, raw_text in files.items():
        summary.append(f"Found Terraform file: {tf_path.name}")
        resource_count = _count_resource_blocks(raw_text)
        summary.append(f"  resources: {resource_count}")

        cleaned_text = _clean_raw_text(raw_text)
        cleaned_text = _apply_aws_default_cleanup(cleaned_text)
        analysis_input = _build_analysis_payload(tf_path.name, cleaned_text, resource_count)
        analysis_text = analyze_terraform(analysis_input)

        if not dry_run:
            destination = output / tf_path.name
            destination.write_text(cleaned_text, encoding="utf-8")
            summary.append(f"  wrote cleaned Terraform: {destination}")

            report_file = output / f"{tf_path.stem}_analysis.tf"
            report_file.write_text(_format_analysis_report(analysis_text), encoding="utf-8")
            summary.append(f"  wrote analysis report: {report_file}")

    print("Refactor summary:")
    for line in summary:
        print(line)


def _count_resource_blocks(raw_text: str) -> int:
    return len(re.findall(r'^resource\s+"[^"]+"\s+"[^"]+"', raw_text, flags=re.MULTILINE))


def _clean_raw_text(raw_text: str) -> str:
    cleaned = raw_text.replace('\r\n', '\n').strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"^([ \t]+)#", r"#", cleaned, flags=re.MULTILINE)
    if not cleaned.endswith("\n"):
        cleaned += "\n"
    return cleaned


def _apply_aws_default_cleanup(raw_text: str) -> str:
    blocks = _extract_resource_blocks(raw_text)
    cleaned_text = raw_text
    for resource_type, resource_name, block_text in blocks:
        cleaned_block = _cleanup_resource_block(resource_type, block_text)
        if cleaned_block != block_text:
            cleaned_text = cleaned_text.replace(block_text, cleaned_block)
    return cleaned_text


def _extract_resource_blocks(raw_text: str) -> list[tuple[str, str, str]]:
    blocks: list[tuple[str, str, str]] = []
    lines = raw_text.splitlines()
    i = 0
    while i < len(lines):
        match = re.match(r'^resource\s+"([^"]+)"\s+"([^"]+)"\s*{', lines[i].strip())
        if match:
            resource_type, name = match.group(1), match.group(2)
            block_lines = [lines[i]]
            depth = lines[i].count('{') - lines[i].count('}')
            i += 1
            while i < len(lines) and depth > 0:
                line = lines[i]
                depth += line.count('{') - line.count('}')
                block_lines.append(line)
                i += 1
            blocks.append((resource_type, name, '\n'.join(block_lines) + '\n'))
        else:
            i += 1
    return blocks


def _cleanup_resource_block(resource_type: str, block_text: str) -> str:
    defaults = _DEFAULT_RESOURCE_DEFAULTS.get(resource_type, {})
    if not defaults:
        return block_text

    cleaned_lines: list[str] = []
    for line in block_text.splitlines():
        stripped = line.strip()
        removed = False
        for key, default_value in defaults.items():
            if re.match(rf'^{re.escape(key)}\s*=\s*{re.escape(default_value)}$', stripped):
                removed = True
                break
        if not removed:
            cleaned_lines.append(line)
    cleaned_block = '\n'.join(cleaned_lines).rstrip() + '\n'
    return cleaned_block


def _build_analysis_payload(filename: str, cleaned_text: str, resource_count: int) -> str:
    payload = {
        "filename": filename,
        "provider": "aws",
        "resource_count": resource_count,
        "cleaned_hcl": cleaned_text,
        "instructions": (
            "You are an AWS Terraform refactoring assistant. Analyze the supplied Terraform content and provide a concise set "
            "of refactoring recommendations. Identify where default values can be removed, where identical resources or variables "
            "can be grouped, and whether any module structure improvements are appropriate. Return the answer in Terraform comment style "
            "using # comments and keep it actionable."
        ),
    }
    return json.dumps(payload, indent=2)


def _format_analysis_report(analysis: str) -> str:
    lines = ["# Terraform LLM analysis report", "#"]
    if analysis.strip():
        for line in analysis.splitlines():
            stripped = line.rstrip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                lines.append(stripped)
            else:
                lines.append(f"# {stripped}")
    else:
        lines.append("# No analysis available.")
    return "\n".join(lines) + "\n"
