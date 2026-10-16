"""Datasheet temperature ratings for the native-21 s47 BOM lines whose ledger entry has none (temp-ratings 2026-10-15).

Every rating was read from the manufacturer document named in `source` (PDF page = printed page unless stated), downloaded
2026-10-15/16 to worktrees/runs-native21/s47/temp-ratings-dl/<group>/<part>/ (sha256 prefix in `doc`). Machine-readable
extracts with verbatim quotes: ../ds/{passives,semis_a,semis_b,conn}.json.

model:
  ic    est = pad + P x Rth (+ extra_k): the gate's probe-row rule (pad copper as the local-ambient / die proxy; for a TA
        rating adding P x RthJA double-counts the board spreading RthJA contains, which is conservative)
  body  est = the B3 body model's tj_c (the part has a B3 heat row)
  res   resistor: pad (terminal) against the derating line at P with the 20 % power margin; element (tj_c) where B3 has a body
"""
DL = "runs-native21/s47/temp-ratings-dl"

# numbers the power table needs (W), each from the datasheets below
DS = {
    "lvc_icc_w": 1e-4,                    # ICC 10 uA max (-40..125) x 5.15 V = 52 uW, + CMOS / 10 k output loads; bound 0.1 mW
    "tlv3201_w": 65e-6 * 5.15,            # IQ 65 uA max at 5 V, -40..125 C (SBOS561C p.5)
    "tps3700_w": 13e-6 * 17.5 + 0.5e-3 * 0.25,   # IDD 13 uA max (SBVS187G p.6) at V15_LS + OUTB sinking 0.5 mA at VOL 0.25 V
    "amc1311_w": 9.7e-3 * 5.15 + 7.2e-3 * 3.465,  # IDD1 9.7 mA max (4.5-5.5 V), IDD2 7.2 mA max (3.0-3.6 V), SBAS786C p.11
    "iso6721_w": 2 * 3.5e-3 * 5.15,       # ICC1 / ICC2 3.5 mA max per side, DC opposite-default state (SLLSFJ0F p.12)
    "cais3720_w": (4.1e-3 + 2.3e-3) * 5.15,  # IDDA 4.1 + IDDB 2.3 mA max, DC opposite-default, 5 V (v1.08 p.11)
    "vol628a_w": 2.12e-3 * 1.5,           # 2.12 mA RMS x VF max 1.5 V at 5 mA (82401 p.3)
    "pmeg_vf": 0.53,                      # VF max 530 mV at IF 3 A, Tj 25 C (PMEG6030EP v.2 p.5; VF falls with Tj)
}

R = {}


def ic(mpn, t, applies, source, basis, rth=None, what=None, gap=None, extra_k=0.0, extra_basis=None, model="ic", **kw):
    R[mpn] = dict(model=model, limit_c=t, t_max_c=t, applies=applies, source=source, basis=basis, rth=rth,
                  what=what or ("pad + P x Rth" if rth else "pad (local-ambient proxy)"), gap=gap, extra_k=extra_k,
                  extra_basis=extra_basis, **kw)


# ---------------------------------------------------------------- semiconductors (ds/semis_a.json, ds/semis_b.json)
ic("PMEG6030EP,115", 150.0, "TJ",
   "Nexperia PMEG6030EP v.2 (7 Nov 2017) p.3 Limiting values (LCSC C456127 copy, sha 89bc99ad6f4835fb)",
   "Tj junction temperature max 150 C (abs max, IEC 60134); Tamb -55..150 C. Rth(j-a) 200 K/W FR4 standard footprint "
   "(p.3; 120 K/W on 1 cm2, Rth(j-sp) 12 K/W)", rth=(200.0, "Rth(j-a) FR4 standard footprint, p.3"),
   what="pad + P x Rth(j-a); P = turn-off charge x VF x f",
   gap="VF is the 25 C table maximum at 3 A (p.5); the turn-off peak is several A, beyond the table, and no hot-Tj VF or "
       "IR maximum is published (Fig. 5 typical ~10 mA at 25-30 V, Tj 125 C): reverse leakage during the turn-on "
       "transient (VR up to 15.5 V for ~1 us of each 16.7 us) is not in the self-heat")
