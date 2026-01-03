#!/usr/bin/env python3
"""
Analyze power section component placement for temper-2edy.10
Check for overlaps and clearance violations between high-voltage components.
"""

import sys
sys.path.append('packages/temper-placer/src')

from temper_placer.io.kicad_parser import parse_kicad_pcb
import math

def get_component_bbox(comp):
    """Get bounding box for a component."""
    if not comp.initial_position:
        return None
    
    x, y = comp.initial_position
    w, h = comp.bounds
    
    # Account for rotation (simplified - assumes 0, 90, 180, 270)
    rot = comp.initial_rotation or 0
    if rot % 2 == 1:  # 90 or 270 degrees
        w, h = h, w
    
    return {
        'ref': comp.ref,
        'x_min': x - w/2,
        'x_max': x + w/2,
        'y_min': y - h/2,
        'y_max': y + h/2,
        'center': (x, y),
        'size': (w, h)
    }

def check_overlap(bbox1, bbox2):
    """Check if two bounding boxes overlap."""
    x_overlap = not (bbox1['x_max'] < bbox2['x_min'] or bbox2['x_max'] < bbox1['x_min'])
    y_overlap = not (bbox1['y_max'] < bbox2['y_min'] or bbox2['y_max'] < bbox1['y_min'])
    return x_overlap and y_overlap

def get_clearance(bbox1, bbox2):
    """Get minimum clearance between two bounding boxes."""
    # Edge-to-edge distance
    dx = max(0, max(bbox1['x_min'] - bbox2['x_max'], bbox2['x_min'] - bbox1['x_max']))
    dy = max(0, max(bbox1['y_min'] - bbox2['y_max'], bbox2['y_min'] - bbox1['y_max']))
    
    if dx > 0 and dy > 0:
        # Diagonal distance
        return math.sqrt(dx**2 + dy**2)
    else:
        # One dimension overlaps, return the other
        return max(dx, dy)

def main():
    result = parse_kicad_pcb('width_final.kicad_pcb')
    netlist = result.netlist
    
    # Power section components
    power_comps = ['D2', 'C_BUS1', 'C_BUS2', 'Q1', 'Q2']
    
    # Get bounding boxes
    bboxes = {}
    for comp in netlist.components:
        if comp.ref in power_comps:
            bbox = get_component_bbox(comp)
            if bbox:
                bboxes[comp.ref] = bbox
    
    print("=" * 70)
    print("POWER SECTION COMPONENT PLACEMENT ANALYSIS (temper-2edy.10)")
    print("=" * 70)
    print()
    
    print("Component Positions and Sizes:")
    print("-" * 70)
    for ref, bbox in sorted(bboxes.items()):
        print(f"{ref:8s}: Center ({bbox['center'][0]:6.2f}, {bbox['center'][1]:6.2f}) mm, "
              f"Size ({bbox['size'][0]:5.2f} x {bbox['size'][1]:4.2f}) mm")
    print()
    
    # Check for overlaps and clearances
    print("Clearance Analysis:")
    print("-" * 70)
    
    min_hv_clearance = 2.0  # mm - minimum for high voltage
    min_std_clearance = 0.5  # mm - minimum for standard
    
    issues = []
    warnings = []
    
    refs = sorted(bboxes.keys())
    for i, ref1 in enumerate(refs):
        for ref2 in refs[i+1:]:
            bbox1 = bboxes[ref1]
            bbox2 = bboxes[ref2]
            
            if check_overlap(bbox1, bbox2):
                issues.append(f"❌ OVERLAP: {ref1} and {ref2} - components physically overlap!")
            else:
                clearance = get_clearance(bbox1, bbox2)
                
                # Determine required clearance based on component types
                # Q1, Q2 are IGBTs (high voltage), D2 is rectifier (high voltage)
                # C_BUS are DC bus caps (high voltage)
                is_hv_pair = True  # All these components are HV
                
                required = min_hv_clearance if is_hv_pair else min_std_clearance
                
                status = "✓" if clearance >= required else "⚠"
                
                msg = f"{status} {ref1} ↔ {ref2}: {clearance:.2f} mm (required: {required:.2f} mm)"
                
                if clearance < required:
                    warnings.append(msg)
                    print(msg)
                else:
                    print(msg)
    
    print()
    
    if issues:
        print("CRITICAL ISSUES:")
        print("-" * 70)
        for issue in issues:
            print(issue)
        print()
    
    if warnings:
        print("WARNINGS (Insufficient Clearance):")
        print("-" * 70)
        for warning in warnings:
            print(warning)
        print()
    
    if not issues and not warnings:
        print("✓ All clearances meet requirements!")
        print()
    
    # Recommendations
    print("Recommendations:")
    print("-" * 70)
    if issues or warnings:
        print("1. Increase spacing between components in power section")
        print("2. Consider vertical stacking (Q1/Q2 on opposite sides of board)")
        print("3. Review AC_N and DC_BUS+ net routing for potential shorts")
        print("4. Ensure adequate creepage/clearance for HV nets (2mm minimum)")
    else:
        print("1. Verify that routing respects the 2mm HV clearance")
        print("2. Check for any trace-to-pad shorts in DRC report")
        print("3. Ensure power planes do not create unintended shorts")
    
    print()
    print("=" * 70)

if __name__ == '__main__':
    main()
