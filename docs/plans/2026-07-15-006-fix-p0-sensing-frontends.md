---
title: "fix: Sensing front-ends — CT bias, NTC thermal, ZCD, bus ADC"
type: fix
status: pending
date: 2026-07-15
origin: docs/audits/2026-07-15-atopile-electrical-design-audit.md
depends_on: [2026-07-15-003]
blocks: []
---

# fix: Sensing Front-Ends — CT, NTC, ZCD, Bus ADC

## Summary

Four sensing circuits are either missing critical components or have floating
inputs that make them non-functional:

1. **P0-6:** Current transformer primary is not in series with any current
   path (declared `required = true` but never connected). The burden output
   is bipolar AC fed directly to the ESP32 ADC with no DC bias.
2. **P0-5:** Thermal protection has no NTC thermistor — the `ntc_sense` net
   floats between the comparator input and the MCU ADC pin. The reference
   network is also degenerate.
3. **P1-1:** Zero-crossing detection (`zcd`) signal exists but no detection
   circuit (high-value divider or opto-coupler from AC line) is present.
4. **P1-2:** Bus voltage ADC input (`adc_v_bus`) is required by the MCU
   module but no resistive divider feeds it — only the (broken) OVP
   comparator divider exists on the `v_bus` net.

## Problem Frame

### P0-6: Current transformer

**File:** `modules.ato:652-679` (CurrentSensing module)

**Primary (open):**
```ato
signal primary_in          # line 657
primary_in.required = true # line 658
```
In `main.ato:272-276`, only `i_sense` is connected. `primary_in` is never
wired — the CT primary must be in series with the tank current path
(either the tank output to ground path, or the half-bridge output to
tank path). The `required = true` flag should have caused `ato build` to
fail; investigate why it didn't (possible atopile bug or the required
check is not enforced for signal-in-module ports).

**Output (no bias):**
The burden resistor produces a bipolar AC voltage proportional to current.
The ESP32 ADC (GPIO1) can only measure 0-3.3V unipolar. Negative half-cycles
clamp through the ESP32's internal protection diodes — only one current
polarity is measured. A 1.65V mid-rail bias is needed:
- VCC_3V3 → 10k → I_SENSE → 10k → GND (resistive divider for 1.65V bias)
- Add an AC-coupling cap between the burden resistor and the bias node
- Add a series resistor (1k) and clamp diodes for ADC protection

**Alternative:** Precision half-wave rectifier + filter cap — simpler but
loses zero-crossing information and introduces measurement lag.

### P0-5: Thermal NTC

**File:** `modules.ato:1034-1067` (ThermalComparator module)

**Missing NTC:**
No NTC thermistor component exists in the design. The only NTC is
`NTC_Inrush` (`components.ato:136`) for inrush limiting — it's not a
thermal sensor. The `ntc_sense` net connects from MCU GPIO3 to the
ThermalComparator's comparator input with no sensing element bridging
the two.

**Degenerate reference:**
```ato
r_ref = new Resistor
r_ref.value = 10kohm
r_ref.tolerance = 1%

r_hyst = new Resistor
r_hyst.value = 100kohm
```
With only a 10k pull-up (r_ref) to VCC and a 100k hysteresis feedback to
the output but no bottom-leg resistor, INP sits at ~3.3V regardless of
output state (the 100k is effectively open when the comparator output is
high-impedance, or pulls to ~VCC through 10k||100k ≈ 9.1k equivalent).
This is not a meaningful temperature threshold.

**What's needed:**
- An NTC thermistor (e.g., 100k NTC at 25°C) physically mounted on the
  heatsink
- A resistor divider: VCC → R_fixed → NTC → GND, with the tap at
  `ntc_sense`
- A reference divider that sets the trip point: VCC → R_top → R_bot → GND,
  with tap at `comp.INP`
- The hysteresis resistor (r_hyst) feeds back from comparator output to INP
  (not INN) to create positive feedback

### P1-1: Zero-crossing detection

**File:** `modules.ato:367` (PowerInput module — `signal zcd`)

The `zcd` signal is declared and routed to MCU IO13 at `main.ato:348` but
there is no detection circuit. A ZCD circuit needs:
- **High-value resistive divider from AC line:** e.g., two 1M resistors in
  series from AC_L, with a 100k to ground. Tap at the junction gives ~3V
  peak at 120VAC.
- **Or an opto-coupler:** H11L1 or similar with AC input — provides
  isolation and a clean digital edge at the zero-crossing. Preferred for
  noisy environments.
- **Clamping:** The MCU pin must be protected from transients — a 3.3V zener
  or BAT54S dual diode to VCC/GND at the MCU input.

### P1-2: Bus voltage ADC

**File:** `modules.ato:1259-1260` (MCU module)

`adc_v_bus.required = true` at GPIO2, but no divider feeds it. The
`v_bus` net exists for the OVP comparator (plan 004 fixes that circuit)
but no separate scaled-down version exists for the ADC.

