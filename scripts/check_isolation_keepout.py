#!/usr/bin/env python3
"""Physical mains<->SELV isolation-barrier gate: enforce by construction.

Motivation
----------
``pcb/temper.kicad_pcb`` contains ZERO keepout zones (verified:
``grep -c "keepout\\|keep_out" pcb/temper.kicad_pcb`` returns 0). The
mains<->SELV isolation boundary -- the single most safety-critical property
of this board's layout under IEC 60335-1 / 60335-2-6 -- exists today only as
*declarations and after-the-fact checks*: ``elec/domain_manifest.yaml`` says
which nets are which, ``elec/src/main.ato`` floats the SELV domain, and
several clearance/creepage checks measure distance once copper already
exists. Those clearance checks have themselves proven fragile on this
project -- ``docs/evidence/2026-07-27-creepage-burndown.md`` and
``2026-07-27-net-classification-gate.md`` document 24 false-positive and 11
false-negative HV/SELV clearance findings from bugs in the classification
logic those checks depended on.

This gate does not re-measure clearance between arbitrary copper pairs (that
is ``check_net_classification.py`` / the router's own clearance engine's
job, and the domain-*connectivity* question is ``check_domain_partition.py``'s
job, over the compiled netlist). This gate checks a narrower, physically
stronger property: that a **dedicated keepout region** exists on the board,
spans every copper layer, is wide enough to satisfy the isolation
requirement by construction, and that the board's real copper (traces,
vias, pads, pours) actually respects it. A keepout makes the violation
*impossible to route into* rather than merely *detectable once routed* --
the professional's-first-act framing this gate exists to enforce.

Which clearance figure: BASIC clearance through REINFORCED creepage
---------------------------------------------------------------------
The DC bus is +-170V about a grounded midpoint (340V differential -- see
``elec/domain_manifest.yaml``'s ``+170V_BUS``/``PWR_RTN``/``DC_BUS_RTN``
declarations and ``docs/hardware/POWER_PLANE_DESIGN.md`` Sec 2.1/6.1). The
SELV domain is user-accessible in normal use: the RTD probe reads the pan
surface, and the UI (buttons, USB) is touched directly during operation --
so this is not a barrier between two internal functional circuits (which
IEC 60335-1 would treat as BASIC/working insulation, ~2-3mm class); it is a
barrier between a mains-derived circuit and a part a user's hand can reach,
which the standard requires REINFORCED insulation across (equivalent to two
independent basic-insulation layers, since there is no separate
double-insulated enclosure barrier doing this job at the board level for
this crossing).

``packages/temper-placer/configs/netclass_rules.yaml`` already declares
6.0mm for ``ACMains``/``HighVoltage`` pairs, citing "IEC 60335-1 Table 16
working isolation at 400V" -- note "working isolation": that figure is the
BASIC/functional clearance between two HV-class nets of similar domain, not
the reinforced mains<->user-accessible-SELV figure this barrier actually
needs. Reusing it here would repeat the exact class of error flagged in this
plan ("do NOT assume 3-6mm; that error was made earlier on this project").

At <=400V working voltage, pollution degree 2, material group IIIb (the
conservative, unverified-CTI assumption for generic FR4), the commonly
cited (and industry-standard, e.g. widely used in offline/universal-input
SMPS layout guides for the analogous IEC 60950-1/62368-1 "reinforced
insulation, <=250Vac mains, post-doubler/PFC bus" case) figures are
approximately 6.4mm CLEARANCE and 8.0mm CREEPAGE for reinforced insulation.
Creepage (surface distance) is always >= clearance (through-air distance)
for the same voltage/pollution class, and a PCB keepout enforces surface
distance directly (both sides of the gap are literally board surface), so
the creepage figure is the binding one for sizing a physical keepout.
MIN_BARRIER_WIDTH_MM below is therefore set to the top of the stated
3.0-8.0mm range, not the middle: **8.0mm**.
UNVERIFIED-at-primary (same epistemic status as several figures already
carried in ``elec/domain_manifest.yaml``'s own OVP-01 protective-impedance
writeup): IEC 60335-1's Table 16 / IEC 60664-1's creepage tables are
paywalled primary text; this figure is reconstructed from secondary/industry
sources, not read from the standard directly in this pass. Never shrunk to
match this repo's existing (looser) 6.0mm netclass figure -- see the plan's
hard rule against weakening a safety distance to get a green gate.

What this checks
-----------------
Looks for a zone on the board that is BOTH a keepout (``keepoutSettings`` is
not None, i.e. a "rule area" in modern KiCad terms, not an ordinary copper
pour) AND named exactly ``BARRIER_ZONE_NAME`` (a documented convention, not
an inference from shape/position -- distinguishes this specific
safety-critical barrier from any other incidental keepout a board might
carry, e.g. under a connector to keep pour off a mounting hole).

If found, verifies ALL of:
  1. LAYER SPAN: the zone's declared layers, after expanding ``*.Cu``
     wildcards, cover every copper layer the board's own stackup declares
     (``(layers ...)`` entries of type ``signal``) -- not just the outer two.
  2. KEEPOUT SETTINGS: tracks/vias/pads/copperpour/footprints are all
     ``not_allowed`` -- a "keepout" that still permits routing through it
     enforces nothing.
  3. WIDTH: the polygon, eroded (via Shapely negative buffer) by half of
     ``MIN_BARRIER_WIDTH_MM``, is non-empty everywhere the erosion is
     checked -- i.e. the barrier is at least ``MIN_BARRIER_WIDTH_MM`` wide
     at its narrowest, not merely on average.
  4. PARTITION: subtracting the keepout polygon from the board outline
     (``Edge.Cuts``) yields EXACTLY two disjoint regions. A "barrier" that
     does not span the full board edge-to-edge does not actually separate
     anything -- copper can simply route around its ends -- so this gate
     treats a non-bisecting keepout as equivalent to a missing one.
  5. NO INTRUSION: no copper item (segment, arc, via -- expanded to every
     copper layer physically between its endpoints' layers, not just the
     two named ones, since a through-via's drill breaches every internal
     layer regardless of what its ``layers`` field names -- pad, or
     non-keepout zone polygon) overlaps the keepout region on any shared
     layer.
  6. NO FAR-SIDE CROSSING: every HV-domain-classified pad lands in exactly
     one of the two partition regions, every SELV-domain-classified pad
     lands in the other, and no domain has copper in both regions (which
     would mean the "barrier" doesn't actually correspond to the real
     domain split).

Fail-closed contract (this repo's METHODOLOGY.md Sec 4/5, matching
``check_domain_partition.py`` / ``check_copper_net_consistency.py``): never
exits 0 unless it positively confirms a real, non-empty check ran. Exits
non-zero for every one of:
  - the board or manifest file is missing, empty, or fails to parse
  - the manifest has zero HV nets or zero SELV nets
  - the board has zero footprints, zero pads, zero copper items, or zero
    copper layers in its own stackup declaration
  - zero HV-classified pads or zero SELV-classified pads are found on the
    board (nothing of one domain exists to protect -- the barrier question
    is moot, not "0 violations")
  - the board outline (``Edge.Cuts``) cannot be determined
  - the barrier keepout zone is missing (VIOLATION, not GATE_ERROR -- see
    below: this is a real, substantive, correctly-reasoned finding against
    real data, not a vacuous no-op)

Exit codes:
  0 - PASSED: barrier keepout found, spans all copper layers, correctly
      configured, >=MIN_BARRIER_WIDTH_MM everywhere, bisects the board into
      exactly two regions, zero copper intrusions, zero far-side crossings.
  3 - VIOLATION: the barrier is missing, undersized, misconfigured, does
      not bisect the board, is intruded upon, or a domain has copper on
      both sides.
  5 - GATE ERROR: the gate could not run a trustworthy check at all (see
      list above) -- never conflated with "0 violations".

Usage:
  uv run --no-sync python scripts/check_isolation_keepout.py
  uv run --no-sync python scripts/check_isolation_keepout.py --board PATH --manifest PATH
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.github_summary import get_github_summary_path  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402

from temper_placer.core.pad_geometry import pad_bounding_radius  # noqa: E402

REPO_ROOT = find_repo_root()
DEFAULT_BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"
DEFAULT_MANIFEST = REPO_ROOT / "elec" / "domain_manifest.yaml"

EXIT_OK = 0
EXIT_VIOLATION = 3
EXIT_GATE_ERROR = 5

# Naming convention for the one zone this gate treats as THE mains<->SELV
# barrier -- deliberately narrow (not "any keepout") so an unrelated keepout
# elsewhere on the board (e.g. under a connector) is never mistaken for it.
BARRIER_ZONE_NAME = "MAINS_SELV_ISOLATION_BARRIER"

# REINFORCED creepage, pollution degree 2, material group IIIb, <=400V
# working voltage -- top of the plan's stated 3.0-8.0mm range. See module
# docstring "Which clearance figure" for full derivation and UNVERIFIED
# caveat. Never shrink this to make the gate pass (plan hard rule).
MIN_BARRIER_WIDTH_MM = 8.0

_COPPER_LAYER_TYPE = "signal"


class GateError(Exception):
    """Raised for any condition that must fail closed (exit 5)."""


# ---------------------------------------------------------------------------
# Domain manifest (self-contained loader -- deliberately NOT imported from
# check_domain_partition.py: this gate's correctness must not depend on a
# sibling gate's internal representation changing out from under it, same
# reasoning check_copper_net_consistency.py gives for its own copy).
# ---------------------------------------------------------------------------


@dataclass
class Manifest:
    hv_nets: frozenset[str]
    selv_nets: frozenset[str]


def load_manifest(path: Path) -> Manifest:
    if not path.is_file():
        raise GateError(f"domain manifest not found: {path}")
    raw_text = path.read_text(encoding="utf-8")
    if not raw_text.strip():
        raise GateError(f"domain manifest is empty: {path}")

    import yaml

    try:
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise GateError(f"domain manifest is not valid YAML: {exc}") from exc

    if not isinstance(data, dict):
        raise GateError(f"domain manifest must be a mapping at the top level: {path}")

    domains = data.get("domains")
    if not isinstance(domains, dict) or not domains:
        raise GateError(
            "domain manifest has no non-empty 'domains' mapping -- an empty "
            "or absent domain declaration must fail the gate, not pass it "
            "vacuously"
        )

    def _nets_for(domain_name: str) -> frozenset[str]:
        entry = domains.get(domain_name)
        if not isinstance(entry, dict):
            raise GateError(f"domain manifest has no {domain_name!r} domain mapping")
        nets = entry.get("nets")
        if not isinstance(nets, list) or not nets:
            raise GateError(f"domain manifest's {domain_name!r} domain has zero nets declared")
        for n in nets:
            if not isinstance(n, str) or not n:
                raise GateError(f"domain manifest's {domain_name!r} domain has a non-string/empty net entry")
        return frozenset(nets)

    hv_nets = _nets_for("HV")
    selv_nets = _nets_for("SELV")
    overlap = hv_nets & selv_nets
    if overlap:
        raise GateError(f"domain manifest declares net(s) in BOTH HV and SELV: {sorted(overlap)}")

    return Manifest(hv_nets=hv_nets, selv_nets=selv_nets)


# ---------------------------------------------------------------------------
# Board loading (kiutils -- same library resync_pcb_netlist.py and
# check_copper_net_consistency.py already use to read this exact format).
# ---------------------------------------------------------------------------


@dataclass
class PadInstance:
    ref: str
    number: str
    x: float
    y: float
    radius: float  # exact, tight, rotation-invariant circumscribing radius --
    # see temper_placer.core.pad_geometry.pad_bounding_radius. NOT
    # max(size.X, size.Y)/2 (the prior formula): that under-reports the
    # true corner extent of a square/near-square rect/roundrect pad (a
    # circle never contains a rectangle) -- measured worst case on this
    # board: C2/C3/C4/C5 pad 1 (4x4mm roundrect), true bounding radius
    # 2.725mm vs the old model's 2.000mm, a 0.725mm under-report; see
    # docs/evidence/2026-07-28-pad-geometry-model-fix.md for the full
    # per-pad survey (including a citation in the originating plan that
    # did not hold up: R30 pad 1 is a genuine circle, not a rect/roundrect,
    # so the old formula was already exact for it).
    layers: frozenset[str]  # copper layers only, wildcard-expanded
    net_name: str


@dataclass
class SegmentItem:
    kind: str  # "Segment" | "Arc"
    ident: str
    layer: str
    width: float
    points: list[tuple[float, float]]  # 2+ points, absolute board coords


@dataclass
class ViaItem:
    ident: str
    x: float
    y: float
    radius: float
    layers: frozenset[str]  # copper layers physically spanned (ordinal-expanded)


@dataclass
class CopperZoneItem:
    ident: str
    net_name: str
    layers: frozenset[str]
    polygons: list[list[tuple[float, float]]]


@dataclass
class KeepoutZoneItem:
    ident: str
    name: str | None
    layers_raw: list[str]
    keepout_tracks: str | None
    keepout_vias: str | None
    keepout_pads: str | None
    keepout_copperpour: str | None
    keepout_footprints: str | None
    polygons: list[list[tuple[float, float]]]


@dataclass
class BoardData:
    copper_layers_ordered: list[str]  # ordinal-sorted, e.g. F.Cu, In1.Cu, In2.Cu, B.Cu
    pads: list[PadInstance]
    segments: list[SegmentItem]
    vias: list[ViaItem]
    copper_zones: list[CopperZoneItem]
    keepout_zones: list[KeepoutZoneItem]
    board_outline: list[tuple[float, float]] | None  # Edge.Cuts polygon, if any


def _rotate(x: float, y: float, angle_deg: float | None) -> tuple[float, float]:
    """KiCad's footprint-child rotation (y-down board frame): R(-theta), not
    the R(+theta) this function used before. Confirmed against real
    ``kicad-cli 10.0.4 pcb drc`` ground truth in
    docs/evidence/2026-07-29-cross-domain-creepage-rotation-convention.md
    (Sec. 2) and matches ``scripts/check_pad_orientation.py``'s
    independently-validated (57/57 against real DRC) ``_rotate``."""
    a = math.radians(angle_deg or 0.0)
    return (x * math.cos(a) + y * math.sin(a), -x * math.sin(a) + y * math.cos(a))


def _expand_copper_layers(raw_layers: list[str], copper_layers_ordered: list[str]) -> frozenset[str]:
    out: set[str] = set()
    copper_set = set(copper_layers_ordered)
    for name in raw_layers:
        if name in ("*.Cu", "*Cu"):
            out |= copper_set
        elif name in copper_set:
            out.add(name)
        # non-copper layers (Mask/Paste/SilkS/...) intentionally ignored --
        # this gate only ever reasons about copper.
    return frozenset(out)


def _via_layer_span(via_layers_raw: list[str], copper_layers_ordered: list[str]) -> frozenset[str]:
    """A via's drilled barrel physically breaches every copper layer between
    its two named endpoints (KiCad only records the two outermost layers a
    through via touches, e.g. ["F.Cu", "B.Cu"], even though the drill passes
    through every internal layer too). Expand by ordinal position in the
    board's own stackup, not by name -- never assume alphabetical order."""
    if not via_layers_raw:
        # No layer info at all: conservatively assume it spans every copper
        # layer (fail toward "this via can intrude", never toward "this via
        # is safely confined").
        return frozenset(copper_layers_ordered)
    named = _expand_copper_layers(via_layers_raw, copper_layers_ordered)
    if not named:
        return frozenset(copper_layers_ordered)
    indices = [copper_layers_ordered.index(n) for n in named if n in copper_layers_ordered]
    if not indices:
        return frozenset(copper_layers_ordered)
    lo, hi = min(indices), max(indices)
    return frozenset(copper_layers_ordered[lo : hi + 1])


