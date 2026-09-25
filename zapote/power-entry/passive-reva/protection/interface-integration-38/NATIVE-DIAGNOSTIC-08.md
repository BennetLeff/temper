# Rev38 native-library ERC diagnostic

**Status: diagnostic only, 2026-09-24. U7 native acceptance OPEN.** This
temporary `source-build-05` build adds project-local library registration to
the grid- and footprint-corrected candidate from `NATIVE-DIAGNOSTIC-07.md`.
It uses the same unreviewed shelf poses and 360 × 250 mm planning outline.

The strict candidate generator now writes a local KiCad project file to
activate its `fp-lib-table`, and a `sym-lib-table` with a matching generated
numeric-pin symbol library. The flat schematic's embedded symbol IDs and
instances use that same library nickname. Each symbol uses the selected
per-reference MPN identity, while its pin names remain numeric placeholders.
This is a library-resolution repair, not a functional pin-name audit.

KiCad 10.0.4 ERC dropped from **383** to **63 warnings**. All 295
`lib_symbol_issues` and 25 `footprint_link_issues` are gone; the remaining
63 `isolated_pin_label` warnings correspond exactly to 63 single-node nets
in the frozen source. They are recorded for individual disposition, not
silenced or counted as an ERC pass. KiCad's exported netlist remains equal
to the source projection: **295 references, 246 named nets and 1,052 numeric
`(net, reference, pin)` edges**, with zero missing or extra edges. The board
is byte-identical to `NATIVE-DIAGNOSTIC-07.md`, with 22 DRC violations and
the 499 unconnected-item report cap.

| Artifact | SHA-256 / scope |
| --- | --- |
| Frozen `source-build-05` receipt | `4f07f1177fbe39eef940e665892c40285e77925ce4f4622ddbf21cd38672a7f5` |
| Temporary poses | `46d114daca00f24e90a2362ae6ef9ff2b5ac65452d31afde73842fbddf73419b` |
| Temporary board | `d37b17eceec966e2b423af80422af92c6ca3d3c9a9a629437428e99964678ece` |
| Temporary schematic | `f2cf70eb44d0e5e5577940200d59dd18be332f660aa3e3dc4c87d3337ab6f1c5` |
| Generated numeric symbol library | `1c9af0e3904b2527427570ba61e8cf31365f8d16bbedf3811a0f682cc558e8f9` |
| Project `sym-lib-table` | `393fba00707f527cec187a10c12f9c43305160d4dd5cb18e52cc9ee324f12968` |
| Project `fp-lib-table` | `3ec742ee827183db4e22af4ac432c25bfb1a139c7da670fdea5c28ddc452d9f3` |
| Project file | `ca3d163bab055381827226140568f3bef7eaac187cebd76878e0b63e9e442356` |
| Source manifest | `17e04c5de641c64859757bc01d1a69969cf1df76dae75a17747a7d02a1b29d9f` |

The temporary files are under `/tmp/temper-rev38-erc-library-generated-05`.
The 63 single-node nets and their board pads must remain traceable in any
future ERC disposition. No routed copper, insulation construction, reviewed
placement, or physical timing evidence is present.
