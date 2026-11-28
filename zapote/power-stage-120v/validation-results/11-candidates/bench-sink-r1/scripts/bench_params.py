"""Bench heatsink r1: every geometric and material input, with its source.

Frame (written for native-21 s53; the FET land is s57's, the M11 frame is unchanged): x right along the board's rear edge, y into the board from that
edge (y = 0 is the edge, y < 0 is off-board), z up from the board's top copper. mm unless stated.

Source tags (full citations, URLs and SHA-256 in ../sources/SOURCES.md):
  [IPW]  Infineon IPW65R018CFD7 Rev 2.0, p.3 (RthJC 0.28, Tj 150, 60 Ncm M3), p.12 outline Z8B00003327 rev 06
  [GBJ]  Diodes GBJ2510 DS21221 Rev 11-2: p.1 case dielectric 2500 Vrms, #6 screw 5.0 in-lb max; p.2 RthJC 1.0 typ per element;
         p.4 outline (A 29.70-30.30, B 19.70-20.30, L 4.40-4.80)
  [HNK]  Henkel/Bergquist Thermal Interface Selection Guide (2017), SIL PAD pages (K-10 p.75, 2000 p.71, 900S p.65): breakdown,
         thickness and the thermal-impedance-vs-pressure rows (ASTM D5470, includes interfacial resistance)
  [WAK]  Wakefield Thermal bonded-fin catalogue p.99, 510/511/512 series (511-3M row, profile 6438-1)
  [CAN]  Cantherm SDF thermal cut-off sheet (2016/June): DF110S Tf 110 / Th 86 C, tolerance +0/-5 C, 250 V 10 A, live metal case
  [NTC]  Vishay NTCALUG01A series, doc 29092 rev 14-Jan-2026: M3 lug, 1500 VAC terminals-to-lug, 100 MOhm at 500 VDC, -55..150 C
  [LEE]  Lee Spring LC 055E 03 S product page (read 2026-10-18)
  [M11]  owner-items/m11/RECOMMENDATION.md + board-sink-geometry.json (tab plane, pad edges, edge copper), stack_calc.py
  [T03]  validation-results/03-loss-thermal-budget/round3: TO-247 exposed tab area 151.2-240.1 mm2
  [CPL]  validation-results/08-manufacturing-package/native-21/fab/cpl-jlcpcb-order.csv (device centres)
  EST    engineering estimate, named as such where used
"""

# ---------------------------------------------------------------- devices on the sink row
# Body centres (CPL rows: Q2 68.05, BR1 94.2; Q3/Q5/Q6 = footprint anchor + 5.45, the centre pin)
FET_X = {"Q5": 9.95, "Q6": 27.95, "Q3": 50.05, "Q2": 68.05}
FET_SIDE = {"Q5": "HS", "Q6": "LS", "Q3": "LS", "Q2": "HS"}
FET_LEG = {"Q5": "B", "Q6": "B", "Q3": "A", "Q2": "A"}
TAB_NET = {"Q5": "bus_p", "Q6": "sw_b", "Q3": "sw_a", "Q2": "bus_p", "BR1": "(plastic back)"}   # [M11] table section 1
BR1_X = 94.2
BR1_X_SPAN = (79.6, 109.2)          # F.Fab, [M11]
Y_TAB = 1.835                       # FET tab plane, F.Fab, [M11]
Y_BR1_BACK = 2.30                   # BR1 back face, [M11]
Y_FET_LEAD = 4.215                  # lead-row centre, [M11]
Y_BR1_LEAD = 4.6
FET_DRILL = 1.8                     # temper:TO-247-3_Vertical_D1.8 since stage 57 (DECISIONS 87; 1.5 before), [M11]
BR1_DRILL = 1.6                     # FOOTPRINTS.md F6
Y_PAD_EDGE_FET = 1.965              # nearest FET pad copper to the edge, [M11]
Y_EDGE_COPPER = 0.6                 # HOT pours on all four layers come to 0.6 mm from the edge, [M11]
X_BOARD_MIN = 0.0

