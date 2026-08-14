"""Tests for check_rotation_quadrant_arithmetic.py.

Proves the gate fires on the exact bug shapes found/fixed on 2026-08-13
(PR #1144's `_rot_idx / 90`, and the live `router_v6/_pipeline_verify.py`
bug this same change fixed), and does NOT fire on the many correct `* 90` /
`* pi / 2` / `rotation_quadrant_to_degrees(...)` call sites already in the
tree -- a gate that flags the correct usage would fail every PR, not just a
buggy one.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_rotation_quadrant_arithmetic as gate  # noqa: E402


def _violations(text: str, name: str = "snippet.py") -> list[gate.Violation]:
    return gate.scan_text(Path(name), text)


class TestCatchesTheRealBugShapes:
    def test_pr1144_shaped_python_division(self):
        """The exact PR #1144 shape: dividing the raw index by 90 assuming
        it is already degrees, silently zeroing every non-zero rotation."""
        src = "degrees = comp.initial_rotation_quadrant / 90\n"
        v = _violations(src)
        assert len(v) == 1
        assert v[0].rule == "division"

    def test_pr1144_shaped_division_with_float_divisor(self):
        v = _violations("x = comp.initial_rotation_quadrant / 90.0\n")
        assert any(vv.rule == "division" for vv in v)

    def test_getattr_wrapped_division(self):
        """The exact shape the pre-fix `_pipeline_verify.py` sibling bug
        would have had, had it divided instead of skipping the multiply."""
        src = 'rotation = float(getattr(comp, "initial_rotation_quadrant", 0) or 0) / 90\n'
        v = _violations(src)
        assert any(vv.rule == "division" for vv in v)

    def test_bare_getattr_with_no_multiply_is_not_flagged_by_this_gate(self):
        """The actual pre-fix `_pipeline_verify.py` bug (no `* 90` AT ALL,
        just passing the raw index straight through) has no arithmetic
        operator for this textual gate to key on -- it is indistinguishable
        from a correct pass-through of an already-resolved degree value
        without also tracking types/dataflow. This gate is deliberately a
        narrower, false-positive-averse net (rules 1-3 in the module
        docstring); it does not claim to catch every shape of this defect
        class, only the ones with a diagnostic operator adjacent to the
        field name. The `_pipeline_verify.py` bug itself is covered by its
        own regression test (test_pipeline_verify_rotation_regression.py),
        not by this gate.
        """
        src = 'rotation=float(getattr(comp, "initial_rotation_quadrant", 0) or 0),\n'
        assert _violations(src) == []

    def test_math_radians_without_x90(self):
        src = "angle = math.radians(comp.initial_rotation_quadrant)\n"
        v = _violations(src)
        assert any(vv.rule == "radians-without-x90" for vv in v)

    def test_np_radians_without_x90(self):
        src = "angle = np.radians(comp.initial_rotation_quadrant or 0)\n"
        v = _violations(src)
        assert any(vv.rule == "radians-without-x90" for vv in v)

    def test_rust_to_radians_direct(self):
        src = "let rad = comp.initial_rotation_quadrant.unwrap_or(0).to_radians();\n"
        v = _violations(src, "snippet.rs")
        assert any(vv.rule == "to_radians-without-x90" for vv in v)

    def test_rust_to_radians_direct_with_as_f64(self):
        src = "let rad = (initial_rotation_quadrant as f64).to_radians();\n"
        v = _violations(src, "snippet.rs")
        assert any(vv.rule == "to_radians-without-x90" for vv in v)


class TestDoesNotFlagCorrectUsage:
    def test_multiply_by_90_is_fine(self):
        src = "rotation = float(c.initial_rotation_quadrant * 90) if c.initial_rotation_quadrant is not None else 0.0\n"
        assert _violations(src) == []

    def test_multiply_by_pi_over_2_is_fine(self):
        src = "angle = float(comp.initial_rotation_quadrant) * math.pi / 2.0\n"
        assert _violations(src) == []

    def test_radians_of_the_multiplied_value_is_fine(self):
        src = (
            "rotation_deg = comp.initial_rotation_quadrant * 90.0 if comp.initial_rotation_quadrant is not None else 0.0\n"
            "math.radians(rotation_deg)\n"
        )
        assert _violations(src) == []

    def test_canonical_helper_call_is_fine(self):
        src = "rotation = rotation_quadrant_to_degrees(comp.initial_rotation_quadrant)\n"
        assert _violations(src) == []

    def test_modulo_normalization_is_fine(self):
        src = "idx = comp.initial_rotation_quadrant % 4\n"
        assert _violations(src) == []

    def test_getattr_with_multiply_is_fine(self):
        src = 'rotation=rotation_quadrant_to_degrees(getattr(comp, "initial_rotation_quadrant", 0)),\n'
        assert _violations(src) == []

    def test_prose_slash_separated_attribute_list_is_not_division(self):
        """Real docstrings in this tree use `/` as a separator between
        attribute names, e.g. ``initial_position / initial_rotation_quadrant
        / initial_side`` meaning "these three", not division. The divisor
        must be a digit for rule 1 to fire."""
        src = '"""Component with None initial_position / initial_rotation_quadrant / initial_side."""\n'
        assert _violations(src) == []

    def test_slash_slash_comment_is_not_division(self):
        src = "// initial_rotation_quadrant // still not division syntax\n"
        assert _violations(src) == []

    def test_rust_index_method_is_fine(self):
        src = "let idx = RotationQuadrant::from_raw(comp.initial_rotation_quadrant.unwrap_or(0)).index();\n"
        assert _violations(src) == []

    def test_rust_to_degrees_direct_is_fine(self):
        """`.to_degrees()` is never mentioned by any rule -- only
        `.to_radians()` (rule 3) treats the raw index as if it were already
        an angle; nothing converts FROM the index TO degrees incorrectly by
        construction, since the index IS the thing being multiplied by 90 to
        produce degrees in the first place."""
        src = "let deg = (comp.initial_rotation_quadrant.unwrap_or(0) as f64 * 90.0);\n"
        assert _violations(src) == []


class TestRealRepoIsClean:
    def test_the_current_tree_has_zero_violations(self):
        """Anti-vacuity: proves the gate actually runs against the real
        tree and finds nothing, rather than passing only because a fixture
        was constructed to make it pass. If this starts failing, either a
        real regression landed or a legitimate new pattern needs a rule
        update -- not a silent allowlist."""
        violations = gate.scan()
        assert violations == [], "\n".join(str(v) for v in violations)
