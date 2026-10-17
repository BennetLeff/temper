"""Read-only parse of native-21/section.kicad_pcb -> {ref: {"nets": set, "fp": str}}; and parts/group map."""
import re, sys, json
sys.dont_write_bytecode = True
from pathlib import Path
PS = Path(__file__).resolve().parents[4]
N21 = PS/"native-21"
def footprints():
    t = (N21/"section.kicad_pcb").read_text()
    out = {}
    for blk in re.split(r"\n\t\(footprint ", t)[1:]:
        blk = blk.split("\n\t(", 1)[0] if False else blk
        m = re.search(r'\(property "Reference" "([^"]+)"', blk)
        if not m: continue
        ref = m.group(1)
        end = blk.find("\n\t(gr_") if False else len(blk)
        nets = set(re.findall(r'\(pad "[^"]*"[^\n]*\n(?:[^\n]*\n){0,12}?\s*\(net "([^"]+)"\)', blk))
        nets |= set(re.findall(r'\(net "([^"]+)"\)', blk))
        pads = re.findall(r'\(pad "[^"]*" (smd|thru_hole|np_thru_hole|connect)', blk)
        out[ref] = dict(fp=blk.split('"')[1], nets=nets, smd=pads.count("smd"), tht=pads.count("thru_hole"))
    return out
def parts():
    return {p["ref"]: p for p in json.load(open(N21/"layout/parts.json"))}
def placement():
    return json.load(open(N21/"placement.json"))
if __name__ == "__main__":
    f = footprints(); p = parts()
    print(len(f), len(p), set(p)-set(f), len(set(f)-set(p)))
    for r in ("J4","J3","J11","T1","U36","R38","J6","R5","U1"): print(r, sorted(f[r]["nets"]))