# TO-247 outline, [IPW] p.12 (min, max)
TO247 = dict(A=(4.70, 5.30), A1=(2.20, 2.60), A2=(1.50, 2.50), b=(1.00, 1.40), b1=(1.60, 2.41), b2=(2.57, 3.43),
             c=(0.38, 0.89), D=(20.70, 21.50), D1=(13.08, 17.65), D2=(0.51, 1.35), E=(15.50, 16.30), E1=(12.38, 14.15),
             L=(19.80, 20.40), L1=(3.85, 4.50))
# b = lead width in the hole, b1 / b2 = outer / centre lead width above the shoulder (stage 57: the 1.72-1.93 mm
# finished hole admits a small outer shoulder, b1 >= 1.60; only b2 is always wider), so the body seats on pin 2 at L1.
TAB_AREA = (151.2, 240.1)           # exposed drain metal, [T03]
RTH_JC_FET = 0.28                   # max, [IPW] p.3
TJ_MAX_FET = 150.0                  # [IPW] p.3
TJ_TARGET_FET = 125.0               # power-stage design target (docs/evidence/2026-10-12-thermal-trip-ladder-l3.md)
LEAD_X_PLAY = None                  # not used: x is set by the 5.44 pitch in 1.8 mm holes

# GBJ2510, [GBJ]
GBJ = dict(A=(29.70, 30.30), B=(19.70, 20.30), L=(4.40, 4.80), lead_t=(0.60, 0.80), lead_w=(0.90, 1.10),
           hole=(3.10, 3.40), S=(10.80, 11.20), H=(2.00, 2.40))
# [GBJ] p.4 read from the drawing: R lead thickness, I lead width, N mounting-hole diameter, S hole centre above the body
# bottom, H a 2.0-2.4 mm wide lead feature (wider than the 1.6 mm hole, so BR1 seats on it) whose position along the
# lead is NOT dimensioned: BR1's seated height is measured on a loose part (README section 5).
BR1_AREA = 29.70 * 19.70            # rear face, min outline (as stack_calc.py)
RTH_JC_BR1_ELEM = 1.0               # typ per element, [GBJ] p.2
TJ_MAX_BR1 = 150.0                  # [GBJ] (as stack_calc.py)
BR1_CASE_VRMS = 2500                # case dielectric strength, [GBJ] p.1
BR1_SCREW_TORQUE_MAX_NM = 5.0 * 0.113   # 5.0 in-lb, [GBJ] p.1

# ---------------------------------------------------------------- sink: Wakefield 511-3M, [WAK]
SINK_PN = "Wakefield-Vette 511-3M"
SINK_WIDTH = 132.33                 # base width (along x)
SINK_LEN = 76.2                     # cut length (along z): fins vertical
SINK_HEIGHT = 59.7                  # base + fins (along -y), milled 'M' series
SINK_BASE_T = 5.6                   # A = 0.220 in, milled
SINK_FIN_PITCH = 8.7                # C = 0.342 in
SINK_FLATNESS = 0.002               # per unit length (in/in = mm/mm), milled; 0.05 was a mis-conversion of 0.002 in/in. No tool reads it
RSA_NAT = 0.90                      # C/W natural convection, distributed sources, 50 C rise
RSA_NAT_RISE = 50.0
RSA_FORCED_100CFM = 0.12            # C/W at 100 CFM, shrouded (not our fan; not used for any claim)
K_6063 = 200.0                      # W/mK, 6063-T5 (EST, handbook class 200-209)
SINK_X0 = -12.0                     # placed x -12.0 .. 120.33
Z_SINK_BOTTOM = 4.5                 # sink lower edge above the board top; set with a 4.5 mm gauge at assembly
Z_SINK_TOL = 0.3                    # gauge-set (4.5 mm drill-bit shank or feeler stack), brackets then locked

