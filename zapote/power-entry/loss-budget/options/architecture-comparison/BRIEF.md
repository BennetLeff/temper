# PFC architecture comparison before further layout

User authorization: delegate to Luna the proposed model benchmark and bounded
comparison of practical alternatives. Base: `07a066e86251c13b0aec95b3d6f4ce958459db39`.
This is a research/decision deliverable. No CAD, procurement, production-model
parameter, acceptance threshold or retained experiment-02 evidence changes.

## Question and common boundary

Does the buffered C7 proposal deserve implementation, or are fixed choices
(frequency, magnetics, package and drive) hiding a materially better assembly?
The current 38–53 W result is a conditional MOSFET-plus-gate subtotal at
120 Vrms, 15 A input RMS, 400 V bus, 129.107 kHz, 180 µH, 12 V drive and
4.7 Ω. It is neither a whole-board loss nor a guaranteed range. The comparison
must not promote model arithmetic to measured behavior.

Use approximately 1,796 W input at nominal line as the existing operating
reference, with 15 A RMS input ceiling. Compare high line at the same power;
show low-line derating explicitly. Keep wall input, DC output and pan power
separate. No topology can produce 1,800 W delivered power from 1,800 W input
with nonzero losses. This work does not invent a new product output requirement.

Hold the comparison conditions visible: line, bus, load, switching frequency,
magnetics, gate drive, case/junction temperature and cooling. Source test points
remain source test points unless their transfer is justified. Null unknown
losses do not become zero. No candidate wins a whole-assembly comparison from
a partial switching subtotal or headline efficiency at another operating point.

## Three independent work packages

1. Manufacturer benchmark: obtain measured reference evidence and determine
   which predictions it can actually test. Retain source/revision/page/hash,
   point extraction uncertainty and model input applicability. A whole-board
   efficiency measurement is not direct switch-energy evidence; it can falsify
   an excessive partial-loss prediction only at a correctly matched point.
2. Silicon design comparison: baseline plus lower-frequency conventional boost,
   with appropriately resized inductance and reviewed ripple/current/energy,
   saturation and core/winding loss. Consider whether available bias removes
   the need for a new driver rail; no assumption that a higher voltage is safe.
3. Kelvin-source SiC: one evidence-strong exact part/driver/bias combination,
   with switching-condition transfer, source return, startup/EN and cooling
   costs. Identify what shortfall would justify a later interleaved/bridgeless
   comparison; do not design those topologies in this pass.

## Assembly ledger and decision criteria

Account separately for MOSFET conduction; disjoint switch/commutation energy;
boost diode; mains bridge; inductor DC, AC and core loss; shunt; EMI magnetics;
capacitor ESR; PCB/fuse/terminals/contacts; bias/controller/relay loads; cooling
power and thermal path. Distinguish device-die heat from gate-network heat.
Attach cost, physical size, availability and protection complexity when sourced;
otherwise name the missing evidence. Do not assign invented totals or rankings.

Prefer a simpler conventional design if it can satisfy the eventual full loss,
size and protection budget. Escalate topology only when an evidenced remaining
constraint makes that complexity worthwhile. No numerical budget is newly
approved by this brief; illustrative thresholds must be labeled proposals.

Done when the three bounded reports and source records are inspected, material
claims reconciled, a comparison matrix records both evidence and unknowns, and
one next discriminating experiment is recommended. Lack of adequate public
measurements may complete the research with model validation still indeterminate.
No new circuit is qualified by completion of this report.
