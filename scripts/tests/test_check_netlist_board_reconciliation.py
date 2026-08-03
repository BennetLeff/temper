"""Tests for scripts/check_netlist_board_reconciliation.py (plan
2026-08-02-021, R16, U3).

Covers the gate script's fail-closed contract: exit 0 when the board and
netlist agree, exit 3 (VIOLATION) when any reconciliation class fires, exit 5
(GATE ERROR) on a stale design netlist or a missing board -- never a clean
pass on data the gate could not trust.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_netlist_board_reconciliation as gate  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"
REAL_NETLIST = REPO_ROOT / "elec" / "build" / "default.net"


def _write_netlist(path: Path, comps: list[tuple[str, str, str]]) -> None:
    """[(ref, footprint, sheetpath_suffix), ...] -- same shape as the real
    compiled netlist's (sheetpath (names "...:Top::<suffix>")) records. Each
    component gets one pin on net 'gnd' so the net membership reconciles with
    the single-pad board footprints."""
    blocks = []
    for ref, footprint, suffix in comps:
        blocks.append(
            f'    (comp (ref "{ref}")\n'
            f'      (value "?")\n'
            f'      (footprint "{footprint}")\n'
            f'      (sheetpath (names "/repo/elec/src/main.ato:Top::{suffix}") '
            f'(tstamps "deadbeef"))\n'
            f'      (tstamps "deadbeef"))'
        )
    nodes = "".join(f'\n      (node (ref "{ref}") (pin "1"))' for ref, _fp, _s in comps)
    path.write_text(
        "(export (version \"E\")\n"
        "  (components\n" + "\n".join(blocks) + "\n  )\n"
        "  (nets\n"
        f'    (net (code "1") (name "gnd"){nodes})\n'
        "  )\n)\n"
    )


def _write_board(path: Path, comps: list[tuple[str, str]]) -> None:
    """[(ref, sheetpath), ...] footprints with a single pad on net 1."""
    from kiutils.board import Board
    from kiutils.footprint import Footprint, Pad
    from kiutils.items.common import Net as KiNet
    from kiutils.items.common import Position

    board = Board(version="20230121", generator="pytest", nets=[])
    fps = []
    for ref, sheetpath in comps:
        fp = Footprint(entryName="temper:Test", tstamp=f"fp-{ref}", position=Position(0, 0))
        fp.properties = {"Reference": ref, "Value": "?", "Sheetpath": sheetpath}
        fp.pads = [
            Pad(number="1", type="smd", tstamp=f"fp-{ref}-p1", net=KiNet(number=1, name="gnd"))
        ]
        fps.append(fp)
    board.footprints = fps
    board.to_file(str(path))


def _matching_pair(tmp_path: Path) -> tuple[Path, Path]:
    board_path = tmp_path / "board.kicad_pcb"
    netlist_path = tmp_path / "default.net"
    _write_board(board_path, [("C1", "a.cap1"), ("C2", "b.cap2")])
    _write_netlist(
        netlist_path,
        [
            ("C1", "temper:Test", "a.cap1"),
            ("C2", "temper:Test", "b.cap2"),
        ],
    )
    return board_path, netlist_path


def test_gate_exits_zero_when_board_and_netlist_agree(tmp_path: Path) -> None:
    board_path, netlist_path = _matching_pair(tmp_path)
    assert gate.run(board_path, netlist_path, tmp_path, skip_freshness=True) == gate.EXIT_OK


def test_gate_exits_three_on_renumbered_pair(tmp_path: Path) -> None:
    """The check script exits non-zero (VIOLATION) when a reconciliation
    class fires -- here a wholesale renumber the refdes SET could not see."""
    board_path, _ = _matching_pair(tmp_path)
    mutated = tmp_path / "renumbered.net"
    _write_netlist(
        mutated,
        [
            ("C2", "temper:Test", "a.cap1"),
            ("C1", "temper:Test", "b.cap2"),
        ],
    )
    assert gate.run(board_path, mutated, tmp_path, skip_freshness=True) == gate.EXIT_VIOLATION


def test_gate_exits_three_on_missing_component(tmp_path: Path) -> None:
    """The tank-capacitor class (a design component with no board footprint)
    fires a MISSING finding and the gate exits 3."""
    board_path, _ = _matching_pair(tmp_path)
    mutated = tmp_path / "missing.net"
    _write_netlist(
        mutated,
        [
            ("C1", "temper:Test", "a.cap1"),
            ("C2", "temper:Test", "b.cap2"),
            ("C3", "temper:Test", "tank.c_tank3"),
        ],
    )
    assert gate.run(board_path, mutated, tmp_path, skip_freshness=True) == gate.EXIT_VIOLATION


def test_gate_fails_closed_on_stale_netlist(tmp_path: Path) -> None:
    """A stale design netlist fails closed (GATE ERROR), never a clean
    pass against an old design."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "main.ato").write_text("module main\n")
    board_path, netlist_path = _matching_pair(tmp_path)
    past = time.time() - 3600
    import os

    os.utime(netlist_path, (past, past))
    assert gate.run(board_path, netlist_path, src_dir) == gate.EXIT_GATE_ERROR


def test_gate_fails_closed_on_missing_board(tmp_path: Path) -> None:
    _, netlist_path = _matching_pair(tmp_path)
    assert (
        gate.run(tmp_path / "missing.kicad_pcb", netlist_path, tmp_path, skip_freshness=True)
        == gate.EXIT_GATE_ERROR
    )


def test_gate_passes_on_real_board_and_fresh_netlist() -> None:
    """U3 verification: the gate's verdict on the current board is PASS (the
    tank-cap class is PASS-for-missing -- tank.c_tank3 IS in the board file,
    staged off-outline)."""
    if not REAL_BOARD.is_file() or not REAL_NETLIST.is_file():
        pytest.skip("board or compiled netlist missing (run `make netlist`)")
    assert gate.run(REAL_BOARD, REAL_NETLIST, REPO_ROOT / "elec" / "src") == gate.EXIT_OK
