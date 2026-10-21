# Revision D cost estimate

This complete meter occupies one PCB. Budget for obtaining one usable instrument while paying the manufacturer's minimum batch. No checkout quote, reservation or purchase has been submitted.

## Five assembled boards at JLC

`manufacturing/order_estimate.py 5` (KiCad Python) reproduces these figures and writes `manufacturing/order-estimate-5.json`. Inputs:
- JLC assembly-library snapshot, read 2026-10-20 (`manufacturing/prices/jlc-parts-2026-10-20.json`): price tiers, stock, library class, attrition (`lossNumber`) and minimum quantity (`leastPatchNumber`) per part;
- board counts: 173 placements, 556 SMT joints per board, leadless parts U1, U8, U9, U10 and U13, and 23 THT joints on J2–J6 and JP1–JP6;
- the published fee table;
- the fabrication instant quote of the same day.

Each line buys max(5 × per-board quantity + attrition, minimum). That is our reading of JLC's library fields; the quote from the uploaded BOM is authoritative. Every line has stock for this order. The thinnest is OPA2810, with 251 in stock against 10 needed.

| Item | USD |
|---|---:|
| SMT parts (58 lines; attrition and minimums add $9.21) | 351.55 |
| Extended-part fee, 30 × $3.07 | 92.10 |
| Setup + stencil | 9.71 |
| SMT joints, 5 × 556 × $0.0016 | 4.45 |
| X-ray, 25 leadless parts × $0.82 | 20.50 |
| Confirm placement | 0.45 |
| PCB fabrication, 5 pcs (detail below) | 116.73 |
| **Economic PCBA total** | **595.49** |
| JLC fits J2–J6/JP1–JP6: parts $12.49, 115 manual joints $1.89, labour $3.58 | 17.95 |
| **Five complete boards, before shipping and taxes** | **613.44** |

That is $122.69 per board. Standard PCBA would cost $678.81 before hand fitting: higher setup and stencil fees, feeder loading on all 58 lines, and fixtures. Shipping, sales tax/VAT, import duty and coupons are excluded.

**Fabrication quote.** 4 layers, 140 × 100 mm, 1.6 mm, 1 oz outer and 0.5 oz inner copper, ENIG 1 µin, epoxy filled and capped vias, 3–4-day build.

| Line | USD |
|---|---:|
| Engineering fee | 25.00 |
| POFV | 18.28 |
| ENIG | 18.20 |
| TG155 material | 7.32 |
| Board | 8.70 |
| Minimum via 0.2 mm | 18.28 |
| 4-wire Kelvin test | 17.47 |
| Horizontal electroless via plating | 3.48 |

- The 0.2 mm via option forces TG155 material and the 4-wire Kelvin test. The 0.25 mm option forces the same extras and costs $116.15.
- Only an all-0.3 mm via board avoids them, at $80.98. That is not available here: 58 holes are 0.20 mm and 57 are 0.25 mm, including the POFV pads.
- JLC leaves vias over 0.5 mm unfilled. Every via on this board is 0.30 mm or smaller.

**Where the money goes.** The ICs at $1 or more are $309.22, 88 % of the parts. ADS9224R and AD9833 alone are $155.34. The Rev E codec front end removes ADS9224R, AD9833 and both THS4551s, about $39 per board, and adds TAC5112 and three relays for about $13, before its smaller support parts.

## BOM arithmetic checkpoint

Catalog snapshot checked 2026-10-20:

| Item | Quantity | USD |
|---|---:|---:|
| All components for one instrument | 184 | 76.01 |
| Machine-placed components per PCB | 173 | 72.95 |
| Hand-fitted components per PCB | 11 | 3.06 |
| SMT parts for two assemblies | 346 placements | 145.89 |

Both `SMT` and `JLC SMT` source tags count as machine placements. Hand fitting includes the DC jack and ten two-pin headers. Two Samtec SNT-100-BK-G shunts, leads, supply and standards are accessories; their cost is outside the component-set subtotal. These figures include Rev C TIA compensation (local C104; C105/C41 removed), four 22 Ω driver resistors (R90–R93), four 100 pF driver feedback capacitors (C106–C109), and 4.32 Ω output resistors. Rev D adds R94 (22 Ω 0.1 % R_iso, C861239), R95/R96 (1 Ω LDO input resistors, C22936), the rail monitors R97–R100 and C110/C111 (existing BOM lines), and changes R83 to 1.74 MΩ (C422975 replaces C482655). The Rev D audit fixes ([rev-d-audit.md](rev-d-audit.md), **Applied**) swap ten part lines and add two 10 µF X7R reference caps (C95841). Exact source sums are $76.0052 total, $72.9468 SMT and $3.0584 hand-fitted per instrument; reconcile with the final exported BOM. Rev D adds $0.068 of parts per board over Rev C, plus one extended-line feeder fee per order.

