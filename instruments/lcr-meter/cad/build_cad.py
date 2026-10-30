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
# Board-level geometry. Rev E's design.json carries none of these keys, so the defaults below are the
# Rev E values and its build is unchanged; Rev F (cad/tools/rev_f.py) writes its own.
BOARD = DATA.get('board', {})
OUTLINE = BOARD.get('outline', [50, 45, 190, 150])          # x0, y0, x1, y1 (mm)
HOLES = BOARD.get('holes', [[54, 54], [186, 54], [54, 146], [186, 146]])
REF_TEXT = BOARD.get('ref_text', {'U13': [80, 135], 'U7': [170.2, 105.6], 'U14': [141, 104.2], 'U16': [58.3, 121.0]})
SILK = BOARD.get('silk', [['TEMPER LCR / REV E / TIDA-060029 + TAC5112',79,47.6,1.2],['USB-C 5V + DATA',62,64,1],['DISCHARGED DUT ONLY',79,50.4,1],['HCUR',108,58.6,1],['HPOT',130,58.6,1],['LPOT',152,58.6,1],['LCUR',174,58.6,1],['K4 REF',182,70,.8],['K2 5k',152.5,128,.8],['K1 100R',167.5,128,.8],['K3 100k',182.3,128,.8],['BOOTSEL',60,84,.8],['RESET',60,95,.8],['J4 CLK/DIO',64,105,.8],['J5 GND/3V3',60,115,.8],['J6 TX/RX',77,111,.8],['USB GND REFERENCED',111,147,1]])
LIBS = Path('/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints')
LOCAL = ROOT / 'LCR.pretty'
LOCAL.mkdir(exist_ok=True)
NS = uuid.UUID('fe873b1d-6907-478a-9001-08dfbf0e6385')
def uid(s: str) -> str:
    return str(uuid.uuid5(NS, s))
def q(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)
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
# KiCad 10 ships no 3D model under these footprints' model paths: point them at a matching package
# model, or at the exact-part USB-C model that cad/tools/models_3d.py writes to cad/3dmodels/.
KI3D = '${KICAD10_3DMODEL_DIR}/'
MODEL_SWAP = {
    'USB_C_Receptacle_HRO_TYPE-C-31-M-12': ('Connector_USB.3dshapes/USB_C_Receptacle_HRO_TYPE-C-31-M-12.step',
                                            '${KIPRJMOD}/3dmodels/USB_C_Receptacle_HRO_TYPE-C-31-M-12.step'),
    'VQFN-24-1EP_4x4mm_P0.5mm_EP2.45x2.45mm': ('Package_DFN_QFN.3dshapes/VQFN-24-1EP_4x4mm_P0.5mm_EP2.45x2.45mm.step',
                                               KI3D + 'Package_DFN_QFN.3dshapes/Texas_RGE0024C_VQFN-24-1EP_4x4mm_P0.5mm_EP2.1x2.1mm.step'),
    'HVSSOP-8-1EP_3x3mm_P0.65mm_EP1.57x1.89mm': ('Package_SO.3dshapes/HVSSOP-8-1EP_3x3mm_P0.65mm_EP1.57x1.89mm.step',
                                                 KI3D + 'Package_SO.3dshapes/MSOP-8-1EP_3x3mm_P0.65mm_EP1.68x1.88mm.step'),
}
for name, (old, new) in MODEL_SWAP.items():
    path = LOCAL / (name + '.kicad_mod')
    if path.exists():
        path.write_text(path.read_text().replace(KI3D + old, new))
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
from schematic_pages import write_pages
write_pages(ROOT, DATA, symbols, geometry, pinout, local_fp, uid, q)
# pcbnew provides footprint geometry, rotation and pad placement.
b=k.BOARD();b.SetCopperLayerCount(4)
settings=b.GetDesignSettings();settings.SetAuxOrigin(pos(OUTLINE[0],OUTLINE[3]));settings.m_SolderMaskMargin=mm(0.05)
settings.m_MinClearance=mm(0.15);settings.m_TrackMinWidth=mm(0.15);settings.m_ViasMinSize=mm(0.45);settings.m_MinThroughDrill=mm(0.2)
nets={}
for n in sorted({n for p in PARTS for n in p['pins'].values() if n is not None}):
    net=k.NETINFO_ITEM(b,n);b.Add(net);nets[n]=net
