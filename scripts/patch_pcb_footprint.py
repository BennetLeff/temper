import re
import sys


def patch_pcb():
    pcb_path = "pcb/temper.kicad_pcb"
    output_path = "pcb/temper_fixed.kicad_pcb"

    print(f"Reading {pcb_path}...")
    with open(pcb_path, "r") as f:
        content = f.read()

    # 1. Locate U_MCU block
    # We look for the footprint definition
    start_marker = '(footprint "Package_DFN_QFN:QFN-56-1EP_7x7mm_P0.4mm_EP5.6x5.6mm"'
    start_idx = content.find(start_marker)

    if start_idx == -1:
        print("Error: U_MCU footprint not found!")
        sys.exit(1)

    # Find the end of this footprint block
    # It ends with a closing parenthesis that matches the opening one
    # We scan forward counting parens
    balance = 0
    end_idx = -1
    for i in range(start_idx, len(content)):
        if content[i] == "(":
            balance += 1
        elif content[i] == ")":
            balance -= 1
            if balance == 0:
                end_idx = i + 1
                break

    if end_idx == -1:
        print("Error: Could not find end of U_MCU block")
        sys.exit(1)

    mcu_block = content[start_idx:end_idx]
    print(f"Found U_MCU block ({len(mcu_block)} chars)")

    # 2. Extract Nets from existing pads (to preserve connectivity)
    # Map pin_number -> net_id_string (e.g. "1" -> '1 "GND"')
    net_map = {}

    # We iterate lines to be robust against multi-line formatting
    lines = mcu_block.split("\n")
    current_pin = None

    for line in lines:
        s = line.strip()
        # Start of pad
        m_pad = re.search(r'\(pad\s+"([^"]+)"', s)
        if m_pad:
            current_pin = m_pad.group(1)
            continue

        # Net definition (inside pad)
        if current_pin and s.startswith("(net "):
            # Extract content inside (net ...)
            # e.g. (net 1 "GND") -> 1 "GND"
            # Use non-greedy match or exclude parens
            m_net = re.search(r"\(net\s+([^)]+)\)", s)
            if m_net:
                net_map[current_pin] = m_net.group(1)
                current_pin = None  # Reset

    print(f"Preserved {len(net_map)} net assignments from existing pads.")

    # 3. Remove ALL existing pads from the block
    # We use regex to remove (pad ...) blocks
    # Logic: Replace (pad ... <matching parens> ...) with empty string
    # This is hard with regex due to nested parens.
    # Alternative: Split block into lines, filter out lines starting with (pad, reconstruct.
    # But pads can be multi-line.

    # Better approach: Iterate lines. If line (stripped) starts with (pad, skip it AND its indented children.
    # KiCad formatting is usually consistent.

    lines = mcu_block.split("\n")
    new_lines = []
    skip_mode = False
    pad_indent = ""

    for line in lines:
        stripped = line.strip()
        if stripped.startswith('(pad "'):
            # Check if this is a one-line pad or multi-line
            balance = line.count("(") - line.count(")")
            if balance == 0:
                # One line pad, skip it
                continue
            else:
                # Multi-line pad, enter skip mode
                skip_mode = True
                pad_indent = line[: line.find("(")]  # Capture indentation
                continue

        if skip_mode:
            # Check if we closed the parens
            # This is risky if we have nested properties.
            # But standard KiCad pads are usually well structured.
            # Let's verify end of pad by indentation or paren count?
            # Safer: Count parens for the *entire block*? No.

            # Heuristic: If indentation returns to pad_indent level and starts with ')', it's the end?
            # Or just count parens on the skipped lines.
            balance += line.count("(") - line.count(")")
            if balance == 0:
                skip_mode = False
            continue

        new_lines.append(line)

    # 4. Insert NEW pads
    # We construct the pad strings using the data from the fetched file
    # And inject the preserved nets.

    # New pads data (from fetched file)
    # I'll embed the raw strings for simplicity, but injecting the net

    new_pads_template = [
        # Paste the fetched pads here, but replace newlines with proper indentation
    ]

    # ... (Pad definitions will be inserted here) ...

    # Wait, I need the actual pad definitions.
    # I will paste the fetched pads into a list of strings below.
    # And I need to handle the "net" property injection.

    pass

    # I'll create a separate file with the pad data to avoid a massive script here.

    # Import pad data
    try:
        from scripts.mcu_footprint_data import NEW_PADS
    except ImportError:
        # Fallback if run from root
        import sys

        sys.path.append(".")
        from scripts.mcu_footprint_data import NEW_PADS

    # Prepare new pad lines
    new_pad_lines = []

    # We need to inject (net X "Name") into the pads
    # NEW_PADS is a single string with many (pad ...) blocks
    # We split by (pad "

    # Simple regex based replacement
    # We iterate over the pad definitions in NEW_PADS
    # For each pad "N", look up net in net_map and insert it before the closing paren of the pad block

    pad_blocks = re.findall(r'(\(pad\s+"([^"]+)"[^)]+(?:\([^)]+\)[^)]*)*\))', NEW_PADS, re.DOTALL)

    # Wait, simple regex won't match nested parens correctly for the whole block.
    # But the structure is consistent: (pad "N" ... (layers ...) ... )

    # Let's just iterate lines of NEW_PADS
    raw_lines = NEW_PADS.strip().split("\n")

    processed_pads = []
    current_pad = []
    current_pin = None

    for line in raw_lines:
        sline = line.strip()
        if sline.startswith("(pad"):
            if current_pad:
                # Flush previous pad
                processed_pads.append((current_pin, current_pad))
            current_pad = [line]
            # Extract pin number
            m = re.search(r'\(pad\s+"([^"]+)"', sline)
            current_pin = m.group(1) if m else None
            # Check for thermal pad (pad "57") or paste pads (pad "")
            if not m and sline.startswith('(pad ""'):
                current_pin = ""
        else:
            if current_pad:
                current_pad.append(line)

    # Flush last
    if current_pad:
        processed_pads.append((current_pin, current_pad))

    # Construct final text
    final_pad_text = []

    for pin, lines in processed_pads:
        # Check if we have a net for this pin
        if pin and pin in net_map:
            net_def = net_map[pin]  # e.g. '1 "GND"'
            # Insert net definition before the last closing parenthesis of the BLOCK
            # The block might be multi-line. The last line has the closing paren?
            # Or the indentation logic handles it.

            # We assume the last line of 'lines' contains the closing paren for the pad.
            # We insert `(net {net_def})` before it?
            # KiCad format: (pad ... (net 1 "GND"))
            # Usually net is the last property.

            # Find the last closing paren in the last line?
            last_line = lines[-1]
            # Insert before the last char?
            # Actually, let's just append a new line with the net, indented.
            # But we need to be inside the pad block.

            # Check indentation of last line
            indent = ""
            m_ind = re.match(r"^(\s*)", lines[1] if len(lines) > 1 else lines[0])
            if m_ind:
                indent = m_ind.group(1)

            # Add net line
            net_line = f"{indent}\t(net {net_def})"

            # We need to insert it BEFORE the closing of the pad block.
            # The pad block structure in NEW_PADS seems to end with a closing paren on a separate line?
            # Looking at mcu_footprint_data.py:
            # (pad ...
            #     ...
            # )
            # Yes, the closing paren is on the last line, indented.

            # So we insert before the last line
            lines.insert(-1, net_line)

        # Add to output, ensuring indentation matches the PCB file
        # The PCB file seems to use 4 spaces or 2 spaces?
        # NEW_PADS uses tabs/spaces mix?
        # We'll just indent everything by 4 spaces (standard) relative to component?
        # mcu_block indentation seems to be 4 spaces.

        for l in lines:
            final_pad_text.append("    " + l.strip())  # Add base indent

    # 5. Reassemble the component block
    # Filter old lines to remove pads
    # (Already did this with new_lines in step 3 logic, but need to implement it properly)

    # Actually, let's restart step 3 with the buffer logic
    filtered_lines = []
    skip = False

    mcu_lines = mcu_block.split("\n")
    for line in mcu_lines:
        s = line.strip()
        if s.startswith('(pad "'):
            # Skip this pad block
            # We assume pads are indented.
            # If line ends with ), it's single line.
            if s.endswith(")") and s.count("(") == s.count(")"):
                continue
            skip = True
            continue

        if skip:
            # Check unindent or end of block?
            # Pads in KiCad are usually:
            # (pad ...
            #   ( ... )
            # )
            # If line starts with ) and matches indentation of (pad, we stop skipping?
            # Simpler: if line matches `    )` (indentation of pad block closing), stop skipping.
            # Or if line starts with `(pad`, we are in next pad (should have stopped skipping).
            # Or if line starts with `(model`, we are done with pads.

            if s.startswith("(pad") or s.startswith("(model") or s == ")":
                skip = False
                # Fall through to process this line (unless it's another pad)
                if s.startswith('(pad "'):
                    if s.endswith(")") and s.count("(") == s.count(")"):
                        continue
                    skip = True
                    continue
            else:
                continue

        filtered_lines.append(line)

    # Find insertion point for new pads (before (model ... or before closing paren)
    insert_idx = len(filtered_lines) - 1  # Default before last closing paren
    for i, line in enumerate(filtered_lines):
        if line.strip().startswith("(model"):
            insert_idx = i
            break

    # Insert new pads
    filtered_lines[insert_idx:insert_idx] = final_pad_text

    # Reassemble PCB
    new_mcu_block = "\n".join(filtered_lines)

    new_content = content[:start_idx] + new_mcu_block + content[end_idx:]

    print(f"Writing {output_path}...")
    with open(output_path, "w") as f:
        f.write(new_content)

    print("Done!")


if __name__ == "__main__":
    patch_pcb()
