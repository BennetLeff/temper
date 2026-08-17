<!-- provenance: commit=caec25d61 (main, HEAD at task start), worktree agent-a7148c963cf859481.
pcb/temper.kicad_pcb sha256 6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1
verified unchanged at task start, at every rebuild, and at task end (read-only
w.r.t. the board; no board writes attempted). -->

# `domain_clearance.py` / `netclass_constraints.py` Rust-port, stages 1-2 — DONE

Specification: `docs/evidence/2026-08-17-placer-constraint-rust-port-spike.md`
(PR #1319, read via `git show 1e21b6111:...` — not on `main` at task start).
Its findings were taken as verified per task instructions and independently
re-confirmed while executing (e.g. `test_requirement_matrix_values_pinned`
does not exist anywhere in the tree — grepped directly, zero hits, matching
the spike's own "UNVERIFIED, flagged rather than assumed" note).

Commits: `0201767f8` (stage 1), `511f91be8` (stage 2).

## Stage 1 — finish `domain_clearance.py`, single-source the safety matrix

**What ported / single-sourced.** The `IEC60335_REQUIREMENTS` matrix (6
rows) was hand-duplicated in two places: the Python dict in
`requirements/validators/clearance.py` and `temper-drc-rs`'s own
`MATRIX_ROWS` const. Both now read from ONE source:
`packages/temper-design-bundle/src/safety_value.rs`'s new
`requirement_matrix()` — a `SafetyValue`-typed table (`RequirementRow`
struct) reusing this same module's own recovered Table 17 (basic cell,
doubled per cl. 29.2.3 for reinforced rows) and Table 18 (functional row i)
cells for every **creepage** figure — real `RecoveredPrimary`/`Derived`
provenance, not re-derived, not invented. The **clearance** figures (3.0
basic / 6.0 reinforced / 0.5 functional) stay plain `f64`, not
`SafetyValue`, because they were already flagged UNSOURCED in the pre-port
comments (not a Table 16 value) — wrapping them in `SafetyValue::Derived`
or `RecoveredPrimary` would have manufactured a false provenance chain;
`design_value_mm` (an as-built target, never read by the validator) is
likewise plain `f64`. This was a deliberate design choice, not an
oversight — documented in the module comment and this doc.

**LOC.** `packages/temper-design-bundle/src/safety_value.rs`: +155 (the
`RequirementRow` struct, `requirement_matrix()`, 1 new unit test).
`packages/temper-drc-rs/src/req_safe_01.rs`: net −24 (the 30-line
hand-maintained `MATRIX_ROWS` const + its now-corrected-in-passing stale
doc comment replaced by a 16-line `matrix_rows()` flattener calling the
single source). `domain_clearance.py`: +18/−9 (docstring update only — the
function body was unchanged, since it already read `IEC60335_REQUIREMENTS`
indirectly). `requirements/validators/clearance.py`: net −32 → +10 (the
32-line hand-written dict literal replaced by an 11-line generator function
calling the Rust accessor at import time).

**Wiring proof (live, not by naming).** `req_safe_01_verify_iec60335` — the
CI-gate safety validator per `clearance.py:512`'s `verify_iec60335_compliance`
— calls `matrix_rows()`, which calls `temper_design_bundle::safety_value::
requirement_matrix()` directly (verified: `cargo build`, then
`.venv/bin/python -c "import temper_drc_rs as r;
print(r.req_safe_01_requirement_matrix())"` returns the 6 rows unchanged).
Production `IEC60335_REQUIREMENTS` (`validators/clearance.py`) is built at
import time by calling that same accessor — verified directly: importing
the module and printing the dict shows the same enum-tuple keys, same
insertion order, same values as before. Every existing consumer
(`domain_clearance.py::_matrix_rows()`, `real_board.py`, `drc_result.py`,
`router_v6/_clearance_family_py_oracle.py`'s live import) needed zero
changes.

**Discovered while porting, not fixed (flagged per hard rules).**
`req_safe_01.rs`'s `MATRIX_ROWS` doc comment (pre-port) described PD2
figures (4.0mm basic / 8.0mm reinforced, "currently-ENFORCED PD2... per the
owner's sealed-compartment decision") while the actual array held PD3
figures (6.3/12.6mm) — a documentation-only staleness (handoff §11/§12
pattern: a comment survives a value change). Values were never wrong; only
the prose was. Corrected in the same commit since I was already replacing
that block, but flagged here as its own finding: nobody would have caught
this by reading the code's *behavior* (both the old array and the new
`requirement_matrix()` return the same 6.3/12.6 values); only reading the
comment against the data caught it.

## Stage 2 — port `netclass_constraints.py`'s orchestration

Checked for the coordinating sibling agent (the task's coordination note
promised one editing this file's classifier) before starting: `git log
--all` shows zero commits touching `netclass_constraints.py` this session,
and the file's classification logic (`classify_net_type` call site,
`_NET_TYPE_TO_CLASS`, `_SEVERITY_RANK`) was unchanged from the spike's own
description. Proceeded per the task's explicit permission ("port the
corrected version" if landed first; port unchanged otherwise) and its
"do not fight them over the classification logic" instruction — the
classifier's keyword verdict is preserved byte-for-byte by this port,
confirmed by a differential (below) that would fail if it were not.

**What ported.** The O(n²) cross-class pairing loop, severity-rank
component-class resolution, and `class_pairs` override lookup — the ~110
genuinely-unported LOC the spike identified — into
`packages/temper-orchestration/src/netclass.rs` (new file, 270 LOC incl.
tests/comments; two `#[pyfunction]`s:
`netclass_separated_constraints_py` for the batch orchestration,
`netclass_resolve_component_class_py` so the pre-existing direct unit test
of `_resolve_component_net_class` and the batch path call the identical
Rust kernel and cannot silently diverge). Added `temper-io-types` as a new
unconditional, `default-features = false` dependency of
`temper-orchestration` (matches the existing `temper-geometry`/
`temper-data-model` unconditional-dependency pattern in that same
`Cargo.toml`) to reach `classify_net_type` directly rather than duplicating
its keyword logic — zero wasm32 impact verified (temper-io-types' `pyo3`
is optional, its own default is disabled here).

**What stayed Python, deliberately.** The opaque-object marshalling
(`comp.pins`/`pin.net` `getattr` access — `components`/`netlist` are
placer `Component`/`Net` objects, not plain dicts, matching
`domain_clearance.py`'s own "Python marshals, Rust computes" boundary) and
`_resolve_component_net_class`'s public name/signature (kept for
`tests/pcl/test_netclass_constraints.py`'s pre-existing direct unit tests,
which pass unmodified against the new thin wrapper).

**LOC.** `netclass.rs`: +270 (new file). `netclass_constraints.py`: net
−76 → +136 (the 110-line pairing/severity/override loop replaced by ~90
lines of marshalling + FFI call + an expanded docstring explaining the
2026-08-17 port). `lib.rs`/`Cargo.toml`: +16 (module declaration, 2
pyfunction registrations, 1 new dependency).

**Wiring proof (live, not by naming).** `_encoder_core.py:324-328` is the
production call site — `generate_netclass_separated_constraints` runs on
every CP-SAT full-board solve (unlike `domain_clearance.py`, which the
spike found unwired). Verified directly:
`.venv/bin/python -c "import temper_orchestration as to;
print(hasattr(to, 'netclass_separated_constraints_py'),
hasattr(to, 'netclass_resolve_component_class_py'))"` → both `True`;
`test_golden_board_pumpkin_real_board.py` (the real-board CP-SAT
integration test that imports and calls
`generate_netclass_separated_constraints` on the actual production board
data) passes unchanged.

## Oracles created (not re-pinned — zero existed for either file)

1. `packages/temper-placer/tests/requirements/clearance_oracle/
   _iec60335_requirements_py_oracle.py` (86 LOC) — verbatim pre-port
   `IEC60335_REQUIREMENTS` + its two enums. Differential:
   `test_iec60335_requirements_rust_differential.py` (118 LOC, 5 tests):
   row count, row-for-row bit-exact values (`float.hex()`), insertion
   order, production-dict parity, key-type parity.
2. `packages/temper-placer/tests/pcl/_netclass_constraints_py_oracle.py`
   (184 LOC) — verbatim pre-port `netclass_constraints.py`. Differential:
   `test_netclass_constraints_rust_differential.py` (271 LOC, 19 tests: 6
   classification-only, 13 orchestration scenarios covering every branch —
   cross-class pairing, same-class skip, `existing_constraints`
   suppression incl. the `AdjacentConstraint` non-suppression case,
   `touch_refs`, a real `class_pairs` override from the production YAML,
   multi-component pairing — plus 1 Hypothesis property test, 60 random
   examples over component/net-class combinations).

Both registered in `scripts/oracle_hashes.json` (169 total pinned oracles,
was 167 at task start — **only 2 new entries added; zero existing entries
touched or re-pinned**, verified via `git diff scripts/oracle_hashes.json`
showing exactly the 2 additive lines, one per commit).

## Test counts (measured, this session)

| Suite | Result |
|---|---|
| `cargo test` `temper-design-bundle` (`--lib`) | 52/52 |
| `cargo test` `temper-design-bundle` (`--doc`) | 1/1 |
| `cargo test --features python` `temper-drc-rs` (`--lib` + doctests) | 3435/3435 + 1/1 doctest |
| `cargo test` `temper-orchestration` (`--lib`) | 1168/1168 |
| `cargo test` `temper-orchestration` (`--doc`) | 1/1 (compile_fail) |
| `cargo clippy -D warnings` (both crates) | clean (0 new warnings; 5 pre-existing unrelated `net_class_validation.rs` dead-code warnings, not touched by this work, not introduced by it — confirmed via `git log`/`git status` on that file) |
| `pytest packages/temper-placer/tests/requirements/` | 881/881 (+25 pre-existing skips) |
| `pytest test_domain_clearance.py` | 20/20 (+5 pre-existing skips) |
| `pytest test_clearance_validator_rust_differential.py` | 16/16 |
| `pytest test_clearance_family_rust_differential.py` (router_v6) | 72/72 |
| `pytest test_iec60335_requirements_rust_differential.py` (new) | 5/5 |
| `pytest test_netclass_constraints.py` | 8/8 |
| `pytest test_netclass_constraints_rust_differential.py` (new) | 19/19 |
| `pytest test_golden_board_pumpkin_real_board.py` | 1/1 |
| `pytest test_e2e_netclass_ssot.py` | 4/5 (1 pre-existing, unrelated — see below) |
| `scripts/check_oracle_hashes.py` | 169/169 OK |
| `scripts/check_pyo3_duplicate_registration.py` | 0 duplicates, 692 registrations, 10 crates |

**Pre-existing, unrelated failures encountered (not fixed, not mine):**
- `test_e2e_netclass_ssot.py::test_class_pairs_contain_safety_critical_entries`
  — asserts `"IEC 60335-1" in class_pairs[("ACMains","Signal")]["because"]`;
  the actual string is `"UNSOURCED legacy 6.0mm (debunked... citation...)"`.
  This reads `configs/netclass_rules.yaml` directly (not
  `netclass_constraints.py`'s orchestration); `git diff` confirms that YAML
  file was never touched by either of my commits. A stale-citation-text
  assertion, the exact "running check pinned to a wrong number" pattern
  from handoff §11 — but not introduced or touched by this work.
- `test_heatsink_colocation.py::test_rejects_the_committed_board_placement`
  — asserts `{"U5": 3, "U6": 2}` rotations against the live-parsed board;
  actual is `{"U5": 2, "U6": 1}`. Reads `pcb/temper.kicad_pcb` directly via
  `kicad_parser`, imports nothing from any file this work touched. Board
  sha256 confirmed unchanged throughout.

## Safety matrix: now single-sourced?

**Yes, for stage 1's scope.** The 6-row `IEC60335_REQUIREMENTS`/
`MATRIX_ROWS` duplication the spike flagged (§1a) is collapsed: one array
of literal numbers (`safety_value.rs::requirement_matrix()`), two thin
consumers (`req_safe_01.rs::matrix_rows()` for the Rust validator,
`validators/clearance.py::_build_iec60335_requirements()` for every Python
consumer). Zero values changed — proven by the new differential, not
merely asserted.

**Not addressed (correctly out of scope, per the spike's own §1b/§1c):**
the three-classifier duplication (4-keyword `netclass_constraints.py` /
14-KiCad-NetClass router tables / 5-VoltageDomain `domain_clearance.py`)
remains three homes — the spike's own stage 3, explicitly gated on an
owner classification-scheme decision, not attempted here.

## Behavioural differences found

**None between pre-port Python and post-port Rust** — every differential
(the new matrix one, the new netclass one including a 60-example property
test, and the 6 pre-existing suites the ports run under) passed with zero
divergence. The one real finding was the stale PD2-vs-PD3 doc comment in
`req_safe_01.rs` (§Stage 1 above) — a documentation bug, not a behavioral
one; the underlying values were already correct on both sides before this
port touched anything.

## What "done" means — checklist

- Rust implementation + thin pyo3 binding: yes, both stages, wired and
  proven live by call-site tracing + direct `hasattr`/import checks, not
  by naming.
- Python that is now dead is deleted, not left as a shim: the 32-line
  `IEC60335_REQUIREMENTS` literal and the 110-line netclass pairing loop
  are both gone from their Python files, replaced by thin marshalling +
  FFI calls — not commented out, not `# TODO: remove`.
- Differential oracle created for each port: yes, 2 new oracles, 24 new
  tests total, zero existing oracles touched or re-pinned.
- Full test suites pass: yes, exact counts above; the 2 failures present
  are pre-existing, independently confirmed unrelated via `git diff`.
- Stage 2 was not deferred — the coordination risk named in the task
  (a sibling mid-edit on the same file) did not materialize (checked via
  `git log --all` before starting), so both stages landed.
