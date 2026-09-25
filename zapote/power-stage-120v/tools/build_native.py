"""Generate native KiCad artifacts from the frozen power-stage source."""

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "zapote/current-sense/tools"))
from build_current_sense_native import build  # noqa: E402
from planning_stackup import apply_planning_stackup  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--stackup", type=Path, help="Apply the approved nominal stackup")
    args = parser.parse_args()
    u = REPO / "zapote/power-stage-120v"
    build(
        REPO,
        u / "source-build-01",
        args.output.resolve(),
        u / "poses.json",
        u / "outline.json",
        ("PowerStage120V",),
        entry_module="PowerStage120V",
        entry_file="elec/src/power_stage_120v.ato",
        title="120 V Full-Bridge Induction Power Stage",
        local_libraries=u / "libraries",
        sheet_name="PowerStage120V",
        manifest_schema="zapote.power-stage-120v.native-source-manifest.v1",
    )

    if args.stackup is not None:
        apply_planning_stackup(args.output.resolve(), args.stackup.resolve())
