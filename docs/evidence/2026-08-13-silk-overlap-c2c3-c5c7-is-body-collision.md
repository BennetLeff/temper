<!-- provenance: commit=a9a6b7dfcf9cc5e86184664ef26ae25a33e11f73 dirty=UNKNOWN -->
# `silk_overlap`'s two saturating pairs (C2xC3, C5xC7) are symptoms of real
# capacitor body collisions, not a cosmetic silkscreen defect

Follow-up to PR #1150 (`fix/drc-ceiling-track-silk-uncap`, based on
`fix/board-schematic-resync`), which corrected `silk_overlap`'s ceiling from
a saturated 199 to its true measured 13,407 and explicitly left "fixing the
underlying placement/footprint issue" out of scope. This document closes
that gap: it determines which is wrong (footprint or placement), and finds
the answer is placement, with a consequence more serious than the silkscreen
framing suggests.

**Headline: C2/C3 and C5/C7 do not merely have overlapping silkscreen. Their
component BODIES physically occupy the same space** -- confirmed three
independent ways (corrected coordinate math cross-validated against
kicad-cli's own ground truth, kicad-cli's `courtyards_overlap` DRC check
directly, and a rendered SVG crop showing the can outlines visually
interlocking). This is not a newly-introduced defect either: it is two of
the 8 `courtyards_overlap` violations `power_pcb_dataset/drc_ceiling.json`
already tracks at ceiling 8 (measured 8, zero headroom) -- nobody had
previously connected "these are the same two footprint pairs saturating
`silk_overlap`" to "these are body collisions already flagged by a different
DRC category." No PCB edit is made by this change. Per the task brief's own
instruction, a placement fix collides with concurrent reroute/via/stackup
work on this same file and needs sequencing, not a race -- so this document
stops at reporting and does not move C2, C3, C4, C5, or any of their
colliding neighbors.

## 0. Provenance

| | |
|---|---|
| Branch | `fix/silk-overlap-c2-c3`, based on `origin/fix/drc-ceiling-track-silk-uncap` (PR #1150's branch, itself based cleanly on `origin/fix/board-schematic-resync` / PR #1134 -- `gh pr view 1150` reports `mergeStateStatus: CLEAN` against that base) |
| Commit measured against | `3c36a81c61529c66f8ac86f445ed8bb155429a51` |
| `pcb/temper.kicad_pcb` sha256 | `b7d865b7946f55dcc0d907cccbbee12f730fd1878b30d417bd56004d1091c1d6` |
| `kicad-cli --version` | `10.0.5` |
| `scripts/measure_uncapped_drc.py` | no `temper_*` package imports (stdlib `subprocess`/`re`/`json` only) -- not subject to the pyo3/maturin extension-freshness hazards in `AGENTS.md`; freshness/import checks for those extensions were not needed for this task and were not run. |

`git status --porcelain` clean, `git grep -l "^<<<<<<< "` empty, before and
after every step below.

## 1. Reproduction: `saturating-pair`, both flagged footprint pairs

```
$ python3 scripts/measure_uncapped_drc.py saturating-pair C2 C3 --scratch-dir <scratch>
TRUE silk_overlap C2xC3: 12852

$ python3 scripts/measure_uncapped_drc.py saturating-pair C5 C7 --scratch-dir <scratch>
TRUE silk_overlap C5xC7: 360
```

Both match PR #1150's recorded numbers exactly (12,852 + 360 = 13,212 of the
13,407 board total, ~98.5%). `pcb/temper.kicad_pcb` was not modified to
produce these numbers -- `measure_uncapped_drc.py` only ever writes scratch
copies outside the repo.

## 2. Which is wrong: the footprint, or the placement?

### 2.1 The footprint content is stock upstream KiCad, not a local defect

`C2`, `C3`, `C4`, `C5` are all `Capacitor_THT:CP_Radial_D35.0mm_P10.00mm_SnapIn`
-- **4 instances of this footprint exist on the board** (confirmed by
scanning every `(footprint "Capacitor_THT:CP_Radial_D35...")` block and its
paired `Reference` property). This library is not vendored in the repo
(`pcb/fp-lib-table` points at the system KiCad install); `git grep` for a
project-local `.pretty` copy finds none. Each board instance carries its own
byte-for-byte copy of the footprint's graphics (KiCad bakes a footprint's
geometry into the board file at place time), so a per-instance edit in
`pcb/temper.kicad_pcb` would not touch the shared library and would not
affect any other project.

The silkscreen's headline feature -- 554 `fp_line` segments on `F.SilkS`,
`x` stepping 0.04mm from 5.0 to 22.6mm, drawing a shaded half-disc -- is
**identical**, count and coordinates, to the file shipped in KiCad's own
`Capacitor_THT.pretty`
(`.../org.kicad.KiCad.Library.Footprints/.../Capacitor_THT.pretty/CP_Radial_D35.0mm_P10.00mm_SnapIn.kicad_mod`,
`grep -c fp_line` = 556 there vs. 554+2 short polarity-mark lines here,
same start coordinates for the first several lines). This hatch is upstream
KiCad's own way of shading the can body for a polarized snap-in electrolytic
-- not a local import artifact, not something introduced by this repo. The
actual polarity mark is a separate small "+" (two short crossing lines,
`(-13.854,-9.875)-(-10.354,-9.875)` and `(-12.104,-11.625)-(-12.104,-8.125)`)
that is untouched by anything below. **Conclusion: the footprint is not
defective.** A footprint-library change is not the correct fix here, so the
"note the blast radius across every instance" contingency does not apply --
but the placement blast radius below does.

