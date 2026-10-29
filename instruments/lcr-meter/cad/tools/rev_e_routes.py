# Rev E copper, executed inside cad/tools/rev_e.py (names: parts, routing, RELAYS, DRV_Y, RLY_Y).
# Hand routing: every segment and via is given by coordinates.  Layers: F.Cu parts side, In1 GND
# plane, In2 and B.Cu signal.


def T(net, layer, *pts, w=0.2):
    routing['tracks'].append({'net': net, 'layer': layer, 'width': w, 'points': [list(p) for p in pts]})


def V(net, x, y, d=0.6):
    routing['vias'].append({'net': net, 'at': [x, y], 'diameter': d, 'drill': 0.3})


def dropvia(net, x, y):
    n = len(routing['vias'])
    routing['vias'] = [v for v in routing['vias']
                       if not (v['net'] == net and abs(v['at'][0] - x) < 0.01 and abs(v['at'][1] - y) < 0.01)]
    assert len(routing['vias']) == n - 1, (net, x, y)


def drop(net, layer, *pts):
    """Remove a Rev D segment of `net` on `layer` that has every point of `pts` on it."""
    keep = []
    for t in routing['tracks']:
        hit = t['net'] == net and t['layer'] == layer and all(
            any(abs(q[0] - p[0]) < 0.01 and abs(q[1] - p[1]) < 0.01 for q in t['points']) for p in pts)
        if not hit:
            keep.append(t)
    assert len(keep) < len(routing['tracks']), (net, layer, pts)
    routing['tracks'] = keep


TOP, BOT = RLY_Y - 4.78, RLY_Y + 4.78          # relay pad rows (pins 6-10 north, 1-5 south)

# ------------------------------------------------------------ -12 V: reroute north of the TIA keepout
# Rev D ran -12 V on In2 along y 121 under the new relay row.  U7 also reaches -12 V from the east
# (via 174.38,103.29), so the west feed now joins that branch north of the summing-node keepout.
drop('-12V', 'In2.Cu', (153.5, 113.5393), (153.5, 121))
drop('-12V', 'In2.Cu', (153.5, 121), (165.3, 121))
drop('-12V', 'In2.Cu', (165.3, 121), (165.3, 114.1393))
drop('-12V', 'In2.Cu', (165.3, 114.1393), (165.4091, 114.0302))
drop('-12V', 'In2.Cu', (165.4091, 114.0302), (165.7261, 114.0302))
T('-12V', 'In2.Cu', (153.5, 113.5393), (157.6, 109.4393), (157.6, 103.5), (173.2, 103.5), (174.3798, 103.2932))

# ------------------------------------------------------------ TIA_OUT: B.Cu feed, In2 bus at y 126.2
T('TIA_OUT', 'F.Cu', (165.4, 106.7), (164.0, 106.7))                    # U7.1 to C104.2 (Rev D)
T('TIA_OUT', 'B.Cu', (165.1, 102.0), (158.6, 102.0), (158.6, 126.2))
V('TIA_OUT', 158.6, 126.2)
T('TIA_OUT', 'In2.Cu', (152.5, 126.2), (182.3, 126.2))
# ------------------------------------------------------------ SOURCE_BUF: 47 ohm isolation, In2 bus y 129.6
# U6A (unity follower, feedback at the pin) drives SRC_DRV; R104 47 ohm isolates the relay bus,
# whose extracted board copper (9.8 pF) plus the relay capacitances took the driver loop to 38.5 deg
# (validation/stability-full-chain, reverelaycng100).  The Rev D pin straps under U6 follow the pins.
parts['U6']['pins'].update({'1': 'SRC_DRV', '2': 'SRC_DRV'})
for t in routing['tracks']:
    if t['net'] == 'SOURCE_BUF' and all(168.5 <= x <= 171.0 and 88.5 <= y <= 92.5 for x, y in t['points']):
        t['net'] = 'SRC_DRV'
T('SRC_DRV', 'F.Cu', (169.3115, 91.8727), (169.0423, 91.6035), (169.0423, 89.5806), (169.6604, 88.9625))
V('SRC_DRV', 169.6604, 88.9625)
T('SRC_DRV', 'In2.Cu', (169.6604, 88.9625), (170.2229, 88.4), (173.0, 88.4), (174.6, 86.8), (174.6, 85.8))
V('SRC_DRV', 174.6, 85.8)
T('SRC_DRV', 'F.Cu', (174.6, 85.8), (175.675, 85.8))
add('R104', 'R47', 'afe', {'1': 'SRC_DRV', '2': 'SOURCE_BUF'}, (176.5, 85.8, 0))
T('SOURCE_BUF', 'F.Cu', (177.325, 85.8), (178.4, 85.8))
V('SOURCE_BUF', 178.4, 85.8)
# down x 185.5, 3.4 mm clear of DUT_HI on B.Cu at x 188.9 (stacked at x 188.8 it coupled 2.4 pF)
T('SOURCE_BUF', 'In2.Cu', (178.4, 85.8), (178.4, 87.6), (179.2, 88.4), (184.5, 88.4), (185.5, 89.4),
  (185.5, 129.6), (152.5, 129.6))
