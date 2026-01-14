
from kiutils.board import Board
from kiutils.items.common import Position
from temper_placer.router_v6.test_boards import get_available_boards
from pathlib import Path
import subprocess
import sys

# Get template
boards = get_available_boards()
piantor = boards[0]
path = Path(piantor.path)
board = Board.from_file(path)

# Keep only one footprint for testing
fp = board.footprints[0]
board.footprints = [fp]
board.traceItems = []
board.zones = []
board.drawings = []

def test_config(name, modifier_func):
    # Reload fresh copy of footprint
    test_board = Board.from_file(path)
    test_board.footprints = [test_board.footprints[0]]
    test_board.traceItems = []
    test_board.zones = []
    test_board.drawings = []
    
    # Apply modification
    modifier_func(test_board.footprints[0])
    
    # Save
    out_path = Path(f'/tmp/bisect_{name}.kicad_pcb')
    test_board.to_file(out_path)
    
    # Run DRC check
    cmd = ['kicad-cli', 'pcb', 'drc', '--output', f'/tmp/drc_{name}.json', str(out_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    
    status = "PASS" if proc.returncode == 0 else "FAIL"
    print(f"Test '{name}': {status}")
    if status == "FAIL":
        # print(proc.stderr[:100])
        pass

# Tests
print("Starting bisection...")

def no_properties(fp):
    fp.properties = []

def no_pads(fp):
    fp.pads = []

def no_graphics(fp):
    fp.graphicItems = []

def no_models(fp):
    fp.models = []

test_config("baseline", lambda x: None) # Should fail
test_config("no_props", no_properties)
test_config("no_pads", no_pads)
test_config("no_graphics", no_graphics)
test_config("no_models", no_models)
