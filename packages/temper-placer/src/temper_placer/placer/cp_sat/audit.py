"""Placement audit — geometric invariant verification for CP-SAT placements.

Verifies that solver output respects all PCL constraint types via
post-process geometric checks.  Complements the KiCad DRC truth gate (U7).

The pure geometry (``_bbox``, ``_chebyshev_gap``) lives in the
``temper-geometry`` Rust crate (``audit.rs``); the per-constraint checks
and report building stay here.

Post-solve audit totality (R24 — plan 2026-08-02-016)
------------------------------------------------------

The audit is TOTAL over the encoder's constraint surface, closing the
silent-constraint-drop seam class (docs/solutions/logic-errors/
silent-constraint-drop-seam-bugs-2026-07-11.md):

* Every :class:`ConstraintType` the CP-SAT encoder can emit maps to
  exactly one post-solve recomputation in ``PlacementAuditor._CHECK_MAP``
  (KTD2).  ``validate_audit_register()`` enforces this as a test-time
  contract: adding a new encoding without an audit check is a test
  failure, not a coverage gap that drifts.
* A constraint type absent from the map FAILS CLOSED via
  :class:`UnregisteredConstraintTypeError` instead of passing silently
  (KTD1 — a pass-on-unknown is exactly the seam class this audit exists
  to close).
* A constraint whose geometry is not representable in the
  :class:`Placement` model (e.g. PIN_TO_PIN adjacency — the model carries
  no per-pin geometry, or a referenced component absent from the
  placement) audits to an ``UNVERIFIED`` record.  An ``UNVERIFIED``
  record FAILS the run unless its (type, discriminator) pair carries a
  documented exemption in ``PlacementAuditor._EXEMPTIONS`` (the
  documented-NOTE convention: genuinely-missing geometry is disabled with
  a documented NOTE, never guessed).

Register table — every encoded type has exactly one recomputation or one
documented exemption (values are the ``ConstraintType.value`` strings the
encoder emits):

==========================  =================================  ===========
ConstraintType (value)      check / exemption                   notes
==========================  =================================  ===========
separated                   ``_check_separated``                also covers the
                                                                standalone
                                                                domain_clearance_*,
                                                                netclass_autogen_*,
                                                                courtyard_*
                                                                SEPARATEDs
enclosing                   ``_check_enclosing``
adjacent                    ``_check_adjacent``                 ``pin_to_pin``
                                                                metric: UNVERIFIED
                                                                + exemption
on_side                     ``_check_on_side``
anchored                    ``_check_anchored``
keepout                     ``_check_keepout``
aligned                     ``_check_aligned``
loop_area                   ``_check_loop_area``
(isolation barrier)         ``audit_isolation_barrier``         HV/SELV one-sided
                                                                bounds recomputed;
                                                                isolator
                                                                pad-cluster
                                                                straddle
                                                                UNVERIFIED +
                                                                exemption
==========================  =================================  ===========

Every row above is enforced by ``validate_audit_register()`` (all
``ConstraintType`` members and every encoder-emitted type have a check,
and every mapped method exists) and by the completeness tests in
``tests/placer/cp_sat/test_audit.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import temper_geometry as _tg

from temper_placer.pcl.constraints import (
    AdjacentConstraint,
    AlignedConstraint,
    AnchoredConstraint,
    BaseConstraint,
    ConstraintType,
    DistanceMetric,
    EnclosingConstraint,
    KeepoutConstraint,
    LoopAreaConstraint,
    OnSideConstraint,
    SeparatedConstraint,
)


class UnregisteredConstraintTypeError(ValueError):
    """Raised when a constraint type has no registered audit check (KTD1).

    The audit fails closed on unknown types: a pass-on-unknown is exactly
    the silent-constraint-drop seam class this audit exists to close, so
    an unregistered type is a hard failure naming the type, never a clean
    pass.
    """


@dataclass
class AuditViolation:
    """A single constraint violation found by the auditor."""

    constraint_id: str
    constraint_type: str
    description: str
    detail: str = ""


@dataclass
class AuditReport:
    """Result of running all audit checks on a placement.

    ``unverified`` holds documented-exemption records — constraints whose
    geometry is not representable in the :class:`Placement` model but that
    carry a registered exemption in ``PlacementAuditor._EXEMPTIONS``.
    They are visible for review but do not fail the run.  An
    ``UNVERIFIED`` record WITHOUT an exemption is a ``failed`` violation,
    never a silent pass.
    """

    passed: int
    failed: int
    violations: list[AuditViolation] = field(default_factory=list)
    unverified: list[AuditViolation] = field(default_factory=list)

    @property
    def all_pass(self) -> bool:
        return self.failed == 0


@dataclass
class Placement:
    """Placement geometry for audit — extracted from solver output."""

    positions_mm: dict[str, tuple[float, float]]
    sizes_mm: dict[str, tuple[float, float]]
    rotations: dict[str, int]
    board_w_mm: float = 100.0
    board_h_mm: float = 100.0
    zones: dict[str, tuple[float, float, float, float]] = field(default_factory=dict)
    zone_components: dict[str, list[str]] = field(default_factory=dict)


def _bbox(placement: Placement, ref: str) -> tuple[float, float, float, float]:
    """Return (x_min, y_min, x_max, y_max) for a component in mm.

    Computed in the ``temper-geometry`` Rust crate (``audit.rs``) with
    the exact f64 operation order of the former pure-Python body
    (``hw = sw / 2`` etc.), pinned bit-exactly by
    ``tests/placer/cp_sat/test_audit_rust_differential.py``.
    """
    cx, cy = placement.positions_mm.get(ref, (0.0, 0.0))
    sw, sh = placement.sizes_mm.get(ref, (0.0, 0.0))
    return _tg.bbox_from_center_py(cx, cy, sw, sh)


def _chebyshev_gap(
    bbox_a: tuple[float, float, float, float],
    bbox_b: tuple[float, float, float, float],
) -> float:
    """Chebyshev distance between two axis-aligned rectangles.
    Returns 0 if they overlap, >0 gap otherwise (or negative if overlapping deeply).

    Computed in the ``temper-geometry`` Rust crate (``audit.rs``) with
    the exact f64 operation order of the former pure-Python body,
    including Python-builtin ``max`` NaN semantics (pinned bit-exactly by
    ``tests/placer/cp_sat/test_audit_rust_differential.py``).
    """
    ax1, ay1, ax2, ay2 = bbox_a
    bx1, by1, bx2, by2 = bbox_b
    return _tg.chebyshev_gap_py(ax1, ay1, ax2, ay2, bx1, by1, bx2, by2)


class PlacementAuditor:
    """Run geometric audit checks on a Placement."""

    # Register: every ConstraintType the encoder can emit maps to exactly
    # one post-solve recomputation method (KTD2).  Totality is enforced by
    # validate_audit_register() + the completeness tests.
    _CHECK_MAP: dict[ConstraintType, str] = {
        ConstraintType.SEPARATED: "_check_separated",
        ConstraintType.ENCLOSING: "_check_enclosing",
        ConstraintType.ADJACENT: "_check_adjacent",
        ConstraintType.ON_SIDE: "_check_on_side",
        ConstraintType.ANCHORED: "_check_anchored",
        ConstraintType.KEEPOUT: "_check_keepout",
        ConstraintType.ALIGNED: "_check_aligned",
        ConstraintType.LOOP_AREA: "_check_loop_area",
    }

    # Documented UNVERIFIED exemptions: (ConstraintType, discriminator) ->
    # reason.  A constraint that cannot be verified (see
    # ``_unverified_reason``) FAILS the run unless its key is registered
    # here.  Following the documented-NOTE convention (docs/solutions/
    # logic-errors/silent-constraint-drop-seam-bugs-2026-07-11.md):
    # genuinely-missing geometry is disabled with a documented NOTE,
    # never guessed.  The corpus contains no PIN_TO_PIN constraint today,
    # so this entry is latent — built so the mechanism exists and the
    # exemption is reviewable before any real solve could strand on it.
    _EXEMPTIONS: dict[tuple[ConstraintType, str], str] = {
        (
            ConstraintType.ADJACENT,
            DistanceMetric.PIN_TO_PIN.value,
        ): (
            "Placement carries no per-pin geometry, so PIN_TO_PIN adjacency "
            "cannot be recomputed from placement coordinates. The encoder "
            "approximates PIN_TO_PIN as edge-to-edge (handlers/adjacent.py), "
            "but the auditor cannot confirm the true pin-to-pin metric, so it "
            "is recorded UNVERIFIED rather than passed on a different metric. "
            "Documented NOTE (plan 2026-08-02-016 U4): real pin-geometry "
            "verification is deferred to the follow-up that adds pins to the "
            "Placement model. No PIN_TO_PIN constraint exists in the current "
            "corpus; this exemption is latent."
        ),
    }

    def __init__(self, placement: Placement) -> None:
        self.placement = placement

    def audit(
        self,
        constraints: list[BaseConstraint],
        loop_components: dict[str, list[str]] | None = None,
    ) -> AuditReport:
        passed = 0
        failed = 0
        violations: list[AuditViolation] = []
        unverified: list[AuditViolation] = []
        for c in constraints:
            reason = self._unverified_reason(c, loop_components)
            if reason is not None:
                record = AuditViolation(
                    constraint_id=c.id,
                    constraint_type=c.constraint_type.value,
                    description=f"UNVERIFIED: {reason}",
                    detail=reason,
                )
                if self._is_exempt(c):
                    # Documented exemption: recorded for review, does not fail.
                    unverified.append(record)
                else:
                    # No documented exemption: UNVERIFIED fails the run —
                    # never a silent pass on a constraint that was not checked.
                    failed += 1
                    violations.append(record)
                continue
            v_list = self._check(c, loop_components)
            if v_list:
                failed += 1
                violations.extend(v_list)
            else:
                passed += 1
        return AuditReport(
            passed=passed,
            failed=failed,
            violations=violations,
            unverified=unverified,
        )

    def _check(
        self, c: BaseConstraint, loop_components: dict[str, list[str]] | None = None
    ) -> list[AuditViolation]:
        method_name = self._CHECK_MAP.get(c.constraint_type)
        if method_name is None:
            # KTD1: fail closed on unregistered types — the pre-change
            # behavior (return []) was the silent-pass seam.
            raise UnregisteredConstraintTypeError(
                f"Constraint type {c.constraint_type!r} ({c.constraint_type.value}) "
                f"has no post-solve audit check — the audit fails closed on "
                f"unregistered types (KTD1). Register a recomputation in "
                f"PlacementAuditor._CHECK_MAP or a documented exemption in "
                f"PlacementAuditor._EXEMPTIONS."
            )
        method = getattr(self, method_name)
        if c.constraint_type == ConstraintType.LOOP_AREA:
            return method(c, loop_components)  # type: ignore[arg-type]
        return method(c)  # type: ignore[arg-type]

    # ---- unverifiable-constraint detection ----

    def _unverified_reason(
        self,
        c: BaseConstraint,
        loop_components: dict[str, list[str]] | None = None,
    ) -> str | None:
        """Return a reason string when *c* cannot be verified, else None.

        Two conditions make a constraint unverifiable with the current
        :class:`Placement` model:

        * the metric is not recomputable from component geometry
          (``PIN_TO_PIN`` adjacency — no per-pin geometry).
        * a referenced component/zone/loop is absent from the placement —
          the pre-change checks silently skipped those (a clean pass on a
          constraint that was never actually checked).
        """
        if (
            c.constraint_type is ConstraintType.ADJACENT
            and getattr(c, "metric", None) is DistanceMetric.PIN_TO_PIN
        ):
            return (
                "PIN_TO_PIN adjacency cannot be recomputed: the Placement model "
                "carries no per-pin geometry."
            )
        missing = self._missing_refs(c, loop_components)
        if missing:
            return (
                "constraint references component(s) absent from the placement: "
                + ", ".join(sorted(missing))
            )
        return None

    def _missing_refs(
        self,
        c: BaseConstraint,
        loop_components: dict[str, list[str]] | None = None,
    ) -> list[str]:
        """Refs referenced by *c* that are absent from the Placement geometry."""
        if c.constraint_type is ConstraintType.SEPARATED:
            return [name for name in (c.a, c.b) if not self._resolve(name)]
        if c.constraint_type is ConstraintType.ENCLOSING:
            missing: list[str] = []
            if c.outer not in self.placement.zones:
                missing.append(c.outer)
            missing.extend(r for r in c.inner if r not in self.placement.positions_mm)
            return missing
        if c.constraint_type is ConstraintType.ADJACENT:
            return [r for r in (c.a, c.b) if r not in self.placement.positions_mm]
        if c.constraint_type is ConstraintType.ON_SIDE:
            return [r for r in c.components if r not in self.placement.positions_mm]
        if c.constraint_type is ConstraintType.ANCHORED:
            return [] if c.component in self.placement.positions_mm else [c.component]
        if c.constraint_type is ConstraintType.KEEPOUT:
            return [] if c.zone_name in self.placement.zones else [c.zone_name]
        if c.constraint_type is ConstraintType.ALIGNED:
            return [r for r in c.components if r not in self.placement.positions_mm]
        if c.constraint_type is ConstraintType.LOOP_AREA:
            comps = (loop_components or {}).get(c.loop_name, [])
            if not comps:
                return [c.loop_name]
            return [r for r in comps if r not in self.placement.positions_mm]
        return []

    def _is_exempt(self, c: BaseConstraint) -> bool:
        """True when *c*'s (type, discriminator) key has a documented exemption."""
        return self._exemption_key(c) in self._EXEMPTIONS

    @staticmethod
    def _exemption_key(c: BaseConstraint) -> tuple[ConstraintType, str]:
        """(type, discriminator) key for the exemption registry.

        For ADJACENT the discriminator is the ``DistanceMetric``; for
        every other type the discriminator is the type value itself (only
        metric-level conditions are unverifiable per-type today).
        """
        if c.constraint_type is ConstraintType.ADJACENT:
            metric = getattr(c, "metric", DistanceMetric.EDGE_TO_EDGE)
            return (c.constraint_type, metric.value)
        return (c.constraint_type, c.constraint_type.value)

    # ---- checks ----

    def _check_separated(self, c: SeparatedConstraint) -> list[AuditViolation]:
        refs_a = self._resolve(c.a)
        refs_b = self._resolve(c.b)
        for ra in refs_a:
            for rb in refs_b:
                if ra == rb:
                    continue
                if ra not in self.placement.positions_mm or rb not in self.placement.positions_mm:
                    # Unreachable through audit() (intercepted by
                    # _unverified_reason); kept as defense-in-depth.
                    continue
                gap = _chebyshev_gap(
                    _bbox(self.placement, ra),
                    _bbox(self.placement, rb),
                )
                if gap < c.min_distance_mm:
                    return [
                        AuditViolation(
                            constraint_id=c.id,
                            constraint_type=c.constraint_type.value,
                            description=f"SEPARATED {ra}-{rb} gap={gap:.1f}mm < {c.min_distance_mm}mm",
                            detail=f"gap={gap:.1f}",
                        )
                    ]
        return []

    def _check_enclosing(self, c: EnclosingConstraint) -> list[AuditViolation]:
        zone = self.placement.zones.get(c.outer)
        if zone is None:
            # Unreachable through audit() (intercepted by _unverified_reason).
            return []
        zx1, zy1, zx2, zy2 = zone
        for ref in c.inner:
            if ref not in self.placement.positions_mm:
                continue
            bx1, by1, bx2, by2 = _bbox(self.placement, ref)
            margin = c.margin_mm
            if bx1 < zx1 + margin or by1 < zy1 + margin or bx2 > zx2 - margin or by2 > zy2 - margin:
                return [
                    AuditViolation(
                        constraint_id=c.id,
                        constraint_type=c.constraint_type.value,
                        description=f"ENCLOSING {ref} outside {c.outer}",
                        detail=f"bbox=({bx1:.1f},{by1:.1f})-({bx2:.1f},{by2:.1f}) zone=({zx1:.1f},{zy1:.1f})-({zx2:.1f},{zy2:.1f})",
                    )
                ]
        return []

    def _check_adjacent(self, c: AdjacentConstraint) -> list[AuditViolation]:
        # VERIFIED 2026-07-18: this previously always computed
        # center-to-center Chebyshev distance regardless of c.metric,
        # silently ignoring EDGE_TO_EDGE (the default) and PIN_TO_PIN
        # entirely.  The encoder's own handler (handlers/adjacent.py)
        # approximates PIN_TO_PIN as edge-to-edge (pin geometry is not
        # modelled in the placement grid), so the auditor now:
        #   * audits EDGE_TO_EDGE and CENTER_TO_CENTER against the same
        #     geometry primitives the encoder used (KTD3), and
        #   * never audits PIN_TO_PIN at all — audit() intercepts it in
        #     _unverified_reason and records it UNVERIFIED (with a
        #     documented exemption). See docs/solutions/test-failures/
        #     integration-temper-hardcoded-components-drifted-from-pcl-fixture.md
        #     for the original false-positive incident this guard exists to
        #     prevent.
        a, b = c.a, c.b
        if a not in self.placement.positions_mm or b not in self.placement.positions_mm:
            # Unreachable through audit() (intercepted by _unverified_reason).
            return []

        if c.metric == DistanceMetric.PIN_TO_PIN:
            # Defense-in-depth: audit() intercepts PIN_TO_PIN before
            # reaching here; a direct call must not silently pass.
            raise UnregisteredConstraintTypeError(
                f"PIN_TO_PIN adjacency ({c.id}) reached the edge-check path — "
                f"it must be routed through the UNVERIFIED exemption in "
                f"PlacementAuditor.audit()."
            )

        if c.metric == DistanceMetric.EDGE_TO_EDGE:
            dist = _chebyshev_gap(_bbox(self.placement, a), _bbox(self.placement, b))
        else:  # CENTER_TO_CENTER
            ax, ay = self.placement.positions_mm[a]
            bx, by = self.placement.positions_mm[b]
            dist = max(abs(ax - bx), abs(ay - by))

        if dist > c.max_distance_mm:
            return [
                AuditViolation(
                    constraint_id=c.id,
                    constraint_type=c.constraint_type.value,
                    description=f"ADJACENT {a}-{b} dist={dist:.1f}mm > {c.max_distance_mm}mm",
                    detail=f"dist={dist:.1f}",
                )
            ]
        return []

    def _check_on_side(self, c: OnSideConstraint) -> list[AuditViolation]:
        side = c.side.value
        max_d = c.max_distance_mm
        bw, bh = self.placement.board_w_mm, self.placement.board_h_mm
        for ref in c.components:
            if ref not in self.placement.positions_mm:
                continue
            bx1, by1, bx2, by2 = _bbox(self.placement, ref)
            if side == "left" and bx1 > max_d:
                return [
                    AuditViolation(
                        constraint_id=c.id,
                        constraint_type=c.constraint_type.value,
                        description=f"ONSIDE {ref} x_start={bx1:.1f}mm > {max_d}mm from left edge",
                    )
                ]
            if side == "right" and bx2 < bw - max_d:
                return [
                    AuditViolation(
                        constraint_id=c.id,
                        constraint_type=c.constraint_type.value,
                        description=f"ONSIDE {ref} x_end={bx2:.1f}mm < {bw - max_d:.1f}mm from right edge",
                    )
                ]
            if side == "top" and by2 < bh - max_d:
                return [
                    AuditViolation(
                        constraint_id=c.id,
                        constraint_type=c.constraint_type.value,
                        description=f"ONSIDE {ref} y_end={by2:.1f}mm < {bh - max_d:.1f}mm from top edge",
                    )
                ]
            if side == "bottom" and by1 > max_d:
                return [
                    AuditViolation(
                        constraint_id=c.id,
                        constraint_type=c.constraint_type.value,
                        description=f"ONSIDE {ref} y_start={by1:.1f}mm > {max_d}mm from bottom edge",
                    )
                ]
        return []

    def _check_anchored(self, c: AnchoredConstraint) -> list[AuditViolation]:
        ref = c.component
        if ref not in self.placement.positions_mm:
            # Unreachable through audit() (intercepted by _unverified_reason).
            return []
        if c.position is not None:
            cx, cy = self.placement.positions_mm[ref]
            px, py = c.position
            tol = 0.5  # mm tolerance for position anchoring
            if abs(cx - px) > tol or abs(cy - py) > tol:
                return [
                    AuditViolation(
                        constraint_id=c.id,
                        constraint_type=c.constraint_type.value,
                        description=f"ANCHORED {ref} at ({cx:.1f},{cy:.1f}) != ({px:.1f},{py:.1f})",
                        detail=f"pos=({cx:.1f},{cy:.1f}) target=({px:.1f},{py:.1f})",
                    )
                ]
        elif c.region is not None:
            bx1, by1, bx2, by2 = _bbox(self.placement, ref)
            rx1, ry1, rx2, ry2 = c.region
            if bx1 < rx1 or by1 < ry1 or bx2 > rx2 or by2 > ry2:
                return [
                    AuditViolation(
                        constraint_id=c.id,
                        constraint_type=c.constraint_type.value,
                        description=f"ANCHORED {ref} outside region",
                        detail=f"bbox=({bx1:.1f},{by1:.1f})-({bx2:.1f},{by2:.1f}) region=({rx1},{ry1})-({rx2},{ry2})",
                    )
                ]
        return []

    def _check_keepout(self, c: KeepoutConstraint) -> list[AuditViolation]:
        zone = self.placement.zones.get(c.zone_name)
        if zone is None:
            # Unreachable through audit() (intercepted by _unverified_reason).
            return []
        kx1, ky1, kx2, ky2 = zone
        margin = c.margin_mm
        kx1 -= margin
        ky1 -= margin
        kx2 += margin
        ky2 += margin
        for ref in self.placement.positions_mm:
            if ref == c.zone_name:
                continue
            bx1, by1, bx2, by2 = _bbox(self.placement, ref)
            if bx1 < kx2 and bx2 > kx1 and by1 < ky2 and by2 > ky1:
                return [
                    AuditViolation(
                        constraint_id=c.id,
                        constraint_type=c.constraint_type.value,
                        description=f"KEEPOUT {ref} overlaps keepout {c.zone_name}",
                        detail=f"bbox=({bx1:.1f},{by1:.1f})-({bx2:.1f},{by2:.1f}) keepout=({kx1:.1f},{ky1:.1f})-({kx2:.1f},{ky2:.1f})",
                    )
                ]
        return []

    def _check_aligned(self, c: AlignedConstraint) -> list[AuditViolation]:
        axis = c.axis.value
        tol = c.tolerance_mm
        refs = [r for r in c.components if r in self.placement.positions_mm]
        for i in range(len(refs)):
            for j in range(i + 1, len(refs)):
                ax, ay = self.placement.positions_mm[refs[i]]
                bx, by = self.placement.positions_mm[refs[j]]
                diff = abs(ax - bx) if axis in ("x", "major") else abs(ay - by)
                if diff > tol:
                    return [
                        AuditViolation(
                            constraint_id=c.id,
                            constraint_type=c.constraint_type.value,
                            description=f"ALIGNED {refs[i]}-{refs[j]} axis={axis} diff={diff:.1f}mm > {tol}mm",
                            detail=f"diff={diff:.1f}",
                        )
                    ]
        return []

    def _check_loop_area(
        self,
        c: LoopAreaConstraint,
        loop_components: dict[str, list[str]] | None = None,
    ) -> list[AuditViolation]:
        comps = loop_components or {}
        loop_comps: list[str] = comps.get(c.loop_name, [])
        if not loop_comps:
            # Unreachable through audit() (intercepted by _unverified_reason).
            return []
        refs = [r for r in loop_comps if r in self.placement.positions_mm]
        if not refs:
            return []
        min_x = min(_bbox(self.placement, r)[0] for r in refs)
        min_y = min(_bbox(self.placement, r)[1] for r in refs)
        max_x = max(_bbox(self.placement, r)[2] for r in refs)
        max_y = max(_bbox(self.placement, r)[3] for r in refs)
        aabb_area = (max_x - min_x) * (max_y - min_y)
        if aabb_area > c.max_area_mm2:
            return [
                AuditViolation(
                    constraint_id=c.id,
                    constraint_type=c.constraint_type.value,
                    description=f"LOOP_AREA AABB={aabb_area:.1f}mm2 > {c.max_area_mm2}mm2",
                    detail=f"aabb=({min_x:.1f},{min_y:.1f})-({max_x:.1f},{max_y:.1f}) area={aabb_area:.1f}",
                )
            ]
        return []

    def _resolve(self, name: str) -> list[str]:
        """Resolve a name to component refs."""
        if name in self.placement.positions_mm:
            return [name]
        if name in self.placement.zones and name in self.placement.zone_components:
            return [
                r for r in self.placement.zone_components[name] if r in self.placement.positions_mm
            ]
        return []


