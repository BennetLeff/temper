"""Regression test for the net-ordinal corruption bug in resync_pcb_netlist.py.

Falsifier (docs/evidence/2026-07-27-resync-net-ordinal-fix.md): "resyncing
preserves all routed copper and its net assignments." KiCad stores each
segment's/via's/zone's net as a bare ORDINAL INDEX into the board's net
table, not a name. The pre-fix tool rebuilt `board.nets` (sorted
alphabetically, renumbered 1..N) at the end of `resync()` but never touched
`board.traceItems` or `board.zones` -- so whenever the rebuild reordered the
net table (which it does on almost any real edit: add/remove/rename a net
shifts everyone after it alphabetically), every piece of copper kept
pointing at its OLD ordinal, which now names a DIFFERENT net. Measured on
the real board: 79% of segments and 75% of vias would have been silently
reassigned.

This test builds a minimal board+netlist pair via kiutils/hand-written
S-expressions, with net names chosen so that alphabetical resorting is
GUARANTEED to reorder every one of them (old board order z/a/m -> new
sorted order a/m/z), then asserts every copper item's net NAME (not
ordinal -- a test that only checked counts would not have caught this) is
unchanged after resync. A counts-only assertion would pass on the buggy
tool (segment/via/zone counts are never added or removed by the bug); only
a name-identity check catches it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kiutils.board import Board  # noqa: E402
from kiutils.items.brditems import Segment, Via  # noqa: E402
from kiutils.items.common import Net, Position  # noqa: E402
from kiutils.items.zones import Zone  # noqa: E402

from resync_pcb_netlist import NetRemapError, resync  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_netlist(path: Path, net_names: list[str]) -> None:
    """Minimal KiCad-format netlist: zero components, N nets. Zero
    components is deliberate -- it isolates the test to the net-ordinal
    remap logic, independent of footprint resolution/fp-lib-table, which
    resync's footprint pipeline already covers elsewhere and is unrelated
    to this bug (the bug is entirely in board.traceItems/board.zones)."""
    nets_sexpr = "\n".join(
        f'    (net (code "{i + 1}") (name "{name}"))' for i, name in enumerate(net_names)
    )
    path.write_text(
        f"""(export (version "E")
  (components)
  (nets
{nets_sexpr}
  )
)
"""
    )


def _build_scrambled_board(path: Path) -> None:
    """Old board net table deliberately in NON-alphabetical order (as a real
    KiCad board's net table is: nets are numbered in creation order, not
    name order), guaranteeing every one of the 3 nets lands at a different
    ordinal once the tool rebuilds the table sorted by name (a/m/z).

        old ordinal 1 = "zzz_net"   -> new ordinal 3
        old ordinal 2 = "aaa_net"   -> new ordinal 1
        old ordinal 3 = "mmm_net"   -> new ordinal 2

    Carries one Segment and one Via on each of the 3 nets, plus a Zone, so
    every corruption path (segment/via/zone) is covered by a single fixture.
    """
    board = Board()
    board.version = "20230121"
    board.generator = "pytest"
    board.nets = [
        Net(number=1, name="zzz_net"),
        Net(number=2, name="aaa_net"),
        Net(number=3, name="mmm_net"),
    ]
    board.traceItems = [
        Segment(start=Position(0, 0), end=Position(1, 1), width=0.2, layer="F.Cu", net=1, tstamp="seg-on-zzz"),
        Segment(start=Position(0, 0), end=Position(2, 2), width=0.2, layer="F.Cu", net=2, tstamp="seg-on-aaa"),
        Segment(start=Position(0, 0), end=Position(3, 3), width=0.2, layer="F.Cu", net=3, tstamp="seg-on-mmm"),
        Via(position=Position(5, 5), size=0.6, drill=0.3, layers=["F.Cu", "B.Cu"], net=1, tstamp="via-on-zzz"),
    ]
    board.zones = [
        Zone(net=2, netName="aaa_net", layers=["F.Cu"], tstamp="zone-on-aaa"),
    ]
    board.to_file(str(path))


# tstamp -> expected net NAME (not ordinal -- ordinals are EXPECTED to
# change; the invariant under test is that the NAME each item resolves to
# is unchanged).
EXPECTED_NAME_BY_TSTAMP = {
    "seg-on-zzz": "zzz_net",
    "seg-on-aaa": "aaa_net",
    "seg-on-mmm": "mmm_net",
    "via-on-zzz": "zzz_net",
}
EXPECTED_ZONE_NAME_BY_TSTAMP = {"zone-on-aaa": "aaa_net"}


def _resolve_names(board: Board) -> tuple[dict[str, str], dict[str, str]]:
    """Resolve every copper item's net ordinal to a name using the board's
    OWN (post-resync) net table -- exactly what a human opening the file in
    KiCad would see."""
    number_to_name = {n.number: n.name for n in board.nets}
    number_to_name[0] = ""
    trace_names = {
        item.tstamp: number_to_name[item.net]
        for item in board.traceItems
        if item.tstamp in EXPECTED_NAME_BY_TSTAMP
    }
    zone_names = {
        zone.tstamp: number_to_name[zone.net]
        for zone in board.zones
        if zone.tstamp in EXPECTED_ZONE_NAME_BY_TSTAMP
    }
    return trace_names, zone_names


def test_net_table_is_guaranteed_to_reorder(tmp_path: Path) -> None:
    """Sanity check on the fixture itself: confirm the scrambled old order
    really does differ from the alphabetically-sorted new order for every
    net, so this test cannot pass by accident (e.g. if resync happened to
    not reorder anything, both the buggy and fixed tool would agree)."""
    netlist_path = tmp_path / "default.net"
    _write_netlist(netlist_path, ["aaa_net", "mmm_net", "zzz_net"])
    board_path = tmp_path / "board.kicad_pcb"
    _build_scrambled_board(board_path)

    old_board = Board.from_file(str(board_path))
    old_number_by_name = {n.name: n.number for n in old_board.nets}
    new_number_by_name = {name: i + 1 for i, name in enumerate(sorted(old_number_by_name))}

    assert old_number_by_name != new_number_by_name
    for name in old_number_by_name:
        assert old_number_by_name[name] != new_number_by_name[name], (
            f"net {name!r} coincidentally kept the same ordinal -- fixture "
            "does not actually exercise the reorder case"
        )


def test_resync_preserves_copper_net_names_across_reorder(tmp_path: Path) -> None:
    """The falsifier, after the fix: every copper item's net NAME survives
    a resync that is guaranteed to renumber every net ordinal."""
    netlist_path = tmp_path / "default.net"
    _write_netlist(netlist_path, ["aaa_net", "mmm_net", "zzz_net"])
    board_path = tmp_path / "board.kicad_pcb"
    _build_scrambled_board(board_path)

    report = resync(
        netlist_path=netlist_path,
        board_path=board_path,
        fp_lib_table_path=tmp_path / "fp-lib-table",  # never touched: 0 components
        dry_run=False,
    )

    # Every net ordinal really did change (net_count matches, but the
    # mapping is a genuine permutation) -- otherwise this test would not be
    # distinguishing the fix from the bug.
    assert report["net_count"] == 3
    assert report["copper_items_checked"] == 5  # 3 segments + 1 via + 1 zone
    assert report["copper_orphaned_count"] == 0
    assert report["copper_net_remapped_count"] == 5  # every ordinal changed

    new_board = Board.from_file(str(board_path))
    trace_names, zone_names = _resolve_names(new_board)

    assert trace_names == EXPECTED_NAME_BY_TSTAMP
    assert zone_names == EXPECTED_ZONE_NAME_BY_TSTAMP


def test_prefix_fix_tool_corrupts_copper_names_on_the_same_fixture(tmp_path: Path) -> None:
    """Reproduces the PRE-fix tool's behavior directly (rebuild board.nets,
    do NOT touch traceItems/zones) against the identical fixture used above,
    and asserts it DOES corrupt the net names -- i.e. this fixture is a
    faithful reproduction of the real bug, not a fixture that happens to
    dodge it. This is the "prove the test fails before the fix" evidence,
    executable rather than only narrated: it exercises the buggy code path
    (old_board.nets = list(net_table.values()) with no copper remap) inline
    rather than importing a since-fixed function, so it keeps demonstrating
    the bug even after resync() itself is fixed.
    """
    netlist_path = tmp_path / "default.net"
    _write_netlist(netlist_path, ["aaa_net", "mmm_net", "zzz_net"])
    board_path = tmp_path / "board.kicad_pcb"
    _build_scrambled_board(board_path)

    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from gen_pcb_skeleton import parse_netlist as _parse_netlist

    netlist = _parse_netlist(netlist_path)
    old_board = Board.from_file(str(board_path))

    # Verbatim pre-fix logic from resync_pcb_netlist.py's old line 271-ish:
    # rebuild the net table sorted by name, renumbered 1..N, and write it
    # back -- WITHOUT touching old_board.traceItems or old_board.zones.
    sorted_nets = sorted(netlist.nets.values(), key=lambda n: n.name)
    buggy_net_table = [Net(number=i + 1, name=n.name) for i, n in enumerate(sorted_nets)]
    old_board.nets = buggy_net_table
    old_board.to_file(str(board_path))

    corrupted_board = Board.from_file(str(board_path))
    trace_names, zone_names = _resolve_names(corrupted_board)

    assert trace_names != EXPECTED_NAME_BY_TSTAMP, (
        "the pre-fix reproduction did not corrupt any copper net name -- "
        "this fixture would not have caught the real bug"
    )
    assert zone_names != EXPECTED_ZONE_NAME_BY_TSTAMP


def test_orphaned_copper_fails_closed_instead_of_silently_writing(tmp_path: Path) -> None:
    """A net that has real copper on it in the old board but no longer
    exists in the netlist at all (the deleted-resistor case) must abort the
    resync with NetRemapError and leave the board file UNCHANGED, never
    silently reassign the copper to net 0 or fabricate a mapping."""
    netlist_path = tmp_path / "default.net"
    # "zzz_net" is deliberately absent from the netlist.
    _write_netlist(netlist_path, ["aaa_net", "mmm_net"])
    board_path = tmp_path / "board.kicad_pcb"
    _build_scrambled_board(board_path)
    original_bytes = board_path.read_bytes()

    with pytest.raises(NetRemapError, match="orphaned copper"):
        resync(
            netlist_path=netlist_path,
            board_path=board_path,
            fp_lib_table_path=tmp_path / "fp-lib-table",
            dry_run=False,
        )

    assert board_path.read_bytes() == original_bytes, (
        "resync must not write the board file when it cannot safely remap "
        "every copper item's net"
    )


def test_zone_net_name_inconsistency_fails_closed(tmp_path: Path) -> None:
    """A zone whose `net_name` field disagrees with what its `net` ordinal
    resolves to in the PRE-resync board is already-corrupt input; the tool
    must refuse to guess which of the two disagreeing values is correct."""
    netlist_path = tmp_path / "default.net"
    _write_netlist(netlist_path, ["aaa_net", "mmm_net", "zzz_net"])
    board_path = tmp_path / "board.kicad_pcb"
    _build_scrambled_board(board_path)

    # Corrupt the zone's redundant net_name field so it disagrees with its
    # own net ordinal (ordinal 2 = "aaa_net" per _build_scrambled_board).
    board = Board.from_file(str(board_path))
    for zone in board.zones:
        if zone.tstamp == "zone-on-aaa":
            zone.netName = "mmm_net"
    board.to_file(str(board_path))
    original_bytes = board_path.read_bytes()

    with pytest.raises(NetRemapError, match="disagrees with"):
        resync(
            netlist_path=netlist_path,
            board_path=board_path,
            fp_lib_table_path=tmp_path / "fp-lib-table",
            dry_run=False,
        )

    assert board_path.read_bytes() == original_bytes
