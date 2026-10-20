#!/usr/bin/env python3
"""Thin native-KiCad adapter. Circuit and placement truth is design.json.
Run with KiCad's bundled Python. No inference of connectivity or electrical rules.
"""
from __future__ import annotations
import json
import re
import shutil
import uuid
from pathlib import Path
import pcbnew as k
# KiCad sorts serialized items by UUID. Seed native generation before loading
# footprints so serialization order and the subsequent UUIDv5 rewrite are stable.
k.KIID.SeedGenerator(60029)
ROOT = Path(__file__).resolve().parent
DATA = json.loads((ROOT / 'design.json').read_text())
PARTS = DATA['parts']
LIBS = Path('/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints')
LOCAL = ROOT / 'LCR.pretty'
LOCAL.mkdir(exist_ok=True)
NS = uuid.UUID('fe873b1d-6907-478a-9001-08dfbf0e6385')
def uid(s: str) -> str:
    return str(uuid.uuid5(NS, s))
def q(s: str) -> str:
    return json.dumps(s)
def mm(x: float) -> int:
    return k.FromMM(x)
def pos(x: float, y: float) -> k.VECTOR2I:
    return k.VECTOR2I(mm(x), mm(y))
def pinout(p: dict) -> dict:
    if p['kind'] in ['R','C','H']:
        return {'1': ['1','passive'], '2': ['2','passive']}
    return DATA['pinouts'][p['kind']]
def local_fp(p: dict) -> str:
    return 'LCR:' + p['footprint'].split(':')[1]
# Project-local footprints: reference unmodified official library land patterns.
for p in PARTS:
    lib, name = p['footprint'].split(':')
    if lib != 'LCR':
        shutil.copyfile(LIBS / (lib + '.pretty') / (name + '.kicad_mod'), LOCAL / (name + '.kicad_mod'))
