"""Thin transport to the existing source-bound native builder."""
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[4]
ROOT = REPO / "zapote/power-entry/active-rectifier"
sys.path.insert(0,str(REPO / "zapote/current-sense/tools"))
from build_current_sense_native import build
if __name__ == "__main__":
    build(REPO,Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve(),
          ROOT/"poses.json",ROOT/"outline.json",("power_entry_active",),
          entry_module="PowerEntryActiveUnit",entry_file="elec/src/power_entry_active_unit.ato",
          title="Experimental active rectifier and fused DC bank",local_libraries=ROOT/"libraries")
