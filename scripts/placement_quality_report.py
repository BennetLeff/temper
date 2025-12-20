#!/usr/bin/env python3
"""
Unified placement quality report script.
Evaluates placement metrics, DRC, and optionally routing for a KiCad PCB.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

# Add packages/temper-placer/src to sys.path
sys.path.append(str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

try:
    from temper_placer.io.kicad_parser import parse_kicad_pcb
    from temper_placer.io.reference_loader import load_reference_pcb, infer_quality_config
    from temper_placer.metrics.quality import compute_quality_report
    from temper_placer.validation.drc_runner import run_drc, is_kicad_cli_available
    from temper_placer.losses.base import LossContext
except ImportError as e:
    print(f"Error: Missing dependencies. Ensure you are running from the project root and have dependencies installed. {e}")
    sys.exit(1)

console = Console()

def parse_args():
    parser = argparse.ArgumentParser(description="Generate unified placement quality report")
    parser.add_argument("--pcb", type=str, required=True, help="Path to .kicad_pcb file")
    parser.add_argument("--config", type=str, help="Optional PCL constraints YAML file")
    parser.add_argument("--route", action="store_true", help="Run FreeRouting verification (adds time)")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument("--output", type=str, help="Output file path (for JSON)")
    return parser.parse_args()

def main():
    args = parse_args()
    pcb_path = Path(args.pcb)
    
    if not pcb_path.exists():
        console.print(f"[red]Error:[/] PCB file not found: {pcb_path}")
        sys.exit(1)
        
    # 1. Load design
    if not args.json:
        console.print(f"[bold blue]Evaluating:[/] {pcb_path}")
    try:
        design = load_reference_pcb(pcb_path)
    except Exception as e:
        if not args.json:
            console.print(f"[red]Error parsing PCB:[/] {e}")
        sys.exit(1)
        
    # 2. Placement Metrics
    if not args.json:
        console.print("  - Computing placement metrics...")
    context = LossContext.from_netlist_and_board(design.netlist, design.board)
    
    # Load manual config or infer one
    if args.config:
        from temper_placer.io.config_loader import load_constraints
        constraints = load_constraints(Path(args.config))
        # Map constraints to quality config structure
        quality_cfg = {
            "thermal_components": set(constraints.thermal_properties.high_power_components) if constraints.thermal_properties else set(),
            "hv_components": set(), # TODO: Extract from constraints
            "lv_components": set(),
            "zone_assignments": {ref: zone for zone, refs in constraints.zones.items() for ref in refs} if hasattr(constraints, 'zones') else {},
            "loop_components": [], # TODO
            "min_hv_lv_clearance": constraints.hv_clearance_mm if hasattr(constraints, 'hv_clearance_mm') else 8.0
        }
    else:
        quality_cfg = infer_quality_config(design)
        
    placement_report = compute_quality_report(
        design.state, design.netlist, design.board, context, quality_cfg
    )
    
    # 3. DRC Metrics
    drc_metrics = {"violations": 0, "errors": 0, "warnings": 0}
    if is_kicad_cli_available():
        if not args.json:
            console.print("  - Running KiCad DRC...")
        try:
            drc_res = run_drc(pcb_path)
            drc_metrics = {
                "violations": drc_res.error_count + drc_res.warning_count,
                "errors": drc_res.error_count,
                "warnings": drc_res.warning_count
            }
        except Exception as e:
            if not args.json:
                console.print(f"  [yellow]Warning:[/] DRC failed: {e}")
    else:
        if not args.json:
            console.print("  [yellow]Skipping DRC:[/] kicad-cli not available")
        
    # 4. Routing Metrics (Optional)
    routing_metrics = {}
    if args.route:
        if not args.json:
            console.print("  - Running FreeRouting (this may take several minutes)...")
        from temper_placer.routing.freerouting import FreeRoutingWrapper
        router = FreeRoutingWrapper()
        if router.is_available():
            try:
                route_res = router.route(pcb_path)
                routing_metrics = {
                    "completion_pct": route_res.completion_pct,
                    "wirelength_mm": route_res.wirelength_mm,
                    "via_count": route_res.via_count,
                    "routing_time_s": route_res.elapsed_s
                }
            except Exception as e:
                if not args.json:
                    console.print(f"  [yellow]Warning:[/] Routing failed: {e}")
        else:
            if not args.json:
                console.print("  [yellow]Skipping routing:[/] FreeRouting not available")
            
    # 5. Compile Result
    final_report = {
        "input_file": str(pcb_path),
        "timestamp": datetime.now().isoformat(),
        "placement_metrics": placement_report,
        "drc_metrics": drc_metrics,
        "routing_metrics": routing_metrics,
        "quality_score": placement_report["overall_score"] * 100,
        "pass": drc_metrics["errors"] == 0
    }
    
    # 6. Output
    if args.json:
        json_output = json.dumps(final_report, indent=2)
        if args.output:
            with open(args.output, "w") as f:
                f.write(json_output)
            console.print(f"[green]✓[/] Report written to {args.output}")
        else:
            print(json_output)
    else:
        # Human readable output
        console.print("\n" + "="*50)
        console.print(Panel(f"Quality Score: [bold green]{final_report['quality_score']:.1f}/100[/]", title="Placement Quality Report"))
        
        table = Table(title="Placement Metrics")
        table.add_column("Metric", style="cyan")
        table.add_column("Score", style="magenta")
        for k, v in placement_report.items():
            if k == "total_wirelength":
                table.add_row("Wirelength", f"{v:.1f} mm")
            elif k != "overall_score":
                table.add_row(k.replace("_", " ").title(), f"{v:.2f}")
        console.print(table)
        
        drc_table = Table(title="DRC Metrics")
        drc_table.add_column("Type", style="cyan")
        drc_table.add_column("Count", style="magenta")
        drc_table.add_row("Total Violations", str(drc_metrics["violations"]))
        drc_table.add_row("Errors", f"[red]{drc_metrics['errors']}[/]")
        drc_table.add_row("Warnings", f"[yellow]{drc_metrics['warnings']}[/]")
        console.print(drc_table)
        
        if routing_metrics:
            route_table = Table(title="Routing Metrics")
            route_table.add_column("Metric", style="cyan")
            route_table.add_column("Value", style="magenta")
            route_table.add_row("Completion", f"{routing_metrics['completion_pct']:.1f}%")
            route_table.add_row("Wirelength", f"{routing_metrics['wirelength_mm']:.1f} mm")
            route_table.add_row("Vias", str(routing_metrics["via_count"]))
            console.print(route_table)
            
        status = "[bold green]PASS[/]" if final_report["pass"] else "[bold red]FAIL[/] (DRC errors)"
        console.print(f"\nFinal Status: {status}")

if __name__ == "__main__":
    main()