### 2.2 The placement is wrong: bodies collide, not just silkscreen

The task brief's own suspicion -- "if two 35mm-diameter parts sit 30.5mm
apart centre-to-centre, their bodies overlap" -- is confirmed, with a
wrinkle: 30.52mm is the distance between the two footprints' **anchor
points** (`C2 (at 93.48 64.84 0)`, `C3 (at 87.36 34.94 270)`), not their body
centers. This footprint's true body center is offset 5mm from the anchor in
local coordinates (`(fp_circle (center 5 0) (end 22.5 0) (layer "F.Fab"))`,
i.e. true body radius 17.5mm, diameter 35.0mm matching the part number
exactly). Because `C2` and `C3` carry *different* rotations (0 deg vs.
270 deg), that 5mm offset points in different world directions for each --
which moves their true body centers to only **27.27mm apart**, not 30.52mm.

Sum of body radii is 35.00mm. Center distance 27.27mm. **The true bodies
(`F.Fab`) interpenetrate by 7.73mm at the closest point.** `F.CrtYd`
(KiCad's keep-out courtyard, drawn 0.25mm larger than the true body on this
footprint) overlaps by 8.23mm for the same reason.

`C5` (same footprint, `at 139.62 229.07 180`, true-body world center
`(134.62, 229.07)`, radius 17.5mm) against `C7`
(`Capacitor_THT:C_Rect_L18.0mm_W11.0mm...`, a *different*, non-hatched
rectangular film-cap footprint, `at 137.72 244.66 180`, true `F.Fab` body a
world-space rect `x[121.22,139.22] y[239.16,250.16]`): the closest point on
C7's true body to C5's center is 10.09mm away, inside C5's 17.5mm body
radius by **7.41mm**.

