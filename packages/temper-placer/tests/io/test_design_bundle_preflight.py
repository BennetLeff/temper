"""Tests for the board/netlist identity preflight (plan 2026-07-15-001, U4).

These use synthetic .kicad_pcb and .net text fixtures written to a tmp_path,
not the repo's real board -- keeps the test suite independent of whether the
real production board exists at a given point in the pipeline's history.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from temper_placer.io.design_bundle_preflight import BoardIdentityError, preflight_identity

_PCB_TEMPLATE = """
(kicad_pcb (version 20211014) (generator kiutils)
  {footprints}
)
"""

_NETLIST_TEMPLATE = """
(export (version "E")
  (components
    {comps}
  )
  (nets)
)
"""


def _footprint(ref: str) -> str:
    return f'(footprint "Fuse:Fuse_Holder" (layer "F.Cu") (property "Reference" "{ref}"))'


def _write_pcb(path: Path, refs: list[str]) -> None:
    footprints = "\n  ".join(_footprint(r) for r in refs)
    path.write_text(_PCB_TEMPLATE.format(footprints=footprints))


def _write_netlist(path: Path, refs: list[str]) -> None:
    comps = "\n    ".join(f'(comp (ref "{r}") (value "?"))' for r in refs)
    path.write_text(_NETLIST_TEMPLATE.format(comps=comps))


def test_matching_board_passes(tmp_path: Path):
    refs = [f"U{i}" for i in range(1, 11)]
    pcb = tmp_path / "temper.kicad_pcb"
    netlist = tmp_path / "default.net"
    _write_pcb(pcb, refs)
    _write_netlist(netlist, refs)

    preflight_identity(pcb, netlist)  # must not raise


def test_fixture_path_rejected_regardless_of_overlap(tmp_path: Path):
    refs = [f"U{i}" for i in range(1, 11)]
    benchmarks_dir = tmp_path / "pcb" / "benchmarks"
    benchmarks_dir.mkdir(parents=True)
    pcb = benchmarks_dir / "temper_fixture_33.kicad_pcb"
    netlist = tmp_path / "default.net"
    _write_pcb(pcb, refs)
    _write_netlist(netlist, refs)  # full overlap, still must be rejected

    with pytest.raises(BoardIdentityError, match="fixture"):
        preflight_identity(pcb, netlist)


def test_partial_overlap_below_threshold_rejected(tmp_path: Path):
    pcb = tmp_path / "temper.kicad_pcb"
    netlist = tmp_path / "default.net"
    # 3 of 100 refs overlap -- well below the default 95% threshold. Mirrors
    # the exact 33-vs-100-ref bug this whole effort exists to catch.
    _write_pcb(pcb, ["U1", "U2", "U3"])
    _write_netlist(netlist, [f"U{i}" for i in range(1, 101)])

    with pytest.raises(BoardIdentityError):
        preflight_identity(pcb, netlist)


def test_bring_up_mode_permits_partial_overlap_explicitly(tmp_path: Path):
    pcb = tmp_path / "temper.kicad_pcb"
    netlist = tmp_path / "default.net"
    _write_pcb(pcb, ["U1", "U2"])
    _write_netlist(netlist, [f"U{i}" for i in range(1, 101)])

    preflight_identity(pcb, netlist, bring_up=True)  # must not raise


def test_bring_up_off_by_default_still_rejects_partial_overlap(tmp_path: Path):
    pcb = tmp_path / "temper.kicad_pcb"
    netlist = tmp_path / "default.net"
    _write_pcb(pcb, ["U1", "U2"])
    _write_netlist(netlist, [f"U{i}" for i in range(1, 101)])

    with pytest.raises(BoardIdentityError):
        preflight_identity(pcb, netlist)


def test_missing_pcb_file_raises_clear_error(tmp_path: Path):
    netlist = tmp_path / "default.net"
    _write_netlist(netlist, ["U1"])

    with pytest.raises(FileNotFoundError):
        preflight_identity(tmp_path / "does_not_exist.kicad_pcb", netlist)


def test_missing_netlist_file_raises_clear_error(tmp_path: Path):
    pcb = tmp_path / "temper.kicad_pcb"
    _write_pcb(pcb, ["U1"])

    with pytest.raises(FileNotFoundError):
        preflight_identity(pcb, tmp_path / "does_not_exist.net")
