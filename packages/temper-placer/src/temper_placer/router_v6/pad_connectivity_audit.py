"""Pad-connectivity verification: does a net's copper actually join its pads?

**Why this exists, and what it is not.** ``topology_copper_audit.py``
answers "does this net have ANY copper" (segment/via/zone exists with this
net's number attached). That is necessary but nowhere near sufficient: a
net can have segments, and a rising completion counter, while those
segments never touch the net's own pads at all.

That is not a hypothetical failure mode -- it happened, on this board, in
commit ``b39b382d15b25bd8d0f80e5fc2530489fab1d114``'s *rejected*
predecessor. That change picked a grid-backed layer for a tree-route edge
without checking it was actually the pad's own layer. Reported completion
rose 26.3% -> 41.6%, but it emitted 23,605 segments that never touched
their pad, and KiCad DRC's unconnected-item count got WORSE (396 -> 398),
not better. A segment/via counter and a "nets with copper" set both went
up while the board got less correct. This module is the check that would
have caught it: given a net's pads and its emitted copper, build the
copper-plus-pad connectivity graph and check every pad is actually in one
connected component -- not merely that copper with the right net number
exists somewhere on the board.

**Design.** ``check_net_pad_connectivity`` is the core, pure-data check:
no I/O, no parsing, takes plain pad/segment/via records and returns a
verdict. This is what a router (this spike's ``_astar_nlayer.py`` or, if
this were productionized, the real per-net driver) would call right after
producing a route, before ever trusting a completion counter.
``audit_pcb_file`` is a thin adapter that parses a written ``.kicad_pcb``
(pad positions via the existing, tested ``kicad_parser``; segment/via
blocks via the same paren-balanced technique ``topology_copper_audit.py``
already uses, applied independently here per that module's own stated
convention) and runs the core check per net -- this is what this spike
uses to audit its own measured production-board output.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from temper_placer.router_v6.topology_copper_audit import (
    _extract_top_level_blocks,
    net_number_to_name_map,
)

__all__ = [
    "CopperSegment",
    "CopperVia",
    "NetPad",
    "NetConnectivityResult",
    "check_net_pad_connectivity",
    "audit_pcb_file",
    "zone_layers_and_fill_stats",
    "find_pin_identity_pad_mismatches",
]

Point = tuple[float, float]

# Layer sentinel for a through-hole / all-layer pad or via: connects to
# every layer in the checker's layer universe, not just one named layer.
ALL_LAYERS = "*"


@dataclass(frozen=True)
class CopperSegment:
    """One net's routed trace segment: a same-layer line between two points."""

    p1: Point
    p2: Point
    layer: str


@dataclass(frozen=True)
class CopperVia:
    """One net's via: connects ``position`` across every layer it spans.

    ``layers=()`` means "spans every layer the checker is told about"
    (matches how vias in this codebase's occupancy-grid marking are
    treated -- ``astar_grid._mark_route_blocked`` blocks a via on every
    grid it has, not just its nominal start/end layer).

    ``_parse_segments_and_vias`` fills this from KiCad semantics: a via
    with a ``blind``/``buried``/``micro`` type token gets its declared
    layer pair; a via with NO type token is a THROUGH via and gets
    ``()`` -- the file format default is through, and a through via
    pierces every copper layer regardless of the declared pair.
    """

    position: Point
    layers: tuple[str, ...] = ()


@dataclass(frozen=True)
class NetPad:
    """One net's pad (or other physical terminal, e.g. an existing via)."""

    position: Point
    layer: str  # a specific copper layer name, or ALL_LAYERS for THT
    ref: str = ""  # "<component>.<pad number>", diagnostic only


