#!/usr/bin/env python3
"""
Regenerate firmware/config.h from firmware/config.yaml.

Usage:
    python3 firmware/tools/gen_config.py

The script is idempotent — it only overwrites config.h when the
generated content differs from the current file.
"""

import sys
import os
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader


def main():
    repo_root = Path(__file__).resolve().parent.parent
    manifest_path = repo_root / "config.yaml"
    template_path = Path(__file__).resolve().parent / "config.h.j2"
    output_path = repo_root / "config.h"

    if not manifest_path.exists():
        print(f"ERROR: manifest not found at {manifest_path}", file=sys.stderr)
        sys.exit(1)

    with open(manifest_path) as f:
        manifest = yaml.safe_load(f)

    env = Environment(loader=FileSystemLoader(template_path.parent))
    template = env.get_template(template_path.name)
    rendered = template.render(**manifest)

    # Ensure trailing newline
    if not rendered.endswith("\n"):
        rendered += "\n"

    tmp_path = output_path.with_suffix(".h.tmp")
    with open(tmp_path, "w") as f:
        f.write(rendered)

    if output_path.exists():
        with open(output_path) as f:
            existing = f.read()
        if existing == rendered:
            tmp_path.unlink()
            print("config.h up to date")
            return

    tmp_path.rename(output_path)
    print("config.h regenerated")


if __name__ == "__main__":
    main()
