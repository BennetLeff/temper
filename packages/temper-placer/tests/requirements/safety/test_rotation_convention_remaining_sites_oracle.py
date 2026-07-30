"""Oracle-verified regression guards for the *second* rotation-convention
sweep: 9 additional R(+theta)/R(-theta) sites found beyond PR #479's 12 and
``check_pad_orientation.py``'s pre-existing 13th (see
``scripts/check_no_raw_rotation_trig.py``'s module docstring, "Second
sweep" section, for the full classification of all 9).

Six of those nine were genuine bugs and were fixed to route through
``temper_placer.geometry.kicad_transform`` -- the same single sanctioned
implementation the original 12 use, not a 19th independently-typed copy:

  1. ``scripts/check_pad_orientation.py::_corners``
  2. ``router_v6/constraints_geometry.py::RotatedRect.corners``
  3. ``router_v6/constraints_geometry.py::point_to_rotated_rect_distance``
  4. ``router_v6/connectivity.py::_to_pad_coordinates``
  5. ``router_v6/escape_via_generator.py``'s dog-bone candidate rotation
  6. ``visualization/model.py::Rectangle.corners`` and
     ``visualization/board_renderer.py::get_pad_shapes``'s pad-corner path

The other three (``packages/temper-geometry/src/polygon.rs::rotate_polygon``,
``scripts/bench_rust_geometry.py``, ``scripts/internal_route.py``) were
investigated and are covered elsewhere: the first two have no KiCad
correspondence at all (see the lint's docstring) and the third is fixed but
currently unreachable for unrelated reasons (broken imports pre-dating this
work), so a live pipeline test would require fixing that unrelated
breakage first -- out of scope here, flagged in the lint's docstring.

Every site below carried the SAME shape of bug as the original 12 -- see
the module docstring of ``test_rotation_convention_oracle.py`` for the
"why the existing test suite missed this" background, most importantly:
90-degree multiples cannot discriminate R(+theta) from R(-theta), so every
test in this file exercises a NON-90-degree angle (typically 37 or 45
degrees) verified against real ``pcbnew`` -- KiCad's own placement engine,
not a reimplementation of its rotation formula.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from temper_placer.core.netlist import Component, Pin
from temper_placer.router_v6.connectivity import CopperPad, _to_pad_coordinates
from temper_placer.router_v6.constraints_geometry import (
    Point,
    RotatedRect,
    point_to_rotated_rect_distance,
)
from temper_placer.router_v6.dense_package_detection import DensePackage
from temper_placer.router_v6.escape_via_generator import generate_escape_vias
from temper_placer.router_v6.stage0_data import DesignRules, NetClassRules
from temper_placer.visualization.board_renderer import get_pad_shapes
from temper_placer.visualization.model import PadView, Rectangle
from temper_placer.visualization.model import Point as VizPoint

# Reused, not reimplemented -- same pcbnew-oracle plumbing
# `test_rotation_convention_oracle.py` already built and battle-tested.
from tests.requirements.safety.test_rotation_convention_oracle import (
    _ORACLE_TOLERANCE_MM,
    _pcbnew_oracle_batch,
    _pcbnew_python_or_skip,
)

_REPO_ROOT = Path(__file__).resolve().parents[5]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
assert _SCRIPTS_DIR.is_dir(), f"expected scripts/ at {_SCRIPTS_DIR}"

if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import check_pad_orientation as _check_pad_orientation  # noqa: E402

# Non-90-degree angle used throughout -- deliberately not a multiple of 90
# (see this module's docstring for why that matters).
_ANGLE_DEG = 37.0
_DX, _DY = 6.0, -2.5
_ORIGIN_X, _ORIGIN_Y = 12.0, -4.0


def _oracle_world_point(dx: float, dy: float, angle_deg: float) -> tuple[float, float]:
    """A local offset rotated by ``angle_deg`` about the origin, per real
    ``pcbnew`` (footprint placed at (0,0)). Skips loudly if no interpreter
    with pcbnew bindings is available."""
    interpreter = _pcbnew_python_or_skip()
    oracle = _pcbnew_oracle_batch(interpreter, [(dx, dy, angle_deg)])
    if oracle is None:
        pytest.skip(f"pcbnew oracle call failed for interpreter {interpreter}")
    return oracle[0]


# =============================================================================
# 1. check_pad_orientation.py::_corners
# =============================================================================


class TestCheckPadOrientationCornersAgainstPcbnewOracle:
    def test_corner_matches_pcbnew_at_non_90_degree_angle(self):
        """Was previously exempted from the raw-trig lint on the theory
        that a symmetric rectangle's corner SET is invariant to R(+theta)
        vs R(-theta) at the 90-degree-multiple angles every real pad on
        this board happens to use. True, but not the same claim as
        "correct at every angle" -- this gate runs on any board handed to
        it. One specific corner (the (+hw,+hh) local offset) must land
        exactly where pcbnew places a pad with that same local offset on a
        footprint rotated by the pad's own absolute angle.
        """
        hw, hh = 0.5, 0.3
        pad = _check_pad_orientation.Pad(
            number="1",
            shape="rect",
            net=None,
            layers=("F.Cu",),
            cx=_ORIGIN_X,
            cy=_ORIGIN_Y,
            width=2 * hw,
            height=2 * hh,
            angle_deg=_ANGLE_DEG,
        )
        corners = _check_pad_orientation._corners(pad)
        # local_pts order: (-hw,-hh), (hw,-hh), (hw,hh), (-hw,hh)
        ox, oy = _oracle_world_point(hw, hh, _ANGLE_DEG)
        expected = (_ORIGIN_X + ox, _ORIGIN_Y + oy)
        got = corners[2]  # (hw, hh)
        assert got[0] == pytest.approx(expected[0], abs=_ORACLE_TOLERANCE_MM)
        assert got[1] == pytest.approx(expected[1], abs=_ORACLE_TOLERANCE_MM)


# =============================================================================
# 2/3. router_v6/constraints_geometry.py
# =============================================================================


class TestRotatedRectCornersAgainstPcbnewOracle:
    def test_corner_matches_pcbnew_at_non_90_degree_angle(self):
        """``RotatedRect.rotation`` is populated from real board pad and
        component rotation (``deterministic/stages/setup.py``), so its
        corners must land where KiCad would actually place that
        rectangle's own corners.
        """
        w, h = 1.0, 0.6
        rect = RotatedRect(center=Point(_ORIGIN_X, _ORIGIN_Y), size=(w, h), rotation=_ANGLE_DEG)
        corners = rect.corners
        hw, hh = w / 2, h / 2
        ox, oy = _oracle_world_point(hw, hh, _ANGLE_DEG)
        expected = (_ORIGIN_X + ox, _ORIGIN_Y + oy)
        got = corners[2]  # (hw, hh) local point, per the TL/TR/BR/BL ordering
        assert got.x == pytest.approx(expected[0], abs=_ORACLE_TOLERANCE_MM)
        assert got.y == pytest.approx(expected[1], abs=_ORACLE_TOLERANCE_MM)


class TestPointToRotatedRectDistanceAgainstPcbnewOracle:
    def test_oracle_corner_is_exactly_on_the_rect_boundary(self):
        """The pre-fix bug inverted the *old, wrong* R(+theta) convention
        (negate the angle, reapply the same R(+theta) formula) instead of
        the real inverse of the corrected R(-theta) convention -- a
        forward/inverse confusion, not just a sign flip. Ground truth: a
        world point that pcbnew says IS one exact corner of a rotated rect
        must transform to local coordinates exactly (+hw, +hh) (up to
        pcbnew's own nm quantization), so the signed distance to the rect
        must be ~0 (on the boundary), not some other, wrongly-transformed
        value.
        """
        w, h = 1.0, 0.6
        hw, hh = w / 2, h / 2
        rect = RotatedRect(center=Point(_ORIGIN_X, _ORIGIN_Y), size=(w, h), rotation=_ANGLE_DEG)
        ox, oy = _oracle_world_point(hw, hh, _ANGLE_DEG)
        world_corner = Point(_ORIGIN_X + ox, _ORIGIN_Y + oy)
        dist = point_to_rotated_rect_distance(world_corner, rect)
        assert dist == pytest.approx(0.0, abs=1e-4)

    def test_oracle_corner_offset_outward_is_reliably_outside(self):
        """A point pushed further out along the same local radial
        direction from an oracle-verified corner must read as OUTSIDE
        (positive distance) -- if the transform's sign were flipped, this
        point would misclassify as inside or at the wrong distance
        entirely, since it would be evaluated in a mirrored local frame.
        """
        w, h = 1.0, 0.6
        hw, hh = w / 2, h / 2
        rect = RotatedRect(center=Point(_ORIGIN_X, _ORIGIN_Y), size=(w, h), rotation=_ANGLE_DEG)
        ox, oy = _oracle_world_point(hw * 1.5, hh * 1.5, _ANGLE_DEG)
        world_point = Point(_ORIGIN_X + ox, _ORIGIN_Y + oy)
        dist = point_to_rotated_rect_distance(world_point, rect)
        assert dist > 0.0


# =============================================================================
# 4. router_v6/connectivity.py::_to_pad_coordinates
# =============================================================================


class TestToPadCoordinatesAgainstPcbnewOracle:
    def test_oracle_world_point_recovers_original_local_offset(self):
        """Same forward/inverse confusion as
        ``point_to_rotated_rect_distance`` above, on ``CopperPad.rotation``.
        A world point that pcbnew places for a given local offset and pad
        rotation must map back, through ``_to_pad_coordinates``, to that
        exact local offset.
        """
        dx, dy = _DX, _DY
        pad = CopperPad(
            identity=object(),  # unused by _to_pad_coordinates
            center=Point(_ORIGIN_X, _ORIGIN_Y),
            shape="rect",
            size=(2.0, 2.0),
            rotation=_ANGLE_DEG,
        )
        ox, oy = _oracle_world_point(dx, dy, _ANGLE_DEG)
        world_point = Point(_ORIGIN_X + ox, _ORIGIN_Y + oy)
        local_x, local_y = _to_pad_coordinates(world_point, pad)
        assert local_x == pytest.approx(dx, abs=_ORACLE_TOLERANCE_MM)
        assert local_y == pytest.approx(dy, abs=_ORACLE_TOLERANCE_MM)


# =============================================================================
# 5. router_v6/escape_via_generator.py -- dog-bone candidate rotation
# =============================================================================


@pytest.fixture
def _design_rules():
    default_rules = NetClassRules(
        name="Default", clearance_mm=0.05, trace_width_mm=0.1, via_diameter_mm=0.2, via_drill_mm=0.1
    )
    return DesignRules(
        net_classes={"Default": default_rules},
        net_class_assignments={},
        default_clearance_mm=0.05,
        default_trace_width_mm=0.1,
        default_via_diameter_mm=0.2,
        default_via_drill_mm=0.1,
    )


class TestEscapeViaGeneratorDogBoneRotationAgainstPcbnewOracle:
    def test_dogbone_candidate_matches_pcbnew_at_non_90_degree_angle(self, _design_rules):
        """``Component.initial_rotation`` is typed as an int quadrant index
        (0-3), so a real board can never drive this call site past a
        90-degree multiple today -- masked, per
        ``check_no_raw_rotation_trig.py``'s "Second sweep" section, not
        live-wrong. This test forces a fractional index (0.5 -> 45 degrees,
        via this module's own ``angle = float(initial_rotation) * pi/2``
        formula) to exercise the fixed rotation at a genuinely
        discriminating angle, matching this task's brief: "add a test at a
        non-90 angle -- the whole class hid because every fixture used
        right angles."

        The single pin sits at local (0, 0) so its world position is the
        component's own position regardless of rotation-index-vs-radian
        interpretation quirks elsewhere in the pipeline (an unrelated,
        pre-existing wrinkle in how ``pin_world_position`` interprets a
        non-int ``initial_rotation`` -- irrelevant here because rotating
        (0, 0) is a no-op under any convention). That isolates the
        candidate-offset rotation this task fixed as the only
        rotation-dependent geometry under test.
        """
        pin = Pin(name="1", number="1", position=(0.0, 0.0), net="NET1", width=0.4, height=0.4)
        comp = Component(
            ref="U1",
            footprint="TEST",
            bounds=(2.0, 2.0),
            pins=[pin],
            initial_position=(_ORIGIN_X, _ORIGIN_Y),
            initial_rotation=0.5,  # forces the escape_via_generator angle to 45 deg
        )
        dense_pkg = DensePackage(
            component=comp, pin_count=1, pitch_mm=1.0, package_type="BGA", requires_escape=True
        )

        vias = generate_escape_vias(dense_pkg, _design_rules, strategy="dog-bone")
        assert len(vias) == 1
        via = vias[0]

        # First candidate tried is (+half_pitch, +half_pitch) = (0.5, 0.5);
        # nothing else is in the scene, so it is always the chosen one.
        ox, oy = _oracle_world_point(0.5, 0.5, 45.0)
        expected = (_ORIGIN_X + ox, _ORIGIN_Y + oy)
        assert via.position[0] == pytest.approx(expected[0], abs=_ORACLE_TOLERANCE_MM)
        assert via.position[1] == pytest.approx(expected[1], abs=_ORACLE_TOLERANCE_MM)


# =============================================================================
# 6. visualization/model.py::Rectangle.corners and
#    visualization/board_renderer.py::get_pad_shapes
# =============================================================================


class TestVisualizationRectangleCornersAgainstPcbnewOracle:
    def test_corner_matches_pcbnew_at_non_90_degree_angle(self):
        """Renders a visual proxy of the real board -- a wrongly-mirrored
        component outline at a non-quadrant angle would mislead anyone
        looking at the visualization, even though today's discrete
        placer-rotation state never produces one.
        """
        w, h = 1.0, 0.6
        rect = Rectangle(
            center=VizPoint(_ORIGIN_X, _ORIGIN_Y), width=w, height=h, rotation=_ANGLE_DEG
        )
        corners = rect.corners
        hw, hh = w / 2, h / 2
        ox, oy = _oracle_world_point(hw, hh, _ANGLE_DEG)
        expected = (_ORIGIN_X + ox, _ORIGIN_Y + oy)
        got = corners[2]  # (w/2, h/2) per corners_rel ordering
        assert got.x == pytest.approx(expected[0], abs=_ORACLE_TOLERANCE_MM)
        assert got.y == pytest.approx(expected[1], abs=_ORACLE_TOLERANCE_MM)


class TestBoardRendererPadShapeAgainstPcbnewOracle:
    def test_pad_rect_path_matches_pcbnew_at_non_90_degree_angle(self):
        """``get_pad_shapes`` draws an SVG path for a rotated rect pad.
        Extract the (hw, hh) corner from the emitted path string and check
        it against real pcbnew placement for the same local offset and
        pad rotation.
        """
        w, h = 1.0, 0.6
        hw, hh = w / 2, h / 2
        pad = PadView(
            position=VizPoint(_ORIGIN_X, _ORIGIN_Y),
            size=(w, h),
            shape="rect",
            rotation=_ANGLE_DEG,
        )
        shapes = get_pad_shapes((pad,))
        assert len(shapes) == 1
        path = shapes[0]["path"]
        # Path is "M x0,y0 L x1,y1 L x2,y2 L x3,y3 Z"; third point (index 2,
        # 0-based) is the (hw, hh) local corner per corners_rel ordering.
        points = [seg.split()[-1] for seg in path.replace("Z", "").split(" ") if "," in seg]
        gx, gy = (float(v) for v in points[2].split(","))
        ox, oy = _oracle_world_point(hw, hh, _ANGLE_DEG)
        expected = (_ORIGIN_X + ox, _ORIGIN_Y + oy)
        assert gx == pytest.approx(expected[0], abs=_ORACLE_TOLERANCE_MM)
        assert gy == pytest.approx(expected[1], abs=_ORACLE_TOLERANCE_MM)
