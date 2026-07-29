<!-- provenance: commit=0baca74a79a9f9bed464483db7d91d0302bcd2f4 dirty=true -->

# Intra-component `shorting_items` on `pcb/temper.kicad_pcb`: root cause

Issue #374. Base commit `0baca74a` (`Merge pull request #407 from
BennetLeff/docs/tank-design-envelope-solution`), branch
`investigate/intra-component-shorts`, worktree `agent-aed695f5067ecaa08`.
`dirty=true`: the "after" numbers were produced by the fix in this same
working tree; the "before" numbers come from the unmodified committed
`pcb/temper.kicad_pcb`, which this change does not touch.

Environment: macOS arm64 (Darwin 25.5.0), `kicad-cli` 10.0.4, Python
3.12.13, `uv`.

## Summary (read this first)

**The shorts are real, not a reporting artifact — but their cause is in
tooling, not in the board design.** `pcb/temper.kicad_pcb` is a genuinely
malformed KiCad file: 327 pads on 99 rotated footprints have pad *positions*
that were rotated and pad *bodies* that were not. If you fabricated from this
file, the gerbers would carry the overlaps, because every downstream KiCad
tool reads the same bytes DRC does.

There are **two independent root causes**, and on one component they were
cancelling each other out:

| # | Cause | Where it lives | Intra-component shorts explained |
|---|---|---|---|
| A | `write_placements_to_pcb` rotated footprints without rewriting the pads' absolute `at` angles | tooling (`temper_placer.io._write_board`) | 55 of 60 |
| B | Three hand-built library footprints declare pads that overlap in the footprint's **own** local frame | board design (`pcb/libs/*.pretty/*.kicad_mod`) | 5 of 60, plus 30 more that cause A was masking |

Cause A is fixed in this change. Cause B is a board-design defect: `pcb/` is
read-only to this investigation and the remedy is a human editing three
`.kicad_mod` files — see "What a human must do" below.

Measured effect of the cause-A fix, median of N=9 `kicad-cli pcb drc` runs per
board (this DRC has run-to-run scatter on connectivity-derived counts; the
repo's own baseline records median 164, range 152–175):

| metric | before | after |
|---|---|---|
| total violations | 1487 [1467–1493] | **1262** [1249–1277] |
| `shorting_items` | 168 [148–172] | **110** [99–122] |
| …of which intra-component | 60 [60–60] | **35** [35–35] |
| `solder_mask_bridge` | 154 [154–154] | **78** [78–78] |
| `lib_footprint_mismatch` | 107 [107–107] | **14** [14–14] |
| `unconnected_items` | 382 [382–382] | 389 [389–389] |

The intra-component count is the deterministic one (pure geometry, zero
scatter on both sides): **60 → 35**. Every one of the 35 survivors is cause B.

## What the puzzle actually was

The prior investigation established that U9's pads, transformed into the board
frame *assuming the pad bodies rotate with the footprint*, sit 0.235 mm apart
with no overlap — yet KiCad reports them shorting. The resolution is that the
assumption is wrong for this file: **KiCad does not rotate the pad bodies,
because the file never told it to.**

In a `.kicad_pcb`, a pad's `(at x y angle)` angle is the pad's **absolute**
world orientation. KiCad's parser does *not* add the parent footprint's angle
to it. (The additive convention — angle relative to the parent — holds only
inside `.kicad_mod` library files.) So when a writer sets
`footprint.at = (x y 270)` and leaves every pad's angle absent:

- pad **positions** rotate, because KiCad rotates the footprint-relative `at`
  offsets at load time — which is why the prior transform reproduced DRC's
  reported pad coordinates exactly;
- pad **bodies** do not, because each pad's own absolute angle is still 0.

U9 is an SSOP-20: 1.2 × 0.4 mm pads on a 0.635 mm pitch. Rotated 270°, the
pitch axis becomes board-X while the pad bodies still present their 1.2 mm
dimension along board-X. Adjacent pads are 0.635 mm apart and 1.2 mm wide
across that axis: **0.565 mm of solid copper overlap** between every adjacent
pair. That is a real short, and KiCad is right to report it.

This also explains the fingerprint the prior investigation noticed but could
not place: shorts appear on *every adjacent pad pair carrying different nets*,
and only there. The "duplicated adjacent nets" lead on U9 (pads 2/3 both
`vcc`, 4/5 both `bias`, 6/7 both `refin_n`) was a coincidence of that
component's pinout — those pairs overlap too, they just aren't *shorts*
because both pads are on the same net, so DRC stays silent. U23, which has no
duplicated nets, shorts on all nine of its adjacent pairs. One rule, no
exceptions.

### Why only a handful of components, when 99 footprints are rotated

Because the overlap is `pad_long_axis − pitch`, and only fine-pitch packages
with elongated pads have a positive value there. A 0603 resistor rotated 90°
has 0.56 × 0.62 mm pads 0.96 mm apart: still a 0.34 mm gap after the bug.
SOIC/SSOP/SOT rows are the packages where the pad's long axis exceeds the
pitch. That is why the defect concentrates on U9/U7/U25/U23/U4/U19/U20/U22
rather than spraying across the board.

## Evidence

### 1. `pcb/temper.kicad_pcb` was not written by KiCad

```
$ head -1 pcb/temper.kicad_pcb
(kicad_pcb (version 20211014) (generator kiutils)
```

`kiutils` is a third-party Python serializer. Across all 168 footprints and
519 pads, **zero** pads carry an `at` angle, while 99 footprints are rotated
(44 at 90°, 32 at 180°, 23 at 270°) covering 327 pads.

### 2. Real KiCad files write the absolute pad angle

`packages/temper-placer/tests/fixtures/external/.cache/bitaxe_ultra/bitaxeUltra.kicad_pcb`
(`generator pcbnew`, i.e. authored by KiCad itself):

| footprint rotation | pad `at` angle | pads |
|---|---|---|
| 0° | absent | 148 |
| 90° | 90° | 42 |
| 180° | 180° | 105 |
| 270° | 270° | 92 |
| 90°/270° | other (0/180/270) | 53 |

The dominant diagonal is `pad_angle == fp_angle`, which is only consistent
with the angle being absolute. (The off-diagonal entries are pads whose
library footprint gives them an intrinsic rotation; e.g. 13 pads sit at
absolute 0 on a 90°-rotated footprint, which is legal and unambiguous under
the absolute reading and impossible to express under a relative one.)

### 3. Controlled experiment: deleting the angles breaks a known-good board

Take that same KiCad-authored board, which reports **zero** `shorting_items`
and **zero** `solder_mask_bridge`, and strip only the angle token from every
pad's `at`:

```bash
python3 - <<'EOF'
import re
src = open('bitaxeUltra.kicad_pcb', errors='replace').read()
new, n = re.subn(r'(\(pad "[^"]*" \w+ [\w_]+\s*\(at [-\d.]+ [-\d.]+) [-\d.]+\)', r'\1)', src)
open('bitaxe_stripped.kicad_pcb', 'w').write(new)   # n == 270 pads
EOF
kicad-cli pcb drc --format json -o b_orig.json  bitaxeUltra.kicad_pcb
kicad-cli pcb drc --format json -o b_strip.json bitaxe_stripped.kicad_pcb
```

| board | total | `shorting_items` | `solder_mask_bridge` |
|---|---|---|---|
| original | 386 | **0** | **0** |
| pad angles stripped | 658 | **103** | **127** |

Nothing moved. No geometry changed. Only 270 optional tokens were deleted, and
a clean board acquired 103 copper shorts. That is the temper board's exact
condition, reproduced on an independent board from a different author.

### 4. The inverse experiment on the temper board

Adding `fp_angle` to every pad's `at` on rotated footprints (327 pads, in a
scratch copy — `pcb/` untouched) drops `shorting_items` 164 → 100,
`solder_mask_bridge` 154 → 78, and `lib_footprint_mismatch` 107 → **14** in a
single run. The `lib_footprint_mismatch` collapse is independent
corroboration: KiCad's own board-vs-library comparator agrees the embedded
footprints only match their libraries once the pad angles are present.

### 5. Model check against every reported short

Two geometric models were computed over all 168 footprints and compared
against the 56 Pad+Pad `shorting_items` KiCad reports:

| model | predicted | matching DRC | missed | spurious |
|---|---|---|---|---|
| pad bodies rotate with the footprint | 31 | **0** | 56 | 31 |
| pad bodies do **not** rotate | 56 | **55** | 1 | 1 |

The "do not rotate" model reproduces DRC almost exactly. Its one miss (K1
pads 13/14, which touch at exactly zero gap — a strict-inequality artifact of
that first script) and its one spurious hit (R30, which DRC reports as
`PTH pad`, not `Pad`) are both accounted for below; the final gate,
`scripts/check_pad_orientation.py`, matches DRC on **57 of 57** geometric
pairs.

## Cause B: three library footprints whose pads overlap in their own frame

This check is rotation-independent: it asks whether two different-net pads of
a footprint overlap in the footprint's *local* coordinates, before any
placement. Exactly three footprints fail, all from the project's own
libraries; no KiCad standard-library footprint fails.

| ref | library footprint | source file | defect |
|---|---|---|---|
| U27 | `lib:ESP32-S3-WROOM-1` | `pcb/libs/lib.pretty/ESP32-S3-WROOM-1.kicad_mod` | pads declared `(size 0.9 1.7)` at a **1.27 mm pitch along Y** — the 1.7 mm dimension lies on the pitch axis, so adjacent pads overlap by 0.43 mm. Width and height are transposed: the Espressif land pattern is 0.9 mm across the pitch, 1.7 mm outward. **30 pairs.** |
| R30 | `lib:LitzPad_15A` | `pcb/libs/lib.pretty/LitzPad_15A.kicad_mod` | two 8.0 mm-diameter through-hole pads on a **5.0 mm** pitch — 3 mm of overlap. Its own `descr` already says "low confidence — no part-specific datasheet exists... Flagged for human visual cross-check before fabrication." **1 pair** (reported 4× by DRC, once per copper layer). |
| K1 | `temper:Relay_SPST_Omron-G4A-E` | `pcb/libs/temper.pretty/Relay_SPST_Omron-G4A-E.kicad_mod` | pads `13`/`14` are 6.35 mm wide at a **6.35 mm** pitch — exactly zero gap, edge-to-edge contact. **1 pair.** |

### The two causes were cancelling on U27

U27 shows **no** shorts on the committed board and **30** after the cause-A
fix. That is not a regression. Its footprint is rotated 270°, so under cause A
its pads presented their 0.9 mm dimension along the (board-X) pitch axis and
cleared by 0.37 mm. Rotate the bodies correctly and the declared 1.7 mm
dimension lands on the 1.27 mm pitch, which is what the library actually says.
Two bugs were hiding each other; fixing one exposes the other. U27's copper
was never correct — it was wrong in a way that happened to look right.

## The fix (tooling)

`packages/temper-placer/src/temper_placer/io/_write_board.py` —
`write_placements_to_pcb` set `footprint.at` rotation and nothing else. It now
calls a new `_reorient_pads(fp, old_fp_angle, new_fp_angle)`, which rewrites
every pad's absolute angle as `new_fp_angle + intrinsic`, where
`intrinsic = old_pad_angle − old_fp_angle` — so a pad with a genuine
library-defined rotation keeps it.

`packages/temper-placer/src/temper_placer/io/_parse_modules.py` — the reader
must move with the writer or the round trip double-counts. `Pin.pad_rotation_deg`
is documented as the pad's rotation *relative to its footprint* (every
consumer — `core.pad_geometry`, `router_v6.obstacle_map`,
`requirements.validators._copper` — adds the component rotation to it), so it
is now recovered as `pad_at_angle − fp_angle` instead of being read as
`pad_at_angle`. On the committed board (all pad angles 0) this makes the
internal model agree with KiCad's reading of the same file, which is the
point: the placer now *sees* the overlaps rather than modelling a board that
does not exist on disk.

`scripts/internal_route.py` computed `pad_abs_angle = fp_angle + pad.at.angle`,
the `.kicad_mod` convention applied to a `.kicad_pcb`. It now uses the pad's
angle directly.

Not changed, deliberately: `scripts/check_isolation_keepout.py` models pads
with `pad_bounding_radius`, which is provably rotation-invariant, so pad-angle
semantics cannot affect its verdict.

### End-to-end proof through the real writer

The production path is skeleton (`scripts/gen_pcb_skeleton.py`, all footprints
at rotation 0) → `write_placements_to_pcb` applies CP-SAT's placement. To
measure the fix on the real board without touching `pcb/`, that step was
replayed: zero every footprint angle in a scratch copy (reproducing the
skeleton's shape), then write back each component's true `(x, y, rotation)`
through `write_placements_to_pcb`. Tracks, vias, zones and nets are carried
through untouched.

```
template written: 168 footprints, all at rotation 0
placed: updated=168 skipped=0
pads carrying a non-zero absolute angle in the repaired board: 327
```

DRC on that output gives the "after" column in the summary table.

The `unconnected_items` increase (382 → 389) is the same defect being told
honestly. The seven new entries are pairs like `Pad 18 [gnd] of U9` /
`Pad 19 [gnd] of U9` and `Pad 2 [vcc] of U9` / `Pad 3 [vcc] of U9` —
**same-net** pads that were only "connected" because their oversized copper
bodies overlapped. Correct the geometry and they are correctly reported as
unrouted. They were never routed; the short was standing in for a trace.

## The gate

`scripts/check_pad_orientation.py`, tested by
`scripts/tests/test_check_pad_orientation.py` (22 tests). Two independent
checks over the board's own bytes — no library lookup, no KiCad invocation:

1. **Rotation reached the pads.** A footprint rotated by a non-multiple of
   180° whose pads *all* carry absolute angle 0 is flagged. 180° is exempt: it
   maps an axis-aligned pad onto itself, so the omission is unobservable in
   copper. A narrow `ALLOWLIST` exists for the rare legal case of a library
   whose intrinsic pad rotation genuinely cancels the placement.
2. **No intra-footprint copper overlap on different nets.** A separating-axis
   test over the pads' oriented rectangles; coincident edges count as
   connected, matching KiCad's connectivity engine.

Sensitivity and specificity, both measured:

| board | verdict | detail |
|---|---|---|
| `pcb/temper.kicad_pcb` | **FAIL** (exit 1) | 67 rotated footprints with unrotated pads; **57** overlapping pairs — exactly the 57 distinct geometric pairs behind KiCad's 60 intra-component `shorting_items` rows (R30's single pair is reported once per copper layer) |
| `bitaxeUltra.kicad_pcb` (KiCad-authored) | **PASS** (exit 0) | 137 footprints, 444 pads, 2258 different-net pairs, zero false positives |

The gate is **not** wired into a CI workflow by this change, because it fails
on the committed board by design — that failure *is* issue #374, and the board
is read-only here. Wire it in the same change that lands the regenerated
board.

Fail-closed: exits non-zero on a missing, unparseable or non-`kicad_pcb` file,
on zero footprints, on zero pads, and on zero pad pairs compared (an overlap
check that evaluated nothing is a broken invocation, not a clean board).

Regression coverage for the writer itself:
`packages/temper-placer/tests/io/test_pad_orientation_roundtrip.py` (8 tests) —
pad bodies follow their footprint at 90/180/270°, the resulting adjacent gap
is exactly `pitch − pad_width` (0.235 mm for an SSOP-20), intrinsic pad
rotation survives, and write→parse→write is stable rather than accumulating a
rotation per pass. **Falsifier: disabling `_reorient_pads` fails 7 of those 8
tests**; all 8 pass with it.

## The other 91 shorts (Pad+Track, Track+Via, Pad+Via, …)

Partly the same mechanism, and the residue is a genuine routing problem.
`Pad+Track` shorts halve (46 → 23) and `Track+Via` shorts halve (33 → 17) from
the cause-A fix alone, for two reasons: over-long pad bodies physically
collide with traces routed to their neighbours, and `shorting_items` is a
*connectivity-cluster* check, so one bridged pad pair merges two net clusters
and every track and via on either net becomes a reported short. Those are
second-order reports of the same defect.

The remainder is real router output that must be fixed by routing, not by
this change. It is tracked by the existing DRC ratchet
(`PRODUCTION_ROUTER_OUTPUT_SHORTING_ITEMS`) and is out of scope here.

## What a human must do (board design — NOT done here)

`pcb/` is read-only to this investigation. Two actions, in order:

1. **Fix the three library footprints** (cause B). All three are
   fabrication blockers; the two high-current ones sit on mains-adjacent nets.
   - `pcb/libs/lib.pretty/ESP32-S3-WROOM-1.kicad_mod` — transpose every pad's
     `(size 0.9 1.7)` to `(size 1.7 0.9)` for the two side rows (pads at
     `x = ±9.00`, pitched in Y) so the 0.9 mm dimension lies on the 1.27 mm
     pitch, and re-derive the bottom thermal row (pads at `y = ±12.75`,
     pitched in X) against the Espressif land pattern rather than by
     inspection. **Verify against the ESP32-S3-WROOM-1 datasheet recommended
     PCB land pattern — do not take the transposition on this document's
     word.**
   - `pcb/libs/lib.pretty/LitzPad_15A.kicad_mod` — 8.0 mm pads on a 5.0 mm
     pitch cannot exist. Either the pad diameter or the pitch is wrong. This
     footprint's own description already flags it as unsourced and awaiting
     human cross-check; it carries the resonant-tank current, so the
     resolution needs a real terminal spec, not a geometric nudge.
   - `pcb/libs/temper.pretty/Relay_SPST_Omron-G4A-E.kicad_mod` — pads `13`/`14`
     are 6.35 mm wide on a 6.35 mm pitch (zero gap). The file comments say
     they are "modeled as an SMD landing pad on F.Cu for netlist/pin-count
     parity only", so shrinking them to restore a real clearance should be
     electrically free — but confirm that against the G4A-E terminal drawing.
2. **Regenerate `pcb/temper.kicad_pcb`** through the fixed writer so the pad
   angles land on disk, then re-run `scripts/check_pad_orientation.py` (must
   exit 0) and wire it into CI.

Until step 2 lands, the committed board remains malformed and
`scripts/check_pad_orientation.py` will keep failing on it. That is the
correct reading, not a gate to relax.

## Reproduction

```bash
# Baseline DRC on the committed board
kicad-cli pcb drc --format json -o /tmp/drc.json pcb/temper.kicad_pcb

# The gate: fails on the committed board, passes on a KiCad-authored one
uv run python scripts/check_pad_orientation.py            # exit 1
uv run python scripts/check_pad_orientation.py \
  packages/temper-placer/tests/fixtures/external/.cache/bitaxe_ultra/bitaxeUltra.kicad_pcb  # exit 0

# Regression coverage
uv run pytest scripts/tests/test_check_pad_orientation.py \
              packages/temper-placer/tests/io/test_pad_orientation_roundtrip.py -q
```
