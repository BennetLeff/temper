"""Contracts for the bounded real-board family campaign entrypoint."""

from __future__ import annotations

from types import SimpleNamespace

from temper_placer.placer.cp_sat.constraint_family_campaign import (
    ConstraintFamilyCampaignStatus,
    ConstraintFamilyProbe,
)
from temper_placer.placer.cp_sat.constraint_family_frontier import (
    ConstraintFamilySearchFrontier,
)
from temper_placer.placer.cp_sat.constraint_family_real_board import (
    run_real_board_constraint_family_campaign,
)
from temper_placer.placer.cp_sat.constraint_restoration_campaign import (
    RestorationLimits,
)


class _Netlist:
    components = (SimpleNamespace(ref="A"), SimpleNamespace(ref="B"))


class _Instance:
    components = (("A", 1.0, 1.0), ("B", 1.0, 1.0))
    initial_placements = {"A": (1.0, 1.0, 0), "B": (3.0, 1.0, 0)}


def _limits() -> RestorationLimits:
    return RestorationLimits(total_timeout_s=5.0, stage_timeout_s=2.0, memory_limit_mb=None)


def _parse(_path: object, **_kwargs: object) -> SimpleNamespace:
    return SimpleNamespace(board=SimpleNamespace(width=20.0, height=20.0), netlist=_Netlist())


def _prepare(_path: object, **_kwargs: object) -> _Instance:
    return _Instance()


def _warm_start(_instance: object, **_kwargs: object) -> SimpleNamespace:
    return SimpleNamespace(usable=True, hints={"A": (1.0, 1.0, 0), "B": (3.0, 1.0, 0)})


def test_real_board_campaign_persists_and_reuses_rich_frontier(tmp_path) -> None:
    board_path = tmp_path / "board.kicad_pcb"
    board_path.write_bytes(b"authoritative-board")
    frontier_path = tmp_path / "frontier.json"
    probes = (ConstraintFamilyProbe(("family",), "family"),)
    def solver(_netlist: object, _board: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            status="optimal",
            positions={"A": (1.0, 2.0), "B": (3.0, 4.0)},
            rotations={"A": 0, "B": 1},
        )

    common = {
        "pcb_path": board_path,
        "families": {"family": {"marker": "family"}},
        "probes": probes,
        "limits": _limits(),
        "parse": _parse,
        "prepare": _prepare,
        "warm_start": _warm_start,
        "frontier_path": frontier_path,
    }
    first = run_real_board_constraint_family_campaign(solver=solver, **common)
    assert first.status is ConstraintFamilyCampaignStatus.COMPLETE
    assert frontier_path.is_file()
    assert len(ConstraintFamilySearchFrontier.read(frontier_path).records) == 1

    def cache_miss(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("cached real-board probe was not reused")

    second = run_real_board_constraint_family_campaign(solver=cache_miss, **common)
    assert second.status is ConstraintFamilyCampaignStatus.COMPLETE
    assert second.probes[0].accepted


def test_real_board_entrypoint_fails_closed_without_verified_warm_start(tmp_path) -> None:
    board_path = tmp_path / "board.kicad_pcb"
    board_path.write_bytes(b"authoritative-board")

    def unavailable(_instance: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(usable=False, hints={}, message="stripped solve timed out")

    result = run_real_board_constraint_family_campaign(
        board_path,
        families={"family": {}},
        parse=_parse,
        prepare=_prepare,
        warm_start=unavailable,
        limits=_limits(),
    )
    assert result.status is ConstraintFamilyCampaignStatus.INVALID
    assert "timed out" in result.diagnostics[0]


def test_real_board_entrypoint_rejects_opaque_cache_projection_before_solving(tmp_path) -> None:
    board_path = tmp_path / "board.kicad_pcb"
    board_path.write_bytes(b"authoritative-board")
    result = run_real_board_constraint_family_campaign(
        board_path,
        families={"family": {"opaque": object()}},
        probes=(ConstraintFamilyProbe(("family",), "family"),),
        frontier_path=tmp_path / "frontier.json",
        parse=_parse,
        prepare=_prepare,
        warm_start=_warm_start,
        limits=_limits(),
        solver=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must fail before solve")),
    )
    assert result.status is ConstraintFamilyCampaignStatus.INVALID
    assert "frontier key" in result.diagnostics[0]