@dataclass
class NetConnectivityResult:
    """Verdict for one net: are its pads actually joined by its copper?"""

    net_name: str
    pad_count: int
    pads_connected: int  # size of the largest copper-connected pad group
    fully_connected: bool  # every pad is in that one group
    has_any_copper: bool  # any segment/via exists for this net at all
    unreached_pads: tuple[NetPad, ...] = field(default_factory=tuple)
    # Layers on which this net has ANY zone block declared (outline or
    # filled -- see ``_parse_zones``). Diagnostic only; does not affect
    # ``fully_connected``/``pads_connected``, which remain a pure
    # segment+via+pad graph verdict.
    zone_layers: tuple[str, ...] = field(default_factory=tuple)
    # True when every one of this net's unreached pads sits on a layer
    # that has a zone declared for this net -- i.e. the segment/via graph
    # says "not connected", but a zone pour this audit cannot see (or
    # cannot see FILLED -- see ``_parse_zones``'s filled/unfilled count)
    # might be delivering that connection instead. This is a "cannot
    # measure" verdict, not a "connected" one: the audit does not attempt
    # point-in-polygon zone-fill analysis (thermal reliefs, clearance
    # cutouts, unfilled islands all make a naive "inside the outline"
    # check an active source of false confidence on a mains-voltage
    # board -- see this module's ``_parse_zones`` docstring).
    zone_dependent_unmeasured: bool = False

    @property
    def is_fake_completion(self) -> bool:
        """The exact b39b382d shape: copper exists for this net (a naive
        "has copper" check, or a segment/via counter, would call this net
        done or improved), but its own pads are not actually joined by
        that copper. True fake completion, not merely "incomplete".

        Deliberately UNCHANGED by zone dependence: this property answers
        "does the segment/via graph alone connect this net's pads", which
        is exactly what it always meant. Use ``category`` for the
        3-way connected/broken/zone_dependent_unmeasured partition a
        report should actually act on.
        """
        return self.has_any_copper and not self.fully_connected

    @property
    def category(self) -> str:
        """One of ``"connected"``, ``"zone_dependent_unmeasured"``, or
        ``"broken"`` -- the partition a completion report should use.
        A net cannot be honestly called "broken" (nor "connected") when
        every pad this audit failed to join has a zone declared on its
        own layer for this net: this audit has no visibility into zone
        fill geometry at all (see ``_parse_zones``), so that case is
        neither a confirmed pass nor a confirmed fail.
        """
        if self.fully_connected:
            return "connected"
        if self.zone_dependent_unmeasured:
            return "zone_dependent_unmeasured"
        return "broken"


class _UnionFind:
    """Union-find with path compression and union-by-size.

    Union-by-size only keeps trees shallow; it does NOT, by itself, make it
    safe to snapshot ``find(x)`` mid-construction and treat that snapshot
    as permanent. *Any* union (rank-based or not) can still relocate the
    root of an already-merged component -- ``union`` always reparents one
    of the two input roots, and a caller who read that root before the
    reparenting has a now-stale value. The only thing that makes a
    ``find()`` result trustworthy is calling it *after* every union that
    could touch that component has already happened. See
    ``check_net_pad_connectivity``'s two-pass pad handling, which is the
    actual fix for that failure mode (was: a per-pad root snapshot taken
    mid-loop, before later pads' own multi-layer unions had run -- verified
    against this board's ``thermal.j_fan-p1``, ``discharge.r_dis1a-p2``,
    and ``discharge.r_dis2a-p2`` nets, and pinned by this module's own
    regression tests).
    """

    __slots__ = ("_parent", "_size")

    def __init__(self) -> None:
        self._parent: dict = {}
        self._size: dict = {}

    def _ensure(self, x) -> None:
        if x not in self._parent:
            self._parent[x] = x
            self._size[x] = 1

    def find(self, x):
        self._ensure(x)
        root = x
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[x] != root:
            self._parent[x], x = root, self._parent[x]
        return root

    def union(self, a, b) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self._size[ra] < self._size[rb]:
            ra, rb = rb, ra
        self._parent[rb] = ra
        self._size[ra] += self._size[rb]


