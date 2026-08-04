"""Differential test: Rust reference-alias manifest loader (temper_io_types)
vs the pinned Python oracle.

Wave 4, Phase 3, candidate 5 — the config/reference loaders migration (plan
``docs/plans/2026-08-02-001-feat-wave4-phase3-formats-io-plan.md``, candidate
5). The manifest loader is a pure YAML-to-dataclass surface: PyYAML
(``yaml.safe_load``) and ``pathlib.Path.read_text`` stay on the Python side
and are called back across the boundary; schema validation, alias
validation, and the exact ``ValueError`` strings are Rust.

The Rust ``ReferenceAliasManifest`` pyclass and
``load_reference_alias_manifest`` pyfunction (in ``temper_io_types``, from
the ``temper-io-types`` crate) must reproduce the pre-migration
implementation of ``temper_placer/io/reference_aliases.py`` bit-identically,
pinned verbatim as the oracle (``_reference_aliases_py_oracle.py``, commit
79ab9bd0e).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import temper_io_types as _io

import tests.io._reference_aliases_py_oracle as _oracle

LOAD_MANIFEST = _io.load_reference_alias_manifest
MANIFEST_CLS = _io.ReferenceAliasManifest

ROOT = Path(__file__).parents[2]
PRODUCTION_MANIFEST = ROOT / "configs" / "temper_constraints.references.yaml"


def _manifest_key(m):
    return (tuple(sorted(m.component_aliases.items())), tuple(sorted(m.loop_aliases.items())))


# ---------------------------------------------------------------------------
# Production manifest parity.
# ---------------------------------------------------------------------------


def test_production_manifest_matches_oracle():
    refs = {
        "C2", "C3", "C6", "C17", "C24", "C28", "C38", "C39",
        "R23", "R27", "R31", "T1", "U4", "U7", "U8", "U9", "U27",
    }
    py_m = _oracle.load_reference_alias_manifest(PRODUCTION_MANIFEST, component_refs=refs, loop_names=set())
    rs_m = LOAD_MANIFEST(str(PRODUCTION_MANIFEST), component_refs=refs, loop_names=set())
    assert _manifest_key(rs_m) == _manifest_key(py_m)
    assert rs_m.component_aliases["U_MCU"] == py_m.component_aliases["U_MCU"]
    assert rs_m.loop_aliases == py_m.loop_aliases


# ---------------------------------------------------------------------------
# Validation error parity (exact message text).
# ---------------------------------------------------------------------------


def _both_raise(content: str, component_refs, loop_names, match: str | None = None):
    path = Path(__import__("tempfile").mkdtemp()) / "m.yaml"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError) as py_exc:
        _oracle.load_reference_alias_manifest(path, component_refs=component_refs, loop_names=loop_names)
    with pytest.raises(ValueError) as rs_exc:
        LOAD_MANIFEST(str(path), component_refs=component_refs, loop_names=loop_names)
    # The messages embed the path; normalize the leading path segment.
    py_msg = str(py_exc.value).split(": ", 1)[1]
    rs_msg = str(rs_exc.value).split(": ", 1)[1]
    assert rs_msg == py_msg
    if match:
        assert match in rs_msg


def test_rejects_alias_source_that_is_live():
    _both_raise(
        "schema_version: 1\ncomponent_aliases:\n  C2: C3\n",
        {"C2", "C3"}, set(), "already a live name",
    )


def test_rejects_alias_target_missing_from_board():
    _both_raise(
        "schema_version: 1\ncomponent_aliases:\n  LEGACY_A: C999\n",
        {"C2"}, set(), "targets missing component",
    )


def test_rejects_unknown_schema_version():
    _both_raise(
        "schema_version: 2\ncomponent_aliases: {}\n",
        set(), set(), "expected schema_version",
    )


def test_rejects_schema_version_missing():
    _both_raise(
        "component_aliases: {}\n",
        set(), set(), "expected schema_version",
    )


def test_rejects_empty_names():
    _both_raise(
        "schema_version: 1\ncomponent_aliases:\n  '': C2\n",
        {"C2"}, set(), "empty name",
    )


def test_rejects_self_alias():
    _both_raise(
        "schema_version: 1\ncomponent_aliases:\n  LEGACY_A: LEGACY_A\n",
        {"C2"}, set(), "maps a name to itself",
    )


def test_rejects_non_mapping_aliases():
    _both_raise(
        "schema_version: 1\ncomponent_aliases: [1, 2]\n",
        set(), set(), "must be a mapping",
    )


def test_rejects_non_string_keys():
    _both_raise(
        "schema_version: 1\ncomponent_aliases:\n  1: C2\n",
        {"C2"}, set(), "must be strings",
    )


def test_rejects_non_string_values():
    _both_raise(
        "schema_version: 1\ncomponent_aliases:\n  LEGACY_A: 5\n",
        {"C2"}, set(), "must be strings",
    )


def test_loop_alias_validation_uses_loop_namespace():
    _both_raise(
        "schema_version: 1\nloop_aliases:\n  LEGACY_LOOP: MISSING_LOOP\n",
        set(), {"REAL_LOOP"}, "missing loop",
    )


def test_loop_aliases_valid_path_matches_oracle(tmp_path):
    path = tmp_path / "ok.yaml"
    path.write_text(
        "schema_version: 1\nloop_aliases:\n  LEGACY_LOOP: REAL_LOOP\n",
        encoding="utf-8",
    )
    py_m = _oracle.load_reference_alias_manifest(path, component_refs=set(), loop_names={"REAL_LOOP"})
    rs_m = LOAD_MANIFEST(str(path), component_refs=set(), loop_names={"REAL_LOOP"})
    assert _manifest_key(rs_m) == _manifest_key(py_m)


def test_manifest_equality_and_fields_match_oracle(tmp_path):
    path = tmp_path / "ok2.yaml"
    path.write_text(
        "schema_version: 1\ncomponent_aliases:\n  A: C2\n  B: C3\n",
        encoding="utf-8",
    )
    py_m = _oracle.load_reference_alias_manifest(path, component_refs={"C2", "C3"}, loop_names=set())
    rs_m = LOAD_MANIFEST(str(path), component_refs={"C2", "C3"}, loop_names=set())
    assert (rs_m == rs_m) == (py_m == py_m)
    assert rs_m.component_aliases == py_m.component_aliases
    assert rs_m.loop_aliases == py_m.loop_aliases
    # frozen dataclass: no attribute assignment
    with pytest.raises(AttributeError):
        py_m.component_aliases = {}
    with pytest.raises(AttributeError):
        rs_m.component_aliases = {}


def test_missing_file_raises_same_error(tmp_path):
    missing = tmp_path / "missing.yaml"
    with pytest.raises(FileNotFoundError):
        _oracle.load_reference_alias_manifest(missing, component_refs=set(), loop_names=set())
    with pytest.raises(FileNotFoundError):
        LOAD_MANIFEST(str(missing), component_refs=set(), loop_names=set())