**What's needed:**
- A resistor divider from `dc_bus_plus` (the half-bus, ~170V nominal) to
  ground: e.g., 200k + 10k → 170V → 8.07V — still exceeds ADC range
- Corrected: 2M + 10k → 170V → 0.845V (safe for 3.3V ADC, but high impedance)
- Better: Use a dedicated divider (e.g., 510k + 10k) with a 100nF bypass
  cap to ground for ADC input filtering
- The divider should be separate from the OVP comparator divider to avoid
  loading and noise coupling

## Scope Boundaries

### In scope
- Add CT primary wiring to the tank current path in `main.ato`
- Add DC bias network to the CT sense output in the CurrentSensing module
- Add NTC thermistor component and reference divider to the ThermalComparator
  module
- Add ZCD detection circuit (opto-coupler or resistive divider) to the
  PowerInput module
- Add bus voltage ADC divider separate from the OVP divider
- Verify all new circuits with atopile assertions for voltage ranges

### Deferred
- Calibration of CT burden resistor value (depends on actual CST-1005 turn
  ratio — see plan 008 for BOM verification)
- NTC thermistor selection (depends on heatsink thermal interface
  mechanical design)
- ADC firmware calibration and filtering

### Out of scope
- MCU firmware changes for sensor reading
- PCB layout optimization for analog signal routing

## Implementation Units

### U1. CT primary wiring + output bias

**File:** `elec/src/main.ato` — route `ct_sense.primary_in` in series
with the tank current path (e.g., between `tank.out` and ground, or
between the half-bridge output and the tank input).

**File:** `elec/src/modules.ato` — add DC bias network to the
CurrentSensing module:
```ato
# Bias network: VCC 3.3V → 10k → I_SENSE → 10k → GND
# AC coupling from burden resistor to bias node
# ADC protection: 1k series + BAT54S clamp
```

### U2. NTC thermistor + reference fix

**File:** `elec/src/modules.ato` — ThermalComparator module

Add:
- NTC component (100k at 25°C, B=3950 or similar)
- Fixed resistor for the NTC divider (e.g., 100k to VCC, NTC to GND,
  tap at `ntc_sense` → 1.65V at 25°C)
- Bottom-leg resistor for the reference divider so INP sits at a defined
  trip threshold (e.g., 100°C trip → NTC resistance ~6.8k → V_INN ~0.22V
  with 100k pull-up; set V_INP via divider to ~0.22V)
- Verify hysteresis resistor polarity (should feedback to INP, not INN)

**File:** `elec/src/main.ato` — connect the NTC to the `ntc_sense` net
(was expected to be external)

### U3. ZCD detection circuit

**File:** `elec/src/modules.ato` — PowerInput module (option: opto-coupler)

Add:
```ato
# Option A: Opto-coupler (preferred for noise immunity)
# H11L1 or similar with AC input — series resistor from AC_L through
# opto LED, zcd output is open-drain, pulled up to 3.3V at MCU
#
# Option B: Resistive divider (simpler, no isolation)
# AC_L → 220k → 220k → zcd → 10k → GND
# with 3.3V zener clamp at the zcd node
```

### U4. Bus voltage ADC divider

**File:** `elec/src/modules.ato` — add a bus ADC divider in the
appropriate module (PowerManagement or a new BusMonitor module)

```ato
# 340V full-scale → half-bus = 170V nominal
# Divider: 510k + 10k → V_ADC = 170 × 10/(510+10) = 3.27V at 170V
# (stays within 3.3V ADC range)
# 100nF bypass cap at ADC input for filtering
```

**File:** `elec/src/main.ato` — wire the new divider output to
`mcu.adc_v_bus`

## Test Strategy

1. **CT:**
   - Without HV: inject a known current (e.g., 1A RMS from a function
     generator + power amp) through the CT primary and verify ADC reading
   - Verify DC bias is ~1.65V with no current
   - Verify both positive and negative half-cycles produce ADC readings
     above and below 1.65V

2. **NTC:**
   - Measure voltage at `ntc_sense` at room temperature and verify it
     matches the expected divider output for the selected NTC
   - Heat the NTC (hot air gun) and verify the comparator trips at the
     designed threshold
   - Verify the hysteresis band (output toggles cleanly without
     oscillation near threshold)

3. **ZCD:**
   - Apply low-voltage AC (e.g., 12VAC from a transformer) to the AC
     input and scope the ZCD output — verify clean digital edges near
     the zero-crossings
   - Verify no 50/60 Hz noise on adjacent ADC channels

4. **Bus ADC:**
   - Apply a known DC voltage to the divider input and verify ADC
     reading is within 1% of calculated value
   - Verify the divider doesn't load the OVP comparator path (separate
     dividers ensure independent operation)

## References

- Master audit: `docs/audits/2026-07-15-atopile-electrical-design-audit.md`
- Plan 003: Grounding architecture (affects CT grounding)
- Plan 004: OVP comparator fix (bus divider is separate from ADC divider)
- CST-1005 datasheet: turn ratio verification (plan 008)
- ESP32-S3 datasheet: ADC input impedance, sampling time requirements
