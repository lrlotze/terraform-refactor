"""tfrefactor — AI-assisted Terraform refactoring tool."""

from .parser import parse_files, parse_directory
from .detector import detect_module_groups
from .emitter import emit

__all__ = ["parse_files", "parse_directory", "detect_module_groups", "emit"]
