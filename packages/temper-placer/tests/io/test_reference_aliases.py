"""Tests for source-backed placement reference manifests."""

from pathlib import Path

import pytest

from temper_placer.io.reference_aliases import load_reference_alias_manifest

ROOT = Path(__file__).parents[2]
MANIFEST = ROOT / "configs" / "temper_constraints.references.yaml"


def test_production_manifest_contains_only_existing_targets() -> None:
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
            "R18",
            "R22",
            "R25",
            "T1",
            "U3",
            "U6",
            "U7",
            "U8",
            "U26",
        },
        loop_names=set(),
    )

    assert manifest.component_aliases["U_MCU"] == "U26"
    assert manifest.component_aliases["D_BOOT"] == "U7"
    assert manifest.loop_aliases == {}


def test_manifest_rejects_alias_source_that_is_live(tmp_path: Path) -> None:
    path = tmp_path / "live.references.yaml"
    path.write_text("schema_version: 1\ncomponent_aliases:\n  C2: C3\n", encoding="utf-8")
    with pytest.raises(ValueError, match="already a live name"):
        load_reference_alias_manifest(path, component_refs={"C2", "C3"}, loop_names=set())
