# Draft TI support request — not sent

Subject: LMR51430XDDCR 500-kHz PFM transient model and WEBENCH simulation availability

We need a transient model for the exact LMR51430XDDCR 500-kHz PFM variant.
The intended design is 13.5–16.5 V input, 3.3 V output, 0.5 A continuous
load and 1 A/10 ms load pulses. The circuit uses 5.6 µH, two 22 µF output
capacitors and a 100 kΩ/22.1 kΩ feedback divider.

On September 10, 2026, the signed-in WEBENCH selection card showed an enabled
SIMULATE action for LMR51430X. The generated exact LMR51430XDDCR design
(13.5–16.5 V to 3.3 V/1 A, 70 °C ambient) instead displays “Simulation not
enabled for this design.” Its Export page offers design information but no
simulation-export format.

Is a supported transient model available for this exact variant? Please
identify its version, supported simulator and permitted use/export. An
unencrypted SPICE/PSpice netlist would let us evaluate simulator compatibility;
we do not assume ngspice compatibility. If only an encrypted or vendor-hosted
model exists, please identify the supported way to simulate and export raw
startup, line and bidirectional load-step waveforms.

We need to understand whether the model covers PFM at light load, the 0.6 V
reference, soft-start, minimum on-time and current-limit/hiccup behavior, and
which behaviors TI explicitly excludes from the model. Is the WEBENCH
selection-card/design-page disagreement expected or a tool issue?
