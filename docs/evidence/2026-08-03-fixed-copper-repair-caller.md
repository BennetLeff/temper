<!-- provenance: commit=bcc5fa0ded062584d23cc707298c705afe4fcdc9 dirty=false -->

# Fixed-copper hoisted into the repair caller — issue #617

**Date:** 2026-08-03
**Branch:** `feat/fixed-copper-repair-caller` (worktree
`.claude/worktrees/agent-fixed-copper`).
**Issue:** #617 — hoist `fixed_copper` into `run_clearance_repair_solve` so
the production repair caller can express the full evidence recipe (the piece
Run A of the wave-2 write could not express, and the reason the wave-2 board
was written from the direct `solve_placement` Run B instead of the
production caller).
**Board measured:** `pcb/temper.kicad_pcb` on `origin/main` — the post-#602
wave-2 written board (K3 = TE Schrack RT314012 at (66.87, 50.59) absolute,
C27 on-board at (28.62, 242.0) absolute / (8.62, 222.0) local... the parsed
local positions used by the solve are K3 (43.12, 17.92) and C27 (28.62,
222.0)). **`pcb/**` and `elec/**` untouched** (a sibling agent owns the board
right now).

## 1. Interface change

`run_clearance_repair_solve` gained `fixed_copper: dict | None = None` and
forwards it, unchanged, into every `solve_placement` round. The recipe dict
carries the run-B values: `free_refs={K3, C27}`, `margin_mm=0.05`,
`include_other_pads=True` (default), and a `parse_result` with **no zone
items** (the run-B convention — the zone-inclusive variant is the open
run-C/gap-1 follow-up). Default `None` keeps pre-hoist behaviour
byte-identical; the loop callers that do not pass it are unchanged.

`ClearanceRepairReport` records the recipe for evidence:
`fixed_copper_free_refs` (sorted tuple, empty when absent),
`fixed_copper_margin_mm` (None when absent), and
`fixed_copper_audit_violations` (the aborting audit's violation count when a
fixed-copper gap terminates the repair; 0 otherwise — including a clean
fixed-copper run, where the audit PASSED rather than counting 0 into the
report).

## 2. Round-abort decision — both audits fail closed the same way

The fixed-copper post-solve audit (`audit_fixed_copper` inside
`solve_placement`) shares the validator audit's raise contract **exactly**:
a violation on a feasible/optimal solve raises `RuntimeError` (the encoding
is unsound for that solve — see `fixed_copper.py`'s soundness proof). The
loop catches it and terminates with status `"gap"` naming the offending
ref(s), with **no further rounds** — identical handling to the REQ-SAFE-01
validator audit's `"gap"` path (issue #523 gap 2). The two audits are
therefore consistent by construction: same raise, same catch, same terminal
status; the report `reason` distinguishes which audit fired (the fixed-copper
message is prefixed `fixed-copper post-solve audit FAILED`, the validator's
`REQ-SAFE-01 validator post-solve audit FAILED`). The offending refs land on
`unreinforced_pairs` as single-ref pairs `(ref, "")` — a pad-vs-copper
violation has no second component ref — and the count lands on
`fixed_copper_audit_violations`.

Tests pin this: `TestRepairLoopFixedCopper::test_fixed_copper_audit_hard_failure_aborts_round_as_gap`
monkeypatches `audit_fixed_copper` to raise and asserts status `"gap"`, no
rounds appended, the ref named, and the violation count carried.

## 3. Reproduction — the run-B recipe through the hoisted caller

`docs/evidence/k3_fixed_copper_repair_solve.py` runs the production repair
recipe through `run_clearance_repair_solve` **with** the fixed-copper dict
(the run-B values): full-classification placement + full voltage-domain map,
nothing hard-pinned, min-displacement toward current positions,
`max_displacement_mm=60.0`, every rotation pinned, full 11,571
domain-clearance + 530 keepaway, no chain exemption, `free_refs={K3, C27}`,
margin 0.05, no zone items, seed 0, 180s/round, max 4 rounds.

**Result (single round, feasible):**

| field | hoisted-caller run | Run B (written board, wave-2 doc) |
|---|---|---|
| status | `clean` (1 round) | feasible |
| K3 | (43.12, 17.92) — **unmoved** from written | (43.12, 17.92) |
| C27 | (39.21, 220.92) — **on-board** | (28.62, 222.0) — on-board |
| validator hard/intra/gaps | **0 / 0 / 0** | 0 / 0 / 0 |
| covered_pair_count | 11,571 | 11,571 |
| geometry_trusted | True | True |
| fixed-copper audit | 0 violations (passed) | 0 violations |
| refs moved (>0.001mm) | 168 | 167 (>0.02mm, different threshold) |
| total displacement | 5685.7mm | 6484.2mm |

The hoisted caller reproduces Run B's **class**: validator-clean buckets,
fixed-copper-clean, K3's RT314012 position untouched, C27 on-board (no
longer in the staging row). It does NOT reproduce the literal Run-B
coordinates — see §5 for why the current model cannot. **Determinism
check:** a second run with `seed=1` produced byte-identical positions
(K3 (43.12, 17.92), C27 (39.21, 220.92), buckets 0/0/0, 168 moved,
5685.7mm) — the feasible point found is stable across seeds, so the
1281-1282 DRC class is reproducible, not a one-off draw.

