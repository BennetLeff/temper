<!-- provenance: commit=e63028ccde1be397032479e0735f2a7c1f710d95 dirty=false (worktree zonefill-measure, branched from origin/main at e63028ccd, clean at HEAD; pcb/temper.kicad_pcb never written by this task -- it was chmod a-w for the duration and every kicad-cli run executed against a scratch copy given a resolvable project via copy_kicad_project_sidecar. sha256 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b verified unchanged before and after, see sec 0. kicad-cli 10.0.5; pcb/temper.kicad_dru regenerated (gitignored). No number in power_pcb_dataset/drc_ceiling.json was changed.) -->

# Should `pcb/temper.kicad_pcb` ship with its zones filled?

**Verdict: (c), narrowly — the current unfilled state is correct *as the
measurement basis*, for a reason not previously articulated: it is what
fabrication actually receives. But "correct" applies only to the protocol
question. Neither (a) nor (b) survives measurement, and the board itself
carries two defects this measurement exposes.**

- **(a) ship filled — DISQUALIFIED.** KiCad's fill of this board is not
  reproducible. Six fills of a byte-identical input produced six different
  files and six different coppers (§4). One of the racing pours is the
  +170 V DC bus.
- **(b) refill before measuring — DISQUALIFIED as a ceiling basis.** Its
  stated justification is that filled pours genuinely connect nets and the
  9 zone-dependent nets are merely unmeasured. Measured against KiCad's own
  connectivity engine, that is false: filling completely connects **none**
  of the nine (§2). Refilling would also make DRC measure copper that the
  current fabrication output does not contain (§6).
- **(c) as amended.** The unfilled board's gerbers carry **zero** pour
  copper (§6), so today's DRC is fabrication-accurate, not blind. That is
  the un-articulated reason. It is *not* a statement that the board is fit
  to build.

`--refill-zones` should be adopted as a standing **safety probe** reported
alongside the ceiling, never as the ceiling itself — it is how the mains
barrier defect in §3 was found.

---

## 0. Protocol, provenance, instrument state

| | |
|---|---|
| Worktree | cut fresh from `origin/main` @ `e63028ccde1be397032479e0735f2a7c1f710d95` |
| Board | `pcb/temper.kicad_pcb` sha256 `26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b` — **verified unmodified at start and end** |
| Board state | 151 zone blocks, **0** `filled_polygon`, 10 uuids in the whole file |
| kicad-cli | 10.0.5 |
| Flags | `--all-track-errors --format json` — `run_drc()`'s exact list; the only variable added is `--refill-zones` |
| Thread pinning | `_drc_api._single_threaded_kicad_env()`, confirmed active (`pinned=True`) |
| `pcb/temper.kicad_dru` | **regenerated** (gitignored) via `scripts/generate_kicad_dru.py` → 33208 bytes, sha256 `488a01a81ea29dd6b4ed3106d3f5c0b036a9d07bf9a545a60b1ca6fbc74a0fdb`, 33 rules. Verified live: `creepage` reads 106, not 0 |
| `fp-lib-table` | present as a board sibling. Verified live: `lib_footprint_issues` reads **13**, not the 168 signature; `lib_footprint_mismatch` 26 |
| Samples | 3 runs per condition, violation **sets** intersected (not counts) |
| cProfile | **not enabled** in any run |
| Machine load | 1-min loadavg 3.94–10.65 across the session on 24 cores (other agents active). Counts were invariant to load; only wall-clock varied |
| `scripts/check_stale_extensions.py` | run before and after. **8 stale / 2 fresh / 0 unloadable**, *all* decided by mtime fallback with no build stamp. Not load-bearing here: the DRC path is `kicad-cli` (external binary) and `pad_connectivity_audit` is pure Python (its only import is `topology_copper_audit`). The one Rust dependency, `temper_design_bundle_python`, is used solely to *generate* the `.kicad_dru`, whose output was checked against its own content |
| Board writes | none. `pcb/temper.kicad_pcb` was `chmod a-w` for the duration as a guard; all work used scratch copies with `copy_kicad_project_sidecar` |