(ROOT / 'fp-lib-table').write_text('(fp_lib_table (version 7) (lib (name "LCR") (type "KiCad") (uri "${KIPRJMOD}/LCR.pretty") (options "") (descr "Vendored KiCad 10 footprints")))\n')
# Adapt USB mechanical slots and signal lands to verified HRO 2020 drawing.
usb_path=LOCAL/'USB_C_Receptacle_HRO_TYPE-C-31-M-12.kicad_mod'
usb_text=usb_path.read_text().replace('(drill oval 0.6 1.2)', '(drill oval 0.6 1.4)')
usb_text=usb_text.replace('(size 0.65 0.65)', '(size 0.6 0.6)').replace('(drill 0.65)', '(drill 0.6)')
usb_text=usb_text.replace('(size 1 1.6)', '(size 1 1.8)')
usb_text=usb_text.replace(' -4.045)', ' -3.67)').replace(' 1.45)', ' 1.14)')
usb_text=usb_text.replace('(at -3.25 ', '(at -3.2 ').replace('(at 3.25 ', '(at 3.2 ')
usb_text=usb_text.replace('(at -2.45 ', '(at -2.4 ').replace('(at 2.45 ', '(at 2.4 ')
usb_text=usb_text.replace('(at -4.32 -3.13)', '(at -4.325 -3.1)').replace('(at 4.32 -3.13)', '(at 4.325 -3.1)')
usb_text=usb_text.replace('(at -4.32 1.05)', '(at -4.325 1.08)').replace('(at 4.32 1.05)', '(at 4.325 1.08)')
usb_text=usb_text.replace('(layer "F.SilkS")', '(layer "F.Fab")')
usb_path.write_text(usb_text)
# The oscillator land pattern uses manufacturer drawing 1=EN,2=GND,3=OUT,4=VDD.
(LOCAL / 'Oscillator_3225.kicad_mod').write_text('''(footprint "Oscillator_3225" (version 20241229) (generator "pcbnew") (layer "F.Cu") (attr smd)
(property "Reference" "Y?" (at 0 -2.3) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))
(property "Value" "16MHz" (at 0 2.3) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))
(fp_rect (start -1.6 -1.25) (end 1.6 1.25) (stroke (width 0.1) (type default)) (fill none) (layer "F.Fab"))
(fp_rect (start -2.05 -1.7) (end 2.05 1.7) (stroke (width 0.05) (type default)) (fill none) (layer "F.CrtYd"))
(pad "1" smd rect (at -1.1 0.85) (size 1.4 1.2) (layers "F.Cu" "F.Paste" "F.Mask"))
(pad "2" smd rect (at 1.1 0.85) (size 1.4 1.2) (layers "F.Cu" "F.Paste" "F.Mask"))
(pad "3" smd rect (at 1.1 -0.85) (size 1.4 1.2) (layers "F.Cu" "F.Paste" "F.Mask"))
(pad "4" smd rect (at -1.1 -0.85) (size 1.4 1.2) (layers "F.Cu" "F.Paste" "F.Mask")))\n''')
# Schematic symbols and instances. All pin names/types are explicit in design.json.
FX = '(effects (font (size 1.27 1.27)))'
rootid = uid('schematic')
symbols = []
geometry = {}
for kind in sorted({p['kind'] for p in PARTS}):
    p = next(p for p in PARTS if p['kind'] == kind)
    po = pinout(p)
    pins = list(po)
    coords = {}
    if kind in ['R','C','H']:
        half_w, half_h = 2.54, 2.54
        coords = {'1': (-7.62,0,0), '2':(7.62,0,180)}
    else:
        half_w = 12.7
        n = (len(pins)+1)//2
        half_h = max(5.08,(n+1)*1.27)
        for i, pn in enumerate(pins):
            left = i < n
            index = i if left else i-n
            coords[pn] = (-15.24 if left else 15.24, (n-1)*1.27-index*2.54, 0 if left else 180)
    body = f'(rectangle (start {-half_w} {-half_h}) (end {half_w} {half_h}) (stroke (width 0.254) (type default)) (fill (type background)))'
    if kind == 'C':
        body = '(polyline (pts (xy -0.76 -2.54) (xy -0.76 2.54)) (stroke (width 0.254) (type default)) (fill (type none))) (polyline (pts (xy 0.76 -2.54) (xy 0.76 2.54)) (stroke (width 0.254) (type default)) (fill (type none)))'
    pins_text = []
    for pn,(x,y,a) in coords.items():
        name,typ = po[pn]
        length = 6.86 if kind == 'C' else 5.08 if kind in ['R','H'] else 2.54
        pins_text.append(f'(pin {typ} line (at {x} {y} {a}) (length {length}) (name {q(name)} {FX}) (number {q(pn)} {FX}))')
    name = 'LCR:'+kind
    s = f'(symbol {q(name)} (pin_names (offset 0.508)) (in_bom yes) (on_board yes) (property "Reference" "U" (at 0 {half_h+2.54} 0) {FX}) (property "Value" {q(kind)} (at 0 {-half_h-2.54} 0) {FX}) (symbol {q(kind+"_0_1")} {body}) (symbol {q(kind+"_1_1")} {" ".join(pins_text)}))'
    symbols.append(s)
    geometry[kind]=(coords,half_h)
symbols.append('(symbol "LCR:PWR_FLAG" (power) (pin_names (offset 0)) (in_bom no) (on_board no) (property "Reference" "#FLG" (at 0 0 0) (effects (font (size 1.27 1.27)) hide)) (property "Value" "PWR_FLAG" (at 0 3.81 0) (effects (font (size 1.27 1.27)))) (symbol "PWR_FLAG_0_1" (polyline (pts (xy 0 0) (xy 0 1.27) (xy -1.27 2.54) (xy 1.27 2.54) (xy 0 1.27)) (stroke (width 0) (type default)) (fill (type none)))) (symbol "PWR_FLAG_1_1" (pin power_out line (at 0 0 90) (length 0) (name "pwr" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))))')
(ROOT/'LCR.kicad_sym').write_text('(kicad_symbol_lib (version 20241209) (generator "lcr_adapter")\n'+'\n'.join(s.replace('(symbol "LCR:', '(symbol "') for s in symbols)+')\n')
(ROOT/'sym-lib-table').write_text('(sym_lib_table (version 7) (lib (name "LCR") (type "KiCad") (uri "${KIPRJMOD}/LCR.kicad_sym") (options "") (descr "Explicit datasheet pin definitions")))\n')
# A2 page with five named blocks and explicit component locations.
layout={
'J1':(60,62),'U1':(140,62),'D1':(60,115),'R1':(40,150),'R2':(95,150),'R3':(150,150),'C5':(130,106),'C6':(130,126),
'U4':(238,62),'U5':(318,62),'C1':(225,110),'C2':(285,110),'C3':(225,140),'C4':(285,140),'R4':(335,140),'J3':(335,110),
'U2':(435,64),'Y1':(520,64),'R5':(420,110),'R6':(490,110),'R7':(555,110),'R13':(420,140),'R14':(490,140),'C7':(410,165),'C8':(460,165),'C9':(510,165),'C10':(560,165),
'U3':(90,250),'J2':(250,250),'R8':(155,220),'R9':(220,220),'R10':(155,285),'R11':(220,285),'R12':(160,250),'R15':(240,320),'C11':(70,310),'C12':(155,320),'C13':(65,350),'C14':(240,350)}
for i in range(4):
    x=370+i*58
    layout['R'+str(16+i)]=(x,235)
    layout['C'+str(15+i)]=(x,280)
    layout['JP'+str(i+1)]=(x,325)
