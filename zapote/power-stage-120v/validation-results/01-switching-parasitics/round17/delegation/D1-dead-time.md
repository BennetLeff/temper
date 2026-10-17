# D-1: worst-case dead time of the UCC21550 on this board

**Read [README.md](README.md) first (ground rules, board facts).**

## Why it matters

Round 17's D2 grid sweeps dead time over 250 / 348 / 450 ns. At 250 ns the
turned-off MOSFET's gate is still above 3 V when its partner is commanded
on (shoot-through risk) in nearly every case; at 348 and 450 ns those cases
pass. The 250 / 450 ns corners were placeholders "for resistor tolerance plus
driver accuracy". Whether the 250 ns failures are real depends on the true
minimum dead time.

## Task

1. Find the DT pin network of U1 (leg A) and U2 (leg B) in the netlist and
   board: resistor value(s), tolerance, part number, and anything else on
   the DT pin (capacitor, pull-down, connection to DIS). Cite the reference
   designators and values from `frozen/default.csv` / `frozen/default.net`.
2. From the **TI UCC21550 datasheet** (cite revision and page), get the
   dead-time programming equation and its accuracy/tolerance (min/typ/max
   over temperature), and how the dead time interacts with the input PWM
   (does the driver insert dead time only when the inputs overlap, or always?).
   Check how this board's controller drives INA/INB (`docs/hardware/power-section-120v/POWER-SECTION.md`
   and the controller interface doc `validation-plan/06-controller-interface.md`).
3. Compute the **minimum, nominal and maximum dead time** with the
   resistor tolerance and the driver's stated accuracy, at the temperature
   extremes the datasheet gives. Also note propagation-delay mismatch
   between the two channels if the datasheet specifies it, since it shifts
   the effective dead time.
4. State whether 250 ns is reachable. If the true minimum is above 250 ns,
   say which D2 dead-time corners should replace 250/450 ns.

## Deliverable

`round17/delegation/out-D1/README.md` with the one-line answer (minimum
dead time on this board, with its basis), the DT network, the cited
equation and tolerances, and a small committed Python script that does the
min/nom/max calculation (`dead_time.py`) and its output.

## Acceptance

Every number traces to the netlist/BOM or a cited datasheet page; the
script reproduces the table; the min/max are a real worst case (all
tolerances stacked) or explicitly labelled typical.
