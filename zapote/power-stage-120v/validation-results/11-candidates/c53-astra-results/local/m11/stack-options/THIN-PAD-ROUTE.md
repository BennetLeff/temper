# Thin insulating pad instead of the 2 mm AlN tile: evidence search, question for the certifier, and our own test plan (2026-10-17)

## 1. What commercial practice is public (searched; nothing conclusive)
- **Breville / PolyScience Control Freak:** public material gives a half-bridge drive, a twin-fan system that cools the coil and sensor separately from the electronics, and conflicting ratings
  (100-1,800 W on one listing, 240 V / 10 A / 2.4 kW on another). **No teardown, service manual or insulation detail found.** US9006622B2 "Induction cooking" describes a cooling plenum separate from the
  coil power electronics; whether it is PolyScience's is not established.
- **Impulse Labs:** 3 kWh LFP battery, 1.5 kW AC input, custom inverters, claims UL 858 certification. **No teardown or insulation detail found.**
- **Patents read through search snippets (not read in full):** one claims thin insulating sheets (under 1 mm) either side of an inductor stack with a metal heat-sink plate; one uses creepage distance around the working coil
  to prevent shock; none states whether the heat sink is earthed or floating. US 11612021 ("Induction heating device having improved insulation structure") is a scanned image and was not read.
- **General practice (my knowledge, not sourced here):** mainstream hobs mount IGBTs in TO-247 on an aluminium heatsink with a thin pad (mica, silicone-coated mica, filled film or a thin ceramic). Fuji Electric's
  application note says a module on a grounded heatsink needs an additional thermally conductive insulating layer (https://americas.fujielectric.com/?p=155003).
- **Gap:** how either named product insulates its devices is unknown. A teardown of a purchased unit, or the products' certification reports, would settle it.

## 2. Why a thin pad is the interesting route (repo analysis)
- The M11 recommendation's clause table (`owner-items/m11/RECOMMENDATION.md`, section 2): solid insulation through the insulator needs **>= 2 mm**, **or >= 3 layers each passing the supplementary 16.3 test, or thermal assessment plus the 16.3 test** (cl. 29.3 / 29.3.1 b / 29.3.2 / 29.3.3).
- A 2 mm tile is reinforced "by caliper reading" (29.3.1). A thin single layer qualifies only through the lab's **29.3.3 thermal-assessment and test route**; three thin layers (29.3.2) are thermally too costly.
- Thermal (repo formulas, `stack-calc.txt`): HI-FLOW 300P 0.102-0.127 mm: Rcs 0.349-0.555 C/W, **meets the 0.7 C/W budget**; SIL PAD 1500ST 0.203 mm: 0.618-0.981, fails; SIL PAD K-10 0.152 mm: 1.10-1.75, fails.
- Field strength is the catch: 470 V across 0.102 mm is **4.61 kV/mm** (0.152 mm: 3.09; 2 mm: 0.23), so partial discharge and ageing are the real questions for a thin film.
- A thin pad still needs the **8.0 mm creepage by geometry** (overhang of the pad and a pedestal that stays 8 mm clear), which the cheap die-cut film can provide at low cost.

## 3. Question for the certifier (ready to send; NOT sent: the owner sends it)
Subject: Thin insulating pad between mains-referenced TO-247 tabs and an earthed heatsink: acceptable route under IEC 60335-1 / UL 858?

Our 120 V (127 V max) induction cooktop power board has four TO-247 MOSFETs and a bridge rectifier whose metal tabs are live (bus about 340 V peak, switching nodes) on a heatsink that is bonded to protective earth.
We need reinforced insulation between the live tabs and the sink. We currently plan a 2.0 mm ceramic tile (29.3.1), which is costly for production. We would like your view on a thin pad instead:
1. Is a **single thin insulating sheet** (for example a polyimide-coated phase-change pad, 0.10-0.15 mm, rated 5,000 Vac) acceptable as reinforced insulation through the **29.3.3 thermal-assessment and test route**, and which standard edition and clause set does your lab apply to a cord-connected cooktop (UL 858 / UL 1026, CSA C22.2 No. 64, NOM)?
2. If so, what tests will you require on the assembled stack (dielectric withstand voltage and duration, humidity conditioning, temperature cycling or ageing, partial discharge, abnormal operation), with the pass criteria?
3. Do you accept our creepage by geometry (8.0 mm surface path from tab metal to the pedestal, over the pad edge), or do you measure over the pad surface differently?
4. Would a **heatsink at mains potential**, enclosed in a plastic duct with reinforced insulation to chassis, be easier for you to accept than an earthed sink with a thin pad? We would use catalogue pads (functional insulation) between tabs and sink in that case.
5. Is a type test on 3-5 samples before the design is frozen possible, and what lead time and cost?
Please answer in writing so we can attach it to our file.

## 4. Our own test plan (we test ourselves too, before and alongside the lab)
Proposed gates; the lab sets the final criteria. Numbers marked (repo) come from the M11 recommendation / stack_calc; the rest are targets to confirm with the lab.
| Gate | Test | Method | Pass criterion |
|---|---|---|---|
| G0 thermal screen | interface thermal resistance per FET with the real sink | thermocouple on the case, full-power run at the 18 A first-power ceiling, then higher as the ladder allows; measure (Tcase - Tpedestal) / P | <= 0.7 C/W per FET (repo, D-36) |
| G1 dielectric | withstand on the assembled stack, live tabs to sink | hipot, 60 s on the type samples, 1 s on production units | 3,000 V ac / 60 s type, 2,000 V ac / 1 s routine (repo, M11 section 4); no breakdown, leakage within the tester's limit |
| G2 partial discharge | PD inception and extinction on the stack | PD detector at a voltage above the working peak (470 V across the pad) with margin | no PD at 1.25 x working peak (target, lab to confirm) |
| G3 conditioning | humidity then G1 | 93 % RH, 40 C, 48 h, then hipot (lab to confirm duration) | passes G1 after |
| G4 ageing | thermal cycling and pad creep | -10 to +125 C cycles and hot hold at the pad temperature with the clamp load; clamp-force relaxation measured | passes G1 and G2 after; no cut-through, no flow-out under the tab |
| G5 mechanical | tab burr and cut-through | microscope on the pad after clamp at the specified force; edge radius of the tab; compare lots | no punctures; G1 on each |
| G6 creepage | measured surface and air paths | CAD measurement plus physical check on the built sink | >= 8.0 mm everywhere (repo) |
| G7 fault | tab-to-sink short | abnormal-operation run with the firmware limit defeated, per the lab | fuse/OCP clear, no hazard (lab) |
| G8 repeatability | across lots and assembly | repeat G0-G1 on 3 assemblies from separate pad batches | spread inside the criteria |
Equipment needed: a hipot tester (to 3 kV ac), a PD detector or a lab with one, a thermal chamber, thermocouples, a microscope. If the lab owns G2-G4, run G0, G1, G5, G6 in house first.

## 5. Recommended sequence
1. Send the certifier question (owner). 2. In parallel, buy a Control Freak or find its certification report to see what a shipping product does (owner decision, about $1,500). 3. Order thin pads (Hi-Flow 300P class) for the same geometry as the AlN tiles so the
two routes can be tested side by side on the type samples. 4. Run G0, G1, G5, G6 in house; take G2-G4 to the lab if they confirm the route.
