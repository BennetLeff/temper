"""model.Layout: pad addressing, rigid-group transform and the hand-routing helpers."""

import pytest
from fixtures import LIB, part

from temper_boardkit import model


def layout():
    parts = {"R1": part("R1", "R", 10, 10, 90, p1="A", p2="B")}
    groups = {"g": {"pivot": (0, 0), "to": (5, 5), "turn": 90, "refs": ["R1"]}}
    return model.Layout(
        LIB, parts, groups, {"tracks": [], "vias": [], "keepouts": []}, src_file="test_model.py"
    )


def test_rot_kicad_convention():
    # +90 (counter-clockwise on screen, y down): local +x goes to board -y
    assert model.rot(1, 0, 90) == pytest.approx((0, -1))
    assert model.unrot(*model.rot(0.3, 0.7, 33), 33) == pytest.approx((0.3, 0.7))
    assert model.norm_rot(-180) == 180 and model.norm_rot(270) == -90
    assert model.r3(-0.00001) == 0.0 and str(model.r3(-0.0)) == "0.0"


def test_pad_addressing_and_group():
    L = layout()
    assert L.P("R1.1") == (10.0, 10.825)  # pad 1 at local (-0.825, 0) turned 90
    assert L.P("R1.2", 0.1, -0.1) == (10.1, 9.075)
    assert L.B("g", 1, 0) == (5.0, 4.0)
    with pytest.raises(KeyError):
        L.pad_local("R1", "9")


def test_tracks_vias_and_src():
    L = layout()
    L.T("A", "F.Cu", "R1.1", (10, 12))
    L.T45("A", "F.Cu", (0, 0), (3, 1), "h")
    L.V("A", "R1.1")
    tr = L.routing["tracks"]
    assert tr[0]["points"] == [[10.0, 10.825], [10.0, 12.0]]
    assert tr[1]["points"] == [[0.0, 0.0], [2.0, 0.0], [3.0, 1.0]]
    assert tr[0]["src"].startswith("test_model.py:")
    assert L.routing["vias"][0] == {
        "net": "A",
        "at": [10.0, 10.825],
        "diameter": 0.45,
        "drill": 0.3,
        "src": L.routing["vias"][0]["src"],
    }
    with pytest.raises(AssertionError):
        L.T45("A", "F.Cu", (0, 0), (1, 3), "h")  # the longer span is vertical


def test_drop_widen_ko():
    L = layout()
    L.routing["tracks"].append(
        {"net": "A", "layer": "B.Cu", "width": 0.2, "points": [[1, 1], [2, 1]], "src": "copy:g"}
    )
    L.routing["vias"].append(
        {"net": "A", "at": [5, 5], "diameter": 0.6, "drill": 0.3, "src": "copy:g"}
    )
    L.V("A", 5, 5)  # replaces the copied via at the same spot
    assert [v["src"] for v in L.routing["vias"]] == [L.routing["vias"][0]["src"]] and len(
        L.routing["vias"]
    ) == 1
    L.WIDEN("A", "B.Cu", 0, 0, 3, 3, 0.5)
    assert L.routing["tracks"][0]["width"] == 0.5
    with pytest.raises(AssertionError):
        L.WIDEN("A", "F.Cu", 0, 0, 3, 3, 0.5)
    L.DROP("A", 0, 0, 3, 3)
    assert L.routing["tracks"] == []
    L.KO("void", [(0, 0), (1, 0), (1, 1)])
    assert L.routing["keepouts"][0]["layers"] == ["In1.Cu", "In2.Cu", "B.Cu"]
