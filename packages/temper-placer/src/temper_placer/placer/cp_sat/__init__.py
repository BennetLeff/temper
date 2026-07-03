"""CP-SAT placement engine for temper-placer."""

from temper_placer.placer.cp_sat.audit import AuditReport, Violation, audit_placement
from temper_placer.placer.cp_sat.model import (
    SolveContext,
    SolveResult,
    SolveStatus,
    add_chebyshev_clearance,
    add_edge_anchoring,
    add_no_overlap,
    add_proximity,
    add_region_membership,
    add_soft_wirelength_objective,
    build_cp_sat_model,
    solve_cp_sat_model,
)

__all__ = [
    "AuditReport",
    "SolveContext",
    "SolveResult",
    "SolveStatus",
    "Violation",
    "add_chebyshev_clearance",
    "add_edge_anchoring",
    "add_no_overlap",
    "add_proximity",
    "add_region_membership",
    "add_soft_wirelength_objective",
    "audit_placement",
    "build_cp_sat_model",
    "solve_cp_sat_model",
]
