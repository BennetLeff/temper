# Enclosure coordination: candidate 23 / stage 38 (supply topology)

Record for the enclosure session (temper-f7). Nothing has been sent; this file is the request. Board frame as in the
fit gate (KiCad x right, y down, mm).

## What changes on the power board
| Item | s35 | s38 | Source |
|---|---|---|---|
| PS1 (IRM-20-15, 52.4 x 27.2 x 24 mm potted module) at (233.0, 126.0, 180 deg), courtyard [206.5, 112.1, 259.5, 139.9] | fitted | **deleted**; the area stays empty (no part moved into it, DECISIONS 47 item 6) | `native-21/layout/place.py`; `validation-plan/enclosure-fit/native21-courtyards.json` |
| PS2 at (163.7, 3.6) | MEAN WELL IRM-20-24 | **MPM-20-24**, same Case 219A body 52.4 x 27.2 x 24 mm and pin map; pin length 3.5 +1 / -0.5 mm (IRM-20: +/-1) | MPM-20-SPEC 2024-10-30 p.4; IRM-20-SPEC 2025-11-21 p.3 |
| Board heat (B3 heat file) | PS1 1.52 W nominal / 3.0 W worst (half into the board) | PS1 row gone; PS2 row unchanged (2.775 W worst, IRM efficiency kept although MPM-20 is 87 % typ) | `round5-native21/b3/inputs/native21-board-heat-sources.json` |
| J4 pin 1 | V15_SELV (15 V from PS1) | not connected (`j4_nc1`) | `CONTROLLER-REQUEST.md` addendum 2 |

Board-only fit on s38: FIT 400 / 0 / 0 / 402 / 0 (s35: 401 / 0 / 0 / 403 / 0; one part fewer). B3 ratings on s38 are the
s35 values (laminate -56.4 K, rated part -38.9 K): the release gate is still open on the R5 / FET-row copper, not on
anything this stage touched. The ZC-string resistors R67-R70 next to the old PS1 site run 1.4-2.0 K cooler.

## Requests
1. **Envelope above the old PS1 site.** The 24 mm module height over [206.5, 112.1, 259.5, 139.9] is gone. If the
   enclosure reserved that volume (cable routing, the PS3 bay or a duct), it is free on s38; tell us before anything
   is placed there, because the power board keeps it empty for now.
2. **PS3 is MEAN WELL MPM-65-15ST in the chassis** (controller request item 6) and now also carries the controller
   logic (PS1 deleted, J13 rail merge). The bay-air ceiling in `CONTROLLER-REQUEST.md` ("Needed from elsewhere":
   PS3 bay air <= 58 C) still applies; MPM-65's ambient limit is 60.7 C against IRM-60's 60.3 C at that load.
3. **D-22 inlet module choke** becomes the KEMET / YAGEO SCF31X-220-2R1A011JH (`MODULE-REQUEST.md`): 45 x 42 x 33 mm
   max, 91.9 g, -40 / +130 C. Please check the module's choke space and fixing for that body.
4. Nothing else moves: J11, F2, R130, D3, D17 and every connector keep their s35 poses.
