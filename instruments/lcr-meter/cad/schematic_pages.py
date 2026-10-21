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
                "Fit ONE MATCHED pair: JP1+JP4=100R; JP2+JP5=5k; JP3+JP6=100k.\n"
                "Power OFF to change ranges. One local C104=100pF compensates all ranges.\n"
                "No BUF634A: maximum source current approximately 18mA. Isolated, discharged DUT only."),
        "source": ("DDS excitation and reconstruction",
                   "24MHz DDS clock from RP2040 120MHz / 5; sine output only.\n"
                   "Two 330R/1nF RC stages, AC coupling, OPA810 noninverting gain 6.\n"
                   "This block is added to the TI reference. Measure actual amplitude and distortion."),
        "adc": ("Simultaneous voltage / current acquisition",
                "Channel A = HIGH_BUF - LOW_BUF; channel B = LOW_BUF - TIA_OUT.\n"
                "Z = [RF / (1+j*2*pi*f*RF*CF)] * A/B. CF=100pF on every range; high-range pole=15.9kHz.\n"
                "ADS9224REVM p26 topology: 22R inside feedback, 100pF || 1k, then 4.32R to ADC.\n"
                "REFby2 drives VOCM. REFOUT is decoupled only. Each REFP uses 22uF."),
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
        '(date "2026-10-20") (rev "D") (company "Temper") '
        '(comment 1 "Engineering prototype. One PCB. Isolated, discharged DUT only.")) (lib_symbols)'
    ]
    for i, (sheet, (title, notes)) in enumerate(sheets.items(), 2):
        x, y = 30 + ((i-2) % 2)*185, 45 + ((i-2)//2)*70
        root_chunks.append(
            f'(sheet (at {x} {y}) (size 160 40) (stroke (width 0.254) (type default)) '
            f'(fill (color 0 0 0 0)) (uuid "{uid("sheet-"+sheet)}") '
            f'(property "Sheetname" {q(title)} (at {x} {y-2} 0) {fx}) '
            f'(property "Sheetfile" "{sheet}.kicad_sch" (at {x} {y+42} 0) {fx}) '
            f'(instances (project "temper-lcr" (path "/{rootid}" (page "{i}")))))'
        )
        root_chunks.append(
            f'(text {q({"afe":"Matched RG/RF: 100R / 5k / 100k","source":"100Hz-100kHz small-signal excitation","adc":"Two channels / one conversion instant","digital":"USB control, firmware and host calibration","power":"External 5V → quiet +/-12V"}[sheet])} '
            f'(at {x+5} {y+20} 0) (effects (font (size 1.5 1.5)) (justify left)) '
            f'(uuid "{uid("overview-"+sheet)}"))'
        )
        if sheet == "afe":
            _write_afe(root, data, symbols, local_fp, uid, q, title, notes)
            continue
        if sheet == "adc":
            _write_adc(root, data, symbols, geometry, pinout, local_fp, uid, q, title, notes)
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
            f'(paper "A2") (title_block (title {q(title)}) (date "2026-10-20") (rev "D") '
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
                f'(in_bom yes) (on_board yes) (dnp no) (uuid "{uid(ref)}") {" ".join(proptext)} '
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
    return result


def _write_adc(root, data, symbols, geometry, pinout, local_fp, uid, q, title, notes):
    """Connected FDA compensation networks; source pin maps remain authoritative."""
    parts = {p['ref']: p for p in data['parts'] if p['sheet'] == 'adc'}
    rootid, pageid = uid('schematic'), uid('sheet-adc')
    fx = '(effects (font (size 1.27 1.27)) (justify left))'
    stroke = '(stroke (width 0.254) (type default)) (fill (type background))'
    main = {'2': (-5, -3), '3': (-5, 3), '11': (5, -3), '10': (5, 3)}
    power = {'5': (-3, -3), '6': (-1, -3), '7': (1, -3), '8': (3, -3),
             '13': (-4, 3), '14': (-2, 3), '15': (0, 3), '16': (2, 3), '17': (4, 3),
             '9': (-5, -1), '12': (-5, 1), '1': (5, -1), '4': (5, 1)}
    names = {'2': 'IN+', '3': 'IN-', '10': 'OUT+', '11': 'OUT-', '9': 'VOCM',
             '12': 'PD', '1': 'FB-', '4': 'FB+'}
    units = []
    for unit, coords in [(1, main), (2, power)]:
        pins = []
        for pn, (dx, dy) in coords.items():
            angle = 0 if dx == -5 else 180 if dx == 5 else 270 if dy < 0 else 90
            typ = 'input' if pn in ('2', '3', '9', '12') else 'output' if pn in ('10', '11', '1', '4') else 'power_in'
            pins.append(f'(pin {typ} line (at {dx*2.54} {-dy*2.54} {angle}) (length 2.54) '
                        f'(name {q(names.get(pn, "VS+" if pn in ("5", "6", "7", "8") else "GND"))} {fx}) '
                        f'(number {q(pn)} {fx}))')
        height = 10.16 if unit == 1 else 5.08
        units.append(f'(symbol "ADC_FDA_{unit}_1" (rectangle (start -10.16 {height}) (end 10.16 {-height}) {stroke}) {" ".join(pins)})')
    fda = (f'(symbol "LCR:ADC_FDA" (pin_names (offset 0.508)) (in_bom yes) (on_board yes) '
           f'(property "Reference" "U" (at 0 12.7 0) {fx}) '
           f'(property "Value" "THS4551" (at 0 -12.7 0) {fx}) {" ".join(units)})')
    vertical = (f'(symbol "LCR:ADC_CV" (pin_names hide) (in_bom yes) (on_board yes) '
                f'(property "Reference" "C" (at 5.08 0 0) {fx}) '
                f'(property "Value" "C" (at 5.08 -2.54 0) {fx}) '
                f'(symbol "ADC_CV_0_1" '
                f'(polyline (pts (xy -2.54 -0.762) (xy 2.54 -0.762)) {stroke}) '
                f'(polyline (pts (xy -2.54 0.762) (xy 2.54 0.762)) {stroke})) '
                f'(symbol "ADC_CV_1_1" '
                f'(pin passive line (at 0 -7.62 90) (length 6.858) (name "1" {fx}) (number "1" {fx})) '
                f'(pin passive line (at 0 7.62 270) (length 6.858) (name "2" {fx}) (number "2" {fx}))))')
    extra = _afe_symbols(q) + [fda, vertical]
    library = root / 'LCR.kicad_sym'
    text = library.read_text().rstrip()
    library.write_text(text[:-1] + '\n' + '\n'.join(s.replace('(symbol "LCR:', '(symbol "') for s in [fda, vertical]) + ')\n')
    chunks = [f'(kicad_sch (version 20250114) (generator "lcr_adapter") (uuid "{uid("page-adc")}") '
              f'(paper "A2") (title_block (title {q(title)}) (date "2026-10-20") (rev "D") (company "Temper")) '
              f'(lib_symbols {" ".join(symbols+extra)})']
    endpoints = {}
    counter = 0
    def point(pt):
        return tuple(round(v*2.54, 4) for v in pt)
    def add(expr):
        nonlocal counter
        counter += 1
        chunks.append(expr.replace('@UUID@', uid(f'adc-drawing-{counter}')))
    def wire(a, b):
        if a == b:
            return
        a, b = point(a), point(b)
        add(f'(wire (pts (xy {a[0]} {a[1]}) (xy {b[0]} {b[1]})) (stroke (width 0) (type default)) (uuid "@UUID@"))')
    def path(*pts):
        for a, b in zip(pts, pts[1:]):
            wire(a, b)
    def label(net, pt, angle=0):
        x, y = point(pt)
        add(f'(global_label {q(net)} (shape bidirectional) (at {x} {y} {angle}) '
            f'(effects (font (size 1 1)) (justify {"right" if angle == 0 else "left"})) (uuid "@UUID@"))')
    def junction(pt):
        x, y = point(pt)
        add(f'(junction (at {x} {y}) (diameter 0) (color 0 0 0 0) (uuid "@UUID@"))')
    def note(text, pt, size=1.27):
        x, y = point(pt)
        add(f'(text {q(text)} (at {x} {y} 0) (effects (font (size {size} {size})) (justify left top)) (uuid "@UUID@"))')
    def component(ref, kind, at, coords=None, unit=1, prop_positions=None):
        p = parts[ref]
        if coords is None:
            coords = {'1': (3, 0), '2': (-3, 0)} if kind in ('AFE_JPR', 'ADC_CR') else {'1': (-3, 0), '2': (3, 0)}
        x, y = point(at)
        props = {'Reference': ref, 'Value': p['value'], 'Footprint': local_fp(p), 'MPN': p['mpn'],
                 'Manufacturer': p['manufacturer'], 'LCSC': p['lcsc'], 'Unit_USD': str(p['unit_usd']), 'Assembly': p['assembly']}
        proptext = []
        for name, value in props.items():
            pos = prop_positions.get(name) if prop_positions else None
            px, py = point(pos) if pos else (x, y + (-5.08 if name == 'Reference' else 5.08 if name == 'Value' else 0))
            hide = '' if name in ('Reference', 'Value') and unit == 1 else ' hide'
            proptext.append(f'(property {q(name)} {q(value)} (at {px} {py} 0) (effects (font (size 1.27 1.27)){hide}))')
        identity = uid(ref) if unit == 1 else uid(f'{ref}-unit-{unit}')
        pins = ' '.join(f'(pin "{pn}" (uuid "{uid(ref+"pin"+pn)}"))' for pn in coords)
        add(f'(symbol (lib_id "LCR:{kind}") (at {x} {y} 0) (unit {unit}) (in_bom yes) (on_board yes) '
            f'(dnp no) (uuid "{identity}") {" ".join(proptext)} {pins} '
            f'(instances (project "temper-lcr" (path "/{rootid}/{pageid}" (reference "{ref}") (unit {unit})))))')
        for pn, (dx, dy) in coords.items():
            key = (ref, pn)
            if key in endpoints:
                raise ValueError(f'Duplicate ADC pin: {key}')
            endpoints[key] = (at[0]+dx, at[1]+dy)
    note(notes, (8, 7), 1.5)
    for offset, u, rin, rfb, rout, riso, cf, cg, cd in [
        (0, 'U8', (60, 61), (62, 63), (91, 90), (65, 64), (106, 107), (63, 62), 64),
        (58, 'U9', (66, 67), (68, 69), (93, 92), (71, 70), (108, 109), (69, 68), 70),
    ]:
        note(f'{u}: feedback senses the nodes AFTER 22R, BEFORE 4.32R.', (8, 20+offset), 1.5)
        component(u, 'ADC_FDA', (42, 45+offset), main,
                  prop_positions={'Reference': (42, 39+offset), 'Value': (42, 51+offset)})
        component(u, 'ADC_FDA', (16, 63+offset), power, unit=2)
        for pn in power:
            endpoint = endpoints[(u, pn)]
            net = parts[u]['pins'][pn]
            if net is None:
                x, y = point(endpoint)
                add(f'(no_connect (at {x} {y}) (uuid "{uid(u+pn+"nc")}"))')
            else:
                label(net, endpoint, 180 if power[pn][0] > 0 else 0)
        for n, (y, fy, cy, takeoff) in enumerate([(42, 31, 25, 67), (48, 59, 65, 71)]):
            y, fy, cy = y+offset, fy+offset, cy+offset
            rr, rf, ro, ri, fc, gc = [f'R{rin[n]}', f'R{rfb[n]}', f'R{rout[n]}', f'R{riso[n]}', f'C{cf[n]}', f'C{cg[n]}']
            for ref, kind, at in [(rr, 'AFE_R', (21, y)), (rf, 'AFE_JPR', (46, fy)),
                                  (ro, 'AFE_R', (58, y)), (ri, 'AFE_R', (82, y)),
                                  (fc, 'ADC_CR', (46, cy)), (gc, 'AFE_C', (112, y))]:
                component(ref, kind, at)
            label(parts[rr]['pins']['1'], (18, y))
            path((24, y), (32, y), (37, y))
            path((47, y), (55, y))
            path((61, y), (takeoff, y), (79, y))
            label(parts[ro]['pins']['1'], (51, y), 180)
            label(parts[ro]['pins']['2'], (takeoff, y), 180)
            path((32, y), (32, fy), (32, cy), (43, cy))
            path((32, fy), (43, fy))
            label(parts[rr]['pins']['2'], (32, fy))
            path((49, cy), (takeoff, cy), (takeoff, fy), (takeoff, y))
            path((49, fy), (takeoff, fy))
            for pt in [(32, y), (32, fy), (takeoff, y), (takeoff, fy)]:
                junction(pt)
            path((85, y), (98, y), (109, y))
            label(parts[ri]['pins']['2'], (103, y), 180)
            label('GND', (115, y), 180)
            junction((98, y))
        component(f'C{cd}', 'ADC_CV', (98, 45+offset), {'1': (0, 3), '2': (0, -3)},
                  prop_positions={'Reference': (101, 44+offset), 'Value': (101, 46+offset)})
    used = {ref for ref, _ in endpoints}
    adc = parts['U10']
    coords, hh = geometry[adc['kind']]
    local = {pn: (dx/2.54, -dy/2.54) for pn, (dx, dy, _) in coords.items()}
    component('U10', adc['kind'], (176, 58), local,
              prop_positions={'Reference': (176, 58-hh/2.54-2), 'Value': (176, 58+hh/2.54+2)})
    for pn, (dx, _) in local.items():
        endpoint = endpoints[('U10', pn)]
        net = adc['pins'][pn]
        if net is None:
            x, y = point(endpoint)
            add(f'(no_connect (at {x} {y}) (uuid "{uid("U10"+pn+"nc")}"))')
        else:
            far = (endpoint[0]+(-1 if dx < 0 else 1), endpoint[1])
            path(endpoint, far)
            label(net, far, 0 if dx < 0 else 180)
    note('Reference and supply bypass. REFby2 directly drives both VOCM pins;\nC74=1uF. EVM per-driver 100R / 100nF VOCM filters are omitted.\nRGT internal FB pads are NC; external feedback uses main OUT pads.', (139, 96))
    remaining = [p for p in parts.values() if p['ref'] not in used and p['ref'] != 'U10']
    for j, p in enumerate(remaining):
        at = (146+(j % 3)*33, 106+(j//3)*12)
        component(p['ref'], 'AFE_C', at)
        label(p['pins']['1'], (at[0]-3, at[1]))
        label(p['pins']['2'], (at[0]+3, at[1]), 180)
    expected = {(r, pn) for r, p in parts.items() for pn in p['pins']}
    if set(endpoints) != expected:
        raise ValueError(f'ADC pin coverage differs: {set(endpoints)^expected}')
    chunks.append('(embedded_fonts no))')
    (root/'adc.kicad_sch').write_text('\n'.join(chunks)+'\n')


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
              f'(paper "A2") (title_block (title {q(title)}) (date "2026-10-20") (rev "D") (company "Temper")) '
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
            f'(dnp no) (uuid "{identity}") {" ".join(proptext)} {pins} '
            f'(instances (project "temper-lcr" (path "/{rootid}/{pageid}" (reference "{ref}") (unit {unit})))))')
        for pn,(dx,dy) in coords.items():
            endpoints[(ref,pn)]=(at[0]+dx,at[1]+dy)
    note(notes,(8,7),1.5)
    note('TI source and range network',(10,27),1.8)
    component('U6','OPA2810_DUAL',(30,60))
    label('EXCITE',(20,58));path((20,58),(25,58))
    path((25,62),(20,62),(20,72),(39,72),(39,60))
    path((35,60),(39,60),(48,60),(48,38))
    for jp,res,y in [('JP1','R40',38),('JP2','R41',46),('JP3','R42',54)]:
        component(jp,'AFE_JP',(60,y));component(res,'AFE_R',(78,y))
        path((48,y),(57,y));path((63,y),(75,y));path((81,y),(95,y))
        label(parts[jp]['pins']['2'],(63,y),180)
        if y!=38:junction((48,y))
    path((95,38),(95,46),(95,54),(95,60),(112,60))
    junction((39,60));junction((95,46));junction((95,54))
    label('SOURCE_BUF',(39,72),180)
    component('J3','AFE_DUT',(115,60))
    label('DUT_HI',(102,60),180)
    note('J3: connect external, isolated DUT between HI and LO.\nNo DUT component is fitted on this PCB.',(98,68))
    # Rev D: R94 isolates fixture/cable capacitance from the summing node; the LOW
    # follower taps the J3 side, so channel A stays the DUT voltage.
    component('R94','AFE_R',(136,60))
    path((118,60),(133,60));path((139,60),(145,60),(145,62),(155,62))
    label('DUT_LO',(124,60),180);label('TIA_SUM',(142,60),180)
    note('Rev D: R94 22R 0.1% between J3 LO and the TIA summing node.\nLOW follower senses J3 LO; host uses Zf = R94 + RF||C104.',(118,50))
    component('U7','OPA2810_DUAL',(160,60))
    path((155,58),(151,58));label('GND',(151,58))
    path((165,60),(190,60),(190,24))
    label('TIA_OUT',(190,60),180)
    path((145,24),(145,28),(145,32),(145,36),(145,40),(145,49),(145,60))
    junction((145,60))
    for res,jp,y in [('R43','JP4',24),('R44','JP5',32),('R45','JP6',40)]:
        component(res,'AFE_R',(160,y));component(jp,'AFE_JPR',(177,y))
        path((145,y),(157,y));path((163,y),(170,y),(174,y));path((180,y),(190,y))
        label(parts[jp]['pins']['2'],(174,y))
        if y!=24:junction((145,y));junction((190,y))
    component('C104','AFE_C',(160,49))
    path((145,49),(157,49));path((163,49),(190,49));junction((145,49));junction((190,49))
    note('TI transimpedance topology; Rev C compensation\nC104=100pF directly across U7.1 and U7.2 in all ranges',(138,12),1.8)
    for ref,at,inputnet,outputnet,start in [('U6',(105,100),'DUT_HI','HIGH_BUF',(95,60)),('U7',(160,100),'DUT_LO','LOW_BUF',(128,60))]:
        component(ref,'OPA2810_DUAL',at,2)
        x,y=at
        path(start,(start[0],y-2),(x-5,y-2));junction(start)
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
