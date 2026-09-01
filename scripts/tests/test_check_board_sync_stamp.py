"""Tests for scripts/write_board_sync_stamp.py + scripts/check_board_sync_stamp.py.

These two tools are the provenance half of the board/netlist reconciliation
story (2026-08-13 desync postmortem, gap C): `write_board_sync_stamp.py`
records, beside `pcb/temper.kicad_pcb`, a content digest of the board +
netlist it was last verified against (and refuses to write one unless
`check_netlist_board_reconciliation.py` currently passes);
`check_board_sync_stamp.py` fails closed whenever that recorded digest no
longer matches -- board changed, netlist changed, or no stamp exists at all.

Fixture helpers (`_write_netlist`/`_write_board`) are a deliberate,
self-contained COPY of the ones in
`scripts/tests/test_check_netlist_board_reconciliation.py` -- this repo's
own stated convention for gate test fixtures (see that file, and
`check_footprint_drift`/`check_copper_net_consistency`'s own test files):
a test's correctness must not depend on another gate/test module's internal
representation changing out from under it.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_board_sync_stamp as stamp_gate  # noqa: E402
import write_board_sync_stamp  # noqa: E402
from _lib.freshness import compute_inputs_digest, read_stamp  # noqa: E402


def _write_netlist(path: Path, comps: list[tuple[str, str, str]]) -> None:
    """[(ref, footprint, sheetpath_suffix), ...] -- same shape as the real
    compiled netlist's records. Each component gets one pin on net 'gnd' so
    net membership reconciles with the single-pad board footprints."""
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


def _write_stamp(
    board_path: Path, netlist_path: Path, src_dir: Path, repo_root: Path | None = None
) -> int:
    return write_board_sync_stamp.main(
        [
            "--board",
            str(board_path),
            "--netlist",
            str(netlist_path),
            "--src-dir",
            str(src_dir),
            "--repo-root",
            str(repo_root if repo_root is not None else src_dir),
            "--skip-freshness-check",
        ]
    )


class TestWriteBoardSyncStamp:
    def test_refuses_to_stamp_when_not_reconciled(self, tmp_path: Path) -> None:
        """The mutation this whole mechanism exists to catch: a wholesale
        renumber between board and netlist. write_board_sync_stamp.py must
        refuse to write a stamp -- writing one would falsely assert this
        desynced pair is verified."""
        board_path, _ = _matching_pair(tmp_path)
        renumbered = tmp_path / "renumbered.net"
        _write_netlist(
            renumbered,
            [
                ("C2", "temper:Test", "a.cap1"),
                ("C1", "temper:Test", "b.cap2"),
            ],
        )
        rc = _write_stamp(board_path, renumbered, tmp_path)
        assert rc == 1
        assert read_stamp(board_path) is None

    def test_refuses_to_stamp_on_dropped_component(self, tmp_path: Path) -> None:
        """A design component with no board footprint at all (the
        4-missing-footprint half of the 2026-08-13 incident)."""
        board_path, _ = _matching_pair(tmp_path)
        missing = tmp_path / "missing.net"
        _write_netlist(
            missing,
            [
                ("C1", "temper:Test", "a.cap1"),
                ("C2", "temper:Test", "b.cap2"),
                ("C3", "temper:Test", "c.cap3"),
            ],
        )
        rc = _write_stamp(board_path, missing, tmp_path)
        assert rc == 1
        assert read_stamp(board_path) is None

    def test_writes_stamp_when_reconciled(self, tmp_path: Path) -> None:
        board_path, netlist_path = _matching_pair(tmp_path)
        rc = _write_stamp(board_path, netlist_path, tmp_path)
        assert rc == 0
        recorded = read_stamp(board_path)
        assert recorded is not None
        expected = compute_inputs_digest([board_path, netlist_path], tmp_path)
        assert recorded == expected

    def test_refuses_when_board_missing(self, tmp_path: Path) -> None:
        _, netlist_path = _matching_pair(tmp_path)
        rc = _write_stamp(tmp_path / "nope.kicad_pcb", netlist_path, tmp_path)
        assert rc == 1

    def test_refuses_when_netlist_missing(self, tmp_path: Path) -> None:
        board_path, _ = _matching_pair(tmp_path)
        rc = _write_stamp(board_path, tmp_path / "nope.net", tmp_path)
        assert rc == 1


class TestCheckBoardSyncStamp:
    def test_violation_when_no_stamp_present(self, tmp_path: Path) -> None:
        """The exact gap this mechanism exists to close: a board that has
        never been through the stamping tool carries no provenance at all,
        which must fail loud (VIOLATION), never be silently treated as
        fine."""
        board_path, netlist_path = _matching_pair(tmp_path)
        rc = stamp_gate.run(board_path, netlist_path, tmp_path, skip_freshness=True)
        assert rc == stamp_gate.EXIT_VIOLATION

    def test_passes_when_freshly_stamped(self, tmp_path: Path) -> None:
        board_path, netlist_path = _matching_pair(tmp_path)
        assert _write_stamp(board_path, netlist_path, tmp_path) == 0
        rc = stamp_gate.run(
            board_path, netlist_path, tmp_path, skip_freshness=True, repo_root=tmp_path
        )
        assert rc == stamp_gate.EXIT_OK

    def test_violation_when_netlist_changes_after_stamping(self, tmp_path: Path) -> None:
        """Construct the failure this mechanism is meant to catch: elec/src
        changes (recompiling the netlist) after the board was stamped, with
        no matching board resync+restamp -- exactly the mid-drift state of
        the 2026-08-13 incident, caught the moment the netlist moves rather
        than five days later."""
        board_path, netlist_path = _matching_pair(tmp_path)
        assert _write_stamp(board_path, netlist_path, tmp_path) == 0
        assert stamp_gate.run(
            board_path, netlist_path, tmp_path, skip_freshness=True, repo_root=tmp_path
        ) == (stamp_gate.EXIT_OK)

        # elec/src changed -- a component was renumbered in the schematic --
        # and the netlist was recompiled, but the board was never resynced
        # or restamped.
        _write_netlist(
            netlist_path,
            [
                ("C1", "temper:Test", "a.cap1"),
                ("C9", "temper:Test", "b.cap2"),  # C2 -> C9 renumber
            ],
        )
        rc = stamp_gate.run(
            board_path, netlist_path, tmp_path, skip_freshness=True, repo_root=tmp_path
        )
        assert rc == stamp_gate.EXIT_VIOLATION

    def test_violation_when_board_changes_after_stamping(self, tmp_path: Path) -> None:
        """The other half: the BOARD is hand-edited after stamping (e.g. a
        component moved/added/renumbered directly in the PCB editor)
        without the netlist changing at all. Because the stamp's digest
        covers the board's own bytes, not only the netlist's, this must
        also fail -- a stamp that only tracked the netlist would stay
        silently 'fresh' through exactly this edit."""
        board_path, netlist_path = _matching_pair(tmp_path)
        assert _write_stamp(board_path, netlist_path, tmp_path) == 0
        assert stamp_gate.run(
            board_path, netlist_path, tmp_path, skip_freshness=True, repo_root=tmp_path
        ) == (stamp_gate.EXIT_OK)

        # Board edited in place: C1 renumbered to C9 on the board only.
        _write_board(board_path, [("C9", "a.cap1"), ("C2", "b.cap2")])
        rc = stamp_gate.run(
            board_path, netlist_path, tmp_path, skip_freshness=True, repo_root=tmp_path
        )
        assert rc == stamp_gate.EXIT_VIOLATION

    def test_gate_error_when_board_missing(self, tmp_path: Path) -> None:
        _, netlist_path = _matching_pair(tmp_path)
        rc = stamp_gate.run(
            tmp_path / "nope.kicad_pcb",
            netlist_path,
            tmp_path,
            skip_freshness=True,
            repo_root=tmp_path,
        )
        assert rc == stamp_gate.EXIT_GATE_ERROR

    def test_gate_error_when_netlist_missing(self, tmp_path: Path) -> None:
        board_path, _ = _matching_pair(tmp_path)
        rc = stamp_gate.run(
            board_path,
            tmp_path / "nope.net",
            tmp_path,
            skip_freshness=True,
            repo_root=tmp_path,
        )
        assert rc == stamp_gate.EXIT_GATE_ERROR

    def test_gate_error_on_stale_netlist_relative_to_src(self, tmp_path: Path) -> None:
        """Both sides' freshness matters, not just their mutual agreement
        (see module docstring): a netlist that is itself stale relative to
        elec/src/**.ato must fail closed, never be trusted as a comparison
        baseline even if it happens to byte-match an old stamp."""
        import os

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.ato").write_text("module main\n")
        board_path, netlist_path = _matching_pair(tmp_path)
        assert _write_stamp(board_path, netlist_path, tmp_path) == 0

        past = time.time() - 3600
        os.utime(netlist_path, (past, past))
        # Bypass write_board_sync_stamp's own freshness gate above (already
        # stamped before backdating); check_board_sync_stamp must still
        # fail closed WITHOUT skip_freshness.
        rc = stamp_gate.run(board_path, netlist_path, src_dir, repo_root=tmp_path)
        assert rc == stamp_gate.EXIT_GATE_ERROR

    def test_real_repo_stamp_state(self) -> None:
        """Documents, rather than asserts a fixed verdict on, this
        mechanism's status against the real repo: `pcb/temper.kicad_pcb`
        has no stamp yet (this tool is new), so the gate is expected to
        report VIOLATION until `write_board_sync_stamp.py` is run for the
        first time (which itself requires the board and netlist to be
        reconciled -- see check_netlist_board_reconciliation.py's own
        documented finding count on current main)."""
        repo_root = Path(__file__).resolve().parents[2]
        board = repo_root / "pcb" / "temper.kicad_pcb"
        netlist = repo_root / "elec" / "build" / "default.net"
        src_dir = repo_root / "elec" / "src"
        if not board.is_file() or not netlist.is_file():
            pytest.skip("board or compiled netlist missing (run `make netlist`)")
        rc = stamp_gate.run(board, netlist, src_dir)
        # History: pre-#1447 this board had no stamp and the honest verdict
        # was VIOLATION/GATE_ERROR ("never silently 0 on a board that has
        # never been stamped"). #1447 wrote the first real stamp and #1460
        # made its digest environment-portable (netlist build-path
        # normalisation), so with a stamp present the honest assertion is
        # EXIT_OK; an un-stamped board must still fail closed.
        stamp = board.with_name(board.name + ".source-digest")
        if stamp.is_file():
            assert rc == stamp_gate.EXIT_OK, (
                f"board carries a stamp but the gate returned rc={rc} -- "
                "the stamp is stale or the digest normalisation regressed"
            )
        else:
            assert rc in (stamp_gate.EXIT_VIOLATION, stamp_gate.EXIT_GATE_ERROR)
