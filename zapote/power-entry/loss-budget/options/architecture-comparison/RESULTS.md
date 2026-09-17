# PFC architecture comparison — 2026-09-17

The buffered C7 is a reasonable experimental baseline, but the available evidence
does not establish an optimum. All three Luna research units are complete.
The next useful comparison is **frequency plus actual magnetics**, with a
matched switching-energy reference pursued alongside it. Do not select a new
PCB topology from these partial loss figures.

## What the three investigations established

| Investigation | Result | Decision consequence |
| --- | --- | --- |
| [Manufacturer benchmark](benchmark/REPORT.md) | TI and Infineon publish measured whole-board efficiency, but no sufficiently matched switching-energy capture was found. | The Rust model remains physically unvalidated. Manufacturer efficiency cannot calibrate an unmatched device/event model. |
| [Silicon and frequency](silicon/REPORT.md) | Lower frequency reduces the conditional switching subtotal, while demanding larger effective inductance to preserve ripple. | Compare 90 kHz and 65 kHz with real magnetic candidates before further optimizing the 129 kHz circuit. |
| [Kelvin-source SiC](sic/REPORT.md) | NTH4L060N065SC1 with UCC27624 and proposed 0/+15 V is a research candidate; its published switching energies use -5/+18 V. | Keep it as a competing candidate, without claiming a loss advantage or importing mismatched switching energy. |

## The frequency trade is large enough to investigate

At 120 Vrms, 400 V bus and the retained 15 A true-RMS input case, hold
`L × frequency` constant. Scale the retained no-assist C7 overlap, Eoss and
gate-charge terms with frequency, keeping its conduction term fixed:

| Frequency | Effective inductance | Conditional switch/gate subtotal | Reduction from baseline |
| --- | ---: | ---: | ---: |
| 129.107 kHz baseline | 180 µH | 45.50 W | — |
| 90 kHz | 258 µH | 33.68 W | 11.82 W |
| 65 kHz | 358 µH | 26.13 W | 19.38 W |

These are transparent model sensitivities, not new simulations or measured
assembly losses. All three use the same nominal 12 V drive and charge/resistance
assumptions. The nominal input power is 1796.310 W; it is not delivered DC-bus
or pan power. At 108 V the 15 A limit requires derating. At 132 V a same-power
comparison needs a new true-RMS current solve; `P/V` alone omits ripple.

A larger inductor may consume some or all of the predicted switch benefit through
winding/core loss, volume, cost and cooling. No exact 258/358 µH replacement has
been qualified. Existing 180 µH ratings cannot be copied to either replacement.
The SiC candidate's approximately 8.64 W nominal 25 °C conduction screen is **not**
comparable to the C7 subtotal: SiC switching loss remains unknown at the proposed
bias and event-current distribution.

## Next experiment and stopping rule

1. Retain the 129 kHz baseline. Screen exact 90 kHz/258 µH and 65 kHz/358 µH
   effective-inductance candidates at operating bias, including tolerances,
   saturation, hot DCR, core/AC winding loss, physical volume and procurement.
   Start with 90 kHz as the smaller magnetic change, while retaining 65 kHz
   in the comparison so it is not prematurely excluded.
2. Run those source-bound cases through the maintained model at the same
   input-power/current-limit contract. Include the diode, bridge, shunt,
   capacitor, PCB/contact, auxiliary and cooling terms. Record unknown terms
   as unknown; do not rank incomplete totals as complete assemblies.
3. Obtain a matched switching reference: exact device, driver/bias/resistance,
   bus, event currents and temperature with interpretable energy accounting.
   Manufacturer reference data or an independently calibrated device model
   can constrain the simulation; assembled waveform evidence is still needed
   for hardware qualification. Keep numerical verification separate from both.
4. Compare whole-assembly loss, size, cost and controllability against a written
   system budget. Keep current hardware unchanged until the comparison justifies
   a candidate. A shared 15 V gate supply is an additional simplification to
   test, not a reason to reuse 12 V loss predictions.

Escalate to interleaving if the conventional boost cannot meet the agreed
magnetic/current/thermal/EMI budget. Consider bridgeless only if bridge losses
justify its control and EMI complexity. Neither escalation has been designed
or ruled out by this research. A budget and unresolved dominant loss terms,
rather than sunk effort in a footprint, determine the next architecture step.

## Evidence and limits

[Verification](VALIDATION.md) records integration corrections and checks.
[Delegation](DELEGATION.md) records ownership and requested models.
[Provenance](provenance.json) binds this research snapshot and its retained PDFs.
No CAD, production Rust validator, acceptance threshold, frozen board evidence,
or memory catalog changed. Research is complete; physical model validation and
hardware qualification remain indeterminate.