for ref, x, *_ in RELAYS:
    V('TIA_OUT', x, 125.3)
    T('TIA_OUT', 'F.Cu', (x, TOP), (x, 125.3))
    T('TIA_OUT', 'In2.Cu', (x, 125.3), (x, 126.2))
    V('SOURCE_BUF', x, 130.65)
    T('SOURCE_BUF', 'F.Cu', (x, BOT), (x, 130.65))
    T('SOURCE_BUF', 'In2.Cu', (x, 130.65), (x, 129.6))

# ------------------------------------------------------------ RF legs from R43-R45 pin 2 (x 161.875)
T('RF5K', 'F.Cu', (161.875, 117.3), (156.0, 117.3), (155.04, 118.26), (155.04, TOP))
T('RF100', 'F.Cu', (161.875, 111.8), (159.4, 111.8))
V('RF100', 159.4, 111.8)
T('RF100', 'In2.Cu', (159.4, 111.8), (159.4, 124.2), (170.04, 124.2), (170.04, 125.3))
V('RF100', 170.04, 125.3)
T('RF100', 'F.Cu', (170.04, TOP), (170.04, 125.3))
T('RF100K', 'F.Cu', (161.875, 113.7), (160.0, 113.7))
V('RF100K', 160.0, 113.7)
T('RF100K', 'In2.Cu', (160.0, 113.7), (160.0, 123.5), (184.84, 123.5), (184.84, 125.3))
V('RF100K', 184.84, 125.3)
T('RF100K', 'F.Cu', (184.84, TOP), (184.84, 125.3))

# ------------------------------------------------------------ RG legs and DUT_HI (B.Cu, east edge)
# HCUR (J3) along y 57.5 behind the jacks, under H2's corner at y 59, down the east edge to the RG row
T('DUT_HI', 'B.Cu', (108.0, 51.0), (108.0, 57.5), (180.5, 57.5), (182.0, 59.0), (188.9, 59.0), (188.9, 137.75),
  (155.04, 137.75), w=0.25)
for ref, x, rng, rg, rf, rgnet, setnet in RELAYS:
    T(rgnet, 'F.Cu', (x + 2.54, BOT), (x + 2.54, RLY_Y + 8.0 - 0.825))
    V('DUT_HI', x + 2.54, 137.75)
    T('DUT_HI', 'F.Cu', (x + 2.54, RLY_Y + 8.0 + 0.825), (x + 2.54, 137.75), w=0.25)

# ------------------------------------------------------------ coils
# VRLY: pin 10 to pin 1 on F.Cu inside each relay, via under pin 1, In2 bus along y 143.6.
for ref, x, *_ in RELAYS:
    T('VRLY', 'F.Cu', (x - 5.08, TOP), (x - 5.08, 135.0))
    V('VRLY', x - 5.08, 135.0)
    T('VRLY', 'In2.Cu', (x - 5.08, 135.0), (x - 5.08, 143.6))
    # flyback diode beside pin 5: anode to the SET node, cathode via to the VRLY bus
    T('VRLY', 'F.Cu', (x + 6.4, RLY_Y + 8.6 + 1.05), (x + 6.4, 138.6))
    V('VRLY', x + 6.4, 138.6)
    T('VRLY', 'In2.Cu', (x + 6.4, 138.6), (x + 6.4, 143.6))
T('VRLY', 'In2.Cu', (145.4, 143.6), (188.7, 143.6))
V('VRLY', 145.4, 143.6)
T('VRLY', 'F.Cu', (145.4, 143.6), (145.4, 145.2))
T('VRLY', 'F.Cu', (144.025, 145.2), (146.725, 145.2), w=0.4)
T('VRLY', 'F.Cu', (162.25, 135.6), (162.42, 135.0))                      # D5 cathode to K1 pin 1 via
# 5 V to R101 on B.Cu from the FB1 feed via; the via sits 0.275 mm off the R101.1 land (no via-in-pad)
T('5V', 'B.Cu', (105.6906, 122.7729), (141.4, 122.7729), (141.4, 145.2), w=0.3)
V('5V', 141.4, 145.2)
T('5V', 'F.Cu', (141.4, 145.2), (142.375, 145.2), w=0.3)


def drive(x, qx, gate_r_x):
    """Gate, pull-down and GND copper of one driver (template of rev_e.driver)."""
    gate = parts_by_xy_gate[qx]
    T(gate, 'F.Cu', (gate_r_x + 0.825, DRV_Y - 0.95), (qx - 0.9375, DRV_Y - 0.95))
    T(gate, 'F.Cu', (gate_r_x + 0.825, DRV_Y - 0.95), (gate_r_x + 0.825, DRV_Y + 0.8))
    T('GND', 'F.Cu', (gate_r_x - 0.825, DRV_Y + 0.8), (gate_r_x - 0.825, 142.8))
    V('GND', gate_r_x - 0.825, 142.8)
    T('GND', 'F.Cu', (qx - 0.9375, DRV_Y + 0.95), (qx - 0.9375, 142.8))
    V('GND', qx - 0.9375, 142.8)
    gpio = gate[:-2]
    T(gpio, 'F.Cu', (gate_r_x - 0.825, DRV_Y - 0.95), (gate_r_x - 0.825, 138.6))
    V(gpio, gate_r_x - 0.825, 138.6)
    return gpio, gate_r_x - 0.825


parts_by_xy_gate = {}
for q in ('Q2', 'Q3', 'Q4', 'Q5'):
    parts_by_xy_gate[parts[q]['pcb'][0]] = parts[q]['pins']['1']
