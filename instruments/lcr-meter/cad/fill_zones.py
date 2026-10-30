#!/usr/bin/env python3
"""Persist native KiCad zone fill; run with bundled pcbnew Python.

When design.json sets board.teardrops (Rev F), KiCad's teardrop generator runs first: the Python API has no
entry point for it, so `kicad-cli pcb drc --refill-zones --save-board` creates the teardrop zones.  Their
zones carry no UUID in the file and come out in a run-dependent order with run-dependent priorities, so they are
rewritten in the order of their net, layer and outline text, with priority 30000 + rank, and loaded below with a
seeded KIID generator: the UUIDs KiCad assigns on load, and so its save order, are the same on every run.  The
fill is the in-process ZONE_FILLER as before, with the teardrops filled one zone per call (a threaded fill of
all of them moves a vertex of one or two teardrops by about 3e-5 mm2 from run to run).
"""
import json
import re
import subprocess
from pathlib import Path
import pcbnew
ROOT = Path(__file__).resolve().parent
path = ROOT / 'temper-lcr.kicad_pcb'


def teardrops():
    log = ROOT.parent / 'build' / 'teardrop-drc.json'
    log.parent.mkdir(exist_ok=True)
    subprocess.run(['kicad-cli', 'pcb', 'drc', '--refill-zones', '--save-board', '--format', 'json',
                    '--output', str(log), str(path)], check=True, capture_output=True)
    text = path.read_text()
    blocks = []                      # (start, end, key) of every teardrop zone
    for m in re.finditer(r'\n\t\(zone\n', text):
        j = m.start()
        end = text.find('\n\t)', j + 1) + 3
        block = text[j:end]
        if '(teardrop' in block:
            key = re.sub(r'\(filled_polygon.*', '', block, flags=re.S)
            key = re.sub(r'\((uuid|priority) [^)]*\)', '', key)
            blocks.append((j, end, key))
    order = sorted(range(len(blocks)), key=lambda b: blocks[b][2])
    out, i = [], 0
    for n, (j, end, key) in enumerate(blocks):
        out.append(text[i:j])
        if n == 0:                   # every teardrop zone, in key order, where the first one was
            for r, b in enumerate(order):
                bj, bend, _ = blocks[b]
                out.append(re.sub(r'\(priority \d+\)', f'(priority {30000 + r})', text[bj:bend], count=1))
        i = end
    out.append(text[i:])
    path.write_text(''.join(out))
    n = len(blocks)
    return n


design = json.loads((ROOT / 'design.json').read_text())
n_td = teardrops() if design.get('board', {}).get('teardrops') else 0
pcbnew.KIID.SeedGenerator(60030)
board = pcbnew.LoadBoard(str(path))
filler = pcbnew.ZONE_FILLER(board)
tds = [z for z in board.Zones() if z.IsTeardropArea()]
filler.Fill([z for z in board.Zones() if not z.IsTeardropArea()])
for z in tds:                        # one at a time: the threaded fill of teardrops differs by ~3e-5 mm2 run to run
    filler.Fill([z])
if not pcbnew.SaveBoard(str(path), board):
    raise RuntimeError('KiCad did not save the filled board')
print(f'Filled {len(board.Zones())} zones ({n_td} teardrops) and saved {path}')