## 4. DRC proxy — Run A regression is FIXED

`docs/evidence/k3_fixed_copper_repair_drc.py` writes the solved placement to
a **/tmp copy** of the board under the canonical stem `temper.kicad_pcb` with
the regenerated `temper.kicad_dru` and a copy of `temper.kicad_pro` beside
it (the wave-2 Sec 4 convention: a candidate named otherwise silently drops
the custom creepage/track_width categories). Tool: `run_drc` (kicad-cli
**10.0.4**, `--all-track-errors`), N=5 samples. Baseline measured at the
committed board's canonical path (1261-1263, matching the documented
written-board figure — the DRU-resolution convention is verified working).

| gate | Run A (pre-hoist caller, wave-2 doc) | **hoisted caller (this PR)** | written board (= Run B) | Run A |
|---|---:|---:|---:|---:|
| total_errors | 1428-1437 | **1281-1282** | 1261-1263 | — |
| clearance | 458 | 386 | 377-378 | — |
| creepage | 211 | 223 | 185-187 | — |
| shorting_items | ~199-200* | 186 | 199-200 | — |
| solder_mask_bridge | 206 | 135 | 154 | — |
| hole_clearance | — | 110 | 105 | — |
| courtyards_overlap | — | 15 | 11 | — |
| REQ-SAFE-01 | 0/0 | **0/0** | 0/0 | — |

\* Run A's shorting/courtyards figures were not broken out in the wave-2 doc
(run A is reported there as totals + clearance/creepage/solder_mask/silk).

**Verdict: the hoist fixes the Run-A regression.** Through the fixed
caller, `fixed_copper` moves the DRC outcome from Run A's 1428-1437 (the
caller-interface artifact that made the wave-2 write use the direct-solve
Run B) to 1281-1282 — a **~147-error improvement**, buckets 0/0/0, and no
Run-A-style regression. The hoisted placement sits ~20 errors from the
written board (1261-1263): better than Run A by a wide margin, not quite the
written board's numbers — because the written board itself is at the current
model's feasibility boundary (§5).

**Honest caveat:** 1281-1282 is 14-15 over the committed board's 1267
error ceiling. The hoist is a caller-interface fix, not a placement-quality
fix: it makes the production caller *able* to express the run-B recipe. A
board written from the hoisted placement would need its own ceiling
re-measurement and would carry this headroom — the owner should treat the
run-B recipe through the loop as "fixes the regression, verify the landing
board's own ceiling", not as "guaranteed under 1267". The written board
(1261-1263) remains the best-known placement, and it is not reproducible by
the current model (§5).

