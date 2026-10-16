import json
B = "/Users/bennet/Desktop/temper/worktrees/runs-native21/s47/temp-ratings-dl/semis-a"
R = "/Users/bennet/Desktop/temper/worktrees/runs-native21"

def ds(title, doc, rev, url, sha, local):
    return {"title": title, "doc": doc, "revision": rev, "url": url, "sha256_prefix16": sha, "local": local}

def rt(parameter, value_c, applies_to, kind, page, quote):
    return {"parameter": parameter, "value_c": value_c, "applies_to": applies_to, "kind": kind, "page": page, "quote": quote}

def th(parameter, value_kw, condition, page, quote):
    return {"parameter": parameter, "value_kw": value_kw, "condition": condition, "page": page, "quote": quote}

def el(parameter, value, unit, condition, page, quote=None):
    d = {"parameter": parameter, "value": value, "unit": unit, "condition": condition, "page": page}
    if quote:
        d["quote"] = quote
    return d

out = {}

# 1 PMEG6030EP
out["PMEG6030EP,115"] = {
    "manufacturer": "Nexperia",
    "designators": "D6-D9",
    "datasheet": ds("PMEG6030EP 3 A low VF MEGA Schottky barrier rectifier, Product data sheet",
                    "PMEG6030EP v.2", "v.2, 7 November 2017 (supersedes PMEG6030EP_1, 20100120)",
                    "https://datasheet.lcsc.com/datasheet/pdf/598a8a4be41fa942ad873c7b94285078.pdf?productCode=C456127 (LCSC copy; assets.nexperia.com returned HTTP 403 Access Denied to curl)",
                    "89bc99ad6f4835fb", f"{B}/pmeg6030ep/PMEG6030EP_lcsc_C456127.pdf"),
    "ratings": [
        rt("Tj max", 150, "junction", "absolute maximum (Limiting values, IEC 60134)", "PDF p3 / printed 3 / 14",
           "Tj junction temperature - 150 °C"),
        rt("Tamb range", [-55, 150], "ambient", "absolute maximum (Limiting values)", "PDF p3 / printed 3 / 14",
           "Tamb ambient temperature -55 150 °C"),
        rt("Tstg range", [-65, 150], "storage", "absolute maximum (Limiting values)", "PDF p3 / printed 3 / 14",
           "Tstg storage temperature -65 150 °C"),
    ],
    "thermal": [
        th("Rth(j-a)", 200, "in free air; FR4 PCB, single-sided copper, tin-plated, standard footprint (notes [1][2])", "PDF p3 / printed 3 / 14",
           "Rth(j-a) thermal resistance from junction to ambient in free air [1] [2] - - 200 K/W"),
        th("Rth(j-a)", 120, "in free air; FR4 PCB, single-sided copper, tin-plated, mounting pad for cathode 1 cm2 (notes [3][2])", "PDF p3 / printed 3 / 14",
           "[3] [2] - - 120 K/W ... [3] Device mounted on an FR4 PCB, single-sided copper, tin-plated, mounting pad for cathode 1 cm2."),
        th("Rth(j-a)", 60, "in free air; ceramic PCB, Al2O3, standard footprint (notes [4][2])", "PDF p3 / printed 3 / 14",
           "[4] [2] - - 60 K/W ... [4] Device mounted on a ceramic PCB, Al2O3, standard footprint."),
        th("Rth(j-sp)", 12, "junction to soldering point of cathode tab (note [5])", "PDF p3 / printed 3 / 14",
           "Rth(j-sp) thermal resistance from junction to solder point [5] - - 12 K/W ... [5] Soldering point of cathode tab."),
    ],
    "electrical": [
        el("VF max", 330, "mV", "IF = 0.1 A; Tj = 25 °C (typ 290)", "PDF p5 / printed 5 / 14", "IF = 0.1 A; Tj = 25 °C - 290 330 mV"),
        el("VF max", 400, "mV", "IF = 0.5 A; Tj = 25 °C (typ 340)", "PDF p5 / printed 5 / 14"),
        el("VF max", 440, "mV", "IF = 1 A; Tj = 25 °C (typ 380)", "PDF p5 / printed 5 / 14", "IF = 1 A; Tj = 25 °C - 380 440 mV"),
        el("VF max", 470, "mV", "IF = 1.5 A; Tj = 25 °C (typ 400)", "PDF p5 / printed 5 / 14"),
        el("VF max", 500, "mV", "IF = 2 A; Tj = 25 °C (typ 430)", "PDF p5 / printed 5 / 14"),
        el("VF max", 530, "mV", "IF = 3 A; Tj = 25 °C (typ 460)", "PDF p5 / printed 5 / 14", "IF = 3 A; Tj = 25 °C - 460 530 mV"),
        el("VF at hot Tj", None, None, "NOT TABULATED. Only Fig. 4 (typical curves Tj = 150/125/85/25/-40 °C), PDF p6. Hot-Tj VF is lower than 25 °C VF (negative tempco), so the 25 °C max is the conservative tabulated number.", "PDF p6 Fig. 4"),
        el("IFSM", 50, "A", "tp = 8 ms; Tj(init) = 25 °C; square wave", "PDF p3 / printed 3 / 14", "IFSM non-repetitive peak forward current tp = 8 ms; Tj(init) = 25 °C; square wave - 50 A"),
        el("IFRM", None, None, "NOT LISTED in Limiting values (only IF(AV) and IFSM).", "PDF p3"),
        el("IF(AV) max", 3, "A", "δ = 0.5; f = 20 kHz; Tamb ≤ 50 °C (ceramic PCB) or Tsp ≤ 135 °C; square wave", "PDF p3 / printed 3 / 14"),
        el("Ptot max", [0.625, 1.05, 2.1], "W", "Tamb ≤ 25 °C; FR4 standard footprint / FR4 1 cm2 cathode pad / ceramic Al2O3 standard footprint", "PDF p3 / printed 3 / 14",
           "Ptot total power dissipation Tamb ≤ 25 °C [2] 625 mW; [3] 1.05 W; [1] 2.1 W"),
        el("IR max", 200, "µA", "VR = 60 V; Tj = 25 °C (typ 80)", "PDF p5 / printed 5 / 14", "VR = 60 V; Tj = 25 °C - 80 200 µA"),
        el("IR typ", [4, 5], "µA", "VR = 5 V / 10 V; Tj = 25 °C (no max given)", "PDF p5 / printed 5 / 14"),
        el("IR at Tj = 125 °C", None, None, "NO MAX TABULATED. Fig. 5 (typical) curve (1) Tj = 125 °C reads roughly 5e-3 A at VR -> 0, ~1e-2 A at 25-30 V, ~2e-2 A at 60 V (graph read, typical only). Fig. 5 has no 150 °C curve.", "PDF p6 Fig. 5"),
        el("Cd typ", [360, 120], "pF", "VR = 1 V / 10 V; f = 1 MHz", "PDF p5"),
    ],
    "notes": "No 6 cm2 mounting condition in this datasheet: the three listed Rth(j-a) conditions are FR4 standard footprint (200), FR4 1 cm2 cathode pad (120), ceramic Al2O3 standard footprint (60). No 'Tj = 175 °C' rating anywhere; 175 appears only as the last tick on the temperature axes of Figs 9-12 (IF(AV) vs Tamb/Tsp, PDF p7-8, drawn with Tj = 150 °C). Datasheet note [2] to Table 6: 'For Schottky barrier diodes thermal runaway has to be considered, as in some applications the reverse power losses PR are a significant part of the total power losses.' Single grade (no suffix-dependent temperature grade); ',115' is the packing suffix."
}

