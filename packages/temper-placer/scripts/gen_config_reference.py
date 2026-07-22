#!/usr/bin/env python3
"""Generate docs/reference/config-reference.md from Pydantic model introspection.

Walks the PlacementConstraints model tree using model_fields to produce
a markdown reference for every config field, including type, default,
description, and constraints.

Usage:
    python scripts/gen_config_reference.py          # Generate (idempotent)
    python scripts/gen_config_reference.py --check  # CI gate (exit non-zero if stale)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic.fields import FieldInfo

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
OUTPUT_PATH = REPO_ROOT / "docs" / "reference" / "config-reference.md"


def _get_root_model() -> type[BaseModel]:
    from temper_placer._constraint_types.config import PlacementConstraints
    return PlacementConstraints


def _collect_models(root: type[BaseModel]) -> list[tuple[str, type[BaseModel]]]:
    """Recursively collect all Pydantic model classes from the root model's fields."""
    seen: set[int] = set()
    models: list[tuple[str, type[BaseModel]]] = []

    def visit(model_cls: type[BaseModel], path: str) -> None:
        cls_id = id(model_cls)
        if cls_id in seen:
            return
        seen.add(cls_id)
        models.append((path, model_cls))

        for name, field_info in model_cls.model_fields.items():
            annotation = field_info.annotation
            if annotation is None:
                continue
            # Handle Union/Optional types
            origin = getattr(annotation, "__origin__", None)
            if origin is not None:
                # For list[...], dict[...], etc. with BaseModel args
                args = getattr(annotation, "__args__", ())
                for arg in args:
                    if isinstance(arg, type) and issubclass(arg, BaseModel):
                        visit(arg, f"{path}.{name}")
            elif isinstance(annotation, type) and issubclass(annotation, BaseModel):
                visit(annotation, f"{path}.{name}")

    visit(root, "PlacementConstraints")
    return models


def _format_type(annotation: Any) -> str:
    """Format a type annotation for display."""
    if annotation is None:
        return "Any"
    origin = getattr(annotation, "__origin__", None)
    if origin is list:
        args = getattr(annotation, "__args__", ())
        if args:
            return f"list[{_format_type(args[0])}]"
        return "list"
    if origin is dict:
        return "dict"
    if origin is tuple:
        return "tuple"
    if hasattr(annotation, "__name__"):
        return annotation.__name__
    return str(annotation)


def _format_default(field_info: FieldInfo) -> str:
    """Format the default value for display."""
    if field_info.default_factory is not None:
        factory = field_info.default_factory
        if factory is list:
            return "[]"
        if factory is dict:
            return "{}"
        # For callable factories like FeedbackConfig, get the class name
        if callable(factory):
            result = factory()
            if isinstance(result, BaseModel):
                return f"{type(result).__name__}()"
            return str(result)[:60]
        return str(factory)
    if field_info.default is not None and field_info.default is not Ellipsis:
        return repr(field_info.default)
    if field_info.is_required():
        return "(required)"
    return "None"


def _format_constraints(field_info: FieldInfo) -> str:
    """Extract constraint metadata from FieldInfo."""
    constraints = []
    metadata = field_info.metadata
    for m in metadata:
        if hasattr(m, "gt") and m.gt is not None:
            constraints.append(f"gt={m.gt}")
        if hasattr(m, "ge") and m.ge is not None:
            constraints.append(f"ge={m.ge}")
        if hasattr(m, "lt") and m.lt is not None:
            constraints.append(f"lt={m.lt}")
        if hasattr(m, "le") and m.le is not None:
            constraints.append(f"le={m.le}")
    if constraints:
        return ", ".join(constraints)
    return "—"


def generate_reference() -> str:
    """Generate the full config reference markdown."""
    root = _get_root_model()
    models = _collect_models(root)

    lines: list[str] = []
    lines.append("# Configuration Reference")
    lines.append("")
    lines.append("*Auto-generated from Pydantic model introspection.*")
    lines.append("")
    lines.append("## Table of Contents")
    lines.append("")
    for path, _ in models:
        name = path.split(".")[-1]
        lines.append(f"- [{name}](#{name.lower()})")
    lines.append("")

    for path, model_cls in models:
        name = path.split(".")[-1]
        lines.append(f"## {name}")
        lines.append("")
        if model_cls.__doc__:
            doc = model_cls.__doc__.split("\n")[0].strip()
            lines.append(f"{doc}")
            lines.append("")

        # Frozen/mutable info
        config = getattr(model_cls, "model_config", {})
        frozen = config.get("frozen", False)
        extra = config.get("extra", "ignore")
        lines.append(f"- **Frozen**: {frozen}")
        lines.append(f"- **Extra keys**: {extra}")
        lines.append("")

        lines.append("| Field | Type | Default | Constraints | Description |")
        lines.append("|-------|------|---------|-------------|-------------|")

        for field_name, field_info in model_cls.model_fields.items():
            ftype = _format_type(field_info.annotation)
            default = _format_default(field_info)
            constraints = _format_constraints(field_info)
            description = (field_info.description or "").replace("|", "\\|")
            lines.append(f"| `{field_name}` | `{ftype}` | {default} | {constraints} | {description} |")

        lines.append("")

    lines.append(f"*Generated from `{root.__module__}.{root.__qualname__}`*")
    lines.append("")
    return "\n".join(lines)


def _idempotent_write(content: str, path: Path) -> bool:
    """Write content to path only if it differs from current content. Returns True if written."""
    if path.exists() and path.read_text() == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate configuration reference from Pydantic models")
    parser.add_argument("--check", action="store_true", help="Exit non-zero if generated doc is stale")
    args = parser.parse_args()

    content = generate_reference()

    if args.check:
        if not OUTPUT_PATH.exists():
            print(f"ERROR: {OUTPUT_PATH} does not exist. Run without --check to generate.", file=sys.stderr)
            return 1
        if OUTPUT_PATH.read_text() != content:
            print(f"ERROR: {OUTPUT_PATH} is stale. Run scripts/gen_config_reference.py to regenerate.", file=sys.stderr)
            return 1
        print(f"OK: {OUTPUT_PATH} is up-to-date.")
        return 0
    else:
        written = _idempotent_write(content, OUTPUT_PATH)
        if written:
            print(f"Generated: {OUTPUT_PATH}")
        else:
            print(f"Up-to-date: {OUTPUT_PATH}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
