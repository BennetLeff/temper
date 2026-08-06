#!/usr/bin/env python3
"""Freeform (non-straight) mains<->SELV barrier feasibility on the committed placement.

Why this exists
---------------
``scripts/check_isolation_keepout.py`` fails closed on ``origin/main``: no
``MAINS_SELV_ISOLATION_BARRIER`` keepout exists. Two prior probes answered
"can a barrier be drawn?" only for *straight* corridors:

  - ``docs/evidence/2026-07-28-isolation-keepout.md`` -- exhaustive search over
    every axis-aligned split and every straight-line orientation: best case
    still misclassifies 90/318 pads.
  - ``docs/evidence/2026-08-01-isolation-barrier-feasibility{,-experiment}.md``
    (PR #563) -- CP-SAT corridor *re-placement* at 8.0mm, both orientations,
    +-25mm budget: NO-GO.

PR #565 observed, correctly, that the gate requires edge-to-edge partition and
exactly-two-regions but **not straightness**, so a bending / boundary-following
corridor is admissible and was never tested. This script settles that larger
question, for the *committed placement* (no component moves).

Three parts:

PART A -- admissibility probe (synthetic boards, the gate's own ``run()``):
  does check 4 really accept a non-convex, bending, boundary-following keepout?
  Three synthetic fixtures, each a strictly harder shape than the last.

PART B -- shape-independent feasibility on the real board.

  The argument, stated so the verdict does not depend on any search heuristic:

  Let ``C`` be the union of all copper on all layers (the barrier must span
  every copper layer -- check 1 -- so copper on *any* layer obstructs it), and
  let ``F`` be the copper-free region. A conforming barrier ``B`` satisfies:

    (i)  ``B subset F``                      -- check 5, no intrusion
    (ii) ``B`` is >= 8.0mm wide everywhere   -- check 3's stated contract,
         formalised the standard way: ``B`` is a union of discs of radius
         ``MIN_BARRIER_WIDTH_MM/2`` (every point of ``B`` lies in an 8mm-wide
         disc that is itself entirely inside ``B``).

  Every such disc lies in ``F``, so every such disc lies in
  ``O := opening(F, r) = (F erode r) dilate r`` -- the union of ALL
  8mm-wide-everywhere copper-free regions. Hence ``B subset O`` for *every*
  conforming barrier, of every shape: straight, bent, serpentine,
  boundary-following, multi-lobed, or leaving and re-entering the outline.

  Therefore ``board \\ O subset board \\ B``. If two pads lie in the SAME
  connected component of ``board \\ O``, that component is a connected subset
  of ``board \\ B``, so those two pads are on the SAME side of every conforming
  barrier. If one is HV and the other SELV, check 6 fails for every conforming
  barrier -> **no conforming barrier exists, of any shape**.

  This is a necessary condition, computed once, with no search over candidate
  polygons. It is conservative in the safe direction: the ambient is the board
  outline *expanded*, so barriers that leave and re-enter the board are
  allowed; connected components are taken with Shapely's decomposition, which
  splits point-touching regions apart, making "same component" harder to
  trigger, not easier.

PART C -- HV-side connectivity. Checks 4 and 6 together demand ONE region
  holding every HV copper pad, so the HV side must be connected. Part C computes
  the most permissive space that side could occupy and reports whether the HV
  copper pads fall into one component or several. See _part_c for the argument.

Obstacle models, isolating what would have to change:
  as-routed  -- traces + vias + pads + copper pours (the board as committed)
  reroutable -- pads only (assume a full re-route; placement unchanged), under
                both the gate's circumscribing-circle pad model and exact
                rotated pad outlines

A half-width sweep (r = 4.0 down to 0.25mm) quantifies how far the required
separation would have to fall before the placement admits *any* barrier --
recorded as evidence, NOT as a proposal to lower MIN_BARRIER_WIDTH_MM (8.0mm
is a creepage figure for the voltage/pollution class, not a tuning knob).

Usage:
  uv run --no-sync python docs/evidence/2026-08-04-isolation-barrier-freeform-corridor.py
"""

# provenance: commit=838096820b30ca3999aaa76fffa9ea736c6c89a0 dirty=false

