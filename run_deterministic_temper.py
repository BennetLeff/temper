#!/usr/bin/env python3
"""
Run deterministic pipeline on Temper board - Final Validation
This is temper-ho32: the final milestone for zero-DRC validation.
"""

import sys
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Add packages to path
sys.path.insert(0, str(Path(__file__).parent / 'packages' / 'temper-placer' / 'src'))

from temper_placer.pipeline.mvp3_runner import MVP3Runner, MVP3Config

def main():
    print("=" * 80)
    print("FINAL VALIDATION: Temper Board Deterministic Pipeline")
    print("=" * 80)
    print()
    
    # Paths
    pcb_path = Path(__file__).parent / 'pcb' / 'temper.kicad_pcb'
    config_path = Path(__file__).parent / 'configs' / 'temper_deterministic_config.yaml'
    output_path = Path(__file__).parent / 'pcb' / 'temper_deterministic_final.kicad_pcb'
    
    print(f"Input PCB:  {pcb_path}")
    print(f"Config:     {config_path}")
    print(f"Output PCB: {output_path}")
    print()
    
    # Verify files exist
    if not pcb_path.exists():
        print(f"ERROR: Input PCB not found: {pcb_path}")
        return 1
    if not config_path.exists():
        print(f"ERROR: Config file not found: {config_path}")
        return 1
    
    # Configure MVP3
    mvp3_config = MVP3Config(
        layer_count=4,
        cell_size_mm=0.25,
        slot_spacing_mm=5.0,
    )
    
    # Create runner
    runner = MVP3Runner(
        pcb_path=pcb_path,
        config_path=config_path,
        output_path=output_path,
        mvp3_config=mvp3_config,
    )
    
    # Run pipeline
    print("Starting deterministic pipeline...")
    print()
    result = runner.run()
    
    # Report results
    print()
    print("=" * 80)
    print("RESULTS")
    print("=" * 80)
    print()
    
    if result.success:
        print("✅ Pipeline completed successfully!")
        print()
        print(f"Components placed: {result.components_placed}/{result.total_components}")
        print(f"Nets routed: {result.nets_routed}/{result.total_nets}")
        
        if result.total_nets > 0:
            completion = 100 * result.nets_routed / result.total_nets
            print(f"Routing completion: {completion:.1f}%")
        
        print()
        print(f"Output saved to: {output_path}")
        print()
        
        if completion >= 100.0:
            print("🎉 100% ROUTING COMPLETION ACHIEVED!")
            print("Next step: Run KiCad DRC validation")
        else:
            print(f"⚠️  {result.total_nets - result.nets_routed} nets failed to route")
        
        return 0
    else:
        print("❌ Pipeline failed!")
        print(f"Error: {result.error}")
        return 1

if __name__ == '__main__':
    sys.exit(main())
