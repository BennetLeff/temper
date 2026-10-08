"""Emit a readable, source-bound gate-drive schematic and local symbol table."""
import argparse, hashlib, json, sys
from pathlib import Path

LIBRARY = "GateDriveUnit"
PIN_NAMES = {
    "U1": {"1":"INA", "2":"INB", "3":"VCCI_1", "4":"GNDI", "5":"DIS", "6":"DT", "7":"NC_7", "8":"VCCI_2", "9":"VSSB", "10":"OUTB", "11":"VDDB", "14":"VSSA", "15":"OUTA", "16":"VDDA"},
    "Q1": {"1":"G", "2":"S", "3":"D"},
}

def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def main(repo, source, output, receipt):
    sys.path.insert(0, str(repo / "scripts"))
    import gen_schematics as g
    net = g.parse_netlist(source / "build/default.net")
    g.apply_bom_values(net, g.load_bom_values(source / "build/default.csv"))
    comps = sorted(net.components.values(), key=lambda c: c.ref)
    parts = {c.part_name: net.libparts[c.part_name] for c in comps}
    symbols = {}
    for c in comps:
        if c.part_name in symbols: continue
        s = g.synthesize_symbol(parts[c.part_name])
        for pin, name in PIN_NAMES.get(c.ref, {}).items():
            s = s.replace(f'(name "{pin}"', f'(name "{name}"')
        sid = g._sanitize_name(c.part_name)
        symbols[c.part_name] = s
    d = [g._schematic_header("Standalone Isolated Dual Gate Drive", g.ROOT_UUID).replace("2026-07-15", "2026-09-12"), "(lib_symbols"]
    for part_name, symbol in symbols.items():
        sid = g._sanitize_name(part_name)
        d.append(symbol.replace(f'(symbol "{sid}"', f'(symbol "{LIBRARY}:{sid}"', 1))
    d.append(")")
    def note(t,x,y,size=1.27): return f'(text "{t}" (at {x} {y} 0) (effects (font (size {size} {size})) (justify left)) (uuid "{g._uuid_from_seed(t)}"))'
    d += [note("CONTROL / J1: PWM_H, PWM_L, PERMIT, CTRL_GND", 30.48, 15.24, 1.8), note("ISOLATED LS SUPPLY / J2: +15V_LS, HV_RETURN", 30.48, 190.5, 1.8), note("GATE OUTPUTS / J3,J4: GATE + KELVIN RETURN", 30.48, 276.86, 1.8), note("Q1 AO3400A: PERMIT high pulls DIS low; floating PERMIT is disabled", 30.48, 289.56)]
    pin_net = {(r,p): n.name for n in net.nets.values() for r,p in n.nodes}
    singles = {(r,p) for n in net.nets.values() if len(n.nodes)==1 for r,p in n.nodes}
    for idx,c in enumerate(comps):
        x = 54.61 + (idx % 5) * 76.2
        y = 50.8 + (idx // 5) * 45.72
        part = parts[c.part_name]; sid = LIBRARY+":"+g._sanitize_name(c.part_name)
        d.append(g._symbol_instance(c.ref,sid,x,y,c.footprint,c.part_name,g._uuid_from_seed(f"flatinst:{c.tstamp}"),libpart=part,display_value=c.display_value))
        for num,_ in part.pins:
            px,py=g._pin_absolute_position(part,num,x,y)
            n=pin_net.get((c.ref,num))
            if n:
                label=g._global_label(n,px,py,g._uuid_from_seed(f"label:{c.ref}:{num}:{n}"))
                if px < x: label=label.replace(f"(at {px:.2f} {py:.2f} 0)",f"(at {px:.2f} {py:.2f} 180)").replace("(justify left bottom)","(justify right bottom)")
                d.append(label)
            if n is None or (c.ref,num) in singles: d.append(g._no_connect(px,py,g._uuid_from_seed(f"nc:{c.ref}:{num}")))
    d.append(")")
    output.mkdir(parents=True,exist_ok=True)
    sch=output/"section.kicad_sch"; lib=output/"gate-drive-unit.kicad_sym"; table=output/"sym-lib-table"
    sch.write_text("\n".join(d)+"\n")
    lib.write_text('(kicad_symbol_lib (version 20231120) (generator "zapote_gate_drive")\n'+"\n".join(symbols.values())+'\n)\n')
    # Keep the table portable when the native candidate is copied into the
    # coordinator's project.  KiCad expands KIPRJMOD relative to the project
    # containing section.kicad_sch; absolute worktree paths would silently
    # bind a copied schematic to this checkout.
    table.write_text('(sym_lib_table (version 7)\n  (lib (name "GateDriveUnit") (type "KiCad") (uri "${KIPRJMOD}/gate-drive-unit.kicad_sym") (options "") (descr "Source-derived gate-drive symbols"))\n)\n')
    rec={"status":"emitted-native-verification-required","source_netlist_sha256":digest(source/"build/default.net"),"source_bom_sha256":digest(source/"build/default.csv"),"helper_sha256":digest(Path(__file__)),"outputs":{p.name:digest(p) for p in (sch,lib,table)},"component_count":len(comps),"native_erc":"NOT RUN","pcb_touched":False}
    receipt.write_text(json.dumps(rec,indent=2)+"\n")

if __name__ == "__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--repo",type=Path,required=True); ap.add_argument("--source",type=Path,required=True); ap.add_argument("--output",type=Path,required=True); ap.add_argument("--receipt",type=Path,required=True); a=ap.parse_args(); main(a.repo.resolve(),a.source.resolve(),a.output.resolve(),a.receipt.resolve())
