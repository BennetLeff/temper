#!/usr/bin/env python3
"""Pairwise HV<->SELV creepage measurement: the PD2/PD3 sizing instrument.

Motivation
----------
The project must decide between pollution degree PD2 (8.0mm reinforced
creepage) and PD3 (12.6mm) -- see ``docs/ENVIRONMENTAL_SPEC.md`` Sec 3 and
commit ``c58c94d8``. Sizing the *cost* of PD3 requires knowing which
cross-domain (HV<->SELV) pad pairs fall below a given threshold, and that
number has, until this script, only ever been produced by throwaway scripts
embedded in evidence docs (``docs/evidence/2026-07-28-req-safe-01-
rederivation.md``: "The throwaway harness scripts were deliberately not
committed."). ``c58c94d8``'s own commit message reports two independent
measurements of the same quantity disagreeing -- 152 sub-12.6mm pairs on one
session's board state, 202 on a sibling's -- explained only after the fact as
differing board state, because no shared, re-runnable instrument existed to
tell the two apart directly. This script is that instrument.

What this is NOT
-----------------
``scripts/check_isolation_keepout.py`` is a **topological** gate: it verifies
a named barrier keepout zone exists, spans every copper layer, is wide
enough, and that HV/SELV pads sit on opposite sides of it. It does not
compute pairwise pad-to-pad distances at all. This script is the
**geometric** complement: it enumerates every cross-domain pad pair and
measures its real copper-to-copper creepage distance. It intentionally
reuses that gate's manifest-loading discipline, domain classification, and
pad-extraction conventions (see ``load_manifest``/``load_board`` below,
copied rather than imported for the same fail-closed-independence reason
``check_isolation_keepout.py`` itself gives for not importing
``check_domain_partition.py``'s internals).

This is a **measurement tool, not a gate**. It never exits non-zero because
violations were found -- only because it could not run a trustworthy
measurement at all (missing/empty inputs, zero HV or zero SELV pads, etc.,
mirroring this repo's anti-vacuous-truth discipline -- see
``scripts/check_vacuous_gates.py``). It is not wired into CI and must not
be. Do not add a --fail-on-violations flag to this script; if a gate is
wanted later, build one that imports this module's ``measure()`` function
rather than repurposing this script's exit code.

Which threshold is "current"
-----------------------------
``--min-creepage-mm`` defaults to the figure this repo actually enforces
today, not a literal duplicated here. As of this writing that is
``scripts/check_isolation_keepout.py``'s ``MIN_BARRIER_WIDTH_MM`` (imported,
not copied) -- **8.0mm**, the PD2 figure, matching
``docs/ENVIRONMENTAL_SPEC.md`` Sec 3 ("Pollution Degree: PD2") on
``origin/main`` as of this writing. PR #457 is reported to add a SSOT module
at ``packages/temper-placer/src/temper_placer/core/isolation_constants.py``
(``MIN_BARRIER_WIDTH_MM``); as of this writing that module does not exist on
``origin/main`` (checked via ``git log --all`` / ``git ls-tree`` -- it exists
only on an unmerged branch), so this script does NOT depend on it. When it
lands, switch this import over and delete this paragraph.

Separately, a sibling, unmerged branch (commit ``c58c94d8``, not an ancestor
of ``origin/main`` as of this writing) already re-targeted
``check_isolation_keepout.py``'s constant to 12.6mm (PD3) on its own branch.
That decision has not reached ``origin/main``. Use ``--min-creepage-mm 12.6``
explicitly to measure the PD3 case; do not assume it is the default just
because a sibling branch made it one there.

How pad geometry is measured
-----------------------------
Pad-edge to pad-edge, not centre to centre, via
``temper_placer.core.pad_geometry.pad_pair_distance`` -- the same exact,
shape-aware, rotation-aware model ``check_isolation_keepout.py`` already
imports from. An earlier U7 analysis that modelled pads as points at pin
centres under-reported creepage by 0.417mm; this script never does that.

Pad rotation: a pad's ``(at x y angle)`` angle in a ``.kicad_pcb`` file is
its ABSOLUTE world orientation already -- it is not added to the parent
footprint's angle. This is the same finding ``scripts/check_pad_
orientation.py`` exists to police (docs/evidence/2026-07-29-intra-component-
shorts-root-cause.md) and the same convention
``temper_placer.io._parse_modules.py`` uses (see its ``pad_abs_rotation_deg``
comment). Verified directly against this repo's own ground truth before
relying on it: computing T1 pin1<->pin4 and K1 pin13<->pinA1 with this
convention reproduces the exact, previously-published 9.100mm / 8.000mm
figures (docs/evidence/2026-07-28-req-safe-01-rederivation.md); adding the
footprint angle to the pad angle instead reproduces neither (T1 comes out
7.800mm).

Pad *position* (local offset -> world), by contrast, needs the footprint's
own rotation applied: ``world = footprint_position + R(+theta) *
local_offset``, using the SAME sign convention ``check_isolation_keepout.py``
and ``temper_placer.io._parse_modules.py`` both already use (confirmed by
reading ``_parse_modules.py``'s own ``rotated_cx``/``rotated_cy``
computation). This is a genuinely open question elsewhere in this repo's own
history: docs/evidence/2026-07-28-req-safe-01-rederivation.md's "Rotation-
convention caveat" section found this repo's own parser/writer use
``R(+theta)`` while KiCad's own internal convention is ``R(-theta)``, that
the two conventions agree everywhere except pairs involving a 90/270-degree-
rotated footprint's position relative to ANOTHER footprint, and left which
one is "real" as an open question (weak evidence favoured ``R(+theta)``).
This script therefore does not silently pick a side and stay quiet about it:
by default (disable with ``--no-rotation-sensitivity-check``) it recomputes
every violating pair under BOTH conventions and flags any pair whose
PASS/FAIL verdict differs between them, instead of reporting a number that
might depend on an unresolved convention question without saying so. As it
happens,
``pcb/temper.kicad_pcb`` has zero back-side (B.Cu) footprints as of this
writing, so the position-mirroring half of this ambiguity (see ``_rotate``
usage below) never triggers either way on this board; this is checked at
runtime, not assumed, and reported in ``Report.back_side_pads_found``.

Body-free vs body-crossing
---------------------------
A surface creepage path that runs under a component's own moulded body
cannot be lengthened by a routed slot -- the slot would have to be milled
underneath a mounted part. Classification per pair, for every pair below
the threshold: build each footprint's body outline from its ``F.Fab`` graphic
items (falling back to ``F.CrtYd`` when a footprint carries no ``F.Fab``
geometry), as the CONVEX HULL of every point on those layers in board
coordinates. Convex hull is a deliberate, documented over-approximation
(never under-approximation) of the true body outline for any non-convex
part: the unsafe direction here is under-reporting a body's extent (which
would recommend "add a slot" as a fix where a slot is physically impossible
because it would have to run under the part), not over-reporting it (which
merely mis-labels a genuinely-fixable pair as unfixable, a conservative
error). Then take the straight-line segment between the two pads' nearest
copper-core points (the same segment ``pad_pair_distance`` implicitly
measures along) and test it against every footprint's body polygon on the
board -- not just the two endpoint pads' own footprints, since a third
component's body can physically sit between two other components' pads too.
A pair is ``body_crossing`` if that segment's intersection with any body
polygon has non-trivial length (> 0.01mm, to reject a mere boundary touch at
one endpoint); ``body_free`` if it crosses none; ``unknown`` if neither pad's
own footprint carries usable F.Fab/F.CrtYd geometry (7 of 168 footprints on
this board as of this writing -- C1, C6, F1, L2, R30, RT1, U27) and no
crossing was otherwise found, since a genuine own-body crossing cannot be
ruled out for those without guessing. This is reported explicitly, never
silently folded into ``body_free``.

Denominator discipline
-----------------------
Every report states ``pairs_examined = hv_pads * selv_pads`` -- the full
cross-domain pad-pair space, not just the pairs that happened to violate.
"0 violations" can never silently mean "found nothing": if ``hv_pads`` or
``selv_pads`` is zero, this script raises ``ToolError`` (never reports a
clean 0-violation result for an empty domain), matching
``check_isolation_keepout.py``'s and ``check_vacuous_gates.py``'s discipline.

Determinism
-----------
No ``kicad-cli`` invocation anywhere in this script -- board and manifest
are read directly via ``kiutils``/``yaml``, so this tool's output is fully
deterministic for a fixed ``(board, manifest, threshold)`` input, unlike
``kicad-cli``-based DRC (documented +-2 run-to-run non-determinism on this
board).

Usage
-----
  uv run --no-sync python scripts/measure_cross_domain_creepage.py
  uv run --no-sync python scripts/measure_cross_domain_creepage.py --min-creepage-mm 12.6
  uv run --no-sync python scripts/measure_cross_domain_creepage.py \\
      --min-creepage-mm 8.0 --compare-to-mm 12.6
  uv run --no-sync python scripts/measure_cross_domain_creepage.py --json out.json
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.path_setup import setup_temper_placer_path  # noqa: E402
from _lib.provenance import collect as collect_provenance  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root()
setup_temper_placer_path(REPO_ROOT)  # repo's own packages/*/src ahead of any venv copy

# Reused, not duplicated: the currently-enforced minimum, wherever it
# actually lives today (see module docstring "Which threshold is current").
from check_isolation_keepout import (  # noqa: E402
    MIN_BARRIER_WIDTH_MM as CURRENT_ENFORCED_MIN_CREEPAGE_MM,
)

from temper_placer.core.pad_geometry import (  # noqa: E402
    DEFAULT_ROUNDRECT_RATIO,
    pad_core_polygon,
    pad_pair_distance,
)

DEFAULT_BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"
DEFAULT_MANIFEST = REPO_ROOT / "elec" / "domain_manifest.yaml"

EXIT_OK = 0
EXIT_TOOL_ERROR = 5

# A LineString-vs-body-polygon intersection shorter than this is treated as a
# boundary touch (e.g. a pad sitting right at its own footprint's courtyard
# edge), not a genuine under-the-body crossing. 10 microns, well below any
# manufacturing or measurement tolerance on this board.
_BODY_CROSSING_LENGTH_EPS_MM = 0.01

# Points-per-quarter-circle used only for approximating FpCircle/FpArc body
# outline points before taking the convex hull -- coarse is fine here, the
# hull only needs to bound the true shape, not trace it exactly.
_ARC_APPROX_POINTS = 16


class ToolError(Exception):
    """Raised for any condition that must fail closed -- never a silent 0."""


# ---------------------------------------------------------------------------
# Domain manifest -- same discipline as check_isolation_keepout.py's loader
# (self-contained on purpose: this tool's correctness must not depend on a
# sibling script's internal representation changing out from under it).
# Exact literal net name matching only -- never a prefix or naming-
# convention guess (elec/domain_manifest.yaml's own ground rule; a net named
# "+340V_BUS" was actually the ~170V half-bus).
# ---------------------------------------------------------------------------


@dataclass
class Manifest:
    hv_nets: frozenset[str]
    selv_nets: frozenset[str]


def load_manifest(path: Path) -> Manifest:
    if not path.is_file():
        raise ToolError(f"domain manifest not found: {path}")
    raw_text = path.read_text(encoding="utf-8")
    if not raw_text.strip():
        raise ToolError(f"domain manifest is empty: {path}")

    import yaml

    try:
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise ToolError(f"domain manifest is not valid YAML: {exc}") from exc

    if not isinstance(data, dict):
        raise ToolError(f"domain manifest must be a mapping at the top level: {path}")

    domains = data.get("domains")
    if not isinstance(domains, dict) or not domains:
        raise ToolError(
            "domain manifest has no non-empty 'domains' mapping -- an empty "
            "or absent domain declaration must fail closed, not measure "
            "vacuously"
        )

    def _nets_for(domain_name: str) -> frozenset[str]:
        entry = domains.get(domain_name)
        if not isinstance(entry, dict):
            raise ToolError(f"domain manifest has no {domain_name!r} domain mapping")
        nets = entry.get("nets")
        if not isinstance(nets, list) or not nets:
            raise ToolError(f"domain manifest's {domain_name!r} domain has zero nets declared")
        for n in nets:
            if not isinstance(n, str) or not n:
                raise ToolError(f"domain manifest's {domain_name!r} domain has a non-string/empty net entry")
        return frozenset(nets)

    hv_nets = _nets_for("HV")
    selv_nets = _nets_for("SELV")
    overlap = hv_nets & selv_nets
    if overlap:
        raise ToolError(f"domain manifest declares net(s) in BOTH HV and SELV: {sorted(overlap)}")

    return Manifest(hv_nets=hv_nets, selv_nets=selv_nets)


# ---------------------------------------------------------------------------
# Board loading
# ---------------------------------------------------------------------------


def _rotate_plus_theta(x: float, y: float, angle_deg: float | None) -> tuple[float, float]:
    """R(+theta): the sign convention this repo's own parser/writer
    (temper_placer.io._parse_modules.py / _write_modules.py) and
    check_isolation_keepout.py both use for local-offset -> world-position.
    See module docstring's "How pad geometry is measured" section for the
    ground-truth verification and the open-question caveat this is NOT the
    only convention seen in this repo's history."""
    a = math.radians(angle_deg or 0.0)
    return (x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a))


