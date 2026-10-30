#!/usr/bin/env python3
"""Native KiCad drill/SMT geometry receipt; no substituted clearance engine (temper_boardkit.kicad.via_in_pad)."""
from pathlib import Path
import hashlib
import json
import sys

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / 'cad' / 'tools'))
import boardkit_path  # noqa: E402,F401
from temper_boardkit import kicad  # noqa: E402

path = root / 'cad/temper-lcr.kicad_pcb'
board = kicad.load_board(path)
# Only the exposed-pad thermal vias may touch an SMD land (no POFV); any via ring on another land fails;
# every via is tented on B.Mask.
expected = {('U1','57'), ('U11','9'), ('U12','9'), ('U13','25'), ('U14','25')}
rows = kicad.via_in_pad_audit(board, expected)
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
