"""
Net Bundle Analyzer — partition nets into bundle equivalence classes.

Origin: U1 of docs/plans/2026-06-28-002-feat-net-bundling-lazy-grounding-plan.md

Two nets share a bundle class iff:
 1. Identical constraint-type signature: (net_class, trace_width, clearance,
    has_diff_pair, pin_layer_set).
 2. Geometric footprint overlap > 50% Jaccard index on skeleton edges.

References:
  - R1 (Bundle equivalence), R2 (Bundle manifest), R2.1 (Determinism)
  - KD1 (equivalence criteria), KD6 (diff pair singleton bundles)
  - OQ-R3 (Jaccard threshold initial = 0.5)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from shapely.geometry import MultiPoint, Point, Polygon


@dataclass(frozen=True)
class TypeSignature:
    """Constraint-type signature for bundle equivalence (R1)."""

    net_class: str
    trace_width: float
    clearance: float
    has_diff_pair: bool
    pin_layer_set: frozenset[str]


@dataclass(kw_only=True)
class BundleClass:
    """A single bundle equivalence class (R2)."""

    bundle_id: int
    net_indices: list[int]  # sorted by net index
    type_signature: TypeSignature
    geometric_footprint: Polygon
    constraint_types: frozenset[str]  # "safety", "performance", "aesthetic"
    is_diff_pair: bool = False


@dataclass
class BundleManifest:
    """Output of BundleAnalyzer.analyze() (R2)."""

    bundles: dict[int, BundleClass] = field(default_factory=dict)
    bundle_id_for_net: dict[int, int] = field(default_factory=dict)
    unbundled_net_indices: list[int] = field(default_factory=list)

    @property
    def bundle_count(self) -> int:
        return len(self.bundles)


class BundleAnalyzer:
    """Pre-partition nets into bundle equivalence classes.

    Consumes the netlist, channel skeletons, design rules, and diff pairs
    to produce a deterministic :class:`BundleManifest`.
    """

    def __init__(
        self,
        nets: list[Any],
        skeletons: dict[str, Any],
        design_rules: Any | None = None,
        diff_pairs: list[Any] | None = None,
        pcb: Any | None = None,
        jaccard_threshold: float = 0.5,
    ):
        self.nets = nets
        self.skeletons = skeletons
        self.design_rules = design_rules
        self.diff_pairs = diff_pairs or []
        self.pcb = pcb
        self.jaccard_threshold = jaccard_threshold

        self._diff_pair_nets: set[str] = set()
        for dp in self.diff_pairs:
            self._diff_pair_nets.add(dp.p_net)
            self._diff_pair_nets.add(dp.n_net)

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def analyze(self) -> BundleManifest:
        """Run the full bundle analysis and return a BundleManifest."""
        n = len(self.nets)
        if n == 0:
            return BundleManifest()

        type_signatures = [self._compute_type_signature(i) for i in range(n)]
        edge_covers = [self._compute_edge_cover(i) for i in range(n)]

        # Pre-group by type signature for efficient pairwise Jaccard.
        sig_groups: dict[TypeSignature, list[int]] = {}
        for i in range(n):
            sig = type_signatures[i]
            sig_groups.setdefault(sig, []).append(i)

        # Separate diff-pair nets into singleton (2-net) bundles (KD6).
        diff_pair_classes: list[tuple[int, int]] = []
        matched_diff_nets: set[int] = set()
        for dp in self.diff_pairs:
            p_idx = _find_net_index(self.nets, dp.p_net)
            n_idx = _find_net_index(self.nets, dp.n_net)
            if p_idx is not None and n_idx is not None:
                diff_pair_classes.append((p_idx, n_idx))
                matched_diff_nets.add(p_idx)
                matched_diff_nets.add(n_idx)

        # Partition remaining (non-diff-pair) nets within each type-signature
        # group by Jaccard overlap.
        bundle_id = 0
        bundles: dict[int, BundleClass] = {}
        bundle_id_for_net: dict[int, int] = {}

        # 1. Diff-pair singleton bundles (KD6).
        for p_idx, n_idx in sorted(diff_pair_classes, key=lambda x: x[0]):
            sig = type_signatures[p_idx]
            bundles[bundle_id] = BundleClass(
                bundle_id=bundle_id,
                net_indices=sorted([p_idx, n_idx]),
                type_signature=sig,
                geometric_footprint=self._footprint_for_union([p_idx, n_idx]),
                constraint_types=frozenset(["safety", "performance"]),
                is_diff_pair=True,
            )
            bundle_id_for_net[p_idx] = bundle_id
            bundle_id_for_net[n_idx] = bundle_id
            bundle_id += 1

        # 2. Non-diff-pair bundles via Jaccard clustering.
        for sig, indices in sorted(sig_groups.items(), key=lambda kv: min(kv[1])):
            eligible = [i for i in indices if i not in matched_diff_nets]
            if not eligible:
                continue

            clusters = _jaccard_cluster(eligible, edge_covers, self.jaccard_threshold)
            for cluster in clusters:
                cluster_sorted = sorted(cluster)
                cluster_sorted[0]
                bundles[bundle_id] = BundleClass(
                    bundle_id=bundle_id,
                    net_indices=cluster_sorted,
                    type_signature=sig,
                    geometric_footprint=self._footprint_for_union(cluster_sorted),
                    constraint_types=_classify_bundle_constraints(sig),
                    is_diff_pair=False,
                )
                for ni in cluster_sorted:
                    bundle_id_for_net[ni] = bundle_id
                bundle_id += 1

        unbundled = sorted(set(range(n)) - set(bundle_id_for_net.keys()))

        # Sort bundles by bundle_id (already assigned in increasing order of
        # first net index, which satisfies R2.1 determinism).
        return BundleManifest(
            bundles=dict(sorted(bundles.items())),
            bundle_id_for_net=bundle_id_for_net,
            unbundled_net_indices=unbundled,
        )

    # -----------------------------------------------------------------
    # Signature computation (R1)
    # -----------------------------------------------------------------

    def _compute_type_signature(self, net_idx: int) -> TypeSignature:
        net = self.nets[net_idx]
        net_class = _net_class(net)
        width = 0.2
        clearance = 0.2
        if self.design_rules is not None and hasattr(self.design_rules, "get_rules_for_net"):
            rule = self.design_rules.get_rules_for_net(net.name)
            width = rule.trace_width_mm
            clearance = rule.clearance_mm
        has_dp = net.name in self._diff_pair_nets
        pin_layers = self._pin_layer_set(net_idx)
        return TypeSignature(
            net_class=net_class,
            trace_width=round(width, 6),
            clearance=round(clearance, 6),
            has_diff_pair=has_dp,
            pin_layer_set=frozenset(pin_layers),
        )

    def _pin_layer_set(self, net_idx: int) -> set[str]:
        """Return the set of pin surface layers for this net."""
        layers: set[str] = set()
        net = self.nets[net_idx]
        if self.pcb is None:
            return layers
        comp_by_ref = {c.reference: c for c in getattr(self.pcb, "components", [])}
        for comp_ref, pin_name in getattr(net, "pins", []):
            comp = comp_by_ref.get(comp_ref)
            if comp is None:
                continue
            pin = comp.get_pin(pin_name) if hasattr(comp, "get_pin") else None
            if pin is not None:
                layer = getattr(pin, "layer", None)
                if layer:
                    layers.add(layer)
        return layers

    # -----------------------------------------------------------------
    # Geometric footprint computation (R1)
    # -----------------------------------------------------------------

    def _footprint_for_union(self, net_indices: list[int]) -> Polygon:
        """Convex hull of all pin positions across the given nets, expanded."""
        points: list[Point] = []
        for ni in net_indices:
            points.extend(self._net_pin_points(ni))
        if not points:
            return Polygon()
        hull = MultiPoint([(p.x, p.y) for p in points]).convex_hull
        if hull.is_empty:
            return Polygon()
        margin = self._median_edge_length()
        hull = hull.buffer(margin) if isinstance(hull, Point) else hull.buffer(margin)
        if not isinstance(hull, Polygon):
            hull = hull.convex_hull
        if not isinstance(hull, Polygon):
            return Polygon()
        return hull

    def _net_pin_points(self, net_idx: int) -> list[Point]:
        """Return list of Point geometries for a net's pin world positions."""
        points: list[Point] = []
        net = self.nets[net_idx]
        if self.pcb is None:
            return points
        comp_by_ref = {c.reference: c for c in getattr(self.pcb, "components", [])}
        for comp_ref, pin_name in getattr(net, "pins", []):
            comp = comp_by_ref.get(comp_ref)
            if comp is None:
                continue
            comp_pos = getattr(comp, "initial_position", None)
            if comp_pos is None:
                continue
            pin = comp.get_pin(pin_name) if hasattr(comp, "get_pin") else None
            local_pos = getattr(pin, "position", None) if pin is not None else None
            if local_pos is not None:
                points.append(Point(comp_pos[0] + local_pos[0], comp_pos[1] + local_pos[1]))
            else:
                points.append(Point(comp_pos[0], comp_pos[1]))
        return points

    def _median_edge_length(self) -> float:
        """Median channel edge length across all skeletons (for footprint margin)."""
        lengths: list[float] = []
        for skeleton in self.skeletons.values():
            for u, v in skeleton.graph.edges:
                lengths.append(((u[0] - v[0]) ** 2 + (u[1] - v[1]) ** 2) ** 0.5)
        if not lengths:
            return 10.0
        lengths.sort()
        mid = len(lengths) // 2
        return lengths[mid]

    def _compute_edge_cover(self, net_idx: int) -> frozenset[str]:
        """Return the set of skeleton edge IDs whose midpoints lie within
        the net's geometric footprint."""
        footprint = self._footprint_for_union([net_idx])
        if footprint.is_empty:
            return frozenset()
        edges: set[str] = set()
        for layer_name, skeleton in self.skeletons.items():
            for i, (u, v) in enumerate(skeleton.graph.edges):
                n1, n2 = sorted([u, v])
                edge_id = f"{layer_name}_E{i}_{n1}_{n2}"
                midpoint = Point((n1[0] + n2[0]) / 2, (n1[1] + n2[1]) / 2)
                if footprint.contains(midpoint):
                    edges.add(edge_id)
        return frozenset(edges)


