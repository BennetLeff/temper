"""Model-level equivalence for the six Protocol-ported handlers (R19/R2 shape).

Pins the *constructed CP-SAT model*, not just the Python-side call
sequence, for `adjacent.py`, `aligned.py`, `anchored.py`, `enclosing.py`,
`loop_area.py`, `onside.py` — the six handlers ported behind
`handlers/_model_protocol.py`. Two encoders agreeing on Python-side calls
can still build different models, so this compares
`CpSatModel.model_ref.Proto()` variable/constraint counts and the solve
status against numbers captured from the pre-refactor tree (git commit
`dc9c5a86`, before `_model_protocol.py` existed and before the six
handlers' `TYPE_CHECKING` imports were repointed from the concrete
`cp_sat.model.{CpSatModel,ComponentVars}` to the Protocol types).

This is the R19 "pinned oracle" applied to a typing-only refactor: the
refactor is expected to be behaviourally a no-op (every handler file is
`from __future__ import annotations`, so type annotations are never
evaluated at runtime — the refactor cannot change any function's
bytecode, only what a type checker sees). The pinned numbers below are
the empirical proof of that claim, not an assumption of it: they were
captured by running this exact fixture set against the handlers *before*
the Protocol edit landed, and are asserted bit-for-bit (`==`, not
tolerance) against the *after* code.

`keepout.py` and `separated.py` are deliberately absent from this file —
see `_model_protocol.py`'s module docstring for why they were parked
rather than ported.
"""

from __future__ import annotations

from temper_placer.pcl.constraints import (
    AdjacentConstraint,
    AlignedConstraint,
    AnchoredConstraint,
    Axis,
    BoardSide,
    ConstraintTier,
    DistanceMetric,
    EdgeType,
    EnclosingConstraint,
    LoopAreaConstraint,
    OnSideConstraint,
)
from temper_placer.placer.cp_sat.encoder import EncoderContext
from temper_placer.placer.cp_sat.handlers.adjacent import encode_adjacent
from temper_placer.placer.cp_sat.handlers.aligned import encode_aligned
from temper_placer.placer.cp_sat.handlers.anchored import encode_anchored
from temper_placer.placer.cp_sat.handlers.enclosing import encode_enclosing
from temper_placer.placer.cp_sat.handlers.loop_area import encode_loop_area
from temper_placer.placer.cp_sat.handlers.onside import encode_onside
from temper_placer.placer.cp_sat.model import CpSatModel

_BECAUSE = "test fixture rationale, exceeds the 10 char minimum"


def _build_model(comps: list[str], units_per_mm: int = 100) -> CpSatModel:
    model = CpSatModel(units_per_mm=units_per_mm)
    for name in comps:
        model.add_component(name, 0, 0, 200, 100)
        model.add_rotation(name, is_polarized=True)
    return model


def _model_stats(model: CpSatModel, labels: list) -> dict:
    """Proto-level stats (deterministic — no solver search involved) plus a solve."""
    proto = model.model_ref.Proto()
    sol = model.solve(time_limit_s=5.0)
    return {
        "num_variables": len(proto.variables),
        "num_constraints": len(proto.constraints),
        "num_labels": len(labels),
        "solve_status": sol.status.name,
    }


# Pinned oracle: captured against git commit dc9c5a86 (pre-`_model_protocol.py`),
# i.e. the original `cp_sat.model.{CpSatModel,ComponentVars}`-typed handlers.
_ORACLE = {
    "adjacent": {
        "num_variables": 18,
        "num_constraints": 16,
        "num_labels": 1,
        "solve_status": "OPTIMAL",
    },
    "aligned": {
        "num_variables": 28,
        "num_constraints": 24,
        "num_labels": 3,
        "solve_status": "OPTIMAL",
    },
    "anchored_position": {
        "num_variables": 10,
        "num_constraints": 8,
        "num_labels": 1,
        "solve_status": "OPTIMAL",
    },
    "anchored_region": {
        "num_variables": 10,
        "num_constraints": 10,
        "num_labels": 1,
        "solve_status": "OPTIMAL",
    },
    "enclosing": {
        "num_variables": 19,
        "num_constraints": 20,
        "num_labels": 2,
        "solve_status": "OPTIMAL",
    },
    "loop_area": {
        "num_variables": 25,
        "num_constraints": 24,
        "num_labels": 1,
        "solve_status": "OPTIMAL",
    },
    "onside": {
        "num_variables": 19,
        "num_constraints": 14,
        "num_labels": 2,
        "solve_status": "OPTIMAL",
    },
}


