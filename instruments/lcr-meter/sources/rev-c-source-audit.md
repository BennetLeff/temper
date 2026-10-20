> Final manufacturing update: C105 (10pF) and C41 (5pF) are removed. C104 is the fixed local100pF capacitor for every range; its100pF MPN below remains fitted. The10pF sourcing record is retained as development history.

# Revision C added and changed component sources

Retrieved and checked 2026-10-20. The source JSON records exact catalog identity, stock and prototype price; quantities are not procurement reservations.

| References | Exact part / LCSC | Primary dimensional/electrical evidence |
|---|---|---|
| C104, C106–C109 | Samsung CL10C101JB8NNNC / C14858 | `CL10C100JB8NNNC.pdf` family table: 100 pF, C0G, ±5%, 50 V; CL10 1.60 × 0.80 mm, height max0.90 mm |
| C105 | Samsung CL10C100JB8NNNC / C1634 | Same family table: 10 pF, C0G, ±5%, 50 V |
| R90–R93 | UNI-ROYAL 0603WAF220JT5E / C23345 | [Manufacturer general-purpose thick-film sheet](https://www.royalohm.com/assets/pdf/products/smd/1.pdf), retained `C23345-0603WAF220JT5E.pdf`: 0603 1.60±0.10 ×0.80±0.10 mm, 0.45±0.10 mm high, 1/10 W,75 V; ordering code F1%,220J22Ω,T5E5000/reel |
| R64,R65,R70,R71 | Yageo RC0603FR-074R32L / C482855 | [Exact manufacturer specification](https://yageogroup.com/component-documentation/download/specsheet/RC0603FR-074R32L), retained `C482855-RC0603FR-074R32L.pdf`:4.32Ω1%,100mW75V,1.60±0.10 ×0.80±0.10 mm,0.45±0.10 mm high |

Distributor datasheet URLs initially returned HTML. Those files were replaced with verified manufacturer-hosted PDF documents; text extractions are retained for inspection. Both resistor catalog entries resolve to the same symmetric0603 library footprint UUID `398691f1f785460098bbe5ee6590333c`. The two Samsung values share footprint UUID `f8151fdc728a41ebbc304e11d39e5437`. Native standard0603 R/C lands remain applicable; all new passives are nonpolar, with zero extra CPL rotation correction.

All keyed IC MPNs and footprints are unchanged from revision B. `placement-rev-c.json` retains their exact numbered-pad orientation evidence and records the additional passive references. The final native placement export supplies translated coordinates and current rotations; the manufacturer assembly preview is still required before ordering.

Additional primary circuit evidence: `ti/ADS9224REVM-SBAU315B.pdf` from https://www.ti.com/lit/pdf/SBAU315 and `ti/SBOC476.zip` from https://www.ti.com/lit/zip/SBOC476. The complete package manifest pins every retained source byte.
