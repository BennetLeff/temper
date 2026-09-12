"""Use the existing strict native transport with voltage-unit identity."""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "zapote/current-sense/tools"))
from build_current_sense_native import build

if __name__ == "__main__":
    unit = REPO / "zapote/voltage-sense"
    build(
        REPO,
        unit / "source-build-04",
        Path(sys.argv[1]).resolve(),
        unit / "poses.json",
        unit / "outline.json",
        ("VoltageSenseUnit",),
        entry_module="VoltageSenseUnit",
        entry_file="elec/src/voltage_sense_unit.ato",
        title="Half-Bus Voltage Sensing / OVP",
    )
