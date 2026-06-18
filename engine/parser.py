"""
HCL Parser for Terraform files.

Produces a structured Python object model from .tf file text.
Handles nested blocks, type coercion, and round-trip rendering.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Union
import re


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Attribute:
    """A single key = value pair inside a block."""
    key: str
    raw_value: str        # original text as it appeared in the file (quoted string, number, etc.)
    typed_value: Any      # coerced Python value (bool, int, float, str, list)


@dataclass
class NestedBlock:
    """A labeled sub-block inside a resource, e.g. metadata_options { ... }"""
    block_type: str                          # e.g. "metadata_options"
    labels: list[str]                        # optional labels (rare in resource nested blocks)
    attributes: dict[str, Attribute] = field(default_factory=dict)
    nested_blocks: list["NestedBlock"] = field(default_factory=list)


@dataclass
class ResourceBlock:
    resource_type: str                       # e.g. "aws_vpc"
    resource_name: str                       # e.g. "tfer--vpc-0b530d7af19ffa635"
    attributes: dict[str, Attribute] = field(default_factory=dict)
    nested_blocks: list[NestedBlock] = field(default_factory=list)


@dataclass
class ProviderBlock:
    provider_name: str                       # e.g. "aws"
    attributes: dict[str, Attribute] = field(default_factory=dict)
    nested_blocks: list["NestedBlock"] = field(default_factory=list)


@dataclass
class TerraformBlock:
    """terraform { required_providers { ... } }"""
    raw_content: str                         # preserved verbatim for safe round-trip


@dataclass
class OutputBlock:
    output_name: str
    attributes: dict[str, Attribute] = field(default_factory=dict)


@dataclass
class DataBlock:
    data_type: str                           # e.g. "terraform_remote_state"
    data_name: str                           # e.g. "vpc"
    attributes: dict[str, Attribute] = field(default_factory=dict)
    nested_blocks: list[NestedBlock] = field(default_factory=list)


Block = Union[ResourceBlock, ProviderBlock, TerraformBlock, OutputBlock, DataBlock]


@dataclass
class HCLFile:
    blocks: list[Block] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Type coercion helpers
# ---------------------------------------------------------------------------

def _coerce_value(raw: str) -> Any:
    """
    Convert a raw HCL attribute value string to the most appropriate Python type.

    Rules (in order):
    - Quoted string "true" / "false"  → bool
    - Quoted string of a pure integer  → int
    - Bare true / false               → bool
    - Bare integer                    → int
    - Bare float                      → float
    - Quoted interpolation "${...}"   → str (preserved as-is)
    - Everything else                 → str (stripped of surrounding quotes)
    """
    stripped = raw.strip()

    # Bare booleans (unquoted)
    if stripped == "true":
        return True
    if stripped == "false":
        return False

    # Quoted values
    if stripped.startswith('"') and stripped.endswith('"'):
        inner = stripped[1:-1]

        # Interpolation — preserve as-is (includes the quotes)
        if "${" in inner:
            return stripped  # keep full quoted interpolation string

        # Quoted boolean strings
        if inner == "true":
            return True
        if inner == "false":
            return False

        # Quoted integer strings
        if re.fullmatch(r"-?\d+", inner):
            return int(inner)

        # Quoted float strings
        if re.fullmatch(r"-?\d+\.\d+", inner):
            return float(inner)

        return inner  # plain string without quotes

    # Bare integer
    if re.fullmatch(r"-?\d+", stripped):
        return int(stripped)

    # Bare float
    if re.fullmatch(r"-?\d+\.\d+", stripped):
        return float(stripped)

    # List literal  [ ... ]  — preserve as raw string for safety
    # (lists in Terraformer output are usually security group IDs, not defaults)
    return stripped


# ---------------------------------------------------------------------------
# Tokeniser / block extractor
# ---------------------------------------------------------------------------

def _extract_blocks(text: str) -> list[str]:
    """
    Split top-level HCL text into a list of raw block strings.
    Each block is either:
      - A top-level block with braces: resource "..." "..." { ... }
      - (No bare assignments at top level in Terraform files)
    """
    blocks = []
    i = 0
    n = len(text)

    while i < n:
        # Skip whitespace and blank lines
        while i < n and text[i] in (" ", "\t", "\n", "\r"):
            i += 1
        if i >= n:
            break

        # Find the start of the next block — scan to '{'
        block_start = i
        brace_pos = text.find("{", i)
        if brace_pos == -1:
            break  # no more blocks

        # Collect the block header (everything before the opening brace)
        depth = 0
        j = brace_pos
        while j < n:
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    blocks.append(text[block_start:j + 1])
                    i = j + 1
                    break
            j += 1
        else:
            # Unbalanced braces — skip to avoid infinite loop
            break

    return blocks


# ---------------------------------------------------------------------------
# Attribute and nested-block parser
# ---------------------------------------------------------------------------

def _parse_attributes_and_nested(body: str) -> tuple[dict[str, Attribute], list[NestedBlock]]:
    """
    Parse the body of a block (text between the outer braces) into:
    - attributes: dict of key → Attribute
    - nested_blocks: list of NestedBlock

    Handles:
    - Simple key = value lines
    - Nested blocks: label { ... }
    - Multi-line map values: key = { k = v }
    """
    attributes: dict[str, Attribute] = {}
    nested_blocks: list[NestedBlock] = []

    text = body
    pos = 0
    n = len(text)

    while pos < n:
        # Skip whitespace
        while pos < n and text[pos] in (" ", "\t", "\n", "\r"):
            pos += 1
        if pos >= n:
            break

        # Skip comments
        if text[pos] == "#" or (pos + 1 < n and text[pos:pos+2] == "//"):
            while pos < n and text[pos] != "\n":
                pos += 1
            continue

        # Read a token (identifier)
        if not (text[pos].isalpha() or text[pos] == "_"):
            pos += 1
            continue

        token_start = pos
        while pos < n and (text[pos].isalnum() or text[pos] in ("_", "-")):
            pos += 1
        token = text[token_start:pos]

        # Skip whitespace after token
        while pos < n and text[pos] in (" ", "\t"):
            pos += 1

        if pos >= n:
            break

        # Case 1: key = value  (attribute assignment)
        if text[pos] == "=":
            pos += 1  # skip '='
            while pos < n and text[pos] in (" ", "\t"):
                pos += 1

            # Read value — may be a quoted string, number, bool, or inline map/list
            raw_val, pos = _read_value(text, pos)
            typed = _coerce_value(raw_val)
            attributes[token] = Attribute(key=token, raw_value=raw_val, typed_value=typed)
            # Skip to end of line
            while pos < n and text[pos] not in ("\n",):
                pos += 1

        # Case 2: nested block  identifier [optional_label] {
        elif text[pos] == '"' or text[pos] == "{":
            # Collect optional labels
            labels = []
            while pos < n and text[pos] == '"':
                lbl_start = pos + 1
                pos += 1
                while pos < n and text[pos] != '"':
                    pos += 1
                labels.append(text[lbl_start:pos])
                pos += 1  # skip closing quote
                while pos < n and text[pos] in (" ", "\t"):
                    pos += 1

            if pos < n and text[pos] == "{":
                # Find matching closing brace
                brace_start = pos
                depth = 0
                j = pos
                while j < n:
                    if text[j] == "{":
                        depth += 1
                    elif text[j] == "}":
                        depth -= 1
                        if depth == 0:
                            break
                    j += 1
                inner_body = text[brace_start + 1:j]
                pos = j + 1

                sub_attrs, sub_nested = _parse_attributes_and_nested(inner_body)
                nb = NestedBlock(
                    block_type=token,
                    labels=labels,
                    attributes=sub_attrs,
                    nested_blocks=sub_nested,
                )
                nested_blocks.append(nb)
            else:
                # Unexpected — skip line
                while pos < n and text[pos] != "\n":
                    pos += 1
        else:
            # Skip unknown token
            while pos < n and text[pos] != "\n":
                pos += 1

    return attributes, nested_blocks


def _read_value(text: str, pos: int) -> tuple[str, int]:
    """
    Read a single HCL value starting at pos.
    Returns (raw_value_string, new_pos).
    Handles: quoted strings (including interpolations), numbers, booleans, lists [...].
    """
    n = len(text)
    if pos >= n:
        return ("", pos)

    # Quoted string
    if text[pos] == '"':
        start = pos
        pos += 1
        while pos < n:
            if text[pos] == '\\':
                pos += 2  # skip escaped char
            elif text[pos] == '"':
                pos += 1
                break
            else:
                pos += 1
        return (text[start:pos], pos)

    # List [...]
    if text[pos] == "[":
        start = pos
        depth = 0
        while pos < n:
            if text[pos] == "[":
                depth += 1
            elif text[pos] == "]":
                depth -= 1
                if depth == 0:
                    pos += 1
                    break
            pos += 1
        return (text[start:pos], pos)

    # Inline map {...}  (e.g. config = { path = "..." })
    if text[pos] == "{":
        start = pos
        depth = 0
        while pos < n:
            if text[pos] == "{":
                depth += 1
            elif text[pos] == "}":
                depth -= 1
                if depth == 0:
                    pos += 1
                    break
            pos += 1
        return (text[start:pos], pos)

    # Bare value (bool, number, identifier)
    start = pos
    while pos < n and text[pos] not in (" ", "\t", "\n", "\r", "#", "}"):
        pos += 1
    return (text[start:pos], pos)


# ---------------------------------------------------------------------------
# Top-level block parser
# ---------------------------------------------------------------------------

_BLOCK_HEADER_RE = re.compile(
    r"""^(?P<type>[a-zA-Z_][a-zA-Z0-9_]*)\s*(?P<labels>(?:"[^"]*"\s*)*)""",
    re.DOTALL
)


