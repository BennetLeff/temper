"""F.Fab body-collision post-solve audit (R24 discipline) -- the fail-closed
guard that stops the placer from ever again emitting a physically-
unassemblable board.

**The gap this closes.** Commit ``de59c0458`` (PR #602, 2026-08-03) moved 12
components in one automated re-solve and created ``C2xC3`` -- two 35mm
snap-in electrolytic capacitors whose bodies interpenetrate by 7.73mm.
``solve_placement``'s existing courtyard machinery
(``add_no_overlap_2d`` + per-pair ``SEPARATED``-``tau``) did not catch it,
and the only downstream signal was ``courtyards_overlap: 8`` -- an opaque
ratchet number, not an alarm tied to "these two parts cannot physically both
be fitted." PR #1168 (2026-08-13) reproduced the defect deliberately: with
the isolation barrier relaxed, ``solve_placement`` returned ``optimal`` for
placements later shown (by writing them to a board and running live
``kicad-cli`` DRC) to carry 14 and 9 ``courtyards_overlap`` violations,
including a collision worse than anything on the board today.

**What this module adds.** A post-solve audit, structurally identical in
contract to ``fixed_copper.audit_fixed_copper`` and
``validator_audit.audit_domain_clearance_validator`` (the same R24
"recompute independent of the solver's claim, hard-fail a feasible/optimal
solve that produced a real violation" pattern): for every pair of
components with known ``F.Fab`` body geometry, recompute the TRUE body
polygons at the SOLVED coordinates (``core.fab_body.FabBody``, delegating
rotation to the same canonical kernel ``core.courtyard.Courtyard`` uses --
see that module's docstring) and measure real overlap area. A pair with
nonzero body-overlap area is a physical collision -- two solids occupying
the same space, not a drawing convention.

**Body collision vs. courtyard touch (the distinction the brief demands).**
PR #1158 measured all 8 of the board's current ``courtyards_overlap`` pairs
and found 6 real ``F.Fab`` body collisions (0.15mm-7.73mm interpenetration)
and 2 benign courtyard-only touches (``C3xK3``, ``C2xPS1`` -- bodies clear
by 0.19mm/0.39mm; only the courtyard's extra keep-out margin overlaps).
This module measures ``F.Fab`` body overlap ONLY -- never courtyard
geometry -- so a benign courtyard touch, with zero real body-overlap area,
is never a violation. Firing on a benign courtyard touch is exactly the
failure mode the brief warns against: "a guard that fires on benign
courtyard overlap will be disabled by the first person it inconveniences."

**Handling the existing 6 (deliberately NOT a vacuous pass).** The current
board already carries 6 real body collisions -- this guard cannot demand a
clean board without either fixing them here (out of scope; PR #1158 owns
that remediation plan) or becoming vacuous the moment anyone runs it
against ``pcb/temper.kicad_pcb``-derived geometry. The design chosen is a
RATCHET against a pinned, provenance-carrying allowlist
(``configs/body_collision_allowlist.yaml``,
``load_body_collision_allowlist``): a listed pair is permitted at or below
its recorded baseline overlap area, but --
  (a) any pair NOT on the allowlist with real body overlap is a hard
      failure ("new" collision), and
  (b) a pair that IS on the allowlist but whose resolved overlap area
      EXCEEDS its recorded baseline is also a hard failure ("worsened").
(b) is not optional: PR #1168 showed a re-solve can make an existing bad
pair worse (up to 9.47mm, versus this board's current 7.73mm worst case)
while still reporting ``optimal``. A guard that only checked pair identity
against an allowlist would have let that through; comparing against a
recorded baseline magnitude does not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from shapely.geometry import Polygon

from temper_placer.core.fab_body import FabBody

#: Real overlap area below this (mm^2) is treated as floating-point noise
#: from a boundary touch, not a real collision -- matches the "clear by
#: 0.19mm/0.39mm" benign pairs measuring exactly 0.0 area under this
#: pipeline (see module docstring / this repo's PR #1158 cross-validation).
AREA_TOLERANCE_MM2 = 1e-6


# ---------------------------------------------------------------------------
# Allowlist
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BodyCollisionAllowlistEntry:
    ref_a: str
    ref_b: str
    baseline_overlap_mm2: float
    note: str = ""


@dataclass(frozen=True)
class BodyCollisionAllowlist:
    """Pinned pre-existing body collisions this guard permits, at or below
    their recorded baseline severity. See
    ``configs/body_collision_allowlist.yaml`` for the live data and its
    provenance/review-by fields."""

    entries: dict[frozenset, BodyCollisionAllowlistEntry] = field(default_factory=dict)
    board_sha256: str = ""
    review_by: str = ""
    remediation_pr: str = ""

    def get(self, ref_a: str, ref_b: str) -> BodyCollisionAllowlistEntry | None:
        return self.entries.get(frozenset((ref_a, ref_b)))

    def __len__(self) -> int:
        return len(self.entries)


#: An allowlist with zero entries -- every real body collision is a hard
#: failure. Used when no allowlist file is supplied; NOT the production
#: default (the CLI always loads ``configs/body_collision_allowlist.yaml``
#: for the real board), but the correct fail-closed default for a caller
#: (e.g. a from-scratch synthetic placement) that has no pre-existing debt
#: to acknowledge.
EMPTY_ALLOWLIST = BodyCollisionAllowlist()


def load_body_collision_allowlist(path: Path) -> BodyCollisionAllowlist:
    """Parse a ``body_collision_allowlist.yaml``-shaped file.

    Raises:
        FileNotFoundError: *path* does not exist.
        ValueError: a pair entry is missing ``a``/``b``/``baseline_overlap_mm2``,
            or the same unordered pair appears twice (ambiguous baseline --
            fail loudly rather than silently taking whichever the YAML
            loader happened to keep last).
    """
    if not path.exists():
        raise FileNotFoundError(f"Body-collision allowlist not found: {path}")

    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries: dict[frozenset, BodyCollisionAllowlistEntry] = {}
    for row in data.get("pairs", []):
        try:
            a = str(row["a"])
            b = str(row["b"])
            baseline = float(row["baseline_overlap_mm2"])
        except KeyError as exc:
            raise ValueError(f"Allowlist pair entry missing required key: {row!r}") from exc
        key = frozenset((a, b))
        if key in entries:
            raise ValueError(
                f"Allowlist lists pair ({a}, {b}) more than once -- ambiguous baseline"
            )
        entries[key] = BodyCollisionAllowlistEntry(
            ref_a=a, ref_b=b, baseline_overlap_mm2=baseline, note=str(row.get("note", ""))
        )

    return BodyCollisionAllowlist(
        entries=entries,
        board_sha256=str(data.get("board_sha256", "")),
        review_by=str(data.get("review_by", "")),
        remediation_pr=str(data.get("remediation_pr", "")),
    )


# ---------------------------------------------------------------------------
# The audit
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BodyCollisionViolation:
    """One pair whose resolved F.Fab bodies collide in a way this guard does
    not permit."""

    ref_a: str
    ref_b: str
    overlap_mm2: float
    #: "new" -- not on the allowlist at all; "worsened" -- on the allowlist,
    #: but the resolved overlap exceeds the recorded baseline.
    kind: str
    baseline_overlap_mm2: float | None = None

    def describe(self) -> str:
        if self.kind == "worsened":
            return (
                f"{self.ref_a}<->{self.ref_b} F.Fab body overlap WORSENED: "
                f"{self.overlap_mm2:.4f}mm^2 > allowlisted baseline "
                f"{self.baseline_overlap_mm2:.4f}mm^2"
            )
        return (
            f"{self.ref_a}<->{self.ref_b} NEW F.Fab body collision: "
            f"{self.overlap_mm2:.4f}mm^2 overlap (not on the allowlist)"
        )


@dataclass
class BodyCollisionAuditResult:
    """Result of ``audit_body_collisions``."""

    #: Pairs this guard does not permit -- MUST be empty for a solve to be
    #: accepted (the caller, ``solve_placement``, raises when it is not).
    violations: list[BodyCollisionViolation] = field(default_factory=list)
    #: Allowlisted pairs whose resolved overlap was at or below baseline
    #: (reportable, never raised) -- diagnostic visibility into the debt
    #: this solve carried forward unchanged.
    allowlisted: list[BodyCollisionViolation] = field(default_factory=list)
    #: Total component pairs actually compared (both refs had parsed F.Fab
    #: geometry and a resolved position).
    checked_pairs: int = 0
    #: Refs present in the solved placement with no F.Fab geometry --
    #: excluded from every pairwise check (never silently treated as
    #: "clear"). Reportable so a systematically-missing footprint library
    #: entry is visible rather than a silent blind spot.
    refs_without_geometry: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.violations

    def report(self) -> str:
        lines = [
            f"F.Fab body-collision audit: {len(self.violations)} violation(s), "
            f"{len(self.allowlisted)} allowlisted (unchanged-or-better) pair(s) "
            f"over {self.checked_pairs} checked pair(s)"
            f"{f', {len(self.refs_without_geometry)} ref(s) excluded (no F.Fab geometry)' if self.refs_without_geometry else ''}."
        ]
        for v in sorted(self.violations, key=lambda v: -v.overlap_mm2):
            lines.append(f"  VIOLATION: {v.describe()}")
        for v in sorted(self.allowlisted, key=lambda v: -v.overlap_mm2):
            lines.append(
                f"  allowlisted: {v.ref_a}<->{v.ref_b} {v.overlap_mm2:.4f}mm^2 "
                f"(baseline {v.baseline_overlap_mm2:.4f}mm^2)"
            )
        return "\n".join(lines)


def _global_polygon_or_buffered(body: FabBody, x: float, y: float, rotation_idx: int) -> Polygon:
    poly = body.get_global_polygon(x, y, rotation_idx)
    if not poly.is_valid:
        # Self-intersecting outline from an unusual footprint graphic
        # (rare -- e.g. a poly with a degenerate/self-crossing edge).
        # buffer(0) is shapely's standard idiom for repairing this into a
        # valid geometry equivalent in area; it is a GEOS library boundary
        # operation, not a re-derivation of the geometry itself.
        poly = poly.buffer(0)
    return poly


def audit_body_collisions(
    fab_bodies: dict[str, FabBody],
    resolved_positions_mm: dict[str, tuple[float, float]],
    resolved_rotations: dict[str, int],
    allowlist: BodyCollisionAllowlist,
) -> BodyCollisionAuditResult:
    """R24 post-solve audit: true ``F.Fab`` body overlap for every component
    pair with known body geometry, computed from the solved coordinates
    independent of the solver's feasibility claim.

    Args:
        fab_bodies: ``{ref: FabBody}`` -- local body geometry, e.g. from
            ``io.fab_body_extraction.extract_fab_bodies``.
        resolved_positions_mm: ``{ref: (x_mm, y_mm)}`` solved centers.
        resolved_rotations: ``{ref: 0-3 quadrant index}`` solved rotations.
            A ref present in ``resolved_positions_mm`` but absent here is
            treated as rotation index 0 -- the same convention
            ``CpSatPlacementResult.rotations.get(ref, 0)`` and
            ``validator_audit.build_validator_placement`` use: a component
            with no rotation variable (fixed/polarized) is pinned at index
            0 by construction.
        allowlist: pinned pre-existing collisions this call permits at or
            below their recorded baseline (see ``BodyCollisionAllowlist``).
            Pass ``EMPTY_ALLOWLIST`` for a placement with no pre-existing
            debt to acknowledge -- every real collision is then a hard
            failure.

    Returns:
        A ``BodyCollisionAuditResult``. ``violations`` is empty iff the
        solve introduced no new body collision and worsened none of the
        allowlisted ones.
    """
    refs = sorted(set(fab_bodies) & set(resolved_positions_mm))
    refs_without_geometry = sorted(set(resolved_positions_mm) - set(fab_bodies))

    result = BodyCollisionAuditResult(refs_without_geometry=refs_without_geometry)

    polygons: dict[str, Any] = {}
    bounds: dict[str, tuple[float, float, float, float]] = {}
    for ref in refs:
        x, y = resolved_positions_mm[ref]
        rot = resolved_rotations.get(ref, 0)
        poly = _global_polygon_or_buffered(fab_bodies[ref], x, y, rot)
        polygons[ref] = poly
        bounds[ref] = poly.bounds  # (minx, miny, maxx, maxy)

    n = len(refs)
    for i in range(n):
        ref_a = refs[i]
        ax0, ay0, ax1, ay1 = bounds[ref_a]
        poly_a = polygons[ref_a]
        for j in range(i + 1, n):
            ref_b = refs[j]
            bx0, by0, bx1, by1 = bounds[ref_b]
            # Cheap broad-phase reject: bounding boxes must overlap before
            # a real polygon boolean is worth computing (O(n^2) pairs over
            # a ~170-component board is fine for the bbox check; the
            # shapely intersection is the expensive step this skips for
            # the overwhelming majority of far-apart pairs).
            if ax1 < bx0 or bx1 < ax0 or ay1 < by0 or by1 < ay0:
                continue
            result.checked_pairs += 1
            poly_b = polygons[ref_b]
            area = poly_a.intersection(poly_b).area
            if area <= AREA_TOLERANCE_MM2:
                continue  # bodies clear -- a courtyard-only touch, if any, is not this guard's concern

            entry = allowlist.get(ref_a, ref_b)
            if entry is None:
                result.violations.append(
                    BodyCollisionViolation(ref_a, ref_b, area, kind="new")
                )
            elif area > entry.baseline_overlap_mm2 + AREA_TOLERANCE_MM2:
                result.violations.append(
                    BodyCollisionViolation(
                        ref_a,
                        ref_b,
                        area,
                        kind="worsened",
                        baseline_overlap_mm2=entry.baseline_overlap_mm2,
                    )
                )
            else:
                result.allowlisted.append(
                    BodyCollisionViolation(
                        ref_a,
                        ref_b,
                        area,
                        kind="allowlisted",
                        baseline_overlap_mm2=entry.baseline_overlap_mm2,
                    )
                )

    return result


__all__ = [
    "AREA_TOLERANCE_MM2",
    "EMPTY_ALLOWLIST",
    "BodyCollisionAllowlist",
    "BodyCollisionAllowlistEntry",
    "BodyCollisionAuditResult",
    "BodyCollisionViolation",
    "audit_body_collisions",
    "load_body_collision_allowlist",
]
