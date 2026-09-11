# Transformer footprint correction

The existing `temper:CST3015` footprint was drawn with primary lands 9.0 mm wide and 4.8 mm tall, and a 13.8 mm row spacing. That produces only 9.1 mm vertical copper clearance. Its description claimed those dimensions came from Coilcraft's recommended land pattern.

The official drawing retained in `../cst3015.pdf`, page 2 (Document 1608-2, revised 09/08/25), shows **4.8 mm horizontal width and 9.0 mm vertical height**. The 6.36 mm primary dimension is between inner horizontal edges. The **18.5 mm vertical dimension is between the bottom of the primary lands and the top of the secondary lands**. It is neither centre spacing nor overall height.

The new `temper:CST3015_Datasheet2025` uses primary centres x=±5.58 mm, y=−11.55 mm, and secondary centres x=±6.88 mm, y=13.75 mm. Primary lands are 4.8×9.0 mm; secondary lands are 3.0×4.6 mm. Row centres are 25.3 mm apart, leaving the specified 18.5 mm vertical edge gap. Pad numbers follow the recommended land-pattern view: 2/1 at upper left/right and 3/4 at lower left/right. The land envelope is centred vertically; the fabrication outline is a nominal 23×30 mm component envelope, not a detailed body model.

`interpretation.json` binds the PDF, legacy footprint and correction. `native-pads.json` is KiCad's independent readback of actual pad positions and dimensions. `official-land-pattern.png` retains the drawing crop used in review. The legacy file is retained unchanged as `CST3015-legacy.kicad_mod`.

This correction removes the alleged 9.1 mm *PCB-pad* limitation for the new unit. It does not establish the transformer's internal/body insulation compliance with the cooker requirements. The full-cooker board and shared legacy footprint have not been changed; they need a separate consumer audit before migration.
