import json
P = "/Users/bennet/Desktop/temper/worktrees/runs-native21/s47/temp-ratings-dl/passives"
out = {}

# ---------- UniRoyal ----------
uni_ds = {"title": "UniRoyal (Uniroyal Electronics) Thick Film Chip Resistors Data Sheet, 01005/0201/0402/0603/0805/1206/1210/1812/2010/2512 Series",
          "revision": "V.3, Feb.12,2019",
          "url": "https://datasheet.lcsc.com/datasheet/pdf/0a975aaa49b7c97f38a963127be4a823.pdf",
          "sha256_prefix16": "11cd644d5d8a34a6",
          "local": "/Users/bennet/Desktop/temper/worktrees/runs-native21/s42/dl/uniroyal-25121WF680JT4E.pdf (byte-identical copy: " + P + "/uniroyal-1206/uniroyal-1206W4F.pdf)"}
uni_quote_op = "Ratings table: '0603  75V  150V  300V  <50mΩ  1A  2A  -55℃~155℃' / '1206  200V  400V  500V  <50mΩ  2A  10A  -55℃~155℃'; Derating: 'Resistors shall have a power rating based on continuous load operation at an ambient temperature from -55℃ to 70℃. For temperature in excess of 70℃, the load shall be derated as shown in figure 1'"
uni_der = "Ambient-temperature derating (Figure 1, curve '0201~2512'): 100 % rated power from -55 C to 70 C, linear to 0 % at 155 C. No terminal/film-temperature derating published."
r0603 = {"0603WAF1000T5E": "100 ohm", "0603WAF1003T5E": "100 kohm", "0603WAF4991T5E": "4.99 kohm", "0603WAF1002T5E": "10 kohm",
         "0603WAF5601T5E": "5.6 kohm", "0603WAF1001T5E": "1 kohm", "0603WAF2702T5E": "27 kohm", "0603WAF2200T5E": "220 ohm", "0603WAF3302T5E": "33 kohm"}
for mpn, val in r0603.items():
    out[mpn] = {"manufacturer": "UniRoyal (Uniroyal Electronics Global)", "datasheet": uni_ds,
        "temp_max_c": 155, "temp_min_c": -55, "applies_to": "operating temperature range; power rating and derating referenced to AMBIENT temperature",
        "page": "PDF p5 (printed 'Page 5/9'): ratings table (operating temperature) and section 9 derating curve; PDF p4 (printed 'Page 4/9'): power rating at 70 C",
        "quote": uni_quote_op, "power_rated_w": 0.1,
        "derating": uni_der + " Line: P = 0.1 W x (155 - Ta)/85 for 70 < Ta <= 155 C.",
        "other": f"{val}, 1 %, thick film; code WA = 1/10 W (p1 part-number table). Max working voltage 75 V, max overload 150 V, dielectric withstanding 300 V (p5).",
        "series_level": True, "notes": "Series datasheet, not part-specific; value decoded per the datasheet's part-number rules (p1)."}
out["0603WAF0000T5E"] = {"manufacturer": "UniRoyal (Uniroyal Electronics Global)", "datasheet": uni_ds,
    "temp_max_c": 155, "temp_min_c": -55, "applies_to": "operating temperature range (ambient)",
    "page": "PDF p5 (printed 'Page 5/9'), section 7 Ratings",
    "quote": "'0603  75V  150V  300V  <50mΩ  1A  2A  -55℃~155℃' (columns: Max. Working Voltage, Max. Overload Voltage, Dielectric withstanding Voltage, Resistance Value of Jumper, Rated Current of Jumper, Max. Overload Current of Jumper, Operating Temperature)",
    "power_rated_w": None,
    "derating": "No current-vs-temperature derating published for the jumper; the Figure 1 power derating (100 % at 70 C to 0 % at 155 C) is for resistors. Rated current 1 A is not stated with a temperature condition.",
    "other": "0 ohm jumper: resistance < 50 mohm, rated current 1 A, max overload current 2 A (p5).",
    "series_level": True, "notes": "Series datasheet. Jumper dissipation at 1 A is <= 50 mW (I^2 x 50 mohm)."}
