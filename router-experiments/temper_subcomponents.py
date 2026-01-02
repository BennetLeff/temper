#!/usr/bin/env python3
"""
Temper Sub-Component Experiments

Creates isolated experiments for each major subsystem of the Temper board.
Tests Router V5/V6 features before full integration.

Sub-Components:
1. Power Stage (Q1, Q2, D1, D2) - HV/340V, creepage test
2. Gate Driver (U_GATE, C_BOOT, R_GATE) - Gate loop inductance
3. MCU (U_MCU, C_MCU_*) - Decoupling, fine-pitch
4. Current Sensing (U_CT, R_BURDEN) - Kelvin star-point
5. DC Bus (C_BUS1, C_BUS2) - High-current via arrays
6. Full Integration - All components
"""

import sys
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))


@dataclass
class SubComponent:
    """Definition of a Temper sub-component for testing."""
    name: str
    components: List[str]
    nets: List[str]
    challenges: List[str]
    router_features_tested: List[str]
    board_size_mm: Tuple[float, float]
    description: str


# Define Temper Sub-Components
SUB_COMPONENTS = {
    "power_stage": SubComponent(
        name="Power Stage",
        components=["Q1", "Q2", "D1", "D2"],
        nets=["+340V_BUS", "DC_BUS_RTN", "SW_NODE"],
        challenges=[
            "HV creepage (340V → 3.0mm)",
            "High-current traces (40A)",
            "Thermal management (50W per IGBT)",
            "Commutation loop inductance",
        ],
        router_features_tested=[
            "Creepage/clearance enforcement",
            "Via arrays (40A → 20+ vias)",
            "Trace width sizing (4mm+)",
        ],
        board_size_mm=(50, 40),
        description="Half-bridge IGBTs with freewheeling diodes. 340V/40A switching.",
    ),
    
    "gate_driver": SubComponent(
        name="Gate Driver",
        components=["U_GATE", "C_BOOT", "R_GATE_H", "R_GATE_L", "C_VCC"],
        nets=["GATE_HS", "GATE_LS", "+15V", "GND"],
        challenges=[
            "Gate loop inductance (<20nH)",
            "High-side bootstrap",
            "dV/dt immunity",
            "Isolated driver routing",
        ],
        router_features_tested=[
            "Critical loop minimization",
            "Differential pair (for isolated signals)",
            "Guard rings",
        ],
        board_size_mm=(35, 30),
        description="UCC21550 isolated gate driver with bootstrap circuit.",
    ),
    
    "mcu_subsystem": SubComponent(
        name="MCU Subsystem",
        components=["U_MCU", "C_MCU_1", "C_MCU_2", "C_MCU_3", "C_MCU_4"],
        nets=["+3V3", "GND", "SPI_CLK", "SPI_MOSI", "SPI_MISO", "GPIO_*"],
        challenges=[
            "Fine-pitch QFN escape",
            "Decoupling placement",
            "Power/ground distribution",
            "SPI high-speed routing",
        ],
        router_features_tested=[
            "BGA/QFN escape routing",
            "Fanout generation",
            "Via stitching for GND",
        ],
        board_size_mm=(30, 30),
        description="ESP32-S3 MCU with decoupling capacitors.",
    ),
    
    "current_sensing": SubComponent(
        name="Current Sensing",
        components=["U_CT", "R_BURDEN", "C_CT_FILT", "U_OPAMP_CT"],
        nets=["I_SENSE_FORCE", "I_SENSE_SENSE", "GND"],
        challenges=[
            "Kelvin sensing topology",
            "Force vs sense trace widths",
            "Star-point connection",
            "Noise immunity",
        ],
        router_features_tested=[
            "Star-point topology",
            "Segment-specific widths",
            "Guard traces",
        ],
        board_size_mm=(25, 25),
        description="Current transformer with burden resistor. Kelvin sensing required.",
    ),
    
    "dc_bus": SubComponent(
        name="DC Bus Capacitors",
        components=["C_BUS1", "C_BUS2"],
        nets=["+340V_BUS", "DC_BUS_RTN"],
        challenges=[
            "Very high current (40A peak)",
            "Low ESL requirement",
            "Plane connections",
            "Via arrays for current distribution",
        ],
        router_features_tested=[
            "Via arrays (40A → 20+ vias)",
            "Plane connection routing",
            "Creepage enforcement",
        ],
        board_size_mm=(30, 20),
        description="Bulk capacitors for voltage doubler. 40A peak current.",
    ),
    
    "connectors": SubComponent(
        name="AC Input + Coil",
        components=["J_AC_IN", "J_COIL", "J_NTC"],
        nets=["AC_L", "AC_N", "COIL_OUT", "NTC_SENSE"],
        challenges=[
            "High-current connectors (10A+)",
            "Creepage from AC input",
            "Mixed signal/power routing",
        ],
        router_features_tested=[
            "Creepage enforcement",
            "Via arrays for current",
            "Edge placement",
        ],
        board_size_mm=(30, 35),
        description="Power connectors: AC input, coil output, NTC temperature.",
    ),
}


