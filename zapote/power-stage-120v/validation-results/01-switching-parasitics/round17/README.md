# D1-FEM round 17: full inductance matrices from single-port solves (in progress)

> **Correction (2026-09-30):** the first qualification in §3 used a
> uniform-field fixture and missed a defect: Elmer's VTU writer averages DG
> fields within each body by default, smoothing the per-tet B. The first
> leg-A matrix came out low (diagonal 29.68/28.47/23.50/30.62 vs energy
> 33.05/31.84/29.57/40.31 nH) and failed its spread check; it is withdrawn.
> Fixed and re-qualified on non-uniform fields and on the board — see §5.

- Board: native-17 export, leg A, closures as round 16.
- Mesher: `scripts/mesh25d_hybrid.py` (round 16, with the gates) — one fix:
  the stray-node check in the outer-box meshing was quadratic and never
  finished at 8 M tets; now a set difference (62 s for 7.94 M tets).
- Solver: Hypre GMRES(100) + singular AMS on the remote box, 12 ranks (one
  per physical core; OpenMPI 5 refuses more), tolerance 1e-8.
- Operator: Claude, 2026-09-29. Evidence class: simulation/model-based.

## 1. Tolerance 1e-8 (not 1e-10)

On the round-16 column-free small mesh, P1's energy was 29.77064 nH at
relative residual 1.1e-7 and 29.77092 nH converged (5e-11): 1e-5 relative.
The AMS scan below also shows 29.7527 nH at 6.5e-6 (0.06 % low). At 1e-8
the solver error is far below any mesh error; it saves ~25 % of iterations.

## 2. AMS parameter scan: defaults stay

Small mesh, P1, GMRES(100), 4 ranks, 3000-iteration cap
(`scripts/ams_tune_remote.sh`):

| Variant | Residual at 3000 | Wall |
| --- | ---: | ---: |
| default | 6.5e-6 | 1662 s |
| alpha/beta threshold 0.5 | 6.0e-6 | 1712 s |
| relax times 2 | 1.1e-5 | 2110 s |
| cycle type 13 / 14 | crash in Hypre setup (Elmer passes no Pi components) | |

## 3. Mutual inductances by reciprocity (qualified exactly)

For lowest-order edge elements, x_iᵀ K x_j = (1/μ0) ∫ B_i·B_j dV and
K x_j = b_j, so L_ij = (1/μ0) Σ vol · B_i·B_j over tets, exactly, from
single-port solves. B is constant per tet; Elmer writes it as the elemental
field `magnetic flux density e` (`run_elmer.py --vtu`: Discontinuous
Galerkin, bulk only). Elmer's elemental output is not discontinuous at
interior boundaries: nodes on a port sheet carry the other side's value, so
each tet's B is taken from its nodes off the port sheets
(`scripts/inductance_matrix.py`; the within-tet spread of the rest is
checked, normalised by the largest |B| of all runs).

Two-port plate section, exact L11 3.141593 / L22 1.884956 / M 1.884956 nH:

| Run | L11 | L22 | M | spread |
| --- | ---: | ---: | ---: | ---: |
| Mac, direct, 1 partition | 3.141593 | 1.884956 | 1.884956 | 3.5e-11 |
| Remote, GMRES+AMS, 4 partitions | 3.141593 | 1.884956 | 1.884956 | 3.1e-11 |

