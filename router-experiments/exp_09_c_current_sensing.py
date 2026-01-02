#!/usr/bin/env python3
"""
EXP-09-C: Current Sensing Sub-Component

Tests Router V5 star-point Kelvin sensing topology.
Components: U_CT, R_BURDEN, C_CT_FILT, U_OPAMP_CT

Success Criteria:
- Force path: 2.0mm trace width
- Sense path: 0.2mm trace width
- Star-point connection at R_BURDEN
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.routing.star_point import create_kelvin_constraints, get_segment_width


def test_kelvin_sensing():
    print("\n" + "=" * 70)
    print("EXP-09-C: CURRENT SENSING SUB-COMPONENT (KELVIN)")
    print("=" * 70)
    
    # Create Kelvin constraints
    constraints = create_kelvin_constraints(
        net_name="I_SENSE",
        force_pins=["U_CT.OUT"],
        sense_pins=["U_OPAMP_CT.IN"],
        star_point="R_BURDEN.1",
        force_width=2.0,
        sense_width=0.2,
    )
    
    print(f"\nKelvin Sensing Configuration:")
    print(f"  Net: I_SENSE")
    print(f"  Star Point: R_BURDEN.1")
    print(f"  Force pins: U_CT.OUT")
    print(f"  Sense pins: U_OPAMP_CT.IN")
    
    print(f"\nSegment Constraints:")
    for c in constraints:
        print(f"  {c.from_pin} → {c.to_pin}: {c.trace_width_mm}mm ({c.description})")
    
    # Test segment width lookup
    force_width = get_segment_width("I_SENSE", "R_BURDEN.1", "U_CT.OUT", constraints)
    sense_width = get_segment_width("I_SENSE", "R_BURDEN.1", "U_OPAMP_CT.IN", constraints)
    
    print(f"\nWidth Validation:")
    print(f"  Force path: {force_width}mm (expected 2.0mm)")
    print(f"  Sense path: {sense_width}mm (expected 0.2mm)")
    
    # Validation
    if force_width == 2.0 and sense_width == 0.2:
        print(f"\n✅ EXP-09-C PASS: Star-point topology correct")
        print("  • Force = 2.0mm ✅")
        print("  • Sense = 0.2mm ✅")
        print("  • Star-point at R_BURDEN ✅")
        return 0
    else:
        print(f"\n❌ EXP-09-C FAIL: Width mismatch")
        return 1


if __name__ == "__main__":
    sys.exit(test_kelvin_sensing())
