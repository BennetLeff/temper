# Power-part 3D models

These six STEP files give the PCB a visible body for BR1, D3, J6, RV1, L1 and T1. They are **provisional geometry** built from manufacturer dimensions and the reviewed local pad coordinates. They are not manufacturer CAD and are not evidence of screw, lead-form, wire-entry, package creepage or enclosure fit. The colored VRML files are optional visualizations; the board uses STEP files for mechanical export.

`model-map-power-parts.json` in the parent directory records each part's footprint, source documents, dimensions, SHA-256 and limits. All assets are original geometry generated in this repository; no vendor CAD files are redistributed. The STEP geometry uses millimetres with a KiCad model scale of 1. The optional VRML uses millimetres with a KiCad model scale of `0.3937008`.

The six STEP files can be rebuilt with OpenCascade 7.9.3:

```sh
for part in bridge diode kds tmov choke ct; do
  PS_MODEL="$part" /opt/homebrew/bin/DRAWEXE -b -f generate_step.tcl
done
```

Each shape reported valid in OpenCascade. Its model origin is the footprint origin: model X equals footprint X, model Y is the negative of footprint Y, and Z is positive above the PCB. The body envelopes are:

| Ref | Body maximum or nominal size | Footprint-alignment detail |
| --- | --- | --- |
| BR1 | 30.3 × 4.8 × 20.3 mm overall height | Leads at X = 0, 10, 17.5, 25 mm |
| D3 | 12.954 × Ø7.874 mm body | Locally formed to 20 mm pitch |
| J6 | 5.08 × 27 × 25 mm installed body | Two pins at Y = 0, 15.24 mm |
| RV1 | Ø23 × 9 mm disc; 28 mm seated height | Locally formed to 7.5 mm pitch |
| L1 | 45 × 25.5 × 41 mm body | Four pins on 10 × 25 mm grid |
| T1 | 23 × 30 × 15.2 mm body | Four pads at authored footprint centres |

TDK [publishes a STEP archive](https://product.tdk.com/en/search/emc/emc/line-filter/info?part_no=B82726S2203A020) for L1, but the archive returned HTTP 403 when fetched for this work. [Coilcraft lists a 3D model](https://www.coilcraft.com/en-us/products/transformers/power-transformers/current-sensing/cst3015/cst3015-100e/) for T1, and [Phoenix lists CAD downloads](https://www.phoenixcontact.com/en-us/products/printed-circuit-board-terminal-kds-3-1704004) for J6. Their exact downloadable files were not accessible here. Replace these provisional models with vendor files or measured part geometry before relying on a 3D enclosure check.
