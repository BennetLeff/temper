"""U4: Post-solve constraint audit for CP-SAT placement.

Verifies every hard constraint encoded in the CP-SAT model is satisfied
by the solver output. Runs unconditionally after every solve — never trust
solver output without verification (see docs/solutions/logic-errors/
unsound-atmostk-capacity-encoding.md).

Audit checks mirror the constraint semantics in model.py exactly:
  - No-overlap: AABB pairwise check (R1)
  - Clearance: Chebyshev edge-to-edge distance >= threshold (R2)
  - Edge anchoring: component-to-edge distance <= max (R3)
  - Adjacency: 4 linear proximity inequalities (R4)
  - Region membership: component wholly within bounds (R5)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Violation:
    """A single constraint violation found by the audit.

    Attributes:
        constraint_type: One of 'no_overlap', 'clearance', 'edge_anchor',
            'adjacency', 'region_membership'.
        components: Component reference(s) involved in the violation.
        actual: The measured value (mm) that triggered the violation.
        expected: The expected threshold value (mm).
        detail: Human-readable description of the violation.
    """

    constraint_type: str
    components: list[str]
    actual: float
    expected: float
    detail: str


@dataclass
class AuditReport:
    """Result of the post-solve constraint audit.

    Attributes:
        passed: True iff all audited constraints are satisfied.
        violations: List of Violation objects (empty when passed=True).
        stats: Dict with 'checked', 'passed', 'failed' counts.
    """

    passed: bool
    violations: list[Violation] = field(default_factory=list)
    stats: dict = field(
        default_factory=lambda: {"checked": 0, "passed": 0, "failed": 0}
    )


def _get_size(ref: str, components: dict) -> tuple[float, float]:
    """Extract (width_mm, height_mm) from a component dict.

    Accepts keys: 'width_mm'/'height_mm', 'w'/'h', or 'width'/'height'.
    """
    c = components[ref]
    w = c.get("width_mm", c.get("w", c.get("width", 0)))
    h = c.get("height_mm", c.get("h", c.get("height", 0)))
    return float(w), float(h)


def _build_boxes(
    positions: dict[str, tuple[float, float]],
    components: dict[str, dict],
) -> dict[str, tuple[float, float, float, float]]:
    """Build bounding-box dict: {ref: (left, bottom, right, top)} in mm."""
    boxes: dict[str, tuple[float, float, float, float]] = {}
    for ref in positions:
        x, y = positions[ref]
        w, h = _get_size(ref, components)
        boxes[ref] = (x, y, x + w, y + h)
    return boxes


def _aabb_overlap(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> bool:
    """Check if two axis-aligned bounding boxes overlap (not just touching).

    Each box is (left, bottom, right, top). Overlap occurs when intervals
    overlap in BOTH x and y axes. Exact touching (e.g. a.right == b.left)
    does NOT count as overlap.
    """
    al, ab, ar, at = a
    bl, bb, br, bt = b
    return al < br and ar > bl and ab < bt and at > bb


def _audit_no_overlap(
    boxes: dict[str, tuple[float, float, float, float]],
    refs: list[str],
    violations: list[Violation],
    checked: int,
) -> tuple[int, int]:
    """Check all component pairs for AABB overlap (R1)."""
    no_overlap_passed = 0
    for i in range(len(refs)):
        for j in range(i + 1, len(refs)):
            checked += 1
            ri, rj = refs[i], refs[j]
            if _aabb_overlap(boxes[ri], boxes[rj]):
                a = boxes[ri]
                b = boxes[rj]
                overlap_x = min(a[2], b[2]) - max(a[0], b[0])
                overlap_y = min(a[3], b[3]) - max(a[1], b[1])
                violations.append(
                    Violation(
                        constraint_type="no_overlap",
                        components=[ri, rj],
                        actual=max(overlap_x, overlap_y),
                        expected=0.0,
                        detail=(
                            f"Components {ri} and {rj} overlap: "
                            f"{overlap_x:.2f}mm x {overlap_y:.2f}mm "
                            f"({ri}=({a[0]:.1f},{a[1]:.1f})-({a[2]:.1f},{a[3]:.1f}), "
                            f"{rj}=({b[0]:.1f},{b[1]:.1f})-({b[2]:.1f},{b[3]:.1f}))"
                        ),
                    )
                )
            else:
                no_overlap_passed += 1
    return checked, no_overlap_passed


def _audit_clearance(
    constraints: dict,
    boxes: dict[str, tuple[float, float, float, float]],
    violations: list[Violation],
    checked: int,
    passed: int,
) -> tuple[int, int]:
    """Check Chebyshev edge-to-edge clearance (R2).

    For each (a, b) pair, at least one of the 4 directional edge-to-edge
    distances must be >= min_dist_mm. This matches the model's BoolOr
    encoding in add_chebyshev_clearance.
    """
    for entry in constraints.get("clearance_pairs", []):
        if len(entry) == 3:
            a, b, min_dist = entry[0], entry[1], float(entry[2])
        else:
            continue

        checked += 1
        if a not in boxes or b not in boxes:
            continue

        a_l, a_b, a_r, a_t = boxes[a]
        b_l, b_b, b_r, b_t = boxes[b]

        # 4 directional edge-to-edge distances (as encoded in the model):
        # left_of: a's right edge to b's left edge (a is to the left of b)
        # right_of: b's right edge to a's left edge (b is to the left of a)
        # below: a's top edge to b's bottom edge (a is below b)
        # above: b's top edge to a's bottom edge (b is below a)
        left_of = b_l - a_r
        right_of = a_l - b_r
        below = b_b - a_t
        above = a_b - b_t

        actual_clearance = max(left_of, right_of, below, above, 0.0)

        if actual_clearance < min_dist - 1e-9:
            violations.append(
                Violation(
                    constraint_type="clearance",
                    components=[a, b],
                    actual=actual_clearance,
                    expected=min_dist,
                    detail=(
                        f"Chebyshev edge-to-edge clearance {actual_clearance:.2f}mm "
                        f"< {min_dist:.1f}mm for {a}-{b} "
                        f"(left_of={left_of:.2f}, right_of={right_of:.2f}, "
                        f"below={below:.2f}, above={above:.2f})"
                    ),
                )
            )
        else:
            passed += 1

    return checked, passed


def _audit_edge_anchors(
    constraints: dict,
    positions: dict[str, tuple[float, float]],
    components: dict[str, dict],
    boxes: dict[str, tuple[float, float, float, float]],
    board_w_mm: float | None,
    board_h_mm: float | None,
    violations: list[Violation],
    checked: int,
    passed: int,
) -> tuple[int, int]:
    """Check edge anchoring distances (R3).

    For each (ref, edge, max_dist_mm), verifies the distance from the
    component's specified edge to the board edge is <= max_dist_mm.
    "right" and "top" edges require board_w_mm / board_h_mm respectively.
    """
    for entry in constraints.get("edge_anchors", []):
        if len(entry) == 3:
            ref, edge, max_dist = entry[0], entry[1], float(entry[2])
        else:
            continue

        checked += 1
        if ref not in boxes:
            continue

        box = boxes[ref]
        x, y = positions[ref]
        w, h = _get_size(ref, components)

        if edge == "left":
            dist = x
        elif edge == "bottom":
            dist = y
        elif edge == "right":
            if board_w_mm is None:
                dist = x + w  # fallback: report distance of right edge from origin
            else:
                dist = board_w_mm - (x + w)
        elif edge == "top":
            if board_h_mm is None:
                dist = y + h  # fallback: report distance of top edge from origin
            else:
                dist = board_h_mm - (y + h)
        else:
            continue

        if dist > max_dist + 1e-9:
            violations.append(
                Violation(
                    constraint_type="edge_anchor",
                    components=[ref],
                    actual=dist,
                    expected=max_dist,
                    detail=(
                        f"Component {ref} {edge}-edge distance {dist:.2f}mm "
                        f"> {max_dist:.1f}mm (position=({x:.1f},{y:.1f}), "
                        f"size=({w:.1f},{h:.1f}))"
                    ),
                )
            )
        else:
            passed += 1

    return checked, passed


def _audit_adjacency(
    constraints: dict,
    boxes: dict[str, tuple[float, float, float, float]],
    components: dict[str, dict],
    violations: list[Violation],
    checked: int,
    passed: int,
) -> tuple[int, int]:
    """Check pairwise adjacency constraints (R4).

    For each (a, b, max_dist_mm), verifies the same 4 linear inequalities
    as add_proximity in model.py:
      x_start[b] <= x_start[a] + w_a + max_d
      x_start[a] <= x_start[b] + w_b + max_d
      y_start[b] <= y_start[a] + h_a + max_d
      y_start[a] <= y_start[b] + h_b + max_d
    """
    for entry in constraints.get("adjacent_pairs", []):
        if len(entry) == 3:
            a, b, max_dist = entry[0], entry[1], float(entry[2])
        else:
            continue

        checked += 1
        if a not in boxes or b not in boxes:
            continue

        x_a, y_a = boxes[a][0], boxes[a][1]
        x_b, y_b = boxes[b][0], boxes[b][1]
        w_a, h_a = _get_size(a, components)
        w_b, h_b = _get_size(b, components)

        candidates = [
            (x_b, x_a + w_a + max_dist, "x_start[b] <= x_start[a] + w_a + max_d"),
            (x_a, x_b + w_b + max_dist, "x_start[a] <= x_start[b] + w_b + max_d"),
            (y_b, y_a + h_a + max_dist, "y_start[b] <= y_start[a] + h_a + max_d"),
            (y_a, y_b + h_b + max_dist, "y_start[a] <= y_start[b] + h_b + max_d"),
        ]

        failed_inequalities = []
        for lhs, rhs, desc in candidates:
            if lhs > rhs + 1e-9:
                failed_inequalities.append(f"{desc}: {lhs:.2f} <= {rhs:.2f}")

        if failed_inequalities:
            violations.append(
                Violation(
                    constraint_type="adjacency",
                    components=[a, b],
                    actual=max(
                        abs(x_b - x_a) - w_a,
                        abs(x_a - x_b) - w_b,
                        abs(y_b - y_a) - h_a,
                        abs(y_a - y_b) - h_b,
                        0.0,
                    ),
                    expected=max_dist,
                    detail=(
                        f"Components {a} and {b} exceed max adjacency distance "
                        f"{max_dist:.1f}mm: {'; '.join(failed_inequalities)}"
                    ),
                )
            )
        else:
            passed += 1

    return checked, passed


def _audit_region_membership(
    constraints: dict,
    boxes: dict[str, tuple[float, float, float, float]],
    components: dict[str, dict],
    violations: list[Violation],
    checked: int,
    passed: int,
) -> tuple[int, int]:
    """Check region membership constraints (R5).

    For each (ref, region_bounds), checks the component is wholly within
    [x_min, x_max] x [y_min, y_max].
    """
    for entry in constraints.get("region_members", []):
        if len(entry) == 5:
            ref, x_min, x_max, y_min, y_max = (
                entry[0],
                float(entry[1]),
                float(entry[2]),
                float(entry[3]),
                float(entry[4]),
            )
        elif len(entry) == 2:
            ref, bounds = entry[0], entry[1]
            x_min, x_max, y_min, y_max = (
                float(bounds[0]),
                float(bounds[1]),
                float(bounds[2]),
                float(bounds[3]),
            )
        else:
            continue

        checked += 1
        if ref not in boxes:
            continue

        a_l, a_b, a_r, a_t = boxes[ref]

        out_of_bounds = []
        if a_l < x_min - 1e-9:
            out_of_bounds.append(f"left edge {a_l:.2f} < {x_min:.1f}")
        if a_r > x_max + 1e-9:
            out_of_bounds.append(f"right edge {a_r:.2f} > {x_max:.1f}")
        if a_b < y_min - 1e-9:
            out_of_bounds.append(f"bottom edge {a_b:.2f} < {y_min:.1f}")
        if a_t > y_max + 1e-9:
            out_of_bounds.append(f"top edge {a_t:.2f} > {y_max:.1f}")

        if out_of_bounds:
            actual_max_excess = max(
                max(x_min - a_l, 0.0),
                max(a_r - x_max, 0.0),
                max(y_min - a_b, 0.0),
                max(a_t - y_max, 0.0),
            )
            violations.append(
                Violation(
                    constraint_type="region_membership",
                    components=[ref],
                    actual=actual_max_excess,
                    expected=0.0,
                    detail=(
                        f"Component {ref} outside region "
                        f"[{x_min:.1f}, {x_max:.1f}] x [{y_min:.1f}, {y_max:.1f}]: "
                        f"{'; '.join(out_of_bounds)}"
                    ),
                )
            )
        else:
            passed += 1

    return checked, passed


def audit_placement(
    positions: dict[str, tuple[float, float]],
    components: dict[str, dict],
    constraints: dict | None = None,
    scale_factor: int = 10,
    board_w_mm: float | None = None,
    board_h_mm: float | None = None,
) -> AuditReport:
    """Audit a placement against all hard constraints.

    Verifies every constraint type encoded in model.py against the
    solved position values. Matches the model's semantics exactly:
    pairwise NoOverlap2D (R1), Chebyshev clearance (R2), edge anchoring
    (R3), linear proximity adjacency (R4), and region membership (R5).

    The audit runs unconditionally — it is not gated on debug mode.

    Args:
        positions: {ref: (x_mm, y_mm)} bottom-left corner coordinates in mm.
        components: {ref: {w/width_mm: float, h/height_mm: float}} component
            dimensions. Accepts 'w'/'h', 'width_mm'/'height_mm', or
            'width'/'height' keys.
        constraints: Optional dict with these keys (all optional):
            - clearance_pairs: list of (a, b, min_dist_mm)
            - adjacent_pairs: list of (a, b, max_dist_mm)
            - edge_anchors: list of (ref, edge, max_dist_mm)
                where edge is 'left'|'right'|'bottom'|'top'
            - region_members: list of
                (ref, x_min, x_max, y_min, y_max) or
                (ref, (x_min, x_max, y_min, y_max))
        scale_factor: Grid scale (units per mm). Kept for API compatibility
            with the model; audit works in mm-space.
        board_w_mm: Board width in mm (required for 'right' edge anchors).
        board_h_mm: Board height in mm (required for 'top' edge anchors).

    Returns:
        AuditReport with passed/violations/stats.

    Raises:
        KeyError: If a component referenced in a constraint is not found
            in the positions dict.
    """
    constraints = constraints or {}
    violations: list[Violation] = []

    refs = list(positions.keys())

    # Validate all constraint-referenced components exist
    _validate_constraint_refs(constraints, positions)

    boxes = _build_boxes(positions, components)

    # Track stats as we go
    checked = 0
    no_overlap_passed = 0
    clearance_passed = 0
    edge_passed = 0
    adj_passed = 0
    region_passed = 0

    # 1. No-overlap (R1)
    checked, no_overlap_passed = _audit_no_overlap(boxes, refs, violations, checked)

    # 2. Clearance (R2)
    checked, clearance_passed = _audit_clearance(
        constraints, boxes, violations, checked, 0
    )

    # 3. Edge anchoring (R3)
    checked, edge_passed = _audit_edge_anchors(
        constraints,
        positions,
        components,
        boxes,
        board_w_mm,
        board_h_mm,
        violations,
        checked,
        0,
    )

    # 4. Adjacency (R4)
    checked, adj_passed = _audit_adjacency(
        constraints, boxes, components, violations, checked, 0
    )

    # 5. Region membership (R5)
    checked, region_passed = _audit_region_membership(
        constraints, boxes, components, violations, checked, 0
    )

    total_passed = (
        no_overlap_passed + clearance_passed + edge_passed + adj_passed + region_passed
    )

    return AuditReport(
        passed=len(violations) == 0,
        violations=violations,
        stats={
            "checked": checked,
            "passed": total_passed,
            "failed": len(violations),
        },
    )


def _validate_constraint_refs(
    constraints: dict, positions: dict[str, tuple[float, float]]
) -> None:
    """Validate that all constraint-referenced components exist in positions.

    Raises KeyError with a descriptive message for the first missing reference.
    """
    all_refs = set(positions.keys())

    for entry in constraints.get("clearance_pairs", []):
        if len(entry) >= 2:
            for r in (entry[0], entry[1]):
                if r not in all_refs:
                    raise KeyError(
                        f"Clearance constraint references component '{r}' "
                        f"which is not in the placement"
                    )

    for entry in constraints.get("adjacent_pairs", []):
        if len(entry) >= 2:
            for r in (entry[0], entry[1]):
                if r not in all_refs:
                    raise KeyError(
                        f"Adjacency constraint references component '{r}' "
                        f"which is not in the placement"
                    )

    for entry in constraints.get("edge_anchors", []):
        if len(entry) >= 1:
            r = entry[0]
            if r not in all_refs:
                raise KeyError(
                    f"Edge anchor references component '{r}' "
                    f"which is not in the placement"
                )

    for entry in constraints.get("region_members", []):
        if len(entry) >= 1:
            r = entry[0]
            if r not in all_refs:
                raise KeyError(
                    f"Region membership references component '{r}' "
                    f"which is not in the placement"
                )