def load_board(board_path: Path) -> BoardData:
    if not board_path.is_file():
        raise GateError(f"board not found: {board_path}")
    try:
        from kiutils.board import Board
    except ImportError as exc:
        raise GateError(f"kiutils is not installed: {exc}") from exc
    try:
        board = Board.from_file(str(board_path))
    except Exception as exc:  # kiutils raises plain Exception/ValueError on malformed input
        raise GateError(f"failed to parse board {board_path}: {exc}") from exc

    signal_layers = [ly for ly in board.layers if getattr(ly, "type", None) == _COPPER_LAYER_TYPE]
    if not signal_layers:
        raise GateError(f"board declares zero copper (type=signal) layers: {board_path}")
    copper_layers_ordered = [ly.name for ly in sorted(signal_layers, key=lambda ly: ly.ordinal)]

    if not board.footprints:
        raise GateError(f"board has zero footprints: {board_path}")

    pads: list[PadInstance] = []
    for fp in board.footprints:
        props = fp.properties or {}
        ref = props.get("Reference") or "<noref>"
        fx, fy = fp.position.X, fp.position.Y
        fangle = fp.position.angle or 0.0
        flipped = str(fp.layer or "F.Cu").startswith("B.")
        for pad in fp.pads:
            net_name = pad.net.name if pad.net is not None else ""
            lx, ly = pad.position.X, pad.position.Y
            if flipped:
                lx = -lx
            dx, dy = _rotate(lx, ly, fangle)
            ax, ay = fx + dx, fy + dy
            layers = _expand_copper_layers(pad.layers or [], copper_layers_ordered)
            # Exact, shape-aware bounding-circle radius: a safety intrusion
            # check must never UNDER-approximate a pad's physical extent
            # (matches the "over-approximate, never under" rule already
            # applied to segments/vias below). This used to be
            # max(size.X, size.Y) / 2 for every pad shape, which describes
            # no KiCad pad shape except "circle" -- it under-reports a
            # square/near-square rect/roundrect pad's true corner extent (a
            # circle never contains a rectangle; see PadInstance.radius's
            # own docstring for the measured worst case on this board).
            # `pad_bounding_radius` is the pad's EXACT, tight,
            # rotation-invariant circumscribing radius -- see
            # temper_placer.core.pad_geometry's module docstring for the
            # closed-form derivation and never-under-reports proof.
            size_x = getattr(pad.size, "X", 0.0) or 0.0
            size_y = getattr(pad.size, "Y", 0.0) or 0.0
            pad_shape = getattr(pad, "shape", None) or "rect"
            pad_roundrect_ratio = getattr(pad, "roundrectRatio", None)
            if pad_roundrect_ratio is None:
                pad_roundrect_ratio = 0.25
            radius = pad_bounding_radius(size_x, size_y, pad_shape, pad_roundrect_ratio)
            pads.append(
                PadInstance(
                    ref=ref, number=pad.number, x=ax, y=ay, radius=radius,
                    layers=layers, net_name=net_name,
                )
            )
    if not pads:
        raise GateError(f"board has zero pads across {len(board.footprints)} footprint(s)")

    segments: list[SegmentItem] = []
    vias: list[ViaItem] = []
    for item in board.traceItems:
        kind = type(item).__name__
        ident = getattr(item, "tstamp", None) or f"<{kind} with no tstamp>"
        if kind == "Segment":
            segments.append(
                SegmentItem(
                    kind="Segment",
                    ident=ident,
                    layer=item.layer,
                    width=item.width,
                    points=[(item.start.X, item.start.Y), (item.end.X, item.end.Y)],
                )
            )
        elif kind == "Arc":
            segments.append(
                SegmentItem(
                    kind="Arc",
                    ident=ident,
                    layer=item.layer,
                    width=item.width,
                    points=[
                        (item.start.X, item.start.Y),
                        (item.mid.X, item.mid.Y),
                        (item.end.X, item.end.Y),
                    ],
                )
            )
        elif kind == "Via":
            vias.append(
                ViaItem(
                    ident=ident,
                    x=item.position.X,
                    y=item.position.Y,
                    radius=item.size / 2.0,
                    layers=_via_layer_span(item.layers or [], copper_layers_ordered),
                )
            )
        # other trace-item kinds (if any future KiCad version adds one) are
        # intentionally not silently skipped from the denominator -- see
        # run()'s copper_items_examined accounting, which counts every
        # board.traceItems entry regardless of kind.

    copper_zones: list[CopperZoneItem] = []
    keepout_zones: list[KeepoutZoneItem] = []
    for i, zone in enumerate(board.zones):
        ident = zone.tstamp or f"<Zone index {i}>"
        polys = [[(pt.X, pt.Y) for pt in poly.coordinates] for poly in zone.polygons if poly.coordinates]
        if zone.keepoutSettings is not None:
            ks = zone.keepoutSettings
            keepout_zones.append(
                KeepoutZoneItem(
                    ident=ident,
                    name=zone.name,
                    layers_raw=list(zone.layers or []),
                    keepout_tracks=ks.tracks,
                    keepout_vias=ks.vias,
                    keepout_pads=ks.pads,
                    keepout_copperpour=ks.copperpour,
                    keepout_footprints=ks.footprints,
                    polygons=polys,
                )
            )
        else:
            copper_zones.append(
                CopperZoneItem(
                    ident=ident,
                    net_name=zone.netName or "",
                    layers=_expand_copper_layers(zone.layers or [], copper_layers_ordered),
                    polygons=polys,
                )
            )

    board_outline: list[tuple[float, float]] | None = None
    for item in board.graphicItems:
        if getattr(item, "layer", None) == "Edge.Cuts" and type(item).__name__ == "GrPoly":
            coords = getattr(item, "coordinates", None)
            if coords:
                board_outline = [(pt.X, pt.Y) for pt in coords]
                break

    total_copper = len(segments) + len(vias) + len(copper_zones)
    if total_copper == 0:
        raise GateError(
            f"board has zero copper items (0 segments/arcs/vias/non-keepout-zones): "
            f"{board_path} -- nothing for this gate to check an intrusion against "
            "(anti-vacuous-truth: report as a gate error, not '0 violations')"
        )

    return BoardData(
        copper_layers_ordered=copper_layers_ordered,
        pads=pads,
        segments=segments,
        vias=vias,
        copper_zones=copper_zones,
        keepout_zones=keepout_zones,
        board_outline=board_outline,
    )