chunks=[f'(kicad_sch (version 20250114) (generator "lcr_adapter") (uuid "{rootid}") (paper "A2") (title_block (title "Temper USB LCR bench meter") (date "2026-10-20") (rev "A") (company "Temper") (comment 1 "Engineering prototype. Isolated, discharged DUT only.")) (lib_symbols {" ".join(symbols)})']
for title,xy,wh in [('USB / factory HID bridge',(20,25),(160,155)),('Power / USB suspend control',(195,25),(175,155)),('Coherent converter / clock',(385,25),(195,155)),('Buffered source / transimpedance',(20,195),(290,185)),('Select exactly ONE feedback jumper',(335,195),(245,185))]:
    x,y=xy;w,h=wh
    chunks.append(f'(rectangle (start {x} {y}) (end {x+w} {y+h}) (stroke (width 0.254) (type default) (color 70 100 140 1)) (fill (type none)) (uuid "{uid(title)}"))')
    chunks.append(f'(text {q(title)} (at {x+5} {y+7} 0) (effects (font (size 2 2) (bold yes)) (justify left)) (uuid "{uid(title+"text")}"))')
for p in PARTS:
    ref=p['ref']; x,y=(round(v/1.27)*1.27 for v in layout[ref]); coords,hh=geometry[p['kind']];id=uid(ref)
    props={'Reference':ref,'Value':p['value'],'Footprint':local_fp(p),'MPN':p['mpn'],'Manufacturer':p['manufacturer'],'LCSC':p['lcsc'],'Unit_USD':str(p['unit_usd']),'Assembly':p['assembly']}
    proptext=[]
    for name,val in props.items():
        yy=y-hh-3.81 if name=='Reference' else y+hh+3.81 if name=='Value' else y
        hidden='' if name in ['Reference','Value'] else ' hide'
        proptext.append(f'(property {q(name)} {q(val)} (at {x} {yy} 0) (effects (font (size 1.27 1.27)){hidden}))')
    pintext=' '.join(f'(pin {q(pn)} (uuid "{uid(ref+"pin"+pn)}"))' for pn in coords)
    chunks.append(f'(symbol (lib_id "LCR:{p["kind"]}") (at {x} {y} 0) (unit 1) (in_bom yes) (on_board yes) (dnp no) (uuid "{id}") {" ".join(proptext)} {pintext} (instances (project "temper-lcr" (path "/{rootid}" (reference "{ref}") (unit 1)))))')
    for pn,(dx,dy,a) in coords.items():
        px,py=round(x+dx,4),round(y-dy,4);net=p['pins'][pn]
        if net is None:
            chunks.append(f'(no_connect (at {px} {py}) (uuid "{uid(ref+pn+"nc")}"))')
        else:
            ex=px-3.81 if dx<0 else px+3.81
            chunks.append(f'(wire (pts (xy {px} {py}) (xy {ex} {py})) (stroke (width 0) (type default)) (uuid "{uid(ref+pn+"wire")}"))')
            justify='right bottom' if dx<0 else 'left bottom'
            chunks.append(f'(label {q(net)} (at {ex} {py} 0) (effects (font (size 1.27 1.27)) (justify {justify})) (uuid "{uid(ref+pn+"label")}"))')
for i,net in enumerate(['GND','VBUS'],1):
    x,y=round((220+i*50)/1.27)*1.27,165.1
    ref=f'#FLG0{i}'
    chunks.append(f'(symbol (lib_id "LCR:PWR_FLAG") (at {x} {y} 0) (unit 1) (in_bom no) (on_board no) (dnp no) (uuid "{uid(ref)}") (property "Reference" "{ref}" (at {x} {y} 0) (effects (font (size 1.27 1.27)) hide)) (property "Value" "PWR_FLAG" (at {x} {y-3.81} 0) {FX}) (pin "1" (uuid "{uid(ref+"pin")}")) (instances (project "temper-lcr" (path "/{rootid}" (reference "{ref}") (unit 1)))))')
    chunks.append(f'(label "{net}" (at {x} {y} 0) (effects (font (size 1.27 1.27)) (justify left bottom)) (uuid "{uid(ref+"label")}"))')