ic("BAT54S-7-F", 150.0, "TJ",
   "Diodes DS11005 Rev. 34-2 (Nov 2023) p.2 Thermal Characteristics (sha 50b04e4e17bcf5db)",
   "Operating and storage temperature TJ, TSTG -65..+150 C; RthJA 500 K/W typ, PD 200 mW at 25 C derating to 0 at "
   "150 C (Fig. 4, = 625 K/W, used)", rth=(625.0, "PD derating Fig. 4 p.3 (RthJA 500 K/W typ p.2)"))
ic("BAS116H,115", 150.0, "TJ", "Nexperia BAS116H Rev. 3 (31 May 2011) p.2 Limiting values (LCSC C74210, sha 04966fbaa922997c)",
   "Tj max 150 C; Tamb -65..150 C; Rth(j-a) 330 K/W (p.3)", rth=(330.0, "Rth(j-a) FR4 standard footprint, p.3"))
ic("30KPA150CA", 150.0, "TJ", "Good-Ark Doc.US30KPA28A-30KPA320CAxSM5.0 (Jan 2020) p.1 (sha 7700d2c23b98a681)",
   "Operating junction and storage TJ, TSTG -55..+150 C (Good-Ark, the ledger's maker). The BOM's LCSC C19111562 is "
   "listed as Littelfuse, whose 30KPA sheet (Rev BA.08/27/20, sha 1fe25d7c0973063d) rates TJ -55..175 C, RthJA 40 K/W typ",
   rth=(40.0, "Littelfuse RthJA 40 K/W typ (Good-Ark lists none)"),
   gap="maker ambiguity: ledger Good-Ark (150 C) vs LCSC C19111562 Littelfuse (175 C); the lower is used")
LVC = ("RthJA 357.1 K/W DBV (current TI LVC1G sheets; the 2013 1G10 / 1G332 sheets print 165 K/W)")
for mpn, doc in (("SN74LVC1G00DBVR", "TI SCES212AC (rev. Aug 2026) p.5, sha 1264f79853e6119b"),
                 ("SN74LVC1G10DBVR", "TI SCES486E (rev. Dec 2013) p.3 (RthJA p.2), sha 4902c8770413a400"),
                 ("SN74LVC1G332DBVR", "TI SCES489E (rev. Dec 2013) p.3 (RthJA p.2), sha 5ecad3180cb93664"),
                 ("SN74LVC1G17DBVR", "TI SCES351Y (rev. Oct 2025) p.5, sha c76fa723fac45024"),
                 ("SN74LVC1G132DBVR", "TI SCES546E (rev. Aug 2026) p.5, sha fae33d78fe46834a")):
    ic(mpn, 125.0, "TA", doc, "Recommended operating free-air temperature TA -40..125 C (no TJ max is printed); " + LVC,
       rth=(357.1, LVC))
ic("TPS70950DBVR", 125.0, "TJ", "TI SBVS186H (rev. Jul 2021) p.4 Recommended Operating Conditions (sha 8c14e3efae738a27)",
   "Operating junction temperature TJ -40..125 C (recommended; abs max -55..150 C); RthJA 212.1 K/W DBV", model="body",
   what="B3 body model (dbv5) junction")
ic("TLV3201AIDBVR", 125.0, "TA", "TI SBOS561C (rev. May 2024) p.4 (sha 1777bba814c74772)",
   "Specified temperature -40..125 C (EC tables at TA; abs max operating -55..125 C, TJ 150 C); RthJA 237.8 K/W DBV",
   rth=(237.8, "RthJA DBV p.4"))
