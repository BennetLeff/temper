"""U4 fail-capable defense test for the LOOP_AREA encoding.

Added by the constraint-mutation-suite triage (plan 2026-08-02-006, R32):
the existing loop-area test (``test_encoder.py::TestLoopArea``) solves with
no objective, so the solver parks all four components at the origin and any
AABB ceiling is trivially satisfied — the encoding's AABB machinery is never
exercised. This scenario anchors two loop components at opposite corners so
the AABB is genuinely large and the ceiling is binding.

It is the kill defense behind the runner's ``loop_sign_flip_ceiling`` kill:
with the ceiling flipped to a floor (area >= max_area_units), the anchored
AABB (~1764 mm^2 = 17.6M units^2) is forced to exceed a 5000 mm^2 ceiling
(50M units^2) that no 5000x5000-unit board AABB (max 25M units^2) can reach,
so the model becomes infeasible.

This is a targeted fail-capable scenario, not the exhaustive BMC suite of
plan 2026-08-02-005 (which is not landing in this changeset).
"""

from __future__ import annotations

from temper_placer.pcl.constraints import AnchoredConstraint, ConstraintTier, LoopAreaConstraint
from temper_placer.placer.cp_sat.encoder import EncoderContext, encode_constraints
from temper_placer.placer.cp_sat.model import CpSatModel

REFS = ["C_BUS", "Q1", "Q2", "C_OUT"]


def test_anchored_spread_ceiling() -> None:
    """A genuinely large loop AABB must still respect the area ceiling.

    C_BUS is anchored at (5,5)mm and Q1 at (45,45)mm on a 50x50mm board, so
    the loop AABB is ~1764 mm^2 — well under the 5000 mm^2 ceiling but large
    enough that the ceiling is binding. The unmutated encoder must satisfy it.
    """
    model = CpSatModel(units_per_mm=100)
    for ref in REFS:
        model.add_component(ref, 0, 0, 200, 200)
        model.add_rotation(ref, is_polarized=True)
    model.set_bounds(0, 0, 5000, 5000)

    anchor1 = AnchoredConstraint(
        component="C_BUS",
        tier=ConstraintTier.HARD,
        position=(5.0, 5.0),
        because="Loop defense test anchors the loop AABB",
    )
    anchor2 = AnchoredConstraint(
        component="Q1",
        tier=ConstraintTier.HARD,
        position=(45.0, 45.0),
        because="Loop defense test anchors the loop AABB",
    )
    c = LoopAreaConstraint(
        loop_name="commutation",
        max_area_mm2=5000.0,
        tier=ConstraintTier.HARD,
        because="Minimize commutation loop to reduce voltage overshoot and EMI emission",
    )
    ctx = EncoderContext(
        board_w_mm=50.0,
        board_h_mm=50.0,
        board_x_max_units=5000,
        board_y_max_units=5000,
        loop_components={"commutation": REFS},
    )
    encode_constraints([anchor1, anchor2, c], model, ctx)
    sol = model.solve(time_limit_s=2.0)
    assert sol.feasible, (
        "anchored-spread loop with a 5000mm^2 ceiling must be feasible; an "
        "infeasible solve means the area ceiling was flipped to a floor"
    )

    xs = [sol.positions[r][0] - sol.sizes[r][0] // 2 for r in REFS]
    ys = [sol.positions[r][1] - sol.sizes[r][1] // 2 for r in REFS]
    xe = [sol.positions[r][0] + sol.sizes[r][0] // 2 for r in REFS]
    ye = [sol.positions[r][1] + sol.sizes[r][1] // 2 for r in REFS]
    aabb_w = (max(xe) - min(xs)) / 100.0
    aabb_h = (max(ye) - min(ys)) / 100.0
    aabb_area = aabb_w * aabb_h
    assert aabb_area <= 5000.0, f"Loop area {aabb_area:.1f} mm^2 > 5000"