# ---------------------------------------------------------------- insulator strip candidates, [HNK]
# psi -> thermal impedance C-in2/W (ASTM D5470, includes interfacial resistance)
PADS = {
    "SIL PAD K-10 0.152 mm": dict(t=0.152, bd_vac=6000, er=3.7, carrier="polyimide",
                                  z={10: 0.86, 25: 0.56, 50: 0.41, 100: 0.38, 200: 0.33},
                                  pn="Bergquist 2165804 (SPK10, 0.006 in, adhesive one side, 304.8 x 292.1 mm)"),
    "SIL PAD 2000 0.254 mm": dict(t=0.254, bd_vac=4000, er=4.0, carrier="fiberglass",
                                  z={10: 0.57, 25: 0.43, 50: 0.33, 100: 0.25, 200: 0.20},
                                  pn="Bergquist SP2000-0.010-00-1212 (304.8 x 304.8 mm)"),
    "SIL PAD 900S 0.229 mm": dict(t=0.229, bd_vac=5500, er=6.0, carrier="fiberglass",
                                  z={10: 0.95, 25: 0.75, 50: 0.61, 100: 0.47, 200: 0.41},
                                  pn="Bergquist SP900S-0.009-AC-1212 (304.8 x 304.8 mm, adhesive one side)"),
}
PAD_CHOICE = "SIL PAD 2000 0.254 mm"   # decided in README section 3 from bench_thermal.py's table

# strip extent on the sink face (one continuous strip under Q5..BR1)
STRIP_X = (-3.0, 111.5)
STRIP_TOP_Z = 32.0                  # 6.5 mm over the highest tab metal (25.49)
STRIP_OVERHANG = 2.5                # strip bottom hangs this far below the sink's lower edge (scribed line on the strip)
STRIP_OVERHANG_TOL = 0.3
STRIP_PLACE_TOL = 0.5               # hand placement of the strip ends and top (EST)
X_GROOVE_PD3 = 1.5                  # IEC 60335-1 cl. 29.2 / IEC 60664-1 'X': gaps narrower than this are bridged (PD3; PD2 1.0)
FET_POS_TOL = 0.465                 # device x play in its holes: (1.93 largest finished hole - 1.00 lead b min) / 2 (stage 57)
H_SMD_MAX = 1.1                     # tallest part under the clamp bar: SOD-128 D6-D9 (EST from the package class)

# BR1 stack: grease + aluminium shim on the sink, then the strip, then BR1 (BR1 sits 0.465 mm behind the tab plane)
SHIM_T = 0.508                      # 0.020 in 6061 shim (EST k below)
K_SHIM = 167.0                      # W/mK, 6061-T6 (EST)
SHIM_SIZE = (28.0, 17.0)            # inside BR1's 29.7 x 19.7 back face
GREASE_BLT = 0.025                  # bond line (EST, TC-5622 TDS 0.02 mm)
# grease per area: optimistic DOWSIL TC-5622 0.06 C-cm2/W; conservative Henkel TIC1000A proxy 0.32 C/W x 0.2 in2 (stack_calc.py)
GREASE_CM2 = (0.06, 0.32 * 0.2 * 6.4516)

# ---------------------------------------------------------------- clamp
SPRING = dict(pn="Lee Spring LC 055E 03 S", L0=14.3, k=18.512, Ls=8.36, OD=9.14, hole=9.53, F_solid=113.94)   # [LEE]
FR4_T = (1.44, 1.76)                # 1.6 mm +/-10 % (EST; IPC-4101 class)
FR4_PAD = (14.0, 16.0)              # x, z
BAR = dict(t=9.525, h=25.4, x=(-11.0, 119.5), z=(6.0, 31.4))    # 6061 3/8 x 1 in flat bar
POCKET_DEPTH = 7.0                  # 3/8 in flat-bottom pocket
POCKET_DEPTH_TOL = 0.05             # +/- on the fab drawing (spring preload), jlc-mech-r1 section 1 row 1; no tool reads it
BAR_HOLE_D = 4.5                    # bar end holes, through (M4 clearance)
SPACER_L = 10.0                     # bar-to-sink spacer length (M4, aluminium)
BAR_SCREW_X = (-7.0, 115.5)
BAR_SCREW_Z = 18.7
SPRING_Z = 15.0                     # spring axis height (tab-metal middle band)
CLAMP_ACCEPT_N = (45.0, 102.0)      # DECISIONS 2026-10-09 R32 item 3 (comb acceptance per TO-247)
CLAMP_TARGET_MIN_N = 60.0           # M11 RECOMMENDATION 4.2: >= 60 N, target 80 N
E_6061 = 68.9e3                     # N/mm2 (EST, handbook)