gpio_via = {}
for ref, x, rng, rg, rf, rgnet, setnet in RELAYS:
    qx = x + 5.08 - 0.9375
    g, gx = drive(x, qx, qx - 3.4425)
    gpio_via[g] = gx
    T(setnet, 'F.Cu', (x + 5.08, BOT), (x + 5.08, DRV_Y))                  # pin 5 to drain
    T(setnet, 'F.Cu', (x + 6.4, RLY_Y + 8.6 - 1.05), (x + 5.08, RLY_Y + 8.6 - 1.05))   # diode anode
g, gx = drive(None, 164.0, 164.0 - 3.4425)
gpio_via[g] = gx

# RST: F.Cu bus north of the relays, down the K2/K1 gap (x 160.6) to Q2 and D5
T('RLY_RST', 'F.Cu', (157.58, 120.6), (187.38, 120.6))
for ref, x, *_ in RELAYS:
    T('RLY_RST', 'F.Cu', (x + 5.08, 120.6), (x + 5.08, TOP))
T('RLY_RST', 'F.Cu', (160.6, 120.6), (160.6, 138.3), (164.9375, 138.3))
T('RLY_RST', 'F.Cu', (164.9375, DRV_Y), (164.9375, 137.3), (164.35, 136.7), (164.35, 135.6))

# Driver GPIOs on B.Cu: four lines from the MCU along y 85.45-86.8, down x 142.4-144.2, east along
# the driver row.  Order: SET_MED ends first, then RESET, SET_LO, SET_HI.
ROW = [  # net, MCU pin breakout y on B.Cu, vertical x, driver-row y
    ('RNG_SET_MED', 85.45, 146.8, 139.25), ('RNG_RESET', 85.9, 146.2, 140.2),
    ('RNG_SET_LO', 86.3, 145.6, 140.9), ('RNG_SET_HI', 86.8, 145.0, 141.6)]
for net, by, vx, ry in ROW:
    T(net, 'B.Cu', (vx, by), (vx, ry), (gpio_via[net], ry), (gpio_via[net], 138.6))

# ------------------------------------------------------------ four-terminal jacks (J3 HCUR, J7 HPOT, J8 LPOT, J9 LCUR)
# The J3 header's copper is pruned with it; each jack gets its own run.  Layers keep the four apart:
# HCUR B.Cu, HPOT In2, LPOT F.Cu then In2, LCUR F.Cu then B.Cu.
# HPOT: In2 along y 59.5, down x 171 to U6.5 (HIGH follower +IN) on the Rev D F.Cu approach
T('HPOT', 'In2.Cu', (130.0, 51.0), (130.0, 59.5), (171.0, 59.5), (171.0, 87.6))
V('HPOT', 171.0, 87.6)
T('HPOT', 'F.Cu', (171.0, 87.6), (171.0, 88.3), (167.0, 88.3), (167.0, 89.0), (165.0, 89.0), (165.0, 90.025),
  (165.8875, 90.025), w=0.25)
# R105 (HCUR-HPOT default) between the two runs
V('DUT_HI', 135.0, 57.5)
T('DUT_HI', 'F.Cu', (135.0, 57.5), (136.175, 58.5))
V('HPOT', 139.0, 59.5)
T('HPOT', 'F.Cu', (139.0, 59.5), (137.825, 58.5))
# LPOT: F.Cu along y 62 to R106, In2 down x 175.8 (west of the SOURCE_BUF via, east of the GND via at
# 174.98,104.8), back to F.Cu on the Rev D approach to U7.5 (LOW follower +IN)
T('LPOT', 'F.Cu', (152.0, 51.0), (152.0, 62.0), (177.0, 62.0), (177.0, 61.975), w=0.25)
V('LPOT', 175.8, 62.0)
T('LPOT', 'In2.Cu', (175.8, 62.0), (175.8, 110.275))
V('LPOT', 175.8, 110.275)
T('LPOT', 'F.Cu', (175.8, 110.275), (174.3, 110.275), (173.0, 108.975), (170.1125, 108.975), w=0.25)
# LCUR (DUT_LO): F.Cu along y 60.3 past R106 to R107, B.Cu down x 179.5 to the Rev D run into R94
T('DUT_LO', 'F.Cu', (174.0, 51.0), (174.0, 60.3), (184.54, 60.3), (184.54, 61.175), w=0.25)
V('DUT_LO', 179.5, 60.3)
T('DUT_LO', 'B.Cu', (179.5, 60.3), (179.5, 100.54), (173.71, 100.54), (170.0, 104.25), (166.175, 104.25), w=0.25)
V('DUT_LO', 166.175, 104.25)
T('DUT_LO', 'F.Cu', (166.175, 104.25), (166.175, 105.3), w=0.25)
# C78 (100 pF to GND) on the LCUR corner
V('DUT_LO', 179.5, 100.54)
T('DUT_LO', 'F.Cu', (179.5, 100.54), (179.5, 101.575), w=0.25)
T('GND', 'F.Cu', (179.5, 103.225), (179.5, 104.2))
V('GND', 179.5, 104.2, 0.45)

