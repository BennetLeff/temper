<!-- provenance: commit=a3fbaff37afd739b72f2b109847813b30ceb8e88 dirty=true -->

# Hyphen-boundary net-classification defect, Family C: `clearance_check.py`/`creepage_check.py`/`clearance_engine.py` + `temper-geometry` kernels + 3 inline copies

**Date:** 2026-08-13

Branch `fix/hyphen-boundary-clearance-creepage`, branched from
`origin/fix/board-schematic-resync` (base commit `a3fbaff37`, own worktree
`/home/bennet/Desktop/temper/.claude/worktrees/hyphen-clearance-fix`).
`make venv-isolate`; `scripts/check_stale_extensions.py` 10/10 fresh +
explicit `importlib.import_module` on all 10 extensions confirmed loadable,
before and after every measurement below (see §6). `make netlist` run fresh
in this worktree; `elec/build/default.net.source-digest`:
`8cfd715e60a3b8e22313562d8afed4ba48f54f096f73ef52d8f573bb378bea6a` (same
digest PR #1162/#1164 measured against).

This is **Family C** of the hyphen-boundary net-classification defect, per
PR #1162's own accounting:

> Family C — NOT fixed in [#1162], reported as blast radius:
> `clearance_check.py`/`creepage_check.py`/`clearance_engine.py` and their
> `temper-geometry` Rust kernels, plus 3 more non-delegating inline copies.

PR #1145 declares `hb-gnd`/`s1`/`I_SENSE`; PR #1162 fixes Family A
(`temper-io-types::placer_core::netclass`) and Family B
(`temper-design-bundle::design_rules::hv_word_boundary_match`); PR #1164
declares 7 more genuinely-HV `Default`-class nets; PR #1165 maps 4
protective-impedance mid-chain nodes to `HighVoltage`. None of those are
duplicated or reverted here.

## 1. Root cause

Identical shape to Families A and B: `(?:^|_)kw(?:$|[\d_])` (or the
byte-scan equivalent in Rust) anchors a word boundary on `_` and
start/end-of-string only. `-` was never a boundary character, anywhere in
Family C's history either:

```
is_high_voltage_net("hb_gnd")   -> False (no HV keyword matches "gnd")
is_ground-ish check n/a here -- Family C has no dedicated ground predicate,
only HV/Power/GND-flavoured net-class classifiers.

_is_hv_keyword_match("hb-gnd")  -> False  (before fix; no "-" boundary)
_classify_net_class("hb-gnd")   -> "SIGNAL"  (before fix)
_classify_net_class("hb-gnd")   -> "GND"     (after fix)
```

## 2. Full inventory

**The three named Python modules + their `temper-geometry` Rust kernels:**

| # | Python module | Function(s) | Rust kernel | Delegates? |
|---|---|---|---|---|
| 1 | `router_v6/clearance_check.py` | `_is_hv_keyword_match`, `_classify_net_class` | none — inline `re.search`, own keyword tables | No (pure Python) |
| 2 | `router_v6/creepage_check.py` | `_is_high_voltage_net` | `temper-geometry::creepage_check.rs::is_high_voltage_net`/`word_bounded`/`word_bounded_prefix` | Yes, fully |
| 3 | `router_v6/clearance_engine.py` | `_kw_boundary_match`, `_net_class_to_voltage_class` | `temper-geometry::via_clearance.rs::kw_boundary_match`/`word_bounded`/`voltage_number`/`net_class_to_voltage_class` | Yes, fully |

**The 3 inline copies PR #1162 counted** (confirmed present, all three
still using the unfixed `_`-only pattern before this branch):

4. `_constraint_types/config.py::PlacementConstraints.get_net_class` (lines
   450/461 in PR #1162's numbering) — GND/VSS/VCC/VDD and HV/BUS/DC_BUS
   keyword sets.
5. `io/_parse_board.py::_is_plane_required_net` (line 83) — GND/VCC/PWR
   plane-eligibility fallback.
6. `router_v6/constraints_design_rules.py::ClearanceMatrix.parse` (line
   445) — zone-name `"HV"` keyword check (operates on **zone names**, not
   net names).

**More than PR #1162 counted — found during this pass, reported, not
fixed:**

- **`temper-drc-rs::router_clearance.rs::classify_net_class`/`is_hv_gate`**
  (`HV_GATE_KEYWORDS`/`HV_CLASS_KEYWORDS`/`GND_KEYWORDS`/`POWER_KEYWORDS`,
  lines 207-258). This is the **actual production backend**
  `clearance_check.verify_clearance`'s default `backend="auto"` prefers
  whenever `temper_drc_rs` is importable (true in every environment this
  check ships to). **Not the same defect shape as this PR's fix**: it uses
  plain `str.contains()` substring matching throughout, not an anchored
  `(?:^|_)kw(?:$|[\d_])` regex — a different, *pre-2026-07-27* defect
  axis, out of scope for a hyphen-boundary fix. Reported here in full,
  with the coordinator's own three questions answered precisely rather
  than summarized, because "already tracked" turned out to need checking
  rather than trusting:

  - **Where it is known.** Exactly one place: this file's own comment,
    lines 260-281 — *"this Rust port... was never updated to match, so
    the fix was DEAD CODE in production: the differential test suite
    (`test_clearance_rust_differential.py`) never caught this because its
    own fixture net names... are all keyword-matched already and never
    exercise a manifest-only name"* — plus
    `docs/evidence/2026-07-27-clearance-copper-balance.md` Part B, which
    states the fallback plainly: *"Degrades to the substring heuristic
    alone (never raises) if the manifest cannot be found or parsed."*
    Neither passage calls out substring-vs-word-boundary as its own axis;
    both are about the *narrow 4-keyword gate* being incomplete, closed
    (for manifest-declared nets) by OR-ing in `hv_net_names`. The
    substring nature of the matching itself is visible in the code but
    not named as a defect anywhere I found.
  - **Whether anything enforces or tracks it.** No. Searched: this file's
    own `mod tests` has no unit test of `classify_net_class`/`is_hv_gate`
    exercising a substring-collision case; `gh issue list` /
    `gh pr list --state all` for "router_clearance", "classify_net_class",
    "temper-drc-rs substring" return nothing on point. It is recorded in
    one code comment and one evidence doc from 2026-07-27 and nothing
    re-verifies or re-flags it going forward — recorded, not owned,
    matching the pattern this session has repeatedly found elsewhere.
  - **What it affects in production, measured, not inferred.** Two
    concrete tests, run against this branch's own build (fresh, import-
    verified extensions), through `verify_clearance(..., backend=X)` for
    `X` in `{"python", "rust", "auto"}`:
    1. `hb-gnd` vs `+15V` (the PR #1145 headline pairing) — **required
       clearance is `0.127mm` (the un-escalated default) on all three
       backends, including production `"auto"`, even with this PR's own
       fix fully applied.** Neither `hb-gnd` nor `+15V` matches
       `HV_GATE_KEYWORDS`/`_CLASSIFY_HV_KEYWORDS`' narrow AC_/HV_/
       HIGH_VOLTAGE/MAINS gate, and `hb-gnd` is not yet manifest-declared
       on this base branch (that is PR #1145's own, separate, not-yet-
       merged change) — so this PR's classification fix (`hb-gnd` now
       correctly reads `GND`, not `SIGNAL`) does **not**, by itself,
       close the live routed-clearance gap for this exact pairing; PR
       #1145 landing is still required for that.
    2. `classify_net_class("safety-line")` genuinely returns `NetClass::Hv`
       in the Rust backend (verified by direct source read: `"LINE"` is
       in `HV_CLASS_KEYWORDS`, matched via bare `.contains()`) — a live,
       real misclassification, distinct from and predating this PR's
       hyphen-boundary defect (it is the plain-substring `"LINE"` bug
       already fixed on the Python side 2026-07-27, per this file's own
       comment "never updated to match" in Rust). Measured its actual
       consequence: paired against `AC_L` (a genuinely HV-gated net),
       `required_clearance` is `14.0mm` regardless of whether
       `safety-line` classifies as `HV`, `GND`, `POWER`, or `SIGNAL` —
       confirmed by calling `get_clearance("HV", class_b, voltage=230.0)`
       directly for all four `class_b` values, all four return `14.0`.
       Root cause, read from `router_clearance.rs::get_clearance`:
       `result = py_max_slice(&[iec_clr, iec_creep, voltage_class_clearance_mm(vc_a), voltage_class_creepage_mm(vc_a), voltage_class_clearance_mm(vc_b), voltage_class_creepage_mm(vc_b), ipc])`
       — the **maximum** across candidates from *both* sides plus the raw
       working-voltage table. A `class_b` misclassified toward `Hv` can
       only ever push this maximum **up or leave it unchanged, never
       down** (`is_hv_gate`, not `classify_net_class`, is what gates
       *whether* escalation happens at all, and `is_hv_gate("safety-line")`
       is `False` regardless of `classify_net_class`'s output — the
       narrow 4-keyword list `"LINE"` is not a member of). So this
       specific substring bug is a **phantom-over-strictness** risk
       (erodes trust in the gate exactly as this task's own framing
       warns, when it fires) — verified, not merely plausible-sounding,
       to be **not** a false-negative / under-protection risk the way the
       narrow-gate issue above is.

  **Net assessment**: recorded but unowned — a comment and an evidence
  doc, no test, no issue, no scheduled follow-up. Materially relevant to
  how much weight this PR's classification-layer fix carries on a
  `backend="auto"`/`"rust"` run (item 1 above shows a real, currently-live
  gap this PR does not close), but not fixed here — it is a different
  defect axis (substring vs. boundary-set) from this task's explicit
  hyphen-boundary scope, and fixing it is a separately-scoped effort
  (narrowing `is_hv_gate`'s keyword list is a false-negative risk to get
  right independently; word-bounding `classify_net_class` needs its own
  over-match audit, mirroring §4 below, against `temper-drc-rs`'s own
  fixture/differential corpus).
- **`temper-geometry::trace_width_assignment.rs::kw_boundary_match_impl`**
  (backs `router_v6/trace_width_assignment.py::_determine_trace_width`).
  Same `(?:^|_)kw(?:$|[\d_])` shape, same hyphen-blind-spot, confirmed by
  direct code read. **Not fixed here**: this function assigns trace
  *width*, not clearance/creepage — it does not decide whether a violation
  is reported, which is this task's explicit scope ("these are the checks
  that decide whether a clearance or creepage violation is reported at
  all"). A curiosity found in the process: `trace_width_assignment.rs` and
  `via_clearance.rs` **both** register a pyo3 function named
  `kw_boundary_match_py` into the same `temper_geometry` Python module;
  `via_clearance::register` runs after `trace_width_assignment::register`
  in `lib.rs`, so the later registration wins and
  `trace_width_assignment.py`'s own `_kw_boundary_match` wrapper (calling
  `_tg.kw_boundary_match_py`) is dead code, unreachable in practice —
  `_determine_trace_width` calls `_tg.determine_trace_width_py` directly,
  which uses its own private `kw_boundary_match_impl`, unaffected by the
  shadowing. Reported as a pre-existing naming collision, not caused by
  and not fixed by this change.

