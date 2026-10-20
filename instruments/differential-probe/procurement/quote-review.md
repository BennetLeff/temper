# JLCPCB live quote review — 2026-10-20

Status: incomplete engineering-prototype quote. Five PCBs, two populated. No order or payment submitted. The user explicitly authorized acceptance of JLC's assembly terms; that acceptance completed and BOM/CPL processing succeeded. The assembly draft was saved by JLC. Private contact details and checkout session URLs are excluded from this repository.

## Reject the initial automatic matches

JLC matched generic Comment values despite the separate MPN and Manufacturer columns. Examples included X7R instead of C0G compensation capacitors and lower-precision substitutes for 0.01% resistors. The initial table is archived as [rejected matching evidence](validation/jlc-initial-matches-rejected.json), not approved assembly data.

The export now puts MPN in Comment, preserves the electrical Value in its own column, and supplies 39 verified catalog mappings from [jlc-part-map.json](jlc-part-map.json). [Exact search results](exact-part-search.json) preserve the lookup evidence. A catalog ID identifies a part; it does not reserve stock or qualify it electrically.

The saved revised UI has 87 selected references with matching MPNs, and 48 awaiting sourcing/allocation. [Reviewed table](validation/jlc-reviewed-matches.json) preserves all 135 reference rows. Eleven 499-ohm precision-resistor references still display an incorrect automatic candidate but remain unchecked. The initial MDD SS14 matches were rejected. D4–D7 now select verified Diodes Incorporated B140-13-F / C15759. Do not use JLC's headline “confirmed” count as an exact-part acceptance count.

## Global sourcing cart — seven exact part lines

These lines cover all 48 references awaiting sourcing/allocation per PCB. All offers selected are DigiKey through JLC, with the search displaying 8–14 business days to source. They are in the sourcing cart, not purchased, allocated, or added to an approved placement preview.

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

This is only a partial component purchase. It excludes JLC-stock components, PCBs, assembly, any further taxes/fees, final shipping to Austin, and enclosure/leads. It is not the delivered price of two probes. The authorized contact details were saved in JLC checkout. End use is Commercial, with application described as a differential oscilloscope probe for commercial Temper induction-cooktop development and testing, destination United States. Checkout additionally requires the separate Customer Compliance Statement; it was viewed but its I Agree button was not pressed, and the checkbox is clear. No order was submitted. Payment has not been authorized.

## Part identities resolved; allocation remains pending

R12/R32 now use RT0805BRD07220RL / C865304, D4–D7 use B140-13-F / C15759, and D8 uses 1N4148W-7-F / C83528. The [part-selection record](../docs/part-identity-corrections.md) documents manufacturer ordering, ratings and land-pattern checks. Source generator, schematic and BOM were regenerated; the corrected BOM was uploaded and the saved JLC draft was reloaded to confirm all 135 references, including D5. All 87 selected rows match their exact MPNs. The eleven incorrect 499-ohm candidates remain unchecked.

The schematic net/pin assignments and generated copper instructions are unchanged. The final PCB diff contains only five hidden diode Value fields; placements, copper, slots and insulation geometry are byte-identical to the prior board. Fresh ERC/DRC and the board/source checks pass, with zero unconnected items. CPL is byte-identical. Regenerated fabrication files differ only in export metadata.

JLC's NEXT action opens “Project has unselected parts” and offers “Do not place” or “Select parts”. Returned to Select parts; no incomplete assembly order was accepted. The global-sourcing purchase/allocation and separate compliance acceptance are pending. The full assembly price, placement rotations and destination-qualified freight are still unavailable. Do not present USD 699.89 as the complete order total, and do not omit missing parts to advance the quote.
