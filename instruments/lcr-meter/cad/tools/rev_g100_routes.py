# Rev G100 copper, executed inside cad/tools/rev_g100.py after the west and east bodies moved 10 mm north (names:
# parts, routing, P, T, T45, V, DROP, WIDEN, KO, prune).  Hand routing by coordinates; no autorouter, no path search.

# ============================================================== 0. what the new outline and the moved parts leave behind
# copper south of the new edge (the old flash fan-out, BOOTSEL, RUN, MON12 / MON_N12 tails, the old 5 V trunk)
_t = CLEAR(below=144.55)
# the old flash fan-out and the parts placed again (QSPI, BOOTSEL, RUN network, TP20 / TP21, J5)
_t |= CLEAR({'QSPI_CS', 'QSPI0', 'QSPI1', 'QSPI2', 'QSPI3', 'QSPI_CLK_FLASH', 'BOOTSEL'}, box=(57, 137.5, 82, 145))
_t |= CLEAR(box=(57.5, 137.6, 67.6, 145.0))          # under the flash's new place
print('prune:', prune(_t | {'GND', '3V3', 'RUN', '5V', 'USB_VBUS', 'HEARTBEAT', 'FAULT', 'LED_HB', 'LED_FLT'}))


def _near(p, q, tol=0.01):
    return abs(p[0] - q[0]) < tol and abs(p[1] - q[1]) < tol


def DELSEG(net, *pts):
    """Remove the segments of a net that have an end at any of these points."""
    routing['tracks'][:] = [t for t in routing['tracks']
                            if not (t['net'] == net and any(_near(e, q) for e in t['points'] for q in pts))]


def DELV(net, *pts):
    routing['vias'][:] = [v for v in routing['vias'] if not (v['net'] == net and any(_near(v['at'], q) for q in pts))]


def MOVEPT(net, old, new, layers=None):
    """Move a via of the net at `old`, and every track end there, to `new`."""
    for v in routing['vias']:
        if v['net'] == net and _near(v['at'], old):
            v['at'] = list(new)
    for t in routing['tracks']:
        if t['net'] == net and (layers is None or t['layer'] in layers):
            t['points'] = [list(new) if _near(e, old) else e for e in t['points']]


# ============================================================== 1. west: the power entry over the west-edge runs
# JACK_HC / JACK_LC came down the west edge on In2 and turned east at y 118.6 / 119.6, straight through the power
# entry's vias.  They now turn at y 116.5 / 117.2, the via-free channel between U16's GND via and the 5 V via, drop to
# B.Cu at (55.75, 116.5) / (53.2, 117.2), and jog south at x 62.7 / 62.0 to their old R127 / R130 taps.
_jk = CLEAR({'JACK_HC', 'JACK_LC'}, box=(50.5, 113.0, 67.0, 136.9))
T('JACK_HC', 'In2.Cu', (53.0, 58.0), (53.0, 116.0), (53.5, 116.5), (62.7, 116.5), (62.7, 118.1), (63.2, 118.6),
  (64.6, 118.6))
T('JACK_LC', 'In2.Cu', (51.6, 57.0), (51.6, 116.6), (52.2, 117.2), (62.0, 117.2), (62.0, 119.0), (62.6, 119.6),
  (66.2, 119.6))