def _rotate_minus_theta(x: float, y: float, angle_deg: float | None) -> tuple[float, float]:
    """R(-theta): KiCad's own internal footprint-rotation convention per
    docs/evidence/2026-07-28-req-safe-01-rederivation.md's "Rotation-
    convention caveat" and scripts/check_pad_orientation.py's documented
    y-down-frame formula. Used only by the sensitivity check, never as the
    primary measurement."""
    a = math.radians(angle_deg or 0.0)
    return (x * math.cos(a) + y * math.sin(a), -x * math.sin(a) + y * math.cos(a))


@dataclass(frozen=True)
class PadInfo:
    ref: str
    number: str
    net_name: str
    domain: str  # "HV" | "SELV"
    width: float
    height: float
    shape: str
    roundrect_ratio: float
    cx: float
    cy: float
    cx_alt: float  # position under R(-theta), for the sensitivity check
    cy_alt: float
    rotation_rad: float
    is_back_side: bool

    @property
    def label(self) -> str:
        return f"{self.ref}.{self.number}({self.net_name})"

    def spec(self, *, alt: bool = False) -> tuple[float, float, str, float, float, float, float]:
        """``pad_geometry.pad_pair_distance``'s pad tuple."""
        cx = self.cx_alt if alt else self.cx
        cy = self.cy_alt if alt else self.cy
        return (self.width, self.height, self.shape, cx, cy, self.rotation_rad, self.roundrect_ratio)


