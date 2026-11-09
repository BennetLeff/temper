# Rev G copper, executed inside cad/tools/rev_g.py after the Rev F copper has moved with the cut (names: parts,
# routing, P, T, T45, V, DROP, WIDEN, KO).  Hand routing by coordinates; no autorouter, no path search.
# Layers as Rev F: F.Cu parts side, In1 GND plane, In2 and B.Cu signal.
#
# Band (y 57-67) layer plan, north to south:
#   B.Cu  y 53.0  JK_HPOT, J7 -> x 142.78 -> K4 NO1 (under the jacks, between the centre pins and GND legs)
#   In2   y 56.4  JACK_LC, R129 at J9 -> the west edge;   B.Cu y 56.9 JK_HCUR (Rev F's DUT_HI run, renamed)
#   In2   y 57.6  JACK_HC, R126 at J3 -> the west edge
#   F.Cu  y 58.2  the jack TVS row;  y 60.33 / 62.87 the photoMOS output pins on x = jack centre
#   In2   y 59.4  ISO_SINK, the LCUR/LPOT string back to Q7
#   In2   y 63.6  ISO_S1 (R132 -> U19 LED);  y 64.4 ISO_S2M (U20 LED -> U21 LED)
#   B.Cu  y 65.8  DUT_HI, R122 -> the Rev F x 90.2 spine to the RG resistors
# West edge: In2 x 52.0 JACK_LC, x 52.45 JACK_HC (STATUS stays on x 51.0) down to the dividers north of U1, then
# B.Cu x 55.9 / 56.6 south and east along y 137.0-138.06 (between USB_DM and USB_DP) to the GPIO 28 / 29 escapes.

# ============================================================== 1. jacks: TVS, switch, series resistor
# --- HCUR (J3): jack line straight down x 67 through the TVS to U18; TVS ground to the BNC's own GND leg
T('JK_HCUR', 'F.Cu', 'J3.5', 'D21.1', 'U18.4')
T('GND', 'F.Cu', 'D21.2', (69.2, 56.8), 'J3.2')
T('ISO_HCUR', 'F.Cu', 'U18.6', 'R122.1')
T('DUT_HI', 'F.Cu', 'R122.2', 'D25.1')
T('GND', 'F.Cu', 'D25.2', (59.5, 62.87))
V('GND', 59.5, 62.87)
T('DUT_HI', 'F.Cu', (62.4, 62.87), (62.4, 64.4))
V('DUT_HI', 62.4, 64.4)
T('DUT_HI', 'B.Cu', (62.4, 64.4), (63.8, 65.8), (90.2, 65.8))
V('DUT_HI', 90.2, 65.8)                    # top of the Rev F F.Cu spine (x 90.2) to R40 / R41 / R42
# --- HPOT (J7)
T('JK_HPOT', 'F.Cu', 'J7.5', 'D22.1', 'U19.6')
T('GND', 'F.Cu', 'D22.2', (91.2, 56.8), 'J7.2')
T('ISO_HPOT', 'F.Cu', 'U19.4', 'R123.1')
T('HPOT', 'F.Cu', 'R123.2', (92.725, 64.2), (92.025, 64.9), (87.475, 64.9), (87.475, 68.725))   # to the U6 +IN run
T('HPOT', 'F.Cu', 'C119.1', (87.475, 65.4))
T('GND', 'F.Cu', 'C119.2', (84.775, 64.35))
V('GND', 84.775, 64.35)
T('HPOT', 'F.Cu', 'D26.1', (87.475, 67.2))
T('GND', 'F.Cu', 'D26.2', (84.2, 67.2))
V('GND', 84.2, 67.2)
# --- LPOT (J8)
T('JK_LPOT', 'F.Cu', 'J8.5', 'D23.1', 'U20.6')
T('GND', 'F.Cu', 'D23.2', (113.2, 56.8), 'J8.2')
T('ISO_LPOT', 'F.Cu', 'U20.4', 'R124.1')
T('LPOT', 'F.Cu', 'R124.2', (115.6, 62.87), (116.3, 63.57), (116.3, 70.8))                     # to the U7 +IN run
T('LPOT', 'F.Cu', (116.3, 65.6), 'C120.1')
T('GND', 'F.Cu', 'C120.2', (119.8, 65.6))
V('GND', 119.8, 65.6)
T('LPOT', 'F.Cu', (116.3, 67.4), 'D27.1')
T('GND', 'F.Cu', 'D27.2', (118.9, 67.4), (119.5, 66.8))      # clear of the Rev F RLY_RST B.Cu run (y 67.6)
V('GND', 119.5, 66.8)
# --- LCUR (J9): DUT_LO west to the Rev F run down x 122.6 (TIA input), BAV99 beside it
T('JK_LCUR', 'F.Cu', 'J9.5', 'D24.1', 'U21.4')
T('GND', 'F.Cu', 'D24.2', (135.2, 56.8), 'J9.2')
T('ISO_LCUR', 'F.Cu', 'U21.6', 'R125.1')
T('DUT_LO', 'F.Cu', 'R125.2', (123.4, 62.87), (122.6, 63.67), (122.6, 70.1))
T('DUT_LO', 'F.Cu', (122.6, 65.2), 'D28.3')
T('GND', 'F.Cu', 'D28.1', (126.05, 64.25), (127.0, 65.2))
T('GND', 'F.Cu', 'D28.2', (126.05, 66.15), (127.0, 65.2))
V('GND', 127.0, 65.2)

