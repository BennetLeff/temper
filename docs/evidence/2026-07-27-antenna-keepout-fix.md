# `check_antenna_keepout` fix: corner/centre bug + module-centred keepout

Scope: `packages/temper-placer/tests/requirements/validators/pick_and_place.py:363`
(`check_antenna_keepout`), and its tests in
`packages/temper-placer/tests/requirements/dfm/test_placement_rules.py`.

## Falsifier

Stated before research: **my reading fails if Espressif specifies the antenna
keepout relative to the board edge rather than the module body.**

Result: partially fired, in a way that sharpens rather than overturns the
conclusion. Espressif's own clearance figure ("Keepout Zone for ESP32-S3
Module's Antenna") specifies the "Min 15 mm" dimension as a **base-board
cutout** measured from the module, not purely a module-body-relative offset
— and separately states the 15 mm figure again as an **end-product housing**
clearance ("in all directions") once the board is inside an enclosure. So
there are two different 15 mm clearances in Espressif's own guidance (PCB
substrate cutout, and enclosure air-gap), not one. Despite that, the antenna's
*own* footprint — the thing a copper-pour check can actually reason about —
is still anchored to the module body (one end of it, per the land-pattern
drawing), which is what this fix needed. The falsifier didn't invalidate the
approach, but it does mean the "15 mm in all directions" text is doing double
duty and shouldn't be over-read as a symmetric PCB-level keepout footprint.

## Defect 1 — coordinate convention mismatch (confirmed, fixed)

`_geometry.py:24-30`'s `_rects_overlap` is corner-origin (`x1, y1, w1, h1`).
`keepout_zone` was already built correctly as a centre-to-corner conversion
(`esp32_x - KEEPOUT/2, ...`). `pour_rect` was built as
`(pos[0], pos[1], size[0], size[1])` — treating the pour's centre as a
corner, offsetting every pour by half its size.

Fix (`pick_and_place.py`, in `check_antenna_keepout`):

```python
pour_rect = (pos[0] - size[0] / 2, pos[1] - size[1] / 2, size[0], size[1])
```

**Does this bug appear elsewhere?** Searched every rect-construction site
across `packages/temper-placer/tests/requirements/validators/*.py`:

- `_rects_overlap` is used **only** at this one call site in the whole
  validators package (confirmed via grep for the helper and for a
  hand-rolled `x1 + w1 <` style reimplementation — none found elsewhere).
- `_point_in_rect` is used in `layout_review.py` (heatsink zones, isolation
  zones) and `switching_nodes.py` (ground-plane zones, power-plane zones),
  but in every case the caller passes the zone rectangles in directly as
  pre-built `(x, y, w, h)` tuples — these functions never construct a rect
  internally from a component's `position` + `size` dict the way
  `check_antenna_keepout` did. No corner/centre confusion possible there
  because there's no internal construction step to get wrong.
- Grepped the whole validators directory for the pattern that caused this bug
  (`size[0]`/`size[1]` combined with a `position`/`pos` unpack): the only
  hits were the two lines already fixed here.

**Verdict: this defect is isolated to this one call site — it does not
recur elsewhere in the validators package.**

## Defect 2 — keepout centred on the module (confirmed validator bug, plus an unrealistic test fixture)

### What Espressif actually specifies

Sources (fetched directly, URLs below):

1. **ESP32-S3-WROOM-1 & WROOM-1U Datasheet v1.8**, Espressif Systems.
   https://documentation.espressif.com/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf
   - Section 10.1 "Module Dimensions" (Figure 10-1): module is **18.0 mm
     (width) x 25.5 mm (length) x 3.1 mm (height)**.
   - Section 11.1 "PCB Land Pattern" (Figure 11-1): the "Antenna Area" is
     drawn as a band across the **full 18 mm width**, **6 mm deep**, at the
     module's top edge — i.e. at **one end** of the module, not centred on
     it. This directly contradicts the validator's prior assumption.
   - `ESP32_MODULE_SIZE_MM` in the existing code is `(16.0, 37.0)` — this
     does **not** match the datasheet. Flagged as a separate, pre-existing
     bug (see UNVERIFIED/follow-up below); not fixed here because
     `check_antenna_keepout` never consumed this constant, so it's outside
     this function's blast radius, and a companion test
     (`test_esp32_module_size`) pins the wrong value tautologically.

