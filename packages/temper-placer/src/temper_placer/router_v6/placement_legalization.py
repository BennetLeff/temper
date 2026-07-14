"""Placement collision guard used before Router V6 starts routing.

The router receives a placement from CP-SAT, whose constraints include zones,
edge margins, and safety separation.  A local force-directed displacement
cannot preserve those constraints, so it must not silently "legalize" the
board.  This compatibility class retains the historical pipeline seam while
making the stage a fail-closed verification step.
"""

from __future__ import annotations

from temper_placer.router_v6.placement_audit import PlacementAuditor
from temper_placer.router_v6.stage0_data import ParsedPCB


class Legalizer:
    """Check that a placement is collision-free without changing it."""

    def __init__(self, pcb: ParsedPCB):
        self.pcb = pcb
        self.auditor = PlacementAuditor(pcb)

    def legalize(self) -> bool:
        """Return whether the supplied placement has no component overlaps.

        Component movement belongs in the constraint-aware CP-SAT placer.  A
        false result is diagnostic only: this router-level approximation uses
        pin hulls, not KiCad footprint courtyards.  The KiCad DRC run on the
        emitted board is the authoritative, fail-closed geometry gate.
        """
        return not self.auditor.check_collisions()
