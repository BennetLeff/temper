<!-- provenance: commit=459472aafd25e0ad4d0d49bfdd630ad8b6bd03b0 dirty=true -->

# Propagating the corrected footprints into `pcb/temper.kicad_pcb`

Issue #374. Base commit `459472aa` (`fix(pcb): resolve K1/R30 intra-component
copper shorts with datasheet/standards evidence (#420)`), branch
`fix/regenerate-board-corrected-footprints` off
`investigate/intra-component-shorts`, isolated worktree
`agent-a7b2a31967003436b`. `dirty=true`: the "after" numbers were produced by
the change in this same working tree; the "before" numbers come from the
board exactly as committed at `459472aa`, recovered with
`git show 459472aa:pcb/temper.kicad_pcb`.

Environment: macOS arm64 (Darwin 25.5.0), `kicad-cli` 10.0.4, Python 3.12.13,
`uv`.

## Summary (read this first)

`docs/evidence/2026-07-29-intra-component-shorts-root-cause.md` established
two independent causes of the board's intra-component copper shorts, fixed the
tooling half (cause A, `_write_board._reorient_pads`) and left two actions for
a human. Both have now landed: the three defective library footprints were
corrected in `#420`, and this change propagates all of it into the board's
**embedded** footprint copies.

**Result: intra-component copper shorts on `pcb/temper.kicad_pcb` are 60 → 0.**

| metric, median [range] of `kicad-cli pcb drc` runs (before N=9, after N=15) | before | after | Δ |
|---|---|---|---|
| total violations | 1477 [1469–1494] | **1234** [1232–1258] | −243 |
| `shorting_items` | 155 [152–169] | **68** [66–87] | −87 |
| …of which **intra-component** | **60** [60–60] | **0** [0–0] | **−60** |
| …of which router/inter-component | 95 [92–109] | 68 [66–87] | −27 |
| `solder_mask_bridge` | 154 [154–154] | **64** [64–64] | −90 |
| `lib_footprint_mismatch` | 108 [108–108] | **28** [28–28] | −80 |
| `unconnected_items` | 382 [382–382] | **388** [388–388] | **+6** |

The intra-component figure is the deterministic one — pure geometry, zero
scatter on both sides. `unconnected_items` is the only number that rose; §4
proves every newly reported pair is same-net and explains why that is a truth
correction rather than a regression.

## 1. What changed in the board, and only that

`scripts/resync_pcb_netlist.py` preserves existing footprints for
sheetpath-matched components, so it will not refresh embedded geometry on its
own; and any path that rebuilds `board.nets` risks the net-ordinal corruption
documented in `docs/evidence/2026-07-27-post-ovp-resync.md` §1 (measured at
79% of segments and 75% of vias on this exact board). This change therefore
uses a **line-oriented, in-place edit** of the embedded footprints. The net
table is never rebuilt, no copper item is read or rewritten, and no
UUID/`tstamp` is regenerated.

`git diff --stat` on the board: **330 changed lines, 0 added, 0 removed**
(660 `+`/`−` lines against 13,576). Every one of them is a `(pad ...)` line.

| # | Change | Scope | Count |
|---|---|---|---|
| 1 | **U27** `lib:ESP32-S3-WROOM-1` — `(size 0.9 1.7)` → `(size 1.7 0.9)` | the two side rows only, selected by local `x = ±9.00` | **33 pads** (16 left + 17 right) |
| 2 | **R30** `lib:LitzPad_15A` — pad 2 `(at 5 0)` → `(at 13 0)` | pad 2 only; diameter 8.0 and drill 3.0 untouched | **1 pad** |
| 3 | **K1** `temper:Relay_SPST_Omron-G4A-E` — pads 13/14 `(layers "F.Cu")` → `(layers "F.Fab")` | number, type, size, position all unchanged | **2 pads** |
| 4 | **Absolute pad angle** — `(at x y)` → `(at x y R)` where `R` is the parent footprint's board rotation | every pad of every footprint whose rotation is not 0 | **327 pads** |

U27's 5 bottom-edge pads (`y = −12.75`) and its 1 top pad (`y = +12.75`) were
verified untouched: 39 pads on the footprint, 33 changed, 6 unchanged.

### Why the pad angle is exactly `R`

A `.kicad_pcb` pad's `(at x y angle)` angle is **absolute**; KiCad does not add
the parent footprint's angle to it (the additive convention holds only inside
`.kicad_mod` library files). The writer fix computes
`new_pad_angle = new_fp_angle + intrinsic`, where
`intrinsic = old_pad_angle − old_fp_angle`. This edit reproduces that exactly
for the production path (skeleton at rotation 0 → placement applied), which
gives `intrinsic = 0` and `new_pad_angle = R`.

