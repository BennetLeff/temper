# Round 18: why the remote FEM extraction is slow, and how to make it faster

> Lab notebook for the speed-up investigation set by
> [`round17/native21-setup/SPEEDUP-BRIEF.md`](../round17/native21-setup/SPEEDUP-BRIEF.md).
> Operator: Claude, 2026-10-07/08, while the native-21 chain ran. Evidence
> class: measurements on the remote box (small meshes, 2 ranks) and the
> chain's own logs, read passively. **Estimates are labelled.** No solve of
> the live chain was touched; the recommendations are for the user to schedule.

**Status: battery 6 (§4.2, the causes of the remaining ~2000 iterations) was still running on the box at hand-back; results land in `~/temper-fem/speedup/logs/battery-b6.log`.**

## 0. Summary

| # | Change | Speed-up | Accuracy evidence | Confidence |
| --- | --- | --- | --- | --- |
| R1 | `Linear System Scaling = False` in the AV solver (no code change) | iterations to 1e-8: **4653 -> ~2000 (2.3x) measured** on the round-16 board mesh at 2 ranks; 6105 at 12 ranks in round 17 | L = 29.77090 vs direct 29.77092 nH; Q1-Q3 re-qualification PENDING | high for this mesh; PENDING on the ladder (§4.1) |
| R2 | Fine extraction at h = 1 mm only (drop fine h2, h3) | chain **10.6 -> 4.7 days, 2.27x (estimate)** | round 17's own check: h1-only vs full recipe 0.026 nH, 0.10 % of sqrt(LiiLjj) (rerun here) | high (already the leg-B19 recipe) |
| R3 | Memory guard + a plan for leg A21 fine | avoids a predicted OOM of the whole box (71 GB est. vs 62 GB) | §5 | the estimate is solid (6.1 kB/tet on every solve); the fix needs a user decision |
| R4 | B21 coarse corrections on the Mac in parallel | removes ~12 h (estimate) from the remote queue | same solver, qualified on the Mac in round 17 | medium (Mac Elmer must be rebuilt; one Mac timing is an outlier) |
| R5 | Do not run experiments beside the chain on its hyper-thread siblings | — | measured: the chain loses 17.7 %; and a run at a case boundary stalls it (26 min lost once, now guarded) | high |

R1 x R2 together: **~5x on the chain (estimate)** (2.27 x ~2.3; R1 applies to the
Krylov time, 98-99 % of every solve). §4.2 asks what explains the remaining
~2000 iterations (healthy AMS needs tens to ~100); PENDING.

## 1. History (4a)

`scripts/history.py` parses every solve under `~/temper-fem/r16` and `r17`
(97 runs: `logs/history.tsv`); `scripts/history_summary.py`
(`logs/history_summary.txt`) summarises the converged 12-rank board solves:

| Class | Solves | Iterations to 1e-8 | Krylov share of wall | Setup (load+assembly+AMS+Hypre) | Post (fields+VTU) | c = s*rank/(it*Mtet) | Memory |
| --- | ---: | --- | --- | ---: | ---: | ---: | --- |
| fine 0.35 mm (7.9-9.9 M tets) | 21 | median 9121 (7405-10705) | 99.0-99.4 % | 41 s | 59 s | 2.02 | 6.06-6.23 kB/tet |
| coarse 1.0 mm (2.2-3.3 M tets) | 24 | median 5991 (4235-9797) | 98.2-99.2 % | 11 s | 17 s | 1.61 | 6.23-6.53 kB/tet |

- Iterations hardly depend on mesh size: 850 k tets needs 6105 (12 ranks), 8.6 M tets 7478-9871.
  The cost is in the solver set-up of the problem, not in h.
- Iterations depend on the partition: the same mesh and port take 4653 iterations at
  2 ranks (`runs/base-thin-full`) and 6105 at 12 (round 17 `qual/q3p1`) to 1e-8.
- Native-21 is worse: leg A21's coarse base needed **12,672-14,055** iterations per port
  (live `a21c/campaign.log`), 2x native-19's; its coarse case took 8.0 h, not ~3 h.
- **Native-21 leg A at h = 0.5 mm is harder still:** P1 16,004 and P2_C39 **20,109**
  iterations (2 h 47 min), above every earlier coarse solve. Our experiments do not explain
  it: iteration counts do not depend on load, and its rate (1.976 it/s with our runs beside
  it) is the same per iteration as the h1 ports (1.715 it/s beside our runs, 2.086 alone, on
  a 12 % larger mesh; `logs/chain_n21_rates.txt`). Our runs cost it ~15 % of its wall time
  (estimate, from that ratio); the rest is the 20 k iterations.
