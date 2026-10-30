"""Copper-to-edge distances per board edge, for the edge-rail (V-cut) decision.

Run with KiCad's bundled Python on a filled board (cad/rebuild.sh fills the zones):
    <kicad-python> cad/tools/edge_clearance.py [OUT.json]
Read-only. For each straight edge of the rectangular outline it reports the nearest copper on any layer
(pads, tracks, vias, filled zones), the nearest track or via, the nearest land, and every SMT land of
an assembled part within 2.0 mm of the edge.  Distances are from the copper outline, in mm.
The measurement is temper_boardkit.kicad.edge_clearance.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boardkit_path  # noqa: E402,F401
from temper_boardkit import kicad  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / 'validation' / 'edge-clearance-rev-f.json'
PCB = ROOT / 'temper-lcr.kicad_pcb'
try:
    out = kicad.edge_clearance(PCB, label=str(PCB.relative_to(ROOT.parent)))
except RuntimeError as e:
    sys.exit(f'{e}: run cad/rebuild.sh (or cad/fill_zones.py) first')
OUT.write_text(json.dumps(out, indent=1) + '\n')
print(kicad.edge_summary(out))
print('->', OUT)
