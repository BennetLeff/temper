# `lib_footprint_issues` 13 → 168: measurement artifact, not a board defect

**Status: COMPLETE.**

**Verdict up front: 168 is not a real count of anything. It is what
kicad-cli reports for `lib_footprint_issues` when it cannot resolve *any*
footprint library at all — every one of the board's 168 footprints gets
flagged, because none of them resolve. The real, current, honest count is
13, unchanged, live-reproduced three separate ways on today's board. No
ceiling change is needed. This was never a board regression.**

**Board sha256 for every live measurement in this document**:
`26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b`
(worktree `agent-a4c2b4fe898ec732f`, main `11a7e7c52`; re-verified
unchanged before writing this document; `pcb/temper.kicad_pcb` was never
modified by this task). `kicad-cli --version`: `10.0.5`.

---

## 1. What are the 168? A total resolution failure, not 168 real issues.

The board has exactly 168 footprints. Counted directly from the committed
file:

```
grep -oP '\(footprint "\K[^"]+' pcb/temper.kicad_pcb | sed 's/:.*//' | sort | uniq -c
```

| library nickname | count |
|---|---:|
| `Resistor_SMD` | 67 |
| `Capacitor_SMD` | 29 |
| `Package_TO_SOT_SMD` | 17 |
| `temper` (project-custom) | 9 |
| `Resistor_THT` | 9 |
| `Capacitor_THT` | 9 |
| `Package_SO` | 5 |
| `Diode_SMD` | 5 |
| `TestPoint` | 4 |
| `Package_TO_SOT_THT` | 4 |
| `lib` (project-custom) | 3 |
| `Inductor_SMD` | 2 |
| `Varistor`, `Fuse`, `Converter_ACDC`, `Connector_PinHeader_2.54mm`, `Connector_JST` (project-custom) | 1 each |

**Sum = 168, exactly.** That is the whole board. A real `lib_footprint_issues`
regression would flag some subset of footprints whose embedded geometry has
drifted from its library source; it would not plausibly hit 100% of every
footprint on a board that has been placed, routed, and DRC'd through 1300+
PRs with this category sitting at a stable 13 the entire time. A reading
that equals the board's total footprint count is the signature of a
resolution failure, not a defect census — confirmed below.

## 2. Root cause, isolated by direct reproduction (three controlled runs, same board, same kicad-cli)

`pcb/temper.kicad_pcb`'s footprint references resolve through
`pcb/fp-lib-table`, which maps library nicknames to paths. Two path forms
are in play:

- Standard libraries (`Resistor_SMD`, `Capacitor_SMD`, etc., 155 footprints)
  resolve via `${KICAD10_FOOTPRINT_DIR}/*.pretty` — and
  `KICAD10_FOOTPRINT_DIR` is **not an OS environment variable**. It is a
  KiCad-internal variable defined in `kicad_common.json`'s
  `environment.vars` block, which KiCad only reads from `KICAD_CONFIG_HOME`.
- Project-custom libraries (`temper`, `lib`, `Connector_JST`, 13 footprints)
  resolve via `${KIPRJMOD}/libs/*.pretty` — `KIPRJMOD` is the project
  directory itself, resolved natively, no config-home dependency — **but
  only if `pcb/fp-lib-table` and `pcb/libs/` are present in whatever
  directory kicad-cli is pointed at.**

So a DRC scratch harness has two independent ways to break footprint
resolution: omit the project's own `fp-lib-table`/`libs/`, or fail to seed
`KICAD_CONFIG_HOME` with a real `kicad_common.json`. I reproduced all three
combinations directly against the current committed board (scratch dirs
under `/tmp/claude-1000/.../scratchpad/lfi-repro/`, not committed):

| Case | Project `fp-lib-table` + `libs/` present? | `KICAD_CONFIG_HOME` seeded with real `kicad_common.json`? | `lib_footprint_issues` |
|---|---|---|---:|
| 1 | No | No (fresh empty dir) | **168** |
| 2 | Yes | No (fresh empty dir) | **165** |
| 3 | Yes | Yes (copied from `~/.config/kicad/10.0/`) | **13** |

Case 1 reproduces the reported regression **exactly**. Case 3 reproduces
the stored ceiling **exactly** (and also reproduces the historical
`lib_footprint_mismatch` figure of 26 exactly — that category doesn't even
appear in cases 1/2, because a footprint that fails to resolve at all is
reported as an "issue," not a "mismatch"; those two categories are mutually
exclusive per footprint). Case 2 corroborates the *other* number already on
record: `docs/evidence/2026-08-17-drc-ceiling-methodology-gaps-silk-overlap-and-sampling.md`
§2.2's side-finding reports an ad-hoc sweep (via
`scripts/measure_uncapped_drc.py`'s `_single_thread_env`, which *does* copy
`fp-lib-table`/`libs/` through `make_scratch_board` but only points
`KICAD_CONFIG_HOME` at a bare `mkdir`'d directory) reading **165** —
matching Case 2 to the integer.

**This nails the mechanism with no gap left to guess at**: `lib_footprint_issues`
is exquisitely sensitive to whether the DRC scratch harness fully mirrors
`temper_placer.validation._drc_api._single_threaded_kicad_env` — which
copies the *real* `KICAD_CONFIG_HOME`'s top-level files (library tables,
`kicad_common.json`) into the scratch config directory before pinning
threads — versus a hand-rolled scratch setup that stops at "point
`KICAD_CONFIG_HOME` somewhere empty."

## 3. Tracing it to the specific document that produced 168