def _parse_block(raw: str) -> Block | None:
    """Parse a single raw block string into the appropriate Block dataclass."""
    brace_pos = raw.index("{")
    header = raw[:brace_pos].strip()
    body = raw[brace_pos + 1:raw.rindex("}")]

    # Strip leading comment lines (from emitter file-header comments or inline comments)
    # so the block-type regex always anchors to the actual keyword.
    header_lines = [l for l in header.splitlines() if not l.strip().startswith("#")]
    header = "\n".join(header_lines).strip()

    m = _BLOCK_HEADER_RE.match(header)
    if not m:
        return None

    block_type = m.group("type")
    # Extract quoted labels from header
    labels = re.findall(r'"([^"]*)"', m.group("labels"))

    if block_type == "resource" and len(labels) >= 2:
        attrs, nested = _parse_attributes_and_nested(body)
        return ResourceBlock(
            resource_type=labels[0],
            resource_name=labels[1],
            attributes=attrs,
            nested_blocks=nested,
        )

    if block_type == "provider" and len(labels) >= 1:
        attrs, nested = _parse_attributes_and_nested(body)
        return ProviderBlock(provider_name=labels[0], attributes=attrs, nested_blocks=nested)

    if block_type == "terraform":
        # Preserve terraform block verbatim — it contains required_providers with
        # complex nested syntax that we don't need to manipulate
        return TerraformBlock(raw_content=raw)

    if block_type == "output" and len(labels) >= 1:
        attrs, _ = _parse_attributes_and_nested(body)
        return OutputBlock(output_name=labels[0], attributes=attrs)

    if block_type == "data" and len(labels) >= 2:
        attrs, nested = _parse_attributes_and_nested(body)
        return DataBlock(data_type=labels[0], data_name=labels[1], attributes=attrs, nested_blocks=nested)

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_hcl(text: str) -> HCLFile:
    """Parse a Terraform HCL file into an HCLFile object model."""
    raw_blocks = _extract_blocks(text)
    hcl = HCLFile()
    for raw in raw_blocks:
        block = _parse_block(raw.strip())
        if block is not None:
            hcl.blocks.append(block)
    return hcl


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