from __future__ import annotations

import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from check_isolation_keepout import (  # noqa: E402
    BARRIER_ZONE_NAME,
    MIN_BARRIER_WIDTH_MM,
    BoardData,
    Manifest,
    PadInstance,
    _rotate,
    load_board,
    load_manifest,
    run,
)

BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"
MANIFEST = REPO_ROOT / "elec" / "domain_manifest.yaml"
PROVENANCE_COMMIT = "838096820b30ca3999aaa76fffa9ea736c6c89a0"

# Circle approximation for every buffer: 64 segments/quadrant. Erosion with a
# vertex-on-circle polygon under-cuts slightly (offset < r between vertices),
# which makes O marginally LARGER, i.e. errs toward "a barrier might exist" --
# the safe direction for a necessary condition.
QUAD_SEGS = 64
HALF_WIDTH_MM = MIN_BARRIER_WIDTH_MM / 2.0


# ---------------------------------------------------------------------------
# PART A -- does check 4 admit a non-convex / boundary-following keepout?
# ---------------------------------------------------------------------------


def _synthetic_probe(tmp_dir: Path) -> list[tuple[str, str, list[str]]]:
    """Run the REAL gate over synthetic boards whose barrier is deliberately
    non-straight. Returns [(shape_name, state, [violation checks]), ...]."""
    from kiutils.board import Board, LayerToken
    from kiutils.footprint import Footprint, Pad
    from kiutils.items.brditems import Segment
    from kiutils.items.common import Net, Position
    from kiutils.items.gritems import GrPoly
    from kiutils.items.zones import Hatch, KeepoutSettings, Zone, ZonePolygon
    from shapely.geometry import LineString

    copper_layers = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]

    manifest_path = tmp_dir / "manifest.yaml"
    manifest_path.write_text(
        "schema_version: 1\ndomains:\n  HV:\n    nets: [\"ac_l\"]\n  SELV:\n    nets: [\"gnd\"]\n"
    )

    # Each case: (name, centreline polyline, HV footprint xy, SELV footprint xy).
    # Board is the square (0,0)-(100,100). Corridors are the polyline buffered
    # by 5mm => 10mm wide, comfortably over the 8mm floor.
    cases = [
        (
            "straight-baseline",
            [(50, -5), (50, 105)],
            (20.0, 50.0),
            (80.0, 50.0),
        ),
        (
            # Non-convex: bulges right in the middle, four bends.
            "serpentine-4-bend",
            [(50, -5), (50, 25), (70, 25), (70, 75), (50, 75), (50, 105)],
            (20.0, 50.0),
            (85.0, 50.0),
        ),
        (
            # Boundary-following: enters and exits the SAME (left) edge,
            # cordoning off an edge pocket instead of bisecting the board.
            "boundary-following-pocket",
            [(-5, 35), (35, 35), (35, 65), (-5, 65)],
            (12.0, 50.0),
            (80.0, 50.0),
        ),
    ]

    results: list[tuple[str, str, list[str]]] = []
    for name, centreline, (hv_x, hv_y), (selv_x, selv_y) in cases:
        poly = LineString(centreline).buffer(5.0, quad_segs=QUAD_SEGS)
        coords = [Position(round(x, 4), round(y, 4)) for x, y in poly.exterior.coords[:-1]]

        board = Board()
        board.version = "20211014"
        board.generator = "freeform-probe"
        board.layers = [
            LayerToken(ordinal=0, name="F.Cu", type="signal"),
            LayerToken(ordinal=1, name="In1.Cu", type="signal"),
            LayerToken(ordinal=2, name="In2.Cu", type="signal"),
            LayerToken(ordinal=31, name="B.Cu", type="signal"),
            LayerToken(ordinal=44, name="Edge.Cuts", type="user"),
        ]
        board.nets = [Net(number=0, name=""), Net(number=1, name="ac_l"), Net(number=2, name="gnd")]
        board.graphicItems = [
            GrPoly(
                coordinates=[Position(0, 0), Position(100, 0), Position(100, 100), Position(0, 100)],
                layer="Edge.Cuts",
                width=0.1,
            )
        ]
        board.zones = [
            Zone(
                net=0,
                netName="",
                layers=copper_layers,
                name=BARRIER_ZONE_NAME,
                hatch=Hatch(style="none", pitch=0.0),
                keepoutSettings=KeepoutSettings(
                    tracks="not_allowed",
                    vias="not_allowed",
                    pads="not_allowed",
                    copperpour="not_allowed",
                    footprints="not_allowed",
                ),
                polygons=[ZonePolygon(coordinates=coords)],
                tstamp=f"barrier-{name}",
            )
        ]

        fps = []
        for ref, (fx, fy), net in (
            ("R1", (hv_x, hv_y), Net(number=1, name="ac_l")),
            ("U1", (selv_x, selv_y), Net(number=2, name="gnd")),
        ):
            fp = Footprint()
            fp.entryName = f"Test:{ref}"
            fp.layer = "F.Cu"
            fp.position = Position(fx, fy)
            fp.properties = {"Reference": ref}
            fp.pads = [
                Pad(
                    number="1",
                    type="smd",
                    shape="rect",
                    position=Position(0, 0),
                    size=Position(1, 1),
                    layers=["F.Cu"],
                    net=net,
                )
            ]
            fps.append(fp)
        board.footprints = fps
        # One trace far from every corridor, so "copper items examined" != 0.
        board.traceItems = [
            Segment(
                start=Position(hv_x - 3, 95),
                end=Position(hv_x + 3, 95),
                width=0.3,
                layer="F.Cu",
                net=1,
                tstamp=f"seg-{name}",
            )
        ]

        board_path = tmp_dir / f"probe-{name}.kicad_pcb"
        board.to_file(str(board_path))
        state, report = run(board_path, manifest_path)
        results.append((name, state, sorted({v.check for v in report.violations})))
    return results


