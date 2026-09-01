"""
Router V6 Stage 3.0: Bundle Analyzer — Net Partitioning into Bundle Equivalence Classes.

Partitions nets into bundle classes based on constraint-type signature and geometric
overlap (Jaccard index on skeleton edge coverage). Produces a deterministic
BundleManifest consumed by the bundled encoding path.

Origin: U1 of docs/plans/2026-06-28-002-feat-net-bundling-lazy-grounding-plan.md
Requirements: R1, R2, R2.1

Wave-4 migration (spike docs/evidence/2026-08-09-bundle-analyzer-geos-spike.md):
the GEOS seam moved to ``temper-geometry``'s ``bundle_analyzer`` kernel —
``MultiPoint(pads).convex_hull`` is a faithful transcription of GEOS's own
ConvexHull (Graham scan + double-double orientation predicate), ``hull.buffer(m)``
is a transcription of GEOS's ``OffsetSegmentGenerator`` (region bit-identical to
shapely 2.1.2 / GEOS 3.13.1), and the ``STRtree(points).query(footprint,
predicate="contains")`` edge-cover query is a strict point-in-convex-polygon over
the same region (the index only prunes candidates; the result set is a pure
function of the region).  The two ``combined.union(...)`` sites below survive in
Python because their only consumer is ``BundleClass.geometric_footprint`` — a
field with zero production readers — the same "PORT with kept lines" pattern as
``obstacle_map.py``'s ``LineString.buffer``/``unary_union`` keeps.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import temper_geometry as _tg
from shapely.geometry import MultiPoint, Polygon


@dataclass(frozen=True)
class TypeSignature:
    """Constraint-type signature for bundle equivalence.

    Two nets share a bundle class iff their TypeSignature is identical AND
    their geometric footprints overlap sufficiently (Jaccard > 0.5).

    2026-08-07 (docs/evidence/2026-08-07-sat-model-reduction-options.md
    Sec 3.4): the original signature also matched on exact ``trace_width``/
    ``clearance`` (rounded floats) and ``pin_layer_set`` (an exact
    frozenset). On the production board that produced only 8 bundle
    classes covering 21/110 nets -- this board has 11 distinct design-rule
    netclasses (``netclass_rules.yaml``), each with its own width/clearance,
    so "same coarse net_class" (e.g. 98 nets all classified "signal" by
    ``net_classification.classify_net_type``) almost never meant "same
    exact width/clearance/pin-layer-set" in practice. Widened here to
    ``safety_category`` (the design-rule-authoritative AC/HV/LV isolation
    tier) + ``net_class`` (the coarse name-pattern bucket) + diff-pair
    status -- see this class's own module docstring / ``analyze()``'s
    soundness note for why this widening does not weaken the model.
    """

    safety_category: str | None  # "AC", "HV", "LV", or None (unassigned net)
    net_class: str  # "ground", "power", "hv", "signal"
    has_diff_pair: bool


@dataclass
class BundleClass:
    """A bundle equivalence class: set of nets sharing constraint signature + geometry."""

    bundle_id: int
    net_indices: list[int]  # sorted by net index for determinism
    type_signature: TypeSignature
    geometric_footprint: Polygon
    constraint_types: frozenset[str]  # {"safety", "performance", "aesthetic"}
    is_diff_pair: bool


@dataclass
class BundleManifest:
    """Complete bundle partition of the netlist.

    Attributes:
        bundles: Mapping from bundle_id to BundleClass.
        bundle_id_for_net: Reverse lookup from net_idx to bundle_id.
        unbundled_net_indices: Nets that could not be bundled (singletons).
    """

    bundles: dict[int, BundleClass] = field(default_factory=dict)
    bundle_id_for_net: dict[int, int] = field(default_factory=dict)
    unbundled_net_indices: list[int] = field(default_factory=list)

    @property
    def bundle_count(self) -> int:
        return len(self.bundles)

    def is_bundled(self, net_idx: int) -> bool:
        return net_idx in self.bundle_id_for_net


class BundleAnalyzer:
    """Partitions nets into bundle equivalence classes.

    Two nets are bundle-equivalent iff:
    1. Their TypeSignature is identical (same safety_category, net_class,
       diff-pair status -- see ``TypeSignature``'s own docstring for why
       exact trace_width/clearance/pin_layer_set matching was dropped
       2026-08-07)
    2. Their geometric footprints overlap with Jaccard index > 0.5

    Diff-pair nets form their own dedicated 2-net bundles (KD6).

    **Soundness of the widened TypeSignature** (docs/evidence/2026-08-07-
    sat-model-reduction-options.md Sec 3.4, this task's own fix):

    - **Capacity soundness**: a bundle's SAT channel variable is shared by
      all its member nets, so a channel-capacity term must reflect the
      combined physical width of every member, not one representative
      member's width. ``ModelBuilder._create_capacity_constraints`` (fixed
      alongside this change) sums each member net's *own*
      ``trace_width_mm + clearance_mm`` from ``design_rules`` when building
      a bundle's capacity term -- so bundling nets with different widths no
      longer under-counts the capacity a bundle actually needs. This is
      what makes it safe to drop the old exact ``trace_width``/``clearance``
      match: the capacity constraint is exact per-member now, not merely
      "close enough because everyone in the bundle has the same width."
    - **Safety-domain soundness**: bundling never crosses an AC/HV/LV
      boundary, because ``safety_category`` -- the design-rule-authoritative
      isolation tier from ``netclass_rules.yaml`` (not the name-pattern
      heuristic in ``net_classification.py``, which can misclassify a
      HV-designated net like ``GATE_HS``/``GATE_LS`` as "signal" purely
      because its *name* doesn't match an HV pattern) -- is part of the
      required-match signature. A net design-rules tags AC or HV can never
      share a bundle (and therefore never share a capacity/routing
      decision) with an LV net, regardless of what the coarser ``net_class``
      says.
    - **Geometric soundness is unchanged**: the Jaccard > 0.5 footprint-
      overlap requirement -- the primary defense against forcing unrelated,
      board-spanning nets into one bundle -- is untouched by this change.
    - **Known pre-existing gap, not affected either way**: SMD pin
      layer restrictions (``ModelBuilder._create_layer_constraints``) are
      not enforced for bundled member nets today, independent of
      ``TypeSignature`` -- that function only ever looks up per-net
      ``(net_idx, edge_id)`` keys, which bundled member nets never
      populate (only the unbundled/singleton nets do). Dropping
      ``pin_layer_set`` from the signature does not remove any enforcement
      that existed, since none existed for bundled nets before this change
      either; this remains a real, separately-scoped gap for future work.
    """

    def __init__(
        self,
        nets: list,
        skeletons: dict[str, Any],
        design_rules: Any | None = None,
        diff_pairs: list | None = None,
        pcb: Any | None = None,
        jaccard_threshold: float = 0.5,
    ):
        self.nets = nets
        self.skeletons = skeletons
        self.design_rules = design_rules
        self.diff_pairs = diff_pairs or []
        self.pcb = pcb
        self.jaccard_threshold = jaccard_threshold

        # Build fast lookups
        self._net_to_idx = {net.name: i for i, net in enumerate(nets)}
        self._diff_pair_net_names: set[str] = set()
        for dp in self.diff_pairs:
            self._diff_pair_net_names.add(dp.p_net)
            self._diff_pair_net_names.add(dp.n_net)

        # Compute median skeleton edge length for footprint expansion
        self._median_edge_length = self._compute_median_edge_length()

        # Lazily-built (edge_id, midpoint) table shared across all
        # `_compute_covered_edges` calls -- see that method's docstring for
        # why (2026-08-07 vectorization).  The Rust
        # `covered_edge_indices_py` kernel scans these arrays with a
        # bounding-box precheck in place of the pre-migration STRtree
        # spatial index.
        self._edge_ids: np.ndarray | None = None
        self._mids_x: list[float] = []
        self._mids_y: list[float] = []

    def _compute_median_edge_length(self) -> float:
        lengths = []
        for skeleton in self.skeletons.values():
            for _u, _v, data in skeleton.graph.edges_with_data():  # type: ignore[attr-defined]
                w = data.get("weight", 1.0)
                lengths.append(w)
        if not lengths:
            return 10.0
        lengths.sort()
        mid = len(lengths) // 2
        return lengths[mid] if len(lengths) % 2 == 1 else (lengths[mid - 1] + lengths[mid]) / 2.0

    def _net_pad_positions(self, net) -> list[tuple[float, float]]:
        """Resolve a net's pad positions to world coordinates.

        Delegates to ``temper_placer.core.pin_geometry.net_pad_positions``,
        the consolidated SSOT. This method previously summed
        ``comp.initial_position + pin.position`` directly, silently
        skipping the component's rotation -- for the 148/169 (87.6%)
        components on ``pcb/temper.kicad_pcb`` with nonzero
        ``initial_rotation``, every pad position feeding this net's
        geometric footprint (``_compute_geometric_footprint``, used for
        bundle-class Jaccard overlap) was wrong. See
        ``pin_geometry.net_pad_positions``'s docstring for the measured
        error and ``scripts/duplicate_predicate_registry.py``.
        """
        if not self.pcb:
            return []

        from temper_placer.core.pin_geometry import net_pad_positions

        comp_by_ref = {comp.ref: comp for comp in self.pcb.components}
        return net_pad_positions(net, comp_by_ref)

    def _compute_geometric_footprint(self, net) -> Polygon:
        """Compute the convex hull of a net's pad positions, expanded by median edge length.

        Wave-4 migration: for >=3 pads the hull and its buffer are computed
        by ``temper_geometry``'s ``bundle_analyzer`` kernel (GEOS ConvexHull
        + OffsetSegmentGenerator transcriptions, region bit-identical to the
        pre-migration shapely result).  The 0/1/2-pad footprints are pure
        axis-aligned box construction and stay here.
        """
        positions = self._net_pad_positions(net)
        if len(positions) < 2:
            # Single pad: create a small square around it
            if positions:
                cx, cy = positions[0]
                m = self._median_edge_length
                return Polygon(
                    [
                        (cx - m, cy - m),
                        (cx + m, cy - m),
                        (cx + m, cy + m),
                        (cx - m, cy + m),
                    ]
                )
            # No positions: empty polygon
            return Polygon()

        if len(positions) == 2:
            # Two pads: create a rectangular envelope
            (x1, y1), (x2, y2) = positions
            _dx, _dy = abs(x2 - x1), abs(y2 - y1)
            margin = self._median_edge_length
            minx = min(x1, x2) - margin
            maxx = max(x1, x2) + margin
            miny = min(y1, y2) - margin
            maxy = max(y1, y2) + margin
            return Polygon(
                [
                    (minx, miny),
                    (maxx, miny),
                    (maxx, maxy),
                    (minx, maxy),
                ]
            )

        ring = _tg.convex_hull_ring_py(positions)
        if not ring:
            # MultiPoint(positions).convex_hull is not a polygon (collinear
            # or degenerate pads) -> the pre-migration code returned
            # Polygon().
            return Polygon()
        return Polygon(_tg.hull_buffer_ring_py(ring, self._median_edge_length))

    def _build_edge_index(self) -> None:
        """Precompute every skeleton edge's id and midpoint, once.

        2026-08-07 vectorization (docs/evidence/2026-08-07-sat-model-
        reduction-options.md Sec 3.4): the previous ``_compute_covered_edges``
        re-derived every one of ``total_edges`` (id, midpoint) pairs AND
        re-tested each one against the net's footprint from scratch on
        *every* call -- i.e. once per net. On the production board
        (204,490 edges x 110 nets) that is ~22.5M raw-Python
        ``Polygon.contains(Point(...))`` calls and MEASURED ~391s wall,
        ~3.5s/net average (one net alone: 80.6s). This method builds the
        (edge_id, midpoint) table exactly once, cached on the instance;
        ``_compute_covered_edges`` then hands the midpoint arrays to the
        Rust kernel, which does one bounding-box-pruned, exact point-in-
        convex-polygon pass per net instead of a Python-level loop over
        every edge -- the same fix shape as ``07d514f9``'s KD-tree rewrite
        of island bridging elsewhere in this pipeline.
        """
        if self._edge_ids is not None:
            return

        edge_ids: list[str] = []
        mids_x: list[float] = []
        mids_y: list[float] = []
        for layer_name, skeleton in self.skeletons.items():
            for i, (_u, _v) in enumerate(skeleton.graph.edges):  # type: ignore[attr-defined]
                n1, n2 = sorted([_u, _v])
                edge_ids.append(f"{layer_name}_E{i}_{n1}_{n2}")
                mids_x.append((n1[0] + n2[0]) / 2.0)
                mids_y.append((n1[1] + n2[1]) / 2.0)

        self._edge_ids = np.array(edge_ids, dtype=object)
        self._mids_x = mids_x
        self._mids_y = mids_y

    def _compute_covered_edges(self, footprint: Polygon) -> frozenset[str]:
        """Compute the set of skeleton edge IDs whose midpoints lie within the footprint.

        Wave-4 migration: the pre-migration ``STRtree(points).query(footprint,
        predicate="contains")`` becomes a strict point-in-convex-polygon scan
        in ``temper-geometry``'s ``bundle_analyzer`` kernel.  The result set
        is a pure function of the footprint region -- the index only pruned
        candidates -- so it is bit-identical.
        """
        self._build_edge_index()
        assert self._edge_ids is not None
        if not self._mids_x or footprint.is_empty:
            return frozenset()
        try:
            idx = _tg.covered_edge_indices_py(
                list(footprint.exterior.coords),
                self._mids_x,
                self._mids_y,
            )
        except Exception:
            return frozenset()
        if len(idx) == 0:
            return frozenset()
        return frozenset(self._edge_ids[idx].tolist())

    def _jaccard(self, a: frozenset, b: frozenset) -> float:
        """Jaccard index: |A ∩ B| / |A ∪ B|."""
        if not a and not b:
            return 1.0
        intersection = len(a & b)
        union = len(a | b)
        if union == 0:
            return 0.0
        return intersection / union

    def _compute_type_signature(self, net) -> TypeSignature:
        """Compatibility adapter for direct callers; Rust owns classification."""
        from temper_placer.router_v6.net_classification import get_single_layer_mode

        safety_category: str | None = None
        if self.design_rules:
            rule = self.design_rules.get_rules_for_net(net.name)  # type: ignore[attr-defined]
            safety_category = getattr(rule, "safety_category", None)
        safety, net_class, has_diff_pair = _tg.bundle_type_signature_py(
            net.name,
            safety_category,
            net.name in self._diff_pair_net_names,
            get_single_layer_mode(),
        )
        return TypeSignature(
            safety_category=safety,
            net_class=net_class,
            has_diff_pair=has_diff_pair,
        )

    def analyze(self) -> BundleManifest:
        """Run the full bundle analysis and return a BundleManifest.

        Pad resolution and shapely footprint construction remain the narrow
        Python compatibility seam.  Rust owns every deterministic analysis
        decision: v6 type signatures, edge-cover collection, Jaccard graph,
        diff-pair handling, connected components, IDs/order, and manifest
        records.  The dataclass construction below is deliberately only an
        adapter for the established Python-facing API.
        """
        n = len(self.nets)
        if n == 0:
            return BundleManifest()

        # Python resolves mutable PCB objects and retains the legacy shapely
        # footprint field.  Rust receives only immutable primitive records.
        net_footprints: list[Polygon] = []
        for net in self.nets:
            footprint = self._compute_geometric_footprint(net)
            net_footprints.append(footprint)
        rings = [
            [] if footprint.is_empty else list(footprint.exterior.coords)
            for footprint in net_footprints
        ]
        safety_categories: list[str | None] = []
        for net in self.nets:
            safety_category = None
            if self.design_rules:
                rule = self.design_rules.get_rules_for_net(net.name)  # type: ignore[attr-defined]
                safety_category = getattr(rule, "safety_category", None)
            safety_categories.append(safety_category)
        diff_pairs = [
            (dp.p_net, dp.n_net, dp.base_name)
            for dp in self.diff_pairs
        ]
        from temper_placer.router_v6.net_classification import get_single_layer_mode

        self._build_edge_index()
        assert self._edge_ids is not None
        mids_x, mids_y = self._mids_x, self._mids_y
        # The pinned differential oracle overrides the edge-index builder
        # with its verbatim STRtree implementation.  Recover its immutable
        # point coordinates only for that test-only shape; production always
        # uses the midpoint arrays built above.
        if len(mids_x) != len(self._edge_ids) and hasattr(self, "_edge_points"):
            points = self._edge_points  # type: ignore[attr-defined]
            mids_x = [point.x for point in points]
            mids_y = [point.y for point in points]
        records, id_pairs, unbundled = _tg.analyze_bundle_manifest_py(
            [net.name for net in self.nets],
            safety_categories,
            diff_pairs,
            rings,
            self._edge_ids.tolist(),
            mids_x,
            mids_y,
            self.jaccard_threshold,
            get_single_layer_mode(),
        )

        bundles: dict[int, BundleClass] = {}
        for (
            bundle_id,
            indices,
            safety_category,
            net_class,
            signature_has_diff_pair,
            is_diff_pair,
            constraint_types,
        ) in records:
            combined = net_footprints[indices[0]]
            for idx in indices[1:]:
                with contextlib.suppress(Exception):
                    combined = combined.union(net_footprints[idx])
            if isinstance(combined, MultiPoint):
                combined = combined.convex_hull
            if not isinstance(combined, Polygon):
                combined = Polygon()
            bundles[bundle_id] = BundleClass(
                bundle_id=bundle_id,
                net_indices=list(indices),
                type_signature=TypeSignature(
                    safety_category=safety_category,
                    net_class=net_class,
                    has_diff_pair=signature_has_diff_pair,
                ),
                geometric_footprint=combined,
                constraint_types=frozenset(constraint_types),
                is_diff_pair=is_diff_pair,
            )
        return BundleManifest(
            bundles=bundles,
            bundle_id_for_net=dict(id_pairs),
            unbundled_net_indices=list(unbundled),
        )
