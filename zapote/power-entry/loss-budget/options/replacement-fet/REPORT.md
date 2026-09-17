# Option 2 — replacement MOSFET on the existing UCC28180 drive

Research date: **2026-09-17**. This is a parts shortlist and a bounded loss
sensitivity, not a production selection. The candidates retain the existing
650 V, TO-247 PFC-switch envelope and are screened against the retained
UCC28180D controller. No board, gate waveform, thermal path, or hardware was
changed.

## Recommendation for the next model pass

Use **IPW65R045C7** as the first replacement model and **IPW65R041CFD7** as
the second. Both are 650 V, three-lead TO-247 silicon superjunction parts and
are orderable in tube packaging from a distributor. They are the only two
shortlisted parts for which the manufacturer publishes both Qgd and a numeric
Eoss point suitable for a first sensitivity comparison. The C7 has the lowest
published Qg/Qgd and Eoss of the silicon choices; the CFD7 has the lower
published hot RDS(on) typical and a faster body diode, so it is the useful
thermal-loss counterpoint. Those hot typicals use different device/test
currents and do not establish a same-temperature ranking.

**NVHL040N65S3F** is an active, well-stocked third source with the same
three-lead package and 40 mOhm maximum RDS(on), but its Qg/Qgd are much larger
and its Eoss is only a graph. Treat it as a supply-risk fallback, not as a
loss winner. The TO-247-4 **NVH4L040N65S3F** adds a Kelvin source lead, but it
cannot be called drop-in: the existing footprint and gate/source routing are
three-lead. It is retained as a conditional layout option only.

The 650 V SiC **IMW65R048M1H** is deliberately excluded from the direct
replacement shortlist. Its 18 V recommended turn-on voltage conflicts with
the unvalidated AUX_15V_IN gate waveform, and its 40 A (25 °C case) / 28 A
(100 °C case) continuous rating leaves less thermal margin than the incumbent.
Its excellent Qg/Qgd therefore does not establish a compatible replacement.

## Common operating point and calculation boundary

The common sensitivity point is the retained model point: 389.615 V bus,
129,107.392 Hz, 120 V RMS line, 15 A RMS input current, external 10 ohm gate
resistor plus the incumbent's 3.3 ohm intrinsic-gate resistance. The model's
nominal overlap result is 126.582 W and its retained baseline Eoss is 16.835
uJ/event (2.174 W at the switching frequency). The 136.002 W MOSFET-plus-gate
subtotal is explicitly an overlap sensitivity, not a measured loss.

Each silicon candidate is rated 650 V, giving a nominal static VDS/Vbus ratio
of 1.668 at 389.615 V. That is the same voltage class as the incumbent; it is
not an overshoot qualification. The 108/120/132 V line sweep keeps the common
bus/frequency assumptions for comparison and does not substitute for a
measured peak VDS waveform.

For orientation only, multiplying each datasheet's **Eoss at 400 V** by the
common frequency gives 1.511 W (C7) and 1.808 W (CFD7). This is not an
operating-point prediction: Eoss is nonlinear with VDS and the datasheet
curves use different test conditions. No numeric Eoss term is invented for
the onsemi part. Similarly, the 15 A RMS conduction term is scaled using the
existing model's duty-weighted **I² factor of 141.82 A²** (not 15²=225 A²)
only to expose a sensitivity:

| part / condition | RDS(on) input | duty-weighted conduction sensitivity |
| --- | ---: | ---: |
| incumbent hot sensitivity | 100 mOhm (authored sensitivity) | 14.182 W |
| IPW65R045C7, 150 °C typical curve point | 96 mOhm | 13.615 W |
| IPW65R041CFD7, 150 °C typical curve point | 76 mOhm | 10.778 W |
| NVHL040N65S3F, 25 °C maximum only | 40 mOhm | 5.673 W |

The hot rows are **typical curve values**, not guaranteed maximums, and are at
different datasheet currents and test setups. They do not rank the parts at a
common temperature. The onsemi hot value is not tabulated and remains null.
These numbers must not be added to measured Eon/Eoff or used as an
electrothermal result.

The UCC28180 source/sink peak ratings (1.5 A source, 2 A sink) do not prove a
gate waveform. The retained controller datasheet reports a typical gate-high
of 11.2 V at VCC=12.2 V and 15.2 V at VCC=20 V; the present AUX_15V_IN rail
has no validated local producer or measured gate amplitude. All candidate
RDS(on)/Qg values below are specified at 10 V unless stated otherwise. A
scope capture of VGS, VDS and ID at 108/120/132 V line is required before
ranking overlap loss.

The standalone [`calc.rs`](calc.rs) reproduces the arithmetic and prints a
conditional Miller-duration proxy under the explicit 10 V gate-bias
assumption. Using each manufacturer's internal gate resistance where it is
published, it gives C7 about 70.8 ns turn-on / 60.3 ns turn-off and CFD7
about 99.5 ns turn-on / 75.1 ns turn-off for Qgd transfer at the same 10 ohm
external resistor, with turn-off assuming a 0 V low state. NVHL040N65S3F has no published
internal Rg or plateau value in the retained sheet, so its proxy is null.
These are charge/resistance estimates, not event energies or UCC output
waveforms; no overlap-W claim is made from them.

## Candidate comparison

### 1. Infineon IPW65R045C7 — first model candidate