# KiCad's own file format and geometry engine store and quantise every
# board coordinate to 1 nanometre (1e-6 mm) resolution -- an mm value in a
# written .kicad_pcb never carries more than 6 decimal digits, and KiCad's
# internal units (EDA_IU) are integer nanometres. So on any real board, two
# coordinates that differ by less than half a nanometre are not merely
# "close" -- they are THE SAME point. This codebase's own pad-position
# math (footprint-transform composition: translate + rotate + parent
# offset, chained through several call sites) accumulates float error far
# below that floor -- observed ~1e-14 mm on this board's WDT_KICK pad
# (117.3925, 139.53000000000003) vs. its own via, written cleanly at
# (117.3925, 139.53) -- eight orders of magnitude under the 5e-7 mm/0.5nm
# resolution floor. Snapping to the nearest nanometre before dividing by
# tolerance_mm removes exactly that noise, and only that noise: two float
# representations of what KiCad considers one point become bit-identical
# before the tolerance-bucket rounding below, so they can no longer land on
# opposite sides of a round-half-to-even tie by sub-nanometre accident.
#
# This does NOT remove tie boundaries in general -- any fixed-decimal
# bucketing scheme has them, and two genuinely distinct nanometre-resolution
# points 0.01mm apart can still legitimately land in different
# ``tolerance_mm``-sized buckets. That is real ambiguity about which side
# of a grid line a point falls on, not a bug. What this fixes is only the
# case where the SAME physical point, reconstructed via two different
# float code paths, disagreed with itself about which bucket it was in.
_KICAD_NM_PER_MM = 1_000_000


def _snap_to_kicad_nm(value: float) -> float:
    return round(value * _KICAD_NM_PER_MM) / _KICAD_NM_PER_MM


def _cluster_key(point: Point, tolerance_mm: float) -> tuple[int, int]:
    """Snap a world point onto a tolerance-sized bucket.

    Two points within ``tolerance_mm`` of a shared bucket boundary collapse
    to the same key -- deliberately coarse (default 0.02mm, well under any
    trace width on this board) so float noise from grid quantization never
    splits a real, physically-touching connection into two nodes. This
    mirrors ``astar_core.grid_quantization_tolerance``'s reasoning without
    depending on any specific grid's cell size, since this module runs
    after routing, on written board geometry, independent of grid pitch.

    The coordinates are first snapped to KiCad's own 1nm resolution
    (``_snap_to_kicad_nm``) so that sub-nanometre float noise from this
    codebase's own transform math can never push a point across a
    ``round()`` tie boundary that the point's "true" (nanometre-resolution)
    value does not actually sit on.
    """
    x = _snap_to_kicad_nm(point[0])
    y = _snap_to_kicad_nm(point[1])
    return (round(x / tolerance_mm), round(y / tolerance_mm))


