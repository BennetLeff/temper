# Closure review: native-21 stage 10 against the stage-8 closure findings

Reviewer: independent, read-only. Date: 2026-10-08.

**Board:** `scratchpad/s10/section.kicad_pcb`. I re-hashed it as SHA-256 `ef993141…b6df`, which matches the brief and FAB-NOTE. I compared it with stage 7 (`s7/`, `ebdfdb3c`) and stage 8 (`s8b/`, `d4468ffd`).

**Method:** the same as in REVIEW-STAGE8.md.
- My own pcbnew extraction (`geom_s10.json`), plus shapely.
- `path.py` for routed paths. It does not see a track that merely passes over a pad centre, so for C145 and C147 I read the copper directly.
- `spacing.py`, `stackgap.py`, `newcaps.py` and `m4.py`.
- My own `kicad-cli pcb drc --refill-zones --schematic-parity` rerun, in `drc10/drc-refill.json`.

## Verdicts

| Id | Verdict | Evidence (measured) |
| --- | --- | --- |
| **B1** | **CLOSED** | Every VDD–VSS 100 nF loop is 2.07–2.20 mm, F.Cu 0.4 mm, no vias, on all four channels (details below). The 1 µF caps (C145–C148) sit 4.0–4.3 mm away per side and the 10 µF caps 6.1–6.4 mm. U1 pin 14 now has a direct 0.4 mm track to the n_ha pads. |
| **N1** | **CLOSED** | The sw_a track from the Q2 source pour to C50.1 is 24.09 mm, identical to stage 7. R71 is back at (75.6, 34.6) and R74 at (26.6, 35.2), their stage-7 spots. The 0.3 mm n_ha diagonal (74.8, 30.7)→(72.375, 39.6) is restored. |
| **M1** | **PARTIAL** (now MINOR) | Values now meet SBAS786C: C149 (VDD1) and C150 (VDD2) are 1 µF. C149's loop is 13.8 + 12.9 mm with 4 vias; C150's is 4.9 + 15.3 mm with 3 vias. The VDD2 100 nF loop got longer: C29 v3v3 1.8 → 3.85 mm (now through a via), selv_gnd 9.4 → 12.0 mm. The VDD1 100 nF (C28) is 7.3 + 9.9 mm with 5 vias. The ISO7710s are unchanged and fine. |
| **M4** | **CLOSED** (residual risk noted) | H1–H7 are at the stage-8 positions, and both outer layers are copper-free within the washer diameter at every hole. FAB-NOTE and BRINGUP-PROBES now require an insulating chain: nylon screw, washer and standoff, male-female or nylon at the chassis, and no metal within 10 mm. H4 and H6 still have HOT In1 copper 1.20 / 1.90 mm from the hole wall, so a wrong metal screw remains a single-error hazard. |
| **N2** | **PARTIAL** (MINOR) | The legend now reads "H2-H7". The per-hole NYLON marks are still F.Fab only. The board-ID text still trips silk-to-edge and overlaps PS1's silk, and the H2–H7 refdes still overlap the washer circles. |
| **N3** | **CLOSED** — and my stage-8 description was wrong | See the correction below. |
| **N5** | **CLOSED** | The F1 value, `positions-kicad.csv` and the BOM all read MDA-25-R. |

**Correction to REVIEW-STAGE8 (N3 and B1 text):**
- The leg_ret In1 run at y = 40 is live: it runs from via (51.725, 40.55) through (53.3–55.6, 40.15) to x = 110. What DRC flagged was a duplicate, overlapping 55.6→95.4 segment, whose east end landed mid-track.
- Stage 10 removed only that duplicate. The 55.6→110 run remains, and it is correct.
- So there was no 36 mm of dead copper. Calling it an obstacle that could be "deleted" was wrong; it is a real In1 routing constraint.

**Not re-verified here:** N6, which is left open as a method difference. My H4 figure is still 1.20 mm.

## 1. B1 and N1 measurements