V('JACK_HC', 64.6, 118.6)
T('JACK_HC', 'F.Cu', (64.6, 118.6), 'R127.1')
V('JACK_LC', 66.2, 119.6)
T('JACK_LC', 'F.Cu', (66.2, 119.6), 'R130.1')
V('JACK_HC', 55.7, 116.5)
T('JACK_HC', 'B.Cu', (55.7, 116.5), (55.7, 136.9), (55.75, 136.95), w=0.15)
T('JACK_HC', 'B.Cu', (58.4, 137.1), (58.6, 136.9), (69.1, 136.9), w=0.15)
V('JACK_LC', 53.2, 117.2)
T('JACK_LC', 'B.Cu', (53.2, 117.2), (53.2, 124.0), (55.2, 126.0), (55.2, 137.0), w=0.15)
# R110's GND via between the two In2 runs; C16's GND via out of the B.Cu JACK_LC path; STATUS turns at y 123 clear
# of U3's GND via
MOVEPT('GND', (52.0, 114.15), (52.3, 114.15))
MOVEPT('GND', (53.1, 120.1), (54.05, 120.15))
MOVEPT('STATUS', (51.0, 122.0), (51.0, 123.0))
MOVEPT('STATUS', (58.4, 122.0), (58.4, 123.0))
# C17 (3V3 LDO output) sits where R1 and CC1 were.  C17 GND goes under U3 (between pins 5 and 4) to U3's GND via;
# R1 stands upright east of it, CC1 leaves south under C17, R1 GND ties to the CC pull-downs' via
DELSEG('GND', (60.0, 123.55)); DELV('GND', (60.0, 123.55))
T('GND', 'F.Cu', 'C17.2', (59.3, 121.9), (56.85, 121.9), w=0.3)
DELSEG('CC1', (61.175, 122.0))
T('CC1', 'F.Cu', 'R1.1', (61.9, 123.3), (61.6, 123.6), (59.575, 123.6), (58.856, 124.319))
DELSEG('GND', (62.825, 122.0))
T('GND', 'F.Cu', 'R1.2', (62.6, 121.375), (62.825, 121.6), (62.825, 122.896))
# 3V3 from the LDO to R127 / R130's 3V3 end, which runs on to U1's 3V3 escape
T('3V3', 'F.Cu', (60.6, 120.7), (60.9, 120.4), (63.5, 120.4), (63.5, 122.425), 'R127.2', w=0.3)

# C18 (3V3 bulk) between the CC pull-downs' GND via and R130's 3V3 run
T('3V3', 'F.Cu', 'C18.1', (66.2, 125.95))
T('GND', 'F.Cu', 'C18.2', (63.865, 123.165), (63.094, 123.165))

# ============================================================== 2. the QSPI flash, west of U1's south side
# U2's pins 1-4 face west (H3), 5-8 east.  CLK and IO0 run on F.Cu along the south edge; IO3 and CS on B.Cu; IO1 and
# IO2 on In2 (both layers are empty south of y 139.5 here).  The west-column pins and IO3 drop through vias under
# U2's body (x 59.9 / 64.3), between the pad rows.
for _n, _y in (('QSPI_CS', 139.545), ('QSPI1', 140.815), ('QSPI2', 142.085), ('GND', 143.355)):
    V(_n, 59.9, _y)
    T(_n, 'F.Cu', (58.51, _y), (59.9, _y))
V('QSPI3', 64.3, 140.815)
T('QSPI3', 'F.Cu', (65.69, 140.815), (64.3, 140.815))
# VCC: U2.8 -> its 100 nF C11 -> the U1 3V3 run at x 68.017; C11 GND to C8's GND pad
T('3V3', 'F.Cu', 'U2.8', (66.6, 139.545), (67.21, 140.155), 'C11.1', (68.017, 140.175))
T('GND', 'F.Cu', 'C11.2', (68.6, 138.625))
# CLK: U1.52 -> R13 (33 R, turned) -> F.Cu y 143.5 -> U2.6
DELSEG('QSPI_CLK', (72.675, 143.5))
T('QSPI_CLK', 'F.Cu', (74.902, 141.273), (74.902, 142.923), (74.325, 143.5))
T('QSPI_CLK_FLASH', 'F.Cu', 'R13.2', (67.6, 143.5), (66.185, 142.085), 'U2.6')
# IO0: U1.53 F.Cu down x 75.263 (between C5 and R3), west along y 144.3 under R13 -> U2.5
T('QSPI0', 'F.Cu', 'U1.53', (75.4, 137.956), (75.263, 138.094), (75.263, 143.9), (74.863, 144.3), (67.355, 144.3),
  (66.41, 143.355), 'U2.5')