chunks.append('(embedded_fonts no))')
(ROOT/'temper-lcr.kicad_sch').write_text('\n'.join(chunks)+'\n')
# pcbnew provides footprint geometry, rotation and pad placement.
b=k.BOARD();b.SetCopperLayerCount(4)
settings=b.GetDesignSettings();settings.SetAuxOrigin(pos(50,115));settings.m_SolderMaskMargin=mm(0.05)
settings.m_MinClearance=mm(0.15);settings.m_TrackMinWidth=mm(0.15);settings.m_ViasMinSize=mm(0.45);settings.m_MinThroughDrill=mm(0.2)
nets={}
for n in sorted({n for p in PARTS for n in p['pins'].values() if n is not None}):
    net=k.NETINFO_ITEM(b,'/'+n);b.Add(net);nets[n]=net
fps={}
for p in PARTS:
    ref=p['ref'];name=local_fp(p).split(':')[1]
    f=k.FootprintLoad(str(LOCAL),name);f.SetReference(ref);f.SetValue(p['value']);f.SetFPID(k.LIB_ID('LCR',name));f.SetPosition(pos(*p['pcb'][:2]));f.SetOrientationDegrees(p['pcb'][2])
    path=k.KIID_PATH();path.push_back(k.KIID(rootid));path.push_back(k.KIID(uid(ref)));f.SetPath(path)
    f.Reference().SetTextSize(pos(.8,.8));f.Reference().SetTextThickness(mm(.12))
    if p['kind'] in ['R','C']:
        f.Reference().SetLayer(k.F_Fab)
    if ref=='U1':
        f.Reference().SetPosition(pos(70,67))
    for name,value in {'MPN':p['mpn'],'Manufacturer':p['manufacturer'],'LCSC':p['lcsc'],'Unit_USD':str(p['unit_usd']),'Assembly':p['assembly']}.items():
        f.SetField(name,value)
        f.GetField(name).SetVisible(False)
    actual={pad.GetNumber() for pad in f.Pads() if pad.GetNumber()}
    if actual != set(p['pins']):
        raise ValueError(f"{ref}: footprint pins {actual} differ from source pins {set(p['pins'])}")
    for pad in f.Pads():
        num=pad.GetNumber()
        if num and num in p['pins']:
            if p['pins'][num] is not None:
                pad.SetNet(nets[p['pins'][num]])
            else:
                name=f"unconnected-({ref}-{pinout(p)[num][0]}-Pad{num})"
                net=k.NETINFO_ITEM(b,name);b.Add(net);pad.SetNet(net)
    b.Add(f);fps[ref]=f
# Board edge, mechanical fixing holes and clear labels.
for a,c in [((50,50),(130,50)),((130,50),(130,115)),((130,115),(50,115)),((50,115),(50,50))]:
    s=k.PCB_SHAPE();s.SetShape(k.SHAPE_T_SEGMENT);s.SetStart(pos(*a));s.SetEnd(pos(*c));s.SetLayer(k.Edge_Cuts);s.SetWidth(mm(.05));b.Add(s)
for i,(x,y) in enumerate([(54,68),(126,54),(54,111),(126,111)],1):
    f=k.FootprintLoad(str(LIBS/'MountingHole.pretty'),'MountingHole_3.2mm_M3');f.SetReference('H'+str(i));f.SetPosition(pos(x,y));f.Reference().SetLayer(k.F_Fab);f.SetAttributes(k.FP_EXCLUDE_FROM_BOM|k.FP_EXCLUDE_FROM_POS_FILES|k.FP_BOARD_ONLY);b.Add(f)
for text,x,y,size in [('TEMPER LCR / REV A',91,54,1.5),('USB POWER / PC CONTROL',82,57,1),('DISCHARGE DUT FIRST',109,71,1),('HI',124,78,1),('LO',124,80.54,1),('20R   200R   2kR   20kR',111,109,1),('ONE RANGE JUMPER ONLY',107,112,1),('USB GND REFERENCED',70,104,1),('5R MIN / NO LIVE DUT',70,107,1)]:
    t=k.PCB_TEXT(b);t.SetText(text);t.SetPosition(pos(x,y));t.SetTextSize(pos(size,size));t.SetTextThickness(mm(.15));t.SetLayer(k.F_SilkS);b.Add(t)
