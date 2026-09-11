# LMR51430 datasheet model — verified development replay

The user selected datasheet-based modeling with Luna while retaining
LMR51430XDDCR. Luna built the [model package](../../../engineering/models/lmr51430-datasheet/README.md)
and [native exercise](../../../engineering/scenarios/lmr51430-datasheet/README.md).
The host ran the final three-case quick exercise with ngspice 45.2 on September
10, 2026. It exited 0. This bundle preserves the executed model, parameter
ledger, source snapshots, decks, logs and binary raw waveforms.

| Development case | Observed output | Meaning |
| --- | --- | --- |
| 15 V, 6.6 Ω load, nominal capacitors and 5.6 µH | Mean 3.315226 V; 3.307127–3.320963 V during 15–19 ms | Nominal regulation through the external divider; nominal target from divider arithmetic is 3.314932 V. |
| 0.05 → 0.5 → 0.05 A, 3 ms pulse | Minimum 2.880473 V; maximum 3.335566 V during the recorded response windows | A transient concern in this model. The dip is below the 3.135 V rail target, but the assumed compensation prevents attributing it directly to the real IC. |
| 4.54 µF input / 22.01 µF output / 4.48 µH, 6.6 Ω load | Mean 3.305104 V; 3.269143–3.335965 V during 15–19 ms | Sensitivity to reduced assumed capacitance and inductance. The 66.822 mV span is unfiltered; it is not the adopted bandwidth-limited ripple measurement. |

The host independently checked all 10,891,866 waveform rows for finite values,
strictly increasing time and complete 20 ms captures. Model, ledger, simulator
version, deck, log and rawfile hashes match the [manifest](manifest.json).
The model and runner source snapshots match the current package. The load
waveform actually reaches 0.05, 0.5 and 0.05 A; interpolated rise and fall
rates are both 0.1 A/µs. Input and output energies are finite and positive,
with input energy exceeding delivered output energy. Those energy checks
exercise the power path; the artificial snubber and omitted device losses
prevent an efficiency claim.

[Verification details](verification.json) also record passing shell syntax and
ShellCheck checks, refusal to overwrite an existing output (exit 2), and refusal
to run with a missing simulator (exit 2). Earlier partial authoring runs are
not evidence for this final package. The short reference-override probe described
in the model README establishes parameter behavior only, not settled regulation.

This is usable development evidence. No qualified-model approval was created,
no scored trial slot was consumed, and no powered hardware test was performed.
The full ten-case development sweep and adopted thirteen-case qualification
protocol were not run here. Startup uses a resistive load, and the development
load pulse is shorter than the adopted 10 ms pulse/100 ms hold protocol.

Use these findings to prioritize comparison of load response and effective
capacitance with independent circuit evidence or bench measurements. Do not tune
the unpublished compensation merely to satisfy the rail target, and do not
replace the regulator on the basis of this approximate model's dip alone.

Reproduce from the feature worktree with a fresh output directory:

```sh
LMR_QUICK=1 harness-lab/engineering/scenarios/lmr51430-datasheet/run_exercise.sh /tmp/lmr-model-new-run
```

The source snapshot records are retained byte-for-byte and their `sha256.txt`
files name the original temporary collection paths. The manifest and executed
deck includes use bundle-relative paths. Binary `.raw` files are retained locally
but Git-ignored; a checkout alone will need a fresh replay to recover them.