@dataclass
class FootprintBody:
    ref: str
    polygon: object | None  # shapely Polygon, or None if no usable outline
    source: str  # "F.Fab" | "F.CrtYd" | "none"


@dataclass
class BoardData:
    footprints_total: int
    pads_total: int
    hv_pads: list[PadInfo]
    selv_pads: list[PadInfo]
    bodies: dict[str, FootprintBody]
    back_side_pads_found: int


def _local_points_of_graphic_item(item) -> list[tuple[float, float]]:
    """Best-effort local-frame point extraction for a footprint graphic
    item, used only to build a body-outline convex hull -- see module
    docstring "Body-free vs body-crossing". Circles/arcs are approximated by
    sampled points on their true boundary (never inside it), which the
    convex hull then over-, never under-, bounds."""
    kind = type(item).__name__
    if kind == "FpLine":
        return [(item.start.X, item.start.Y), (item.end.X, item.end.Y)]
    if kind == "FpRect":
        x0, y0 = item.start.X, item.start.Y
        x1, y1 = item.end.X, item.end.Y
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    if kind == "FpPoly":
        return [(p.X, p.Y) for p in item.coordinates]
    if kind == "FpCircle":
        cx, cy = item.center.X, item.center.Y
        ex, ey = item.end.X, item.end.Y
        r = math.hypot(ex - cx, ey - cy)
        return [
            (cx + r * math.cos(2 * math.pi * k / _ARC_APPROX_POINTS), cy + r * math.sin(2 * math.pi * k / _ARC_APPROX_POINTS))
            for k in range(_ARC_APPROX_POINTS)
        ]
    if kind == "FpArc":
        return [(item.start.X, item.start.Y), (item.mid.X, item.mid.Y), (item.end.X, item.end.Y)]
    return []  # FpText, FpTextBox, Image, ... carry no body-relevant geometry


