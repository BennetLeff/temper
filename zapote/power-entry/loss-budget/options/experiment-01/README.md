# MOSFET comparison experiment 01

This diagnostic evaluates the three parts in [PLAN.md](PLAN.md) through the
maintained Rust switching model. It does not change the source circuit or
participate in automatic part selection. [SOURCE-AUDIT.md](SOURCE-AUDIT.md)
records the independently checked device inputs and their applicability limits.

## Reproduce

From the repository root, with a shared Zapote Cargo target configured:

```sh
cargo build --manifest-path zapote/Cargo.toml --release --offline --locked \
  -p zapote-harness --bin zapote-pfc-mosfet-experiment
"$CARGO_TARGET_DIR/release/zapote-pfc-mosfet-experiment" \
  zapote/power-entry/shunt-repair/candidate/source-manifest.json > report.json
```

The CLI exits 2 for a numerically valid but physically INDETERMINATE experiment.
Retain stdout and stderr; an execution failure is not an empty successful result.

The independent audit uses standalone Rust and no production solver imports.
Compile it, then transport the exact report values into its tab-separated input:

```sh
rustc --edition=2021 -O \
  zapote/power-entry/loss-budget/options/experiment-01/independent-audit.rs \
  -o /tmp/pfc-independent-audit
jq -r '.scenarios[] | [.index, .input.line_rms_v,
  .simulation_inputs.switching_hz, .simulation_inputs.gate_bias_v,
  .simulation_inputs.rds_on_ohm, .simulation_inputs.qg_c,
  .simulation_inputs.qgd_c, .simulation_inputs.gate_plateau_v,
  .simulation_inputs.external_gate_r_ohm, .simulation_inputs.intrinsic_gate_r_ohm,
  .simulation_inputs.current_transfer_charge_c, .simulation_inputs.coss_energy_j,
  .turn_on_current_a, .turn_off_current_a, .switch_rms_a, .input_power_w,
  .overlap_w, .eoss_w, .conduction_w, .gate_network_w, .total_w] | @tsv' \
  report.json > audit-input.tsv
/tmp/pfc-independent-audit < audit-input.tsv > audit-result.json
```

`jq` transports fields; Rust owns the engineering calculation. The audit assumes
the contract's 400 V bus, 180 µH, 15 A RMS and 1.5/2 A driver peaks. The report's
own configuration validation binds those fields and the exact device inputs.
Analytical agreement establishes the conditional calculation only. It does
not establish the real gate waveform, switching energy or installed cooling.

## Evidence

The coordinator retains the experiment JSON, arithmetic audit, mutation tests,
runtime/source identities and review under `evidence/`. Results and a next-step
decision are in `RESULTS.md`. No measured semiconductor or thermal values are
filled in by this experiment.
