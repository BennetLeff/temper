# D-11 — retain the divider; receive, qualify and flag the bus measurement

**Keep R26–R29 = 4 × 470 kΩ, R30 = 15.8 kΩ and U7/R36/R37 unchanged; add a controller-side OPA2388 half-gain difference receiver biased at 0.25 V, and latch a measurement-over-range fault at calibrated ADC ≥ 1.210 V while retaining U7 as hardware OVP.**

Proposal complete for review against owner decision `83c02a9a06383f020227ce57a14bc37a18c956ff`; **not hardware qualification**. Analysis: OpenAI GPT-6 / Codex, 2026-10-02. The owner dropped divider alternatives and their rating checks. Only `out-D11/` changes; no circuit, board, netlist or firmware changes.

The earlier stop report remains in commit `c7b0916e1`. Its finding stands: U4.2 and U7.4 share `vsense_in`. The owner resolved the scope conflict by retaining that divider, not by making the two paths independent. [bus_sense.py](bus_sense.py) rechecks source statements, BOM identities and native/netlist endpoint parity; [bus_sense.json](bus_sense.json) records input hashes and calculations. Frozen component aliases are not treated as MPN authority.

## 1. What the measurement must do

| Read-only source | Established use / limit |
| --- | --- |
| `docs/hardware/power-section-120v/POWER-SECTION.md` §4 | VBUS near-zero timing for line-synchronous bursts; the temperature loop uses the RTD and under-glass sensor. |
| `firmware/components/hal/include/temper_pins.h:43–45` | GPIO2 / ADC1_CH1 voltage assignment; no electrical receiver specification. |
| `firmware/components/hal/include/hal_adc.h` and `esp32/hal_adc_esp32.c` | Generic acquisition/calibration facilities, not a bus measurement service. |
| `firmware/main/main.c`, `state_handlers.c`, C/header symbol searches | No implemented bus-voltage consumer establishes voltage feed-forward, bus-based power limiting, backup OVP or telemetry accuracy. ADC initialization in `main.c` is commented out; power-control interfaces are still external stubs. |
| `firmware/test/test_common.h:286–288` | Legacy `/110` conversion is test code, not this circuit's calibration. |
| D-10, task06 J4.11/.12 | Differential pair has no selected receiver. Root controller U27.38 / GPIO2 is already locally driven. |

The required magnitude range is normal operation through 198 V, with valid near-zero timing and an explicit upper-range status. No source establishes a percentage accuracy or crossing-time requirement. For this proposal only, allocate **±6% at 170/198 V, ±5 V at zero and ±250 µs crossing timing**; these are engineering targets for owner acceptance, not recovered firmware requirements. No bus-based precision power limit or redundant safety integrity is claimed.

The conditional DC budget below meets the two magnitude targets. A sinusoidal 170 V crest / 60 Hz illustration gives about **154.5 µs** crossing uncertainty including amplitude error, nominal input/output filter delays, U4's maximum 90% delay and one sample interval. That is an **estimate**, not an assembled timing bound: the rectified, loaded film-bus waveform is not an ideal sinusoid. Verify actual crossing windows and burst timing before enabling heating. A slowly sampled telemetry loop is insufficient; propose **20 ksample/s**, time-stamped acquisition, a phase/window estimator and separate unaveraged fault processing.

**The literal “accuracy over 0–240 V” cannot be confirmed.** The nominal linear endpoint is 239.9747 V and some tolerance corners leave the range earlier. Treat “240 V” as a nominal label for the input-limit region, never as a guaranteed inclusive accurate endpoint. Report a value only while the qualified transfer and validity rules apply; over-range carries no precise bus value.

## 2. Receiver on the controller

Use **OPA2388ID** (dual, 3.3 V supply) as follows. All new reference and receiver returns are **SELV_GND**; the new reference is separate from HOT-side U5/REF25.

```text
J4.12 VBUS_N -- RN 20.0k -- A−       A output -- RF 10.0k -- A−
J4.11 VBUS_P -- RP 20.0k -- A+       B output -- RB 10.0k -- A+

3V3 -- 1.00k (1%) -- local LM4040A25IDBZR cathode (2.5 V)
                         anode -> SELV_GND
2.5 V -- 90.9k -- divider midpoint -- 10.1k -- SELV_GND
                       midpoint -> B+; B− tied to B output (0.25 V)

A output -- 100 ohm -- allocated ADC1 input
                         |
                       100 nF
                         |
                      SELV_GND
```

