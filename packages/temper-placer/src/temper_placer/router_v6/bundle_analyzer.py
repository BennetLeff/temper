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

        Pin resolution goes through
        :func:`temper_placer.core.pad_identity.resolve_net_pins`
        (occurrence-indexed), not ``comp.get_pin(pin_name)``'s first
        match -- an independent, previously-unfixed copy of the same bug
        ``_pipeline_grid._net_pad_positions`` had (see
        ``temper_placer.core.pad_identity``'s module docstring): a
        component with more than one physical pad sharing a pad number
        (K2/K3's current-sharing contacts) would otherwise have every
        occurrence resolve to the SAME coordinate, silently shrinking a
        net's convex-hull footprint used for bundle/EMI-constraint
        detection.
        """
        from temper_placer.core.pad_identity import resolve_net_pins

        positions: list[tuple[float, float]] = []
        if not self.pcb:
            return positions

        # Build comp_by_ref
        comp_by_ref = {comp.ref: comp for comp in self.pcb.components}

        for comp_ref, _pin_name, pin in resolve_net_pins(net, comp_by_ref):
            comp = comp_by_ref.get(comp_ref)
            if comp is None:
                continue
            comp_pos = getattr(comp, "initial_position", None)
            if comp_pos is None:
                continue
            if pin is None:
                positions.append((float(comp_pos[0]), float(comp_pos[1])))
                continue
            px, py = pin.position
            positions.append((float(comp_pos[0]) + float(px), float(comp_pos[1]) + float(py)))
        return positions

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
        """Compute the constraint-type signature for a net.

        See ``TypeSignature``'s own docstring (2026-08-07) for why this
        keys on ``safety_category`` (design-rule-authoritative AC/HV/LV
        isolation tier) + ``net_class`` (coarse name-pattern bucket) +
        diff-pair status, rather than exact trace_width/clearance/
        pin_layer_set as before.
        """
        from temper_placer.router_v6.net_classification import classify_net_type

        net_class = classify_net_type(net.name)
        has_diff_pair = net.name in self._diff_pair_net_names

        safety_category: str | None = None
        if self.design_rules:
            rule = self.design_rules.get_rules_for_net(net.name)  # type: ignore[attr-defined]
            safety_category = getattr(rule, "safety_category", None)

        return TypeSignature(
            safety_category=safety_category,
            net_class=net_class,
            has_diff_pair=has_diff_pair,
        )

    def analyze(self) -> BundleManifest:
        """Run the full bundle analysis and return a BundleManifest."""
        n = len(self.nets)
        if n == 0:
            return BundleManifest()

        # Compute per-net type signatures and edge covers
        net_signatures: list[TypeSignature] = []
        net_edge_covers: list[frozenset[str]] = []
        net_footprints: list[Polygon] = []

        for net in self.nets:
            sig = self._compute_type_signature(net)
            net_signatures.append(sig)
            footprint = self._compute_geometric_footprint(net)
            net_footprints.append(footprint)
            net_edge_covers.append(self._compute_covered_edges(footprint))

        # Group by type signature
        sig_groups: dict[TypeSignature, list[int]] = {}
        for i, sig in enumerate(net_signatures):
            sig_groups.setdefault(sig, []).append(i)

        # Within each type-signature group, partition by geometric overlap
        bundles = {}
        bundle_id_for_net: dict[int, int] = {}
        unbundled: list[int] = []
        next_bundle_id = 0

        for sig, net_indices in sig_groups.items():
            if len(net_indices) == 1:
                # Singleton: cannot bundle
                ni = net_indices[0]
                unbundled.append(ni)
                continue

            # Detect diff-pair nets in this group
            diff_pair_nets_in_group: set[int] = set()
            for ni in net_indices:
                net_name = self.nets[ni].name
                if net_name in self._diff_pair_net_names:
                    diff_pair_nets_in_group.add(ni)

            # KD6: Diff-pair nets form their own 2-net bundles
            # Group diff-pair nets and non-diff-pair nets separately
            paired_diff_nets: list[tuple[int, int]] = []
            remaining_diff_nets: set[int] = set()
            remaining_non_diff_nets: list[int] = []

            for ni in net_indices:
                if ni in diff_pair_nets_in_group:
                    remaining_diff_nets.add(ni)
                else:
                    remaining_non_diff_nets.append(ni)

            # Match diff pairs
            diff_pair_by_name: dict[str, tuple[str, str]] = {}
            for dp in self.diff_pairs:
                diff_pair_by_name[dp.base_name] = (dp.p_net, dp.n_net)

            matched_pairs: set[str] = set()
            for dp in self.diff_pairs:
                base = dp.base_name
                if base in matched_pairs:
                    continue
                p_idx = self._net_to_idx.get(dp.p_net)
                n_idx = self._net_to_idx.get(dp.n_net)
                if (
                    p_idx is not None
                    and n_idx is not None
                    and p_idx in remaining_diff_nets
                    and n_idx in remaining_diff_nets
                ):
                    paired_diff_nets.append((p_idx, n_idx))
                    remaining_diff_nets.discard(p_idx)
                    remaining_diff_nets.discard(n_idx)
                    matched_pairs.add(base)

            # Create bundles for diff pairs (each pair = one bundle)
            for p_idx, n_idx in paired_diff_nets:
                sorted_nets = sorted([p_idx, n_idx])
                # Use combined footprint.  KEPT LINE: the combined footprint
                # only populates `geometric_footprint`, a field with zero
                # production consumers (the pipeline serializes only
                # bundle_id/net_indices/constraint_types/is_diff_pair), so
                # the union stays in shapely -- see the module docstring.
                combined = net_footprints[p_idx]
                with contextlib.suppress(Exception):
                    combined = combined.union(net_footprints[n_idx])
                if isinstance(combined, MultiPoint):
                    combined = combined.convex_hull

                bundles[next_bundle_id] = BundleClass(
                    bundle_id=next_bundle_id,
                    net_indices=sorted_nets,
                    type_signature=sig,
                    geometric_footprint=combined
                    if isinstance(combined, Polygon)
                    else net_footprints[p_idx],
                    constraint_types=frozenset({"safety", "performance"}),
                    is_diff_pair=True,
                )
                for ni in sorted_nets:
                    bundle_id_for_net[ni] = next_bundle_id
                next_bundle_id += 1

            # Unmatched diff-pair nets go into non-diff-pair pool
            remaining_non_diff_nets.extend(remaining_diff_nets)
            remaining_non_diff_nets.sort()

            # Cluster remaining non-diff-pair nets by geometric overlap (Jaccard)
            if not remaining_non_diff_nets:
                continue

            # Greedy clustering: build connected components via Jaccard > threshold
            # Each component becomes a bundle
            adjacency: dict[int, set[int]] = {ni: set() for ni in remaining_non_diff_nets}
            for i in range(len(remaining_non_diff_nets)):
                for j in range(i + 1, len(remaining_non_diff_nets)):
                    ni = remaining_non_diff_nets[i]
                    nj = remaining_non_diff_nets[j]
                    jac = self._jaccard(net_edge_covers[ni], net_edge_covers[nj])
                    if jac > self.jaccard_threshold:
                        adjacency[ni].add(nj)
                        adjacency[nj].add(ni)

            visited: set[int] = set()
            for ni in remaining_non_diff_nets:
                if ni in visited:
                    continue
                # BFS to find connected component
                component: list[int] = []
                stack = [ni]
                while stack:
                    node = stack.pop()
                    if node in visited:
                        continue
                    visited.add(node)
                    component.append(node)
                    for neighbor in adjacency.get(node, set()):
                        if neighbor not in visited:
                            stack.append(neighbor)

                component.sort()
                if len(component) == 1:
                    unbundled.append(component[0])
                else:
                    # Compute combined footprint.  KEPT LINE: the union
                    # output only populates the dead `geometric_footprint`
                    # field (see the diff-pair kept line above).
                    combined_fp = None
                    for idx in component:
                        fp = net_footprints[idx]
                        if combined_fp is None:
                            combined_fp = fp
                        else:
                            with contextlib.suppress(Exception):
                                combined_fp = combined_fp.union(fp)
                    if combined_fp is None or not isinstance(combined_fp, Polygon):
                        combined_fp = Polygon()

                    bundles[next_bundle_id] = BundleClass(
                        bundle_id=next_bundle_id,
                        net_indices=component,
                        type_signature=sig,
                        geometric_footprint=combined_fp,
                        constraint_types=frozenset(),
                        is_diff_pair=False,
                    )
                    for ni in component:
                        bundle_id_for_net[ni] = next_bundle_id
                    next_bundle_id += 1

        # Sort bundles by bundle_id (which is already in order of first net)
        unbundled.sort()

        return BundleManifest(
            bundles={bid: bundles[bid] for bid in sorted(bundles)},
            bundle_id_for_net=dict(sorted(bundle_id_for_net.items())),
            unbundled_net_indices=unbundled,
        )