ic("TPS3700DDCR", 125.0, "TJ", "TI SBVS187G (rev. Feb 2019) p.5 Absolute Maximum Ratings (sha 3bb7daed20b154bf)",
   "Operating junction temperature TJ -40..125 C (the abs-max row; the EC table is specified over TJ -40..125 C, p.6; "
   "no TA row); RthJA 204.6 K/W DDC", rth=(204.6, "RthJA DDC p.5"))
ic("TPS7A4700RGWR", 125.0, "TJ", "TI SBVS204G (rev. May 2026) p.4 Absolute Maximum Ratings (sha 8ca46a9968923d2e)",
   "Operating virtual junction TJ -40..125 C (abs max; no separate 150 C); RthJA 32.5 K/W RGW. The B3 gate already gates "
   "U26 on this (b3_ratings_gate GATED['rgw'])", model="body", what="B3 body model (rgw) junction = the gated U26 row")
ic("TLVH431BQDBZR", 125.0, "TA", "TI SLVS555N (rev. Jun 2024) p.5 (sha e30d628cb6475d48)",
   "Operating free-air temperature TLVH43x_Q -40..125 C (BQ = B tolerance, Q grade, p.8 / p.13 / addendum p.28); TJ abs "
   "max 150 C; RthJA 206 K/W DBZ. The B3 gate already gates U16 / U18 / U20 on this", rth=(206.0, "RthJA DBZ p.5"),
   what="pad + P x RthJA = the gated B3 row")
ic("AMC1311BDWVR", 125.0, "TA", "TI SBAS786C (rev. Jun 2022) p.6 Recommended Operating Conditions (sha 4a80cec704b1f432)",
   "Specified ambient TA -55..125 C for AMC1311B (addendum p.30); TJ abs max 150 C; RthJA 84.6 K/W DWV (p.7)",
   rth=(84.6, "RthJA DWV p.7"))
ic("ISO6721FBDR", 125.0, "TA", "TI SLLSFJ0F (rev. Feb 2023) p.6 (sha bd54a79cc78f46b4)",
   "Ambient TA -40..125 C (addendum p.41); TJ abs max 150 C; RthJA 104.6 K/W D (p.7)", rth=(104.6, "RthJA D p.7"))
ic("CA-IS3720HW", 125.0, "TA", "Chipanalog CA-IS372x v1.08 (2024-12-17, Chinese) p.6 7.3 (sha e3061919c85989c8; English v1.02 agrees)",
   "Ambient TA -40..125 C; TJ abs max 150 C; RthJA 83.4 K/W SOIC16-WB (p.7, board not stated)", rth=(83.4, "RthJA SOIC16-WB p.7"))
ic("2EDR8259XXUMA1", 125.0, "TA", "Infineon 2EDRx259X Rev 1.7 (2026-04-09) p.12 Table 11 (sha f49391ca00e15397)",
   "Ambient TA -40..125 C (operating range); TJ -40..150 C abs max and operating, 'continuous operation above 125 C may "
   "reduce lifetime'; RthJA 69 K/W 2s2p (p.11 Table 10)", rth=(69.0, "RthJA25 2s2p p.11"),
   what="pad + P x RthJA (P = the B3 heat row); body tj_c also reported")
ic("VOL628A-2X001T", 110.0, "TA", "Vishay 82401 Rev. 1.9 (10-Feb-2023) p.2 Absolute Maximum Ratings (sha 86b23c8c1723580a)",
   "Ambient temperature range Tamb -55..+110 C; Tj 125 C (input and output); no thermal resistance published (power "
   "derating Fig. 1 p.3 only)", gap="no Rth published: the 3 mW LED self-heat is not added (< 1 K at any plausible Rth)")