r1206 = {"1206W4F1003T5E": "100 kohm", "1206W4F100KT5E": "1.00 ohm (code 100K: '100' significant figures x K = 10^-2, per p1 section 2.4.3)", "1206W4F1001T5E": "1 kohm"}
for mpn, val in r1206.items():
    out[mpn] = {"manufacturer": "UniRoyal (Uniroyal Electronics Global)", "datasheet": uni_ds,
        "temp_max_c": 155, "temp_min_c": -55, "applies_to": "operating temperature range; power rating and derating referenced to AMBIENT temperature",
        "page": "PDF p5 (printed 'Page 5/9'): ratings table and section 9 derating; PDF p4 (printed 'Page 4/9'): power rating at 70 C",
        "quote": uni_quote_op, "power_rated_w": 0.25,
        "derating": uni_der + " Line: P = 0.25 W x (155 - Ta)/85 for 70 < Ta <= 155 C.",
        "other": f"{val}, 1 %, thick film; code W4 = 1/4 W (p1). Resistance-range table p4: 1206 1/4 W covers 0.1 ohm <= R < 10 Mohm at 1 % (1/3 W only for 0.01-0.1 ohm). Max working voltage 200 V, overload 400 V (p5).",
        "series_level": True, "notes": "Series datasheet. The LCSC 1206W4F copy (0a975aaa...) is byte-identical to the s42 local file (same sha256)."}

# ---------- Yageo RT ----------
rt_ds = {"title": "Yageo Chip Resistor Surface Mount RT series 0100 to 2512 (thin film, high precision) Product specification",
         "revision": "V.16, May 06, 2025",
         "url": "https://datasheet.lcsc.com/datasheet/pdf/46d7760c582640714d605308a25a220a.pdf?productCode=C95204",
         "sha256_prefix16": "0a729d144519a702",
         "local": "/Users/bennet/Desktop/temper/worktrees/runs-native21/s45/dl/yageo_rt.pdf"}
for v in ["49K9", "15K8", "10K", "12K6", "140K", "1K", "2K21", "105K", "6K2", "4K42", "750R", "2K94", "90K9", "104K", "63K4", "11K"]:
    mpn = f"RT0603BRD07{v}L"
    out[mpn] = {"manufacturer": "Yageo", "datasheet": rt_ds,
        "temp_max_c": 155, "temp_min_c": -55, "applies_to": "operating temperature range; power rating and derating referenced to AMBIENT temperature (Tamb)",
        "page": "PDF p5 (printed 'Product specification 5'), Table 2; PDF p6 (printed 6), Power rating + Fig. 6",
        "quote": "Table 2: 'RT0603  1/10W 75V 150V' with Operating Temperature Range '–55°C to +155°C'; p6: 'Each type rated power at 70°C: ... RT0603=1/10W' / 'Fig. 6 Maximum dissipation (P) in percentage of rated power as a function of the operating ambient temperature (T amb)'",
        "power_rated_w": 0.1,
        "derating": "Fig. 6 curve 'RT0402~1206': 100 % to 70 C ambient, linear to 0 % at 155 C. P = 0.1 W x (155 - Ta)/85 for 70 < Ta <= 155 C. No terminal/film-temperature derating published.",
        "other": "B = +/-0.1 %, R = paper taping reel, D = 25 ppm/C, 07 = 7 inch reel (p2). Table 2: RT0603 +/-0.1 % at +/-25 ppm/C covers 1 ohm to 1 Mohm, so 750R..140K are in range. Max working 75 V, overload 150 V.",
        "series_level": True, "notes": "Series datasheet (LCSC copy filed under C95204, RT0603BRD0710KL)."}

# ---------- Yageo RC_L ----------
rc_ds = {"title": "Yageo Chip Resistor Surface Mount RC_L series 0075 to 2512 (thick film) Product specification",
         "revision": "V.12, August 02, 2022",
         "url": "https://datasheet.lcsc.com/datasheet/pdf/b426be3ce22c6de3e0c3a2248e49159e.pdf?productCode=C130275",
         "sha256_prefix16": "e7dbabb061192522",
         "local": P + "/yageo-rc/PYu-RC_Group_51_RoHS_L.pdf"}
