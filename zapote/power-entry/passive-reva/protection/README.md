# Passive Rev A protection checkpoint

This directory defines the protection disposition for the retained passive
power-entry baseline: Diodes **GBJ2510-F**, U9 boost switch, U10 boost diode,
the 400 V capacitor bank, F1 line fuse and a proposed DC bus fuse F2.

The checkpoint is deliberately a design disposition, not a safety or hardware
qualification. It answers which paths must be interrupted and where a future
CAD revision must place the interrupter. It does not turn catalogue ratings or
the nominal 179 J bank-energy calculation into a clearing claim.

## Current decision

Keep the passive GBJ2510-F bridge as the comparison baseline. Reserve an F2
position in series with the positive bus between U10's cathode and the bank
positive terminal. The exact candidate is **Mersen A70QS50-14F**, 50 A,
14 x 51 mm, but it remains `PART_SELECTED`; coordination is not demonstrated.

The open design inputs and subsequent qualification gates are separated in
[`DISPOSITION.md`](DISPOSITION.md). Prototype CAD does not require a prior
powered test, but release as a protected section requires the missing
coordination evidence. In particular, the existing
700 VAC clearing-I²t number cannot be applied to the 400 Vdc capacitor fault.
[`ALTERNATIVES.md`](ALTERNATIVES.md) records a SIBA 16 A / 1000 Vdc fallback
with published DC total-I²t data; it is a sourcing lead, not a qualified
replacement.

## Evidence boundary

- Passive bridge loss input: `../../shunt-repair/bridge-thermal-02/assessment.json`.
- Exact passive board and net boundaries: `../../shunt-repair/candidate/section.kicad_pcb`.
- A70QS source packet and conditions:
  `../../loss-budget/campaign/runs/2026-09-17-pfc-campaign/AR-MERSEN/`.
- Fault topology and negative-control loop check:
  `../../loss-budget/campaign/runs/2026-09-17-pfc-campaign/AR-PROTECT/`.

The active-bridge construction is not used as evidence for the passive board.
The historical candidate remains unchanged.
