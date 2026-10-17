# JLC PCBA viewer, first CPL upload (2026-10-17 ~10:45): `fab/cpl-jlcpcb.csv` lands the parts off the board

Uploaded: `fab/native-21-gerbers.zip`, `fab/bom-jlcpcb.csv`, **`fab/cpl-jlcpcb.csv`** (Y positive, 4.2 to 181.9 mm). JLC asked "the system
detects components that may be offset from the PCB, try to auto-align?"; the owner answered No (auto-align would move parts to
JLC's library footprints and hide our own centroids).

**Finding: the CPL Y sign is wrong for JLC.** In the viewer (`shots/placement-viewer-positive-y-2026-10-17.jpg`) a large cluster of
parts is drawn above and outside the board outline, while the board is drawn below them: the CPL previews mirrored top to bottom.
This is the case `cpl-rotation-audit/README.md` ("Not a rotation, but check it first: CPL Y sign") predicted: the Gerber frame has
the board at Y 0 to -190 and JLC's own KiCad plugins write negative Y; `fab/cpl-jlcpcb.csv` and `fab/positions-kicad.csv` use
positive Y. The README asks to confirm in the preview which of the two files lands parts on their pads: **the positive-Y file
does not.** No rotation check is meaningful on this preview.

**Next:** upload `cpl-rotation-audit/cpl-jlcpcb.corrected-ynegated.csv` (32 rotation corrections applied and Y negated) and
re-read the viewer. If parts then land on their pads, `fab/` needs a Y-negated CPL as the order file (today's `fab/cpl-jlcpcb.csv`
is not what JLC wants).

## Which parts the viewer lists
It lists only parts JLC will place: the 75 matched lines with stock. Absent from the list (so absent from any placement check):
the 8 shortage lines (C5 / C6, D3 / D17, F1, F2, J2 / J5, J6, L1, Q2 / Q3 / Q5 / Q6) and the two unmatched lines (bank, U41 / U42).
Of the 23 NEEDS-PREVIEW parts, **F2, J2, J5 and J6 cannot be checked here**; the other 19 are listed.
