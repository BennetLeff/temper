# Brief: profile the remote FEM extraction and find how to make it much faster

You are investigating the inductance-extraction job running on the remote workstation. Your goal is
a measured account of where its time goes and a ranked, evidence-backed plan that cuts its wall time
by a large factor (aim for 3–10×) **without** loosening its accuracy. You recommend and prototype; you
do not change the running job.

## 1. Context in five minutes

- **What the job computes.** Task 01 needs a 4×4 loop-inductance matrix per half-bridge leg of the
  native-21 power board: two bus-capacitor loops plus two gate loops. Each matrix comes from four
  single-port magnetostatic solves (1 A per port) of a 2.5-D layered tetrahedral mesh of the
  board's copper. The mutuals come by reciprocity from the four solutions' B fields
  (`round17/scripts/inductance_matrix.py`).
- **Solver.** Elmer `WhitneyAVSolver` (lowest-order edge elements), Hypre GMRES(100) preconditioned
  by singular AMS, tolerance 1e-8, 12 MPI ranks (`round17/scripts/run_elmer.py --hypre-ams
  --hypre-method 8 --ams-singular`). Each solve writes elemental B as VTU, and the matrix is built
  from that.
- **Campaign.** `round17/scripts/campaign.py` meshes, gates, runs the four solves one at a time
  (memory), builds the matrix and keeps `status.json` / `campaign.log` current. The native-21 chain
  is [`chain_n21.sh`](chain_n21.sh). Per leg it runs:
  - a coarse base (arch height h 1 mm, 1.0 mm edges);
  - four coarse corrections (h 0.5/2/3 mm, and h 1 mm at a 20 mm crop);
  - three fine cases (h 1/2/3 mm at 0.35 mm edges).

  That is 8 cases × 4 solves × 2 legs = **64 solves**.
- **Known timings.**
  - Coarse native-21 leg A: 3.37 M tets, ~2.1 it/s, ~21 GB, ~1.5–2 h per port (ETA estimate).
  - Fine native-19 leg B: 8.6 M tets, ~0.7 it/s, ~51 GB, several hours per port.
  - Whole chain: **roughly a week**.
- **Why it matters.** These matrices feed the switching decision grid (STATUS.md). The engineering
  loop waits on them, and every board revision repeats the whole campaign.

Read first, in this order:
1. `validation-results/01-switching-parasitics/STATUS.md` (current answer, "How far to trust it").
2. `ROUNDS.md`: round 11 (a direct solve needs 140–550 GB), round 12 (BiCGStab+ILU), **round 16**
   (why Hypre GMRES(100)+AMS; matches direct to 7 digits), **round 17 README §1–5** (tolerance
   choice, AMS parameter scan, reciprocity, the DG-averaging defect and its re-qualification,
   campaign observability).
3. `round17/scripts/`: `campaign.py`, `run_elmer.py`, `mesh25d_hybrid.py`, `inductance_matrix.py`,
   `matrix_gate.py`, `status.py`, `ams_tune_remote.sh`, `qualify_mutual_remote.sh`.
4. [`README.md`](README.md) in this folder (the native-21 setup and the new gate-loop closures).
5. `FINDINGS.md` M1/M2 (mesh-error and curvature findings that set the case list).

## 2. The machine and how to reach it

- `bennet@100.121.239.87` over Tailscale. AMD Ryzen 9 5900X: **12 physical cores / 24 threads,
  one NUMA node**, 64 MB L3, 62 GB RAM, 938 GB disk (~200 GB free). Open MPI 4.1.6. Elmer built
  Release from conda hypre 2.32 / MUMPS 5.7 / OpenBLAS (`~/temper-fem/build-elmer.sh`;
  install `~/temper-fem/elmer-install`; conda env `temper-fem`).
- **SSH.** Tailscale SSH asks for a browser approval per new session. Reuse the user's control
  socket: `ssh -o ControlPath=~/.ssh/cm/fem bennet@100.121.239.87 ...` (opened 2026-10-07 22:04
  local time, 12 h persistence). If `ssh -O check` fails, ask the user to reopen it:
  `ssh -o ControlMaster=yes -o ControlPath=~/.ssh/cm/fem -o ControlPersist=12h -fN bennet@100.121.239.87`.
