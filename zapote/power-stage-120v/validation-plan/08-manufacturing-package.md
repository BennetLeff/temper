# 08 — Manufacturing package and independent review

Part of the [master plan](00-MASTER-PLAN.md). Read the master plan's ground
rules first. Run this after any task that changes the board, and last overall.

## Goal

1. Fix the one known fabrication defect: silkscreen text below JLCPCB's
   minimum.
2. Generate the full JLCPCB package: Gerbers, drill files, BOM, position
   file, and a fabrication note.
3. Review the package independently of KiCad's own view.
4. Check parts sourcing.

This produces a **candidate** package. It does not release fabrication;
`DECISIONS.md` controls that.

Evidence class: **exact structural** for file content; **heuristic** for the
visual review.

## Known inputs

- Board: `native-09/section.kicad_pcb`, the presentation revision with visible
  designators. Record its SHA-256.
- JLCPCB rules and answers: `FAB-JLCPCB.md`. The stackup is JLC041622-7628,
  2 oz outer and inner, 1.6 mm, and CTI must be confirmed on the order.
- The JLCPCB silkscreen minimum is **1.0 mm text height and 0.15 mm stroke**
  (https://jlcpcb.com/capabilities/pcb-capabilities, read 2026-09-26). The
  board has all 114 designators at 0.8 mm / 0.12 mm, and 397 footprint outline
  strokes at 0.12 mm.
- BOM source: `frozen/default.csv` (never `default.net`).
- DRC baseline (master plan §3): 0 copper findings, 28 library warnings,
  3 silk overlaps (L1/J3), and 1 intended R5 open.
- JLCPCB rule check: `tools/jlc_dfm_check.py` (run under KiCad Python).

## Step 1: silkscreen

1. Edit `reference-labels.json`: set every reference's `size` to 1.0, and add
   or set the thickness to 0.15 if the schema supports it. Read
   `tools/apply_reference_labels.py` to see which fields it applies; extend the
   tool only if it can't set thickness, and add a test in
   `tests/test_reference_labels.py`.
2. Re-apply with the tool. It writes a new board; follow its usage docstring
   exactly. Then:
   - Confirm copper is unchanged: run `tools/copper_dump.py` and compare
     `items_sha256` with the pre-change dump. **They must be equal.**
   - Run the DRC. Copper findings must stay at 0. Record the new silk overlap
     count and fix any new overlaps by moving labels in `reference-labels.json`
     (larger text may collide).
3. **Footprint outline strokes (0.12 mm):** JLCPCB's page recommends ≥ 0.15 mm.
   Stock KiCad footprints use 0.12 mm and normally print, but faintly.
   Recommended: leave the footprints unchanged and state the deviation in the
   fab note. Changing stock footprints means local overrides per footprint
   (see `FOOTPRINTS.md` for the J4 override pattern), and that is owner
   approval territory.
4. **L1/J3 silk overlaps (3):** move or trim with the owner's agreement, or
   document them as accepted.

## Step 2: generate the files

Use kicad-cli. Write the outputs to `validation-results/08-manufacturing-package/fab/`.

```sh
B=native-09/section.kicad_pcb
O=validation-results/08-manufacturing-package/fab
mkdir -p $O/gerbers
kicad-cli pcb export gerbers --output $O/gerbers/ \
  --layers F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts \
  --use-drill-file-origin --subtract-soldermask $B
kicad-cli pcb export drill --output $O/gerbers/ --format excellon \
  --excellon-separate-th --generate-map --map-format gerberx2 $B
kicad-cli pcb export pos --output $O/positions.csv --format csv --units mm --side both $B
```

Check `kicad-cli pcb export gerbers --help` for the exact flag names in 10.0.4
before running, and adjust. Record the exact commands used.

Then:

- **Zip:** zip the gerbers folder for upload.
- **BOM:** convert `frozen/default.csv` to JLCPCB's BOM format (Comment,
  Designator, Footprint, LCSC Part #) with a script (`scripts/bom_jlc.py`).
  Most parts here are through-hole power parts without LCSC numbers; mark
  them "hand-assembled / consigned".
- **Position file:** convert to JLCPCB's CPL columns (Designator, Mid X,
  Mid Y, Layer, Rotation).
- **Fab note** (`fab/FAB-NOTE.md`), listing:
  - the stackup name
  - 2 oz on all layers
  - CTI ≥ 175 V required (group IIIa)
  - lead-free HASL or ENIG
  - the silkscreen deviation, if kept
  - "no impedance control"

## Step 3: independent review

1. Install gerbv (`brew install gerbv`). Load every Gerber and drill file.
   Check:
   - the layer count and order
   - the outline is closed, 240 × 160 mm
   - all drills are inside copper pads; there are 8 NPTH holes
   - mask openings on every pad
   - no silk on pads (JLCPCB needs 0.15 mm pad-to-silk)
   - the inner layers show the planes
2. Compare the drill counts in the Excellon files against the board: 147 vias
   and 116 plated pads, from `native-09/verification/jlc-dfm.json`.
3. Rerun `tools/jlc_dfm_check.py` on the final board. It must PASS.
4. **Human step (can't be automated here):** upload the zip to JLCPCB's
   online DFM viewer and read its report. Record the findings in the report.
   If you're a model without web upload, list this as a step for the operator.

## Step 4: parts sourcing

- For every BOM line, check stock and lifecycle at one or more distributors
  (Digi-Key, Mouser, LCSC) by exact MPN. Record the date and the stock level.
- Flag any part that is:
  - not stocked
  - NRND or obsolete
  - on a "ReviewOnly" footprint, meaning its footprint dimensions still need
    datasheet confirmation (see `FOOTPRINTS.md`, `RADIAL-FOOTPRINTS.md`)

## Acceptance criteria

- Copper `items_sha256` is unchanged by the silkscreen step.
- DRC copper findings are 0.
- `jlc_dfm_check.py` passes.
- All designators are ≥ 1.0 mm / 0.15 mm.
- The Gerber review checklist is complete, with no open finding.
- The BOM has 114 designators, matching `frozen/default.csv`.
- Sourcing is checked for every MPN.

## Deliverables

In `validation-results/08-manufacturing-package/`:

- `README.md`
- `fab/` with the gerbers, the zip, the BOM, the positions file and the fab
  note
- `outputs/gerber_review.md`, a checklist with screenshots
- `outputs/sourcing.csv`

Commit the updated `reference-labels.json` and the board separately from the
fab outputs, with a message stating that copper is unchanged.