# IO3: U1.51 F.Cu down x 74.478 to a via, B.Cu y 141.8 west -> under-body via
T('QSPI3', 'F.Cu', 'U1.51', (74.6, 137.588), (74.478, 137.711), (74.478, 140.481), (73.509, 141.45), (73.303, 141.45))
V('QSPI3', 73.303, 141.45)
T('QSPI3', 'B.Cu', (73.303, 141.45), (72.953, 141.8), (65.285, 141.8), (64.3, 140.815))
# IO2: U1.54 escapes north to a via inside U1's pin ring, In2 x 75.383 south, west along y 143.0
T('QSPI2', 'F.Cu', (75.8, 136.439), (75.383, 136.022))
V('QSPI2', 75.383, 136.022)
T('QSPI2', 'In2.Cu', (75.383, 136.022), (75.383, 143.0), (60.815, 143.0), (59.9, 142.085))
# IO1: U1.55 escapes north, loops west under U1 on In2 (as on Rev G) to x 72.428, south, west along y 142.3
T('QSPI1', 'F.Cu', 'U1.55', (76.2, 135.86), (76.326, 135.735))
V('QSPI1', 76.326, 135.735)
T('QSPI1', 'In2.Cu', (76.326, 135.735), (76.619, 135.441), (76.619, 134.625), (76.344, 134.349), (75.835, 134.349),
  (72.428, 137.756), (72.428, 142.3), (61.9, 142.3), (60.415, 140.815), (59.9, 140.815))
# CS: U1.56 -> via -> In2 x 78.048 south -> via between R8 (BOOTSEL resistor) and R7 (pull-up) -> B.Cu y 143.0 west
# -> under-body via (moved off U2.1's row so the In2 runs below can pass)
DELSEG('QSPI_CS', (59.9, 139.545)); DELV('QSPI_CS', (59.9, 139.545))
V('QSPI_CS', 60.1, 139.95)
T('QSPI_CS', 'F.Cu', 'U2.1', (59.7, 139.545), (60.1, 139.945))
T('QSPI_CS', 'F.Cu', (76.753, 137.09), (77.335, 137.09))
V('QSPI_CS', 77.335, 137.09)
T('QSPI_CS', 'In2.Cu', (77.335, 137.09), (78.048, 137.804), (78.048, 141.902), (76.95, 143.0))
V('QSPI_CS', 76.95, 143.0)
T('QSPI_CS', 'B.Cu', (76.95, 143.0), (61.0, 143.0), (61.0, 140.85), (60.1, 139.95))
T('QSPI_CS', 'F.Cu', 'R8.1', (76.95, 143.0), 'R7.1')
T('3V3', 'F.Cu', 'R7.2', (80.175, 143.0), (80.8, 143.0))
# BOOTSEL: R8 -> via north of it -> In2 east, north-east -> via under SW1 -> SW1.1
V('BOOTSEL', 79.6, 141.0)
T('BOOTSEL', 'F.Cu', 'R8.2', (79.6, 141.975), (79.6, 141.0))
T('BOOTSEL', 'In2.Cu', (79.6, 141.0), (83.0, 141.0), (85.3, 138.7), (85.9, 138.7))
V('BOOTSEL', 85.9, 138.7)
T('BOOTSEL', 'F.Cu', (85.9, 138.7), (85.2, 138.7))
V('GND', 83.9, 142.5)                                   # C10's GND
T('GND', 'F.Cu', 'C10.2', (83.9, 142.5))

# ============================================================== 3. USB_DP back to R4 (its Rev G path, which crossed the
# old flash fan-out): In2 x 65.9 south, B.Cu y 138.45 east past R4, F.Cu back to R4.1
T('USB_DP', 'In2.Cu', (65.342, 131.9), (65.9, 132.458), (65.9, 137.9))
V('USB_DP', 65.9, 137.9)
T('USB_DP', 'B.Cu', (65.9, 137.9), (66.45, 138.45), (78.981, 138.45), (79.597, 139.065))
V('USB_DP', 79.597, 139.065, d=0.6)
DELSEG('USB_DP', (78.337, 140.325))
T('USB_DP', 'F.Cu', (79.597, 139.065), (78.525, 140.325), 'R4.1')

