
import sys
import re

def fix_pcb(path):
    print(f"Fixing {path}...")
    with open(path, 'r') as f:
        content = f.read()
        
    # 1. Upgrade version to KiCad 9
    content = content.replace("(version 20211014)", "(version 20241229)")
    
    # 2. Convert (tstamp <uuid>) to (uuid "<uuid>")
    # KiCad 9 expects (uuid "...") with quotes.
    # kiutils outputs (tstamp <uuid>) without quotes.
    tstamp_pattern = re.compile(r"\(tstamp ([0-9a-fA-F-]+)\)")
    content = tstamp_pattern.sub(r'(uuid "\1")', content)
    
    # 3. Fix malformed drill offsets: (drill ['offset', -0.9, 0] (offset -0.9 0))
    # We want: (drill (offset -0.9 0))
    drill_pattern = re.compile(r"\(drill \['offset'[^]]+\] ")
    content = drill_pattern.sub("(drill ", content)
    
    # 4. Fix zone connect_pads syntax if needed
    # (connect_pads (clearance 0.2)) -> (connect_pads yes (clearance 0.2))
    # content = content.replace("(connect_pads (clearance", "(connect_pads yes (clearance")

    with open(path, 'w') as f:
        f.write(content)
    print("PCB fixed for KiCad 9 compatibility.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        fix_pcb(sys.argv[1])
    else:
        print("Usage: python fix_pcb.py <file>")