# -----------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------

def _find_net_index(nets: list[Any], name: str) -> int | None:
    for i, net in enumerate(nets):
        if net.name == name:
            return i
    return None


def _net_class(net: Any) -> str:
    """Return one of 'ground', 'power', 'hv', 'signal' (R1 type-signature field)."""
    try:
        from temper_placer.router_v6.net_classification import classify_net_type

        return classify_net_type(net.name)
    except ImportError:
        return "signal"


def _classify_bundle_constraints(sig: TypeSignature) -> frozenset[str]:
    """Placeholder constraint classification (full logic in U2 / type_gating.py).

    Uses the fallback mapping from the plan (R3-R5):
      hv → Safety, power → Performance, ground → Safety, signal → Performance.
    """
    types: set[str] = set()
    if sig.net_class in ("ground", "hv"):
        types.add("safety")
    if sig.net_class in ("power", "signal"):
        types.add("performance")
    if sig.has_diff_pair:
        types.add("performance")
    types.add("safety")  # layer restrictions are always Safety
    return frozenset(types)


def _jaccard_edge_cover(
    a: frozenset[str], b: frozenset[str]
) -> float:
    """Jaccard index |A ∩ B| / |A ∪ B| (or 0.0 if both empty)."""
    if not a and not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    if union == 0:
        return 0.0
    return intersection / union


def _jaccard_cluster(
    indices: list[int],
    edge_covers: list[frozenset[str]],
    threshold: float,
) -> list[list[int]]:
    """Greedy clustering by Jaccard threshold within a type-signature group.

    Deterministic: sorts indices first, processes in sorted order.
    Returns list of clusters (each cluster is a list of net indices).
    """
    sorted_indices = sorted(indices)
    clusters: list[list[int]] = []
    assigned: set[int] = set()

    for i in sorted_indices:
        if i in assigned:
            continue
        cluster = [i]
        assigned.add(i)
        for j in sorted_indices:
            if j in assigned:
                continue
            # jaccard with EVERY member of the cluster (transitive overlap)
            if all(
                _jaccard_edge_cover(edge_covers[j], edge_covers[m]) > threshold
                for m in cluster
            ):
                cluster.append(j)
                assigned.add(j)
        clusters.append(cluster)

    return clusters