The official Rev. 2.1 sheet identifies a 650 V, PG-TO247-3 silicon CoolMOS
C7, 46 A at 25 °C case / 29 A at 100 °C case, 45 mOhm maximum RDS(on), 93 nC
typical Qg and 30 nC typical Qgd. Its 11.7 uJ Eoss point is specified at
400 V. The gate plateau is 5.4 V in the 400 V, 24.9 A, 0-to-10 V gate-charge
test; the datasheet's internal gate resistance is 0.85 ohm. The UCC28180
plus 10 ohm authored resistor is electrically plausible
only pending the actual waveform. The datasheet explicitly names PFC stages
and hard-switching PWM applications.

The package is the same three-lead drain-tab/gate/source arrangement as the
incumbent. It has no Kelvin source pin. The 150 °C RDS(on) curve point is
0.096 ohm typical at the datasheet's 24.9 A, 10 V test current; use it as a
typical thermal sensitivity, not a guaranteed hot limit. Mouser's observed
page listed 519 pieces immediately available, tube, $12.55 at quantity 1.
An exact DigiKey purchase page was not resolved in this run; its stock is
recorded as unknown rather than copied from a similarly named CFD7 page.
Because the Mouser page was crawled three weeks before retrieval, inventory
must be rechecked at purchase.

### 2. Infineon IPW65R041CFD7XKSA1 — hot-RDS counterpoint

The silicon order code is IPW65R041CFD7; the stocked distributor code observed
was **IPW65R041CFD7XKSA1**. The official Rev. 2.1 sheet identifies a 650 V,
PG-TO247-3 CFD7, 50 A at 25 °C case / 32 A at 100 °C case, 41 mOhm maximum
RDS(on), 102 nC typical Qg and 31 nC typical Qgd. Eoss at 400 V is 14.0 uJ.
The 5.7 V plateau is specified at 400 V and 24.8 A, 0-to-10 V; the datasheet's
internal gate resistance is 3.8 ohm. Its 150 °C
RDS(on) curve point is 0.076 ohm typical under that same current and gate
bias. The CFD7 sheet calls out hard-commutation robustness and a fast body
diode, but its headline application language emphasizes resonant/ZVS
topologies; that is not evidence of lower hard-switched PFC Eon/Eoff.

The package is the same three-lead TO-247 geometry and has no Kelvin source.
Mouser observed 198 pieces of the exact X suffix, tube, $10.93; DigiKey
observed 252 pieces, tube, $10.93. These are dated page observations, not a
live inventory guarantee.

### 3. onsemi NVHL040N65S3F — stocked silicon fallback

The retained LCSC PDF mirror of the official onsemi Rev. 1 sheet gives 650 V
minimum breakdown, 65 A continuous at 25 °C case, 40 mOhm maximum RDS(on) at
32.5 A/10 V, Qg=153 nC and Qgd=61 nC at 400 V/32.5 A/10 V, and 159 ns/840 nC
typical reverse recovery at 32.5 A. The official onsemi PDF URL is retained
alongside the mirror URL and the local PDF hash; the mirror bytes are the
evidence actually retained here.
The Eoss-vs-VDS graph is present, but no numeric 400 V Eoss is tabulated in
the retained text, so the Eoss term is **null** here. The high Qg and Qgd
relative to the two Infineon parts predict a larger gate/overlap sensitivity
under the same drive, but no Eon/Eoff claim is made.

It is a three-lead TO-247 and therefore mechanically closest to the incumbent.
The Mouser observation listed 711 pieces, tube, $15.53; the exact DigiKey
page was not live-resolved in this run and remains an indicative distributor
search observation only. Both pages identify an active/AEC-Q101 part. The
pages were crawled weeks to months before this report and must be rechecked.

### Conditional layout option: onsemi NVH4L040N65S3F

This is the same 650 V/40 mOhm silicon family in a four-lead TO-247-4L with a
Kelvin source. DigiKey observed 448 pieces in tube at $15.16 and Mouser
observed 12 pieces in tube. Its Qg is 160 nC; the Eoss value is graph-only.
The extra source lead could reduce common-source inductance, but it requires a
new footprint and gate/source copper review. It is not an electrical
drop-in replacement for this board and is not included in the ranked three.

## Evidence and next tests

The exact source bindings, PDF hashes, distributor URLs, observed stock and
all null terms are machine-readable in `candidates.json`. The three retained
datasheet PDFs are copied under `sources/` and hash-checked against that JSON.
Distributor stock is a point-in-time observation, not a procurement
commitment.

Next tests, in order:

1. Measure the actual AUX_15V_IN gate-high/low waveform and controller current
   with the incumbent part, including VGS plateau and turn-off undershoot.
2. Replace only the switch on a clamped-inductive fixture and capture VDS/ID
   Eon/Eoff at 108/120/132 V line-equivalent current, 25/100/125 °C case
   conditions where practical. Do not add measured Eon/Eoff to Eoss if the
   measurement already includes Coss discharge.
3. Re-run the Rust sensitivity with candidate-specific Qgd/Eoss/RDS inputs,
   retaining missing Eoss and missing hot-RDS terms as null rather than zero.
4. Verify the existing three-lead TO-247 land pattern, drain-tab isolation,
   gate loop inductance and heatsink mounting before any board edit.