# ---------------------------------------------------------------------------
# Register contract (KTD2 / U2, U4)
# ---------------------------------------------------------------------------


def audit_register_types() -> frozenset[ConstraintType]:
    """Every ConstraintType with a registered post-solve recomputation."""
    return frozenset(PlacementAuditor._CHECK_MAP)


def encoder_emitted_types() -> frozenset[ConstraintType]:
    """Every ConstraintType the CP-SAT encoder can emit.

    The encoder surface is ``HANDLER_REGISTRY`` (every concrete handler
    module is imported unconditionally by ``handlers/__init__.py``, so the
    registry is complete by construction).  The standalone encodings in
    ``domain_clearance.py`` / ``netclass_constraints.py`` /
    ``_encoder_core.py`` (courtyard) all emit ``SeparatedConstraint``
    objects — the already-registered SEPARATED type — so the registry is
    the complete type surface.
    """
    from temper_placer.placer.cp_sat.handlers import HANDLER_REGISTRY

    return frozenset(HANDLER_REGISTRY)


def validate_audit_register() -> frozenset[ConstraintType]:
    """Enforce register totality (KTD2) — raise if the register is incomplete.

    Fails (AssertionError) when any :class:`ConstraintType` member or any
    encoder-emitted type lacks an audit check, or when a mapped method
    name does not exist on :class:`PlacementAuditor`.  The completeness
    test in ``test_audit.py`` calls this so adding a new encoding without
    an audit entry is a test-time failure, not a drift that passes.

    Returns the set of registered types when the register is complete.
    """
    registered = audit_register_types()
    problems: list[str] = []
    for ct in ConstraintType:
        if ct not in registered:
            problems.append(f"ConstraintType {ct.value!r} has no audit check")
    for ct in encoder_emitted_types():
        if ct not in registered:
            problems.append(f"encoder-emitted type {ct.value!r} has no audit check")
    for ct, method_name in PlacementAuditor._CHECK_MAP.items():
        if not hasattr(PlacementAuditor, method_name):
            problems.append(f"audit check method {method_name!r} for {ct.value!r} is missing")
    if problems:
        raise AssertionError(
            "Post-solve audit register incomplete (KTD2):\n" + "\n".join(problems)
        )
    return registered


