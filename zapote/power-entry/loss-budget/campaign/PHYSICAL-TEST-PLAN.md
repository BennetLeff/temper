# PFC switching-loss measurement — physical test plan (proposal)

Date: 2026-09-17
Status: **PROPOSAL — NOT AUTHORIZED.** The campaign plan explicitly authorizes
no purchase, fabrication or powered bench operation. Nothing in this document
may be executed until a qualified engineer, working under the site's electrical
safety process, separately approves it. This is a scope and comparison
specification, not an authorization.

Campaign context: [CLOSEOUT.md](CLOSEOUT.md). Evidence commit
`a975fff03e5599d805d19da3788e9e756d6b809d`.

## 1. Why this measurement

Every model-based result in the campaign depends on one number: the boost
switch's switching energy. The retained analytic model attributes 37.37 W of
the 45.50 W baseline switch/gate subtotal to switching overlap, and an
independent vendor-model double-pulse simulation disagrees by ~30% (26.76 W for
the baseline device). Two external references could not anchor the term at all,
and the largest claimed lever in the whole campaign — the retained board device
STW65N65DM2AG costing ~2.05x the C7 on switching (93.183 W vs 45.5023 W) —
has neither a reachable vendor model nor a datasheet energy curve.

This measurement closes that gap. It is the only remaining item in the campaign
that requires bench time.

## 2. What the result decides

| Outcome | Decision it enables |
| --- | --- |
| measured STW-to-C7 switching ratio >= 1.5 | The board part is the wrong part; a device swap is the primary heat fix, and its size is known. |
| measured ratio 1.2-1.5 | Swap is worthwhile but modest; weigh against the bridge (Section 8). |
| measured ratio < 1.2 | The analytic model's largest claim is wrong; the device axis is not the lever, and the bridge becomes the lead target. |
| measured C7 energy far from both models | The whole switching model is unusable; re-derive before ranking anything. |

## 3. Devices under test

| Priority | Device | Role |
| --- | --- | --- |
| P0 | `STW65N65DM2AG` | the retained board part; the unverified large lever |
| P0 | `IPW65R045C7` | C1 baseline; also the control that ties this measurement to the frozen models |
| P1 | `IPZ60R040C7` | K-SILICON candidate; independently the best switching device found |

Same package (TO-247) for P0; the fixture should accept all three.

## 4. Conditions to reproduce (frozen)

These are the exact conditions the two models were evaluated at, so the
measured energies are directly comparable. Do not "improve" them.

- **Bus voltage:** 400 V DC clamp (measure at the device terminals, not the
  supply output).
- **Gate drive:** 0 -> 12 V; **external gate resistance 9.7 ohm turn-on /
  5.3 ohm turn-off** (the retained `no-assist` buffered drive: 4.7 ohm external
  plus 5.0/0.6 ohm driver path). Record the actual measured edge and any
  driver-source/sink current limit.
- **Turn-on current:** 11.95 A; **turn-off current:** 15.01 A. Sweep at least
  8 / 12 / 15 A so the energy-vs-current slope is visible.
- **Case temperature:** 25 C and 125 C set-points. State how temperature was
  established and held (hot-plate or heater), and measure case temperature, not
  ambient. A two-second double pulse will not reach a settled junction; report
  case temperature and state the junction-temperature limitation explicitly.
- **Freewheel diode:** use the retained boost diode if available
  (`C3D20065D`); otherwise state the substitute and its SiC technology. The
  vendor simulation quantified a substitute as +1.0% on `Eon+Eoff`; expect a
  similar-order effect here.
- **Clamp inductor:** sized to reach the test currents without saturating; it is
  a test element, not the PFC boost choke. State its value and saturation
  current.

## 5. Apparatus (minimum)

- Isolated DC bus supply, 400 V, current-limited, with a low-inductance film
  bus capacitor bank.
- Clamped-inductive double-pulse fixture with the DUT, freewheel diode, and
  clamp inductor.
- Gate driver reproducing 9.7/5.3 ohm and 0 -> 12 V, with a clean single-pulse
  input.
- **High-voltage differential voltage probe**, >= 1 kV, >= 100 MHz, measuring
  `V_ds` at the device pins (not at the bulk capacitor).
- **Current transducer**: coaxial shunt or Rogowski, >= 30 A, >= 50 MHz
  bandwidth, in the device source/drain path.