def check_net_pad_connectivity(
    net_name: str,
    pads: Sequence[NetPad],
    segments: Sequence[CopperSegment],
    vias: Sequence[CopperVia],
    all_layers: Sequence[str] = (),
    tolerance_mm: float = 0.02,
    zone_layers: Sequence[str] = (),
) -> NetConnectivityResult:
    """Does this net's copper actually connect all of its own pads?

    A net with 0 or 1 pads is trivially connected (nothing to join).
    Otherwise: build a union-find over (snapped-point, layer) nodes, union
    every segment's two endpoints (same layer only -- a segment never
    changes layer), union every via's position across the layers it spans,
    then union each pad's own node(s) in. The verdict is
    ``fully_connected = (largest pad-containing component's pad count ==
    total pad count)`` -- every pad must land in the SAME component, not
    merely "some component with copper in it."

    ``zone_layers`` (optional, pure data -- same design as everything else
    here: caller parses the board, this function only reasons about
    already-extracted facts) lists the layers on which this net has ANY
    zone declared. It never changes ``fully_connected``/``pads_connected``
    -- those remain a pure segment+via+pad-graph verdict. It only sets
    ``zone_dependent_unmeasured`` when every pad the graph failed to reach
    sits on a layer with a zone for this net: see
    ``NetConnectivityResult.category``.
    """
    if len(pads) <= 1:
        return NetConnectivityResult(
            net_name=net_name,
            pad_count=len(pads),
            pads_connected=len(pads),
            fully_connected=True,
            has_any_copper=bool(segments or vias),
        )

    uf = _UnionFind()

    def node(point: Point, layer: str):
        return (_cluster_key(point, tolerance_mm), layer)

    for seg in segments:
        uf.union(node(seg.p1, seg.layer), node(seg.p2, seg.layer))

    layer_universe = tuple(all_layers) if all_layers else tuple(
        sorted({s.layer for s in segments} | {p.layer for p in pads if p.layer != ALL_LAYERS})
    )

    for via in vias:
        via_layers = via.layers or layer_universe
        keys = [node(via.position, layer) for layer in via_layers]
        for k in keys[1:]:
            uf.union(keys[0], k)

    def pad_nodes(pad: NetPad):
        if pad.layer == ALL_LAYERS:
            layers = layer_universe or (ALL_LAYERS,)
            return [node(pad.position, layer) for layer in layers]
        return [node(pad.position, pad.layer)]

    # First pass: union each pad's own multi-layer nodes together (a THT
    # pad's barrel joins every layer it spans) -- but do NOT read back a
    # root yet. ``_UnionFind.union`` always reparents one of its two input
    # roots, so a root read here could still be silently relocated by a
    # LATER pad's own multi-layer union (this is the stale-root bug: see
    # ``_UnionFind``'s docstring). Collect each pad's representative node
    # instead of its root.
    pad_repr_nodes = []
    for pad in pads:
        nodes = pad_nodes(pad)
        for extra in nodes[1:]:
            uf.union(nodes[0], extra)
        pad_repr_nodes.append(nodes[0])

    # Second, separate pass: every union that exists (segments, vias, and
    # every pad's own multi-layer expansion) is now complete, so no
    # further union can happen and no root read from here on can go stale.
    pad_roots = [uf.find(repr_node) for repr_node in pad_repr_nodes]

    counts: dict = {}
    for root in pad_roots:
        counts[root] = counts.get(root, 0) + 1
    largest = max(counts.values()) if counts else 0
    # Only treat a component as "the" majority when it actually joins more
    # than one pad -- if every pad is its own isolated singleton (largest
    # == 1), no pad is genuinely connected to any other, and an arbitrary
    # tie-broken "majority" pick would wrongly exempt one pad from
    # unreached_pads even though it reaches nobody either.
    majority_root = max(counts, key=counts.get) if counts and largest > 1 else None
    unreached = tuple(
        pad for pad, root in zip(pads, pad_roots) if majority_root is None or root != majority_root
    )

    zone_layer_set = set(zone_layers)

    def _zone_could_reach(pad: NetPad) -> bool:
        if not zone_layer_set:
            return False
        # A through-hole pad's barrel touches every copper layer, so a
        # zone on ANY layer is a candidate; an SMD pad only benefits from
        # a zone on its own specific layer.
        return pad.layer == ALL_LAYERS or pad.layer in zone_layer_set

    zone_dependent_unmeasured = bool(unreached) and all(_zone_could_reach(p) for p in unreached)

    return NetConnectivityResult(
        net_name=net_name,
        pad_count=len(pads),
        pads_connected=largest,
        fully_connected=(largest == len(pads)),
        has_any_copper=bool(segments or vias),
        unreached_pads=unreached,
        zone_layers=tuple(sorted(zone_layer_set)),
        zone_dependent_unmeasured=zone_dependent_unmeasured,
    )


# ---------------------------------------------------------------------------
# Real-board adapter: parse a written .kicad_pcb and audit every net on it.
# ---------------------------------------------------------------------------

