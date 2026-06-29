"""
Placement Validation Tests

Automated tests to verify placement output meets requirements:
1. Fixed components at specified positions
2. No overlaps between components
3. Zone compliance (components in correct zones)
4. Power stage topology (correct relative positions)
"""

from pathlib import Path

import numpy as np
import pytest

from temper_placer.io.config_loader import load_constraints
from temper_placer.io.kicad_parser import parse_kicad_pcb


def compute_overlaps(positions: dict, netlist) -> list[tuple[str, str, float]]:
    """Compute pairwise overlaps between components."""
    overlaps = []
    refs = list(positions.keys())

    for i, ref1 in enumerate(refs):
        for ref2 in refs[i+1:]:
            pos1 = positions[ref1]
            pos2 = positions[ref2]

            try:
                comp1 = netlist.get_component(ref1)
                comp2 = netlist.get_component(ref2)
            except (KeyError, ValueError, IndexError):
                continue

            # Check AABB overlap
            half_w1, half_h1 = comp1.width / 2, comp1.height / 2
            half_w2, half_h2 = comp2.width / 2, comp2.height / 2

            dx = abs(pos1[0] - pos2[0])
            dy = abs(pos1[1] - pos2[1])

            min_dx = half_w1 + half_w2
            min_dy = half_h1 + half_h2

            if dx < min_dx and dy < min_dy:
                overlap_area = (min_dx - dx) * (min_dy - dy)
                overlaps.append((ref1, ref2, overlap_area))

    return overlaps


class TestPlacementValidation:
    """Tests for validating placement output."""

    @pytest.fixture
    def load_placement(self):
        """Load the output PCB and constraints."""
        pcb_path = Path(__file__).parent.parent / "output_temper_with_priority.kicad_pcb"
        config_path = Path(__file__).parent.parent / "configs" / "temper_constraints.yaml"

        if not pcb_path.exists():
            pytest.skip(f"Output PCB not found: {pcb_path}")

        result = parse_kicad_pcb(pcb_path)
        constraints = load_constraints(config_path)

        # Extract positions from parsed netlist
        positions = {}
        for comp in result.netlist.components:
            if comp.initial_position:
                positions[comp.ref] = comp.initial_position

        return result.netlist, constraints, positions

    def test_fixed_components_at_positions(self, load_placement):
        """Verify fixed components are at their specified positions."""
        netlist, constraints, positions = load_placement

        for ref, expected_pos in constraints.fixed_positions.items():
            if ref not in positions:
                continue  # Component might not exist in netlist

            actual_pos = positions[ref]
            distance = np.sqrt(
                (actual_pos[0] - expected_pos[0])**2 +
                (actual_pos[1] - expected_pos[1])**2
            )

            assert distance < 6.0, \
                f"{ref} at {actual_pos}, expected {expected_pos} (off by {distance:.2f}mm)"

    def test_no_overlaps(self, load_placement):
        """Verify no components overlap."""
        netlist, constraints, positions = load_placement

        overlaps = compute_overlaps(positions, netlist)

        if overlaps:
            overlap_strs = [f"{a}-{b}: {area:.2f}mm²" for a, b, area in overlaps[:10]]
            pytest.fail(f"Found {len(overlaps)} overlaps: {', '.join(overlap_strs)}")

    def test_power_stage_topology(self, load_placement):
        """Verify power stage components have correct relative positions."""
        netlist, constraints, positions = load_placement

        power_stage = ["Q1", "Q2", "D1", "D2", "C_BUS1", "C_BUS2"]

        # Skip if power stage components not in output
        if not all(ref in positions for ref in power_stage):
            pytest.skip("Not all power stage components in output")

        # Check Q1 is above Q2 (higher Y)
        assert positions["Q1"][1] > positions["Q2"][1], \
            f"Q1 ({positions['Q1'][1]:.1f}) should be above Q2 ({positions['Q2'][1]:.1f})"

        # Check D1 is left of Q1
        assert positions["D1"][0] < positions["Q1"][0], \
            f"D1 ({positions['D1'][0]:.1f}) should be left of Q1 ({positions['Q1'][0]:.1f})"

        # Check C_BUS1 is right of Q1
        assert positions["C_BUS1"][0] > positions["Q1"][0], \
            f"C_BUS1 ({positions['C_BUS1'][0]:.1f}) should be right of Q1 ({positions['Q1'][0]:.1f})"

        # Check Q1-Q2 vertical spacing (should be ~10mm)
        q1q2_dist = abs(positions["Q1"][1] - positions["Q2"][1])
        assert 5.0 < q1q2_dist < 20.0, \
            f"Q1-Q2 spacing {q1q2_dist:.1f}mm should be 5-20mm"

    def test_zone_compliance(self, load_placement):
        """Verify components are in their assigned zones."""
        netlist, constraints, positions = load_placement

        violations = []

        for ref, zone_name in constraints.zone_assignments.items():
            if ref not in positions:
                continue

            pos = positions[ref]

            # Find zone
            zone = None
            for z in constraints.zones:
                if z.name == zone_name:
                    zone = z
                    break

            if zone is None:
                continue

            # Check if position is in zone bounds
            x, y = pos
            x_min, y_min, x_max, y_max = zone.bounds

            if not (x_min <= x <= x_max and y_min <= y <= y_max):
                violations.append(f"{ref} at ({x:.1f}, {y:.1f}) outside zone '{zone_name}' [{x_min}-{x_max}, {y_min}-{y_max}]")

        if violations:
            pytest.fail(f"Zone violations: {'; '.join(violations[:5])}")

    def test_hv_clearance(self, load_placement):
        """Verify HV components have minimum clearance from LV."""
        netlist, constraints, positions = load_placement

        hv_components = {"Q1", "Q2", "D1", "D2", "C_BUS1", "C_BUS2", "J_AC_IN"}
        lv_components = {"U_MCU", "U_LDO_3V3", "U_LDO_5V", "J_USB", "J_DEBUG"}

        hv_clearance = constraints.hv_clearance_mm
        violations = []

        for hv_ref in hv_components:
            if hv_ref not in positions:
                continue
            hv_pos = positions[hv_ref]

            for lv_ref in lv_components:
                if lv_ref not in positions:
                    continue
                lv_pos = positions[lv_ref]

                distance = np.sqrt(
                    (hv_pos[0] - lv_pos[0])**2 +
                    (hv_pos[1] - lv_pos[1])**2
                )

                if distance < hv_clearance:
                    violations.append(f"{hv_ref}-{lv_ref}: {distance:.1f}mm < {hv_clearance}mm")

        if violations:
            pytest.fail(f"HV clearance violations: {'; '.join(violations[:5])}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
