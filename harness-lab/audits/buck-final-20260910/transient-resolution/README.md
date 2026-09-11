# LMR51430 load-step transient resolution

Date: 2026-09-10. This is bounded model-development evidence for the
existing `LMR51430XDDCR`; it is not a hardware qualification or a transient
requirement decision.

## Question and method

The retained 20 ms exercise reported a 2.880473 V minimum during a 0.05 to
0.5 A, 0.1 A/us, 3 ms pulse. I replayed the exact stimulus with the frozen
model (`62d3bda599e7f7a301b9cc7115e305d33e48edb07957e7f5602c19b92956e096`)
and ngspice 45.2 (`/opt/homebrew/bin/ngspice -n -b`). To keep the diagnostic
bounded, these are 11 ms captures with the same 1 ms VIN ramp and pulse
timings; the post-step window ends at 11 ms. Each deck saves output, FB,
switch node, inductor current, and internal model command/reference nodes.
The exact decks, logs, binary rawfiles, copied provenance ledger, and hashes
are retained here; `waveform.raw` files are large and are intentionally
artifact evidence rather than qualification data.

## Results

| Case | COUT | KP | VOUT minimum | VOUT maximum | command peak | FB minimum | SW range | inductor peak |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| base | 44 uF | 5 A/V | 2.880473 V @ 6.136 ms | 3.335566 V | 0.945961 A | 0.521363 V | -0.232 to 14.999 V | 0.991037 A |
| lower KP | 44 uF | 2 A/V | 2.572724 V @ 6.174 ms | 3.337273 V | 0.980101 A | 0.465661 V | -0.253 to 14.999 V | 1.028253 A |
| lower COUT | 22 uF | 5 A/V | 2.800349 V @ 6.082 ms | 3.355074 V | — | — | — | — |
| higher COUT | 88 uF | 5 A/V | 2.934005 V @ 6.222 ms | 3.325888 V | — | — | — | — |

The load measurements remain exactly 0.05 A, 0.5 A, and 0.05 A in the
pre/high/post windows. The base capture has 1,907,720 rows and completed
without nonfinite values or simulator errors.

## Diagnosis

The dip is a model control-and-energy response, not modeled peak-current
limiting. The requested load step adds 0.45 A. During the first millisecond
after the step the output capacitor must supply much of that missing current;
the 22 uF and 88 uF comparisons move the minimum in the expected direction.
The base controller command rises only to 0.946 A, well below the datasheet
4.76 A typical high-side peak limit, while FB is below the 0.600 V reference
and the switch node shows active ~15 V pulses. Therefore current-limit
clipping and a completely gated-off switch are not supported.

The KP comparison is diagnostic rather than a tuning recommendation: reducing
the assumed proportional gain makes the first dip materially worse and delays
the minimum. This confirms sensitivity to the unpublished PI representation.
`KP`, `KI`, and `CCTRL` are explicitly marked assumed in the model provenance;
TI states that the part has internal compensation but does not publish those
values. The simulation therefore cannot map the 2.880473 V number to the real
IC's loop bandwidth or phase margin.

There is a second model limitation to resolve before using the waveform for
design closure. The model's `BSET` gates every 500 kHz cycle directly on
instantaneous `FB < ref`. TI's datasheet section 8.3.1 describes peak-current
mode comparator termination each cycle, while section 8.4.4 limits PFM
frequency reduction to light load when minimum on-time or minimum peak
current is reached. The current model's unconditional per-cycle FB gate may
therefore suppress pulses in situations where a CCM controller would start a
cycle and terminate it by the current comparator. This is a source-grounded
model-fidelity issue, not evidence that adding output capacitance fixes the
actual device. A follow-up model-only experiment should move PFM skipping to
the documented minimum-current/light-load condition, preserve all other model
parameters, and compare the same captured command/FB/SW signals. It must not
be promoted as a fix without that comparison.

## Resolution

Retain LMR51430XDDCR for the present board decision. Do not ratchet a rail
requirement, reject the part, or claim that a capacitor addition cures the
device from this approximate model. Treat the 2.880473 V result as a bounded
model concern. The concrete closure requirement is either (a) a qualified
LMR51430 model with documented compensation and correct PFM/CCM behavior, or
(b) bench evidence using the actual BOM and the adopted load-pulse protocol.
Until one exists, report this transient as unresolved physical behavior with
the model's PI and pulse-gating assumptions called out.

TI source anchors used here are the retained primary datasheet
`harness-lab/audits/buck-20260909/sources/ti-lmr51430.pdf`, SLUSEF4A Rev. A:
500 kHz CCM trim (450–560 kHz), 4.0 ms typical soft-start, 70 ns minimum on
time, 150 ns minimum off time, 4.76 A typical peak limit, and section 8.4.4's
0.48 A typical minimum PFM peak and 20 mA typical zero-current threshold.

## Controlled pulse-gating experiment

### Superseded attempt

The earlier `pfm_corrected` and `pfm_zcd20` captures are invalid: their decks
used `../model.lib`, which loaded the parent scratch model rather than the
changed local copy. They must not be used as evidence.

The invalid attempts should not be interpreted as results. The prior model
expression already used the same 20 mA typical zero-current value as a literal;
no separate ZCD conclusion is drawn from those incorrectly bound decks.

### Validated local-model replay

The fresh `pfm_corrected_v2` deck includes `./model.lib`; its local model hash
is `6b7adcfae15d780ad9621951eec46ddb50d68ab41cf3fe2b9201139bded0103d`,
distinct from the base model. The same 11 ms run completed with 1,990,880
rows. Its minimum remained 2.880473 V at 6.136 ms, but recovery overshoot
increased sharply: maximum 3.761389 V at 9.103 ms and post-window mean
3.378411 V (base 3.335566 V maximum and 3.323654 V post mean). The command,
FB, switch, and inductor peaks in the initial dip remained 0.946 A, 0.521 V,
15.0 V, and 0.991 A respectively.

This variant therefore does not cure the dip and introduces a large recovery
overshoot in this model. It demonstrates that the pulse-gating rule materially
changes the model's later dynamics, but it does not establish which rule is
correct for the silicon. The earlier claim that gating was ruled out is
withdrawn. The remaining resolution is to keep both behaviors as explicitly
bounded model variants and require a qualified model or bench evidence before
using either transient waveform for a product decision.
