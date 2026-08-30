"""Contracts for resumable displacement-deletion search frontiers."""

from __future__ import annotations

from dataclasses import dataclass

from temper_placer.placer.cp_sat.constraint_restoration_campaign import (
    RestorationLimits,
    RestorationStageStatus,
)
from temper_placer.placer.cp_sat.displacement_deletion_campaign import (
    DisplacementDeletionCampaignStatus,
    run_displacement_deletion_campaign,
)
from temper_placer.placer.cp_sat.displacement_deletion_frontier import (
    DeletionProbeKey,
    DeletionProbeRecord,
    DeletionSearchFrontier,
    available_board_hash,
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


def _netlist(*refs: str) -> _Netlist:
    return _Netlist([_Component(ref) for ref in refs])


def _warm_start(*refs: str) -> _WarmStart:
    return _WarmStart({ref: (float(index), 10.0, 0) for index, ref in enumerate(refs)})


def _limits() -> RestorationLimits:
    return RestorationLimits(total_timeout_s=10.0, stage_timeout_s=2.0, memory_limit_mb=None)


def test_key_is_canonical_and_includes_probe_identity() -> None:
    first = DeletionProbeKey(("B", "A"), 2, 40, {"z": [2, 1], "a": True}, "BOARD")
    second = DeletionProbeKey(("A", "B"), 2.0, 40.0, {"a": True, "z": [2, 1]}, "board")
    assert first.canonical == second.canonical
    assert first.digest == second.digest
    assert '"released_refs":["A","B"]' in first.canonical
    assert '"base_radius_mm":2.0' in first.canonical
    assert '"release_radius_mm":40.0' in first.canonical
    assert '"production_options"' in first.canonical
    assert '"board_hash":"board"' in first.canonical


def test_frontier_round_trip_is_canonical_and_deduplicates_keys(tmp_path) -> None:
    key = DeletionProbeKey(("A",), 2, 40, {"family": "ordinary"})
    older = DeletionProbeRecord(key, RestorationStageStatus.UNKNOWN, 1.0)
    newer = DeletionProbeRecord(key, RestorationStageStatus.INFEASIBLE, 2.0)
    frontier = DeletionSearchFrontier((older, newer))
    path = tmp_path / "frontier.json"
    frontier.write(path)
    restored = DeletionSearchFrontier.read(path)
    assert len(restored.records) == 1
    assert restored.records[0].status is RestorationStageStatus.INFEASIBLE
    assert restored.to_json() == frontier.to_json()


def test_unknown_cache_hit_never_qualifies_for_half_search(tmp_path) -> None:
    path = tmp_path / "frontier.json"
    calls = 0

    def solver(_netlist: object, _board: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        radii = kwargs["hard_displacement_radii_mm"]
        if all(value == 2.0 for value in radii.values()):
            return type("Solve", (), {"status": "infeasible"})()
        if radii["A"] == 40.0:
            return type("Solve", (), {"status": "unknown"})()
        return type("Solve", (), {"status": "infeasible"})()

    first = run_displacement_deletion_campaign(
        _netlist("A", "B", "C", "D"),
        object(),
        _warm_start("A", "B", "C", "D"),
        {"g0": ("A",), "g1": ("B",), "g2": ("C",), "g3": ("D",)},
        solver=solver,
        production_options={"family": "ordinary"},
        frontier_path=path,
        limits=_limits(),
    )
    first_calls = calls
    assert first.status is DisplacementDeletionCampaignStatus.COMPLETE
    assert first.singleton_tests[0].status is RestorationStageStatus.UNKNOWN
    assert first.balanced_half_tests == ()

    def should_not_run(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("resumed campaign should use cached probes")

    second = run_displacement_deletion_campaign(
        _netlist("A", "B", "C", "D"),
        object(),
        _warm_start("A", "B", "C", "D"),
        {"g0": ("A",), "g1": ("B",), "g2": ("C",), "g3": ("D",)},
        solver=should_not_run,
        production_options={"family": "ordinary"},
        frontier_path=path,
        limits=_limits(),
    )
    assert calls == first_calls
    assert second.singleton_tests[0].status is RestorationStageStatus.UNKNOWN
    assert second.balanced_half_tests == ()


def test_cache_key_mismatch_does_not_reuse_record(tmp_path) -> None:
    path = tmp_path / "frontier.json"
    key = DeletionProbeKey(("A",), 2, 40, {"family": "old"})
    DeletionSearchFrontier((DeletionProbeRecord(key, RestorationStageStatus.INFEASIBLE, 1.0),)).write(path)
    def solver(_netlist: object, _board: object, **kwargs: object) -> object:
        return type("Solve", (), {"status": "infeasible"})()

    result = run_displacement_deletion_campaign(
        _netlist("A"),
        object(),
        _warm_start("A"),
        {"all": ("A",)},
        solver=solver,
        production_options={"family": "new"},
        frontier_path=path,
        limits=_limits(),
        test_balanced_halves=False,
    )
    assert result.status is DisplacementDeletionCampaignStatus.COMPLETE
    assert all("reused cached" not in diagnostic for report in result.all_tests for diagnostic in report.diagnostics)
    assert len(DeletionSearchFrontier.read(path).records) == 3  # old record plus baseline and singleton


def test_board_hash_reads_metadata_only() -> None:
    board = type("Board", (), {"board_sha256": "ABC123"})()
    assert available_board_hash(board) == "abc123"
    assert available_board_hash(object()) is None


def test_opaque_production_options_fail_closed_when_caching() -> None:
    def solver(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("opaque key must fail before solver invocation")

    result = run_displacement_deletion_campaign(
        _netlist("A"),
        object(),
        _warm_start("A"),
        {"all": ("A",)},
        solver=solver,
        production_kwargs={"constraint": object()},
        frontier=DeletionSearchFrontier(),
        limits=_limits(),
    )
    assert result.status is DisplacementDeletionCampaignStatus.INVALID
    assert result.baseline is not None
    assert result.baseline.status is RestorationStageStatus.INVALID
    assert "cache key" in result.baseline.diagnostics[0]