# ------------------------------------------------------------ K4 reference relay (182, 70) and its driver
T('DUT_HI', 'B.Cu', (182.6, 59.0), (182.6, 61.8), w=0.25)             # COM2 tap off the HCUR run
V('DUT_HI', 182.6, 61.8)
T('DUT_HI', 'F.Cu', (182.6, 61.8), (182.0, 62.4), (182.0, 65.22), w=0.25)
T('REF_A', 'F.Cu', (184.54, 62.825), (184.54, 65.22))                  # R107 to NO2 (pin 7)
T('RLY_RST', 'F.Cu', (187.08, 65.22), (187.08, 62.6))                   # RESET coil: B.Cu to the RST bus
V('RLY_RST', 187.08, 62.6)
T('RLY_RST', 'B.Cu', (187.08, 62.6), (187.08, 120.6))
V('RLY_RST', 187.08, 120.6)
# VRLY: In2 up x 186.2 from the coil bus, west along y 77 to pins 1/10, stub to the D9 cathode via
T('VRLY', 'In2.Cu', (186.2, 143.6), (186.2, 77.0), (176.92, 77.0))
V('VRLY', 176.92, 77.0)
T('VRLY', 'F.Cu', (176.92, 77.0), (176.92, 65.22))
T('VRLY', 'F.Cu', (188.6, 79.45), (188.0, 80.05), (188.0, 80.2))
V('VRLY', 188.0, 80.2)
T('VRLY', 'In2.Cu', (188.0, 80.2), (186.2, 80.2))
# SET: pin 5 to the Q6 drain, D9 anode beside it
T('RLY_SET_REF', 'F.Cu', (187.08, 74.78), (187.08, 81.0))
T('RLY_SET_REF', 'F.Cu', (188.6, 77.35), (187.08, 77.35))
# gate network (R108 at 182.7, 80.05; R109 at 182.7, 81.8) and grounds
T('RNG_SET_REF_G', 'F.Cu', (183.525, 80.05), (185.205, 80.05))
T('RNG_SET_REF_G', 'F.Cu', (183.525, 80.05), (183.525, 81.8))
T('GND', 'F.Cu', (181.875, 81.8), (181.875, 82.9))
V('GND', 181.875, 82.9, 0.45)
T('GND', 'F.Cu', (185.205, 81.95), (185.205, 82.9))
V('GND', 185.205, 82.9, 0.45)
# GPIO14 (U1 pin 17): north to a via, B.Cu along y 81.6 (between the GND vias at 89.6 and 93.3),
# F.Cu over the 12 V B.Cu run at x 173.6 to R108
T('RNG_SET_REF', 'F.Cu', (83.8, 83.5625), (83.8, 82.1))
V('RNG_SET_REF', 83.8, 82.1, 0.45)
T('RNG_SET_REF', 'B.Cu', (83.8, 82.1), (84.3, 81.6), (172.5, 81.6))
V('RNG_SET_REF', 172.5, 81.6, 0.45)
T('RNG_SET_REF', 'F.Cu', (172.5, 81.6), (174.05, 80.05), (181.875, 80.05))

# ------------------------------------------------------------ Rev D leftovers under the codec and legs
for x, y in [(133.7476, 105.4147), (134.8592, 95.25), (150.2422, 83.5845), (149.2643, 107.8039),
             (152.325, 99.3), (152.325, 88.3), (141.25, 91.15), (141.25, 104.95), (139.5, 91.55),
             (137.525, 101.7)]:
    dropvia('GND', x, y)
for x, y in [(139.5, 101.3427), (155, 104), (155, 93)]:
    dropvia('3V3', x, y)
drop('3V3', 'B.Cu', (130.9985, 102.7065), (138.1362, 102.7065))
drop('3V3', 'B.Cu', (138.1362, 102.7065), (139.5, 101.3427))
drop('3V3', 'In2.Cu', (150.8446, 105.4147), (143.572, 105.4147))
drop('3V3', 'In2.Cu', (143.572, 105.4147), (139.5, 101.3427))
drop('3V3', 'In2.Cu', (150.8446, 105.4147), (154.5, 105.4147))
drop('3V3', 'In2.Cu', (154.5, 105.4147), (154.5, 104.5))
drop('3V3', 'In2.Cu', (154.5, 104.5), (155, 104))
drop('3V3', 'In2.Cu', (155, 104), (155.3, 103.7))
drop('3V3', 'In2.Cu', (155.3, 103.7), (155.3, 93.3))
drop('3V3', 'In2.Cu', (155.3, 93.3), (155, 93))
drop('3V3', 'F.Cu', (155.0375, 104), (155, 104))
drop('3V3', 'F.Cu', (155.0375, 93), (155, 93))
dropvia('3V3', 79.1069, 79.8819)             # F.Cu passes straight through; its In2 run fed FB2
for x, y in [(136.4967, 61.8647), (107.5438, 62.4567), (122.9407, 72.1052), (111.7548, 58.6476),
             (104.7224, 68.0574)]:                # AD9833 / DDS-filter ground vias
    dropvia('GND', x, y)
for v in routing['vias']:                         # C6 ground via beside the SET_LO run: 0.45 mm
    if v['net'] == 'GND' and abs(v['at'][0] - 88.9275) < 0.01 and abs(v['at'][1] - 85.8121) < 0.01:
        v['diameter'] = 0.45

