# PFC branch-current and native copper screen

The PFC power-stage screen now runs through the common unit runner. It binds
the reviewed source pins to the saved board, calculates switching-state
currents, splits the native copper graph, and measures actual pad copper with
drill voids excluded. It does not certify mains operation or thermal safety.

The [verification receipt](../runs/2026-09-12-pfc-current/verification.json)
retains the pre-repair seven-board run, tests, source/input hashes, review records,
failed development runs and native geometry evidence. That instrument-validation
run did not edit a product PCB; the subsequent repair below did.

The subsequent [independent-oracle validation](oracle-2026-09-12/README.md)
checks these instruments against closed-form math, actual ngspice solves,
native KiCad geometry and exhaustive cut-graph references. It exposed and
fixed CCM validity, segmentation-invariance and dimensional-conversion defects.
The same five nominal screening findings remained after instrument correction.
The subsequent [PCB repair](../../power-entry/evidence/copper-repair-2026-09-12/README.md)
widens one segment with its determined current preserved, leaving four bridge
terminal-neck findings. Their uniform-width screen needs a finite-neck thermal
assessment before it can establish the physical temperature of those connections;
neither a formula implementation test nor a process-aborted DRC run supplies that
evidence.

## Model and source binding

- Exact source validation pins the current Würth **760800301**, rather than
  the obsolete inductor in the earlier architecture note. Its nominal 180 µH
  comes from the [manufacturer datasheet](https://www.we-online.com/components/products/datasheet/760800301.pdf).
- The existing source-bound bus-divider calculation gives 389.615 V. The
  existing 16.2 kΩ frequency-resistor calculation uses the
  [UCC28180 datasheet](https://www.ti.com/lit/ds/symlink/ucc28180.pdf).
- The operating screen assumes 120 V RMS and a 15 A true-RMS power-stage
  current limit, ideal CCM operation and nominal component values. Triangular
  inductor ripple remains in the ON/OFF samples before RMS is calculated.
- Kirchhoff current balance is checked independently in every connected net.
  Input/output energy and capacitor charge balance have regression coverage.
- NTC/relay, dual diode anodes and five capacitor branches do not receive an
  assumed equal share. Signed difference waveforms identify branches whose
  current is independent of sharing. Other branches receive an explicitly
  labeled component-current envelope, allowing nonnegative time-varying
  shares. Circulating/parasitic currents are outside this model.

At this nominal operating point: input/inductor RMS is 15 A, switch RMS is
11.909 A, diode RMS is 9.120 A, ideal DC load is 4.611 A and aggregate capacitor
RMS is 7.868 A. These are simulated/model values, not bench measurements.

## Saved-board result

The screen binds 152 native trace objects, splits them into graph edges, and
records actual pad/trace contacts. The final report distinguishes determined
currents, sharing envelopes, auxiliary pad/package links and physical copper.
Repeated physical pads with the same package pin retain separate barrels and
UUID-bound polygons. Auxiliary conductor links are never reported as traces.

Five sections violate the nominal **70 µm external copper / assumed 20 °C
rise** IPC screening equation already copied from Temper's Rust DRC. The four
2.5 mm sections screen at 10.4205 A, and the 4 mm section screens at 14.6513 A;
the determined nominal contribution is 15 A in each case.

| Native segment UUID | Net | Layer | Width | Start → end, mm |
|---|---|---|---|---|
| `e45ca754-66c7-4204-987e-e69d5ed1af44` | minus | F.Cu | 4 mm | (71.1,132) → (75.3,132) |
| `1a8c9e36-4bbf-486e-a8a9-34985b0b249e` | minus | B.Cu | 2.5 mm | (30,115) → (30,123.5) |
| `6be299ab-3af0-4444-8bb5-c26c3d6443f6` | ac1 | F.Cu | 2.5 mm | (35.08,115) → (35.08,124) |
| `44d2e757-cc34-46a2-88aa-5ae29db62817` | ac2 | B.Cu | 2.5 mm | (40.16,109) → (40.16,115) |
| `e7dc2c72-d7b2-4456-afa6-efe227e0f8f8` | plus | F.Cu | 2.5 mm | (45.24,115) → (45.24,108) |

These are screening failures against the stated model, not measured
temperatures or fabrication-qualified ampacity limits. They remain in the
common runner's authoritative verdict. A clean KiCad DRC does not erase them.

## Geometry and uncertainty

Pad contact measurements use KiCad's **inside** copper polygons and
**outside** drill polygons. They report observed transverse copper chords,
not component body dimensions or the largest pad bounding-box dimension.
The chord is a lower bound on available local contact width; it does not
prove a minimum cut through the whole pad, plane, barrel or thermal relief.

Software/model gaps remain explicit: area-current distribution inside zones,
finite-width side contacts without a resolved area network, pad/plane minimum
cuts and unsupported contact shapes. These do not receive exact-current
certificates. Plating, hot resistance, saturation/tolerances, EMI/control/bias
and bleeder contributions, circulating currents, losses, inrush and fault
transients require additional models/inputs. Powered hardware is NOT RUN.

## Regressions and learned failure modes

- Duty-averaging pulses before RMS understates branch heating. Keep ON/OFF
  samples and test every reported moment against the emitted waveform.
- Summing ON and OFF moments without their time weights double-counted the
  constant load. A constant-load/energy regression now catches this.
- A zone edge ID missing its target silently dropped all but one connection.
  Graph edge identity includes each target, and native cluster comparison runs
  after all copper contacts have been added.
- A package pin number is not a physical-pad identity. Repeated relay pads
  need distinct barrel/contact edges and exact UUID binding.
- Equal RMS at sharing vertices does not prove equal signed waveforms;
  cancellation between vertices must remain possible unless sensitivity is zero.
- A graph tree can be false when side-contact copper or zone paths are omitted.
  Those nets remain uncertified rather than producing exact current claims.
- The independent 30° native-pad fixture detects rotation-sign/pose errors and
  drill-filled copper. The saved-width regression narrows a 6 mm segment to
  0.2 mm and requires a new failure on that specific native UUID.

## Reproduce

Run the normal `zapote-unit-run` command with `validation/units.json`; PFC
waveform, branch and contact records appear in the power-entry report's
`pfc_power` field. The common runner refreshes native manufacturing evidence.
The standalone `zapote-pfc-power` binary also accepts source, native, saved PCB
and manufacturing JSON paths for replay. Exit codes are 0 PASS, 1 FAIL and
2 INDETERMINATE. Treat a replay receipt as evidence only when its provenance
matches the source board and extractor.

The pinned pad fixture contains only native pad/via records; its metadata
records the hash of the complete extraction retained in the run archive.
The width mutation is explicitly derived test input: it changes saved board
width and matching native trace width while retaining unchanged pad geometry.
