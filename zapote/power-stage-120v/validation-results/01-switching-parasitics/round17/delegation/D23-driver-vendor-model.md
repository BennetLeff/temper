# D-23: replace the driver approximation with TI's UCC21550 model

**Read [README.md](README.md) first (ground rules, board facts).**

## Why it matters

Every D2 switching result so far drives the gates through an
output-resistance approximation (5 Ω pull-up, 0.55 Ω pull-down, ideal command
edges; `d2/leg_matrix.cir`, "drivers"). D-2 (`out-D2/`) found it omits the
transient pull-up boost and does not reproduce TI's capacitive-load
rise/fall. The dead time is also imposed as an ideal command gap, while the
real UCC21550 sets it from the DT pin (native-18/19: R9/R17 = 49.9 kΩ, estimated
396.6–488.0 ns; `DECISIONS.md` 2026-10-03) and combines it with the input gap
by the longer-of rule (D-20 R24). The controller gap is 200 ns
(`DECISIONS.md`, O07). To vet gate timing **in simulation** rather than on the
bench, the driver itself must be modelled.

## Task

1. **Model:** obtain TI's UCC21550 SPICE/PSpice transient model (TI product
   page, design resources). Record its version, URL and SHA-256; if the
   licence forbids redistribution, keep it out of git like the Infineon
   library (fetch script + hash check, as `sim-kit/models/fetch_models.sh`
   does). Verify it runs in ngspice 45.2 (PSpice compatibility as needed);
   if it does not, say exactly why and stop.
2. **Driver fixture:** reproduce TI's datasheet characterisation with the
   model: propagation delay, rise/fall into the datasheet load, the DT-pin
   dead time at 20 kΩ and 50 kΩ against SLUSE89C's table (pp10, 25–26) and the
   longer-of behaviour with a 200 ns input gap. Report model vs datasheet
   (typ/min/max).
3. **D2 deck variant:** a copy of `d2/leg_matrix.cir` with the vendor driver
   (DT pin with 49.9 kΩ, VDD/VSS per the frozen netlist, bootstrap high side,
   DIS held enabled) replacing the B-source approximation, driven by
   PWM inputs with the 200 ns controller gap. Run the native-18/19 decision
   cases (`d2/grid.py`: S1/S2/S4 at the resulting dead time, ESL 1.06 and
   10 nH) on `d2/legA-h0-best.matrix.txt`.
4. **Compare** with `d2/results/grid-best-longdt/`: actual dead time at the
   gates (VGS crossings), off-gate peak against 3.0 V and the 1.9 V hot screen,
   die VDS, ZVS. Say whether any verdict changes and whether the 391–498 ns
   window assumption holds with the real driver.

## Deliverable

`round17/delegation/out-D23/README.md` (one-line answer first), the fixture
and comparison tables, the variant deck, runner and raw outputs (no licensed
models). Simulation only: no board, netlist, `elec/`, `pcb/` or firmware edits.

## Acceptance

The fixture reproduces the datasheet within stated tolerances or the
mismatch is reported; the baseline (approximation) rows reproduce
`grid-best-longdt` for the same cases; aborts are indeterminate.