# ------------------------------------------------------------ codec U14 (141, 97.5)
# corner VSS pads A1-A4 leave outward (they sit on the pin-1/pin-24 diagonal) to their own vias
for x, y in [(140.5, 97.0), (141.5, 97.0), (140.5, 98.0), (141.5, 98.0)]:
    V('GND', x, y, 0.45)                                                   # exposed pad, filled
T('GND', 'F.Cu', (139.275, 95.775), (138.3, 95.775), (137.9, 95.4))     # A1
V('GND', 137.9, 95.4, 0.45)
T('GND', 'F.Cu', (139.275, 99.225), (138.7, 99.8))                      # A2
V('GND', 138.7, 99.8, 0.45)
T('GND', 'F.Cu', (142.725, 99.225), (142.37, 99.225))                   # A3 to pin 12
T('GND', 'F.Cu', (142.725, 98.87), (142.725, 99.225))                   # pin 13 to A3
T('GND', 'F.Cu', (142.25, 99.7), (142.9, 100.2))
V('GND', 142.9, 100.2, 0.45)
T('GND', 'F.Cu', (142.725, 95.775), (142.725, 95.0), (142.85, 94.75))   # A4
V('GND', 142.85, 94.75, 0.45)
# AVDD / VREF decoupling north of the package; 3V3A loop on x 141.25 east of the caps
T('3V3A', 'F.Cu', (140.25, 95.6), (140.25, 94.325))
T('3V3A', 'F.Cu', (140.725, 94.325), (141.25, 94.325), (141.25, 89.35), (140.975, 89.35))
T('3V3A', 'F.Cu', (141.25, 89.35), (141.25, 88.6))
V('3V3A', 141.25, 88.6, 0.45)
T('CODEC_VREF', 'F.Cu', (139.75, 95.6), (139.75, 95.25), (139.2, 94.7), (138.6, 94.7), (138.6, 94.325))
T('GND', 'F.Cu', (138.6, 92.775), (139.425, 92.0), (140.25, 92.775))
V('GND', 139.425, 92.0, 0.45)
T('GND', 'F.Cu', (140.25, 91.25), (140.25, 92.775))
# LDO U15 (133.5, 91.5): 5VA in from C67, 3V3A out through C68 to C60
T('5VA', 'F.Cu', (131.125, 92.45), (132.3625, 92.45))
T('5VA', 'F.Cu', (131.45, 92.45), (131.45, 90.55), (132.3625, 90.55))
T('GND', 'F.Cu', (132.3625, 91.5), (133.5, 91.5))
V('GND', 133.5, 91.5, 0.45)
T('GND', 'F.Cu', (130.4, 90.55), (129.4, 90.55))
V('GND', 129.4, 90.55, 0.45)
T('3V3A', 'F.Cu', (134.6375, 90.55), (135.6, 89.59), (136.7, 89.59))
T('3V3A', 'F.Cu', (137.425, 89.55), (139.525, 89.55))
T('GND', 'F.Cu', (136.7, 91.25), (137.7, 91.25))
V('GND', 137.7, 91.25, 0.45)
# 5VA from FB1/C103 (Rev D F.Cu run and In2 hop), up x 128.6 to C67
T('5VA', 'F.Cu', (108.525, 119.0), (120.2292, 107.2958), (124.396, 107.2958))
V('5VA', 124.396, 107.2958)
T('5VA', 'In2.Cu', (124.396, 107.2958), (127.6, 104.0918), (127.6, 97.6))
V('5VA', 127.6, 97.6)
T('5VA', 'F.Cu', (127.6, 97.6), (127.6, 93.5), (128.65, 92.45), (130.4, 92.45))
# DREG and IOVDD decoupling west of the package
T('CODEC_DREG', 'F.Cu', (139.1, 96.25), (136.575, 96.25))
T('CODEC_DREG', 'F.Cu', (136.5, 95.775), (136.5, 95.125))
T('GND', 'F.Cu', (135.025, 96.25), (133.8, 95.2), (134.45, 94.4))
V('GND', 133.8, 95.2, 0.45)
T('3V3', 'F.Cu', (139.1, 98.75), (136.175, 98.75))
T('3V3', 'F.Cu', (136.175, 99.575), (135.95, 100.275))
T('GND', 'F.Cu', (134.625, 99.1), (133.9, 99.9), (134.05, 101.0))
V('GND', 133.9, 99.9, 0.45)
T('3V3', 'F.Cu', (130.9985, 102.7065), (141.25, 102.7065))
T('3V3', 'F.Cu', (135.95, 102.7065), (135.95, 101.725))
# I2C: pull-ups under pins 7/8, bus vias either side
T('I2C_SCL', 'F.Cu', (139.75, 99.4), (139.75, 100.875))
T('I2C_SCL', 'F.Cu', (139.75, 100.875), (138.75, 100.875))
V('I2C_SCL', 138.75, 100.875, 0.45)
T('I2C_SDA', 'F.Cu', (140.25, 99.4), (140.25, 99.75), (141.25, 100.75), (141.25, 100.875))
T('I2C_SDA', 'F.Cu', (141.25, 100.875), (142.2, 100.875))
V('I2C_SDA', 142.2, 100.875, 0.45)
# I2S fan-out to staggered vias
I2S_VIA = {'I2S_BCLK': (137.85, 96.75), 'I2S_FSYNC': (137.15, 97.25), 'I2S_DOUT': (137.85, 97.75),
           'I2S_DIN': (137.15, 98.25)}
