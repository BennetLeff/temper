#!/usr/bin/env python3
"""Check that firmware/config.h values match firmware/config.yaml.

Parses the generated header and the YAML manifest, then asserts that
every #define and every *_DEFAULT field matches the manifest value.
Exits 0 on match, 1 with details on mismatch.
"""

import re
import sys
from pathlib import Path

import yaml


def parse_legacy_defines(header_text):
    """Extract {name: value_str} from '#define NAME value' lines."""
    defines = {}
    for m in re.finditer(r"^#define\s+(\w+)\s+(.+)$", header_text, re.MULTILINE):
        name = m.group(1)
        val = m.group(2).strip()
        defines[name] = val
    return defines


def parse_default_fields(header_text):
    """Extract {field: value_str} from '.field = value,' inside *_DEFAULT."""
    fields = {}
    for m in re.finditer(r"^\s*\.(\w+)\s*=\s*([^,\s]+)", header_text, re.MULTILINE):
        field = m.group(1)
        val = m.group(2).strip()
        fields[field] = val
    return fields


def fmt_manifest_value(entry):
    """Format a manifest value as it would appear in the generated header."""
    val = entry["value"]
    ctype = entry.get("c_type", "uint32_t")
    if ctype == "float":
        return f"{val}f"
    return str(val)


def main():
    repo_root = Path(__file__).resolve().parent.parent
    manifest_path = repo_root / "config.yaml"
    header_path = repo_root / "config.h"

    with open(manifest_path) as f:
        manifest = yaml.safe_load(f)

    with open(header_path) as f:
        header_text = f.read()

    defines = parse_legacy_defines(header_text)
    fields = parse_default_fields(header_text)

    errors = []

    for group_name, entries in manifest.items():
        for entry in entries:
            # Check #define if present
            csym = entry.get("c_symbol")
            if csym:
                expected_val = fmt_manifest_value(entry)
                if csym not in defines:
                    errors.append(f"{csym}: missing #define in config.h")
                elif defines[csym] != expected_val:
                    errors.append(
                        f"{csym}: #define mismatch "
                        f"header='{defines[csym]}' manifest='{expected_val}'"
                    )

            # Check struct field
            field = entry.get("field")
            if field:
                expected_val = fmt_manifest_value(entry)
                if field not in fields:
                    errors.append(f"{field}: missing field in config.h *_DEFAULT")
                elif fields[field] != expected_val:
                    errors.append(
                        f"{field}: field mismatch "
                        f"header='{fields[field]}' manifest='{expected_val}'"
                    )

    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        sys.exit(1)

    print("config.h matches manifest")
    sys.exit(0)


if __name__ == "__main__":
    main()