# film-cap row behind the bar (C38-C41, courtyard front edge = 28.2 - 9.59/2)
Y_FILM_COURTYARD_FRONT = 28.2 - 9.59 / 2

# ---------------------------------------------------------------- thermal sensors and cut-off
TCO = dict(pn="Cantherm SDF DF110S", Tf=110.0, Th=86.0, tol=(-5.0, 0.0), rating="250 VAC 10 A", case="live metal")   # [CAN]
NTC = dict(pn="Vishay NTCALUG01A104GA", lug="M3", dw_vac=1500, ir_mohm_500v=100, t_max=150.0)                      # [NTC]
FW_TRIP_C = 95.0                    # firmware/config.yaml OVER_TEMP_THRESHOLD
HW_TRIP_BAND_C = (98.3, 104.6)      # controller thermal-sense comparator, 64-corner band (config.yaml doc text)

# ---------------------------------------------------------------- insulation floors used for the bench (basic)
# M11 RECOMMENDATION section 2 'Basic, for reference': clearance 0.8 mm (PD3 footnote) + 0.5 = 1.3 mm; creepage 4.0 mm
# (IEC 60335-1 Table 17 row iii PD3 IIIa; = row iv PD2 IIIa for the 300 V step-3 test, docs/evidence/2026-07-28-creepage-
# determination-brainstorm.md); type test 1250 V (Table 7 basic).
CREEPAGE_BASIC = 4.0
CLEARANCE_BASIC = 1.3
HIPOT_BASIC_VAC = 1250

# bench voltages
V_LINE_MAX_RMS = 132.0              # COMMISSIONING step 6 top of the variac ramp
V_STEP3_DC = 300.0                  # COMMISSIONING step 3 isolated supply
V_DIE_WORST = 435.7                 # OPEN-ITEMS S3 (s51 matrices, as-built network): worst die VDS, S2 fault case

# ---------------------------------------------------------------- fixture layout (drawing inputs, bench_cad.py)
NTC_XZ = (77.8, 40.0)               # M3 tapped, front face, between Q2 and BR1 above the strip
TCO_XZ = (94.2, 40.0)               # TCO body centre (horizontal along x), above BR1, the largest heat source
TCO_CLAMP_SCREW_XZ = (94.2, 47.0)   # M3 tapped for the cushioned loop clamp's tab
BOND_XZ = (110.0, 72.0)             # M4 tapped, PE bond ring lug (14 AWG G/Y)
BR1_SCREW = "M3 x 10 SHCS + ISO 7092 small-series M3 washer (6.0 OD: an ISO 7089 7.0 OD washer does not pass the 6.5 mm bar slot) into the sink's tapped hole, through BR1's 3.1-3.4 mm hole (GBJ N)"
BRACKET = dict(angle=(38.1, 38.1, 3.175), height=70.0)   # 1-1/2 x 1-1/2 x 1/8 in aluminium angle, one per sink end
STANDOFF_H = 15.0                   # nylon M3 male-female at H1, H3-H8; board top = 15 + 1.6 above the baseplate
BOARD_T = 1.6
BASEPLATE = dict(w=400.0, d=300.0, t=18.0, board_x0=30.0, board_y0=80.0)   # plywood; board (0,0) at (30, 80) from rear-left
WINDOW = dict(x=(-2.0, 112.0), y=(-2.0, 22.0))   # board coords: solder/rework access under the sink row
MOUNT_HOLES = {"H1": (285.0, 135.0, "metal allowed (nylon used)"), "H3": (6.0, 180.0, "nylon"), "H4": (86.0, 180.0, "nylon"),
               "H5": (24.0, 74.0, "nylon"), "H6": (88.0, 100.0, "nylon"), "H7": (128.0, 54.0, "nylon"),
               "H8": (194.0, 130.0, "nylon"), "H2": (223.0, 135.0, "EMPTY"), "H9": (142.0, 4.0, "EMPTY"),
               "H10": (152.0, 122.0, "EMPTY")}  # native-21/layout/board_only21.json; FAB-NOTE (H2, H9, H10 empty)
