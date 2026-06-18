from __future__ import annotations

from pathlib import Path


def load_tf_files(source: Path) -> dict[Path, str]:
    if source.is_file():
        return {source: load_tf_text(source)}

    if source.is_dir():
        return {path: load_tf_text(path) for path in sorted(source.rglob("*.tf"))}

    raise ValueError(f"Source path does not exist: {source}")


def load_tf_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")