The 58 unique SMT lines comprise 30 extended, 27 basic and one preferred line (was 55 lines, 34 extended, before the audit fixes). LCSC stock for C861239, C422975 and C22936 was not confirmed at this snapshot; check it at BOM upload. C165948 USB connector and ST C7519 ESD protector were independently confirmed as extended. Catalog stock/prices do not guarantee eventual availability or the PCBA purchase price.

Published Economic starting costs:

```text
2 × $72.9468 SMT parts                $145.8936
30 × $3.07 feeder loading              $92.1000
Setup                                  $8.1800
Stencil                                $1.5300
Subtotal before other charges        $247.7036
```

**Epoxy-filled and copper-capped vias (POFV) are required** for seventeen intended exposed-pad and selected ADC capacitor/signal-pad locations (54 vias; every exposed pad now has 5–9), including C107.1/C109.1 in the new FDA feedback network. The four-layer board does not qualify for JLC's free 6–20-layer POFV offer. The 2026-10-20 fabrication quote above includes it. Tenting alone is incompatible with this package.

Add PCB fabrication, POFV, assembly joints, required leadless-package X-ray, attrition/minimum placement quantities, hand parts, shipping and taxes. Supplier pack sizes and loss allowances can exceed simple BOM multiplication.

## Cash budgets

| Route | USD allowance | Assumptions |
|---|---:|---|
| Bare-board batch; hand assemble one | 140–220 | One component set, four-layer fabrication and ordinary shipping; reflow/rework tools already available |
| Two JLC SMT assemblies; finish by hand | 320–450 | Two SMT sets, fixed fees, fabrication, inspection and shipping allowances |
| Supply/cable/fixture/shunts/standards | Add 30–100+ | Excludes a reference meter, oscilloscope and enclosure |

Use the full batch cost when deciding to build one instrument. Dividing it by two does not reduce the first payment. Taxes/import fees, special sourcing and a possible respin are outside these allowances.

JLC advertises two-board prototype assembly, ordinarily with at least five bare PCBs. RP2040 C2040 is listed for Economic and Standard service; its 0.4 mm pitch alone does not force Standard. Other parts/options can change eligibility.

Sources checked 2026-10-20: [assembly prices](https://jlcpcb.com/help/article/pcb-assembly-price), [capabilities](https://jlcpcb.com/capabilities/pcb-assembly-capabilities), [prototype minimum](https://jlcpcb.com/solutions/pcb-prototype-assembly), [fabrication/assembly quantities](https://jlcpcb.com/blog/reduce-pcb-assembly-cost-prototype), [RP2040 eligibility](https://jlcpcb.com/partdetail/RaspberryPi-RP2040/C2040). [JLC via finishes](https://jlcpcb.com/blog/five-via-finishes) and [POFV layer eligibility](https://jlcpcb.com/news/free-via-in-pad-6-20-layer-pcbs-pofv) establish the required process; the uploaded BOM/CPL/fabrication quote is authoritative.

## Useful upgrades

| Investment | Benefit | Required work |
|---|---|---|
| Characterized standards and rigid shielded fixture | Better calibration/repeatability; first priority | Bound AC parasitics; validate after fixture changes |
| Remote Kelvin sensing | Less lead/contact error | Circuit/fixture redesign and fresh stability/calibration work |
| Four-wire DC resistance channel | Addresses 1 mΩ shunt/winding DC resistance | New current source, offset/thermal-EMF control and calibration |
| Relay ranges/state sensing | Convenience; fewer manual errors | Switching parasitic/leakage and control validation |
| USB isolation | Breaks computer-ground loops | New interface/power design and noise qualification; no energized-DUT rating implied |
| Display/local controls | Computer-free operation | Firmware/interface work; no automatic accuracy improvement |

Revision D has simultaneous voltage/current acquisition, clock-aware capture, R_iso for fixture-capacitance stability and ±12 V rail monitors. It also includes the stability compensation and corresponding frequency-dependent host correction for the shared 100 pF feedback capacitor. These features are included in the present BOM. No added component establishes an accuracy number without measurement evidence.