def _footprint_body_polygon(fp) -> FootprintBody:
    from shapely.geometry import MultiPoint

    fx, fy = fp.position.X, fp.position.Y
    fangle = fp.position.angle or 0.0
    flipped = str(fp.layer or "F.Cu").startswith("B.")
    ref = (fp.properties or {}).get("Reference") or "<noref>"

    def _collect(layers: frozenset[str]) -> list[tuple[float, float]]:
        pts: list[tuple[float, float]] = []
        for item in fp.graphicItems:
            if getattr(item, "layer", None) not in layers:
                continue
            for lx, ly in _local_points_of_graphic_item(item):
                if flipped:
                    lx = -lx
                dx, dy = _rotate_plus_theta(lx, ly, fangle)
                pts.append((fx + dx, fy + dy))
        return pts

    for layers, source in (
        (frozenset({"F.Fab", "B.Fab"}), "F.Fab"),
        (frozenset({"F.CrtYd", "B.CrtYd"}), "F.CrtYd"),
    ):
        pts = _collect(layers)
        if len(pts) < 3:
            continue
        hull = MultiPoint(pts).convex_hull
        if hull.geom_type == "Polygon" and not hull.is_empty:
            return FootprintBody(ref=ref, polygon=hull, source=source)

    return FootprintBody(ref=ref, polygon=None, source="none")