# ---------------------------------------------------------------------------
# Geometry checks (Shapely)
# ---------------------------------------------------------------------------


@dataclass
class Violation:
    check: str
    detail: str


@dataclass
class Report:
    copper_layers: list[str] = field(default_factory=list)
    footprints_examined: int = 0
    pads_examined: int = 0
    hv_pads: int = 0
    selv_pads: int = 0
    copper_items_examined: int = 0  # segments + arcs + vias + non-keepout zones
    keepout_zones_found_total: int = 0  # any keepout, by any name
    barrier_found: bool = False
    violations: list[Violation] = field(default_factory=list)


def _polygon_or_none(coords_list: list[list[tuple[float, float]]]):
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    polys = [Polygon(pts) for pts in coords_list if len(pts) >= 3]
    polys = [p for p in polys if p.is_valid and not p.is_empty]
    if not polys:
        return None
    if len(polys) == 1:
        return polys[0]
    return unary_union(polys)


def run(
    board_path: Path,
    manifest_path: Path,
    barrier_name: str = BARRIER_ZONE_NAME,
    min_width: float = MIN_BARRIER_WIDTH_MM,
) -> tuple[str, Report]:
    """Returns (state, report), state in 'clean' | 'violation'.

    Raises GateError for anything that must fail closed (exit 5) -- caller
    (main()) is responsible for catching it.
    """
    report = Report()

    manifest = load_manifest(manifest_path)
    board = load_board(board_path)

    report.copper_layers = board.copper_layers_ordered
    report.footprints_examined = len({p.ref for p in board.pads})
    report.pads_examined = len(board.pads)
    report.copper_items_examined = len(board.segments) + len(board.vias) + len(board.copper_zones)
    report.keepout_zones_found_total = len(board.keepout_zones)

    hv_pads = [p for p in board.pads if p.net_name in manifest.hv_nets]
    selv_pads = [p for p in board.pads if p.net_name in manifest.selv_nets]
    report.hv_pads = len(hv_pads)
    report.selv_pads = len(selv_pads)

    if not hv_pads:
        raise GateError(
            "zero HV-domain-classified pads found on the board -- nothing of "
            "the HV domain exists to protect (anti-vacuous-truth: this is a "
            "gate error, not '0 violations')"
        )
    if not selv_pads:
        raise GateError(
            "zero SELV-domain-classified pads found on the board -- nothing "
            "of the SELV domain exists to protect (anti-vacuous-truth: this "
            "is a gate error, not '0 violations')"
        )

    matching = [z for z in board.keepout_zones if z.name == barrier_name]
    if len(matching) == 0:
        report.violations.append(
            Violation(
                "missing",
                f"No keepout zone named {barrier_name!r} found on the board "
                f"({report.keepout_zones_found_total} other keepout zone(s) "
                "present, if any). The mains<->SELV isolation barrier is not "
                "physically enforced -- it exists only as declarations "
                "(elec/domain_manifest.yaml) and after-the-fact clearance "
                "checks. A human must place a keepout region spanning all "
                f"{len(board.copper_layers_ordered)} copper layers "
                f"({', '.join(board.copper_layers_ordered)}), at least "
                f"{min_width}mm wide throughout, bisecting the board so "
                "every HV-domain component is on one side and every "
                "SELV-domain component is on the other, named exactly "
                f"{barrier_name!r}.",
            )
        )
        return "violation", report
    if len(matching) > 1:
        report.violations.append(
            Violation(
                "duplicate",
                f"{len(matching)} keepout zones are named {barrier_name!r} -- "
                "exactly one is expected; ambiguous which is the real barrier.",
            )
        )
        return "violation", report

    barrier = matching[0]
    report.barrier_found = True

    # Check 1: layer span.
    barrier_layers = _expand_copper_layers(barrier.layers_raw, board.copper_layers_ordered)
    missing_layers = [ly for ly in board.copper_layers_ordered if ly not in barrier_layers]
    if missing_layers:
        report.violations.append(
            Violation(
                "layer-span",
                f"Barrier zone {barrier.ident} does not span all copper "
                f"layers: missing {missing_layers} (declared layers: "
                f"{barrier.layers_raw}, board copper layers: "
                f"{board.copper_layers_ordered}).",
            )
        )

    # Check 2: keepout settings actually forbid copper.
    settings = {
        "tracks": barrier.keepout_tracks,
        "vias": barrier.keepout_vias,
        "pads": barrier.keepout_pads,
        "copperpour": barrier.keepout_copperpour,
        "footprints": barrier.keepout_footprints,
    }
    for setting_name, value in settings.items():
        if value != "not_allowed":
            report.violations.append(
                Violation(
                    "keepout-settings",
                    f"Barrier zone {barrier.ident} keepout setting "
                    f"{setting_name!r} is {value!r}, expected 'not_allowed' "
                    "-- a keepout that still permits this enforces nothing.",
                )
            )

    barrier_poly = _polygon_or_none(barrier.polygons)
    if barrier_poly is None:
        raise GateError(f"barrier zone {barrier.ident} has no valid polygon geometry")

    # Check 3: width, everywhere.
    eroded = barrier_poly.buffer(-min_width / 2.0)
    if eroded.is_empty:
        report.violations.append(
            Violation(
                "width",
                f"Barrier zone {barrier.ident} is narrower than "
                f"{min_width}mm at some point along its length (erosion by "
                f"{min_width / 2.0}mm collapses it to empty).",
            )
        )

    # Check 4: partition -- board outline minus barrier == exactly 2 pieces.
    if board.board_outline is None:
        raise GateError("board outline (Edge.Cuts) could not be determined -- cannot verify partition")
    from shapely.geometry import Polygon as ShapelyPolygon

    board_poly = ShapelyPolygon(board.board_outline)
    if not board_poly.is_valid or board_poly.is_empty:
        raise GateError("board outline (Edge.Cuts) polygon is invalid or empty")

    diff = board_poly.difference(barrier_poly)
    if diff.geom_type == "Polygon":
        pieces = [diff] if not diff.is_empty else []
    elif diff.geom_type == "MultiPolygon":
        pieces = [g for g in diff.geoms if not g.is_empty]
    else:
        pieces = []
    pieces = [p for p in pieces if p.area > 1e-6]

    side_a = side_b = None
    if len(pieces) != 2:
        report.violations.append(
            Violation(
                "partition",
                f"Barrier zone {barrier.ident} does not bisect the board "
                f"into exactly two regions (found {len(pieces)}) -- a "
                "barrier that does not span the full board edge-to-edge "
                "does not separate anything; copper can route around its "
                "ends.",
            )
        )
    else:
        side_a, side_b = pieces[0], pieces[1]

    # Check 5: no copper intrusion into the barrier, on shared layers.
    from shapely.geometry import LineString, Point

    for seg in board.segments:
        seg_layers = _expand_copper_layers([seg.layer], board.copper_layers_ordered)
        if not (seg_layers & barrier_layers):
            continue
        geom = LineString(seg.points).buffer(seg.width / 2.0) if seg.width > 0 else LineString(seg.points)
        if geom.intersects(barrier_poly):
            report.violations.append(
                Violation(
                    "intrusion",
                    f"{seg.kind} {seg.ident} on layer {seg.layer} intrudes "
                    f"into barrier zone {barrier.ident}.",
                )
            )

    for via in board.vias:
        if not (via.layers & barrier_layers):
            continue
        geom = Point(via.x, via.y).buffer(via.radius)
        if geom.intersects(barrier_poly):
            report.violations.append(
                Violation(
                    "intrusion",
                    f"Via {via.ident} (layers {sorted(via.layers)}) intrudes "
                    f"into barrier zone {barrier.ident}.",
                )
            )

    for pad in board.pads:
        if not (pad.layers & barrier_layers):
            continue
        # Buffered by the pad's own conservative bounding-circle radius, not
        # just its center point -- a pad whose body overlaps the keepout
        # while its center sits just outside must still be caught (never
        # under-approximate a safety intrusion check).
        geom = Point(pad.x, pad.y).buffer(pad.radius) if pad.radius > 0 else Point(pad.x, pad.y)
        if geom.intersects(barrier_poly):
            report.violations.append(
                Violation(
                    "intrusion",
                    f"Pad {pad.ref}.{pad.number} (net {pad.net_name!r}) "
                    f"intrudes into barrier zone {barrier.ident}.",
                )
            )

    for cz in board.copper_zones:
        if not (cz.layers & barrier_layers):
            continue
        cz_poly = _polygon_or_none(cz.polygons)
        if cz_poly is None:
            continue
        if cz_poly.intersects(barrier_poly):
            report.violations.append(
                Violation(
                    "intrusion",
                    f"Zone {cz.ident} (net {cz.net_name!r}) intrudes into "
                    f"barrier zone {barrier.ident}.",
                )
            )

    # Check 6: no domain has copper on both sides / same side as the other.
    if side_a is not None and side_b is not None:

        def _side_of(x: float, y: float) -> str | None:
            pt = Point(x, y)
            in_a = side_a.contains(pt) or side_a.distance(pt) < 1e-6
            in_b = side_b.contains(pt) or side_b.distance(pt) < 1e-6
            if in_a and not in_b:
                return "A"
            if in_b and not in_a:
                return "B"
            return None  # ambiguous/inside barrier -- already reported by check 5 if it's copper

        hv_sides = {_side_of(p.x, p.y) for p in hv_pads} - {None}
        selv_sides = {_side_of(p.x, p.y) for p in selv_pads} - {None}

        if len(hv_sides) > 1:
            report.violations.append(
                Violation(
                    "far-side-crossing",
                    f"HV-domain pads are present on BOTH sides of the "
                    f"barrier ({sorted(hv_sides)}) -- the barrier does not "
                    "correspond to a real domain split.",
                )
            )
        if len(selv_sides) > 1:
            report.violations.append(
                Violation(
                    "far-side-crossing",
                    f"SELV-domain pads are present on BOTH sides of the "
                    f"barrier ({sorted(selv_sides)}) -- the barrier does not "
                    "correspond to a real domain split.",
                )
            )
        if hv_sides and selv_sides and hv_sides == selv_sides and len(hv_sides) == 1:
            report.violations.append(
                Violation(
                    "far-side-crossing",
                    "HV-domain and SELV-domain pads are on the SAME side of "
                    "the barrier -- the barrier does not separate the two "
                    "domains at all.",
                )
            )

    if report.violations:
        return "violation", report
    return "clean", report


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _print_report(state: str, report: Report, board_path: Path, manifest_path: Path) -> None:
    print(f"Board: {board_path}")
    print(f"Manifest: {manifest_path}")
    print(
        f"Copper layers: {len(report.copper_layers)} ({', '.join(report.copper_layers)}). "
        f"Footprints examined: {report.footprints_examined}. "
        f"Pads examined: {report.pads_examined} "
        f"(HV={report.hv_pads}, SELV={report.selv_pads}). "
        f"Copper items examined (segments+arcs+vias+non-keepout zones): "
        f"{report.copper_items_examined}. "
        f"Keepout zones found on board (any name): {report.keepout_zones_found_total}."
    )
    print(f"Barrier zone {'FOUND' if report.barrier_found else 'NOT FOUND'} (name={BARRIER_ZONE_NAME!r}).")
    print(f"Required minimum barrier width: {MIN_BARRIER_WIDTH_MM}mm (REINFORCED creepage; see module docstring).")

    gh = get_github_summary_path()

    if state == "clean":
        msg = (
            f"PASSED -- barrier keepout {BARRIER_ZONE_NAME!r} verified: spans all "
            f"{len(report.copper_layers)} copper layer(s), >= {MIN_BARRIER_WIDTH_MM}mm "
            f"wide throughout, bisects the board into exactly 2 regions, 0 copper "
            f"intrusions across {report.copper_items_examined} copper item(s) + "
            f"{report.pads_examined} pad(s) checked, 0 far-side domain crossings "
            f"across {report.hv_pads} HV pad(s) / {report.selv_pads} SELV pad(s)."
        )
        print(f"\n{msg}")
        if gh:
            with open(gh, "a") as f:
                f.write(f"### Isolation Keepout Gate -- PASSED\n{msg}\n")
        return

    print(f"\n=== VIOLATIONS: {len(report.violations)} ===")
    by_check: dict[str, list[Violation]] = {}
    for v in report.violations:
        by_check.setdefault(v.check, []).append(v)
    gh_lines: list[str] = []
    for check_name, vs in sorted(by_check.items()):
        print(f"\n  [{check_name}] {len(vs)} violation(s):")
        for v in vs[:50]:
            print(f"    {v.detail}")
            gh_lines.append(f"- `[{check_name}]` {v.detail}")
        if len(vs) > 50:
            print(f"    ... and {len(vs) - 50} more")

    print(f"\nFAILED -- {len(report.violations)} violation(s)")
    if gh:
        with open(gh, "a") as f:
            f.write(f"### Isolation Keepout Gate -- FAILED\n{len(report.violations)} violation(s)\n\n")
            for line in gh_lines[:200]:
                f.write(line + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--board", type=Path, default=DEFAULT_BOARD)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--barrier-name", type=str, default=BARRIER_ZONE_NAME)
    parser.add_argument("--min-width-mm", type=float, default=MIN_BARRIER_WIDTH_MM)
    args = parser.parse_args()

    try:
        state, report = run(args.board, args.manifest, args.barrier_name, args.min_width_mm)
    except GateError as exc:
        print("=== ISOLATION KEEPOUT GATE ERROR ===", file=sys.stderr)
        print(f"Reason: {exc}", file=sys.stderr)
        print(
            "GATE RESULT: ERROR -- not PASSED, not a violation. The gate "
            "could not run a trustworthy check.",
            file=sys.stderr,
        )
        gh = get_github_summary_path()
        if gh:
            with open(gh, "a") as f:
                f.write(f"### Isolation Keepout Gate -- GATE ERROR\n{exc}\n")
        sys.exit(EXIT_GATE_ERROR)

    _print_report(state, report, args.board, args.manifest)

    if state == "violation":
        sys.exit(EXIT_VIOLATION)
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
