# D1-FEM round 12: an iterative Elmer solver, qualified

- Solver: Elmer (round-6 build, `/tmp/ps-r6-fem-elmer-install`), first-order
  edge elements. Operator: Claude, 2026-09-28.
- Fixtures: the round-9/10 meshes (exact sections, two-port section,
  board-style thick plates). Results: `results/iterative-fixtures.json`.
- **Verdict: BiCGStab(l) (degree 4) with ILU1 is qualified.** It
  reproduces every exact value and the direct solver to every printed digit,
  with Elmer's abort-on-non-convergence proven by a negative control, and
  its memory grows about linearly. The board solve fits this 32 GB Mac by
  estimate.

## Settings (candidate I1)

```
Linear System Solver = Iterative
Linear System Iterative Method = BiCGStabl
BiCGStabl Polynomial Degree = 4
Linear System Preconditioning = ILU1
Linear System Convergence Tolerance = 1e-10
Linear System Abort Not Converged = True
Use Tree Gauge = False
```

**Negative control:** the same section with `Max Iterations = 50` ends with
`IterSolve: Too many iterations were needed`, exit 1 and no energy. So an
exit code of 0 under these settings means the solve reached the tolerance
(round 6's AMS run reported success while stagnating; this can't).

## Results

| Fixture | I1 | Reference | I1 peak memory / time |
| --- | ---: | ---: | ---: |
| Section, port on the boundary | 3.141592 nH | exact 3.141593 | 0.37 GB / 14 s |
| Section, port 2 mm inside | 3.141592 nH | exact 3.141593 | 0.38 GB / 16 s |
| Two-port section L₁₁ / L₂₂ / M | 3.141592 / 1.884956 / 1.884956 nH | exact | 0.37 GB / ~13 s each |
| Thick plates, 0.5 mm (154k tets) | 2.785094 nH | direct 2.785094 | 0.57 GB / 12 s (direct 2.9 GB / 62 s) |
| Thick plates, 0.35 mm (403k tets) | 2.808988 nH | direct 2.808988 | 1.35 GB / 53 s (direct 9.9 GB / 417 s) |

Other candidates: **GCR + ILU2 failed** every fixture (Elmer aborted on
non-convergence). **BiCGStab + ILU2** returned the exact values with exit 0
under the same abort setting, but prints residuals in a format the runner
doesn't parse, so it isn't counted; I1 is the one to use.

## Board estimate

I1's peak memory grew as about N^0.9 (0.57 → 1.35 GB for 154k → 403k
tetrahedra). Applied to round 11's leg-A counts: about 9 GB (3.2 M), 13 GB
(5.2 M) and 23 GB (9.5 M). These fit 32 GB; the iteration count on the real
board (many conductors, thin gaps) is the thing to watch, not memory.

## Next (round 13)

1. Fix the last barrel conflict (C40.2, top of In1; the surrounding copper
   is ordinary, so it's a mesher robustness issue at fragmented faces) and
   mesh with barrels.
2. Add the four ports per leg and the raised arches (D1-FEM §2, round-6
   amendment) as flat sheets with a constant direction.
3. Solve leg A with I1 at 0.25/0.6 then 0.2/0.5 mm, and check the iteration
   count, memory and the crop/mesh convergence rules of §5.

## Reproduce

```sh
R9=... R10=... OUT=...   # meshes from round9/round10 scripts
scripts/battery.sh
/Users/bennet/Miniforge3/bin/python3 scripts/run_elmer_fixture.py sect.msh neg --pec 2 --port 4 \
    --k 0 0 100 --iterative BiCGStabl --precond ILU1 --maxit 50    # must fail
```
