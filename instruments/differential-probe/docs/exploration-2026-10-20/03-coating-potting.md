# Coating and potting after Rev B compensation

Research date: 2026-10-20. **Verdict: worthwhile second-stage experiment; no present spacing reduction.** Establish the unpotted Rev B response first, then encapsulate an unchanged sacrificial assembly and recalibrate. An eventual compact derivative needs its own insulation and performance qualification. No board, BOM or existing qualification requirements change through this note.

## Baseline and possible size benefit

The reviewed [Rev B layout](../layout.md) is 240 × 84 mm, with five 33 pF compensated sections per leg, 35 mm leg translation, ten capacitor slots, and a 20 mm exposed-HV-to-shield setback. Canonical PCB SHA-256, verified locally: `b0c15add2b69967cee0593962e1b3b22795725ed36ccbfc408b05c3fb4002b65`. The user-selected stage-53 DUT hash also matches its [README identity](../../README.md): `82af7bd93e62d1f2e6c7c2c2b971a4830bf6e09078bae3f269d8bead9a31fd27`.

Potting this PCB saves **zero PCB area**. A later layout could reduce ladder separation, slot-dependent surface paths, and enclosure setbacks where qualified encapsulation replaces the exposed insulation path. Size gain is unknown: component bodies, leads, the amplifier region, and capacitance to the grounded shield can still set dimensions. No defensible percentage or new millimetre spacing follows from the public sources.

## What IEC 60664-3 establishes

The [IEC public scope](https://webstore.iec.ch/en/publication/26148) explicitly permits reduced creepage/clearance for protected assemblies, but distinguishes **type 1**, which improves the protected microenvironment, from **type 2**, treated similarly to solid insulation. These describe demonstrated protection, not interchangeable labels for “paint” and “potting.” A conformal-coating datasheet or a filled box does not establish either system's compliance. Coating edges, coverage beneath components, interfaces, adhesion and environmental durability remain relevant.

The probe-specific starting point is [IEC 61010-031:2022](https://webstore.iec.ch/en/publication/70272), whose scope covers hand-manipulated measurement probes and related accessories; this applicability is an engineering inference requiring confirmation for the final assembly. Do not substitute a generic pollution reduction for its accessible-part, insulation and probe-wire requirements. Frequency also matters: [IEC 60664-4's scope](https://webstore.iec.ch/en/publication/2804) addresses periodic stress above 30 kHz, including this probe's 35–60 kHz band, and flags limits on how it relates to type 2 protection. Full normative texts were unavailable for this study. The full applicable standards and qualification review are needed before deriving distances, impulse levels or test voltages. This research claims no certified 3 kV/CAT envelope.

## Calibration will not automatically transfer

**Inference:** material replaces air in the distributed electric field, increasing some inter-node and node-to-earth capacitances unequally. The five intentional 33 pF capacitors themselves do not acquire the resin's permittivity multiplier. As an illustrative calculation only, a wholly air-filled 0.2 pF stray would become 0.544 pF at relative permittivity 2.72: +0.344 pF, about 1% of 33 pF. Actual fields partly traverse PCB, packages and air, so this is not a predicted response change.

Equal-looking pours cannot guarantee equal transfer functions. A bottom trimmer can correct a dominant time-constant error; it cannot remove every distributed pole or dielectric-loss term. The [existing qualification plan](../qualification.md) therefore remains essential: final shield and leads, DC ratio, amplitude/phase, CMRR, loading and recovery. Pre-pot calibration supplies a comparison, not a final certificate.

**Unknown:** encapsulant permittivity/loss versus frequency, temperature and absorbed moisture; capacitance temperature coefficient; dielectric absorption and post-overload settling in this geometry. The C0G network's stability does not characterize these added paths. Record zero recovery after both polarity stresses and humidity exposure, including slow tails beyond the existing one-cycle recovery objective.

## Candidate process and material risks

Use **Dow SYLGARD 184**, a transparent two-part silicone, as the first screening candidate. [Dow's product page](https://www.dow.com/en-us/pdp.sylgard-184-silicone-elastomer-kit.01064291z.html) identifies PCB/HV-resistor-pack use, 10:1 mixing, 48-hour room-temperature cure, approximately 3500 mPa·s viscosity, relative permittivity 2.72 at 100 Hz and thermal conductivity 0.27 W/(m·K). These typical values support candidate selection, not insulation thickness calculations. Its low-frequency permittivity does not characterize 5 MHz behavior.

Silicone compliance is attractive for CTE mismatch; [Dow's selection guide](https://www.dow.com/documents/11/11-3922-01-silicone-encapsulants-and-gels.pdf?iframe=true) also distinguishes adhesion and rework behavior among formulations. This is not a thermally conductive heat sink. **Calculated:** each approximately 10.005 MΩ leg dissipates 0.90 W at 3 kV DC, or 0.45 W at 3 kV peak sine; simultaneous common-mode excitation can heat both legs. Measure resistor temperatures and gain drift after encapsulation.

Voids beneath capacitors, in slots and at lead exits, or delamination after thermal cycling can concentrate electric field and support partial discharge. Transparency helps inspection but cannot prove void-free interfaces. Use controlled cleaning, mixing, vacuum deairing and filling; Dow provides [bubble-reduction guidance](https://www.dow.com/en-us/faq/reduce-bubbles-conformal-coating.html). Rework by cutting silicone can damage coatings/components and leave new interfaces; treat a repaired HV module as requiring renewed qualification.

For a printed housing, screen **Formlabs Flame Retardant Resin**, not an unspecified resin. Its [datasheet](https://formlabs-media.formlabs.com/datasheets/2301750-TDS-ENUS-0_1.pdf) reports dielectric properties; the [product page](https://formlabs.com/global/products/flame-retardant-resin/) gives V-0 at 3 mm. Neither establishes a certified enclosure wall or the potting bond. Formlabs explicitly warns that SLA residue can [inhibit silicone cure](https://formlabs.com/support/Silicone-mold-making-and-silicone-part-production/). Validate the exact washed/post-cured resin, silicone, flux and any primer together; cosmetic release agents are additional unqualified interfaces.

## Bounded next experiment

Build one retained unpotted control and two sacrificial identical Rev B units after compensation is understood. First cast small housing/PCB/lead coupons to check complete interfacial cure, adhesion and sectioned voids. Record lots, cleaning, fill orientation, mass, cure and dimensions. Encapsulate only the HV region symmetrically, keeping trims and low-voltage service access clear; initially preserve conductor positions. Filling slots changes their insulation mechanism and conflicts with the canonical layout's no-bridging instruction: record a separate experimental assembly variant with its own insulation assessment.

Measure before/after transfer functions, per-tip capacitance, CMRR and recovery; recalibrate after full cure. Repeat over proposed 10/25/50 °C screening points and controlled humidity/thermal cycling, with a sectioned companion coupon. Retain ±2%/≤1° main-band targets, measured CMRR and the tentative ≤10 pF total loading target. Only after low-voltage success should a qualified HV fixture assess leakage, partial-discharge inception/extinction and withstand under the actual waveform. Passing supports a compact prototype study, not manufacturing release.
