"""Handlers must reject unresolved required inputs instead of dropping them."""

from __future__ import annotations

import pytest

from temper_placer.pcl.constraints import (
    AdjacentConstraint,
    AlignedConstraint,
    AnchoredConstraint,
    Axis,
    BoardSide,
    ConstraintTier,
    EdgeType,
    EnclosingConstraint,
    KeepoutConstraint,
    LoopAreaConstraint,
    OnSideConstraint,
    SeparatedConstraint,
)
from temper_placer.placer.cp_sat.encoder import EncoderContext
from temper_placer.placer.cp_sat.errors import UnresolvedConstraintRefsError
from temper_placer.placer.cp_sat.handlers.adjacent import encode_adjacent
from temper_placer.placer.cp_sat.handlers.aligned import encode_aligned
from temper_placer.placer.cp_sat.handlers.anchored import encode_anchored
from temper_placer.placer.cp_sat.handlers.enclosing import encode_enclosing
from temper_placer.placer.cp_sat.handlers.keepout import encode_keepout
from temper_placer.placer.cp_sat.handlers.loop_area import encode_loop_area
from temper_placer.placer.cp_sat.handlers.onside import encode_onside
from temper_placer.placer.cp_sat.handlers.separated import encode_separated
from temper_placer.placer.cp_sat.model import CpSatModel

_BECAUSE = "missing references must never silently weaken placement"


def _model() -> CpSatModel:
    model = CpSatModel(units_per_mm=100)
    model.add_component("U1", 0, 0, 200, 200)
    model.add_rotation("U1", is_polarized=True)
    return model


def _ctx(**kwargs: object) -> EncoderContext:
    return EncoderContext(
        board_w_mm=50.0,
        board_h_mm=50.0,
        board_x_max_units=5000,
        board_y_max_units=5000,
        **kwargs,
    )


@pytest.mark.parametrize(
    ("handler", "constraint", "context"),
    [
        (
            encode_adjacent,
            AdjacentConstraint("U1", "MISSING", 1.0, ConstraintTier.HARD, _BECAUSE, id="adj"),
            _ctx(),
        ),
        (
            encode_aligned,
            AlignedConstraint(["U1", "MISSING"], Axis.X, ConstraintTier.HARD, _BECAUSE, id="align"),
            _ctx(),
        ),
        (
            encode_anchored,
            AnchoredConstraint("MISSING", ConstraintTier.HARD, _BECAUSE, position=(1.0, 1.0), id="anchor"),
            _ctx(),
        ),
        (
            encode_enclosing,
            EnclosingConstraint("MISSING_ZONE", ["U1"], ConstraintTier.HARD, _BECAUSE, id="enc"),
            _ctx(),
        ),
        (
            encode_keepout,
            KeepoutConstraint("MISSING_ZONE", ConstraintTier.HARD, _BECAUSE, id="keepout"),
            _ctx(),
        ),
        (
            encode_loop_area,
            LoopAreaConstraint("MISSING_LOOP", 100.0, ConstraintTier.HARD, _BECAUSE, id="loop"),
            _ctx(),
        ),
        (
            encode_onside,
            OnSideConstraint(["MISSING"], BoardSide.LEFT, EdgeType.NEAR, ConstraintTier.HARD, _BECAUSE, id="side"),
            _ctx(),
        ),
        (
            encode_separated,
            SeparatedConstraint("U1", "MISSING", 1.0, ConstraintTier.HARD, _BECAUSE, id="sep"),
            _ctx(),
        ),
    ],
)
def test_handler_fails_closed_for_unresolved_required_input(handler, constraint, context) -> None:
    model = _model()

    with pytest.raises(UnresolvedConstraintRefsError, match=constraint.id):
        handler(constraint, model.component_map, model, context)


def test_loop_area_warn_policy_skips_unresolved_loop() -> None:
    """The solver's explicit warn downgrade must reach the loop handler.

    Production golden-board placement intentionally permits known extracted
    loop drift while it records the unresolved names.  The default remains
    fail-closed (covered by the parameterized test above); only an explicit
    ``warn`` context may turn this known no-op into a skipped constraint.
    """
    model = _model()
    context = _ctx(unresolved_ref_policy="warn")
    constraint = LoopAreaConstraint("MISSING_LOOP", 100.0, ConstraintTier.HARD, _BECAUSE, id="loop")

    assert encode_loop_area(constraint, model.component_map, model, context) == []


def test_encoder_warn_policy_skips_handler_unresolved_zone() -> None:
    """Warn applies to handler-time zone expansion, not only preflight."""
    model = _model()
    context = _ctx(
        zones={"MISSING_ZONE": (0.0, 0.0, 10.0, 10.0)},
        unresolved_ref_policy="warn",
    )
    constraint = SeparatedConstraint(
        "MISSING_ZONE", "U1", 1.0, ConstraintTier.HARD, _BECAUSE, id="sep-zone"
    )

    from temper_placer.placer.cp_sat.encoder import encode_constraints

    assert encode_constraints([constraint], model, context) == []


def test_separated_fails_closed_for_stale_zone_membership() -> None:
    model = _model()
    context = _ctx(
        zones={"GROUP": (0.0, 0.0, 10.0, 10.0)},
        zone_components={"GROUP": ["U1", "STALE"]},
    )
    constraint = SeparatedConstraint("GROUP", "U1", 1.0, ConstraintTier.HARD, _BECAUSE, id="zone-sep")

    with pytest.raises(UnresolvedConstraintRefsError, match="STALE"):
        encode_separated(constraint, model.component_map, model, context)


def test_separated_self_pair_remains_explicit_noop() -> None:
    """A zone/ref overlap is intentional: no component separates from itself."""
    model = _model()
    context = _ctx()
    constraint = SeparatedConstraint("U1", "U1", 1.0, ConstraintTier.HARD, _BECAUSE, id="self-sep")

    assert encode_separated(constraint, model.component_map, model, context) == []
