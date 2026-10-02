# D-11 — blocked by shared measurement / OVP divider

**Do not change R26–R30 alone: U4 and U7 share the divider, so extending U4's linear range also raises the hardware OVP threshold; obtain an owner decision on separating the sense path or jointly revising OVP before selecting divider values and a controller receiver.**

Status: **scope conflict; D-11 design acceptance incomplete**. This is a stop-and-report handback, not a completed divider/receiver proposal. Base: `4574380993f525cdfa4f41702416b398a22689c3`. Analysis: OpenAI GPT-6 / Codex, 2026-10-02. Only this output folder is changed.

## What prevents the requested change

The brief correctly says U7 is a separate comparator: U4 clipping does not itself disable U7's threshold comparison. But U7 does **not** have a separate bus divider. The requested R26–R30 ratio change cannot preserve an unaffected, out-of-scope OVP circuit.

The source, frozen netlist and native-17 pad assignments agree:

| Evidence | Connection |
| --- | --- |
| `elec/src/power_stage_120v.ato:421,502` under the power-stage project | `u_vsense.VINP` and `u_ovp.INN` both connect to `VSENSE_IN` |
| `frozen/default.net:1365–1370` | `vsense_in` joins R29.2, R30.1, C27.1, **U4.2 and U7.4** |
| `native-17/section.kicad_pcb:11128,13287` | U4 pad 2 and U7 pad 4 both carry `vsense_in` |
| Source lines 484–502 and native R36/R37 | U7 compares this tap against the REF25 divider, 10 kΩ above 140 kΩ |

Paths in that table are relative to `zapote/power-stage-120v/`.
The evidence script checks both complete net endpoint sets (`vsense_in` and `ovp_thresh`), selected BOM/native identities, and the source statements. Its JSON records file hashes and exact native pad lines. This checks assignments, not physical copper continuity. Frozen netlist component aliases are not used as MPN authority; the resolved CSV and native values are checked, as in D-10.

There is no newly discovered board-versus-netlist mismatch. The conflict is between the brief's scope and the shared circuit. The owner explicitly selected “Deliver the blocker report” after this conflict was reported. The explicit exclusion of OVP therefore remains in force; this handback does not extend the design scope.

## Rerunnable demonstration of the conflict

These are **nominal DC calculations**, without tolerance, temperature, leakage, dynamic or reference-error terms. They establish coupling, not worst-case protection thresholds.

```
k = R30 / (R26 + R27 + R28 + R29 + R30)
U4 input = k × VBUS
U7 threshold = 2.5 × 140 / (10 + 140) = 2.333333 V
VBUS at OVP = U7 threshold / k
```

The present R26–R29 total 1.88 MΩ and R30 is 15.8 kΩ. U4 reaches 2 V at **239.974684 V**; nominal U7 trip is **279.970464 V**.

For a counterexample, keep the top string and substitute 12.4 kΩ below it. U4 then sees only **1.834707 V at 280 V**, but U7's nominal trip rises to **356.096774 V**. **12.4 kΩ is not a recommendation** and has not been rated or accuracy-qualified here.

| Bus (V) | Current U4 input (V) | Counterexample U4 input (V), R30=12.4 kΩ |
| ---: | ---: | ---: |
| 170 | 1.416816 | 1.113929 |
| 198 | 1.650174 | 1.297400 |
| 240 | 2.000211 | 1.572606 |
| 280 | 2.333579 | 1.834707 |

More generally, making `k × 280 ≤ 2` while retaining U7's nominal 2.333333 V reference forces its nominal trip to **at least 326.666667 V**. Adding measurement-range margin increases that threshold further. This is an algebraic implication of the unchanged nominal circuit, not a stacked worst-case bound.

## Findings retained for a resumed D-11

- `docs/hardware/power-section-120v/POWER-SECTION.md` §4 explicitly intends VBUS zero-crossing information for line-synchronous bursts. A receiver must therefore preserve meaningful near-zero readings and distinguish missing-supply indication from a real zero crossing. A high-bus accuracy table alone cannot qualify that use.
- `firmware/components/hal/include/temper_pins.h:43–45` assigns voltage sensing to GPIO2 / ADC1_CH1. `hal_adc.h` describes a generic calibrated voltage interface. Searching the firmware C/header sources for the pin/channel symbols finds their definitions only; no consumer establishes a deployed bus control loop, power-limit calculation, software OVP backup or telemetry accuracy requirement. `firmware/test/test_common.h:286–288` has a historical test conversion using a divisor of 110, not this board's transfer function. This is not an approved accuracy target.
- D-10's J4.11/J4.12 result remains applicable: no selected differential receiver; the root controller's V_BUS_SENSE is already driven. A future receiver should live at the controller end of the differential pair, with an explicitly allocated ADC input. Do not join it to the existing analog driver or ground VBUS_N.
- TI [AMC1311 SBAS786C, pp10,20,22, §7.9 and §8.3.3](https://www.ti.com/lit/ds/symlink/amc1311.pdf) guarantees linear behavior through 2 V. Above that, output still increases with reduced linearity before positive clipping (2.49 V typical differential). This is distinct from the negative differential fail-safe indication for missing/undervoltage VDD1 or asserted SHTDN. Firmware must classify overrange and sensor-invalid states separately from valid bus measurements, inhibit operation on invalid sensing, and never convert a clipped reading into a claim of safe bus voltage. U7 remains the hardware protection path.
- Espressif [ESP32-S3 datasheet v2.2, p66, Tables 5-5/5-6](https://www.espressif.com/sites/default/files/documentation/esp32-s3_datasheet_en.pdf) specifies attenuation-dependent effective ranges and calibrated errors under stated DC test conditions. Receiver selection must use those ranges rather than assume ideal conversion across the supply rails; ADC nonlinearity and calibration remain part of the eventual error budget.

## Owner decision and unfinished acceptance

Choose a revised scope:

1. Preserve the existing OVP divider and threshold; authorize a separate measurement divider or isolated input-conditioning path for U4. Its loading of OVP, if any, must be evaluated.
2. Authorize coordinated R26–R30 and U7 threshold changes, including renewed OVP corner and timing analysis.
3. Retain the present circuit and explicitly accept its limited accurate measurement range; this does not meet the original 280 V linear-range objective.

After that decision, D-11 still needs the selected E96/E192 divider values; per-resistor voltage/power checks; a defined OVP-plus-transient envelope; temperature/tolerance/amplifier accuracy and resolution comparisons; a complete receiver/load/common-mode/ADC design; and concrete firmware thresholds and error policy. No owner-defined accuracy target or guaranteed transient ceiling was established. POWER-SECTION.md explicitly says the historical MOV clamp example does not bound returned tank energy.

## Reproduce

From the repository root, with standard-library Python 3.12:

```sh
python3.12 zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D11/bus_sense.py > /tmp/d11-bus-sense.json
diff -u zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D11/bus_sense.json /tmp/d11-bus-sense.json
```

The JSON includes the runtime version, so a different patch version changes that field. The script uses the committed, hashed D-10 read-only parser and does not invoke its full audit. No Rust/native bridge build, simulation, board edit, netlist edit or firmware edit is needed.

Validation: Python 3.12.12 replay matched byte-for-byte; the import-boundary gate passed (5 contracts kept, none broken); the read-only derived-artifact check passed. The initial missing-tool failure and isolated validation environment are documented in [validation.txt](validation.txt).
