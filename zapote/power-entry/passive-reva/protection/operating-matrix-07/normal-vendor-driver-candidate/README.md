# Full-plant UCC27511A candidate (startup rejected)

## Subsequent host-tracked result

The full run in `tracked/run/` stopped after 292.260 wall seconds at
97.345625 ms of the requested 500 ms. ngspice reported a timestep-too-small
failure at `e.xdriver.e_u1_u1_e1#branch`. The producer and gzip both exited
zero; those transport statuses do not mean the analysis completed. Independent
inspection found 4,353,208 finite, strictly increasing rows, and the unchanged
normal checker rejected the incomplete endpoint. The trace, source hashes,
stop metadata and checker report are retained. No operating point was accepted.

This later run uses the dedicated first-invalid tracker in `tracked/progress.rs`,
with sixteen extra internal signals and explicit PSpice compatibility. Its
source/binary provenance is in `tracked/run/inputs.json`. The original smoke
description below refers to the earlier tracker and remains diagnostic only.

This directory is a bounded candidate derived from the normal-tracked cold
deck. It is a comparison artifact for the driver surrogate; it is not an
acceptance result, a hardware qualification, or an equivalence claim.

The following normal-tracked files were copied byte-for-byte:

* `cold.cir` (`eaa5c20900fd8a5d577e629e3f678378690b6e427098303cffe6aa41d54447d2`);
* `ucc28180-pwm-latch.inc` (`2e885755aad4d03fb9c06d7c556faf23ad0ae7922f581d56752db78933b97251`);
* `standby.inc` (`94d995d17a85ef932fe511bb2adbee02a1cd3fd1c88604b16d6b6929b31a50eb`);
* `clamp.inc` (`96cd8d6bfd3870b22403c39437ef2625f0a930f9e06632adcebbc45b61b9dcde`).

`protection.inc` retains the normal-tracked disable FET, PWM divider,
`Rgs`, `Ben` monitor, and `Csmallgs`/`Csmallgd`/`Csmallds` values. Only the
authored surrogate block (`Bdriver_req`, `Rdriver_delay`, `Cdriver_delay`,
`Rdriver`, and `Rgate`) is replaced with the unchanged TI UCC27511A model.
The model is copied locally at `vendor/UCC27511A.lib`, byte-identical to the
retained f2-shutdown-04 vendor source (SHA-256
`eb78c0ce0d9cf2dd5bbc5f937bbfc6cc38c95215e035feaeb3950672e8c05c6d`). Its
SPICE order is `INM INP VDD GND OUTH OUTL`, so the candidate instantiates
`Xdriver disable pwm_input aux15 0 outh outl UCC27511A` and uses separate
`10 Ω` `OUTH` and `OUTL` paths into the original gate node. This is the same
split-output topology exercised by the small vendor fixture. It differs from
the physical KiCad pin-number order and from the surrogate's single controlled
source plus one `10 Ω` gate resistor.

The copied tracker `progress.rs` is otherwise unchanged from the required
normal-tracked source (`f063aad3972d184853d49d6240419221117f8eba4a69d811dbdd53b89caaf672`).
It has one dedicated-candidate addition, `command("set ngbehavior=ps")`,
immediately before `ngSpice_Circ`. The resulting candidate source hash is
`2ed26fb7f78daad7fbb181d99bfe0e6e9666c12d80a70a070f393c8223d6a1dd`, and its
unique smoke binary is `progress-vendor-driver` (SHA-256
`27d77a57d338fd80d44151f900aa8c16f2561d9dbd94ccea1015b72283cfbefe`).

The bounded command was:

```sh
rustc --edition=2021 -O progress.rs -L /opt/homebrew/lib -l ngspice \
  -o progress-vendor-driver
SPICE_SCRIPTS=/opt/homebrew/Cellar/ngspice/45.2/share/ngspice/scripts \
DYLD_LIBRARY_PATH=/opt/homebrew/opt/libngspice/lib \
  ./progress-vendor-driver cold.cir 2 0.5 trace.tsv > run.log 2>&1
```

This two-second wall smoke advanced to `7.83040100760039846e-3 s` of
simulation and exported 45,680 trace rows. A separate finite-trace check
confirmed all 15 columns are finite, rows are nondecreasing in time, and the
largest sampled time gap is `5.000000000000664e-7 s`. The run stopped at its
requested wall limit and therefore is diagnostic only; the nominal 0.5 s
endpoint was not reached. The later full-run attempt is recorded above.
