
from kiutils.board import Board
from temper_placer.router_v6.test_boards import get_available_boards
from pathlib import Path
import subprocess

boards = get_available_boards()
piantor = boards[0]
path = Path(piantor.path)
board = Board.from_file(path)

print("Scanning for corrupt drills...")
fixed_count = 0
for fp in board.footprints:
    for pad in fp.pads:
        if pad.drill and isinstance(pad.drill, str) and "[" in pad.drill:
            print(f"Found corrupt drill in FP {fp.description} Pad {pad.number}: {pad.drill}")
            # Fix it: pure SMD pads shouldn't have drills usually? 
            # Or if they do, it's likely a parsing error.
            # Let's try setting it to None if it's SMD?
            if pad.type == 'smd':
                pad.drill = None
                fixed_count += 1
            else:
                print("  WARNING: TH pad with corrupt drill? Not removing.")

print(f"Fixed {fixed_count} pads.")

out_path = Path('/tmp/piantor_drill_fixed.kicad_pcb')
board.to_file(out_path)

cmd = ['kicad-cli', 'pcb', 'drc', '--output', '/tmp/drc_fixed.json', str(out_path)]
proc = subprocess.run(cmd, capture_output=True, text=True)

if proc.returncode == 0:
    print("SUCCESS: DRC passed with fixed drills!")
else:
    print(f"FAILED: {proc.stderr}")
