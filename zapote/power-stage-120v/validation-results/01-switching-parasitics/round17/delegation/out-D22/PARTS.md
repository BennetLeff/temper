# Proposed inlet filter module

This is a proposal in front of the existing board filter, after the appliance's upstream fuse/disconnect. The existing L1, X/Y capacitors, rectifier and power board are unchanged. Both line and neutral pass through the additional current-compensated choke. Bond the module's Y returns directly to PE; keep filtered and unfiltered conductors apart.

```text
inlet L,N ── 2.2 µF X2 across L–N ── coupled choke ── existing board filter
                                               │
                     4.7 µF X2 across L–N ──────┤
              3.9 Ω + 4.7 µF X2 series branch ──┤
              15 kΩ + 15 kΩ bleed across L–N ──┤
         each conductor → (4.7 nF || 2.2 nF) Y2 → PE
```

The choke's differential leakage supplies the DM inductance. The CM result in the unmodified receiver model requires the coupled winding and Y branches. The two Y capacitances use separate short branches: their assumed ESLs are explicit in `filter-scenarios.json`. Parallel capacitors sharing one long PE pigtail do not achieve that model.

## Parts and ratings

Dimensions below are body L × W × H, not a production land pattern. Datasheet page numbers are printed pages. All quoted catalog prices are planning snapshots read 2026-10-03, excluding freight, taxes and tariffs; availability is not a purchase reservation.