That `intrinsic = 0` is not assumed — it was **measured**. Every one of the 40
distinct library footprints the board references was opened on disk and
scanned for a non-zero pad `at` angle:

```
libraries referenced: 40
missing on disk: 4          (KiCad-10 renames: C_Disc_D10.0mm_W5.0mm_P5.00mm,
                             Fuse_Holder_5x20mm, L_Bourns_SRP1265A,
                             R_Disc_D15.0mm_W7.0mm_P7.5mm)
with intrinsic non-zero pad angles: 0
```

The 4 unresolvable ones are a pre-existing condition (they are the
`lib_footprint_issues` the DRC already reports, 8 before and 8 after) and
carry no pads that could have an intrinsic angle in this board's copy.

327 pads received an angle, out of 519 total — byte-for-byte the same count
the root-cause investigation produced by replaying the real writer
(`pads carrying a non-zero absolute angle in the repaired board: 327`).

## 2. Diff-scope proof — nothing else moved

Both boards were parsed with an independent s-expression reader and compared
field by field. **This is the anti-corruption check; it is the most important
result in this document.**

```
OK   counts: unchanged
       {"footprints": 168, "segments": 2338, "vias": 48, "zones": 96,
        "nets": 164, "arcs": 0}
OK   net table (ordinal -> name): unchanged            (all 164 entries)
OK   footprints (lib_id/ref/uuid/at/layer): unchanged  (all 168, incl. rotation)
OK   copper net identity BY NAME: all 2482 items unchanged
       (breakdown: {'segment': 2338, 'via': 48, 'zone': 96})
OK   pad roster (ref, number) in file order: unchanged (all 519)

pad angles written:   327
pad size changes:      33   (all U27, all 0.9x1.7 -> 1.7x0.9)
pad position changes:   1   (R30 pad 2, [5,0] -> [13,0])
pad layer changes:      2   (K1 pads 13/14, ['F.Cu'] -> ['F.Fab'])
pad NET changes:        0
RESULT: PASS
```

Every segment, via and zone was resolved through the board's own net table to
a net **name**, in file order, on both sides. All 2,482 resolved to the same
name. Zero footprints moved or rotated; zero `tstamp`s changed; zero pads
changed net.

Independently corroborated by the repo's own gate, which reads the board
against the compiled netlist rather than against the old board:

```
$ make netlist && uv run python scripts/check_copper_net_consistency.py
Copper: 2482 item(s) total (Segment=2338, Via=48, Zone=96), 2482 checked
        (net != 0), 0 skipped (net == 0, no-net).
Pads:   510 checked (exact ref+pin match in netlist), 9 skipped
        (no exact match -- resync's positional-fallback candidates).
PASSED -- 0 violations across 2482 copper item(s) and 510 pad(s) checked.
```

Also green and unchanged: `scripts/ci_identity_check.py` (board identity),
`scripts/check_domain_partition.py` (0 domain crossings, 0 isolator-barrier
breaches). `scripts/check_isolation_keepout.py` remains red — it is red on
`main` for an unrelated reason (the board has zero keepout zones; that is
hardware work, `docs/evidence/2026-07-28-isolation-keepout.md`).

## 3. DRC measurement protocol

`docs/STRATEGY.md`: "Any figure gated on `shorting_items` is unreliable at ±11
[...] A shorts fix must be validated over N ≥ 5 runs with median and range,
never a single before/after." Every figure in this document is a **median over
N ≥ 9**, with the full range quoted.

```bash
# before
git show 459472aa:pcb/temper.kicad_pcb > /tmp/before.kicad_pcb
# after
kicad-cli pcb drc --format json -o out.json pcb/temper.kicad_pcb   # x15
```

"Intra-component" means both items of a `shorting_items` violation name the
same component reference, parsed from the DRC item descriptions. It has zero
run-to-run scatter on both boards (60 in all 9 before-runs, 0 in all 15
after-runs), which is what makes it the trustworthy signal in a metric whose
aggregate scatters by ±20.

### `lib_footprint_mismatch`: 108 → 28, with zero new entries

Every class that disappeared is a rotated SMD package — the pad-angle
signature — plus the two corrected project footprints:

