"""Property-based + metamorphic tests for the migrated zone-adjustment kernel.

Wave 4, Phase 5 (deterministic hubs slice). These properties exercise the
migrated ``temper_design_bundle_python.deterministic_hubs.zone_adjustments_kernel``
through the ``temper_placer.deterministic.feedback.zone_adjuster`` shim;
bit-identical parity against the pinned pre-migration Python is asserted
separately by ``test_zone_adjuster_rust_differential.py``.

Five hypothesis properties (R1c):

- P1. Output shape: every emitted adjustment has non-negative delta_width and
  delta_height, and at least one strictly positive.
- P2. Threshold gate: a zone with fewer violations than the threshold is never
  adjusted.
- P3. Max-size bound: no delta exceeds ``max_size - current`` in either axis.
- P4. Direction gating: a zone whose ``can_expand`` lacks "right"/"left" never
  gains width; lacking "up"/"down" never gains height.
- P5. Monotonicity: increasing the violation count never shrinks a zone's
  deltas.

Three metamorphic relations (R1d):

- MR1. Violation-order invariance: reordering the violation list preserves the
  adjustments (first-seen order is preserved, values unchanged).
- MR2. Unrelated-zone noop: violations in a zone not present in the config
  never affect the config-present zones' adjustments.
- MR3. Threshold shift: raising the threshold by N suppresses exactly the
  zones with count in [old_threshold, new_threshold).
"""

from __future__ import annotations

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from temper_placer.deterministic.feedback.violation_mapper import MappedViolation
from temper_placer.deterministic.feedback.zone_adjuster import ZoneAdjuster

_DIRS = ["right", "left", "up", "down"]


def _config(n_zones=3, base=10.0):
    cfg = {}
    for i in range(n_zones):
        cfg[f"Z{i}"] = {
            "bounds": [(0, 0), (base, base)],
            "max_size": (base * 2, base * 2),
            "can_expand": list(_DIRS),
        }
    return cfg


def _violations(count, zone, offset=0.0):
    return [
        MappedViolation(
            type="clearance",
            components=["Q2"],
            position=(10.0 + offset + i * 0.1, 10.0),
            zone=zone,
        )
        for i in range(count)
    ]


class TestProperties:
    @given(
        st.integers(0, 30),
        st.integers(1, 5),
        st.floats(0.1, 2.0, allow_nan=False, allow_infinity=False),
        st.lists(st.sampled_from(_DIRS), min_size=1, max_size=4, unique=True),
    )
    @settings(max_examples=100, deadline=None)
    def test_p1_output_shape(self, count, threshold, expansion, dirs):
        cfg = {"Z": {"bounds": [(0, 0), (10, 10)], "max_size": (20, 20), "can_expand": list(dirs)}}
        result = ZoneAdjuster(cfg, violation_threshold=threshold, expansion_per_violation=expansion).compute_adjustments(
            _violations(count, "Z")
        )
        if count >= threshold:
            adj = result.adjustments["Z"]
            assert adj.delta_width >= 0.0 and adj.delta_height >= 0.0
            assert adj.delta_width > 0.0 or adj.delta_height > 0.0
        else:
            assert result.adjustments == {}

    @given(st.integers(0, 40), st.integers(1, 10))
    @settings(max_examples=100, deadline=None)
    def test_p2_threshold_gate(self, count, threshold):
        # count drawn below threshold by construction — no filtering.
        count = min(count, threshold - 1)
        result = ZoneAdjuster(_config(), violation_threshold=threshold).compute_adjustments(
            _violations(count, "Z0")
        )
        assert "Z0" not in result.adjustments

    @given(st.integers(1, 60), st.floats(0.1, 3.0, allow_nan=False, allow_infinity=False))
    @settings(max_examples=100, deadline=None)
    def test_p3_max_size_bound(self, count, expansion):
        cfg = {"Z": {"bounds": [(0, 0), (10, 10)], "max_size": (12, 13), "can_expand": list(_DIRS)}}
        result = ZoneAdjuster(cfg, expansion_per_violation=expansion).compute_adjustments(
            _violations(count, "Z")
        )
        if "Z" in result.adjustments:
            adj = result.adjustments["Z"]
            assert adj.delta_width <= 2.0 + 1e-9
            assert adj.delta_height <= 3.0 + 1e-9

    @given(st.integers(1, 30), st.lists(st.sampled_from(_DIRS), min_size=1, max_size=4, unique=True))
    @settings(max_examples=100, deadline=None)
    def test_p4_direction_gating(self, count, dirs):
        cfg = {"Z": {"bounds": [(0, 0), (10, 10)], "max_size": (20, 20), "can_expand": list(dirs)}}
        result = ZoneAdjuster(cfg).compute_adjustments(_violations(count, "Z"))
        if "Z" in result.adjustments:
            adj = result.adjustments["Z"]
            has_w = "right" in dirs or "left" in dirs
            has_h = "up" in dirs or "down" in dirs
            assert (adj.delta_width > 0.0) == has_w
            assert (adj.delta_height > 0.0) == has_h

    @given(st.integers(1, 25), st.integers(1, 25), st.integers(1, 8))
    @settings(max_examples=60, deadline=None)
    def test_p5_monotonicity(self, count_a, count_b, threshold):
        assume(threshold <= min(count_a, count_b))
        cfg = _config(1)
        low = ZoneAdjuster(cfg, violation_threshold=threshold).compute_adjustments(
            _violations(count_a, "Z0")
        )
        high = ZoneAdjuster(cfg, violation_threshold=threshold).compute_adjustments(
            _violations(count_b, "Z0")
        )
        adj_low = low.adjustments.get("Z0")
        adj_high = high.adjustments.get("Z0")
        if count_a == count_b:
            assert (adj_high is None) == (adj_low is None)
            return
        if count_a > count_b:
            adj_low, adj_high = adj_high, adj_low
        assert adj_high is not None
        if adj_low is not None:
            assert adj_high.delta_width >= adj_low.delta_width
            assert adj_high.delta_height >= adj_low.delta_height