## 3. The fix

Mirrors PR #1162's approach exactly: `_` and `-` are now equivalent
boundary characters, on both the leading and trailing side, in every
matcher listed as "Fixed here" below.

**Fixed:**

- `router_v6/clearance_check.py`: `_is_hv_keyword_match`,
  `_classify_net_class` (GND/POWER branches too).
- `router_v6/creepage_check.py` / `temper-geometry::creepage_check.rs`:
  `is_high_voltage_net`, `word_bounded`, `word_bounded_prefix` — **both
  arms**, Rust kernel and pinned Python differential oracle
  (`tests/router_v6/test_creepage_check_rust_differential.py`'s
  `_oracle_is_high_voltage_net`) together, avoiding the PR #1136/#1137
  one-side-only regression.
- `_constraint_types/config.py::PlacementConstraints.get_net_class`.
- `io/_parse_board.py::_is_plane_required_net`, and its own independent
  live-tracking oracle in
  `tests/router_v6/test_u2_stackup_role_ssot.py::_expected_plane_required_net`.
- `router_v6/constraints_design_rules.py::ClearanceMatrix.parse`'s
  zone-name HV check.

**Deliberately NOT widened — `clearance_engine.py` / `via_clearance.rs`:**

`_kw_boundary_match`/`_net_class_to_voltage_class`
(`kw_boundary_match_py`/`net_class_to_voltage_class_py` in
`via_clearance.rs`) were **not** widened, unlike the other two named
modules. Two independent reasons, either one sufficient alone:

1. **Zero live exposure, verified by code search, not assumption.** This
   module's only production caller is `clearance_check._classify_net_class`
   (via `get_clearance(class_a, class_b, ...)`), which always passes one of
   the four fixed class labels `"HV"`/`"GND"`/`"POWER"`/`"SIGNAL"` —
   never a raw net name. Board-wide simulation of all 162 real net names
   (§5) confirms zero flips attributable to this module specifically: the
   3 real flips all originate in `_classify_net_class` upstream, before a
   net class ever reaches `clearance_engine.py`.
2. **A structural test-harness conflict that widening cannot avoid.**
   `tests/router_v6/test_via_clearance_tier2_rust_differential.py` pins
   `_oracle_kw_boundary_match`/`_oracle_net_class_to_voltage_class`
   **byte-verbatim against a frozen historical commit**
   (`_ORACLE_PIN_SHA = "f1ffc013"`, mechanically enforced by
   `test_oracle_is_verbatim_copy`, which `git show`s that commit and
   diffs it character-for-character against the oracle in the test file).
   This is the same category of frozen migration-fidelity pin as
   `_core_py_oracle.py` (Family A) and `_clearance_family_py_oracle.py`
   (this same Family C's own `clearance_check`/`creepage_check`
   orchestration bodies) — both of which PR #1162 and this fix leave
   untouched on purpose. Editing the oracle's source text to match a
   widened boundary breaks `test_oracle_is_verbatim_copy` outright (tried
   and reverted — see §7); *not* editing it and widening the Rust kernel
   anyway breaks `test_kw_boundary_match_oracle_parity`/
   `test_net_class_to_voltage_class_oracle_parity` for hyphen-adjacent
   fixtures already in this file's own corpus (e.g. `"ac-dc"`, added by a
   prior author specifically to pin the *old* boundary's SELV
   classification). There is no way to widen this one kernel without
   either breaking a byte-exact migration-fidelity guarantee or
   introducing exactly the one-side-only cross-arm regression PR
   #1136/#1137 already taught this repo to avoid.

