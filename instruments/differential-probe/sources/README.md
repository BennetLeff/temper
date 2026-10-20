# Source evidence

Retrieved/checked on 2026-10-20. Manufacturer datasheet links for every selected component are embedded in the schematic and exported BOM. Additional design references are in `../docs/design.md`.

The PDF/text pairs here preserve the accessible TI data sheets and the KEMET 33 pF specification. Other manufacturer documents were inspected through web retrieval; their URLs are retained, but a local copy was not available for every document. Plain-text extracts accompany the PDFs for reproducible pin and ordering-table inspection.

`catalog-snapshot.json` and `catalog-final-selections.json` preserve catalog searches, including rejected or misspelled candidates. They are search history, not the selected BOM. In particular, the selected comparator ordering codes include the **A**: TLV1704AIPWR and TLV1702AIDGKR. The thin-film RT0805BRD0797R6L search was superseded by the selected, available catalog alternative RC0805FR-0797R6L (97.6 Ω, 1%; LCSC C483266). The local catalog returned 98 pieces for that alternative; this is cached catalog evidence, not a live-stock promise.

The authoritative selections are the schematic MPN fields, exported to `../bom.csv`. LCSC identifiers are provided where cross-checked, but this is not a JLC assembly release. Main selected catalog matches include ADA4817 C207502, OPA810 C1852077, TLV1704 C181596, TLV1702 C2870937, CD4013 C13527, TL431 C41283, BAV199 C40919, and the two LDOs C514356/C514358. Recheck exact MPN, package, tolerance and current stock before ordering.

Do not substitute a part based on a matching family name alone. The board-level source check verifies pad numbers, not authorized substitutes. The high-voltage resistor tolerance and the TI TL431 DBZ pinout are particularly consequential.

## Rev B additions

`GKG60015-EW-2026.pdf` is the April 2026 EW Electronics drawing for the selected 12–60 pF top-adjust trimmer. `GKG-trimmers.pdf` and its text extract provide the legacy family detail used to cross-check terminal geometry and rotor connection. The local footprint pin numbers are explicitly assigned in the circuit record; inspect the received part against that drawing.

`CST3015.pdf` and its text extract preserve Coilcraft document 1608 for the stage-53 CT correction. The [calculation record](../docs/stage53-ct-correction.md) includes the document identity, verified board hash and limits of the sinusoidal and DC-pulse calculations.

`OPA810-model.zip` and `opa810_a.lib` archive TI’s unmodified OPA810 Rev A PSpice model (2020-06-11), retrieved from [TI SBOMB73](https://www.ti.com/lit/zip/sbomb73). Model and fixture hashes are in `../validation/spice/sha256.txt`; the limitations, including clipping slightly beyond ideal rails, are documented in the [circuit record](../docs/circuit-revb.md).

## Procurement identity corrections

`B140.pdf`, `1N4148W.pdf` and `Yageo-RT.pdf`, with text extracts, preserve the official manufacturer documents supporting the [three corrected orderable-part entries](../docs/part-identity-corrections.md). Earlier catalog snapshots retain the rejected identities as history.
