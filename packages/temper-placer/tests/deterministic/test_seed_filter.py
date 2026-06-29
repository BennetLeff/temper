"""Tests for the pure filter_seed function.

@req(2026-06-23-004, R1)
@req(2026-06-23-004, K1)
@req(2026-06-23-004, K2)
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.deterministic.bottleneck_map import BottleneckMap
from temper_placer.deterministic.seed_filter import filter_seed


def _low_map() -> BottleneckMap:
    return BottleneckMap(
        cell_size_mm=1.0,
        width=2,
        height=2,
        origin_xy=(0.0, 0.0),
        scores=(0.1, 0.1, 0.1, 0.1),
    )


def _map_with_high_cell() -> BottleneckMap:
    """A 2x2 map with one high-congestion cell at (col=1, row=0)."""
    return BottleneckMap(
        cell_size_mm=1.0,
        width=2,
        height=2,
        origin_xy=(0.0, 0.0),
        scores=(0.1, 0.8, 0.1, 0.1),
    )


class TestAcceptance:
    def test_accepts_all_low_congestion(self) -> None:
        seed = {"R1": (0.5, 0.5), "R2": (1.5, 0.5)}
        assert filter_seed(seed, _low_map(), 0.7, 0.5, frozenset()) is True

    def test_rejects_one_high_congestion_lv(self) -> None:
        seed = {"R1": (0.5, 0.5), "R2": (1.5, 0.5)}  # R2 in 0.8 cell
        assert filter_seed(seed, _map_with_high_cell(), 0.7, 0.5, frozenset()) is False

    def test_hv_triggers_lower_threshold(self) -> None:
        # 0.6 cell; HV threshold is 0.5, so 0.6 >= 0.5 rejects.
        m = BottleneckMap(
            cell_size_mm=1.0,
            width=2,
            height=2,
            origin_xy=(0.0, 0.0),
            scores=(0.6, 0.1, 0.1, 0.1),
        )
        seed = {"U_HV": (0.5, 0.5)}
        assert filter_seed(seed, m, 0.7, 0.5, frozenset({"U_HV"})) is False

    def test_lv_tolerates_hv_threshold(self) -> None:
        # 0.6 cell; LV threshold is 0.7, so 0.6 < 0.7 accepts.
        m = BottleneckMap(
            cell_size_mm=1.0,
            width=2,
            height=2,
            origin_xy=(0.0, 0.0),
            scores=(0.6, 0.1, 0.1, 0.1),
        )
        seed = {"R_LV": (0.5, 0.5)}
        assert filter_seed(seed, m, 0.7, 0.5, frozenset()) is True

    def test_empty_seed_is_accepted(self) -> None:
        # An empty seed trivially satisfies the filter (vacuously true).
        assert filter_seed({}, _low_map(), 0.7, 0.5, frozenset()) is True

    def test_out_of_bounds_clamped_to_zero(self) -> None:
        # OOB coordinates clamp to 0.0; under any threshold, accepted.
        seed = {"R1": (999.0, 999.0), "R2": (-50.0, -50.0)}
        assert filter_seed(seed, _low_map(), 0.7, 0.5, frozenset()) is True

    def test_threshold_boundary_equality_rejects(self) -> None:
        # score == threshold must reject (>= is the comparator).
        m = BottleneckMap(
            cell_size_mm=1.0,
            width=1,
            height=1,
            origin_xy=(0.0, 0.0),
            scores=(0.7,),
        )
        assert filter_seed({"R1": (0.5, 0.5)}, m, 0.7, 0.5, frozenset()) is False


class TestDeterminismAndPurity:
    def test_determinism_property(self) -> None:
        # Two calls with identical inputs return identical results. We
        # do not require the same call signature twice; we just exercise
        # the loop enough times to be confident.
        seed = {"R1": (0.5, 0.5), "R2": (1.5, 0.5)}
        m = _map_with_high_cell()
        first = filter_seed(seed, m, 0.7, 0.5, frozenset())
        for _ in range(5):
            assert filter_seed(seed, m, 0.7, 0.5, frozenset()) == first

    def test_disjoint_maps_no_cross_contamination(self) -> None:
        # Two BottleneckMap instances; filtering on A then B does not
        # mutate either (BottleneckMap is frozen; we just confirm that
        # the result for each map is the result *of that map*).
        seed = {"R1": (1.5, 0.5)}  # 0.8 cell
        map_a = _map_with_high_cell()
        map_b = _low_map()
        assert filter_seed(seed, map_a, 0.7, 0.5, frozenset()) is False
        assert filter_seed(seed, map_b, 0.7, 0.5, frozenset()) is True
        # Calling in the opposite order must also yield the right result.
        assert filter_seed(seed, map_b, 0.7, 0.5, frozenset()) is True
        assert filter_seed(seed, map_a, 0.7, 0.5, frozenset()) is False

    def test_result_depends_on_hv_refs(self) -> None:
        # Same seed+map; result depends on which refs are HV.
        m = BottleneckMap(
            cell_size_mm=1.0,
            width=2,
            height=2,
            origin_xy=(0.0, 0.0),
            scores=(0.6, 0.1, 0.1, 0.1),
        )
        seed = {"U_X": (0.5, 0.5)}
        assert filter_seed(seed, m, 0.7, 0.5, frozenset()) is True
        assert filter_seed(seed, m, 0.7, 0.5, frozenset({"U_X"})) is False


# ---------------------------------------------------------------------------
# Hypothesis property tests
# ---------------------------------------------------------------------------

# Bounded strategies so the test runs fast and stays self-describing.
_seed_strategy = st.dictionaries(
    keys=st.text(min_size=1, max_size=4),
    values=st.tuples(
        st.floats(-50, 50, allow_nan=False, allow_infinity=False),
        st.floats(-50, 50, allow_nan=False, allow_infinity=False),
    ),
    min_size=1,
    max_size=10,
)
_score_list = st.lists(
    st.floats(0, 1, allow_nan=False, allow_infinity=False),
    min_size=4,
    max_size=1024,
)


@st.composite
def _bottleneck_map(draw) -> BottleneckMap:
    width = draw(st.integers(2, 32))
    height = draw(st.integers(2, 32))
    cell_size = draw(st.floats(0.5, 10, allow_nan=False, allow_infinity=False))
    origin_x = draw(st.floats(-20, 20, allow_nan=False, allow_infinity=False))
    origin_y = draw(st.floats(-20, 20, allow_nan=False, allow_infinity=False))
    target = width * height
    scores = draw(st.lists(st.floats(0, 1, allow_nan=False), min_size=target, max_size=target))
    return BottleneckMap(
        cell_size_mm=cell_size,
        width=width,
        height=height,
        origin_xy=(origin_x, origin_y),
        scores=tuple(scores),
    )


@st.composite
def _args_with_boundary(draw) -> tuple:
    """Generate args guaranteed to include a cell-boundary coordinate
    and a negative coordinate, so the property test exercises both
    floor-on-boundary and negative-clamp code paths.
    """
    m = draw(_bottleneck_map())
    # Pick a cell boundary on X (col*cell_size + origin_x) and use a
    # negative Y to exercise the negative-coordinate clamp.
    col = 0
    boundary_x = m.origin_xy[0] + col * m.cell_size_mm
    boundary_y = -1.0  # always negative
    seed: dict[str, tuple[float, float]] = {
        "B1": (boundary_x, boundary_y),
    }
    # Add a couple of random refs so the seed is not trivial.
    extras = draw(
        st.dictionaries(
            keys=st.text(min_size=1, max_size=4),
            values=st.tuples(
                st.floats(-50, 50, allow_nan=False, allow_infinity=False),
                st.floats(-50, 50, allow_nan=False, allow_infinity=False),
            ),
            min_size=0,
            max_size=5,
        )
    )
    seed.update(extras)
    threshold = draw(st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False))
    hv_threshold = draw(st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False))
    hv_refs = draw(
        st.frozensets(st.sampled_from(list(seed.keys())), max_size=len(seed))
    )
    return seed, m, threshold, hv_threshold, hv_refs


class TestProperty:
    @given(_args_with_boundary())
    @settings(max_examples=50, deadline=None)
    def test_idempotent_and_pure(
        self, args: tuple[Mapping, BottleneckMap, float, float, frozenset]
    ) -> None:
        seed, m, threshold, hv_threshold, hv_refs = args
        first = filter_seed(seed, m, threshold, hv_threshold, hv_refs)
        # Calling again with identical inputs returns identical result.
        for _ in range(3):
            assert filter_seed(seed, m, threshold, hv_threshold, hv_refs) == first

    @given(_args_with_boundary())
    @settings(max_examples=50, deadline=None)
    def test_disjoint_map_no_mutation(
        self, args: tuple[Mapping, BottleneckMap, float, float, frozenset]
    ) -> None:
        seed, m, threshold, hv_threshold, hv_refs = args
        before = m.scores
        filter_seed(seed, m, threshold, hv_threshold, hv_refs)
        # The map is a frozen dataclass, so this is enforced at the type
        # level. We assert the visible state to be safe.
        assert m.scores == before

    @given(seed=_seed_strategy, m=_bottleneck_map())
    @settings(max_examples=50, deadline=None)
    def test_below_threshold_when_all_zero(
        self, seed: Mapping[str, tuple[float, float]], m: BottleneckMap
    ) -> None:
        zero_map = replace(m, scores=tuple(0.0 for _ in m.scores))
        assert filter_seed(seed, zero_map, 0.7, 0.5, frozenset()) is True

    @given(_args_with_boundary())
    @settings(max_examples=50, deadline=None)
    def test_property_invariants_observed(
        self, args: tuple[Mapping, BottleneckMap, float, float, frozenset]
    ) -> None:
        """Soft check: the test must include cell-boundary and negative
        coords across the 50 examples. This test is mostly a tripwire
        for the gate in scripts/spikes/rd1_bottleneck_data_path.sh.
        """
        seed, m, _, _, _ = args
        # Find the boundary reference and verify its x coord satisfies
        # (x - origin_x) % cell_size == 0. (Using `approx` for fp equality.)
        for ref, (x, y) in seed.items():
            if ref == "B1":
                rel_x = x - m.origin_xy[0]
                cell = m.cell_size_mm
                # 0.0 (or very close) means it's on a boundary
                if cell > 0:
                    import math

                    mod = math.fmod(rel_x, cell)
                    if abs(mod) < 1e-6 or abs(mod - cell) < 1e-6:
                        assert y < 0, "Expected B1 to also have a negative Y"
                        return
        # If we got here, the constraint was not exercised on this draw;
        # _args_with_boundary guarantees it always is, so failing is OK.
        pytest.fail("Boundary coordinate was not present in this draw")