- Every solve converged; no crash except AMS cycle types 13/14 (round 17, exit 139).
- ElmerGrid partitioning 10-34 s per port (directory timestamps,
  `logs/n21-coarse-phase-times.txt`); meshing + gates ~20 s per coarse case, 80 s fine
  (`logs/mesh-gate-times.txt`).

## 2. Profile (4b)

perf is unavailable (`perf_event_paranoid = 4`, no sudo) and ptrace is limited to
descendants (Yama scope 1), so the chain could not be sampled. Passive evidence:

- `pidstat`: every chain rank 99.9 % user CPU, ~2 involuntary switches/s, no page
  faults: Open MPI busy-polls, so CPU% cannot separate compute from waiting.
- **Phase split** (all solves, solver.log timers): Krylov 98-99.4 %; mesh load
  7-29 s, assembly 2-7 s, AMS setup 1-2.5 s, Hypre setup 2-9 s, fields + VTU 15-80 s.
  Live native-21 coarse ports: non-Krylov time 27-54 s of 2195-7568 s.
- **Memory by phase** (`scripts/rss_sampler.py`, our 2-rank runs, `logs/rss/`):
  on 824-851 k tets: mesh loaded 3.6-3.7 GB, assembled 3.7 GB, Krylov 5.2-5.3 GB peak,
  field calc and VTU add nothing. The GMRES(100) basis is ~0.96 kB/tet of the 6.2.
- **Bound by what?** Not settled within the budget. Evidence: (a) our 2 ranks beside
  the chain cost it 17.7 % (2.086 -> 1.718 it/s, `scripts/chain_rate.py`);
  (b) on a nearly idle box (the chain blocked at a case boundary, 09:09-09:24),
  2 ranks ran legA-small-thin at 0.136-0.143 s/iteration, against 0.106 s/it for 12
  ranks in round 17: 12 ranks only 1.3x faster than 2; (c) on the hyper-thread
  siblings of busy chain cores, the same 2 ranks take ~1 s/it and 1 rank 1.76 s/it
  (`runs/ns-thin-np*-400`). (b) points to memory bandwidth or communication limits at
  12 ranks; it is one measurement on a box that was not fully idle. The whole-machine
  test `scripts/scaling_test.sh` settles it (§7).

## 3. Hypotheses

### H1 One matrix, four right-hand sides