### Two instrument errors found and corrected mid-measurement

1. **kicad-cli synthesizes item uuids.** The board carries 10 uuids, so
   kicad-cli invents one per reported item, per run: 271 of ~617 item
   uuids shared across two runs of the *same* board whose counts were
   identical at 776. Keying violations on uuid made a deterministic board
   read as 1398/1673 unstable. **Key on `(description, x, y)`; never on
   uuid.** Corrected, the same board reads 773 stable / 6 unstable.
2. The repo's own `_parse_drc_json` **does not read the top-level
   `unconnected_items` array at all** (339 entries here, none of them in
   the 776). Every ratchet number is blind to it. This measurement reads
   it directly.

---

## 1. Full DRC diff — every category that moves

3 runs each, sets intersected. **A** = committed board, no refill (status
quo). **B** = same file + `--refill-zones` (in-memory). **C** = three
*independently filled* board files, DRC'd with no refill flag — what
shipping a filled artifact would actually measure.

| category | A unfilled | B +refill | C filled-file | Δ | safe / unsafe |
|---|---|---|---|---|---|
| `via_dangling` | **111** | **28** | **28** | **−83** | **safe** — see §1.1 |
| `creepage` | **106** | **130** | 129–130 | **+24** | **UNSAFE** — §3 |
| `isolated_copper` | 0 | **2** | **2** | **+2 (new class)** | unsafe (floating copper) |
| `clearance` | 179 | 180 | 180 | +1 | unsafe (minor) |
| `shorting_items` | 39 | 39 | 39 | 0 | — |
| `copper_edge_clearance` | 11 | 11 | 11 | 0 | — |
| `hole_clearance` | 33 | 33 | 33 | 0 | — |
| `silk_overlap` | 199 | 199 | 199 | 0 | **199 = `ERROR_LIMIT` cap — a floor, not a count** |
| `silk_over_copper` | 42 | 42 | 42 | 0 | — |
| `lib_footprint_issues` | 13 | 13 | 13 | 0 | — |
| `lib_footprint_mismatch` | 26 | 26 | 26 | 0 | — |
| `missing_courtyard` / `courtyards_overlap` | 5 / 1 | 5 / 1 | 5 / 1 | 0 | — |
| `drill_out_of_range` | 6 | 6 | 6 | 0 | — |
| `solder_mask_bridge` | 4 | 4 | 4 | 0 | — |
| `silk_edge_clearance` | 1 | 1 | 1 | 0 | — |
| **errors** | **379** | **404** | 403–404 | **+25** | |
| **warnings** | **397** | **316** | **316** | **−81** | |
| **total violations** | **776** | **720** | 719–720 | **−56** | |
| **`unconnected_items`** | **339** | **264** | **264** | **−75** | §2 |

Set-level (not count-level) diff, A → filled:

- **30 violations appear**: 23 `creepage`, 4 `shorting_items`, 2
  `isolated_copper`, 1 `clearance`.
- **87 violations disappear**: 83 `via_dangling`, 4 `shorting_items`.
- **All 23 new `creepage` violations involve a zone item.** Zero of the
  106 baseline creepage violations do — they cannot, there is no copper.

### 1.1 `via_dangling` 111 → 28 is real, and it reverses a prior finding

The 83 removed are genuine artifacts of measuring an unfilled board: the
vias are connected by pour copper that does not exist on disk. 28 survive
and are real defects.

**This does not contradict `docs/evidence/2026-08-17-refill-zones-drc-runner-gap-measurement.md`; it supersedes it on a different board.** That
document measured board sha `9c1f4a37…` (96 zones) and found
`via_dangling` **25 with and without refill** — a null result with a
positive control. Today's committed board is sha `26981fea…` (151 zones)
and gives **111 → 28**. The null result was true of that board, not this
one. Any citation of "25, unchanged under refill" against the current
board is stale.

---

## 2. Connectivity — the crux, and the premise is false

