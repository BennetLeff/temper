"""U4 fail-capable defense tests for the KEEPOUT encoding.

Added by the constraint-mutation-suite triage (plan 2026-08-02-006, R32):
the existing keepout test (``test_encoder.py::TestKeepout``) uses a mid-board
zone with a zero margin, so the interval's margin path is never exercised and
the solver parks the single component at the origin, far from the zone. These
scenarios place the keepout zone at the origin (so any interval misplacement
is observable) and anchor a component beside it (so a doubled interval is an
over-constraint).

They are the kill defenses behind the runner's keepout kill set:
- ``test_origin_zone_keepout``          -> kills the dropped ``AddNoOverlap2D``
  and halved-interval mutations,
- ``test_origin_zone_keepout_anchored`` -> kills the margin double-count
  mutation (the doubled interval covers the anchored component, making the
  model infeasible).

These are targeted fail-capable scenarios, not the exhaustive BMC suite of
plan 2026-08-02-005 (which is not landing in this changeset).
"""

from __future__ import annotations

from temper_placer.pcl.constraints import AnchoredConstraint, ConstraintTier, KeepoutConstraint
from temper_placer.placer.cp_sat.encoder import EncoderContext, encode_constraints
from temper_placer.placer.cp_sat.model import CpSatModel


def _no_overlap_zone(x1, x2, y1, y2) -> bool:
    """True when the bbox avoids the origin keepout [-100,300]x[-100,300]."""
    return not (x1 < 300 and x2 > -100 and y1 < 300 and y2 > -100)


def test_origin_zone_keepout() -> None:
    """A keepout zone covering the origin must push the component out of it.

    With the zone at the origin, the parked-at-origin search can no longer
    hide a dropped or misplaced keepout interval: any feasible placement
    must avoid the zone, and the unmutated encoder guarantees it.
    """
    model = CpSatModel(units_per_mm=100)
    model.add_component("A", 0, 0, 200, 200)
    model.add_rotation("A", is_polarized=True)
    model.set_bounds(0, 0, 2000, 2000)

    c = KeepoutConstraint(
        zone_name="ORIGIN_FLY",
        tier=ConstraintTier.HARD,
        margin_mm=1.0,
        because="No components allowed near origin keepout for safety isolation",
    )
    ctx = EncoderContext(
        board_w_mm=20.0,
        board_h_mm=20.0,
        board_x_max_units=2000,
        board_y_max_units=2000,
        zones={"ORIGIN_FLY": (0.0, 0.0, 2.0, 2.0)},
    )
    encode_constraints([c], model, ctx)
    sol = model.solve(time_limit_s=1.0)
    assert sol.feasible, "origin keepout with an unmutated encoder must be feasible"

    x, y = sol.positions["A"]
    sw, sh = sol.sizes["A"]
    x1, x2 = x - sw // 2, x + sw // 2
    y1, y2 = y - sh // 2, y + sh // 2
    assert _no_overlap_zone(x1, x2, y1, y2), (
        f"A at ({x1},{y1})-({x2},{y2}) overlaps the origin keepout"
    )


def test_origin_zone_keepout_anchored() -> None:
    """A component anchored beside the origin zone stays out of it.

    The anchor forces the component to (500,500)mm-relative center, i.e. a
    bbox [400,600]x[400,600] in units, directly beside the [−100,300] zone.
    The unmutated encoder's interval [−100,300] clears it; if the margin were
    double-counted the interval would cover the component and the model would
    be infeasible — the feasible-assertion below is that defense.
    """
    model = CpSatModel(units_per_mm=100)
    model.add_component("A", 0, 0, 200, 200)
    model.add_rotation("A", is_polarized=True)
    model.set_bounds(0, 0, 2000, 2000)

    anchor = AnchoredConstraint(
        component="A",
        tier=ConstraintTier.HARD,
        position=(5.0, 5.0),
        because="Keepout defense test anchors the component beside the zone",
    )
    c = KeepoutConstraint(
        zone_name="ORIGIN_FLY",
        tier=ConstraintTier.HARD,
        margin_mm=1.0,
        because="No components allowed near origin keepout for safety isolation",
    )
    ctx = EncoderContext(
        board_w_mm=20.0,
        board_h_mm=20.0,
        board_x_max_units=2000,
        board_y_max_units=2000,
        zones={"ORIGIN_FLY": (0.0, 0.0, 2.0, 2.0)},
    )
    encode_constraints([anchor, c], model, ctx)
    sol = model.solve(time_limit_s=1.0)
    assert sol.feasible, (
        "anchored component beside the origin keepout must be feasible; an "
        "infeasible solve means the keepout interval covers the anchored "
        "component (margin double-count)"
    )

    x, y = sol.positions["A"]
    sw, sh = sol.sizes["A"]
    x1, x2 = x - sw // 2, x + sw // 2
    y1, y2 = y - sh // 2, y + sh // 2
    assert _no_overlap_zone(x1, x2, y1, y2), (
        f"A at ({x1},{y1})-({x2},{y2}) overlaps the origin keepout"
    )