# ---------------------------------------------------------------- connectors and fuses (ds/conn.json)
J1_RISE = 23.0 * (13.5 / 32.0) ** 2
ic("1714971", 105.0, "upper limiting temperature (ambient + own rise)",
   "Phoenix Contact online-catalog PDF 1714971 MKDS 5/ 2-9,5 (generated 2026-10-16) p.5 ambient conditions, p.4 "
   "temperature-rise test, p.6 derating (sha 36517cfd4b96d200)",
   "Ambient (operation) -40..105 C 'depending on the current carrying capacity / derating curve'; IEC 60947-7-4 rise test: "
   "ambient + rise <= upper limiting temperature. cULus E60425 (B/C 300 V 30 A) and CSA 13631 state no temperature",
   extra_k=round(J1_RISE, 2),
   extra_basis="own rise at 13.5 A scaled I^2 from the p.6 curve (32 A flat to 82 C on 6 mm2 = 23 K rise)",
   what="pad + own contact rise",
   gap="the p.6 derating curve is for 6 mm2 conductors only; the 14 AWG (2.1 mm2) inlet wire cools the terminal less, so "
       "the rise is larger than the scaled 4.1 K; no UL temperature (UL 1059 rise / RTI) found (Product iQ blocked)")
ic("KLDR025.TXP", 125.0, "ambient at the fuse (implied: end of the rerating curve)",
   "Littelfuse Class CC KLDR series, revised 06/27/2022, p.6 temperature rerating curve (Farnell copy, sha c51ae8155f39548d)",
   "No operating temperature range is published; the rerating curve (ambient = air immediately surrounding the fuse) runs "
   "-55..~125 C: -14 % at 60 C, -25 % at 80 C. UL 248-4 E81895 / CSA LR29862 state no temperature. Clips 01250003H "
   "(125 series, E14721): no temperature rating published",
   gap="no published maximum temperature for the fuse or its 01250003H clips (UL E14721 not reachable); 125 C is the end of "
       "the rerating curve, not a rating; the fuse's own I^2R heat is not in B3")
ic("B2P3-VH(LF)(SN)", 105.0, "connector incl. temperature rise",
   "JST eVH.pdf (2026-01) p.1 Specifications (sha d51e669c597988b2); legacy JST catalogue p.190 (RS copy, sha dd4cad3c4a2e3e6f)",
   "Temperature range -40..+105 C including temperature rise in applying electrical current; legacy catalogue: 'Maximum "
   "temperature registered in UL is 105 C' (E60389), general range then -25..+85 C",
   gap="the current sheet points UL/CSA terms to JST's 'List of Registered Overseas Standards' (not obtained); at 1.3-1.42 A "
       "of 10 A the own rise is small and not added")
ic("3403.0279.23", 125.0, "ambient", "Schurter UMT-H datasheet (21.07.2026) p.1 Technical Data, p.3 derating (sha bac65726cd086e79)",
   "Admissible ambient -55..125 C, climatic 55/125/21; derating 160 mA-16 A curve: 83 % at 60 C, 74 % at 80 C. cURus "
   "E41599 states no separate temperature")
ic("0430451612", 105.0, "operating incl. 30 K rise at rated current",
   "Molex PS-43045 Rev R (2025-11-14) sheet 11 sect. 4.5 (sha b5f03865599a0576)",
   "Operating -40..+105 C for the tin-plated header (finish A, 43045-1612), values include 30 C rise at rated current; "
   "UL E29179 / CSA LR19980 (UL 1977) state no temperature")
ic("1704004", 100.0, "ambient", "Phoenix Contact online-catalog PDF 1704004 KDS 3 (generated 2026-10-16) p.5 (sha 068a14900fa7b0b6)",
   "Ambient (operation) -40..100 C 'depending on the current carrying capacity / derating curve' (no curve in the PDF); "
   "UL E60425 / CSA 13631 state no temperature; leakage current only (0.97 mA)")

RATINGS = R