`pad_connectivity_audit.audit_pcb_file(Path)` on the committed board
reproduces the briefed baseline **exactly**:

```
139 nets: connected 60 | broken 70 | zone_dependent_unmeasured 9
zone blocks: filled=0 unfilled=151
```

**The same call on a filled board raises `ValueError: Expression does not
have the correct type`.** `zone_layers_and_fill_stats` returns
`filled=0 unfilled=0` — it counts zero zone blocks in a file that has 151.
The repo's connectivity instrument cannot read a KiCad-10-saved board at
all (§4.2). So the audit cannot answer the question on a filled artifact;
it can only answer it on the artifact that has no copper.

Answered instead with **KiCad's own connectivity engine** (the
`unconnected_items` array), which does understand filled zones:

| net (the nine) | unfilled | r4 | r5 | r6 | result |
|---|---|---|---|---|---|
| `+170V_BUS` | 10 | 8 | 8 | 8 | improved, not resolved |
| `DC_BUS_RTN` | 7 | 6 | 6 | 6 | improved, not resolved |
| `PWR_RTN` | 14 | 13 | 13 | 13 | improved, not resolved |
| `SW_NODE` | 6 | 4 | 4 | 4 | improved, not resolved |
| `ac_n` | 2 | 1 | 1 | 1 | improved, not resolved |
| `tank.c_tank1-p2` | 3 | 2 | 2 | 2 | improved, not resolved |
| `power_in.ntc-no` | 2 | 2 | 2 | 2 | **unchanged** |
| `w1_1` | 3 | 3 | 3 | 3 | **unchanged** |
| `w1_2` | 1 | 1 | 1 | 1 | **unchanged** |

**Filling completely connects none of the nine.** The count of nets
appearing in `unconnected_items` is **79 before and 79 after** — not one
net leaves the list. The −75 improvement is concentrated in two plane
nets: `gnd` 84 → 40 (−44) and `+3V3` 47 → 25 (−22), i.e. 66 of 75.

This kills (b)'s premise. It also independently corroborates
`docs/evidence/2026-08-15-unrouted-nets-rootcause.md`: *"a fill pass would
not fix these nets — the outlines are in the wrong place."*

**The closed loop in the brief is real and worse than stated.** Policy
excludes six of the nine from A\* because "a pour covers them"; the verdict
function refuses to credit a pour as copper; and the gerbers (§6) contain
no pour at all. All three agree those nets have **no copper**. Filling does
not open the loop.

---

## 3. Filling introduces a mains-to-SELV barrier violation

Classification is by the DRU rule name kicad-cli itself reports. No
standards value is invented, read from Table 8, or taken from anywhere but
the generated `.kicad_dru` and the violation text KiCad emitted.

Creepage violations per rule, unfilled vs all six independent fills:

| rule | required | unfilled | r1 | r2 | r3 | r4 | r5 | r6 |
|---|---|---|---|---|---|---|---|---|
| **`AC Mains to LV`** | **12.6 reinforced** | **4** | **16** | 16 | 16 | 16 | 16 | 16 |
| `HV to LV` | 12.6 reinforced | 56 | 67 | 68 | 67 | 67 | 68 | 67 |
| `HighVoltageIsolated to LV` | 12.6 reinforced | 20 | 20 | 20 | 20 | 20 | 20 | 20 |
| `HighVoltageSignal to LV` | 12.6 reinforced | 17 | 17 | 17 | 17 | 17 | 17 | 17 |
| `HighVoltageTank to LV` | 12.6 reinforced | 7 | 7 | 7 | 7 | 7 | 7 | 7 |
| `HighVoltageTank functional` | 10.0 HV↔HV | 2 | 2 | 2 | 2 | 2 | 2 | 2 |

Worst-case (minimum) actual surface path, in mm:

