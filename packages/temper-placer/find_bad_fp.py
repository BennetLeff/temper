
from kiutils.board import Board
from temper_placer.router_v6.test_boards import get_available_boards
from pathlib import Path
import subprocess

boards = get_available_boards()
piantor = boards[0]
path = Path(piantor.path)
full_board = Board.from_file(path)
all_fps = full_board.footprints

print(f"Total footprints: {len(all_fps)}")

def check_range(start_idx, end_idx):
    # Create board with subset of footprints
    board = Board.from_file(path)
    board.footprints = all_fps[start_idx:end_idx]
    board.traceItems = []
    board.zones = []
    board.drawings = []
    
    out_path = Path(f'/tmp/bisect_range_{start_idx}_{end_idx}.kicad_pcb')
    board.to_file(str(out_path))
    
    cmd = ['kicad-cli', 'pcb', 'drc', '--output', f'/tmp/drc_{start_idx}.json', str(out_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode == 0

# Linear scan for now if small enough, or chunks
chunk_size = 10
for i in range(0, len(all_fps), chunk_size):
    end = min(i + chunk_size, len(all_fps))
    result = check_range(i, end)
    print(f"Range {i}-{end}: {'PASS' if result else 'FAIL'}")
    
    if not result:
        print("  Drilling down...")
        for j in range(i, end):
            if not check_range(j, j+1):
                print(f"    Footprint {j} FAILED")
                # Dump this footprint to file for inspection
                with open(f'/tmp/bad_fp_{j}.txt', 'w') as f:
                    f.write(all_fps[j].to_sexpr())
