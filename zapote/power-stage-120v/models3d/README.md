# Native-09 component models

All 114 footprints now resolve a visible model in KiCad 10.0.4. The 92 existing
working library assignments are retained. Sixteen original STEP assets cover
the other 22 components, including five broken library links.

The added models are **provisional dimensioned envelopes**, not manufacturer
CAD. See the three `model-map-*.json` files and family README files for exact
reference assignments, source URLs, dimensions, hashes and limitations. Lead
forms, installed heights, mating connectors and mounting details may be
simplified. These models do not qualify enclosure fit or insulation. Loose
straps, lugs, harnesses, screws, heatsink and enclosure are not included.

Models use `${KIPRJMOD}/../models3d/` paths, so keep this directory beside
`native-09`. The remaining stock models require KiCad's standard model library.

## Reapply after regenerating or replaying the board

Run these explicit finishing adapters with KiCad's Python, from this unit:

```sh
"$KICAD_PY" tools/apply_reference_labels.py native-09/section.kicad_pcb \
  reference-labels.json /tmp/labeled.kicad_pcb /tmp/labels-receipt.json
"$KICAD_PY" tools/apply_3d_models.py /tmp/labeled.kicad_pcb /tmp/modeled.kicad_pcb
```

Use fresh output names, verify the result, then replace the active board.
The adapters only edit footprint fields and model assignments. The frozen
placement generator is intentionally unchanged: editing it would invalidate
the native-08 replay provenance. Reference positions are authored for this
placement and need review if any footprint moves.

The [presentation verification](../native-09/verification/presentation/README.md)
records current board hashes, model coverage, unchanged physical geometry and
fresh checks.
