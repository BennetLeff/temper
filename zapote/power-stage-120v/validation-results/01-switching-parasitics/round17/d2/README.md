# Round 17 D2: switching transient on the FEM board matrix (provisional)

`leg_matrix.cir` is round 3's complementary-leg deck (same Infineon L1
models, driver output-resistance approximation, snubbers, shunt, ramped
current-source load, solver options) with the board copper replaced by the
FEM 4-port matrix: one coupled inductor per FEM port (C38 branch, C39
branch, high-side gate path, low-side gate path) and `K` from the FEM
mutuals. The common-source effect comes from the power-to-gate mutuals, not
a separate `LCS`. Not from the FEM: the bulk path `LBULK` (round-3
heuristic), capacitor ESL `LESL` (TDK bound ≤ ~20 nH; swept), shunt `LSHUNT`
(Vishay 0.5–5 nH). The Infineon model already has the TO-247 leads.

**Wiring check** (`run_d2.py --wiring-check`): with every board inductance
0.01 nH and no coupling, this deck and round 3's describe the same circuit;
all six die measures agree to < 1 % (VDS LS/HS, VGS max/min both devices).

## Provisional case: leg A, 1 mm matrix (arches included), 170 V, 37 A, LS turn-off, 348 ns

| LESL | LS die VDS peak | HS die VDS peak | LS gate after HS on-command (max) | aborted |
| --- | ---: | ---: | ---: | --- |
| 5 nH | 191.2 V | 170.9 V | 2.20 V | no |
| 10 nH | 195.0 V | 171.0 V | — | no |
| 20 nH | 202.7 V | 171.0 V | 2.07 V | no |

Against the task criteria (01-switching-parasitics.md): VDS ≤ 520 V and
off-device VGS < 3.0 V (3.5 V min threshold − 0.5 V) both hold in this one
case. Round 3's single case with heuristic inductances failed both (724 V,
7.37 V); the main difference is its assumed 11.5 nH common-source
inductance, where the FEM gives power-to-gate coupling k = 0.12–0.16.

**Provisional only:** one case, the 1 mm matrix (closure arches included,
10 mm crop margin which round 17's sensitivity runs show overstates L by
several percent), no S2 fault (61/71 A at 280 V), S3, S4, DIR=1 or
dead-time corners yet. The full grid runs on the h -> 0 matrix.
