# M11 HOT->PE heatsink stack: cost / benefit of the three ways round "a large custom AlN tile" (2026-10-17)

Inputs: `interface_thermal.py` and `tile_packing.py` (this folder, repo formulas / geometry, committed), the M11 sourcing read (`../CONFIRMED.md`), and an Opus research
agent's read-only study of option 3 (web numbers below are its, labelled SNIPPET where it said so; not independently re-checked). Prototype lot 10-20 boards.

## What the tile has to do (why it is big)
Reinforced insulation HOT->earthed pedestal: >= 2 mm solid ceramic (IEC 60335-1 cl. 29.3.1 by caliper) and 8.0 mm creepage, which at a 2 mm tile needs about 6 mm of overhang beyond
the tab metal at each end and about 6 mm above it. The FETs sit on an 18 mm pitch, so one tile spans several devices: A 42.75 x 31.8 mm (Q5, Q6) and B 73.75 x 31.8 mm (Q3, Q2, BR1).
Interface budget (D-36): <= 0.7 C/W per FET; this is the binding check, not Tj (RECOMMENDATION.md section 3).

## The options
| | Material per stack | Thermal vs 0.7 C/W (cons.) | Compliance | Effort | Verdict |
|---|---|---|---|---|---|
| **0. Baseline: standard 114 mm AlN plate, custom cut and lapped** | plate USD 341 / 2 stacks = **~$170** + cutting / lapping (doc total $190-320) | 0.40-0.63, passes | clean (cl. 29.3.1) | RFQ; 2.032 mm tiles are special order (Valley has only 1.016 mm) | the design |
| **1. Larger common plate** (127 mm: 3 stacks; 138 x 190 mm: 5 stacks per plate) | area-priced: ~$141 (127) / ~$138 (138 x 190); ideal cut-to-size ~$97 | same as 0 | same | no design change; **2 mm AlN at those sizes not found** | **~18-20 % saving, modest; worth asking for in the RFQ** |
| **2. 2 mm alumina (96 %) instead of AlN** | Almath 150 x 150 x 2 mm from GBP 65 (SNIPPET): 4 stacks per plate = **~GBP 16 (~$21) per stack** | k 30: 0.62-0.99; k 24: 0.69-1.10; k 15: 0.90-1.43: **fails 0.7 conservative** (passes optimistic at k >= 24); FET +2.6 to +5.9 K at 22 A (+2.3 K at 18 A for k 24) | same 2 mm (cl. 29.3.1); alumina k not established (9 / 15 / 25 W/mK in listings); as-fired plates warp, no lapped source found | same geometry; needs lapped or ground plates | **cheap bench / fit proxy, not the compliance sample** |
| 3a. Isolated packages (ISOPLUS247 etc.) | no 650 V CFD7-class isolated part; IXTR102N65X2: 33 mohm, 31-week lead, standard X2 diode, 2500 V: below the 3000 V reinforced test | losses ~1.8x | basic at best | still needs supplementary layer and 8 mm creepage | no |
| 3b. Top-side-cooled SMD (QDPAK) | IPDQ65R017CFD7A 17 mohm, RthJC 0.18 C/W | ~0.77 cons. (fails) | top tab is still live: same insulator problem | new stage: power-section re-layout and enclosure | production option only |
| 3c. JLC aluminium-core (IMS) | cheap | dielectric 1 W/mK: fails | 3000 V breakdown: basic only | new stage, SMD only | no |
| 3d. Catalogue sheets for the whole row | McMaster AlN <= 1.52 mm (price UNKNOWN); Shapal Hi-M Soft (machinable AlN, 100 W/mK, +/-20 % thickness) "from ~$255-263"; gap pads fail | Shapal 0.43-0.68 (passes by 0.02) | Shapal needs grinding to 2.00 +/-0.05 | same geometry, easier machining | **second source for the RFQ** |
| 3e. HOT-referenced sink | $10-30 per stack with catalogue pads | passes | reinforced barrier moves to the whole sink: duct, standoffs, probe-inaccessibility, NTC isolation: novel | major enclosure redesign; certifier opinion first | production-stage idea |

## The lever that dominates: how many stacks
The stack is needed on a board only when it runs against the real heatsink in the enclosure (type-test hipot, thermal, first-article). Bench-only boards on an isolated, current-limited
supply do not need it. AlN at ~$170-320 per stack: 20 stacks = ~$3.4-6.4k; 4 stacks = ~$0.7-1.3k. The tile quantity moves the cost far more than any material or sizing choice.

## Direction (justification)
1. **Decide the stack count first (owner).** Proposed: 4 stacks of AlN (type sample, hipot sample, thermal sample, spare), not one per board.
2. **Keep AlN 2.0 mm for the compliance and thermal samples.** It is the only option that passes the interface budget and cl. 29.3.1 cleanly, and the test evidence transfers to production. Alumina fails the formal budget and its k is unknown.
3. **Use alumina for fit and mechanics only**: 1 plate of 150 mm (about 4 stacks, ~GBP 65) lets the comb spring, pedestal flatness and clamp load be proven before AlN is spent; a cracked alumina tile costs $21, not $170.
4. **One RFQ, three asks:** (a) 2.0 mm AlN tiles A and B cut and lapped (Valley, Almath, Precision Ceramics), (b) the same on 127 mm and 138 x 190 mm plates if offered, (c) Shapal Hi-M Soft ground to 2.00 +/-0.05 as a second source. Nothing sent; the owner sends it.
5. **Do not change the mounting concept for this lot.** The QDPAK and hot-sink routes are production-stage options (new layout and enclosure, certifier opinion for the hot sink); revisit them at the next re-layout.

## Uncertain
Alumina k and flatness; Shapal sheet size and tolerance; AlN availability at 2 mm and larger plates; all prices are list or snippet, not quotes; the stack count is the owner's decision.
