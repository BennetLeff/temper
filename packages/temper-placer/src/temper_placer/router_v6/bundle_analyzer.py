"""
Router V6 Stage 3.0: Bundle Analyzer — Net Partitioning into Bundle Equivalence Classes.

Partitions nets into bundle classes based on constraint-type signature and geometric
overlap (Jaccard index on skeleton edge coverage). Produces a deterministic
BundleManifest consumed by the bundled encoding path.

Origin: U1 of docs/plans/2026-06-28-002-feat-net-bundling-lazy-grounding-plan.md
Requirements: R1, R2, R2.1
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import Any

from shapely.geometry import MultiPoint, Point, Polygon


@dataclass(frozen=True)
class TypeSignature:
    """Constraint-type signature for bundle equivalence.

    Two nets share a bundle class iff their TypeSignature is identical AND
    their geometric footprints overlap sufficiently (Jaccard > 0.5).
    """
    net_class: str  # "ground", "power", "hv", "signal"
    trace_width: float  # mm
    clearance: float  # mm
    has_diff_pair: bool
    pin_layer_set: frozenset[str]


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
    1. Their TypeSignature is identical (same net class, width, clearance, etc.)
    2. Their geometric footprints overlap with Jaccard index > 0.5

    Diff-pair nets form their own dedicated 2-net bundles (KD6).
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

    def _compute_median_edge_length(self) -> float:
        lengths = []
        for skeleton in self.skeletons.values():
            for _u, _v, data in skeleton.graph.edges(data=True):  # type: ignore[attr-defined]
                w = data.get("weight", 1.0)
                lengths.append(w)
        if not lengths:
            return 10.0
        lengths.sort()
        mid = len(lengths) // 2
        return lengths[mid] if len(lengths) % 2 == 1 else (lengths[mid - 1] + lengths[mid]) / 2.0

    def _net_pad_positions(self, net) -> list[tuple[float, float]]:
        """Resolve a net's pad positions to world coordinates."""
        positions: list[tuple[float, float]] = []
        if not self.pcb:
            return positions

        # Build comp_by_ref
        comp_by_ref = {comp.ref: comp for comp in self.pcb.components}

        for comp_ref, pin_name in getattr(net, "pins", []):
            comp = comp_by_ref.get(comp_ref)
            if comp is None:
                continue
            comp_pos = getattr(comp, "initial_position", None)
            if comp_pos is None:
                continue
            pin = comp.get_pin(pin_name) if hasattr(comp, "get_pin") else None
            if pin is None:
                positions.append((float(comp_pos[0]), float(comp_pos[1])))
                continue
            px, py = pin.position
            positions.append(
                (float(comp_pos[0]) + float(px), float(comp_pos[1]) + float(py))
            )
        return positions

    def _compute_geometric_footprint(self, net) -> Polygon:
        """Compute the convex hull of a net's pad positions, expanded by median edge length."""
        positions = self._net_pad_positions(net)
        if len(positions) < 2:
            # Single pad: create a small square around it
            if positions:
                cx, cy = positions[0]
                m = self._median_edge_length
                return Polygon([
                    (cx - m, cy - m),
                    (cx + m, cy - m),
                    (cx + m, cy + m),
                    (cx - m, cy + m),
                ])
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
            return Polygon([
                (minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy),
            ])

        mp = MultiPoint(positions)
        hull = mp.convex_hull
        if isinstance(hull, Polygon):
            return hull.buffer(self._median_edge_length)
        return Polygon()

    def _compute_covered_edges(self, footprint: Polygon) -> frozenset[str]:
        """Compute the set of skeleton edge IDs whose midpoints lie within the footprint."""
        edges: set[str] = set()
        for layer_name, skeleton in self.skeletons.items():
            for i, (_u, _v) in enumerate(skeleton.graph.edges):  # type: ignore[attr-defined]
                n1, n2 = sorted([_u, _v])
                edge_id = f"{layer_name}_E{i}_{n1}_{n2}"
                # Check if edge midpoint is within footprint
                mx = (n1[0] + n2[0]) / 2.0
                my = (n1[1] + n2[1]) / 2.0
                try:
                    if footprint.contains(Point(mx, my)):
                        edges.add(edge_id)
                except Exception:
                    pass
        return frozenset(edges)

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
        """Compute the constraint-type signature for a net."""
        from temper_placer.router_v6.net_classification import classify_net_type

        net_class = classify_net_type(net.name)
        has_diff_pair = net.name in self._diff_pair_net_names

        width = 0.2
        clearance = 0.2
        if self.design_rules:
            rule = self.design_rules.get_rules_for_net(net.name)  # type: ignore[attr-defined]
            width = rule.trace_width_mm
            clearance = rule.clearance_mm

        # Pin layer set from component pin lookups
        pin_layers: set[str] = set()
        if self.pcb:
            comp_by_ref = {comp.ref: comp for comp in self.pcb.components}  # type: ignore[attr-defined]
            for comp_ref, pin_name in getattr(net, "pins", []):
                comp = comp_by_ref.get(comp_ref)
                if comp is None:
                    continue
                pin = comp.get_pin(pin_name) if hasattr(comp, "get_pin") else None  # type: ignore[attr-defined]
                if pin and not getattr(pin, "is_pth", True):
                    pin_layers.add(getattr(pin, "layer", "F.Cu"))
                else:
                    pin_layers.add("any")

        return TypeSignature(
            net_class=net_class,
            trace_width=round(width, 4),
            clearance=round(clearance, 4),
            has_diff_pair=has_diff_pair,
            pin_layer_set=frozenset(pin_layers),
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
                if p_idx is not None and n_idx is not None:
                    if p_idx in remaining_diff_nets and n_idx in remaining_diff_nets:
                        paired_diff_nets.append((p_idx, n_idx))
                        remaining_diff_nets.discard(p_idx)
                        remaining_diff_nets.discard(n_idx)
                        matched_pairs.add(base)

            # Create bundles for diff pairs (each pair = one bundle)
            for p_idx, n_idx in paired_diff_nets:
                sorted_nets = sorted([p_idx, n_idx])
                # Use combined footprint
                combined = net_footprints[p_idx]
                with contextlib.suppress(Exception):
                    combined = combined.union(net_footprints[n_idx])
                if isinstance(combined, MultiPoint):
                    combined = combined.convex_hull

                bundles[next_bundle_id] = BundleClass(
                    bundle_id=next_bundle_id,
                    net_indices=sorted_nets,
                    type_signature=sig,
                    geometric_footprint=combined if isinstance(combined, Polygon) else net_footprints[p_idx],
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
                    # Compute combined footprint
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