# Pattern that matches a bare Terraform resource/data reference expression:
# e.g. aws_vpc.some_name.id  or  aws_vpc.some_name.attribute
_RESOURCE_REF_RE = re.compile(r'^[a-z][a-z0-9_]*\.[a-zA-Z0-9_\-]+\.[a-z][a-z0-9_]*$')


def _render_value(attr: Attribute) -> str:
    """Render a typed value back to HCL syntax."""
    v = attr.typed_value
    raw = attr.raw_value.strip()

    # Interpolation strings — preserve exactly as stored (already includes quotes)
    if isinstance(v, str) and "${" in v:
        return v

    # Bare Terraform resource reference expressions (not string literals):
    # e.g. aws_vpc.tfer--vpc-xxx.id  → rendered without quotes
    if isinstance(v, str) and _RESOURCE_REF_RE.match(v):
        return v

    # Lists — preserve raw, but unquote any resource reference expressions inside
    if isinstance(v, str) and raw.startswith("["):
        # Replace "aws_type.name.attr" (quoted reference) with bare expression
        return re.sub(r'"([a-z][a-z0-9_]*\.[a-zA-Z0-9_\-]+\.[a-z_]+)"', r'\1', raw)

    # Inline maps — preserve raw
    if isinstance(v, str) and raw.startswith("{"):
        return raw

    if isinstance(v, bool):
        return "true" if v else "false"

    if isinstance(v, int):
        return str(v)

    if isinstance(v, float):
        return str(v)

    # String — quote it
    if isinstance(v, str):
        return f'"{v}"'

    return raw


