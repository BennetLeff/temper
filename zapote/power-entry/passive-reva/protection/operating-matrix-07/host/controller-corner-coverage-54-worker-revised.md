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
trace with threshold parameters set to feasible points in the datasheet region,
retaining the existing named windows and checker. The UVLO values cannot be
combined as independent one-at-a-time endpoints: `VCCON - VCCOFF` must also
remain within 1.6–2.0 V. The feasible region is
`10.8 <= VCCON <= 12.1`, `9.1 <= VCCOFF <= 10.3`, and
`1.6 <= VCCON - VCCOFF <= 2.0` V. Its useful boundary vertices include
(10.8,9.1), (10.8,9.2), (11.1,9.1), (11.9,10.3), (12.1,10.3), and
(12.1,10.1) V. For the current `SW` representation, a scratch fixture would
map a chosen pair to `Vt=(VCCON+VCCOFF)/2` and
`Vh=(VCCON-VCCOFF)/2`; this does not alter the frozen source.

The OVP ranges must likewise remain a separately labelled sensitivity because
the retained table does not provide a joint-corner correlation for
`VOVP_L`, `VOVP_H`, and reset. A future fixture may sweep those endpoints one
at a time, but must not call arbitrary combinations a device corner:
VOVP_L 105/109%, VOVP_H 107/111%, and VOVP_H reset 100/104% of VREF.

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

## Correction: existing UVLO source waveform does not cover all UVLO corners

The original candidate endpoint wording above is intentionally superseded by
the feasible-region constraints. There is also a concrete limitation in the
retained pin stimulus: `controller-integration-06/controller/functional.cir:4`
holds VCC at 12.0 V during 31–60 µs and at 10.0 V during 61–90 µs. The
authored model declares 11.5/9.5 V at
`controller-integration-06/controller/ucc28180.inc:9-12`, and the checker calls
those windows enabled/retained at
`controller-integration-06/controller/checks.rs:57-60`.

At the published **maximum** VCCON of 12.1 V, a 12.0 V plateau is 0.1 V too
low to establish turn-on. At the published **minimum** VCCOFF of 9.1 V, a
10.0 V plateau is 0.9 V above the turn-off threshold, so it cannot establish
turn-off. The 9.0 V plateau at 91–120 µs is below every published VCCOFF and
the 15 V recovery plateau is above every published VCCON, so those two portions
are robust under the table values. This is an analytic observation about the
prescribed PWL source and threshold inequalities, not a silicon or supply
guarantee.

If the parent later elects to run the one optional sensitivity, the minimum
source-bound change is therefore a scratch pin fixture with VCC plateaus at
12.2 V and 9.0 V (0.1 V margins beyond the table), six feasible UVLO vertex
pairs above, and separate OVP endpoint runs. Expected authority remains TI
table 7.5 and sections 8.3.3–8.3.4. Without that source-stimulus change, an
extra run would merely restate the hard-coded nominal thresholds and add no
new model-bound; no such run was performed here.
