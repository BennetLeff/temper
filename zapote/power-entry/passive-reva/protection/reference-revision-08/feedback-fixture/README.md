# Experimental VD-vs-baseline-VB feedback fixture

This is one small A/B controller-feedback test for reference revision 08. It
uses two copies of the exact unchanged host-authored `UCC28180_FN` surrogate.
The old copy senses the VB divider and the candidate copy senses the VD divider;
all other pins are forced to VCC=15 V, VCOMP=3 V, ICOMP=1 V, and ISENSE=-0.1 V.
Each divider is 1 Mohm / 13 kohm / 680 pF. Both banks start at 390 V. VD alone
steps to 450 V and returns, then VB alone steps to 450 V and returns.

The run is bounded to 500 us with a 20 ns maximum timestep. The Rust checker
requires a finite, strictly increasing trace ending at 500 us, baseline PWM
activity, each isolated OVP assertion and gate inhibit, recovery, and the
absence of candidate-controller OVP during the VB-only excursion. The retained
compressed trace is `feedback.tsv.gz` (the checker accepts its decompressed
stream on stdin).

## Reproduction and result

Solver command (the only solver invocation):

```text
python3 zapote/power-entry/passive-reva/protection/operating-matrix-07/host/harness-lifecycle-144/command_guard.py run --timeout 60 --receipt /private/tmp/temper-pkgs-1-4/zapote/power-entry/passive-reva/protection/reference-revision-08/feedback-fixture/ngspice.receipt.json --cwd /private/tmp/temper-pkgs-1-4/zapote/power-entry/passive-reva/protection/reference-revision-08/feedback-fixture -- /opt/homebrew/bin/ngspice -b feedback.cir
```

Tool: `/opt/homebrew/bin/ngspice`, version 45.2, KLU Direct Linear Solver;
the guard receipt records a completed run with return code 0, a 60 s deadline,
and 1.320745 s wall runtime. The circuit uses ngspice's `method=gear` option,
as in the supplied controller functional fixture; this is a functional
behavior check rather than a numerical comparison against a full baseline.
The checker was built without Cargo and run as:

```text
rustc check.rs -O -o check
gzip -dc feedback.tsv.gz | ./check -
```

Recorded checker result: 35,138 rows ending at 500.000 us; 10 baseline PWM
rising gate pulses on each controller; VD-only OVP asserted only on the
candidate and inhibited only its gate; both recovered; VB-only OVP asserted
only on the old controller while the candidate stayed clear and kept pulsing;
both recovered at the end.

## Source and artifact hashes

SHA-256 (the include is copied byte-for-byte from
`operating-matrix-07/accepted-baseline-11/ucc28180-pwm-latch.inc`):

```text
caa87dda7e61e319fd5f9fbf02b0a9304224b244e846061fda68ea9280a35d6e  feedback.cir
2e885755aad4d03fb9c06d7c556faf23ad0ae7922f581d56752db78933b97251  ucc28180-pwm-latch.inc
d8fe820918f498b9af1298cad0d10d980a5d123e610e6a8d487200759573dbaf  check.rs
537c04a96aefdd9c59bf30341c7ec1755c30ff12253c3313f728dcc3a111c888  feedback.tsv.gz
c67fb1e33e0a4331c4580cea3e14eff026f00dd34d39cdc0be9e4aaf82bbc9ae  ngspice.receipt.json
```

The donor example used for fixture shape is
`operating-matrix-07/controller-latched/functional.cir` (SHA-256
`d1a2cbf67249b62b961399c859193683b3c850a0d228974b71295ad7a474d6e5`); it is
not modified. This fixture is labelled experimental VD-vs-baseline-VB and
makes no source07 authority or integration claim.

This is an authored-model functional test only. It does not qualify
closed-loop regulation, startup sequencing, external detector behavior,
physical component margins, or board-level transient performance. It does not
change the frozen model, add an ideal source trip, or alter F2 actuation.
