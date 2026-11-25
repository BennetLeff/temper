# c59: what to do about the 0.637 drain-pin copper (OPEN-ITEMS S33, DECISIONS 88)

Desk scope, 2026-11-25. Nothing is built or ordered. Copper read from s57 (`25596d8e`).

| Option | Result | Evidence |
| --- | --- | --- |
| Second copper layer (F.Cu tongue + vias) | **Not a local edit.** 6 vias give 2.07-2.37 x F1, but the tongue breaks the 3.2 mm rule to the snubber pads (C12 / C13 / C19 / C20) by 0.475 mm, and with those moved, to the gate resistors (R10 / R12 / R18 / R20) by 0.328 mm; plane voids grow up to 1.75 mm. A shape that (nearly) fits has room for 3 vias, 0.52-0.59 x | `scripts/drain_feed_scope.py` (screen only: no refill, DRC, thermal or return-path check; three shapes plus one with snubbers ignored) |
| Fuse, same clips, 20 A Class CC | CCMR020 (time-delay) 918 A2s = 1.19 x; KLKR020 (fast) 900 = 1.21 x. CCMR carry by the repo's 0.75 rule is 13.5 A: the release line with no margin, under 15 A. No melting I2t is published, so nuisance (G3) and F2 selectivity (G5) are UNKNOWN | `scripts/fuse_vs_neck.py` |
| Fuse, 10 x 38 semiconductor | **Eaton FWC-25A10F** 390 A2s = 2.79 x (checked on the Eaton sheet). **Fails F2 selectivity:** it melts at 60 A2s, under F2's estimated 67, so a blower-tap fault would also open F1. Class aR: the sheet gives no low-overload limit and no ambient derate. UL Recognised, not Listed. Under BR1's 510 A2s but over the plan's 255 (0.5 x 510). **Mersen A60Q25-2:** no I2t on its sheet or product page; the 440 A2s given in review is unverified | same |
| Fuse, new clips | Bel 0ADEC9250-BE 470 A2s = 2.32 x, carry 18 A, every technical gate passes. UL Recognized: waits on the certifier (item 32) and needs the F1 footprint changed | `12-decisions/f1-data/`, graded there on the old 1,698 A2s neck |

**Judgement:** do not re-layout the FET row. F1 and its clips are fitted by the owner, so a same-clip fuse does not touch the bare board.
For the prototypes prefer CCMR020 (time-delay, so less nuisance risk) with the 13.5 A release limit kept. Open on it: G3 and G5
(no published melting I2t; read the time-current curve or ask Littelfuse), stock (distributor listings conflict), and the 25 A basis the certifier packet cites. `f1_decision.py` G4 still uses
the old neck; KLDR025 fails G4 by 36 %, not 0.7 %.
