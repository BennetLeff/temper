"""U0: CP-SAT Feasibility Spike for Temper Induction Board.

Throwaway script — validates that CP-SAT can place ~33 components on the temper
board (100mm x 150mm) within 60s with all hard constraints satisfied.
"""

import sys
import time

from ortools.sat.python import cp_model

# ---- Board parameters ----
BOARD_W_MM = 100.0
BOARD_H_MM = 150.0
SCALE = 10  # 0.1mm grid
BOARD_W = int(BOARD_W_MM * SCALE)
BOARD_H = int(BOARD_H_MM * SCALE)

# ---- HV clearance ----
CREEPAGE_MM = 6.0
SAFETY_FACTOR = 1.414213562  # sqrt(2)
CLEARANCE_MM = CREEPAGE_MM * SAFETY_FACTOR  # ~8.5mm
CLEARANCE = int(CLEARANCE_MM * SCALE)

# ---- Zone definitions (mm, scaled) ----
HV_ZONE = {
    "x_min": int(5 * SCALE),
    "x_max": int(55 * SCALE),
    "y_min": int(5 * SCALE),
    "y_max": int(145 * SCALE),
}
MCU_ZONE = {
    "x_min": int(60 * SCALE),
    "x_max": int(95 * SCALE),
    "y_min": int(5 * SCALE),
    "y_max": int(145 * SCALE),
}

# ---- Realistic component sizes (W x H in mm) ----
# HV components
HV_COMPS = {
    "Q1": (22, 16),  # IGBT
    "Q2": (22, 16),  # IGBT
    "D1": (6, 3),  # Diode
    "C_DC": (18, 32),  # DC-link cap
}
# LV / MCU components
LV_COMPS = {
    "U_MCU": (10, 10),
    "U_GATE_DRV": (5, 7),
    "C1": (4, 3),  # Decoupling cap
    "C2": (4, 3),
    "C3": (4, 3),
    "C4": (4, 3),
    "C5": (4, 3),
    "C6": (4, 3),
    "R1": (6, 2),  # Resistor
    "R2": (6, 2),
    "R3": (6, 2),
    "R4": (6, 2),
    "R5": (6, 2),
    "J_AC": (12, 8),  # Connector
    "J_COIL": (12, 8),  # Connector
    "U_OPTO": (5, 7),  # Optocoupler
    "U_REG": (6, 5),  # Voltage regulator
    "L1": (14, 14),  # Inductor
    "C_BUS": (10, 16),  # Bus capacitor
    "R_SHUNT": (10, 5),  # Shunt resistor
    "D_ZENER": (3, 5),  # Zener
    "Q_AUX": (5, 5),  # Aux transistor
    "U_AMP": (5, 5),  # Op-amp
    "R_PULLUP": (6, 2),
    "R_PULLDOWN": (6, 2),
    "C_BYPASS": (4, 3),
    "C_FILTER": (6, 4),
    "D_TVS": (5, 3),  # TVS diode
    "F1": (8, 4),  # Fuse
}

ALL_COMPS = {**HV_COMPS, **LV_COMPS}
HV_REFS = set(HV_COMPS.keys())
LV_REFS = set(LV_COMPS.keys())

# HV↔LV pairs that need clearance (simplified: all HV vs all LV that could be close)
# In practice this is selective; for the spike we check all cross-zone pairs.
HV_LV_PAIRS = [(h, lv) for h in HV_REFS for lv in LV_REFS]

# ---- Adjacency constraints ----
ADJACENT_PAIRS = [
    ("Q1", "Q2", 10),  # Commutation loop
    ("U_GATE_DRV", "Q1", 15),  # Gate driver proximity
]

# ---- Edge constraints ----
LEFT_EDGE_COMPS = ["J_AC", "J_COIL"]
LEFT_EDGE_MAX_DIST = 2  # mm

# ---- Enclosed components ----
HV_ENCLOSED = ["Q1", "Q2", "D1", "C_DC"]


