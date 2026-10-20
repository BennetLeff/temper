# 06 — Can 1% HV resistors replace the 0.1% parts?

**Disposition:** the [Rev B build decision](../revb-build-decision.md) keeps 0.1% parts and cancels this note's proposed dedicated comparison experiment. The calculations remain supporting research, not additional required bench work.

**Decision: a worthwhile prototype experiment, with a corrected trim design and measured drift/VCR acceptance.** Initial tolerance alone does not justify twenty expensive 0.1% resistors. However, 4.87 kΩ + an unscreened 200 Ω trimmer does not cover every corner, and the available cheaper HVC part doubles the specified absolute TCR. This note proposes no CAD/BOM change or voltage release.

## Candidate parts and trim coverage

Rev B uses twenty HVCB2512BDE1M00 resistors: ten per leg, grouped into five `2 MΩ || 33 pF` sections. A real alternative is **HVCB2512FKC1M00**, 1 MΩ, 1%, 50 ppm/°C, in the same 2512 package. The existing part is 0.1%, 25 ppm/°C. Stackpole's current [HVC datasheet, September 2025](https://www.seielect.com/Catalog/SEI-hvc.pdf) specifies 2 W at 70°C and a 3 kV working-voltage ceiling for 2512, additionally limited by `sqrt(PR)`: 1.414 kV for 1 MΩ. The older `SEI-HVCB.pdf` linked by the BOM has different ratings; use the current HVC document when confirming purchases.