# 2 BAT54S-7-F
out["BAT54S-7-F"] = {
    "manufacturer": "Diodes Incorporated",
    "designators": "D18-D20",
    "datasheet": ds("BAT54 /A /C /S Surface-Mount Schottky Barrier Diode", "DS11005", "Rev. 34 - 2, November 2023",
                    "https://www.diodes.com/assets/Datasheets/ds11005.pdf", "50b04e4e17bcf5db", f"{B}/bat54s/ds11005.pdf"),
    "ratings": [
        rt("TJ, TSTG range", [-65, 150], "junction (operating) and storage", "absolute maximum (Thermal Characteristics table)", "PDF p2 / printed 2 of 5",
           "Operating and Storage Temperature Range (Note 7) TJ, TSTG -65 to +150 °C"),
    ],
    "thermal": [
        th("RθJA", 500, "typical; part mounted on FR-4 board with recommended pad layout (Note 5)", "PDF p2 / printed 2 of 5",
           "Typical Thermal Resistance Junction to Ambient Air (Note 5) RθJA 500 °C/W"),
        th("RθJC", 180, "typical; device mounted on polyimide substrate PC board, FR-4 2oz 1*MRP layout (Note 6)", "PDF p2 / printed 2 of 5",
           "Typical Thermal Resistance Junction to Case (Note 6) RθJC 180 °C/W"),
    ],
    "electrical": [
        el("PD", 200, "mW", "TA = +25 °C, FR-4 recommended pad (Note 5); Fig. 4 derates linearly from 200 mW at 25 °C to 0 at 150 °C", "PDF p2 / printed 2 of 5; Fig. 4 PDF p3",
           "Power Dissipation (Note 5) PD 200 mW"),
        el("VF max", 240, "mV", "IF = 0.1 mA, TA = 25 °C", "PDF p2"),
        el("VF max", 320, "mV", "IF = 1 mA, TA = 25 °C", "PDF p2", "— — 320 IF = 1mA"),
        el("VF max", 400, "mV", "IF = 10 mA, TA = 25 °C", "PDF p2", "Forward Voltage VF — — 400 mV IF = 10mA"),
        el("VF max", 500, "mV", "IF = 30 mA, TA = 25 °C", "PDF p2"),
        el("VF max", 800, "mV", "IF = 100 mA, TA = 25 °C", "PDF p2", "— — 800 IF = 100mA"),
        el("IR max", 2.0, "µA", "VR = 25 V, TA = 25 °C (Note 8 short pulse)", "PDF p2", "Reverse Leakage Current (Note 8) IR — — 2.0 µA VR = 25V"),
        el("IR typ at 125 °C", None, "µA", "NO MAX TABULATED; Fig. 2 typical curve TA = 125 °C reads roughly 70-80 µA at VR = 25 V (graph read)", "PDF p3 Fig. 2"),
        el("IO", 200, "mA", "average rectified output current (Note 5)", "PDF p2"),
        el("IFRM", 300, "mA", "repetitive peak forward current", "PDF p2"),
        el("IFSM", 600, "mA", "t < 1.0 s", "PDF p2"),
    ],
    "notes": "Ratings table does not state whether PD/RθJA are per diode or per package for the dual (S = series pair) variant. The PD derating curve (200 mW at 25 °C to 0 at 150 °C = 1.6 mW/K, i.e. 625 K/W) is NOT consistent with the 'typical' RθJA of 500 °C/W (which would give 250 mW at 25 °C); for a conservative self-heat use 625 K/W, or 500 K/W as the stated typical. Note 7: 'The heat generated must be less than the thermal conductivity from Junction-to-Ambient: dPD / dTJ < 1 / RθJA.' Single commercial grade; automotive variant is BAT54SQ (separate datasheet). '-7-F' is 3k tape-and-reel, lead-free."
}