| Proposed item | Qty | Exact order code | Rating / body size / source |
| --- | ---: | --- | --- |
| Coupled choke | 1 | TDK **B82726S2203A020** | 250 VAC, 20 A at 60 °C / 50 Hz; 1.6 mH/winding −30/+50%; typical differential leakage 18 µH and DCR 4.5 mΩ/winding at 20 °C; 45 × 25.5 × 41 mm. [May 2026 datasheet, pp. 2–5](https://product.tdk.com/system/files/dam/doc/product/emc/emc/line-filter/data_sheet/30/db/ind_2008/b82726s22x3.pdf). |
| Input X capacitor | 1 | TDK **B32923C3225K000** | 2.2 µF ±10%, X2, 305 VAC; 26.5 × 14.5 × 29.5 mm, 22.5 mm pitch. [June 2026 B3292*C/D, pp. 3, 7, 11–13](https://product.tdk.com/system/files/dam/doc/product/capacitor/film/emi/data_sheet/20/20/db/fc_2009/x2_b32921_928.pdf). |
| Output and damping X capacitors | 2 | TDK **B32924D3475K000** | Each 4.7 µF ±10%, X2, 305 VAC; 31.5 × 21 × 31 mm, 27.5 mm pitch. Same datasheet, pp. 3, 8, 11–13; 120 V/µs pulse rating (p. 12). |
| Main Y capacitors | 2 | TDK **B32021A3472M000** | Each 4.7 nF ±20%, Y2, 300 VAC; 13 × 5 × 11 mm, 10 mm pitch. [June 2026 B3202*A3/B3/C3, pp. 2–5](https://product.tdk.com/system/files/dam/doc/product/capacitor/film/emi/data_sheet/20/20/db/fc_2009/y2_b32021_026.pdf). |
| HF Y capacitors | 2 | TDK **B32021A3222M000** | Each 2.2 nF ±20%, Y2, 300 VAC; 13 × 4 × 9 mm, 10 mm pitch. Same datasheet p. 5; [manufacturer production listing](https://product.tdk.com/en/search/capacitor/film/emi-suppression/info?part_no=B32021A3222M000). |
| Damping resistor | 1 | Vishay **AC05000003908JAC00** | 3.9 Ω ±5%, 5 W at 40 °C, 4.7 W at 70 °C, flameproof coating; body 18 × Ø7.5 mm. [Vishay 28730, 05-Dec-2024, pp. 1–2, 6–7, 10](https://www.vishay.com/doc?28730=); [orderable Newark listing](https://www.newark.com/vishay/ac05000003908jac00/res-3r9-5w-axial-wirewound-rohs/dp/84AH4613). This is the standard AC part, not the separately specified AC-CS safety fuse resistor. |
| Bleed resistors | 2 | Vishay **PR02000201502JA100** | Each 15 kΩ ±5%, copper-lead PR02, 2 W at 70 °C, 500 V AC/DC; flameproof coating. [Vishay 28729, 08-Jul-2025, pp. 1–3, 5](https://www.vishay.com/docs/28729/pr010203.pdf); [orderable DigiKey listing](https://www.digikey.com/en/products/detail/vishay-beyschlag-draloric-bc-components/PR02000201502JA100/7350674). |

Use X2 only where across-line impulse/category assessment permits it; the specified 305 VAC rating comfortably exceeds 140 VAC but does not establish the appliance's surge qualification. Keep the existing surge protection and upstream overcurrent protection. Y2 goes only to protective earth in this Class I proposal; it is not a substitute for reinforced insulation to an accessible unearthed surface.

## Fifteen-ampere input and saturation

At 15 A RMS, estimated added-choke copper loss is **2.025 W** using typical cold DCR or **2.700 W** using the explicit **6 mΩ/winding hot planning value**. The latter is not a datasheet maximum. `budget.py` computes both at 120 and 140 V; line voltage does not change I²R at fixed current. Maintain the choke's local ambient at or below its 60 °C rating for this allocation. Do not put the module in the heatsink's hot exhaust stream merely because both are at the left end.

Line and neutral load flux cancel. TDK p. 4 specifies less than 10% inductance decrease under its DC-bias test at rated current and 20 °C; it does **not** give a guaranteed hot leakage-inductance-versus-rectifier-peak-current curve. The simulation therefore tests added leakage down to **9 µH** (half the typical 18 µH), and also tests low original-choke leakage. This is a sensitivity assumption, not a saturation bound. Confirm both the differential inductance and CM impedance under the measured pulsed 15 A RMS input, hot, including inrush and winding imbalance. There is no supported claim that a 20 A RMS rating limits arbitrary rectifier current peaks.

The line-frequency X currents and resistor losses are calculated at 60 Hz (the larger value for the same voltage at 50/60 Hz) with high capacitance tolerance. At 140 V, each 4.7 µF branch carries about **0.273 A RMS** from line frequency; the 2.2 µF input cap carries **0.128 A**. Add the modeled switching-harmonic currents in quadrature, as reported in `harmonic-loss-results.json`. Their constant ESR model is an estimate; the manufacturer's p. 13 frequency/current chart and actual case temperature still govern capacitor acceptance. Do not label this a guaranteed broadband ripple-current rating.

The damping branch dissipates up to **0.305 W** from the stated line-frequency/tolerance calculation, plus its reported HF loss. Its cold-start capacitor energy is **0.101 J**, or **0.405 J** for an opposite-polarity reclose at the stated 140 V crest and maximum capacitance. The AC05 single-pulse chart (28730 p. 6) is roughly 3 J/Ω near 3.9 Ω (a graphical estimate, about 12 J), above those isolated energy estimates. Repetitive surge/reclose, actual pulse shape and thermal recovery require the p. 7 check; capacitor energy alone is not a whole-appliance surge guarantee. The modeled resistor ESL is 0.5 µH nominal with 0.1–2 µH sensitivity.

`damping-results.json` compares the same passive receiver with its damping branch connected/open over 100 Hz–150 kHz. It shows a substantial reduction of DC-port resonant impedance. That fixture includes the LISN and a fixed conducting rectifier pair; it is **not** a closed-loop input-filter stability proof. Validate interaction with mains impedance, rectifier commutation and the future controller's burst behavior before hardware release.

## Bleed, leakage and thermal allocation

Require every added X capacitor to remain connected to the **30 kΩ bleed pair** after unplugging; no relay may isolate a charged branch. The calculation includes the existing two 1 µF X capacitors as ±20% planning values and added X capacitors at +10%. With the explicitly stacked resistor assumptions in `budget.json` (initial tolerance, 80 K temperature excursion and specified 1000-hour drift), **198 V crest falls below 34 V in 0.901 s**. This is a proposed ≤34 V / 1 s acceptance target, not a claim of appliance-standard certification, lifetime coverage or single-fault coverage. A failed-open bleed or a backfeeding supply defeats it; verify at the unplugged terminals. This pair does not discharge the rectifier-isolated DC link.

At 140 V the initial-tolerance calculation gives **0.344 W** maximum per bleed resistor and **73.5 V RMS** maximum voltage division. The two added Y pairs total **6.9 nF nominal per conductor**; their +20% value draws **0.437 mA** at 140 V/60 Hz for one conductor at that voltage to PE. Add the existing Y capacitance, other supplies, wiring and single-fault cases to the appliance leakage-current budget; this is not the total touch current.

Reserve **8 W** module heat as an enclosure planning allowance, with the calculated nominal loss and HF estimates separately visible. It is not a measured maximum. Confirm choke winding/case, capacitor case and resistor temperatures at sustained 15 A RMS input in the actual duct arrangement.

## Enclosure and cost

Reserve **110 × 80 × 50 mm (0.44 L)** near the left mains entry, outside the sink exhaust duct. This is a component/carrier/cover allowance, not a routed carrier board or approved insulation layout. The 41 mm choke height leaves room for the carrier, pins, standoffs and cover in the 50 mm allocation; the final assembly must check clearances, creepage, terminals, strain relief and mounting.

The planning subtotal is **$29.54** in parts, **$44.54** including a $15 carrier/terminal/cover allowance. Basis: [choke $13.73 catalog listing](https://www.digikey.com/en/products/detail/tdk/B82726S2203A020/3502593), [input X $2.05](https://www.mouser.com/en/ProductDetail/TDK/B32923C3225K?qs=TAh7utZnAiXirT9yBYlNUA%3D%3D), [4.7 µF X $3.38 each](https://www.mouser.com/en/ProductDetail/TDK/B32924D3475K?qs=7a3bTcro1EXyZ%252BrKR0OGfg%3D%3D). Both Y values and resistors use explicit allowances in `budget.py`. The choke may require a distributor backorder; these are orderable production codes, not a promise of immediate delivery.

The 4.7 nF Y part is listed in production in the [TDK part record](https://product.tdk.com/en/search/capacitor/film/emi-suppression/info?part_no=B32021A3472M000). Reducing the main Y from 10 nF to 4.7 nF cuts its leakage allocation; `reduced-Y-results.json` retains the comparison. The complete appliance still needs an explicit leakage-current allocation, including its existing filter and both supplies.