RN/RP: RT0603BRD0720KL; RF/RB: RT0603BRD0710KL. Specify the two bias-divider resistors in the same RT0603 B/D family: **0.1%, 25 ppm/°C**. Their exact order codes/availability remain a procurement check. Give the op amp local supply bypassing and the reference the manufacturer's recommended layout; select stable filter capacitors. The output capacitor is **after** the isolating 100 Ω, not across U4 outputs. The nominal output RC is 10 µs. Capacitive-load stability and ADC acquisition settling require bench validation.

With matched ratios:

```
VADC = 0.25 + 0.5 × (VBUS_P − VBUS_N)
VBUS_est = (VADC − 0.25) / (0.5 × 15.8 / 1895.8)
```

| Operating point | Nominal receiver output |
| --- | ---: |
| Zero bus | 0.250000 V |
| 170 V bus | 0.958408 V |
| 198 V bus | 1.075087 V |
| U4 differential output = 2 V | 1.250000 V |
| U4 typical positive clipping, differential = 2.49 V | 1.495 V (illustrative) |
| U4 fail-safe differential ≤ −2.5 V | Demands ≤ −1 V; receiver saturates low, classified invalid |

**Load and common mode.** U4 specifies common mode 1.39–1.49 V, a 10 kΩ nominal load (1 kΩ in the maximum-loading column), and maximum capacitance 500 pF/output-to-ground or 250 pF differential [TI SBAS786C pp6,10](https://www.ti.com/lit/ds/symlink/amc1311.pdf). The normal output-pin envelope is 0.39–2.49 V. RN is nominally 20 kΩ and RP+RB is 30 kΩ; their minimum values remain above our conservative 10 kΩ interface requirement. Nominal peak load current is only 74.7 µA. Specify **≤400 pF conductor-to-ground and ≤200 pF between conductors including cable, connector and input parasitics** as a harness acceptance contract, leaving margin to TI's limits. No large input capacitors; no grounded VBUS_N.

OPA2388 supplies can be 2.5–5.5 V; its common-mode range includes both rails. The summing node is nominally 0.630–0.997 V in the normal range. Its specified linear-output test region starts 0.15 V from a rail with a 10 kΩ load; the normal output has margin. Fail-safe saturation is diagnostic, not linear operation. Offset is ≤7.5 µV over temperature and bias current ≤400 pA over 0–85°C [TI SBOS777D pp6–9](https://www.ti.com/lit/ds/symlink/opa388.pdf). The calculation allocates **0.1 mV output error** for active-stage offset, bias, finite gain, source impedance and small supply effects; this allocation must be verified in the assembled circuit.

The local reference's calculated cathode current is **0.584–0.970 mA** at 3.135–3.465 V, within the range used for its error budget and above its 80 µA minimum. Its error allocation is ±3.5 mV at 25°C / ±20 mV over temperature, using the LM4040A25I limits and cathode-current change. See [TI SLOS456Q p9](https://www.ti.com/lit/ds/symlink/lm4040.pdf) and the existing `REFERENCE-BIAS.md` methodology.

Place this stage at the **receiving controller connector**, keeping the pair differential through the harness. Reserve an unshared ADC1 channel or explicitly disconnect the existing V_BUS_SENSE driver in a later controller revision. There is no approved harness or spare-channel allocation today. Power the receiver, ADC and U4 low side from the coordinated SELV rail; permit stays low during rail loss/startup. The series resistors limit injection but do not prove absence of back-powering. Qualify partial-power, open-wire, shorted-pair and ESD cases; the analog transfer alone does not detect every wiring fault.

### ADC use

Select **ADC1, 12 bit, 6 dB attenuation (ATTEN2)** and successful curve-fitting calibration. ESP32-S3 v2.2 p66 Tables 5-5/5-6 gives 0–1600 mV effective range and ±10 mV calibrated total error at 25°C, DC input, external 100 nF and Wi-Fi disabled. DNL/INL are ±4/±8 LSB under those conditions. Avoid interpreting the supply rail or the effective range as ideal ADC full scale; the room-temperature error figure is not a guarantee over temperature, Wi-Fi activity or dynamic operation. [Espressif datasheet](https://www.espressif.com/sites/default/files/documentation/esp32-s3_datasheet_en.pdf)

The proposal produces a **116.679 mV** change between 170 and 198 V; 1 mV maps to **0.239975 V bus**. An idealized 1.6 V/4096 scaling would give **0.09374 V/step**, only a resolution illustration, not a calibrated raw-code law or ENOB claim. Use calibrated millivolts for thresholds. Do not add INL again on top of the datasheet total-error term.

The current HAL silently falls back to a 3100 mV linear scale when calibration is missing or fails (`hal_adc_esp32.c:162–175`), regardless of selected attenuation. **The future bus service must reject that fallback.** It must positively establish calibration success and propagate conversion failures. No firmware edit is made here.

## 3. Accuracy with the unchanged divider

This is an independent-sign, stacked DC calculation, not RSS. No cancellation or matched temperature tracking is assumed. The RT parts' B/D tolerance/TC codes come from [Yageo RT family, ordering table p2 and characteristics pp5–6](https://www.yageogroup.com/content/datasheet/asset/file/PYU-RT_1-TO-0-01_ROHS_L); the top string's 1% / 100 ppm/°C is from [RC1206FR-07470KL, p1](https://www.yageogroup.com/component-documentation/download/specsheet/RC1206FR-07470KL).

| Term | 25°C stack | 0–85°C planning stack |
| --- | --- | --- |
| R26–R29, each | ±1% | ±1%, each independently ±100 ppm/°C × 60°C |
| R30, R36/R37, receiver network and reference divider | ±0.1% | ±0.1%, independently ±25 ppm/°C × 60°C |
| AMC1311B offset / gain | ±1.5 mV / ±0.2% | Add ±1.8 mV / ±0.72144% conservatively using full 180°C box-method span and worst initial gain |
| AMC1311B nonlinearity | ±0.8 mV input equivalent | Same |
| U4 input current | ±15 nA **assumed across VIN** | **±100 nA design allocation** |
| U7 input current on shared tap | ±50 pA | ±5 nA |
| New local reference | ±3.5 mV before /10 divider | ±20 mV before /10 divider |
| Receiver active-stage allowance | ±0.1 mV at ADC | Same allocation |
| ESP32 calibrated ADC | ±10 mV at ADC | Same **qualification target**, not a temperature specification |

AMC specifications: [SBAS786C pp10–11](https://www.ti.com/lit/ds/symlink/amc1311.pdf). Input-bias maximum is specified only at **IN=GND1, 25°C**; extending it across VIN or temperature is an explicit assumption. TC is a box metric, so multiplying it by the limited temperature excursion would not establish a local-slope bound. These are **conditional budgets**, not unconditional worst-case accuracy claims. Missing contributors include qualified leakage versus VIN/temperature, resistor voltage coefficient/aging, EMI, dynamic loading, noise and assembled calibration residuals.

| Bus | U4 VIN nominal | Proposed ADC nominal | Conditional absolute bus error, 25°C | Conditional absolute bus error, 0–85°C |
| ---: | ---: | ---: | ---: | ---: |
| 0 V | 0 | 0.250000 V | 3.318 V | 4.860 V |
| 170 V | 1.416816 V | 0.958408 V | 5.483 V | 9.502 V |
| 198 V | 1.650174 V | 1.075087 V | 5.905 V | 10.430 V |
| 230 V | 1.916869 V | 1.208434 V | 6.387 V | 11.489 V |
| 240 V | 2.000211 V | No accurate prediction | Not all corners linear | Not all corners linear |
| 280 V | 2.333579 V | No accurate prediction | Over-range | Over-range |

Errors are rounded upward from the generated intervals. Current hardware has **no ADC reading at any of these points** because the receiver is absent; the proposed ADC numbers apply to the circuit above. No claimed improvement to U4's own range or accuracy is implied.

Conditional input-limit endpoints, including assumed shared-tap leakage, are **237.332–242.624 V at 25°C**, and **235.403–244.604 V over the planning temperature envelope**. Thus even the unmodified system cannot promise linear measurement on every unit at 240 V. At zero, preserve the signed calibrated residual for diagnostics; do not turn all negative values into plausible zero measurements before validating the channel. Factory zero/span calibration can remove static errors, but no smaller post-calibration budget is claimed without evidence.

## 4. Over-range behavior and firmware rule

Above 2 V input, U4's transfer continues with reduced linearity until clipping near 2.5 V input; 2.49 V differential clipping is typical, not a precision clamp. Missing/undervoltage high-side supply or asserted shutdown instead produces a negative fail-safe differential. Positive over-range is **not** fail-safe, and VDD2 loss is not covered by the high-side fail-safe claim. [TI SBAS786C §8.3.3 p22, electrical limits p10](https://www.ti.com/lit/ds/symlink/amc1311.pdf)

Proposed behavior, with all thresholds in **calibrated millivolts**:

1. Start with PERMIT low. Require valid rails, calibration, fresh samples and plausible line-cycle behavior before accepting the channel. Sampling target: 20 ksample/s; proposed stale deadline: 150 µs. These are service requirements, not latency measurements of today's firmware. The existing 100 Hz control task cannot satisfy them; a later implementation needs a dedicated acquisition/fault path with measured scheduling and gate-disable latency.
2. `BUS_FAULT` asserted always requests shutdown/latch handling, regardless of the analog value. Never debounce away or override hardware protection using U4.
3. Calibration/conversion error, stale data, missing rail or ADC <100 mV ⇒ **SENSOR_INVALID**, inhibit and latch. Negative U4 fail-safe drives this receiver toward its lower rail; a normal zero-bus reading is approximately 250 mV (conditional temperature interval 229.75–270.23 mV), well separated.
4. ADC ≥**1210 mV** ⇒ **BUS_MEAS_OVERRANGE**, inhibit and latch on the next validated raw acquisition. Do not average this decision with earlier low samples. Label it “high bus / measurement over-range”; do **not** report a precise bus voltage or assert that the actual bus is necessarily ≥240 V.
5. Otherwise convert only inside the qualified validity window. The 1210 mV policy deliberately sacrifices part of the nominal upper range. Any impossible high/rail reading is also fault-level. An open or shorted pair may mimic zero; waveform plausibility plus independent fault circuitry is required, and this is not a complete diagnostic-coverage claim.
6. No automatic restart on returning below threshold. Deliberate reset requires cleared hardware latch/fault, restored rail/calibration health, validated line cycles and ADC below a proposed **1100 mV** re-arm level. A low sample during a rectified-bus zero crossing alone must not re-arm the cooker.

At **VIN exactly 2 V**, the lowest calculated ADC is 1.233959 V at 25°C and **1.220590 V** in the planning envelope, both above 1.210 V. Normal 198 V reaches at most **1.118547 V** in that envelope. Thus the conditional design budget gives separation from normal operation and detects the edge of linearity before losing an accurate transfer. Nominal threshold ≈230.4 V; possible crossings are **224.08–236.79 V at 25°C** and **219.24–241.98 V over the planning envelope**. This is an intentional guard, not a new calibrated “240 V comparator.” Qualify these assumptions before treating the rule as guaranteed; U7 remains independent of software but shares the divider electrically.

## 5. Consistency with U7's trip

At 240/260/280 V, the divider still has a predictable input voltage; U4 does not have a specified accurate output once its input leaves the linear region. The following ADC column is an **ideal gain-one extrapolation solely to locate the expected signal region**, not a guaranteed reading/code or an extension of the accuracy table.

| Actual bus | U4 input nominal | Input interval, 25°C conditional | Ideal extrapolated ADC | Expected interpretation |
| ---: | ---: | ---: | ---: | --- |
| 240 V | 2.000211 V | 1.978370–2.022484 V | 1.250105 V | Boundary; guard normally flags it; temperature corners can still be valid on lower-ratio units |
| 260 V | 2.166895 V | 2.143254–2.191006 V | 1.333448 V | Over-range; U7 normally has not tripped |
| 280 V | 2.333579 V | 2.308137–2.359526 V | 1.416790 V | Over-range; U7 may have tripped or may still be below its particular threshold |

**Do not manufacture exact ADC codes above 2 V.** At 260/280 V, only the qualitative increasing/then-clipping behavior is supported; a numeric bus estimate would lack a specified error. A fast jump from normal directly into over-range also depends on dynamic response and software scheduling; the DC guard does not certify shutdown latency.

U7 compares `VSENSE_IN` with `REF25 × R37/(R36+R37)`. Nominal reference is 2.333333 V, giving a **279.970464 V** trip. TLV3201—not TLV3202—has ±3 mV offset at 25°C, ±4 mV over temperature, 50 pA / 5 nA input-bias limits, and 1.2 mV **typical** internal hysteresis. [TI SBOS561C p5, §6.5; p13 Figure 8-3](https://www.ti.com/lit/ds/symlink/tlv3201.pdf)

| Included terms | 25°C bus trip interval | 0–85°C planning interval |
| --- | ---: | ---: |
| R36/R37 tolerance (+TC for temperature column), U7 offset; ideal 2.5 V reference and nominal bus divider | **279.573–280.368 V** | **279.397–280.544 V** |
| Above + bus divider tolerance/TC, shared input-current assumptions, U7 positive-input bias, REF25 ±3.5/±20 mV | **276.111–283.855 V** | **271.902–288.209 V** |

The first row is the requested partial corner stack; the second exposes major omitted terms. **Neither is a complete protection bound**: U7 hysteresis has no maximum here, common-mode/supply effects and transient response remain outside the table, and the U4 leakage allocations require qualification. The typical hysteresis corresponds to about **0.144 V bus**; it is not a worst-case margin. Do not double-count LM4040 TC on top of its full-temperature voltage limit. REF25 regulation depends on the bias conditions already analyzed in `REFERENCE-BIAS.md`.

The over-range guard's latest conditional crossing remains well below the expanded U7 trip region. It is therefore consistent to observe **over-range with U7 healthy** through the gap; do not diagnose an OVP fault merely because these indicators differ. Conversely, U7 at trip drives a shared input already outside U4's linear range, so comparing an extrapolated U4 value with exactly 280 V cannot test U7 accuracy. **J4.10 is aggregate BUS_FAULT**, ORed with bus OCP and CT faults, not an independently observable U7 flag. A high BUS_FAULT with a modest U4 reading is not itself a contradiction. Verify U7 consistency with a controlled ramp and a direct probe of `OVP_OK_HOT`, while separately observing U4 and aggregate BUS_FAULT. No board modifications are proposed for that measurement.

## Acceptance and remaining integration

Items 1, 3, 4 and 5 have proposals and rerunnable evidence; the divider-option task is superseded. The retained divider covers normal 170–198 V use. **An unconditional 0–240 V accuracy approval is not supported** by the endpoint corners, missing system requirement or unavailable full-range device/system limits.

Owner/integration decisions remaining: accept or replace the proposed coarse accuracy/timing targets; allocate an unshared ADC and receiving connector; approve the 1210 mV early-fault policy and manual re-arm behavior. Physical qualification must cover leakage, ADC calibration over environment/Wi-Fi, harness capacitance, receiver settling/fail-safe recovery, actual zero-cross windows, partial power and U7 ramp/trip timing. These are conditions for implementing/enabling the proposal, not requests to change R26–R30 or U7.

## Reproduce and checks

From repository root (Python 3.12, standard library only):

```sh
python3.12 zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D11/bus_sense.py > /tmp/d11-bus-sense.json
diff -u zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D11/bus_sense.json /tmp/d11-bus-sense.json
```

Run the arithmetic checks with `python3.12 -m unittest discover -s zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D11 -p "test_bus_sense.py" -v`.

The script enumerates independent receiver resistor/reference/common-mode corners and solves both threshold endpoints, checking that each selected corner crosses inside its own linear range. The maximum top-string resistance and minimum bottom resistance give minimum divider ratio, and vice versa. Input loading uses the maximum Thevenin resistance. U7 threshold and bus-divider extremes are stacked with independent signs. Runtime and input hashes are recorded; a different Python patch version changes its runtime field. See [validation.txt](validation.txt) for actual checks. No native build, SPICE or physical measurement was performed.