| rule | unfilled | every fill (r1–r6) |
|---|---|---|
| **`AC Mains to LV`** | **11.5078** | **6.0005** |
| `HV to LV` | 0.67 | 0.67 |
| `HighVoltageSignal to LV` | 0.67 | 0.67 |
| `HighVoltageIsolated to LV` | 3.5781 | 3.5781 |
| `HighVoltageTank to LV` | 8.2117 | 8.2117 |
| `HighVoltageTank functional` (10.0) | 5.0 | 5.0 |

**The HV↔HV tank pair at 10.0 mm is untouched by filling** — 2 violations,
worst 5.0 mm, in every condition. That is a clean negative result.

**The mains barrier is not.** Filling the `ac_n` pour (240 V AC neutral,
priority 80) takes the worst `AC Mains to LV` creepage from **11.5078 mm to
6.0005 mm** against a **12.6 mm reinforced** requirement — a 6.6 mm
deficit, reproducible in all six fills. The four worst new pairs:

```
required 12.6  actual 6.0005  Via [+3V3] on F.Cu-B.Cu  <->  Zone [ac_n] on In3.Cu (priority 80)
required 12.6  actual 6.0005  Via [+3V3] on F.Cu-B.Cu  <->  Zone [ac_n] on In4.Cu (priority 80)
required 12.6  actual 6.0005  Via [+3V3] on F.Cu-B.Cu  <->  Zone [ac_n] on B.Cu   (priority 80)
required 12.6  actual 6.0005  Via [gnd]  on F.Cu-B.Cu  <->  Zone [ac_n] on B.Cu   (priority 80)
```

All 23 new creepage violations involve zone copper: 12 `AC Mains to LV`,
11 `HV to LV`.

**Read this correctly.** The fill does not *create* a hazard that filling
invented — it makes an existing one measurable. The `ac_n` zone outline
already encroaches on SELV vias; only the absence of copper hides it. A
board built with these outlines filled has a 6.0 mm mains-to-SELV gap.
This is a **board defect, exposed by the probe**, and it is the single
strongest reason not to adopt (a) by simply filling and re-baselining:
that would ratchet a mains-barrier violation into the accepted baseline.

---

## 4. Determinism — the fill is not reproducible

### 4.1 The copper differs run to run

Six independent fills of the byte-identical committed board
(`--refill-zones --save-board`), r1–r3 unpinned, **r4–r6 with
`_single_threaded_kicad_env()` pinning** — the nondeterminism is present
in both, so it is not a thread-pool artifact of the harness:

| | r1 | r2 | r3 | r4† | r5† | r6† |
|---|---|---|---|---|---|---|
| file size (bytes) | 2748930 | 2789331 | 2771483 | 2759066 | 2782867 | 2768199 |
| sha256 | all six distinct | | | | | |
| `filled_polygon` rings | 144 | 144 | 144 | 144 | 144 | 144 |
| fill vertices | 27942 | 29457 | 28795 | 28316 | 29202 | 28687 |
| total copper (mm²) | 22033.77 | 22099.36 | 22218.35 | 22215.68 | 22094.83 | 22031.86 |

† pinned.

Compared **order-independently** (zone order in the file is itself
unstable, so index-pairing is invalid and was discarded):

- **Only 57 of 144 filled rings (39.6%) are identical across all six runs.**
- Total copper area spread **186.50 mm² (0.84%)**; vertex-count spread
  1515 (5.4%).

### 4.2 Per-net, the instability is bimodal and lands on the HV bus

| layer / net | observed filled areas across r1–r6 (mm²) |
|---|---|
| **B.Cu `+170V_BUS`** | **471.85 / 472.14** or **923.78** — a 451.94 mm² coin flip |
| **In3.Cu `+170V_BUS`** | **285.71 / 286.00** or **616.54 / 616.82** — 331.11 mm² |
| **B.Cu `hb-gnd`** | **96.06** or **365.45** — 269.39 mm² |
| **In3.Cu `hb-gnd`** | **33.42** or **245.97** — 212.55 mm² |
| In1.Cu (all) | perfectly stable, spread 0.0000 |