# Explicit human-authored track list. All segments are in board millimetres.
routing=ROOT/'routing.json'
if routing.exists():
    rt=json.loads(routing.read_text())
    for via in rt.get('vias',[]):
        v=k.PCB_VIA(b);v.SetPosition(pos(*via['at']));v.SetWidth(mm(via.get('diameter',.6)));v.SetDrill(mm(via.get('drill',.3)));v.SetViaType(k.VIATYPE_THROUGH);v.SetLayerPair(k.F_Cu,k.B_Cu);v.SetNet(nets[via['net']]);b.Add(v)
    for route in rt.get('tracks',[]):
        layer={'F.Cu':k.F_Cu,'B.Cu':k.B_Cu,'In1.Cu':k.In1_Cu,'In2.Cu':k.In2_Cu}[route['layer']]
        points=[]
        for pt in route['points']:
            if isinstance(pt,str):
                ref,pn=pt.split('.');pad=next(z for z in fps[ref].Pads() if z.GetNumber()==pn);points.append(pad.GetPosition())
            else:points.append(pos(*pt))
        for a,c in zip(points,points[1:]):
            t=k.PCB_TRACK(b);t.SetStart(a);t.SetEnd(c);t.SetWidth(mm(route.get('width',.2)));t.SetLayer(layer);t.SetNet(nets[route['net']]);b.Add(t)
    for zn in rt.get('zones',[]):
        z=k.ZONE(b);z.SetLayer({'In1.Cu':k.In1_Cu,'In2.Cu':k.In2_Cu,'B.Cu':k.B_Cu}[zn['layer']]);z.SetNet(nets[zn['net']]);z.SetLocalClearance(mm(.2));z.SetPadConnection(k.ZONE_CONNECTION_FULL);z.SetThermalReliefGap(mm(.25));z.SetThermalReliefSpokeWidth(mm(.3));z.Outline().NewOutline()
        for x,y in zn['points']:z.Outline().Append(mm(x),mm(y))
        b.Add(z)
    # Native CLI --refill-zones performs filling in its initialized KiCad context.
k.SaveBoard(str(ROOT/'temper-lcr.kicad_pcb'),b)
board_path=ROOT/'temper-lcr.kicad_pcb'
item_index=iter(range(100000))
board_path.write_text(re.sub(r'\(uuid "[^"]+"\)',lambda _:f'(uuid "{uid("pcb-item-"+str(next(item_index)))}")',board_path.read_text()))
# Project settings carry explicit common fabrication minima.
pro={'meta':{'filename':'temper-lcr.kicad_pro','version':1},'board':{'design_settings':{'rules':{'min_clearance':.15,'min_track_width':.15,'min_via_diameter':.45,'min_through_hole_diameter':.2,'min_copper_edge_clearance':.3,'min_hole_clearance':.2,'min_hole_to_hole':.25,'min_silk_clearance':.1,'min_text_height':.8,'min_text_thickness':.12},'defaults':{'copper_line_width':.2},'rule_severities':{}},'layer_presets':[]},'net_settings':{'classes':[{'name':'Default','clearance':.15,'track_width':.2,'via_diameter':.6,'via_drill':.3,'microvia_diameter':.3,'microvia_drill':.1,'diff_pair_width':.2,'diff_pair_gap':.2,'diff_pair_via_gap':.25}], 'meta':{'version':3}},'erc':{'erc_exclusions':[],'meta':{'version':0},'pin_map':[],'rule_severities':{}},'schematic':{'drawing':{'default_text_size':50}}}
(ROOT/'temper-lcr.kicad_pro').write_text(json.dumps(pro,indent=2)+'\n')
# Native pad coordinates are the routing oracle; avoid hand-written rotation math.
out={p['ref']:{pad.GetNumber():[k.ToMM(pad.GetPosition().x),k.ToMM(pad.GetPosition().y),pad.GetNetname()] for pad in fps[p['ref']].Pads() if pad.GetNumber()} for p in PARTS}
(ROOT.parent/'build'/'pad-coordinates.json').write_text(json.dumps(out,indent=2)+'\n')
print(f'Wrote schematic and PCB: {len(PARTS)} components, {len(nets)} nets')
