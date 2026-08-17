"""Tests for source-backed placement reference manifests."""

from pathlib import Path

import pytest
from temper_io_types import load_reference_alias_manifest

ROOT = Path(__file__).parents[2]
MANIFEST = ROOT / "configs" / "temper_constraints.references.yaml"


def test_production_manifest_contains_only_existing_targets() -> None:
    """Every alias target must be a live ref on the current production board.

    The ref set is hardcoded from the board (post-#517/#521, 169 components)
    so a manifest edit that points an alias at a non-existent component — or
    at the wrong component, like the pre-re-solve stale targets — fails the
    loader's missing-target check instead of passing vacuously.

    RE-DERIVED 2026-08-13 (board/schematic resync): the ref set and every
    assertion below were re-verified by direct Sheetpath match against the
    resynced board (see temper_constraints.references.yaml's own updated
    provenance/inline notes) -- 8 of the targets below changed designator
    (D_BOOT/U_RTD/TH_HEATSINK/R_GATE_H(IGH)/R_GATE_L(OW)/U_GATE/U_BUCK --
    see the manifest file's own inline "-- was X pre-resync" comments for
    the individual before/after pairs).
    """
    manifest = load_reference_alias_manifest(
        MANIFEST,
        component_refs={
            "C2",
            "C3",
            "C6",
            "C17",
            "C24",
            "C28",
            "C39",
            "C40",
            "R18",
            "R22",
            "R25",
            "R55",
            "T1",
            "U3",
            "U6",
            "U7",
            "U8",
            "U27",
        },
        loop_names=set(),
    )

    # Key mappings re-derived 2026-08-13 from board sheetpaths against the
    # resynced board (e.g. ...hb.gate_hs.driver -> U6, not the pre-resync
    # U7 -- refdes is not stable identity across a resync, Sheetpath is).
    assert manifest.component_aliases["U_MCU"] == "U27"
    assert manifest.component_aliases["D_BOOT"] == "U7"
    assert manifest.component_aliases["U_GATE"] == "U6"
    assert manifest.component_aliases["U_BUCK"] == "U3"
    assert manifest.component_aliases["R_GATE_H"] == "R18"
    assert manifest.component_aliases["C_CT_FILT"] == "C28"
    assert manifest.loop_aliases == {}

    # Added 2026-08-12 (docs/evidence/2026-08-12-thermal-emi-declaration-drift.md):
    # thermal_management.yaml's own spelling of four already-verified concepts,
    # plus TH_HEATSINK (safety.thermal.ntc, THM-01's heatsink-lug-mount NTC).
    assert manifest.component_aliases["U_RTD"] == "U8"
    assert manifest.component_aliases["TH_HEATSINK"] == "R55"
    assert manifest.component_aliases["R_GATE_HIGH"] == "R18"
    assert manifest.component_aliases["R_GATE_LOW"] == "R22"
    assert manifest.component_aliases["C_VCC2"] == "C17"


def test_manifest_rejects_alias_source_that_is_live(tmp_path: Path) -> None:
    path = tmp_path / "live.references.yaml"
    path.write_text("schema_version: 1\ncomponent_aliases:\n  C2: C3\n", encoding="utf-8")
    with pytest.raises(ValueError, match="already a live name"):
        load_reference_alias_manifest(path, component_refs={"C2", "C3"}, loop_names=set())


def test_manifest_rejects_alias_target_missing_from_board(tmp_path: Path) -> None:
    path = tmp_path / "missing.references.yaml"
    path.write_text("schema_version: 1\ncomponent_aliases:\n  LEGACY_A: C999\n", encoding="utf-8")
    with pytest.raises(ValueError, match="targets missing component"):
        load_reference_alias_manifest(path, component_refs={"C2"}, loop_names=set())


def test_manifest_rejects_unknown_schema_version(tmp_path: Path) -> None:
    path = tmp_path / "bad-schema.references.yaml"
    path.write_text("schema_version: 2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="schema_version"):
        load_reference_alias_manifest(path, component_refs=set(), loop_names=set())


def test_manifest_rejects_empty_names(tmp_path: Path) -> None:
    path = tmp_path / "empty.references.yaml"
    path.write_text("schema_version: 1\ncomponent_aliases:\n  '': C2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="empty name"):
        load_reference_alias_manifest(path, component_refs={"C2"}, loop_names=set())


def test_manifest_rejects_escape_decoded_control_char_source(tmp_path: Path) -> None:
    """The lM4 discriminator, in the suites, oracle-free.

    PyYAML decodes the double-quoted escape ``"\\x1c"`` into U+001C (the
    Reader validates the raw stream, not decoded escapes). The kept Python
    ``str.strip`` call-back (reference_aliases.rs:182) treats U+001C-U+001F
    as whitespace, so the decoded source name strips to empty and the
    manifest is REJECTED. The lM4 mutant (Rust ``str::trim`` instead of the
    strip call-back) keeps U+001C non-empty — pinned by the in-crate unit
    test ``rust_trim_keeps_u001c_where_python_strip_removes_it``
    (reference_aliases.rs:247-261) — and would ACCEPT this manifest, so the
    ``pytest.raises(ValueError)`` below fails under the mutant. The
    differential's parity form (``test_reference_aliases_rust_differential.py:201-225``)
    still adds breadth: all of U+001C-U+001F plus any future
    Python-whitespace-class divergence.
    """
    path = tmp_path / "ctrl.references.yaml"
    path.write_text('schema_version: 1\ncomponent_aliases:\n  "\\x1c": C2\n', encoding="utf-8")
    with pytest.raises(ValueError, match="empty name"):
        load_reference_alias_manifest(path, component_refs={"C2"}, loop_names=set())


def test_manifest_rejects_self_alias(tmp_path: Path) -> None:
    path = tmp_path / "self.references.yaml"
    path.write_text("schema_version: 1\ncomponent_aliases:\n  LEGACY_A: LEGACY_A\n", encoding="utf-8")
    with pytest.raises(ValueError, match="maps a name to itself"):
        load_reference_alias_manifest(path, component_refs={"C2"}, loop_names=set())
