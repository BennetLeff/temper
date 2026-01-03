#!/usr/bin/env python3
"""
Run EXP-01: Pitchfork Fanout Unit Test

This script tests the router's fanout capabilities on a synthetic PCB
with 1.27mm pitch headers (fine grid test).

Usage:
    python3 experiments/temper-3w66/run_experiment.py
"""

import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
import math


try:
    from kiutils.board import Board
    from kiutils.items.common import Position
    from kiutils.items.brditems import Via, Segment
except ImportError:
    print("ERROR: kiutils not installed. Run: pip install kiutils")
    sys.exit(1)


@dataclass
class FanoutConfig:
    """Configuration for Fanout Generation."""

    pitch: float = 2.54
    via_drill: float = 0.3
    via_size: float = 0.6
    trace_width: float = 0.2
    strategy: str = "staggered"
    via_clearance: float = 0.2


class SimpleFanoutGenerator:
    """Simplified fanout generator for testing without full dependencies."""

    def __init__(self, board: Board, config: FanoutConfig = None):
        self.board = board
        self.config = config or FanoutConfig()
        self.vias_created = []
        self.traces_created = []

    def _get_pad_world_position(self, footprint, pad) -> Tuple[float, float]:
        """Get pad position in world coordinates."""
        fp_pos = footprint.position
        if hasattr(fp_pos, "X"):
            fp_x, fp_y = fp_pos.X, fp_pos.Y
        else:
            fp_x, fp_y = fp_pos[0], fp_pos[1]

        if pad.position:
            pad_x, pad_y = pad.position.X, pad.position.Y
        else:
            return (fp_x, fp_y)

        rotation = getattr(footprint, "rotation", 0) or 0

        if rotation == 0:
            return (fp_x + pad_x, fp_y + pad_y)
        elif rotation == 90:
            return (fp_x - pad_y, fp_y + pad_x)
        elif rotation == 180:
            return (fp_x - pad_x, fp_y - pad_y)
        elif rotation == 270:
            return (fp_x + pad_y, fp_y - pad_x)
        else:
            rad = math.radians(rotation)
            cos_r, sin_r = math.cos(rad), math.sin(rad)
            rx = pad_x * cos_r - pad_y * sin_r
            ry = pad_x * sin_r + pad_y * cos_r
            return (fp_x + rx, fp_y + ry)

    def generate_fanouts(self) -> Dict[str, int]:
        """Generate fanouts for all pads in the board."""
        results = {}

        for fp_idx, footprint in enumerate(self.board.footprints):
            ref = footprint.properties.get("Reference", f"U{fp_idx}")
            pads = footprint.pads

            for pad_idx, pad in enumerate(pads):
                net_name = pad.net.name if pad.net else ""

                if not net_name:
                    continue

                world_pos = self._get_pad_world_position(footprint, pad)
                px, py = world_pos

                pitch = self.config.pitch

                directions = [
                    (0.5 * pitch, 0.5 * pitch),
                    (0.5 * pitch, -0.5 * pitch),
                    (-0.5 * pitch, 0.5 * pitch),
                    (-0.5 * pitch, -0.5 * pitch),
                ]

                best_dx, best_dy = directions[pad_idx % 4]

                fx = px + best_dx
                fy = py + best_dy

                via = Via(
                    position=Position(X=fx, Y=fy),
                    size=self.config.via_size,
                    drill=self.config.via_drill,
                    layers=["F.Cu", "B.Cu"],
                    net=pad.net,
                )

                self.board.traceItems.append(via)
                self.vias_created.append((fx, fy))

                trace = Segment(
                    start=Position(X=px, Y=py),
                    end=Position(X=fx, Y=fy),
                    width=self.config.trace_width,
                    layer="F.Cu",
                    net=pad.net,
                    tstamp=f"00000000-0000-0000-0000-{len(self.traces_created):012d}",
                )

                self.board.traceItems.append(trace)
                self.traces_created.append((px, py, fx, fy))

                if net_name not in results:
                    results[net_name] = 0
                results[net_name] += 1

        return results


def count_pads_and_nets(pcb_path: Path) -> dict:
    """Count pads and nets in the pitchfork board."""
    print(f"Loading board: {pcb_path}")

    board = Board.from_file(str(pcb_path))

    total_pads = 0
    nets_found = set()

    for footprint in board.footprints:
        for pad in footprint.pads:
            total_pads += 1
            if pad.net and pad.net.name:
                nets_found.add(pad.net.name)

    return {
        "board": board,
        "footprints": len(board.footprints),
        "total_pads": total_pads,
        "nets": len(nets_found),
    }


