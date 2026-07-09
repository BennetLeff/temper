"""DeltaMapper: Maps Violation -> ConstraintDelta. Shared across gates.

Per ``docs/plans/2026-07-08-007-feat-compound-place-route-loop-plan.md`` U3:
a single `DeltaMapper.map()` dispatches by `ViolationType` to the correct
existing PCL constraint.  Every gate's `to_delta()` delegates here so
constraint construction has one home.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.placer.cp_sat.feedback import ConstraintDelta
    from temper_placer.placer.cp_sat.gates import Violation


class DeltaMapper:
    """Maps Violation -> ConstraintDelta. Shared across gates.

    Dispatch by ``ViolationType`` onto the existing PCL constraint
    vocabulary.  No new PCL types are introduced.
    """

    _CLEARANCE_DELTA_MM: float = 0.1  # Pad by 0.1 mm per round.

    @staticmethod
    def map(violation: Violation) -> ConstraintDelta | None:
        """Map a Violation to a ConstraintDelta the loop can inject.

        Returns ``None`` for violation types placement cannot fix
        (e.g. intra-component clearance, or informational-only types).
        """
        from temper_placer.placer.cp_sat.gates import ViolationType
        from temper_placer.placer.cp_sat.feedback import ConstraintDelta
        from temper_placer.pcl.constraints import (
            AnchoredConstraint,
            ConstraintTier,
            KeepoutConstraint,
            LoopAreaConstraint,
            SeparatedConstraint,
        )

        vtype = violation.type

        # ---- CLEARANCE -> SeparatedConstraint (HARD) --------------------
        if vtype is ViolationType.CLEARANCE:
            comps = violation.components
            if len(comps) < 2:
                return None
            a, b = comps[0], comps[1]
            min_dist = violation.severity + DeltaMapper._CLEARANCE_DELTA_MM
            cid = f"feedback_clearance_{a}_{b}"
            constraint = SeparatedConstraint(
                a=a,
                b=b,
                min_distance_mm=min_dist,
                tier=ConstraintTier.HARD,
                because=(
                    violation.description
                    or f"DRC clearance violation: {a}-{b}"
                ),
                id=cid,
            )
            return ConstraintDelta(
                constraint=constraint,
                reason=f"Clearance violation: {a}-{b} needs {min_dist:.1f}mm",
                priority=5,
            )

        # ---- UNROUTED -> AnchoredConstraint (STRONG) --------------------
        if vtype is ViolationType.UNROUTED:
            nets = violation.nets
            comps = violation.components
            net_name = nets[0] if nets else ""
            comp_ref = comps[0] if comps else ""
            if not comp_ref:
                return None

            region_ctx = violation.context.get("region", None)
            if region_ctx and len(region_ctx) == 4:
                region = (
                    float(region_ctx[0]),
                    float(region_ctx[1]),
                    float(region_ctx[2]),
                    float(region_ctx[3]),
                )
            else:
                region = (-10.0, -10.0, 10.0, 10.0)

            cid = f"feedback_unrouted_{comp_ref}_{net_name}"
            constraint = AnchoredConstraint(
                component=comp_ref,
                region=region,
                tier=ConstraintTier.STRONG,
                because=(
                    f"Unrouted net {net_name} on {comp_ref} "
                    f"â€” bias position for routing"
                ),
                id=cid,
            )
            return ConstraintDelta(
                constraint=constraint,
                reason=f"Unrouted pin on {comp_ref} (net {net_name})",
                priority=15,
            )

        # ---- LOOP_INDUCTANCE -> LoopAreaConstraint (SOFT) ---------------
        if vtype is ViolationType.LOOP_INDUCTANCE:
            loop_name = str(violation.context.get("loop", "commutation"))
            max_area = float(violation.context.get("max_area_mm2", 2000.0))
            tightened = min(violation.severity * 0.95, max_area * 0.95)
            cid = f"loop_{loop_name}"
            constraint = LoopAreaConstraint(
                loop_name=loop_name,
                max_area_mm2=tightened,
                tier=ConstraintTier.SOFT,
                because=(
                    f"Loop inductance: {violation.severity:.1f} > "
                    f"{violation.threshold:.1f} mmÂ²"
                ),
                id=cid,
            )
            return ConstraintDelta(
                constraint=constraint,
                reason=(
                    f"Loop area {violation.severity:.1f} mmÂ² > "
                    f"{violation.threshold:.1f} mmÂ²"
                ),
                priority=30,
            )

        # ---- THERMAL -> SeparatedConstraint (HARD) ----------------------
        if vtype is ViolationType.THERMAL:
            comps = violation.components
            if len(comps) < 2:
                return None
            a, b = comps[0], comps[1]
            min_dist = violation.threshold + 1.0
            cid = f"feedback_thermal_{a}_{b}"
            constraint = SeparatedConstraint(
                a=a,
                b=b,
                min_distance_mm=min_dist,
                tier=ConstraintTier.HARD,
                because=(
                    violation.description
                    or f"Thermal separation: {a}-{b}"
                ),
                id=cid,
            )
            return ConstraintDelta(
                constraint=constraint,
                reason=f"Thermal violation: {a}-{b} needs {min_dist:.1f}mm",
                priority=10,
            )

        # ---- CREEPAGE -> SeparatedConstraint (HARD) ---------------------
        if vtype is ViolationType.CREEPAGE:
            nets = violation.nets
            if len(nets) < 2:
                return None
            a, b = nets[0], nets[1]
            min_dist = violation.threshold
            cid = f"feedback_creepage_{a}_{b}"
            constraint = SeparatedConstraint(
                a=a,
                b=b,
                min_distance_mm=min_dist,
                tier=ConstraintTier.HARD,
                because=(
                    violation.description
                    or f"IEC creepage: {a}-{b}"
                ),
                id=cid,
            )
            return ConstraintDelta(
                constraint=constraint,
                reason=f"Creepage violation: {a}-{b} needs {min_dist:.1f}mm",
                priority=5,
            )

        # ---- VIA_COUNT -> KeepoutConstraint (SOFT) ----------------------
        if vtype is ViolationType.VIA_COUNT:
            device = str(violation.context.get("device", "via_region"))
            zone_name = f"keepout_vias_{device}"
            cid = f"feedback_via_count_{device}"
            constraint = KeepoutConstraint(
                zone_name=zone_name,
                tier=ConstraintTier.SOFT,
                because=violation.description or "Insufficient thermal vias",
                id=cid,
            )
            return ConstraintDelta(
                constraint=constraint,
                reason=f"Via count: {violation.description}",
                priority=20,
            )

        # ---- SLOP -> KeepoutConstraint (SOFT) ---------------------------
        if vtype is ViolationType.SLOP:
            artifact_type = str(
                violation.context.get("artifact_type", "slop")
            )
            artifacts = violation.context.get("artifacts", [])
            if artifacts and isinstance(artifacts, list):
                first = artifacts[0]
                net_name = str(first.get("net_name", "?"))
            else:
                net_name = "?"
            zone_name = f"SLOP_{artifact_type}_{net_name}"
            cid = f"feedback_slop_{zone_name}"
            constraint = KeepoutConstraint(
                zone_name=zone_name,
                tier=ConstraintTier.SOFT,
                because=(
                    violation.description
                    or "Slop artifact detected â€” keep components clear"
                ),
                id=cid,
            )
            return ConstraintDelta(
                constraint=constraint,
                reason=f"Slop artifact: {violation.description}",
                priority=30,
            )

        return None
