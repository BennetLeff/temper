# FR-4 pad Gerber check (scripts/bench_pads_verify.py; do not edit)

Files: `fab/pads/bench-pads-1.6mm-r1.zip`, `fab/pads/bench-pads-0.8mm-r1.zip`. Renders: `fab/pads/bench-pads-*-r1.png` (gerbv: outline black, NPTH red, silk blue, F.Mask openings green).

| zip | check | measured | expected | verdict | note |
|---|---|---|---|---|---|
| 1.6mm | layer files | B_Cu.gbl, B_Mask.gbs, Edge_Cuts.gm1, F_Cu.gtl, F_Mask.gts, F_Silkscreen.gto, NPTH.drl | B_Cu.gbl, B_Mask.gbs, Edge_Cuts.gm1, F_Cu.gtl, F_Mask.gts, F_Silkscreen.gto, NPTH.drl | PASS |  |
| 1.6mm | panel size (outline bbox) | 60.000 x 48.000 | >= 3.0 x 3.0 (JLC min) | PASS | 60 x 48 by design |
| 1.6mm | outline closes into the panel and its milled slots | 4 slot regions, board area 2416.0 mm2 | >= 1 slot region, board = outer - slots | PASS |  |
| 1.6mm | NPTH sizes | 0.60 | >= 0.50, in (0.5, 0.8) | PASS |  |
| 1.6mm | NPTH hits inside the board | 84 of 84 | 84 of 84 | PASS |  |
| 1.6mm | mouse-bite pitch / web between holes | 0.833 / 0.233 | web in (0.2, 0.3) (JLC recommended) | PASS |  |
| 1.6mm | pieces after breaking along the bites | 1 frame + 6 pads + 3 pad-to-pad bridges | 1 frame + 6 pads | PASS | every tab fully perforated, else a pad stays joined |
| 1.6mm | pad routed outline (Edge.Cuts edges of each pad) | 14.000 x 16.000; 14.000 x 16.000; 14.000 x 16.000; 14.000 x 16.000; 14.000 x 16.000; 14.000 x 16.000 | 14.000 x 16.000 (bench_params.FR4_PAD) | PASS |  |
| 1.6mm | residue beyond the outline after the break (model) | max 0.039 mm | <= 0.10 mm | PASS | router-radius fillet just outside the last bite at each tab end; sand flush |
| 1.6mm | milled gap between neighbouring pads (x, y) | 2.000, 2.000 | in (1.6, 2.0) (JLC board spacing) | PASS |  |
| 1.6mm | frame rail widths (L, R, B, T) | 5.000, 5.000, 5.000, 5.000 | >= 3.0 (JLC tooling edge) | PASS |  |
| 1.6mm | milled gap pads-to-frame (L, R, B, T) | 2.000, 2.000, 2.000, 2.000 | in (1.6, 2.0) | PASS |  |
| 1.6mm | perforated tabs per pad | pad 1: bottom+top, pad 2: bottom+top, pad 3: bottom+top, pad 4: bottom+top, pad 5: bottom+top, pad 6: bottom+top | top+bottom each (the 14 mm edges) | PASS |  |
| 1.6mm | every tab joins the frame or a neighbouring pad | frame, pad 1, pad 2, pad 3, pad 4, pad 5, pad 6 | frame / pad n | PASS |  |
| 1.6mm | tab perforated width (first hole edge to last hole edge) | 5.600 | >= 5.0 (JLC mouse-bite tab minimum) | PASS |  |
| 1.6mm | tab centred on its pad edge (x offset) | max 0.000 | < 0.01 | PASS |  |
| 1.6mm | bite row inset from the pad's routed edge | 0.250 | 0.250 (break inside the outline) | PASS |  |
| 1.6mm | B_Cu.gbl empty (no copper) | 0 objects | 0 | PASS |  |
| 1.6mm | B_Mask.gbs: each pad wholly in a mask opening | 6 of 6 | 6 of 6 | PASS | bare laminate on both faces |
| 1.6mm | F_Cu.gtl empty (no copper) | 0 objects | 0 | PASS |  |
| 1.6mm | F_Mask.gts: each pad wholly in a mask opening | 6 of 6 | 6 of 6 | PASS | bare laminate on both faces |
| 1.6mm | silkscreen off the pads | 0 of 698 stroke points on a pad | 0 | PASS |  |
| 1.6mm | gerbv render (outline, NPTH, F.SilkS, F.Mask) | exit 0; no messages | exit 0, no messages | PASS |  |
| 1.6mm | gerbv loads B_Cu.gbl | exit 0; RS-274D guess (empty file) | exit 0 | PASS | gerbv's format guess for a Gerber with no apertures; the file is RS-274X with %FS/%MO |
| 1.6mm | gerbv loads B_Mask.gbs | exit 0; no messages | exit 0 | PASS |  |
| 1.6mm | gerbv loads Edge_Cuts.gm1 | exit 0; no messages | exit 0 | PASS |  |
| 1.6mm | gerbv loads F_Cu.gtl | exit 0; RS-274D guess (empty file) | exit 0 | PASS | gerbv's format guess for a Gerber with no apertures; the file is RS-274X with %FS/%MO |
| 1.6mm | gerbv loads F_Mask.gts | exit 0; no messages | exit 0 | PASS |  |
| 1.6mm | gerbv loads F_Silkscreen.gto | exit 0; no messages | exit 0 | PASS |  |
| 1.6mm | gerbv loads NPTH.drl | exit 0; no messages | exit 0 | PASS |  |
| 0.8mm | layer files | B_Cu.gbl, B_Mask.gbs, Edge_Cuts.gm1, F_Cu.gtl, F_Mask.gts, F_Silkscreen.gto, NPTH.drl | B_Cu.gbl, B_Mask.gbs, Edge_Cuts.gm1, F_Cu.gtl, F_Mask.gts, F_Silkscreen.gto, NPTH.drl | PASS |  |
| 0.8mm | panel size (outline bbox) | 60.000 x 48.000 | >= 3.0 x 3.0 (JLC min) | PASS | 60 x 48 by design |
| 0.8mm | outline closes into the panel and its milled slots | 4 slot regions, board area 2416.0 mm2 | >= 1 slot region, board = outer - slots | PASS |  |
| 0.8mm | NPTH sizes | 0.60 | >= 0.50, in (0.5, 0.8) | PASS |  |
| 0.8mm | NPTH hits inside the board | 84 of 84 | 84 of 84 | PASS |  |
| 0.8mm | mouse-bite pitch / web between holes | 0.833 / 0.233 | web in (0.2, 0.3) (JLC recommended) | PASS |  |
| 0.8mm | pieces after breaking along the bites | 1 frame + 6 pads + 3 pad-to-pad bridges | 1 frame + 6 pads | PASS | every tab fully perforated, else a pad stays joined |
| 0.8mm | pad routed outline (Edge.Cuts edges of each pad) | 14.000 x 16.000; 14.000 x 16.000; 14.000 x 16.000; 14.000 x 16.000; 14.000 x 16.000; 14.000 x 16.000 | 14.000 x 16.000 (bench_params.FR4_PAD) | PASS |  |
| 0.8mm | residue beyond the outline after the break (model) | max 0.039 mm | <= 0.10 mm | PASS | router-radius fillet just outside the last bite at each tab end; sand flush |
| 0.8mm | milled gap between neighbouring pads (x, y) | 2.000, 2.000 | in (1.6, 2.0) (JLC board spacing) | PASS |  |
| 0.8mm | frame rail widths (L, R, B, T) | 5.000, 5.000, 5.000, 5.000 | >= 3.0 (JLC tooling edge) | PASS |  |
| 0.8mm | milled gap pads-to-frame (L, R, B, T) | 2.000, 2.000, 2.000, 2.000 | in (1.6, 2.0) | PASS |  |
| 0.8mm | perforated tabs per pad | pad 1: bottom+top, pad 2: bottom+top, pad 3: bottom+top, pad 4: bottom+top, pad 5: bottom+top, pad 6: bottom+top | top+bottom each (the 14 mm edges) | PASS |  |
| 0.8mm | every tab joins the frame or a neighbouring pad | frame, pad 1, pad 2, pad 3, pad 4, pad 5, pad 6 | frame / pad n | PASS |  |
| 0.8mm | tab perforated width (first hole edge to last hole edge) | 5.600 | >= 5.0 (JLC mouse-bite tab minimum) | PASS |  |
| 0.8mm | tab centred on its pad edge (x offset) | max 0.000 | < 0.01 | PASS |  |
| 0.8mm | bite row inset from the pad's routed edge | 0.250 | 0.250 (break inside the outline) | PASS |  |
| 0.8mm | B_Cu.gbl empty (no copper) | 0 objects | 0 | PASS |  |
| 0.8mm | B_Mask.gbs: each pad wholly in a mask opening | 6 of 6 | 6 of 6 | PASS | bare laminate on both faces |
| 0.8mm | F_Cu.gtl empty (no copper) | 0 objects | 0 | PASS |  |
| 0.8mm | F_Mask.gts: each pad wholly in a mask opening | 6 of 6 | 6 of 6 | PASS | bare laminate on both faces |
| 0.8mm | silkscreen off the pads | 0 of 748 stroke points on a pad | 0 | PASS |  |
| 0.8mm | gerbv render (outline, NPTH, F.SilkS, F.Mask) | exit 0; no messages | exit 0, no messages | PASS |  |
| 0.8mm | gerbv loads B_Cu.gbl | exit 0; RS-274D guess (empty file) | exit 0 | PASS | gerbv's format guess for a Gerber with no apertures; the file is RS-274X with %FS/%MO |
| 0.8mm | gerbv loads B_Mask.gbs | exit 0; no messages | exit 0 | PASS |  |
| 0.8mm | gerbv loads Edge_Cuts.gm1 | exit 0; no messages | exit 0 | PASS |  |
| 0.8mm | gerbv loads F_Cu.gtl | exit 0; RS-274D guess (empty file) | exit 0 | PASS | gerbv's format guess for a Gerber with no apertures; the file is RS-274X with %FS/%MO |
| 0.8mm | gerbv loads F_Mask.gts | exit 0; no messages | exit 0 | PASS |  |
| 0.8mm | gerbv loads F_Silkscreen.gto | exit 0; no messages | exit 0 | PASS |  |
| 0.8mm | gerbv loads NPTH.drl | exit 0; no messages | exit 0 | PASS |  |

