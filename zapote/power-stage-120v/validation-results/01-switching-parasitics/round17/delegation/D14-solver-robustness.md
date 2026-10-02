# D-14: ngspice robustness for the D2 deck (the aborts)

**Read [README.md](README.md) first (ground rules, board facts).**

## Why it matters

Some D2 runs abort with "timestep too small" at node `bus`: 10 of 680 in the
best-matrix grid (`d2/results/grid-best/`: S3 280 V direction 1, 5 A at ESL
20 nH and 10 A at 1.06 nH, at every dead time; one at t = 2 µs, one at
t = 2 ps), and 11 of 32 of D-6's 0.1 ns timestep-refinement runs. Neighbouring
parameter values converge smoothly, so these look like solver failures, but
indeterminate cases weaken every grid and timestep convergence is not
established.

## Task

1. Reproduce the aborts (grid-best cases and D-6's `refine.py` set).
2. Find the cause: initial operating point (the t = 2 ps abort), the switching
   edge at t = 2 µs, the B-source driver model in `d2/leg_matrix.cir`, the
   coupled-inductor K matrix, the vendor model, or tolerances in
   `validation-plan/sim-kit/common/options.inc`.
3. Propose the smallest change that makes them converge **without changing
   the physics**: solver options (method, reltol/abstol/vntol/chgtol, gmin,
   itl limits, `.ic`/UIC strategy, maximum step), or a numerically equivalent
   deck formulation. A change that alters results is not acceptable.
4. Qualify it: rerun a representative set (all decision cases + every
   aborting case + D-6's refinement set) with old and new settings; where
   both converge, results must agree to a tolerance you justify (e.g. off-gate
   within 0.01 V, VDS within 0.5 %); show timestep convergence (0.2 → 0.1 →
   0.05 ns) for the decision cases under the new settings.

## Deliverable

`round17/delegation/out-D14/README.md`: one-line answer (cause, fix,
evidence), the qualified options/deck change as a **proposed** file in
`out-D14/` (do not edit `common/options.inc` or the D2 deck in place), the
comparison and convergence tables, scripts and raw outputs (no vendor
library).

## Acceptance

Every former abort either converges under the proposal or is explained;
no converged result moves beyond the stated tolerance; timestep convergence
demonstrated for the decision cases.
