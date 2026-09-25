# Full-plant stall review: bounded reduced probes

Date: 2026-09-20

This folder archives short, isolated probes made after the tracked cold-start
capture stopped at `t=0.348534537976268155 s`. The cold-start inputs were not
changed and the full simulation was not replayed.

## Captured full-plant evidence

`normal-tracked/checker-report.txt` rejects row 9,736,225 because time is not
strictly increasing. `inspection.txt` reports first non-increasing time at
`0.256990362212805523 s`, 1,126,438 non-increasing rows among 14,951,468,
and final time `0.348534537976268155 s` (required endpoint 0.5 s). At the
first event, `gate=-7.7156 uV`, `vcomp=3.16435065864 V`, and
`icomp=3.12790255643 V`. At the endpoint, `gate=-5.8361 uV`,
`q=en=5`, `fault=0`, `vcomp=2.84559003104 V`, `icomp=2.50404966322 V`,
`VB=366.544469 V`, and `IL=3.558664 A`. The trace did not save
`raw`, `pwm_hold`, `pwm_input`, `drv_req`, or `drv`, so the endpoint cannot
identify which controller edge is active. Reconstructing the Braw ramp from
`phase`, `m2`, and the controller equation gives 2.531607 V versus ICOMP
2.504050 V at the endpoint; this is a timing clue, not proof of causality.

## Timestamp-neighborhood probes

Each `late-*.cir` is the existing unsafe isolated PWM bridge fixture with its
PWL raw edge moved to one captured timestamp; each `late-safe-*.cir` uses the
same fixture with the finite DAC output (`Bgate=3*V(pwm_hold)`). The two
neighborhoods are the first non-increasing timestamp
`0.2569903622128 s` and the final stall timestamp `0.3485345379763 s`.

| Fixture | Edge timestamp | Result | Evidence |
|---|---:|---|---|
| unsafe `late` | 0.2569903622128 s | aborts (`Timestep too small`, node `drv_req`) | 38 rows; `pwm_hold` stops at 2.4999741 V |
| unsafe `late` | 0.3485345379763 s | aborts (`Timestep too small`, node `drv_req`) | 38 rows; `pwm_hold` stops at 2.4999741 V |
| finite-edge `late-safe` | 0.2569903622128 s | reaches requested endpoint | 356 rows; gate reaches 10.5976 V |
| finite-edge `late-safe` | 0.3485345379763 s | reaches requested endpoint | 448 rows; gate reaches 10.5976 V |

This reproduces the known hard `pwm_hold` re-thresholding failure at both
actual timestamps. It does **not** reproduce the full-plant stall because the
full candidate already uses the finite edge. Therefore it cannot establish
that Bgate or the external driver is the full-plant cause.

## Vendor UCC27511A check

The repository vendor artifact is
`f2-shutdown-04/vendor/UCC27511A_TINA_TRANS/UCC27511A.lib`, a TI PSpice
transient model with pins `INM INP VDD GND OUTH OUTL`. A direct ngspice 45.2
smoke test is archived as `sources/ucc27511a-ngspice-test.cir`. It completes
when run with the retained vendor `.spiceinit` (`set ngbehavior=ps`). The
initial `no such function 'if'` error came from running outside that harness;
it does not establish a model incompatibility. See the compatibility
correction below for the reproduced results. No port or model change was
made here; full-plant adoption still needs an interface validation receipt.

## Bounded hypotheses and next capture

1. The full candidate's remaining hard event is the analog-feedback Braw
   comparator (`Braw` compares the phase ramp to ICOMP). The endpoint's
   reconstructed ramp/ICOMP crossing and healthy q/en/fault make this a
   testable timing candidate, not a root-cause claim. A reduced reproduction
   should retain `Biamp`, `Cicomp`, `Bvamp`, `Bm2`, and the ADC/DFF/DAC chain
   while saving `raw`, `phase`, `m2`, `pwm_data`, `pwm_clk`, `pwm_reset`,
   `pwm_q`, `pwm_hold`, `pwm_input`, `drv_req`, `drv`, and `gate`.
2. The `UPWM_ADC`/DFF/DAC event chain uses strict 2.5-V bridge thresholds and
   1-ns delays. If `raw` is repeatedly re-evaluated while ICOMP moves, this
   can produce same-time callbacks even though the DAC edge is finite. The
   saved nodes above distinguish a Braw edge from a downstream driver edge.
3. `Bphase` uses `time-PERIOD*floor(time/PERIOD)` and `cycle_reset` is a
   PULSE. A phase/cycle-reset scheduling interaction remains possible but is
   less supported because the final phase is about 1.9255 us, well away from
   the period boundary. It should be checked only after the raw/held chain is
   captured.

No tolerance, timestep, deduplication, or model behavior was changed to make
these probes pass.

### Compatibility correction

The first smoke command was run outside the vendor directory and therefore
missed its retained `.spiceinit`. That parse failure is not a model limitation.
The vendor harness's `.spiceinit` contains `set ngbehavior=ps`; rerunning the
same test from the vendor directory completed under ngspice 45.2 with 12,487
transient points and 124 rejected points. The existing retained
`driver-final-interface.cir` also completed unchanged (12,128 rows); its
reported checks include default-off 1.53e-10 V, positive-enable 14.96403 V,
and RUN-fall-to-gate-4V delay 0.211801 us. These logs and the `.spiceinit`
are archived here.

This makes vendor-driver substitution technically feasible, but it remains a
separate model adoption: the model has split OUTH/OUTL outputs and its input
pins are `INM INP VDD GND`, while the operating-matrix net currently uses the
source-07 enable/pwm interface and an authored driver surrogate. A short
integration fixture must map polarity, OUTH/OUTL gate resistors, disable FET,
and 12-nF load and compare default-off, enable, disable, and AUX-drop timing
before any full-plant run. No integration was attempted in this review.