### Stack layout

Each stack is three 0805s at y 43.95 / 41.85 / 39.75, with pads 1.9 mm apart, straddling the OUT pin.

| Channel | Pins | Caps (100 nF / 1 µF / 10 µF) | Cap pad x |
| --- | --- | --- | --- |
| U1 high side | 16 / 14 at 75.555 / 78.095 | C10 / C145 / C11 | 75.88 / 77.78 |
| U1 low side | 11 / 9 | C8 / C146 | 82.22 / 84.12 |
| U2 high side | — | C17 / C147 / C18 | 28.88 / 30.78 |
| U2 low side | — | C15 / C148 | 35.22 / 37.12 |

### Routed paths

| Loop | VDD leg | VSS leg | Vias |
| --- | --- | --- | --- |
| U1 16→C10→14 | 2.07 | 2.20 | 0 |
| U2 16→C17→14 | 2.20 | 2.20 | 0 |
| U1 11→C8→9 | 2.20 | 2.20 | 0 |
| U2 11→C15→9 | 2.20 | 2.20 | 0 |
| U1 → C11 (10 µF) | 6.27 | 6.40 | 0 |
| U2 → C18 | 6.40 | 6.13 | 0 |
| U1 → C146 | 4.30 | 4.30 | 0 |
| U2 → C148 | 3.98 | 4.30 | 0 |
| C145 / C147 | — | — | 0 |

C145 and C147 are reached by the 0.4 mm p_h / n_h columns at x 75.88 / 77.78 passing straight over their pads, about 4.2 mm per side, with no vias.

Stage 8 had 30 mm through 2 vias on the U1 VSSA leg. The claim of 2.07–2.2 mm with no vias is confirmed.

### Output necks

OUTx necks to 0.3 mm through the 0.9 mm pad gap, with 0.30 mm clearance to the VDD and VSS pads on each side. My DRC rerun reports no clearance or solder-mask errors.

### N1

The other gate-loop return segments match stage 7 (measured):
- n_ha U1.14→C50.2: 24.61 → 24.52 mm, lower because of the new parallel stack link;
- n_hb U2.14→C57.2: 7.60 mm, unchanged;
- sw_b Q5.3→C57.1: 42.35 mm, unchanged;
- n_ls U1.9→C52.2: 5.66 mm, unchanged.

## 2. Is the +2 nH bound sound?

**Diff against stage 7:** I diffed every track and via on these nets: the four out_h/out_l nets, all gate nets, sw_a/sw_b, n_ha/n_hb, p_ha/p_hb, n_ls, v15_ls and leg_ret. Within the gate loops, the only changes are:

| Output | Stage 7 | Stage 10 neck |
| --- | --- | --- |
| A out_h | 0.6 mm | 7.83 mm at 0.3 mm |
| B out_h | 0.6 mm | 7.83 mm at 0.3 mm |
| A out_l | 0.5 mm | 6.23 mm at 0.3 mm; its 0.5 mm approach is re-angled, path 9.22 → 9.36 mm |
| B out_l | 0.6 mm | 6.53 mm at 0.3 mm |

On top of those, there is the new 0.4 mm VSS-to-stack link (parallel, lowers L) and the stack caps themselves.

**Other changes are outside the loops:**
- The other leg_ret, n_ls and v15_ls changes are in the AMC/ISO and LS-bias block (x 96–117, y 42–116), well away from the gate loops.
- The sw_a, sw_b, n_ha and n_hb return paths are unchanged.

**My estimate:** the thin-strip partial self-inductance of each neck, for 2 oz copper at 0.6/0.5 → 0.3 mm, rises by:
- **+0.92 nH** for out_h, A and B;
- +0.53 nH for A out_l;
- +0.76 nH for B out_l.

A partial-inductance increase bounds the loop increase from above, because the return is unchanged or slightly closer.

