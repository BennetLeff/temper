# Revised controller with explicit PWM latch

This is the current candidate after the long startup investigation. The
controller model hash is in `model-input.json`; test results and wall times
are in `results.json`. Six independent host fixtures pass: current-loop
gain/pole, 15 functional assertions, soft-start/SOC/retry, PWM timing,
intra-cycle PWM hold/reset, and the older short warm fault witness.

The latch is grounded in TI UCC28180 section 8.2's functional block diagram.
The preceding direct-comparator model fails `pwm-hold.cir`: it withdraws the
pulse when ICOMP rises within the same oscillator cycle. The new latch holds
the pulse until reset, with a separate PCL latch still able to interrupt it.
That proves the implemented state behavior, not yet that a full cold-start
trace is trustworthy or that the real converter is qualified.

Comment erratum in the retained model snapshot: the prose above
`Bicomp_reset` still mentions UVLO among ICOMP reset causes. The expression
itself correctly contains only the VSENSE/ISENSE fault conditions and OVP;
the source review in `../host/controller-model-review.md` explains that
distinction. Keep this snapshot byte-identical to the tested input.

The PWM analog/digital interfaces are explicit. Their nominal simulation
delay is ADC 1 ns + DFF clock 1 ns / rise 1 ps + half of a 1 ns DAC rise,
or 2.501 ns at the gate-logic threshold. `pwm_checks.rs` accounts for those
declared model parameters in its expected edge and retains the original
3 ns numerical tolerance. These are not TI silicon propagation bounds.
The ngspice ADC bridge default is 1 ns, as discussed in the
[ngspice developer response](https://sourceforge.net/p/ngspice/discussion/133842/thread/3c16b72459/);
the new model declares it instead of relying on implicit bridges.

The older warm fixture still triggers its detector and holds the external
latch off. It starts from a precharged example and does not satisfy the
required fault-from-settled-operation campaign.

Build the three Rust checkers here with `rustc --edition=2021 -O`; run each
SPICE fixture and its matching checker as in `../controller-probes/README.md`.
Use this directory's `pwm_checks.rs` for this delayed latch model. Large
completed traces may be losslessly stored as `.tsv.gz`; decompress to the
original filename before checking. `../host/fixture-archive-manifest.json`
records verified uncompressed hashes. Historical model versions and failed
checks remain separately retained.