2. **ESP32-S3 Hardware Design Guidelines**, "General Principles of PCB
   Layout for Modules."
   https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/pcb-layout-design.html
   - Verbatim (fetched raw HTML, tags stripped, not model-paraphrased):
     *"It is suggested to place the module's on-board PCB antenna outside
     the base board, and the feed point of the antenna close to the edge of
     the base board. ... If the antenna cannot extend beyond the board edge,
     the feed point should still be placed as close to the board edge as
     possible. Then cut off the base board on both sides of the antenna and
     below it ... Figure 'Keepout Zone for ESP32-S3 Module's Antenna' shows
     the suggested clearance area. ... Ensure that the PCB antenna on the
     base board also has a sufficiently large clearance area inside the
     housing. A clearance of at least 15 mm is recommended in all
     directions."*
   - The referenced figure (`esp32s3-module-clearance.png`, fetched
     directly) shows the base-board cutout: a **"Min 15"** mm dimension
     measured sideways from the antenna/module, plus small (**"Max 2"**,
     **"Max 1"**) tolerances on the opposite corner, over a clearance-area
     height matching the **6 mm** antenna band. Antenna feed point is drawn
     at one end of the module, board material cut away around it.

### Is 15 mm the right number, and where does it come from?

**Yes — confirmed correct**, and now cited. `ESP32_ANTENNA_KEEPOUT_MM =
15.0` matches both the "Min15" board-cutout dimension in the clearance
figure and the "at least 15 mm ... in all directions" housing-clearance
text. This constant was already right; it just wasn't sourced. It's now
sourced in a comment.

### Where the antenna sits relative to module origin/dimensions

Antenna is **not at the module centre**. It occupies a band at one end,
depth 6 mm, spanning the full 18 mm width (land pattern Figure 11-1).
Treating `esp32_position` as the module's centre (established by Defect 1's
own convention — `keepout_zone` already subtracts half the keepout size from
`esp32_position`), the antenna band's centre sits offset from the module
centre by:

```
ESP32_MODULE_LENGTH_MM / 2 - ESP32_ANTENNA_BAND_DEPTH_MM / 2
= 25.5 / 2 - 6 / 2 = 9.75 mm
```

### Rotation

**UNVERIFIED / not implemented.** Fixtures carry a `rotation` field on
component dicts (e.g. `esp32_placement`), but `check_antenna_keepout`'s
signature (`esp32_position, copper_pours, board_dimensions`) never received
it, and no caller (including `check_pick_and_place_compliance`, which reads
`component.get("position")` but drops `rotation` on the floor at
`pick_and_place.py:451`) threads it through. No fixture in the test suite
exercises a non-zero rotation for the antenna-keepout tests. Implementing a
real rotation transform would require guessing which local axis/direction
the antenna faces at `rotation == 0` — a convention this codebase does not
define anywhere and Espressif's docs obviously can't specify (it's an
artifact of this placer's coordinate system, not the module). Rather than
fabricate that convention, the fix offsets along +Y unconditionally and
documents this explicitly as a known gap in the code comment. A real fix
needs `rotation` added to the function signature, wired from
`check_pick_and_place_compliance`, and the offset vector `(0,
ESP32_ANTENNA_OFFSET_MM)` rotated by it.

### Validator vs. test — which was wrong

**Both**, in different ways:

- **The validator was wrong** to centre the keepout on the module. Fixed:
  the keepout is now centred at `esp32_position + (0,
  ESP32_ANTENNA_OFFSET_MM)`, anchored toward the antenna end rather than the
  module centroid.
- **The original test fixture was also wrong**, independent of where
  exactly within the module the antenna sits. Proof: the original
  `esp32_placement` fixture / `test_adequate_antenna_keepout_passes` pour was
  `size=(40, 30)` centred at the **same point** as the module (`(50, 50)`).
  A pour of half-height 15 mm centred on a module whose real half-length is
  `25.5 / 2 = 12.75 mm` necessarily **overhangs the module's own physical
  edge by `15 - 12.75 = 2.25 mm` on both ends** — including the antenna
  end. Since the antenna sits at (or inward from) that edge, not beyond it,
  the pour cannot avoid covering at least part of the antenna region no
  matter how precisely the keepout box is placed within/adjacent to the
  module footprint. A single gapless rectangular pour, centred on and larger
  than the module in both dimensions, can never satisfy "ground pour under
  module **except antenna area**" — that requires an actual gap in the pour,
  which the fixture never modelled. This was verified computationally, not
  just argued (see `/private/tmp/.../scratchpad` calc: `overlap=True` for
  both the buggy *and* the corner/centre-corrected version of the original
  pour against the module-centred keepout, and still overlaps against the
  corrected, antenna-end-anchored keepout).

**Fix applied to the test data:** `esp32_placement` and
`test_adequate_antenna_keepout_passes` now use a pour
`position=(50, 43), size=(16, 14)` — sized/positioned to cover only the
module's non-antenna (southern) end, clear of the antenna-end keepout box
(`y ∈ [52.25, 67.25]` after the fix) with margin. This is a realistic
"ground pour under most of the module, clear of the antenna" scenario,
rather than a solid rectangle that blankets the whole module including the
antenna.

## Collateral bug found (not one of the two stacked defects, fixed because it blocked verification)

Four test functions in `test_placement_rules.py` had fixture-parameter names
that didn't match any fixture (`_esp32_placement`, `_esp32_antenna_violation`
x2, and a stray `_self` parameter on a plain module-level function) — almost
certainly the residue of an automated "prefix unused args with underscore"
lint pass that didn't understand pytest's fixture-injection-by-parameter-name
magic. This made 4 of the antenna/ESP32 tests **error** (fixture not found)
rather than run at all, and in every case the fixture was unused inside the
test body anyway (values were hardcoded inline). Fixed by removing the dead
fixture parameters / the stray `_self` parameter. This is unrelated to
Defects 1/2 but had to be fixed to actually exercise
`test_adequate_antenna_keepout_passes` and its siblings.