# ---------------------------------------------------------------------------
# PART B -- shape-independent feasibility on the real board
# ---------------------------------------------------------------------------


@dataclass
class ObstacleModel:
    name: str
    description: str
    kinds: tuple[str, ...]  # which entries of the geometry bank obstruct the barrier


def _exact_pad_polygons() -> tuple[dict[str, list], list[dict]]:
    """Exact copper footprints of every COPPER-BEARING pad, as rotated Shapely
    polygons -- rect / roundrect / circle / oval (the only four shapes present
    on this board; verified by survey). Returned alongside a per-pad record so
    isolator gaps can be recomputed on true geometry.

    The gate models every pad as its *circumscribing circle*
    (``pad_bounding_radius``) -- deliberately conservative for an intrusion
    check, but it OVER-states the extent of an elongated pad by up to
    (diagonal - half-width). Whether that over-statement is what blocks the
    barrier is a question about the gate's model, not about the board, so it
    has to be measured separately."""
    from kiutils.board import Board
    from shapely import affinity
    from shapely.geometry import LineString, Point, Polygon

    board = Board.from_file(str(BOARD))
    copper_names = {ly.name for ly in board.layers if getattr(ly, "type", None) == "signal"}

    def _has_copper(layers: list[str]) -> bool:
        return any(ln in ("*.Cu", "*Cu") or ln in copper_names for ln in (layers or []))

    def _local_shape(shape: str, w: float, h: float, rr_ratio: float):
        if shape == "circle":
            return Point(0, 0).buffer(max(w, h) / 2.0, quad_segs=32)
        if shape == "oval":
            if w >= h:
                r = h / 2.0
                d = max(w - h, 0.0) / 2.0
                return LineString([(-d, 0), (d, 0)]).buffer(r, quad_segs=32)
            r = w / 2.0
            d = max(h - w, 0.0) / 2.0
            return LineString([(0, -d), (0, d)]).buffer(r, quad_segs=32)
        rect = Polygon([(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)])
        if shape == "roundrect":
            r = max(min(rr_ratio, 0.5), 0.0) * min(w, h)
            if r > 1e-9:
                return rect.buffer(-r, quad_segs=32).buffer(r, quad_segs=32)
        return rect

    bank: dict[str, list] = defaultdict(list)
    records: list[dict] = []
    for fp in board.footprints:
        ref = (fp.properties or {}).get("Reference") or "<noref>"
        fx, fy = fp.position.X, fp.position.Y
        fang = fp.position.angle or 0.0
        flipped = str(fp.layer or "F.Cu").startswith("B.")
        for pad in fp.pads:
            if not _has_copper(pad.layers or []):
                continue
            lx, ly = pad.position.X, pad.position.Y
            if flipped:
                lx = -lx
            dx, dy = _rotate(lx, ly, fang)
            ax, ay = fx + dx, fy + dy
            w = getattr(pad.size, "X", 0.0) or 0.0
            h = getattr(pad.size, "Y", 0.0) or 0.0
            rr = getattr(pad, "roundrectRatio", None)
            rr = 0.25 if rr is None else rr
            geom = _local_shape(getattr(pad, "shape", None) or "rect", w, h, rr)
            # KiCad stores a pad's shape rotation absolutely (footprint angle
            # already folded in); y-down board frame, so a CCW board rotation
            # is a negative Shapely rotation. Cross-checked against K1: the
            # A1(coil) <-> 13(contact) gap this reproduces is exactly 8.000mm,
            # matching the placer's own evaluate_isolator_feasibility figure
            # recorded in docs/evidence/2026-08-01-isolation-barrier-feasibility.md.
            geom = affinity.rotate(geom, -(pad.position.angle or 0.0), origin=(0, 0))
            geom = affinity.translate(geom, ax, ay)
            bank["pads_exact"].append(geom)
            net_name = pad.net.name if pad.net is not None else ""
            records.append({"ref": ref, "number": pad.number, "net": net_name, "geom": geom, "x": ax, "y": ay})
    return bank, records