| footprint | before | after |
|---|---|---|
| `R_0603_1608Metric` | 28 | 0 |
| `C_0603_1608Metric` | 16 | 0 |
| `SOT-23-5` | 8 | 0 |
| `R_1206_3216Metric` | 7 | 0 |
| `R_0805_2012Metric` | 5 | 0 |
| `R_2512_6332Metric`, `D_SOD-123`, `D_SMA`, `SOT-23`, `SOIC-14_3.9x8.7mm_P1.27mm` | 3, 2, 2, 2, 2 | 0 |
| `L_0603_1608Metric`, `SOT-23-6`, `SSOP-20_3.9x8.7mm_P0.635mm` | 1, 1, 1 | 0 |
| **`LitzPad_15A`** | **1** | **0** |
| **`ESP32-S3-WROOM-1`** | **1** | **0** |
| all remaining (THT parts at rotation 0/180) | 28 | **28** |

The 28 survivors are the same footprints at the same counts before and after
(`CP_Radial` 4, `R_Axial_DIN0918` 4, `C_Rect_L18` 3, `R_Axial_DIN0207` 3,
`C_Rect_L41.5` 2, `Relay_SPDT_Omron-G5LE-1` 2, `TO-220-2` 2, `TO-247-3` 2,
`PinHeader_1x02` 1, `Converter_ACDC` 1, `R_Axial_DIN0204` 1, `RV_Disc` 1,
`DIP-6` 1, `SOIC16W_Isolated` 1). That is pre-existing drift against KiCad 10's
own library revisions; this change neither fixes nor worsens it. **Zero new
mismatches were introduced** — which is the direct confirmation that the board's
embedded copies now agree with `pcb/libs/**`.

## 4. The `unconnected_items` rise, 382 → 388, is a truth correction

This is the one number that went up, and it is the number the root-cause
investigation predicted would go up.

Pads whose oversized or unrotated copper bodies physically overlapped were
being counted by KiCad's connectivity engine as **connected**. Correcting the
geometry separates them, and they are then correctly reported as unrouted.
They were never routed; the short was standing in for a trace.

All 36 newly reported pairs were checked individually against the 30 that
disappeared over the same edit (KiCad re-picks the nearest item for a ratsnest
line, so most of the churn is the same logical break re-described):

```
before: 382 items (382 distinct)   after: 388 items (388 distinct)
NEW pairs: 36   REMOVED pairs: 30
cross-net new pairs: 0
```

**Every one of the 36 is SAME-NET. Zero are cross-net.** The genuinely new
pad-to-pad breaks are exactly the fine-pitch parts the root-cause document
named:

| pair | net |
|---|---|
| `Pad 2` / `Pad 3` of U9 | `vcc` |
| `Pad 4` / `Pad 5` of U9 | `bias` |
| `Pad 6` / `Pad 7` of U9 | `refin_n` |
| `Pad 18` / `Pad 19` of U9 | `gnd` |
| `Pad 11` / `Pad 12` of U23 | `gnd` |
| `Pad 12` / `Pad 13` of U23 | `gnd` |
| `Pad 4` / `Pad 9` of U25 | `safety.fault_or3-b2` |
| `Pad 16` of U9 / `Pad 2` of R37 | `cs_n` |

The remaining 28 are pad↔track re-attributions on nets that were already
reported unconnected before the change.

### Side effects of the K1 and R30 edits, measured rather than assumed

- **R30 pad 2 moved 8 mm.** No copper was landing on its old position: zero
  copper endpoints within 4.0 mm of `(47.28, 182.86)`. It was already reported
  unconnected before the change (`PTH pad 2 [tank-out] of R30` /
  `Pad 1 [tank-out] of T1`) and still is. The move orphaned nothing.
- **K1 pads 13/14 lost their copper layer.** Copper *was* landing on both
  (segments at exactly 0.000 mm from each pad centre), which is why this was
  checked rather than waved through. Net effect on the board: **one** new
  dangling stub, `Track [w1_2] on F.Cu, length 0.0255 mm` — a 25 µm fragment.
  `track_dangling` goes 28 → 29, `via_dangling` 5 → 4. That is the honest
  report: `pcb/libs/temper.pretty/Relay_SPST_Omron-G4A-E.kicad_mod`'s own
  datasheet-sourced `descr` states these are #250 Faston quick-connect tabs
  that "have zero PCB copper connection on this variant; they mate externally
  with a push-on spade connector, not a PCB trace." Copper routed to them was
  never going to be a connection.

## 5. Router-output category (`route_pcb()`), and PR #412

`route_pcb()` was run 3× and its output SHA-256'd to confirm the router's
geometry is deterministic (all three digests identical), then DRC was sampled
N=11 on that one routed file — the protocol
`test_production_board_routing_drc_regression` itself documents.

