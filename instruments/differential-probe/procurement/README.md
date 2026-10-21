# Rev C procurement preparation — 2026-10-20

**Status:** draft files only. Nothing has been uploaded, quoted with an account, ordered or paid for.

Rev C is the compacted Rev B. Its reasoning and the before/after table are in [`../docs/revc.md`](../docs/revc.md).

The Rev B procurement record covers the JLC upload, the rejected automatic matches and the partial sourcing cart. It is preserved in [`quote-review.md`](quote-review.md) and in git at `ca79d882f`. Its `validation/jlc-*.json`, `validation/renders/`, `catalog-check.json` and `exact-part-search.json` files are Rev B evidence and do not describe this board.

## Prepared files

- [Gerber/drill ZIP](revc-gerbers.zip), from [`gerbers/`](gerbers/): four copper layers, masks, paste, silk, and the routed outline with ten capacitor slots and the inter-leg notch.
- [JLC BOM](bom-jlc.csv) and [placement](cpl-jlc.csv): 105 references, matching the BOM exactly. BT1/BT2 are bottom-side THT.
- [Native position export](positions-raw.csv) and [component export](components-raw.csv).
- [Checksums](validation/sha256.txt), [ERC](validation/erc.rpt), [DRC](validation/pcb-drc.json) (0 violations, 0 unconnected) and [assembly parity](validation/assembly-parity.json).

Run `sh procurement/export.sh` from the probe directory. It re-runs ERC and DRC, clears `gerbers/` and rebuilds every file above. It does not edit parts or the PCB.

The JLC Comment field carries the MPN, because JLC matched generic values when this was not done for Rev B.

## Part identities

[`jlc-part-map.json`](jlc-part-map.json) is pruned to the Rev C BOM. It adds the identities checked on 2026-10-20:

| MPN | LCSC part | LCSC stock |
|---|---|---|
| HVCB2512BDE2M00 | C4553702 | 0 |
| OPA2810IDR | C1849413 | 4,074 |
| MDD SS14 | C2480 | — |
| Vishay 1N4148W-E3-18 | C191428 | — |
| Amphenol 031-5431-10RFX | C6956217 | 33 |

These Rev C MPNs have **no reviewed LCSC identity**:

- KEMET C1812C330JHGACTU (also unmapped in Rev B), C0805C302F5GACTU and C0805C161F5GACTU.
- Stackpole RNCF0603TKY499R, RNCF0603TKY1K00 and RNCF0603TKY2K00.
- Yageo RT0805BRD07220RL and RT0805BRD0766K5L.
- The PCB-mount C&K 7101SDAV2BE and 7201P3DAV2QE, and the MPD BH9VPC.

Source these by exact MPN, through global sourcing or consignment. Do not accept automatic substitutions.

The S1/S2 select-on-test positions also need small kits of neighbouring E24 1% C0G values, chosen at calibration (see [`../docs/design.md`](../docs/design.md)).

**Stock risk.** On 2026-10-20 DigiKey had 9 × HVCB2512BDE2M00 against the 20 needed for two boards, with an 18-week lead time. This is an owner decision; see [`../docs/revc.md`](../docs/revc.md#1-2-mω-hv-resistors-10-instead-of-20).

## Component prices

Public DigiKey/LCSC prices checked on 2026-10-20 are in [`prices-2026-10-20.csv`](prices-2026-10-20.csv). `python3 procurement/cost.py` gives $535.81 in components for two Rev C boards, against $768.27 for Rev B. The caveats are in [`../docs/revc.md`](../docs/revc.md#cost-dated-2026-10-20).

Out of stock at DigiKey on that date, with LCSC stock: OPA2810IDR (C1849413), BAV199 (C40919), MMBT3906 (C75549), and RT0805BRD0749R9L, RT0805BRD0747KL and RT0805BRD0730KL. C0805C302F5GACTU and C0805C161F5GACTU were not in stock anywhere checked.

## Fabrication quote reference

These are public JLC quote-page prices, not logged in, for 5 pcs, 1.6 mm, 1 oz, standard build:

| 150 × 70 mm | HASL lead-free | ENIG |
|---|---:|---:|
| 4 layers (includes $25 engineering fee) | $36.80 | $49.30 |
| 2 layers (not adopted) | $10.40 | $26.90 |

Assembly was not quoted, because that needs an account upload. Slots of at least 1.0 mm are within JLC's standard routing; the slot path is far below the length that triggers a fee.

## Enclosure and leads

The enclosure is a Hammond 1455N2201. Mounting, standoff height and lid holes are in [`../docs/layout.md`](../docs/layout.md#enclosure-shield-and-mounting).

The HV leads, tips, feedthroughs and strain relief are designed in [`../docs/hv-leads.md`](../docs/hv-leads.md), which lists every part with its rating basis and its 2026-10-20 price and stock. Quantities for two probes are in [`leads-bom.csv`](leads-bom.csv); `python3 procurement/cost.py` gives **$771.05**, of which the single 100 ft spool of Alpha Wire 392040 RD005 (UL AWM 3239, 10 kV DC) is $664.22. The Stäubli 23.0480-21 J2 adapter was only found at element14 (NZD 18.13 per 2) and is not in the USD total.

Two copper-free FR4 parts are made by JLC. Run `sh procurement/export-mech.sh` from the probe directory to regenerate them from [`../tools/leads.rs`](../tools/leads.rs); it DRC-checks both boards and writes:

- [Tip plate Gerbers](tip-plate-gerbers.zip) and [DXF](mech/tip-plate/tip-plate-outline.dxf): 103.12 × 53.09 mm, 1.6 mm, replaces the Hammond aluminium tip-end plate. Order with no copper (or with the empty copper layers as supplied), any solder-mask colour, white silkscreen. Ask for countersunk screw holes (Ø5.84 mm × 82°) to reuse the Hammond flat-head screws; otherwise use #6 pan-head thread-forming screws.
- [Lead bridge Gerbers](lead-bridge-gerbers.zip) and [DXF](mech/lead-bridge/lead-bridge-outline.dxf): 86.0 × 69.0 mm, 1.6 mm.

Neither part has been quoted; the 150 × 70 mm two-layer quote above ($10.40 for 5) bounds each. Checksums are in [`mech/sha256.txt`](mech/sha256.txt).

Do not substitute ordinary 1 kV DMM leads, and do not substitute wire without a UL style or a stated test voltage.