# 3 BAS116H
out["BAS116H,115"] = {
    "manufacturer": "Nexperia",
    "designators": "D4, D5",
    "datasheet": ds("BAS116H Low leakage switching diode, Product data sheet", "BAS116H v.3", "Rev. 3, 31 May 2011 (Nexperia-branded reissue, © 2017)",
                    "https://datasheet.lcsc.com/datasheet/pdf/3effef0d92ac4111bb2691a2d714473d.pdf?productCode=C74210 (LCSC copy; assets.nexperia.com returned HTTP 403)",
                    "04966fbaa922997c", f"{B}/bas116h/BAS116H_lcsc_C74210.pdf"),
    "ratings": [
        rt("Tj max", 150, "junction", "absolute maximum (Limiting values, IEC 60134)", "PDF p2 / printed 2 of 10",
           "Tj junction temperature - 150 °C"),
        rt("Tamb range", [-65, 150], "ambient", "absolute maximum (Limiting values)", "PDF p2 / printed 2 of 10",
           "Tamb ambient temperature −65 +150 °C"),
        rt("Tstg range", [-65, 150], "storage", "absolute maximum (Limiting values)", "PDF p2 / printed 2 of 10",
           "Tstg storage temperature −65 +150 °C"),
    ],
    "thermal": [
        th("Rth(j-a)", 330, "in free air; FR4 PCB, single-sided copper, tin-plated, standard footprint; reflow only", "PDF p3 / printed 3 of 10",
           "Rth(j-a) thermal resistance from junction to ambient in free air [1][2] - - 330 K/W"),
        th("Rth(j-sp)", 70, "junction to soldering point of cathode tab", "PDF p3 / printed 3 of 10",
           "Rth(j-sp) thermal resistance from junction to solder point [3] - - 70 K/W"),
    ],
    "electrical": [
        el("Ptot", 375, "mW", "Tamb ≤ 25 °C, FR4 standard footprint", "PDF p2", "Ptot total power dissipation Tamb ≤ 25 °C [1][4] - 375 mW"),
        el("IR max", 5.0, "nA", "VR = 75 V, Tamb = 25 °C (typ 0.003 nA)", "PDF p3 / printed 3 of 10", "IR reverse current VR = 75 V - 0.003 5.0 nA"),
        el("IR max", 80.0, "nA", "VR = 75 V; Tj = 150 °C (typ 3 nA)", "PDF p3 / printed 3 of 10", "VR = 75 V; Tj = 150 °C - 3 80.0 nA"),
        el("VF max", [0.90, 1.00, 1.10, 1.25], "V", "IF = 1 / 10 / 50 / 150 mA, Tamb = 25 °C, pulsed", "PDF p3"),
        el("IF max", 215, "mA", "FR4 standard footprint, pulse test", "PDF p2"),
        el("IFRM", 500, "mA", "repetitive peak forward current", "PDF p2"),
        el("IFSM", [4, 1, 0.5], "A", "square wave tp = 1 µs / 1 ms / 1 s, Tj = 25 °C prior to surge", "PDF p2"),
    ],
    "notes": "pdftotext drops some glyphs (≤, −, µ) in this LCSC copy; values checked against layout. Fig. 3 (PDF p4) gives IR vs Tj (max and typ) at VR = 75 V up to 150 °C+. Single grade; ',115' is packing."
}

