"""Load source-backed placement reference reconciliation manifests."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class ReferenceAliasManifest:
    """Validated aliases that may be passed to the CP-SAT encoder."""

    component_aliases: dict[str, str]
    loop_aliases: dict[str, str]


def load_reference_alias_manifest(
    path: Path,
    *,
    component_refs: Collection[str],
    loop_names: Collection[str],
) -> ReferenceAliasManifest:
    """Load and validate a source-backed alias manifest.

    The manifest is deliberately only a map of names to names. It cannot
    invent a target: every target must already exist in the parsed board or
    loop namespace. A source that is already a live component/loop name is
    rejected because rewriting it would silently change current design intent.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ValueError(f"{path}: expected schema_version: 1")

    component_refs_set = set(component_refs)
    loop_names_set = set(loop_names)

    component_aliases = _read_aliases(raw, "component_aliases", path)
    loop_aliases = _read_aliases(raw, "loop_aliases", path)
    _validate_aliases(
        component_aliases,
        available=component_refs_set,
        namespace="component",
        path=path,
    )
    _validate_aliases(
        loop_aliases,
        available=loop_names_set,
        namespace="loop",
        path=path,
    )
    return ReferenceAliasManifest(component_aliases, loop_aliases)


def _read_aliases(raw: dict, key: str, path: Path) -> dict[str, str]:
    value = raw.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"{path}: {key} must be a mapping")
    aliases: dict[str, str] = {}
    for source, target in value.items():
        if not isinstance(source, str) or not isinstance(target, str):
            raise ValueError(f"{path}: {key} keys and values must be strings")
        if not source.strip() or not target.strip():
            raise ValueError(f"{path}: {key} contains an empty name")
        aliases[source] = target
    return aliases


def _validate_aliases(
    aliases: dict[str, str],
    *,
    available: set[str],
    namespace: str,
    path: Path,
) -> None:
    for source, target in aliases.items():
        if target not in available:
            raise ValueError(
                f"{path}: {namespace} alias {source!r} targets missing {namespace} {target!r}"
            )
        if source in available and source != target:
            raise ValueError(
                f"{path}: {namespace} alias source {source!r} is already a live name; "
                "do not rewrite current design intent"
            )
