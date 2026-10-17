# JLC PCBA viewer with the Y-negated CPL (2026-10-17 ~10:50): parts land on the board

Uploaded `cpl-rotation-audit/cpl-jlcpcb.corrected-ynegated.csv` (copy `~/Documents/jlc-upload/cpl-ynegated.csv`), BOM unchanged,
auto-align answered No. Result: **every listed part lands on the board** (`shots/placement-viewer-negated-y-2026-10-17.jpg`).
The positive-Y `fab/cpl-jlcpcb.csv` did not (see PLACEMENT-VIEWER-2026-10-17.md). So the order CPL must be Y-negated; `fab/` still
holds the positive-Y file and has not been changed.

## Per-part look at the NEEDS-PREVIEW list (read through the viewer's 3D model; gross alignment only, pin 1 not verified)
| Part(s) | Viewer result |
|---|---|
| C126-C129 (electrolytics) | Model on its four pads, "+" marks visible; polarity not checked against the board silk |
| J1 (Phoenix 2-pos) | Body inside its outline, screw circles over the pads |
| J4 (Micro-Fit 2x8) | Body inside its outline, pin-1 marker visible, no offset |
| PS2 (MPM-20-24) | Body on the footprint, A- / A+ / AC/N / AC/L pins on the pads |
| R5 (1 mOhm shunt) | Body ends on the two current pads, the two sense fingers outboard (as designed) |
| T1 (CST3015) | Body on its outline, pin-1 marker top right |
| U1, U2 (2EDR8259 SOIC-16W) | Models on the footprint outlines, pin-1 dots visible; orientation not compared with the board silk |
| RV1 (TMOV20RP) | **Unclear**: the model (a rectangle with a grey square and a disc) does not obviously match the footprint; the audit said the pad layouts match "no better than 2.30 mm rms" |
| D18-D20 (SOT-23) | Selected but the viewer did not zoom onto them; **not judged** |
| R130, U36, U43, U44 | **Not looked at yet** |
| F2, J2, J5, J6 | **Not in the viewer** (JLC shortage lines): cannot be checked here |

JLC's own DFM review of the placement happens 4-6 hours after an order is placed (a note on the preview page), so this is a
coarse check, not a verdict.