def load_board(board_path: Path, manifest: Manifest) -> BoardData:
    if not board_path.is_file():
        raise ToolError(f"board not found: {board_path}")
    try:
        from kiutils.board import Board
    except ImportError as exc:
        raise ToolError(f"kiutils is not installed: {exc}") from exc
    try:
        board = Board.from_file(str(board_path))
    except Exception as exc:  # kiutils raises plain Exception/ValueError on malformed input
        raise ToolError(f"failed to parse board {board_path}: {exc}") from exc

    if not board.footprints:
        raise ToolError(f"board has zero footprints: {board_path}")

    hv_pads: list[PadInfo] = []
    selv_pads: list[PadInfo] = []
    pads_total = 0
    back_side_pads_found = 0
    bodies: dict[str, FootprintBody] = {}

    for fp in board.footprints:
        ref = (fp.properties or {}).get("Reference") or "<noref>"
        bodies[ref] = _footprint_body_polygon(fp)

        fx, fy = fp.position.X, fp.position.Y
        fangle = fp.position.angle or 0.0
        flipped = str(fp.layer or "F.Cu").startswith("B.")

        for pad in fp.pads:
            pads_total += 1
            net_name = pad.net.name if pad.net is not None else ""
            domain = "HV" if net_name in manifest.hv_nets else "SELV" if net_name in manifest.selv_nets else None
            if domain is None:
                continue

            lx, ly = pad.position.X, pad.position.Y
            if flipped:
                lx = -lx
            dx, dy = _rotate_plus_theta(lx, ly, fangle)
            cx, cy = fx + dx, fy + dy
            adx, ady = _rotate_minus_theta(lx, ly, fangle)
            cx_alt, cy_alt = fx + adx, fy + ady

            if flipped:
                back_side_pads_found += 1

            # Pad angle is ABSOLUTE as written in a placed .kicad_pcb -- see
            # module docstring "How pad geometry is measured". Not exercised
            # for flipped footprints on this board (none exist as of this
            # writing, checked above); the sign choice here for that case is
            # a best-effort, UNVERIFIED mirror and is flagged via
            # back_side_pads_found rather than silently trusted.
            pad_angle_deg = pad.position.angle or 0.0
            rotation_rad = math.radians(-pad_angle_deg if flipped else pad_angle_deg)

            size_x = getattr(pad.size, "X", 0.0) or 0.0
            size_y = getattr(pad.size, "Y", 0.0) or 0.0
            shape = getattr(pad, "shape", None) or "rect"
            roundrect_ratio = getattr(pad, "roundrectRatio", None)
            if roundrect_ratio is None:
                roundrect_ratio = DEFAULT_ROUNDRECT_RATIO

            info = PadInfo(
                ref=ref,
                number=pad.number,
                net_name=net_name,
                domain=domain,
                width=size_x,
                height=size_y,
                shape=shape,
                roundrect_ratio=roundrect_ratio,
                cx=cx,
                cy=cy,
                cx_alt=cx_alt,
                cy_alt=cy_alt,
                rotation_rad=rotation_rad,
                is_back_side=flipped,
            )
            (hv_pads if domain == "HV" else selv_pads).append(info)

    if pads_total == 0:
        raise ToolError(f"board has zero pads across {len(board.footprints)} footprint(s)")
    if not hv_pads:
        raise ToolError(
            "zero HV-domain-classified pads found on the board -- nothing of "
            "the HV domain exists to measure (anti-vacuous-truth: this is a "
            "tool error, not '0 violations')"
        )
    if not selv_pads:
        raise ToolError(
            "zero SELV-domain-classified pads found on the board -- nothing "
            "of the SELV domain exists to measure (anti-vacuous-truth: this "
            "is a tool error, not '0 violations')"
        )

    return BoardData(
        footprints_total=len(board.footprints),
        pads_total=pads_total,
        hv_pads=hv_pads,
        selv_pads=selv_pads,
        bodies=bodies,
        back_side_pads_found=back_side_pads_found,
    )


# ---------------------------------------------------------------------------
# Pairwise measurement
# ---------------------------------------------------------------------------


@dataclass
class PairFinding:
    hv: PadInfo
    selv: PadInfo
    distance_mm: float
    body_class: str = "unclassified"  # "body_free" | "body_crossing" | "unknown" | "unclassified"
    crossed_by: tuple[str, ...] = ()
    convention_sensitive: bool | None = None  # None = not checked
    distance_mm_alt: float | None = None  # under R(-theta), if checked

    @property
    def label(self) -> str:
        return f"{self.hv.label} <-> {self.selv.label}"


def _classify_body(hv: PadInfo, selv: PadInfo, bodies: dict[str, FootprintBody]) -> tuple[str, tuple[str, ...]]:
    from shapely.ops import nearest_points

    core_hv = pad_core_polygon(hv.width, hv.height, hv.shape, hv.cx, hv.cy, hv.rotation_rad, hv.roundrect_ratio)
    core_selv = pad_core_polygon(
        selv.width, selv.height, selv.shape, selv.cx, selv.cy, selv.rotation_rad, selv.roundrect_ratio
    )
    p1, p2 = nearest_points(core_hv, core_selv)

    from shapely.geometry import LineString

    line = LineString([p1, p2])

    crossed: list[str] = []
    for ref, body in bodies.items():
        if body.polygon is None:
            continue
        inter = line.intersection(body.polygon)
        if inter.length > _BODY_CROSSING_LENGTH_EPS_MM:
            crossed.append(ref)

    if crossed:
        return "body_crossing", tuple(sorted(crossed))

    own_hv_unknown = bodies.get(hv.ref) is None or bodies[hv.ref].polygon is None
    own_selv_unknown = bodies.get(selv.ref) is None or bodies[selv.ref].polygon is None
    if own_hv_unknown or own_selv_unknown:
        return "unknown", ()

    return "body_free", ()


