"""Pinned pure-Python BundleAnalyzer oracle.

This is the pre-migration BundleAnalyzer from commit 8fd69df1 (the parent of
the Rust orchestration port), kept as a test-only reference.  It intentionally
does not import ``temper_geometry`` or any production analyzer/classifier:
manifest grouping, classification, edge coverage, and ordering all stay
independent of the Rust implementation under test.
"""

from __future__ import annotations

import contextlib
import re
from dataclasses import dataclass, field
from typing import Any

from shapely.geometry import MultiPoint, Point, Polygon


@dataclass(frozen=True)
class TypeSignature:
    safety_category: str | None
    net_class: str
    has_diff_pair: bool


@dataclass
class BundleClass:
    bundle_id: int
    net_indices: list[int]
    type_signature: TypeSignature
    geometric_footprint: Polygon
    constraint_types: frozenset[str]
    is_diff_pair: bool


@dataclass
class BundleManifest:
    bundles: dict[int, BundleClass] = field(default_factory=dict)
    bundle_id_for_net: dict[int, int] = field(default_factory=dict)
    unbundled_net_indices: list[int] = field(default_factory=list)

    @property
    def bundle_count(self) -> int:
        return len(self.bundles)

    def is_bundled(self, net_idx: int) -> bool:
        return net_idx in self.bundle_id_for_net


# These are the router_v6 patterns at the pinned baseline.  Keep the matcher
# here rather than calling router_v6.net_classification: that module is now a
# Rust adapter, and an oracle that calls it would share the decision under test.
_GROUND_NET_PATTERNS = ("GND", "PGND", "CGND", "AGND", "DGND", "VSS")
_POWER_NET_PATTERNS = (
    "+3V3", "+5V", "+12V", "+15V", "VCC", "VDD", "VBUS",
    "+340V", "DC_BUS", "PWR_RTN", "V_BUS",
)
_HV_NET_PATTERNS = ("AC_L", "AC_N", "PE", "DC_BUS+", "DC_BUS-", "SW_NODE")


def _matches_any(name: str, patterns: tuple[str, ...]) -> bool:
    upper = name.upper()
    for pattern in patterns:
        escaped = re.escape(pattern)
        if pattern and not pattern[-1].isalnum():
            if re.search(rf"(?:^|[_-]){escaped}", upper):
                return True
        elif re.search(rf"(?:^|[_-]){escaped}(?:$|[\d_-])", upper):
            return True
    return False


def _classify_net_type(name: str, single_layer_mode: bool) -> str:
    if single_layer_mode:
        return "signal"
    if _matches_any(name, _GROUND_NET_PATTERNS):
        return "ground"
    if _matches_any(name, _POWER_NET_PATTERNS) or name.upper().startswith("+"):
        return "power"
    if _matches_any(name, _HV_NET_PATTERNS):
        return "hv"
    return "signal"


