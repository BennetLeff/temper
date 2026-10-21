"""Small helpers for scripted hand edits of cad/design.json and cad/routing.json.

Edits are explicit: every segment and via is given by coordinates or REF.pad, so the
result is still hand routing.  Used by the Rev D audit fixes (docs/rev-d-audit.md).
"""
import json
from pathlib import Path

CAD = Path(__file__).resolve().parents[1]


class Board:
    def __init__(self):
        self.design = json.loads((CAD / 'design.json').read_text())
        self.routing = json.loads((CAD / 'routing.json').read_text())

    def part(self, ref):
        return next(p for p in self.design['parts'] if p['ref'] == ref)

    def set_part(self, ref, **kw):
        self.part(ref).update(kw)

    def drop_tracks(self, pred):
        before = len(self.routing['tracks'])
        self.routing['tracks'] = [t for t in self.routing['tracks'] if not pred(t)]
        return before - len(self.routing['tracks'])

    def drop_track_points(self, net, *pts):
        """Remove tracks of `net` whose point list equals one of the given lists."""
        want = [json.dumps(p) for p in pts]
        return self.drop_tracks(lambda t: t['net'] == net and json.dumps(t['points']) in want)

    def drop_via(self, net, at, tol=0.01):
        before = len(self.routing['vias'])
        self.routing['vias'] = [v for v in self.routing['vias']
                                if not (v['net'] == net and abs(v['at'][0] - at[0]) < tol and abs(v['at'][1] - at[1]) < tol)]
        assert before - len(self.routing['vias']) == 1, (net, at)

    def track(self, net, layer, points, width=0.2):
        self.routing['tracks'].append({'net': net, 'layer': layer, 'width': width, 'points': points})

    def via(self, net, at, diameter=0.45, drill=0.2):
        self.routing['vias'].append({'net': net, 'at': at, 'diameter': diameter, 'drill': drill})

    def save(self):
        (CAD / 'design.json').write_text(json.dumps(self.design, indent=2) + '\n')
        (CAD / 'routing.json').write_text(json.dumps(self.routing, indent=2) + '\n')