def measure_all_pairs(hv_pads: list[PadInfo], selv_pads: list[PadInfo]) -> list[PairFinding]:
    """Exact pad-edge-to-pad-edge distance for EVERY cross-domain pair --
    this is the full denominator, not a pre-filtered subset. Cheap enough to
    brute-force: ~21k pairs on the real board measure in ~1.3s."""
    findings: list[PairFinding] = []
    for hv in hv_pads:
        for selv in selv_pads:
            d = pad_pair_distance(hv.spec(), selv.spec())
            findings.append(PairFinding(hv=hv, selv=selv, distance_mm=d))
    return findings


def classify_violations(
    findings: list[PairFinding],
    threshold_mm: float,
    bodies: dict[str, FootprintBody],
    *,
    check_rotation_sensitivity: bool = True,
) -> list[PairFinding]:
    """Return the subset of *findings* below *threshold_mm*, with body
    classification (and, optionally, rotation-convention sensitivity)
    computed only for that subset -- the expensive per-pair checks are never
    run against the full denominator, only the pairs that matter.

    Builds NEW ``PairFinding`` objects rather than mutating *findings* in
    place: a pair violating at 8.0mm is also a member of the set violating
    at 12.6mm, so if this function mutated shared objects, classifying a
    second threshold against the same ``all_findings`` list would silently
    overwrite the first threshold's already-reported ``body_class``/
    ``convention_sensitive`` (computed relative to a DIFFERENT threshold) on
    objects a caller may still be holding a reference to. Caught during this
    script's own development: printing the 8.0mm report before running the
    12.6mm comparison, then re-serializing the 8.0mm report to JSON
    afterwards, showed different rotation-sensitivity counts for the exact
    same report depending on when it was read -- a real aliasing bug, not a
    measurement one. Returning fresh objects per threshold makes each
    ``Report.violations`` list immutable in practice once returned."""
    violating: list[PairFinding] = []
    for f in findings:
        if f.distance_mm >= threshold_mm:
            continue
        body_class, crossed_by = _classify_body(f.hv, f.selv, bodies)
        distance_mm_alt: float | None = None
        convention_sensitive: bool | None = None
        if check_rotation_sensitivity:
            distance_mm_alt = pad_pair_distance(f.hv.spec(alt=True), f.selv.spec(alt=True))
            convention_sensitive = (distance_mm_alt < threshold_mm) != (f.distance_mm < threshold_mm)
        violating.append(
            PairFinding(
                hv=f.hv,
                selv=f.selv,
                distance_mm=f.distance_mm,
                body_class=body_class,
                crossed_by=crossed_by,
                convention_sensitive=convention_sensitive,
                distance_mm_alt=distance_mm_alt,
            )
        )
    violating.sort(key=lambda f: f.distance_mm)
    return violating


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


@dataclass
class Report:
    board_path: Path
    manifest_path: Path
    threshold_mm: float
    footprints_total: int
    pads_total: int
    hv_pads_total: int
    selv_pads_total: int
    pairs_examined: int
    back_side_pads_found: int
    footprints_with_body_outline: int
    violations: list[PairFinding] = field(default_factory=list)


def measure(
    board_path: Path,
    manifest_path: Path,
    threshold_mm: float,
    *,
    check_rotation_sensitivity: bool = True,
) -> tuple[Report, list[PairFinding], dict[str, FootprintBody]]:
    """Run the full measurement. Returns (report_at_threshold, all_findings,
    bodies) -- callers doing a differential comparison should reuse
    ``all_findings``/``bodies`` rather than re-parsing the board for a
    second threshold (see ``measure_at_second_threshold``)."""
    manifest = load_manifest(manifest_path)
    board = load_board(board_path, manifest)

    all_findings = measure_all_pairs(board.hv_pads, board.selv_pads)
    violations = classify_violations(
        all_findings, threshold_mm, board.bodies, check_rotation_sensitivity=check_rotation_sensitivity
    )

    report = Report(
        board_path=board_path,
        manifest_path=manifest_path,
        threshold_mm=threshold_mm,
        footprints_total=board.footprints_total,
        pads_total=board.pads_total,
        hv_pads_total=len(board.hv_pads),
        selv_pads_total=len(board.selv_pads),
        pairs_examined=len(board.hv_pads) * len(board.selv_pads),
        back_side_pads_found=board.back_side_pads_found,
        footprints_with_body_outline=sum(1 for b in board.bodies.values() if b.polygon is not None),
        violations=violations,
    )
    return report, all_findings, board.bodies


