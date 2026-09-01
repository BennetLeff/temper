#!/usr/bin/env python3
"""Every implementation that places a footprint child in world coordinates
must agree with ``scripts/kicad_pad_rotation_oracle.py`` -- i.e. with
``pcbnew``, KiCad's own placement engine.

Why a *behavioural* gate, when a lint already exists
-----------------------------------------------------
``scripts/check_no_raw_rotation_trig.py`` is a syntactic lint: it forbids a
known-vulnerable file from re-typing the rotation formula. That is
necessary and it is not sufficient, and this repo has the receipt.

``scripts/measure_cross_domain_creepage.py`` was written on 2026-07-29
(``8302756d3``) -- the same day the R(+theta)/R(-theta) sweep corrected 12
sites and created ``temper_placer.geometry.kicad_transform``. It was
written from a *superseded* evidence document that still described the
sign as an open question, so it typed its own ``_rotate_plus_theta`` and
used it as the primary measurement. The lint never fired, because the lint
only guards an enumerated list of files that had *already* carried the bug,
and this file was brand new. It sat wrong for three weeks.

The cost was not a wrong number, which is the failure mode this project is
used to. It reported the wrong *set*: it filtered its violation list by the
R(+theta) column, so pairs violating under KiCad's real convention but not
under R(+theta) were never examined at all. On a real evaluation a K1/C6
footprint swap read 155 -> 235 violations under R(+theta) and 122 -> 92
(zero new, 30 resolved) under the true convention -- the broken instrument
argued against a correct change. See ``AGENTS.md``, "Measurement
Instruments That Lie".

A syntactic lint cannot catch that, because a correctly-typed R(+theta) is
syntactically indistinguishable from a correctly-typed R(-theta). Only
executing the code against ground truth can. That is this gate.

What it checks
---------------
``REGISTRY`` below names every Python-reachable entry point that maps a
footprint-local offset (plus a rotation, and optionally a footprint origin)
to a world position. Each is **resolved by import and actually called** on
a fixed probe corpus, and its answer compared to ``pcbnew``'s to
``TOLERANCE_MM``.

Resolving by import-and-call, rather than by scanning source for call
sites, is deliberate. A sibling coverage gate on this repo produced a false
positive exactly one day after it shipped because it scanned Python source
for instantiations and missed one made from Rust via ``getattr``. Most of
the registry here is Rust underneath -- ``kicad_transform`` is a pure
delegation shim over ``temper_geometry.kicad_*_py`` -- so a source scan
would be reading a shim body that contains no formula at all while the real
arithmetic runs in a ``.so``. Calling the function exercises whichever
language actually answers, and a mutation applied at *either* layer is
caught (``test_check_pad_world_position_oracle.py::TestMutation`` mutates
both the Python shim and the Rust symbol beneath it, and requires a
violation from each).

Ground truth
-------------
``pcbnew`` is not importable from this project's ``uv``-managed venv, and
is absent from most machines. So the oracle's answers are **pinned** in
``pad_rotation_oracle_corpus.json`` next to this script, together with the
sha256 of the ``kicad_pad_rotation_oracle.py`` that produced them and the
``pcbnew`` build string that ran. If that oracle script changes, the pin is
stale by definition and this gate fails closed (exit 5) rather than
checking against numbers whose provenance it can no longer vouch for.
Regenerate deliberately, with a real pcbnew:

    TEMPER_PCBNEW_PYTHON=/path/to/python3 \\
        python3 scripts/check_pad_world_position_oracle.py --regenerate-corpus

When an interpreter with ``pcbnew`` *is* available, ``--verify-live-oracle``
re-runs it and confirms the pinned corpus still reproduces. That is an
additional check, never a substitute: the gate's own verdict never depends
on pcbnew being present, because a gate that silently downgrades to "skipped"
on the machines that matter is the defect this project keeps hitting.

Anti-vacuity
-------------
A gate that cannot fail is worth nothing, so every way this one could
quietly become vacuous is a hard error (exit 5), not a pass:

* ``REGISTRY`` empty, or the corpus empty.
* Any registered site failing to import, resolve, or be callable. A site
  that vanished is a GATE ERROR, never a silently smaller check (the
  ``check_pll_range_consistency.py`` / ``check_no_raw_rotation_trig.py``
  precedent: require all named things, not whatever is found).
* The corpus not *discriminating*. Every row is checked to confirm that
  R(+theta) and R(-theta) actually give different answers there, by more
  than ``DISCRIMINATION_MIN_MM``. This is the load-bearing one. At 0 and
  180 degrees the two conventions are IDENTICAL, and at 90/270 they differ
  only in which of x/y is negated -- so a probe that is symmetric about the
  axis the sign flips passes under both. That degeneracy is precisely how
  the original bug hid: ``test_clearance_copper.py::TestRotation::
  test_rotated_footprint_moves_its_pads`` measured a distance that was
  identical under either sign and reported green for weeks.
* Fewer than ``MIN_ASYMMETRIC_ROWS`` rows at angles that are not multiples
  of 90 degrees with both offset components non-zero. A 45-degree row with
  dx != dy cannot be satisfied by any sign-symmetric coincidence.

Known gap -- pad BODY orientation is not covered
--------------------------------------------------
This gate covers the pad's *position* (where a footprint child lands). It
does NOT cover the pad's *body* orientation (how its rectangle is turned
about its own centre). That is a separate transform and, as of 2026-08-18,
the two disagree in this repo:

    core/pad_geometry.py::pad_core_polygon (and ::pad_polygon) call
    shapely.affinity.rotate(core, +math.degrees(rotation_rad), ...),
    bypassing kicad_transform.shapely_rotation_angle_deg -- i.e. R(+theta).
    Its Rust twin, clearance_geometry.rs::pad_core, is a bit-exact
    transcription of that same arithmetic. Meanwhile
    scripts/check_board_containment.py::_pad_polygons rotates the IDENTICAL
    object through the sanctioned bridge, i.e. R(-theta).

Measured (4.0 x 1.0 mm rect, corner sets compared):
    at  90 deg: identical corner set
    at  30 deg: mirrored -- the two disagree

It is invisible on ``pcb/temper.kicad_pcb`` because all 527 pads sit at
multiples of 90 degrees (measured histogram: 0:58, 90:202, 180:175,
270:92, and ZERO at any other angle), and for a centred rectangle at a
quadrant angle the rotated corner SET is the same under either sign. That
degeneracy is why ``pad_pair_distance`` reproduced kicad-cli to four
decimals across 11 distinct values and was reasonably believed correct.

So it is correct today by coincidence of this board's placement, not by
construction -- the exact distinction AGENTS.md's "When Rust and Python
disagree" section warns about. The first non-orthogonal pad angle on this
board makes it wrong. It is deliberately NOT fixed here: ``pad_core`` is
pinned bit-for-bit against verbatim-Python oracles, so changing it is its
own change with its own differential evidence, not a drive-by. Extending
this gate to pad-body polygons (probe pcbnew for a rotated pad's real
corners) is the natural next increment and would make the fix verifiable.

Exit codes (mirrors check_no_raw_rotation_trig.py):
  0 - clean: every registered site agrees with pcbnew.
  3 - violation: at least one registered site disagrees.
  5 - tool_error: vacuous or unverifiable run. Never conflated with clean.
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

ORACLE_SCRIPT = "scripts/kicad_pad_rotation_oracle.py"
CORPUS_FILENAME = "pad_rotation_oracle_corpus.json"

# Agreement tolerance. pcbnew stores positions in integer nanometres, so its
# own answers are quantised at 1e-6 mm; anything above that is a real
# disagreement. The two conventions differ by O(mm) on this corpus, so this
# threshold is nowhere near the decision boundary.
TOLERANCE_MM = 1e-5

# A corpus row is only useful if R(+theta) and R(-theta) actually disagree
# there by more than this. See "Anti-vacuity" above.
DISCRIMINATION_MIN_MM = 0.1

MIN_ASYMMETRIC_ROWS = 4

EXIT_OK = 0
EXIT_VIOLATION = 3
EXIT_TOOL_ERROR = 5


class GateError(Exception):
    """Raised for any condition that must fail closed (exit 5)."""


class Call(Enum):
    """How a registered site is invoked, and how its answer is compared.

    Sites do not share one signature -- some take degrees, some radians,
    some also take the footprint origin, and one is the *inverse*
    transform. Encoding the calling convention as data (rather than a
    lambda per entry) keeps the registry readable and keeps every entry
    resolved the same way: import the module, getattr the name, call it.
    """

    XY_DEG = "f(x, y, angle_deg) -> (world_x, world_y) about the origin"
    XY_RAD = "f(x, y, angle_rad) -> (world_x, world_y) about the origin"
    XY_ORIGIN_RAD = "f(x, y, origin_x, origin_y, angle_rad) -> (world_x, world_y)"
    # World -> local. Checked as the inverse: feeding it the oracle's own
    # answer must return the original local offset. A site that silently
    # became the *forward* transform (a real regression this repo has had --
    # see check_no_raw_rotation_trig.py's note on
    # point_to_rotated_rect_distance) fails this, whereas comparing it
    # directly against R(+theta) would have PASSED it.
    INVERSE_XY_RAD = "f(world_x, world_y, angle_rad) -> (local_x, local_y)"


@dataclass(frozen=True)
class Site:
    """One implementation that must agree with pcbnew."""

    name: str
    module: str
    attr: str
    call: Call
    note: str


# Every Python-reachable implementation of KiCad's local->world footprint
# child placement. Adding a new one here is the intended way to extend the
# gate; a site that is removed from the repo must be removed here too, or
# run() fails closed on the failed import.
REGISTRY: tuple[Site, ...] = (
    Site(
        name="kicad_transform.rotate_local_to_world_deg",
        module="temper_placer.geometry.kicad_transform",
        attr="rotate_local_to_world_deg",
        call=Call.XY_DEG,
        note="The sanctioned shim. Rust underneath (temper_geometry."
        "kicad_rotate_local_to_world_deg_py); every consolidated site "
        "reaches KiCad's convention through this call.",
    ),
    Site(
        name="kicad_transform.rotate_local_to_world",
        module="temper_placer.geometry.kicad_transform",
        attr="rotate_local_to_world",
        call=Call.XY_RAD,
        note="Radians form of the same shim. Registered separately because "
        "the degrees wrapper and the radians one are distinct Rust "
        "pyfunctions, not one calling the other.",
    ),
    Site(
        name="kicad_transform.place_local_to_world",
        module="temper_placer.geometry.kicad_transform",
        attr="place_local_to_world",
        call=Call.XY_ORIGIN_RAD,
        note="Rotate-then-translate in one call: the exact 'pad offset from "
        "the footprint origin, placed at the footprint's board position' "
        "pattern this gate is named for.",
    ),
    Site(
        name="kicad_transform.rotate_world_to_local",
        module="temper_placer.geometry.kicad_transform",
        attr="rotate_world_to_local",
        call=Call.INVERSE_XY_RAD,
        note="The documented inverse. Its formula IS R(+theta) -- correctly "
        "so, as the transpose of R(-theta) -- which is why it is checked "
        "as a round trip through the oracle and not against a sign.",
    ),
    Site(
        name="temper_geometry.kicad_rotate_local_to_world_deg_py",
        module="temper_geometry",
        attr="kicad_rotate_local_to_world_deg_py",
        call=Call.XY_DEG,
        note="The Rust kernel itself, checked directly and not only through "
        "the shim above, so shim/kernel drift cannot hide behind either.",
    ),
    Site(
        name="temper_geometry.rotate_local_to_world_py",
        module="temper_geometry",
        attr="rotate_local_to_world_py",
        call=Call.XY_RAD,
        note="clearance_geometry.rs::rotate_local_to_world -- a SECOND Rust "
        "copy of the convention, pinned rather than consolidated (see "
        "kicad_transform's docstring). REQ-SAFE-01's copper positions "
        "come through here, so it is checked independently.",
    ),
    Site(
        name="requirements.validators._copper._rotate",
        module="temper_placer.requirements.validators._copper",
        attr="_rotate",
        call=Call.XY_RAD,
        note="The REQ-SAFE-01 mains<->SELV clearance/creepage copper-position "
        "site. This is the one that concealed real clearance hazards on 18 "
        "production components when it was R(+theta).",
    ),
    Site(
        name="scripts/check_isolation_keepout.py::_rotate",
        module="check_isolation_keepout",
        attr="_rotate",
        call=Call.XY_DEG,
        note="Live CI gate enforcing mains<->SELV creepage on the real board.",
    ),
    Site(
        name="scripts/check_pad_orientation.py::_rotate",
        module="check_pad_orientation",
        attr="_rotate",
        call=Call.XY_DEG,
        note="Independently authored and already correct before the 2026-07-29 "
        "sweep; validated against 57/57 real kicad-cli shorting_items pairs.",
    ),
    Site(
        name="scripts/measure_cross_domain_creepage.py::_rotate",
        module="measure_cross_domain_creepage",
        attr="_rotate",
        call=Call.XY_DEG,
        note="THE SITE THIS GATE EXISTS FOR. Was a locally-typed R(+theta) "
        "('_rotate_plus_theta') used as the primary measurement, and used to "
        "FILTER the violation list, so it reported the wrong violation set. "
        "Fixed 2026-08-18 to delegate to kicad_transform.",
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
# Convention reference implementations
#
# These two exist ONLY so the gate can prove its own corpus discriminates
# between them. Neither is used to decide any site's verdict -- every
# verdict is decided against pcbnew's pinned answers. This file is
# therefore not a 13th copy of the formula in the sense
# check_no_raw_rotation_trig.py guards against; it is the harness that
# proves the copies elsewhere are right.
# ---------------------------------------------------------------------------


def _r_minus_theta(x: float, y: float, deg: float) -> tuple[float, float]:
    a = math.radians(deg)
    return (x * math.cos(a) + y * math.sin(a), -x * math.sin(a) + y * math.cos(a))


def _r_plus_theta(x: float, y: float, deg: float) -> tuple[float, float]:
    a = math.radians(deg)
    return (x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a))


def sha256_of(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as e:
        raise GateError(f"could not hash {path}: {e}") from None


def corpus_path(repo_root: Path) -> Path:
    return repo_root / "scripts" / CORPUS_FILENAME


def load_corpus(repo_root: Path) -> dict:
    path = corpus_path(repo_root)
    if not path.is_file():
        raise GateError(
            f"oracle corpus missing: {path}. Regenerate it on a machine with pcbnew "
            "(--regenerate-corpus). Refusing to report clean without ground truth."
        )
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise GateError(f"could not read oracle corpus {path}: {e}") from None
    if not isinstance(data, dict):
        raise GateError(f"oracle corpus {path} is not a JSON object")

    rows = data.get("rows")
    expected = data.get("expected")
    if not isinstance(rows, list) or not rows:
        raise GateError(f"oracle corpus {path} has zero probe rows -- vacuous, refusing to run")
    if not isinstance(expected, list) or len(expected) != len(rows):
        raise GateError(
            f"oracle corpus {path}: 'expected' has {len(expected) if isinstance(expected, list) else 'no'} "
            f"entries for {len(rows)} rows -- corrupt, refusing to run"
        )

    pinned = data.get("oracle_sha256")
    actual = sha256_of(repo_root / ORACLE_SCRIPT)
    if pinned != actual:
        raise GateError(
            f"{ORACLE_SCRIPT} has changed since this corpus was generated "
            f"(pinned {pinned}, actual {actual}). The pinned answers can no longer be "
            "attributed to the current oracle. Regenerate with --regenerate-corpus on a "
            "machine with pcbnew -- do NOT re-pin the hash without re-running it."
        )
    return data


def assert_corpus_discriminates(data: dict) -> int:
    """Prove every row can tell R(+theta) from R(-theta), and that enough
    rows are asymmetric. See "Anti-vacuity" in the module docstring."""
    rows = data["rows"]
    expected = data["expected"]

    asymmetric = 0
    for i, ((dx, dy, deg), exp) in enumerate(zip(rows, expected)):
        plus = _r_plus_theta(dx, dy, deg)
        gap = math.dist(plus, tuple(exp))
        if gap <= DISCRIMINATION_MIN_MM:
            raise GateError(
                f"corpus row {i} ({dx}, {dy}, {deg} deg) does NOT discriminate: R(+theta) "
                f"lands {gap:.9f}mm from pcbnew's answer, at or below the "
                f"{DISCRIMINATION_MIN_MM}mm floor. A row where both conventions agree "
                "cannot catch the bug this gate exists for -- 0/180 degrees are exactly "
                "degenerate. Remove or replace the row; do not lower the floor."
            )
        if deg % 90 != 0 and dx != 0 and dy != 0 and abs(dx) != abs(dy):
            asymmetric += 1

    if asymmetric < MIN_ASYMMETRIC_ROWS:
        raise GateError(
            f"corpus has {asymmetric} asymmetric row(s) (angle not a multiple of 90 deg, "
            f"both offsets non-zero, |dx| != |dy|); at least {MIN_ASYMMETRIC_ROWS} are "
            "required. Without them a sign-symmetric coincidence can satisfy the whole "
            "corpus -- which is how this bug survived its first test suite."
        )
    return asymmetric


def resolve_site(site: Site):
    """Import-and-getattr. Any failure is a GATE ERROR, never a skip."""
    try:
        module = importlib.import_module(site.module)
    except Exception as e:  # ImportError, and anything an import side effect raises
        raise GateError(
            f"registered site '{site.name}': could not import '{site.module}': "
            f"{type(e).__name__}: {e}. A site that cannot be imported is not a smaller "
            "check, it is an unverifiable one."
        ) from None
    try:
        fn = getattr(module, site.attr)
    except AttributeError:
        raise GateError(
            f"registered site '{site.name}': '{site.module}' has no attribute "
            f"'{site.attr}' -- REGISTRY has drifted from the repo (a rename must "
            "update this list, not silently shrink the gate)."
        ) from None
    if not callable(fn):
        raise GateError(f"registered site '{site.name}': '{site.module}.{site.attr}' is not callable")
    return fn


def check_site(site: Site, data: dict) -> SiteResult:
    fn = resolve_site(site)
    rows = data["rows"]
    expected = data["expected"]

    worst = 0.0
    worst_detail = ""
    for (dx, dy, deg), exp in zip(rows, expected):
        rad = math.radians(deg)
        try:
            if site.call is Call.XY_DEG:
                got = fn(dx, dy, deg)
            elif site.call is Call.XY_RAD:
                got = fn(dx, dy, rad)
            elif site.call is Call.XY_ORIGIN_RAD:
                got = fn(dx, dy, 0.0, 0.0, rad)
            elif site.call is Call.INVERSE_XY_RAD:
                got = fn(exp[0], exp[1], rad)
            else:  # pragma: no cover - Call is exhaustive
                raise GateError(f"site '{site.name}': unhandled call convention {site.call}")
        except GateError:
            raise
        except Exception as e:
            raise GateError(
                f"registered site '{site.name}': raised {type(e).__name__} on probe "
                f"({dx}, {dy}, {deg}): {e}"
            ) from None

        # INVERSE sites must return the ORIGINAL local offset; forward sites
        # must return pcbnew's world position.
        target = (dx, dy) if site.call is Call.INVERSE_XY_RAD else (exp[0], exp[1])
        try:
            err = math.dist((got[0], got[1]), target)
        except (TypeError, IndexError):
            raise GateError(
                f"registered site '{site.name}': returned {got!r}, not an (x, y) pair"
            ) from None
        if err > worst:
            worst = err
            worst_detail = (
                f"local=({dx}, {dy}) angle={deg}deg -> got ({got[0]:.9f}, {got[1]:.9f}), "
                f"pcbnew/oracle says ({target[0]:.9f}, {target[1]:.9f}), error {err:.9f}mm"
            )

    if worst <= TOLERANCE_MM:
        return SiteResult(site=site, ok=True, worst_error_mm=worst, detail="agrees with pcbnew")

    plus_hint = ""
    dx, dy, deg = rows[0]
    if math.dist(fn_probe_forward(fn, site, rows[0], expected[0]), _r_plus_theta(dx, dy, deg)) <= TOLERANCE_MM:
        plus_hint = (
            "  <-- this is exactly R(+theta), the standard-math CCW convention. "
            "KiCad rotates footprint children by R(-theta). Delegate to "
            "temper_placer.geometry.kicad_transform instead of typing the formula."
        )
    return SiteResult(site=site, ok=False, worst_error_mm=worst, detail=worst_detail + plus_hint)


def fn_probe_forward(fn, site: Site, row, exp) -> tuple[float, float]:
    """One forward evaluation of *fn*, used only to enrich a failure message
    with 'this is R(+theta)'. Never affects a verdict."""
    dx, dy, deg = row
    rad = math.radians(deg)
    try:
        if site.call is Call.XY_DEG:
            got = fn(dx, dy, deg)
        elif site.call is Call.XY_RAD:
            got = fn(dx, dy, rad)
        elif site.call is Call.XY_ORIGIN_RAD:
            got = fn(dx, dy, 0.0, 0.0, rad)
        else:
            return (float("nan"), float("nan"))
        return (got[0], got[1])
    except Exception:
        return (float("nan"), float("nan"))


# ---------------------------------------------------------------------------
# Live pcbnew (optional confirmation, never a substitute)
# ---------------------------------------------------------------------------


def resolve_pcbnew_python() -> Path | None:
    """An interpreter that can really ``import pcbnew``, probed by importing
    rather than by existence check -- a ``/usr/bin/python3`` that EXISTS but
    lacks the bindings is exactly how a whole test family silently skipped
    for a week on this project. Mirrors ``_resolve_pcbnew_python`` in
    tests/placer/cp_sat/test_zone_pour_production_measurement.py."""
    candidates: list[Path] = []
    override = os.environ.get("TEMPER_PCBNEW_PYTHON")
    if override:
        candidates.append(Path(override))
    candidates.append(Path("/usr/bin/python3"))
    candidates.append(
        Path("/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3")
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


# ---------------------------------------------------------------------------


def run(repo_root: Path, *, verify_live_oracle: bool = False) -> Report:
    if not REGISTRY:
        raise GateError("REGISTRY is empty -- vacuous run, refusing to report clean")

    oracle = repo_root / ORACLE_SCRIPT
    if not oracle.is_file():
        raise GateError(f"the oracle itself is missing: {oracle}")

    data = load_corpus(repo_root)
    asymmetric = assert_corpus_discriminates(data)

    report = Report(
        corpus_rows=len(data["rows"]),
        asymmetric_rows=asymmetric,
        oracle_sha256=data["oracle_sha256"],
        pcbnew_version=data.get("pcbnew_version", "unknown"),
    )

    if verify_live_oracle:
        python = resolve_pcbnew_python()
        if python is None:
            raise GateError(
                "--verify-live-oracle was requested but no interpreter with pcbnew "
                "bindings could be found (tried $TEMPER_PCBNEW_PYTHON, /usr/bin/python3, "
                "KiCad.app). Refusing to report a live verification that did not happen."
            )
        live = run_live_oracle(repo_root, python, data["rows"])
        for i, (got, exp) in enumerate(zip(live, data["expected"])):
            err = math.dist(got, exp)
            if err > TOLERANCE_MM:
                raise GateError(
                    f"pinned corpus row {i} no longer reproduces under live pcbnew "
                    f"({pcbnew_version(python)}): pinned {exp}, live {got}, error {err:.9f}mm"
                )
        report.live_oracle_verified = True

    for site in REGISTRY:
        report.results.append(check_site(site, data))
        report.sites_checked += 1

    if report.sites_checked != len(REGISTRY):  # pragma: no cover - defensive
        raise GateError("checked fewer sites than registered -- denominator is never a subset")

    return report


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
            f"{ORACLE_SCRIPT}. Each row is [local_dx_mm, local_dy_mm, "
            "footprint_angle_deg]; each expected entry is the pad's real "
            "board-frame position for a footprint at the origin. Generated by "
            "scripts/check_pad_world_position_oracle.py --regenerate-corpus. "
            "Do not hand-edit: the gate re-derives nothing and trusts these "
            "numbers only because oracle_sha256 still matches."
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


def default_probe_rows() -> list[list[float]]:
    """The probe set.

    First block: ten real (local offset, footprint angle) rows taken from
    distinct rotated cross-domain footprints on pcb/temper.kicad_pcb -- the
    exact rows on which the pre-fix measure_cross_domain_creepage.py was
    shown to disagree with pcbnew 10/10. They are at 90/270 degrees with
    dy == 0, so the conventions differ in the SIGN of the resulting y: real,
    and discriminating, but sign-symmetric.

    Second block: asymmetric angles, which the first block cannot supply.
    45 degrees with dx != dy is the case that rules out a sign-symmetric
    coincidence outright; 37 degrees reproduces the figure already pinned in
    tests/requirements/safety/test_rotation_convention_oracle.py; the rest
    cover non-multiples of 90 in both signs and beyond 180.
    """
    return [
        # -- real board rows (C1, C13, C14, C16, C18, C19, C20, C21, C22, C23)
        [15.0, 0.0, 90.0],
        [-0.775, 0.0, 90.0],
        [-2.55, 0.0, 90.0],
        [-0.775, 0.0, 90.0],
        [0.775, 0.0, 90.0],
        [0.775, 0.0, 90.0],
        [-0.775, 0.0, 90.0],
        [-0.775, 0.0, 90.0],
        [-0.775, 0.0, 270.0],
        [-0.775, 0.0, 90.0],
        # -- asymmetric, non-90-multiple angles
        [10.0, 4.0, 45.0],
        [10.0, 4.0, 37.0],
        [3.25, -7.5, 13.5],
        [-6.125, 2.375, -22.75],
        [8.0, 1.5, 200.3],
        [-4.5, -9.25, 123.456],
    ]


def _print_report(report: Report) -> None:
    print(
        f"Pad-world-position oracle gate -- {report.sites_checked} registered site(s) "
        f"checked against pcbnew {report.pcbnew_version} via {ORACLE_SCRIPT}."
    )
    print(
        f"  corpus: {report.corpus_rows} probe row(s), {report.asymmetric_rows} of them "
        f"asymmetric (angle not a multiple of 90, |dx| != |dy|, both non-zero); every row "
        f"proven to separate R(+theta) from R(-theta) by > {DISCRIMINATION_MIN_MM}mm."
    )
    print(f"  oracle sha256: {report.oracle_sha256}")
    print(
        f"  live pcbnew re-verification: {'PERFORMED' if report.live_oracle_verified else 'not requested'}"
    )
    print("")
    for r in report.results:
        mark = "ok  " if r.ok else "FAIL"
        print(f"  [{mark}] {r.site.name}  (worst error {r.worst_error_mm:.3e} mm)")
        if not r.ok:
            print(f"         {r.detail}")

    if report.violations:
        print(
            f"\nFAILED -- {len(report.violations)} registered site(s) disagree with KiCad's own "
            "placement engine. This is the R(+theta)/R(-theta) trap; see this script's "
            "docstring and AGENTS.md 'Measurement Instruments That Lie'."
        )
    else:
        print(
            f"\nPASS -- all {report.sites_checked} site(s) agree with pcbnew to "
            f"{TOLERANCE_MM}mm across {report.corpus_rows} probe row(s)."
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n", 1)[0], formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--verify-live-oracle",
        action="store_true",
        help="Additionally re-run pcbnew and confirm the pinned corpus still reproduces. "
        "Errors (never skips) if no pcbnew interpreter is available.",
    )
    parser.add_argument(
        "--regenerate-corpus",
        action="store_true",
        help="Re-derive the pinned ground truth from a real pcbnew and rewrite the corpus.",
    )
    args = parser.parse_args()

    repo_root = find_repo_root()
    setup_temper_placer_path(repo_root)

    if args.regenerate_corpus:
        try:
            path = regenerate_corpus(repo_root)
        except GateError as e:
            print(f"TOOL ERROR: {e}")
            sys.exit(EXIT_TOOL_ERROR)
        print(f"Regenerated {path}")
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
            f.write(f"\n### Pad-world-position oracle gate: {state}\n")
            f.write(
                f"- Sites checked: {report.sites_checked}\n"
                f"- Probe rows: {report.corpus_rows} ({report.asymmetric_rows} asymmetric)\n"
                f"- Violations: {len(report.violations)}\n"
            )

    sys.exit(EXIT_VIOLATION if report.violations else EXIT_OK)


if __name__ == "__main__":
    main()
