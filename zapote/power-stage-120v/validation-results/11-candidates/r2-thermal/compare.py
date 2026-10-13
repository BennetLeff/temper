import json,sys
from pathlib import Path
R=Path(__file__).resolve().parent/"runs"
names=sys.argv[1:]
refs=["L1","C5","C6","PS1","PS2","R5","C38","C39","C40","C41","C21","U41","U42","U26"]
runs={n:json.loads((R/f"{n}.json").read_text()) for n in names}
print("%-22s"%"run", "peak", "block1mm", "fetrow", *refs)
for n,r in runs.items():
    pr={p['ref']:p for p in r['parts']}
    def f(ref):
        p=pr.get(ref)
        if not p: return "  -  "
        return "%5.1f/%5.1f"%(p.get('tj_c',float('nan')),p['pad_max_cell_c'])
    b=r.get('peak_1mm_block') or {}
    print("%-22s"%n, "%.1f"%r['peak']['temperature_c'], "%.1f"%b.get('temperature_c',0), "%.1f"%(r['fet_row_max_c'] or 0), *[f(x) for x in refs])