def _geometry_bank(board: BoardData) -> dict[str, list]:
    """Copper items as the GATE models them. Layer-agnostic (a conforming
    barrier spans every copper layer, so copper on any layer obstructs it), but
    layer-FILTERED: a pad declared only on a non-copper layer (F.Fab) carries
    no copper and is not an obstacle -- exactly what the gate's own check 5
    does when it skips pads whose copper-layer set is empty."""
    from shapely.geometry import LineString, Point, Polygon

    out: dict[str, list] = defaultdict(list)
    for seg in board.segments:
        line = LineString(seg.points)
        out["traces"].append(line.buffer(seg.width / 2.0, quad_segs=16) if seg.width > 0 else line)
    for via in board.vias:
        out["vias"].append(Point(via.x, via.y).buffer(via.radius, quad_segs=16))
    for pad in board.pads:
        if not pad.layers:
            continue  # no copper on any layer -> not an obstacle (gate check 5 skips it too)
        out["pads_circle"].append(
            Point(pad.x, pad.y).buffer(pad.radius, quad_segs=16) if pad.radius > 0 else Point(pad.x, pad.y)
        )
    for cz in board.copper_zones:
        for ring in cz.polygons:
            if len(ring) >= 3:
                p = Polygon(ring)
                if p.is_valid and not p.is_empty:
                    out["pours"].append(p)
    return out


def _opening(free, r: float):
    """opening(free, r) -- the union of every disc of radius r that fits inside
    ``free``. Any barrier that is >= 2r wide everywhere and copper-free is a
    subset of this, whatever its shape."""
    eroded = free.buffer(-r, quad_segs=QUAD_SEGS)
    if eroded.is_empty:
        return eroded
    return eroded.buffer(r, quad_segs=QUAD_SEGS)


def _components(geom) -> list:
    if geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom]
    return [g for g in geom.geoms if g.geom_type == "Polygon" and not g.is_empty]


def _separable_pads(board: BoardData, manifest: Manifest, board_poly):
    """The pads the necessary condition may reason about: classified by the
    manifest, carrying copper on at least one layer, and inside the outline.

    Copper-bearing is load-bearing: check 5 forbids copper from overlapping the
    barrier, so a copper pad can never sit INSIDE it and check 6 must therefore
    place it on one side or the other. A pad with no copper (K1.13/K1.14 here)
    can legally fall inside the barrier, in which case check 6's ``_side_of``
    returns None and drops it -- so it cannot be used to prove impossibility."""
    from shapely.geometry import Point

    hv, selv, dropped = [], [], []
    for p in board.pads:
        if p.net_name in manifest.hv_nets:
            dom = "HV"
        elif p.net_name in manifest.selv_nets:
            dom = "SELV"
        else:
            continue
        if not p.layers:
            dropped.append((dom, p, "no copper layer"))
            continue
        if not board_poly.covers(Point(p.x, p.y)):
            dropped.append((dom, p, "outside Edge.Cuts"))
            continue
        (hv if dom == "HV" else selv).append(p)
    return hv, selv, dropped


