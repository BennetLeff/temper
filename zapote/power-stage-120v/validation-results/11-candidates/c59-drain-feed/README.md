# c59: what to do about the 0.637 drain-pin copper (OPEN-ITEMS S33, DECISIONS 88)

Desk scope, 2026-11-25. Nothing is built or ordered. Copper read from s57 (`25596d8e`).

| Option | Result | Evidence |
| --- | --- | --- |
| Second copper layer (F.Cu tongue + vias) | **Not a local edit.** 6 vias give 2.07-2.37 x F1, but the tongue breaks the 3.2 mm rule to the snubber pads (C12 / C13 / C19 / C20) by 0.475 mm, and with those moved, to the gate resistors (R10 / R12 / R18 / R20) by 0.328 mm; plane voids grow up to 1.75 mm. A shape that (nearly) fits has room for 3 vias, 0.52-0.59 x | `scripts/drain_feed_scope.py` (screen only: no refill, DRC, thermal or return-path check; three shapes plus one with snubbers ignored) |
| Fuse, same clips | KLKR020 (fast) 900 A2s = 1.21 x; CCMR020 (time-delay) 918 A2s = 1.19 x. Carry by the repo's 0.75 rule is 13.5 A: exactly the 13.5 A release line, under the 15 A target (no margin) | `scripts/fuse_vs_neck.py`; survey values, some read from mirrors; KLKR derate assumed |
| Fuse, new clips | Bel 0ADEC9250-BE 470 A2s = 2.32 x, carry 18 A. UL Recognized, not Listed: waits on the certifier (item 32), and needs the F1 footprint changed | `12-decisions/f1-data/`, which used the old 1,698 A2s neck |

**Judgement:** do not re-layout the FET row. F1 and its clips are fitted by the owner, so a same-clip fuse does not touch the bare board.
For the prototypes prefer CCMR020 (time-delay, so less nuisance risk) with the 13.5 A release limit kept. Not checked: its melting I2t
(nuisance and F2 selectivity, gates G3 / G5), its stock, and the 25 A basis the certifier packet cites. `f1_decision.py` G4 still uses
the old neck; KLDR025 fails G4 by 36 %, not 0.7 %.
