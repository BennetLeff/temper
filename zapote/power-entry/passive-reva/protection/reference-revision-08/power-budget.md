# Reference revision 08: Control Freak-class input-power budget

This is a planning budget for Temper's PFC and downstream inverter. The
comparison target is the **appliance input nameplate class** of the US
Breville/PolyScience Control Freak CMC850: 120 V AC, 60 Hz, 1800 W. It is not a
claim that Temper should produce 1800 W on the DC bus or deliver 1800 W to a
pan.

The manufacturer-authored one-page technical specification lists a 100–1800 W
power range and `120 V ~ 60 Hz / 1800 W` for CMC850BSSUSA/CMC850BSSUSC
([specification PDF](https://www.webstaurantstore.com/documents/specsheets/specsheet_for_polyscience_cmc850bssusa_induction_cooking_system.pdf),
accessed 2026-09-21). It is hosted by a distributor; the Breville-hosted
[CMC850 instruction book](https://www.breville.com/content/dam/breville/us/en/assets/miscellaneous/instruction-manual/commercial/CMC850-instruction-manual.pdf)
identifies the CMC850 and the North American 120 V version. These sources do
not establish Temper's efficiency, PF waveform, auxiliary consumption,
low-line behavior, DC output, or pan-heating performance.

## Definitions and equations

Use RMS quantities at the appliance input:

* `S_VA = V_rms × I_rms` is apparent power.
* `P_W = S_VA × PF` is real input power. PF includes displacement and
  distortion effects; it is not interchangeable with efficiency.
* `P_mains_limit(V) = min(1800 W, V × 15 A × PF)` applies the existing 15 A
  RMS screen and the 1800 W nominal mains cap.
* `P_dc_bus = η_PFC × P_mains` is the proposed AC-to-DC bus budget.
* `P_inverter = P_dc_bus − P_aux` assumes auxiliaries draw from the DC bus.
  `P_aux` is a provisional bus-side allocation for bias, fans, sensing and
  housekeeping; the actual supply topology is not bound. If auxiliaries
  instead draw directly from AC, use `η_PFC × (P_mains − P_aux_AC)` with
  their AC input consumption. Do not mix AC input watts and DC output watts.

The last two equations are an allocation model, not measured Temper data.

## Planning assumptions

| Quantity | Planning value/range | Status and implication |
|---|---:|---|
| Nominal mains benchmark | 120 V AC, 60 Hz, 1800 W | External nameplate comparison; not a vendor efficiency or pan-power claim |
| Input-current screen | 15 A RMS maximum | Existing campaign screen retained; applies to the complete appliance when hardware is measured |
| Power factor | 0.99 nominal illustration; 0.97–1.00 sensitivity | Assumption only; confirm with synchronized voltage/current capture |
| PFC efficiency, `η_PFC` | 0.95 nominal illustration; 0.93–0.97 sensitivity | Assumption only; no PMP10948 or other reference efficiency is inherited |
| Physical DC auxiliaries, `P_aux` | 20 W nominal illustration; 10–30 W sensitivity | Assumption only; current ideal-aux simulation omits this draw |
| Downstream inverter/pan conversion | Not budgeted as a guaranteed efficiency | Requires a separate inverter and cooking-performance measurement |

## 108/120/132 V budget

The table uses PF 0.99 for the current-limited cases, `η_PFC = 0.95`, and
`P_aux = 20 W` for the nominal illustration. `S` is the apparent-power value
at the 15 A screen. The 132 V row is cap-limited before 15 A is reached.

| Line voltage | 15 A apparent limit `S` | Real-power ceiling `P_mains_limit` | Current at that ceiling | `P_dc_bus` at η=0.95 | `P_inverter` after 20 W aux |
|---:|---:|---:|---:|---:|---:|
| 108 V | 1620 VA | 1603.8 W (`108×15×0.99`) | 15.000 A | 1523.6 W | 1503.6 W |
| 120 V | 1800 VA | 1782.0 W (`120×15×0.99`) | 15.000 A | 1692.9 W | **1672.9 W** |
| 132 V | 1980 VA | 1800.0 W (nominal cap) | 13.774 A | 1710.0 W | 1690.0 W |

The nominal illustration is therefore 1672.9 W into the inverter at 120 V,
not 1800 W DC and not 1800 W pan heat. Reaching exactly 1800 W real input at
120 V while holding a 15 A RMS maximum requires PF = 1.000; at PF 0.99 it
would require 15.152 A and must be folded back. The 108 V ideal-PF bound is
1620 W, while PF 0.99 lowers the planning ceiling to 1603.8 W.

## Sensitivity to PFC efficiency and auxiliary draw

For each row, `P_inverter_low = 0.93 × P_mains − 30 W` and
`P_inverter_high = 0.97 × P_mains − 10 W`:

| Line voltage | `P_mains` used | Inverter input low (η=0.93, aux=30 W) | Nominal (η=0.95, aux=20 W) | Inverter input high (η=0.97, aux=10 W) |
|---:|---:|---:|---:|---:|
| 108 V | 1603.8 W | 1461.5 W | 1503.6 W | 1545.7 W |
| 120 V | 1782.0 W | 1627.3 W | 1672.9 W | 1718.5 W |
| 132 V | 1800.0 W | 1644.0 W | 1690.0 W | 1736.0 W |

The 91.28 W spread at 120 V is an assumption sensitivity, not an uncertainty
interval for a built unit. It should be replaced by measured losses and
auxiliary power before freezing a bus or inverter rating.

## Low-line foldback requirement

At 108 V, a controller requesting 1800 W at PF 0.99 would require
`1800/(108×0.99) = 16.84 A`, above the retained 15 A screen. The control law
must therefore reduce real input power to at most 1603.8 W under the PF 0.99
planning case (or demonstrate a measured PF high enough to justify a different
ceiling). This is an electrical operating-envelope requirement, not a claim
about the Control Freak's internal low-line implementation and not a branch-
circuit conclusion.

At 120 V the same rule gives 1782 W at PF 0.99. At 132 V the 1800 W nominal
cap is reached at 13.774 A, leaving current headroom but no permission to
increase the nameplate target.

## What the existing campaign does and does not cover

The accepted operating matrix has nine discrete PFC-model points. Its largest
declared resistive output is 1392.35 W (132 V) and its limiting input screen is
13.412 A at 108 V/1242.52 W. Those are authored-model screens. The campaign
uses ideal auxiliary rails and does not model a complete appliance containing
the induction inverter, fans, controller bias, or real auxiliary power. Its
`I_rms` values therefore cannot be relabeled as full-appliance current or as
evidence of 0.99 PF/0.95 efficiency. It also has no measured 1800 W input
point, no continuous thermal result, and no pan-heating result. See
[power target 105](../operating-matrix-07/host/power-target-105.md),
[campaign report 139](../operating-matrix-07/host/campaign-report-139.md), and
[normal-screen margins 89](../operating-matrix-07/host/normal-screen-margins-89.md).

## Proposed acceptance requirements for this revision

1. At 108, 120, and 132 V RMS, capture synchronized line voltage, complete
   appliance line current, real power, VA, and PF over the same settled window.
   Report RMS current for the whole appliance; do not substitute the ideal-aux
   PFC trace.
2. Enforce `P_mains ≤ min(1800 W, V×15 A×PF)` over the declared settled RMS
   measurement window. Choose separate startup/inrush limits and windows;
   this steady-state equation is not an instantaneous trip rule.
   Verify the 108 V foldback rather than interpolating from the existing nine
   points.
3. Measure PFC input power, DC-bus power, and each physical auxiliary rail so
   `η_PFC` and `P_aux` can replace the planning assumptions. Include fan speed,
   controller bias, and inverter idle/active states.
4. Demonstrate the 120 V nominal point at the selected target (1782 W for the
   PF 0.99/15 A planning case, or 1800 W only with measured PF/current that
   satisfies both caps) for a sustained interval with bus ripple, magnetic
   temperature, semiconductor stress, and capacitor ripple recorded.
5. Qualify the downstream inverter separately. A DC-bus or inverter-input
   result must not be reported as pan power; cooking parity needs defined
   cookware, contents, heat-up, temperature stability, disturbance recovery,
   and sustained-operation measurements.
6. Re-run protection and fault qualification on the revised topology. The
   current diode-short, failed-switch, and local-VD findings cannot be carried
   over by arithmetic budget alone.
