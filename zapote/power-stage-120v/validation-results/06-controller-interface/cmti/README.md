# F6 / AOE-29: CMTI table for every isolation crossing

Desk calculation, current for s52. Rerun from `zapote/power-stage-120v`:
`python3 -I validation-results/06-controller-interface/cmti/cmti_table.py`. It prints PASS / FAIL / OPEN per row, rewrites
`cmti.csv`, and exits non-zero if the control row stops failing. `cmti_table.py` is the source of every number below; if they
disagree, the script wins. This file replaces the 2026-10 text that rated UCC21550 drivers against a 95 V/ns model edge.

## Basis

- dv/dt: the stage-42 basis, with the S6 study (`11-candidates/s6-cmti-2026-10-16/`, `cm_barrier.json`): S4 chord
  **49.7 V/ns at typical Qrr and 68.16 V/ns at maximum Qrr**; ZVS 10 V/ns. 1 V/ns = 1 kV/us. These are model figures, not
  measurements; the S6 bench items below test them.
- Rule (RESOLUTION-PLAN F6): CMTI >= 1.5 x dv/dt for every crossing whose upset gives a gate command: 1.5 x 68.16 =
  **102.2 kV/us**. Time-filtered crossings (tau >= 10 us) are judged on the filter, not on 1.5x.
- "seen" is what the barrier actually sees at max Qrr: HV_RET to PE is 0.74 V/ns with the rectifier conducting, 6.59 V/ns with
  all four diodes blocking (nominal), 22.6 V/ns for the worst single parasitic. The stacked-pessimistic corner (86.7 V/ns) is a
  stack of assumed corners and a bench item.

## Result (7 PASS, 0 FAIL, 5 OPEN; the control row fails as required)

| Ref | MPN | Class | CMTI (V/ns) | Verdict | Why |
|---|---|---|---:|---|---|
| U1, U2 | 2EDR8259XXUMA1 | GATE | 150 | PASS | 150 >= 102.2 (2.20x); 15.0x at ZVS |
| U43, U44 | ISO6721FBDR | FILTERED | 100 | PASS | tau 49.9 us; raw 1.47x of the chord; valid while an upset lasts < 0.42 us (bench item) |
| U32 | CA-IS3720HW | FILTERED | 100 | PASS | same filter; sees 6.59 V/ns (15.2x) |
| U41, U42 | R24C2T25/R-R | BIAS | 150 | PASS | 150 >= 68.16 (2.20x); a regulation upset, not a gate command |
| U9 | CA-IS3720HW | OPEN | 100 | OPEN | the consumer (controller) filter is not in this repo; rating is 15.2x the dv/dt seen |
| U4 | AMC1311BDWVR | OPEN | 100 | OPEN | the consumer (controller ADC / firmware) is not in this repo |
| U36 | VOL628A-2X001T | OPEN | n/a | OPEN | no datasheet CMTI number |
| T1 | CST3015-200ED | OPEN | n/a | OPEN | Cww unspecified; break-even Cww 186 pF (5.20 mV per pF on the burden node); ask Coilcraft |
| PS2 | MPM-20-24 | OPEN | n/a | OPEN | not on a switch node; no CMTI spec |
| CTRL | hypothetical 50 kV/us | GATE | 50 | FAIL | the control: must fail (short by 52.2 kV/us) |

The hard-edge duration for a 520 V swing at 68.16 V/ns is 7.63 ns, 56x shorter than the 0.42 us the monitor filter rides through.
Barrier injection (Cio x 68.16 V/ns): U1 / U2 136 mA, 1.04 nC; U41 / U42 239 mA, 1.82 nC; U4 102 mA; U43 / U44 / U32 / U9 34 mA.

## Verdict

F6 closes on the gate drivers: the 2EDR8259XXUMA1 is 2.20x the maximum-Qrr chord. The monitor crossings pass on their
filter only while an upset stays under 0.42 us; TI and Chipanalog give no upset-duration figure, so that is a bench item.
S6 is closed with no layout change (commit 52d3bb819, OPEN-ITEMS S6); the ledger carries the 68.16 V/ns diode
dv/dt (IPW65R018CFD7, 0.97 of rating, still a gap against the 56 V/ns screen until the D-8 double pulse).

## Bench items (S6)

- D-8 double pulse with max-Qrr parts: SW_A <= 100 V/ns (predicted 68.2 chord, about 91 peak).
- HV_RET to SELV_GND dv/dt <= 66.7 V/ns on the full assembly.
- Glitch capture through a 370-740-edge S4 burst on U43 / U44 OUTB, U32 HB_RX and U9 BUS_FAULT_FLT.
- U36 EFT / surge.

## OPEN items

- U9 BUS_FAULT and U4 VBUS leave the board unfiltered; the controller needs a debounce (2 consecutive samples or about
  10 us RC) before acting. The controller side is not in this repo.
- U36 has no CMTI number; firmware should validate zero-cross period (50 / 60 Hz window) before using it.
- T1: ask Coilcraft (cst@coilcraft.com) for Cww. My judgment (not sourced) is that a 3015 package is far below 186 pF.