`+170V_BUS` and `hb-gnd` are **exactly anti-correlated**: when one takes
the shared region the other loses it.

**Root cause: equal-priority overlapping zones.** On B.Cu and In3.Cu both
nets' zones are declared at **`priority 70`** with overlapping outlines
(`+170V_BUS` B.Cu outline 487.060 mm², `hb-gnd` B.Cu outline 365.501 mm²).
KiCad's fill order between equal-priority zones is not defined, so
whichever fills first claims the copper. 35 of 46 (layer, net) buckets show
a nonzero area spread; the outer/In3/In4 layers put 22–28 zones each at
priority 70, so the collision is systemic, not a one-off.

**This is a board defect, independent of the fill/no-fill decision.** It
should be fixed by assigning distinct priorities regardless of which option
is chosen.

### 4.3 A filled board is also nondeterministic to *measure*

| condition | violations UNSTABLE across 3 runs | `unconnected_items` UNSTABLE |
|---|---|---|
| A unfilled | 6 of 779 | **0 of 339 — perfectly deterministic** |
| B +refill | 10 of 725 | **76 of 307** |
| C filled files | 18 of 729 | **69 of 303** |

Under refill the *count* of unconnected items is 264 every run while
**which** items are unconnected changes run to run. The connectivity
verdict itself becomes nondeterministic. Today's unfilled measurement is
the only one of the three that is exactly reproducible.

### 4.4 `--save-board` is a format migration, not just a fill

The committed board is written in the legacy s-expression dialect
(`(zone (net 3) (net_name "+170V_BUS") ...)`). KiCad 10.0.5 rewrites the
whole file to the current dialect (`(zone (net "+170V_BUS") ...)`):

- **1563506 → ~2.76 MB (+76%)**
- **10 uuids → 10071**, of which only **4900 are shared between two
  consecutive saves** — ~51% churn on every regeneration
- the repo's `pad_connectivity_audit` / `kicad_parser` **cannot parse the
  result at all** (§2)

So committing a filled board also commits a whole-file dialect migration
whose diff is ~19,000 lines and ~50% unstable per regeneration.

---

## 5. What fabrication actually receives

`kicad-cli pcb export gerbers`, B.Cu layer, G36 = area-fill region:

| source | bytes | G36 regions |
|---|---|---|
| committed board (unfilled) | 68661 | **0** |
| filled copy (r4) | 162629 | **34** |
| `output_gerbers/routed_v3_with_zones-B_Cu.gbl` (committed, KiCad 9.0.6, 2025-12-29) | 5178 | **0** |
| `output_gerbers/routed_v3_with_zones-F_Cu.gtl` (committed) | 13162 | **0** |

**The committed fabrication output contains no pour copper — despite being
named `with_zones`.** The same fiction the DRC protocol carries has already
propagated into the artifact's filename.

This is the un-articulated reason (c) is right *about the protocol*:
today's DRC measures what today's gerbers contain. Refilling before
measuring, while shipping the board unfilled, would make DRC measure a
board nobody builds — a new instrument lie in the opposite direction.

**Residual ambiguity, and it is safety-relevant.** `kicad-cli` does not
auto-fill, but a human opening this board in the KiCad GUI and plotting
would very likely fill first — that is the normal fab workflow. The
committed artifact is therefore **ambiguous about what gets built**: one
plausible workflow yields ~22,000 mm² of copper and a 6.0 mm mains-to-SELV
gap; the other yields no pour copper and 9 unconnected primary-power nets.
Neither is fit to fabricate, and the artifact does not say which you get.

---

## 6. What a fill would invalidate