# ---------------------------------------------------------------- passives (ds/passives.json)
def res(mpns, prated, tknee, tmax, source, basis, gap=None):
    for m in mpns:
        R[m] = dict(model="res", res=(prated, tknee, tmax), t_max_c=tmax, limit_c=tmax, applies="terminal / element",
                    source=source, basis=basis, gap=gap, what="terminal (pad) vs derating line at P, 20 % margin")


UNI = "UniRoyal Thick Film Chip Resistors data sheet V.3 (Feb.12, 2019) p.5 ratings table + sect. 9 derating, p.4 power (sha 11cd644d5d8a34a6)"
res(["0603WAF1000T5E", "0603WAF1003T5E", "0603WAF4991T5E", "0603WAF1002T5E", "0603WAF5601T5E", "0603WAF1001T5E",
     "0603WAF2702T5E", "0603WAF2200T5E", "0603WAF3302T5E"], 0.1, 70, 155, UNI,
    "0603: operating -55..155 C; 1/10 W at 70 C derating linearly to 0 W at 155 C")
res(["0603WAF0000T5E"], 0.1, 70, 155, UNI, "0603 jumper: <50 mOhm, rated current 1 A (overload 2 A); -55..155 C; no "
    "current derating published; carries no current in operation")
res(["1206W4F1003T5E", "1206W4F100KT5E", "1206W4F1001T5E"], 0.25, 70, 155, UNI,
    "1206 'W4' 1/4 W at 70 C derating to 0 W at 155 C; operating -55..155 C (100K = 1.00 ohm)")
RT = "Yageo RT series V.16 (May 06, 2025) p.5 Table 2, p.6 Fig. 6 (sha 0a729d144519a702)"
res(["RT0603BRD0749K9L", "RT0603BRD0715K8L", "RT0603BRD0710KL", "RT0603BRD0712K6L", "RT0603BRD07140KL", "RT0603BRD071KL",
     "RT0603BRD072K21L", "RT0603BRD07105KL", "RT0603BRD076K2L", "RT0603BRD074K42L", "RT0603BRD07750RL", "RT0603BRD072K94L",
     "RT0603BRD0790K9L", "RT0603BRD07104KL", "RT0603BRD0763K4L", "RT0603BRD0711KL"], 0.1, 70, 155, RT,
    "RT0603 1/10 W; operating -55..+155 C; rated power at 70 C, linear to 0 at 155 C")
res(["RC1206FR-07220KL", "RC1206FR-073RL", "RC1206FR-072K2L", "RC1206FR-0716K5L"], 0.25, 70, 155,
    "Yageo RC_L series V.12 (Aug 02, 2022) p.6 Table 3, p.7 Fig. 10-1 (sha e7dbabb061192522)",
    "RC1206 1/4 W ('07' standard power, p.2); operating -55..155 C; 70 C knee to 0 W at 155 C")
res(["RL1206FR-070R68L"], 0.25, 70, 155, "Yageo RL series V.3 (Apr 07, 2023) p.5 Table 2, p.6 Fig. 5 (sha a222719aba346137, "
    "distributor mirror; Yageo URL 404)", "RL1206 1/4 W normal power; operating -55..+155 C; 70 C knee to 0 W at 155 C")
res(["TNPW060311K7BEEA"], 0.11, 70, 125, "Vishay TNPW e3 doc 28758 (rev 10-Apr-2026) p.1, p.6-7 (sha 6f0508c568cb355a)",
    "film temperature limit by mode: 'General' 0.11 W at 70 C to 125 C film (used, the lowest); 'Power' 0.17 W to 155 C; "
    "'Advanced' 0.21 W to 175 C")
res(["AC05000001507JAC00"], 5.0, 40, 250, "Vishay Draloric AC/AC-AT doc 28730 (rev 07-Dec-2020) p.1, p.8 derating, p.9 (sha 246742c2396d6eef)",
    "operating -55..250 C (upper category temperature 200 C, climatic -55/200/56); 5 W at 40 C (4.7 W at 70 C); the p.8 "
    "curve (100 % to 40 C, ~30 % at 200 C, 0 at 250 C) is taken as a straight line 40 -> 250 C (below the curve)",
    gap="no surface / hot-spot maximum published; not UL recognised (ledger)")

