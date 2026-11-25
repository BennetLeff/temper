# c60: M11 seating fixture, first design pass (OPEN-ITEMS S32, 2026-11-25)

**Status: tolerance-checked concept. Not drawn, not reviewed, not orderable.** Every number is from `scripts/seat_tolerance.py` (controls inside) or
a bench_params.py parameter it imports.

## The finding that decides it

**The leads, not the bar, limit the fixture.** A flat bar sets the tab plane; each lead must then sit free in its hole, or it is bent and the tab
springs off when released. A lead is a b × c rectangle in a round hole, so its corner touches first. The play is then far below the
(D − c)/2 used in DECISIONS 87 and bench-sink-r1.

| Lead and hole | (D − c)/2 | Corner-limited | Needed | Closes |
|---|---|---|---|---|
| Typical 1.20 × 0.60, smallest hole 1.72 | ± 0.560 | ± 0.233 | ± 0.155 | yes |
| Largest 1.40 × 0.89, smallest hole 1.72 | ± 0.415 | ± 0.055 (below zero with a 0.075 row offset) | ± 0.155 | **no** |
| Largest 1.40 × 0.89, largest hole 1.93 | ± 0.520 | ± 0.130 | ± 0.155 | **no** |

- "Needed" = hole position 0.075 + within-lot A1 0.05 (EST) + bar flatness 0.03, one lot, bar at mid-travel (below). The full datasheet A1 needs 0.305.
- Lot limit: at b = 1.2, c ≤ 0.756 in the smallest hole; at b = 1.3, ≤ 0.615; at b = 1.4, ≤ 0.436 (`lead_limit_one_lot`).
- If the lot fails, 2.04 mm drills close the worst lead. That is a new board, and the pads and the drain neck would need re-checking.

**Gate before drawing: measure b and c on the FET lot** (25 parts, both outer leads and the drain). The same measurement covers b1 (DECISIONS 87).

**BR1 (pass 2):** the 0.665 mm step places BR1 0.2 mm off its nominal 0.465; its lead has ± 0.124 at the worst corner against 0.275 needed. It closes
at nominal sizes (0.290). The step is therefore **provisional**: size it from measured GBJ leads, or shim the pad.

## Concept

1. **Bar:** one stainless 416 or 304 bar (about 115 mm long), ground face flat ≤ 0.03 mm, at y 1.835 (tab plane), z ≥ 9. Stainless, not
   aluminium: the bar must not be a heat sink for the drain joints.
2. **Squareness:** the bar is dowelled to a ground base plate at 90° ± 0.02° (0.3° is the budget). Board rests on pads outside the window and is
   clamped at H5 (24, 74) and H9 (142, 4).
3. **Window:** open below x −2 … 112, y −2 … 22, as bench-sink-r1's baseplate, for bottom preheat and the iron.
4. **Clamps:** one spring finger per package on its front face at z 9–23, above the 1.1 mm SMD row. Force about 10 N: hold, do not bend.
5. **Set the bar (key step):** load the four FETs, clamp lightly, slide the bar in y to both stops, read the travel on an indicator, lock at the middle.
   This needs no datum on the board. **Accept a board only if the travel is at least 0.20 mm** (EST; 2 × 0.10 left). Less travel means a lead is near a wall.
6. **Solder, cool, release.** Then a 0.05 mm feeler across all four tabs against a straight edge.
7. **Pass 2 (BR1, COMMISSIONING 4b):** re-clamp the same bar on the soldered Q2 / Q3 tabs as datum, with the step, sink off.

## Not done

- Drawing, material certificate, cost; whether the clamp fingers clear C12 / C13 / C19 / C20 and the film caps in 3D.
- The bow of the board's row on the pads, and the spring-back of a joint as it cools: not modelled.
- Squareness budget: 0.02° of plate plus board tilt on the pads; no FEA.
- Independent review and pre-mortem (required before ordering).
