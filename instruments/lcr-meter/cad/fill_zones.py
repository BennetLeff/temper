#!/usr/bin/env python3
"""Persist native KiCad zone fill; run with bundled pcbnew Python."""
from pathlib import Path
import pcbnew
path = Path(__file__).resolve().parent / 'temper-lcr.kicad_pcb'
board = pcbnew.LoadBoard(str(path))
pcbnew.ZONE_FILLER(board).Fill(board.Zones())
if not pcbnew.SaveBoard(str(path), board):
    raise RuntimeError('KiCad did not save the filled board')
print(f'Filled {len(board.Zones())} zones and saved {path}')
