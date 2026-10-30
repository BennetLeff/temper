"""Fast pre-DRC for hand routing (no KiCad): the LCR meter's configuration of temper_boardkit.predrc.

python3 cad/tools/predrc.py [--design D.json] [--routing R.json] [--json OUT] [--render x0,y0,x1,y1 --out PNG]
                            [--kicad DRC.json]

The checks (clearance, edge, holes, keepouts, via-on-land, width, courtyard, angle, craft, unconnected,
dangling) are packages/temper-boardkit/src/temper_boardkit/predrc.py; this file holds what is the LCR's:
  * the footprint geometry dumped once by cad/tools/pad_library.py (cad/tools/pad_library.json);
  * the five exposed-pad thermal sets that may carry vias (the audit_dfm.py set);
  * In1.Cu is the GND plane: GND vias and GND through-hole pads inside its zone join it;
  * the J connectors (BNCs, USB-C) overhang the board edge by design (KiCad: Rev E passes);
  * Rev E's outline and mounting holes when design.json has no board block;
  * the static part cached in build/predrc-cache.pkl.
Tracks and vias may carry a 'src' key (the rev_f_routes.py line that made them); violations quote it.
It is a fast screen, not a sign-off: the KiCad rebuild and DRC run at block and commit boundaries.
Calibration (--kicad DRC.json prints both tallies): Rev E 48b012771 gives 0/0 in both; the first Rev F
placement gives the same clearance 9, courtyard 12, edge 3, PTH-in-courtyard 2 and unconnected 209
in both, KiCad's one extra dangling via being a GND via on an In1 fill island.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import boardkit_path  # noqa: F401
from shapely.geometry import Point, Polygon  # noqa: F401  (rev_f.py uses predrc.Point / predrc.Polygon)
from temper_boardkit import predrc as _p
from temper_boardkit.model import fp_name  # noqa: F401
from temper_boardkit.predrc import place_geom, summary  # noqa: F401

CAD = Path(__file__).resolve().parents[1]
LIB = json.loads((CAD / 'tools' / 'pad_library.json').read_text())
EXPOSED = {('U1', '57'), ('U11', '9'), ('U12', '9'), ('U13', '25'), ('U14', '25')}
DEFAULT_OUTLINE = [50, 45, 190, 150]
DEFAULT_HOLES = [[54, 54], [186, 54], [54, 146], [186, 146]]
RULES = dict(_p.RULES)
DRC = _p.PreDRC(LIB, exposed=EXPOSED, default_outline=DEFAULT_OUTLINE, default_holes=DEFAULT_HOLES,
                plane=('GND', 'In1.Cu'), edge_exempt=('J',), rules=RULES,
                cache_path=CAD.parent / 'build' / 'predrc-cache.pkl')

static_items = DRC.static_items
dyn_items = DRC.dyn_items
craft_inputs = DRC.craft_inputs
check = DRC.check
render = DRC.render


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--design', default=str(CAD / 'design.json'))
    ap.add_argument('--routing', default=str(CAD / 'routing.json'))
    ap.add_argument('--json', help='write the full result here')
    ap.add_argument('--render', help='x0,y0,x1,y1 window to render')
    ap.add_argument('--out', default='predrc.png')
    ap.add_argument('--kicad', help='a kicad-cli DRC json of the same board: print both tallies side by side')
    a = ap.parse_args()
    design = json.loads(Path(a.design).read_text())
    routing = json.loads(Path(a.routing).read_text())
    res = check(design, routing)
    print(summary(res))
    if a.kicad:
        print(_p.compare(res, json.loads(Path(a.kicad).read_text())))
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1) + '\n')
    if a.render:
        render(design, routing, res, [float(v) for v in a.render.split(',')], a.out)
    return 0 if not res['violations'] and not res['unconnected'] else 1


if __name__ == '__main__':
    sys.exit(main())