The port enters only the RHS (`run_elmer.py`: a `Magnetic Field Strength` BC on the
port's boundary; PEC and every other boundary identical). But set-up is ≤ 1.6 % of a
port solve (above), so one assembly + one AMS setup for four ports saves < 1.6 %
(measured). Block/multi-RHS Krylov: not in Elmer or Hypre's ParCSR Krylov solvers; would
need new code. Previous port's solution as initial guess (estimate): the ports' fields
couple with k = 0.12-0.62 (round 17 §6), so the best scaled guess removes at most
1 - sqrt(1 - k^2) ≈ 21 % of the initial error, i.e. ~0.1 of 8 decades: ~1-2 % of the
iterations. Not worth doing.

### H2 Krylov method

PCG + AMS diverges (residual grows to 0.3 after 4000 iterations, `runs/r18on-thin-pcg`),
as in round 16: Elmer hard-codes the auxiliary AMG relaxation to type 3 (hybrid
Gauss-Seidel, forward), which makes AMS non-symmetric. GMRES(30) with the round-18
patch: 7.1e-7 after 4000 iterations against 1e-8 after 2584 for GMRES(100). Scaling off:
GMRES(30) 3660 iterations against ~2050 for GMRES(100) (+78 %), memory 2.395 vs 2.683
GB/rank (-10.7 %). Restarts hurt; GMRES(30) is a memory lever only.

### H3 Stopping criterion

`scripts/tol_savings.py` on every 1e-8 run's residual history (`logs/tol_savings.tsv`):
stopping at 1e-7 saves 3-30 % (median ~15 %), at 1e-6 12-55 % (median ~29 %).
Energy error against residual (round 16/17 data, legA-small-thin, direct 29.77092 nH):
residual 1.1e-5 -> -1.2e-3, 6.5e-6 -> -6.1e-4, 1.1e-7 -> -9.4e-6, ≤ 1e-9 -> exact: the
relative energy error is ~90x the residual. **Scaling off** (`runs/ns-thin-tol1e-*`,
same mesh, P1, 2 ranks):

| Tolerance | Iterations | L (nH) | vs direct 29.77092 |
| --- | ---: | ---: | ---: |
| 1e-6 | 1376 | 29.76998 | -3.2e-5 |
| 1e-7 | 1731 | 29.77082 | -3.4e-6 |
| 1e-8 | ~2050 (1.9e-8 at 2000) | 29.77090 | -6.7e-7 |

1e-7 saves ~15 % at an energy error 30x below the brief's 1e-4. Mutuals at 1e-7 are not
checked (Q3 ran at 1e-8), so the chain keeps 1e-8; 1e-7 is a qualified-later option.

### H4 AMS settings — and the defect behind most of the iterations

Elmer's `SolveLinearSystem` scales the system before Hypre sees it
(`Linear System Scaling`, default True): A^ = S A S, S = diag(1/sqrt|a_ii|). The
discrete gradient G and Nedelec interpolation Pi it passes to AMS
(`SParIterSolver.F90`, `PrepareHypreAMS`) are not scaled. AMS assumes range(G) is the
near-kernel of the matrix it gets; for A^ that is S^-1 range(G). On these graded meshes
(35 um copper to 4 mm far field) S varies by orders of magnitude, so AMS's corrections
act on the wrong vectors.

Two fixes, legA-small-thin (round 16's column-free board mesh, 850,640 tets, P1;
direct 29.77092 nH), 2 ranks:

| Run | Iterations to 1e-8 | L (nH) | Note |
| --- | ---: | ---: | --- |
| baseline (`base-thin-full`) | 4653 | 29.77088 | 6105 at 12 ranks (round 17 q3p1) |
| **scaling off** (`noscale-thin-2000`) | **2000 (1.9e-8)** | 29.77090 | no code change |
| patched AMS (`r18on-thin`) | 2584 | 29.77092 | G and Pi rows scaled by 1/s_i (`scripts/patch_elmer_ams.py`, separate install) |
| patched library, keyword off (`r18-scaleaux`) | identical residuals to baseline | | control |

Scaling off is simpler and better; the patch is not needed.
**Caveat (a mistake corrected on the way):** the first test mesh, `meshes/sA-e3`
(native-21 leg A cropped to 2 mm), fails the closed-loop gate for P1 (two PEC
components): every variant stalled near 1e-2 there, including scaling off for 20,000
iterations (`logs/v1-noscale-gmres.txt`). Those runs are not evidence for or against
anything; they do show what an inconsistent RHS looks like (§4.2).

AMS scan beyond round 17 (scaling off, iterations to 1e-8): default ~2050; cycle type 7
2119; alpha threshold 0.6 **1884 (-8 %)**; GMRES(30) 3660. Threshold 0.9, 3 AMS cycles per
iteration, GMRES(300), non-singular mode and Dirichlet scaling: battery 6 (§4.2).

### H5 Parallel configuration — PENDING whole-machine test (§7)

### H6 Mesh size

Tets are geometry-limited: native-21 leg A at 2.0 mm edges and 3 mm margin still has
1.54 M tets (`meshes/sA-e2.log`). The air box (+0.7 %) and crop (converged at 20 mm)
are round 17 results; coarsening far from the loops was not pursued: Krylov iterations,
not tets, dominate.

### H7 Campaign structure

`scripts/recipe_check.py` (`logs/recipe_check.txt`) re-runs round 17's
`fine_h1_recipe_check.py` without its ngspice import chain: h1-only recipe vs full
recipe max |d| 0.026 nH = 0.10 % of sqrt(LiiLjj). Round 17 already dropped fine h2/h3
for leg B19 on this basis; `chain_n21.sh` still runs them for both legs (4 of its 6
fine cases, ~60 % of its estimated time). Transferring the fine-minus-coarse offset
between legs instead of solving fine h1: 1.05 % of sqrt(LiiLjj) between leg A n17 and
leg B n19 (same script): too large to recommend as the default.

`scripts/chain_estimate.py` (`logs/chain_estimate.txt`), **estimates**, scaled from
measured native-19 cases with the measured native-21 coarse base walls:

| | Current chain | Proposed (R2) |
| --- | ---: | ---: |
| wall | 255 h = 10.6 days | 113 h = 4.7 days |

(The A21 base wall used here includes ~10 h beside our experiments, which cost the chain
~18 %; the estimate is high by up to that.)

### H8 Build

Not pursued: with ~2000-5000 iterations of a memory/communication-bound kernel, a
`-march=znver3` rebuild is worth ≤ 10-15 % (estimate, from typical SpMV/AMG
vectorisation gains); R1/R2 come first.

## 4. The remaining iterations (coordinator priority) — PENDING

### 4.1 Q1-Q3 re-qualification with scaling off (`scripts/qualify18.sh`)

Round 17's mutual-inductance qualification re-run with `Linear System Scaling = False`,
2 ranks (`logs/qualify-noscale.log`, `logs/qualify-noscale-q1q2.log`):

| Check | Scaling off | Reference | Iterations (off) | Iterations (round 17, scaling on) |
| --- | --- | --- | ---: | ---: |
| Q1 plate + floating blocks, L from B vs energy | 2.762937 vs 2.762936 nH, spread 1.0e-15 | 2.762936 (direct) | 100 (1e-10) | 198 |
| Q2 two-port plate L11 / M | 3.141593 / 1.884956 nH | 3.141593 / 1.884956 exact | 32, 32 (1e-10) | 82, 82 |
| Q3 board (legA-small-thin) L11 | 29.770909 (B) / 29.7709 (energy) | 29.77092 direct | 2119 (1e-8) | 7783 (1e-9, 12 ranks) |
| Q3 L22 | 29.054665 / 29.05466 | 29.05466 (round 17) | 2228 | 7123 |
| Q3 M12 from B fields vs pair-solve energy | **18.106441 vs 18.106450** nH | round 17: 18.106446 / 18.106450 | pair 2086 | 5259 |
| Q3 gates | within-tet spread 8.6e-16; diagonals vs energy 3.0e-7, 1.8e-7 | ≤ 1e-5 | | |

M12 by reciprocity and by pair energy agree to 9e-6 nH (5e-7 relative); every entry is
within 1e-6 relative of round 17's. Q2's L22 line was cut when captured (operator error);
its full re-run is queued (`logs/qualify-noscale-q2-full.log` when it lands).
The fixture meshes have no mesher log, so `inductance_matrix.py`'s port-identity check
needed a port record beside them: `r17/qual/meshes/{f2,sect2,legA-small-thin}.log`,
written by hand with round 17's drives and marked as a round-18 shim.

### 4.2 What explains ~2000 iterations — PENDING (battery 6)

## 5. Leg A21 fine h = 1 mm does not fit in memory

Every solve so far used 6.06-6.53 kB per tet (history). Native-21 coarse h1 meshes:
A21 3,373,055, B21 2,715,967 tets (live chain). Fine/coarse ratio at h = 1 mm: 3.45
(leg B n19) - 3.59 (leg A n17). Estimates: **A21 fine h1 11.6-12.1 M tets, 71-74 GB;
B21 fine h1 9.4 M tets, 57 GB**, on a 62 GB box with 1 GB swap. fine h2/h3 are larger.

What reduces it (measured on 850 k tets, 2 ranks): scaling off changes nothing
(2.683 vs 2.688 GB/rank); the field calculation and VTU output add nothing (peak is in
the Krylov phase); GMRES(30) saves 9.3 % (2.439 vs 2.688 GB/rank) but slows convergence
with the patch (PENDING with scaling off). So A21 fine h1 is ~64 GB at best: **it does
not fit by any solver setting tested.** Options, for the user:
1. More memory (64 -> 128 GB DDR4), or a swap file (~16 GB): the mesh structures
   (~70 % of the RSS, loaded before the Krylov phase and only read again after it) are
   the cold pages. Swap is an estimate of behaviour, untested.
2. Fine h1 for A21 at 0.45 mm edges instead of 0.35 (estimate from the n17 leg-A
   ladder, tets ~ h^-1.32: ~8.4 M tets, ~51 GB). This changes the mesh-offset step of
   the recipe; FINDINGS M1 accepts +4-6 % on self-L and the 0.35 -> 0.45 difference is
   ~1 % (estimate from round 17's 0.35/0.5/0.7 ladder).
3. Transfer the fine offset (1.05 % error, above).
The proposed chain runs B21 fine first and guards A21 (refuses above 56 GB) so the box
is never OOM'd; option 1 or 2 is the user's call.

**Decision (user, 2026-10-08): option 2.** chain_n21_v2.sh was launched at 2026-10-08
~21:10 UTC (rescaling off from legA21-h2 on; base cases and legA21-h0p5 reused).
[`fine_n21_e0p45.sh`](fine_n21_e0p45.sh) waits for it to exit, then solves fine h = 1 mm at
0.45 mm edges for each leg whose 0.35 mm case the guard refused (A21 certainly; B21 at
~57 GB estimate most likely). `scripts/variant2.sh` now also holds experiments during any
`-e0p*` case, not only `e0p35`.

## 6. The Mac as a second node (estimate)

`scripts/mac_estimate.py` (`logs/mac_estimate.txt`). Round 17's only Mac board solves
(legA h1 e0.7, 3.47 M tets, 10 ranks): c = 0.59, 0.66, 0.72 and one outlier 1.54
s*rank/(it*Mtet), 4.6-4.9 kB/tet; the remote's coarse median is 1.61. At 8 ranks a case
on the Mac takes 0.61x (best 3) to 1.43x (outlier) of the remote's wall (estimate).
With ~26 GB usable, every B21 coarse correction (14.8-21.9 GB at 6.1 kB/tet) and A21
h0.5/h2 fit; A21 h3/m20 (26-27 GB) do not. Disk: ≤ 12.5 GB of field files per case,
deleted per case. `mac_b21corr.sh` runs B21's four corrections there
(`chain_n21_v2.sh` with `B21_CORR_ON_MAC=1` skips them on the remote): ~12 h off the
remote queue at current solver speed (estimate). **Prerequisite: the Mac has no Elmer
install now** (round 17's lived in /tmp).

## 7. Needs the whole machine (user to schedule)

- `scripts/scaling_test.sh` (~1.5 h, box idle): s/iteration at 2/4/6/8/12 ranks, 24
  hyper-threads, 2 x 6 on the two CCDs, 3 x 4, on the b19c coarse mesh at a fixed 500
  iterations. Decides whether two ports at once beat one 12-rank solve.

## 8. Cost of this investigation to the chain (measured)

- 2-rank experiments on CPUs 22/23: chain 2.086 -> 1.718 it/s (-17.7 %).
- 2026-10-08 08:58-09:24: the chain's next case waited for our runs (campaign.py waits
  until no `ElmerSolver_mpi` runs at all): 26 min lost. `variant2.sh` now starts a run
  only while the chain is mid-solve.
- One useless 20,000-iteration run (the broken sA-e3 mesh) could not be stopped: the
  session's permission rules refuse `kill`.

## 9. Recommendations, ranked

1. **R1 `Linear System Scaling = False`** for every solve (no code change). Iterations to
   1e-8: 4653 -> ~2050 on the board mesh at 2 ranks, 2.3x (measured); fixtures 2-2.5x.
   Q1-Q3 re-qualified (§4.1). Confidence high. Optional on top: AMS alpha threshold 0.6
   (-8 %, one measurement) and tol 1e-7 (-15 %, energy error 3.4e-6; mutuals unchecked).
2. **R2 fine h = 1 mm only.** 2.27x on the chain (estimate), accuracy 0.10 % (round 17's
   check, rerun). Confidence high.
3. **R3 memory guard** on A21 fine (56 GB): the 0.35 mm A21 fine case is ~71 GB (estimate)
   and does not fit by any solver setting tested (GMRES(30) -10.7 %, scaling off 0 %,
   VTU 0 %). User options: 128 GB RAM; A21 fine at 0.45 mm (~51 GB est.); a swap file
   (untested); or offset transfer (1.05 % error).
4. **R4 Mac** takes B21's coarse corrections (~12 h off the remote queue, estimate;
   needs an Elmer build on the Mac first).
5. **Whole-machine scaling test** (`scripts/scaling_test.sh`) before betting on
   concurrent ports: one near-idle measurement says 12 ranks are only 1.3x faster than 2.
Combined R1 x R2: chain ~10.6 days (current, estimate) -> ~2 days (estimate:
113 h / 2.3 on the 98-99 % Krylov share).

**Current chain:** stop it at the next case boundary after the coarse corrections at
the latest, and certainly before `campA21` fine starts (predicted OOM of the whole box).
Stopping now (kill only the `chain_n21.sh` bash; the running case finishes) and
relaunching as `chain_n21_v2.sh` saves the most: every remaining coarse case runs ~2.3x
faster and the finished ones are reused.

## Files

`scripts/` (history, tol_savings, recipe_check, chain_estimate, mac_estimate,
chain_rate, rss_sampler, variant/variant2/battery/battery2, qualify18, patch_elmer_ams
+ build_elmer_r18, run_elmer18, campaign18, scaling_test), `lists/` (the batteries as
run), `logs/` (parsed summaries; raw solver logs stay on the box in
`~/temper-fem/speedup/runs`), `chain_n21_v2.sh`, `mac_b21corr.sh`.