# ============================================================== 4. RUN, MON12, MON_N12: around the flash on In2
# The QSPI runs close U1's south side to U2 on all three signal layers, so the three nets that cross them run west
# under U2's west pads (x 58.3-59.3, between H3 and the under-body vias) and east along the south edge (y 143.85-144.55).
# Their order is fixed by where they leave: MON_N12 leaves first (B.Cu to R99), then MON12 (In2 to C110 / R98), then
# RUN (F.Cu to SW2), so RUN is the outer track all the way round.
T('RUN', 'B.Cu', (70.632, 129.292), (66.4, 129.292))
V('RUN', 66.4, 129.292)
T('RUN', 'In2.Cu', (66.4, 129.292), (66.4, 138.1), (66.1, 138.4), (58.6, 138.4), (58.3, 138.7), (58.3, 144.25),
  (58.6, 144.55), (88.0, 144.55), (88.3, 144.25), (88.3, 143.4))
V('RUN', 88.3, 143.4)
T('RUN', 'F.Cu', (88.3, 143.4), (87.3, 144.4), (85.4, 144.4), (84.875, 143.875))
T('MON12', 'F.Cu', 'U1.38', (68.3, 134.5))
V('MON12', 68.3, 134.5)
T('MON12', 'In2.Cu', (68.3, 134.5), (67.65, 135.15), (67.65, 138.45), (67.35, 138.75), (59.1, 138.75), (58.8, 139.05),
  (58.8, 143.9), (59.1, 144.2), (87.25, 144.2), (87.6, 143.85), (87.6, 137.6), (88.0, 137.2), (89.6, 137.2))
V('MON12', 87.6, 143.85)
V('MON12', 89.6, 137.2)
DELV('MON12', (87.6, 143.85))                           # the In2 run passes straight through: no via there
T('MON12', 'F.Cu', (89.6, 137.2), (90.225, 136.575))
T('MON_N12', 'F.Cu', 'U1.39', (69.3, 134.9), (69.1, 135.1))
V('MON_N12', 69.1, 135.1)
T('MON_N12', 'In2.Cu', (69.1, 135.1), (68.25, 135.95), (68.25, 138.8), (67.95, 139.1), (59.6, 139.1), (59.3, 139.4),
  (59.3, 143.55), (59.6, 143.85), (85.8, 143.85), (86.3, 143.35))
V('MON_N12', 86.3, 143.35)
T('MON_N12', 'B.Cu', (86.3, 143.35), (86.3, 141.8), (86.6, 141.5), (97.4, 141.5), (98.0, 140.9), (98.0, 137.3))
V('MON_N12', 98.0, 137.3)
T('MON_N12', 'F.Cu', (98.0, 137.3), (94.72, 137.3), (94.225, 136.805), (94.225, 136.2))
# R9 (pull-up) west of SW2, C14 (cap) east of SW1, RUN between the buttons
T('RUN', 'F.Cu', 'R9.1', (84.375, 141.9))
T('3V3', 'F.Cu', 'R9.2', (81.0, 139.225))
T('RUN', 'F.Cu', (84.875, 141.9), (84.875, 141.4), (85.375, 140.9), (90.4, 140.9), (91.0, 140.3), 'C14.1')
T('GND', 'F.Cu', 'C14.2', (91.0, 137.45), (91.775, 136.675))
T('GND', 'F.Cu', (89.85, 138.0), 'C14.2')
V('GND', 90.4, 142.9)
T('GND', 'F.Cu', 'SW2.2', (90.4, 142.9))
V('GND', 94.6, 140.1)                                   # TP9 (debugger GND)
T('GND', 'F.Cu', (94.6, 141.6), (94.6, 140.1))
T('GND', 'F.Cu', (61.25, 112.9), (61.2, 113.9))          # TP21 to the I2S pads' GND via