# ---------------------------------------------------------------------------
# Isolation-barrier post-solve audit (plan 2026-08-02-016 U2)
# ---------------------------------------------------------------------------


@dataclass
class IsolationBarrierAudit:
    """Post-solve audit of the mains<->SELV isolation barrier.

    ``violations`` are hard failures — an HV/SELV side whose recomputed
    bound contradicts the encoded corridor edge.  ``unverified`` holds
    documented-exemption records (isolator pad-cluster straddles, which
    are not representable in the :class:`Placement` model) — visible for
    review, not failing.
    """

    violations: list[AuditViolation] = field(default_factory=list)
    unverified: list[AuditViolation] = field(default_factory=list)

    @property
    def all_pass(self) -> bool:
        return not self.violations


# Epsilon for the barrier audit's mm-space recomputation.  The encoder
# enforces the corridor edges in integer units (units_per_mm=100,
# even-rounded by CpSatModel.mm_to_units — a 0.02mm step), and position
# extraction rounds to 3 decimals.  The solver-satisfying bound can sit up
# to one even-rounding step (0.01mm) below the nominal mm value, so 0.05mm
# covers both roundings with headroom.  Documented, never tuned to silence
# a real mismatch: a genuine barrier violation exceeds the corridor width,
# far beyond this epsilon.
_BARRIER_AUDIT_EPS_MM = 0.05


