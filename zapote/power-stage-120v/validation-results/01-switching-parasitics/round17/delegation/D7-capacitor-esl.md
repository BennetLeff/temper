# D-7: capacitor ESL from vendor data

**Read [README.md](README.md) first (ground rules, board facts).**

## Why it matters

The D2 deck sweeps the local film capacitors' ESL (C38–C41, TDK
B32652A0104K000, 0.1 µF, 15 mm pitch) over 5 / 10 / 20 nH because no
part-specific value was found (`round17/PACKAGE-INDUCTANCE.md`; round 3's
"TDK bound ≤ ~20 nH"). The new 5-port bulk model (`round17/d2/leg_matrix5.cir`)
also needs the ESL of the bulk film capacitors C5/C6 (TDK B32656G0275J000,
2.7 µF, 4-pin, 37.5 × 20.3 mm). A sourced value could narrow the sweep.

## Task

1. For both part numbers, look for: TDK's SPICE / S-parameter / equivalent-
   circuit models (TDK product pages and its simulation tool downloads),
   impedance-vs-frequency curves in the datasheet or series catalogue, and
   any stated "self-inductance" or "ESL" figure (TDK film catalogues often
   give nH per mm of pitch for a series).
2. Extract ESL: from a model directly, or from the self-resonant frequency
   and capacitance (ESL = 1 / ((2π f_SR)² C)), stating the curve, the read
   values and their reading uncertainty.
3. Say what the value includes (leads cut at what length? PCB mounting?)
   versus what our FEM already includes (the FEM closure reaches the pads;
   the capacitor body and leads above the board are not in the FEM).
4. Recommend an ESL range per part for the D2 sweep, with its basis.

## Deliverable

`round17/delegation/out-D7/README.md`: one-line answer per part (ESL range
and its basis), sources with URLs/revisions/figure numbers, and a committed
script that does any SRF→ESL arithmetic. Store downloaded vendor models only
if their licence permits redistribution; otherwise record URL + hash.

## Acceptance

Each value traces to a vendor document/model or a curve reading with
stated uncertainty; "bound" only for a real bound.