def print_experiment_matrix():
    """Print the experiment matrix for Temper sub-components."""
    print("\n" + "=" * 80)
    print("TEMPER SUB-COMPONENT ROUTING EXPERIMENTS")
    print("=" * 80)
    
    print("\n" + "─" * 80)
    print(f"{'Sub-Component':<20} {'Size (mm)':<12} {'Components':<10} {'Router Features'}")
    print("─" * 80)
    
    for key, sc in SUB_COMPONENTS.items():
        size_str = f"{sc.board_size_mm[0]}×{sc.board_size_mm[1]}"
        comp_count = len(sc.components)
        features = ", ".join(sc.router_features_tested[:2])
        print(f"{sc.name:<20} {size_str:<12} {comp_count:<10} {features}")
    
    print("─" * 80)


def print_detailed_experiments():
    """Print detailed experiment specifications."""
    for i, (key, sc) in enumerate(SUB_COMPONENTS.items(), 1):
        print(f"\n{'=' * 80}")
        print(f"EXPERIMENT {i}: {sc.name.upper()}")
        print(f"{'=' * 80}")
        print(f"\nDescription: {sc.description}")
        print(f"Board Size: {sc.board_size_mm[0]}×{sc.board_size_mm[1]} mm")
        
        print(f"\nComponents ({len(sc.components)}):")
        for comp in sc.components:
            print(f"  • {comp}")
        
        print(f"\nNets ({len(sc.nets)}):")
        for net in sc.nets:
            print(f"  • {net}")
        
        print(f"\nRouting Challenges:")
        for challenge in sc.challenges:
            print(f"  ⚠️  {challenge}")
        
        print(f"\nRouter V5/V6 Features Tested:")
        for feature in sc.router_features_tested:
            print(f"  ✅ {feature}")


def generate_experiment_plan():
    """Generate the experiment execution plan."""
    print("\n" + "=" * 80)
    print("EXPERIMENT EXECUTION PLAN")
    print("=" * 80)
    
    plan = [
        ("power_stage", "Test creepage/clearance on 340V HV nets", "Track 2"),
        ("dc_bus", "Test via arrays on 40A DC bus", "Track 1"),
        ("current_sensing", "Test star-point Kelvin sensing", "Track 4"),
        ("gate_driver", "Test gate loop critical paths", "Loop minimization"),
        ("mcu_subsystem", "Test fine-pitch escape routing", "Fanout"),
        ("connectors", "Test mixed HV/LV routing", "Integration"),
    ]
    
    print("\nRecommended Order:")
    print("─" * 80)
    
    for i, (key, objective, feature) in enumerate(plan, 1):
        sc = SUB_COMPONENTS[key]
        print(f"\n{i}. {sc.name}")
        print(f"   Objective: {objective}")
        print(f"   Tests: {feature}")
        print(f"   Components: {', '.join(sc.components)}")
    
    print("\n" + "─" * 80)
    print("After all pass: Run FULL INTEGRATION on complete Temper board")
    print("─" * 80)


def main():
    """Run the sub-component analysis."""
    print_experiment_matrix()
    print_detailed_experiments()
    generate_experiment_plan()
    
    print("\n" + "=" * 80)
    print("NEXT STEPS")
    print("=" * 80)
    print("""
1. Create individual experiment scripts for each sub-component
2. Extract component positions from temper_constraints.yaml
3. Generate minimal netlists for each experiment
4. Run Router V5/V6 on each experiment
5. Validate: creepage, via arrays, star-point, etc.
6. Fix issues in isolation before full integration
7. Run full Temper board routing
""")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
