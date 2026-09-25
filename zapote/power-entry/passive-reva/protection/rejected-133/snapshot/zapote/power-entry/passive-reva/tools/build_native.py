"""Project the passive source build into a KiCad native candidate."""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
ROOT = REPO / "zapote/power-entry/passive-reva"
sys.path.insert(0, str(REPO / "zapote/current-sense/tools"))
from build_current_sense_native import build  # noqa: E402


if __name__ == "__main__":
    build(
        REPO,
        Path(sys.argv[1]).resolve(),
        Path(sys.argv[2]).resolve(),
        ROOT / "poses.json",
        ROOT / "outline.json",
        ("power_entry_passive_reva", "power_entry_protection"),
        entry_module="PowerEntryPassiveReva",
        entry_file="elec/src/power_entry_passive_reva.ato",
        title="Passive F2 supervisor construction candidate - NOT QUALIFIED",
        local_libraries=ROOT / "libraries",
    )
