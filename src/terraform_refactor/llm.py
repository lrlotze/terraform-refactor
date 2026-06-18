from __future__ import annotations

import json
import os
from typing import Any

try:
    import openai
except ImportError:  # pragma: no cover
    openai = None


def analyze_terraform(payload: str) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key or openai is None:
        return _local_analysis(payload, api_key is None)

    openai.api_key = api_key
    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a Terraform refactoring assistant for AWS HCL files."},
            {"role": "user", "content": payload},
        ],
        temperature=0.2,
        max_tokens=500,
    )

    choice = response.choices[0]
    if hasattr(choice, "message"):
        return choice.message.content
    return choice.text


def _local_analysis(payload: str, missing_api_key: bool) -> str:
    data = json.loads(payload)
    if missing_api_key:
        return (
            "# OpenAI API key not configured; returning placeholder analysis.\n"
            "# Review the cleaned Terraform output and replace this with a real LLM analysis when OPENAI_API_KEY is set.\n"
            f"# Detected {data.get('resource_count', 'unknown')} AWS resource block(s).\n"
            "# Suggested next steps:\n"
            "#   1. Remove explicit default values where AWS defaults are safe.\n"
            "#   2. Group repeated resource patterns into modules.\n"
            "#   3. Split flat imports into smaller files for network, compute, and networking.\n"
        )
    return "# No analysis available."