for net, (x, y) in I2S_VIA.items():
    T(net, 'F.Cu', (x, y), (139.1, y))
    V(net, x, y, 0.45)

# ------------------------------------------------------------ MCU (U1) to codec and relay drivers
# Rev D breakouts reused: pin 4 (SDO_A) DIN, 5 (SDO_B) DOUT, 6 (CS) BCLK, 7 (SCLK) FSYNC, 8 (CONVST)
# SET_HI, 9 (SDI) SET_LO, 11 (RESET) SDA, 13 (DDS_SCLK) RESET, 14 (DDS_SDATA) SET_MED; pin 12 new.
T('I2S_DIN', 'F.Cu', (85.4375, 88.4), (86.5401, 88.4), (86.779, 88.6389))
V('I2S_DIN', 86.779, 88.6389)
T('I2S_DIN', 'B.Cu', (86.779, 88.6389), (88.0401, 89.9), (121.6, 89.9), (128.1, 96.4), (134.4, 96.4),
  (136.25, 98.25), (137.15, 98.25))
T('I2S_DOUT', 'F.Cu', (85.4375, 88.0), (84.4761, 88.0), (84.0674, 88.4087))
V('I2S_DOUT', 84.0674, 88.4087)
T('I2S_DOUT', 'B.Cu', (84.0674, 88.4087), (84.4224, 88.0537), (86.9742, 88.0537), (87.386, 88.4655),
  (87.386, 88.489), (87.7093, 88.8123), (88.1662, 88.8123), (88.252, 88.7265), (122.792, 88.7265),
  (129.9695, 95.904), (134.8976, 95.904), (136.7435, 97.75), (137.85, 97.75))
T('I2S_BCLK', 'F.Cu', (85.4375, 87.6), (86.3466, 87.6), (86.7964, 88.0498), (87.7269, 88.0498), (87.9377, 88.2606))
V('I2S_BCLK', 87.9377, 88.2606)
T('I2S_BCLK', 'B.Cu', (87.9377, 88.2606), (133.0, 88.2606), (136.1, 91.3606), (136.1, 95.0), (137.85, 96.75))
T('I2S_FSYNC', 'F.Cu', (85.4375, 87.2), (86.9455, 87.2), (87.1917, 87.4462))
V('I2S_FSYNC', 87.1917, 87.4462)
T('I2S_FSYNC', 'B.Cu', (87.1917, 87.4462), (87.45, 87.7), (88.15, 87.7), (88.2, 87.75), (115.85, 87.75))
V('I2S_FSYNC', 115.85, 87.75, 0.45)
T('I2S_FSYNC', 'In2.Cu', (115.85, 87.75), (122.8, 94.7), (135.1, 94.7), (137.15, 96.75), (137.15, 97.25))
T('I2C_SDA', 'F.Cu', (85.4375, 85.6), (87.1977, 85.6), (87.2961, 85.5016), (87.3, 85.5), (87.75, 85.5))
V('I2C_SDA', 87.75, 85.5, 0.45)
T('I2C_SDA', 'In2.Cu', (87.75, 85.5), (88.55, 86.3), (88.6, 86.3), (88.65, 86.35), (88.75, 86.35),
  (88.8, 86.4), (95.4, 86.4), (108.5, 99.5), (108.5, 100.6))
V('I2C_SDA', 108.5, 100.6, 0.45)
T('I2C_SDA', 'B.Cu', (108.5, 100.6), (109.8, 101.9), (142.2, 101.9), (142.2, 100.875))
T('I2C_SCL', 'F.Cu', (85.4375, 85.2), (87.1, 85.2), (87.85, 84.45))
V('I2C_SCL', 87.85, 84.45, 0.45)
T('I2C_SCL', 'In2.Cu', (87.85, 84.45), (88.5, 85.1), (95.95, 85.1), (107.7, 96.85))
V('I2C_SCL', 107.7, 96.85, 0.45)
T('I2C_SCL', 'B.Cu', (107.7, 96.85), (111.725, 100.875), (138.75, 100.875))
T('RNG_SET_HI', 'F.Cu', (85.4375, 86.8), (87.75, 86.8))
V('RNG_SET_HI', 87.75, 86.8, 0.45)
T('RNG_SET_HI', 'B.Cu', (87.75, 86.8), (145.0, 86.8))
T('RNG_SET_LO', 'F.Cu', (85.4375, 86.4), (84.8, 86.4), (84.6, 86.6))
V('RNG_SET_LO', 84.6, 86.6, 0.45)
T('RNG_SET_LO', 'B.Cu', (84.6, 86.6), (87.25, 86.6), (87.55, 86.3), (145.6, 86.3))
T('RNG_RESET', 'F.Cu', (85.4375, 84.8), (86.0166, 84.8), (87.5814, 83.2352), (87.7944, 83.2352))
V('RNG_RESET', 87.7944, 83.2352)
T('RNG_RESET', 'B.Cu', (87.7944, 83.2352), (90.4592, 85.9), (146.2, 85.9))
T('RNG_SET_MED', 'F.Cu', (85.4375, 84.4), (88.0657, 81.7718), (89.8285, 81.7718), (90.8033, 82.7466),
  (96.3534, 82.7466))