_NET_ATTR_RE = re.compile(r"\(net\s+(\d+)\)")
_SEGMENT_START_RE = re.compile(r"\(start\s+([-\d.]+)\s+([-\d.]+)\)")
_SEGMENT_END_RE = re.compile(r"\(end\s+([-\d.]+)\s+([-\d.]+)\)")
_LAYER_RE = re.compile(r'\(layer\s+"([^"]+)"\)')
_VIA_AT_RE = re.compile(r"\(at\s+([-\d.]+)\s+([-\d.]+)\)")
_VIA_LAYERS_RE = re.compile(r'\(layers\s+((?:"[^"]+"\s*)+)\)')
# KiCad's via type token is a bare `blind`/`buried`/`micro` right after
# `(via` (pcb_io_kicad_sexpr_parser.cpp parsePCB_VIA). Absent -> THROUGH.
_VIA_TYPE_RE = re.compile(r"\(via\s+(blind|buried|micro)\b")
_LAYER_NAME_RE = re.compile(r'"([^"]+)"')


def _parse_segments_and_vias(
    pcb_content: str,
) -> tuple[dict[str, list[CopperSegment]], dict[str, list[CopperVia]]]:
    num_to_name = net_number_to_name_map(pcb_content)
    segs_by_net: dict[str, list[CopperSegment]] = {}
    for block in _extract_top_level_blocks(pcb_content, ("segment",)):
        net_m = _NET_ATTR_RE.search(block)
        start_m = _SEGMENT_START_RE.search(block)
        end_m = _SEGMENT_END_RE.search(block)
        layer_m = _LAYER_RE.search(block)
        if not (net_m and start_m and end_m and layer_m):
            continue
        name = num_to_name.get(int(net_m.group(1)))
        if not name:
            continue
        segs_by_net.setdefault(name, []).append(
            CopperSegment(
                p1=(float(start_m.group(1)), float(start_m.group(2))),
                p2=(float(end_m.group(1)), float(end_m.group(2))),
                layer=layer_m.group(1),
            )
        )

    vias_by_net: dict[str, list[CopperVia]] = {}
    for block in _extract_top_level_blocks(pcb_content, ("via",)):
        net_m = _NET_ATTR_RE.search(block)
        at_m = _VIA_AT_RE.search(block)
        if not (net_m and at_m):
            continue
        name = num_to_name.get(int(net_m.group(1)))
        if not name:
            continue
        layers_m = _VIA_LAYERS_RE.search(block)
        type_m = _VIA_TYPE_RE.search(block)
        if type_m:
            # A typed via (blind / buried / micro) connects exactly its
            # declared layer pair -- nothing outside it.
            layers = tuple(_LAYER_NAME_RE.findall(layers_m.group(1))) if layers_m else ()
        else:
            # No type token: KiCad treats the via as THROUGH -- it pierces
            # every copper layer regardless of the declared pair (which is
            # only the stack extent, e.g. F.Cu/B.Cu). ``()`` is the
            # CopperVia convention for "spans every layer the checker knows
            # about" (see CopperVia's docstring).
            layers = ()
        vias_by_net.setdefault(name, []).append(
            CopperVia(position=(float(at_m.group(1)), float(at_m.group(2))), layers=layers)
        )
    return segs_by_net, vias_by_net


_ZONE_LAYERS_RE = re.compile(r'\(layers\s+((?:"[^"]+"\s*)+)\)')


