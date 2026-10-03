# 09 — Mechanical fit

Part of the [master plan](00-MASTER-PLAN.md). Read the master plan's ground
rules first. The heatsink selection comes from task 03. Without it, use a
representative extrusion and mark the result provisional.

## Goal

Check the assembled board in 3D for collisions and clearances against:

- the shared heatsink along the top edge
- the terminal hardware: M4 studs J2/J5/J7–J10 (Würth 74650074 REDCUBE), link
  straps and lugs
- mains wiring entry at J1
- the enclosure envelope, which isn't defined yet; this task produces its
  requirements

Evidence class: **exact structural** for model-vs-model collisions, and
**heuristic** where the models are provisional envelopes. The physical test
that confirms it is a trial assembly with measured hardware.

## Inputs

- Board with 3D models: `native-09/section.kicad_pcb`.
  - All 114 parts resolve a model (`native-09/verification/presentation/README.md`).
  - Sixteen are provisional dimensioned envelopes, listed in `models3d/`
    (read its READMEs for each model's limits).
  - The heatsink, enclosure, loose links and wiring hardware are **not
    modelled**.
- Terminal hardware envelopes: `terminal_envelopes.json`.
  - Exposed-metal envelopes for straps and lugs, in normal and bring-up
    configurations.
  - These are estimates. Measured hardware must replace them (DECISIONS.md,
    ASSEMBLY.md).
- Heatsink placement:
  - It runs along board x 12–165 mm at the top edge, per the D2 approval and
    `tools/placement_metrics.py` (`HEATSINK_X`).
  - The TO-247s are vertical, and their tabs face the heatsink.
  - The heatsink is PE-bonded, and the devices are insulated with pads.
- Insulation floors (D5-BASIS.md):
  - 8.0 mm between HOT and SELV/PE.
  - The heatsink is PE, so every HOT part must be ≥ 8.0 mm from the heatsink
    **metal**. The exception is the insulated device tabs, whose insulation is
    the pad plus the device package (check the pad's rating).

## Steps

1. **Export the board STEP:**
   ```sh
   kicad-cli pcb export step --subst-models --output /tmp/board.step native-09/section.kicad_pcb
   ```
   Check `--help` for the flags in 10.0.4. Confirm the STEP includes every
   model. KiCad's log lists missing models; the count must be 0.
2. **Model the missing parts** as simple solids in FreeCAD (install it; stop
   if that fails twice) or in a CadQuery script:
   - **Heatsink:** the task 03 extrusion profile, length 153 mm, positioned
     against the TO-247 tabs with the insulating pad thickness.
   - **Screws and clips:** per TO-247 and BR1. Their type is not chosen yet;
     use an M3 screw with an insulating bushing as the representative.
   - **Terminal hardware:** lugs and straps from `terminal_envelopes.json`, in
     both configurations.
   - **Mains cable entry:** J1 plus a wire bend radius for the chosen gauge
     (14 AWG for 15 A; state the assumption).
3. **Check collisions and clearances** between every pair of solids. Use
   FreeCAD's `Part` boolean `common` for collisions and a distance query for
   clearance. Report:
   - any interference (volume > 0)
   - clearance from every HOT metal part to the heatsink and PE hardware
     against the 8.0 mm floor, excepting the insulated tabs
   - clearance from tall parts to the heatsink fins
   - assembly access: can each heatsink screw be driven with the board
     populated? Is there a tool path?
4. **Height envelope:** report the tallest component and its height above the
   board. That's the minimum enclosure internal height, and a requirement for
   the enclosure (not a check against it).
5. **Heatsink mounting force:** check that the TO-247 leads aren't stressed.
   Confirm the lead-bend and standoff distance between board and tab centre vs
   the heatsink position, using the datasheet package drawing.

## Acceptance criteria

| Check | Pass |
| --- | --- |
| Missing 3D models in the STEP | 0 |
| Interferences | 0 |
| HOT metal to PE heatsink/hardware, not through the pad insulation | ≥ 8.0 mm (D5 floor) |
| Every heatsink screw | reachable |
| Output | A list of enclosure requirements: height, keep-outs and cable entry |

## Deliverables

In `validation-results/09-mechanical-fit/`:

- `README.md`
- `scripts/` (the FreeCAD or CadQuery script)
- `outputs/assembly.step`
- `outputs/clearances.csv`
- `outputs/views/*.png` (iso, top, heatsink side)
- `outputs/enclosure-requirements.md`

## Pitfalls

- The provisional envelopes are boxes. A pass against a box is optimistic for
  collisions near real curved parts, and a fail may be an artefact of the box.
  Label every result that involves a provisional model.
- Units: KiCad STEP is in mm; check that the FreeCAD import scale is 1.
