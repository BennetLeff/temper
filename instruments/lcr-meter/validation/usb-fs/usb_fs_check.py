"""USB D+/D- routing against Full Speed signal integrity (read-only).

Run with KiCad's bundled Python:  <kicad-python> validation/usb-fs/usb_fs_check.py
Writes validation/usb-fs/usb-fs-check.json and exits 1 on any finding.

The RP2040 USB PHY is Full Speed only (12 Mb/s; RP2040 datasheet 4.1). USB 2.0 7.1.2.1 gives FS
driver rise and fall times of 4-20 ns. A trace is electrically short, and its impedance and
matching do not matter, when its one-way delay is under a sixth of the rise time (the usual
lumped-element rule). FR-4 outer-layer delay is about 6-7 ps/mm, so the short-line limit is
4 ns / 6 / 7 ps/mm = 95 mm for the fastest legal edge. The D+/D- skew budget in USB 2.0 7.1.3
is 100 ps for the source driver pair; a mismatch costs about 7 ps/mm.

Findings: any D+/D- net longer than the short-line limit, or a pair mismatch above 1 ns / 7 ps
(well inside FS's 20 ns-edge timing, and a gross routing error if exceeded).
"""
import hashlib
import json
import sys
from pathlib import Path

import pcbnew as k

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / 'usb-fs-check.json'
PCB = ROOT / 'cad/temper-lcr.kicad_pcb'
board = k.LoadBoard(str(PCB))
MM = 1e-6
PS_PER_MM = 7.0
SHORT_LINE_MM = 4000 / 6 / PS_PER_MM
PAIRS = (('USB_DP', 'USB_DM'), ('USB_DP_MCU', 'USB_DM_MCU'))

length = {}
for t in board.GetTracks():
    if t.Type() != k.PCB_TRACE_T:
        continue
    n = t.GetNetname()
    if n in {x for p in PAIRS for x in p}:
        length[n] = length.get(n, 0.0) + t.GetLength() * MM
vias = {}
for t in board.GetTracks():
    if t.Type() == k.PCB_VIA_T and t.GetNetname() in length:
        vias[t.GetNetname()] = vias.get(t.GetNetname(), 0) + 1

findings, rows = [], []
for p, m in PAIRS:
    lp, lm = length.get(p, 0.0), length.get(m, 0.0)
    skew_ps = abs(lp - lm) * PS_PER_MM
    rows.append({'pair': [p, m], 'length_mm': [round(lp, 2), round(lm, 2)], 'vias': [vias.get(p, 0), vias.get(m, 0)],
                 'mismatch_mm': round(abs(lp - lm), 2), 'skew_ps': round(skew_ps, 1)})
    for n, ln in ((p, lp), (m, lm)):
        if ln > SHORT_LINE_MM:
            findings.append(f'{n} {ln:.1f} mm exceeds the {SHORT_LINE_MM:.0f} mm short-line limit')
    if skew_ps > 1000 / 7:
        findings.append(f'{p}/{m} mismatch {abs(lp - lm):.1f} mm ({skew_ps:.0f} ps)')
total = [sum(r['length_mm'][i] for r in rows) for i in (0, 1)]
result = {'board_sha256': hashlib.sha256(PCB.read_bytes()).hexdigest(), 'short_line_limit_mm': round(SHORT_LINE_MM, 1),
          'pairs': rows, 'connector_to_mcu_mm': [round(x, 2) for x in total],
          'connector_to_mcu_skew_ps': round(abs(total[0] - total[1]) * PS_PER_MM, 1), 'findings': findings}
OUT.write_text(json.dumps(result, indent=1) + '\n')
print(json.dumps({k_: result[k_] for k_ in ('pairs', 'connector_to_mcu_mm', 'connector_to_mcu_skew_ps', 'short_line_limit_mm')}))
print(f'{len(findings)} findings')
for f in findings:
    print('FINDING', f)
sys.exit(1 if findings else 0)
