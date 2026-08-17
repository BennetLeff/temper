# Finishing agent — progress log (2026-08-17)

Starting point: main `aec4bf1f8`, board sha256
`bf2dbb3dcd48f9f1457306769e786d6fcbfa87287339f8a39473888ce80db1f5`
(unchanged throughout this session — verified after every commit).

Task: LOC cap gate refactor, hash-order gate NEW_SITEs in `_astar_nlayer.py`,
oracle-hash drift investigation, Core Tests failures — per
`docs/HANDOFF-2026-08-17.md` and PR #1304's triage.

## Fixed

1. **Hash-order gate — 4 NEW_SITEs in `_astar_nlayer.py`, GREEN.**
   `_family_halo_layers`'s four `for layer in <set>:` loops sorted
   (matching `a3c2e600d`'s established remedy for the other 2 of 6 sites).
   Surgical: only those 4 lines touched, per coordination (the file's
   clearance-halo logic itself is owned by the #1301 re-measurement
   agent). `scripts/check_hash_order_determinism.py`: 24 known sites, 0 new.

2. **LOC cap gate — 4 of 9 files fixed via genuine module splits, real
   seams, no line-count gaming:**
   - `cli/__init__.py` (1050 -> 821): extracted 7 post-solve
     audit-input/report-printing functions into `cli/_optimize_audit.py`.
   - `validation/results/battery_run.py` (1011 -> 896, allowlist entry
     removed): extracted the U10 pre-battery smoke test (already marked by
     its own section header) into `validation/results/_battery_smoke_test.py`.
   - `regression/drc_ratchet.py` (1236 -> 844, allowlist entry removed):
     extracted the 3 R27 ceiling-raise-governance methods
     (`find_ceiling_raises`/`validate_raise_evidence`/`detect_ceiling_raise`)
     into `regression/_ceiling_raise_evidence.py` — confirmed by inspection
     these touch no `DrcRatchet` instance state, the real seam between the
     class-shaped and pure-function-shaped halves of the file.
   - `placer/cp_sat/gates.py` (1285 -> 1101, baseline lowered 1210 -> 1101):
     extracted the two leaf, routed-board-only gates (`QualityGate`,
     `ErcGate`) into `placer/cp_sat/_quality_erc_gates.py`.

   Every split: re-exported at the old import path so every existing
   caller/test is unaffected (verified — no test files edited for any of
   these 4). Every split: ruff clean, vulture gate clean (baseline line
   numbers updated where cli/__init__.py's shrink shifted them),
   import-linter clean, `.hash-order-inventory` regenerated where a split
   moved an already-accepted site. Each split verified against its full
   test suite AND cross-checked by temporarily restoring the pre-split
   file and re-running the same tests, to separate "pre-existing failure"
   from "regression I introduced" — every failure encountered was
   reproduced identically pre- and post-split (see individual commits for
   per-file detail: missing `ngspice`/`kicad-footprints` binaries in this
   sandbox, a synthetic-fixture commit-SHA control unrelated to the split,
   stale CI-test-registration entries in an unrelated file).

3. **Oracle-hash drift — evidence assembled, NOT re-pinned (owner
   decision).** `docs/evidence/2026-08-17-oracle-hash-drift-evidence-and-repin-values.md`:
   - Confirmed PR #1304's diagnosis of `_via_validation_run_py_oracle.py`'s
     stale `_PINNED` dict entry with an exact byte-level trace (hashing the
     pre-fix parent commit's oracle blob reproduces the stale pinned value
     exactly), PLUS found that the two tests the "fixing" commit's message
     claims it added never actually landed anywhere in the tree.
   - Independently reproduced the determinism claim those missing tests
     would have proven — 14 fresh-interpreter runs across distinct
     `PYTHONHASHSEED` values, using a properly diversified 8-via fixture
     (unlike the existing 1-via pinned tests, which can't exercise a sort's
     ordering) — byte-identical in every run, both arms.
   - Found a second, previously undocumented drift:
     `_graph_py_oracle.py` (a forced one-line import fix from PR #1280's
     networkx removal, never re-pinned in `scripts/oracle_hashes.json`).
   - Both findings state the exact one-line diff a re-pin would assert.
     Neither applied — left honestly red, per the task's explicit
     oracle-re-pinning caution and PR #1304's own precedent of treating
     comparable evidence as an owner decision, not agent-executable.

## Left honestly red, with reasons

**LOC cap — 5 of 9 files remain, all in `router_v6`'s routing core:**
`_astar_nlayer.py` (explicitly owned by others — the coordination note
scopes my involvement in this file to the hash-order sites only, not a
LOC-cap refactor of its clearance-halo logic), `_pipeline_route.py`,
`_zone_pour_stitch.py`, `_adapter_convert.py`, `_ground_plane.py`. All five
are central to the live routing/zone-generation pipeline that a sibling
agent is actively regenerating the board's copper through, several carry
pinned oracles with content-hash registration
(`_adapter_convert_py_oracle.py`, `_adapter_convert_marshal_rust_differential.py`),
and `_zone_pour_stitch.py`/`_ground_plane.py` are directly in the
zone/ground-plane territory the coordination note reserves for other
agents. A safe split here needs either a quiet routing tree or hand-off
coordination neither of which this session had; attempting it blind risked
exactly the kind of collision the handoff's §12 warns about. Genuinely
unattempted, not attempted-and-abandoned.

**Core Tests.** Ran the full `packages/temper-placer/tests/placer/cp_sat/`
suite live (884 passed, 24 failed, 10 skipped) and the full `validation`/
`cli`/`regression` suites individually. Every failure found traces to one
of: a missing `ngspice` binary, a missing `kicad-footprints` package, or a
DRC/creepage/body-collision check against the real committed board's
current state (none of which this session's commits touch) — confirmed
pre-existing in every case checked, not new. Full enumeration and
per-failure root-causing beyond that classification was out of this
session's scope (LOC cap / hash-order / oracle-drift were the explicit
assignment); flagging here rather than claiming it's complete.
`packages/temper-placer/tests/validation/test_ci_test_file_registration.py`
has 2 failures (`test_no_new_uncovered_test_files`,
`test_no_stale_tracked_entries`) naming files this session didn't touch —
notably `router_v6/test_astar_nlayer.py` is now flagged as CI-covered when
its "known uncovered" registry entry says otherwise, which reads as #1303
(the PR that wired it into router_v6 group 3) leaving that registry
unreconciled. Not fixed here (out of assigned scope); flagged for whoever
owns that gate next.

## No real new bugs found this session (beyond what's in the oracle-hash
## evidence doc)

Nothing found while doing this work rose to the level of #1304's
`nbunch`-filter class of bug — the LOC-cap splits were pure moves with no
logic change, and the oracle-hash investigation's two findings are
registry-drift, not code-correctness, issues.
