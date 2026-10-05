# R7 coupon calibration and holdout preparation

**Hardware NOT_RUN.** This adapter prepares the existing bench evaluator for the R7 coupon comparison. It imports pinned `bench_validation/bench.rs` verbatim inside a temporary Rust module. It does not implement another fit algorithm, identify individual thermal resistances, control equipment or calibrate firmware.

Run `./run.sh` for the synthetic checks. To evaluate future files, run `./run.sh fit.csv fit.meta holdout.csv holdout.meta` with absolute data paths. The underlying raw schema remains `bench_validation/templates/samples.csv`; `templates/run.meta` contains the extra R7 identity fields and deliberately fails until completed with real acquisition evidence. Standalone rustc/rustfmt/clippy-driver and POSIX tools suffice. No Cargo or installed extensions are touched.

## What changed

- Require different **pan identities** for the fit/holdout pair, alongside different run IDs, raw origins and raw byte hashes. The existing evaluator allowed another run on the same pan.
- Require matching cartridge, full geometry/BOM SHA256, bond batch and join-process revision. Reassembly or changed joins require new identities and requalification rather than mixing configurations.
- Keep the existing bounded first-order fit and its global/dynamic holdout residual checks. It identifies an effective time constant, gain and offset for this condition; it cannot separately identify contact conductance, chip mass and bond conductivity.
- Report a separate proposed **strict <2°C and <2 s** screen over a declared 40–250°C plateau. Temperature is guarded by `abs(error)+2*u_error`; response by `t90_pan+2*u_time`. Values overlapping the limit remain INDETERMINATE. The reference transition plus lag bound must be ≤0.2 s (proposed 10% of the response target). The old 3 s / 5°C high-temperature screens are not exported.
- Preserve stable-plateau, baseline, excitation, continuity, contact, provenance and uncertainty checks. Model-fit success does not make the thermal screen pass, and neither is a release authorization.

The displayed metrics from the pinned reducer have six decimal places. Screen comparisons include a 0.000001-unit rounding allowance; this avoids claiming a marginal pass from formatting. It is not a physical uncertainty model.

## Synthetic evidence

The unchanged independent closed-form generator supplies a 1.5 s, gain0.98 plant and a separate higher-temperature holdout. The adapter recovers tau≈1.503 s, gain≈0.9798; holdout residual RMSE≈0.052°C and dynamic maximum≈0.222°C. That is a successful surrogate fit, while the same synthetic sensor has about −2.700°C steady error and 3.753 s pan-step response: both proposed R7 screens fail. This explicitly demonstrates the distinction.

Weaker-contact and hidden-dynamics fixtures reject transfer. Same-pan metadata and empty physical templates reject import. The 27 tests comprise 17 inherited bench tests and 10 adapter tests. Three additional entry-point cases independently reject reused run IDs, raw origins and identical CSV bytes. A temporary parameterized copy of the pinned Rust analytic generator (tau 0.5 s, gain 1) produces a separate software-only passing case; its guarded error and response screens both pass while physical_validation remains NOT_RUN. This is a branch-coverage fixture, not a prediction for an R7 cartridge. The fixture geometry/BOM hashes made of repeated `a`/`b` digits are intentionally synthetic identity tokens, never real CAD evidence.

## Limits of the identity gate

Hash syntax and equality are checked here; the caller must verify that geometry/BOM digests actually refer to the built article and attach the source files. Software cannot authenticate a certificate, pan ID, measurement origin or independent contact observation. The adapter compares one fit/holdout pair, not a whole campaign ledger: review `TEST_MATRIX.md` before acquisition and keep every holdout pan out of every fit used for its evaluation. Changing a pan label does not create independence.

The old bench metadata's `approved_temperature_max_c` records an external review limit; the executable does not confer approval. No 250°C test is enabled by a chip rating or by synthetic metadata. Current cartridge seals, joins, insulation and fixture limits remain unresolved.

No model is transferred to firmware. The fit uses measured pan temperature as an input to predict the RTD; it is a forward surrogate validation, **not blind estimation of unknown pan temperature**. Evaluate any eventual inverse/lead estimator on the same frozen holdout data separately.