def _same_component_conflicts(components: list, hv: list[PadInstance], selv: list[PadInstance]):
    """Components of ``board \\ O`` holding pads of BOTH domains. Each one is a
    proof that no conforming barrier of any shape exists."""
    from shapely.geometry import Point
    from shapely.strtree import STRtree

    if not components:
        return 0, [{"component_index": -1, "note": "board \\ O is empty"}]
    tree = STRtree(components)

    def _assign(pads: list[PadInstance]) -> dict[int, list[PadInstance]]:
        by_comp: dict[int, list[PadInstance]] = defaultdict(list)
        for p in pads:
            pt = Point(p.x, p.y)
            best, best_d = None, float("inf")
            for i in tree.query(pt):
                d = components[int(i)].distance(pt)
                if d < best_d:
                    best, best_d = int(i), d
            if best is None:
                for i, comp in enumerate(components):
                    d = comp.distance(pt)
                    if d < best_d:
                        best, best_d = i, d
            by_comp[best].append(p)
        return by_comp

    hv_by, selv_by = _assign(hv), _assign(selv)
    conflicts = []
    for ci in sorted(set(hv_by) & set(selv_by)):
        a, b = hv_by[ci], selv_by[ci]
        best = min(
            ((h, s, ((h.x - s.x) ** 2 + (h.y - s.y) ** 2) ** 0.5 - h.radius - s.radius) for h in a for s in b),
            key=lambda t: t[2],
        )
        conflicts.append(
            {
                "component_index": ci,
                "component_area_mm2": round(components[ci].area, 2),
                "hv_pads": len(a),
                "selv_pads": len(b),
                "closest_pair": f"{best[0].ref}.{best[0].number}({best[0].net_name}) <-> {best[1].ref}.{best[1].number}({best[1].net_name})",
                "closest_circle_model_gap_mm": round(best[2], 4),
            }
        )
    return len(components), conflicts


def _isolator_gaps(board: BoardData, manifest: Manifest, exact_records: list[dict]) -> list[dict]:
    """For every component carrying pads of BOTH domains, the minimum gap
    between its HV copper and its SELV copper -- under the gate's circle model
    and under exact pad geometry. A conforming barrier has to pass between
    them, so a component whose own two domains are closer than the barrier
    width is a shape-independent blocker that no re-placement of that component
    can fix (only a different part, or a domain re-declaration, can)."""
    by_ref_circle: dict[str, dict[str, list[PadInstance]]] = defaultdict(lambda: {"HV": [], "SELV": []})
    for p in board.pads:
        if not p.layers:
            continue
        if p.net_name in manifest.hv_nets:
            by_ref_circle[p.ref]["HV"].append(p)
        elif p.net_name in manifest.selv_nets:
            by_ref_circle[p.ref]["SELV"].append(p)

    by_ref_exact: dict[str, dict[str, list[dict]]] = defaultdict(lambda: {"HV": [], "SELV": []})
    for rec in exact_records:
        if rec["net"] in manifest.hv_nets:
            by_ref_exact[rec["ref"]]["HV"].append(rec)
        elif rec["net"] in manifest.selv_nets:
            by_ref_exact[rec["ref"]]["SELV"].append(rec)

    rows = []
    for ref, groups in sorted(by_ref_circle.items()):
        if not (groups["HV"] and groups["SELV"]):
            continue
        c_best = min(
            ((h, s, ((h.x - s.x) ** 2 + (h.y - s.y) ** 2) ** 0.5 - h.radius - s.radius) for h in groups["HV"] for s in groups["SELV"]),
            key=lambda t: t[2],
        )
        eg = by_ref_exact.get(ref, {"HV": [], "SELV": []})
        if eg["HV"] and eg["SELV"]:
            e_best = min(
                ((h, s, h["geom"].distance(s["geom"])) for h in eg["HV"] for s in eg["SELV"]),
                key=lambda t: t[2],
            )
            exact_gap = round(e_best[2], 4)
            exact_pair = f"{e_best[0]['number']}({e_best[0]['net']}) <-> {e_best[1]['number']}({e_best[1]['net']})"
        else:
            exact_gap, exact_pair = None, "-"
        rows.append(
            {
                "ref": ref,
                "hv_copper_pads": len(groups["HV"]),
                "selv_copper_pads": len(groups["SELV"]),
                "circle_model_gap_mm": round(c_best[2], 4),
                "exact_geometry_gap_mm": exact_gap,
                "exact_closest_pair": exact_pair,
                "exact_admits_8mm": (exact_gap is not None and exact_gap >= MIN_BARRIER_WIDTH_MM),
            }
        )
    return sorted(rows, key=lambda r: (r["exact_geometry_gap_mm"] is None, r["exact_geometry_gap_mm"]))