- The remote login shell is zsh: wrap commands in `bash -lc "..."` and
  `source ~/miniconda3/etc/profile.d/conda.sh; conda activate temper-fem`.
- On the Mac, zsh treats `$VAR:t` as a modifier: write `"${R}:path"` in scp targets.

## 3. Hard rules (the live job comes first)

1. **Do not stop, kill, suspend, re-nice or restart the running chain** (`chain_n21.sh`, its
   `campaign.py`, `ElmerSolver_mpi`), and do not touch its directories `~/temper-fem/r17/{a21c,
   b21c,a21corr,b21corr,campA21,campB21}` or `chain_n21.out`. If your evidence says it should be
   restarted with a better configuration, **recommend** it with the expected saving. The user
   decides.
2. **Never `pkill -f <pattern>` over ssh**: the pattern matches the ssh command line and kills your
   session. `pkill -x ElmerSolver` would kill the live job too. Kill only PIDs you started.
3. **Resource budget while the chain runs.** Elmer under MPI collapses when cores are
   oversubscribed (a 20× slowdown was observed when other work shared the cores). The chain owns
   12 ranks, and a fine solve takes ~51 GB of the 62 GB. Your experiments may use **at most 2
   cores and 6 GB**, on small meshes, and only while the chain is in a coarse case. During a fine
   case (tag `e0p35` in `chain_n21.out`) do profiling and analysis only. If a test needs the full
   machine, design it, estimate it, and put it in your report for the user to schedule.
4. **Disk.** The root filled to 0 bytes once (round-17 field files, ~7.5 GB per fine port). Work in
   `~/temper-fem/speedup/`. Delete `case.result.*`, `*.vtu`, `*.pvtu` after you extract what you
   need, and keep total use under 40 GB.
5. **Accuracy is not negotiable.** A speed-up only counts if it reproduces a reference within the
   documented error. See §5.
6. **Repository.** Make your own git worktree off branch `codex/power-stage-120v-build`, write only
   under `validation-results/01-switching-parasitics/round18-speedup/`, commit there, do not push.
   Never `git stash` (the stash stack is shared across worktrees). Commit messages end with the
   repository's Co-Authored-By line.
7. **Evidence.** Every number in your report must be reproducible from a committed script or log.
   Say "estimate" when it is one, and "bound" only when it bounds.

## 4. What to investigate

### 4a. Reconstruct the history (read-only)

Build one table of every past solve from the remote logs: `~/temper-fem/r16/`, `~/temper-fem/r17/*`
(`campaign.log`, `*.out` with Hypre residual histories, `status.json`, `manifest-*.json`,
`/usr/bin/time` records written by `run_elmer.py`) and the round READMEs. For each solve record:
- mesh, tets and DOFs, ranks;
- iterations to 1e-8;
- wall time split into setup, Krylov and output;
- it/s, peak memory;
- whether it converged, restarted or crashed.

Note how iterations scale with tets, arch height and edge size. That table is your baseline.

### 4b. Profile the live job (passive)

On the running `ElmerSolver_mpi` ranks, sample without perturbing them: `perf top` / `perf record
-p <pid> -F 99` (or `py-spy`-style sampling if perf is unavailable; you have no sudo), `/proc/<pid>/status`,
`pidstat`, and memory bandwidth if counters are readable. Split each solve's wall time into:
- mesh reading and partitioning (`ElmerGrid`);
- assembly;
- Hypre AMS setup;
- Krylov iterations: matvec vs preconditioner apply vs orthogonalisation (GMRES(100) keeps 100
  vectors);
- VTU writing and the reciprocity post-processing.

Decide whether the solve is bound by compute, memory bandwidth or communication.

### 4c. Hypotheses to test (ranked by our current guess; your measurements decide)

1. **One matrix, four right-hand sides.** The four port solves on a mesh likely share the same
   system matrix and differ only in the source. Today each is a separate Elmer run (assembly + AMS
   setup + Krylov). Check whether ports enter only the RHS. If so, measure what re-use buys: one
   assembly and one AMS setup, a multi-RHS or block Krylov solve, or all four ports in one Elmer
   run. Also check whether a previous port's solution is a useful initial guess.