fps={}
for p in PARTS:
    ref=p['ref'];name=local_fp(p).split(':')[1]
    f=k.FootprintLoad(str(LOCAL),name);f.SetReference(ref);f.SetValue(p['value']);f.SetFPID(k.LIB_ID('LCR',name));f.SetPosition(pos(*p['pcb'][:2]));f.SetOrientationDegrees(p['pcb'][2])
    path=k.KIID_PATH();path.push_back(k.KIID(rootid));path.push_back(k.KIID(uid("sheet-"+p["sheet"])));path.push_back(k.KIID(uid(ref)));f.SetPath(path)
    f.Reference().SetTextSize(pos(.8,.8));f.Reference().SetTextThickness(mm(.12))
    if ref in REF_TEXT: f.Reference().SetPosition(pos(*REF_TEXT[ref]))  # Rev E: U13; U7 clear of R94; U14 clear of decoupling; U16 west of the EN/IN tie
    if not ref.startswith('U'):
        f.Reference().SetLayer(k.F_Fab)
    for name,value in {'MPN':p['mpn'],'Manufacturer':p['manufacturer'],'LCSC':p['lcsc'],'Unit_USD':str(p['unit_usd']),'Assembly':p['assembly']}.items():
        f.SetField(name,value)
        f.GetField(name).SetVisible(False)
    f.SetDNP(p['assembly']=='DNP')
    actual={pad.GetNumber() for pad in f.Pads() if pad.GetNumber()}
    if actual != set(p['pins']):
        raise ValueError(f"{ref}: footprint pins {actual} differ from source pins {set(p['pins'])}")
    for pad in f.Pads():
        num=pad.GetNumber()
        if num and num in p['pins']:
            if p['pins'][num] is not None:
                pad.SetNet(nets[p['pins'][num]])
            else:
                unit_ref = ref + ('B' if ref in ('U8','U9') and num in ('1','4') else '')
                name=f"unconnected-({unit_ref}-{pinout(p)[num][0]}-Pad{num})"
                net=k.NETINFO_ITEM(b,name);b.Add(net);pad.SetNet(net)
    b.Add(f);fps[ref]=f
# Board edge, mechanical fixing holes and clear labels.
# Rev E: top edge at y 45 (was 50) so the four BNC jacks sit on it; the holes stay put.
X0,Y0,X1,Y1=OUTLINE
for a,c in [((X0,Y0),(X1,Y0)),((X1,Y0),(X1,Y1)),((X1,Y1),(X0,Y1)),((X0,Y1),(X0,Y0))]:
    s=k.PCB_SHAPE();s.SetShape(k.SHAPE_T_SEGMENT);s.SetStart(pos(*a));s.SetEnd(pos(*c));s.SetLayer(k.Edge_Cuts);s.SetWidth(mm(.05));b.Add(s)
for i,(x,y) in enumerate(HOLES,1):
    f=k.FootprintLoad(str(LIBS/'MountingHole.pretty'),'MountingHole_3.2mm_M3');f.SetReference('H'+str(i));f.SetPosition(pos(x,y));f.Reference().SetLayer(k.F_Fab);f.SetAttributes(k.FP_EXCLUDE_FROM_BOM|k.FP_EXCLUDE_FROM_POS_FILES|k.FP_BOARD_ONLY);b.Add(f)
