#!/usr/bin/env python3
"""Native KiCad drill/SMT geometry receipt; no substituted clearance engine."""
from pathlib import Path
import hashlib
import json
import pcbnew as k

root = Path(__file__).resolve().parent.parent
path = root / 'cad/temper-lcr.kicad_pcb'
board = k.LoadBoard(str(path))
rows, ring_rows = [], []
for via in board.GetTracks():
    if not isinstance(via, k.PCB_VIA):
        continue
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if pad.GetAttribute() != k.PAD_ATTRIB_SMD:
                continue
            # Native HitTest expands the pad by the circular drill radius.
            # This is conservative near rounded corners and does not derive rotations.
            if pad.HitTest(via.GetPosition(), via.GetWidth(k.F_Cu) // 2, k.F_Cu) and \
                    not pad.HitTest(via.GetPosition(), via.GetDrillValue() // 2, k.F_Cu):
                # Drill outside the land but the via ring touches it: an untented ring wicks paste.
                ring_rows.append((footprint.GetReference(), pad.GetNumber(), via.GetNetname(),
                                  k.ToMM(via.GetPosition().x), k.ToMM(via.GetPosition().y)))
            if pad.HitTest(via.GetPosition(), via.GetDrillValue() // 2, k.F_Cu):
                rows.append({'reference': footprint.GetReference(), 'pad': pad.GetNumber(),
                             'net': via.GetNetname(),
                             'x_mm': k.ToMM(via.GetPosition().x),
                             'y_mm': k.ToMM(via.GetPosition().y),
                             'drill_mm': k.ToMM(via.GetDrillValue()),
                             'diameter_mm': k.ToMM(via.GetWidth(k.F_Cu)),
                             'process': 'exposed-pad thermal via, unfilled, tented on B.Mask'})
rows.sort(key=lambda row: (row['reference'], row['pad'], row['x_mm'], row['y_mm']))
expected = {('U1','57'), ('U11','9'), ('U12','9'), ('U13','25'), ('U14','25')}
actual = {(row['reference'], row['pad']) for row in rows}
assert actual == expected, f'Unexpected drill/SMT overlap set: {actual ^ expected}'
# Only exposed-pad thermal vias may touch an SMD land (no POFV); any via ring on another land fails.
ring_rows = [r for r in ring_rows if (r[0], r[1]) not in expected]
assert not ring_rows, f'Via ring overlaps an SMD land: {ring_rows}'
for via in board.GetTracks():   # tented: no B.Mask opening on any via
    if isinstance(via, k.PCB_VIA):
        assert via.IsTented(k.B_Mask), f'via at {via.GetPosition()} is not tented on B.Mask'
result = {'board_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
          'method': 'native pcbnew PAD.HitTest with drill-radius accuracy; all SMT pads/all through vias',
          'required_process': 'standard tented vias (no POFV); thermal vias in the five exposed pads stay open on '
                              'top under paste, per the TI package notes (filled, plugged or tented); '
                              'obtain vendor DFM approval',
          'unexpected_via_ring_smt_overlaps': [],
          'intended_overlaps': rows,
          'unexpected_drill_smt_overlaps': [],
          'vendor_dfm_approval': 'NOT PERFORMED'}
(root / 'validation/via-in-pad-process.json').write_text(json.dumps(result, indent=2)+'\n')
print(f'{len(rows)} exposed-pad thermal vias (tented); no other via drill or ring on an SMT land.')
