"""Tests for InputStage's board identity preflight wiring (plan
2026-07-15-001, unit U4).

Scoped narrowly to the identity-gate wiring itself, not InputStage's full
behavior (constraint/spec loading has heavy real-file dependencies out of
scope here). Uses the repo's real quarantined fixture
(pcb/benchmarks/temper_fixture_33.kicad_pcb) as input since it's a real,
already-valid board `parse_kicad_pcb` can parse -- a synthetic minimal
.kicad_pcb risks not satisfying that parser's expectations, which isn't what
this test is about.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from temper_placer.pipeline.stages.input_stage import InputStage
from temper_placer.pipeline.state import PipelineError

_FIXTURE_PCB = Path("pcb/benchmarks/temper_fixture_33.kicad_pcb")


def _write_netlist(path: Path, refs: list[str]) -> None:
    comps = "\n    ".join(f'(comp (ref "{r}") (value "?"))' for r in refs)
    path.write_text(f'(export (version "E") (components\n    {comps}\n) (nets))')


@pytest.mark.skipif(not _FIXTURE_PCB.exists(), reason="quarantined fixture not present")
def test_fixture_board_rejected_before_constraints_apply(tmp_path: Path):
    netlist_path = tmp_path / "default.net"
    _write_netlist(netlist_path, ["X"])  # role_violation fires regardless of overlap

    context = {"input_pcb": _FIXTURE_PCB, "netlist_path": netlist_path}
    state = SimpleNamespace()

    with pytest.raises(PipelineError, match="[Ii]dentity"):
        InputStage()(state, context)


def test_missing_netlist_skips_preflight_without_raising(tmp_path: Path):
    # Not every InputStage caller has this project's real netlist available
    # (other boards' tests, pre-`make netlist` runs) -- a missing netlist is
    # a soft skip here, unlike scripts/internal_route.py where it's a hard
    # configuration error (see that script's own wiring).
    context = {
        "input_pcb": _FIXTURE_PCB,
        "netlist_path": tmp_path / "does_not_exist.net",
    }
    state = SimpleNamespace()

    if not _FIXTURE_PCB.exists():
        pytest.skip("quarantined fixture not present")

    # Should proceed past the identity check (skipped) -- whatever happens
    # next (constraint/spec loading) is out of scope for this test; we only
    # assert it's not the identity gate that stops it.
    try:
        InputStage()(state, context)
    except PipelineError as e:
        assert "identity" not in str(e).lower()
