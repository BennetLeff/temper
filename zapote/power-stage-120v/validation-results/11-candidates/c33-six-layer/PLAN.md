# Candidate 33: six-layer stack study (plan, 2026-10-14)

## Why
JLC instant quote, 2026-10-14 (`jlc-quote-2026-10-14.json`; 290 x 190 mm, 1.6 mm, ENIG, 2 / 2 oz, flying probe):

| Build | 5 pcs | 500 pcs | per board at 500 | build time at 500 |
|---|---|---|---|---|
| 4 L, plugged vias (no via-in-pad) | $186.99 | $7,623.25 | $15.25 | 5-6 days |
| **4 L, epoxy filled and capped (FAB-NOTE today)** | $214.36 | $8,395.03 | **$16.79** | 5-6 days |
| 6 L, filled and capped (no charge on 6 L) | $196.59 | $8,087.75 | $16.18 | 10-11 days |

- The 4-layer fill-and-cap premium is $771.78 / 500 = $1.54 per board ($700.11 covering + $71.67 forced plating).
- Removing via-in-pad would save that, but the in-pad vias are essential (U26 exposed-pad field, R5 shunt current
  fields, U41 / U42 pad edges) and would need re-validation. Rejected for $1.54.
- Six layers cost $0.61 per board less than the current spec and add two planes. That is the study.
- None of JLC's listed surcharges applies (`enig_area.py`: ENIG 3.1 % of top + bottom on the stage-32 board against the 30 % threshold;
  451.5 cm^2 < 650 cm^2; about 18,400 holes/m^2 < 150,000; 0.2 mm minimum track; 29 cm long).
- To confirm with a 6-layer Gerber upload: the inner-copper line read the same $2,083.80 at 500 for 4 and 6 layers.
- E-test fixture instead of flying probe: -$0.26 per board (4 L), -$0.16 (6 L) at 500.

## Area today (`density.py` on the stage-32 board, `runs-native21/s32/b2`, board 2fb346dc)
- Courtyards cover 41.9 % of the 451.5 cm^2 outline, almost all on the top side (bottom 0.2 %).
- The 17 largest parts are 65.7 % of the courtyard area: PS1, PS2, C5, C6, L1, T1, F1, the five resonant caps, RV1,
  C1, C2, J4, J1.
- Area-scaled fab lines are about $15.5 of the $16.18, so each 10 % of bounding area is about $1.5 per board.

## What six layers can and cannot change
- Can: routing-bound regions (the y 47-60 band, the SELV spine), so 30a (U44 -> ISO6721FB HS-B -> LS) and 30b (C161)
  may close; the 18 return-path open changes left after s32; plane continuity under the OCP / Kelvin loops (F8 pickup); heat spreading.
- Cannot: the 8.0 mm reinforced barrier and the 12.6 mm RES_A creepage. They are plan-view on every layer, and every
  through-laminate path is already >= 8.0 mm (stage 18), so thinner 6-layer dielectrics do not break the basis.
  Same-layer inner spacing stays as today unless the certifier accepts inner layers as solid insulation (packet A3 #10).

## Steps
0. **Tooling audit: done** (`AUDIT-4L.md`). The stack is copied from native-20 by `build_native21.py`, and six
   models hard-code it (sheet solver, B3 thermal, F8 loops / run_ocp, return-path ADJ, plane roles in the layout
   scripts). First a behaviour-neutral refactor to one stackup source and a `layers21.py` module, proved by re-scoring
   s32 unchanged; then the six-layer passes.
1. **Stack-up.** JLC's 6-layer 1.6 mm build with 2 oz inner (stack ID, dielectrics, laminate): into `stackup.json`.
   Re-ask the CTI inquiry for that stack. Layer plan to test: F (power / parts), In1 plane, In2 signal, In3 signal,
   In4 plane, B (power). The bus planes keep their pairing.
2. **Phase A: same outline and placement, six layers.** Re-route; close 30a / 30b and the return-path opens. Run the
   full chain, necks, OCP pickup and thermal; score against s32 (tag native21s32). Accept only if every gate holds, and cost and
   performance are both no worse.
3. **Phase B: delete PS1 (candidate 23) and compact** in one re-layout, after the controller's J13 merge
   (`../c23-supply-topology/CONTROLLER-REQUEST.md`). Measure the area recovered. Propose an outline change to the
   enclosure session only if the saving justifies it.
4. **Fallback:** if Phase A does not pay, candidate 23 is done on four layers anyway; the leakage fix does not wait on
   the layer count.