- Gate-voltage probe.
- Oscilloscope >= 500 MHz, >= 2 GS/s, >= 4 channels.
- Thermal fixture for the 25/125 C points.

## 6. Method

1. **Deskew V and I before any measurement.** Measure the residual probe skew
   with a known resistive or reference edge and report it. Skew is the largest
   systematic error in an `Eon`/`Eoff` integration; an unreported skew makes the
   number non-comparable to the models.
2. Apply a single double pulse; capture `V_ds(t)` and `I_d(t)`.
3. **Define the integration window by a stated rule** (e.g. from the 10% point
   of the current rise to the point where `V_ds` reaches its on-state value)
   and record it. Report the sensitivity of the result to a +/-10 ns window
   shift, exactly as the simulation did (+0.087% for `Eoff`).
4. `Eon = INT V_ds(t) * I_d(t) dt` over the turn-on window; `Eoff` likewise over
   the turn-off window.
5. **State the `Eoss` convention.** `Eon` from a hard-switched clamp may or may
   not include the Coss discharge. Report both `Eon_including_Coss` and
   `Eon_excluding_Coss`, and measure or source `Eoss(400 V)` separately. The
   analytic model books `Eoss` separately (1.5106 W at this point); the vendor
   simulation measured 9.76 uJ. Do not double-count.
6. Repeat at least 10 pulses per condition; report mean and spread. Discard and
   re-run on any probe or fixture fault; never average across a fault.
7. Repeat for each device and both temperatures.
8. Retain raw oscilloscope files, not screenshots alone.

## 7. Comparison targets and acceptance criteria

Frequency-weighted comparison, `f = 129107.39198576905 Hz`, at 25 C:

| Quantity | Analytic model | Independent vendor model |
| --- | ---: | ---: |
| IPW65R045C7 `Eon` | — | 102.50 uJ @ 12.07 A |
| IPW65R045C7 `Eoff` | — | 104.79 uJ @ 14.99 A |
| IPW65R045C7 `Eoss(400 V)` | 11.7 uJ (datasheet) | 9.76 uJ |
| IPW65R045C7 `(Eon+Eoff)*f` | 37.368 W (overlap term) | 26.76 W |
| IPW65R045C7 total switch+gate | 45.5023 W | — |
| STW65N65DM2AG total switch+gate | 93.183 W | not obtained |
| STW65N65DM2AG / IPW65R045C7 ratio | 2.05x | not obtained |

Acceptance, to be confirmed by the authorizing engineer before the test:

- **Control:** if measured C7 `(Eon+Eoff)*f` is within +/-25% of 26.76 W, the
  vendor model is corroborated and the correction applies to everything derived
  from it. If it lands near 37.4 W instead, the analytic model was right and the
  vendor model is not usable.
- **Lever:** the STW-to-C7 switching ratio (Section 2).
- Report an explicit uncertainty band; a bare point value is not an acceptable
  receipt.

## 8. Optional companion measurement (recommended, lower risk)

The input bridge is the largest *certain* term (28.30 W) and its datasheet
carries exactly one forward-drop test point (1.05 V at 12.5 A, 25 C). A simple
`V_F(I)` sweep on `GBJ2510-F` — DC or low-frequency, no fast probes needed —
would replace a 0.85/1.30 V assumption band with measured data at the real
currents and temperatures, and would firm up the campaign's second-largest term
for far less effort than the switching test. Consider running it in the same
session.

## 9. Safety

400 V DC is lethal, and DC arcs do not self-extinguish at zero crossing.

- Qualified personnel only, under the site's electrical safety process; no lone
  work.
- Isolate and lock out before changing the fixture; verify dead before touch.
- Discharge and verify the bus capacitor bank before every intervention.
- Treat the double pulse as live at all times the bus is charged.
- Rated PPE and an appropriate safe-work distance; use differential probes and
  isolated supplies as intended.
- This document does not constitute a safety assessment. The authorizing
  engineer owns the hazard analysis.

## 10. What to retain

Raw oscilloscope captures, probe calibration and deskew records, fixture
schematics, actual measured temperatures, per-pulse energies and spread, the
integration-window rule and its sensitivity, `Eoss` convention, and SHA-256 of
every file. The receipt must separate measured from modelled quantities and
must leave `hardware_qualification` state explicit.

## 11. Authorization

```text
authorizing engineer:
approval reference:
approved apparatus / facility:
hazard analysis reference:
approved conditions (any deviation from Section 4):
date:
```