## New test pinning the corner/centre convention

Added `test_pour_position_is_a_centre_not_a_corner`: constructs a pour whose
`position`, read as a centre, sits clear of the keepout zone (passes), but
whose `position`, read as a corner (the old buggy behavior), pokes into the
keepout zone (would fail). This regresses loudly if Defect 1 is reintroduced.

## Verification

`python -m pytest packages/temper-placer/tests/requirements/dfm/ -q`

- **Before** (this worktree, after rebasing onto the assigned base commit):
  `4 failed, 111 passed, 1 skipped, 7 errors` (0.35s). All 4 failures and all
  7 errors are in `test_documentation.py` / `test_test_points.py` (BOM/DNP
  validators and test-point validators, unrelated packages) plus the 4
  antenna-keepout fixture-name errors described above.

  Note: this doesn't match the task's stated baseline of "1 failed, 59
  passed, 1 skipped in test_placement_rules.py" — that baseline was not
  reproducible in this worktree; reported honestly rather than
  reconciled/fabricated.

- **After**: `4 failed, 116 passed, 1 skipped, 3 errors` (0.21s). The
  remaining 4 failures and 3 errors are unchanged, pre-existing, and entirely
  in `test_documentation.py` / `test_test_points.py` — untouched by this fix.
  Within `test_placement_rules.py` alone: before `56 passed, 1 skipped, 4
  errors`; after `61 passed, 1 skipped, 0 errors` (net +5: 4 errors resolved
  + 1 new convention-pinning test).

- `test_copper_in_antenna_keepout_fails` (the negative test) still fails the
  placement after the fix — verified directly: `result.passed == False`,
  and the actual `DFM001-ANT-002` ("Copper pour found in ESP32 antenna
  keepout zone") violation fires, not just the unrelated edge-distance
  violation. Confirms the fix isn't a vacuous gate.

- `ruff check` on both changed files: all checks passed.

## UNVERIFIED / follow-up items (not fixed here, out of this function's scope)

1. **`ESP32_MODULE_SIZE_MM = (16.0, 37.0)`** does not match the datasheet's
   real `18.0 x 25.5 mm`. Not fixed here — `check_antenna_keepout` doesn't
   consume it, and a companion test (`test_esp32_module_size`) tautologically
   pins the wrong value. Worth a dedicated follow-up (would need to update
   that test too).
2. **Rotation is not applied to the antenna keepout.** See "Rotation" above.
   `check_pick_and_place_compliance` reads `component.get("rotation")` for
   nothing — it's discarded before calling `check_antenna_keepout`.
3. **`DFM001-ANT-001` (`edge_dist_x`/`edge_dist_y` < 15 mm ⇒ violation)**
   flags the ESP32 as "too close to the board edge" — but Espressif's actual
   guidance is the opposite: place the antenna *as close to the board edge
   as possible* (ideally overhanging it). This check appears to test
   distance-from-`esp32_position`-to-nearest-board-edge, which is a
   different (and possibly backwards) requirement from the antenna's own
   15 mm clearance zone. Not investigated or changed — out of scope for this
   task (Defects 1/2 are specifically about the copper-pour/keepout overlap
   check, `DFM001-ANT-002`), and no test in the current suite is sensitive to
   it either way for the fixtures involved here. Flagged for a separate
   audit given this project's track record of backwards-requirement bugs
   (e.g. MOV-upstream-of-fuse).
4. **Keepout box shape.** The fix keeps the keepout as a 15x15 mm square
   (matching the existing, tested `ESP32_ANTENNA_KEEPOUT_MM` value) merely
   *repositioned* toward the antenna end. Espressif's real clearance area is
   asymmetric (6 mm deep x wider-than-15mm-on-one-side, per the clearance
   figure), not a symmetric square. Documented as a known simplification, not
   silently wrong — the number (15) and the anchor point (antenna end, not
   module centre) are now both sourced; the exact shape is not.