Given (1) makes this a purely theoretical exposure and (2) makes fixing it
destructive to an existing, working, unrelated safety net, this module is
reported as **audited and intentionally left at `_`-only boundary**, the
same disposition PR #1162 gave the four *pin-name* pattern sets in Family A
(also audited, also intentionally not widened, also documented rather than
silently dropped).

## 4. The over-match found and mitigated: "LINE" vs 14 real SELV nets

Board-wide simulation of all 162 real net names against the widened
`_is_hv_keyword_match` (clearance_check.py) / `is_high_voltage_net`
(creepage_check.rs) boundary, **before any mitigation**, finds exactly one
over-match keyword: **`"LINE"`**, now matching any net whose name ends in a
hyphenated `-line` suffix (previously only `_line` matched). 14 real,
compiled nets on the production board are affected:

| Net | Source of SELV confirmation |
|---|---|
| `safety-line` | PR #1164 (SafetyInterlock fault-tree logic, power_3v3-bound) |
| `safety-line-1` .. `safety-line-3` | PR #1164, same |
| `safety-line-4` .. `safety-line-7` | PR #1164 §C (0 connected pads — no physical creepage risk either way) |
| `safety.ocp-line` | PR #1164 |
| `safety.ocp2-line` | PR #1164 (independently corroborates PR #1123's own conclusion) |
| `safety.ovp-line` | PR #1164 |
| `safety.thermal-line` | PR #1164 |
| `safety.coil_thermal-line` | PR #1164 |
| `safety.uvlo_logic-line` | `elec/domain_manifest.yaml`'s own declaration (explicit, pre-existing) |