for mpn, val in {"RC1206FR-07220KL": "220 kohm", "RC1206FR-073RL": "3 ohm", "RC1206FR-072K2L": "2.2 kohm", "RC1206FR-0716K5L": "16.5 kohm"}.items():
    out[mpn] = {"manufacturer": "Yageo", "datasheet": rc_ds,
        "temp_max_c": 155, "temp_min_c": -55, "applies_to": "operating temperature range; power rating and derating referenced to AMBIENT temperature (Tamb)",
        "page": "PDF p6 (printed 'Product specification 6'), Table 3 RC1206 row; PDF p7 (printed 7), Operating temperature range / Power rating / Fig. 10-1; PDF p2 for the '07' code",
        "quote": "Table 3 RC1206: '1/4 W  -55℃ to 155℃  200V  400V  500V'; p7: 'RC0402 to RC2512 Range: -55 to +155 (Fig. 10-1)' and 'Each type rated power at 70 : ... RC1206=1/4W, 1/2W'",
        "power_rated_w": 0.25,
        "derating": "Fig. 10-1: 100 % to 70 C ambient, linear to 0 % at 155 C. P = 0.25 W x (155 - Ta)/85 for 70 < Ta <= 155 C. No terminal/film-temperature derating published.",
        "other": f"{val}, F = +/-1 %, R = paper taping reel, '07 = 7 inch dia. Reel & Standard power' (p2), so the 1/4 W rating applies (1/2 W is the 7W/3W double-power code). 1 % range 1 ohm-10 Mohm; TCR +/-200 ppm/C for 1-10 ohm, +/-100 ppm/C above 10 ohm.",
        "series_level": True, "notes": "Series datasheet (LCSC copy filed under C130275 = RC1206FR-07220KL)."}

# ---------- Yageo RL ----------
rl_ds = {"title": "Yageo Chip Resistor Surface Mount RL series 0402 to 2512 (thick film, low ohmic) Product specification",
         "revision": "V.3, April 07, 2023",
         "url": "https://store.comet.bg/download-file.php?id=22105",
         "sha256_prefix16": "a222719aba346137",
         "local": P + "/yageo-rl/comet-22105.pdf"}
out["RL1206FR-070R68L"] = {"manufacturer": "Yageo", "datasheet": rl_ds,
    "temp_max_c": 155, "temp_min_c": -55, "applies_to": "operating temperature range (normal power); power rating and derating referenced to AMBIENT temperature (Tamb)",
    "page": "PDF p5 (printed 'Product specification 5'), Table 2 RL1206; PDF p6 (printed 6), Operating temperature range / Power rating / Fig. 5; PDF p2 for the '07' code",
    "quote": "Table 2 RL1206: '1/4W  -55°C to +155°C  10mΩ ≤ R < 1Ω'; p6: 'Normal Power: Range: –55 °C to +155 °C (Fig. 5)' / 'Double Power: Range: –55 °C to +125 °C (Fig. 6)' / 'RL1206=1/4 W, 1/2W;'",
    "power_rated_w": 0.25,
    "derating": "Fig. 5 (normal power): 100 % to 70 C ambient, linear to 0 % at 155 C. P = 0.25 W x (155 - Ta)/85 for 70 < Ta <= 155 C. (The 1/2 W double-power 7W code derates to 0 at 125 C; not this part.)",
    "other": "0.68 ohm, F = +/-1 %, '07 = 7 inch dia. Reel and standard power' (p2) so 1/4 W normal power. TCR for RL1206 500 mohm < R < 1 ohm: +/-200 ppm/C (p5).",
    "series_level": True,
    "notes": "No LCSC listing for the exact MPN. Yageo's own URL 404'd; V.3 taken from a distributor (comet.bg) mirror. Older V.2 (June 01, 2017) LCSC copies also saved (C705571 = RL1206JR-070R68L, sha a5f96898facf84de; C327066 = RL1206FR-070R068L, sha 3157d0aacc95b02a), same ratings."}