Two separate causes move this category, and they must not be conflated:

| board / reader state | completion | total | `shorting_items` | …intra | `unconnected_items` |
|---|---|---|---|---|---|
| old board, 2026-07-28 seeding | 0.3854 | 1784 | 186 | — | 396 |
| old board, **today** (reader fix `1979fcc8` only) | 0.3646 | 1821 [1800–1824] | 199 [186–199] | 50 [36–60] | **402** |
| new board, today (reader fix + this change) | 0.3750 | **1551** [1508–1558] | **115** [89–122] | **0** [0–0] | **405** |

- **PR #412's failure is reproduced exactly** on the *unchanged* board: "Router
  output unconnected_items 402 exceeds the measured baseline 396". That +6
  predates this change. It comes from the already-merged reader fix
  (`_parse_modules.py` now recovers `Pin.pad_rotation_deg` as
  `pad_at_angle − fp_angle`), which stopped the placer modelling a board that
  does not exist on disk.
- This change then moves it 402 → 405. All 55 newly reported unconnected pairs
  were checked: **all same-net, 0 cross-net**, same mechanism as §4.
- Completion rate goes **up**, 0.3646 → 0.3750: the router routes *more* once
  the pad geometry it plans against is real.
- Everything else ratchets down hard: total −270, `shorting_items` −84,
  intra-component `shorting_items` 50 → **0**, `lib_footprint_mismatch` 88 → 14.

## 6. Re-baselined constants

`packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py`. These
gates assert the **median of 5** runs, so each threshold is set just above the
worst median-of-5 obtainable from the sample, bootstrapped over every 5-run
subset — not above the worst single run.

| constant | old | new | why |
|---|---|---|---|
| `PRODUCTION_COMMITTED_BOARD_TOTAL_DVIOLATIONS` | 1495 | **1260** | median 1234 [1232–1258]; median-of-5 spans 1232–1250 over all 3003 subsets. Ratchet down 235. |
| `PRODUCTION_COMMITTED_BOARD_SHORTING_ITEMS` | 170 | **90** | median 68 [66–87]; median-of-5 spans 67–83. Ratchet down 80. |
| `PRODUCTION_COMMITTED_BOARD_UNCONNECTED` | 382 | **388** | 388 in all 15 runs, zero scatter. **Raised by exactly the +6 proved same-net in §4.** |
| `PRODUCTION_ROUTER_OUTPUT_TOTAL_DVIOLATIONS` | 1810 | **1560** | median 1551 [1508–1558]; median-of-5 spans 1526–1558 over all 462 subsets. Ratchet down 250. |
| `PRODUCTION_ROUTER_OUTPUT_SHORTING_ITEMS` | 199 | **125** | median 115 [89–122]; median-of-5 spans 89–122. Ratchet down 74. |
| `PRODUCTION_ROUTER_OUTPUT_UNCONNECTED` | 396 | **405** | 405 in all 11 runs, zero scatter. +6 from `1979fcc8`, +3 from this change, all same-net (§5). |

`PRODUCTION_BOARD_BASELINE_SHAPE` (168 / 2338 / 48 / 96) is **unchanged**, and
that is the point: this change rewrote pad geometry without touching a single
piece of copper, so the shape guard correctly stays green (§2).

Both `unconnected` assertion messages were rewritten. The old text —
"this number may only go down" — is true for a fixed board geometry but was
about to be read as a licence to bump a constant; it now says the constraint
holds *for a fixed geometry*, names the one legitimate exception, and requires
a pair-by-pair same-net proof in `docs/evidence/` before the constant may move
again.

Nothing was skipped, xfailed, weakened, or marked `continue-on-error`.

## 7. The gate is NOT wired into CI — and here is exactly why

`scripts/check_pad_orientation.py` on the regenerated board:

```
checked 168 footprints, 519 pads, 1687 different-net pad pairs

FAIL: 1 intra-footprint copper overlap(s) on different nets:
  - K1 (temper:Relay_SPST_Omron-G4A-E): pad 13 [power_in.ntc-no] and
    pad 14 [w1_2] overlap in copper (centres 6.350 mm apart,
    sizes 6.35x1.2 @ 0 deg and 6.35x1.2 @ 0 deg)
```

Measured on both boards with the same invocation (`168 footprints, 519 pads,
1687 different-net pad pairs` on each — the gate compared exactly the same
population before and after, so neither result is a change in what was
measured):

| | before (`459472aa`) | after |
|---|---|---|
| check 1 — rotated footprints with unrotated pad bodies | **67** | **0** |
| check 2 — intra-footprint copper overlaps on different nets | **57** | **1** |

