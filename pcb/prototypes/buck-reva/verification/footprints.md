# Buck Rev A — footprint and land-pattern verification

Revision A, frozen 2026-09-10. All footprints are vendored in the local
library `buck-reva.pretty/` and resolved by `fp-lib-table`; the board does not
rely on global libraries. Pad geometry, solder mask, paste, silkscreen,
courtyard and fabrication layers were inspected independently of visual
resemblance.

## Core references

| Ref | Exact MPN | Local footprint | Land-pattern evidence | Result |
|---|---|---|---|---|
| U3 | LMR51430XDDCR | `SOT-23-6` | Pads byte-identical to KiCad `Package_TO_SOT_SMD:SOT-23-6` (IPC/JEDEC MO-178). Pin map 1 GND, 2 SW, 3 VIN, 4 FB, 5 EN, 6 BOOT checked against the TI LMR51430 datasheet (SLUSF4A) and the KiCad `Regulator_Switching:LMR51430` symbol. | PASS |
| L2 | SRP1265A-5R6M | `L_Bourns_SRP1265A` | Reviewed v5 land: pads 3.1 × 5.0 mm at ±5.55 mm, inner land gap 8.0 mm, outer span 14.2 mm, pad height 5.0 mm; body 13.5 × 12.5 mm, maximum envelope 14.0 × 12.8 mm, courtyard 15.0 × 13.8 mm. Verified against the retained Bourns SRP1265A drawing by the prior audit (`harness-lab/audits/buck-20260910-followup/layout.md`; PDF SHA-256 `30b470999b737a6350ce5b09a917a5f12090c2e0895a78ddc15285e3d44ec649`). No generic smaller inductor land is used. | PASS |
| C9 | CL32B106KBJZW6E | `C_1210_3225Metric` | Pads byte-identical to KiCad `Capacitor_SMD:C_1210_3225Metric` (IPC-7351 nominal 1210 / 3225 metric). Samsung product page and assembly-guidance link retained in `current-buck-bom.md`. | PASS (see limit 1) |
| C11, C12 | GRM32ER71E226KE15L | `C_1210_3225Metric` | As C9. | PASS (see limit 1) |
| C10, C13 | C0603C104K5RACTU | `C_0603_1608Metric` | Pads byte-identical to KiCad `Capacitor_SMD:C_0603_1608Metric` (IPC-7351 nominal 0603). | PASS |
| R16, R17 | RC0603FR-07100KL / RC0603FR-0722K1L | `R_0603_1608Metric` | Pads byte-identical to KiCad `Resistor_SMD:R_0603_1608Metric` (IPC-7351 nominal 0603). | PASS |

## Prototype I/O and mechanics

| Ref | Part | Local footprint | Dimensions checked | Result |
|---|---|---|---|---|
| J1, J2 | Würth Elektronik 691253500002 (WR-TBL 2535) | `TerminalBlock_5.08mm_1x02` | Created from the Würth drawing (rev 26-AUG-14, sheet 1/2): pitch 5.08 mm, recommended PCB hole Ø1.5 mm, pin 1 centre 2.54 mm from the body end, body 10.16 × 5.3 mm, height 11.2 mm, top wire entry, M3 rising-cage screw. Pad diameter 2.8 mm selected (annular ring 0.65 mm on the 1.5 mm hole); body/courtyard 10.16 × 5.3 (+0.5/+0.25) mm. Pin 1 is rectangular and marked on silk. | PASS |
| TP1–TP4 | bare copper probe pad (no purchased part) | `TestPoint_Probe_2mm` | 1.8 mm roundrect pad, F.Cu + F.Mask only (no paste), 0.9 mm courtyard annulus. | PASS |
| H1–H4 | M3 mounting hole (no purchased part) | `MountingHole_3.2mm_M3` | KiCad official `MountingHole:MountingHole_3.2mm_M3`; 3.2 mm non-plated hole, no annular ring, isolated. | PASS |

## Mechanical / assembly review

- Terminal bodies sit inboard of the board edge with screwdriver access from
  the top and wires from above; no body overhangs Edge.Cuts.
- Terminal courtyard, probe pad, mounting hole and core courtyards do not
  overlap (native DRC `courtyards_overlap` is an error in this project and
  reports 0).
- Connector orientation and pin 1 are marked on silk (`1` and the value text);
  bare pads are labelled by reference and value.
- `L2` and the two terminal blocks have **no STEP 3D model**, so the 3D render
  shows their body footprint only. Their board-level dimensions are verified
  above; the missing cosmetic model is explicitly not a blocker per the board
  plan.

## Limits (recorded, not waived)

1. The 1210 capacitors use the KiCad IPC-7351 nominal land, which is the
   industry-standard footprint for the body size. A vendor-specific paste
   reduction (e.g. Samsung soft-termination guidance) was **not** re-derived
   for Rev A; the vendor guidance links are retained in the BOM ledger. If the
   first article shows tombstoning or insufficient heel fillets, the paste
   apertures are the first thing to revisit.
2. The Würth pad diameter is a designer choice (the drawing specifies the hole
   only). 2.8 mm is standard and gives a 0.65 mm annular ring on a 1.5 mm hole,
   comfortably within the fabricator's minimum.
3. Via-in-pad: the core routing carries nine vias at SMD pad centres
   (0.8 mm / 0.4 mm), mask-tented but not filled/capped — including the U3 GND
   pad and the R16/R17 feedback divider. This is an assembly consideration, not
   a pad-geometry defect; see the via-treatment note in `board-freeze.md`.
