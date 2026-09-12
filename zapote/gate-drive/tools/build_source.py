import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "zapote/current-sense/tools"))
from build_current_sense_source import build  # noqa: E402

if __name__ == "__main__":
    build(REPO, Path(sys.argv[1]).resolve(), "elec/src/gate_drive_unit.ato", "GateDriveUnit")
