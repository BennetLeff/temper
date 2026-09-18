"""Emit a readable, source-bound power-entry schematic and local symbol table."""
import argparse, hashlib, json, sys
from pathlib import Path

LIBRARY = "PowerEntryActiveUnit"
PIN_NAMES = {"U1":{"1":"L","2":"VCCHL","3":"GATEHL","4":"HVS_NC","5":"GATELL","6":"VCC","7":"RECT_GND","8":"COMP_POL","9":"COMP_NC","10":"GATELR","11":"HVS_NC","12":"R","13":"VCCHR","14":"GATEHR","15":"HVS_NC","16":"VR"},"U11":{"1":"HOT_GND","2":"ICOMP","3":"ISENSE","4":"FREQ","5":"VCOMP","6":"VSENSE","7":"VCC","8":"GATE"},"U9":{"1":"G","2":"D","3":"S"},"U10":{"1":"A1","2":"K","3":"A2"}}

def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def main(repo, source, output, receipt):
    sys.path.insert(0, str(repo / "scripts"))
    import gen_schematics as g
    net = g.parse_netlist(source / "build/default.net")
    g.apply_bom_values(net, g.load_bom_values(source / "build/default.csv"))
    comps = sorted(net.components.values(), key=lambda c: c.ref)
    manifest=json.loads((output/"source-manifest.json").read_text())
    values={c["reference"]:c.get("value") or c["mpn"] for c in manifest["components"]}
    for c in comps: c.display_value=values[c.ref]
    parts = {c.part_name: net.libparts[c.part_name] for c in comps}
    symbols = {}
    for c in comps:
        if c.part_name in symbols: continue
        s = g.synthesize_symbol(parts[c.part_name])
        for pin, name in PIN_NAMES.get(c.ref, {"1":"G","2":"D","3":"S"} if c.ref in ["U55","U56","U57","U58"] else {}).items():
            s = s.replace(f'(name "{pin}"', f'(name "{name}"')
        sid = g._sanitize_name(c.part_name)
        symbols[c.part_name] = s
    d = [g._schematic_header("Active rectifier / fused bank - unqualified prototype", g.ROOT_UUID).replace("2026-07-15", "2026-09-12").replace('(paper "A3")','(paper "A1")'), "(lib_symbols"]
    for part_name, symbol in symbols.items():
        sid = g._sanitize_name(part_name)
        d.append(symbol.replace(f'(symbol "{sid}"', f'(symbol "{LIBRARY}:{sid}"', 1))
    d.append(")")
    def note(t,x,y,size=1.27): return f'(text "{t}" (at {x} {y} 0) (effects (font (size {size} {size})) (justify left)) (uuid "{g._uuid_from_seed(t)}"))'
    d += [note("1800 W nominal AC input / 120 VAC / external 15 A RMS foldback required", 30.48, 15.24, 2.0), note("ALL control, permit and auxiliary headers are HOT bus-minus referenced",30.48,22.86,2.0),note("UNQUALIFIED PROTOTYPE - external isolated bias and precharge supervisor required",30.48,30.48,2.0)]
    pin_net = {(r,p): n.name for n in net.nets.values() for r,p in n.nodes}
    singles = {(r,p) for n in net.nets.values() if len(n.nodes)==1 for r,p in n.nodes}
    for idx,c in enumerate(comps):
        x = 54.61 + (idx % 9) * 86.36
        y = [124.46, 243.84, 294.64, 345.44, 396.24, 447.04, 497.84, 548.64][idx // 9]
        part = parts[c.part_name]; sid = LIBRARY+":"+g._sanitize_name(c.part_name)
        inst = g._symbol_instance(c.ref,sid,x,y,c.footprint,c.part_name,g._uuid_from_seed(f"flatinst:{c.tstamp}"),libpart=part,display_value=c.display_value)
        instance=next(v["instance_path"] for v in manifest["bridge"]["components"] if v["reference"]==c.ref)
        attrs=manifest["source_attributes"][instance]
        fields={"SourceInstance":instance,"MPN":attrs["mpn"],"Datasheet":attrs.get("datasheet","")}
        extra="".join(f'\n    (property "{key}" {json.dumps(value)} (at {x:.2f} {y:.2f} 0) (effects (font (size 1.27 1.27)) hide))' for key,value in fields.items())
        inst=inst.rsplit(")",1)[0]+extra+"\n)"
        d.append(inst)
        for num,_ in part.pins:
            px,py=g._pin_absolute_position(part,num,x,y)
            n=pin_net.get((c.ref,num))
            if n and (c.ref,num) not in singles:
                label=g._global_label(n,px,py,g._uuid_from_seed(f"label:{c.ref}:{num}:{n}"))
                if px < x: label=label.replace(f"(at {px:.2f} {py:.2f} 0)",f"(at {px:.2f} {py:.2f} 180)").replace("(justify left bottom)","(justify right bottom)")
                d.append(label)
            if n is None or (c.ref,num) in singles: d.append(g._no_connect(px,py,g._uuid_from_seed(f"nc:{c.ref}:{num}")))
    d.append(")")
    output.mkdir(parents=True,exist_ok=True)
    sch=output/"section.kicad_sch"; lib=output/"power-entry-unit.kicad_sym"; table=output/"sym-lib-table"
    sch.write_text("\n".join(d)+"\n")
    lib.write_text('(kicad_symbol_lib (version 20231120) (generator "zapote_power_entry")\n'+"\n".join(symbols.values())+'\n)\n')
    # Keep the table portable when the native candidate is copied into the
    # coordinator's project.  KiCad expands KIPRJMOD relative to the project
    # containing section.kicad_sch; absolute worktree paths would silently
    # bind a copied schematic to this checkout.
    table.write_text('(sym_lib_table (version 7)\n  (lib (name "PowerEntryActiveUnit") (type "KiCad") (uri "${KIPRJMOD}/power-entry-unit.kicad_sym") (options "") (descr "Source-derived power-entry symbols"))\n)\n')
    rec={"status":"emitted-native-verification-required","source_netlist_sha256":digest(source/"build/default.net"),"source_bom_sha256":digest(source/"build/default.csv"),"helper_sha256":digest(Path(__file__)),"outputs":{p.name:digest(p) for p in (sch,lib,table)},"component_count":len(comps),"native_erc":"NOT RUN","pcb_touched":False}
    receipt.write_text(json.dumps(rec,indent=2)+"\n")

if __name__ == "__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--repo",type=Path,required=True); ap.add_argument("--source",type=Path,required=True); ap.add_argument("--output",type=Path,required=True); ap.add_argument("--receipt",type=Path,required=True); a=ap.parse_args(); main(a.repo.resolve(),a.source.resolve(),a.output.resolve(),a.receipt.resolve())
