#!/usr/bin/env python3
"""
Regenerate cross-language NetClassRules domain model from SSOT manifest.

Usage:
    python3 scripts/gen_domain_models.py              # regenerate all
    python3 scripts/gen_domain_models.py --check      # CI mode: exit 1 if any drift

The script is idempotent — it writes each output to a .tmp file, compares
byte-for-byte with the existing file, and only atomically replaces if content
differs. This follows the firmware/tools/gen_config.py precedent.
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader

REPO_ROOT = Path(__file__).resolve().parent.parent

MANIFEST_PATH = REPO_ROOT / "packages" / "temper-placer" / "configs" / "netclass_rules_manifest.yaml"
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
PYTHON_TEMPLATE_NAME = "netclass_rules.py.j2"
RUST_TEMPLATE_NAME = "netclass_rules.rs.j2"
PYTHON_OUTPUT = REPO_ROOT / "packages" / "temper-placer" / "src" / "temper_placer" / "core" / "netclass_rules_gen.py"
RUST_FILE = REPO_ROOT / "packages" / "temper-drc-rs" / "src" / "board.rs"

BEGIN_MARKER = "// BEGIN GENERATED NetClassRules"
END_MARKER = "// END GENERATED NetClassRules"

# ---------------------------------------------------------------------------
# Type mapping
# ---------------------------------------------------------------------------

PY_TYPE = {
    "string": "str",
    "float": "float",
    "int": "int",
    "optional_string": "str | None",
    "optional_float": "float | None",
    "optional_int": "int | None",
    "string_enum": 'Literal["HV", "LV", "AC", "iso"] | None',
    "dict": "dict[str, float] | None",
}

RS_TYPE = {
    "string": "String",
    "float": "f64",
    "int": "i32",
    "optional_string": "Option<String>",
    "optional_float": "Option<f64>",
    "optional_int": "Option<i32>",
    "string_enum": "Option<String>",
    "dict": "Option<HashMap<String, f64>>",
}


def py_default(field: dict[str, Any]) -> str:
    """Format a field's default value as Python source."""
    default = field.get("default")
    if default is None:
        return "None"
    if isinstance(default, str):
        return f'"{default}"'
    if isinstance(default, bool):
        return "True" if default else "False"
    if isinstance(default, float):
        return repr(default)
    if isinstance(default, int):
        return repr(default)
    return repr(default)


def rs_default(field: dict[str, Any]) -> str:
    """Format a field's default value as Rust source."""
    typ = field.get("type", "string")
    default = field.get("default")
    if default is None:
        return "None"
    rust_type = RS_TYPE.get(typ, "String")
    if rust_type == "String":
        return "String::new()"
    if rust_type == "f64":
        val = float(default)
        if val == int(val) and val != 0.0:
            return f"{val:.1f}_f64"
        return f"{val}_f64"
    if rust_type == "i32":
        return f"{int(default)}_i32"
    return repr(default)


def prepare_template_context(manifest: dict[str, Any]) -> dict[str, Any]:
    """Transform manifest fields into template-ready context."""
    fields = manifest.get("fields", [])
    data_fields = []
    doc_only_fields = []
    needs_hashmap = False

    for field in fields:
        typ = field.get("type", "string")
        if typ == "doc_only":
            doc_only_fields.append(field)
            continue

        py_type = PY_TYPE.get(typ, "str")
        rs_type = RS_TYPE.get(typ, "String")
        rust_name = field.get("rust_name", field["name"])
        required = field.get("required", False)

        entry = {
            "name": field["name"],
            "rust_name": rust_name,
            "doc": field.get("doc", ""),
            "py_type": py_type,
            "py_default": py_default(field),
            "rs_type": rs_type,
            "rs_default": rs_default(field),
            "required": required,
        }
        data_fields.append(entry)

        if rs_type == "Option<HashMap<String, f64>>":
            needs_hashmap = True

    return {
        "data_fields": data_fields,
        "doc_only_fields": doc_only_fields,
        "needs_hashmap": needs_hashmap,
    }


def render_template(env: Environment, template_name: str, context: dict[str, Any]) -> str:
    """Render a Jinja2 template and ensure trailing newline."""
    template = env.get_template(template_name)
    rendered = template.render(**context)
    if not rendered.endswith("\n"):
        rendered += "\n"
    return rendered


