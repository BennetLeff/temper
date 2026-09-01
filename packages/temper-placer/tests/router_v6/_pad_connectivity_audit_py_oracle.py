"""Pinned pure-Python oracle for the pad endpoint/layer audit graph.

This file is intentionally standalone: it is a verbatim characterization of
the graph core before the Rust migration and must not import the production
audit module.  The differential suite feeds it the same primitive records as
``temper_geometry.pad_connectivity_audit_py``.
"""

from __future__ import annotations

from collections.abc import Sequence

ALL_LAYERS = "*"
_KICAD_NM_PER_MM = 1_000_000


class _UnionFind:
    def __init__(self) -> None:
        self._parent: dict[tuple[tuple[int, int], str], tuple[tuple[int, int], str]] = {}
        self._size: dict[tuple[tuple[int, int], str], int] = {}

    def _ensure(self, key):
        if key not in self._parent:
            self._parent[key] = key
            self._size[key] = 1

    def find(self, key):
        self._ensure(key)
        root = key
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[key] != root:
            self._parent[key], key = root, self._parent[key]
        return root

    def union(self, left, right):
        left_root, right_root = self.find(left), self.find(right)
        if left_root == right_root:
            return
        if self._size[left_root] < self._size[right_root]:
            left_root, right_root = right_root, left_root
        self._parent[right_root] = left_root
        self._size[left_root] += self._size[right_root]


def _cluster_key(point: tuple[float, float], tolerance_mm: float) -> tuple[int, int]:
    x = round(point[0] * _KICAD_NM_PER_MM) / _KICAD_NM_PER_MM
    y = round(point[1] * _KICAD_NM_PER_MM) / _KICAD_NM_PER_MM
    return (round(x / tolerance_mm), round(y / tolerance_mm))


def graph_verdict(
    pads: Sequence[tuple[float, float, str]],
    segments: Sequence[tuple[float, float, float, float, str]],
    vias: Sequence[tuple[float, float, Sequence[str]]],
    all_layers: Sequence[str] = (),
    tolerance_mm: float = 0.02,
    zone_layers: Sequence[str] = (),
) -> tuple[int, bool, bool, tuple[int, ...], tuple[str, ...], bool]:
    """Return the primitive verdict tuple consumed by the Rust kernel."""
    if len(pads) <= 1:
        return (len(pads), True, bool(segments or vias), (), (), False)

    uf = _UnionFind()

    def node(x: float, y: float, layer: str):
        return (_cluster_key((x, y), tolerance_mm), layer)

    for x1, y1, x2, y2, layer in segments:
        uf.union(node(x1, y1, layer), node(x2, y2, layer))

    layer_universe = tuple(all_layers) if all_layers else tuple(
        sorted({segment[4] for segment in segments} | {pad[2] for pad in pads if pad[2] != ALL_LAYERS})
    )
    for x, y, layers in vias:
        via_layers = tuple(layers) or layer_universe
        keys = [node(x, y, layer) for layer in via_layers]
        for key in keys[1:]:
            uf.union(keys[0], key)

    representatives = []
    for x, y, layer in pads:
        pad_layers = layer_universe or (ALL_LAYERS,) if layer == ALL_LAYERS else (layer,)
        keys = [node(x, y, pad_layer) for pad_layer in pad_layers]
        for key in keys[1:]:
            uf.union(keys[0], key)
        representatives.append(keys[0])

    roots = [uf.find(node) for node in representatives]
    counts: dict = {}
    for root in roots:
        counts[root] = counts.get(root, 0) + 1
    largest = max(counts.values()) if counts else 0
    majority = max(counts, key=counts.get) if counts and largest > 1 else None
    unreached = tuple(index for index, root in enumerate(roots) if majority is None or root != majority)
    zones = tuple(sorted(set(zone_layers)))
    zone_dependent = bool(zones) and bool(unreached) and all(
        pads[index][2] == ALL_LAYERS or pads[index][2] in zones for index in unreached
    )
    return (largest, largest == len(pads), bool(segments or vias), unreached, zones, zone_dependent)