def measure_at_second_threshold(
    base_report: Report,
    all_findings: list[PairFinding],
    bodies: dict[str, FootprintBody],
    threshold_mm: float,
    *,
    check_rotation_sensitivity: bool = True,
) -> Report:
    """Re-classify the SAME parsed board/pair set at a different threshold --
    no re-parse, no re-measure of distances (they don't depend on the
    threshold). This is what makes requirement 7 ("cheap enough to run
    twice") true in practice: the expensive board parse and the O(pairs)
    exact-distance pass happen exactly once regardless of how many
    thresholds are compared."""
    violations = classify_violations(
        all_findings, threshold_mm, bodies, check_rotation_sensitivity=check_rotation_sensitivity
    )
    return Report(
        board_path=base_report.board_path,
        manifest_path=base_report.manifest_path,
        threshold_mm=threshold_mm,
        footprints_total=base_report.footprints_total,
        pads_total=base_report.pads_total,
        hv_pads_total=base_report.hv_pads_total,
        selv_pads_total=base_report.selv_pads_total,
        pairs_examined=base_report.pairs_examined,
        back_side_pads_found=base_report.back_side_pads_found,
        footprints_with_body_outline=base_report.footprints_with_body_outline,
        violations=violations,
    )


def _component_attribution(violations: list[PairFinding]) -> list[tuple[str, float, int]]:
    """[(ref, worst_distance_mm, pair_count), ...] sorted worst-first --
    "a list of parts to fix," per this tool's own requirement."""
    by_ref: dict[str, list[float]] = {}
    for f in violations:
        by_ref.setdefault(f.hv.ref, []).append(f.distance_mm)
        by_ref.setdefault(f.selv.ref, []).append(f.distance_mm)
    out = [(ref, min(ds), len(ds)) for ref, ds in by_ref.items()]
    out.sort(key=lambda t: t[1])
    return out


def format_report(report: Report, *, limit: int = 50) -> str:
    lines: list[str] = []
    lines.append(f"Board: {report.board_path}")
    lines.append(f"Manifest: {report.manifest_path}")
    lines.append(f"Threshold: {report.threshold_mm}mm")
    lines.append(
        f"Footprints: {report.footprints_total} ({report.footprints_with_body_outline} with a usable "
        f"F.Fab/F.CrtYd body outline). Pads: {report.pads_total} total "
        f"(HV={report.hv_pads_total}, SELV={report.selv_pads_total})."
    )
    lines.append(
        f"DENOMINATOR -- cross-domain pairs examined: {report.pairs_examined} "
        f"({report.hv_pads_total} HV x {report.selv_pads_total} SELV, every one measured)."
    )
    if report.back_side_pads_found:
        lines.append(
            f"WARNING: {report.back_side_pads_found} pad(s) found on a back-side (B.Cu) footprint -- "
            "this script's flip/rotation handling for that case is UNVERIFIED (see module docstring)."
        )
    else:
        lines.append("Back-side (B.Cu) footprints: 0 -- flip-convention ambiguity does not apply to this board.")

    n = len(report.violations)
    body_free = sum(1 for f in report.violations if f.body_class == "body_free")
    body_crossing = sum(1 for f in report.violations if f.body_class == "body_crossing")
    unknown = sum(1 for f in report.violations if f.body_class == "unknown")
    sensitive = sum(1 for f in report.violations if f.convention_sensitive)

    lines.append("")
    lines.append(f"VIOLATIONS (< {report.threshold_mm}mm): {n} of {report.pairs_examined} pairs examined.")
    lines.append(f"  body_free (fixable by a routed slot):     {body_free}")
    lines.append(f"  body_crossing (NOT fixable by a slot):    {body_crossing}")
    lines.append(f"  unknown (no body outline data):           {unknown}")
    if sensitive:
        lines.append(
            f"  rotation-convention-sensitive (verdict flips under R(-theta)): {sensitive} "
            "-- see module docstring's open-question caveat."
        )

    if report.violations:
        lines.append("")
        lines.append("Worst pairs (smallest gap first):")
        for f in report.violations[:limit]:
            tag = {"body_free": "FREE", "body_crossing": "BODY", "unknown": "UNK "}[f.body_class]
            sens = " [CONVENTION-SENSITIVE]" if f.convention_sensitive else ""
            crossed = f" (crosses: {', '.join(f.crossed_by)})" if f.crossed_by else ""
            lines.append(f"  [{tag}] {f.distance_mm:7.3f}mm  {f.label}{crossed}{sens}")
        if n > limit:
            lines.append(f"  ... and {n - limit} more")

        lines.append("")
        lines.append("Components to fix (worst gap first):")
        for ref, worst, count in _component_attribution(report.violations)[:limit]:
            lines.append(f"  {ref}: worst gap {worst:.3f}mm, involved in {count} violating pair(s)")

    return "\n".join(lines)