**Sign-convention note, so this is checked, not trusted:** computing this
requires rotating each footprint's local geometry by its stored `(at x y
angle)` into world coordinates. The first pass used the textbook
counter-clockwise rotation matrix and got the wrong answer (a comfortable
1.13mm *gap* between C2/C3 courtyards) -- which would have wrongly concluded
"cosmetic, safe to trim silkscreen." That result was checked against an
independent ground truth (next section) before being trusted, was found
wrong, and the rotation was corrected to clockwise
(`x' = x*cosθ + y*sinθ, y' = -x*sinθ + y*cosθ`), which is the convention
that reproduces kicad-cli's own verdict exactly for every one of the 8 pairs
below. This is exactly the class of silent-wrong-answer error the task
brief warns "produced wrong answers repeatedly today" -- caught here only
because the geometric conclusion was cross-checked against the DRC engine's
own output rather than shipped on hand-rolled trig alone.

### 2.3 Independent verification 1: kicad-cli's own `courtyards_overlap` check

`pcb/temper.kicad_pro` already runs `"courtyards_overlap": "error"`. A live
`kicad-cli pcb drc --format json --severity-error` against the unmodified
board (never altered by this investigation) reports:

```
courtyards_overlap 8
```

-- and `power_pcb_dataset/drc_ceiling.json`'s `violations_by_type.courtyards_overlap`
ceiling is **already 8**, i.e. this board has zero headroom in that category
today, live measurement matches ceiling exactly. The 8 pairs, read directly
from the DRC JSON:

```
R4  x C4
K3  x C3
L1  x C5
C22 x C4
C2  x C3   <- the silk_overlap-dominant pair (12,852 of 13,407)
C2  x PS1
C4  x R46
C5  x C7   <- the other silk_overlap pair (360 of 13,407)
```

Both `silk_overlap`-saturating pairs are in this list, named by kicad-cli's
own courtyard engine, completely independent of `measure_uncapped_drc.py`'s
silkscreen-specific method. And the blast radius is wider than the two
`silk_overlap` pairs alone: **every one of the 4 on-board
`CP_Radial_D35.0mm` instances (C2, C3, C4, C5) sits in at least one courtyard
collision** -- C4 alone is in three (R4, C22, R46), none of which are
CP_Radial_D35.0mm and so don't carry the dense hatch, which is why they
don't also saturate `silk_overlap` the way C2xC3/C5xC7 do (matches PR
#1150's own note that re-adding C4 to a deleted board does not re-saturate
`silk_overlap`, while C2, C3, or C5 individually do). The silkscreen
category is only surfacing 2 of a pre-existing 8-way courtyard pile-up in
this corner of the board.

### 2.4 Independent verification 2: rendered visual

`kicad-cli pcb export svg --layers F.Fab,F.CrtYd,F.SilkS,Edge.Cuts
--page-size-mode 2 --mode-single` against the unmodified board, rasterized
and cropped to the C2/C3 and C5/C7 regions: both crops show the `F.Fab`
body fills (and `F.CrtYd` outlines) of each pair visibly interlocking --
not touching, not a near-miss, a real lens-shaped intersection consistent
with the 7.4-7.7mm depths computed above. (Scratch-only artifacts, not
committed -- reproducible with the command above against the same board
hash.)

## 3. Why this changes the fix

The task brief's own decision tree: *"If the parts physically collide -> a
placement fix is required; report it as a safety/assembly defect and
coordinate... If only silkscreen overlaps -> the usual fix is trimming."*
Section 2 establishes the first branch, not the second, for both pairs.

Trimming or removing the dense silkscreen hatch on C2/C3 (or C5/C7) would
make `silk_overlap`'s count -- and the specific C2xC3/C5xC7 numbers -- drop
dramatically, and would be a legitimate improvement if these parts merely
had overlapping *artwork*. They do not: the physical cans occupy the same
volume today. Deleting the silkscreen that happens to visualize that
collision would not fix it -- it would make the DRC gate quieter while the
board becomes no more assemblable, on a mains-voltage IEC 60335-1 induction
cooktop controller where "the capacitors don't actually fit where they were
placed" is a build-stopping defect, not a print-quality one. Shipping a
"fix" that reduces a tracked ratchet number while leaving the underlying
physical collision untouched -- on a safety-critical board, silently -- is
exactly the outcome the ratchet-ceiling machinery in
`power_pcb_dataset/drc_ceiling.json` exists to prevent people from doing by
accident; doing it deliberately here to make one line item look better would
defeat the point.

**No PCB edit is made by this change.** Per the task brief: *"If your fix
requires moving C2 or C3, say so explicitly and stop before doing it -- a
placement change collides with the reroute work and needs sequencing, not a
race."* It does. This document is that explicit stop: fixing the C2/C3,
C5/C7, and (per Sec. 2.3) the K3/C3, L1/C5, C2/PS1, R4/C4, C22/C4, C4/R46
courtyard collisions all requires moving at least one part per pair, on the
same `pcb/temper.kicad_pcb` that a concurrent effort is stripping copper
from and rerouting 7 nets on, and another is resizing vias on. Sequencing a
placement change against those needs a human/orchestration decision, not an
agent racing to land geometry edits on a file three other efforts are
actively rewriting.

## 4. DRC delta

**Zero.** No file under `pcb/` is touched by this change; only this
evidence document is added. `silk_overlap` remains 13,407 true / 199
reported-capped, `courtyards_overlap` remains 8/8 (ceiling already at
measured value, no slack). Per the brief's instruction to report honestly
when a category does not fall: it does not fall, because making it fall via
the only lever available without a placement change (deleting silkscreen)
would be fixing the gate's number instead of the board's defect, on a
component pile-up this document did not create license to paper over.

## 5. Recommended follow-up (not executed here)

1. Coordinate a placement pass, sequenced after the in-flight
   reroute/via-enlargement/stackup work lands on this file, to resolve all
   8 `courtyards_overlap` pairs in Sec. 2.3 -- at minimum, separate C2 from
   C3, and C5 from C7, by more than one body radius' worth of clearance
   (>=17.5mm plus working margin, not the ~13.6-15.7mm they have today).
2. Only *after* placement is fixed does it become meaningful to ask whether
   any residual `silk_overlap` is real cosmetic-only overlap worth trimming
   -- re-run `scripts/measure_uncapped_drc.py saturating-pair` on the
   re-placed board before deciding.
3. `courtyards_overlap`'s ceiling (8) should not be raised to accommodate
   this -- it is already at the live count with no slack; any regression
   elsewhere on the board would need a real fix, not a ratchet increase.

## 6. Reproduction

```bash
# From this branch (fix/silk-overlap-c2-c3, based on origin/fix/drc-ceiling-track-silk-uncap):
mkdir -p /tmp/scratch/silk_c2c3 /tmp/scratch/silk_c5c7
python3 scripts/measure_uncapped_drc.py saturating-pair C2 C3 --scratch-dir /tmp/scratch/silk_c2c3
python3 scripts/measure_uncapped_drc.py saturating-pair C5 C7 --scratch-dir /tmp/scratch/silk_c5c7

# kicad-cli's own courtyard check, independent of the silk-overlap tooling above:
/home/bennet/.local/bin/kicad-cli pcb drc --format json --severity-error \
  --output /tmp/scratch/full_drc.json pcb/temper.kicad_pcb
python3 -c "
import json
d = json.load(open('/tmp/scratch/full_drc.json'))
for v in d['violations']:
    if v['type'] == 'courtyards_overlap':
        print([it['description'] for it in v['items']])
"

# Rendered visual (crop to the C2/C3 and C5/C7 regions after rasterizing):
/home/bennet/.local/bin/kicad-cli pcb export svg --layers F.Fab,F.CrtYd,F.SilkS,Edge.Cuts \
  --page-size-mode 2 --mode-single --output /tmp/scratch/board.svg pcb/temper.kicad_pcb
convert -density 150 /tmp/scratch/board.svg /tmp/scratch/board.png   # imagemagick
```
