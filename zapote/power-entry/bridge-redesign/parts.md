# Bridge part and package identity

All candidates retain the exact source-bound bridge part:

| reference | manufacturer / MPN | KiCad footprint | package facts used |
| --- | --- | --- | --- |
| U1 | Diodes Incorporated / GBU2510A | `Diode_THT:Diode_Bridge_GBU2510` | Inline 4-pin through-hole bridge; 5.08 mm pitch; body approximately 21.8–22.3 × 18.3–18.8 × 17.5–18.0 mm |

The baseline source manifest, schematic symbol and local footprint library are
copied into every candidate bundle. No alternate package is claimed in this
checkpoint: the 6 mm constant-width attempt fails the 2 mm clearance profile,
while the 3 mm attempt does not close the 15 A current screen. An alternate
package requires a separately sourced, dated manufacturer drawing and
mechanically mountable replacement before it can replace U1.

The physical-model and cooling owners should use the exact U1 body, lead and
pad dimensions from their reviewed inputs. The approximate body dimensions
above are a routing-envelope reference, not a substitute for the datasheet
land pattern or thermal rating.
