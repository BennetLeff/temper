# Event-aware normal-metrics oracle fixtures

This folder is a small, independent oracle for a future event-aware normal-metrics evaluator. It is deliberately separate from the full operating-matrix simulations and does not change the original checker or any acceptance policy.

## Fixture contract

`generate.rs` writes an exact 12-column TSV with this immutable header:

```
time_s v_ac_v i_ac_a v_load_v i_load_a v_b_v i_l_a v_d_v v_ds_v v_gs_v armed on
```

(The serialized files use tabs.) It emits samples `k = 0..100000` at `t = k * 5e-7 s`, covering `0..0.05 s` with strictly positive 500 ns steps. Numeric fields use 17-significant-digit scientific notation so decoded f64 values round-trip; the final sample uses the literal `0.05` to satisfy the checker endpoint contract. The source waveform is `v_ac = 170 sin(2*pi*60*t)` V and `i_ac = 5 sin(2*pi*60*t)` A, so the known RMS values are 120.208153 V and 3.535534 A, in-phase real input power is 425 W, and PF is 1. The load is `400 V * 1.0625 A = 425 W` at every row. Other nominal values are `v_b=389.615 V`, `i_l=4 A`, `v_d=390 V`, `v_ds=20 V`, `v_gs=15 V`, `armed=1`, `on=1`.

`base.tsv.gz` is the strictly increasing oracle. It was generated with `rustc --edition=2021 -D warnings generate.rs -o generate`, compressed with `gzip -n`, and checked by the unchanged checker binary below with `--end-s .05`. The expected checker stdout is retained verbatim in `base-checker.stdout`; stderr is empty and the process exits 0.

`assert.rs` decodes the compressed rows and compares timestamp bit patterns. Its retained `timestamp-assertions.txt` receipt proves that both inserted boundary rows decode to the exact `0.05 - 1/60` f64 and that the base endpoint decodes to the exact `0.05` f64; this catches decimal serialization that only looks equal at 12 digits.

The three equal-time fixtures intentionally exercise semantics that the original checker rejects before producing metrics:

* `equal_time_exact.tsv.gz` repeats the row at `t=0.025 s` unchanged. The original checker rejects line 50003 with `time not strictly increasing`.
* `equal_time_stress_peak.tsv.gz` writes a same-time `v_ds=20 -> 700 -> 20 V` group at the interior timestamp `t=0.025 s`. An event-aware evaluator should preserve the instantaneous 700 V stress peak while integrating over the zero-duration group; the original checker rejects line 50003 before evaluating it.
* `equal_time_cycle_boundary.tsv.gz` inserts the exact `f64` expression `t=0.05 - 1/60` (the final 60-Hz cycle boundary), writes `v_b=v_d=405 V`, then a same-time row returns to the nominal values. This row is between the surrounding 500-ns grid samples; it is an explicit cycle-boundary changed-energy ordering probe. The original checker rejects line 66670 before evaluating it.

The duplicate rows are deliberate test inputs, not an argument that equal-time output is valid for the existing strict checker. No full simulation, device qualification, or product-compliance claim is attached to these files.

## Reproduction and source binding

The immutable checker source is `../../checker/operating_point_checker.rs` (SHA-256 `845dde5ba649f8076c238b590f7fc11490e6a0a96bdbd4998f759429699c1d54`). The checker executable used for this receipt is `/private/tmp/matrix07-checker` (SHA-256 `24c95bea81b44a3d5038a32552297afed17547fcd1b3ddcfd99434e84638b85c`). Commands were:

```
rustc --edition=2021 -D warnings generate.rs -o generate
./generate .
gzip -n -f base.tsv equal_time_exact.tsv equal_time_stress_peak.tsv equal_time_cycle_boundary.tsv
rustc --edition=2021 -D warnings assert.rs -o assert
gzip -dc equal_time_cycle_boundary.tsv.gz | sed -n '66669,66670p' | ./assert boundary
gzip -dc base.tsv.gz | tail -1 | ./assert endpoint
gzip -dc base.tsv.gz | /private/tmp/matrix07-checker --end-s .05 > base-checker.stdout 2> base-checker.stderr
gzip -dc equal_time_exact.tsv.gz | /private/tmp/matrix07-checker --end-s .05 > equal_time_exact-checker.stdout 2> equal_time_exact-checker.stderr
gzip -dc equal_time_stress_peak.tsv.gz | /private/tmp/matrix07-checker --end-s .05 > equal_time_stress_peak-checker.stdout 2> equal_time_stress_peak-checker.stderr
gzip -dc equal_time_cycle_boundary.tsv.gz | /private/tmp/matrix07-checker --end-s .05 > equal_time_cycle_boundary-checker.stdout 2> equal_time_cycle_boundary-checker.stderr
```

Variant command exit status is retained in the corresponding `*-checker.exit` file. The expected exits are 1 for all three variants and 0 for the base. `generate` itself is retained only as a reproducibility convenience; `generate.rs` is the source of truth.

## Base checker oracle

The base output is:

```
window_s=0.000000000e0..5.000000000e-2 vrms=120.208153 irms=3.535534 real_input_power_w=425.000000 pf=1.000000
load_power_w=425.000000 vb_mean_v=389.615000 vb_min_v=389.615000 vb_max_v=389.615000 vb_ripple_pp_v=0.000000 vb_cycle_means_v=[389.6149999997868, 389.61499999975524, 389.6149999997208] vb_cycle_drift=0.000000
energy_delta_rate_w=0.000000 energy_balance_pin_pout_de_w=0.000000
il_peak_a=4.000000 vd_peak_v=390.000000 vb_peak_v=389.615000 vds_peak_v=20.000000 vgs_abs_peak_v=15.000000 armed_fraction=1.000000 on_fraction=1.000000
engineering_screen=PASS
qualification=NOT_CLAIMED (loss estimate/screen do not establish thermal qualification or product compliance)
```

The equal-time fixtures must remain useful even if a new evaluator rejects them: their original-checker rejection is an explicit baseline, while their content gives deterministic duplicate, instantaneous-peak, and changed-energy-group cases for event-aware tests.
