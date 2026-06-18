from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .llm import analyze_terraform
from .parser import load_tf_files


def run_refactor(source: Path, output: Path, dry_run: bool = False) -> None:
    files = load_tf_files(source)
    if not files:
        raise ValueError(f"No Terraform files found in source: {source}")

    output.mkdir(parents=True, exist_ok=True)
    summary: list[str] = [f"Analyzing {len(files)} Terraform file(s) from {source}"]

    for tf_path, content in files.items():
        summary.append(f"Found Terraform file: {tf_path.name}")
        resource_count = len(_extract_resources(content))
        summary.append(f"  resources: {resource_count}")

        cleaned_content = _clean_parsed_content(content)
        hcl_text = _format_hcl(cleaned_content)
        analysis_input = _build_analysis_payload(tf_path.name, content, cleaned_content)
        analysis_text = analyze_terraform(analysis_input)

        if not dry_run:
            destination = output / tf_path.name
            destination.write_text(hcl_text, encoding="utf-8")
            summary.append(f"  wrote cleaned Terraform: {destination}")

            report_file = output / f"{tf_path.stem}_analysis.tf"
            report_file.write_text(_format_analysis_report(analysis_text), encoding="utf-8")
            summary.append(f"  wrote analysis report: {report_file}")

    print("Refactor summary:")
    for line in summary:
        print(line)


def _extract_resources(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    return parsed.get("resource", []) or []


def _clean_parsed_content(parsed: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}

    for block_type, block_list in parsed.items():
        if not isinstance(block_list, list):
            cleaned[block_type] = block_list
            continue

        cleaned_blocks: list[dict[str, Any]] = []
        for block in block_list:
            cleaned_block = {}
            for name, body in block.items():
                if isinstance(body, dict):
                    cleaned_block[name] = _normalize_resource_body(body)
                else:
                    cleaned_block[name] = body
            cleaned_blocks.append(cleaned_block)
        cleaned[block_type] = cleaned_blocks

    return cleaned


def _normalize_resource_body(body: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in sorted(body.items()):
        if key in {"id", "arn", "owner_id"}:
            continue
        normalized[key] = value
    return normalized


def _build_analysis_payload(filename: str, original: dict[str, Any], cleaned: dict[str, Any]) -> str:
    payload = {
        "filename": filename,
        "provider": "aws",
        "original_blocks": original,
        "cleaned_blocks": cleaned,
        "instructions": (
            "Analyze the Terraform file and provide a concise set of AWS-specific refactoring recommendations. "
            "Identify where default values can be removed, where identical resources or variables can be grouped, "
            "and whether any module structure improvements are appropriate. "
            "Produce the answer in Terraform comment style using # comments."
        ),
    }
    return json.dumps(payload, indent=2)


def _format_analysis_report(analysis: str) -> str:
    lines = ["# Terraform LLM analysis report", "#"""]
    if analysis.strip():
        for line in analysis.splitlines():
            if line.strip():
                if line.startswith("#"):
                    lines.append(line)
                else:
                    lines.append(f"# {line}")
    else:
        lines.append("# No analysis available.")
    return "\n".join(lines)


def _format_hcl(parsed: dict[str, Any]) -> str:
    lines: list[str] = []
    for block_type, block_list in parsed.items():
        if not isinstance(block_list, list):
            continue

        for block in block_list:
            for name, body in block.items():
                lines.append(f"{block_type} {name} {{")
                if isinstance(body, dict):
                    for key, value in body.items():
                        lines.append(f"  {key} = {json.dumps(value)}")
                else:
                    lines.append(f"  {body}")
                lines.append("}")
                lines.append("")
    return "\n".join(lines).strip()