2. **Krylov method.** The system is symmetric (`Linear System Symmetric = True`) but the campaign
   uses GMRES(100) rather than PCG. Find out why (round 16), and test PCG+AMS on the same small
   mesh: iterations, wall time, memory (no 100-vector basis), and agreement.
3. **Stopping criterion.** Tolerance 1e-8 was chosen to keep solver error far below mesh error
   (round 17 §1). Track the port **energy** (the inductance) against the residual along the
   iteration history. If L converges to < 1e-5 relative long before the residual hits 1e-8, an
   energy-based or looser stop could cut iterations substantially. Show the error it would add.
4. **AMS / BoomerAMG settings beyond round 17's scan:**
   - coarsening (HMIS/PMIS, aggressive levels) and strong threshold (0.25 is a 2-D default; 0.5–0.7
     is typical in 3-D);
   - interpolation, smoother type and sweeps, cycle type. Types 13/14 crashed in Hypre setup
     because Elmer passes no Pi components; find out whether that is fixable.
   - Measure setup cost against iteration savings.
5. **Parallel configuration.** Try 6/8/10/12 ranks (and hybrid MPI+OpenMP if Hypre was built with
   OpenMP), process binding (`--bind-to core --map-by core`), and hyper-threads. The 5900X has two
   CCDs with separate L3; placement may matter. A memory-bound solve may run as fast on fewer ranks,
   which would let **two coarse solves run at once**.
6. **Mesh size:**
   - how tets split between copper, dielectric sub-layers (`--dz-max 0.25`), arch levels and graded
     air (`--air 10`, `--h-far 2.0`, `--band-pad`);
   - the crop converged by 20 mm and the air box changes L by +0.7 % (round 17), so what can be
     coarsened far from the loops with a measured effect below the mesh error?
7. **Campaign structure.** Are all eight cases per leg needed for the extrapolation recipe ("fine
   quad(1,2,3) + coarse [cubic − quad(1,2,3)] + crop correction")? Can some corrections be
   shared between legs or carried from a cheaper run? Can cases run concurrently within memory?
8. **Build and libraries.** Release build with conda's generic binaries. Would a native build of
   Hypre/Elmer (`-O3 -march=znver3`), a different BLAS, or a newer Hypre (or mixed-precision AMG)
   make a measurable difference? Estimate before building anything; a rebuild must not replace the
   install the chain uses (install to a new prefix).
9. **Anything else you find**, including whether a different formulation or solver package would
   pay off. Round 9 rejected Palace; round 11 sized the direct solve. Do not re-run settled
   history; cite it.

## 5. Accuracy guardrails (every candidate must pass)

- **Fixtures.** The two-port plate section must still give exactly L11 3.141593, L22 1.884956 and
  M 1.884956 nH (round 17 §3), with within-tet spread checks as in §5.
- **Board reference.** On a small board case with a known answer (for example a coarse native-19 leg
  B case already on the remote, `~/temper-fem/r17/b19c`, or a deliberately small crop you solve both
  ways), the candidate must reproduce every matrix entry to < 1e-4 relative (or explain why a looser
  bound is safe against the mesh error documented in FINDINGS M1), keep the matrix SPD, and pass
  `matrix_gate.py`.
- **Reciprocity.** The mutuals from B-field reciprocity must agree with an independent pair-solve
  energy check on at least one pair (the method in round 17).

## 6. Deliverables

In `validation-results/01-switching-parasitics/round18-speedup/` of your worktree, committed:
1. `README.md`: the history table (4a), the profile (4b), then each hypothesis with what you
   measured, the speed-up (measured, or estimated and labelled so) and the accuracy evidence. End
   with a **ranked recommendation list** with expected total wall-time saving.
2. A **proposed new chain**: what to run, in what order and configuration, and how long you expect
   it to take, as a script ready for the user to launch. Include whether to stop the current chain
   now, at the next case boundary, or let it finish, and why.
3. The scripts and logs behind every number (small meshes, fixture runs, perf captures, parsers).

Report back with a short summary: the biggest wins, the confidence in each, and anything that needs
the whole machine and hence the user's scheduling.