for text,x,y,size in SILK:
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
            t=k.PCB_TRACK(b);t.SetStart(a);t.SetEnd(c);t.SetWidth(mm(route.get('width',.2)));t.SetLayer(layer);t.SetNet(nets[route['net']]);t.SetLocked(route.get('locked',False));b.Add(t)
    for zn in rt.get('zones',[]):
        z=k.ZONE(b);z.SetLayer({'In1.Cu':k.In1_Cu,'In2.Cu':k.In2_Cu,'B.Cu':k.B_Cu}[zn['layer']]);z.SetNet(nets[zn['net']]);z.SetLocalClearance(mm(.2));z.SetPadConnection(k.ZONE_CONNECTION_FULL);z.SetThermalReliefGap(mm(.25));z.SetThermalReliefSpokeWidth(mm(.3));z.Outline().NewOutline()
        for x,y in zn['points']:z.Outline().Append(mm(x),mm(y))
        b.Add(z)
    for ko in rt.get('keepouts',[]):
        for layer in ko['layers']:
            z=k.ZONE(b);z.SetIsRuleArea(True)
            z.SetLayer({'F.Cu':k.F_Cu,'In1.Cu':k.In1_Cu,'In2.Cu':k.In2_Cu,'B.Cu':k.B_Cu}[layer])
            z.SetDoNotAllowTracks(ko.get('tracks',False));z.SetDoNotAllowVias(ko.get('tracks',False))
            z.SetDoNotAllowZoneFills(True);z.SetDoNotAllowPads(False)
            z.SetDoNotAllowFootprints(False);z.SetZoneName(ko['name'])
            z.Outline().NewOutline()
            for x,y in ko['points']:z.Outline().Append(mm(x),mm(y))
            b.Add(z)
    # Native CLI --refill-zones performs filling in its initialized KiCad context.
k.SaveBoard(str(ROOT/'temper-lcr.kicad_pcb'),b)
board_path=ROOT/'temper-lcr.kicad_pcb'
item_index=iter(range(100000))
board_path.write_text(re.sub(r'\(uuid "[^"]+"\)',lambda _:f'(uuid "{uid("pcb-item-"+str(next(item_index)))}")',board_path.read_text()))
# Project settings carry explicit common fabrication minima.  Rev E: every via is 0.30 mm drill; JLC's
# standard 4-layer via option reads "0.3mm/(0.4/0.45mm)" (hole/diameter), so a 0.45 mm via has 0.075 mm ring.
pro={'meta':{'filename':'temper-lcr.kicad_pro','version':1},'board':{'design_settings':{'rules':{'min_clearance':.15,'min_track_width':.15,'min_via_diameter':.45,'min_via_annular_width':.075,'min_through_hole_diameter':.3,'min_copper_edge_clearance':.3,'min_hole_clearance':.2,'min_hole_to_hole':.25,'min_silk_clearance':.1,'min_text_height':.8,'min_text_thickness':.12},'defaults':{'copper_line_width':.2},'rule_severities':{}},'layer_presets':[]},'net_settings':{'classes':[{'name':'Default','clearance':.15,'track_width':.2,'via_diameter':.6,'via_drill':.3,'microvia_diameter':.3,'microvia_drill':.1,'diff_pair_width':.2,'diff_pair_gap':.2,'diff_pair_via_gap':.25}], 'meta':{'version':3}},'erc':{'erc_exclusions':[],'meta':{'version':0},'pin_map':[],'rule_severities':{}},'schematic':{'drawing':{'default_text_size':50}}}
(ROOT/'temper-lcr.kicad_pro').write_text(json.dumps(pro,indent=2)+'\n')
# Native pad coordinates are the routing oracle; avoid hand-written rotation math.
out={p['ref']:{pad.GetNumber():[k.ToMM(pad.GetPosition().x),k.ToMM(pad.GetPosition().y),pad.GetNetname()] for pad in fps[p['ref']].Pads() if pad.GetNumber()} for p in PARTS}
(ROOT.parent/'build'/'pad-coordinates.json').write_text(json.dumps(out,indent=2)+'\n')
print(f'Wrote schematic and PCB: {len(PARTS)} components, {len(nets)} nets')
