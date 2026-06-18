from __future__ import annotations

from pathlib import Path
from typing import Any

import hcl2


def load_tf_files(source: Path) -> dict[Path, dict[str, Any]]:
    if source.is_file():
        return {source: _parse_tf_file(source)}

    if source.is_dir():
        return {path: _parse_tf_file(path) for path in sorted(source.rglob("*.tf"))}

    raise ValueError(f"Source path does not exist: {source}")


def _parse_tf_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return hcl2.load(handle)
