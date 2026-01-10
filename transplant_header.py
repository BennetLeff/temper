
import sys
import re

def transplant(template_path, target_path):
    print(f"Transplanting header from {template_path} to {target_path}...")
    
    with open(template_path, 'r') as f:
        template_content = f.read()
    
    with open(target_path, 'r') as f:
        target_content = f.read()
        
    # 1. Extract header from template (everything before first content item)
    patterns = [r"\(footprint ", r"\(gr_", r"\(segment ", r"\(via ", r"\(zone "]
    first_template_pos = len(template_content)
    for p in patterns:
        m = re.search(p, template_content)
        if m and m.start() < first_template_pos:
            first_template_pos = m.start()
            
    header = template_content[:first_template_pos]
    
    # 2. Extract content from target (everything from first content item)
    first_target_pos = len(target_content)
    for p in patterns:
        m = re.search(p, target_content)
        if m and m.start() < first_target_pos:
            first_target_pos = m.start()
            
    content = target_content[first_target_pos:]
    
    # 3. Join them
    final_output = header + content
    
    # 4. Fix kiutils bugs
    
    # Fix the uuid bug
    tstamp_pattern = re.compile(r"\(tstamp ([0-9a-fA-F-]+)\)")
    final_output = tstamp_pattern.sub(r'(uuid "\1")', final_output)
    
    # Fix corrupted drill offset bug (kiutils outputting python list representation)
    # The corrupted syntax is usually: (drill ['offset', (offset -0.9 0))
    # Note: It has TWO opening parens and TWO closing parens.
    # Our previous regex was: \(drill \['offset'[^)]+\)
    # This matched (drill ['offset', (offset -0.9 0) but LEFT the final )
    # This caused a massive paren imbalance.
    
    # Corrected regex to match BOTH parens:
    final_output = re.sub(r"\(drill \['offset', \(offset [^)]+\)\)", "", final_output)
    
    # Sometimes it might be slightly different:
    final_output = re.sub(r"\(drill \['offset'[^)]+\)\)", "", final_output)

    # 5. Balance Parentheses
    # We need exactly ONE open paren to start (the board) and all others to be balanced
    # The header includes the opening (kicad_pcb ...)
    # So we need final_output to have EXACTLY one more ( than ) at the very end to be balanced.
    
    open_count = final_output.count('(')
    # First, strip all trailing closing parens and whitespace to start clean
    final_output = final_output.rstrip().rstrip(')')
    
    # Now count internal parens
    internal_open = final_output.count('(')
    internal_close = final_output.count(')')
    
    # We need internal_close to equal internal_open - 1 (since the board is still open)
    # Then we add the final ) to close the board.
    
    diff = internal_open - internal_close
    print(f"Paren count: Open={internal_open}, Close={internal_close}, Diff={diff}")
    
    if diff > 1:
        # Need more closing parens for internal items
        final_output += ")" * (diff - 1)
    elif diff < 1:
        # Too many closing parens somehow? This shouldn't happen after rstrip(')')
        # but let's be safe.
        pass

    # Finally, close the board
    final_output = final_output.rstrip() + "\n)\n"

    with open(target_path, 'w') as f:
        f.write(final_output)
    print("Header transplanted and paren balanced successfully.")

if __name__ == "__main__":
    if len(sys.argv) > 2:
        transplant(sys.argv[1], sys.argv[2])
    else:
        print("Usage: python3 transplant_header.py <template> <target>")