# 4 30KPA150CA
out["30KPA150CA"] = {
    "manufacturer": "Good-Ark Semiconductor (per task); NOTE the BOM LCSC code C19111562 resolves to Littelfuse 30KPA150CA - both datasheets recorded",
    "designators": "D3, D17",
    "datasheet": ds("30KPA28A thru 30KPA320CA Transient Voltage Suppressors, Peak Pulse Power 30KW Stand-off Voltage 28V to 320V",
                    "Doc.US30KPA28A-30KPA320CAxSM5.0", "Jan.2020 (PDF ModDate 2021-07-13)",
                    "https://goodarksemi.com/docs/datasheets/transient_voltage_suppressors/30KPA28A-30KPA320CA.pdf",
                    "7700d2c23b98a681", f"{B}/30kpa/30KPA28A-30KPA320CA.pdf"),
    "ratings": [
        rt("TJ, TSTG range", [-55, 150], "junction (operating) and storage", "absolute maximum", "PDF p1 / printed 1/4",
           "Operating Junction and Storage Temperature Range TJ, TSTG –55 to +150 °C"),
    ],
    "thermal": [
        th("RθJL / RθJA", None, "NOT LISTED in Good-Ark datasheet. Implied by Fig. 3 (steady-state derating, graph read): 8.0 W flat to TL = 75 °C, linear to 0 W at TL = 175 °C, i.e. 80 mW/K -> 12.5 K/W junction-to-lead if the 175 °C end point is taken as TJ; this end point conflicts with the 150 °C TJ rating.", "PDF p4 Fig. 3", "Fig. 3 - Steady State Power Derating Curve"),
    ],
    "electrical": [
        el("PD steady state", 8.0, "W", "on infinite heatsink at TL = 75 °C", "PDF p1 / printed 1/4", "Power Dissipation on Infinite Heatsink at TL = 75 °C PD 8.0 W"),
        el("PPP", 30000, "W", "10/1000 µs waveform, TA = 25 °C, derated above TA = 25 °C per Fig. 1", "PDF p1", "Peak Power Dissipation with a 10/1000 s Waveform PPP 30000 W"),
        el("Pulse derating (Fig. 1)", "100 % to TA = 25 °C, linear to 0 % at TA = 175 °C (graph read)", None, "peak pulse power or current vs ambient temperature", "PDF p4 Fig. 1"),
        el("Steady-state derating (Fig. 3)", "8.0 W to TL = 75 °C, linear to 0 W at TL = 175 °C (graph read)", None, "steady-state power vs lead temperature", "PDF p4 Fig. 3"),
        el("VRWM / VBR min / IR max / IPP / VC", {"VRWM_V": 150, "VBR_min_V": 167.60, "IT_mA": 5, "IR_max_uA": 2, "IPP_A": 129.8, "VC_V": 233.4}, None, "30KPA150CA row, TA = 25 °C", "PDF p3", "30KPA150A 30KPA150CA 167.60 5 2 150 129.8 233.4"),
    ],
    "alt_littelfuse": {
        "datasheet": ds("TVS Diode Axial Leaded – 30000W > 30KPA series", "Littelfuse 30KPA series", "Revised: BA.08/27/20",
                        "https://datasheet.lcsc.com/datasheet/pdf/57dafd23127752bd1f25d2838c3c3386.pdf?productCode=C19111562 (LCSC copy for C19111562)",
                        "1fe25d7c0973063d", f"{B}/30kpa-littelfuse/30KPA_littelfuse_lcsc_C19111562.pdf"),
        "ratings": [rt("TJ, TSTG range", [-55, 175], "junction (operating) and storage", "absolute maximum (Maximum Ratings and Thermal Characteristics)", "PDF p1",
                       "Operating Junction and Storage Temperature Range TJ , TSTG -55 to 175 °C")],
        "thermal": [
            th("RθJL", 8.0, "typical, junction to lead", "PDF p1", "Typical Thermal Resistance Junction to Lead RθJL 8.0 °C/W"),
            th("RθJA", 40, "typical, junction to ambient (mounting not stated)", "PDF p1", "Typical Thermal Resistance Junction to Ambient RθJA 40 °C/W"),
        ],
        "electrical": [
            el("PD steady state", 8.0, "W", "on infinite heat sink at TL = 75 °C", "PDF p1", "Steady State Power Dissipation on Infinite Heat Sink at TL=75ºC PD 8.0 W"),
            el("PPPM", 30, "kW", "10/1000 µs, derated above TJ(initial) = 25 °C per Fig. 3", "PDF p1"),
            el("Pulse derating (Fig. 3)", "100 % to TJ(initial) = 25 °C, linear to ~50 % at 175 °C, then 0 (graph read)", None, "peak pulse power vs initial junction temperature", "PDF p4 Fig. 3"),
            el("IFSM", 400, "A", "8.3 ms single half sine, uni-directional only", "PDF p1"),
            el("30KPA150CA row", {"VR_V": 150, "VBR_min_V": 167.60, "VBR_max_V": 184.36, "IT_mA": 5, "IPP_A": 129.8, "IR_max_uA": 2, "VC_V": 233.4}, None, "TA = 25 °C", "PDF p2"),
        ],
        "notes": "No steady-state-vs-lead-temperature derating curve in the Littelfuse sheet; Fig. 6 typical transient thermal impedance saturates near ~40 °C/W (graph read)."
    },
    "notes": "MANUFACTURER AMBIGUITY: the BOM row ('58,\"D3,D17\",2,10,1000,30KPA150CA,C19111562') carries LCSC C19111562, which LCSC's API reports as brand Littelfuse; the sourcing study notes 'DK Good-Ark listing (stock n/s); Littelfuse 800 T&R'. Good-Ark rates TJ -55..+150 °C with no RθJL; Littelfuse rates TJ -55..+175 °C with RθJL 8 °C/W typ. Use the 150 °C Good-Ark limit unless the buy is confirmed Littelfuse. Good-Ark derating curves end at 175 °C despite the 150 °C TJ rating (internal inconsistency in the Good-Ark sheet)."
}

