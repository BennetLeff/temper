# Headless shared-lib capture receipt

Build:

```
rustc output/shared-capture/src.rs -O \
  -L native=/opt/homebrew/opt/libngspice/lib -l dylib=ngspice \
  -o output/shared-capture/shared-capture
```

Run:

```
SPICE_SCRIPTS=/opt/homebrew/share/ngspice/scripts \
DYLD_LIBRARY_PATH=/opt/homebrew/opt/libngspice/lib \
output/shared-capture/shared-capture
```

The harness uses the documented `ngSpice_Init`, `ngSpice_Circ`,
`ngSpice_Command`, `bg_run`, `bg_halt`, `bg_resume`, `ngSpice_running`, and
callback APIs. On ngspice-45.2 the callback's `bool=false` is observed when
the background run starts and `bool=true` when it is stopped/ready (opposite
the callback parameter's label in one header); completion waits use both the
callback event counter and `ngSpice_running()` state, with the counter sampled
before each asynchronous command. The PWM fixture exports
`hold-paused.tsv` at the 10 us breakpoint and `hold-resumed.tsv` at 20 us;
both traces have strict increasing time. Rows: 10,259 paused and 20,511
resumed. Canonical `hold_checks.rs` passes on resumed output.

The independent RC fixture proves arbitrary `bg_halt` and resume: the run is
halted after the 5 ms request, `rc-paused.tsv` is strictly increasing, then
resumes to the 10 s endpoint (`rc-resumed.tsv`, 10,000,007 rows). The command
returns status 0, and the harness exits status 0 after controlled shutdown.

The shared library reports controlled exit status 0; `ngSpice_Command("quit")`
can return 1 because quit requests reset/detach. The harness treats that exact
controlled status-0 shutdown as success and propagates other command errors.

Hashes:

- `pwm-hold-capture.cir`: `034f88ae5f79fe2e62444aae4b9460816f4d5a69ce084290a55f5336b11db3ba`
- paused trace: `5dcbbd0abbe2b14592e01ec03e25db6cf7f15658fd049c37a23ba10e3235b4bf`
- resumed trace: `e2cf0eaf9e3b0ed10b29a82497e8f7c0c53fba2ca0030c88f9c4ebf79889cf0b`
- RC paused trace: `e8bb37d9a6e2dd3031f3237ad3537195e20e3d8e8ea1880752cbbc7c4a8b5556`
- RC resumed trace (gzip archive): `8b500cbae6b17cb2c469866edf2e70b7575c765a1bd2bab348782607cf003959` (uncompressed SHA; archive SHA `14264b6fbcc967964e67dc29e8c23d28c68e80205ef4ceb9fab93a375449c93c`)
- harness log (PWM): `838b75d6e345727bf66390964669c8f295ec6fc9866bad955987df4d83d096c6`
- harness log (RC halt): `a0b89256948317dd02f82051b44c4b86f522d9486a00bfd4a215c9fcc8136c99`
- harness source: `1ad64e6af4d99bbefcdececab7e930d7cfb5e9013e22f015ef07cb4519308b0f`

Bootstrap diagnostics retained: calling `ngSpice_nospinit()` on this Homebrew
shared library segfaulted, so the harness leaves startup initialization enabled
and supplies `SPICE_SCRIPTS`. Calling `codemodel` before circuit setup triggered
an `IS_SPARSE(Matrix)` assertion; the harness relies on the package `spinit`
loaded through `SPICE_SCRIPTS` instead. No electrical model files were edited.
