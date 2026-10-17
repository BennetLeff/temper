# Native19 component models

The [current inventory](../verification/model-inventory.json) records 142 resolved
component references, including 24 authored provisional envelopes. Follow the
[native19 reproduction commands](../verification/reproduction-commands.json)
to rebuild and inspect the candidate. The PCB adapter applies model assignments;
the inventory checker must report no missing models before exporting STEP.

Local assets use `${KIPRJMOD}/models3d/` inside native19. Stock models still
require the KiCad10 standard model library. Footprints are loaded from the
committed `candidate-libs/`; rebuilding does not replace them from a global
footprint library.

The family README files and `model-map-*.json` retain historical native09
provenance, dimensions, source URLs and limitations. Their old reference counts
and assignments do not describe the current board; use the current inventory.
R5 uses the correctly named `WSK25121L000FEA-envelope.step`, with its provisional
body dimensions documented in the [candidate overview](../README.md).

These are engineering visualization models, not qualified manufacturer CAD.
Lead forms, installed heights and mounting details may be simplified. They do
not establish enclosure fit, heatsink contact or insulation. Loose harnesses,
fasteners, heatsink and enclosure are outside the PCB STEP.
