# ISENSE clamp evidence-gap review

Status: **bounded model evidence; selected-part gap remains open**.

This review is read-only.  It does not rerun the full raw trace, start a new
solver, change `clamp.inc`, or select a different diode/controller.  It
answers whether the current campaign can make an ISENSE-clamp claim from the
existing source-bound receipts.

## What is bounded already

The circuit topology and model identity are reproducible.  The retained
`accepted-baseline-11/cold.cir` has `Risense bridge_minus isense 220`,
`Cisense isense 0 1n`, and `DCLAMP 0 isense BAV23C_ASSUMED_V2`; the included
`accepted-baseline-11/clamp.inc` explicitly labels the diode model assumed and
nominal.  The F2-CREST38 source binding retains the same clamp include
(SHA-256 `96cd8d6bfd3870b22403c39437ef2625f0a930f9e06632adcebbc45b61b9dcde`).
The accepted normal and F2 receipts therefore establish behavior of this exact
authored netlist, not an unmodelled part.

The dedicated fixtures already bound the following **model-level** questions:

* `clamp/clamp_checks.rs` verifies diode polarity, the 220-ohm KCL relation,
  the open/reversed controls, assumed-model PCL and negative excursions, and
  the temperature fixture rows.  Its 1 µA diode-current and 2 mV ISENSE-shift
  limits are deliberately chosen engineering screens, not vendor limits.
* `clamp/limiting-envelope-13/parent-review.json` records 21 authored
  piecewise-law fixtures and an independent flat-state resistor oracle.  Its
  instantaneous peaks remain explicitly **UNVALIDATED**; the tight controls
  diagnose numerical convergence only.  The result is sensitivity to a
  declared VF/I law, not a Vishay bound.
* The complete F2-CREST38 raw trace contains `v(isense)` among its 42 saved
  fields, but the acceptance receipt does not report an ISENSE range or a
  diode-current screen.  The normal grid's 15-field traces do not save ISENSE
  at all.  A normal-grid receipt therefore cannot be used to claim clamp-pin
  behavior.

## Manufacturer bounds and the remaining gap

The retained TI UCC28180 datasheet (`clamp/datasheet-audit/UCC28180.pdf`,
SLUSBQ5D, SHA-256
`e1e1588c6854b43742a667c76df26f06d9ac51231f0176c43b2a46b63c1b00be`) provides
the limits that frame a model screen:

| TI item | Printed source | Meaning here |
|---|---|---|
| ISENSE absolute voltage -24 V to +7 V | p. 5 | Damage boundary, not sensing accuracy |
| ISENSE input current -1 mA to +1 mA | p. 5 | Damage boundary; not an allowable clamp-error current |
| PCL min/typ/max -0.345/-0.400/-0.438 V | p. 6 | Controller threshold characterization over the stated electrical range |
| ISENSE recommended 0 to -1.1 V; external diode VF above 0.438 V and below 1.1 V over variation | §8.3.14, p. 18 | Functional design window that a selected diode must satisfy at its actual current and temperature |
| 220-ohm series path and 1000-pF example filter | §9.2.2.9, p. 27 | Reference implementation; the retained circuit uses 220 ohm/1 nF |

The selected Vishay BAV23C document (`clamp/datasheet-audit/bav23c.pdf`,
document 86374, SHA-256
`b05e055b9bddac73647119b108d61535c80f89b2ad12087d4cee28bb18106d96`) gives
ratings and high-current VF maxima: 1.0 V at 100 mA and 1.25 V at 200 mA at
25 °C, with a -55 to +150 °C operating range.  Its page-3 forward-current
plot is typical.  It does **not** provide guaranteed low-current `VF(min)` or
`VF(max)` versus temperature, lot, or the actual clamp current near the
0.438-V PCL crossing.  The current model's approximately 70.2-nA nominal
PCL current is therefore not vendor-anchored.  This is the material
unbounded ISENSE gap.

The gap has four concrete consequences:

1. The chosen 1 µA/2 mV non-interference screen cannot be promoted to a
   Vishay qualification result.  Typical Figure-1 currents near 0.438 V are
   already tens of µA at 25 °C and larger on hotter typical curves, but those
   readings are not production limits.
2. The existing model does not establish the selected diode's low-current
   forward-voltage window over the controller's -40 to +125 °C electrical
   range.  Its -55 to +150 °C rating does not fill that missing I/V envelope.
3. The F2 raw trace's `v(isense)` can support a model-only pin-voltage report,
   but it has no saved `i(DCLAMP)` or `v(bridge_minus)` channel.  It cannot
   establish clamp current or pulse energy for the full-plant case from the
   saved fields alone.
4. The authored UCC28180 functional surrogate is not a silicon PCL-accuracy,
   propagation, or hot/cold model.  TI's managed TINA/PSpice assets do not
   become an open ngspice transient model by their existence.  This is a
   separate controller-model limitation, not a reason to redesign the clamp.