**`drc_ceiling.json` is already stale against the committed board** — its
`provenance.inputs[0].sha256` is `9c1f4a37…`, the board is `26981fea…`.
Consistent with the known-red state on `main` (#1370). **No number in it
was changed by this work, and no re-baseline is proposed.** Deltas only:

| ceiling entry | recorded | measured today (unfilled) | measured filled |
|---|---|---|---|
| `error_ceiling` | 2201 | 379 | 403–404 |
| `warning_ceiling` | 13563 | 397 | 316 |
| `clearance` | 1117 | 179 | 180 |
| `creepage` | 272 | 106 | 129–130 |
| `shorting_items` | 183 | 39 | 39 |
| `silk_overlap` | 13407 | 199 (**capped**) | 199 (**capped**) |
| **`via_dangling`** | **25** | **111 — breached by +86** | **28 — breached by +3** |
| `lib_footprint_issues` / `_mismatch` | 13 / 26 | 13 / 26 | 13 / 26 |
| `isolated_copper` | **absent (implicit 0)** | 0 | **2 — new class** |

Note the direction: on the *current* board the unfilled measurement
breaches `via_dangling` by 86 while the filled one breaches it by 3.
Nothing follows from this about which artifact is correct — the ceiling
describes a different board — but it should not be cited as an argument
for filling either.

A fill would additionally invalidate:

1. **`pad_connectivity_audit` and everything built on it** — hard parse
   failure on a KiCad-10 board (§2, §4.4). This is the largest single
   breakage and it is silent-adjacent: it raises, but only when called.
2. **Every content-hash provenance record** naming the board
   (`check_measurement_provenance.py`, `_lib/measurement_provenance.py`).
3. **`check_landed_board_shape.py`, `verify_regenerated_board.py`,
   `check_board_defect_corpus.py`** and the 83 scripts that read
   `pcb/temper.kicad_pcb` — any that assume the legacy dialect.
4. **R27** would require a `Ceiling-Approval:` raise for `creepage` and a
   brand-new `isolated_copper` entry, with ≥120 samples since categories
   are declared nondeterministic — and §4 shows the *board* is
   nondeterministic too, so a 120-sample band would be measuring fill
   jitter, not KiCad reporting jitter.

`check_ceiling_raise_evidence_corpus`, `ci_check_drc` and the `regression`
workflow were already red on `main` for board-state reasons (#1370) before
this work and were not touched.

---

## 7. Recommendation

**Adopt (c), amended and time-limited.** Keep the ceiling measured on the
committed, unfilled board — it is the only exactly-reproducible
measurement available (§4.3) and it matches the fabrication output (§5).

**Add `--refill-zones` as a reported safety probe, not as the ceiling.**
Publish both columns. The probe earns its place immediately: it is what
surfaced the 6.0 mm mains-to-SELV creepage (§3) and the 2 `isolated_copper`
findings.

**Do not fill and re-baseline.** It would ratchet a reinforced-barrier
violation into the accepted baseline, commit an artifact whose copper is a
coin flip, and break the connectivity toolchain.

Three board defects this measurement isolates, none of which is a
protocol change and all of which are owner decisions:

1. **Equal-priority overlapping zones** (`+170V_BUS` vs `hb-gnd` at
   priority 70 on B.Cu and In3.Cu). Fixing this is a precondition for any
   future fill being reproducible. Cheapest of the three.
2. **The `ac_n` pour outline violates the 12.6 mm reinforced barrier**
   against `+3V3`/`gnd` vias (6.0005 mm). Must be resolved before this
   board is fabricated by any workflow that fills.
3. **The nine pour-only nets have no copper in any artifact** — not on
   disk, not in the gerbers, and not after a fill (§2).

Only after (1) and (2) does the (a)-vs-(b) question become answerable on
its merits; today it is answered by the board's own defects.

---

## 8. Reproduction

```bash
git worktree add -b <branch> <path> origin/main
python3 scripts/generate_kicad_dru.py           # gitignored; creepage reads 0 without it
# scratch copies only -- never the committed board
python3 -c "from temper_placer.validation._drc_api import copy_kicad_project_sidecar; ..."
kicad-cli pcb drc --all-track-errors [--refill-zones [--save-board]] \
                  --format json --output r.json <scratch>.kicad_pcb
```

Key on `(description, x, y)`, never on `uuid` (§0). Read
`unconnected_items` separately — `_parse_drc_json` drops it.