An earlier attempt integrating the elemental A over the other port was off
by 0.1–0.3 % (Elmer's elemental A is not the raw edge field) and is not
used.

This cuts the campaign from 10 solves (4 ports + 6 pairs) to 4 per arch
height.

## 4. Campaign (running)

`scripts/campaign.py`, resumable: for (h, e) in 1:0.35, 2:0.35, 3:0.35,
1:0.5, 1:0.7 — mesh, gates (no PEC columns, zero leakage, closed loops),
four single-port solves with VTU, matrix. First fine mesh: 7.94 M tets,
47 GB on 12 ranks, gates pass. Results to follow in `results/`.

Observability: `campaign.py` reads each solve's Hypre residual every 30 s
and keeps `WORKDIR/status.json` current (iteration, residual, rate over the
last 10 min, ETA from a log-residual fit over the last ~500 iterations,
memory); `campaign.log` gets START / PROGRESS (every 5 min, with a bar in
orders of magnitude to the tolerance) / DONE / GATES / MATRIX / FAIL lines.
`scripts/status.py WORKDIR` prints the whole campaign as a table.

## 5. Mutual-inductance re-qualification (after the DG-averaging defect)

`run_elmer.py --vtu` now sets `Average Within Materials = False` and saves
the solution (`Output File`), so fields can be reprocessed without
re-solving. `inductance_matrix.py` now gates on (a) within-tet spread at
round-off and (b) each diagonal matching its solve's energy to 1e-5;
`campaign.py` runs that gate after every solve and stops on failure, and
checks the matrix exit code. `scripts/qualify_mutual_remote.sh`:

| Check | From B fields | Independent | Spread |
| --- | ---: | ---: | ---: |
| Q1 plate + floating block (non-uniform), L | 2.762937 nH | 2.762936 (energy) | 9e-16 |
| Q2 two-port plate, L11 / L22 / M | 3.141593 / 1.884956 / 1.884956 | exact | 2e-15 |
| Q3 board, coarse leg A, M12 (P1–P2) | 18.106446 nH | 18.106450 (pair-solve energy) | 1e-15 |

The four h1 solves (energies valid: P1 33.047, P2 31.843, P3 29.573,
P4 40.308 nH) are re-run for their fields; their averaged outputs are
archived on the remote box (`r17/averaged-vtu-runs`).

## 6. First valid matrix: leg A, 1 mm arches, 0.35 mm mesh (7.94 M tets)

Gates: within-tet spread 1.1e-15; every diagonal matches its solve's energy
to ≤ 2e-7.

| nH | P1 C38 | P2 C39 | P3 gate high | P4 gate low |
| --- | ---: | ---: | ---: | ---: |
| P1 | 33.047 | 19.991 | 3.792 | 5.673 |
| P2 | 19.991 | 31.843 | 3.595 | 5.634 |
| P3 | 3.792 | 3.595 | 29.573 | -0.303 |
| P4 | 5.673 | 5.634 | -0.303 | 40.308 |

Coupling k: C38–C39 0.6163, power–gate 0.1213 / 0.1554 / 0.1171 / 0.1573, gate–gate -0.0088.
C38 ∥ C39 effective loop: 26.20 nH. These include the 1 mm closure arches:
not the board value until the h → 0 extrapolation (2 and 3 mm running),
mesh convergence, the air-box check and package inductance are done.

## 7. Hand estimate of the arches (`scripts/arch_estimate.py`)

Strip-over-plane (Wheeler/Hammerstad, air) plus two vertical legs per
closure, return plane bracketed at 0.5 mm (In1) and 1.07 mm (In2) below the
top copper; relative to a flat strip on the top copper (h = 0).

| Loop | dL(1) | dL(2) | dL(3) | straight-line error at 0 | parabola error at 0 | level-1 arch left at h = 0 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| P1/P2 | 6.6–9.1 | 13.9–17.0 | 21.3–24.8 | −0.7…+1.1 | −0.5…+0.9 | 0 |
| P3/P4 | 3.8–4.3 | 8.5–9.2 | 13.6–14.4 | −0.9…−0.6 | −0.6…−0.4 | 2.0–2.9 |

(nH.) Predictions to check: P1's simulated L(2) − L(1) should be 7.3–8.0 nH;
P1 board-only (flat connection across C38) ≈ 33.05 − (6.6…9.1) ≈ 24–26.5 nH.
**Flaw:** the gate–source bridges sit at h + 1 mm (they cross over the
drain–source bridges), so they do not extrapolate away; gate-loop values
would stay ~2–3 nH high. Arch–arch mutual coupling is not modelled.
