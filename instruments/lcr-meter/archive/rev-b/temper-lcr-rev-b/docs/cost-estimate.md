# Revision B cost estimate

This complete meter occupies one PCB. Budget for obtaining one usable instrument while paying the manufacturer's minimum batch. No checkout quote, reservation or purchase has been submitted.

## BOM arithmetic checkpoint

Catalog snapshot checked 2026-10-20:

| Item | Quantity | USD |
|---|---:|---:|
| All components for one instrument | 167 | 76.12 |
| Machine-placed components per PCB | 156 | 73.06 |
| Hand-fitted components per PCB | 11 | 3.06 |
| SMT parts for two assemblies | 312 placements | 146.12 |

Both `SMT` and `JLC SMT` source tags count as machine placements. Hand fitting includes the DC jack and ten two-pin headers. Jumper shunts, leads, supply and standards are accessories. These figures include the final C74/C75 0603 reference bypass substitution; recheck against the final exported BOM.

The 52 unique SMT lines comprise 34 extended, 17 basic and one preferred line. C165948 USB connector and ST C7519 ESD protector were independently confirmed as extended. Catalog stock/prices do not guarantee eventual availability or the PCBA purchase price.

Published Economic starting costs:

```text
2 × $73.0591 SMT parts                $146.1182
34 × $3.07 feeder loading             $104.3800
Setup                                  $8.1800
Stencil                                $1.5300
Subtotal before other charges        $260.2082
```

**Epoxy-filled and copper-capped vias (POFV) are required** for the exposed-pad and selected ADC capacitor/signal-pad vias. The four-layer board does not qualify for JLC's free 6–20-layer POFV offer. The $320–450 estimate below excludes this quote-dependent surcharge. Tenting alone is incompatible with this package.

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

Revision B already has simultaneous voltage/current acquisition and clock-aware capture. Those are not future upgrades carried over from revision A. No added component establishes an accuracy number without measurement evidence.
