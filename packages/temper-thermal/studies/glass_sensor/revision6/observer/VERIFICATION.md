# R6 observer verification

Status: **SYNTHETIC_ESTIMATOR_STUDY / physical NOT_RUN**.

- `rustfmt --check main.rs`: PASS.
- Standalone `rustc --edition=2021 -O -D warnings`: PASS.
- Standalone `clippy-driver --edition=2021 -O -D warnings`: PASS.
- 11 Rust tests: PASS. Equal-temperature equilibrium, internal-flow cancellation, discrete energy conservation, full-scenario time refinement, authorization rejection, stale trace behavior, fresh-frozen blindness, warm-detach blindness, contact/rate non-identifiability, reduced-network DC inversion and positive physical constants.
- All nine scenarios execute all four methods at the same 2,400 sample times: 36 comparison rows. Traces save 17,280 data rows at 250 ms intervals.
- Two actual isolated source mutants were compiled and run. Forcing the contact/freshness predicate true fails `stale_and_invalid_contact_rejected`; erasing the simulated contact-loss injection fails `warm_detach_remains_blind_if_gate_lies`. The scripts verify the named assertion failure, rather than treating a compiler failure as a successful negative test. See `results/mutation-*.txt`.
- `run.sh` stops on test failure before compiling clippy/running model output. No pipe hides the test process exit status. This control flow is directly visible; a separate injected runner-exit test was not performed here.

The initial test compile required an explicit f64 annotation in the identifiability test. The first mutation-harness attempt incorrectly escaped an awk replacement and failed to compile; it was corrected to replace the full line, then both mutants produced the recorded assertion failures. Those development errors are not physics results.

This is characterization, not a successful optimization claim. The bank's worse held-out results and the large startup/fault errors remain in the output. Metrics include the entire trace; no nominal-only pass rate or probability of fault coverage is reported. Numerical tests establish conservation/convergence and intended fault demonstrations, not actual sensor properties, accurate measurement locations, hardware isolation or controller safety.
