import re
import sys

def identify_unrouted(dsn_path, ses_path):
    # 1. Get all nets from DSN
    with open(dsn_path, 'r') as f:
        dsn_content = f.read()
    
    # Matches (net NAME ...)
    # But excludes (net "GND" ...) if it's a supply net sometimes handled differently?
    # DSN format: (network (net NAME ...))
    
    all_nets = set()
    for match in re.finditer(r'\(net \"?([^\s\"\)]+)\"?', dsn_content):
        net_name = match.group(1)
        # Filter out common DSN keywords if regex is too loose
        if net_name not in ['Pins', 'Order', 'Clearance']:
            all_nets.add(net_name)
            
    print(f"DSN Nets: {len(all_nets)}")
    
    # 2. Get routed nets from SES
    with open(ses_path, 'r') as f:
        ses_content = f.read()
        
    routed_nets = set()
    # SES format: (net NAME (wire ...))
    for match in re.finditer(r'\(net \"?([^\s\"\)]+)\"?', ses_content):
        net_name = match.group(1)
        routed_nets.add(net_name)
        
    print(f"Routed Nets: {len(routed_nets)}")
    
    # 3. Compare
    unrouted = all_nets - routed_nets
    
    # Some nets might be in SES but empty?
    # Let's check for "incomplete" in SES log or comments? No.
    
    # Actually, SES contains all nets usually. We need to check if they have wires.
    # But FreeRouting often omits completely unrouted nets or leaves them with just pins?
    
    print("\nPotentially Unrouted Nets (Missing from SES):")
    print(unrouted)
    
    # If set is empty, maybe they are in SES but incomplete.
    # FreeRouter usually reports "incomplete" count.
    
identify_unrouted("pcb/temper_autoroute.dsn", "pcb/temper_autoroute.ses")
