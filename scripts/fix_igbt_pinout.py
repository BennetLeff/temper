#!/usr/bin/env python3
"""
Fix IGBT Pinout (TO-247 1G 2C 3E) in PCB file.

Problem: The current layout has swapped Collector and Emitter nets.
Standard: Pin 2 = Collector, Pin 3 = Emitter.
Current PCB: Pin 2 connected to Emitter Net, Pin 3 connected to Collector Net.

Action: Swap Net assignments on Pad 2 and Pad 3 for Q1 and Q2.
"""

import re
import sys
from pathlib import Path

def swap_pads(content: str, ref: str) -> str:
    """Swap net assignments for Pad 2 and Pad 3 of the given reference."""
    # Find the footprint block
    # We'll use a specific regex to find the block for the reference
    # Because regex matching nested parens is hard, we iterate.
    
    pos = 0
    while True:
        # Find start of a footprint
        match = re.search(r'\(footprint\s+"[^"]+"\s+\(layer\s+"[^"]+"\)', content[pos:])
        if not match:
            break
        
        start = pos + match.start()
        
        # Find the end of the block by counting parens
        depth = 0
        block_end = start
        found_start = False
        
        # Helper to scan forward efficiently
        for i in range(start, len(content)):
            if content[i] == '(':
                depth += 1
                found_start = True
            elif content[i] == ')':
                depth -= 1
            
            if found_start and depth == 0:
                block_end = i + 1
                break
        
        block = content[start:block_end]
        
        if f'property "Reference" "{ref}"' in block:
            print(f"Found {ref}...")
            
            # Extract Pad 2 line
            # Pattern: (pad "2" ... (net ID "NAME"))
            # Use DOTALL to match across newlines
            pad2_match = re.search(r'\(pad "2".*?\(net (\d+) "([^"]+)"\)\)', block, re.DOTALL)
            pad3_match = re.search(r'\(pad "3".*?\(net (\d+) "([^"]+)"\)\)', block, re.DOTALL)
            
            if pad2_match and pad3_match:
                pad2_full = pad2_match.group(0)
                pad2_net_id = pad2_match.group(1)
                pad2_net_name = pad2_match.group(2)
                
                pad3_full = pad3_match.group(0)
                pad3_net_id = pad3_match.group(1)
                pad3_net_name = pad3_match.group(2)
                
                print(f"  Pad 2 was: {pad2_net_name} ({pad2_net_id})")
                print(f"  Pad 3 was: {pad3_net_name} ({pad3_net_id})")
                
                # Create new lines by swapping the net part
                # We replace the net definition in the original strings
                new_pad2_full = pad2_full.replace(f'(net {pad2_net_id} "{pad2_net_name}")', f'(net {pad3_net_id} "{pad3_net_name}")')
                new_pad3_full = pad3_full.replace(f'(net {pad3_net_id} "{pad3_net_name}")', f'(net {pad2_net_id} "{pad2_net_name}")')
                
                # Replace in block
                new_block = block.replace(pad2_full, new_pad2_full).replace(pad3_full, new_pad3_full)
                
                # Replace block in content
                content = content[:start] + new_block + content[block_end:]
                print(f"  Swapped: Pad 2 -> {pad3_net_name}, Pad 3 -> {pad2_net_name}")
                return content
            else:
                print("  Error: Could not find Pad 2 or Pad 3 definitions.")
        
        pos = block_end # Move to next block

    print(f"Warning: {ref} not found.")
    return content

def main():
    input_path = Path("unrouted_v4.kicad_pcb")
    output_path = Path("unrouted_v4_fixed.kicad_pcb")

    if not input_path.exists():
        print(f"Error: {input_path} not found")
        sys.exit(1)

    print(f"Reading {input_path}...")
    content = input_path.read_text()

    print("Fixing Q1...")
    content = swap_pads(content, "Q1")
    
    print("Fixing Q2...")
    content = swap_pads(content, "Q2")

    print(f"Writing to {output_path}...")
    output_path.write_text(content)
    print("Done.")

if __name__ == "__main__":
    main()