FAN = dict(pn="Cooltron FD1225B12W2-61-2NC1", size=120.0, depth=25.0, gap_to_fins=15.0)

# ---------------------------------------------------------------- owner decisions 2026-10-18: JLC solders the TO-247s
# JLC fabrication and assembly, read 2026-10-18 ([JLC] jlcpcb.com/capabilities/pcb-capabilities and
# /capabilities/pcb-assembly-capabilities; [JLCF] jlcpcb.com/help/article/98-PCB-Assembly-FAQs; [JLCB] JLC warpage blog)
PTH_TOL = (-0.08, 0.13)             # finished plated-hole diameter about the drill, [JLC]
HOLE_POS_TOL = 0.075                # hole position, [JLC]
BOW_TWIST = 0.0075                  # IPC bow/twist limit for SMT boards, as quoted by [JLCB]; no JLC guarantee was found
BOARD_XY = (290.0, 190.0)           # FAB-NOTE 'Size' (L-shaped outline; the bounding box is used)
A1_LOT_TOL = 0.05                   # EST: within-lot spread of A1 (one DigiKey lot, D-8); the datasheet range is the bound
HOLE_DIA_LOCAL_TOL = 0.02           # EST: hole-diameter spread inside one board (same drill, same plating)
FET_FLOAT_MAX = 1.0                 # acceptance: body bottom <= L1 max + 1.0 mm above the board (unseated float)

# soldered-lead mechanics (bench_mech.py)
E_LEAD = 117.0e3                    # N/mm2, EST: copper lead frame (C194 class)
SIGMA_LEAD_ALLOW = 200.0            # N/mm2, EST: ~0.55 x a 360 MPa C194 H02 yield; the clamp must stay under it
Z_PIVOT = 0.0                       # EST: a soldered TO-247 rotates about its leads at the board top
PAD_COMPLIANCE = 0.010              # mm, EST: SIL PAD 2000 thickness change over the clamp's force range (no catalogue data)

# per-device shims (selected at fit, under the strip, greased), and the selectable FR-4 pad
SHIM_STEP = 0.025                   # 0.001 in: shim stock steps
SHIM_LAYERS_MAX = 3                 # at most three layers, each face greased (thermal model takes all three)
K_SHIM_FET = 109.0                  # W/mK, EST: brass shim stock (aluminium 167 is better; brass is the bound)
SHIM_MAX_DESIGN = 2.2               # mm: thermal model's thickest FET shim; bench_tolerance.py asserts it covers the stack
SHIM_FET_SIZE = (16.0, 22.0)        # x, z: covers E1 max x D1 max; inside the 18 mm pitch with 2 mm to spare
SHIM_FET_Z0 = Z_SINK_BOTTOM + 1.0   # shim lower edge 1.0 mm above the sink's lower edge (creepage rows stay sink-limited)
FR4_THIN_T = (0.71, 0.87)           # 1/32 in sheet, +/-10 % (EST) for devices whose shim would over-compress the spring

