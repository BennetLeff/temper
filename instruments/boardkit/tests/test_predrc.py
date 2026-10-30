"""predrc.PreDRC: one passing and one failing case per check, on tiny synthetic boards."""

import pytest
from fixtures import LIB, T, V, design, part, routing

from temper_boardkit import predrc

R1 = part("R1", "R", 10, 10, p1="A", p2="B")
R2 = part("R2", "R", 20, 10, p1="A", p2="B")


def drc(**kw):
    return predrc.PreDRC(LIB, **kw)


def kinds(res):
    return sorted(v["kind"] for v in res["violations"])


def routed():
    """R1 and R2 joined pad to pad on both nets: clean."""
    return routing(
        [
            T("A", (9.175, 10), (9.175, 12), (19.175, 12), (19.175, 10)),
            T("B", (10.825, 10), (10.825, 8), (20.825, 8), (20.825, 10)),
        ]
    )


def test_clean_board_passes():
    res = drc().check(design(R1, R2), routed(), cache=False)
    assert res["violations"] == [] and res["unconnected"] == []
    assert res["counts"] == {"pads": 4, "tracks": 6, "vias": 0}


def test_unconnected():
    res = drc().check(design(R1, R2), routing(), cache=False)
    assert {u["net"] for u in res["unconnected"]} == {"A", "B"}


def test_clearance():
    r = routed()
    r["tracks"].append(T("C", (14, 11.75), (16, 11.75)))  # 0.05 mm from the A track edge
    res = drc().check(design(R1, R2), r, cache=False)
    assert "clearance" in kinds(res)
    r["tracks"][-1] = T("C", (14, 11.5), (16, 11.5))
    assert "clearance" not in kinds(drc().check(design(R1, R2), r, cache=False))


def test_edge_and_exemption():
    edge = design(part("J1", "R", 1.0, 10, p1="A", p2="B"), outline=(0, 0, 30, 20))
    assert "edge" in kinds(drc().check(edge, routing(), cache=False))
    assert "edge" not in kinds(drc(edge_exempt=("J",)).check(edge, routing(), cache=False))


def test_hole_and_hole2hole():
    d = design(part("J2", "TH", 15, 15, p1="P"))
    near = routing(
        [T("Q", (14, 15.9), (16, 15.9))]
    )  # 0.4 - 0.1 = 0.3 from the 0.8 drill edge... clear
    assert "hole" not in kinds(drc().check(d, near, cache=False))
    vias = routing(
        vias=[V("Q", 15, 16.0)]
    )  # via drill 0.15 + 0.4 -> 0.45 edge gap, ring overlaps pad
    res = drc().check(d, vias, cache=False)
    assert "clearance" in kinds(res)
    pair = routing(vias=[V("Q", 5, 5), V("R", 5.5, 5, d=0.45)])
    assert "hole2hole" in kinds(drc().check(design(), pair, cache=False))
    far = routing(vias=[V("Q", 5, 5), V("R", 6.0, 5, d=0.45)])
    assert "hole2hole" not in kinds(drc().check(design(), far, cache=False))


def test_keepout_tracks_vs_fill_only():
    ko = {
        "name": "void",
        "layers": ["F.Cu"],
        "points": [[4, 4], [6, 4], [6, 6], [4, 6]],
        "tracks": True,
    }
    r = routing([T("A", (3, 5), (7, 5))], keepouts=[ko])
    assert "keepout" in kinds(drc().check(design(), r, cache=False))
    r["keepouts"][0]["tracks"] = False
    assert "keepout" not in kinds(drc().check(design(), r, cache=False))


def test_via_on_land_and_exposed():
    d = design(part("U1", "EP", 10, 10, p1="S", p2="GND"))
    r = routing(vias=[V("GND", 10.5, 10)])
    assert "via_land" in kinds(drc().check(d, r, cache=False))
    assert "via_land" not in kinds(drc(exposed={("U1", "2")}).check(d, r, cache=False))


def test_width():
    assert "width" in kinds(
        drc().check(design(), routing([T("A", (1, 1), (5, 1), w=0.1)]), cache=False)
    )
    assert "width" in kinds(drc().check(design(), routing(vias=[V("A", 5, 5, d=0.4)]), cache=False))
    assert "width" not in kinds(
        drc().check(design(), routing([T("A", (1, 1), (5, 1), w=0.15)]), cache=False)
    )


def test_courtyard():
    assert "courtyard" in kinds(
        drc().check(design(R1, part("R3", "R", 12.5, 10)), routing(), cache=False)
    )
    assert "courtyard" not in kinds(
        drc().check(design(R1, part("R3", "R", 13.5, 10)), routing(), cache=False)
    )


def test_angle_acid_trap():
    r = routing([T("A", (1, 1), (5, 1), (1, 2))])
    assert "angle" in kinds(drc().check(design(), r, cache=False))
    assert "angle" not in kinds(
        drc().check(design(), routing([T("A", (1, 1), (5, 1), (9, 5))]), cache=False)
    )


def test_dangling_and_plane():
    lone = routing(vias=[V("GND", 5, 5)])
    assert "dangling" in kinds(drc().check(design(), lone, cache=False))
    assert "dangling" not in kinds(drc(plane=("GND", "In1.Cu")).check(design(), lone, cache=False))
    stub = routing([T("A", (9.175, 10), (9.175, 14))])
    res = drc().check(design(R1), stub, cache=False)
    assert [v["at"] for v in res["violations"] if v["kind"] == "dangling"] == [[9.175, 14]]


def test_board_holes_and_cache(tmp_path):
    d = design(holes=[(5, 5)])
    k = drc(cache_path=tmp_path / "c.pkl")
    res = k.check(d, routing([T("A", (6.5, 3), (6.5, 7))]), cache=True)
    assert "hole" in kinds(res) and (tmp_path / "c.pkl").exists()
    assert kinds(k.check(d, routing(), cache=True)) == []


def test_craft_inputs_and_summary():
    pads, drills, board = drc().craft_inputs(design(R1))
    assert [p["pad"] for p in pads] == ["1", "2"] and board == {"outline": [0, 0, 30, 20]}
    assert pads[0]["size"] == pytest.approx([0.8, 0.95], abs=1e-3)
    s = predrc.summary(drc().check(design(R1, R2), routing(), cache=False))
    assert "unconnected A" in s
    tally = predrc.compare(
        {"violations": [{"kind": "edge"}], "unconnected": []},
        {
            "violations": [{"type": "copper_edge_clearance"}, {"type": "silk_overlap"}],
            "unconnected_items": [],
        },
    )
    assert "kicad-only:silk_overlap" in tally