class TestMetamorphic:
    @given(st.integers(0, 20), st.integers(1, 8))
    @settings(max_examples=80, deadline=None)
    def test_mr1_violation_order_invariance(self, count, threshold):
        """Reordering the violation list preserves the per-zone counts and the
        resulting adjustment VALUES. (The first-seen insertion ORDER of the
        adjustments dict is NOT invariant under reversal — the oracle's own
        ``zone_counts`` dict preserves first-seen order — so order is compared
        only when both sides agree by construction.)"""
        cfg = _config(2)
        adjuster = ZoneAdjuster(cfg, violation_threshold=threshold)
        ordered = _violations(count, "Z0") + _violations(count // 2, "Z1")
        a = adjuster.compute_adjustments(ordered)
        b = adjuster.compute_adjustments(list(reversed(ordered)))
        assert set(a.adjustments.keys()) == set(b.adjustments.keys())
        for name in a.adjustments:
            assert (a.adjustments[name].delta_width, a.adjustments[name].delta_height) == (
                b.adjustments[name].delta_width,
                b.adjustments[name].delta_height,
            )

    @given(st.integers(1, 25))
    @settings(max_examples=60, deadline=None)
    def test_mr2_unrelated_zone_noop(self, count):
        cfg = _config(2)
        adjuster = ZoneAdjuster(cfg, violation_threshold=5)
        base = adjuster.compute_adjustments(_violations(count, "Z0"))
        with_noise = adjuster.compute_adjustments(_violations(count, "Z0") + _violations(50, "GHOST"))
        if "Z0" in base.adjustments:
            assert with_noise.adjustments["Z0"].delta_width == base.adjustments["Z0"].delta_width
            assert with_noise.adjustments["Z0"].delta_height == base.adjustments["Z0"].delta_height
        else:
            assert "Z0" not in with_noise.adjustments

    @given(st.integers(1, 20), st.integers(1, 8))
    @settings(max_examples=80, deadline=None)
    def test_mr3_threshold_shift(self, count, base_threshold):
        cfg = _config(1)
        low = ZoneAdjuster(cfg, violation_threshold=base_threshold).compute_adjustments(
            _violations(count, "Z0")
        )
        high = ZoneAdjuster(cfg, violation_threshold=base_threshold + 3).compute_adjustments(
            _violations(count, "Z0")
        )
        if count >= base_threshold + 3:
            assert "Z0" in low.adjustments and "Z0" in high.adjustments
        elif count < base_threshold:
            assert "Z0" not in low.adjustments and "Z0" not in high.adjustments
        else:
            # count in [base_threshold, base_threshold+3): low adjusts, high suppresses
            assert "Z0" in low.adjustments
            assert "Z0" not in high.adjustments