def _parse_zones(pcb_content: str) -> tuple[dict[str, set[str]], int, int]:
    """Which net/layer combinations have a zone declared, and how many of
    this file's zone blocks actually carry computed fill geometry.

    **What this deliberately does NOT do: determine whether any pad is
    actually connected by a zone.** A zone's ``(polygon (pts ...))`` block
    is the zone's drawn OUTLINE (in this codebase's own zone-emission
    writer, ``zone_emission.py``, it is a convex-hull-around-pads
    approximation of where a pour is *intended* -- see that module's
    ``_convex_hull_from_positions``) -- it is not copper. Only a zone's
    ``filled_polygon`` sub-block, written by KiCad's own zone-fill engine
    (or a correct reimplementation honouring clearance cutouts, thermal
    relief spokes, and unfilled islands) after a fill pass, is real,
    DRC-visible copper.

    This function counts both cases (``n_filled_zone_blocks`` /
    ``n_unfilled_zone_blocks``) so a caller can report which situation it's
    actually in, rather than silently treating "has a zone block" as "has
    copper". As measured on this project's own written boards
    (``pcb/temper.kicad_pcb`` and the ``fix/router-nlayer-routing``
    branch's ``temper_routed_nlayer.kicad_pcb``): ZERO zone blocks in
    either file carry ``filled_polygon`` data -- this codebase's zone
    writer never runs a fill pass, so even a correct point-in-polygon
    implementation would have nothing to test against on those files
    today. A net with a zone declared but the file carrying no fill data
    at all is not "probably connected"; it is unmeasured in the strongest
    sense -- the geometry a real check needs was never computed.
    """
    num_to_name = net_number_to_name_map(pcb_content)
    zone_layers: dict[str, set[str]] = {}
    n_filled = 0
    n_unfilled = 0
    for block in _extract_top_level_blocks(pcb_content, ("zone",)):
        net_m = _NET_ATTR_RE.search(block)
        if net_m:
            name = num_to_name.get(int(net_m.group(1)))
            if name:
                layers: set[str] = set()
                layer_m = _LAYER_RE.search(block)
                if layer_m:
                    layers.add(layer_m.group(1))
                layers_m = _ZONE_LAYERS_RE.search(block)
                if layers_m:
                    layers.update(_LAYER_NAME_RE.findall(layers_m.group(1)))
                if layers:
                    zone_layers.setdefault(name, set()).update(layers)
        if "filled_polygon" in block:
            n_filled += 1
        else:
            n_unfilled += 1
    return zone_layers, n_filled, n_unfilled


def _pads_by_net(pcb) -> dict[str, list[NetPad]]:
    from temper_placer.core.pin_geometry import pin_world_layer, pin_world_position

    pads: dict[str, list[NetPad]] = {}
    for comp in pcb.components:
        if not hasattr(comp, "pins"):
            continue
        for pin in comp.pins:
            if not pin.net:
                continue
            raw_layer = pin_world_layer(pin)
            is_through = bool(getattr(pin, "is_pth", False)) or raw_layer in ("all", "*.Cu") or (
                isinstance(raw_layer, str) and "Through" in raw_layer
            )
            layer = ALL_LAYERS if is_through else raw_layer
            pos = pin_world_position(pin, comp)
            pad_number = getattr(pin, "number", None) or getattr(pin, "name", "?")
            pads.setdefault(pin.net, []).append(
                NetPad(position=pos, layer=layer, ref=f"{comp.ref}.{pad_number}")
            )
    return pads


def zone_layers_and_fill_stats(pcb_path: Path) -> tuple[dict[str, set[str]], int, int]:
    """Public file-reading wrapper around ``_parse_zones`` -- for a caller
    (e.g. a completion report) that wants the zone/fill facts
    ``audit_pcb_file`` uses internally, without re-parsing the file.
    Returns ``(zone_layers_by_net, n_filled_zone_blocks,
    n_unfilled_zone_blocks)``; see ``_parse_zones`` for exactly what each
    means and does not mean.
    """
    return _parse_zones(pcb_path.read_text())