# ---------- Vishay TNPW ----------
tnpw_ds = {"title": "Vishay TNPW e3 High Stability Thin Film Flat Chip Resistors",
           "revision": "Document Number 28758, Revision 10-Apr-2026",
           "url": "https://www.vishay.com/docs/28758/tnpw_e3.pdf",
           "sha256_prefix16": "6f0508c568cb355a",
           "local": "/Users/bennet/Desktop/temper/worktrees/runs-native21/s45/dl/vishay_tnpw.pdf"}
out["TNPW060311K7BEEA"] = {"manufacturer": "Vishay (Dale/Beyschlag thin film)", "datasheet": tnpw_ds,
    "temp_max_c": 175, "temp_min_c": -55,
    "applies_to": "operating temperature range = permissible FILM temperature (element/hot-spot) in Advanced Operation mode; also a terminal-part-temperature limit. Mode-dependent: General 125 C, Power 155 C, Advanced 175 C film.",
    "page": "PDF p1 (Technical specifications table + notes); PDF p2 (Maximum resistance change at rated dissipation table); PDF p6-7 derating graphs",
    "quote": "p1: 'Rated dissipation, P70 ... 0.210 W' (TNPW0603), 'Rated dissipation, P at terminal part temperature, ϑt (3) ... 0.5 W ... 105 °C', 'Permissible film temperature, ϑF max. 175 °C', 'Operating temperature range (4) -55 °C to 175 °C'; p2: 'Operating temperature range -55 °C to 125 °C | -55 °C to 155 °C | -55 °C to 175 °C' / 'Permissible film temperature, ϑF max. 125 °C | 155 °C | 175 °C'",
    "power_rated_w": 0.21,
    "derating": "Ambient derating, knee at 70 C: General operation 0.110 W -> 0 at 125 C; Power operation 0.170 W -> 0 at 155 C; Advanced operation 0.210 W -> 0 at 175 C (p2 table, p6-7 graphs). Terminal-part-temperature derating (p7 graph): 0.5 W flat up to terminal 105 C, linear to 0 W at about 155 C (graph reading; endpoint not tabulated). Note (3) p1: 'The specified maximum terminal part temperature must not be exceeded'.",
    "other": "11.7 kohm, B = +/-0.1 %, E = +/-25 ppm/K, EA packaging (p4). TNPW0603 range 1 ohm-332 kohm; Umax 100 V. Load-life drift at P70 1000 h: <= 0.05 % / 0.10 % / 0.20 % for General / Power / Advanced.",
    "series_level": True, "notes": "Series datasheet. The 175 C operating limit is a film temperature, so it is the element/hot-spot rating, not ambient; stability-graded modes cap at 125/155 C film."}

# ---------- Vishay AC05 ----------
ac_ds = {"title": "Vishay Draloric AC, AC-AT Cemented Leaded Wirewound Resistors",
         "revision": "Document Number 28730, Revision 07-Dec-2020",
         "url": "https://datasheet.lcsc.com/datasheet/pdf/977c116010ca315011d5ad74cd3f2f16.pdf?productCode=C1382388",
         "sha256_prefix16": "246742c2396d6eef",
         "local": P + "/vishay-ac05/ac_ac-at.pdf"}
out["AC05000001507JAC00"] = {"manufacturer": "Vishay Draloric", "datasheet": ac_ds,
    "temp_max_c": 250, "temp_min_c": -55,
    "applies_to": "operating temperature range of the resistor (derating referenced to AMBIENT). Climatic category upper category temperature is 200 C. No max surface/hot-spot temperature number is published.",
    "page": "PDF p1 (electrical specs + operating range note); PDF p4 (application information); PDF p8 (Derating and Temperature Rise graphs); PDF p9 (climatic category)",
    "quote": "p1: 'AC05  5W  4.7 W  P x R  0.10 Ω to 910 Ω' (P40, P70) and '• The operating temperature range for these resistors is from -55 °C up to 250 °C'; p4: 'The permissible dissipation is derated for temperatures above 40 °C, as shown in the derating diagram'; p9: 'Climatic category -55 / 200 / 56'",
    "power_rated_w": 4.7,
    "derating": "Rated dissipation 5 W at 40 C (P40) and 4.7 W at 70 C (P70). Derating graph p8: 100 % to 40 C ambient, linear (solid to 200 C, about 30 %), dashed to 0 % at 250 C. Approx line: P = 5 W x (250 - Ta)/210 for 40 < Ta <= 250 C (gives about 4.3 W at 70 C from the graph line vs 4.7 W tabulated, so the graph is not exactly linear from 40 C; use the tabulated P70).",
    "other": "0.15 ohm (value 150 x 10^-3), J = +/-5 %, AC packaging, standard neutral variant (p2 decode). Temperature-rise graph p8: AC05 about 265 K rise at 5 W (graph reading, not tabulated). Endurance at upper category temperature test: 200 C, 30 % of P70, 1000 h (p9).",
    "series_level": True, "notes": "Series datasheet. Hot-spot/surface max not stated as a number; the 250 C operating-range end point (0 % power) is the closest thing. LCSC copy filed under C1382388 = the exact MPN."}

