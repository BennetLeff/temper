# Hardware-utilization audit for operating-matrix-07

Date: 2026-09-20. This is a read-only audit; no long simulation was started.

## Result

The current 20-minute cold-start run cannot use all 12 Apple M2 Pro cores
through ngspice's built-in OpenMP path. The installed Homebrew formula hashes to
`edc6aaf28197fe58f60644dae7cd9dfe9cabb5ed5164fdc3a190e044b17bf9fc` and passes
`--disable-openmp` in its configure arguments. The binary is ngspice 45.2,
compiled with KLU; its `-v` banner says so. The standard `spinit` still contains
`set num_threads=8`, but that setting has no effect in this OpenMP-disabled
build.

Even in an OpenMP-enabled build, the manual says parallel model evaluation is
implemented only for selected BSIM3/BSIM4 and B4SOI versions; all other
transistor models run without multithreading. This deck uses a level-1 `NMOS`
model (`STWMOS`), behavioral `ASRC` expressions, and XSPICE ADC/DFF/DAC
codemodels. Therefore rebuilding with OpenMP would not parallelize the dominant
device mix in this deck. The transient solve itself is time-ordered and cannot
be split across cores without changing the simulator algorithm.

The machine has 12 total cores (8 performance + 4 efficiency) and 32 GB RAM.
The retained `sample` capture of the long run shows the process in the serial
ngspice main thread, consistent with this build and deck. This does not prove
that no helper thread ever exists, but it does show no useful parallel model
evaluation was active at the captured point.

## What was measured already

The retained paired runtime experiment is the relevant local evidence:

* Sparse baseline: 8.482 s.
* KLU identical-model trial: 8.895 s.

KLU therefore did not improve this workload in the existing trial. The
experiment README explicitly keeps Sparse as the active solver and rejects the
trial as a speedup. KLU may still be worth retesting after a model change, but
there is no evidence that selecting it now will shorten the cold run or fix the
stall.

## Best use of the hardware

1. Keep one canonical cold-start run on the validated Sparse configuration;
   this preserves comparability and avoids treating a solver change as a model
   fix.
2. Once that run reaches a valid settled operating point, run independent
   mains/load matrix points as separate ngspice processes, capped at the number
   of physical cores and with bounded output. This is the reliable way to use
   the M2 Pro here: process-level parallelism across independent cases, not
   pretending one transient can be parallelized.
3. Do not add `set num_threads=8` as a claimed optimization unless ngspice is
   rebuilt with OpenMP and the rebuilt binary is identified. For this deck's
   MOS1/ASRC/XSPICE composition, such a rebuild is expected to give little or
   no benefit and would change the simulator provenance.
4. Keep the KLU result as a recorded negative control. A solver swap should be
   a paired, byte-identified experiment, not an unqualified production change.

## Primary source basis

The ngspice 45 manual states that only selected BSIM3/BSIM4/B4SOI model
versions have OpenMP model evaluation and that all other transistor models run
without multithreading (manual §12.10.4, pp. 366–367; lines 13356–13377 in the
web text). It also says only device evaluation is parallelized, while matrix
parallelization is difficult for Sparse and KLU (manual §12.10.3, p. 366;
lines 13351–13355 and 13301–13304). The manual documents `num_threads` and its
default only when compiled with OpenMP (§12.5, p. 361; lines 13139–13142 and
§12.10.4, lines 13362–13368), and describes KLU as a solver choice rather than
an automatic multithreading switch (§11.1.1, p. 313; lines 11642–11646).

Source: [ngspice 45 manual](https://ngspice.sourceforge.io/docs/ngspice-45-manual.pdf).