# ============================================================== 2. jack-side network: R105 / R106 / R107, K4 bypass
T('JK_HCUR', 'F.Cu', 'J3.5', 'R105.1')
T('JK_HPOT', 'F.Cu', 'J7.5', 'R105.2')
T('JK_LPOT', 'F.Cu', 'J8.5', 'R106.2')
T('JK_LCUR', 'F.Cu', 'J9.5', 'R106.1')
# LCUR to R107 (K4 reference): west off U21, B.Cu beside the JK_HCUR riser (x 131.5) to above the Rev F RLY_RST
# B.Cu run (y 67.6), In2 under it, F.Cu into R107
T('JK_LCUR', 'F.Cu', 'U21.4', (131.17, 60.33), (130.5, 61.0))
V('JK_LCUR', 130.5, 61.0)
T('JK_LCUR', 'B.Cu', (130.5, 61.0), (130.5, 66.8))
V('JK_LCUR', 130.5, 66.8)
T('JK_LCUR', 'In2.Cu', (130.5, 66.8), (130.0, 67.3), (130.0, 70.1))
V('JK_LCUR', 130.0, 70.1)
T('JK_LCUR', 'F.Cu', (130.0, 70.1), (130.0, 71.6), (128.775, 72.825), 'R107.1')
# HPOT to K4 NO1 (pole 1 bypass): B.Cu under the jacks
T('JK_HPOT', 'B.Cu', 'J7.5', (91.0, 53.0), (142.0, 53.0), (142.4, 53.4), (142.4, 71.81), (142.78, 72.19))   # >= 3.5 mm from H2
V('JK_HPOT', 142.78, 72.19)
T('JK_HPOT', 'F.Cu', (142.78, 72.19), 'K4.4')
T('JK_HCUR', 'F.Cu', 'K4.8', 'K4.3')        # COM2 to COM1 under the relay body

# ============================================================== 3. isolation LED drive
# String 1: VRLY (K1 pin 1) -> R132 -> U19 LED -> U18 LED -> ISO_SINK.  String 2: VRLY -> R133 -> U20 LED ->
# U21 LED -> ISO_SINK (In2 back west).  Q7 sinks ISO_SINK; its gate from GPIO 15 on In2 x 78.8.
T('VRLY', 'F.Cu', 'R132.1', 'K1.1')
T('ISO_S1', 'F.Cu', 'R132.2', (95.22, 63.6))
V('ISO_S1', 95.22, 63.6)
T('ISO_S1', 'In2.Cu', (95.22, 63.6), (81.8, 63.6), (81.2, 63.0), (81.2, 60.33))
V('ISO_S1', 81.2, 60.33)
T('ISO_S1', 'F.Cu', (81.2, 60.33), 'U19.1')
T('ISO_S1M', 'F.Cu', 'U19.3', (81.4, 62.87), (81.4, 63.9), (80.7, 64.6), (74.6, 64.6), (73.3, 63.3), 'U18.1')
T('ISO_SINK', 'F.Cu', 'U18.3', (75.0, 60.33), (76.13, 59.2), 'Q7.3')
V('ISO_SINK', 75.0, 60.33)
T('VRLY', 'F.Cu', 'R133.1', (101.4, 69.92))
T('ISO_S2', 'F.Cu', 'R133.2', (101.955, 60.33), 'U20.1')
T('ISO_S2M', 'F.Cu', 'U20.3', (103.0, 62.87))
V('ISO_S2M', 103.0, 62.87)
T('ISO_S2M', 'In2.Cu', (103.0, 62.87), (103.0, 63.8), (103.6, 64.4), (140.3, 64.4), (140.9, 63.8), (140.9, 62.87))
V('ISO_S2M', 140.9, 62.87)
T('ISO_S2M', 'F.Cu', (140.9, 62.87), 'U21.1')
T('ISO_SINK', 'F.Cu', 'U21.3', (140.9, 60.33))
V('ISO_SINK', 140.9, 60.33)
T('ISO_SINK', 'In2.Cu', (140.9, 60.33), (139.97, 59.4), (75.93, 59.4), (75.0, 60.33))
T('GND', 'F.Cu', 'Q7.2', (79.39, 58.25), (80.04, 57.6), (80.2, 57.6))
T('GND', 'F.Cu', 'R135.2', (80.2, 57.6))
V('GND', 80.2, 57.6)
T('ISO_G', 'F.Cu', 'Q7.1', 'R134.2')
T('ISO_G', 'F.Cu', 'Q7.1', 'R135.1')
# GPIO 15 (U1 pin 18, north side) between the XIN and RNG_SET_REF escapes, In2 north to the band
T('ISO_DRIVE', 'F.Cu', 'U1.18', (75.4, 129.0), (75.2, 128.8), (75.2, 127.5))
V('ISO_DRIVE', 75.2, 127.5)
T('ISO_DRIVE', 'In2.Cu', (75.2, 127.5), (75.2, 124.6), (77.6, 122.2), (77.6, 80.0), (78.8, 78.8), (78.8, 65.2), (77.4, 63.8))
V('ISO_DRIVE', 77.4, 63.8)
T('ISO_DRIVE', 'F.Cu', (77.4, 63.8), (77.975, 63.225), 'R134.1')

