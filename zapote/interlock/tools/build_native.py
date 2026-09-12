import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "zapote/current-sense/tools"))
from build_current_sense_native import build  # noqa: E402

if __name__ == "__main__":
    u = REPO / "zapote/interlock"
    build(
        REPO,
        u / "source-build-02",
        Path(sys.argv[1]).resolve(),
        u / "poses.json",
        u / "outline.json",
        ("InterlockUnit",),
        entry_module="InterlockUnit",
        entry_file="elec/src/interlock_unit.ato",
        title="Standalone Safety Interlock",
    )