def atomic_write(path: Path, content: str) -> bool:
    """Write content to path atomically. Returns True if file was created or changed."""
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w", newline="\n") as f:
        f.write(content)

    if path.exists():
        with open(path) as f:
            existing = f.read()
        if existing == content:
            tmp_path.unlink()
            return False  # unchanged

    os.replace(tmp_path, path)
    return True


def replace_rust_block(board_rs_path: Path, rust_content: str) -> str:
    """Replace the delimited block in board.rs with generated Rust content.

    Returns the updated file content as a string.
    """
    with open(board_rs_path) as f:
        original = f.read()

    begin_idx = original.find(BEGIN_MARKER)
    end_idx = original.find(END_MARKER)

    if begin_idx == -1:
        print(
            f"ERROR: missing '{BEGIN_MARKER}' marker in {board_rs_path}",
            file=sys.stderr,
        )
        sys.exit(1)
    if end_idx == -1:
        print(
            f"ERROR: missing '{END_MARKER}' marker in {board_rs_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Check for duplicate markers
    if original.count(BEGIN_MARKER) > 1:
        print(
            f"ERROR: multiple '{BEGIN_MARKER}' markers found in {board_rs_path} — "
            f"delimiters must appear exactly once",
            file=sys.stderr,
        )
        sys.exit(1)
    if original.count(END_MARKER) > 1:
        print(
            f"ERROR: multiple '{END_MARKER}' markers found in {board_rs_path} — "
            f"delimiters must appear exactly once",
            file=sys.stderr,
        )
        sys.exit(1)

    # Ensure END_MARKER comes after BEGIN_MARKER
    if end_idx < begin_idx:
        print(
            f"ERROR: '{END_MARKER}' appears before '{BEGIN_MARKER}' in {board_rs_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Find the end of the END_MARKER line
    end_line_idx = original.find("\n", end_idx)
    if end_line_idx == -1:
        end_line_idx = len(original)

    updated = original[:begin_idx] + rust_content + original[end_line_idx + 1 :]
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Regenerate cross-language NetClassRules domain model from SSOT manifest"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="CI mode: exit 1 if generated content differs from committed files",
    )
    args = parser.parse_args()

    # Load manifest
    if not MANIFEST_PATH.exists():
        print(f"ERROR: manifest not found at {MANIFEST_PATH}", file=sys.stderr)
        sys.exit(1)

    with open(MANIFEST_PATH) as f:
        manifest = yaml.safe_load(f)

    context = prepare_template_context(manifest)

    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))

    # Render Python output
    python_content = render_template(env, PYTHON_TEMPLATE_NAME, context)

    # Render Rust block
    rust_content = render_template(env, RUST_TEMPLATE_NAME, context)

    if args.check:
        # CI mode: compare against committed files
        errors = []

        # Check Python output
        if not PYTHON_OUTPUT.exists():
            errors.append(f"missing generated file: {PYTHON_OUTPUT}")
        else:
            with open(PYTHON_OUTPUT) as f:
                existing_py = f.read()
            if existing_py != python_content:
                errors.append(
                    f"{PYTHON_OUTPUT} has drifted from manifest — run: "
                    f"python3 scripts/gen_domain_models.py"
                )

        # Check Rust block
        if not RUST_FILE.exists():
            errors.append(f"missing Rust file: {RUST_FILE}")
        else:
            expected_rs = replace_rust_block(RUST_FILE, rust_content)
            with open(RUST_FILE) as f:
                existing_rs = f.read()
            if existing_rs != expected_rs:
                errors.append(
                    f"{RUST_FILE} NetClassRules block has drifted from manifest — run: "
                    f"python3 scripts/gen_domain_models.py"
                )

        if errors:
            for err in errors:
                print(f"ERROR: {err}", file=sys.stderr)
            sys.exit(1)
        print("All generated domain models match the manifest.")
        return

    # Regenerate mode: write files
    changed_py = atomic_write(PYTHON_OUTPUT, python_content)
    if changed_py:
        print(f"Updated {PYTHON_OUTPUT}")
    else:
        print(f"{PYTHON_OUTPUT} up to date")

    # Update board.rs in-place
    updated_rs = replace_rust_block(RUST_FILE, rust_content)
    changed_rs = atomic_write(RUST_FILE, updated_rs)
    if changed_rs:
        print(f"Updated {RUST_FILE} (NetClassRules block)")
    else:
        print(f"{RUST_FILE} NetClassRules block up to date")


if __name__ == "__main__":
    main()