# ============================================================== 4. jack residual-voltage senses (GPIO 28 / 29)
# 1.5M at each CUR jack; 240k + 100 nF to GND at the west end of the band; 240k to 3V3 north-west of U1.
# West edge on In2 (x 51.6 JACK_LC, x 53.0 JACK_HC, clear of the codec via at (52.4, 91.55)), then B.Cu x 55.2 / 55.65
# between the 5 V trunk and J1's pegs, east along y 137.05-138.06 between USB_DM and USB_DP to the escape vias.
T('JK_HCUR', 'F.Cu', 'J3.5', (60.375, 51.0), 'R126.1')
T('JACK_HC', 'F.Cu', 'R126.2', (59.2, 57.6))
V('JACK_HC', 59.2, 57.6)
T('JK_LCUR', 'F.Cu', 'J9.5', 'R129.1')
T('JACK_LC', 'F.Cu', 'R129.2', (143.5, 51.0))
V('JACK_LC', 143.5, 51.0)
T('JACK_HC', 'In2.Cu', (59.2, 57.6), (53.4, 57.6), (53.0, 58.0), (53.0, 118.15), (53.45, 118.6), (64.6, 118.6))
T('JACK_LC', 'In2.Cu', (143.5, 51.0), (143.5, 55.6), (142.7, 56.4), (52.2, 56.4), (51.6, 57.0), (51.6, 119.0),
  (52.2, 119.6), (66.2, 119.6))
V('JACK_HC', 53.0, 59.2)
T('JACK_HC', 'F.Cu', (53.0, 59.2), 'C121.1', 'R128.1')
V('JACK_LC', 51.6, 62.6)
T('JACK_LC', 'F.Cu', (51.6, 62.6), 'C122.1', 'R131.1')
T('GND', 'F.Cu', 'C121.2', 'R128.2', (57.3, 60.8))
V('GND', 57.3, 60.8)
T('GND', 'F.Cu', 'C122.2', 'R131.2', (57.3, 64.2))
V('GND', 57.3, 64.2)
V('JACK_HC', 64.6, 118.6)
T('JACK_HC', 'F.Cu', (64.6, 118.6), 'R127.1')
V('JACK_LC', 66.2, 119.6)
T('JACK_LC', 'F.Cu', (66.2, 119.6), 'R130.1')
T('3V3', 'F.Cu', 'R127.2', 'R130.2', (66.2, 126.6), (66.95, 127.35), (67.22, 127.35))   # to the U1 3V3 escape
V('JACK_HC', 55.75, 118.6)
T('JACK_HC', 'B.Cu', (55.75, 118.6), (55.75, 136.95), (55.9, 137.1), (58.4, 137.1), (58.6, 136.9), (69.1, 136.9),
  (69.45, 137.25), w=0.15)
V('JACK_LC', 55.2, 119.6)
T('JACK_LC', 'B.Cu', (55.2, 119.6), (55.2, 137.0), (55.63, 137.43), (58.8, 137.43), (58.88, 137.35), (67.3, 137.35),
  (68.05, 138.1), (69.5, 138.1), (69.9, 137.7), w=0.15)

# ============================================================== 5. Rev F copper that leaned on the pour
V('GND', 63.75, 140.25)     # TP21's GND stub (rev_f_routes.py section 12) ended on a Rev F stitching via
