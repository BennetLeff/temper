#!/usr/bin/env python3
"""Native KiCad drill/SMT geometry receipt; no substituted clearance engine."""
from pathlib import Path
import hashlib
import json
import pcbnew as k

root = Path(__file__).resolve().parent.parent
path = root / 'cad/temper-lcr.kicad_pcb'
board = k.LoadBoard(str(path))
rows = []
for via in board.GetTracks():
    if not isinstance(via, k.PCB_VIA):
        continue
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if pad.GetAttribute() != k.PAD_ATTRIB_SMD:
                continue
            # Native HitTest expands the pad by the circular drill radius.
            # This is conservative near rounded corners and does not derive rotations.
            if pad.HitTest(via.GetPosition(), via.GetDrillValue() // 2, k.F_Cu):
                rows.append({'reference': footprint.GetReference(), 'pad': pad.GetNumber(),
                             'net': via.GetNetname(),
                             'x_mm': k.ToMM(via.GetPosition().x),
                             'y_mm': k.ToMM(via.GetPosition().y),
                             'drill_mm': k.ToMM(via.GetDrillValue()),
                             'diameter_mm': k.ToMM(via.GetWidth(k.F_Cu)),
                             'process': 'resin filled, copper capped, planarized (POFV)'})
rows.sort(key=lambda row: (row['reference'], row['pad'], row['x_mm'], row['y_mm']))
expected = {('U1','57'), ('R3','2'), ('U10','13'), ('U10','15'),
            ('U8','17'), ('U9','17'), ('U10','33'), ('U11','9'), ('U12','9'), ('U13','25'),
            ('C107','1'), ('C109','1'), ('C62','2'), ('C63','2'), ('C68','2'), ('C69','2'), ('C75','2')}
actual = {(row['reference'], row['pad']) for row in rows}
assert actual == expected, f'Unexpected drill/SMT overlap set: {actual ^ expected}'
result = {'board_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
          'method': 'native pcbnew PAD.HitTest with drill-radius accuracy; all SMT pads/all through vias',
          'required_process': '4-layer filled/capped via-in-pad (POFV); obtain vendor quote and DFM approval',
          'intended_overlaps': rows,
          'unexpected_drill_smt_overlaps': [],
          'vendor_dfm_approval': 'NOT PERFORMED'}
(root / 'validation/via-in-pad-process.json').write_text(json.dumps(result, indent=2)+'\n')
print(f'{len(rows)} intended filled/capped SMT vias; no unexpected drill/SMT overlaps.')