# ---------- Yageo CC X7R ----------
cc_ds = {"title": "Yageo Surface-Mount Ceramic Multilayer Capacitors, General Purpose & High Capacitance, Class 2, X7R, 6.3 V to 250 V",
         "revision": "V.26, November 19, 2024",
         "url": "https://datasheet.lcsc.com/datasheet/pdf/23ccee80ee542e7cf156a772bb589942.pdf?productCode=C14663",
         "sha256_prefix16": "61a606825ab314ea",
         "local": P + "/yageo-cc/yageo-cc-x7r-lcsc-C14663.pdf"}
for mpn, sz, lc in [("CC0603KRX7R9BB104", "0603", "C14663"), ("CC0805KRX7R9BB104", "0805", "C49678")]:
    out[mpn] = {"manufacturer": "Yageo", "datasheet": cc_ds,
        "temp_max_c": 125, "temp_min_c": -55,
        "applies_to": "operating temperature range (datasheet does not say whether it includes self-heating; no self-heating limit is published)",
        "page": "PDF p14, Table 12 Electrical characteristics",
        "quote": "'Maximum capacitance change as a function of temperature (temperature characteristic/coefficient): ± 15%' / 'Operating temperature range: –55 °C to +125 °C'",
        "power_rated_w": None, "derating": None,
        "other": f"Dielectric X7R; {sz}, 100 nF, K = +/-10 %, R = paper reel 7 inch, 9 = 50 V (p2 ordering code). Endurance test at 125 C for X7R (p25).",
        "series_level": True,
        "notes": f"Series datasheet. LCSC {lc} serves the same file (hash 23ccee80... in both product pages). Yageo's own URL 404'd. No ripple/self-heating statement in this datasheet."}

# ---------- Samsung ----------
def sam(mpn, key, desc, diel, rng_quote, sha, issued, page_self="PDF p15", extra=""):
    return {"manufacturer": "Samsung Electro-Mechanics", "datasheet": {
            "title": f"Samsung Electro-Mechanics SPECIFICATION (Reference Sheet) {mpn}, with MLCC Product Manual" + extra,
            "revision": f"Issued date {issued}",
            "url": f"https://product.samsungsem.com/part/download.do (POST masterKey={key}&type=specsheet; from product page https://product.samsungsem.com/mlcc/{key}.do)",
            "sha256_prefix16": sha,
            "local": f"{P}/samsung/{key}-specsheet/{key}-specsheet.pdf"},
        "temp_max_c": 125, "temp_min_c": -55,
        "applies_to": "temperature characteristic range = maximum operating temperature; the manual states it is a SURFACE temperature limit INCLUDING self-heating, and self-heating rise must not exceed 20 C",
        "page": f"PDF p2 (temperature characteristics); {page_self} (2-6 Self-heating Temperature)",
        "quote": rng_quote + " ; '1) The surface temperature of MLCC must stay within the maximum operating temperature after AC or Pulse voltage is applied.' / '2) The rise in increase by self-heating of MLCC must not exceed 20℃'",
        "power_rated_w": None, "derating": None,
        "other": f"Dielectric {diel}; {desc}. Self-heating limit: <= 20 C rise.",
        "series_level": False,
        "notes": "Part-specific Samsung reference sheet. It gives no separate 'operating temperature range' line; the -55 to 125 C range is under Temperature Characteristics, and the high-temperature test refers to 'Max. operating temperature'."}