# BR1 (DNP at JLC; fitted by the owner before COMMISSIONING step 5)
BR1_DRILL_FIN = (1.6 + PTH_TOL[0], 1.6 + PTH_TOL[1])
BR1_SEAT_Z_EST = 2.2                # EST seated height of the body bottom (on the H feature): MEASURE a loose part first
BR1_LIFT = 0.2                      # drill the sink hole this much high, so BR1 hangs on its screw, never on its leads
BR1_HOLE_Z = BR1_SEAT_Z_EST + sum(GBJ["S"]) / 2 + BR1_LIFT
BAR_SLOT = dict(x=BR1_X, w=6.5, z=(BR1_HOLE_Z - 4.0, BR1_HOLE_Z + 4.0))   # driver access to BR1's screw through the bar
WINDOW_BR1 = dict(x=(75.0, 115.0), y=(22.0, 45.0))   # window extension: bottom preheat beside BR1 while the iron works
PREHEAT_BOARD_C = (100.0, 110.0)    # board bottom at BR1: >= 100 C (PROTOTYPE-LOT / FAB-NOTE); 110 cap (EST, film caps)
SINK_MAX_DURING_SOLDER_C = 80.0     # TCO off the sink, or the sink kept <= Tf - 24 = 86 C ([CAN]); 80 keeps the bench rule
TCO_QTY = dict(fitted=1, spare=4)   # one-shot part: a trip or a solder overheat consumes one

# ---------------------------------------------------------------- alternatives considered (compare_mounts.py)
# [DKS] DigiKey heat-sink filter, keyword TO-247, default order, read 2026-10-18 (362 results; the first 25 rows were read).
# width = across the device (x here), length = along the device (z), fin = depth off the tab (y). R in C/W.
# PC-pin types are board-mount: here they would hang off the board edge with no pins anchored.
CATALOG_TO247 = [
    dict(pn="Ohmite WV-T247-101E", dk_id=2071312, attach="clip + PC pin", w=23.40, l=32.0, fin=16.0, r_nat=9.0, r_forced=(8.0, 500), stock=17288, usd=3.28),
    dict(pn="Ohmite WA-T247-101E", dk_id=2202818, attach="clip + PC pin", w=23.40, l=32.0, fin=16.0, r_nat=11.0, r_forced=(8.0, 500), stock=42741, usd=4.04),
    dict(pn="HSK-045-09 (mfr not shown)", dk_id=26224191, attach="bolt on", w=22.80, l=75.0, fin=16.0, r_nat=8.21, r_forced=None, stock=302, usd=2.41),
    dict(pn="Wakefield-Vette 657-15ABPE", dk_id=5068322, attach="clip + PC pin", w=19.40, l=15.0, fin=31.5, r_nat=None, r_forced=None, stock=467, usd=2.60),
    dict(pn="Ohmite C247-025-1VE", dk_id=2627379, attach="clip + PC pin", w=38.10, l=25.0, fin=18.03, r_nat=None, r_forced=(6.0, 350), stock=1610, usd=6.38),
    dict(pn="Ohmite R2A-CT4-38E", dk_id=2793222, attach="clip + PC pin", w=35.05, l=38.1, fin=22.1, r_nat=8.6, r_forced=(1.0, 800), stock=7389, usd=5.58),
    dict(pn="Ohmite FA-T220-38E", dk_id=2416492, attach="bolt on + PC pin", w=41.60, l=38.1, fin=25.0, r_nat=3.8, r_forced=(1.5, 600), stock=13795, usd=3.91),
]
SINK_GAP_MIN = 0.5                  # EST: hand-fitting gap between neighbouring per-device sinks (both PE: no electrical gap)
# [HNK] p.28 GAP PAD 5000S35: k 5.0 W/mK, fibreglass carrier, 0.020-0.125 in, breakdown > 5000 Vac, Young's modulus
# 121 kPa, impedance of the 0.040 in sheet at 10 / 20 / 30 % strain 0.37 / 0.32 / 0.29 C-in2/W (data stop at 30 %).
GAP5000 = dict(k=5.0, t_in=(0.020, 0.040, 0.060, 0.080, 0.100, 0.125), bd_vac=5000, E_kPa=121.0,
               z_040={0.10: 0.37, 0.20: 0.32, 0.30: 0.29}, strain=(0.10, 0.30))
