# Actual controller unknown-state regression

This test uses copied `controller-finite-edge-safe/ucc28180.inc` source. The
canonical experiment was not modified.

The test-only instrumentation changes the PWM data input from the controller's
known `five` rail to a new internal `test_unknown=2.5 V` source. It widens only
`UPWM_ADC` to `in_low=2`, `in_high=3`, so the PWM DFF data is genuinely
undefined. Raw comparator, oscillator reset, UVLO, VSENSE, VCOMP and ICOMP
stimuli remain known. VCC is 15 V, VSENSE is 3 V, ISENSE is 0 V, VCOMP is 3 V,
and ICOMP is 0.72 V, leaving fault, OVP and PCL masks permissive.

Two copies were run for 20 us with 1 ns nominal step:

| copy | PWM DAC `out_undef` | final `pwm_hold` | final gate |
|---|---:|---:|---:|
| safe candidate | 0 V | 0 V | 0 V |
| negative instrumented copy | 2.5 V | 2.5 V | 7.5 V |

Both simulations exited 0 with 20,078 finite, strictly increasing rows and
ended at 20 us. The XSPICE event output was recorded separately with `eprint`:

```text
xu.pwm_q: 0s, then Us at 0.572201 us,
0s at 7.747214 us, Us at 8.317714 us,
0s at 15.492728 us, Us at 16.063228 us
```

The maintained Rust checker in `check.rs` passes the safe trace and passes the
negative witness only when invoked in `unsafe` mode. Invoking the safe trace in
`unsafe` mode fails as expected. This verifies both the positive safe-off
baseline and the negative unsafe expectation.

The analog export intentionally excludes the digital event vector; the
exported analog channels have equal sampled lengths. The raw logs retain the
separate `eprint` output.


Host review strengthened the Rust checker to require initial samples, bounded
sample gaps and permissive fault masks in both modes, and to reject unknown
CLI modes. `host-results.json` records the safe trace passing the safety
check and the bad trace failing that same check at 7.5 V.
