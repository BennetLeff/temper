# Revision D cost estimate

This complete meter occupies one PCB. Budget for obtaining one usable instrument while paying the manufacturer's minimum batch. No checkout quote, reservation or purchase has been submitted.

## BOM arithmetic checkpoint

Catalog snapshot checked 2026-10-20:

| Item | Quantity | USD |
|---|---:|---:|
| All components for one instrument | 184 | 76.24 |
| Machine-placed components per PCB | 173 | 73.18 |
| Hand-fitted components per PCB | 11 | 3.06 |
| SMT parts for two assemblies | 346 placements | 146.36 |

Both `SMT` and `JLC SMT` source tags count as machine placements. Hand fitting includes the DC jack and ten two-pin headers. Two Samtec SNT-100-BK-G shunts, leads, supply and standards are accessories; their cost is outside the component-set subtotal. These figures include Rev C TIA compensation (local C104; C105/C41 removed), four 22 Ω driver resistors (R90–R93), four 100 pF driver feedback capacitors (C106–C109), and 4.32 Ω output resistors. Rev D adds R94 (22 Ω 0.1 % R_iso, C861239), R95/R96 (1 Ω LDO input resistors, C22936), the rail monitors R97–R100 and C110/C111 (existing BOM lines), and changes R83 to 1.74 MΩ (C422975 replaces C482655). Exact source sums are $76.2393 total, $73.1809 SMT and $3.0584 hand-fitted per instrument; reconcile with the final exported BOM. Rev D adds $0.068 of parts per board over Rev C, plus one extended-line feeder fee per order.

The 55 unique SMT lines comprise 34 extended, 20 basic and one preferred line. LCSC stock for C861239, C422975 and C22936 was not confirmed at this snapshot; check it at BOM upload. C165948 USB connector and ST C7519 ESD protector were independently confirmed as extended. Catalog stock/prices do not guarantee eventual availability or the PCBA purchase price.

Published Economic starting costs:

```text
2 × $73.1809 SMT parts                $146.3618
34 × $3.07 feeder loading             $104.3800
Setup                                  $8.1800
Stencil                                $1.5300
Subtotal before other charges        $260.4518
```

**Epoxy-filled and copper-capped vias (POFV) are required** for fifteen intended exposed-pad and selected ADC capacitor/signal-pad via locations, including C107.1/C109.1 in the new FDA feedback network. The four-layer board does not qualify for JLC's free 6–20-layer POFV offer. The $320–450 estimate below excludes this quote-dependent surcharge. Tenting alone is incompatible with this package.

Add PCB fabrication, POFV, assembly joints, required leadless-package X-ray, attrition/minimum placement quantities, hand parts, shipping and taxes. Supplier pack sizes and loss allowances can exceed simple BOM multiplication.

## Cash budgets

| Route | USD allowance | Assumptions |
|---|---:|---|
| Bare-board batch; hand assemble one | 140–220 plus POFV | One component set, four-layer fabrication and ordinary shipping; reflow/rework tools already available |
| Two JLC SMT assemblies; finish by hand | 320–450 plus POFV | Two SMT sets, fixed fees, fabrication, inspection and shipping allowances |
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