def _part_c(board: BoardData, manifest: Manifest, board_poly, bank: dict[str, list]) -> dict:
    """Gate checks 4 + 6 together demand ONE region holding every HV copper pad
    and ONE holding every SELV copper pad. So the HV side must be connected.

    Where can the HV side reach? The barrier's centreline must stay >= 8/2 mm
    from all copper (else the corridor is not copper-free), so the HV side may
    grow through:
      - ``K`` = {points >= 4mm from all copper} -- corridor-capable free space, and
      - any *blob* of the remaining space that carries NO SELV copper: absorbing
        an HV-only or unclassified-only blob into the HV region is legal, since
        only SELV copper is forbidden there.
    This is the most permissive space the HV region can possibly occupy. If the
    HV copper pads fall into two or more connected components of it, no
    conforming barrier exists for that obstacle model -- the stranded pads
    cannot share a region with the rest, and they cannot sit inside the barrier
    either (check 5 forbids copper there).

    Reported at two raster resolutions; the verdict must agree at both."""
    import shapely
    from scipy.ndimage import distance_transform_edt, label
    from shapely.ops import unary_union

    hv = [p for p in board.pads if p.net_name in manifest.hv_nets and p.layers]
    selv = [p for p in board.pads if p.net_name in manifest.selv_nets and p.layers]
    minx, miny, maxx, maxy = board_poly.bounds
    out: dict = {"models": {}}

    for model_name, kinds in (
        ("as-routed", ("pads_exact", "traces", "vias", "pours")),
        ("reroutable", ("pads_exact",)),
    ):
        copper = unary_union([g for k in kinds for g in bank[k]])
        per_res = []
        for cell in (0.4, 0.25):
            xs = np.arange(minx + cell / 2, maxx, cell)
            ys = np.arange(miny + cell / 2, maxy, cell)
            gx, gy = np.meshgrid(xs, ys)
            cu = shapely.contains_xy(copper, gx, gy)
            inb = shapely.contains_xy(board_poly, gx, gy)
            dist = distance_transform_edt(~cu, sampling=cell)

            def _cells(pads, _ys=ys, _xs=xs, _inb=inb, _cell=cell):
                msk = np.zeros_like(_inb)
                for p in pads:
                    r = int((p.y - _ys[0]) / _cell + 0.5)
                    c = int((p.x - _xs[0]) / _cell + 0.5)
                    if 0 <= r < len(_ys) and 0 <= c < len(_xs):
                        msk[r, c] = True
                return msk

            selv_cells = _cells(selv)
            capable = (dist >= HALF_WIDTH_MM) & inb
            lab, n = label((~capable) & inb)
            selv_blobs = {int(v) for v in np.unique(lab[selv_cells & (lab > 0)])}
            absorbable = np.isin(lab, [i for i in range(1, n + 1) if i not in selv_blobs]) & (lab > 0)
            plab, _ = label(capable | absorbable)

            # Key 0 = "in no admissible HV-side space at all": that pad could
            # only lie inside the barrier, which check 5 forbids for copper.
            # It is a stranded group in its own right, never a silent drop.
            groups: dict[int, list[str]] = defaultdict(list)
            for p in hv:
                r = int((p.y - ys[0]) / cell + 0.5)
                c = int((p.x - xs[0]) / cell + 0.5)
                key = int(plab[r, c]) if (0 <= r < len(ys) and 0 <= c < len(xs)) else 0
                groups[key].append(f"{p.ref}.{p.number}")
            ordered = sorted(groups.values(), key=len)
            per_res.append(
                {
                    "cell_mm": cell,
                    "blobs": int(n),
                    "hv_reachability_components": len(groups),
                    "hv_pads_with_no_admissible_space": len(groups.get(0, [])),
                    "stranded_groups": list(ordered[:-1]) if len(ordered) > 1 else [],
                    "connected": len(groups) == 1 and 0 not in groups,
                }
            )
            homeless = len(groups.get(0, []))
            if homeless:
                tag = f"IMPOSSIBLE ({homeless} HV pad(s) have no admissible HV-side space at all)"
            elif len(groups) == 1:
                tag = "CONNECTED"
            else:
                tag = f"SPLIT into {len(groups)}"
            print(f"  {model_name:12s} cell={cell}mm: HV copper reachability -> {tag}")
            for g in ordered[:-1]:
                print(f"      STRANDED: {len(g)} HV pad(s) {sorted(g)}")
        out["models"][model_name] = per_res
        agree = {r["connected"] for r in per_res}
        out["models"][model_name + "_verdict"] = (
            "possible" if agree == {True} else ("impossible" if agree == {False} else "resolution-dependent")
        )
    return out


