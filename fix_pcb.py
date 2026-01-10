
import sys
import re

def fix_pcb(path):
    print(f"Fixing {path}...")
    with open(path, 'r') as f:
        content = f.read()
        
    # Pattern: (drill ['offset', -0.9, 0] (offset -0.9 0))
    # We want: (drill (offset -0.9 0))
    # Regex: (drill \['offset'[^]]+\] 
    
    pattern = re.compile(r"\(drill \['offset'[^]]+\] ")
    
    fixed_content, count = pattern.subn("(drill ", content)
    
    if count > 0:
        print(f"Fixed {count} instances of malformed drill offset.")
        with open(path, 'w') as f:
            f.write(fixed_content)
    else:
        print("No malformed drill offsets found.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        fix_pcb(sys.argv[1])
    else:
        print("Usage: python fix_pcb.py <file>")
