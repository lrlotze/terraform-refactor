from __future__ import annotations

import json
import os
from typing import Any

import openai


def _get_openai_client() -> Any:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY environment variable is required for LLM analysis.")
    openai.api_key = api_key
    return openai


def analyze_terraform(payload: str) -> str:
    client = _get_openai_client()
    response = client.ChatCompletion.create(
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