**Conclusion:** +2 nH on both gate-port diagonals is at least twice the change, so the bound is sound for this edit. The F6 summaries confirm it: 48 + 48 + 48 + 108 = 252 per leg, with worst off-gate 1.145 V and worst VDS 490.2 V (leg B S4, 27 °C).

The open question from stage 8 (which conductors the P3/P4 ports close through, and the low 24 nH) stays with the FEM record, as the designer states. It is not affected by this change.

## 3. Regression checks on the stage 9/10 changes

**Barrier:**
- The plan-view minimum over all layers is still **8.047 mm**: the leg_a-dis and leg_b-dis vias to the n_ha/n_hb B.Cu zones. There are 0 pairs below 8.0 mm and 387 pair-records below 8.2 mm.
- The stack caps are 10.38 mm (C10/C17/C8/C15 row) to 14.57 mm from SELV.
- The new C149.2 (ocp_kelvin_p) is 8.83 mm from selv_gnd In2; C149.1 is 10.16 mm.
- C150 is ≥ 13.3 mm from HOT.

**3.2 mm group rule between the stacks** (same layer, SW_A/SW_B vs LOW):

| Driver | Closest same-layer pairs |
| --- | --- |
| U1 | U1.14 n_ha pad ↔ v15_ls track **3.31 mm**; stack pad ↔ stack pad (C10.2 ↔ C8.1, C145.2 ↔ C146.1) **3.44 mm** |
| U2 | **3.20 mm**: n_hb vias ↔ hv_ret In1 zone, the same as stage 8 and not from the stacks; stack pads 3.42–3.44 mm |

- The board-wide group/tank exceptions are the same 20 own-part pad/track pairs as at stage 8. None is new.
- Cross-layer: OUTx F.Cu still runs over LOW In1 copper (bias_sw1/2, hv_ret), as at stage 7. This is unchanged and allowed by the rules.

**DRC** (designer's run and my refilled rerun agree):
- 0 errors, 0 unconnected, parity 0;
- 243 warnings: 199 lib, 20 silk_over_copper, **11 track_dangling**, 9 silk_overlap, 4 silk_edge.

**The 11 dangling tracks:** all 0.10–1.03 mm. Ten are the stage-8 jog stubs that remain. One is new: selv_gnd F.Cu at (108.125, 126.6), 0.23 mm, from the C29 re-route. None is longer than 1.03 mm (hot5 at (105.9, 68.4)). Harmless.

**Caps near U4:**
- C149 at (99.5, 111.0) and C150 at (106.6, 131.0); both clear the barrier, as measured above.
- Moving C29 lengthened the VDD2 HF loop (see M1). That is a small regression.

## New findings (stages 9/10)

- **No new BLOCKER or MAJOR.**
- **S10-1 — MINOR — AMC1311 100 nF loops got longer.** C29: VDD2 1.8 → 3.85 mm with a via, GND2 9.4 → 12.0 mm. C28 hot5 leg: 5.1 → 7.3 mm. The new 1 µF caps are not local (C149 ~27 mm loop, 4 vias). For a 5 V / ~6 mA supply this is acceptable, but the 100 nF caps should be routed pin-adjacent on F.Cu.
- **S10-2 — MINOR — Test pads and the probe map.**
  - The pads went from 41 at stage 7 to 36 now. The leg B out_h and out_l pads that sat at (29.82, 41.9) and (35.95, 42.5) are gone; the stacks occupy those spots. BRINGUP-PROBES now points to component pads R18.1/R57.2 and R20.1/R58.2.
  - BRINGUP-PROBES positions are stale against the board for three pads: TP6 (0.53 mm), **TP13 (3.63 mm: doc 55.0, 130.0; board 58.633, 129.962)** and TP16 (1.03 mm).
  - Regenerate the probe map from the current board.
- **S10-3 — MINOR — Solderability at the necks.** The 0.3 mm OUT neck runs under each 0805 body with only 0.30 mm to the cap pads on both sides. DRC passes, but call it out for AOI/X-ray inspection of solder bridging on the four driver stacks at first article.
