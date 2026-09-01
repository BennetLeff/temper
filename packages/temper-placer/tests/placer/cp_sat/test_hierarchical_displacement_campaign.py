"""Focused contracts for the coarse shared-assumption displacement probe."""

from __future__ import annotations

from dataclasses import dataclass

from temper_placer.placer.cp_sat.constraint_restoration_campaign import (
    RestorationLimits,
    RestorationStageStatus,
)
from temper_placer.placer.cp_sat.hierarchical_displacement_campaign import (
    run_coarse_group_displacement_core_experiment,
)


@dataclass
class _Component:
    ref: str


@dataclass
class _Netlist:
    components: list[_Component]


@dataclass
class _WarmStart:
    hints: dict[str, tuple[float, float, int]]
    usable: bool = True


@dataclass
class _Solve:
    status: str
    unsat_core: object = ()
    positions: dict[str, tuple[float, float]] | None = None
    rotations: dict[str, int] | None = None


def _netlist(*refs: str) -> _Netlist:
    return _Netlist([_Component(ref) for ref in refs])


def _warm_start(*refs: str) -> _WarmStart:
    return _WarmStart({ref: (float(i), 10.0, 0) for i, ref in enumerate(refs)})


def _limits() -> RestorationLimits:
    return RestorationLimits(total_timeout_s=5.0, stage_timeout_s=2.0, memory_limit_mb=None)


def test_coarse_groups_share_payload_and_refine_only_implicated_group() -> None:
    def solver(_netlist: object, _board: object, **kwargs: object) -> _Solve:
        labels = kwargs["hard_displacement_assumption_labels"]
        assert isinstance(labels, dict)
        # The first core implicates g0.  Once g0 is split, implicate only its
        # deterministic second half; g1 must remain one coarse group.
        if set(labels.values()) == {"displacement_group_g0", "displacement_group_g1"}:
            return _Solve("infeasible", ["displacement_group_g0", {"name": "foreign_zone"}])
        assert set(labels.values()) == {
            "displacement_group_g0.a", "displacement_group_g0.b", "displacement_group_g1"
        }
        return _Solve("infeasible", ["displacement_group_g0.b"])

    result = run_coarse_group_displacement_core_experiment(
        _netlist("A", "B", "C", "D"),
        object(),
        _warm_start("A", "B", "C", "D"),
        {"g0": ("B", "A"), "g1": ("D", "C")},
        max_refinements=1,
        solver=solver,
        limits=_limits(),
    )

    assert result.status is RestorationStageStatus.INFEASIBLE
    assert len(result.rounds) == 2
    first, second = result.rounds
    assert first.implicated_groups == ("g0",)
    assert first.implicated_members == ("A", "B")
    assert first.foreign_core_labels == ("foreign_zone",)
    assert second.implicated_groups == ("g0.b",)
    assert second.implicated_members == ("B",)
    assert first.groups == {"g0": ("A", "B"), "g1": ("C", "D")}
    assert second.groups == {
        "g0.a": ("A",),
        "g0.b": ("B",),
        "g1": ("C", "D"),
    }


def test_unknown_status_fails_closed_without_partial_placement() -> None:
    def solver(_netlist: object, _board: object, **kwargs: object) -> _Solve:
        del kwargs
        return _Solve("unknown")

    result = run_coarse_group_displacement_core_experiment(
        _netlist("A"), object(), _warm_start("A"), {"all": ("A",)}, solver=solver, limits=_limits()
    )

    assert result.status is RestorationStageStatus.UNKNOWN
    assert result.placement == {}
    assert result.rounds[0].implicated_groups == ()


def test_malformed_core_fails_closed() -> None:
    def solver(_netlist: object, _board: object, **kwargs: object) -> _Solve:
        del kwargs
        return _Solve("infeasible", [None])

    result = run_coarse_group_displacement_core_experiment(
        _netlist("A"), object(), _warm_start("A"), {"all": ("A",)}, solver=solver, limits=_limits()
    )

    assert result.status is RestorationStageStatus.INVALID
    assert result.placement == {}
    assert "malformed UNSAT core" in result.diagnostics[0]


def test_groups_must_partition_authoritative_netlist() -> None:
    result = run_coarse_group_displacement_core_experiment(
        _netlist("A", "B"), object(), _warm_start("A", "B"), {"all": ("A",)}, limits=_limits()
    )

    assert result.status is RestorationStageStatus.INVALID
    assert "partition netlist components exactly" in result.diagnostics[0]