q_x7r = "'Temperature Characteristics X7R (From -55℃ to 125℃, Capacitance change should be within ±15%)'"
q_c0g = "'Temperature Characteristics (From -55℃ to 125℃, Capacitance change should be within 0±30ppm/℃)'"
out["CL21B105KBFNNNE"] = sam("CL21B105KBFNNNE", "CL21B105KBFNNN", "CAP, 1uF, 50V, ±10%, X7R, 0805", "X7R", q_x7r, "583b7deb63d39dd5", "MAY.09.2024")
out["CL32B106KBJNNNE"] = sam("CL32B106KBJNNNE", "CL32B106KBJNNN", "CAP, 10uF, 50V, ±10%, X7R, 1210", "X7R", q_x7r, "f5e74b1afd822274", "MAR.18.2026")
out["CL32B106KBJNNNE"]["notes"] += " Older LCSC copy (C138687, effective March 1, 2013, sha 157111dc0e1c4767, " + P + "/samsung/CL32B106KBJNNNE/) gives the same -55 to 125 C X7R range."
out["CL05B104KB54PNC"] = sam("CL05B104KB54PNC", "CL05B104KB54PN", "CAP, 100nF, 50V, ±10%, X7R, 0402, AEC-Q200 automotive grade, metal-epoxy termination", "X7R",
    "'Temperature Characteristic  From -55℃ to 125℃, Capacitance change should be within ±15%'", "92054b775800cad8", "JUL.15.2025", extra=" (Specification of Automotive MLCC)")
out["CL05B104KB54PNC"]["notes"] += " Automotive reference sheet: temperature cycling -55 to +125 C, high temperature exposure 1000 h at Max. Temperature, HTOL 1000 h at 125 C (p2). The manual (p18) also says 'Temperature of MLCC' on the derating graphs is the surface temperature including self-heating."
out["CL10C101JB8NNNC"] = sam("CL10C101JB8NNNC", "CL10C101JB8NNN", "CAP, 100pF, 50V, ±5%, C0G, 0603", "C0G", q_c0g, "aec8f5c040150719", "JUL.17.2020")
out["CL10C331JB8NNNC"] = sam("CL10C331JB8NNNC", "CL10C331JB8NNN", "CAP, 330pF, 50V, ±5%, C0G, 0603", "C0G", q_c0g, "78b8db7110ad25cd", "JUL.17.2020")

# ---------- Murata ----------
out["GRM21BZ71E106KE15L"] = {"manufacturer": "Murata", "datasheet": {
        "title": "Murata Chip Multilayer Ceramic Capacitors for Consumer Electronics & Industrial Equipment, Reference Sheet GRM21BZ71E106KE15-01A (2012M(0805), X7R(MURATA), 10uF, DC 25V)",
        "revision": "-01A; 'Product specifications in this catalog are as of Jan.9,2025'",
        "url": "https://datasheet.lcsc.com/datasheet/pdf/25c25013e9e59794670905e9d029f396.pdf?productCode=C237493",
        "sha256_prefix16": "8a398f916d26f901",
        "local": P + "/murata/GRM21BZ71E106KE15L/GRM21BZ71E106KE15L-lcsc-C237493.pdf"},
    "temp_max_c": 125, "temp_min_c": -55,
    "applies_to": "operating temperature range INCLUDING self-heating (capacitor surface temperature); self-heating limited to 20 C rise at 25 C ambient for <100 Vdc parts",
    "page": "PDF p2 (Rated Value table); PDF p12 (caution 4, self-heating); PDF p25 (1-2 self-heating)",
    "quote": "p2 Rated Value: '-15 to 15 % *  -55 to 125℃  25℃  DC 25V  10μF  +/-10%  -55 to 125℃' (last range = Operating Temp. Range); p12: 'The load should be contained so that the self-heating of the capacitor body remains below 20°C, when measuring at an ambient temperature of 25°C.'; p25: 'The surface temperature of the capacitor shall not exceed the maximum operating temperature including self-heating.'",
    "power_rated_w": None, "derating": None,
    "other": "Dielectric Z7 = X7R(MURATA) special characteristic: '*Range of capacitance change rate with 50% rated voltage applied' (p2). L = 180 mm plastic tape reel.",
    "series_level": False, "notes": "Part-specific Murata reference sheet (LCSC C237493). Murata's own per-part PDF endpoints are JS-gated/404 from curl."}
