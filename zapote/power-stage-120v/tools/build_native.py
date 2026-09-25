"""Generate native KiCad artifacts from the frozen power-stage source."""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "zapote/current-sense/tools"))
from build_current_sense_native import build  # noqa: E402

if __name__ == "__main__":
    u = REPO / "zapote/power-stage-120v"
    build(
        REPO,
        u / "source-build-01",
        Path(sys.argv[1]).resolve(),
        u / "poses.json",
        u / "outline.json",
        ("PowerStage120V",),
        entry_module="PowerStage120V",
        entry_file="elec/src/power_stage_120v.ato",
        title="120 V Full-Bridge Induction Power Stage",
        local_libraries=u / "libraries",
    )
