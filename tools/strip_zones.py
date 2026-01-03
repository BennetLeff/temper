import sys
import re
from pathlib import Path

def strip_zones(input_path):
    content = Path(input_path).read_text()
    
    # Simple state machine to skip (zone ...) blocks
    # Assumes (zone ...) blocks are well-formed and nested parentheses are balanced
    
    new_content = []
    i = 0
    n = len(content)
    
    while i < n:
        if content[i:i+6] == "  (zone": # match indentation
            # Find matching close paren
            depth = 0
            start = i
            # Consume (zone
            i += 6 
            depth = 1
            while i < n and depth > 0:
                if content[i] == '(': 
                    depth += 1
                elif content[i] == ')':
                    depth -= 1
                i += 1
            # Skip the newline after zone if present
            if i < n and content[i] == '\n':
                i += 1
            print(f"Removed zone at char {start}")
        else:
            new_content.append(content[i])
            i += 1
            
    return "".join(new_content)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: strip_zones.py <file>")
        sys.exit(1)
        
    out = strip_zones(sys.argv[1])
    Path(sys.argv[1]).write_text(out)