# 5 TI logic
def lvc(mpn, title, doc, rev, base, sha, page_ta, page_th, page_icc, rth, rth_quote, rth_basis, extra_notes):
    return {
        "manufacturer": "Texas Instruments",
        "datasheet": ds(title, doc, rev, f"https://www.ti.com/lit/ds/symlink/{base}.pdf", sha, f"{B}/{base}/{base}.pdf"),
        "ratings": [
            rt("TA range", [-40, 125], "free-air ambient", "recommended operating", page_ta, "TA Operating free-air temperature –40 125 °C"),
            rt("TJ max", None, "junction", "absolute maximum", None, "NOT LISTED: the Absolute Maximum Ratings table has Tstg –65..150 °C but no TJ row"),
            rt("Tstg range", [-65, 150], "storage", "absolute maximum", page_ta.replace("p5", "p4").replace("p3", "p2"), "Storage temperature –65 150 °C"),
        ],
        "thermal": [th("RθJA", rth, rth_basis, page_th, rth_quote)],
        "electrical": [
            el("ICC max", 10, "µA", "VI = VCC (or 5.5 V) or GND, IO = 0, VCC = 1.65 V to 5.5 V; same 10 µA in both the –40..85 °C and –40..125 °C columns", page_icc, "ICC VI = 5.5V or GND IO = 0 1.65V to 5.5V 10 10 μA"),
            el("ΔICC max", 500, "µA", "one input at VCC – 0.6 V, others at VCC or GND, VCC = 3 V to 5.5 V", page_icc),
        ],
        "notes": extra_notes,
    }

out["SN74LVC1G00DBVR"] = lvc("SN74LVC1G00DBVR", "SN74LVC1G00 Single 2-Input Positive-NAND Gate", "SCES212AC", "AC, April 1999 – revised August 2026", "sn74lvc1g00", "1264f79853e6119b",
    "PDF p5 / printed 5", "PDF p5 / printed 5", "PDF p6 / printed 6", 357.1, "DBV (SOT-23) 5 357.1 263.7 264.4 195.6 262.2 - °C/W", "JEDEC thermal metric table, DBV 5-pin; RθJB 264.4, ΨJB 262.2",
    "Orderable addendum (PDF p19) lists SN74LVC1G00DBVR op temp '-40 to 125'. Section 8.2.1 (PDF p13) refers to 'TJ(max) listed in the Absolute Maximum Ratings' but no such row exists in this revision. Revision history: DBV RθJA changed 229 -> 357.1 °C/W.")
out["SN74LVC1G10DBVR"] = lvc("SN74LVC1G10DBVR", "SN74LVC1G10 Single 3-Input Positive-NAND Gate", "SCES486E", "E, September 2003 – revised December 2013", "sn74lvc1g10", "4902c8770413a400",
    "PDF p3 / printed 3", "PDF p2 / printed 2", "PDF p4 / printed 4", 165, "θJA Package thermal impedance (4) DBV package 165 °C/W ... (4) The package thermal impedance is calculated in accordance with JESD 51-7.", "listed in Absolute Maximum Ratings table; JESD 51-7 calculation; DBV here is the 6-pin SOT-23",
    "Old-format (2013) datasheet: θJA 165 °C/W is in the Abs Max table, not a JEDEC thermal-metric table. Newer TI LVC1G sheets for the same DBV family list 357.1 °C/W (1G00/1G17/1G132 revision histories record DBV changed 229/206 -> 357.1) - 165 °C/W is likely optimistic; consider 357 °C/W conservatively. DBV is 6-pin for this device (orderable addendum PDF p9: 'SOT-23 (DBV) | 6 ... -40 to 125').")
out["SN74LVC1G332DBVR"] = lvc("SN74LVC1G332DBVR", "SN74LVC1G332 Single 3-Input Positive-OR Gate", "SCES489E", "E, September 2003 – revised December 2013", "sn74lvc1g332", "5ecad3180cb93664",
    "PDF p3 / printed 3", "PDF p2 / printed 2", "PDF p4 / printed 4", 165, "θJA Package thermal impedance (4) DBV package 165 °C/W ... calculated in accordance with JESD 51-7.", "listed in Absolute Maximum Ratings table; JESD 51-7 calculation; DBV 6-pin SOT-23",
    "Same old-format caveat as SN74LVC1G10 (165 °C/W vs 357.1 °C/W in current LVC1G sheets). Orderable addendum PDF p9: 'SOT-23 (DBV) | 6 ... -40 to 125'.")
out["SN74LVC1G17DBVR"] = lvc("SN74LVC1G17DBVR", "SN74LVC1G17 Single Schmitt-Trigger Buffer", "SCES351Y", "Y, July 2001 – revised October 2025", "sn74lvc1g17", "c76fa723fac45024",
    "PDF p5 / printed 5", "PDF p5 / printed 5", "PDF p6 / printed 6", 357.1, "RθJA Junction-to-ambient thermal resistance 357.1 (DBV column)", "JEDEC thermal metric table, DBV 5-pin",
    "ICC row on p6: 'VI = 5.5V or GND, IO = 0, 1.65V to 5.5V ... 10 10 μA' (–40..85 and –40..125 columns); a 25 °C typ/max of 0.5/1.5 µA at VI = 3.6 V, VCC 3-3.6 V is also listed. Orderable addendum PDF p15 '-40 to 125'. Revision history: DBV RθJA changed 229 -> 357.1.")
out["SN74LVC1G132DBVR"] = lvc("SN74LVC1G132DBVR", "SN74LVC1G132 Single 2-Input NAND Gate With Schmitt-Trigger Inputs", "SCES546E", "E, February 2004 – revised August 2026", "sn74lvc1g132", "fae33d78fe46834a",
    "PDF p5 / printed 5", "PDF p5 / printed 5", "PDF p6 / printed 6", 357.1, "DBV (SOT-23) 5 357.1 263.7 264.4 195.6 262.2 - °C/W", "JEDEC thermal metric table, DBV 5-pin; RθJB 264.4, ΨJB 262.2",
    "Orderable addendum PDF p19 '-40 to 125'. Revision history: DBV RθJA changed 206 -> 357.1. Section 8 references a TJ(max) in Abs Max that is not present.")
