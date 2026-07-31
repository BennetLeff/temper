"""Regression tests for check_copper_net_consistency.py.

Motivating incident (docs/evidence/2026-07-30-copper-net-consistency-drift.md):
`elec/src/modules.ato` gained a third tank capacitor (`tank.c_tank3`, commit
3ae26dfe) that atopile sequentially inserted BEFORE `ct_sense.c_filter` and
everything after it in designator order, shifting every subsequent `C`
designator up by one (C27->C28, C28->C29, ... C38->C39). `pcb/temper.kicad_pcb`
was never resynced afterward, so the board's `C27` footprint is still
`ct_sense.c_filter` (an SELV current-sense filter cap) while the freshly
compiled netlist says pin `C27` belongs to `tank.c_tank3` (the HV resonant
tank). That is precisely a `pad-mismatch` violation, and it went undetected
because `check_copper_net_consistency.py` -- despite being registered
`disposition: ci-gate` in `scripts/manifest.yaml` since 2026-07-28 -- was
never actually wired into any GitHub Actions workflow step until this fix
(see `test_gate_is_wired_into_ci_workflow` below, which fails against the
pre-fix `.github/workflows/python-tests.yml`).

This file did not exist before that investigation: the gate's own detection
logic (parse_netlist/load_board/run_checks) had zero test coverage. Each test
below builds a minimal board+netlist pair via kiutils/hand-written
S-expressions and asserts `run_checks` fires the intended violation class --
in particular `test_pad_mismatch_detects_designator_drift`, which is a
scaled-down reproduction of the real C27 incident and fails against a
naive "ref only" or "ordinal only" implementation that does not compare the
board's actual per-pin net name against the netlist's declared one.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_copper_net_consistency import (  # noqa: E402
    EXIT_GATE_ERROR,
    GateError,
    check_netlist_freshness,
    load_board,
    parse_netlist,
    run,
    run_checks,
)
from kiutils.board import Board  # noqa: E402
from kiutils.footprint import Footprint, Pad  # noqa: E402
from kiutils.items.brditems import Segment  # noqa: E402
from kiutils.items.common import Net, Position  # noqa: E402
from kiutils.items.zones import Zone  # noqa: E402


def _write_netlist(path: Path, nets: dict[str, list[tuple[str, str]]]) -> None:
    """nets: {net_name: [(ref, pin), ...]}. Codes assigned 1..N in dict order."""
    blocks = []
    for i, (name, nodes) in enumerate(nets.items()):
        node_sexpr = "\n".join(f'      (node (ref "{ref}") (pin "{pin}"))' for ref, pin in nodes)
        blocks.append(f'    (net (code "{i + 1}") (name "{name}")\n{node_sexpr}\n    )')
    path.write_text(
        "(export (version \"E\")\n"
        "  (components)\n"
        "  (nets\n" + "\n".join(blocks) + "\n  )\n)\n"
    )


def _footprint(ref: str, tstamp: str, pads: list[tuple[str, str | None, int]]) -> Footprint:
    """pads: [(pad_number, net_name_or_None, net_ordinal), ...]."""
    fp = Footprint(entryName="C_0603_1608Metric", tstamp=tstamp, position=Position(0, 0))
    fp.properties = {"Reference": ref, "Value": "?"}
    fp.pads = [
        Pad(
            number=num,
            type="smd",
            net=Net(number=ordinal, name=name) if name is not None else None,
            tstamp=f"{tstamp}-pad{num}",
        )
        for num, name, ordinal in pads
    ]
    return fp


def test_pad_mismatch_detects_designator_drift(tmp_path: Path) -> None:
    """Minimal reproduction of the real C27 incident: board's 'C27' footprint
    is really the old ct_sense.c_filter (SELV, net 'I_SENSE'), but the
    compiled netlist declares pin C27-1 belongs to the HV tank net
    'SW_NODE'. This must be caught as a pad-mismatch -- it is the exact
    defect class this gate exists to catch."""
    netlist_path = tmp_path / "default.net"
    _write_netlist(netlist_path, {"SW_NODE": [("C27", "1")], "gnd": [("C27", "2")]})
    netlist = parse_netlist(netlist_path)

    board_path = tmp_path / "board.kicad_pcb"
    board = Board()
    board.version = "20230121"
    board.generator = "pytest"
    board.nets = [Net(number=1, name="I_SENSE"), Net(number=2, name="gnd")]
    board.footprints = [
        _footprint("C27", "fp-c27", [("1", "I_SENSE", 1), ("2", "gnd", 2)]),
    ]
    board.traceItems = [
        Segment(start=Position(0, 0), end=Position(1, 1), width=0.2, layer="F.Cu", net=1, tstamp="seg1"),
    ]
    board.to_file(str(board_path))
    board_data = load_board(board_path)

    report = run_checks(board_data, netlist)

    mismatches = [v for v in report.violations if v.check == "pad-mismatch"]
    assert len(mismatches) == 1, report.violations
    assert "C27 pad 1" in mismatches[0].detail
    assert "I_SENSE" in mismatches[0].detail
    assert "SW_NODE" in mismatches[0].detail
    # Pad 2 is correctly matched (board 'gnd' == netlist 'gnd'), so it must
    # NOT be reported -- otherwise this test could not distinguish "flags
    # every pad" from "flags only real mismatches".
    assert not any("pad 2" in v.detail for v in report.violations)


def test_matching_board_and_netlist_pass_clean(tmp_path: Path) -> None:
    netlist_path = tmp_path / "default.net"
    _write_netlist(netlist_path, {"I_SENSE": [("C28", "1")], "gnd": [("C28", "2")]})
    netlist = parse_netlist(netlist_path)

    board_path = tmp_path / "board.kicad_pcb"
    board = Board()
    board.version = "20230121"
    board.generator = "pytest"
    board.nets = [Net(number=1, name="I_SENSE"), Net(number=2, name="gnd")]
    board.footprints = [_footprint("C28", "fp-c28", [("1", "I_SENSE", 1), ("2", "gnd", 2)])]
    board.traceItems = [
        Segment(start=Position(0, 0), end=Position(1, 1), width=0.2, layer="F.Cu", net=1, tstamp="seg1"),
    ]
    board.to_file(str(board_path))
    board_data = load_board(board_path)

    report = run_checks(board_data, netlist)
    assert report.violations == []
    assert report.pads_checked == 2


def test_dangling_ordinal_detected(tmp_path: Path) -> None:
    netlist_path = tmp_path / "default.net"
    _write_netlist(netlist_path, {"gnd": [("R1", "1")]})
    netlist = parse_netlist(netlist_path)

    board_path = tmp_path / "board.kicad_pcb"
    board = Board()
    board.version = "20230121"
    board.generator = "pytest"
    board.nets = [Net(number=1, name="gnd")]
    board.footprints = [_footprint("R1", "fp-r1", [("1", "gnd", 1)])]
    # Ordinal 99 does not exist in board.nets at all.
    board.traceItems = [
        Segment(start=Position(0, 0), end=Position(1, 1), width=0.2, layer="F.Cu", net=99, tstamp="seg-dangling"),
    ]
    board.to_file(str(board_path))
    board_data = load_board(board_path)

    report = run_checks(board_data, netlist)
    dangling = [v for v in report.violations if v.check == "dangling-ordinal"]
    assert len(dangling) == 1
    assert "99" in dangling[0].detail


def test_orphaned_net_detected(tmp_path: Path) -> None:
    """Copper on a net whose ordinal resolves fine against the board's OWN
    net table, but that resolved name has no net of that name in the
    compiled netlist at all (e.g. a net deleted from the schematic while
    stale copper for it is still routed)."""
    netlist_path = tmp_path / "default.net"
    _write_netlist(netlist_path, {"gnd": [("R1", "1")]})
    netlist = parse_netlist(netlist_path)

    board_path = tmp_path / "board.kicad_pcb"
    board = Board()
    board.version = "20230121"
    board.generator = "pytest"
    board.nets = [Net(number=1, name="gnd"), Net(number=2, name="deleted_net")]
    board.footprints = [_footprint("R1", "fp-r1", [("1", "gnd", 1)])]
    board.traceItems = [
        Segment(start=Position(0, 0), end=Position(1, 1), width=0.2, layer="F.Cu", net=2, tstamp="seg-orphan"),
    ]
    board.to_file(str(board_path))
    board_data = load_board(board_path)

    report = run_checks(board_data, netlist)
    orphaned = [v for v in report.violations if v.check == "orphaned-net"]
    assert len(orphaned) == 1
    assert "deleted_net" in orphaned[0].detail


def test_zone_name_mismatch_detected(tmp_path: Path) -> None:
    netlist_path = tmp_path / "default.net"
    _write_netlist(netlist_path, {"gnd": [("R1", "1")]})
    netlist = parse_netlist(netlist_path)

    board_path = tmp_path / "board.kicad_pcb"
    board = Board()
    board.version = "20230121"
    board.generator = "pytest"
    board.nets = [Net(number=1, name="gnd")]
    board.footprints = [_footprint("R1", "fp-r1", [("1", "gnd", 1)])]
    board.zones = [
        Zone(net=1, netName="not_gnd", layers=["F.Cu"], tstamp="zone-bad"),
    ]
    board.to_file(str(board_path))
    board_data = load_board(board_path)

    report = run_checks(board_data, netlist)
    zone_mismatches = [v for v in report.violations if v.check == "zone-name-mismatch"]
    assert len(zone_mismatches) == 1
    assert "not_gnd" in zone_mismatches[0].detail


def test_no_net_copper_is_skipped_not_checked(tmp_path: Path) -> None:
    netlist_path = tmp_path / "default.net"
    _write_netlist(netlist_path, {"gnd": [("R1", "1")]})
    netlist = parse_netlist(netlist_path)

    board_path = tmp_path / "board.kicad_pcb"
    board = Board()
    board.version = "20230121"
    board.generator = "pytest"
    board.nets = [Net(number=1, name="gnd")]
    board.footprints = [_footprint("R1", "fp-r1", [("1", "gnd", 1)])]
    board.traceItems = [
        Segment(start=Position(0, 0), end=Position(1, 1), width=0.2, layer="F.Cu", net=0, tstamp="seg-unrouted"),
    ]
    board.to_file(str(board_path))
    board_data = load_board(board_path)

    report = run_checks(board_data, netlist)
    assert report.violations == []
    assert report.copper_checked == 0
    assert report.copper_skipped_no_net == 1


def test_pad_without_exact_netlist_match_is_skipped_not_flagged(tmp_path: Path) -> None:
    """A pad whose (ref, pad_number) has no exact match in the netlist (e.g.
    resync's positional-fallback candidates) must be SKIPPED, never silently
    treated as checked-and-passing nor flagged as a false mismatch."""
    netlist_path = tmp_path / "default.net"
    _write_netlist(netlist_path, {"gnd": [("R1", "1")]})
    netlist = parse_netlist(netlist_path)

    board_path = tmp_path / "board.kicad_pcb"
    board = Board()
    board.version = "20230121"
    board.generator = "pytest"
    board.nets = [Net(number=1, name="gnd"), Net(number=2, name="vcc")]
    board.footprints = [
        _footprint("R1", "fp-r1", [("1", "gnd", 1), ("A1", "vcc", 2)]),
    ]
    board.traceItems = [
        Segment(start=Position(0, 0), end=Position(1, 1), width=0.2, layer="F.Cu", net=1, tstamp="seg1"),
    ]
    board.to_file(str(board_path))
    board_data = load_board(board_path)

    report = run_checks(board_data, netlist)
    assert report.violations == []
    assert report.pads_checked == 1
    assert report.pads_skipped_no_exact_match == 1


def test_parse_netlist_rejects_empty_file(tmp_path: Path) -> None:
    netlist_path = tmp_path / "empty.net"
    netlist_path.write_text("")
    with pytest.raises(GateError, match="empty"):
        parse_netlist(netlist_path)


def test_parse_netlist_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(GateError, match="not found"):
        parse_netlist(tmp_path / "missing.net")


def test_load_board_rejects_zero_footprints(tmp_path: Path) -> None:
    board_path = tmp_path / "board.kicad_pcb"
    board = Board()
    board.version = "20230121"
    board.generator = "pytest"
    board.nets = [Net(number=1, name="gnd")]
    board.traceItems = [
        Segment(start=Position(0, 0), end=Position(1, 1), width=0.2, layer="F.Cu", net=1, tstamp="seg1"),
    ]
    board.footprints = []
    board.to_file(str(board_path))
    with pytest.raises(GateError, match="zero footprints"):
        load_board(board_path)


def test_gate_is_wired_into_ci_workflow() -> None:
    """Silent-skip-hole regression test (same class as commit db779c81,
    'gate CI on Rust DRC backend presence'): this gate existed and was
    registered `disposition: ci-gate` in scripts/manifest.yaml for two days
    (2026-07-28 -> 2026-07-30) before ever being invoked by any GitHub
    Actions workflow, so the real 10-violation C27-and-friends
    designator/net drift on pcb/temper.kicad_pcb sat on `main` undetected.
    Asserts the gate script is actually referenced in a `run:` step of the
    board-gates job in python-tests.yml -- fails against the workflow file
    as it existed before this fix (grep for the literal script name finds
    nothing outside scripts/manifest.yaml)."""
    repo_root = Path(__file__).resolve().parents[2]
    workflow_path = repo_root / ".github" / "workflows" / "python-tests.yml"
    assert workflow_path.is_file(), f"workflow file not found: {workflow_path}"
    text = workflow_path.read_text(encoding="utf-8")

    # Must appear in an actual `run:` invocation, not merely as a comment
    # mentioning the filename -- a comment-only match would make this test
    # pass without the gate ever really executing.
    run_lines = [
        line for line in text.splitlines()
        if "run:" in line or line.strip().startswith("uv run")
    ]
    invoked = any("check_copper_net_consistency.py" in line for line in run_lines)
    assert invoked, (
        "scripts/check_copper_net_consistency.py is not invoked from any "
        "`run:` step in .github/workflows/python-tests.yml -- the gate "
        "exists and has unit tests but CI never actually runs it, exactly "
        "the silent-skip hole this test guards against."
    )


def test_load_board_rejects_zero_copper(tmp_path: Path) -> None:
    board_path = tmp_path / "board.kicad_pcb"
    board = Board()
    board.version = "20230121"
    board.generator = "pytest"
    board.nets = [Net(number=1, name="gnd")]
    board.footprints = [_footprint("R1", "fp-r1", [("1", "gnd", 1)])]
    board.traceItems = []
    board.zones = []
    board.to_file(str(board_path))
    with pytest.raises(GateError, match="zero copper items"):
        load_board(board_path)


class TestNetlistFreshness:
    """Freshness contract: the netlist must be provably built from current
    sources, decided by CONTENT when `make netlist` left a build stamp and by
    the legacy mtime comparison when it did not. The stamped cases below are
    the regression that failed this gate on CI 2026-07-31: the netlist
    actions/cache restores `elec/build/` with its original mtimes while
    `git checkout` stamps every `.ato` source with the checkout time, so a
    byte-identical cached netlist always looked mtime-STALE. The same fix
    already landed in check_domain_partition.py (scripts/_lib/freshness.py);
    this gate must match it."""

    def test_fresh_netlist_passes(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.ato").write_text("# source\n")
        time.sleep(0.05)
        netlist_path = tmp_path / "default.net"
        _write_netlist(netlist_path, {"gnd": [("R1", "1")]})
        check_netlist_freshness(netlist_path, src_dir)  # must not raise

    def test_stale_netlist_fails_closed(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        netlist_path = tmp_path / "default.net"
        _write_netlist(netlist_path, {"gnd": [("R1", "1")]})
        time.sleep(0.05)
        (src_dir / "main.ato").write_text("# edited after the netlist was built\n")
        with pytest.raises(GateError, match="STALE"):
            check_netlist_freshness(netlist_path, src_dir)

    def test_missing_netlist_is_gate_error(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.ato").write_text("# source\n")
        with pytest.raises(GateError, match="not found"):
            check_netlist_freshness(tmp_path / "nope.net", src_dir)

    def test_stamped_netlist_survives_newer_sources(self, tmp_path: Path) -> None:
        """A restored cache: sources newer than the netlist, content unchanged.

        This is the case that failed this gate on 2026-07-31 (CI runs
        30645135140 and 30610662266, "netlist is STALE ... 8 source file(s)
        newer than the compiled netlist"). `git checkout` stamps every .ato
        with the checkout time while actions/cache restores the netlist with
        its original mtime, so a cached netlist is always mtime-older than
        sources it in fact matches. The build stamp proves content equality.
        """
        import os

        from _lib.freshness import write_stamp

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        source = src_dir / "main.ato"
        source.write_text("# source\n")
        netlist_path = tmp_path / "default.net"
        _write_netlist(netlist_path, {"gnd": [("R1", "1")]})
        write_stamp(netlist_path, [source], src_dir)

        future = time.time() + 10_000
        os.utime(source, (future, future))
        assert source.stat().st_mtime > netlist_path.stat().st_mtime

        check_netlist_freshness(netlist_path, src_dir)  # must not raise

    def test_stamped_netlist_still_fails_on_real_edit(self, tmp_path: Path) -> None:
        """Content hashing must not weaken the gate: an actual source change
        is still STALE even though the stamp exists."""
        from _lib.freshness import write_stamp

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        source = src_dir / "main.ato"
        source.write_text("# source\n")
        netlist_path = tmp_path / "default.net"
        _write_netlist(netlist_path, {"gnd": [("R1", "1")]})
        write_stamp(netlist_path, [source], src_dir)

        source.write_text("# genuinely edited after the build\n")
        with pytest.raises(GateError, match="STALE"):
            check_netlist_freshness(netlist_path, src_dir)

    def test_stamped_netlist_catches_backdated_edit(self, tmp_path: Path) -> None:
        """An edit back-dated older than the netlist passes the mtime check and
        must still be caught -- content hashing is strictly stronger here, not
        merely more cache-friendly."""
        import os

        from _lib.freshness import write_stamp

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        source = src_dir / "main.ato"
        source.write_text("# source\n")
        netlist_path = tmp_path / "default.net"
        _write_netlist(netlist_path, {"gnd": [("R1", "1")]})
        write_stamp(netlist_path, [source], src_dir)

        source.write_text("# edited, then back-dated\n")
        past = time.time() - 10_000
        os.utime(source, (past, past))
        assert source.stat().st_mtime < netlist_path.stat().st_mtime

        with pytest.raises(GateError, match="STALE"):
            check_netlist_freshness(netlist_path, src_dir)

    def test_run_end_to_end_fails_closed_on_stale_netlist(self, tmp_path: Path) -> None:
        """Same check exercised through run() (skip_freshness=False, the real
        CI default) end-to-end."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        netlist_path = tmp_path / "default.net"
        _write_netlist(netlist_path, {"gnd": [("R1", "1")]})
        time.sleep(0.05)
        (src_dir / "main.ato").write_text("# edited after the netlist was built\n")
        code = run(tmp_path / "board.kicad_pcb", netlist_path, src_dir, skip_freshness=False)
        assert code == EXIT_GATE_ERROR
