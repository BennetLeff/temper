"""Export resolved Atopile component attributes from a compiled entry.

This is deliberately a native Atopile API adapter: it does not parse source
text or contain circuit-specific declarations.  Rust owns all qualification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _json(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "magnitude") and hasattr(value, "units"):
        return {"magnitude": float(value.magnitude), "units": str(value.units)}
    if isinstance(value, dict):
        return {str(k): _json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(v) for v in value]
    return str(value)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export(project: Path, output: Path,
           entry_file: str = "buck.ato",
           entry_module: str = "BuckCircuitCandidate") -> dict[str, Any]:
    from atopile import api, instance_methods

    entry = (project / entry_file).resolve()
    address = f"{entry}:{entry_module}"
    api.build(address)
    components: list[dict[str, Any]] = []
    for descendant in instance_methods.all_descendants(address):
        if not instance_methods.match_components(descendant):
            continue
        attrs = instance_methods.get_data_dict(descendant)
        components.append({"address": descendant, "attributes": _json(attrs)})
    artifacts = {
        str(path.relative_to(project)): _digest(path)
        for path in sorted(
            (project / "build").glob("*") if (project / "build").is_dir() else []
        )
        if path.is_file()
    }
    sources = {
        str(path.relative_to(project)): _digest(path)
        for path in sorted(project.rglob("*.ato"))
        if path.is_file()
    }
    result = {
        "schema": "temper.circuit-export.v1",
        "atopile_version": "0.2.69",
        "entry": address,
        "components": components,
        "source_sha256": sources,
        "build_sha256": artifacts,
    }
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project", type=Path)
    parser.add_argument("output", type=Path)
    # Parameterized for non-buck blocks (P1 U2); defaults preserve the
    # historical buck entry exactly.
    parser.add_argument("--entry-file", default="buck.ato")
    parser.add_argument("--entry", default="BuckCircuitCandidate")
    args = parser.parse_args()
    export(args.project.resolve(), args.output.resolve(),
           args.entry_file, args.entry)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