V('RNG_SET_MED', 96.3534, 82.7466)
T('RNG_SET_MED', 'B.Cu', (96.3534, 82.7466), (99.0568, 85.45), (146.8, 85.45))

# ------------------------------------------------------------ input legs (F.Cu)
LEG = [  # name, row y, side, codec pin y, fan-in x
    ('C2M', 88.4, -1, 96.25, 143.7), ('C2P', 92.6, 1, 96.75, 144.3),
    ('C1M', 100.6, -1, 97.25, 144.3), ('C1P', 104.8, 1, 97.75, 143.7)]
DIV_IN = {  # R_series pin 2 (Rev D position) to the leg row; C2P steps west first, clear of the C44 12 V via
    'C2M': [(159.775, 90.2), (159.775, 88.4)], 'C2P': [(159.775, 91.8), (158.8, 91.8), (158.8, 92.6)],
    'C1M': [(159.775, 101.0), (159.775, 100.6)], 'C1P': [(159.775, 102.6), (159.775, 104.8)]}
for name, y, side, py, fx in LEG:
    T(f'{name}_DIV', 'F.Cu', *DIV_IN[name], (154.45, y))
    T(f'{name}_DIV', 'F.Cu', (157.6, y), (157.6, y + side * 0.775))
    T(f'{name}_DIV', 'F.Cu', (156.0, y), (156.0, y + side * 0.775))
    T('GND', 'F.Cu', (157.6, y + side * 2.425), (156.0, y + side * 2.375))
    V('GND', 156.8, y + side * 2.4, 0.45)
    T(f'{name}_CLP', 'F.Cu', (152.55, y), (146.725, y))
    T(f'{name}_PIN', 'F.Cu', (145.075, y), (fx, y), (fx, py), (142.9, py))
    # BAT54S: pin 1 GND via north, pin 2 3V3A via to the In2 column at x 147.6
    T('GND', 'F.Cu', (148.8625, y - 0.95), (148.8625, y - 1.95))
    V('GND', 148.8625, y - 1.95, 0.45)
    T('3V3A', 'F.Cu', (148.8625, y + 0.95), (147.6, y + 0.95))
    V('3V3A', 147.6, y + 0.95, 0.45)
T('3V3A', 'In2.Cu', (141.25, 88.6), (147.6, 88.6), (147.6, 105.75))

# ------------------------------------------------------------ source: OPA810 (U5) difference stage
# DAC_P on F.Cu north from U14.20 and west along y 74.9 (south of the 12 V F.Cu run) to R30;
# DAC_M up to a via, In2 north beside the OPA810 plane void, back to F.Cu at R31.
T('SOURCE_AC', 'F.Cu', (129.8125, 70.0), (130.0, 70.1875), (130.0, 72.175))
T('SOURCE_AC', 'F.Cu', (128.4, 70.0), (128.4, 71.225))
T('GND', 'F.Cu', (128.4, 72.775), (127.5, 72.775))
V('GND', 127.5, 72.775, 0.45)
T('DAC_P', 'F.Cu', (130.0, 73.825), (130.0, 74.9), (141.75, 74.9), (141.75, 95.6))
T('DAC_M', 'F.Cu', (142.25, 95.6), (142.25, 74.2))
V('DAC_M', 142.25, 74.2, 0.45)
T('DAC_M', 'In2.Cu', (142.25, 74.2), (142.25, 64.175), (139.0, 64.175))
V('DAC_M', 139.0, 64.175)
T('DAC_M', 'F.Cu', (139.0, 64.175), (137.0, 64.175))
T('SOURCE_FB', 'F.Cu', (135.3, 65.475), (136.6, 65.825))
T('SOURCE_FB', 'F.Cu', (133.8, 61.675), (133.8, 63.525))
T('EXCITE', 'F.Cu', (132.225, 61.675), (132.3805, 62.2451))
T('GND', 'F.Cu', (149.675, 145.2), (150.6, 145.2))                       # C112 ground
V('GND', 150.6, 145.2)
# J1 shield straps (Rev D): four pads share the number SH, so the pad-centre prune cannot see them
T('GND', 'F.Cu', (57.1, 72.675), (57.67, 73.245), (57.67, 73.8))
T('GND', 'F.Cu', (57.1, 81.325), (58.216, 81.325), (58.216, 80.746), (57.67, 80.2))

# ------------------------------------------------------------ SW1/SW2 (TS-1088 pads at x +-2.225)
T('GND', 'F.Cu', (61.7, 87.0), (62.225, 87.0))
T('RUN', 'F.Cu', (57.775, 92.0), (58.3, 92.0))
drop('RUN', 'F.Cu', (60.1267, 93.125), (59.0017, 92.0))
drop('RUN', 'F.Cu', (66.0471, 93.125), (60.1267, 93.125))
T('RUN', 'F.Cu', (59.0017, 92.0), (59.0017, 93.5), (66.0471, 93.5), (66.0471, 93.125))   # under SW2's wider pad
T('GND', 'F.Cu', (61.7, 92.0), (62.225, 92.0))
dropvia('GND', 62.8978, 91.8737)                 # the wider pad reaches the Rev D via's drill
drop('GND', 'F.Cu', (62.8978, 91.8737), (62.528, 91.8737))
V('GND', 63.25, 91.8737)
T('GND', 'F.Cu', (63.25, 91.8737), (62.528, 91.8737))
drop('BOOTSEL', 'F.Cu', (57.5983, 87.0), (57.5983, 92.9759))
drop('BOOTSEL', 'F.Cu', (57.5983, 92.9759), (61.9002, 97.2778))
drop('BOOTSEL', 'F.Cu', (58.3, 87.0), (57.5983, 87.0))
T('BOOTSEL', 'F.Cu', (57.775, 87.0), (56.5, 88.275), (56.5, 93.9), (57.6, 93.9), (60.9778, 97.2778),
  (61.9002, 97.2778))

