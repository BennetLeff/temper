from pathlib import Path

import pytest

from temper_placer.validation.real_board_inventory import InventoryError, build_inventory

ROOT = Path(__file__).resolve().parents[4]


def test_current_generated_board_has_provenance_and_identity() -> None:
    inventory = build_inventory(ROOT / "elec/build/default.net", source_root=ROOT / "elec/src")
    assert inventory.artifact["sha256"]
    assert inventory.artifact["source_files"]
    assert inventory.components
    assert inventory.nets
    assert len({item["ref"] for item in inventory.components}) == len(inventory.components)


def test_missing_artifact_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(InventoryError, match="missing or empty"):
        build_inventory(tmp_path / "missing.net", source_root=ROOT / "elec/src")
