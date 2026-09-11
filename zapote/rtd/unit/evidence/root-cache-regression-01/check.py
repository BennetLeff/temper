import hashlib
import inspect
import json
from pathlib import Path
import shutil
import subprocess
import sys
import pcbnew

REPO = Path('/Users/bennet/Desktop/temper/.worktrees/codex/buck-harness-experiment-plan')
OUT = Path(__file__).resolve().parent
sys.path[:0] = [str(REPO/'harness-lab'), str(REPO/'zapote/rtd')]
import buck_native
import block_native
import apply_routes

CLI = '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
UNIT = REPO/'zapote/rtd/unit'
instruction = UNIT/'routes-09-return-stitches.json'
spec = json.loads(instruction.read_text())
positions = {tuple(x['position_mm']) for x in spec['nets'][0]['vias']}

def census(path):
    b = buck_native.load(path)
    rows = []
    for item in b.GetTracks():
        if item.Type() == pcbnew.PCB_VIA_T:
            pos = tuple(round(x, 6) for x in pcbnew.ToMM(item.GetPosition()))
            if pos in positions:
                rows.append({'position': pos, 'net': item.GetNetname()})
    return sorted(rows, key=lambda x: x['position'])

def refill(path, report):
    p = subprocess.run([CLI, 'pcb', 'drc', '--refill-zones', '--save-board', '--all-track-errors', '--severity-all', '--format', 'json', '--output', str(report), str(path)], capture_output=True, text=True)
    report.with_suffix('.log').write_text(p.stdout+p.stderr)
    if p.returncode != 0:
        raise RuntimeError((p.returncode, p.stderr))

mode = sys.argv[1]
if mode == 'prepare':
    base = OUT/'base'
    shutil.copytree(UNIT/'candidate', base, dirs_exist_ok=True)
    path = base/'section.kicad_pcb'
    path.write_bytes((UNIT/'evidence/source03-return-pass.kicad_pcb').read_bytes())
    b = buck_native.load(path)
    for z in b.Zones():
        z.UnFill()
    for item in list(b.GetTracks()):
        if item.Type() == pcbnew.PCB_VIA_T:
            pos = tuple(round(x, 6) for x in pcbnew.ToMM(item.GetPosition()))
            if pos in positions:
                b.Remove(item)
    buck_native.save(b, path)
    refill(path, base/'refill.json')
    assert census(path) == []
    print('Prepared filled baseline without seven stitches')
else:
    if mode == 'legacy':
        source = inspect.getsource(block_native.replace_copper)
        needle = '    for zone in board.Zones():\n        zone.UnFill()\n'
        assert source.count(needle) == 1
        exec(source.replace(needle, ''), block_native.__dict__)
        source = inspect.getsource(apply_routes._replay)
        needle = '                for zone in target.Zones():\n                    zone.UnFill()\n'
        assert source.count(needle) == 1
        exec(source.replace(needle, ''), apply_routes.__dict__)
    dst = OUT/mode
    shutil.copytree(OUT/'base', dst, dirs_exist_ok=True)
    path = dst/'section.kicad_pcb'
    apply_routes.run(path, instruction, dst/'replay.json')
    before = census(path)
    refill(path, dst/'refill.json')
    result = {'mode': mode, 'before_refill': before, 'after_refill': census(path), 'kicad': pcbnew.Version(), 'board_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    (dst/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))