def format_diff(report_a: Report, report_b: Report) -> str:
    """Requirement 7 -- differential mode: what does moving the threshold
    from report_a to report_b actually cost, in pairs and in parts?"""
    assert report_a.threshold_mm != report_b.threshold_mm
    lo, hi = (report_a, report_b) if report_a.threshold_mm < report_b.threshold_mm else (report_b, report_a)

    lo_pairs = {f.label for f in lo.violations}
    delta = [f for f in hi.violations if f.label not in lo_pairs]
    delta.sort(key=lambda f: f.distance_mm)

    body_free = sum(1 for f in delta if f.body_class == "body_free")
    body_crossing = sum(1 for f in delta if f.body_class == "body_crossing")
    unknown = sum(1 for f in delta if f.body_class == "unknown")

    lines = ["", "=" * 78, f"DIFFERENTIAL: {lo.threshold_mm}mm -> {hi.threshold_mm}mm", "=" * 78]
    lines.append(f"At {lo.threshold_mm}mm: {len(lo.violations)} of {lo.pairs_examined} pairs violate.")
    lines.append(f"At {hi.threshold_mm}mm: {len(hi.violations)} of {hi.pairs_examined} pairs violate.")
    lines.append(
        f"DELTA (the measured cost of moving {lo.threshold_mm}mm -> {hi.threshold_mm}mm): "
        f"{len(delta)} newly-violating pair(s)."
    )
    lines.append(f"  body_free (fixable by a routed slot):  {body_free}")
    lines.append(f"  body_crossing (not fixable by a slot):  {body_crossing}")
    lines.append(f"  unknown:                                 {unknown}")
    if delta:
        lines.append("")
        lines.append("Parts newly implicated by the delta (worst gap first):")
        for ref, worst, count in _component_attribution(delta):
            lines.append(f"  {ref}: worst gap {worst:.3f}mm, involved in {count} newly-violating pair(s)")
    return "\n".join(lines)


def report_to_dict(report: Report) -> dict:
    return {
        "provenance": collect_provenance(REPO_ROOT),
        "board": str(report.board_path),
        "manifest": str(report.manifest_path),
        "threshold_mm": report.threshold_mm,
        "footprints_total": report.footprints_total,
        "footprints_with_body_outline": report.footprints_with_body_outline,
        "pads_total": report.pads_total,
        "hv_pads_total": report.hv_pads_total,
        "selv_pads_total": report.selv_pads_total,
        "pairs_examined": report.pairs_examined,
        "back_side_pads_found": report.back_side_pads_found,
        "violation_count": len(report.violations),
        "violations": [
            {
                "hv": f.hv.label,
                "selv": f.selv.label,
                "distance_mm": f.distance_mm,
                "distance_mm_alt_rotation_convention": f.distance_mm_alt,
                "convention_sensitive": f.convention_sensitive,
                "body_class": f.body_class,
                "crossed_by": list(f.crossed_by),
            }
            for f in report.violations
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--board", type=Path, default=DEFAULT_BOARD)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--min-creepage-mm",
        type=float,
        default=CURRENT_ENFORCED_MIN_CREEPAGE_MM,
        help=f"Creepage threshold in mm (default: {CURRENT_ENFORCED_MIN_CREEPAGE_MM}, "
        "the project's currently-enforced figure -- see module docstring)",
    )
    parser.add_argument(
        "--compare-to-mm",
        type=float,
        default=None,
        help="Also measure at this second threshold and report the differential "
        "(requirement 7 -- e.g. --min-creepage-mm 8.0 --compare-to-mm 12.6)",
    )
    parser.add_argument("--limit", type=int, default=50, help="Max violating pairs / parts to print per section")
    parser.add_argument(
        "--no-rotation-sensitivity-check",
        action="store_true",
        help="Skip the R(+theta)/R(-theta) convention cross-check (faster, less rigorous)",
    )
    parser.add_argument("--json", type=Path, default=None, help="Write the full structured result as JSON")
    args = parser.parse_args()

    try:
        report, all_findings, bodies = measure(
            args.board,
            args.manifest,
            args.min_creepage_mm,
            check_rotation_sensitivity=not args.no_rotation_sensitivity_check,
        )
    except ToolError as exc:
        print("=== CROSS-DOMAIN CREEPAGE MEASUREMENT: TOOL ERROR ===", file=sys.stderr)
        print(f"Reason: {exc}", file=sys.stderr)
        print(
            "RESULT: ERROR -- not a measurement, not '0 violations'. This tool could "
            "not run a trustworthy measurement at all.",
            file=sys.stderr,
        )
        sys.exit(EXIT_TOOL_ERROR)

    print(format_report(report, limit=args.limit))

    outputs = [report]
    if args.compare_to_mm is not None:
        report_b = measure_at_second_threshold(
            report,
            all_findings,
            bodies,
            args.compare_to_mm,
            check_rotation_sensitivity=not args.no_rotation_sensitivity_check,
        )
        print(format_diff(report, report_b))
        outputs.append(report_b)

    if args.json is not None:
        import json

        payload = {"reports": [report_to_dict(r) for r in outputs]}
        args.json.write_text(json.dumps(payload, indent=2))
        print(f"\nWrote JSON to {args.json}")

    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