MLCC_NOTE = "; own ripple heat negligible (gate-charge pulses ~0.34 A RMS shared across the driver bank x mOhm ESR: ~1 mW)"
for m, doc, basis in (
        ("CC0603KRX7R9BB104", "Yageo SMD MLCC general purpose V.26 (Nov 19, 2024) p.14 Table 12 (sha 61a606825ab314ea)",
         "X7R, operating -55..+125 C (self-heating not addressed)"),
        ("CC0805KRX7R9BB104", "Yageo SMD MLCC general purpose V.26 (Nov 19, 2024) p.14 Table 12 (sha 61a606825ab314ea)",
         "X7R, operating -55..+125 C (self-heating not addressed)"),
        ("CL21B105KBFNNNE", "Samsung SEM spec (issued MAY.09.2024) p.2, p.15 sect. 2-6 (sha 583b7deb63d39dd5)",
         "X7R -55..125 C; p.15: surface temperature incl. self-heating within the max operating temperature, rise <= 20 C"),
        ("CL32B106KBJNNNE", "Samsung SEM spec (issued MAR.18.2026) p.2, p.15 (sha f5e74b1afd822274)",
         "X7R -55..125 C; surface temperature incl. self-heating (p.15)"),
        ("CL05B104KB54PNC", "Samsung SEM spec (issued JUL.15.2025) p.2, p.15 (sha 92054b775800cad8)",
         "X7R -55..125 C; surface temperature incl. self-heating (p.15)"),
        ("CL10C101JB8NNNC", "Samsung SEM spec (issued JUL.17.2020) p.2, p.15 (sha aec8f5c040150719)",
         "C0G -55..125 C; surface temperature incl. self-heating (p.15)"),
        ("CL10C331JB8NNNC", "Samsung SEM spec (issued JUL.17.2020) p.2, p.15 (sha 78b8db7110ad25cd)",
         "C0G -55..125 C; surface temperature incl. self-heating (p.15)"),
        ("GRM21BZ71E106KE15L", "Murata reference sheet (as of Jan.9, 2025) p.2, p.12, p.25 (LCSC C237493, sha 8a398f916d26f901)",
         "Z7 (X7R) operating -55..125 C including self-heating"),
        ("GRM188R71E105KA12D", "Murata product data sheet (updated 04/27/2021, mirror) p.2 (sha 5421aafe2e0574d4); catalog C02E p.269",
         "X7R operating -55..125 C; Murata self-heating rule (catalog)"),
        ("GRM31C5C1H104JA01L", "Murata reference sheet (as of Mar.5, 2016) p.1, p.13, p.24 (LCSC C97946, sha 5c84ef333cecfe38)",
         "C0G operating -55..125 C including self-heating"),
        ("C0603C102J5GACTU", "KEMET KEM_C1003_C0G_SMD (2/20/2025) p.1, p.4 (sha 02d179914aeb9585)",
         "C0G -55..+125 C operating temperature range")):
    ic(m, 125.0, "operating (surface)", doc, basis + MLCC_NOTE)
ic("6SVPC220MV", 105.0, "category (ambient / case)", "Panasonic OS-CON SVPC AAB8000C256 p.1, p.2 (sha 1c506b7474c01158)",
   "Category temperature -55..+105 C; endurance 2000 h at 105 C; rated ripple 3160 mA rms at 100 kHz / 105 C; ESR 15 mOhm "
   "max; own ripple heat: <= 0.1 A x 15 mOhm = 0.15 mW, negligible",
   gap="life: 2000 h at 105 C; at the release-case estimate the 10-degree rule gives only a few thousand hours, a "
       "life item outside this temperature check")
RATINGS = R
