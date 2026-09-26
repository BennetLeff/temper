# Part 2: create the missing footprints

**Goal:** every footprint named in `zapote/power-stage-120v/elec/src/parts.ato`
must exist as a KiCad 10 `.kicad_mod` file that the native bridge can vendor.
Each one must be checked against the manufacturer drawing, with that check
recorded.

This part is independent of Part 1. Do it in its own worktree.

## Where footprints must go (read this carefully)

The bridge (`block_source.vendor_candidate_libs`) resolves footprints like this:

1. A name `temper:X` or `lib:X`: if the unit passes `local_libraries`, which
   Part 1's `build_native.py` does, the file **must** be at
   `zapote/power-stage-120v/libraries/<lib>.pretty/<X>.kicad_mod`. It does
   **not** fall back to `pcb/libs` in that case.
2. Any other library name (for example `Package_TO_SOT_THT:TO-247-3_Vertical`)
   resolves from KiCad's stock library:
   `/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints/<lib>.pretty/<X>.kicad_mod`.

So the unit library needs these **eight** files:

| # | File (under `zapote/power-stage-120v/libraries/`) | Part(s) | Action |
| ---: | --- | --- | --- |
| F1 | `temper.pretty/CDE_942C_D19.0_L34.0_Axial_ReviewOnly.kicad_mod` | C23 942C12P1K-F | Author (below) |
| F2 | `temper.pretty/CDE_942C_D26.5_L34.0_Axial_ReviewOnly.kicad_mod` | C21, C22 942C12P22K-F | Author |
| F3 | `temper.pretty/CDE_942C_D32.0_L54.0_Axial_ReviewOnly.kicad_mod` | C5, C6 942C6W2P5K-F | Author |
| F4 | `temper.pretty/TMOV20RP_ReviewOnly.kicad_mod` | RV1 TMOV20RP175E | Author |
| F5 | `temper.pretty/B82726S2_ReviewOnly.kicad_mod` | L1 B82726S2203A020 | Author |
| F6 | `temper.pretty/Diode_Bridge_GBJ2510.kicad_mod` | BR1 GBJ2510-F | Copy from archive, verify |
| F7 | `temper.pretty/CST3015.kicad_mod` | T1 | Copy verbatim from `pcb/libs/temper.pretty/CST3015.kicad_mod` |
| F8 | `lib.pretty/SOIC16W_Isolated.kicad_mod` | U1, U2 | Copy verbatim from `pcb/libs/lib.pretty/SOIC16W_Isolated.kicad_mod` |

**Keep the footprint names exactly as written in `parts.ato`.** Renaming (for
example, dropping `_ReviewOnly` once a footprint is verified) is allowed, but only
as a source change: edit `parts.ato`, rebuild, re-audit and re-freeze. Do that
in a separate commit at the end, and only for footprints whose check record
says VERIFIED.

## General rules for authored footprints

- **Base each file on the closest KiCad stock footprint** and edit the numbers;
  don't write S-expressions from scratch. Suggested bases:
  - axial capacitors: any `Capacitor_THT.pretty/CP_Axial_L*` file (then remove the polarity marking)
  - the TMOV: `Varistor.pretty/RV_Disc_D21.5mm_W4.9mm_P10mm.kicad_mod`
  - the choke: `Inductor_THT.pretty/Choke_Schaffner_RN152-04-43.0x41.8mm.kicad_mod`
- **Pad numbers must equal the pin numbers in `parts.ato`.** The bridge fails if a
  source pin has no pad.
- **Layers:** pads on `*.Cu *.Mask`; body outline on `F.Fab`; silkscreen outline on
  `F.SilkS`, kept off pads; courtyard on `F.CrtYd`, 0.5 mm outside body and pads.
- **Plated through-hole drill** = maximum lead diameter + 0.3 to 0.5 mm. **Pad diameter**
  ≥ drill + 1.2 mm; these are high-current parts, so be generous.
