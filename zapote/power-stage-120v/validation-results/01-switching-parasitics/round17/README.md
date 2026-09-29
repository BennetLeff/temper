# D1-FEM round 17: full inductance matrices from single-port solves (in progress)

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