def audit_pcb_file(
    pcb_path: Path,
    *,
    tolerance_mm: float = 0.02,
) -> dict[str, NetConnectivityResult]:
    """Parse a written ``.kicad_pcb`` and run ``check_net_pad_connectivity``
    for every net that has at least one pad.

    Pad positions come from the existing, tested ``kicad_parser`` /
    ``pin_world_position`` (the same canonical pad-position math the
    router itself uses for pad unblocking) -- not re-derived footprint
    transform math. Segment/via geometry is parsed directly from the
    written file's own paren-balanced blocks, independent of
    ``topology_copper_audit`` (only its block-extraction helper and
    net-number map are reused, per that module's own stated convention of
    applying the same technique independently rather than sharing mutable
    state).
    """
    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6

    pcb = parse_kicad_pcb_v6(pcb_path)
    content = pcb_path.read_text()

    pads_by_net = _pads_by_net(pcb)
    segs_by_net, vias_by_net = _parse_segments_and_vias(content)
    zone_layers_by_net, _n_filled_zones, _n_unfilled_zones = _parse_zones(content)
    all_layers = sorted({s.layer for segs in segs_by_net.values() for s in segs})

    results: dict[str, NetConnectivityResult] = {}
    for net_name, pads in pads_by_net.items():
        results[net_name] = check_net_pad_connectivity(
            net_name,
            pads,
            segs_by_net.get(net_name, []),
            vias_by_net.get(net_name, []),
            all_layers=all_layers,
            tolerance_mm=tolerance_mm,
            zone_layers=tuple(zone_layers_by_net.get(net_name, ())),
        )
    return results


def find_pin_identity_pad_mismatches(
    net_pins: dict[str, Sequence[tuple[str, str]]],
    audit_results: dict[str, NetConnectivityResult],
) -> list[str]:
    """The accounting guard: nets where a ``(component_ref, pin_name)``
    identity view of a net's pins disagrees with the board's REAL physical
    pad count.

    **The invariant.** More than one call site in this codebase has used
    ``(component_ref, pin_name)`` tuple identity as a stand-in for
    "physical pad identity" -- most concretely, treating a net whose pin
    list collapses to a single distinct ``(ref, name)`` tuple (``len(set(
    net.pins)) <= 1``) as having at most one thing to connect. That is
    false whenever a footprint fabricates more than one physical pad under
    the same pad number/name -- a real, documented pattern on this board
    (K2/K3, ``temper:Relay_SPDT_Schrack-RT314012``: pads "1"/"3"/"4" are
    each two physical solder holes 7.5mm apart, for 16A current sharing).
    ``discharge.k_dis1-no``/``discharge.k_dis2-no`` (``pins == [('K2',
    '3'), ('K2', '3')]`` / ``[('K3', '3'), ('K3', '3')]``) are the measured
    real example: this module's own ground-truth pad extraction (parsed
    directly off each component's distinct physical pads, no name-based
    lookup) gives ``pad_count == 2`` for both, at two distinct coordinates.
    A pin-identity view that collapses them to "1 distinct pin, nothing to
    connect" is exactly the mistake that let
    ``_pipeline_grid._net_pad_positions`` (pre-fix) hand Stage 4's A* two
    IDENTICAL coordinates instead of the real two, and let
    ``topology_copper_audit.is_self_referential_net`` (pre-fix) certify
    the resulting no-copper net as "legitimately needs none" -- together,
    a silent, false "this net is fine" that produced a genuinely
    unconnected net with a "routed successfully" log line and no failure
    record anywhere.

    Args:
        net_pins: net name -> its ``[(component_ref, pin_name), ...]``
            pin list, as the router/netlist sees it (``Net.pins``).
        audit_results: net name -> :class:`NetConnectivityResult`, the
            REAL, ground-truth pad count/connectivity for the same net
            (from :func:`audit_pcb_file` against the actual board file --
            never re-derived from ``net_pins`` itself, which is exactly
            the point: this compares two INDEPENDENT sources).

    Returns:
        Sorted net names where the pin-identity view says "<=1 distinct
        pin" but the real board says "more than one physical pad" --
        every one of these is either a genuine collapse defect (fix the
        pin-resolution code path that produced ``net_pins``) or a naming
        coincidence that needs an explicit, reasoned exception -- never a
        silent pass.
    """
    mismatches: list[str] = []
    for name, pins in net_pins.items():
        pins = list(pins)
        if not pins:
            continue
        distinct_pins = len(set(pins))
        result = audit_results.get(name)
        if result is None:
            continue
        if distinct_pins <= 1 and result.pad_count > 1:
            mismatches.append(name)
    return sorted(mismatches)
