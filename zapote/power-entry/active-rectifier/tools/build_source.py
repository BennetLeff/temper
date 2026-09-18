"""Compile the active-rectifier candidate with the existing pinned transport."""
import sys
from pathlib import Path
REPO=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(REPO/"zapote/current-sense/tools"))
from build_current_sense_source import build
if __name__ == "__main__":
    build(REPO,Path(sys.argv[1]).resolve(),"elec/src/power_entry_active_unit.ato","PowerEntryActiveUnit")