The TI absolute-maximum current must not be misread as a diode-current limit:
the resistor-limited clamp current can flow through the external diode while
the controller pin is held in its recommended voltage window.  Conversely,
the external diode's high-current rating does not prove that the controller
pin has a bounded sensing error.

## One useful optional scan, and its exact limit

No new full-plant simulation is justified to close the vendor gap.  If a
model-observability receipt is useful for the already accepted F2-CREST case,
perform one streaming decode of the existing raw artifact
`faults/settled-direct-capture-38/F2-CREST/raw.trace.raw.gz` (SHA-256
`d78e8e2f7c28b8ba9c10ce499af2813202ede8b2e173c39cfdc0ee3d650484fd`) and save
only a small extrema/crossing report for these already-saved signals:

* `v(isense)`;
* `v(xu.pcl_request)`, `v(xu.pcl_hold)`, `v(xu.fault)`;
* `v(fault_inject)` and `v(f2ctl)`;
* `time`, with separate healthy-prefix `[0, 0.65 s]` and post-injection
  `[0.6541666661706754, 0.662 s]` rows.

Compare the reported model pin against the TI design window
`-1.1 V <= v(isense) <= 0 V` and the absolute damage window `-24 V <=
v(isense) <= +7 V`.  Also report the model-only PCL screen, if the saved
`pcl_request` interval identifies it, using the existing `|v(isense)+0.438 V|
<= 2 mV` engineering screen.  Preserve the exact raw hash and do not call a
screen pass a device guarantee.

This scan would close a **reporting gap**—whether the accepted authored model's
saved controller pin stayed in the cited TI window for this case.  It would
not close the selected-Vishay low-current VF/temperature/lot gap, because the
raw fields contain neither a production diode characteristic nor
`i(DCLAMP)`.  The dedicated clamp fixtures already provide the latter for the
assumed model.  A future full-case clamp-current measurement would require a
new source-bound run saving `i(DCLAMP)` and `v(bridge_minus)`; that is optional
model instrumentation, not a hardware-qualification gate.

## Disposition

The current campaign may retain the exact normal-grid and F2-CREST modeled
receipts, with the existing scope that the controller, clamp, passives, and
ideal F2 are authored/nominal models.  It may report the optional raw scan as
an authored-model pin-window diagnostic if parent review requests it.  It
must not say that the selected Vishay BAV23C-E3-08 meets TI's forward-voltage
window, that the 1 µA/2 mV screens are datasheet requirements, or that the
clamp/current path is thermally or electrically qualified.  Closing that
material gap requires a vendor low-current VF-versus-temperature/tolerance
envelope or assembled characterization at the controller-side node, not a
new diode/controller topology.

## What the existing VF sweep can actually bound

The open-clamp rows and the authored hard-clamp rows at VF = 0.350, 0.438,
0.550, 0.700, 0.900, and 1.100 V are useful conditional circuit controls.  At
flat DC, under the declared piecewise law and 220.001 ohm total path, they
bracket the pin relation

```text
VISENSE = -VF - I*0.001,  I = (|VSHUNT|-VF)/(220+0.001)  when active.
```

They do **not** bracket an actual Vishay forward characteristic.  A real diode
can have current-, temperature-, tolerance-, capacitance-, and recovery-
dependent behavior that is absent from the constant-VF law.  In particular,
the 0.350-V row is intentionally below TI's §8.3.14 requirement that the
external diode VF exceed the 0.438-V maximum PCL magnitude, so it is a stress
sensitivity, not a compliant candidate.  The 0.438-to-1.100-V rows likewise
sample laws; they do not prove that a selected lot lies in that window.

Adding an ideal-short row at VF = 0 would be a sound **circuit-level extreme
only** if the source excursion and topology are held fixed and the clamp is
assumed to be a monotonic, zero-impedance shunt.  The resulting flat resistor
currents would be approximately 1.991 mA at -0.438 V, 5.000 mA at -1.1 V, and
22.727 mA at -5 V, with the pin driven close to 0 V.  Those numbers are
conditional DC KCL bounds on the resistor path: they are not an upper bound on
diode current in a dynamic device, a package pulse limit, or controller input
current.  The existing 1-mOhm hard-clamp peaks are explicitly unvalidated, so
the ideal-short row cannot be used to turn those peak diagnostics into a
transient bound.

Conversely, the open-clamp row is the limiting case for no external diode
conduction and leaves the pin near the shunt voltage.  Open and ideal-short
controls therefore bound a simple static topology model from both directions,
but only under the declared law.  They do not resolve the missing selected-part
VF-versus-temperature/lot curve or establish the TI functional window in
silicon. Documenting these conditional endpoints and scanning the existing
raw `v(isense)` field can improve the simulation report. Neither action closes
or bounds the selected-part gap, and neither establishes completion of the
goal's component-model requirement. A vendor envelope or assembled
temperature/pulse measurement remains necessary to establish the actual Vishay
characteristic. This review supplies no evidence requiring a controller or
diode redesign.