def verify_fine_grid(board: Board) -> dict:
    """Verify the board has 1.27mm pitch headers."""
    measurements = []

    for fp in board.footprints:
        pads = fp.pads
        if len(pads) >= 2:
            for i in range(len(pads) - 1):
                p1, p2 = pads[i], pads[i + 1]
                world1 = None
                world2 = None

                if hasattr(fp, "position"):
                    fp_x = fp.position.X if hasattr(fp.position, "X") else fp.position[0]
                    fp_y = fp.position.Y if hasattr(fp.position, "Y") else fp.position[1]
                    if p1.position:
                        world1 = (fp_x + p1.position.X, fp_y + p1.position.Y)
                        world2 = (fp_x + p2.position.X, fp_y + p2.position.Y)

                if world1 and world2:
                    dx = abs(world2[0] - world1[0])
                    dy = abs(world2[1] - world1[1])
                    dist = (dx**2 + dy**2) ** 0.5
                    measurements.append(dist)

    unique_measurements = sorted(set(round(m, 3) for m in measurements))
    has_127mm = any(abs(m - 1.27) < 0.01 for m in measurements)

    return {
        "has_127mm_pitch": has_127mm,
        "unique_distances": unique_measurements,
    }


def check_via_clearance(generator: SimpleFanoutGenerator) -> dict:
    """Check for via-to-via clearance violations."""
    vias = generator.vias_created
    violations = []
    min_dist = generator.config.via_size + generator.config.via_clearance

    for i in range(len(vias)):
        for j in range(i + 1, len(vias)):
            dx = vias[i][0] - vias[j][0]
            dy = vias[i][1] - vias[j][1]
            dist = (dx**2 + dy**2) ** 0.5

            if dist < min_dist and dist > 0:
                violations.append((i, j, dist))

    return {
        "violations": len(violations),
        "min_actual_dist": min(
            (vias[i][0] - vias[j][0]) ** 2 + (vias[i][1] - vias[j][1]) ** 2
            for i in range(len(vias))
            for j in range(i + 1, len(vias))
        )
        if len(vias) > 1
        else 0,
    }


def main():
    """Main entry point."""
    script_dir = Path(__file__).parent
    pcb_path = (
        script_dir
        / ".."
        / ".."
        / "packages"
        / "temper-placer"
        / "tests"
        / "fixtures"
        / "pitchfork.kicad_pcb"
    )

    if not pcb_path.exists():
        print(f"ERROR: Board file not found: {pcb_path}")
        print("Run: python3 packages/temper-placer/tests/fixtures/generators/generate_pitchfork.py")
        sys.exit(1)

    info = count_pads_and_nets(pcb_path)
    board = info["board"]
    grid = verify_fine_grid(board)

    config = FanoutConfig(
        pitch=1.27,
        via_drill=0.3,
        via_size=0.6,
        trace_width=0.2,
        strategy="staggered",
        via_clearance=0.2,
    )

    print(f"\nRunning fanout generation with 1.27mm pitch...")
    generator = SimpleFanoutGenerator(board, config)
    fanout_results = generator.generate_fanouts()

    total_fanouts = sum(fanout_results.values())
    unique_nets = len(fanout_results)
    via_clearance = check_via_clearance(generator)

    print(f"\n{'=' * 60}")
    print("EXP-01: Pitchfork Fanout Unit Test Results")
    print(f"{'=' * 60}")

    print(f"\nBoard Statistics:")
    print(f"  Footprints: {info['footprints']}")
    print(f"  Total pads: {info['total_pads']}")
    print(f"  Named nets: {info['nets']}")

    print(f"\nFanout Results:")
    print(f"  Total fanouts generated: {total_fanouts}")
    print(f"  Unique nets with fanouts: {unique_nets}")
    print(f"  Vias created: {len(generator.vias_created)}")
    print(f"  Traces created: {len(generator.traces_created)}")

    print(f"\nVia Clearance Check:")
    print(f"  Min clearance: {config.via_clearance}mm")
    print(f"  Via size: {config.via_size}mm")
    print(f"  Violations: {via_clearance['violations']}")

    output_pcb = script_dir / "pitchfork_with_fanout.kicad_pcb"
    board.to_file(str(output_pcb))
    print(f"\nSaved board with fanouts to: {output_pcb}")

    if total_fanouts >= info["total_pads"] and via_clearance["violations"] == 0:
        print(f"\n[PASS] Fanout test successful!")
        print(f"       All {info['total_pads']} pins have valid fanout routes")
        print(f"       No via-to-via clearance violations")
        sys.exit(0)
    else:
        print(f"\n[FAIL] Fanout incomplete or has violations")
        sys.exit(1)


if __name__ == "__main__":
    main()
