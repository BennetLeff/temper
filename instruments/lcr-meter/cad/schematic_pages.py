"""Native KiCad hierarchical schematic serialization; no electrical inference.

Receives explicit pin geometry and source records from build_cad.py.
"""
from __future__ import annotations


def write_pages(root, data, symbols, geometry, pinout, local_fp, uid, q):
    """Write five functional sheets and an overview using global named nets."""
    rootid = uid("schematic")
    fx = '(effects (font (size 1.27 1.27)) (justify left))'
    sheets = {
        "afe": ("TI TIDA-060029 analog front end",
                "U6A source buffer; U6B HI sense; U7A transimpedance; U7B LO sense.\n"
                "Ranges: latching relays K1/K2/K3 (range sheet) close one matched RG/RF pair.\n"
                "Four-terminal BNC jacks: HCUR = DUT_HI, LCUR = DUT_LO; followers sense HPOT / LPOT.\n"
                "One local C104=100pF compensates all ranges; C78 100pF DUT_LO to GND (Rev E stability).\n"
                "No BUF634A: maximum source current approximately 18mA. Isolated, discharged DUT only."),
        "source": ("Codec DAC excitation",
                   "TAC5112 OUT1P/OUT1M differential line out at fs = 187.5kHz.\n"
                   "OPA810 difference stage: 2.2k in, 2.0k || 280pF (2 x 560pF in series) feedback and ground leg, gain 0.909.\n"
                   "DC coupled: the stage rejects the 1.65V DAC common mode."),
        "codec": ("Codec acquisition (TAC5112)",
                  "CH1 = HIGH_BUF - LOW_BUF (IN1P/IN1M); CH2 = LOW_BUF - TIA_OUT (IN2P/IN2M).\n"
                  "Each leg: 1k series, 1k + 560pF to GND (K = 0.5), 1uF, BAT54S clamp, 470R to the pin.\n"
                  "TDM controller: RP2040 drives BCLK 12MHz / FSYNC 187.5kHz. I2C address 0x50.\n"
                  "AVDD from U15 AP2112K-3.3 on 5VA; IOVDD from 3V3."),
        "range": ("Range relays",
                  "K1 100R, K2 5k, K3 100k, K4 reference: Panasonic TQ2SA-L2-5V dual-coil latching DPDT.\n"
                  "Pole 1: SOURCE_BUF -> RGx. Pole 2: TIA_OUT -> RFx. NC contacts unconnected.\n"
                  "RESET coils (K1-K4) in parallel on Q2; SET coils on Q3/Q4/Q5/Q6. 1N4148WS flyback per drain.\n"
                  "K4 reference: COM2 on HCUR, NO2 through R107 1k 0.1% to LCUR (REFCAPTURE, leads unplugged).\n"
                  "VRLY = 5V through R101 2.2R + C112 22uF. Firmware: source off, RESET 20ms, SET 20ms."),
        "digital": ("USB, RP2040 and boot / debug",
                    "External 5V input powers the instrument. USB VBUS is sensed only; no backfeed.\n"
                    "Native USB CDC; 120MHz MCU; dual-lane ADC acquisition at up to 1MSPS.\n"
                    "Hold BOOTSEL while resetting for ROM USB firmware loading. SWD and UART provided."),
        "power": ("Power: 5V input, forced PWM, quiet analog rails",
                  "Input: REGULATED 5V +/-5%, 1A, center positive. USB does not supply this board.\n"
                  "TPS65131 PSP/PSN grounded: forced PWM 1.25-1.5MHz. RAW_P ~14.31V; RAW_N ~-14.39V.\n"
                  "TPS7A49 ~+11.97V; TPS7A30 ~-12.00V. Fixed output values are nominal.\n"
                  "Do not substitute capacitor voltage/package without checking DC-bias derating."),
    }
    root_chunks = [
        f'(kicad_sch (version 20250114) (generator "lcr_adapter") (uuid "{rootid}") '
        '(paper "A3") (title_block (title "Temper LCR — TIDA-060029 based") '
        '(date "2026-10-20") (rev "E") (company "Temper") '
        '(comment 1 "Engineering prototype. One PCB. Isolated, discharged DUT only.")) (lib_symbols)'
    ]
    for i, (sheet, (title, notes)) in enumerate(sheets.items(), 2):
        x, y = 30 + ((i-2) % 2)*185, 45 + ((i-2)//2)*60
        root_chunks.append(
            f'(sheet (at {x} {y}) (size 160 40) (stroke (width 0.254) (type default)) '
            f'(fill (color 0 0 0 0)) (uuid "{uid("sheet-"+sheet)}") '
            f'(property "Sheetname" {q(title)} (at {x} {y-2} 0) {fx}) '
            f'(property "Sheetfile" "{sheet}.kicad_sch" (at {x} {y+42} 0) {fx}) '
            f'(instances (project "temper-lcr" (path "/{rootid}" (page "{i}")))))'
        )
        root_chunks.append(
            f'(text {q({"afe":"Matched RG/RF: 100R / 5k / 100k","source":"Coherent codec DAC excitation","codec":"Two channels / one frame clock","range":"Relay-selected ranges","digital":"USB control, firmware and host calibration","power":"External 5V → quiet +/-12V"}[sheet])} '
            f'(at {x+5} {y+20} 0) (effects (font (size 1.5 1.5)) (justify left)) '
            f'(uuid "{uid("overview-"+sheet)}"))'
        )
        if sheet == "afe":
            _write_afe(root, data, symbols, local_fp, uid, q, title, notes)
            continue
        parts = [p for p in data["parts"] if p["sheet"] == sheet]
        large = [p for p in parts if len(pinout(p)) > 4]
        small = [p for p in parts if len(pinout(p)) <= 4]
        layout = {}
        for j, p in enumerate(large):
            layout[p["ref"]] = (65 + j*115, 83)
        for j, p in enumerate(small):
            layout[p["ref"]] = (55 + (j % 6)*94, 160 + (j//6)*29)
        chunks = [
            f'(kicad_sch (version 20250114) (generator "lcr_adapter") (uuid "{uid("page-"+sheet)}") '
            f'(paper "A2") (title_block (title {q(title)}) (date "2026-10-20") (rev "E") '
            '(company "Temper") (comment 1 "Global net names connect functional sheets. See TI conformance matrix.")) '
            f'(lib_symbols {" ".join(symbols)})'
        ]
        chunks.append(
            f'(text {q(notes)} (at 20.32 17.78 0) (effects (font (size 1.5 1.5)) (justify left top)) '
            f'(uuid "{uid(sheet+"-notes")}"))'
        )
        for p in parts:
            ref = p["ref"]
            x, y = (round(v/1.27)*1.27 for v in layout[ref])
            coords, hh = geometry[p["kind"]]
            props = {"Reference":ref, "Value":p["value"], "Footprint":local_fp(p),
                     "MPN":p["mpn"], "Manufacturer":p["manufacturer"], "LCSC":p["lcsc"],
                     "Unit_USD":str(p["unit_usd"]), "Assembly":p["assembly"]}
            proptext = []
            for name, value in props.items():
                yy = y-hh-3.81 if name == "Reference" else y+hh+3.81 if name == "Value" else y
                hidden = "" if name in ("Reference", "Value") else " hide"
                proptext.append(
                    f'(property {q(name)} {q(value)} (at {x} {yy} 0) '
                    f'(effects (font (size 1.27 1.27)){hidden}))'
                )
            pintext = " ".join(f'(pin {q(pn)} (uuid "{uid(ref+"pin"+pn)}"))' for pn in coords)
            chunks.append(
                f'(symbol (lib_id "LCR:{p["kind"]}") (at {x} {y} 0) (unit 1) '
                f'(in_bom yes) (on_board yes) (dnp {"yes" if p["assembly"] == "DNP" else "no"}) (uuid "{uid(ref)}") {" ".join(proptext)} '
                f'{pintext} (instances (project "temper-lcr" (path "/{rootid}/{uid("sheet-"+sheet)}" '
                f'(reference "{ref}") (unit 1)))))'
            )
            for pn, (dx, dy, angle) in coords.items():
                px, py = round(x+dx, 4), round(y-dy, 4)
                net = p["pins"][pn]
                if net is None:
                    chunks.append(f'(no_connect (at {px} {py}) (uuid "{uid(ref+pn+"nc")}"))')
                    continue
                ex = round(px-2.54 if dx < 0 else px+2.54, 4)
                chunks.append(
                    f'(wire (pts (xy {px} {py}) (xy {ex} {py})) (stroke (width 0) (type default)) '
                    f'(uuid "{uid(ref+pn+"wire")}"))'
                )
                # Global labels face inward and stay outside the IC body.
                la = 0 if dx < 0 else 180
                justify = "right" if dx < 0 else "left"
                chunks.append(
                    f'(global_label {q(net)} (shape bidirectional) (at {ex} {py} {la}) '
                    f'(effects (font (size 1 1)) (justify {justify})) '
                    f'(uuid "{uid(ref+pn+"label")}"))'
                )
        if sheet == "power":
            for i, net in enumerate(data["power_flags"], 1):
                x, y = 30.48 + (i-1)*50.8, 393.7
                ref = f"#FLG0{i}"
                chunks.append(
                    f'(symbol (lib_id "LCR:PWR_FLAG") (at {x} {y} 0) (unit 1) (in_bom no) '
                    f'(on_board no) (dnp no) (uuid "{uid(ref)}") '
                    f'(property "Reference" "{ref}" (at {x} {y} 0) '
                    '(effects (font (size 1.27 1.27)) hide)) '
                    f'(property "Value" "PWR_FLAG" (at {x} {y-3.81} 0) {fx}) '
                    f'(pin "1" (uuid "{uid(ref+"pin")}")) '
                    f'(instances (project "temper-lcr" (path "/{rootid}/{uid("sheet-"+sheet)}" '
                    f'(reference "{ref}") (unit 1)))))'
                )
                chunks.append(
                    f'(global_label "{net}" (shape bidirectional) (at {x} {y} 0) '
                    '(effects (font (size 1 1)) (justify right)) '
                    f'(uuid "{uid(ref+"label")}"))'
                )
        chunks.append('(embedded_fonts no))')
        (root/f"{sheet}.kicad_sch").write_text("\n".join(chunks)+"\n")
    root_chunks.append('(embedded_fonts no))')
    (root/"temper-lcr.kicad_sch").write_text("\n".join(root_chunks)+"\n")

def _afe_symbols(q):
    """Explicit multi-unit OPA2810 and compact, unrotated passive symbols."""
    fx = '(effects (font (size 1.27 1.27)) (justify left))'
    stroke = '(stroke (width 0.254) (type default)) (fill (type background))'
    def pin(number, name, typ, x, y, angle, length=2.54):
        return (f'(pin {typ} line (at {x} {y} {angle}) (length {length}) '
                f'(name {q(name)} {fx}) (number {q(number)} {fx}))')
    def base(name, ref, bodies):
        return (f'(symbol "LCR:{name}" (pin_names (offset 0.508)) (in_bom yes) (on_board yes) '
                f'(property "Reference" "{ref}" (at 0 10.16 0) {fx}) '
                f'(property "Value" "{name}" (at 0 -10.16 0) {fx}) {bodies})')
    units = []
    for unit, pins in [(1, [('3','+',-12.7,5.08,0,'input'),('2','-',-12.7,-5.08,0,'input'),('1','OUT',12.7,0,180,'output')]),
                       (2, [('5','+',-12.7,5.08,0,'input'),('6','-',-12.7,-5.08,0,'input'),('7','OUT',12.7,0,180,'output')])]:
        triangle = f'(polyline (pts (xy -10.16 10.16) (xy -10.16 -10.16) (xy 10.16 0) (xy -10.16 10.16)) {stroke})'
        pt = ' '.join(pin(p,n,t,x,y,a) for p,n,x,y,a,t in pins)
        units.append(f'(symbol "OPA2810_DUAL_{unit}_1" {triangle} {pt})')
    power = (f'(rectangle (start -5.08 5.08) (end 5.08 -5.08) {stroke}) '
             + pin('8','VS+','power_in',0,7.62,270)
             + pin('4','VS-','power_in',0,-7.62,90))
    units.append(f'(symbol "OPA2810_DUAL_3_1" {power})')
    result = [base('OPA2810_DUAL','U',' '.join(units))]
    for name, reverse, capacitor, connector in [('AFE_R',False,False,False),('AFE_C',False,True,False),
                                               ('ADC_CR',True,True,False),
                                               ('AFE_JP',False,False,True),('AFE_JPR',True,False,True),
                                               ('AFE_DUT',False,False,True)]:
        if capacitor:
            body = ('(polyline (pts (xy -0.762 -2.54) (xy -0.762 2.54)) '+stroke+') '
                    '(polyline (pts (xy 0.762 -2.54) (xy 0.762 2.54)) '+stroke+')')
            length = 6.858
        else:
            body = f'(rectangle (start -5.08 2.54) (end 5.08 -2.54) {stroke})'
            length = 2.54
        nums = ['2','1'] if reverse else ['1','2']
        pins = pin(nums[0],nums[0],'passive',-7.62,0,0,length) + pin(nums[1],nums[1],'passive',7.62,0,180,length)
        result.append(base(name,'C' if capacitor else 'J' if connector else 'R',f'(symbol "{name}_0_1" {body}) (symbol "{name}_1_1" {pins})'))
    body = f'(circle (center 0 0) (radius 2.54) {stroke}) (circle (center 0 0) (radius 0.508) {stroke})'
    pins = pin('5','~','passive',-7.62,0,0,5.08) + ''.join(pin(n,'~','passive',7.62,0,180,5.08) for n in '1234')
    result.append(base('AFE_BNC','J',f'(symbol "AFE_BNC_0_1" {body}) (symbol "AFE_BNC_1_1" {pins})'))
    return result


def _write_afe(root, data, symbols, local_fp, uid, q, title, notes):
    """Connected TI AFE; every instance pin is verified against design.json."""
    rootid = uid('schematic')
    pageid = uid('sheet-afe')
    extra = _afe_symbols(q)
    library = root/'LCR.kicad_sym'
    text = library.read_text().rstrip()
    # build_cad writes this library immediately before write_pages. Support re-runs.
    if '(symbol "OPA2810_DUAL"' not in text:
        library.write_text(text[:-1]+'\n'+'\n'.join(s.replace('(symbol "LCR:', '(symbol "') for s in extra)+')\n')
    chunks = [f'(kicad_sch (version 20250114) (generator "lcr_adapter") (uuid "{uid("page-afe")}") '
              f'(paper "A2") (title_block (title {q(title)}) (date "2026-10-20") (rev "E") (company "Temper")) '
              f'(lib_symbols {" ".join(symbols+extra)})']
    parts = {p['ref']:p for p in data['parts'] if p['sheet']=='afe'}
    endpoints = {}
    counter = 0
    def point(pt):
        return tuple(round(v*2.54,4) for v in pt)
    def add(expr):
        nonlocal counter
        counter += 1
        chunks.append(expr.replace('@UUID@',uid(f'afe-drawing-{counter}')))
    def wire(a,b):
        if a == b:
            return
        a,b=point(a),point(b)
        add(f'(wire (pts (xy {a[0]} {a[1]}) (xy {b[0]} {b[1]})) (stroke (width 0) (type default)) (uuid "@UUID@"))')
    def path(*pts):
        for a,b in zip(pts,pts[1:]):
            wire(a,b)
    def junction(pt):
        x,y=point(pt)
        add(f'(junction (at {x} {y}) (diameter 0) (color 0 0 0 0) (uuid "@UUID@"))')
    def label(net,pt,angle=0):
        x,y=point(pt)
        add(f'(global_label {q(net)} (shape bidirectional) (at {x} {y} {angle}) '
            f'(effects (font (size 1 1)) (justify {"right" if angle==0 else "left"})) (uuid "@UUID@"))')
    def note(text,pt,size=1.27):
        x,y=point(pt)
        add(f'(text {q(text)} (at {x} {y} 0) (effects (font (size {size} {size})) (justify left top)) (uuid "@UUID@"))')
    def component(ref,kind,at,unit=1,property_positions=None):
        p=parts[ref]
        x,y=point(at)
        if kind=='OPA2810_DUAL':
            coords={1:{'3':(-5,-2),'2':(-5,2),'1':(5,0)},2:{'5':(-5,-2),'6':(-5,2),'7':(5,0)},3:{'8':(0,-3),'4':(0,3)}}[unit]
            top,bottom=(-7,7) if unit!=3 else (-6,6)
        else:
            coords={'1':(-3,0),'2':(3,0)} if kind!='AFE_JPR' else {'1':(3,0),'2':(-3,0)}
            if kind=='AFE_BNC':
                coords={'5':(-3,0),'1':(3,0),'2':(3,0),'3':(3,0),'4':(3,0)}
            top,bottom=-4,3
        props={'Reference':ref,'Value':p['value'],'Footprint':local_fp(p),'MPN':p['mpn'],
               'Manufacturer':p['manufacturer'],'LCSC':p['lcsc'],'Unit_USD':str(p['unit_usd']),'Assembly':p['assembly']}
        proptext=[]
        for name,value in props.items():
            yy=y+2.54*(top if name=='Reference' else bottom if name=='Value' else 0)
            px,py=point(property_positions[name]) if property_positions and name in property_positions else (x,yy)
            hide='' if name in ('Reference','Value') else ' hide'
            proptext.append(f'(property {q(name)} {q(value)} (at {px} {py} 0) (effects (font (size 1.27 1.27)){hide}))')
        identity=uid(ref) if unit==1 else uid(f'{ref}-unit-{unit}')
        pins=' '.join(f'(pin "{pn}" (uuid "{uid(ref+"pin"+pn)}"))' for pn in coords)
        add(f'(symbol (lib_id "LCR:{kind}") (at {x} {y} 0) (unit {unit}) (in_bom yes) (on_board yes) '
            f'(dnp {"yes" if p["assembly"]=="DNP" else "no"}) (uuid "{identity}") {" ".join(proptext)} {pins} '
            f'(instances (project "temper-lcr" (path "/{rootid}/{pageid}" (reference "{ref}") (unit {unit})))))')
        for pn,(dx,dy) in coords.items():
            endpoints[(ref,pn)]=(at[0]+dx,at[1]+dy)
    note(notes,(8,7),1.5)
    note('TI source and range network',(10,27),1.8)
    component('U6','OPA2810_DUAL',(30,60))
    label('EXCITE',(20,58));path((20,58),(25,58))
    path((25,62),(20,62),(20,72),(39,72),(39,60))
    path((35,60),(39,60))
    for res,y in [('R40',38),('R41',46),('R42',54)]:
        component(res,'AFE_R',(78,y))
        path((70,y),(75,y));path((81,y),(95,y))
        label(parts[res]['pins']['1'],(70,y))
    path((95,38),(95,46),(95,54),(95,60),(112,60))
    junction((39,60));junction((95,46));junction((95,54))
    label('DUT_HI',(112,60),180)
    label(parts['U6']['pins']['1'],(39,72),180)
    if 'R104' in parts:
        # Rev E: R104 isolates the relay bus (board copper + relay capacitance) from U6A.
        component('R104','AFE_R',(48,60))
        path((39,60),(45,60));path((51,60),(56,60))
        label('SOURCE_BUF',(56,60),180)
        note('Rev E: R104 47R isolates the SOURCE_BUF relay bus from U6A.',(30,80))
    # Rev E: four-terminal BNC jacks; HCUR keeps DUT_HI, LCUR keeps DUT_LO.
    for ref,net,y in [('J3','DUT_HI',72),('J7','HPOT',80),('J8','LPOT',88),('J9','DUT_LO',96)]:
        component(ref,'AFE_BNC',(68,y))
        label(net,(65,y));label('GND',(71,y),180)
    for ref,a,b,y in [('R105','DUT_HI','HPOT',72),('R106','DUT_LO','LPOT',88)]:
        component(ref,'AFE_R',(84,y))
        label(a,(81,y));label(b,(87,y),180)
    note('J3 HCUR, J7 HPOT, J8 LPOT, J9 LCUR: BNC, 22 mm pitch, shells to GND.\n'
         'Connect an external, isolated, discharged DUT with Kelvin leads.\n'
         'R105/R106 1k tie each POT to its CUR for two-terminal leads.',(56,103))
    # Rev D: R94 isolates fixture/cable capacitance from the summing node; the LOW
    # follower taps the J3 side, so channel A stays the DUT voltage.
    component('R94','AFE_R',(136,60))
    path((124,60),(133,60));path((139,60),(145,60),(145,62),(155,62))
    label('DUT_LO',(124,60),180);label('TIA_SUM',(142,60),180)
    note('Rev D: R94 22R 0.1% between LCUR and the TIA summing node.\nRev E: LOW follower senses LPOT; host uses Zf = R94 + RF||C104.',(118,50))
    component('U7','OPA2810_DUAL',(160,60))
    path((155,58),(151,58));label('GND',(151,58))
    path((165,60),(190,60),(190,49))
    label('TIA_OUT',(190,60),180)
    path((145,24),(145,28),(145,32),(145,36),(145,40),(145,49),(145,60))
    junction((145,60))
    for res,y in [('R43',24),('R44',32),('R45',40)]:
        component(res,'AFE_R',(160,y))
        path((145,y),(157,y));path((163,y),(170,y))
        label(parts[res]['pins']['2'],(170,y),180)
        if y!=24:junction((145,y))
    component('C104','AFE_C',(160,49))
    path((145,49),(157,49));path((163,49),(190,49));junction((145,49))
    component('C78','AFE_C',(124,72))
    label('DUT_LO',(121,72));label('GND',(127,72),180)
    note('Rev E: C78 100pF C0G from LCUR (DUT_LO) to GND (TIA margin with relay parasitics).',(112,76))
    note('TI transimpedance topology; Rev C compensation\nC104=100pF directly across U7.1 and U7.2 in all ranges',(138,12),1.8)
    for ref,at,inputnet,outputnet in [('U6',(105,100),'HPOT','HIGH_BUF'),('U7',(160,100),'LPOT','LOW_BUF')]:
        component(ref,'OPA2810_DUAL',at,2)
        x,y=at
        label(inputnet,(x-12,y-2));path((x-12,y-2),(x-5,y-2))
        path((x-5,y+2),(x-10,y+2),(x-10,y+12),(x+9,y+12),(x+9,y))
        path((x+5,y),(x+9,y),(x+16,y));junction((x+9,y))
        label(outputnet,(x+16,y),180)
    note('Independent HI / LO voltage followers',(95,119),1.8)
    # Dedicated supply units and each retained + supplemental bypass capacitor.
    for ref,x,groups in [('U6',25,[(42,44,50),(43,45,51)]),('U7',125,[(46,48,52),(47,49,53)])]:
        component(ref,'OPA2810_DUAL',(x,129),3)
        for pn,net,y,capnums in [('8',parts[ref]['pins']['8'],120,groups[0]),('4','-12V',138,groups[1])]:
            endpoint=endpoints[(ref,pn)]
            path(endpoint,(x,y),(x+9,y));label(net,(x+9,y),180)
            for j,n in enumerate(capnums):
                cx=x+22+j*20
                component(f'C{n}','AFE_C',(cx,y))
                label(net,(cx-3,y));label('GND',(cx+3,y),180)
    note('Retain TI 100nF + 1uF bypass per rail; added 10nF at each supply pin.\nPCB plane windows and short feedback routes are specified in reference-conformance.md.',(8,158))
    # Assert that every physical AFE pin appears exactly once across all units.
    expected={(r,pn) for r,p in parts.items() for pn in p['pins']}
    if set(endpoints)!=expected:
        raise ValueError(f'AFE pin coverage differs: {set(endpoints)^expected}')
    chunks.append('(embedded_fonts no))')
    (root/'afe.kicad_sch').write_text('\n'.join(chunks)+'\n')
