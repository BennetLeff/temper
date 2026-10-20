# Placement angle audit

On2026-10-20 the independent reviewer compared numbered PAD shapes from the LCSC-owned EasyEDA footprint API with native KiCad pad positions. The saved JSON responses under`sources/placement-library/` contain the owner, footprint UUID, header origin and actual PAD records. These are source evidence; their geometry was not copied into this PCB. Manufacturer drawings remain the land-pattern authority.

| Parts | LCSC | LCSC library zero pose | Added CCW offset | Final CPL |
|---|---|---|---:|---:|
| U1 | C130462 | Pin1 bottom-left; numbered pads run right along bottom |270° |270° |
| U2 | C57767 | Same numbered-pin order |270° |270° |
| U3 | C26360 | Same numbered-pin order |270° |270° |
| U4,U5 | C51118 | Same numbered-pin order |270° |270° |
| D1 | C7519 | Same numbered-pin order |270° |270° |
| Y1 | C725988 | Pin1 bottom-left, matching native footprint |0° |0° |
| J1 | C165948 | Numbered contacts align with native footprint |0° |180° |

All numbered pins, rather than only a pin1 dot, were used to discriminate rotation/reflection. Native KiCad IC footprints at0° have pin1 top-left and numbering down the left. JLC's positive angle convention is counterclockwise per its [pick-and-place documentation](https://jlcpcb.com/help/article/pick-place-file-for-pcb-assembly). R/C parts are nonpolar and retain native angles. Exact exported values are in`manufacturing/orientation-audit.csv`.

**Final JLC placement preview remains required.** An EasyEDA footprint zero pose is evidence for the part-specific correction, but it does not prove a particular JLC feeder/machine setup. J1 especially requires checking both orientation and position: the old library's header origin differs from its body centre, and its land pattern differs from the manufacturer's2020 drawing. CPL coordinates use the reviewed native footprint mechanical anchor; do not infer a translation from signal-pad centroid alone. Compare connector body, shell slots and PCB edge in the vendor preview before assembly approval.

No BOM/CPL was uploaded to JLCPCB and no assembly order was submitted.

Passive-axis evidence is also archived: R0603 UUID398691f1f785460098bbe5ee6590333c, C0603 f8151fdc728a41ebbc304e11d39e5437, C0805 2ee8eb13a0124a108e622ce40c0c25a8, C1206 7bdec8012728462a85919a4d0d033579. Each has pad1 left/pad2 right at zero, matching native KiCad. The catalog metadata links the specified parts to those footprints. **Exception:** EverOhms C3202456 (R13/R14/R19) has no vendor footprint UUID in the retrieved catalog; its0603 package axis is assumed to match the standard nonpolar R0603 model. Confirm these three placements in the final vendor preview.