class TestPortedHandlersModelEquivalence:
    def test_adjacent_matches_pinned_oracle(self) -> None:
        model = _build_model(["Q1", "Q2"])
        ctx = EncoderContext(
            board_w_mm=50.0, board_h_mm=50.0, board_x_max_units=5000, board_y_max_units=5000
        )
        c = AdjacentConstraint(
            a="Q1",
            b="Q2",
            max_distance_mm=10.0,
            tier=ConstraintTier.HARD,
            because=_BECAUSE,
            metric=DistanceMetric.EDGE_TO_EDGE,
        )
        labels = encode_adjacent(c, model.component_map, model, ctx)
        assert _model_stats(model, labels) == _ORACLE["adjacent"]

    def test_aligned_matches_pinned_oracle(self) -> None:
        model = _build_model(["C0", "C1", "C2"])
        ctx = EncoderContext(
            board_w_mm=50.0, board_h_mm=50.0, board_x_max_units=5000, board_y_max_units=5000
        )
        c = AlignedConstraint(
            components=["C0", "C1", "C2"],
            axis=Axis.X,
            tier=ConstraintTier.SOFT,
            because=_BECAUSE,
            tolerance_mm=0.5,
        )
        labels = encode_aligned(c, model.component_map, model, ctx)
        assert _model_stats(model, labels) == _ORACLE["aligned"]

    def test_anchored_position_matches_pinned_oracle(self) -> None:
        model = _build_model(["J1"])
        ctx = EncoderContext(
            board_w_mm=50.0, board_h_mm=50.0, board_x_max_units=5000, board_y_max_units=5000
        )
        c = AnchoredConstraint(
            component="J1", tier=ConstraintTier.HARD, because=_BECAUSE, position=(5.0, 5.0)
        )
        labels = encode_anchored(c, model.component_map, model, ctx)
        assert _model_stats(model, labels) == _ORACLE["anchored_position"]

    def test_anchored_region_matches_pinned_oracle(self) -> None:
        model = _build_model(["J1"])
        ctx = EncoderContext(
            board_w_mm=50.0, board_h_mm=50.0, board_x_max_units=5000, board_y_max_units=5000
        )
        c = AnchoredConstraint(
            component="J1",
            tier=ConstraintTier.HARD,
            because=_BECAUSE,
            region=(0.0, 0.0, 10.0, 10.0),
        )
        labels = encode_anchored(c, model.component_map, model, ctx)
        assert _model_stats(model, labels) == _ORACLE["anchored_region"]

    def test_enclosing_matches_pinned_oracle(self) -> None:
        model = _build_model(["Q1", "Q2"])
        ctx = EncoderContext(
            board_w_mm=50.0,
            board_h_mm=50.0,
            board_x_max_units=5000,
            board_y_max_units=5000,
            zones={"HV_ZONE": (0.0, 0.0, 30.0, 30.0)},
        )
        c = EnclosingConstraint(
            outer="HV_ZONE",
            inner=["Q1", "Q2"],
            tier=ConstraintTier.HARD,
            because=_BECAUSE,
            margin_mm=1.0,
        )
        labels = encode_enclosing(c, model.component_map, model, ctx)
        assert _model_stats(model, labels) == _ORACLE["enclosing"]

    def test_loop_area_matches_pinned_oracle(self) -> None:
        model = _build_model(["Q1", "Q2"])
        ctx = EncoderContext(
            board_w_mm=50.0,
            board_h_mm=50.0,
            board_x_max_units=5000,
            board_y_max_units=5000,
            loop_components={"commutation": ["Q1", "Q2"]},
        )
        c = LoopAreaConstraint(
            loop_name="commutation",
            max_area_mm2=500.0,
            tier=ConstraintTier.STRONG,
            because=_BECAUSE,
        )
        labels = encode_loop_area(c, model.component_map, model, ctx)
        assert _model_stats(model, labels) == _ORACLE["loop_area"]

    def test_onside_matches_pinned_oracle(self) -> None:
        model = _build_model(["J1", "J2"])
        ctx = EncoderContext(
            board_w_mm=50.0,
            board_h_mm=50.0,
            board_x_min_units=0,
            board_y_min_units=0,
            board_x_max_units=5000,
            board_y_max_units=5000,
        )
        c = OnSideConstraint(
            components=["J1", "J2"],
            side=BoardSide.LEFT,
            edge=EdgeType.NEAR,
            tier=ConstraintTier.HARD,
            because=_BECAUSE,
            max_distance_mm=5.0,
        )
        labels = encode_onside(c, model.component_map, model, ctx)
        assert _model_stats(model, labels) == _ORACLE["onside"]