for k in ["SN74LVC1G00DBVR", "SN74LVC1G17DBVR", "SN74LVC1G132DBVR"]:
    out[k]["ratings"][2]["page"] = "PDF p4 / printed 4"
for k in ["SN74LVC1G10DBVR", "SN74LVC1G332DBVR"]:
    out[k]["ratings"][2]["page"] = "PDF p2 / printed 2"
    out[k]["electrical"][0]["quote"] = "ICC VI = 5.5 V or GND, IO = 0 ... 10 ... 10 μA"

# 6 TPS70950DBVR
out["TPS70950DBVR"] = {
    "manufacturer": "Texas Instruments",
    "designators": "U3, U37, U38, U39",
    "datasheet": ds("TPS709 150-mA, 30-V, 1-µA IQ Voltage Regulators With Enable", "SBVS186H", "H, March 2012 – revised July 2021",
                    "https://www.ti.com/lit/ds/symlink/tps709.pdf", "8c14e3efae738a27", f"{R}/s47/dl/ti_tps709.pdf"),
    "ratings": [
        rt("TJ range", [-40, 125], "junction", "recommended operating", "PDF p4 / printed 4", "TJ Operating junction temperature –40 125 °C"),
        rt("TJ range (abs max)", [-55, 150], "junction", "absolute maximum", "PDF p4 / printed 4", "Operating junction temperature, TJ –55 150 °C"),
        rt("Tstg range", [-55, 150], "storage", "absolute maximum", "PDF p4 / printed 4", "Storage temperature, Tstg –55 150 °C"),
    ],
    "thermal": [
        th("RθJA", 212.1, "DBV 5-pin, JEDEC thermal metric", "PDF p4 / printed 4", "RθJA Junction-to-ambient thermal resistance 212.1 73.1 °C/W (DBV, DRV)"),
        th("RθJB", 39.5, "DBV", "PDF p4 / printed 4", "RθJB Junction-to-board thermal resistance 39.5"),
        th("ψJB", 38.7, "DBV", "PDF p4 / printed 4", "ψJB Junction-to-board characterization parameter 38.7"),
        th("RθJC(top)", 78.5, "DBV", "PDF p4 / printed 4", "RθJC(top) Junction-to-case (top) thermal resistance 78.5"),
    ],
    "electrical": [
        el("IGND max", 2.25, "µA", "IOUT = 0 mA, VOUT > 3.3 V (typ 1.4); TA = –40 °C to +85 °C table", "PDF p5 / printed 5", "IGND Ground pin current IOUT = 0 mA, VOUT > 3.3 V 1.4 2.25 µA"),
        el("IGND typ", 350, "µA", "IOUT = 150 mA (no max)", "PDF p5 / printed 5", "IOUT = 150 mA 350"),
        el("Thermal shutdown", {"trip_typ_C": 158, "reset_typ_C": 140}, "°C", "temperature increasing / decreasing, typical", "PDF p5 / printed 5", "Thermal shutdown temperature Shutdown, temperature increasing 158 ... Reset, temperature decreasing 140 °C"),
        el("VDO", {"typ_mV_50mA": 245, "max_mV_50mA": 500, "typ_mV_150mA": 690, "max_mV_150mA": 1200}, "mV", "TPS70950", "PDF p5"),
        el("I(CL)", [200, 320, 500], "mA", "min/typ/max, VOUT = 0.9 × VOUT(nom)", "PDF p5"),
    ],
    "notes": "Electrical Characteristics table (p5) is specified 'at ambient temperature (TA) = –40°C to +85°C'; recommended operating condition is TJ –40..125 °C; orderable addendum (PDF p24) 'TPS70950DBVR ... -40 to 125'. Local copy reused (not re-downloaded)."
}

# 7 TLV3201AIDBVR
out["TLV3201AIDBVR"] = {
    "manufacturer": "Texas Instruments",
    "designators": "U6, U7, U10, U11, U12",
    "datasheet": ds("TLV320x 40ns, microPOWER, Push-Pull Output Comparators (TLV3201, TLV3202)", "SBOS561C", "C, March 2012 – revised May 2024",
                    "https://www.ti.com/lit/ds/symlink/tlv3201.pdf", "1777bba814c74772", f"{B}/tlv3201/tlv3201.pdf"),
    "ratings": [
        rt("Specified temperature range", [-40, 125], "specified (ambient; EC tables use TA)", "recommended operating", "PDF p4 / printed 4", "Specified temperature –40 125 °C"),
        rt("Operating temperature range (abs max)", [-55, 125], "operating (ambient implied)", "absolute maximum", "PDF p4 / printed 4", "Temperature Operating –55 125"),
        rt("TJ max", 150, "junction", "absolute maximum", "PDF p4 / printed 4", "Junction, TJ 150 °C"),
        rt("Tstg range", [-65, 150], "storage", "absolute maximum", "PDF p4 / printed 4", "Storage, Tstg –65 150"),
    ],
    "thermal": [
        th("RθJA", 237.8, "DBV (SOT-23) 5 pins, JEDEC metric", "PDF p4 / printed 4", "RθJA Junction-to-ambient thermal resistance 237.8 281.9 143.6 201.9 °C/W (DBV, DCK, D, DGK)"),
        th("RθJB", 64.1, "DBV", "PDF p4 / printed 4", "RθJB Junction-to-board thermal resistance 64.1"),
        th("ψJB", 63.3, "DBV", "PDF p4 / printed 4", "ψJB Junction-to-board characterization parameter 63.3"),
    ],
    "electrical": [
        el("IQ max", 50, "µA", "VCC = 5 V, TA = 25 °C (typ 40)", "PDF p5 / printed 5", "IQ Quiescent current TA = 25°C 40 50"),
        el("IQ max", 65, "µA", "VCC = 5 V, TA = –40 °C to 125 °C", "PDF p5 / printed 5", "TA = –40°C to 125°C 65"),
        el("IQ max", 46, "µA", "VCC = 2.7 V, TA = 25 °C (typ 36)", "PDF p6 / printed 6"),
        el("IQ max", 60, "µA", "VCC = 2.7 V, TA = –40 °C to 125 °C", "PDF p6 / printed 6"),
    ],
    "notes": "TLV3201 has a single industrial grade 'AI'; orderable addendum PDF p23: 'TLV3201AIDBVR Active Production SOT-23 (DBV) | 5 ... -40 to 125'. Datasheet features: 'expanded industrial temperature range of –40°C to 125°C'. Push-pull output: output-stage dissipation depends on load and switching (not part of IQ)."
}