# ------------------------------------------------------------ USB-C power entry: J1 VBUS -> U16 -> 5V
# VBUS leaves the J1 loop at its south corner and runs down the empty west strip (J2 is gone) on F.Cu.
T('USB_VBUS', 'F.Cu', (56.2386, 82.0767), (56.2386, 82.7), w=0.25)          # under the shield tab
T('USB_VBUS', 'F.Cu', (56.2386, 82.7), (55.0, 83.9386), (55.0, 119.25), (55.8, 120.05), (61.8625, 120.05), w=0.8)
T('USB_VBUS', 'F.Cu', (61.8625, 121.95), (60.0, 121.95), (60.0, 120.05))   # EN to IN, west of the GND via
T('GND', 'F.Cu', (61.8625, 121.0), (60.6, 121.0), w=0.3)    # via 0.35 mm off the U16.2 land
V('GND', 60.6, 121.0)
T('USB_VBUS', 'F.Cu', (61.8625, 118.35), (61.8625, 120.05), w=0.6)          # C113 on pin 1
T('GND', 'F.Cu', (61.8625, 116.45), (61.8625, 115.3), w=0.4)
V('GND', 61.8625, 115.3)
T('VBUS_ILIM', 'F.Cu', (64.1375, 121.0), (65.1, 121.0), (65.425, 121.325), (65.425, 123.6))
T('GND', 'F.Cu', (63.775, 123.6), (63.775, 124.6), w=0.3)                  # R110
V('GND', 63.775, 124.6)
dropvia('GND', 67.7495, 118.6755)                # Q1's source via; nothing lands on it now
# 5V crosses the J5 3V3 feed (F.Cu, x 66.49) on B.Cu: two vias each side, then up into C80.1.
T('5V', 'F.Cu', (64.1375, 120.05), (65.2, 120.05), w=0.6)
T('5V', 'F.Cu', (65.65, 119.65), (65.2, 120.05), (65.65, 120.55), w=0.6)
for x, y in ((65.65, 119.65), (65.65, 120.55), (69.2, 120.1), (70.2, 120.1)):
    V('5V', x, y)
T('5V', 'B.Cu', (65.65, 119.65), (66.1, 120.1), (70.2, 120.1), w=0.6)
T('5V', 'B.Cu', (65.65, 120.55), (66.1, 120.1), w=0.6)
T('5V', 'F.Cu', (69.2, 120.1), (69.2, 118.6), w=0.6)
T('5V', 'F.Cu', (70.2, 120.1), (70.2, 118.6), w=0.6)

# ------------------------------------------------------------ no via in an SMD land outside the exposed pads
# Without POFV a via drill inside a small land wicks solder from the joint.  The thermal-pad vias of U1, U11,
# U12, U13 and U14 stay (bottom-tented, per the TI package notes); these Rev D vias move off their lands.
# R3.2 (USB_DM_MCU): the via sat in the land; dog-bone to the gap between R3's lands, 0.2 mm from each.
dropvia('USB_DM_MCU', 83.9, 92.45)
drop('USB_DM_MCU', 'B.Cu', (83.65, 92.5), (83.7, 92.45))
drop('USB_DM_MCU', 'B.Cu', (83.7, 92.45), (83.9, 92.45))
drop('USB_DM_MCU', 'F.Cu', (83.9, 92.45), (83.9, 92.25))
drop('USB_DM_MCU', 'F.Cu', (83.9, 92.25), (84.0, 92.15))
drop('USB_DM_MCU', 'F.Cu', (84.0, 92.15), (84.0, 92.175))
T('USB_DM_MCU', 'B.Cu', (83.65, 92.5), (84.0, 92.85), (84.0, 93.0), w=0.15)
V('USB_DM_MCU', 84.0, 93.0, 0.45)
T('USB_DM_MCU', 'F.Cu', (84.0, 93.0), (84.0, 92.175), w=0.15)
# C44.1 (12 V): the via ring overlapped the land's north edge (R66 is 0.55 mm north); move it south of the
# land, beside the C44.2 ground via, and carry the B.Cu feed under the capacitor.
dropvia('12V', 160.05, 93.0)
drop('12V', 'F.Cu', (160.05, 93.0), (160.05, 94.0))
T('12V', 'B.Cu', (160.05, 93.0), (160.05, 95.2))
V('12V', 160.05, 95.2, 0.55)
T('12V', 'F.Cu', (160.05, 95.2), (160.05, 94.0))
# Y1.4 (GND): the via ring overlapped the crystal land; 0.3 mm further west
dropvia('GND', 81.0, 75.65)
drop('GND', 'F.Cu', (81.9, 75.65), (81.0, 75.65))
T('GND', 'F.Cu', (81.9, 75.65), (80.7, 75.65))
V('GND', 80.7, 75.65, 0.45)