**1.6mm tabs** (pads numbered row by row from the top left; y is the Gerber y):

| pad | edge | tab centre x, y | perforated width | holes | joins |
|---|---|---|---|---|---|
| 1 | bottom | 132.500, -42.750 | 5.600 | 7 | pad 4 |
| 1 | top | 132.500, -27.250 | 5.600 | 7 | frame |
| 2 | bottom | 148.500, -42.750 | 5.600 | 7 | pad 5 |
| 2 | top | 148.500, -27.250 | 5.600 | 7 | frame |
| 3 | bottom | 164.500, -42.750 | 5.600 | 7 | pad 6 |
| 3 | top | 164.500, -27.250 | 5.600 | 7 | frame |
| 4 | bottom | 132.500, -60.750 | 5.600 | 7 | frame |
| 4 | top | 132.500, -45.250 | 5.600 | 7 | pad 1 |
| 5 | bottom | 148.500, -60.750 | 5.600 | 7 | frame |
| 5 | top | 148.500, -45.250 | 5.600 | 7 | pad 2 |
| 6 | bottom | 164.500, -60.750 | 5.600 | 7 | frame |
| 6 | top | 164.500, -45.250 | 5.600 | 7 | pad 3 |

**0.8mm tabs** (pads numbered row by row from the top left; y is the Gerber y):

| pad | edge | tab centre x, y | perforated width | holes | joins |
|---|---|---|---|---|---|
| 1 | bottom | 132.500, -42.750 | 5.600 | 7 | pad 4 |
| 1 | top | 132.500, -27.250 | 5.600 | 7 | frame |
| 2 | bottom | 148.500, -42.750 | 5.600 | 7 | pad 5 |
| 2 | top | 148.500, -27.250 | 5.600 | 7 | frame |
| 3 | bottom | 164.500, -42.750 | 5.600 | 7 | pad 6 |
| 3 | top | 164.500, -27.250 | 5.600 | 7 | frame |
| 4 | bottom | 132.500, -60.750 | 5.600 | 7 | frame |
| 4 | top | 132.500, -45.250 | 5.600 | 7 | pad 1 |
| 5 | bottom | 148.500, -60.750 | 5.600 | 7 | frame |
| 5 | top | 148.500, -45.250 | 5.600 | 7 | pad 2 |
| 6 | bottom | 164.500, -60.750 | 5.600 | 7 | frame |
| 6 | top | 164.500, -45.250 | 5.600 | 7 | pad 3 |

**60 PASS, 0 FAIL.**
