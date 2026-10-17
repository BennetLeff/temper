# Task 01 rounds: index

One line per round: the question, the outcome, and whether it still holds.
The current answer is in [STATUS.md](STATUS.md). Folder READMEs are the full
records; they are not edited after the fact except to add "superseded" notes.

| Round | Board | Question | Outcome | Status |
| --- | --- | --- | --- | --- |
| [1](README.md) | native-13 | Board loop inductances by sampled plane-pair formulas; first switching sweep | BLOCKED: planes don't overlap along the paths, no capacitor ESL | superseded |
| [2](round2/README.md) | native-13 | Do the complementary drive, dead time and light-load mechanics work? | timing mechanics checked on example inductances | method holds; numbers superseded |
| [3](round3/README.md) | native-15 | ZVS thresholds (A1), heuristic copper inductance scenarios (A2), exploratory grid (B1) | heuristic scenarios only; stress and independence checks FAIL | superseded by FEM; A2's LBULK still used in the deck (see FINDINGS F3) |
| [4](round4/) | native-15/17 | Dead-time ZVS map (C1), dead-time losses (C2), extraction (D1), legacy replay (D2) | C1/C2 conditional; D1 BLOCKED (extraction software) | C1/C2 await the FEM matrix |
| [5](round5/) | native-17 | Commutation and gate-loop extraction with FastHenry; bench plan | BLOCKED (extraction software, port contract) | superseded by FEM ([D1-FEM.md](../../validation-plan/D1-FEM.md)) |
| [6](round6/d1-fem/README.md) | native-17 | First FEM attempt | BLOCKED before extraction | historical |
| [7](round7/d1-fem/README.md) | — | FEM qualification fixtures (coax, plate) | plate fixture below band | historical |
| [8](round8/) | — | Elmer direct solver; Palace build | Palace builds; first coax solve fails | historical |
| [9](round9/README.md) | — | Palace qualification | exact only with boundary ports | Palace not used further |
| [10](round10/README.md) | — | Elmer on all fixtures, incl. two-port mutual | **Elmer qualified** (exact) | holds |
| [11](round11/README.md) | native-17 | How big is a leg-A direct solve? | 140–550 GB: needs an iterative solver | holds |
| [12](round12/README.md) | — | Iterative solver | BiCGStab(l)+ILU1 qualified on fixtures | replaced by Hypre AMS (16) |
| [13](round13/README.md) | native-17 | Build the leg-A model and closures | model built; 3-D mesh fails | closures carried forward |
| [14](round14/README.md) | native-17 | 2.5-D layered mesher | works without barrels; blocked | mesher carried forward |
| [15](round15/README.md) | native-17 | Defeatured mesh, first board solves | mesh had spurious PEC columns | superseded (16) |
| [16](round16/README.md) | native-17 | Converging iterative solver on the board | **Hypre GMRES(100)+AMS** matches direct to 7 digits; via bug fixed | holds |
| [17](round17/README.md) | native-17 | Full 4-port leg-A matrix, extrapolation, sensitivity, switching grid (D2), delegated reviews | first board matrix and grid; see [STATUS.md](STATUS.md) | **current** |

Coordination records for rounds 3–8 are in `../round3-coordination/` …
`../round8-coordination/`.
