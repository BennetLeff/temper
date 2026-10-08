#!/usr/bin/env python3
"""Read saved footprint identities/positions and physical pad centres (KiCad Python)."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import pcbnew

HERE=Path(__file__).resolve().parent
UNIT=HERE.parents[3]
board_path=UNIT/'native-15/section.kicad_pcb'
board=pcbnew.LoadBoard(str(board_path))
parts={}
for fp in board.GetFootprints():
    parts[fp.GetReference()]={'part':fp.GetValue(),'centre_mm':[pcbnew.ToMM(fp.GetPosition().x),pcbnew.ToMM(fp.GetPosition().y)],
                            'pads':[{'number':p.GetNumber(),'centre_mm':[pcbnew.ToMM(p.GetPosition().x),pcbnew.ToMM(p.GetPosition().y)],
                                     'net':p.GetNetname()} for p in fp.Pads()]}
result={'board':'native-15/section.kicad_pcb','board_sha256':hashlib.sha256(board_path.read_bytes()).hexdigest(),
        'kicad_version':pcbnew.GetBuildVersion(),'parts':dict(sorted(parts.items()))}
(HERE.parent/'inputs/board-parts.json').write_text(json.dumps(result,indent=2)+'\n')
print('Saved',len(parts),'footprints; board',result['board_sha256'])
