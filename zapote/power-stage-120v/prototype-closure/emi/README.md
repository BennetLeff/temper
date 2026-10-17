# Pinned EMI evidence intake

Authoritative D22 source: `codex/ps-r17-d22` at `7d1c97b92c0ed42be1c28a32d4ccaadd512d2238`, based on `fda5ab9ece24ef1ee6f2317604c5ca73367d5201`. This directory contains compact verbatim JSON evidence and a thin replay runner. Numerical methods remain in the pinned source; there is no new Python numerical source of truth.

[Readiness result and installation gates](../../../../docs/research/mit-product-design/readiness/power/emi-closure/README.md) distinguish a converged diagnostic model from an approved installed filter.

Run from the repository root with the published source checkout available read-only:

```sh
sh zapote/power-stage-120v/prototype-closure/emi/verify-intake.sh \
  /Users/bennet/.codex/worktrees/ps-r17-d22/temper \
  /Users/bennet/Desktop/temper/worktrees/mit-product-guidance/output/temper-prototype-closure/emi
```

The runner requires existing NumPy, ngspice and the source checkout, checks their evidence identities, replays 32 archived nonlinear captures, checks spectra archives and freshly runs 12 AC decks. It writes only the specified output directory and temporary FFT files. `TEMPER_PYTHON` can select an existing interpreter; no install or shared build is performed. Output includes raw compressed AC waves, decks, logs, upstream test log and `verification.json`. The copied receipt in the readiness directory records the completed run. No newly simulated nonlinear transient or hardware measurement is claimed.

Exercise the fail-closed intake check with the same two arguments using `test-intake.sh`. It changes a temporary copied input and provenance pin, requires rejection before simulation, and verifies that seeded PASS receipts become INCOMPLETE on copied-input, optimized-Python and wrong-HEAD failures. It also confirms that a forbidden source-checkout output is rejected without writing, even with optimization enabled.
