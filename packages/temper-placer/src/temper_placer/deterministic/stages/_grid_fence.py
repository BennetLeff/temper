class FenceViolation(RuntimeError):
    """Raised when the U3 clearance-grid fence detects a non-conservative expansion.

    The fence (R8) samples the boundary of every (pad, layer) expansion
    produced by the U2 pass and asserts each sample lies inside the
    blocked region of the produced grid. A miss means the expansion under-
    blocked: a downstream A* run would think the cell is free and route
    through it, violating creepage. The exception names the offending
    pad (ref, pin_name), layer, sample coordinate, and a human-readable
    reason so the failure is actionable from CI logs.

    @req(2026-06-23-005, R8)
    """


# @req(2026-06-23-005, U2): Module-level log of expansion operations. Rebuilt
# on every `clearance_grid` stage run; consumed by the fence (U3) and the
# closure test (U4a). Persistent state is not used.
#
# Each entry is a tuple:
#   (ref, pin_name, layer_idx, pos, shape, radius, size, eff_creep, cells_added)
# where shape ∈ {"circle", "rect", "roundrect", "oval"} and `size` is the
# bbox (w, h) for rect-shaped pads (or (0, 0) for circles).
_EXPANSION_LOG: list[tuple] = []


# @req(2026-06-23-005, U3): Per-stage fence that asserts the expansion is
# conservative. Returns a list of (ref, pin_name, layer, sample_xy, reason)
# violations; empty list means the expansion is conservative on every
# (pad, layer) pair in `_EXPANSION_LOG`.
#
# Cell quantization: the grid is a discrete array; cells are square and
# the cell center sits at (col*cell + cell/2, row*cell + cell/2). Sampling
# exactly on the boundary radius `pad_radius + eff_creep` can land on a
# cell whose center is just outside the radius. To accommodate, the fence
# samples at `boundary - cell/2` so the cell containing the sample is the
# one just *inside* the boundary. This matches the ±0.5 cell tolerance in
# the plan's R8 and the existing test scenarios.
def check_clearance_grid_conservatism(
    grid,
    expansion_log=None,
    sample_count_circle: int = 16,
):
    """Verify the expanded grid blocks the creepage boundary on every layer.

    For circular pads, sample `sample_count_circle` points on a circle of
    radius `pad_radius + eff_creep - cell/2` and assert each cell is blocked.
    For rect pads, sample 4 corners and 4 edge midpoints offset by
    `eff_creep - cell/2` on each side. The cell/2 inset is the ±0.5 cell
    tolerance required by R8.

    Args:
        grid: The `ClearanceGrid` produced by the stage.
        expansion_log: Iterable of tuples as written by U2. Defaults to the
            module-level `_EXPANSION_LOG`.
        sample_count_circle: Number of points to sample on circular pads.

    Returns:
        List of violation dicts. Each has ``ref``, ``pin_name``, ``layer``,
        ``xy``, and ``reason``. Empty list means conservative.
    """
    log = expansion_log if expansion_log is not None else _EXPANSION_LOG
    violations: list[dict] = []
    import math

    cell = grid.cell_size_mm
    inset = cell / 2.0  # ±0.5 cell tolerance per R8

    for entry in log:
        (ref, pin_name, layer_idx, pos, shape, pad_radius, pad_size, eff_creep, _cells_added) = (
            entry
        )
        if layer_idx < 0 or layer_idx >= grid.layer_count:
            continue

        samples: list[tuple[float, float]] = []
        if shape in ("rect", "roundrect", "oval") and pad_size[0] > 0 and pad_size[1] > 0:
            cx, cy = pos
            w, h = pad_size
            eff = eff_creep - inset
            # 4 corners expanded by eff on each side
            samples.append((cx - w / 2 - eff, cy - h / 2 - eff))
            samples.append((cx + w / 2 + eff, cy - h / 2 - eff))
            samples.append((cx - w / 2 - eff, cy + h / 2 + eff))
            samples.append((cx + w / 2 + eff, cy + h / 2 + eff))
            # 4 edge midpoints
            samples.append((cx, cy - h / 2 - eff))
            samples.append((cx, cy + h / 2 + eff))
            samples.append((cx - w / 2 - eff, cy))
            samples.append((cx + w / 2 + eff, cy))
        else:
            cx, cy = pos
            r = pad_radius + eff_creep - inset
            for i in range(sample_count_circle):
                theta = 2.0 * math.pi * i / sample_count_circle
                samples.append((cx + r * math.cos(theta), cy + r * math.sin(theta)))

        for x, y in samples:
            if grid.is_available(x, y, layer=layer_idx):
                violations.append(
                    {
                        "ref": ref,
                        "pin_name": pin_name,
                        "layer": layer_idx,
                        "xy": (x, y),
                        "reason": (
                            f"cell at ({x:.3f}, {y:.3f}) on layer {layer_idx} is "
                            f"unblocked but should be inside the expanded creepage "
                            f"boundary for pad {ref}.{pin_name}"
                        ),
                    }
                )

    return violations


def check_clearance_grid_perf_budget(
    fence_elapsed_ms: float,
    stage_elapsed_ms: float,
    budget_pct: float = 20.0,
    floor_ms: float = 50.0,
) -> tuple[bool, str | None]:
    """Return (over_budget, warning_message) for fence wall-time.

    The fence is allowed to overrun the soft 20% budget; we emit a WARNING
    rather than a hard failure to keep CI flakes off critical path
    (per the plan's R4: "soft warning, not a hard gate").
    """
    if stage_elapsed_ms < floor_ms:
        return False, None
    overhead_pct = (fence_elapsed_ms / stage_elapsed_ms) * 100.0
    if overhead_pct > budget_pct:
        return True, (
            f"fence overhead {overhead_pct:.1f}% exceeds budget "
            f"{budget_pct:.1f}% (fence={fence_elapsed_ms:.1f}ms, "
            f"stage={stage_elapsed_ms:.1f}ms)"
        )
    return False, None
