"""Placement audit — geometric invariant verification for CP-SAT placements.

Verifies that solver output respects all PCL constraint types via
post-process geometric checks.  Complements the KiCad DRC truth gate (U7).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from temper_placer.pcl.constraints import (
    AdjacentConstraint,
    AlignedConstraint,
    AnchoredConstraint,
    BaseConstraint,
    ConstraintType,
    EnclosingConstraint,
    KeepoutConstraint,
    LoopAreaConstraint,
    OnSideConstraint,
    SeparatedConstraint,
)


@dataclass
class AuditViolation:
    """A single constraint violation found by the auditor."""

    constraint_id: str
    constraint_type: str
    description: str
    detail: str = ""


@dataclass
class AuditReport:
    """Result of running all audit checks on a placement."""

    passed: int
    failed: int
    violations: list[AuditViolation] = field(default_factory=list)

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
    """Return (x_min, y_min, x_max, y_max) for a component in mm."""
    cx, cy = placement.positions_mm.get(ref, (0.0, 0.0))
    sw, sh = placement.sizes_mm.get(ref, (0.0, 0.0))
    hw, hh = sw / 2, sh / 2
    return (cx - hw, cy - hh, cx + hw, cy + hh)


def _chebyshev_gap(
    bbox_a: tuple[float, float, float, float],
    bbox_b: tuple[float, float, float, float],
) -> float:
    """Chebyshev distance between two axis-aligned rectangles.
    Returns 0 if they overlap, >0 gap otherwise (or negative if overlapping deeply).
    """
    ax1, ay1, ax2, ay2 = bbox_a
    bx1, by1, bx2, by2 = bbox_b
    dx = max(ax1 - bx2, bx1 - ax2)
    dy = max(ay1 - by2, by1 - ay2)
    return max(dx, dy)


class PlacementAuditor:
    """Run geometric audit checks on a Placement."""

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
        for c in constraints:
            v_list = self._check(c, loop_components)
            if v_list:
                failed += 1
                violations.extend(v_list)
            else:
                passed += 1
        return AuditReport(passed=passed, failed=failed, violations=violations)

    def _check(
        self, c: BaseConstraint, loop_components: dict[str, list[str]] | None = None
    ) -> list[AuditViolation]:
        ct = c.constraint_type
        if ct == ConstraintType.SEPARATED:
            return self._check_separated(c)  # type: ignore[arg-type]
        elif ct == ConstraintType.ENCLOSING:
            return self._check_enclosing(c)  # type: ignore[arg-type]
        elif ct == ConstraintType.ADJACENT:
            return self._check_adjacent(c)  # type: ignore[arg-type]
        elif ct == ConstraintType.ON_SIDE:
            return self._check_on_side(c)  # type: ignore[arg-type]
        elif ct == ConstraintType.ANCHORED:
            return self._check_anchored(c)  # type: ignore[arg-type]
        elif ct == ConstraintType.KEEPOUT:
            return self._check_keepout(c)  # type: ignore[arg-type]
        elif ct == ConstraintType.ALIGNED:
            return self._check_aligned(c)  # type: ignore[arg-type]
        elif ct == ConstraintType.LOOP_AREA:
            return self._check_loop_area(c, loop_components)  # type: ignore[arg-type]
        return []

    # ---- checks ----

    def _check_separated(self, c: SeparatedConstraint) -> list[AuditViolation]:
        refs_a = self._resolve(c.a)
        refs_b = self._resolve(c.b)
        for ra in refs_a:
            for rb in refs_b:
                if ra == rb:
                    continue
                if ra not in self.placement.positions_mm or rb not in self.placement.positions_mm:
                    continue
                gap = _chebyshev_gap(
                    _bbox(self.placement, ra), _bbox(self.placement, rb),
                )
                if gap < c.min_distance_mm:
                    return [AuditViolation(
                        constraint_id=c.id, constraint_type=c.constraint_type.value,
                        description=f"SEPARATED {ra}-{rb} gap={gap:.1f}mm < {c.min_distance_mm}mm",
                        detail=f"gap={gap:.1f}",
                    )]
        return []

    def _check_enclosing(self, c: EnclosingConstraint) -> list[AuditViolation]:
        zone = self.placement.zones.get(c.outer)
        if zone is None:
            return []
        zx1, zy1, zx2, zy2 = zone
        for ref in c.inner:
            if ref not in self.placement.positions_mm:
                continue
            bx1, by1, bx2, by2 = _bbox(self.placement, ref)
            margin = c.margin_mm
            if bx1 < zx1 + margin or by1 < zy1 + margin or bx2 > zx2 - margin or by2 > zy2 - margin:
                return [AuditViolation(
                    constraint_id=c.id, constraint_type=c.constraint_type.value,
                    description=f"ENCLOSING {ref} outside {c.outer}",
                    detail=f"bbox=({bx1:.1f},{by1:.1f})-({bx2:.1f},{by2:.1f}) zone=({zx1:.1f},{zy1:.1f})-({zx2:.1f},{zy2:.1f})",
                )]
        return []

    def _check_adjacent(self, c: AdjacentConstraint) -> list[AuditViolation]:
        a, b = c.a, c.b
        if a not in self.placement.positions_mm or b not in self.placement.positions_mm:
            return []
        ax, ay = self.placement.positions_mm[a]
        bx, by = self.placement.positions_mm[b]
        dist = max(abs(ax - bx), abs(ay - by))
        if dist > c.max_distance_mm:
            return [AuditViolation(
                constraint_id=c.id, constraint_type=c.constraint_type.value,
                description=f"ADJACENT {a}-{b} dist={dist:.1f}mm > {c.max_distance_mm}mm",
                detail=f"dist={dist:.1f}",
            )]
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
                return [AuditViolation(
                    constraint_id=c.id, constraint_type=c.constraint_type.value,
                    description=f"ONSIDE {ref} x_start={bx1:.1f}mm > {max_d}mm from left edge",
                )]
            if side == "right" and bx2 < bw - max_d:
                return [AuditViolation(
                    constraint_id=c.id, constraint_type=c.constraint_type.value,
                    description=f"ONSIDE {ref} x_end={bx2:.1f}mm < {bw - max_d:.1f}mm from right edge",
                )]
            if side == "top" and by2 < bh - max_d:
                return [AuditViolation(
                    constraint_id=c.id, constraint_type=c.constraint_type.value,
                    description=f"ONSIDE {ref} y_end={by2:.1f}mm < {bh - max_d:.1f}mm from top edge",
                )]
            if side == "bottom" and by1 > max_d:
                return [AuditViolation(
                    constraint_id=c.id, constraint_type=c.constraint_type.value,
                    description=f"ONSIDE {ref} y_start={by1:.1f}mm > {max_d}mm from bottom edge",
                )]
        return []

    def _check_anchored(self, c: AnchoredConstraint) -> list[AuditViolation]:
        ref = c.component
        if ref not in self.placement.positions_mm:
            return []
        if c.position is not None:
            cx, cy = self.placement.positions_mm[ref]
            px, py = c.position
            tol = 0.5  # mm tolerance for position anchoring
            if abs(cx - px) > tol or abs(cy - py) > tol:
                return [AuditViolation(
                    constraint_id=c.id, constraint_type=c.constraint_type.value,
                    description=f"ANCHORED {ref} at ({cx:.1f},{cy:.1f}) != ({px:.1f},{py:.1f})",
                    detail=f"pos=({cx:.1f},{cy:.1f}) target=({px:.1f},{py:.1f})",
                )]
        elif c.region is not None:
            bx1, by1, bx2, by2 = _bbox(self.placement, ref)
            rx1, ry1, rx2, ry2 = c.region
            if bx1 < rx1 or by1 < ry1 or bx2 > rx2 or by2 > ry2:
                return [AuditViolation(
                    constraint_id=c.id, constraint_type=c.constraint_type.value,
                    description=f"ANCHORED {ref} outside region",
                    detail=f"bbox=({bx1:.1f},{by1:.1f})-({bx2:.1f},{by2:.1f}) region=({rx1},{ry1})-({rx2},{ry2})",
                )]
        return []

    def _check_keepout(self, c: KeepoutConstraint) -> list[AuditViolation]:
        zone = self.placement.zones.get(c.zone_name)
        if zone is None:
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
                return [AuditViolation(
                    constraint_id=c.id, constraint_type=c.constraint_type.value,
                    description=f"KEEPOUT {ref} overlaps keepout {c.zone_name}",
                    detail=f"bbox=({bx1:.1f},{by1:.1f})-({bx2:.1f},{by2:.1f}) keepout=({kx1:.1f},{ky1:.1f})-({kx2:.1f},{ky2:.1f})",
                )]
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
                    return [AuditViolation(
                        constraint_id=c.id, constraint_type=c.constraint_type.value,
                        description=f"ALIGNED {refs[i]}-{refs[j]} axis={axis} diff={diff:.1f}mm > {tol}mm",
                        detail=f"diff={diff:.1f}",
                    )]
        return []

    def _check_loop_area(
        self, c: LoopAreaConstraint,
        loop_components: dict[str, list[str]] | None = None,
    ) -> list[AuditViolation]:
        comps = loop_components or {}
        loop_comps: list[str] = comps.get(c.loop_name, [])
        if not loop_comps:
            return []
        refs = [r for r in loop_comps if r in self.placement.positions_mm]
        if not refs:
            return []
        min_x = min(
            _bbox(self.placement, r)[0] for r in refs
        )
        min_y = min(
            _bbox(self.placement, r)[1] for r in refs
        )
        max_x = max(
            _bbox(self.placement, r)[2] for r in refs
        )
        max_y = max(
            _bbox(self.placement, r)[3] for r in refs
        )
        aabb_area = (max_x - min_x) * (max_y - min_y)
        if aabb_area > c.max_area_mm2:
            return [AuditViolation(
                constraint_id=c.id, constraint_type=c.constraint_type.value,
                description=f"LOOP_AREA AABB={aabb_area:.1f}mm2 > {c.max_area_mm2}mm2",
                detail=f"aabb=({min_x:.1f},{min_y:.1f})-({max_x:.1f},{max_y:.1f}) area={aabb_area:.1f}",
            )]
        return []

    def _resolve(self, name: str) -> list[str]:
        """Resolve a name to component refs."""
        if name in self.placement.positions_mm:
            return [name]
        if name in self.placement.zones and name in self.placement.zone_components:
            return [r for r in self.placement.zone_components[name] if r in self.placement.positions_mm]
        return []
