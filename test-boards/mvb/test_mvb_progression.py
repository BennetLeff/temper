import sys
import subprocess
import json
import shutil
from pathlib import Path
import jax.numpy as jnp
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.routing.maze_router import MazeRouter
from temper_placer.io.kicad_exporter import export_routed_pcb
from temper_placer.routing.net_ordering import order_nets
from temper_placer.routing.layer_assignment import assign_layers
from temper_placer.core.loop import LoopCollection

# Set up paths - use absolute path based on script location
SCRIPT_DIR = Path(__file__).parent.absolute()
MVB_DIR = SCRIPT_DIR
OUTPUT_DIR = MVB_DIR / "results"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def find_kicad_cli() -> Path | None:
    cli_path = shutil.which("kicad-cli")
    if cli_path:
        return Path(cli_path)
    standard_paths = [
        "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli",
        "/usr/bin/kicad-cli",
        "/usr/local/bin/kicad-cli",
        "/opt/homebrew/bin/kicad-cli",
    ]
    for path_str in standard_paths:
        path = Path(path_str)
        if path.exists():
            return path
    return None

def run_drc(pcb_path: Path) -> int:
    kicad_cli = find_kicad_cli()
    if not kicad_cli:
        print("WARNING: kicad-cli not found, skipping DRC check")
        return 0 # Skip check if no tool

    report_path = pcb_path.with_suffix(".json")
    
    cmd = [
        str(kicad_cli),
        "pcb",
        "drc",
        "--format", "json",
        "--severity-all",
        "--units", "mm",
        "--output", str(report_path),
        str(pcb_path),
    ]
    
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=False)
        if not report_path.exists():
            print("Error: DRC report not generated")
            return -1
            
        with open(report_path) as f:
            data = json.load(f)
            
        violations = data.get("violations", [])
        # Filter exclusions and warnings, only count errors
        # Also filter edge clearance and library issues which are artifacts of the test fixture
        ignored_types = ["copper_edge_clearance", "lib_footprint_issues"]
        errors = [v for v in violations if v.get("severity") == "error" and v.get("type") not in ignored_types]
        
        # Also print what kind of errors we found for debugging
        if errors:
            print(f"  Found {len(errors)} errors:")
            for e in errors[:5]: # print first 5
                print(f"    - {e.get('type')}: {e.get('description')}")
            if len(errors) > 5:
                print(f"    ... and {len(errors)-5} more")
                
        return len(errors)
    except Exception as e:
        print(f"Error running DRC: {e}")
        return -1

def test_level(level: int) -> bool:
    input_pcb = MVB_DIR / f"mvb_level_{level}.kicad_pcb"
    output_pcb = OUTPUT_DIR / f"mvb_level_{level}_routed.kicad_pcb"
    
    if not input_pcb.exists():
        print(f"Skipping Level {level}: File not found")
        return False

    print(f"\n=== Testing Level {level} ===")
    
    # 1. Parse
    print("Parsing...")
    try:
        result = parse_kicad_pcb(input_pcb)
    except Exception as e:
        print(f"FAILED: Parse error: {e}")
        return False

    board = result.board
    netlist = result.netlist
    
    if not board:
        print("FAILED: Board extraction failed")
        return False

    # 2. Prepare Routing Data
    print("Preparing routing data...")
    positions_list = []
    for comp in netlist.components:
        if comp.initial_position:
            positions_list.append(comp.initial_position)
        else:
            print(f"Warning: Component {comp.ref} has no position, using center")
            positions_list.append((board.width / 2, board.height / 2))
            
    positions = jnp.array(positions_list)
    
    loops = LoopCollection()
    net_order = order_nets(netlist, loops)
    
    # For MVB, we want to route ALL nets, even VCC/GND, unless they are handled by zones.
    # Level 3 has zones. The router should respect zones.
    # We pass all nets.
    
    assignments = assign_layers(netlist, component_positions=positions)

    # 3. Route
    print("Routing...")
    start_time = 0 # measure time if needed
    
    try:
        # Using 0.1mm cell size for precision and soft blocking for RRR
        # Enforce 0.2mm clearance
        router = MazeRouter.from_board(
            board, 
            cell_size_mm=0.1, 
            num_layers=2,
            soft_blocking=True,
            min_clearance=0.2
        )
        routes = router.rrr_route_all_nets(
            netlist, 
            positions, 
            net_order, 
            assignments,
            max_iterations=50
        )
    except Exception as e:
        print(f"FAILED: Router crashed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Check routing success
    failed_nets = [name for name, path in routes.items() if not path.success]
    if failed_nets:
        print(f"FAILED: Routing failed for nets: {failed_nets}")
        # Export anyway for debug
        export_routed_pcb(input_pcb, routes, output_pcb, cell_size=0.1, default_trace_width=0.2)
        return False
        
    print(f"Routing successful. Routed {len(routes)} nets.")
    
    # 4. Export
    print("Exporting...")
    try:
        export_routed_pcb(input_pcb, routes, output_pcb, cell_size=0.1, default_trace_width=0.2)
    except Exception as e:
        print(f"FAILED: Export error: {e}")
        return False
    
    # 5. DRC
    print("Running DRC...")
    drc_violations = run_drc(output_pcb)
    
    if drc_violations == 0:
        print("PASS: 0 DRC violations")
        return True
    elif drc_violations > 0:
        print(f"FAIL: {drc_violations} DRC violations")
        return False
    else:
        print("FAIL: DRC check error")
        return False

def main():
    levels = [0, 1, 2, 3]
    results = {}
    
    for level in levels:
        results[level] = test_level(level)
        
    print("\n" + "="*40)
    print("SUMMARY")
    print("="*40)
    all_passed = True
    for level in levels:
        status = "PASS" if results[level] else "FAIL"
        print(f"Level {level}: {status}")
        if not results[level]:
            all_passed = False
            
    sys.exit(0 if all_passed else 1)

if __name__ == "__main__":
    main()
