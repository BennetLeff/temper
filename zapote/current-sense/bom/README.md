# Current-sense BOM

`bom.csv` and `bom.json` are grouped from the final compiled source manifest: 21 placed items, of which 20 are purchased components; J1 is a pair of bare primary solder lands. The JSON binds its source-manifest hash. Native references, footprint names and exact MPNs are retained.

The two bias resistors are Panasonic ERA3AEB102V (1 kΩ, 0.1%, 0603). The OR gate is TI CD74HC4075M96 (SOIC-14). These replace the earlier draft's 10 kΩ bias parts and unverified SN74HC4075DR identity. The source, schematic and routed board were synchronized and native parity checked after the changes.

The dated 2026-09-11 distributor review is retained in `review-*` files as historical research. Those files describe an earlier source revision; they are not the final BOM. The final Nexperia datasheet link is the manufacturer's `assets.nexperia.com` document in `bom.json`.

Procurement is not closed: TLV3201AIDBVR and BAT54H,115 were reported out of stock at the checked DigiKey/Mouser US listings. The TLV alternate reel quantity was also out of stock; BAT54H,135 stock was not established. The exact Coilcraft reel configuration and some passive quantities need manual confirmation. CD74HC4075M96 had stock at both distributors. Availability is a dated observation, not a reservation. No purchase has been made.

A replacement comparator or clamp must retain the package/pin map and undergo renewed offset, bias, leakage, hysteresis, input-range and timing review. The existence of a footprint-compatible part alone does not establish electrical equivalence. These procurement gaps do not erase the completed source/layout experiment, but they prevent calling it ready to order.
