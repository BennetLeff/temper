# D-26: datasheet-parametric UCC21550 model — bound gate timing in simulation

**Read [README.md](README.md) first (ground rules, board facts).**

## Why it matters

D-23 (`out-D23/`) could not use a vendor driver model: TI publishes only the
automotive UCC21550B-Q1 model (SLUM881, Rev. A), it is a proxy for the board's
UCC21550BDWKR, and it did not converge in ngspice 45.2. The D2 deck still
drives the gates through a 5 Ω / 0.55 Ω output-resistance approximation with
ideal command edges (D-2 found it omits the transient pull-up boost), and the
dead time is imposed as an ideal gap. The owner wants gate timing vetted in
simulation. A model built from the datasheet's **guaranteed** parameters can
bound it without a vendor netlist.

## Task

1. **Parameters with citations** (TI SLUSE89C, catalog UCC21550; pages,
   tables, figures): propagation delay min/typ/max (both channels, both
   edges), pulse-width distortion, channel-to-channel skew, minimum input
   pulse, input thresholds/hysteresis and internal pull-down, DT-pin
   programming (table at 20/50 kΩ and the equation), the combination rule for
   input overlap/gap (longer-of; DECISIONS.md O07 sets a 200 ns controller
   gap), output source/sink current or resistance incl. the boost behaviour
   D-2 described, rise/fall into the datasheet load, UVLO and DIS response.
2. **Model:** a behavioural ngspice subcircuit (B-sources/switches/delays,
   no proprietary content) implementing those parameters, with a
   `CORNER=min|typ|max` parameter that selects the timing corner and the
   DT-resistor value as a parameter (49.9 kΩ, RT0603BRD0749K9L tolerance per
   D-12). Document every simplification.
3. **Fixture:** reproduce each cited datasheet characteristic with the model
   (delay, rise/fall into the datasheet load, DT at 20/50 kΩ, longer-of with a
   200 ns input gap, DIS-to-output). Report model vs datasheet; any miss
   beyond a stated tolerance is a failure, reported, not tuned away silently.
4. **Decision cases:** a copy of `d2/leg_matrix.cir` using the model, driven
   by PWM inputs with the 200 ns controller gap. Run S1/S2/S4 at the native-19
   best matrix (`d2/legA-h0-best-n19.matrix.txt`), ESL 1.06 and 10 nH, at the
   min, typ and max corners. Report the **actual** gate-level dead time (VGS
   crossings), off-gate peak against 3.0 V and the 1.9 V hot screen, die VDS
   and ZVS, and compare with `d2/results/native19-carryover/`.
5. **Verdict:** does the real-driver timing keep the gate dead time inside
   the 391–498 ns window the verdicts rest on (FINDINGS F7) at every corner?
   Does any verdict change?

## Deliverable

`round17/delegation/out-D26/README.md` (one-line answer first), the
parameter table with citations, the model, fixture and comparison tables,
runner and raw outputs (no licensed Infineon or TI files). Simulation only:
no board, netlist, `elec/`, `pcb/` or firmware edits.

## Acceptance

Every parameter cites the catalog-part datasheet; the fixture passes or its
misses are reported; the approximation baseline reproduces
`native19-carryover` for the same cases; aborts are indeterminate.