- **Check 1 now PASSES.** That is the check this whole change exists to
  satisfy, and the 57 → 1 collapse on check 2 tracks KiCad's own 60 → 0
  intra-component `shorting_items`.
- **Check 2 fails on K1 alone**, and it is a false positive introduced by the
  gate's own fail-closed rule, not a defect on the board. `_layers_intersect`
  expands a pad's layer list and keeps only copper layers; K1 pads 13/14 now
  declare `("F.Fab",)`, which expands to the empty set, and the rule is "a pad
  with no declared copper layer cannot be proven separate; treat it as sharing
  (fail-closed)". The two pads then touch edge-to-edge at 6.35 mm pitch and are
  reported.

KiCad disagrees with the gate here, and KiCad is right: it reports **0**
intra-component `shorting_items` on this board, K1 included, because there is
no copper on `F.Fab` to short.

**The gate's contract has a real gap**, and this is a finding about the gate,
not a reason to weaken it or the library:

> `_layers_intersect` conflates two different states. A pad that declares
> layers of which *none* are copper is **provably** copper-free and cannot
> short. A pad that declares *no layers at all* is genuinely unknown and must
> fail closed. Only the second deserves the fail-closed treatment.

Fixing that is a change to the gate's semantics with its own falsifier and its
own test coverage, and it does not belong in a change whose job is to write the
board. Per the standing instruction, the gate stays out of
`.github/workflows/python-tests.yml` until it passes on the committed board.
Its 22 unit tests (`scripts/tests/test_check_pad_orientation.py`) all pass and
are unaffected.

## 8. Known-failing and out of scope (verified pre-existing)

Each of these was reproduced on the board **as committed at `459472aa`** and is
not caused by this change:

| item | before | after |
|---|---|---|
| `scripts/check_isolation_keepout.py` | FAIL (0 keepout zones) | FAIL, identical |
| `scripts/check_measurement_provenance.py` | ERROR — `drc_ceiling.json#boards.temper` stale (recorded input hash `815512…` matches neither the committed board `9f2cdb…` nor the new one) | ERROR, same record. Re-measuring the ceiling needs a `Ceiling-Approval:` trailer and is a separate deliverable. |
| `tests/analysis/test_area_sufficiency_check.py::test_real_board_reports_approximately_108_5_pct` | FAIL, 47.9% vs expected ~108.5% | FAIL, 48.2% (R30's 8 mm pad move and U27's transposed pads grow the pad-derived courtyards by ~95 mm²) |
| `tests/closure/test_router_completion.py::TestPostChangePromotionGate` (sm1/sm2/sm6) | FAIL, `router_completion_pct` 0.34375, `benders_iterations` 0 | FAIL, identical 0.34375. DRC errors on that path drop 1015 → 817. |
| `tests/placer/cp_sat/test_zone_pour_production_measurement.py::test_zone_pours_reduce_unconnected_items` | FAIL — pours ON 402 vs OFF 401 `unconnected_items`, i.e. pours made it *worse* | FAIL — pours ON 404 vs OFF 404, a tie. The gate demands a strict reduction. |

The zone/pour case deserves a note because it is the one that moved: it is a
**differential** measurement (both arms routed and DRC'd in the same run), so
it cannot be a stale-baseline artifact either way, and its verdict —
`docs/evidence/2026-07-28-zone-pour-differential-verdict.md`, "zone/pour does
not reduce unconnected items, U4 should not promote" — is unchanged. This
change moves the delta from **−1 (pours actively harmful)** to **0 (no
effect)**, which is a small improvement in the same "does not help" verdict,
not a new failure. `zones_intersect` +96 and `isolated_copper` +8 in the pours
arm are the same signature the verdict document already records.

The full `tests/placer/cp_sat/` + `tests/io/` suite is otherwise green on the
corrected board: **659 passed, 13 skipped, 1 xfailed, 1 failed** (that one).

## Reproduction

```bash
# board invariants and the by-name copper-net proof
make netlist
uv run python scripts/check_copper_net_consistency.py     # exit 0
uv run python scripts/ci_identity_check.py                # exit 0

# the pad-orientation gate (check 1 passes, check 2 fails on K1 -- see Sec 7)
uv run python scripts/check_pad_orientation.py            # exit 1
uv run pytest scripts/tests/test_check_pad_orientation.py -q   # 22 passed

# DRC baselines
kicad-cli pcb drc --format json -o /tmp/drc.json pcb/temper.kicad_pcb
uv run --no-sync python -m pytest \
  packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py -k production
```
