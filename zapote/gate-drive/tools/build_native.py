import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "zapote/current-sense/tools"))
from build_current_sense_native import build  # noqa: E402

if __name__ == "__main__":
    u = REPO / "zapote/gate-drive"
    build(
        REPO,
        u / "source-build-09",
        Path(sys.argv[1]).resolve(),
        u / "poses.json",
        u / "outline.json",
        ("GateDriveUnit",),
        entry_module="GateDriveUnit",
        entry_file="elec/src/gate_drive_unit.ato",
        title="Standalone Isolated Dual Gate Drive",
    )