def model_coord(ref: str, dim: int) -> int:
    """Return component size in grid units for the given dimension."""
    mm = ALL_COMPS[ref][0] if dim == 0 else ALL_COMPS[ref][1]
    return int(mm * SCALE)


def build_model():
    model = cp_model.CpModel()

    # Per-component variables
    x_start = {}
    y_start = {}
    x_size = {}
    y_size = {}
    x_iv = {}
    y_iv = {}

    for ref in ALL_COMPS:
        w = model_coord(ref, 0)
        h = model_coord(ref, 1)
        x_size[ref] = w
        y_size[ref] = h

        x_start[ref] = model.NewIntVar(0, BOARD_W - w, f"x_{ref}")
        x_end = model.NewIntVar(w, BOARD_W, f"x_end_{ref}")
        x_iv[ref] = model.NewIntervalVar(x_start[ref], w, x_end, f"xiv_{ref}")

        y_start[ref] = model.NewIntVar(0, BOARD_H - h, f"y_{ref}")
        y_end = model.NewIntVar(h, BOARD_H, f"y_end_{ref}")
        y_iv[ref] = model.NewIntervalVar(y_start[ref], h, y_end, f"yiv_{ref}")

    # R1: NoOverlap2D
    x_ivs = [x_iv[r] for r in ALL_COMPS]
    y_ivs = [y_iv[r] for r in ALL_COMPS]
    model.AddNoOverlap2D(x_ivs, y_ivs)

    # R2: Chebyshev clearance (HV ↔ LV pairs)
    for hv_ref, lv_ref in HV_LV_PAIRS:
        b_left = model.NewBoolVar(f"clr_left_{hv_ref}_{lv_ref}")
        b_right = model.NewBoolVar(f"clr_right_{hv_ref}_{lv_ref}")
        b_below = model.NewBoolVar(f"clr_below_{hv_ref}_{lv_ref}")
        b_above = model.NewBoolVar(f"clr_above_{hv_ref}_{lv_ref}")

        # HV on left: LV starts at least (HV_x + HV_w + clearance) from left
        model.Add(x_start[lv_ref] >= x_start[hv_ref] + x_size[hv_ref] + CLEARANCE).OnlyEnforceIf(
            b_left
        )
        # HV on right: HV starts at least (LV_x + LV_w + clearance) from left
        model.Add(x_start[hv_ref] >= x_start[lv_ref] + x_size[lv_ref] + CLEARANCE).OnlyEnforceIf(
            b_right
        )
        # HV below: LV starts at least (HV_y + HV_h + clearance) from bottom
        model.Add(y_start[lv_ref] >= y_start[hv_ref] + y_size[hv_ref] + CLEARANCE).OnlyEnforceIf(
            b_below
        )
        # HV above: HV starts at least (LV_y + LV_h + clearance) from bottom
        model.Add(y_start[hv_ref] >= y_start[lv_ref] + y_size[lv_ref] + CLEARANCE).OnlyEnforceIf(
            b_above
        )

        model.AddBoolOr([b_left, b_right, b_below, b_above])

    # R3: Edge anchoring (left-edge components)
    left_edge_dist = int(LEFT_EDGE_MAX_DIST * SCALE)
    for ref in LEFT_EDGE_COMPS:
        model.Add(x_start[ref] <= left_edge_dist)

    # R4: Adjacency (pairwise linear proximity)
    for a, b, max_dist_mm in ADJACENT_PAIRS:
        max_d = int(max_dist_mm * SCALE)
        model.Add(x_start[b] <= x_start[a] + x_size[a] + max_d)
        model.Add(x_start[a] <= x_start[b] + x_size[b] + max_d)
        model.Add(y_start[b] <= y_start[a] + y_size[a] + max_d)
        model.Add(y_start[a] <= y_start[b] + y_size[b] + max_d)

    # R5: Region membership (HV components enclosed in HV_ZONE with 2mm margin)
    margin = int(2 * SCALE)
    for ref in HV_ENCLOSED:
        model.Add(x_start[ref] >= HV_ZONE["x_min"] + margin)
        model.Add(x_start[ref] + x_size[ref] <= HV_ZONE["x_max"] - margin)
        model.Add(y_start[ref] >= HV_ZONE["y_min"] + margin)
        model.Add(y_start[ref] + y_size[ref] <= HV_ZONE["y_max"] - margin)

    # R6: Soft wirelength + spread objective (tiebreaker)
    # Simplified: minimize sum of pairwise Manhattan distances between related components
    objective_terms = []

    # Wirelength proxy: minimize center-to-center distances for key net pairs
    for a, b, _ in ADJACENT_PAIRS:
        # |x_center_a - x_center_b| + |y_center_a - y_center_b|
        dx = model.NewIntVar(0, BOARD_W, f"dx_{a}_{b}")
        dy = model.NewIntVar(0, BOARD_H, f"dy_{a}_{b}")
        cx_a = x_start[a] + x_size[a] // 2
        cx_b = x_start[b] + x_size[b] // 2
        cy_a = y_start[a] + y_size[a] // 2
        cy_b = y_start[b] + y_size[b] // 2
        model.Add(dx >= cx_a - cx_b)
        model.Add(dx >= cx_b - cx_a)
        model.Add(dy >= cy_a - cy_b)
        model.Add(dy >= cy_b - cy_a)
        objective_terms.append(dx)
        objective_terms.append(dy)

    # Bounding-box spread as tiebreaker (very small weight)
    x_min = model.NewIntVar(0, BOARD_W, "x_min")
    x_max = model.NewIntVar(0, BOARD_W, "x_max")
    y_min = model.NewIntVar(0, BOARD_H, "y_min")
    y_max = model.NewIntVar(0, BOARD_H, "y_max")

    for ref in ALL_COMPS:
        model.Add(x_min <= x_start[ref])
        model.Add(x_max >= x_start[ref] + x_size[ref])
        model.Add(y_min <= y_start[ref])
        model.Add(y_max >= y_start[ref] + y_size[ref])

    spread = (x_max - x_min) + (y_max - y_min)

    # Objective: wirelength + epsilon * spread
    model.Minimize(sum(objective_terms) + spread)

    return model, x_start, y_start, x_size, y_size


