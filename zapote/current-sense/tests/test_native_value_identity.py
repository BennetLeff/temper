"""Board values must agree with the BOM-backed schematic identity."""

from __future__ import annotations

import inspect
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import gen_pcb_skeleton as skeleton  # noqa: E402
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


def _candidate_terminal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, blank_copper: bool):
    """A REDCUBE-style fixture: four paste apertures, one NPTH, four pad-1 legs."""
    paste_pads = []
    copper_pads = []
    for index, (x, y) in enumerate(((0, 0), (0, 5), (5, 0), (5, 5))):
        layers = '"F.Cu" "F.Paste"' if blank_copper and index == 0 else '"F.Paste"'
        paste_pads.append(
            f'(pad "" smd circle (at {x} {y}) (size 2 2) (layers {layers}))'
        )
        copper_pads.append(
            f'(pad "1" thru_hole circle (at {x} {y}) (size 2 2) '
            '(drill 1) (layers "*.Cu" "*.Mask"))'
        )
    footprint = tmp_path / "CandidatePaste.kicad_mod"
    footprint.write_text(
        '(footprint "CandidatePaste" (version 20240108) (generator "pcbnew") '
        '(layer "F.Cu") (attr through_hole) '
        + " ".join(paste_pads)
        + ' (pad "" np_thru_hole circle (at 2.5 2.5) (size 1 1) '
        '(drill 1) (layers "*.Cu" "*.Mask")) '
        + " ".join(copper_pads)
        + ")\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(skeleton, "resolve_footprint", lambda *_: footprint)
    netlist = skeleton.Netlist(
        components={
            "J10": skeleton.Component("J10", "terminal", "Test:CandidatePaste", "fixture", "/J10")
        },
        nets={"1": skeleton.Net("1", "BUS_P", [("J10", "1")])},
    )
    output = tmp_path / "candidate.kicad_pcb"
    return netlist, output


def test_paste_only_apertures_remain_and_four_same_number_copper_pads_get_net(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from kiutils.board import Board

    netlist, output = _candidate_terminal(tmp_path, monkeypatch, blank_copper=False)
    skeleton.generate_candidate_board(
        netlist, {("J10", "1"): "1"}, set(), tmp_path / "unused-fp-lib-table",
        (0.0, 0.0, 40.0, 40.0), {"J10": (20.0, 20.0, 0.0)}, output,
    )
    pads = Board.from_file(str(output)).footprints[0].pads
    assert len([pad for pad in pads if pad.number == "" and pad.type == "smd"]) == 4
    assert len([pad for pad in pads if pad.number == "1" and pad.net.name == "BUS_P"]) == 4
    assert skeleton.candidate_oracle_verify(
        output, netlist, {("J10", "1"): "1"}, (0.0, 0.0, 40.0, 40.0)
    )


def test_unnumbered_copper_pad_still_requires_explicit_pin_disposition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    netlist, output = _candidate_terminal(tmp_path, monkeypatch, blank_copper=True)
    with pytest.raises(ValueError, match="footprint pad '' on J10 is neither mapped"):
        skeleton.generate_candidate_board(
            netlist, {("J10", "1"): "1"}, set(), tmp_path / "unused-fp-lib-table",
            (0.0, 0.0, 40.0, 40.0), {"J10": (20.0, 20.0, 0.0)}, output,
        )
    assert not output.exists()


def test_mapped_pin_cannot_land_only_on_paste(tmp_path, monkeypatch):
    from kiutils.footprint import Footprint

    netlist, output = _candidate_terminal(tmp_path, monkeypatch, blank_copper=False)
    path = tmp_path / "CandidatePaste.kicad_mod"
    footprint = Footprint.from_file(str(path))
    for pad in footprint.pads:
        if pad.number == "1":
            pad.type = "smd"
            pad.layers = ["F.Paste"]
            pad.drill = None
    footprint.to_file(str(path))
    with pytest.raises(ValueError, match="have no copper"):
        skeleton.generate_candidate_board(
            netlist, {("J10", "1"): "1"}, set(), tmp_path / "unused-fp-lib-table",
            (0.0, 0.0, 40.0, 40.0), {"J10": (20.0, 20.0, 0.0)}, output,
        )
    assert not output.exists()


def test_rotated_footprint_rotates_its_pads(tmp_path, monkeypatch):
    """Pad orientation is absolute in a KiCad board: rotation must reach pads."""
    from kiutils.board import Board

    netlist, output = _candidate_terminal(tmp_path, monkeypatch, blank_copper=False)
    path = tmp_path / "CandidatePaste.kicad_mod"
    # Rectangular pads make orientation observable.
    path.write_text(path.read_text().replace("circle", "rect").replace("(size 2 2)", "(size 3 1)"))
    skeleton.generate_candidate_board(
        netlist, {("J10", "1"): "1"}, set(), tmp_path / "unused-fp-lib-table",
        (0.0, 0.0, 40.0, 40.0), {"J10": (20.0, 20.0, 90.0)}, output,
    )
    footprint = Board.from_file(str(output)).footprints[0]
    assert footprint.position.angle == 90.0
    assert {pad.position.angle for pad in footprint.pads} == {90.0}
