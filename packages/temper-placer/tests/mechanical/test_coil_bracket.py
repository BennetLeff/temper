
import math


def test_coil_stackup():
    """Verify coil air gap is within 3mm +/- 0.5mm."""
    # Internal mounting plate to bottom of glass = 12.0mm
    # (Chassis height 50mm, plate at 38mm)
    chassis_to_glass = 12.0
    standoff_height = 4.0 # mm
    bracket_thickness = 0.0 # Coil sits on standoffs? No, on bracket.
    bracket_thickness = 1.0 # 1mm FR4/G10
    coil_height = 4.0 # mm

    # Top of coil = standoff + bracket + coil
    top_of_coil = standoff_height + bracket_thickness + coil_height

    air_gap = chassis_to_glass - top_of_coil

    print(f"Calculated Air Gap: {air_gap} mm")
    assert abs(air_gap - 3.0) <= 0.5 # mm

def test_airflow_area():
    """Verify ventilation slots provide >50% open area."""
    coil_od = 200.0
    coil_id = 40.0
    total_coil_area = math.pi * ((coil_od/2)**2 - (coil_id/2)**2)

    # Minimum required open area
    min_open_area = total_coil_area * 0.5

    # Design slots: 8 slots, each 100mm x 25mm
    slot_area = 8 * (100 * 25)

    assert slot_area >= min_open_area