# 8 TPS3700DDCR
out["TPS3700DDCR"] = {
    "manufacturer": "Texas Instruments",
    "designators": "U14",
    "datasheet": ds("TPS3700 High voltage (18V) window voltage detector with internal reference for over and undervoltage monitoring", "SBVS187G", "G, February 2012 – revised February 2019",
                    "https://www.ti.com/lit/ds/symlink/tps3700.pdf", "3bb7daed20b154bf", f"{R}/s16-fmea-b-dl/tps3700/tps3700.pdf"),
    "ratings": [
        rt("TJ range", [-40, 125], "junction", "absolute maximum ('Operating junction temperature' row in Abs Max table)", "PDF p5 / printed 5", "Operating junction temperature, TJ –40 125 °C"),
        rt("TJ range (EC spec)", [-40, 125], "junction", "electrical characteristics specified range", "PDF p6 / printed 6", "Over the operating temperature range of TJ = –40°C to 125°C, and 1.8 V < VDD < 18 V"),
        rt("Tstg range", [-65, 150], "storage", "absolute maximum", "PDF p5 / printed 5", "Storage temperature, Tstg –65 150 °C"),
    ],
    "thermal": [
        th("RθJA", 204.6, "DDC (SOT) 6 pins, JEDEC metric", "PDF p5 / printed 5", "RθJA Junction-to-ambient thermal resistance 204.6 194.9 °C/W (DDC, DSE)"),
        th("RθJB", 54.3, "DDC", "PDF p5 / printed 5", "RθJB Junction-to-board thermal resistance 54.3"),
        th("ψJB", 52.8, "DDC", "PDF p5 / printed 5", "ψJB Junction-to-board characterization parameter 52.8"),
    ],
    "electrical": [
        el("IDD max", [11, 13, 13, 13], "µA", "VDD = 1.8 V (no load) / 5 V / 12 V / 18 V; typ 5.5 / 6 / 6 / 7; TJ –40..125 °C", "PDF p6 / printed 6", "IDD Supply current VDD = 1.8 V, no load 5.5 11; VDD = 5 V 6 13; VDD = 12 V 6 13; VDD = 18 V 7 13 µA"),
        el("VOL max", 250, "mV", "VDD = 5 V, IO = 5 mA (also 1.8 V/3 mA)", "PDF p6"),
        el("Output terminal current abs max", 40, "mA", "OUTA, OUTB", "PDF p5"),
    ],
    "notes": "The Recommended Operating Conditions table (p5) lists only VDD, VI, VO - no TA or TJ row; the only temperature limits are the Abs Max 'Operating junction temperature -40..125 °C' and the EC conditions TJ -40..125 °C. No TA range stated; orderable addendum (PDF p23) 'TPS3700DDCR ... -40 to 125'. Local copy reused."
}