def render_nested_block(nb: NestedBlock, indent: int = 2) -> str:
    """Render a NestedBlock back to HCL text."""
    pad = " " * indent
    label_str = " ".join(f'"{l}"' for l in nb.labels)
    header = f"{nb.block_type}" + (f" {label_str}" if label_str else "")
    lines = [f"{pad}{header} {{"]
    for attr in nb.attributes.values():
        lines.append(f"{pad}  {attr.key} = {_render_value(attr)}")
    for sub in nb.nested_blocks:
        lines.append(render_nested_block(sub, indent + 2))
    lines.append(f"{pad}}}")
    return "\n".join(lines)


def render_block(block: Block) -> str:
    """Render any Block back to HCL text."""
    if isinstance(block, TerraformBlock):
        return block.raw_content

    if isinstance(block, ProviderBlock):
        lines = [f'provider "{block.provider_name}" {{']
        for attr in block.attributes.values():
            lines.append(f"  {attr.key} = {_render_value(attr)}")
        for nb in block.nested_blocks:
            lines.append(render_nested_block(nb, indent=2))
        lines.append("}")
        return "\n".join(lines)

    if isinstance(block, OutputBlock):
        lines = [f'output "{block.output_name}" {{']
        for attr in block.attributes.values():
            lines.append(f"  {attr.key} = {_render_value(attr)}")
        lines.append("}")
        return "\n".join(lines)

    if isinstance(block, DataBlock):
        lines = [f'data "{block.data_type}" "{block.data_name}" {{']
        for attr in block.attributes.values():
            lines.append(f"  {attr.key} = {_render_value(attr)}")
        for nb in block.nested_blocks:
            lines.append(render_nested_block(nb, indent=2))
        lines.append("}")
        return "\n".join(lines)

    if isinstance(block, ResourceBlock):
        lines = [f'resource "{block.resource_type}" "{block.resource_name}" {{']
        for attr in block.attributes.values():
            lines.append(f"  {attr.key} = {_render_value(attr)}")
        for nb in block.nested_blocks:
            lines.append(render_nested_block(nb, indent=2))
        lines.append("}")
        return "\n".join(lines)

    return ""
