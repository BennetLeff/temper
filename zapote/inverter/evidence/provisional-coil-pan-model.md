# Provisional coil and cookware model for inverter exploration

Date: 2026-09-23. **Status: exploratory design input, not a selected product coil, operating envelope, pan population, or hardware qualification.** This makes the existing nominal coil assumption useful for sensitivity work while retaining the U3 measured-article gate. The user has no physical coil or pan article yet.

## Choice and review

Use the **170 mm replaceable coil shipped with Infineon's EVAL-IHW25N140R5L kit** (`EVALIHW25N140R5LTOBO1`) as the first purchasable *reference assembly*. Infineon's [product page](https://www.infineon.com/evaluation-board/EVAL-IHW25N140R5L) identifies the coil and 2 kW-class kit; its [user guide, Figure 16](https://www.infineon.com/dgdl/Infineon-EVAL-IHW25N140R5L-UserManual-v01_00-EN.pdf?fileId=8ac78c8c8afe5bd0018b18c78e023a8d) charts that kit's no-vessel and one-vessel impedance versus frequency. The chart reads at about 40 kHz are `L_no ≈ 87 µH`, `R_no ≈ 0.34 Ω`, `L_vessel ≈ 60 µH`, `R_vessel ≈ 3.25 Ω` per the existing [tank-coil specification](../../../docs/hardware/TANK_COIL_SPECIFICATION.md) §5. These are *chart readings*, not guaranteed specifications. The coil has no separately published ordering number, winding specification, temperature/current rating, unit-to-unit distribution or Temper installation drawing. Buying the kit would secure a reference sample, not approve a production coil. Its supplied inverter is single-ended; Temper's proposed Rev38 inverter is a different half-bridge topology.

For a later identified reference pan, a [Lodge 10.25-inch cast-iron skillet](https://www.lodgecastiron.com/products/lodge-10-25-inch-seasoned-cast-iron-skillet-usa-icons) has a manufacturer-published 8-inch (about 203 mm) flat bottom and is induction-compatible. This is a **geometry and material candidate only**. Infineon's plotted vessel is not identified as that skillet, so no measured `L` or `R` is attributed to Lodge. Obtain the exact article and record its flat-bottom diameter and base condition before using it as the campaign's reference.

The design choices were: keep one nominal 60 µH / 3.25 Ω vessel (too narrow); invent a pan usage frequency and report Monte Carlo percentiles as if empirical (unjustified); or use **joint impedance scenarios plus explicit stress corners**. The third path is chosen. Probabilities can rank likely cooking behavior after a pan mix is observed or deliberately adopted; protection and component sizing still use bounded adverse cases, including no pan and removal. The latter are modes/faults, not tails to discard at a chosen percentile.

## Joint scenarios, not an empirical distribution

[provisional-pan-cases.csv](provisional-pan-cases.csv) runs through the existing first-harmonic [Rust plant screen](plant_screen.rs). `kit_reference_vessel` and `kit_no_vessel` use Infineon's **different measured conditions on its one coil**. The half-coupling row linearly interpolates *both* `L` and the pan-reflected resistance between those conditions with an arbitrary factor 0.5; it is a sensitivity construction, not a physical law or a named pan. The ±10% rows vary only `L` around the kit vessel point to probe the existing supplier tolerance proposal; they are **not** measured manufacturing quantiles.

The Infineon values are chart reads near **40 kHz** reused at the screen's **47 kHz** comparison point without a measured frequency correction. The manufacturer's chart can later supply a frequency-dependent interpolation; the current rows do not represent 47 kHz measurements.

Three further *cross-coil transfer probes* use the joint pan pairs measured in [a published 180 mm, 110 µH no-load coil study, Table 3](https://www.mdpi.com/2079-9292/12/19/4145): cast iron `(89.76 µH, 4.21 Ω)`, stainless steel `(81.81 µH, 3.36 Ω)`, and Silit Silargan `(69.07 µH, 2.48 Ω)`. Each study inductance is normalized by that study's 110 µH no-load value and multiplied by the kit's 87 µH chart reading, giving about 70.99, 64.70 and 54.63 µH. For a stress probe only, each study's measured **total** resistance is paired with the kit's 0.34 Ω no-vessel proxy, making reflected terms 3.87, 3.02 and 2.14 Ω. This transfer does **not** predict those pans on the Infineon coil: ferrite, gap, diameter, current, temperature and frequency differ. It preserves each observed `(L,R)` pair instead of independently mixing an L from one pan with an R from another and claiming a realistic pan. Independent worst-corner combinations remain necessary for part stress.

There is **no defensible pan probability distribution yet**. A future hierarchical prior can use pan class, base diameter/material, centering/lift, coil sample, current, frequency and temperature as joint inputs. Its class weights need an adopted target pan set or observed home-use population; its conditional spreads need repeated impedance measurements. Until then, an equal-weight Monte Carlo is only a sensitivity visualization, and a 95th percentile has no appliance safety meaning. This does not bar selecting footprints and architecture candidates; it bars using invented probabilities to clear switch, capacitor, connector, thermal or stop limits.

## Screen and closure

Run from repository root:

```sh
rustc --edition=2021 -O zapote/inverter/evidence/plant_screen.rs -o /tmp/zapote-plant-screen
/tmp/zapote-plant-screen zapote/inverter/evidence/provisional-pan-cases.csv
```

The [saved output](provisional-pan-output.csv) uses **390 V, 47 kHz, 300 nF** only as a comparison point. The single-harmonic screen omits source droop, ZVS/commutation, switching loss, startup, faults and temperature, so no current or power in it is a continuous rating or heater-output claim. The separate U2 architecture and U3 measurement gates still apply.

At that one illustrative point, the kit chart reference gives **24.36 A rms** tank fundamental, the no-vessel case **12.18 A**, the cross-coil Silargan transfer **32.25 A**, and varying the reference inductance alone by −10% gives **30.90 A**. The span demonstrates why one nominal pan is a poor component screen. It does not establish how often any case occurs or whether a real 390 V bus can sustain it.

Next, acquire one kit sample and the identified reference/weak pans. Measure the same coil build with no pan and each pan at the installed glass/gap, offset and lift limits over 20–50 kHz, multiple currents and hot/cold states; capture complex impedance and uncertainty. Use these observations to replace chart and cross-coil scenarios, then repeat the campaign on the eventually protected common inverter article before promoting any row into U3. Keep separate bounded bus, capacitor, gate-stop and fault cases: a pan prior cannot close them.
