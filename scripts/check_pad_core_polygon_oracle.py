#!/usr/bin/env python3
"""Gate: every implementation that orients a pad's copper RECTANGLE agrees
with pcbnew, at angles that are not multiples of 90 degrees.

What this gate is for
---------------------
KiCad rotates a footprint child -- a pad offset, a courtyard vertex, a
pad's own copper outline -- **clockwise**, ``R(-theta)``. This repo has
reimplemented that formula by hand more than a dozen times and got the
sign wrong in twelve of them (see
``scripts/check_no_raw_rotation_trig.py``'s docstring and
``docs/evidence/2026-07-29-cross-domain-creepage-rotation-convention.md``).

``scripts/check_pad_world_position_oracle.py`` (PR #1376) closes the
*point* half of that: where a pad's CENTRE lands. This gate closes the
second, independent half: the orientation of the pad's copper
**rectangle** about that centre.

They are genuinely independent code paths.
``core/pad_geometry.py::pad_core_polygon`` and ``::pad_polygon`` rotated
the rectangle with ``shapely.affinity.rotate(+degrees)`` -- R(+theta) --
bypassing the sanctioned bridge entirely, as did their bit-exact Rust
twin ``clearance_geometry.rs::pad_core``. Meanwhile
``scripts/check_board_containment.py::_pad_polygons`` rotated the
*identical object* through
``kicad_transform.shapely_rotation_angle_deg``, i.e. R(-theta). Both
cannot be right.

Why it was invisible, and why that is the dangerous part
--------------------------------------------------------
At a multiple of 90 degrees the two conventions produce the **same corner
set** -- they differ only in the ring's traversal order, which no distance
or containment query can see. Every one of the 527 pads on
``pcb/temper.kicad_pcb`` sits at a multiple of 90 (0:58, 90:202, 180:175,
270:92, none elsewhere). That is exactly why ``pad_pair_distance``
reproduced ``kicad-cli`` to four decimals and was believed correct:
**correct by coincidence of placement, not by construction.** The placer
is free to emit a non-90 rotation at any time, and on the day it does,
every clearance and creepage number computed from a pad polygon becomes a
mirror image of the truth with nothing to announce it.

Measured on a 4x1 mm rectangular pad against pcbnew 10.0.5: corner sets
are **identical at 0/90/180/270** and **mirrored at 30/45/23/-37.5/135/61**
(see ``docs/evidence/2026-08-18-pad-core-polygon-rotation-convention.md``).

How the verdict is reached
--------------------------
Ground truth is pcbnew itself -- KiCad's own placement engine, not a
reimplementation of KiCad's rotation formula. ``scripts/
kicad_pad_polygon_oracle.py`` builds a rectangular pad at a given size,
centre and orientation and reads back the corners of the polygon KiCad
fills with copper. Those answers are pinned in
``scripts/pad_core_polygon_oracle_corpus.json``.

Every registered site is then **resolved by import and called** -- never
source-scanned. A source scan is not enough here for the same reason it
was not enough in PR #1376: ``pad_core_polygon``'s Python body is a
handful of Shapely calls whose *arithmetic* lives in GEOS, and the Rust
twin's body lives in a ``.so`` that a reader of the Python cannot see at
all. Only calling it can tell you which way it turns.

Rectangular pads only, deliberately: for ``shape == "rect"`` the corner
radius is 0, so the pad's copper outline IS ``pad_core_polygon``'s core
and pcbnew's own polygon is an exact 4-corner rectangle. No arc
approximation enters either side of the comparison.

Anti-vacuity
------------
A corpus that could not tell the two conventions apart would let this
gate pass on either. So the corpus proves itself before it is used:

* every row must place R(+theta)'s and R(-theta)'s corner sets more than
  ``DISCRIMINATION_MIN_MM`` apart (Hausdorff-style worst corner
  displacement), and
* a row at a multiple of 90 degrees is a hard **error**, not a skip --
  it is precisely the row that cannot discriminate, and precisely the
  kind of row that made this bug invisible for so long, and
* at least ``MIN_ASYMMETRIC_ROWS`` rows must be at non-multiples of 90
  with unequal half-extents (a square at 45 degrees is symmetric under
  both conventions and would silently be a 90-degree row in disguise).

The corpus is pinned to the oracle script's sha256. If the oracle script
changes, the gate fails closed telling you to **regenerate** -- never to
re-pin.

Exit codes (mirrors scripts/check_pad_world_position_oracle.py,
scripts/check_no_raw_rotation_trig.py):
  0 - clean: every registered site agrees with pcbnew within TOLERANCE_MM.
  3 - violation: at least one site disagrees.
  5 - tool_error: a site will not import/resolve, the corpus is missing,
      stale, malformed, or non-discriminating, or the registry is empty.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.github_summary import get_github_summary_path  # noqa: E402
from _lib.path_setup import setup_temper_placer_path  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402

ORACLE_SCRIPT = "scripts/kicad_pad_polygon_oracle.py"
CORPUS = "scripts/pad_core_polygon_oracle_corpus.json"

# pcbnew stores coordinates in integer nanometres, so its own answers are
# quantised at 1e-6 mm. Anything under this is that quantisation; the two
# conventions differ by whole millimetres on every corpus row.
TOLERANCE_MM = 1e-5

# A corpus row is only useful if R(+theta) and R(-theta) actually place the
# corners this far apart.
DISCRIMINATION_MIN_MM = 0.1

MIN_ASYMMETRIC_ROWS = 4

# FFI pad-shape codes (packages/temper-geometry/src/pad_geometry.rs SHAPE_*).
# Duplicated as literals rather than imported so that the gate can still
# report a *violation* (exit 3) when the geometry package is importable but
# wrong, and a *tool error* (exit 5) when it is not importable at all --
# see resolve_site().
SHAPE_CIRCLE = 0
SHAPE_RECT = 2

EXIT_OK = 0
EXIT_VIOLATION = 3
EXIT_TOOL_ERROR = 5


class GateError(Exception):
    """Raised for any condition that must fail closed (exit 5)."""


class Call(Enum):
    """How a registered site is invoked, and how its answer is compared.

    Encoded as data rather than a lambda per entry so that every site is
    reached the same way: import the module, ``getattr`` the name, call
    it. A site that has been renamed or deleted therefore fails closed on
    resolution instead of silently dropping out of the check.
    """

    #: ``f(width, height, "rect", cx, cy, rotation_rad, ratio)`` returning a
    #: Shapely geometry whose exterior ring carries the pad's corners.
    SHAPELY_PAD = "f(w, h, shape, cx, cy, rot_rad, ratio) -> shapely geometry"

    #: ``f(pad_a_spec, pad_b_spec) -> float`` over the FFI int-shape tuples.
    #: Probed behaviourally: the exact distance from the rotated pad core to
    #: a point 1 mm outside each ground-truth corner. This is the only way
    #: to see ``clearance_geometry.rs::pad_core``'s rotation from Python --
    #: the Rust core is not itself exported, only the distance built on it.
    PAD_PAIR_DISTANCE = "f(pad_a, pad_b) -> mm gap, probed near each true corner"

    #: ``f(footprint, box, rotate, translate, place, shapely_angle)``
    #: yielding ``(number, polygon, centre)`` -- called with real Shapely
    #: callables and a duck-typed footprint, so the gate exercises the
    #: gate-under-test's own body, not a retyped imitation of it.
    CONTAINMENT_PAD_POLYGONS = "f(footprint, box, rotate, translate, place, shapely_angle)"

    #: ``f(theta_deg) -> float`` -- the sanctioned angle to hand
    #: ``shapely.affinity.rotate``. Checked by actually rotating a box with
    #: the returned angle and comparing corners, not by comparing to a sign.
    SHAPELY_ANGLE = "f(theta_deg) -> angle for shapely.affinity.rotate"


@dataclass(frozen=True)
class Site:
    """One implementation that must agree with pcbnew."""

    name: str
    module: str
    attr: str
    call: Call
    note: str


# Every implementation reachable from Python that orients a pad's copper
# rectangle. Adding a new one here is the intended way to extend the gate;
# a site removed from the repo must be removed here too, or run() fails
# closed on the failed import.
REGISTRY: tuple[Site, ...] = (
    Site(
        name="core.pad_geometry.pad_core_polygon",
        module="temper_placer.core.pad_geometry",
        attr="pad_core_polygon",
        call=Call.SHAPELY_PAD,
        note="THE SITE THIS GATE EXISTS FOR. Was a bare "
        "shapely.affinity.rotate(+degrees) -- R(+theta) -- bypassing the "
        "sanctioned bridge. Every REQ-SAFE-01 clearance/creepage number on "
        "this board is built on its output. Fixed 2026-08-18 to route the "
        "angle through kicad_transform.shapely_rotation_angle_deg.",
    ),
    Site(
        name="core.pad_geometry.pad_polygon",
        module="temper_placer.core.pad_geometry",
        attr="pad_polygon",
        call=Call.SHAPELY_PAD,
        note="The router's obstacle-map pad outline (router_v6/obstacle_map."
        "py::_create_pad_polygon delegates here). Carried the identical "
        "R(+theta) call; fixed in the same change. Exact for rect (r == 0), "
        "which is all this gate probes.",
    ),
    Site(
        name="temper_geometry.pad_pair_distance_py",
        module="temper_geometry",
        attr="pad_pair_distance_py",
        call=Call.PAD_PAIR_DISTANCE,
        note="clearance_geometry.rs::pad_core -- the bit-exact Rust twin of "
        "pad_core_polygon, and the kernel REQ-SAFE-01 actually calls. It is "
        "checked here directly rather than only through its Python wrapper: "
        "the differential suite pins Rust == Python, so a convention error "
        "present in BOTH passes it, which is exactly the state this gate "
        "found the repo in.",
    ),
    Site(
        name="scripts/check_board_containment.py::_pad_polygons",
        module="check_board_containment",
        attr="_pad_polygons",
        call=Call.CONTAINMENT_PAD_POLYGONS,
        note="Already R(-theta) before this change -- it is the site whose "
        "disagreement with pad_core_polygon exposed the bug. Registered as a "
        "positive control: if this one ever failed, the gate's own "
        "comparison would be what is wrong.",
    ),
    Site(
        name="geometry.kicad_transform.shapely_rotation_angle_deg",
        module="temper_placer.geometry.kicad_transform",
        attr="shapely_rotation_angle_deg",
        call=Call.SHAPELY_ANGLE,
        note="The sanctioned bridge itself (Rust underneath: temper_geometry."
        "kicad_shapely_rotation_angle_deg_py). Checked by rotating a real "
        "box with whatever it returns, so a shim that stopped delegating -- "
        "or delegated to the wrong kernel -- fails here.",
    ),
)


@dataclass(frozen=True)
class SiteResult:
    site: Site
    ok: bool
    worst_error_mm: float
    detail: str


@dataclass
class Report:
    corpus_rows: int = 0
    asymmetric_rows: int = 0
    sites_checked: int = 0
    oracle_sha256: str = ""
    pcbnew_version: str = ""
    live_oracle_verified: bool = False
    results: list[SiteResult] = field(default_factory=list)

    @property
    def violations(self) -> list[SiteResult]:
        return [r for r in self.results if not r.ok]


# ---------------------------------------------------------------------------
# Convention reference implementations.
#
# These exist ONLY so the gate can prove its own corpus discriminates
# between the two conventions. Neither decides any site's verdict -- every
# verdict is decided against pcbnew's pinned answers. This file is
# therefore not another copy of the formula in the sense
# check_no_raw_rotation_trig.py guards against; it is the harness that
# proves the copies elsewhere are right.
# ---------------------------------------------------------------------------


def _corners_r_minus_theta(
    w: float, h: float, cx: float, cy: float, deg: float
) -> list[tuple[float, float]]:
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    hw, hh = w / 2.0, h / 2.0
    return [
        (cx + x * c + y * s, cy - x * s + y * c)
        for x, y in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh))
    ]


def _corners_r_plus_theta(
    w: float, h: float, cx: float, cy: float, deg: float
) -> list[tuple[float, float]]:
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    hw, hh = w / 2.0, h / 2.0
    return [
        (cx + x * c - y * s, cy + x * s + y * c)
        for x, y in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh))
    ]


def corner_set_error(got: list[tuple[float, float]], want: list[tuple[float, float]]) -> float:
    """Worst distance from any wanted corner to its nearest got corner (and
    back). Order-insensitive on purpose: the two conventions produce the
    same ring in a different traversal order at multiples of 90 degrees,
    and a ring-order difference is not a geometry difference -- no
    distance, containment or area query can observe it. Comparing SETS is
    what makes a failure here mean the copper really moved."""
    if len(got) != len(want):
        return float("inf")

    def worst(a, b):
        return max(min(math.dist(p, q) for q in b) for p in a)

    return max(worst(got, want), worst(want, got))


def sha256_of(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as e:
        raise GateError(f"cannot hash {path}: {e}") from None


def corpus_path(repo_root: Path) -> Path:
    return repo_root / CORPUS


def load_corpus(repo_root: Path) -> dict:
    path = corpus_path(repo_root)
    if not path.is_file():
        raise GateError(
            f"pinned corpus {CORPUS} is missing -- regenerate it with "
            f"`python3 {Path(__file__).name} --regenerate-corpus` on a machine with "
            "KiCad's pcbnew bindings. A gate with no ground truth must not report clean."
        )
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise GateError(f"pinned corpus {CORPUS} is unreadable: {e}") from None

    for key in ("oracle_script", "oracle_sha256", "rows", "expected"):
        if key not in data:
            raise GateError(f"pinned corpus {CORPUS} has no '{key}' key")

    if data["oracle_script"] != ORACLE_SCRIPT:
        raise GateError(
            f"pinned corpus names oracle {data['oracle_script']!r}, this gate expects "
            f"{ORACLE_SCRIPT!r}"
        )

    actual = sha256_of(repo_root / ORACLE_SCRIPT)
    if actual != data["oracle_sha256"]:
        raise GateError(
            f"{ORACLE_SCRIPT} has changed since the corpus was generated "
            f"(pinned {data['oracle_sha256'][:16]}..., actual {actual[:16]}...). "
            "REGENERATE the corpus from a real pcbnew "
            f"(`python3 {Path(__file__).name} --regenerate-corpus`) -- do NOT re-pin "
            "the hash. The whole value of these numbers is that KiCad produced them."
        )

    rows, expected = data["rows"], data["expected"]
    if not rows:
        raise GateError(
            f"pinned corpus {CORPUS} has zero rows -- vacuous run, refusing to report clean"
        )
    if len(rows) != len(expected):
        raise GateError(
            f"pinned corpus {CORPUS} has {len(rows)} rows but {len(expected)} expected entries"
        )
    for i, corners in enumerate(expected):
        if not isinstance(corners, list) or len(corners) != 4:
            raise GateError(
                f"pinned corpus row {i} expects {len(corners)} corners; a rect pad has exactly 4"
            )
    return data


def assert_corpus_discriminates(data: dict) -> int:
    """Prove the corpus can tell R(-theta) from R(+theta) before trusting a
    pass. Returns the count of asymmetric non-90 rows."""
    asymmetric = 0
    for i, (row, want) in enumerate(zip(data["rows"], data["expected"], strict=False)):
        w, h, cx, cy, deg = row
        want_pts = [tuple(p) for p in want]

        if abs(deg) % 90.0 < 1e-9 or abs(abs(deg) % 90.0 - 90.0) < 1e-9:
            raise GateError(
                f"corpus row {i} is at {deg} degrees -- a multiple of 90, where R(+theta) "
                "and R(-theta) produce the SAME corner set. Such a row cannot discriminate "
                "and is exactly the kind of row that hid this bug on a board whose 527 pads "
                "are all at multiples of 90. Rows at 90-degree multiples are a hard error, "
                "not a skip."
            )

        minus = _corners_r_minus_theta(w, h, cx, cy, deg)
        plus = _corners_r_plus_theta(w, h, cx, cy, deg)
        sep = corner_set_error(minus, plus)
        if sep <= DISCRIMINATION_MIN_MM:
            raise GateError(
                f"corpus row {i} ({row}) separates the two conventions by only {sep:.6f}mm "
                f"(<= {DISCRIMINATION_MIN_MM}mm). A pad that is symmetric under both "
                "conventions -- e.g. a square at 45 degrees -- is a 90-degree row in "
                "disguise. Replace the row."
            )

        # And the pinned ground truth must actually BE R(-theta): if pcbnew
        # agreed with R(+theta) on any row, the premise of this whole gate
        # would be wrong and it must say so rather than enforce a fiction.
        if corner_set_error(minus, want_pts) > TOLERANCE_MM:
            raise GateError(
                f"corpus row {i} ({row}): pcbnew's pinned corners are not R(-theta) "
                f"(worst {corner_set_error(minus, want_pts):.9f}mm). Either the corpus is "
                "corrupt or KiCad's convention changed -- investigate before enforcing."
            )
        if abs(w - h) > 1e-9:
            asymmetric += 1

    if asymmetric < MIN_ASYMMETRIC_ROWS:
        raise GateError(
            f"corpus has only {asymmetric} asymmetric (width != height) non-90 row(s); "
            f"at least {MIN_ASYMMETRIC_ROWS} are required. A square pad rotated by theta "
            "and by -theta can coincide, so square rows alone do not rule out a "
            "sign-symmetric coincidence."
        )
    return asymmetric


# ---------------------------------------------------------------------------
# Site resolution and probing
# ---------------------------------------------------------------------------


def resolve_site(site: Site):
    """Import the module and fetch the attribute. Failure is a TOOL ERROR,
    never a skip: a registry entry that stopped resolving means the gate's
    coverage silently shrank, which is the failure mode the whole file
    exists to prevent."""
    try:
        mod = importlib.import_module(site.module)
    except Exception as e:  # ImportError, or anything a package __init__ raises
        raise GateError(
            f"site {site.name!r}: cannot import {site.module!r}: {type(e).__name__}: {e}. "
            "A registered implementation that no longer imports must fail this gate "
            "closed -- it cannot be checked, so it cannot be reported clean."
        ) from None
    try:
        return getattr(mod, site.attr)
    except AttributeError:
        raise GateError(
            f"site {site.name!r}: {site.module}.{site.attr} does not exist. If it was "
            "renamed or deleted, update REGISTRY -- do not let the gate quietly stop "
            "checking it."
        ) from None


def _exterior_corners(geom) -> list[tuple[float, float]]:
    if geom.geom_type != "Polygon":
        raise GateError(f"expected a Polygon for a rect pad, got {geom.geom_type}")
    coords = list(geom.exterior.coords)
    if len(coords) == 5 and math.dist(coords[0], coords[-1]) == 0.0:
        coords = coords[:-1]
    return [(float(x), float(y)) for x, y in coords]


def _duck_footprint(w: float, h: float, cx: float, cy: float, deg: float):
    """A kiutils-shaped stand-in for one footprint holding one pad, so that
    check_board_containment's own ``_pad_polygons`` body runs unmodified.

    The footprint sits AT the pad centre with rotation 0 and the pad angle
    carries the whole orientation, because KiCad stores a placed pad's
    ``at`` angle absolutely -- already composed with its footprint's --
    not relative to it. Proven on this board by T1/T2, which share one
    library footprint at footprint-rotations 90/0 and store pad angles
    90/0."""
    from types import SimpleNamespace

    return SimpleNamespace(
        position=SimpleNamespace(X=cx, Y=cy, angle=0.0),
        pads=[
            SimpleNamespace(
                number="1",
                size=SimpleNamespace(X=w, Y=h),
                position=SimpleNamespace(X=0.0, Y=0.0, angle=deg),
            )
        ],
    )


def probe_site(fn, site: Site, row, want: list[tuple[float, float]]) -> float:
    """Worst error in mm for one site on one corpus row."""
    w, h, cx, cy, deg = row

    if site.call is Call.SHAPELY_PAD:
        geom = fn(w, h, "rect", cx, cy, math.radians(deg), 0.0)
        return corner_set_error(_exterior_corners(geom), want)

    if site.call is Call.SHAPELY_ANGLE:
        from shapely.affinity import rotate, translate
        from shapely.geometry import box

        rect = box(-w / 2.0, -h / 2.0, w / 2.0, h / 2.0)
        rect = translate(rotate(rect, fn(deg), origin=(0, 0)), cx, cy)
        return corner_set_error(_exterior_corners(rect), want)

    if site.call is Call.CONTAINMENT_PAD_POLYGONS:
        from shapely.affinity import rotate, translate
        from shapely.geometry import box

        place, shapely_angle = _containment_transform()
        polys = list(
            fn(_duck_footprint(w, h, cx, cy, deg), box, rotate, translate, place, shapely_angle)
        )
        if len(polys) != 1:
            raise GateError(f"site {site.name!r}: expected 1 pad polygon, got {len(polys)}")
        return corner_set_error(_exterior_corners(polys[0][1]), want)

    if site.call is Call.PAD_PAIR_DISTANCE:
        from shapely.geometry import Point, Polygon

        truth = Polygon(want)
        centre = (cx, cy)
        pad = (w, h, SHAPE_RECT, cx, cy, math.radians(deg), 0.0)
        worst = 0.0
        for corner in want:
            # A point 1 mm beyond each true corner, along the corner's own
            # outward diagonal. Under the wrong convention the copper is
            # mirrored, so these probes land at very different gaps -- the
            # corpus self-check bounds the separation from below.
            vx, vy = corner[0] - centre[0], corner[1] - centre[1]
            norm = math.hypot(vx, vy)
            if norm == 0.0:
                raise GateError(f"degenerate corpus row {row}: corner coincides with centre")
            px = corner[0] + vx / norm
            py = corner[1] + vy / norm
            probe = (0.0, 0.0, SHAPE_CIRCLE, px, py, 0.0, 0.0)
            got = fn(pad, probe)
            expected = truth.distance(Point(px, py))
            worst = max(worst, abs(got - expected))
        return worst

    raise GateError(f"site {site.name!r}: unhandled call convention {site.call}")


def _containment_transform():
    """check_board_containment's own resolution of the sanctioned helpers,
    reused rather than retyped."""
    mod = importlib.import_module("check_board_containment")
    return mod._require_kicad_transform()


def diagnose(fn, site: Site, data: dict) -> str:
    """Name the wrong convention when a site fails, instead of only
    reporting a distance -- the 2026-07-29 incident cost days precisely
    because 'the number is wrong' did not say which way."""
    row = data["rows"][0]
    w, h, cx, cy, deg = row
    plus = _corners_r_plus_theta(w, h, cx, cy, deg)
    try:
        if site.call is Call.SHAPELY_PAD:
            got = _exterior_corners(fn(w, h, "rect", cx, cy, math.radians(deg), 0.0))
        elif site.call is Call.SHAPELY_ANGLE:
            from shapely.affinity import rotate, translate
            from shapely.geometry import box

            rect = translate(
                rotate(box(-w / 2.0, -h / 2.0, w / 2.0, h / 2.0), fn(deg), origin=(0, 0)), cx, cy
            )
            got = _exterior_corners(rect)
        elif site.call is Call.CONTAINMENT_PAD_POLYGONS:
            from shapely.affinity import rotate, translate
            from shapely.geometry import box

            place, shapely_angle = _containment_transform()
            polys = list(
                fn(_duck_footprint(w, h, cx, cy, deg), box, rotate, translate, place, shapely_angle)
            )
            got = _exterior_corners(polys[0][1])
        else:
            return (
                "R(+theta)?"
                if probe_site(fn, site, row, plus) <= TOLERANCE_MM
                else "unknown convention"
            )
    except Exception as e:  # a site that raises is diagnosed as such, not as a sign
        return f"raised {type(e).__name__}: {e}"
    if corner_set_error(got, plus) <= TOLERANCE_MM:
        return "R(+theta) -- the standard-math CCW convention; KiCad rotates children R(-theta)"
    return "neither R(-theta) nor R(+theta)"


# ---------------------------------------------------------------------------
# Live oracle (regeneration / optional verification)
# ---------------------------------------------------------------------------


def resolve_pcbnew_python() -> Path | None:
    """An interpreter that can really ``import pcbnew``, probed by importing
    rather than by existence check -- a ``/usr/bin/python3`` that EXISTS but
    lacks the bindings is exactly how a whole test family silently skipped
    for a week on this project."""
    candidates: list[Path] = []
    override = os.environ.get("TEMPER_PCBNEW_PYTHON")
    if override:
        candidates.append(Path(override))
    candidates.append(Path("/usr/bin/python3"))
    candidates.append(
        Path(
            "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3"
        )
    )
    for c in candidates:
        if not c.exists():
            continue
        try:
            r = subprocess.run([str(c), "-c", "import pcbnew"], capture_output=True, timeout=120)
        except (OSError, subprocess.SubprocessError):
            continue
        if r.returncode == 0:
            return c
    return None


def run_live_oracle(repo_root: Path, python: Path, rows: list) -> list:
    with tempfile.TemporaryDirectory() as td:
        inp = Path(td) / "in.json"
        out = Path(td) / "out.json"
        inp.write_text(json.dumps(rows))
        r = subprocess.run(
            [str(python), str(repo_root / ORACLE_SCRIPT), str(inp), str(out)],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if r.returncode != 0:
            raise GateError(
                f"{ORACLE_SCRIPT} exited {r.returncode} under {python}: {r.stderr.strip()[:500]}"
            )
        return json.loads(out.read_text())


def pcbnew_version(python: Path) -> str:
    try:
        r = subprocess.run(
            [str(python), "-c", "import pcbnew; print(pcbnew.GetBuildVersion())"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        return r.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def default_probe_rows() -> list[list[float]]:
    """The probe set: ``[width_mm, height_mm, cx_mm, cy_mm, angle_deg]``.

    Sizes are real pad sizes taken from ``pcb/temper.kicad_pcb``'s own
    inventory (0.8x0.95 x90, 1.325x0.6 x78, 1.95x0.6 x56, 1.7x0.9 x33,
    1.125x1.75 x24, 1.2x0.4 x20, 2.4x2.4 x16), at board-scale centres.

    The ANGLES cannot be real: the board has none. All 527 pads sit at
    0/90/180/270, which is the entire reason the bug survived -- so every
    row here is deliberately at a non-multiple of 90. Both signs, one past
    180, and one square pad (2.4x2.4 at 33 degrees, still discriminating
    because 33 is not 45) so the check is not only exercised on strongly
    elongated pads.
    """
    return [
        [4.0, 1.0, 0.0, 0.0, 30.0],
        [1.95, 0.6, 149.225, 92.075, 45.0],
        [1.325, 0.6, 100.0, 80.0, 23.0],
        [1.7, 0.9, -12.5, 7.25, -37.5],
        [2.4, 2.4, 50.0, 50.0, 33.0],
        [1.125, 1.75, 210.0, 60.0, 61.0],
        [0.8, 0.95, 33.3, -21.7, 135.0],
        [1.2, 0.4, 7.0, 7.0, 12.5],
        [1.325, 0.6, -80.0, 140.0, 200.3],
        [1.95, 0.6, 12.0, 34.0, -123.456],
    ]


def regenerate_corpus(repo_root: Path) -> Path:
    """Re-derive the pinned answers from a real pcbnew. Deliberate, manual,
    never run by CI."""
    python = resolve_pcbnew_python()
    if python is None:
        raise GateError(
            "no interpreter with pcbnew bindings found (tried $TEMPER_PCBNEW_PYTHON, "
            "/usr/bin/python3, KiCad.app). The corpus can only be regenerated where "
            "KiCad's own placement engine can run."
        )
    rows = default_probe_rows()
    expected = run_live_oracle(repo_root, python, rows)
    payload = {
        "_comment": (
            "Ground truth from pcbnew, KiCad's own placement engine, via "
            f"{ORACLE_SCRIPT}. Each row is [width_mm, height_mm, cx_mm, cy_mm, "
            "angle_deg] describing a RECTANGULAR pad; each expected entry is the "
            "four corners of the copper polygon KiCad itself fills, in pcbnew's "
            "own ring order. Generated by scripts/check_pad_core_polygon_oracle.py "
            "--regenerate-corpus. Do not hand-edit: the gate re-derives nothing and "
            "trusts these numbers only because oracle_sha256 still matches."
        ),
        "oracle_script": ORACLE_SCRIPT,
        "oracle_sha256": sha256_of(repo_root / ORACLE_SCRIPT),
        "pcbnew_version": pcbnew_version(python),
        "rows": rows,
        "expected": expected,
    }
    path = corpus_path(repo_root)
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


# ---------------------------------------------------------------------------


def run(repo_root: Path, *, verify_live_oracle: bool = False) -> Report:
    if not REGISTRY:
        raise GateError("REGISTRY is empty -- vacuous run, refusing to report clean")

    setup_temper_placer_path(repo_root)

    data = load_corpus(repo_root)
    report = Report(
        corpus_rows=len(data["rows"]),
        oracle_sha256=data["oracle_sha256"],
        pcbnew_version=data.get("pcbnew_version", "unknown"),
    )
    report.asymmetric_rows = assert_corpus_discriminates(data)

    if verify_live_oracle:
        python = resolve_pcbnew_python()
        if python is None:
            raise GateError("--verify-live-oracle requested but no pcbnew interpreter was found")
        live = run_live_oracle(repo_root, python, data["rows"])
        for i, (got, want) in enumerate(zip(live, data["expected"], strict=False)):
            err = corner_set_error([tuple(p) for p in got], [tuple(p) for p in want])
            if err > TOLERANCE_MM:
                raise GateError(
                    f"pinned corpus row {i} disagrees with a live pcbnew by {err:.9f}mm -- "
                    "the pin is stale; regenerate it."
                )
        report.live_oracle_verified = True

    expected = [[tuple(p) for p in corners] for corners in data["expected"]]

    for site in REGISTRY:
        fn = resolve_site(site)
        worst = 0.0
        for row, want in zip(data["rows"], expected, strict=False):
            worst = max(worst, probe_site(fn, site, row, want))
        report.sites_checked += 1
        if worst <= TOLERANCE_MM:
            report.results.append(SiteResult(site, True, worst, "agrees with pcbnew"))
        else:
            report.results.append(SiteResult(site, False, worst, diagnose(fn, site, data)))

    return report


def _print_report(report: Report) -> None:
    print(
        f"Pad-core-polygon oracle gate -- {report.sites_checked} registered site(s) "
        f"against {report.corpus_rows} pcbnew-pinned row(s) "
        f"({report.asymmetric_rows} asymmetric, all non-90-multiples)"
    )
    print(f"  pcbnew: {report.pcbnew_version}   oracle sha256: {report.oracle_sha256[:16]}...")
    if report.live_oracle_verified:
        print("  pinned answers re-confirmed against a LIVE pcbnew this run")
    print()
    for r in report.results:
        mark = "ok  " if r.ok else "FAIL"
        print(f"  [{mark}] {r.site.name}: worst {r.worst_error_mm:.9f} mm -- {r.detail}")

    if report.violations:
        print(f"\n=== VIOLATIONS: {len(report.violations)} ===")
        print(
            "\nFAILED -- a pad's copper rectangle is not oriented the way KiCad orients it. "
            "Rotate through temper_placer.geometry.kicad_transform "
            "(shapely_rotation_angle_deg for a Shapely geometry, rotate_local_to_world* "
            "for a point) -- see that module's docstring."
        )
    else:
        print(
            f"\nPASS -- every registered site reproduces pcbnew's own pad corners within "
            f"{TOLERANCE_MM} mm at angles where the two conventions differ."
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--regenerate-corpus",
        action="store_true",
        help="re-derive the pinned answers from a real pcbnew and rewrite the corpus",
    )
    parser.add_argument(
        "--verify-live-oracle",
        action="store_true",
        help="additionally re-confirm every pinned answer against a live pcbnew this run",
    )
    args = parser.parse_args()

    repo_root = find_repo_root()

    if args.regenerate_corpus:
        try:
            path = regenerate_corpus(repo_root)
        except GateError as e:
            print(f"TOOL ERROR: {e}")
            sys.exit(EXIT_TOOL_ERROR)
        print(f"Regenerated {path.relative_to(repo_root)}")
        sys.exit(EXIT_OK)

    try:
        report = run(repo_root, verify_live_oracle=args.verify_live_oracle)
    except GateError as e:
        print(f"TOOL ERROR: {e}")
        sys.exit(EXIT_TOOL_ERROR)

    _print_report(report)

    summary_path = get_github_summary_path()
    if summary_path:
        with open(summary_path, "a") as f:
            state = "violation" if report.violations else "clean"
            f.write(f"\n### Pad-core-polygon oracle gate: {state}\n")
            f.write(
                f"- Sites checked: {report.sites_checked}\n"
                f"- Corpus rows: {report.corpus_rows} ({report.asymmetric_rows} asymmetric)\n"
                f"- pcbnew: {report.pcbnew_version}\n"
                f"- Violations: {len(report.violations)}\n"
            )

    sys.exit(EXIT_VIOLATION if report.violations else EXIT_OK)


if __name__ == "__main__":
    main()