- **Keep the pin-1 marker** as a rectangular pad 1 where the part has a pin 1.
- **Check each file** with
  `kicad-cli fp upgrade --output /tmp/fpcheck <dir>.pretty`: it must parse without error.
  Always pass `--output`; without it the command rewrites your files in place. Then
  export an SVG and look at it:
  `kicad-cli fp export svg --output /tmp/fpsvg <dir>.pretty`.
  Record the pad coordinates you used.

### F1–F3: CDE 942C axial film capacitors

Source: CDE Type 942C catalog, https://www.cde.com/resources/catalogs/942C.pdf
(rating tables; columns D, L and d are body diameter, body length and lead diameter).

| Footprint | D (mm) | L (mm) | d (mm) | Pitch (see rule) | Drill | Pad |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| F1 D19.0 L34.0 | 19.0 | 34.0 | 1.0 | 42.5 | 1.4 | 3.0 |
| F2 D26.5 L34.0 | 26.5 | 34.0 | 1.2 | 42.5 | 1.6 | 3.2 |
| F3 D32.0 L54.0 | 32.0 | 54.0 | 1.2 | 62.5 | 1.6 | 3.2 |

- **Pitch rule:** body length plus at least 4 mm straight lead on each side before
  the bend, rounded up to a 2.5 mm grid (34 + 8 → 42.5; 54 + 8 → 62.5).
  **Verify in the catalog's mounting or lead-bending notes** whether CDE
  specifies a minimum bend distance. If it's larger than 4 mm, recompute.
- **Mounting:** horizontal, body lying on the board. Pads at (0, 0) and (pitch, 0).
- **Outlines:** F.Fab body rectangle centred between pads, L × D.
  Courtyard = body + 0.5 mm, enclosing the pads.
- **Notes to add:**
  - "Heavy part: secure with adhesive or a strap; see Part 4"
  - "942C are non-polar: no polarity mark"

### F4: Littelfuse TMOV20RP175E

Source: a Littelfuse TMOV/iTMOV datasheet, "General Dimensions, Bulk Pack
Non-Crimped Devices" (the older mirror
https://datasheet.octopart.com/TMOV20R230E-Littelfuse-datasheet-8477.pdf has the
table). Values for the **20 mm, 2-lead (E), 115–175 Vrms** row:

| Symbol | Meaning | Min | Max |
| --- | --- | ---: | ---: |
| Dia D | disc diameter | 19.0 | 23.0 |
| A | seated height | 23.0 | 28.0 |
| e | lead spacing | 6.5 | 8.5 (7.5 nominal) |
| e1 | lead offset (leads **not** in line) | 1.5 | 4.0 |
| E | body thickness | — | 9.0 |
| b | lead diameter | 0.76 | 0.86 |

- **KiCad's stock `RV_Disc_D21.5mm_*_P10mm` does not fit:** its pitch is 10 mm, the
  TMOV's is 7.5 mm.
- **Step 1 (required):** find the **current** datasheet that lists the **"RP"**
  part number (`TMOV20RP175E`). Distributor pages (Mouser, DigiKey) link it.
  The mirror above predates the "P". If the current drawing differs, use it and
  record both.
- **Step 2, author:**
  - pads 1 and 2 at (0, 0) and (7.5, 0)
  - drill 1.2 mm, pad 2.4 mm (lead 0.86 max, leaving room for the e1 offset to be formed)
  - F.Fab outline: a circle Ø23 mm plus a 9 mm-thick side-view note; courtyard Ø24 mm
  - note in the file description: "leads not in-line (e1 1.5–4.0 mm); bend lead 2 to line"
- **Stop and ask** if the current datasheet shows a 3-lead part or a pitch other than 7.5 mm.

### F5: TDK B82726S2203A020 common-mode choke

Source: TDK "B82726S22*3A020" datasheet, page 3, "Dimensional drawing and pin
configuration": https://www.tdk-electronics.tdk.com/inf/30/db/ind_2008/b82726s22x3.pdf