def audit_isolation_barrier(
    report: object,
    placement: Placement,
) -> IsolationBarrierAudit:
    """Recompute the isolation barrier's HV/SELV one-sided bounds from the
    resolved placement and compare against the encoded corridor edges.

    The barrier's HV-only/SELV-only constraints are plain one-sided linear
    inequalities (``end <= corridor_lo`` / ``start >= corridor_hi`` in
    ``isolation_barrier.py``) — fully representable in the
    :class:`Placement` model — so they are recomputed here from the same
    ``_bbox`` primitive the auditor uses everywhere (R24 item 3: never
    trust the solver's bookkeeping; recompute from coordinates).

    The isolator pad-cluster straddle constraints require per-pad
    geometry the Placement model does not carry; those audit to
    ``UNVERIFIED`` with a documented exemption (the same documented-NOTE
    convention as PIN_TO_PIN — see the register docstring).  The
    pre-solve ``IsolatorFeasibility`` and
    ``scripts/check_isolation_keepout.py`` remain the authoritative
    checks for isolator straddle.

    Args:
        report: an ``isolation_barrier.IsolationBarrierReport`` (duck-typed
            via its documented attributes so this module does not import
            the barrier module).
        placement: the resolved placement geometry (same model the PCL
            audit uses).

    Returns:
        An :class:`IsolationBarrierAudit`; ``all_pass`` is True iff every
        HV/SELV one-sided bound is satisfied.
    """
    axis = 0 if getattr(report, "orientation", "vertical") == "vertical" else 1
    lo_mm = float(getattr(report, "corridor_position_mm", 0.0))
    hi_mm = lo_mm + float(getattr(report, "corridor_width_mm", 0.0))
    partition = getattr(report, "partition", None)

    violations: list[AuditViolation] = []
    unverified: list[AuditViolation] = []
    if partition is None:
        return IsolationBarrierAudit(violations=violations, unverified=unverified)

    eps = _BARRIER_AUDIT_EPS_MM
    for ref in sorted(partition.hv_only):
        if ref not in placement.positions_mm:
            continue  # not registered in this (possibly subset) solve
        end = _bbox(placement, ref)[2] if axis == 0 else _bbox(placement, ref)[3]
        if end > lo_mm + eps:
            violations.append(
                AuditViolation(
                    constraint_id=f"isolation_barrier_hv_{ref}",
                    constraint_type="isolation_barrier",
                    description=(
                        f"ISOLATION_BARRIER HV {ref} end={end:.2f}mm > "
                        f"corridor lo {lo_mm:.2f}mm"
                    ),
                    detail=f"end={end:.2f} lo={lo_mm:.2f}",
                )
            )

    for ref in sorted(partition.selv_only):
        if ref not in placement.positions_mm:
            continue
        start = _bbox(placement, ref)[0] if axis == 0 else _bbox(placement, ref)[1]
        if start < hi_mm - eps:
            violations.append(
                AuditViolation(
                    constraint_id=f"isolation_barrier_selv_{ref}",
                    constraint_type="isolation_barrier",
                    description=(
                        f"ISOLATION_BARRIER SELV {ref} start={start:.2f}mm < "
                        f"corridor hi {hi_mm:.2f}mm"
                    ),
                    detail=f"start={start:.2f} hi={hi_mm:.2f}",
                )
            )

    for ref in sorted(partition.isolators):
        unverified.append(
            AuditViolation(
                constraint_id=f"isolator_straddle_{ref}",
                constraint_type="isolation_barrier",
                description=(
                    "UNVERIFIED: isolator pad-cluster straddle cannot be "
                    "recomputed from the Placement model"
                ),
                detail=(
                    "Placement carries no per-pad geometry; documented exemption "
                    "(plan 2026-08-02-016 U4). The pre-solve "
                    "IsolatorFeasibility and scripts/check_isolation_keepout.py "
                    "remain the authoritative isolator checks."
                ),
            )
        )

    return IsolationBarrierAudit(violations=violations, unverified=unverified)
