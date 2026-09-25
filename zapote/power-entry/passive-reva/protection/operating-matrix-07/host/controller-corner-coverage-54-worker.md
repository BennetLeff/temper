# Controller-corner coverage audit

Date: 2026-09-21. This is a read-only audit of retained evidence. No SPICE
fixture was changed or run here, and no controller or silicon qualification is
claimed.

## What is already covered

The retained controller integration is a nominal, host-authored UCC28180
surrogate. `controller-integration-06/controller/functional.cir` and
`functional-checks.txt` exercise the model's UVLO enable/disable/recovery,
OVP set/hold/reset, VSENSE standby/recovery, ISENSE open-pin, ICOMP short,
cycle-latched PCL with leading-edge blanking and hold, EDR source current, and
SOC sink current. The retained result lists 15 functional assertions as
passing. `soft-start.cir`/`soft-start-checks.txt` adds a real compensation
network for SOC discharge, standby, and retry. `current-loop.cir` checks the
TI worked-point M1/M2 equations, pole, and oscillator. The integrated witness
and its 10 ns to 5 ns refinement check cover nominal coupled switching and
numerical repeatability.

The model source makes the coverage boundary explicit: `controller/ucc28180.inc`
is host-authored and hard-codes nominal UVLO (11.5/9.5 V), OVP (5.45/5.10 V),
PCL (-0.4 V), SOC (-0.285 V), and nominal logic delays. The receipt and
`controller/README.md` call this B2 nominal functional evidence; they leave
vendor fidelity, temperature/corner behavior, maximum timing, and physical
startup open. The old `host/luna-model-review.md` is superseded by
`host/review-disposition.md`; its ICOMP and SOC findings were addressed in the
retained nominal fixtures, while the ISENSE clamp gap remains separately
tracked.

## One useful remaining controller sensitivity

The only small controller-only test I can justify from the retained source is a
**published-threshold corner sensitivity** for UVLO and OVP. It is missing
from the current nominal fixture, whose hard-coded typical values cannot show
how the surrounding modeled power stage behaves when the controller threshold
moves within TI's stated electrical range. This is a model sensitivity result,
not a claim that the host surrogate reproduces those silicon limits.

The minimum future fixture would instantiate the same pin-forced functional
trace with threshold parameters set to the datasheet endpoints, retaining the
existing named windows and checker. Exercise these published ranges (as
separate one-at-a-time corners, not an invented simultaneous device corner):

* VCCON 10.8/12.1 V, VCCOFF 9.1/10.3 V, and hysteresis 1.6/2.0 V.
* VOVP_L 105/109%, VOVP_H 107/111%, and VOVP_H reset 100/104% of VREF.

For each endpoint, record the first rising enable or falling disable crossing,
the OVP discharge/inhibit crossing, and reset crossing, and assert only the
ordering required by the table and sections 8.3.3–8.3.4: UVLO must disable
below its off threshold and re-enable above its on threshold; OVP_H must
inhibit above its high threshold and permit recovery below its reset threshold;
OVP_L remains the discharge threshold. Do not add a propagation-time or
temperature limit: the TI table does not provide one for this fixture.

Authority is the retained TI UCC28180 RevD PDF
`clamp/datasheet-audit/UCC28180.pdf`, SHA-256
`e1e1588c6854b43742a667c76df26f06d9ac51231f0176c43b2a46b63c1b00be`:
electrical table 7.5 (PDF p. 6) and feature sections 8.3.3–8.3.4 (PDF
pp. 14–15). The result would establish only that the authored model's logic
ordering remains understood over those declared endpoint inputs. It would not
close the encrypted TI macro-model gap, silicon tolerance, delay, thermal,
ISENSE clamp, or hardware claims.

## Why no second test is justified

The retained evidence already exercises the small controller properties named
by `model-gap-closeout-12`: PCL/SOC, UVLO/OVP, blanking/latch retention, and
SOC/latch reset behavior. A new fixture for any of those at nominal values
would duplicate existing evidence. A maximum PCL-to-gate delay or a complete
temperature model cannot be derived from the cited TI data; the timing audit
explicitly leaves that bound null. Therefore the threshold-corner sensitivity
above is the sole concrete optional addition, and the campaign should keep the
current model-gap limitations explicit rather than treating nominal checks as
vendor qualification.