A concrete low-side candidate is [TE RN73C1J4K87BTDF](https://www.te.com/fr/product-7-1879133-2.html), 4.87 kΩ, 0.1%, 10 ppm/°C, 0603, 63 mW/50 V. Pair it with **Bourns 3296W-1-201LF**, retaining the wiper-to-end connection. The [Bourns datasheet](https://www.bourns.com/PDFs/3296.pdf) specifies ±10% total resistance, 25 nominal turns, ±100 ppm/°C, minimum resistance ≤max(1%, 2 Ω), and contact-resistance variation ≤max(1%, 3 Ω). At 200 Ω those last quantities are 2 Ω and 3 Ω, respectively. At 3 kV DC the complete bottom leg sees only 1.5 V/0.45 mW; the nominal corrected trim dissipates about 10 µW.

For `Rtrim = Rtop/1999 − Rfixed`, worst coherent upper-string corners give:

| Fixed resistor | Required trim, Ω | Guaranteed coverage with 200 Ω ±10%? |
|---|---:|---|
| Existing 4.99 kΩ ±0.01%, upper ±0.1% | 7.000–18.003 | Existing 50 Ω works |
| 4.87 kΩ ±0.01%, upper ±1% | 81.989–183.013 | No: minimum total pot is 180 Ω |
| Candidate 4.87 kΩ ±0.1%, upper ±1% | 77.606–187.396 | No |
| 4.87 kΩ + 22.1 Ω, both ±0.1%, upper ±1% | 55.484–165.318 | Yes, before drift allowance |

The last option adds one small fixed resistor per leg and sets nominal trim to 110.401 Ω. Alternatively select a larger fixed value near 4.93 kΩ, or screen the actual 200 Ω pots; neither requires accepting an uncovered corner. End resistance is comfortably below these settings. Full-span resolution becomes roughly 8 Ω/turn versus 2 Ω/turn currently. A 3 Ω contact change represents 600 ppm of the low-leg resistance; the specification concerns adjustment/contact variation, not a guaranteed stationary drift or noise floor.

## What the finite crossover actually changes

The nominal time constant is 66 µs, so `fc = 2411.44 Hz`. For independently changed resistance after calibration, the first-order complex gain sensitivity is approximately `1/(1+j f/fc)`: its magnitude is **0.06874 at 35 kHz and 0.04016 at 60 kHz**. A subsequent 1% resistance-ratio change therefore leaves approximately 687/402 ppm complex error, mostly phase. Resistance influence is small, not zero.

There is a stronger cancellation for initial tolerance: if every section resistance scales by the same factor and DC trim scales the bottom resistance accordingly, equal section capacitors make both time constants scale together. The ideal divider remains exactly 2000:1 at every frequency, with the original 13.1934 nF bottom capacitance.

Unequal sections prevent that exact cancellation. Calculations here sum `Zi = Ri/(1+jωRiCi)`, use `H = Zbottom/(ΣZi+Zbottom)`, and trim `Rbottom=ΣRi/1999`. Exhaustively enumerating five independent ±1% section-resistance corners gives maximum normalized complex errors of **6.59 ppm at 35 kHz / 3.86 ppm at 60 kHz** with equal 33 pF capacitors. Those are about 104/108 dB divider-only rejection between worst corner legs. They are calculated ideal-network results, not assembled CMRR.

Enumerating all 1024 combined ±1% R/±5% C corners, additionally setting `Cbottom=1999/(Σ1/Ci)` to match the high-frequency limit, raises the errors to **239/140 ppm**. Changing R alone within those capacitor corners contributes up to 72.8/42.6 ppm. Thus individual RC mismatch matters, although capacitance matching, strays and assembly remain larger concerns. This assumes unrestricted coarse-capacitor selection; the fine trimmer alone cannot cover ±5% of 13 nF. No node-to-earth strays or amplifier errors are included.

## Tracking, voltage and heating

For 60 dB DC rejection after calibration, differential ratio drift must stay below 1000 ppm: over 60°C that allows only **16.7 ppm/°C** difference between complete leg ratios. Two independent ±50 ppm/°C strings provide no such tracking guarantee; ten components do not guarantee statistical averaging. Pot weighting adds about 2.2 ppm/°C at the corrected nominal setting, plus the fixed resistor's contribution. TCR selection and equal thermal environments matter more than initial absolute tolerance. The HVC TCR test is 25–75°C; extrapolation to the complete −25…85°C envelope needs evidence.

Crucially, HVC lists **typical VCR of 1–200 ppm/V**, and measures resistance at 100 V. The headline “as low as 1 ppm/V” is not an exact-MPN maximum. From 100 to 300 V per resistor, those illustrative coefficients imply 200 ppm to 4% resistance change; neither tolerance grade resolves this uncertainty. Seek a guaranteed exact-grade VCR or measure it.

At 1.5/3 kV DC per tip, nominal resistor stress is 150/300 V and 22.5/90 mW each; sine heating at equal peak voltage is half that. At 50 ppm/°C, a 10°C unequal temperature rise gives 500 ppm DC ratio error. Thermal resistance and temperature tracking have not been established.

## Cost and discriminating experiment

Indexed [DigiKey baseline listings](https://www.digikey.com/en/products/detail/stackpole-electronics-inc/HVCB2512BDE1M00/5824177), an [alternate baseline listing](https://www.digikey.com/en/products/detail/stackpole-electronics-inc/HVCB2512BDE1M00/5824166), and the [1% candidate](https://www.digikey.com/en/products/detail/stackpole-electronics-inc/HVCB2512FKC1M00/1948071) prices retrieved 2026-10-20 imply **$201.84–213.96 versus $45.26 for twenty**, using displayed ten-piece cut-tape breaks: $156.58–168.70 gross resistor savings. The range reflects differing indexed baseline listings, not a live quote. Mouser's connector exhausted its shared quota. Two genuine Bourns pots add roughly $3.23–6.98 from indexed [LCSC](https://lcsc.com/product-detail/Variable-Resistors-Potentiometers_BOURNS-3296W-1-201LF_C83685.html)/[Newark](https://mexico.newark.com/en-MX/bourns/3296w-1-201lf/trimmer-25-turn-200r/dp/39K2053) unit prices; new fixed resistors, calibration labor, shipping and tax remain unpriced.

Build matched 0.1% and 1% ladder coupons with identical capacitors/geometry and the final shield. Record every section's R/C, trim DC and AC, then sweep differential gain/phase and common-mode residual through DC, crossover, 35–60 kHz and 5 MHz. Repeat temperature and warm-up sweeps, adjustment/reseat tests, and qualified 1.5 kV before 3 kV voltage sweeps. Compare voltage dependence and thermal drift separately. Accept the cheaper population only against the same measured amplitude, phase and CMRR budgets.
