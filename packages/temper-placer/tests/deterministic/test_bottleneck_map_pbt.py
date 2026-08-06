"""Property-based + metamorphic tests for the migrated BottleneckMap score/coerce
compute.

Wave 4, Phase 5 (deterministic hubs slice). These properties exercise the
migrated ``temper_design_bundle_python.deterministic_hubs.bottleneck_score_at``
/ ``bottleneck_coerce_score`` kernels through the
``temper_placer.deterministic.bottleneck_map`` shim; bit-identical parity
against the pinned pre-migration Python is asserted separately by
``test_bottleneck_map_rust_differential.py``.

Five hypothesis properties (R1c):

- P1. Range: ``score_at`` is one of the map's scores or ``0.0`` (OOB clamp).
- P2. Row-major indexing: the score at the exact origin of cell ``(col, row)``
  equals ``scores[row * width + col]``.
- P3. Floor semantics: for a point strictly inside cell ``(col, row)``,
  ``score_at`` returns that cell's score.
- P4. OOB clamp: points left/below/right/above the grid return exactly ``0.0``.
- P5. Coerce range: ``_coerce_score`` clamps into ``[0.0, 1.0]`` for any
  finite numeric input and rejects bool/None.

Three metamorphic relations (R1d):

- MR1. Cell translation: on a uniform-score map, translating a point by an
  exact number of whole cells preserves the score.
- MR2. Score uniformity: a uniform map returns the same score everywhere in
  the grid.
- MR3. Origin translation: shifting the map origin and the query point by the
  same delta leaves ``score_at`` unchanged (translational invariance).
"""

from __future__ import annotations

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from temper_placer.deterministic.bottleneck_map import (
    BottleneckMap,
    _coerce_score,
)

_cell_st = st.floats(min_value=0.01, max_value=20.0, allow_nan=False, allow_infinity=False)
_dim_st = st.integers(min_value=1, max_value=16)
_score_st = st.floats(min_value=-2.0, max_value=3.0, allow_nan=False, allow_infinity=False)
_origin_st = st.floats(min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False)
_point_st = st.floats(min_value=-500.0, max_value=500.0, allow_nan=False, allow_infinity=False)


@st.composite
def a_map(draw):
    cell = draw(_cell_st)
    w = draw(_dim_st)
    h = draw(_dim_st)
    ox = draw(_origin_st)
    oy = draw(_origin_st)
    scores = tuple(draw(_score_st) for _ in range(w * h))
    return BottleneckMap(
        cell_size_mm=cell, width=w, height=h, origin_xy=(ox, oy), scores=scores
    )


def _in_grid(m, x, y):
    ox, oy = m.origin_xy
    rel_x, rel_y = x - ox, y - oy
    return (
        rel_x >= 0
        and rel_y >= 0
        and rel_x // m.cell_size_mm < m.width
        and rel_y // m.cell_size_mm < m.height
    )


