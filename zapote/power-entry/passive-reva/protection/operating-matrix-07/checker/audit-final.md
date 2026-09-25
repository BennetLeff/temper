# Final checker audit (read-only)

Audit scope: canonical checker and normalizer under
`/private/tmp/temper-pkgs-1-4/zapote/power-entry/passive-reva/protection/operating-matrix-07/checker/`, compared with
`/private/tmp/temper07-normal/output/final-cold-pwm-latch.cir` and its included
plant/protection files. No canonical files were changed.

## Findings

No channel or polarity defect was found. The circuit saves `v(acsrc)`,
`v(acn)`, and `i(Vac)`. `acn` has a 1 TΩ reference to ground and the source
is otherwise floating from HOT0, so `normalize.rs` correctly forms the
differential source voltage `v(acsrc)-v(acn)` and reverses ngspice's source
branch-current sign (`-i(Vac)`) to mean delivered current. The load is
`Rload load 0 {RLOAD}` and the normalizer's `i_load=v(load)/RLOAD` has the
correct sign. `v(vb)` and `v(vd)` are the two capacitor nodes.

No VDS/VGS reference defect was found for this fixture. `Vchannel` is an
ideal 0-V source from `channel_source` to ground and the MOS source is
`channel_source`; therefore saved `v(sw)` and `v(gate)` equal VDS and VGS
for this model. If that source is removed or moved in a future fixture, the
normalizer contract must change rather than silently reusing these columns.

No ARM/on semantic defect was found. `v(q)` is the protection latch output
and `v(en)` is the local driver-enable expression (`disable` low and AUX15
valid). The normalizer thresholds both at 2.5 V, so `armed` and `on` are
steady local state indicators, not PWM duty. This preserves low duty near
line zero. The checker requires each fraction to be at least 0.99 in the
settled window; a mostly-disabled loop is therefore a STOP. The source's
ARM PWL rises at 60 ms, so a final settled window at 0.5 s contains the
qualified state while startup remains visible to the peak checks.

No settled-window/peak masking defect was found. `--end-s` is mandatory and
must match the final trace time within 1 ns; 0.5 s is the `TSTOP` in
`final-cold-pwm-latch.cir`, and a 1 s run must be invoked with `--end-s 1`.
The checker rejects a trace that merely contains three cycles but has a
wrong/truncated declared endpoint. RMS, input/load power, PF, bus means and
drift use the final three exact 60-Hz cycles with interpolated boundaries.
VD/VB/VDS/VGS/IL peaks scan the complete startup-to-end trace, so a startup
overshoot cannot disappear from a passing settled-window screen.

The bus screen checks the settled-window minimum and maximum against the
389.615 V ±5% envelope, and cycle drift is max-minus-min over the last three
cycle means. A large periodic oscillation with a flat average therefore
cannot pass. Energy accounting reports the finite-window rate for the
declared 2240 µF/19.8 µF/180 µH storage and stops on unexplained negative
`Pin-Pout-dE/dt` beyond `max(1 W, 0.5% Pin)`.

## False-pass / false-rejection checks

The canonical Rust tests pass 11/11 checker tests and 2/2 normalizer tests:

```text
rustc --edition=2021 --test checker/operating_point_checker.rs -o /tmp/m07-checker-tests
/tmp/m07-checker-tests                         # 11 passed, 0 failed
rustc --edition=2021 --test checker/normalize.rs -o /tmp/m07-normalize-tests
/tmp/m07-normalize-tests                       # 2 passed, 0 failed
```

Those tests cover nonuniform analytic sine integration, wrong-current sign,
flat/off controller, mostly-off healthy state, persistent bus oscillation,
output power above input beyond storage, malformed/nonfinite/truncated input,
startup peak retention, and derived-energy overflow. The normalizer test
also verifies the floating AC differential, source-current polarity, load
current, and low-PWM-duty mapping to an enabled local state.

The currently staged deck is `final-cold-continuation.cir`, whose content
identity is
`9925f3da8b8891ca0348b540831be2a1b33a2f86814570a3fd283b031d9d469d`; it is a
corrected PWM-latch model running to a 1 s endpoint with a 500 ms checkpoint
and is still pending. The earlier 58.2898 ms controller-activation failure
belonged to an older model and is not evidence about this deck. There is no
accepted normal-point prefix yet. Fault scenarios are user-authorized but
remain dependent on first accepting a normal prefix. This is an explicit
pending-run boundary, not a reason to widen checker criteria.
