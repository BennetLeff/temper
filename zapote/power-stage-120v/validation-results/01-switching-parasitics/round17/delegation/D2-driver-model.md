# D-2: is the D2 deck's gate-driver approximation faithful?

**Read [README.md](README.md) first (ground rules, board facts).**

## Why it matters

The D2 deck (`round17/d2/leg_matrix.cir`) models each UCC21550 output as a
behavioural current source that blends a **5 Ω pull-up** and a **0.55 Ω
pull-down** with a 5 ns command ramp, then 3.9 Ω external gate resistor, the
FEM gate-loop inductance, and the MOSFET gate. Gate turn-off speed sets
whether the 250–348 ns dead times are long enough, and the pull-down
strength sets how well the off gate resists false turn-on. Round 3 chose
these values; nobody has checked them against the datasheet.

## Task

1. From the **TI UCC21550 datasheet** (cite revision, page, table/figure),
   get: output pull-up and pull-down resistance (min/typ/max and the test
   conditions), peak source/sink current, rise/fall times into a stated
   load, and propagation delay. Note whether the pull-up is a combined
   PMOS/NMOS stage whose effective resistance changes with output voltage.
2. Compare with the deck's 5 Ω / 0.55 Ω and 5 ns ramp. If they differ,
   rerun a few D2 cases with datasheet values (worst-case for each failure
   mode: weakest pull-down for false turn-on, slowest turn-off for dead
   time) using `round17/d2/run_d2.py` with the 1 mm matrix
   `round17/d2/legA-h1-e0p35.matrix.txt` and the extrapolated
   `round17/d2/legA-h0-lin12.matrix.txt`. Cases: S1 (VBUS 170, IL 37, DIR 0,
   DT 348), S2 (280 V, 71 A, DIR 0, DT 348), S4 (170 V, IL −20, DIR 0, DT
   348). Add new parameters to a **copy** of the deck in your output folder;
   do not edit `round17/d2/`.
3. Gate resistor **Yageo RC1206FR-073R9L**: find its parasitic inductance
   if Yageo publishes one (cite); otherwise give a cited typical value for a
   1206 thick-film chip resistor and label it as such.

## Deliverable

`round17/delegation/out-D2/README.md`: the one-line answer (the deck's
driver values are / are not within the datasheet range, and what changes
in S1/S2/S4 when replaced), the cited datasheet values, the R10/R12
inductance, the copied deck and the case outputs.

## Acceptance

Each driver number cites a datasheet page; the reruns are committed
(deck copy, parameters, ngspice measurement logs) and reproduce; the
before/after table uses the same cases and matrices as stated.