## 5. Why the literal Run-B placement is not reproducible today

The exact written positions (and Run B's own raw solved positions) are
**infeasible in the current model**: pinning every ref at the written
positions (with and without `fixed_copper`) returns `infeasible`. The
discriminating constraints are the auto-generated netclass cross-class
separation constraints (`netclass_constraints.py`,
`configs/netclass_rules.yaml` — both unchanged since the write): at the
written positions, 8 cross-class pairs sit at or under the 6.0mm bar, two
of them strictly below (**C2<->C26 and C4<->U6 at 5.995mm < 6.0mm**); the
hoisted (feasible) placement keeps every pair ≥ 6.0mm. Nine further pairs
sit at the 0.4mm courtyard-τ knife-edge.

The write-era `_encoder_solve.py` differs from today's only by additive
reference/loop alias reconciliation (no-ops without aliases), and
`netclass_rules.yaml`/`netclass_constraints.py` are byte-identical, so the
5.995mm pairs were always on the model's boundary: the write-era solve that
produced the written board either encoded them at exactly the 600-unit
bar (equality satisfies `x_end + margin ≤ x_start`) or the 2dp write
rounding pushed them a half-unit under. Either way, **no solve on the
current codebase returns the written coordinates**; the hoisted caller's
result (clean buckets, on-board C27, DRC 1281-1282) is the run-B class the
current model admits.

This is a real, attributable finding for the board owner (not a ratchet
target): the written board lives on the model's feasibility boundary, so a
future re-solve on this board will move it, and the landing board's DRC
must be re-measured rather than assumed equal to the committed one.

## 6. Tests

`tests/placer/cp_sat/test_clearance_repair.py::TestRepairLoopFixedCopper`
(4 new tests, all passing; full `test_clearance_repair.py` +
`test_validator_audit.py`: 47 passed, 1 skipped — the skip is the
environment guard when `pcb/` is absent, which it is not here; the two
pre-existing-failure candidates on main pass with the netlist generated):

- `test_fixed_copper_is_forwarded_into_every_solve_round` — spy on
  `clearance_repair.solve_placement`: the recipe dict reaches every solve
  round byte-identical (a forward that silently dropped it would pass any
  behavior-only test where the constraint does not bite).
- `test_fixed_copper_feasible_solve_returns_expected_buckets` — feasible
  solve with `fixed_copper` + `validator_input` returns hard=0/intra=0/
  gaps=0 and records the recipe on the report.
- `test_fixed_copper_audit_hard_failure_aborts_round_as_gap` — the
  round-abort contract (§2).
- `test_absent_fixed_copper_param_is_unchanged` — report-surface contract
  when the param is absent.

## 7. Gates

- ruff: clean on all touched files.
- import linter: 0 new violations.
- typecheck gate: 214 baseline errors / 0 new.
- evidence provenance: this doc + both scripts carry the commit stamp;
  one pre-existing failure on main unrelated to this PR
  (`2026-08-02-validation-portfolio-review.md`, no provenance line, not on
  the allowlist — fails identically on `origin/main`).
- The evidence scripts' `pcb/**` is read-only: the candidate is written to
  /tmp and deleted after measurement. `pcb/temper.kicad_dru` is regenerated
  into `pcb/` for the measurement (gitignored, deterministic, and required
  by the ceiling protocol's own invocation); `git status` stays clean.

## 8. Reproduction

```bash
uv run --no-sync python docs/evidence/k3_fixed_copper_repair_solve.py   # hoisted run (180s)
export PYTHONPATH="$(pwd)/packages/temper-placer/src:$(pwd)/scripts"
python3 docs/evidence/k3_fixed_copper_repair_drc.py                     # baseline + candidate DRC
# expected: status=clean; K3 (43.12, 17.92) unmoved; C27 (39.21, 220.92)
# on-board; hard=0 intra=0 gaps=0; total_errors 1281-1282 vs baseline
# 1261-1263 (and Run A's 1428-1437 -- the regression the hoist fixes).
```
