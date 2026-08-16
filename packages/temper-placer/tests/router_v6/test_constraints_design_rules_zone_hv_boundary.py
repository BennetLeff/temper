"""2026-08-13: hyphen-boundary net-classification defect ("Family C" -- see
PR #1145/#1162's "Family A"/"Family B" fixes elsewhere in this repo).

``ClearanceMatrix.parse``'s zone-name HV-keyword match (in
``router_v6/constraints_design_rules.py``) anchored word boundaries on "_"
and start/end-of-string only, never "-". This pins both directions: a
hyphenated zone name that should now match, and one that should not.

See docs/evidence/2026-08-13-hyphen-boundary-clearance-creepage-defect.md.
"""

from __future__ import annotations

from types import SimpleNamespace

from temper_placer.router_v6.constraints_design_rules import ClearanceMatrix


def _fake_board(zone_names: list[str]):
    """A duck-typed "internal Board" (no ``netClasses`` attribute, so
    ``ClearanceMatrix.parse`` takes the zone-extraction branch) with one
    rectangular zone per name."""
    zones = [
        SimpleNamespace(
            name=name,
            polygon=None,
            bounds=(0.0, 0.0, 1.0, 1.0),
            net_classes=None,
        )
        for name in zone_names
    ]
    return SimpleNamespace(zones=zones)


def _zone_clearance(matrix: ClearanceMatrix, name: str) -> float:
    zone = next(z for z in matrix.zone_manager.zones if z.name == name)
    return zone.clearance_mm


def test_hyphen_is_now_a_word_boundary_for_zone_hv_match():
    board = _fake_board(["x-hv", "hv-zone", "keepout-hv-1"])
    matrix = ClearanceMatrix.parse(board)
    assert matrix.zone_manager is not None
    for name in ("x-hv", "hv-zone", "keepout-hv-1"):
        assert _zone_clearance(matrix, name) == 3.0, name


def test_hyphen_boundary_does_not_over_match_zone_name():
    board = _fake_board(["archive", "hive-zone", "shvx-1"])
    matrix = ClearanceMatrix.parse(board)
    assert matrix.zone_manager is not None
    for name in ("archive", "hive-zone", "shvx-1"):
        assert _zone_clearance(matrix, name) == 0.2, name


def test_underscore_boundary_still_works():
    board = _fake_board(["x_hv", "hv_zone"])
    matrix = ClearanceMatrix.parse(board)
    assert matrix.zone_manager is not None
    for name in ("x_hv", "hv_zone"):
        assert _zone_clearance(matrix, name) == 3.0, name
