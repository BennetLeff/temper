"""Board values must agree with the BOM-backed schematic identity."""

from __future__ import annotations

import inspect
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_current_sense_native import _assign_board_bom_values, build  # noqa: E402


def test_nominal_value_is_replaced_by_authoritative_mpn() -> None:
    component = SimpleNamespace(ref="C7", value="100nF")
    netlist = SimpleNamespace(components={"C7": component})
    _assign_board_bom_values(netlist, {"C7": "C0603C104K5RACTU"})
    assert component.value == "C0603C104K5RACTU"


def test_missing_bom_identity_rejects_before_mutation() -> None:
    component = SimpleNamespace(ref="C7", value="100nF")
    netlist = SimpleNamespace(components={"C7": component})
    with pytest.raises(ValueError, match="C7"):
        _assign_board_bom_values(netlist, {})
    assert component.value == "100nF"


def test_current_sense_metadata_defaults_are_preserved() -> None:
    parameters = inspect.signature(build).parameters
    assert parameters["sheet_name"].default == "CurrentSense"
    assert parameters["manifest_schema"].default == "zapote.current-sense.native-source-manifest.v1"
