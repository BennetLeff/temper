import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "zapote/current-sense/tools"))
from build_current_sense_native import build  # noqa: E402

if __name__ == "__main__":
    u = REPO / "zapote/thermal-sense"
    build(
        REPO,
        u / "source-build-02",
        Path(sys.argv[1]).resolve(),
        u / "poses.json",
        u / "outline.json",
        ("ThermalSenseUnit",),
        entry_module="ThermalSenseUnit",
        entry_file="elec/src/thermal_sense_unit.ato",
        title="Heatsink and Coil Thermal Detectors",
    )
