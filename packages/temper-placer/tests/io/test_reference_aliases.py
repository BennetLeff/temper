"""Tests for source-backed placement reference manifests."""

from pathlib import Path

import pytest

from temper_placer.io.reference_aliases import load_reference_alias_manifest

ROOT = Path(__file__).parents[2]
MANIFEST = ROOT / "configs" / "temper_constraints.references.yaml"


def test_production_manifest_contains_only_existing_targets() -> None:
    """Every alias target must be a live ref on the current production board.

    The ref set is hardcoded from the board (post-#517/#521, 169 components)
    so a manifest edit that points an alias at a non-existent component — or
    at the wrong component, like the pre-re-solve stale targets — fails the
    loader's missing-target check instead of passing vacuously.
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
            "C38",
            "C39",
            "R23",
            "R27",
            "R31",
            "T1",
            "U4",
            "U7",
            "U8",
            "U9",
            "U27",
        },
        loop_names=set(),
    )

    # Key mappings re-derived 2026-08-01 from board sheetpaths
    # (e.g. ...hb.gate_hs.driver -> U7). These are the post-re-solve
    # designators; the #498 branch's pre-re-solve values were different.
    assert manifest.component_aliases["U_MCU"] == "U27"
    assert manifest.component_aliases["D_BOOT"] == "U8"
    assert manifest.component_aliases["U_GATE"] == "U7"
    assert manifest.component_aliases["U_BUCK"] == "U4"
    assert manifest.component_aliases["R_GATE_H"] == "R23"
    assert manifest.component_aliases["C_CT_FILT"] == "C28"
    assert manifest.loop_aliases == {}


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


def test_manifest_rejects_self_alias(tmp_path: Path) -> None:
    path = tmp_path / "self.references.yaml"
    path.write_text("schema_version: 1\ncomponent_aliases:\n  LEGACY_A: LEGACY_A\n", encoding="utf-8")
    with pytest.raises(ValueError, match="maps a name to itself"):
        load_reference_alias_manifest(path, component_refs={"C2"}, loop_names=set())