# ============================================================== 5. 5V: power entry -> switcher, relays, LED drivers
# Rev G ran the trunk along the old south edge.  Now: off the power entry's B.Cu riser (x 54.462) west, down the
# board edge at x 51.2 (west of J1's shell pads and H3), east along the south edge (B.Cu y 144.25, under the In2
# RUN / MON runs) to C117 and C80; In2 x 99 north from the trunk to R113 and, as on Rev G, to TP1 / R101.
DELSEG('5V', (58.3, 118.9)); DELV('5V', (57.4, 118.9), (58.3, 118.9))
T('5V', 'B.Cu', (54.462, 116.4), (51.9, 116.4), (51.2, 117.1), (51.2, 143.55), (51.9, 144.25), (92.0, 144.25), w=0.6)
T('5V', 'B.Cu', (92.0, 144.25), (92.2, 144.05), (128.6, 144.05), (128.6, 143.75), w=1.0)
V('5V', 118.6, 143.6)
T('5V', 'F.Cu', (118.6, 143.6), 'C117.1', w=0.6)
V('5V', 99.0, 144.05)
T('5V', 'In2.Cu', (99.0, 144.05), (99.0, 127.0), w=0.6)
V('5V', 99.0, 127.0, d=0.6)
T('5V', 'F.Cu', (99.0, 127.0), (98.7, 126.7), (98.7, 117.0), (99.3, 116.4), w=0.4)
T('5V', 'F.Cu', (98.7, 126.5), (100.5, 126.5), w=0.4)
V('5V', 99.0, 135.6, d=0.6)
T('5V', 'F.Cu', (99.0, 135.6), (101.9, 135.6), (102.0, 135.7), 'R113.2')

# ============================================================== 6. USB_VBUS: J1 -> the power entry (U16 IN, C113, TP20)
# J1's VBUS via (Rev F's sense tap) -> In2 north (x 57.75, between U3's GND via and the old 5 V vias) -> U16's IN node.
# STATUS no longer doglegs at y 123 (its In2 run goes straight west along y 128.47, under J1).
DELSEG('STATUS', (51.0, 123.0)); DELSEG('STATUS', (58.4, 123.0))
DELSEG('STATUS', (58.4, 128.72))
T('STATUS', 'In2.Cu', (66.9, 128.72), (66.65, 128.47), (51.0, 128.47), (51.0, 49.6))   # between J1's shell pads and pegs
V('USB_VBUS', 57.75, 117.75)
T('USB_VBUS', 'F.Cu', (57.75, 116.85), (57.75, 117.75), w=0.4)
T('USB_VBUS', 'In2.Cu', (57.75, 117.75), (57.75, 125.65), (57.2, 126.2), w=0.5)
DELV('GND', (58.8, 113.9))
T('USB_VBUS', 'F.Cu', (59.25, 112.9), 'C113.1', w=0.4)

# ============================================================== 7. 3V3: the LDO up to the codec's 3V3 run (which the
# B.Cu trunk at y 108.9 carries to x 84 and on to U1's east pins, the switcher sequencer and TP8)
T('3V3', 'F.Cu', (62.1, 120.4), (62.1, 104.1), (62.5, 103.7), w=0.3)

# ============================================================== 8. debug LEDs
# FLT: U1.34 -> via -> In2 north between STATUS and SWDIO (Rev G's run) -> via south of J4 -> F.Cu through J4's pin gap
# -> R118.  HB: U1.35 -> via -> In2 north -> via in the pocket west of U1 -> R117 -> D19.
T('FAULT', 'F.Cu', 'U1.34', (69.05, 132.9), (68.95, 133.0))
V('FAULT', 68.95, 133.0)
T('FAULT', 'In2.Cu', (68.95, 133.0), (68.219, 133.0), (67.62, 132.401), (67.62, 121.7), (67.3, 121.4))
V('FAULT', 67.3, 121.4)
T('FAULT', 'F.Cu', (67.3, 121.4), (67.73, 120.97), (67.73, 116.905), (66.4, 115.575), 'R118.2')
T('LED_FLT', 'F.Cu', 'D20.2', 'R118.1')
V('GND', 63.6, 111.96)
T('GND', 'F.Cu', 'D20.1', (64.6, 110.96), (63.6, 111.96))
T('HEARTBEAT', 'F.Cu', 'U1.35', (69.9, 133.3), (69.65, 133.55))
V('HEARTBEAT', 69.65, 133.55)
T('HEARTBEAT', 'In2.Cu', (69.65, 133.55), (67.66, 133.55), (67.26, 133.15), (67.26, 128.3), (66.86, 127.9), (66.3, 127.9))
V('HEARTBEAT', 66.3, 127.9)
T('HEARTBEAT', 'F.Cu', (66.3, 127.9), (66.0, 127.6), 'R117.2')
T('LED_HB', 'F.Cu', 'R117.1', 'D19.2')
V('GND', 65.5, 130.1)
T('GND', 'F.Cu', 'D19.1', (65.5, 130.1))
