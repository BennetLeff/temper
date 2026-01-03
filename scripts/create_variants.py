import re
import sys
from pathlib import Path

def get_block_from_content(c, start_pos):
    depth = 0
    for i in range(start_pos, len(c)):
        if c[i] == '(':
            depth += 1
        elif c[i] == ')':
            depth -= 1
            if depth == 0:
                return c[start_pos:i+1]
    return None

def shift_component(content, ref, dx, dy):
    pos = 0
    while True:
        match = re.search(r'\(footprint\s+"[^"]+"', content[pos:])
        if not match:
            break
        start = pos + match.start()
        block = get_block_from_content(content, start)
        if not block:
            break
        
        if f'"Reference" "{ref}"' in block:
            at_match = re.search(r'\(at ([\d.-]+) ([\d.-]+)(?: ([\d.-]+))?\)', block)
            if at_match:
                x = float(at_match.group(1))
                y = float(at_match.group(2))
                r_str = f" {at_match.group(3)}" if at_match.group(3) else ""
                new_at = f"(at {x + dx:.6f} {y + dy:.6f}{r_str})"
                new_block = block.replace(at_match.group(0), new_at)
                return content[:start] + new_block + content[start + len(block):]
        
        pos = start + len(block)
    return content

def move_all_toward_center(c, center_x, center_y, distance):
    pos = 0
    final_content = ""
    last_end = 0
    while True:
        match = re.search(r'\(footprint\s+"[^"]+"', c[pos:])
        if not match:
            break
        start = pos + match.start()
        block = get_block_from_content(c, start)
        if not block:
            break
        
        at_match = re.search(r'\(at ([\d.-]+) ([\d.-]+)(?: ([\d.-]+))?\)', block)
        if at_match:
            x = float(at_match.group(1))
            y = float(at_match.group(2))
            r_str = f" {at_match.group(3)}" if at_match.group(3) else ""
            
            vx = center_x - x
            vy = center_y - y
            mag = (vx**2 + vy**2)**0.5
            if mag > distance:
                nx = x + (vx / mag) * distance
                ny = y + (vy / mag) * distance
            else:
                nx, ny = center_x, center_y
            
            new_at = f"(at {nx:.6f} {ny:.6f}{r_str})"
            new_block = block.replace(at_match.group(0), new_at)
            final_content += c[last_end:start] + new_block
            last_end = start + len(block)
        
        pos = start + len(block)
    final_content += c[last_end:]
    return final_content

def main():
    input_file = Path("pcb/temper_ready_for_route.kicad_pcb")
    content = input_file.read_text()
    
    # Variant 2: SPI components moved 10mm closer to MCU
    spi_refs = ["U_CT", "C_CT_FILT", "U_OPAMP_CT", "MAX31865"]
    v2_content = content
    for ref in spi_refs:
        v2_content = shift_component(v2_content, ref, 10, 0)
    Path("pcb/variant_spi_closer.kicad_pcb").write_text(v2_content)
    print("Created pcb/variant_spi_closer.kicad_pcb")
    
    # Variant 3: All components moved 5mm toward board center (50, 75)
    v3_content = move_all_toward_center(content, 50, 75, 5)
    Path("pcb/variant_center_shift.kicad_pcb").write_text(v3_content)
    print("Created pcb/variant_center_shift.kicad_pcb")

if __name__ == "__main__":
    main()
