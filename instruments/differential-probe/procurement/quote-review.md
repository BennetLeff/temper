# JLCPCB live quote review — 2026-10-20 (Rev B, historical)

> This record describes the **Rev B** board (commit `ca79d882f`). Rev C has not been uploaded or quoted with an account; see [README.md](README.md). The R12/R32 and D4–D8 identity corrections listed below are applied in Rev C.

Status: incomplete engineering-prototype quote. Five PCBs, two populated. No order or payment submitted. The user explicitly authorized acceptance of JLC's assembly terms; that acceptance completed and BOM/CPL processing succeeded. The assembly draft was saved by JLC. Private contact details and checkout session URLs are excluded from this repository.

## Reject the initial automatic matches

JLC matched generic Comment values despite the separate MPN and Manufacturer columns. Examples included X7R instead of C0G compensation capacitors and lower-precision substitutes for 0.01% resistors. The initial table is archived as [rejected matching evidence](validation/jlc-initial-matches-rejected.json), not approved assembly data.

The export now puts MPN in Comment, preserves the electrical Value in its own column, and supplies 36 verified catalog mappings from [jlc-part-map.json](jlc-part-map.json). [Exact search results](exact-part-search.json) preserve the lookup evidence. A catalog ID identifies a part; it does not reserve stock or qualify it electrically.

The revised UI has 80 selected references with matching MPNs, and 55 unresolved/unselected references. [Reviewed table](validation/jlc-reviewed-matches.json) preserves all 135 reference rows. Eleven 499-ohm precision-resistor references still display an incorrect automatic candidate but remain unchecked. D4–D7 were manually unchecked because JLC C2480 is MDD SS14, whereas the schematic names Diodes Incorporated. Do not use JLC's headline “confirmed” count as an exact-part acceptance count.

## Global sourcing cart — seven exact part lines

These lines cover 48 of the 55 unresolved references per PCB. All offers selected are DigiKey through JLC, with the search displaying 8–14 business days to source. They are in the sourcing cart, not purchased, allocated, or added to an approved placement preview.

| MPN | Order quantity | Displayed cart extension, USD |
|---|---:|---:|
| HVCB2512BDE1M00 | 40 | 523.68 |
| C1812C330JHGACTU | 20 | 75.24 |
| GKG60015 | 4 | 8.10 |
| RNCF0603TKY499R | 22 | 40.09 |
| C1206C103F5GACTU | 4 | 42.64 |
| C0805C221J5GACTU | 10 | 1.63 |
| PTS645SL43SMTR92 LFS | 3 | 1.51 |

Cart subtotal: **$692.89**. Sourcing checkout adds **$7.00 handling**, displaying **$699.89**. The 220 pF line includes the displayed four-piece attrition allowance; the switch line includes one spare. Reconfirm any attrition requirements for the other lines when JLC allocates them. Search-page rounded extensions differed slightly from cart values; the table uses cart values.

This is only a partial component purchase. It excludes JLC-stock components, the three unresolved BOM lines below, PCBs, assembly, any further taxes/fees, final shipping to Austin, and enclosure/leads. It is not the delivered price of two probes. Checkout additionally requires a recipient first/last name and mobile number, requested from the user but not yet supplied. Payment has not been authorized.

## Remaining identity corrections before manufacture

- **R12/R32:** the schematic generates `RT0805BRD07220L`, which has no catalog or global-sourcing result. [DigiKey's exact 220-ohm, 0.1%, 0805 listing](https://www.digikey.com/en/products/detail/yageo/RT0805BRD07220RL/5139278) and LCSC C865304 instead use **RT0805BRD07220RL**. Correct the source generator's `r("220 R", "220")` argument to the manufacturer code after verifying the manufacturer ordering table, then regenerate the schematic/BOM and export evidence. This correction has not yet been applied to CAD or the quote.
- **D8:** `1N4148W,115` / Nexperia has no exact JLC or global-sourcing result. The referenced manufacturer PDF could not be retrieved. Establish a real orderable SOD-123 diode, with documented pinout and electrical checks for the reset circuit, before changing the BOM. No replacement is approved.
- **D4–D7:** `SS14` / Diodes Incorporated lacks a verified exact catalog match. Resolve the manufacturer/order-code combination against the original power/protection requirements. MDD C2480 was deselected; no manufacturer substitution is approved.

Do not proceed with a partially populated order to hide these gaps. After resolving identities, regenerate the procurement files, finish allocation, inspect component rotations and routed slots, enter the shipping details, and obtain approval for the actual complete total before payment.