From the drawing (already used to fix the source pin map on 2026-09-25):
- **Pins:** Ø2 ± 0.1 mm, four pins.
- **Pin positions:** pins 1 and 2 on one side, 10 ± 0.5 mm apart. Pins 4 and 3 on the
  opposite side, 4 under 1 and 3 under 2. Rows 25 ± 0.5 mm apart.
- **Windings:** **1–4** and **2–3**, no polarity.
- **Body:** 45 mm maximum along the pin-row direction, 25 mm maximum across, about 41 mm tall.
  Seating standoff 3.5 ± 0.5 mm.
- **Author:**
  - pad 1 at (0, 0), pad 2 at (10, 0), pad 4 at (0, 25), pad 3 at (10, 25)
  - drill 2.5 mm, pad 4.0 mm; pad 1 rectangular
  - F.Fab body rectangle x −17.5 … 27.5, y −0.5 … 25.5 (45 × 26 around the pin pattern centre (5, 12.5))
  - courtyard +0.5 mm
- **Datasheet note:** clearance ≥ 2.5 mm and creepage ≥ 3 mm internal. Don't route
  other nets between the pins.
- **Cross-check:** `zapote/power-stage-120v/audit.rs` asserts L1 pins 1→`l_f`,
  4→`l_filt`, 2→`ac_n_in`, 3→`n_filt`. Your pad numbers must match these physical
  pins.

### F6: GBJ2510 bridge (copy, then verify)

```sh
git show "archive/rev38-power-entry-2026-09-25:zapote/power-entry/passive-reva/libraries/Diode_THT.pretty/Diode_Bridge_GBJ2510.kicad_mod" \
  > zapote/power-stage-120v/libraries/temper.pretty/Diode_Bridge_GBJ2510.kicad_mod
```

Expected geometry in that file:
- pads 1 (rect) at x = 0, 2 at 10, 3 at 17.5, 4 at 25 mm
- all on y = 0; drill 1.6 mm, pad 4.0 mm
- description cites Diodes Inc. DS21221 Rev.11-2

**Verify** against the Diodes Inc. GBJ2510-F datasheet (DS21221):
- pin order `+ ~ ~ −` and 10 / 7.5 / 7.5 mm spacing
- the source's `BridgeGbj2510` map: PLUS = 1, AC1 = 2, AC2 = 3, MINUS = 4

If either differs, **stop and ask**. That would be a source defect.

## Record: `zapote/power-stage-120v/FOOTPRINTS.md`

One row per F1–F8:
- footprint file and SHA-256
- datasheet URL, revision/date, page or figure
- the dimensions you used
- pad coordinates
- verdict: `VERIFIED` (drawing checked) or `PROVISIONAL` (why)

F7 and F8 are verbatim copies: record their source path and confirm the hashes
match `pcb/libs`.

## Acceptance checklist

- [ ] Eight files exist at the paths above; `kicad-cli fp upgrade --output /tmp/fpcheck <lib>.pretty` parses each library without error
- [ ] For each authored footprint, the SVG export was inspected, and pad numbers match the `parts.ato` pins (F5: 1, 2, 3, 4; F4: 1, 2; F1–F3: 1, 2)
- [ ] F7 and F8 are byte-identical to `pcb/libs`
- [ ] `FOOTPRINTS.md` complete; every row VERIFIED or PROVISIONAL with a reason
- [ ] After Part 1 has merged: `python3 zapote/power-stage-120v/tools/build_native.py /tmp/ps-native-probe` gets **past** footprint vendoring. It may still fail later at poses or outline; that's Part 3's job. Delete `/tmp/ps-native-probe` afterwards.
- [ ] PR titled `feat(power): power-stage-120v footprint library`

## Stop and ask if

- a current datasheet contradicts the numbers above
- a footprint needs a pin the source doesn't have, or the reverse
- the GBJ2510 pin order differs from PLUS = 1, AC1 = 2, AC2 = 3, MINUS = 4
