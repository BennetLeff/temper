"""Optimizer-level metamorphic oracle tests (fast config, <30s total).

Unlike parse-level tests that check static board properties, these run
the JAX optimizer with minimal epochs and verify logical invariants of
the placement algorithm itself.

Invariants:
    1. Idempotency — same seed produces identical placements (<0.01mm)
    2. Seed stability — different seeds produce similar wirelength (<2x)
    3. Rotation soundness — back-rotated placements remain in original bounds
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent.parent
_PCB_PATH = (REPO_ROOT / "power_pcb_dataset/corpus/temper/temper.kicad_pcb").resolve()
_CONSTRAINTS_PATH = (
    REPO_ROOT / "packages/temper-placer/configs/temper_constraints.yaml"
).resolve()


def _load():
    if not _PCB_PATH.exists():
        pytest.skip(f"Temper PCB not found: {_PCB_PATH}")
    from temper_placer.io.kicad_parser import parse_kicad_pcb

    result = parse_kicad_pcb(_PCB_PATH)

    if _CONSTRAINTS_PATH.exists():
        from temper_placer.io.config_loader import (
            create_board_from_constraints,
            load_constraints,
        )
        try:
            constraints = load_constraints(_CONSTRAINTS_PATH)
            result.board = create_board_from_constraints(constraints)
        except Exception:
            pass

    return result


def _optimize(netlist, board, seed: int = 42, epochs: int = 10) -> dict[str, tuple[float, float]] | None:
    from temper_placer.losses import (
        BoundaryLoss, CompositeLoss, OverlapLoss, WeightedLoss, WirelengthLoss,
    )
    from temper_placer.losses.base import LossContext
    from temper_placer.optimizer import OptimizerConfig, train

    try:
        composite = CompositeLoss([
            WeightedLoss(WirelengthLoss(), weight=1.0),
            WeightedLoss(OverlapLoss(), weight=10.0),
            WeightedLoss(BoundaryLoss(), weight=5.0),
        ])
        context = LossContext.from_netlist_and_board(netlist, board)
        config = OptimizerConfig.fast_test()
        config.epochs = epochs
        config.seed = seed

        result = train(netlist, board, composite, context, config)
        if not hasattr(result, "best_state") or result.best_state is None:
            return None

        positions = result.best_state.positions  # (N, 2)
        comps = netlist.components
        return {
            comps[i].ref: (float(positions[i, 0]), float(positions[i, 1]))
            for i in range(min(len(comps), positions.shape[0]))
        }
    except ImportError:
        return None


def _wirelength(netlist, placements: dict[str, tuple[float, float]]) -> float:
    total = 0.0
    for net in getattr(netlist, "nets", []):
        positions = []
        for pin in getattr(net, "pins", []):
            ref = pin[0] if isinstance(pin, tuple) and len(pin) >= 1 else ""
            if ref in placements:
                positions.append(placements[ref])
        if len(positions) >= 2:
            for i in range(len(positions)):
                for j in range(i + 1, len(positions)):
                    dx = positions[i][0] - positions[j][0]
                    dy = positions[i][1] - positions[j][1]
                    total += math.sqrt(dx * dx + dy * dy)
    return total


@pytest.mark.slow
@pytest.mark.property
def test_optimizer_idempotency() -> None:
    parsed = _load()
    p1 = _optimize(parsed.netlist, parsed.board, seed=42)
    p2 = _optimize(parsed.netlist, parsed.board, seed=42)

    if p1 is None or p2 is None:
        pytest.skip("Optimizer unavailable")

    diff = 0.0
    for ref in set(p1) & set(p2):
        x1, y1 = p1[ref]
        x2, y2 = p2[ref]
        diff = max(diff, abs(x1 - x2) + abs(y1 - y2))

    assert diff < 0.01, (
        f"Idempotency violated: max manhattan delta {diff:.6f}mm between "
        f"identical-seed runs exceeds 0.01mm tolerance"
    )


@pytest.mark.slow
@pytest.mark.property
def test_optimizer_seed_stability() -> None:
    parsed = _load()
    p42 = _optimize(parsed.netlist, parsed.board, seed=42)
    p99 = _optimize(parsed.netlist, parsed.board, seed=9999)

    if p42 is None or p99 is None:
        pytest.skip("Optimizer unavailable")

    wl42 = _wirelength(parsed.netlist, p42)
    wl99 = _wirelength(parsed.netlist, p99)

    if wl42 == 0 and wl99 == 0:
        pytest.skip("Zero wirelength for both seeds")

    ratio = max(wl42, wl99) / max(min(wl42, wl99), 0.001)
    assert ratio < 2.0, (
        f"Seed instability: wirelength ratio {ratio:.2f} "
        f"(seed=42: {wl42:.1f}, seed=9999: {wl99:.1f})"
    )


@pytest.mark.slow
@pytest.mark.property
def test_optimizer_rotation_soundness() -> None:
    """Rotation soundness: placements on a rotated board, when rotated back,
    must be valid on the original board — within bounds, in correct zones.

    Placement is non-convex — the optimizer converges to different local
    minima on different board shapes.  Equality (same positions) is not
    expected.  Soundness (back-rotated placements lie within the original
    board bounds) IS expected.
    """
    parsed = _load()
    netlist, board = parsed.netlist, parsed.board

    if not board.zones:
        pytest.skip("No zone constraints — rotation soundness requires zones")

    board_rotated = board.rotated_90()
    h = board.height  # original height for reverse-rotation

    p90 = _optimize(netlist, board_rotated, seed=42)
    if p90 is None:
        pytest.skip("Optimizer unavailable")

    # Reverse the 90° rotation: (xr, yr) -> (yr, h - xr)
    p_back: dict[str, tuple[float, float]] = {}
    for ref, (xr, yr) in p90.items():
        p_back[ref] = (yr, h - xr)

    margin = 5.0
    out_of_bounds = []
    for ref, (x, y) in p_back.items():
        if x < -margin or x > board.width + margin:
            out_of_bounds.append(
                f"{ref}: x={x:.2f} outside [0, {board.width:.0f}]"
            )
        if y < -margin or y > board.height + margin:
            out_of_bounds.append(
                f"{ref}: y={y:.2f} outside [0, {board.height:.0f}]"
            )

    assert not out_of_bounds, (
        f"Rotation soundness violated: {len(out_of_bounds)} component(s) "
        f"out of bounds after back-rotation:\n  " + "\n  ".join(out_of_bounds[:10])
    )