out["GRM188R71E105KA12D"] = {"manufacturer": "Murata", "datasheet": {
        "title": "Murata Product Search Data Sheet GRM188R71E105KA12# (1.0uF, 25Vdc, X7R, 0603)",
        "revision": "'Last updated 04/27/2021' (page footer); sheet itself says 'This datasheet may be out of date'",
        "url": "https://store.comet.bg/download-file.php?id=22967",
        "sha256_prefix16": "5421aafe2e0574d4",
        "local": P + "/murata/GRM188R71E105KA12D/comet-22967.pdf"},
    "temp_max_c": 125, "temp_min_c": -55,
    "applies_to": "operating temperature range; Murata's general caution (catalog C02E) makes this a surface temperature limit including self-heating with <= 20 C self-heating at 25 C ambient",
    "page": "PDF p2 (Specifications); self-heating: Murata catalog C02E PDF p269 (local s42 file)",
    "quote": "p2: 'Operating Temperature Range  -55℃ to 125℃' / 'Temperature characteristics  X7R(EIA)' / 'Temperature range of temperature characteristics  -55℃ to 125℃'; catalog C02E p269: '...self-heating of the capacitor body remains below 20°C, when measuring at an ambient temperature of 25°C.'",
    "power_rated_w": None, "derating": None,
    "other": "Dielectric R7 = X7R(EIA); D = 180 mm paper tape reel. Also listed in Murata catalog C02E (2017, local s42 murata-GRM1885C1H472JA01D.pdf, sha 9a8a89cd730ba1b1) PDF p105 as 'GRM188R71E105KA12#  25Vdc X7R 1.0µF ±10%'.",
    "series_level": False,
    "notes": "Part-specific, but a distributor-mirrored 'Product Search Data Sheet' (2021), not Murata's full reference sheet; no LCSC listing and Murata per-part PDF endpoints are JS-gated. The PDF has some damaged flate streams but p2 extracts cleanly. Distributor aggregators flag this part as EOL (not confirmed on murata.com)."}
out["GRM31C5C1H104JA01L"] = {"manufacturer": "Murata", "datasheet": {
        "title": "Murata Chip Monolithic Ceramic Capacitor for General, Reference Sheet GRM31C5C1H104JA01_ (1206, C0G:EIA, 0.1uF, DC50V)",
        "revision": "'Product specifications in this catalog are as of Mar.5,2016'",
        "url": "https://datasheet.lcsc.com/datasheet/pdf/357d841984a94b5db925be64cf2c2923.pdf?productCode=C97946",
        "sha256_prefix16": "5c84ef333cecfe38",
        "local": P + "/murata/GRM31C5C1H104JA01L/GRM31C5C1H104JA01L-lcsc-C97946.pdf"},
    "temp_max_c": 125, "temp_min_c": -55,
    "applies_to": "operating temperature range INCLUDING self-heating (surface temperature); self-heating limited to 20 C rise at 25 C ambient for <100 Vdc parts",
    "page": "PDF p1 (4. Rated value); PDF p13 (self-heating caution); PDF p24 (1-2 self-heating)",
    "quote": "p1: '0±30 ppm/°C  DC 50 V  0.1 uF  ±5 %  -55 to 125 °C' (last column '(Operating Temp. Range)'); p13: 'such that when measuring at atmospheric temperature of 25°C, the product's self-heating remains below 20°C'; p24: 'The surface temperature of the capacitor shall not exceed the maximum operating temperature including self-heating.'",
    "power_rated_w": None, "derating": None,
    "other": "Dielectric 5C = C0G(EIA), temp coefficient 0+/-30 ppm/C over 25 to 125 C. L = 180 mm reel.",
    "series_level": False, "notes": "Part-specific Murata reference sheet (LCSC C97946), dated 2016."}