This is the identical false-positive **shape** as PR #1162's `"COIL"`
finding for Family B (a keyword that legitimately needs word-boundary
matching, colliding with a real net's hyphen-delimited suffix) — not the
same keyword, not the same nets, but the same defect axis, found
independently by the same board-wide-simulation method this task's own
instructions require.

**Mitigation, mirroring PR #1162's own choice exactly**: not by narrowing
the boundary back down for `"LINE"` (would silently reintroduce the
hyphen-boundary defect for the next hyphenated LINE-adjacent net), but by
an explicit denylist checked before the keyword cascade:

- `creepage_check.rs::SELV_LINE_NET_OVERRIDES` (the kernel itself, not
  just its Python wrapper — see the constant's own doc comment for why:
  `temper-orchestration::clearance::run_creepage_check`, the actual
  production per-pair creepage decision, calls
  `temper_geometry.is_high_voltage_net_py` directly, bypassing
  `creepage_check.py`'s Python wrapper entirely, so a Python-only override
  would have been dead code for the real production path — the same
  "DEAD CODE in production" shape already documented for
  `temper-drc-rs`'s independent keyword matcher, see §2).
- `clearance_check.py::_SELV_LINE_NET_OVERRIDES` (checked inside
  `_is_hv_keyword_match`, so both of its call sites —
  `_get_required_clearance`'s direct call and `_classify_net_class`'s
  delegated call — get the correction).
- The differential oracle in
  `test_creepage_check_rust_differential.py::_oracle_is_high_voltage_net`
  re-pinned with the matching override (§3), keeping Rust and Python in
  lock-step per this task's own explicit instruction.

**Zero other over-match keywords found.** The `AC`/`HV`/`HIGH_VOLTAGE`/
`MAINS`/`NEUTRAL`/`PRIMARY`/`HOT`/`L1`/`L2`/`L3`/`PHASE`/`VBUS`/`B+`
keywords (clearance_check.py + creepage_check.rs) and the
`GND`/`VSS`/`PGND`/`CGND`/`AGND`/`VCC`/`VDD`/`POWER` keywords
(clearance_check.py, `_constraint_types/config.py`) and the `GND`/`VCC`/
`PWR` keywords (`_parse_board.py`) have **zero** flips against any of the
162 real net names other than the 3 intended ones (§5) — confirmed by
exhaustive simulation, not sampling.

## 5. Per-net classification changes, all 162 nets, all 5 board-simulable functions

Measured: `create_temper_design_rules()`-independent, direct calls to each
Family-C function against every one of the 162 net names in
`elec/build/default.net`, before vs. after this fix, both with the fresh
extension rebuilt and import-verified each time.

| Function | Home module | Flips |
|---|---|---|
| `_is_hv_keyword_match` | `clearance_check.py` | **0** (14 would-be LINE flips, all suppressed by the override) |
| `_classify_net_class` | `clearance_check.py` | **3**: `hb-gnd` SIGNAL→GND; `hb.gate_hs-vdd` SIGNAL→POWER; `hb.gate_ls-vdd` SIGNAL→POWER |
| `_is_high_voltage_net` | `creepage_check.py`/`.rs` | **0** (same 14 would-be LINE flips, suppressed by the Rust-side override) |
| `get_net_class` | `_constraint_types/config.py` | **3**: identical net/direction to `_classify_net_class` above (`Power`/`Power`/`Power` label spelling) |
| `_is_plane_required_net` | `io/_parse_board.py` | **1**: `hb-gnd` False→True |

**Total: 7 board-wide flips across all 5 functions, all 7 correct and
intended**, matching PR #1145's and PR #1162's own conclusions for the
identical net names in the sibling matcher families (`hb-gnd` is the
flagship intended fix; `hb.gate_hs-vdd`/`hb.gate_ls-vdd` are 0-pad phantom
nets per PR #1162's own finding, carrying zero copper and therefore zero
live creepage/clearance consequence today regardless of classification).
**Zero false positives reach the caller** — the 14-net LINE over-match is
fully absorbed by the two overrides before any classification result is
returned.

`router_v6/constraints_design_rules.py`'s zone-name `"HV"` check is not
board-net-simulable (it classifies **zone names**, not net names — no
zones are defined on this internal-Board code path today). Verified
instead by direct unit test
(`tests/router_v6/test_constraints_design_rules_zone_hv_boundary.py`):
hyphenated zone names now match, non-adjacent substrings still do not,
underscore-boundary is unaffected.

## 6. Verification

- `cargo test --manifest-path packages/temper-geometry/Cargo.toml --lib`:
  **8390/8390 pass** (creepage_check module: 788/788, including 2 new
  tests; via_clearance module untouched and still 419/419 from before this
  branch — no regression from leaving it unwidened).
- `cargo clippy --manifest-path packages/temper-geometry/Cargo.toml --lib -- -D warnings`: clean.
- `make venv-isolate` → `scripts/check_stale_extensions.py`: **PASSED,
  10/10 fresh**, both before this branch's edits and after every rebuild
  in this session. Explicit `importlib.import_module` on all 10 extensions
  succeeded every time this was checked (this session hit the
  `cargo check`/clippy-poisons-the-shared-target-dir trap AGENTS.md
  documents twice — `cargo clean -p temper-geometry` + rebuild recovered
  both times, confirmed by a real `Compiling temper-geometry` line
  reappearing).
- `scripts/check_venv_integrity.py` reports 18/18 "VIOLATION" — **investigated
  and confirmed to be a false positive of the checker itself**, not a real
  hijack: every flagged `.pth`/`direct_url.json` was read directly and
  each one correctly self-references this worktree
  (`.claude/worktrees/hyphen-clearance-fix/...`), not the main checkout or
  any other worktree. Root cause: this worktree is nested inside the main
  checkout's own directory tree (as every `.claude/worktrees/*` worktree
  is, by this repo's own convention), and the checker's per-worktree loop
  (`check_venv_integrity.py:280`) tests membership against *other*
  registered worktrees before testing membership against the *expected*
  repo root — since the main checkout is structurally an ancestor
  directory of this worktree's own path, every legitimately-self-referencing
  path also satisfies "is a subpath of the main checkout," and the
  `or _is_relative_to(candidate, wt)` branch fires first. Not fixed here
  (a pre-existing gate limitation, unrelated to this task's scope).
- Family-C-specific test files: `test_clearance_check.py` 20/20,
  `test_creepage_check.py` 47/47, `test_creepage_check_rust_differential.py`
  26/26, `test_via_clearance_tier2_rust_differential.py` 34/34 (untouched,
  confirms §3's "leave unwidened" decision doesn't regress anything),
  `test_config.py` (constraint_types) 35/35, `test_u2_stackup_role_ssot.py`
  9/9, `test_constraints_design_rules_zone_hv_boundary.py` (new) 3/3.
  **60 Rust-differential + 108 direct-unit tests, 0 failures.**
- `packages/temper-placer/tests/io/`: 1052 passed, 6 failed, 9 skipped, 1
  xfailed. **All 6 failures confirmed pre-existing and unrelated by
  code-path analysis**: this branch's diff touches zero files these
  failures' stack traces pass through
  (`netlist_contracts.rs`/`parse_engine.rs`/`kicad_parser.py`/
  `design_rules.py` — none in `git diff --stat`'s file list). Two are the
  `KICAD7_FOOTPRINT_DIR`-unset environment gap AGENTS.md already documents
  as a known, session-independent gap; one is an already-flagged stale
  `TEMPER_NET_ASSIGNMENTS["gnd"]`-vs-test-expectation drift (the test's own
  assertion message says so verbatim: "update this test's expected_class
  instead of leaving it pinned to the historical gap"); three are a
  `KeyError: 'ac_l'` from `result.netlist.get_net('ac_l')` against the
  on-disk `pcb/temper.kicad_pcb` — a pure key-lookup failure with no
  regex/boundary-matching code anywhere in its call stack.
- `packages/temper-placer/tests/router_v6/`: full-directory run, 3120+
  tests. One known-unrelated failure deselected
  (`test_identical_signal_nets_bundle` —
  `networkx.Graph has no attribute 'edges_with_data'`, an installed-version
  API mismatch unrelated to net classification, matching AGENTS.md's own
  documented `test_channel_skeleton_*`/`networkx` gap). Full run initiated;
  see the PR body for the completed count (this document was drafted while
  the ~15-minute full-directory run was still in flight, per this repo's
  own "do not background-and-wait" discipline — the targeted Family-C
  files above were run to completion first and are the ones this fix's
  correctness actually depends on).
- `scripts/check_net_classification.py`: **PASSED** (unaffected by
  design — audits bare substring `in` tests, not boundary-character
  correctness, exactly as PR #1162 found for the same gate).
- `scripts/check_creepage_clearance_drift.py`: reports a pre-existing
  `GATE ERROR` (a `tank_creepage.py` selection-alias issue, a file this
  branch's diff never touches) — confirmed unrelated, not caused by or
  fixed by this change.
- `git status --porcelain` / `git grep -l "^<<<<<<< "`: clean throughout.

## 7. What was tried and reverted

`via_clearance.rs`'s `word_bounded`/`kw_boundary_match`/`voltage_number`
were widened first, along with
`test_via_clearance_tier2_rust_differential.py`'s
`_oracle_kw_boundary_match`/`_oracle_net_class_to_voltage_class`, mirroring
the other two named modules exactly. This broke
`test_oracle_is_verbatim_copy` (the oracle is no longer byte-identical to
the pinned commit `f1ffc013`) — a mechanically-enforced contract, not a
style preference. Reverted (`git checkout --` on both files) once the
zero-live-exposure argument (§3) made the widening's safety benefit
provably nil; the revert was verified clean (`git diff --stat` on both
files shows no changes) and the extension was rebuilt and
freshness/import-reverified before continuing.

## 8. The honest delta — and what is still outstanding

**Classification-layer delta (measured, §5): 7 net reclassifications across
162 real nets, 0 false positives, 0 false negatives introduced.** This is
the complete, honest, board-wide answer to "what changes" for every
function this fix touches.

**Not measured in this pass: an actual routed-copper clearance/creepage
violation count via `verify_clearance`/`verify_creepage` against real
trace geometry.** Unlike Family A/B (a static net-name → class-label
table, measurable against `elec/domain_manifest.yaml` and pad positions
alone, the way PR #1145 measured `measure_cross_domain_creepage.py`'s
before/after), Family C's `verify_clearance`/`verify_creepage` operate on
`RoutingResults`/`CompiledRoute` — actual routed trace segments, which
this repo has no lightweight loader to construct from the already-routed
`pcb/temper.kicad_pcb` (2193 real trace segments confirmed present via a
direct `kiutils` read), and reconstructing one, or re-running the full
`route_board.py` pipeline (~250-400s, OOM-risky under concurrent agent
load per `AGENTS.md`), is disproportionate to this scoped classification
fix. **Flagged as an explicit, labelled gap, not silently inferred**: the
classification-layer finding (`hb-gnd` now correctly reads as `GND` rather
than `SIGNAL`, `hb.gate_hs-vdd`/`hb.gate_ls-vdd` now read as `POWER`) is
real and reported; whether any *currently-routed* copper on those specific
nets sits closer than the newly-applicable clearance/creepage minimum is
the natural, cheap-to-run follow-up once a `kicad_pcb`-trace-to-
`RoutingResults` loader exists (or the next full `route_board.py` run
happens for an unrelated reason and this check can ride along).

**`temper-drc-rs::router_clearance.rs`'s separate, pre-existing,
already-documented substring-matching defect (§2)** further limits how
much of this classification delta reaches a real `backend="auto"`/`"rust"`
DRC run today — reported, not fixed, per this task's explicit scope
(hyphen-*boundary*, not substring-vs-boundary, a different axis of the
same general "net classifier is unsound" problem family).
