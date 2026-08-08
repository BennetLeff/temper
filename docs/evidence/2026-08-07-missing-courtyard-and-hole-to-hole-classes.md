# Provenance: measured against the commit below; the tracked tree carried
# this investigation's own edits (this document's own change set) at
# measurement time.
provenance: commit=ce91fead7f2b527509c5d9b506e4168af22bf34a dirty=true

<!-- provenance: commit=ce91fead7f2b527509c5d9b506e4168af22bf34a dirty=true -->

# Board-defect corpus: hole-to-hole class closed, missing-courtyard class diagnosed and reported uncovered (STRATEGY.md build order step 4)

**Date:** 2026-08-07
**Scope:** `pcb/temper.kicad_pcb` read-only throughout -- every measurement below is taken on a
run-time *copy*, exactly as the existing `off-board`/`pad-short`/`creepage`/`clearance`/
`courtyard` classes do. `power_pcb_dataset/drc_ceiling.json` read-only and unchanged; no
`Ceiling-Approval:` trailer is authored by this work.

## 0. Context

`docs/STRATEGY.md`'s build order step 4 calls for reaching ~10 fault-injection defect classes with
**injector self-verification** (`METHODOLOGY.md` Sec. 5). Five classes existed
(`off-board`/`pad-short`/`creepage`/`clearance`/`courtyard`, the last two closed
2026-08-07 earlier the same day -- see `docs/evidence/2026-08-07-clearance-courtyard-corpus-coverage.md`).
This document adds two more, drawn from real DRC categories already measured on the committed board
(`hole_to_hole`, `hole_clearance`, `missing_courtyard` all appear in `docs/STRATEGY.md`'s "DRC —
committed board" table) and from `scripts/generate_kicad_dru.py`'s own emitted manufacturing rules
(`hole_to_hole` min 0.5mm).

**One of the two, `hole-to-hole`, is now SOUND.** The other, `missing-courtyard`, is a **deliberate,
reported exception**: its injector is independently self-verified, but its owning gate does not
fire, for two separately diagnosed reasons. Per `METHODOLOGY.md` Sec. 5 ("if a gate turns out not to
catch its own defect class, that is a finding -- report it, do not weaken the class"), this is
reported as a real coverage gap, not silently fixed or dropped.

## 1. Measurement environment

| | |
|---|---|
| kicad-cli | **10.0.5**, extracted from the `ppa:kicad/kicad-10.0-releases` `.deb` (no root available in this sandbox, matching the 2026-08-07 clearance/courtyard doc's environment note). |
| DRC invocation | `temper_placer.validation._drc_api.run_drc` (`kicad-cli pcb drc --all-track-errors --format json`, thread-pinned via `_single_threaded_kicad_env`), reached through `scripts/check_board_defect_corpus.py`'s own `measure_drc()` wrapper -- see Sec. 3 for a change made to that wrapper this pass. |
| Board under test | `pcb/temper.kicad_pcb`, sha256 `1cce4a0872051675b0339de3378ff7ec2c16bb4b035c999dfa408dec5ecbc3f6` (unchanged from the same-day clearance/courtyard measurement). |

## 2. `hole-to-hole`: a real manufacturing rule the corpus had no class for

**Owning gate:** `kicad-drc` (`hole_to_hole` category -- `scripts/generate_kicad_dru.py` emits `(rule
"PTH hole to hole" (constraint hole_to_hole (min 0.5mm)))`).

C24 (a THT 2-pin capacitor, pad 1 net `+170V_BUS`; originally at `(31.57, 88.86)` rot 0, >=10.9mm from
every other drilled hole on the board) is moved to `(95.28, 64.84)`, placing its pad 1 drill 1.8mm
center-to-center (0.20mm edge-to-edge) from the FIXED C2 (THT 2-pin capacitor, pad 1 also net
`+170V_BUS`; NOT moved, at `(93.48, 64.84)`) pad 1 drill -- below the 0.4995mm minimum kicad-cli
measures. The two pads share **one net deliberately**: `hole_to_hole` is a manufacturing/mechanical
constraint independent of electrical connectivity (two holes drilled too close together weaken the
board irrespective of what nets they carry), so pairing same-net pads lets their copper overlap
(legal -- same net) without also tripping `clearance`/`shorting_items`, isolating the hole-to-hole
signal exactly the way the `clearance`/`courtyard` classes isolate theirs.

Measured kicad-cli output on the mutated board, verbatim:

```
hole_to_hole :: Drilled hole too close to other hole (rule 'PTH hole to hole' min 0.4995 mm; actual 0.2000 mm)
    PTH pad 1 [+170V_BUS] of C24
    PTH pad 1 [+170V_BUS] of C2
```

No error names both C24 and C2 on the clean board.

### 2.1 First attempt failed silently -- and why: a `DrcWarning` bucket, not a kicad-cli gap

The first attempt, asserting via `errors_naming_two_pads` exactly like the `clearance` class,
reported **uncovered** even though the mutation and the underlying kicad-cli behavior were both
already correct (verified independently, Sec. 2.2). Root-caused by comparing raw kicad-cli JSON
output (which DOES contain the `hole_to_hole` violation, `"severity": "warning"`) against what
`check_board_defect_corpus.py`'s `measure_drc()` actually returned to the identity check (nothing):

`packages/temper-placer/src/temper_placer/validation/_drc_api.py`'s `_parse_drc_json` buckets every
violation by its own reported `severity` field into **two separate lists** on `DrcResult` --
`errors` (`severity != "warning"`) and `warnings` (`severity == "warning"`). `measure_drc()` returned
only `list(result.errors)`. `hole_to_hole`'s severity is `"warning"` under kicad-cli's own
compiled-in default (verified: it appears with that label in the JSON even with **no** project file
present at all, i.e. this is the rule's intrinsic classification, not something a project file
assigns), so every `hole_to_hole` violation was silently routed into `.warnings` and discarded before
any identity check ever saw it. This is the SAME `_drc_api.py`/`measure_drc()` combination `off-board`,
`pad-short`, `clearance`, and `courtyard` already measure through successfully -- it had simply never
been asked about a rule whose own default severity is `warning` before.

**Fix, scoped to the corpus's own measurement wrapper, not `_drc_api.py` itself:** `measure_drc()`
now returns `list(result.errors) + list(result.warnings)`. This is local to
`check_board_defect_corpus.py` -- `_drc_api.run_drc()` is unmodified, so `drc_ceiling.json`'s ratchet
(`ci_check_drc.py`/`DrcRatchet`) and every other consumer of `run_drc()` are unaffected.

`DrcWarning` (unlike `DrcError`) carries no raw per-item `items` text, only the already-deduped
`components`/`nets` lists (see its docstring in `_drc_api.py`). `errors_naming_two_pads` therefore
still returns nothing for a `DrcWarning` (its `getattr(error, "items", None) or []` degrades to `[]`).
`hole-to-hole`'s identity check was rewritten to a new helper,
`errors_of_type_naming_both_refs(errors, rule, ref_a, ref_b)` -- ref-level (like the existing
`errors_naming_both_refs` the `courtyard` class uses) but scoped to a specific rule, since the
mutation only targets one footprint pair and ref-level identity is unambiguous here (unlike
`pad-short`, which needs pad-number granularity to distinguish two pads of the SAME footprint).

### 2.2 Empirical safety check: does returning warnings change anything else?

Before committing the `measure_drc()` change, every existing class was re-run and the anti-vacuity
control re-checked, since `.warnings` also includes several categories previously invisible to the
corpus entirely (`silk_edge_clearance`, `silk_overlap`, `silk_over_copper`, `lib_footprint_issues`,
`track_dangling`, `via_dangling`, `hole_to_hole` -- all `warning`-severity under kicad-cli's compiled
defaults). None of `courtyards_overlap`/`copper_edge_clearance`/`shorting_items` (the anti-vacuity
control's three categories) are `warning`-severity without a project file, so their counts are
unaffected -- confirmed directly: anti-vacuity control still `PASS`, and all five previously-passing
classes (`off-board`/`pad-short`/`creepage`/`clearance`/`courtyard`) still report `PASS` with
identical messages, across three repeated full-corpus runs.

## 3. `missing-courtyard`: injector self-verified, gate does not fire -- reported, not weakened

**Attempted owning gate:** `kicad-drc` (`missing_courtyard` category).

R1 (THT resistor, `allowMissingCourtyard: False`; one `F.CrtYd` `FpRect` graphic item on the clean
board) has that item **deleted outright** -- not moved, not compressed -- via
`board_defect_mutator.mutate_missing_courtyard`. Fail-closed by construction: the function raises
`MutationError` if the named ref has zero `F.CrtYd`/`B.CrtYd` items to begin with (nothing to prove
by deleting nothing), verified against `F1` (a real footprint that already lacks courtyard graphics
on the committed board -- `TestMutateMissingCourtyard.test_ref_already_missing_courtyard_fails_closed`).

### 3.1 Injector self-verification (independent of the DRC gate)

`board_defect_mutator.courtyard_item_count(board_path, ref)` re-parses the WRITTEN file directly (not
the in-memory object the mutator just wrote) and counts `F.CrtYd`/`B.CrtYd` graphic items on `ref`.
Measured:

| | clean board | mutated board |
|---|---|---|
| `courtyard_item_count(..., "R1")` | **1** | **0** |

This is the "injected artifact differs, structurally, independent of the gate under test" half of
injector self-verification (`METHODOLOGY.md` Sec. 5) -- proven directly against the file bytes, not
inferred from whatever the DRC gate says next.

### 3.2 The DRC gate does not fire -- two independent, separately verified causes

Measured directly, isolating each variable:

| condition | `missing_courtyard` violations reported (R1's deleted courtyard) |
|---|---|
| no `.kicad_pro`, no `--severity-all` | **0** |
| no `.kicad_pro`, **with** `--severity-all` | **0** |
| **with** `.kicad_pro` (`pcb/temper.kicad_pro`, `missing_courtyard: "warning"`), no `--severity-all` | **0** |
| **with** `.kicad_pro`, **with** `--severity-all` | **6** (F1, L2, R1, R30, RT1, U27 -- R1 plus the 5 real pre-existing instances) |

Both are required simultaneously; neither alone is sufficient:

1. **kicad-cli's compiled-in default severity for `missing_courtyard` is `ignore`** when no project
   file accompanies the board -- the check does not run at all, regardless of `--severity-all`
   (which only filters what has already been computed). Every mutated board copy this corpus (and
   `run_drc()` generally) ever measures lives in a scratch workdir next to nothing but a regenerated
   `.kicad_dru` -- never a `.kicad_pro`.
2. **`run_drc()` never passes `--severity-warning`/`--severity-all`** to kicad-cli. Even with the
   real project file copied alongside (escalating `missing_courtyard` from `ignore` to `warning`,
   confirmed by row 3 vs row 1 above -- a project file alone changes nothing without the flag too),
   the JSON output still omits `missing_courtyard` entries unless `--severity-all` is *also* passed.

Neither fix was applied to `_drc_api.py`/`run_drc()`: that function is the canonical path for
`drc_ceiling.json`'s own ratchet and every other DRC-based gate in this repo, not just this corpus,
and passing `--severity-all` there would surface many new categories (silkscreen, `lib_footprint_issues`,
`track_dangling`, `via_dangling`, `hole_to_hole`, ...) across the whole DRC-ceiling contract --
a real, separate, much larger re-baselining task, out of this task's scope, and
`power_pcb_dataset/drc_ceiling.json` is explicitly not to be touched by this work.

(The `measure_drc()` change in Sec. 2.1 -- returning `.warnings` too -- does NOT fix this class: it
only surfaces violations kicad-cli already computed and put in the JSON. `missing_courtyard` is never
computed at all without a project file, so there is nothing in `.warnings` for it to find either.)

### 3.3 Verdict

```
[FAIL] missing-courtyard: missing-courtyard: UNCOVERED (expected, reported per METHODOLOGY.md
       Sec. 5) -- injector independently verified (R1: 1 courtyard item on clean board, 0 on
       mutated board, re-parsed directly), but no DRC error names missing_courtyard for R1 on
       the mutated board. Root cause: kicad-cli's compiled-in default for the missing_courtyard
       rule is 'ignore' without an accompanying .kicad_pro (which this corpus's mutated-board
       workdir never has), AND run_drc() never passes --severity-warning/--severity-all even
       when a project file is present -- either gap alone is sufficient to hide this class.
```

This is reported as `ok=False`, `gate_error=False` (a real coverage gap, not a broken measurement)
and is left in the corpus manifest rather than removed or special-cased to pass -- the corpus's own
exit code is honestly non-zero as a result (6/7 classes covered). Fixing it for real requires
deciding whether `run_drc()` should request warning-severity output repo-wide (and re-baselining
`drc_ceiling.json` against the resulting new categories), which is a maintainer call outside this
task's scope.

## 4. Full corpus run (7 classes, 6 covered)

```
board sha256: 1cce4a0872051675...
  matches manifest seed hash (corpus validated against this board)
anti-vacuity control (clean board at/below recorded ceilings):
  PASS

defect classes:
  [PASS] off-board
  [PASS] pad-short
  [PASS] creepage
  [PASS] clearance
  [PASS] courtyard
  [PASS] hole-to-hole: owning gate kicad-drc (hole_to_hole) fired: 1 DRC error(s) name both
         C24 and C2 on the mutated board and none on the clean board
  [FAIL] missing-courtyard: UNCOVERED (expected, reported per METHODOLOGY.md Sec. 5) -- see Sec. 3

Board-defect corpus: FAIL -- 6/7 classes covered, clean board green
```

Verified stable across three repeated full-corpus runs (identical verdicts and messages each time).

## 5. Not fixed here, deliberately

* `pcb/temper.kicad_pcb` is untouched; every mutation runs against a run-time copy.
* `power_pcb_dataset/drc_ceiling.json` is untouched, and no `Ceiling-Approval:` trailer is authored.
* `_drc_api.py`'s `run_drc()` invocation flags are unmodified -- the fix in Sec. 2.1 is local to
  `check_board_defect_corpus.py`'s own `measure_drc()` wrapper.
* `missing-courtyard`'s owning gate gap is diagnosed, not fixed -- see Sec. 3.3 for why a real fix is
  out of this task's scope.
* The `off-board`/`pad-short`/`creepage`/`clearance`/`courtyard` classes and their documented
  baselines are unchanged.