def audit_placement(x_start, y_start, x_size, y_size):
    """Ad-hoc constraint audit (preview of U4 logic)."""
    violations = []

    # Check R1: No overlap
    refs = list(ALL_COMPS.keys())
    for i in range(len(refs)):
        for j in range(i + 1, len(refs)):
            a, b = refs[i], refs[j]
            ax1 = x_start[a]
            ay1 = y_start[a]
            ax2 = ax1 + x_size[a]
            ay2 = ay1 + y_size[a]
            bx1 = x_start[b]
            by1 = y_start[b]
            bx2 = bx1 + x_size[b]
            by2 = by1 + y_size[b]
            if ax1 < bx2 and ax2 > bx1 and ay1 < by2 and ay2 > by1:
                violations.append(f"OVERLAP: {a} overlaps {b}")

    # Check R2: Clearance
    for hv_ref, lv_ref in HV_LV_PAIRS:
        cx_dist = max(
            abs(x_start[hv_ref] - (x_start[lv_ref] + x_size[lv_ref])),
            abs((x_start[hv_ref] + x_size[hv_ref]) - x_start[lv_ref]),
        )
        cy_dist = max(
            abs(y_start[hv_ref] - (y_start[lv_ref] + y_size[lv_ref])),
            abs((y_start[hv_ref] + y_size[hv_ref]) - y_start[lv_ref]),
        )
        cheb_dist = max(cx_dist, cy_dist)
        if cheb_dist < CLEARANCE:
            violations.append(
                f"CLEARANCE: {hv_ref}↔{lv_ref} Chebyshev distance={cheb_dist / SCALE:.1f}mm < {CLEARANCE / SCALE:.1f}mm"
            )

    # Check R3: Left-edge anchoring
    for ref in LEFT_EDGE_COMPS:
        if x_start[ref] > int(LEFT_EDGE_MAX_DIST * SCALE):
            violations.append(
                f"EDGE: {ref} at x={x_start[ref] / SCALE:.1f}mm > {LEFT_EDGE_MAX_DIST}mm"
            )

    # Check R4: Adjacency (same 4 linear inequalities as CP-SAT model)
    for a, b, max_dist_mm in ADJACENT_PAIRS:
        max_d = int(max_dist_mm * SCALE)
        ok_x = (
            x_start[b] <= x_start[a] + x_size[a] + max_d
            and x_start[a] <= x_start[b] + x_size[b] + max_d
        )
        ok_y = (
            y_start[b] <= y_start[a] + y_size[a] + max_d
            and y_start[a] <= y_start[b] + y_size[b] + max_d
        )
        if not (ok_x and ok_y):
            violations.append(f"ADJACENCY: {a}↔{b} exceeds {max_dist_mm}mm proximity")

    # Check R5: Region membership
    margin = int(2 * SCALE)
    for ref in HV_ENCLOSED:
        if x_start[ref] < HV_ZONE["x_min"] + margin:
            violations.append(f"REGION: {ref} x_min={x_start[ref] / SCALE:.1f} outside HV_ZONE")
        if x_start[ref] + x_size[ref] > HV_ZONE["x_max"] - margin:
            violations.append(f"REGION: {ref} x_max violates HV_ZONE")
        if y_start[ref] < HV_ZONE["y_min"] + margin:
            violations.append(f"REGION: {ref} y_min outside HV_ZONE")
        if y_start[ref] + y_size[ref] > HV_ZONE["y_max"] - margin:
            violations.append(f"REGION: {ref} y_max violates HV_ZONE")

    return violations