class TestProperties:
    @given(a_map(), _point_st, _point_st)
    @settings(max_examples=100, deadline=None)
    def test_p1_score_is_member_or_zero(self, m, x, y):
        s = m.score_at(x, y)
        if _in_grid(m, x, y):
            assert s in m.scores
        else:
            assert s == 0.0

    @given(a_map(), _dim_st, _dim_st)
    @settings(max_examples=60, deadline=None)
    def test_p2_row_major_at_origin(self, m, col, row):
        # Probe the MIDPOINT of cell (col, row): the exact-origin probe
        # `(row*cell) // cell == row` is fp-fragile (the product rounds), and
        # both sides agree bit-exactly on whichever side it lands — the
        # midpoint is guaranteed inside the cell.
        col %= m.width
        row %= m.height
        x = m.origin_xy[0] + col * m.cell_size_mm + m.cell_size_mm / 2.0
        y = m.origin_xy[1] + row * m.cell_size_mm + m.cell_size_mm / 2.0
        assert m.score_at(x, y) == m.scores[row * m.width + col]

    @given(a_map(), _dim_st, _dim_st)
    @settings(max_examples=100, deadline=None)
    def test_p3_strictly_inside_cell(self, m, col, row):
        col %= m.width
        row %= m.height
        x = m.origin_xy[0] + col * m.cell_size_mm + m.cell_size_mm / 2.0
        y = m.origin_xy[1] + row * m.cell_size_mm + m.cell_size_mm / 2.0
        assert m.score_at(x, y) == m.scores[row * m.width + col]

    @given(a_map(), _cell_st)
    @settings(max_examples=60, deadline=None)
    def test_p4_oob_clamp(self, m, big):
        assume(big > 0)
        span = max(m.width, m.height) * m.cell_size_mm
        assert m.score_at(m.origin_xy[0] - big, m.origin_xy[1]) == 0.0
        assert m.score_at(m.origin_xy[0], m.origin_xy[1] - big) == 0.0
        assert m.score_at(m.origin_xy[0] + span + big, m.origin_xy[1]) == 0.0
        assert m.score_at(m.origin_xy[0], m.origin_xy[1] + span + big) == 0.0

    @given(_score_st)
    @settings(max_examples=60, deadline=None)
    def test_p5_coerce_clamps_to_unit_range(self, value):
        if isinstance(value, bool) or value is None:
            return
        result = _coerce_score(value)
        assert 0.0 <= result <= 1.0
        if value > 1.0:
            assert result == 1.0
        if value < 0.0:
            assert result == 0.0


class TestMetamorphic:
    @given(a_map(), _dim_st, _dim_st, _point_st, _point_st)
    @settings(max_examples=60, deadline=None)
    def test_mr1_whole_cell_translation(self, m, dc, dr, x, y):
        """Translating by whole cells on a uniform map preserves the score."""
        # Restrict the probe point into the grid (mod the span) so no OOB
        # clamping interferes with the relation.
        span_x = m.width * m.cell_size_mm
        span_y = m.height * m.cell_size_mm
        px = m.origin_xy[0] + (x % span_x if span_x > 0 else 0.0)
        py = m.origin_xy[1] + (y % span_y if span_y > 0 else 0.0)
        uniform = BottleneckMap(
            cell_size_mm=m.cell_size_mm,
            width=m.width,
            height=m.height,
            origin_xy=m.origin_xy,
            scores=tuple([0.7] * (m.width * m.height)),
        )
        dx = dc * m.cell_size_mm
        dy = dr * m.cell_size_mm
        if not _in_grid(uniform, px + dx, py + dy):
            return
        assert uniform.score_at(px + dx, py + dy) == uniform.score_at(px, py)

    @given(a_map(), _point_st, _point_st, _point_st, _point_st)
    @settings(max_examples=60, deadline=None)
    def test_mr2_uniform_map_constant(self, m, x, y, x2, y2):
        uniform = BottleneckMap(
            cell_size_mm=m.cell_size_mm,
            width=m.width,
            height=m.height,
            origin_xy=m.origin_xy,
            scores=tuple([0.7] * (m.width * m.height)),
        )
        if _in_grid(uniform, x, y) and _in_grid(uniform, x2, y2):
            assert uniform.score_at(x, y) == uniform.score_at(x2, y2)

    @given(a_map(), _point_st, _point_st, _origin_st, _origin_st)
    @settings(max_examples=60, deadline=None)
    def test_mr3_origin_translation(self, m, x, y, tx, ty):
        """Shifting origin and query by the same delta is identity."""
        if not _in_grid(m, x, y):
            return
        moved = BottleneckMap(
            cell_size_mm=m.cell_size_mm,
            width=m.width,
            height=m.height,
            origin_xy=(m.origin_xy[0] + tx, m.origin_xy[1] + ty),
            scores=m.scores,
        )
        if not _in_grid(moved, x + tx, y + ty):
            return
        assert moved.score_at(x + tx, y + ty) == m.score_at(x, y)