`docs/evidence/2026-08-17-drc-ceiling-rebaseline-measurement-and-declined-approval.md`
§Method states its own protocol plainly: *"Scratch copy ... with
`temper.kicad_pcb` + `temper.kicad_pro` copied from `pcb/` and
`temper.kicad_dru` freshly regenerated ... `KICAD_CONFIG_HOME` pointed at a
scratch KiCad config carrying `MaximumThreads=1` (mirrors
`_drc_api._single_threaded_kicad_env`)."* It names `.kicad_pcb` and
`.kicad_pro` explicitly and never mentions `fp-lib-table` or `libs/`. The
parenthetical "mirrors `_drc_api._single_threaded_kicad_env`" describes only
the thread-pin behavior it copied, not the library-table seeding that
function *also* does (copying the real `KICAD_CONFIG_HOME`'s top-level
files) — that half of the real function was not reproduced. That gap is
exactly Case 1 above, and Case 1 reproduces 168 to the integer. No bisection
against board history is needed: this was never a board state, so there is
no board commit to bisect against. It is a property of one measurement
run's own scratch-directory construction.

**This has nothing to do with #1134 (board resync), #1201 (ZCD orphan
removal), or #1178 (6-layer stackup).** None of those PRs touch
`fp-lib-table`, `pcb/libs/`, or any DRC scratch-harness code. The board's
own `lib_footprint_issues` count has been 13 continuously; it is confirmed
live, again, on today's post-#1330+ board in this document (Case 3), matching
the stored ceiling to the integer with zero drift.

## 4. Is it the same root cause as the `test_regression_drc.py` /
   `loop_commutation_loop` / `sep_HV_ZONE_MCU_ZONE` drift? No.

Checked directly: `loop_commutation_loop` and `sep_HV_ZONE_MCU_ZONE` are PCL
placement-constraint identifiers, found in
`packages/temper-placer/tests/pcl/test_constraints.py` (line 216,
`constraint.id == "sep_HV_ZONE_MCU_ZONE"`) and
`packages/temper-placer/src/temper_placer/pcl/unsat_compiler.py`. That is
the placement-constraint compiler resolving zone/net-group references
against the current netlist — a completely different subsystem from DRC
footprint-library-table resolution. `test_regression_drc.py` itself (the
file whose name suggested a connection) treats `lib_footprint_issues` and
`lib_footprint_mismatch` together as `PLACEMENT_IRREDUCIBLE_TYPES` (line
270) — i.e. it already expects these two DRC categories to move together
as one library-drift signal, consistent with §2's finding that they're
mutually exclusive per-footprint outcomes of the same resolution step — but
nothing in that file or in `unsat_compiler.py` touches `fp-lib-table`,
`KICAD_CONFIG_HOME`, or any DRC-runner scratch-directory construction. The
two are unrelated; they only share the word "unresolved."

## 5. Bidirectional corruption — flag for whoever reviews the re-baseline table

The same artifact corrupted the rebaseline doc's table in **both**
directions on these two categories, and both errors point the wrong way for
a ceiling:

- `lib_footprint_issues`: **13 → 168**, a spurious *loosen* (would have
  hidden 155 real future defects worth of headroom under a wrong ceiling).
- `lib_footprint_mismatch`: **26 → 0**, a spurious *tighten* (§2: a totally
  unresolved footprint can't register as "mismatched" against a library it
  never found, so this category silently vanishes under the same broken
  protocol) — a tighten to 0 that would have false-positive-failed every
  future correct measurement of the real value, 26.

Neither number from that table should be used for these two categories.
The real, current values (both reproduced live in this document, Case 3):
**`lib_footprint_issues` = 13, `lib_footprint_mismatch` = 26** — both
identical to the stored ceiling.

## 6. Recommendation

**Not a defect. Not a regression. No ceiling change.** The stored ceiling
of 13 for `lib_footprint_issues` (and 26 for `lib_footprint_mismatch`) is
already the honest, current, measured state of the board — confirmed live
on today's board in this document, and independently confirmed by
`docs/evidence/2026-08-17-drc-ceiling-methodology-gaps-silk-overlap-and-sampling.md`'s
125-sample campaign using the real `_drc_api.run_drc()` protocol (spread 0
at N=125). There is nothing to fix on the board and nothing to fix in any
footprint or library file.

The one thing worth fixing is procedural, and it is not this agent's board
territory to fix: any future ad-hoc DRC scratch harness (as distinct from
the real, already-correct `_drc_api._single_threaded_kicad_env` /
`scripts/measure_uncapped_drc.py`'s `make_scratch_board`, which — per Case
2 above — is *closer* to correct but still not identical to the production
path) needs to either (a) call the real `_drc_api` helpers directly instead
of hand-rolling a scratch config, or (b) explicitly copy `pcb/fp-lib-table`,
`pcb/libs/`, **and** seed `KICAD_CONFIG_HOME` from the real
`~/.config/kicad/<version>/kicad_common.json` before trusting any
`lib_footprint_issues` or `lib_footprint_mismatch` reading. This document
and its live reproduction are the artifact-vs-defect determination the R27
re-baseline needed for this category; the re-baseline itself remains an
owner act.

## Method / reproducibility notes

Three `kicad-cli pcb drc --all-track-errors --format json` runs, single
invocation each (no sampling needed — `lib_footprint_issues` has no known
nondeterminism mechanism per the methodology-gaps doc's own N=125 campaign,
and this document's purpose is isolating a binary environment-configuration
variable, not re-measuring spread). Scratch board copies and scratch
`KICAD_CONFIG_HOME` directories under
`/tmp/claude-1000/-home-bennet-Desktop-temper/8d670d58-2e7c-42ad-b59f-ca4e3fccd905/scratchpad/lfi-repro/`
(not committed, will be cleaned up after this task). `pcb/temper.kicad_pcb`
was copied byte-for-byte into each scratch dir and never modified; sha256
re-verified unchanged (`26981fea2d...`) both before and after this task.
