"""Worst-case tolerance stack for the BNC front panel (J3, J7, J8, J9 through one plate).

python3 validation/enclosure-envelope/bnc_panel_stack.py  ->  bnc-panel-stack.json; exits 1 if a design value fails

Checks the panel rules in README.md "Front wall at the jacks" against linear worst-case stacks:
  1. hole diameter: the M12 thread must pass every hole with the four jacks on one plate;
  2. flange bearing: the flange (13.55) must still bear on the plate around the hole;
  3. board edge: the routed edge must never reach the plate's inside face before the flanges do;
  4. tray slot: the plate is located by the jacks, so the tray must leave it room in y and z;
  5. thread left for the toothed washer and nut.
Two assembly methods: 'jig' (jacks fitted to the plate, nuts snug, then soldered, so each jack's pin float
follows the plate) and 'soldered_first' (jacks soldered seated, then the plate is fitted).

Sources (numbers below; ASSUMED where no document gives one):
  SAMZO BNCKYWE-P03900 rev A1 (sources/rev-f/BNC-KYWE-295-W4-N.txt): M12 thread, flange 13.55 x 1.1, pins 1 wide,
    general tolerance +-0.15 (0-2 mm), +-0.25 (2-5), +-0.35 (>5); centre pin 5.0 behind the flange and the
    6.6 mm thread are scaled off the drawing, given the 2-5 and >5 tolerances here.
  Footprint: legs in 1.4 mm holes (validation/pinout-ledger, BNC row).
  JLCPCB PCB capabilities (https://jlcpcb.com/capabilities/pcb-capabilities, read 2026-11-08): routed outline
    +-0.2 mm, through-hole size +0.13/-0.08, hole position +-0.075, thickness +-10 %.
  Model vs drawing: board_envelope.py gives the STEP flange 13.75 tall (axis 6.875) against 13.55 drawn (6.775).
"""

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent

THREAD = 12.0                      # M12 major diameter
FLANGE_D, FLANGE_T = 13.55, 1.1
TOL_0_2, TOL_2_5, TOL_GT5 = 0.15, 0.25, 0.35
LEG = (1.0 - TOL_0_2, 1.0 + TOL_0_2)
HOLE = (1.4 - 0.08, 1.4 + 0.13)
HOLE_POS = 0.075
EDGE = 0.2
BOARD_T = (1.6 * 0.9, 1.6 * 1.1)
FLANGE_PROUD_NOM = 0.1             # flange front face ahead of the board edge, nominal (drawing, derived)
AXIS = (min(FLANGE_D / 2, 13.75 / 2) - TOL_GT5 / 2, max(FLANGE_D / 2, 13.75 / 2) + TOL_GT5 / 2)
THREAD_LEN = 6.6
SEAT_Z = 0.05                      # ASSUMED: jack body seating height spread after hand soldering
STANDOFF = 0.1                     # ASSUMED: standoff height and position tolerance (printed or machined)
M3_PLAY = (3.2 - 3.0) / 2          # M3 screw in the 3.2 mm NPTH
PROCESS = {  # ASSUMED, stated: hole position, hole diameter, systematic undersize
    'laser_or_machined_metal': {'pos': 0.10, 'dia': 0.10, 'undersize': 0.0},
    'resin_or_fdm_print': {'pos': 0.15, 'dia': 0.15, 'undersize': 0.10},
}
DESIGN = {  # the rules in README.md
    'hole_dia': {'laser_or_machined_metal': 12.5, 'resin_or_fdm_print': 12.7},
    'wall': 2.0, 'edge_relief_depth': 0.6, 'slot_float_y': 1.3, 'slot_float_z': 0.6,
}

float_min = (HOLE[0] - LEG[1]) / 2   # each jack's travel in its holes, per axis, worst tight
float_max = (HOLE[1] - LEG[0]) / 2   # worst loose
flange_pos = TOL_2_5 + TOL_0_2       # flange front face vs centre pin: scaled 5.0 (+-2..5 tol) + 1.1 thickness


def hole_needed(proc, method):
    p = PROCESS[proc]
    if method == 'jig':
        # each jack follows its plate hole within its float; only the excess has to be cleared by the hole
        radial = max(0.0, p['pos'] + HOLE_POS - float_min)
    else:
        # jacks soldered wherever their float left them; the plate sees their full spread (x) and seating (z)
        radial = float_max + HOLE_POS + p['pos'] + SEAT_Z
    return THREAD + 2 * radial + p['dia'] + p['undersize'], radial


def check():
    out, ok = {'inputs': {'float_per_axis_mm': [round(float_min, 3), round(float_max, 3)], 'axis_mm': AXIS,
                          'process': PROCESS, 'design': DESIGN}, 'checks': []}, True

    def add(name, value, limit, good, note, required=True):
        """required=False: the other assembly method, shown for comparison; it does not fail the run."""
        nonlocal ok
        if required:
            ok &= good
        out['checks'].append({'check': name, 'value': round(value, 3), 'limit': round(limit, 3), 'pass': good,
                              'required': required, 'note': note})

    for proc in PROCESS:
        d = DESIGN['hole_dia'][proc]
        for method in ('jig', 'soldered_first'):
            need, radial = hole_needed(proc, method)
            # smallest flange ring left bearing on the plate, on the worst side (hole made at its largest)
            ring = (FLANGE_D - TOL_GT5 - (d + PROCESS[proc]['dia'])) / 2 - radial
            good = need <= d and ring > 0
            add(f'{proc} / {method}: hole Ø needed vs Ø{d:g}', need, d, good,
                f'flange ring left on the worst side {ring:.2f} mm', method == 'jig')
    # Board edge vs the plate's inside face (= the flange front faces). Jig: the jack is pulled forward
    # against the plate, so the tightest float is on our side; soldered first: it may sit anywhere.
    for method, gain in (('jig', -float_min), ('soldered_first', float_max)):
        proud = -FLANGE_PROUD_NOM + EDGE + HOLE_POS + flange_pos + gain
        add(f'board edge ahead of the flanges, {method}', proud, DESIGN['edge_relief_depth'],
            proud < DESIGN['edge_relief_depth'], 'worst case; a positive value means the edge reaches the plate first',
            method == 'jig')
    # Tray slot: the plate follows the jacks. y: jack flange vs board holes, board vs tray standoffs.
    y = HOLE_POS + float_max + flange_pos + M3_PLAY + HOLE_POS + STANDOFF
    add('plate y travel vs tray (slot float each side)', y, DESIGN['slot_float_y'], y <= DESIGN['slot_float_y'], '')
    z = STANDOFF + (BOARD_T[1] - BOARD_T[0]) / 2 + (AXIS[1] - AXIS[0]) / 2 + SEAT_Z
    add('plate z travel vs tray (slot float each side)', z, DESIGN['slot_float_z'], z <= DESIGN['slot_float_z'], '')
    left = THREAD_LEN - DESIGN['wall']
    add('thread left for toothed washer + nut', left, 0.0, left > 0,
        'scaled 6.6 mm thread minus the wall; caliper the nut and washer before cutting')
    out['pass'] = bool(ok)
    return out


if __name__ == '__main__':
    res = check()
    (HERE / 'bnc-panel-stack.json').write_text(json.dumps(res, indent=1) + '\n')
    for c in res['checks']:
        print(('PASS' if c['pass'] else 'FAIL') + ('' if c['required'] else ' (comparison)'), f"{c['check']}: {c['value']} (limit {c['limit']}) {c['note']}")
    sys.exit(0 if res['pass'] else 1)
