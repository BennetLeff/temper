# Rev B procurement preparation — 2026-10-20

**Status: files prepared and Gerbers uploaded to JLCPCB; order not placed.** The user selected **five PCBs, two populated**, after the quote form required at least two assembled boards. Destination is Austin, Texas; street address and account details are intentionally excluded from this repository.

The unchanged Rev B board is the engineering prototype to build, with the existing 0.1% resistor BOM, batteries and both gain ranges. See [build decision and operating restrictions](../docs/revb-build-decision.md). Pods and lumped dividers are Rev C candidates; there is no dedicated resistor-comparison experiment.

## Prepared files

- [Gerber/drill ZIP](revb-gerbers.zip): four copper layers, masks, paste, silk and routed outline.
- [JLC BOM](bom-jlc.csv): exact manufacturer parts exported from the schematic, one row per onboard reference.
- [JLC placement file](cpl-jlc.csv): 135 references, matching the onboard BOM exactly.
- [Native position export](positions-raw.csv) and [component export](components-raw.csv): source data for formatting.
- [Checksums](validation/sha256.txt), [ERC](validation/erc.rpt), [DRC](validation/pcb-drc.json), and [assembly parity](validation/assembly-parity.json).
- [Gerber review](validation/renders/gerber-review.png): copper, routed outline and top paste rendered with PyGerber's API V2. The older `raster-2d` renderer omitted rounded pads and thin outlines; those images were rejected and replaced, not treated as evidence of missing copper.

Run `sh procurement/export.sh` from the probe directory (or invoke the script by path). ERC and DRC must pass before exports. The script derives BOM/placement data; it does not edit parts or the PCB. Native KiCad rotations have not yet been approved against JLC's component-placement preview. Blank LCSC entries require exact-MPN sourcing; do not accept automatic substitutions. The 50 Ω resistance trimmers and capacitance trimmers are included in the 135 onboard references; battery clips, panel switches and BNC are separate offboard purchases.

The board SHA-256 is `b0c15add2b69967cee0593962e1b3b22795725ed36ccbfc408b05c3fb4002b65`. Fresh KiCad 10.0.4 ERC and DRC returned zero violations and zero PCB unconnected items. The rendered copper preserves both straight ladders and no underlying planes; the outline contains ten capacitor slots. The top paste render includes the divided exposed-pad apertures. These checks do not qualify the completed instrument at high voltage.

## JLC quote state

Uploaded ZIP parsed as 240 × 84 mm, four layers. Configured five PCBs, Standard top-side assembly, two populated, ENIG, and explicit layer sequence F.Cu / In1.Cu / In2.Cu / B.Cu. Production-file and parts-placement confirmation were enabled with automatic confirmation disabled. JLC added two 5 mm assembly rails and displayed 240 × 94 mm for the panel envelope. Require the production drawing to preserve the original finished outline and slots.

The displayed PCB/options subtotal was **USD 59.25**, before assembly and components. The page also displayed a USD 33.03 shipping estimate, but the Austin destination had not yet been entered, so that is **not a destination-qualified freight quote**. No final total, payment or shipping commitment exists. Sign-in returned to the quote page and cleared its settings; the same settings and Gerber upload were restored. JLC blocks continuation until its Assembly Service Terms and Conditions are accepted. User confirmation for that acceptance is pending; BOM/CPL matching and checkout remain unfinished. Review the complete order total before purchase.

Saved assembly remark:

> Rev B engineering prototype. Exact MPNs only; no substitutions. Preserve all ten non-plated 1.2 x 8 mm capacitor slots; no solder, adhesive or coating across slots. No added copper/fiducials in the HV ladder area. Preserve the two matched divider geometries. Please quote external/global sourcing for unmatched parts. Provide placement and routed-slot drawings for manual review before production. No conformal coating.

## Sourcing evidence

[Raw catalog and live JLC results](catalog-check.json) distinguish local-index results from live stock calls. The full assembly BOM has not yet been matched or priced by JLC.

| Exact MPN | Quantity for two populated boards, before attrition | Current evidence / action |
|---|---:|---|
| HVCB2512BDE1M00 | 40 | Live JLC C2482550: zero stock. [DigiKey listing](https://www.digikey.com/en/products/detail/stackpole-electronics-inc/HVCB2512BDE1M00/5824166) reports stock; web data is not a reservation. Request exact-part global sourcing/consignment. |
| GKG60015 | 4 | Live JLC C3273413: zero stock. [DigiKey listing](https://www.digikey.com/en/products/detail/ew-electronics/GKG60015/11689267) reports stock. Preserve EW part and existing footprint. |
| C1812C330JHGACTU | 20 | No exact live JLC result. [DigiKey listing](https://www.digikey.com/en/products/detail/kemet/C1812C330JHGACTU/9923023) reports stock. Exact 33 pF / 3 kV C0G required. |
| RNCF0603TKY499R | 22 | No exact live JLC result. [DigiKey listing](https://www.digikey.com/en/products/detail/stackpole-electronics-inc/RNCF0603TKY499R/4072346) reports stock. Preserve 0.01% grade. |
| RNCF0603TKY4K99 | 4 | Live JLC C3942722 reports 1000 available. Reconfirm at allocation. |
| ADA4817-1ARDZ-R7 / OPA810IDR | 4 / 6 | Exact local catalog matches C207502 / C1852077; not yet live allocated. |
| ADP7142AUJZ-R7 / ADP7182AUJZ-R7 | 2 / 2 | Exact local catalog matches C514356 / C514358. Do not match fixed-output suffix variants. |

Order attrition, minimum cut-tape quantities, consignment fees, tax and freight remain quote inputs. There is no completed all-parts cost estimate. No parts have been purchased.

## Enclosure and leads in parallel

The PCB can proceed as a prototype while its assembly is developed. The complete instrument still needs a fixed conductive enclosure, 20 mm HV-to-shield setback in three dimensions, insulating supports at H5/H6, a bonded panel BNC, paired captive HV leads, rated tip/termination insulation and strain relief. Fit two 9 V batteries in the LV compartment and align the two trim-access holes. Record the final geometry before compensation and CMRR measurements. A 240 × 84 mm PCB does not imply a 240 × 84 mm metal box.

Do not substitute ordinary 1 kV DMM leads, or infer a 3 kV working rating from a wire's hipot test. Lead/tip/feedthrough parts and the housing are not yet selected or included in the JLC quote. Their drawings, ratings and assembled clearances must be checked before HV use; board fabrication itself does not resolve those selections.
