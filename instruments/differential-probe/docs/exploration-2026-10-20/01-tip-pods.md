# Potted divider tip pods and coax: research decision

Research date: 2026-10-20. Baseline: Rev B `README.md`, `docs/design.md`, `docs/circuit-revb.md`, and `docs/layout.md`. This explores a replacement architecture; it changes no released geometry or voltage qualification.

**Verdict:** tip-mounted dividers merit a low-voltage experiment. They can remove long, unattenuated HV leads and much of the central box's HV space. A metre of ordinary coax is not merely another 100 pF across the 13 nF compensation bank. Potting and a printed shell can stabilize geometry, but cannot supply an insulation rating from bulk dielectric-strength data.

## What connects to the cable?

Each unchanged upper ladder is ideally `10 MΩ || 6.6 pF`; the bottom is `5002.501 Ω || 13.1934 nF`, giving 2000:1. Two distinct arrangements need testing:

- **Upper ladder in pod; complete bottom in box:** coax is inside the divider. Its source impedance, termination and distributed inductance affect attenuation.
- **Complete divider in pod; high-impedance receiver in box:** coax loads the local tap. Moving the bottom capacitor alone does not create a matched cable driver. The bottom resistor must also remain locally connected if the pod is to retain its DC divider when unplugged.

[Belden 8259](https://www.belden.com/products/cable/coax-triax-cable/50-ohm-coax-cable/8259) specifies nominal 101 pF/m, 50 Ω and 66% propagation velocity. These imply **5.054 ns/m and 253 nH/m**, with 9.10° electrical length at 5 MHz. Nominal 1900 V cable rating is not approval for this probe's fault conditions or accessible connectors.

Calculated lossless-line example: subtract the cable's nominal capacitance from the bottom bank, preserving the lumped-RC compensation assumption. Let `Zu=(1/10M+jω6.6p)^−1`, `Zb=(1/5002.501+jωCb)^−1`, and `θ=ωl/v`. Line ABCD terms are `A=D=cosθ`, `B=j50sinθ`, `C=j sinθ/50`. With the bottom in the box:

`H = 1 / [A + Zu C + (B + Zu D)/Zb]`.

With the complete bottom in the pod and an ideal open receiver:

`H = 1 / [A(1 + Zu/Zb) + Zu C]`.

| Cable | Gain error at 5 MHz, bottom in box | Bottom in pod |
|---|---:|---:|
| 0.3 m | +0.163% | +0.113% |
| 1 m | +1.434% | +1.267% |
| 2 m | +5.560% | +5.206% |

These are **analytical calculations**, excluding cable resistance/loss, receiver capacitance, ladder-node strays and protection. At 60 kHz, the 1 m box-bottom error is only +0.000204%. The ideal passive transfer's phase is near zero: do not automatically assign the cable's flight-time phase to this strongly mismatched network. Nor should the cable-inductance/13 nF resonance estimate be presented as a measured probe resonance; the complete network sets its poles.

A parallel 50 Ω termination changes the DC divider to approximately 200,001:1. Keeping 2000:1 with a 50 Ω bottom instead requires about 100 kΩ upstairs and **90 W at 3 kV DC**. Properly driven, terminated coax therefore means a new active architecture, not a termination resistor added to Rev B. Tektronix describes the [local buffer/cable driver approach](https://download.tek.com/document/60W_15661_1.pdf).

## Matching, current and detachable connections

60 dB CMRR allows approximately **0.1% complex leg mismatch**, before amplifier errors consume their share. A matched, buffered cable pair alone would need delay mismatch below `0.001/(2π·5MHz)=31.8 ps`, approximately 6.3 mm of this cable. Passive-divider length sensitivity follows the equations above instead; independently capacitance-trimmed 1.00/1.05 m box-bottom legs calculate only about **57 dB** at 5 MHz. Cable capacitance matching alone is insufficient. Specify paired length, cable type, temperature and routing, then calibrate the complete assemblies.

The intended 6.6 pF still draws **5.28 mArms at 3 kVpk/60 kHz** and **0.462 A at 70 V/ns**, before shell/ladder strays. A grounded pod screen close to HV can increase both. Every extra 1 pF adds 0.800 mArms and 70 mA respectively. Coax downstream of attenuation avoids putting its entire 101 pF directly on the DUT, but carries return/displacement current through its shield and box bond.

With the bottom only in the box, an unplugged centre conductor can charge toward the tip voltage through the ladder. A local bottom loses its earth reference if the shield disconnects. Nominal ±1.5 V cable signal at a 3 kV tip does not establish touch safety. Prefer captive paired cables initially; detachable versions need explicit open-centre/open-shield, sequencing, connector-access and upper-component-fault analysis. Potting does not resolve these circuits.

## What resin and potting evidence actually supports

[Formlabs electrical tests](https://formlabs.com/support/Electrical-properties-of-selected-Formlabs-SLA-resins/) report High Temp **V1** average breakdown strength of 30.4 kV/mm on 28 mil specimens, tested at 60 Hz with a 500 V/s ramp. That is not a continuous working-voltage or impulse rating. Their separate High Temp **V2** RF data gives εr 3.39 and tanδ 0.021 at 6.78 MHz; versions are not interchangeable. Published CTI examples concern other resins. Exact resin, cure and assembly remain selections.

[Dow SYLGARD 184](https://www.dow.com/en-us/pdp.sylgard-184-silicone-elastomer-kit.01064291z.html) is an electrical encapsulant with typical εr 2.72 at 100 Hz, 450 V/mil dielectric strength and 0.27 W/m·K thermal conductivity. Those properties support evaluation, not dividing 3 kV by strength to select wall thickness. Voids, adhesion interfaces, moisture, thermal cycling and field concentration remain unknown. [Formlabs also warns](https://formlabs.com/uk/white-papers/silicone-part-production-with-3d-printed-tools/) that some PDMS formulations suffer cure inhibition against SLA tooling. Test the actual pairing; do not casually change an electrical encapsulant's mix ratio to cure an interface problem.

## Size benefit and next experiment

The present LV region is approximately **112 × 84 mm**, 53% less PCB area than the full 240 × 84 mm board. Two illustrative **110 × 20 mm** pod boards plus that LV region total 13,808 mm², about 32% less aggregate PCB area. These are packaging estimates, excluding shell walls, insulation distances, tips, strain relief and batteries. There is no demonstrated packaged-volume reduction or loading reduction; 0.9 W per pod at 3 kV DC also needs thermal measurement.

Build two unpotted passive coupons with captive 0.3 m paired cables, comparing complete bottoms in the pods against bottoms in the box. At low voltage measure complex gain, common-mode residual and step recovery through 5 MHz; repeat after cable bending and temperature changes. Then pot one matched pair and repeat, checking cure cross-sections and capacitance changes. Require ±2% amplitude/≤1° corrected phase at 35–60 kHz and a frequency-resolved CMRR budget before choosing the architecture. Insulation, partial-discharge and fault qualification follow on the actual assembly under the simultaneous per-tip and differential envelopes; none has been demonstrated here.
