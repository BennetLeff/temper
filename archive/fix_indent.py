
import sys

def fix_sequential_routing(filepath):
    with open(filepath, 'r') as f:
        lines = f.readlines()
        
    new_lines = []
    
    # We need to find the BAD block and its current indentation
    # Bad block starts roughly at 1380
    
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped:
            new_lines.append(line)
            continue
            
        indent = len(line) - len(stripped)
        
        # If in the problematic range and way over-indented (e.g. 36 spaces)
        if i >= 1370 and i <= 1475 and indent >= 24:
            # Shift back by 16 spaces (36 -> 20, 40 -> 24 etc)
            # This preserves relative indentation!
            new_indent = indent - 16
            new_lines.append(" " * new_indent + stripped)
        else:
            new_lines.append(line)
        
    with open(filepath, 'w') as f:
        f.writelines(new_lines)
    print("Fixed indentation in sequential_routing.py (relative preserved)")

if __name__ == "__main__":
    fix_sequential_routing(sys.argv[1])