def main():
    print(f"CP-SAT Feasibility Spike — Temper Board ({BOARD_W_MM}x{BOARD_H_MM}mm)")
    print(f"N components: {len(ALL_COMPS)}  |  Grid: 0.1mm  |  Clearance: {CLEARANCE_MM:.1f}mm")
    print()

    model, x_start, y_start, x_size, y_size = build_model()

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 60.0
    solver.parameters.num_search_workers = 8
    solver.parameters.log_search_progress = True

    print("Solving (60s timeout, 8 workers)...")
    t0 = time.monotonic()
    status = solver.Solve(model)
    elapsed = time.monotonic() - t0
    print()

    status_name = solver.StatusName(status)
    print(f"Status: {status_name}")
    print(f"Wall time: {elapsed:.1f}s")
    print(
        f"Objective: {solver.ObjectiveValue():.0f}"
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
        else ""
    )

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        print("\nFAIL: No feasible solution found.")
        return 1

    # Extract positions
    positions = {}
    for ref in ALL_COMPS:
        x = solver.Value(x_start[ref]) / SCALE
        y = solver.Value(y_start[ref]) / SCALE
        w = solver.Value(x_size[ref]) / SCALE
        h = solver.Value(y_size[ref]) / SCALE
        positions[ref] = (round(x, 1), round(y, 1), round(w, 1), round(h, 1))

    print("\nPlacement (x, y, w, h in mm):")
    for ref in sorted(positions.keys()):
        x, y, w, h = positions[ref]
        tag = "[HV]" if ref in HV_REFS else "[LV]"
        print(f"  {ref:12s} {tag} ({x:6.1f}, {y:6.1f}) {w:.1f}x{h:.1f}")

    # Audit
    violations = audit_placement(
        {r: solver.Value(x_start[r]) for r in ALL_COMPS},
        {r: solver.Value(y_start[r]) for r in ALL_COMPS},
        x_size,
        y_size,
    )

    print(f"\nConstraint Audit: {'PASSED' if not violations else 'FAILED'}")
    if violations:
        for v in violations:
            print(f"  VIOLATION: {v}")
        return 1

    print(
        f"\nPASS: CP-SAT found feasible placement in {elapsed:.1f}s with all constraints satisfied."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
