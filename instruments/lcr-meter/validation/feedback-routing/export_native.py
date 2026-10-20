"""Export native KiCad geometry only; path analysis lives in measure.rs."""
from pathlib import Path
import hashlib
import sys

import pcbnew as k

board_path = Path(sys.argv[1]).resolve()
board = k.LoadBoard(str(board_path))
nets = {'DUT_LO', 'TIA_OUT', 'RF100', 'RF5K', 'RF100K'}
rows = ['# board_sha256=' + hashlib.sha256(board_path.read_bytes()).hexdigest()]
for item in board.GetTracks():
    if item.GetNetname() not in nets:
        continue
    if isinstance(item, k.PCB_VIA):
        point = item.GetPosition()
        rows.append(f'VIA\t{item.GetNetname()}\t{point.x}\t{point.y}')
    else:
        a, b = item.GetStart(), item.GetEnd()
        rows.append(f'SEG\t{item.GetNetname()}\t{board.GetLayerName(item.GetLayer())}'
                    f'\t{a.x}\t{a.y}\t{b.x}\t{b.y}\t{item.GetWidth()}')
for footprint in board.GetFootprints():
    for pad in footprint.Pads():
        if pad.GetNetname() not in nets:
            continue
        point = pad.GetPosition()
        plated = int(pad.GetAttribute() == k.PAD_ATTRIB_PTH)
        rows.append(f'PAD\t{footprint.GetReference()}.{pad.GetNumber()}'
                    f'\t{pad.GetNetname()}\t{point.x}\t{point.y}\t{plated}')
print('\n'.join(sorted(rows)))
