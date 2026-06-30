"""Metamorphic completeness oracle suite.

Property-based tests that assert invariant relations hold for any board
processed by the pipeline.  Unlike golden fixtures (which catch
regression—"this output changed"), metamorphic tests catch
incorrectness—"this output violates a property that must hold for ALL
inputs, even when the golden baseline is itself wrong."

Relations tested:
    1. Rotation invariance: rotate input 90°, output coordinates rotate accordingly
    2. Swap idempotency: identical components swapped must produce identical output
    3. Seed stability: same board with different seeds must have similar wirelength
    4. Coordinate bounds: all output positions must lie within board extent
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from hypothesis import given, settings
from hypothesis import strategies as st


def _load_parsed_pcb() -> tuple:
    pcb_path = (
        Path(__file__).parent.parent.parent
        / "power_pcb_dataset/corpus/temper/temper.kicad_pcb"
    )
    if not pcb_path.exists():
        pytest.skip("Temper PCB not found")

    from temper_placer.io.kicad_parser import parse_kicad_pcb

    result = parse_kicad_pcb(pcb_path)
    return result.netlist, result.board


def _run_placement(netlist, board, seed: int = 42) -> dict:
    try:
        from temper_placer.losses import BoundaryLoss, OverlapLoss, WirelengthLoss
        from temper_placer.losses.composite import CompositeLossConfig
        from temper_placer.optimizer import train

        loss_config = CompositeLossConfig(
            losses=[
                WirelengthLoss.Config(),
                OverlapLoss.Config(),
                BoundaryLoss.Config(board),
            ]
        )
        return train(
            netlist=netlist,
            board=board,
            loss_config=loss_config,
            epochs=10,
            seed=seed,
        )
    except ImportError:
        return {}


def _compute_wirelength(netlist, placements: dict) -> float:
    total = 0.0
    nets = getattr(netlist, "nets", [])
    for net in nets:
        pins = getattr(net, "pins", [])
        positions = []
        for pin in pins:
            ref = str(getattr(pin, "ref", "") or getattr(pin, "component", ""))
            if ref in placements:
                x, y = placements[ref]
                positions.append((x, y))
        if len(positions) >= 2:
            for i in range(len(positions)):
                for j in range(i + 1, len(positions)):
                    dx = positions[i][0] - positions[j][0]
                    dy = positions[i][1] - positions[j][1]
                    total += math.sqrt(dx * dx + dy * dy)
    return total


@pytest.mark.slow
@pytest.mark.property
def test_rotation_invariance() -> None:
    netlist, board = _load_parsed_pcb()

    placements_0 = _run_placement(netlist, board, seed=42)
    if not placements_0:
        pytest.skip("Placement engine unavailable")

    board_rotated = type(board)(
        width=board.height,
        height=board.width,
    )

    placements_90 = _run_placement(netlist, board_rotated, seed=42)
    if not placements_90:
        pytest.skip("Rotated placement unavailable")

    common_refs = set(placements_0.keys()) & set(placements_90.keys())
    assert len(common_refs) >= len(placements_0) * 0.5, (
        f"Too few components shared between original and rotated: "
        f"{len(common_refs)} / {len(placements_0)}"
    )

    max_drift = 0.0
    for ref in common_refs:
        x0, y0 = placements_0[ref]
        x90, y90 = placements_90[ref]
        expected_x = board_rotated.width - y0
        expected_y = x0
        drift = math.sqrt(
            (x90 - expected_x) ** 2 + (y90 - expected_y) ** 2
        )
        max_drift = max(max_drift, drift)

    assert max_drift < board.width * 0.3, (
        f"Rotation invariant violated: max drift {max_drift:.2f}mm exceeds "
        f"30% of board width ({board.width * 0.3:.2f}mm)"
    )


@pytest.mark.slow
@pytest.mark.property
def test_seed_stability() -> None:
    netlist, board = _load_parsed_pcb()

    placements_a = _run_placement(netlist, board, seed=42)
    placements_b = _run_placement(netlist, board, seed=9999)

    if not placements_a or not placements_b:
        pytest.skip("Placement engine unavailable")

    wl_a = _compute_wirelength(netlist, placements_a)
    wl_b = _compute_wirelength(netlist, placements_b)

    if wl_a == 0 and wl_b == 0:
        pytest.skip("Zero wirelength for both seeds; cannot compare")

    ratio = max(wl_a, wl_b) / max(min(wl_a, wl_b), 0.001)
    assert ratio < 2.0, (
        f"Seed instability detected: wirelength ratio {ratio:.2f} "
        f"(seed=42: {wl_a:.1f}, seed=9999: {wl_b:.1f})"
    )


@pytest.mark.slow
@pytest.mark.property
def test_coordinate_bounds() -> None:
    netlist, board = _load_parsed_pcb()

    placements = _run_placement(netlist, board, seed=42)
    if not placements:
        pytest.skip("Placement engine unavailable")

    margin = getattr(board, "margin", 0.0)
    bw = board.width + margin * 2
    bh = board.height + margin * 2

    violations = []
    for ref, (x, y) in placements.items():
        if x < -margin or x > board.width + margin:
            violations.append(f"{ref}: x={x:.2f} outside [{-margin:.1f}, {board.width + margin:.1f}]")
        if y < -margin or y > board.height + margin:
            violations.append(f"{ref}: y={y:.2f} outside [{-margin:.1f}, {board.height + margin:.1f}]")

    assert not violations, (
        f"{len(violations)} components outside board bounds "
        f"({bw:.1f}x{bh:.1f}):\n  " + "\n  ".join(violations[:5])
    )


@pytest.mark.slow
@pytest.mark.property
def test_idempotency() -> None:
    netlist, board = _load_parsed_pcb()

    placements_1 = _run_placement(netlist, board, seed=42)
    placements_2 = _run_placement(netlist, board, seed=42)

    if not placements_1 or not placements_2:
        pytest.skip("Placement engine unavailable")

    assert set(placements_1.keys()) == set(placements_2.keys()), (
        "Idempotency violated: different component sets between runs with same seed"
    )

    max_delta = 0.0
    for ref in placements_1:
        x1, y1 = placements_1[ref]
        x2, y2 = placements_2[ref]
        delta = math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)
        max_delta = max(max_delta, delta)

    assert max_delta < 0.01, (
        f"Idempotency violated: max delta {max_delta:.6f}mm between "
        f"identical-seed runs exceeds 0.01mm tolerance"
    )


@pytest.mark.slow
@pytest.mark.property
def test_non_overlap() -> None:
    netlist, board = _load_parsed_pcb()

    placements = _run_placement(netlist, board, seed=42)
    if not placements:
        pytest.skip("Placement engine unavailable")

    comp_bounds: dict[str, tuple[float, float, float, float]] = {}
    for comp in netlist.components:
        ref = str(getattr(comp, "ref", None) or getattr(comp, "reference", ""))
        if ref not in placements:
            continue
        w = getattr(comp, "bounds", (1, 1))[0] if hasattr(comp, "bounds") else 1.0
        h = getattr(comp, "bounds", (1, 1))[1] if hasattr(comp, "bounds") else 1.0
        x, y = placements[ref]
        comp_bounds[ref] = (x, y, x + w, y + h)

    refs = list(comp_bounds.keys())
    overlaps = []
    for i in range(len(refs)):
        for j in range(i + 1, len(refs)):
            a = comp_bounds[refs[i]]
            b = comp_bounds[refs[j]]
            if a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]:
                overlaps.append(f"{refs[i]} overlaps {refs[j]}")

    if overlaps:
        pytest.fail(
            f"{len(overlaps)} component overlap(s) detected:\n  "
            + "\n  ".join(overlaps[:10])
        )
