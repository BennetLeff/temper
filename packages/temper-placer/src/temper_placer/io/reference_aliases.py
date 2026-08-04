"""Load source-backed placement reference reconciliation manifests.

Delegation shim — the implementation migrated to Rust (``temper_io_types``,
``reference_aliases.rs``) under Wave 4 Phase 3, candidate 5. PyYAML and
``pathlib.Path.read_text`` are called back across the boundary; schema
validation, alias validation and the ``ValueError`` strings are Rust.
"""

from __future__ import annotations

from temper_io_types import ReferenceAliasManifest, load_reference_alias_manifest

__all__ = ["ReferenceAliasManifest", "load_reference_alias_manifest"]