class BundleAnalyzer:
    """Standalone pre-migration orchestration and its pure-Python seams."""

    def __init__(
        self,
        nets: list,
        skeletons: dict[str, Any],
        design_rules: Any | None = None,
        diff_pairs: list | None = None,
        pcb: Any | None = None,
        jaccard_threshold: float = 0.5,
        single_layer_mode: bool = False,
    ):
        self.nets = nets
        self.skeletons = skeletons
        self.design_rules = design_rules
        self.diff_pairs = diff_pairs or []
        self.pcb = pcb
        self.jaccard_threshold = jaccard_threshold
        self.single_layer_mode = single_layer_mode
        self._net_to_idx = {net.name: i for i, net in enumerate(nets)}
        self._diff_pair_net_names: set[str] = set()
        for dp in self.diff_pairs:
            self._diff_pair_net_names.add(dp.p_net)
            self._diff_pair_net_names.add(dp.n_net)
        self._median_edge_length = self._compute_median_edge_length()

    def _compute_median_edge_length(self) -> float:
        lengths = []
        for skeleton in self.skeletons.values():
            graph = skeleton.graph
            if hasattr(graph, "edges_with_data"):
                edges = graph.edges_with_data()
            else:
                edges = graph.edges(data=True)
            for _u, _v, data in edges:
                lengths.append(data.get("weight", 1.0))
        if not lengths:
            return 10.0
        lengths.sort()
        mid = len(lengths) // 2
        return lengths[mid] if len(lengths) % 2 else (lengths[mid - 1] + lengths[mid]) / 2.0

    def _net_pad_positions(self, net) -> list[tuple[float, float]]:
        positions: list[tuple[float, float]] = []
        if not self.pcb:
            return positions
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
            positions.append((float(comp_pos[0]) + float(px), float(comp_pos[1]) + float(py)))
        return positions

    def _compute_geometric_footprint(self, net) -> Polygon:
        positions = self._net_pad_positions(net)
        if len(positions) < 2:
            if positions:
                cx, cy = positions[0]
                m = self._median_edge_length
                return Polygon([(cx - m, cy - m), (cx + m, cy - m),
                                (cx + m, cy + m), (cx - m, cy + m)])
            return Polygon()
        if len(positions) == 2:
            (x1, y1), (x2, y2) = positions
            margin = self._median_edge_length
            return Polygon([(min(x1, x2) - margin, min(y1, y2) - margin),
                            (max(x1, x2) + margin, min(y1, y2) - margin),
                            (max(x1, x2) + margin, max(y1, y2) + margin),
                            (min(x1, x2) - margin, max(y1, y2) + margin)])
        hull = MultiPoint(positions).convex_hull
        return hull.buffer(self._median_edge_length) if isinstance(hull, Polygon) else Polygon()

    def _compute_covered_edges(self, footprint: Polygon) -> frozenset[str]:
        edges: set[str] = set()
        for layer_name, skeleton in self.skeletons.items():
            for i, (_u, _v) in enumerate(skeleton.graph.edges):
                n1, n2 = sorted([_u, _v])
                edge_id = f"{layer_name}_E{i}_{n1}_{n2}"
                try:
                    if footprint.contains(Point((n1[0] + n2[0]) / 2.0, (n1[1] + n2[1]) / 2.0)):
                        edges.add(edge_id)
                except Exception:
                    pass
        return frozenset(edges)

    @staticmethod
    def _jaccard(a: frozenset, b: frozenset) -> float:
        if not a and not b:
            return 1.0
        union = len(a | b)
        return len(a & b) / union if union else 0.0

    def _compute_type_signature(self, net) -> TypeSignature:
        safety_category: str | None = None
        if self.design_rules:
            rule = self.design_rules.get_rules_for_net(net.name)
            safety_category = getattr(rule, "safety_category", None)
        return TypeSignature(
            safety_category=safety_category,
            net_class=_classify_net_type(net.name, self.single_layer_mode),
            has_diff_pair=net.name in self._diff_pair_net_names,
        )

    def analyze(self) -> BundleManifest:
        """Run the pinned pre-migration manifest orchestration."""
        if not self.nets:
            return BundleManifest()

        net_signatures: list[TypeSignature] = []
        net_edge_covers: list[frozenset[str]] = []
        net_footprints: list[Polygon] = []
        for net in self.nets:
            sig = self._compute_type_signature(net)
            net_signatures.append(sig)
            footprint = self._compute_geometric_footprint(net)
            net_footprints.append(footprint)
            net_edge_covers.append(self._compute_covered_edges(footprint))

        sig_groups: dict[TypeSignature, list[int]] = {}
        for i, sig in enumerate(net_signatures):
            sig_groups.setdefault(sig, []).append(i)

        bundles: dict[int, BundleClass] = {}
        bundle_id_for_net: dict[int, int] = {}
        unbundled: list[int] = []
        next_bundle_id = 0

        for sig, net_indices in sig_groups.items():
            if len(net_indices) == 1:
                unbundled.append(net_indices[0])
                continue

            diff_pair_nets = {
                i for i in net_indices if self.nets[i].name in self._diff_pair_net_names
            }
            remaining_diff = set(diff_pair_nets)
            remaining_non_diff = [i for i in net_indices if i not in diff_pair_nets]
            paired_diff_nets: list[tuple[int, int]] = []
            matched_bases: set[str] = set()
            for dp in self.diff_pairs:
                if dp.base_name in matched_bases:
                    continue
                p_idx = self._net_to_idx.get(dp.p_net)
                n_idx = self._net_to_idx.get(dp.n_net)
                if (p_idx is not None and n_idx is not None and
                        p_idx in remaining_diff and n_idx in remaining_diff):
                    paired_diff_nets.append((p_idx, n_idx))
                    remaining_diff.discard(p_idx)
                    remaining_diff.discard(n_idx)
                    matched_bases.add(dp.base_name)

            for p_idx, n_idx in paired_diff_nets:
                sorted_nets = sorted([p_idx, n_idx])
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
                for i in sorted_nets:
                    bundle_id_for_net[i] = next_bundle_id
                next_bundle_id += 1

            remaining_non_diff.extend(remaining_diff)
            remaining_non_diff.sort()
            if not remaining_non_diff:
                continue

            adjacency: dict[int, set[int]] = {i: set() for i in remaining_non_diff}
            for left in range(len(remaining_non_diff)):
                for right in range(left + 1, len(remaining_non_diff)):
                    a, b = remaining_non_diff[left], remaining_non_diff[right]
                    if self._jaccard(net_edge_covers[a], net_edge_covers[b]) > self.jaccard_threshold:
                        adjacency[a].add(b)
                        adjacency[b].add(a)

            visited: set[int] = set()
            for start in remaining_non_diff:
                if start in visited:
                    continue
                component: list[int] = []
                stack = [start]
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
                    continue
                combined_fp = None
                for i in component:
                    fp = net_footprints[i]
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
                for i in component:
                    bundle_id_for_net[i] = next_bundle_id
                next_bundle_id += 1

        unbundled.sort()
        return BundleManifest(
            bundles={i: bundles[i] for i in sorted(bundles)},
            bundle_id_for_net=dict(sorted(bundle_id_for_net.items())),
            unbundled_net_indices=unbundled,
        )
