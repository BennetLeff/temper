# Source evidence

Retrieved/checked on 2026-10-20. Manufacturer datasheet links for every selected component are embedded in the schematic and exported BOM. Additional design references are in `../docs/design.md`.

The PDF/text pairs here preserve the accessible TI data sheets and the KEMET 33 pF specification. Other manufacturer documents were inspected through web retrieval; their URLs are retained, but a local copy was not available for every document. Plain-text extracts accompany the PDFs for reproducible pin and ordering-table inspection.

`catalog-snapshot.json` and `catalog-final-selections.json` preserve catalog searches, including rejected or misspelled candidates. They are search history, not the selected BOM. In particular, the selected comparator ordering codes include the **A**: TLV1704AIPWR and TLV1702AIDGKR. The thin-film RT0805BRD0797R6L search was superseded by the selected, available catalog alternative RC0805FR-0797R6L (97.6 Ω, 1%; LCSC C483266). The local catalog returned 98 pieces for that alternative; this is cached catalog evidence, not a live-stock promise.

The authoritative selections are the schematic MPN fields, exported to `../bom.csv`. LCSC identifiers are provided where cross-checked, but this is not a JLC assembly release. Main selected catalog matches include ADA4817 C207502, OPA810 C1852077, TLV1704 C181596, TLV1702 C2870937, CD4013 C13527, TL431 C41283, BAV199 C40919, and the two LDOs C514356/C514358. Recheck exact MPN, package, tolerance and current stock before ordering.

Do not substitute a part based on a matching family name alone. The board-level source check verifies pad numbers, not authorized substitutes. The high-voltage resistor tolerance and the TI TL431 DBZ pinout are particularly consequential.
