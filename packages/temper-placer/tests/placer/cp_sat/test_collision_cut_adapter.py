"""Proof-first tests for exact Rust collision-cut projection."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import temper_orchestration as rust
from ortools.sat.python import cp_model

from temper_placer.placer.cp_sat.collision_cut_adapter import (
    RUST_MODEL_UNITS_PER_MM,
    apply_collision_cut,
)
from temper_placer.placer.cp_sat.model import CpSatModel


def _rust_cut() -> object:
    prepared = rust.prepare_collision_campaign(
        "board", "rules", "solver", "axis-x", ["A", "B"], 4, 1_000
    )
    solving = prepared.start_solving()
    candidate = solving.complete_candidate(
        {"A": (1000, 2000, 1), "B": (3000, 4000, 2)}
    )
    decision = candidate.audit("passed", "passed", "trusted", [("B", "A", 0.5, "digest")])
    return decision.take_refining().cuts()[0]


def _model() -> CpSatModel:
    model = CpSatModel(units_per_mm=RUST_MODEL_UNITS_PER_MM)
    for ref in ("A", "B"):
        model.add_component(ref, 0, 0, 10, 10)
        model.add_rotation(ref, is_polarized=False)
    return model


def _pin(model: CpSatModel, values: tuple[int, int, int, int, int, int]) -> None:
    a, b = model.component_map["A"], model.component_map["B"]
    for variable, value in zip(
        (a.x_center, a.y_center, a.rot_ref, b.x_center, b.y_center, b.rot_ref),
        values,
        strict=True,
    ):
        model.model_ref.Add(variable == value)


def test_witnessed_six_value_tuple_is_infeasible() -> None:
    assert RUST_MODEL_UNITS_PER_MM == rust.collision_campaign_model_units_per_mm()
    model = _model()
    before = len(model.model_ref.Proto().constraints)
    apply_collision_cut(model, _rust_cut(), expected_candidate_digest="digest")
    assert len(model.model_ref.Proto().constraints) == before + 1
    _pin(model, (1000, 2000, 1, 3000, 4000, 2))
    assert cp_model.CpSolver().Solve(model.model_ref) == cp_model.INFEASIBLE


@pytest.mark.parametrize("values", [(1001, 2000, 1, 3000, 4000, 2), (1000, 2000, 0, 3000, 4000, 2)])
def test_single_pose_coordinate_or_rotation_neighbor_remains_feasible(
    values: tuple[int, int, int, int, int, int],
) -> None:
    model = _model()
    apply_collision_cut(model, _rust_cut())
    _pin(model, values)
    assert cp_model.CpSolver().Solve(model.model_ref) in (cp_model.OPTIMAL, cp_model.FEASIBLE)


def test_reversed_pair_projection_uses_one_canonical_key() -> None:
    model = _model()
    cut = _rust_cut()
    reversed_cut = SimpleNamespace(
        first=cut.second,
        second=cut.first,
        x_first=cut.x_second,
        y_first=cut.y_second,
        rotation_first=cut.rotation_second,
        x_second=cut.x_first,
        y_second=cut.y_first,
        rotation_second=cut.rotation_first,
        overlap_area_mm2=cut.overlap_area_mm2,
        candidate_digest=cut.candidate_digest,
    )
    apply_collision_cut(model, reversed_cut)
    with pytest.raises(ValueError, match="already applied"):
        apply_collision_cut(model, cut)
    assert len(model._collision_cut_keys) == 1


@pytest.mark.parametrize(
    "bad_cut",
    [
        SimpleNamespace(first="missing", second="B", x_first=1, y_first=2, rotation_first=0,
                        x_second=3, y_second=4, rotation_second=0, overlap_area_mm2=1.0,
                        candidate_digest="digest"),
        SimpleNamespace(first="A", second="B", x_first=1, y_first=2, rotation_first=0,
                        x_second=3, y_second=4, rotation_second=0, overlap_area_mm2=1.0,
                        candidate_digest="stale"),
        SimpleNamespace(first="A", second="B", x_first=1.0, y_first=2, rotation_first=0,
                        x_second=3, y_second=4, rotation_second=0, overlap_area_mm2=1.0,
                        candidate_digest="digest"),
    ],
)
def test_malformed_missing_or_stale_cut_fails_before_model_mutation(bad_cut: object) -> None:
    model = _model()
    before = len(model.model_ref.Proto().constraints)
    with pytest.raises(ValueError):
        apply_collision_cut(model, bad_cut, expected_candidate_digest="digest")
    assert len(model.model_ref.Proto().constraints) == before


def test_scale_mismatch_fails_before_model_mutation() -> None:
    model = CpSatModel(units_per_mm=100)
    for ref in ("A", "B"):
        model.add_component(ref, 0, 0, 10, 10)
        model.add_rotation(ref, is_polarized=False)
    before = len(model.model_ref.Proto().constraints)
    with pytest.raises(ValueError, match="scale"):
        apply_collision_cut(model, _rust_cut())
    assert len(model.model_ref.Proto().constraints) == before


def test_fixed_rotation_disagreement_fails_before_model_mutation() -> None:
    model = CpSatModel(units_per_mm=RUST_MODEL_UNITS_PER_MM)
    model.add_component("A", 0, 0, 10, 10)
    model.add_rotation("A", is_polarized=True)
    model.add_component("B", 0, 0, 10, 10)
    model.add_rotation("B", is_polarized=False)
    before = len(model.model_ref.Proto().constraints)
    with pytest.raises(ValueError, match="fixed component"):
        apply_collision_cut(model, _rust_cut())
    assert len(model.model_ref.Proto().constraints) == before


def test_foreign_variable_is_rejected_before_model_mutation() -> None:
    model = _model()
    foreign = CpSatModel(units_per_mm=RUST_MODEL_UNITS_PER_MM)
    foreign.add_component("A", 0, 0, 10, 10)
    foreign.add_rotation("A", is_polarized=False)
    model._components["A"].x_center = foreign.component_map["A"].x_center
    before = len(model.model_ref.Proto().constraints)
    with pytest.raises(ValueError, match="foreign"):
        apply_collision_cut(model, _rust_cut())
    assert len(model.model_ref.Proto().constraints) == before