def main() -> int:
    import tempfile

    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    result: dict = {"min_barrier_width_mm": MIN_BARRIER_WIDTH_MM, "half_width_mm": HALF_WIDTH_MM}

    print("=" * 90)
    print("PART A -- does check 4 (PARTITION) admit a non-straight / boundary-following keepout?")
    print("=" * 90)
    with tempfile.TemporaryDirectory() as td:
        probe = _synthetic_probe(Path(td))
    result["part_a"] = []
    for name, state, checks in probe:
        ok = "partition" not in checks
        print(f"  {name:28s} gate={state:9s} violations={checks or '[]':24s} partition-check={'PASSED' if ok else 'FAILED'}")
        result["part_a"].append({"shape": name, "state": state, "violations": checks, "partition_ok": ok})
    print()

    print("=" * 90)
    print("PART B -- shape-independent feasibility on the committed placement")
    print("=" * 90)
    manifest = load_manifest(MANIFEST)
    board = load_board(BOARD)
    board_poly = Polygon(board.board_outline)
    print(f"  outline {board_poly.bounds}, area {board_poly.area:.1f} mm^2; copper layers {board.copper_layers_ordered}")

    bank = _geometry_bank(board)
    exact_bank, exact_records = _exact_pad_polygons()
    bank.update(exact_bank)
    counts = {k: len(v) for k, v in sorted(bank.items())}
    print(f"  geometry bank: {counts}")
    result["geometry_bank_counts"] = counts

    hv, selv, dropped = _separable_pads(board, manifest, board_poly)
    print(f"  copper-bearing, in-board classified pads: HV={len(hv)} SELV={len(selv)}")
    for dom, p, why in dropped:
        print(f"    excluded from the proof: {p.ref}.{p.number} ({dom}, net {p.net_name!r}) -- {why}")
    result["hv_pads_used"] = len(hv)
    result["selv_pads_used"] = len(selv)
    result["pads_excluded_from_proof"] = [
        {"ref": p.ref, "number": p.number, "domain": d, "net": p.net_name, "reason": w} for d, p, w in dropped
    ]

    iso = _isolator_gaps(board, manifest, exact_records)
    result["isolator_gaps"] = iso
    print("\n  Components carrying copper of BOTH domains (a barrier must pass between them):")
    print(f"    {'ref':6s} {'HVcu':>4s} {'SELVcu':>6s} {'circle-model':>12s} {'exact':>9s}  {'>=8.0?':>6s}  exact closest pair")
    for r in iso:
        eg = "n/a" if r["exact_geometry_gap_mm"] is None else f"{r['exact_geometry_gap_mm']:9.4f}"
        print(
            f"    {r['ref']:6s} {r['hv_copper_pads']:4d} {r['selv_copper_pads']:6d} "
            f"{r['circle_model_gap_mm']:12.4f} {eg}  {str(r['exact_admits_8mm']):>6s}  {r['exact_closest_pair']}"
        )
    bl = [r for r in iso if not r["exact_admits_8mm"]]
    print(f"    -> on exact geometry, {len(bl)} of {len(iso)} cannot admit an {MIN_BARRIER_WIDTH_MM}mm barrier between their own domains.")

    ambient = board_poly.buffer(50.0, quad_segs=8)  # the barrier may leave and re-enter the outline

    models = [
        ObstacleModel(
            "gate-model-as-routed",
            "traces + vias + pours + pads as the gate's circumscribing circles (board exactly as committed)",
            ("traces", "vias", "pours", "pads_circle"),
        ),
        ObstacleModel(
            "gate-model-reroutable",
            "pads only, gate's circumscribing circles (assume a full re-route; placement unchanged)",
            ("pads_circle",),
        ),
        ObstacleModel(
            "exact-geometry-reroutable",
            "pads only, TRUE rotated pad outlines (assume a full re-route; placement unchanged)",
            ("pads_exact",),
        ),
    ]
    result["models"] = {}
    for model in models:
        parts = [g for kind in model.kinds for g in bank[kind]]
        copper = unary_union(parts)
        free = ambient.difference(copper)
        print(f"\n  --- {model.name}: {model.description}")
        print(f"      {len(parts)} geometries; copper area inside outline {copper.intersection(board_poly).area:.1f} mm^2")

        sweep = []
        for r in (HALF_WIDTH_MM, 3.5, 3.0, 2.5, 2.0, 1.0, 0.5):
            o = _opening(free, r)
            rest = board_poly.difference(o) if not o.is_empty else board_poly
            comps = _components(rest)
            n, conflicts = _same_component_conflicts(comps, hv, selv)
            ok = (not conflicts) and n >= 2
            sweep.append(
                {
                    "half_width_mm": r,
                    "barrier_width_mm": round(2 * r, 3),
                    "corridor_space_in_board_mm2": round(o.intersection(board_poly).area, 2) if not o.is_empty else 0.0,
                    "regions_outside_opening": n,
                    "mixed_domain_regions": len(conflicts),
                    "necessary_condition_met": bool(ok),
                    "conflicts": conflicts[:5],
                }
            )
            print(
                f"      width={2 * r:5.2f}mm  corridor space={sweep[-1]['corridor_space_in_board_mm2']:9.1f} mm^2  "
                f"regions={n:4d}  mixed={len(conflicts):3d}  -> {'POSSIBLE' if ok else 'IMPOSSIBLE'}"
            )
            if conflicts and r == HALF_WIDTH_MM:
                for c in conflicts[:4]:
                    if "note" in c:
                        print(f"          {c['note']}")
                        continue
                    print(
                        f"          mixed region #{c['component_index']} ({c['component_area_mm2']} mm^2): "
                        f"{c['hv_pads']} HV + {c['selv_pads']} SELV copper pads; closest {c['closest_pair']}"
                    )
        result["models"][model.name] = {"description": model.description, "sweep": sweep}

    print("\n" + "=" * 90)
    print("PART C -- HV-side connectivity: the decisive test for gate checks 4 + 6")
    print("=" * 90)
    result["part_c"] = _part_c(board, manifest, board_poly, bank)

    result["provenance"] = {"commit": PROVENANCE_COMMIT, "dirty": False}
    out_json = Path(__file__).with_suffix(".json")
    out_json.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n")
    print(f"\nwrote {out_json.relative_to(REPO_ROOT)}")

    print(f"\n=== VERDICT at MIN_BARRIER_WIDTH_MM = {MIN_BARRIER_WIDTH_MM}mm ===")
    for name, data in result["models"].items():
        at8 = next(s for s in data["sweep"] if s["half_width_mm"] == HALF_WIDTH_MM)
        print(f"  {name:28s}: {'not ruled out by this test' if at8['necessary_condition_met'] else 'NO conforming barrier exists, of ANY shape'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