# ---------- KEMET ----------
out["C0603C102J5GACTU"] = {"manufacturer": "KEMET", "datasheet": {
        "title": "KEMET Surface Mount Multilayer Ceramic Chip Capacitors (SMD MLCCs), C0G Dielectric, 10-250 VDC (Commercial Grade)",
        "revision": "C1003_C0G, 2/20/2025",
        "url": "https://content.kemet.com/datasheets/KEM_C1003_C0G_SMD.pdf",
        "sha256_prefix16": "02d179914aeb9585",
        "local": P + "/kemet-c0g/KEM_C1003_C0G_SMD.pdf"},
    "temp_max_c": 125, "temp_min_c": -55,
    "applies_to": "operating temperature range (datasheet does not state a self-heating limit or say whether self-heating is included)",
    "page": "PDF p1 (Overview/Benefits); PDF p4 (Electrical Parameters/Characteristics)",
    "quote": "p1: 'KEMET's C0G dielectric features a 125°C maximum operating temperature' / '• −55°C to +125°C operating temperature range'; p4: 'Operating Temperature Range  −55°C to +125°C'",
    "power_rated_w": None, "derating": None,
    "other": "Dielectric C0G (G); 0603, C = standard, 102 = 1000 pF, J = +/-5 %, 5 = 50 V, A = N/A, C = 100 % matte Sn, TU = 7 inch reel (p1 ordering). TCC +/-30 ppm/C.",
    "series_level": True,
    "notes": "Series datasheet. The brief named KEM_C1002_C0G_SMD; KEMET's current commercial C0G datasheet is numbered C1003 (KEM_C1003_C0G_SMD.pdf), used here."}

# ---------- Panasonic ----------
out["6SVPC220MV"] = {"manufacturer": "Panasonic (OS-CON)", "datasheet": {
        "title": "Panasonic Conductive Polymer Aluminum Solid Capacitors, Surface Mount Type, SVPC series",
        "revision": "Series pages dated 06-Feb-17; caution pages 10-May-24 / 20-Aug-25; PDF ModDate 2025-10-29 (AAB8000C256)",
        "url": "https://industrial.panasonic.com/cdbs/www-data/pdf/AAB8000/AAB8000C256.pdf",
        "sha256_prefix16": "1c506b7474c01158",
        "local": P + "/panasonic-svpc-official/AAB8000C256.pdf"},
    "temp_max_c": 105, "temp_min_c": -55,
    "applies_to": "category temperature range (ambient); ripple current rated at +105 C",
    "page": "PDF p1 (Specifications: category temp range, endurance); PDF p2 (Characteristics list row, footnotes, frequency correction)",
    "quote": "p1: 'Category temp. range  –55 ℃ to +105 ℃' / 'Endurance  +105 ℃ 2000 h, rated voltage applied'; p2: '6.3  5.9  C6  3160  15  13  0.12  300  6SVPC220MV  1000' / '*1: Ripple current (100 kHz / +105 ℃)'",
    "power_rated_w": None,
    "derating": "Ripple: 3160 mA rms at 100 kHz / +105 C. Frequency correction factor: 0.05 (120 Hz-1 kHz), 0.3 (1-10 kHz), 0.7 (10-100 kHz), 1 (100-500 kHz). No ripple-vs-temperature multiplier is given in this datasheet (rating is already at the 105 C category maximum).",
    "other": "220 uF +/-20 %, 6.3 V, size C6 (6.3 x 5.9 mm). ESR max 15 mohm at 100 kHz/20 C (13 mohm at 300 kHz, reference). tan d 0.12 (120 Hz/20 C). LC 300 uA after 2 min. Endurance 2000 h at 105 C, rated voltage: dC within +/-20 %, tan d <= 150 % of initial limit, LC within initial limit. Panasonic product page confirms '3160 mArms at 105 C and 100 kHz', ESR 15.0 mohm, '2000@105°C'.",
    "series_level": True,
    "notes": "Series datasheet with a per-part row. Official PDF obtained via WebFetch (curl to industrial.panasonic.com timed out). LCSC copy (C128504, 03 Feb. 2017, sha 958cb83078bc8599, " + P + "/panasonic-svpc/) has the same row."}

json.dump(out, open("/Users/bennet/.claude/jobs/fbfc46b4/tmp/temp-ratings/ds/passives.json", "w"), indent=1, ensure_ascii=False)
print(len(out))
