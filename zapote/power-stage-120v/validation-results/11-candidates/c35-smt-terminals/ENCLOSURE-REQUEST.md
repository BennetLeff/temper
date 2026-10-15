# Enclosure coordination: candidate 35 coil terminals (J2 / J5)

Record for the enclosure session (temper-f7). Nothing has been sent; this file is the request.

## What changes

J2 (COIL_FEED) and J5 (RES_A) change from the Würth REDCUBE THR **74650074** to the REDCUBE SMT **7466004R**
(WP-SMBU, M4 internal through-hole thread). Both stay at the same board poses: J5 (132.0, 70.5) and J2 (132.0, 85.5),
15.0 mm centres, board frame (KiCad x right, y down). The coil leads still land on top of each terminal with an M4
screw, a washer and an upturned insulated ring lug (`ASSEMBLY.md`).

| | THR 74650074 (today) | SMT 7466004R (candidate 35) | Source |
|---|---|---|---|
| Body | 7.0 × 7.0 mm square | Ø7.0 mm round | 74650074 rev 002.002 p.1; 7466004R rev 001.003 p.1 |
| Lug seat (terminal top) above the board top | **2.5 mm** (±0.2) | **5.0 mm** | same pages |
| Lug seat change | | **+2.5 mm** | |
| Thread | M4, through the 2.0 mm body; the screw passes the board through a Ø4.3 mm NPTH | M4, through the 5.0 mm body and a 1.0 mm Ø5.0 spigot that sits in a Ø5.2 mm NPTH; thread length 6 mm (Würth product table) | same |
| Below the board | four pins, 3.0 mm below the board top (trimmed THR leads) | nothing: the spigot ends inside the board | same |
| Torque | 1.2 N·m | 1.2 N·m (min breaking 2.9 N·m, design guide p.10) | same; REDCUBE SMD design guide |

The KiCad 3D model of the THR part puts its top 3.7 mm above the board, not the datasheet's 2.5 mm. The SMT part has no
3D model, so the fit gate uses a 5.0 mm envelope over its courtyard (`validation-plan/enclosure-fit/native21-envelopes.json`).
Board-only fit is clean on candidate 35 (`README.md`, chain results).

## Requests

1. **Lug and lead heights: re-run the R26 coil-lead screen with the lug seat 2.5 mm higher.** In R26 the Litz drops to the
   barrel tops at about world Z 57, at world (9, 142.5) for J2 and (9, 173.5) for J5. With the SMT terminal the ring, the
   barrel and the drop all move up 2.5 mm. Check:
   - the J2 constraint beside T1 (CST3015, body top world Z 42.8): J2's barrel axis ≤ 8 mm from the stud axis, and/or
     barrel plus insulation OD ≤ ~7 mm for the first ~12 mm above the ring;
   - the Litz bend radius and the coil lead length to the new barrel tops;
   - anything above the J2 / J5 area (lid, duct, coil carrier) against the raised stack.
2. **Screw length.** The thread now runs 6.0 mm down from the terminal top and stops at the spigot end, about 0.6 mm above
   the board bottom (the Ø5.2 mm hole continues through the board). With a lug-plus-washer stack of S mm, a screw of
   length L protrudes below the board bottom by about L − S − 5.0 − 1.63 mm (5.0 mm body; board 1.633 mm nominal,
   JLC041622-7628):
   - M4 × 8 with S = 1.8 mm leaves the tip about 0.4 mm inside the board hole, with the full 6 mm thread engaged;
   - M4 × 10 with S = 1.8 mm protrudes about 1.6 mm below the board.
   Please choose the screw from the actual lug / washer stack so the tip stays inside the board, or confirm that whatever
   lies under J2 / J5 (heatsink, PE base, insulation sheet) clears a protruding tip at RES_A / COIL_FEED potential
   (up to 409 V rms / 818 V pk in the no-pan 28 A fault, `ASSEMBLY.md`). The THR part needed the same check: its thread is
   short and the screw already passed through the board.
3. **Exposed metal in plan view is unchanged or smaller.** The washer (DIN 125 M4, Ø9 mm) and the ring (≤ 10 mm wide)
   still set the exposed-metal envelope. The terminal body goes from a 7 mm square (9.9 mm diagonal) to a Ø7 mm circle.
   The 5.0 mm tank rule between J2 and J5 and the 12.6 mm RES_A keep-out to SELV / PE do not change on the board (chain
   gates, `README.md`). `terminal_envelopes.json` needs no edit.
4. **Pull and torque.** Würth gives a tearing force of 300–410 N for the through-thread SMD terminal, applied 5 mm from
   the board (design guide p.9). That is lower than the blind-thread SMD part and has no THR counterpart in the guide. If
   the coil-lead strain relief in the enclosure lets the Litz pull on the lug, say so: the bench pull test on a soldered
   sample (README open items) should use that load.

## Not in scope

The board side is done and gated in this candidate. Nothing in the enclosure CAD is changed here, and no one has been
contacted.
