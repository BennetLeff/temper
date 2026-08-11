from dataclasses import dataclass

import temper_drc_rs as _drc
import temper_orchestration as _to

from ..geometry.courtyard import Courtyard
from ..state import BoardState
from .base import Stage


@dataclass
class CourtyardCheckStage(Stage):
    """
    Checks for and resolves component courtyard overlaps (Solder Mask Bridges).

    This stage runs after placement to ensure that no two components have colliding
    courtyards. If collisions are found, it nudges components apart.

    Board boundary clamping (DRC-FIX-4):
    After each nudge, positions are clamped to stay within board boundaries.
    This prevents components from drifting outside the board area during
    overlap resolution, which would cause via_dangling DRC violations.

    Phase D batch D6 of the Rust Orchestration Engine plan (2026-08-09-001):
    the **run orchestration** (the iterative nudge loop, the coincident-center
    branch, the clamping call-backs and the ``placements`` write) is
    implemented in Rust (``temper-orchestration``'s ``CourtyardCheckStage`` /
    ``run_courtyard_check``), crossing the FFI once per stage call; the
    ``_find_collisions`` / ``_clamp_position`` methods are CALLED BACK on this
    instance. The collision detection (shapely/GEOS STRtree + intersects), the
    CPython ``random.random()`` nudge noise and the ``_clamp_position`` kernel
    (``temper_drc_rs.clamp_position_py``) stay single-source (GEOS is not
    bit-reproducible by any Rust port). The pre-migration implementation is
    pinned VERBATIM in
    ``tests/deterministic/_courtyard_check_run_py_oracle.py``.
    """

    courtyards: dict[str, Courtyard]
    board_width: float = 100.0  # Board width in mm
    board_height: float = 150.0  # Board height in mm
    margin: float = 5.0  # Keep components this far from board edges
    max_iterations: int = 500
    nudge_step: float = 0.2  # Increased from 0.1

    @property
    def name(self) -> str:
        return "courtyard_check"

    def _clamp_position(self, pos: tuple[float, float]) -> tuple[float, float]:
        """Clamp position to valid board area within margins.

        Args:
            pos: (x, y) position in mm

        Returns:
            Clamped (x, y) position within [margin, board_dim - margin]
        """
        return _drc.clamp_position_py(
            pos[0], pos[1], self.margin, self.board_width, self.board_height
        )

    def run(self, state: BoardState) -> BoardState:
        """Run the courtyard-overlap resolution orchestration in Rust (Phase D
        D6); crosses the FFI once per stage call."""
        return _to.run_courtyard_check(state, self)

    def _find_collisions(self, placements: dict[str, tuple[float, float]]) -> list[tuple[str, str]]:
        """Find courtyard collisions using spatial indexing for O(n log n) performance.

        Optimization: Use R-tree spatial index to avoid O(n²) pairwise checks.
        Also cache transformed polygons to avoid repeated Shapely operations.
        """
        collisions: list[tuple[str, str]] = []
        refs = list(placements.keys())

        # Cache transformed polygons (major optimization - avoids 1M+ Shapely calls)
        transformed_polys = {}
        for ref in refs:
            if ref in self.courtyards:
                pos = placements[ref]
                # Assume rotation = 0 (as per pipeline comment)
                transformed_polys[ref] = self.courtyards[ref].get_global_polygon(pos[0], pos[1], 0)

        # Build spatial index using bounding boxes
        from shapely.strtree import STRtree

        # Create list of (polygon, ref) pairs for STRtree
        polys_with_refs = [(poly, ref) for ref, poly in transformed_polys.items()]

        if not polys_with_refs:
            return collisions

        # Build R-tree index
        tree = STRtree([poly for poly, _ in polys_with_refs])

        # Query for intersections (O(n log n) instead of O(n²))
        #
        # VERIFIED 2026-07-17: shapely>=2.0's STRtree.query() returns an
        # ndarray of integer INDICES into the array the tree was built
        # from, not geometry objects. The previous `if p is candidate_poly`
        # identity check compared a Polygon to a numpy.int64 and could
        # never match, so ref2 was always None and every candidate was
        # skipped -- this stage detected zero collisions on any board,
        # regardless of real overlaps (confirmed empirically: 27 real
        # courtyards_overlap + 16 pth_inside_courtyard kicad-cli errors on
        # a board this stage reported as fully resolved). See
        # docs/solutions/logic-errors/
        # courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md.
        checked_pairs = set()
        for poly, ref1 in polys_with_refs:
            # Query spatial index for candidates (uses bounding box)
            candidate_indices = tree.query(poly)

            for idx in candidate_indices:
                candidate_poly, ref2 = polys_with_refs[idx]

                if ref1 == ref2:
                    continue

                # Avoid checking same pair twice
                pair = tuple(sorted([ref1, ref2]))
                if pair in checked_pairs:
                    continue
                checked_pairs.add(pair)

                # Exact intersection test (after bounding box filter)
                if poly.intersects(candidate_poly) and not poly.touches(candidate_poly):
                    collisions.append((ref1, ref2))

        return collisions