# 9 TPS7A4700RGWR
out["TPS7A4700RGWR"] = {
    "manufacturer": "Texas Instruments",
    "designators": "U26",
    "datasheet": ds("TPS7A470x 36V, 1A, 4µVRMS, RF LDO Voltage Regulator", "SBVS204G", "G, June 2012 – revised May 2026",
                    "https://www.ti.com/lit/ds/symlink/tps7a47.pdf", "8ca46a9968923d2e", f"{R}/s16-monitor-dl/tps7a47.pdf"),
    "ratings": [
        rt("TJ range (abs max)", [-40, 125], "junction ('operating virtual junction')", "absolute maximum", "PDF p4 / printed 4", "Temperature Operating virtual junction, TJ –40 125 °C"),
        rt("TJ range", [-40, 125], "junction", "electrical characteristics ('Operating junction temperature' row)", "PDF p6 / printed 6", "TJ Operating junction temperature –40 125 °C"),
        rt("Tstg range", [-65, 150], "storage", "handling ratings", "PDF p5 / printed 5", "Tstg Storage temperature range –65 150 °C"),
    ],
    "thermal": [
        th("RθJA", 32.5, "RGW 20-pin VQFN, JEDEC metric", "PDF p5 / printed 5", "RθJA Junction-to-ambient thermal resistance 32.5"),
        th("RθJB", 11.9, "RGW", "PDF p5 / printed 5", "RθJB Junction-to-board thermal resistance 11.9"),
        th("ψJB", 11.9, "RGW", "PDF p5 / printed 5", "ψJB Junction-to-board characterization parameter 11.9"),
        th("RθJC(top)", 27, "RGW", "PDF p5 / printed 5", "RθJC(top) Junction-to-case (top) thermal resistance 27"),
        th("ψJT", 0.3, "RGW", "PDF p5 / printed 5", "ψJT Junction-to-top characterization parameter 0.3"),
        th("RθJC(bot)", 1.7, "RGW", "PDF p5 / printed 5", "RθJC(bot) Junction-to-case (bottom) thermal resistance 1.7"),
    ],
    "electrical": [
        el("I(GND) max", 1.0, "mA", "IO = 0 mA (typ 0.58); –40 °C ≤ TJ ≤ 125 °C", "PDF p6 / printed 6", "I(GND) Ground pin current IO = 0 mA 0.58 1.0 mA"),
        el("I(GND) typ", 6.1, "mA", "IO = 1 A (no max)", "PDF p6 / printed 6", "IO = 1 A 6.1 mA"),
        el("Tsd", {"trip_typ_C": 170, "reset_typ_C": 150}, "°C", "shutdown temperature increasing / reset decreasing, typical", "PDF p6 / printed 6", "Tsd Thermal shutdown temperature Shutdown, temperature increasing 170 °C; Reset, temperature decreasing 150 °C"),
        el("V(DO)", {"typ_mV_0p5A": 216, "typ_mV_1A": 307, "max_mV_1A": 450}, "mV", "VI = 95 % VO(nom)", "PDF p6"),
        el("I(CL)", {"min_A": 1, "typ_A": 1.26}, "A", "VO = 90 % VO(nom)", "PDF p6"),
    ],
    "notes": "The absolute-maximum TJ is the same as the operating range: –40..125 °C ('Operating virtual junction' in Abs Max); there is no separate 150 °C abs-max TJ. Recommended Operating Conditions (p5) lists VI/VO/VEN/IO only. Thermal shutdown (170 °C typ) is above the 125 °C abs max. Orderable addendum PDF p24 'TPS7A4700RGWR ... -40 to 125'. Local copy reused."
}

# 10 TLVH431BQDBZR
out["TLVH431BQDBZR"] = {
    "manufacturer": "Texas Instruments",
    "designators": "U16, U18, U20",
    "datasheet": ds("TLVH431, TLVH432 Low-Voltage Adjustable Precision Shunt Regulators", "SLVS555N", "N, November 2004 – revised June 2024",
                    "https://www.ti.com/lit/ds/symlink/tlvh431.pdf", "e30d628cb6475d48", f"{R}/s16-monitor-dl/tlvh431.pdf"),
    "ratings": [
        rt("TA range (Q grade)", [-40, 125], "free-air ambient", "recommended operating", "PDF p5 / printed 5", "TA Operating free-air temperature ... TLVH43x_Q –40 125"),
        rt("TJ max", 150, "junction ('operating virtual junction')", "absolute maximum", "PDF p5 / printed 5", "TJ Operating virtual junction temperature 150 °C"),
        rt("Tstg range", [-65, 150], "storage", "absolute maximum", "PDF p5 / printed 5", "Tstg Storage temperature –65 150 °C"),
    ],
    "thermal": [
        th("RθJA", 206, "DBZ (SOT-23) 3 pins", "PDF p5 / printed 5", "RθJA Junction-to-ambient thermal resistance 259 52 206 206 140 °C/W (DCK, PK, DBV, DBZ, LP)"),
        th("RθJC(top)", 76, "DBZ", "PDF p5 / printed 5", "RθJC(top) Junction-to-case (top) thermal resistance ... 76 (DBZ)"),
    ],
    "electrical": [
        el("IK continuous", [0.1, 70], "mA", "recommended operating min/max", "PDF p5"),
        el("VKA", ["VREF", 18], "V", "recommended operating", "PDF p5"),
        el("IK(min) for regulation", {"typ_uA": 60, "max_uA": 100}, "µA", "VKA = VREF, TLVH43xB", "PDF p8 / printed 8"),
        el("VREF (BQ, full range)", [1.221, 1.265], "V", "VKA = VREF, IK = 10 mA, TA = –40..125 °C", "PDF p8 / printed 8"),
    ],
    "notes": "Suffix grade confirmed: 'BQ' = B (0.5 %) tolerance, Q temperature grade. Footnote PDF p8: 'Full temperature ranges are –40°C to +125°C for TLVH431Q'; p13: 'the TLVH431xQ devices are characterized for operation from –40°C to +125°C'; orderable addendum PDF p28: 'TLVH431BQDBZR Active Production SOT-23 (DBZ) | 3 3000 ... -40 to 125'. Self-dissipation = VKA × IK (circuit-set). ROC footnote: 'PD = (TJ(max) – TA) / θJA. Operating at the absolute maximum TJ of 150°C can affect reliability.' Local copy reused."
}

json.dump(out, open("/Users/bennet/.claude/jobs/fbfc46b4/tmp/temp-ratings/ds/semis_a.json", "w"), indent=1, ensure_ascii=False)
print(len(out), "MPNs written")
