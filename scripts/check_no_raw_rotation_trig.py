#!/usr/bin/env python3
"""Forbid raw rotation trig in the files that have already reimplemented
KiCad's footprint-child rotation formula, wrongly, once.

Motivating incident
--------------------
A rotation-sign error (KiCad rotates a footprint child -- a pad offset, a
courtyard vertex, a silkscreen item -- by R(-theta); this repo used the
standard-math R(+theta)/CCW convention instead) was independently
reimplemented, by hand, in 12 different places, including
``requirements/validators/_copper.py::_rotate``, which REQ-SAFE-01 uses to
compute copper positions for the mains<->SELV clearance check. It
concealed real clearance hazards on 18 production components. See
docs/evidence/2026-07-29-cross-domain-creepage-rotation-convention.md.

All 12 were corrected and then consolidated into a single implementation,
``temper_placer.geometry.kicad_transform`` (see that module's own
docstring for the full list and the confirming evidence). 12
independently-typed copies of a two-line formula is one careless edit away
from 11 correct copies and 1 silently wrong one again -- a test suite does
not prevent that, only removing the ability to write a 13th copy does.
This gate is that removal: it fails if any of the files that have already
proven capable of hosting this exact bug regresses back to a raw,
locally-typed trig call instead of importing the sanctioned module.

What is checked
-----------------
Each file in ``GUARDED_FILES`` below (the exact set that carried the bug,
or is close enough to the bug's own shape -- see per-entry comments) is
AST-scanned for any call to ``math.cos``, ``math.sin``, ``np.cos``,
``np.sin``, ``numpy.cos``, or ``numpy.sin`` (qualified attribute calls),
plus a bare ``cos(...)``/``sin(...)`` call if ``cos``/``sin`` was imported
via ``from math import cos`` / ``from numpy import cos`` (or ``sin``) in
that same file. Import aliases are resolved (``import math as m`` ->
``m.cos`` still trips it). ``temper_placer/geometry/kicad_transform.py``
itself is the one place in the repo allowed to contain this formula and is
never in ``GUARDED_FILES``.

Why an enumerated file list, not a directory/package rule
------------------------------------------------------------
The obvious-looking alternative -- forbid raw ``math.cos``/``sin``
anywhere under ``core/``, ``io/``, ``placer/``, or similar "geometry-ish"
layers -- was tried first, by audit, and rejected: those same directories
also contain extensive, entirely unrelated trig that has nothing to do
with KiCad's rotation convention and would false-positive under a
directory rule, e.g. (non-exhaustive, found during this gate's own design):

  - ``core/pad_geometry.py::pad_support_radius`` -- a pad's extent along a
    query direction; uses ``abs(cos)``/``abs(sin)``, sign-invariant by
    construction.
  - ``placer/deterministic.py``, ``placer/adjustment.py``,
    ``topological/initial_placement.py``, ``deterministic/stages/
    _grid_fence.py``, ``deterministic/geometry/via_placement.py`` --
    spiral/circular/radial placement search patterns, nothing to do with
    a footprint's own orientation.
  - ``router_v6/thermal_relief.py``, ``physics/thermal_potential.py`` --
    thermal spoke/gradient geometry.
  - ``heuristics/style.py``, ``heuristics/structural.py``,
    ``heuristics/organizational.py`` -- synthetic layout-heuristic
    placement patterns.

A directory rule over that surface would need constant, growing
allowlisting and would be exactly the "broad gate people disable" this
gate's own brief warned against. An enumerated list of the files that have
already proven vulnerable is precise (zero false positives against the
audit above), directly falsifiable (delete one file's sanctioned import
and reintroduce the raw formula -- see the falsifier proof in this
project's PR description), and mirrors this repo's own precedent for
"require ALL named things, not whatever is found" (``check_pll_range_
consistency.py``): a guarded file that goes missing is a GATE ERROR, not a
silently smaller check.

Second sweep: 12 call sites in 9 candidate areas, none in the original 12 plus 1
pre-existing call site
-------------------------------------------------------------------------------
A follow-up audit (see ``docs/evidence/2026-07-30-rotation-sign-remaining-
sites.md``) found 12 additional call sites carrying the same shape of bug,
grouped into 9 candidate areas, none in PR #479's 12 or
``check_pad_orientation.py``'s pre-existing 13th call site.
Classified individually against the same test this whole gate exists to
apply -- does the site transform something that must agree with KiCad's
own placement -- and against real ``pcbnew``/``kicad-cli`` ground truth via
``scripts/kicad_pad_rotation_oracle.py`` where the fix touches a value
KiCad itself would place:

  * ``check_pad_orientation.py::_corners`` -- the previously-exempted
    function above. Fixed, not left exempt: this gate is a live CI check
    on real pad geometry, and "identical corner SET at 90-degree multiples"
    is not the same claim as "correct at every angle". The exemption entry
    for it is removed below now that it contains no raw trig to exempt.
  * ``router_v6/constraints_geometry.py`` (``RotatedRect.corners``,
    ``point_to_rotated_rect_distance``) -- ``RotatedRect.rotation`` is
    populated from real board pad/component rotation
    (``deterministic/stages/setup.py``), so this is KiCad-derived geometry,
    not an isolated utility. Fixed. ``point_to_rotated_rect_distance`` was
    additionally not a simple sign flip: it inverted the *old, wrong*
    R(+theta) convention (negate the angle, reapply the same R(+theta)
    formula) rather than the real inverse of the corrected R(-theta)
    convention, so it silently computed the forward transform again
    instead of the world-to-local inverse.
  * ``router_v6/connectivity.py`` (``_to_pad_coordinates``) -- same
    forward/inverse confusion as above, on ``CopperPad.rotation`` (not yet
    wired from real board data by any production caller today, but the
    field exists specifically to hold KiCad pad orientation). Fixed.
  * ``router_v6/escape_via_generator.py``'s dog-bone candidate rotation --
    rotates a symmetric 4-way offset by the component's real board
    rotation to place a via next to a real pin (``core.pin_geometry``,
    itself KiCad-derived). Fixed.
  * ``visualization/board_renderer.py`` / ``visualization/model.py``
    (``Rectangle.corners``) -- render a visual proxy of the real board;
    ``ComponentView.rotation``/``PadView.rotation`` are meant to hold real
    board orientation. Fixed for correctness even though today's discrete
    quadrant-only rotation state (and ``PadView`` having no production
    constructor yet) makes both currently a no-op. REMOVED from
    ``GUARDED_FILES`` 2026-08-13: the entire ``visualization/`` package
    (5,508 LOC, zero production consumers) was deleted 2026-08-11 (commit
    ``cb36af61``, "deprecate the dead visualization/ package"). Same
    reasoning as ``scripts/internal_route.py`` below -- a guarded file must
    exist (``run()`` fails closed on drift), and a deleted file cannot
    regress.
  * ``scripts/internal_route.py`` -- read a real ``kiutils`` board and
    registered real pad positions with a routing oracle; its registration
    formula was fixed for correctness by this sweep. The import breakage
    flagged here at the time (``jax`` removed from the dependency set, and
    a ``temper_placer.routing`` package that no longer exists -- renamed to
    ``router_v6`` without this script following) was never repaired, and
    the script was RETIREd and deleted on 2026-08-04 as import-dead. It is
    therefore no longer in ``GUARDED_FILES``: a guarded file must exist
    (``run()`` fails closed on drift), and a deleted file cannot regress.
    See ``docs/evidence/2026-08-04-wave4-residual-verdicts.md``.
  * ``packages/temper-geometry/src/polygon.rs::rotate_polygon`` and
    ``scripts/bench_rust_geometry.py``'s ``_py_rotate_point`` -- audited
    and left alone. ``rotate_polygon`` rotates a polygon about its own
    centroid with no KiCad correspondence anywhere in or out (zero
    production callers in Rust or through the pyo3 bridge; used only by
    property-based tests asserting rotation-invariant area, which holds
    under either sign). ``bench_rust_geometry.py`` times that same generic
    Rust ``rotate_point`` (``transform.rs::rotate_point``, NOT the already-
    correct KiCad-specific ``transform_pin_position``) against a matching
    plain-Python CCW reimplementation -- both sides intentionally agree on
    the generic convention being benchmarked, and neither touches KiCad
    data. Neither is a raw-trig regression risk for this gate's own
    purpose, so neither is in ``GUARDED_FILES``; this AST lint has no Rust
    equivalent, deliberately -- see the docstring above this section for
    why an enumerated Python file list is the chosen mechanism, and there
    is no comparable "13 proven-vulnerable files" precedent on the Rust
    side yet.
  * ``core/state.py`` (``rotation_matrix``, ``rotate_points``) -- dead,
    unused JAX-era leftover (``sample_rotation`` two functions above it is
    already marked ``DEPRECATED``); zero production callers. Not fixed,
    not guarded: nothing calls it, so there is nothing to protect.

All newly-fixed sites that carry KiCad-derived rotation are added to
``GUARDED_FILES`` below.

The arithmetic is explicit: 8 call sites were updated -- 7 live
KiCad-derived call sites across 6 files, plus the dead
``scripts/internal_route.py`` registration formula. Four call sites in 3
candidate areas were investigated and left unchanged: the Rust polygon
helper, the Rust benchmark helper, and the two dead JAX-era functions in
``core/state.py``. That count is the historical record of the sweep and is
left as measured; ``GUARDED_FILES`` is three shorter than it, because the
8th site's file (``scripts/internal_route.py``) and the two
``visualization/`` files have since been deleted (see the bullets above).

Exit codes (mirrors scripts/check_undeclared_imports.py, scripts/
check_pll_range_consistency.py):
  0 - clean: no guarded file contains a raw rotation-trig call.
  3 - violation: at least one guarded file contains one.
  5 - tool_error: a guarded file is missing, or the guarded-file list is
      empty (vacuous-run backstop -- never conflated with "0 violations").
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.github_summary import get_github_summary_path  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402

# Every file that either carried the R(+theta)/R(-theta) bug (11 of these
# were among PR #479's 12 corrected sites -- io/_write_board.py,
# io/_write_modules.py and placer/template.py each held more than one call
# site, so 12 call sites collapse to 11 distinct files here) or is a
# hand-verified specialization of the same convention that must not
# regress into raw trig (placer/cp_sat/isolation_barrier.py -- see that
# file's own docstring for why it is exempt from calling into
# kicad_transform directly). check_pad_orientation.py is a 13th,
# independently-authored-and-already-correct implementation folded into
# the same sanctioned module; guarded for the same reason.
#
# The entries below were added by the second sweep documented in this
# module's own docstring (12 call sites in 9 candidate areas). They cover
# the 7 live KiCad-derived call sites across 6 files; the Rust benchmark and
# polygon helper, and core/state.py's two dead functions, were investigated
# and deliberately not guarded (see that section for why: isolated or dead).
# The sweep's 8th site, scripts/internal_route.py, was also fixed but its
# file was deleted on 2026-08-04 as import-dead, so it is not guarded here:
# run() requires every guarded file to exist. visualization/board_renderer.py
# and visualization/model.py were fixed too, but the whole visualization/
# package was deleted 2026-08-11 (commit cb36af61, "deprecate the dead
# visualization/ package") -- removed here 2026-08-13 for the same reason.
GUARDED_FILES: tuple[str, ...] = (
    "packages/temper-placer/src/temper_placer/core/courtyard.py",
    "packages/temper-placer/src/temper_placer/core/pin_geometry.py",
    "packages/temper-placer/src/temper_placer/deterministic/stages/setup.py",
    "packages/temper-placer/src/temper_placer/io/_parse_modules.py",
    "packages/temper-placer/src/temper_placer/io/_write_board.py",
    "packages/temper-placer/src/temper_placer/io/_write_modules.py",
    "packages/temper-placer/src/temper_placer/io/kicad_exporter.py",
    "packages/temper-placer/src/temper_placer/placer/cp_sat/isolation_barrier.py",
    "packages/temper-placer/src/temper_placer/placer/template.py",
    "packages/temper-placer/src/temper_placer/requirements/validators/_copper.py",
    "packages/temper-placer/src/temper_placer/router_v6/connectivity.py",
    "packages/temper-placer/src/temper_placer/router_v6/constraints_geometry.py",
    "packages/temper-placer/src/temper_placer/router_v6/escape_via_generator.py",
    "scripts/check_isolation_keepout.py",
    "scripts/check_pad_orientation.py",
    # Added 2026-08-18. This file was NOT in the original 12: it was created
    # on 2026-07-29 (8302756d3), the same day the sweep fixed them, from a
    # SUPERSEDED evidence doc that still called the sign an open question. It
    # typed its own `_rotate_plus_theta` and used it as the primary
    # measurement AND as the filter for its violation list, so it reported
    # the wrong violation SET for three weeks -- a K1/C6 evaluation read
    # 155 -> 235 violations under R(+theta) against 122 -> 92 under the real
    # convention, i.e. the tool argued against a correct change. Fixed to
    # delegate to kicad_transform; guarded here so it cannot re-type the
    # formula, and registered in check_pad_world_position_oracle.py's
    # REGISTRY so its RESULT is checked against pcbnew, which this
    # syntactic lint cannot do (a correctly-typed R(+theta) is
    # syntactically indistinguishable from a correctly-typed R(-theta) --
    # that is exactly why this file needed a second, behavioural gate).
    "scripts/measure_cross_domain_creepage.py",
)

# (file, function name) pairs inside a guarded file that are exempt --
# each one is a DIFFERENT computation than the local-offset-relative-to-
# parent-origin pattern this gate exists to catch, verified individually
# (not blanket-exempted) before being added here. Every entry needs the
# same kind of justification an allowlist entry gets elsewhere in this
# repo (``.undeclared-imports-allowlist``'s convention) -- see the comment
# on each entry, not just this preamble.
EXEMPT_FUNCTIONS: frozenset[tuple[str, str]] = frozenset(
    {
        # placer/template.py::_cos_sin -- Wave-4 Phase-4 migration. The
        # R(-theta) formula that this file once hosted (and that this gate
        # exists to stop it re-hosting) has MOVED to the Rust kernel
        # ``placer_core::placer_compute::apply_{component,parametric}_
        # template`` (packages/temper-io-types), where it is transcribed
        # from kicad_transform and pinned bit-identical by the differential
        # suite (tests/placer/test_placer_template_rust_differential.py).
        # The Python shim's ``_cos_sin(theta)`` returns the (cos, sin)
        # *transcendental pair* the kernel calls back into -- CPython's
        # ``math.cos``/``math.sin`` are the oracle's libm bits (Rust
        # ``f64::sin`` is 1-ULP-divergent on this platform, measured
        # 2026-08-05), so the seam exists precisely so the kernel does NOT
        # re-type the transcendental. It computes no rotation at all; the
        # formula the gate guards against lives only in the pinned Rust
        # kernel now. Re-checking this exemption means re-confirming
        # ``_cos_sin`` still contains only ``math.cos``/``math.sin`` and no
        # rel/abs arithmetic.
        ("packages/temper-placer/src/temper_placer/placer/template.py", "_cos_sin"),
        # measure_cross_domain_creepage.py::_local_points_of_graphic_item --
        # samples _ARC_APPROX_POINTS evenly-spaced points on an FpCircle's
        # boundary (`cx + r*cos(2*pi*k/N)`, `cy + r*sin(...)`) to feed a
        # convex hull. The angle is a loop index over a FULL circle, never a
        # footprint's orientation, and the emitted point SET is identical
        # under either rotation sign -- it is a circle. This is a different
        # computation from the local-offset-relative-to-parent-origin
        # pattern the gate exists to catch. Re-checking this exemption means
        # confirming the function still only samples closed circles and
        # still applies no footprint/pad angle.
        (
            "scripts/measure_cross_domain_creepage.py",
            "_local_points_of_graphic_item",
        ),
        # router_v6/connectivity.py::_to_pad_coordinates -- an exemption
        # entry briefly existed here (added 2026-08-13, removed 2026-08-14)
        # on the theory that this test-only helper's `R(-rotation)`
        # formula was a *deliberately* sign-divergent pinned oracle meant
        # to "detect the Rust kernel's opposite R(+theta) convention".
        # That was backwards: real `pcbnew` ground truth
        # (`scripts/kicad_pad_rotation_oracle.py`) confirms the Rust
        # kernel's R(+theta) is correct and this helper's R(-rotation) was
        # a regression of a bug already fixed once by 8d89069c2
        # (2026-07-30) and reintroduced by 96eb1ce09 (2026-08-09, "restore
        # _to_pad_coordinates as verbatim Python") re-typing the
        # *pre-fix* formula from scratch instead of the corrected one.
        # Re-fixed 2026-08-14 to delegate to
        # `temper_placer.geometry.kicad_transform.rotate_world_to_local_deg`
        # -- see that function's own docstring. It contains no raw trig
        # anymore, so the exemption entry is removed, not just corrected.
    }
)

_TRIG_MODULES = frozenset({"math", "np", "numpy"})
_TRIG_FUNCS = frozenset({"cos", "sin"})


class GateError(Exception):
    """Raised for any condition that must fail closed (exit 5)."""


@dataclass(frozen=True)
class Violation:
    path: str
    lineno: int
    detail: str


@dataclass
class Report:
    files_checked: int = 0
    violations: list[Violation] = field(default_factory=list)


def _module_aliases(tree: ast.Module) -> dict[str, str]:
    """Map local name -> real module name for ``import X`` / ``import X as
    Y`` statements at any depth (module-level or not -- a guarded file
    importing math inside a function is exactly as capable of hosting the
    bug as a top-level import)."""
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in _TRIG_MODULES:
                    aliases[alias.asname or alias.name] = alias.name
    return aliases


def _bare_trig_names(tree: ast.Module) -> dict[str, str]:
    """Map local name -> real function name for ``from math import cos``
    (or ``sin``, or the numpy equivalents), including aliased imports
    (``from math import cos as mcos``)."""
    names: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in _TRIG_MODULES:
            for alias in node.names:
                if alias.name in _TRIG_FUNCS:
                    names[alias.asname or alias.name] = alias.name
    return names


def _exempt_line_ranges(tree: ast.Module, rel: str) -> list[tuple[int, int]]:
    """Line ranges (inclusive) of functions exempted for this file via
    ``EXEMPT_FUNCTIONS``. A named exemption that matches no function in
    the file is silently unused, not an error -- functions get renamed;
    this only matters if it hides a real violation, and an unused
    exemption cannot do that (see ``run``'s own "used" bookkeeping for
    the case that does matter: an exemption that's never reachable at
    all because the file itself is gone)."""
    wanted = {func for (f, func) in EXEMPT_FUNCTIONS if f == rel}
    if not wanted:
        return []
    ranges = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in wanted:
            end = node.end_lineno if node.end_lineno is not None else node.lineno
            ranges.append((node.lineno, end))
    return ranges


def _find_violations(path: Path, repo_root: Path) -> list[Violation]:
    try:
        source = path.read_text()
    except OSError as e:
        raise GateError(f"{path}: could not read file: {e}") from None

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as e:
        raise GateError(f"{path}: could not parse as Python: {e}") from None

    module_aliases = _module_aliases(tree)
    bare_names = _bare_trig_names(tree)
    rel = str(path.relative_to(repo_root))
    exempt_ranges = _exempt_line_ranges(tree, rel)

    def _is_exempt(lineno: int) -> bool:
        return any(start <= lineno <= end for start, end in exempt_ranges)

    found: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func

        # Qualified form: math.cos(...), np.sin(...), an aliased "import
        # math as m" -> m.cos(...), etc.
        if isinstance(func, ast.Attribute) and func.attr in _TRIG_FUNCS:
            if (
                isinstance(func.value, ast.Name)
                and func.value.id in module_aliases
                and not _is_exempt(node.lineno)
            ):
                real_module = module_aliases[func.value.id]
                found.append(
                    Violation(
                        rel,
                        node.lineno,
                        f"{func.value.id}.{func.attr}(...) -- raw call into "
                        f"'{real_module}.{func.attr}', not "
                        "temper_placer.geometry.kicad_transform",
                    )
                )
                continue

        # Bare form: from math import cos; ...; cos(...)
        if isinstance(func, ast.Name) and func.id in bare_names and not _is_exempt(node.lineno):
            found.append(
                Violation(
                    rel,
                    node.lineno,
                    f"{func.id}(...) -- raw call (imported via 'from ... import "
                    f"{func.id}'), not temper_placer.geometry.kicad_transform",
                )
            )

    return found


def run(repo_root: Path) -> Report:
    report = Report()

    if not GUARDED_FILES:
        raise GateError("GUARDED_FILES is empty -- vacuous run, refusing to report clean")

    for rel in GUARDED_FILES:
        path = repo_root / rel
        if not path.is_file():
            raise GateError(
                f"guarded file '{rel}' does not exist -- GUARDED_FILES has drifted from "
                "the repo (a rename/move must update this list, not silently shrink the "
                "gate's coverage)"
            )
        report.files_checked += 1
        report.violations.extend(_find_violations(path, repo_root))

    return report


def _print_report(report: Report) -> None:
    if report.violations:
        print(f"=== VIOLATIONS: {len(report.violations)} ===\n")
        for v in report.violations:
            print(f"  {v.path}:{v.lineno}: {v.detail}")
        print(
            "\nFAILED -- raw rotation trig found in a file that has already proven "
            "capable of hosting the R(+theta)/R(-theta) sign bug. Use "
            "temper_placer.geometry.kicad_transform instead -- see that module's "
            "docstring."
        )
    else:
        print(
            f"PASS -- no raw rotation trig in {report.files_checked} guarded file(s); "
            "temper_placer.geometry.kicad_transform remains the single implementation."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.parse_args()

    repo_root = find_repo_root()

    try:
        report = run(repo_root)
    except GateError as e:
        print(f"TOOL ERROR: {e}")
        sys.exit(5)

    _print_report(report)

    summary_path = get_github_summary_path()
    if summary_path:
        with open(summary_path, "a") as f:
            state = "violation" if report.violations else "clean"
            f.write(f"\n### No-raw-rotation-trig gate: {state}\n")
            f.write(
                f"- Guarded files checked: {report.files_checked}\n"
                f"- Violations: {len(report.violations)}\n"
            )

    sys.exit(3 if report.violations else 0)


if __name__ == "__main__":
    main()
