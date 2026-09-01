"""Focused contracts for the constraint-family probe cache."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from temper_placer.placer.cp_sat.constraint_family_frontier import (
    ConstraintFamilyProbeKey,
    ConstraintFamilyProbeRecord,
    ConstraintFamilySearchFrontier,
    accepted_placement_covers,
    constraint_family_probe_key,
)
from temper_placer.placer.cp_sat.constraint_restoration_campaign import (
    RestorationLimits,
    RestorationStageStatus,
)


def test_key_is_canonical_and_contains_family_option_digests() -> None:
    first = constraint_family_probe_key(
        ("body_collision", "fixed_copper"),
        production_options={"z": [2, 1], "a": True},
        family_options={"fixed_copper": {"digest_source": "manifest-v1"}},
        limits=RestorationLimits(total_timeout_s=10, stage_timeout_s=2, memory_limit_mb=None),
        board_hash="BOARD",
    )
    second = constraint_family_probe_key(
        ("fixed_copper", "body_collision"),
        production_options={"a": True, "z": [2, 1]},
        family_options={"fixed_copper": {"digest_source": "manifest-v1"}},
        limits={"stage_timeout_s": 2.0, "total_timeout_s": 10.0, "memory_limit_mb": None},
        board_hash="board",
    )
    assert first.canonical == second.canonical
    assert first.digest == second.digest
    assert first.family_set == ("body_collision", "fixed_copper")
    assert len(first.family_digest) == 64
    assert len(first.production_options_digest) == 64
    assert '"family_set":["body_collision","fixed_copper"]' in first.canonical
    assert '"board_hash":"board"' in first.canonical


def test_frontier_round_trip_is_canonical_and_preserves_every_solver_status(tmp_path) -> None:
    records = tuple(
        ConstraintFamilyProbeRecord(
            ConstraintFamilyProbeKey((status.value,), {"mode": "test"}, {"family": status.value}, {"stage_timeout_s": 1}),
            status,
            1.0,
            solver_status=status.value,
        )
        for status in RestorationStageStatus
    )
    frontier = ConstraintFamilySearchFrontier(records)
    path = tmp_path / "family-frontier.json"
    frontier.write(path)
    restored = ConstraintFamilySearchFrontier.read(path)
    assert {record.status for record in restored.records} == set(RestorationStageStatus)
    assert restored.to_json() == frontier.to_json()
    assert json.loads(path.read_text()) ["schema"] == "temper.constraint-family-feasibility-frontier"


def test_duplicate_key_keeps_latest_record() -> None:
    key = ConstraintFamilyProbeKey(("family",), {"mode": "x"}, {}, {})
    old = ConstraintFamilyProbeRecord(key, RestorationStageStatus.UNKNOWN, 1.0)
    new = ConstraintFamilyProbeRecord(key, RestorationStageStatus.INFEASIBLE, 2.0)
    frontier = ConstraintFamilySearchFrontier((old, new))
    assert len(frontier.records) == 1
    assert frontier.records[0].status is RestorationStageStatus.INFEASIBLE


def test_campaign_result_add_adapter_copies_plain_fields() -> None:
    key = ConstraintFamilyProbeKey(("family",), {"mode": "x"}, {}, {})
    result = SimpleNamespace(
        status=RestorationStageStatus.ACCEPTED,
        elapsed_s=1.25,
        solver_status="optimal",
        positions={"A": (1.0, 2.0)},
        rotations={"A": 0},
        verification_passed=True,
        violation_count=0,
        diagnostics=("accepted",),
    )
    frontier = ConstraintFamilySearchFrontier().add(key, result)
    cached = frontier.lookup(key, expected_refs=("A",))
    assert cached is not None
    assert cached.status is RestorationStageStatus.ACCEPTED
    assert cached.positions == {"A": (1.0, 2.0)}
    assert cached.diagnostics == ("accepted",)


def test_accepted_cache_lookup_requires_complete_placement() -> None:
    key = ConstraintFamilyProbeKey(("family",), {}, {}, {})
    incomplete = ConstraintFamilyProbeRecord(
        key,
        RestorationStageStatus.ACCEPTED,
        1.0,
        positions={"A": (1.0, 2.0)},
        rotations={"A": 0},
    )
    frontier = ConstraintFamilySearchFrontier((incomplete,))
    assert not accepted_placement_covers(incomplete, ("A", "B"))
    assert frontier.lookup(key, expected_refs=("A", "B")) is None
    assert frontier.lookup(key, expected_refs=("A",)) is incomplete


def test_nonaccepted_cache_entries_do_not_require_placement_coverage() -> None:
    key = ConstraintFamilyProbeKey(("family",), {}, {}, {})
    record = ConstraintFamilyProbeRecord(key, RestorationStageStatus.UNKNOWN, 1.0)
    assert not accepted_placement_covers(record, ("A", "B"))
    assert ConstraintFamilySearchFrontier((record,)).lookup(key, expected_refs=("A", "B")) is record


def test_cache_rejects_opaque_option_and_tampered_digest() -> None:
    with pytest.raises(TypeError):
        ConstraintFamilyProbeKey(("family",), {"constraint": object()}, {}, {})
    key = ConstraintFamilyProbeKey(("family",), {"mode": "x"}, {}, {})
    payload = key.to_dict()
    payload["family_digest"] = "0" * 64
    with pytest.raises(ValueError, match="family digest"):
        ConstraintFamilyProbeKey.from_dict(payload)
