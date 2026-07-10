"""
U10: Thermal helps-battery run — keep/kill verdict orchestrator.

Wires field solver (U5) + independent scorer (U7) + operating-point gate (U6)
into the helps-battery A/B harness (U3) against the pre-registered pass bar
(U1) to produce a keep/kill verdict artifact.
"""

from temper_placer.validation.results.battery_run import (
    BatteryRunArtifact,
    BatteryRunReport,
    run_thermal_helps_battery,
)

__all__ = [
    "BatteryRunArtifact",
    "BatteryRunReport",
    "run_thermal_helps_battery",
]
