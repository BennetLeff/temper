"""Rev F phase 1: pose of the rigid TPS65131 island (U13, L1, L2, D2, D3 and their parts).

python3 validation/rev-f-floorplan/switcher_pose_search.py     (about 10 s)

For each quarter turn and each U13 position on a 0.5 mm grid over the switcher block, place the
Rev E island rigidly; keep poses whose every courtyard lies inside the block and the outline and
clears every other placed part; score by the smallest centre distance from L1/L2/D2/D3/U13 to
U5/U6/U7/U14 (the regulator_check.py metric). Writes switcher_pose_search.json; floorplan.py's
RIGID['switcher'] takes the best pose.
"""
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import floorplan as F  # noqa: E402

g = F.RIGID['switcher']
refs = g['refs']
others = {r: F.courtyard(r, F.ANCHORS[r]) for r in F.ANCHORS if r not in refs}
rects = F.BLOCKS['switcher']['rects']
px, py = F.PARTS[g['pivot']]['at']
analog = [F.ANCHORS[u][:2] for u in ('U5', 'U6', 'U7', 'U14')]
x0, y0, x1, y1 = F.OUTLINE
poses = []
for turn in (0, 90, 180, -90):
    for i in range(65):
        for j in range(65):
            x, y = 118 + 0.5 * i, 113 + 0.5 * j
            pos, ok = {}, True
            for r in refs:
                e = F.PARTS[r]
                dx, dy = F.rot(e['at'][0] - px, e['at'][1] - py, turn)
                at = (x + dx, y + dy, (e['rot'] + turn + 180) % 360 - 180)
                c = F.courtyard(r, at)
                if (c[0] < x0 or c[2] > x1 or c[1] < y0 or c[3] > y1 or not F.inside(c, rects)
                        or any(F.overlap(c, o) > 1e-6 for o in others.values())):
                    ok = False
                    break
                pos[r] = at[:2]
            if ok:
                d = min(math.dist(pos[s], a) for s in ('L1', 'L2', 'D2', 'D3', 'U13') for a in analog)
                poses.append({'min_distance_mm': round(d, 2), 'turn': turn, 'u13': [x, y]})
poses.sort(key=lambda p: -p['min_distance_mm'])
best_per_turn = {t: next((p for p in poses if p['turn'] == t), None) for t in (0, 90, 180, -90)}
out = {'feasible_poses': len(poses), 'best': poses[0], 'best_per_turn': best_per_turn,
       'chosen': {'turn': g['turn'], 'u13': list(g['to'])}}
(HERE / 'switcher_pose_search.json').write_text(json.dumps(out, indent=1) + '\n')
print(json.dumps(out, indent=1))
