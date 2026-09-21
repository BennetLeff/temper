"""Locating, loading, and resolving the committed JSON Schema files.

R14 makes the committed schema files the definition of every record this package
writes, so they are read from disk rather than reconstructed in Python: one home
for a record's shape, reviewable in a diff.

This module is deliberately neutral between the ledger and the store. Both need
to validate against committed schemas, and neither is layered on the other -- a
``call_terminal`` row records ``served_from``, which is the store's vocabulary,
and a recording records the request the ledger's call described. Putting the
helpers under either one would invent a dependency between peers.

``build_validator`` assembles its ``referencing`` registry from the ``$id`` of
every sibling schema rather than by hand, so a schema may reference another
without this module knowing the reference graph -- which is what lets
``envelope.schema.json`` reference ``usage.schema.json`` with no per-reference
entry here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

#: The schema files are committed data beside the package, not modules inside
#: it: a record's shape is reviewed as a diff, and it must be readable by a CI
#: gate that never imports this package.
SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"


def load_schema(name: str) -> dict[str, Any]:
    """Read one committed schema by filename."""
    contents: dict[str, Any] = json.loads((SCHEMA_DIR / name).read_text())
    return contents


def build_validator(name: str) -> Draft202012Validator:
    """Build a validator for one schema, with every sibling schema resolvable."""
    registry = Registry()
    for path in sorted(SCHEMA_DIR.glob("*.json")):
        contents = json.loads(path.read_text())
        schema_id = contents.get("$id")
        if schema_id:
            registry = registry.with_resource(schema_id, Resource.from_contents(contents))
    return Draft202012Validator(load_schema(name), registry=registry)
