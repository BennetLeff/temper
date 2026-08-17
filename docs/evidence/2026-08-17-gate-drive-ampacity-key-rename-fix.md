# Gate-drive ampacity key rename fix — 2026-08-17

provenance: commit=8157b4344 (main HEAD at task start) dirty=false

Board sha256 throughout this task (verified before and after every step,
`pcb/temper.kicad_pcb` never modified): `6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1`.

This document extends `docs/evidence/2026-08-17-fact-registry-drift-gate-extension.md`
(PR #1320, merged), which registered but deliberately did not fix the defect
described there in its §3.3: `StackupGate._DEFAULT_NET_CURRENTS`
(`packages/temper-placer/src/temper_placer/placer/cp_sat/gates.py`) and
`temper_drc_rs::ipc::net_currents()` (`packages/temper-drc-rs/src/ipc.rs:121-122`)
both key on `"GATE_H"`/`"GATE_L"`, net names that do not exist on this board
(the real nets are `GATE_HS`/`GATE_LS`, verified against `pcb/temper.kicad_pcb`'s
own net table).

## 1. Verifying the defect — by tracing the lookup, not reading the table

Executed (not just read) both pre-fix algorithms against the real pre-fix
tables (commit `d5882072d`, HEAD before this task):

```
GATE_HS: python exact-match=0.1A  rust substring-match=2.0A  StackupGate._resolve_net_current final=0.1A
GATE_LS: python exact-match=0.1A  rust substring-match=2.0A  StackupGate._resolve_net_current final=0.1A
```

Confirmed: `StackupGate._resolve_net_current("GATE_HS")` returned **0.1A**
pre-fix. Mechanism (both sides executed, not inferred): Python's
`_DEFAULT_NET_CURRENTS.get("GATE_HS", 0.1)` exact-match misses (only
`"GATE_H"` was a key); Rust's `get_net_current` case-insensitive
**substring** match *does* find `"GATE_HS".contains("GATE_H")` and returns
2.0A; `_resolve_net_current`'s own documented dispatch rule ("keep the
Python exact-match as authority when it disagrees with Rust") then throws
away the correct Rust answer and returns the wrong Python one, 0.1A.

**But this 0.1A only affects `StackupGate`'s DRC-gate CHECK — not what
sized any copper.** Traced separately, and this is the part PR #1320 could
not verify (no pyo3 build in that worktree) and got right to flag as an
open question: the production **trace-width-assignment** path
(`router_v6/trace_width_assignment.py`'s `_resolve_current_a`) calls
`temper_drc_rs.get_net_current` **directly** (not through
`StackupGate`'s Python table or its dispatch rule at all). For a real net
named `"GATE_HS"`, that direct Rust substring match against the stale
`"GATE_H"` key **already returned 2.0A**, before this fix, purely because
`"GATE_H"` is a literal prefix of `"GATE_HS"`. Verified against the real
built module (`make venv-isolate` in this worktree, `CONDA_PREFIX` unset
per the maturin conflict it otherwise reports):

```
GATE_HS rust= 2.0 gate._resolve_net_current= 2.0   (post-fix)
GATE_LS rust= 2.0 gate._resolve_net_current= 2.0   (post-fix)
```

And confirmed `StackupGate` itself is dark by default: it is registered
only inside `_loop_core.py`'s `if all_gates:` branch (`gates =
[DrcGate(), RoutingGate(), StackupGate(), PhysicsGate(), QualityGate()]`),
never in the default `[DrcGate(), RoutingGate()]` list, and `grep -rn
"all_gates" scripts/ .github/` finds zero CI call sites — the exact same
"dark unless `--all-gates`" shape PR #1322 independently found for
`IECCreepageGate`.

**Net effect of the pre-fix bug, precisely stated**: a verification-only
DRC gate (itself not on the default CI path) silently required only
~0.004mm of copper for `GATE_HS`/`GATE_LS` instead of the correct 0.258mm
(2.0A, 2oz outer, 20°C — see §2). It could not have widened a trace (no
gate ever writes geometry), and it did not narrow one either, because the
thing that actually assigns gate-drive trace width never consulted this
broken path. What it *did* do: silently pass a genuinely undersized
2A gate-drive trace as `CLEAN`, if one ever existed. See §3 for a live
demonstration of exactly that false negative, closed by this fix.

## 2. The fix (both languages, kept in lockstep)

`packages/temper-placer/src/temper_placer/placer/cp_sat/gates.py`,
`StackupGate._DEFAULT_NET_CURRENTS`:

```python
-        "GATE_H": 2.0,
-        "GATE_L": 2.0,
+        "GATE_HS": 2.0,
+        "GATE_LS": 2.0,
```

`packages/temper-drc-rs/src/ipc.rs`, `net_currents()`:

```rust
-        map.insert("GATE_H".into(), 2.0);
-        map.insert("GATE_L".into(), 2.0);
+        map.insert("GATE_HS".into(), 2.0);
+        map.insert("GATE_LS".into(), 2.0);
```

The 2.0A rating itself is unchanged — only the keys now match the board's
real net names. No clearance/creepage/copper-weight/DRU threshold touched.

**Downstream tests updated to match** (the behavioral change is real, even
though it's confined to the DRC-gate check — see §3):

- `tests/placer/cp_sat/test_net_currents_rust_differential.py` — the
  parametrized-over-`sorted(TABLE)` tests need no change (dynamic), but the
  hardcoded case-variant divergence example `"Gate_H"` no longer diverges
  (post-rename, neither side matches it) so was replaced with
  `"gate_hs"`; `test_gate_behavior_unchanged_from_pre_wiring`'s
  `"GATE_L"` assertion was moved to `"GATE_LS"`; a new
  `test_gate_current_rename_fix_2026_08_17` pins the full before/after
  shape (real nets now resolve to 2.0A; the old bogus literals correctly
  fall to the 0.1A default, since they were never real board nets and
  were never entitled to the citation).
- `tests/core/test_ipc2152.py` — `test_known_nets`/`test_case_insensitive`
  moved from `"GATE_H"`/`"Gate_H"` to `"GATE_HS"`/`"gate_hs"` (table-lookup
  assertions only; the two tests that pass current explicitly as an
  argument, e.g. `ipc2152_min_width("GATE_H", 2.0, ...)`, are unaffected
  since that function's net-name parameter is unused — verified by reading
  `ipc2152.py:50`, `_net_name` is prefixed `_`).
- `tests/placer/cp_sat/test_stackup_gate.py` — 5 fixtures relied on
  `"GATE_H"` resolving to 2.0A to exercise "a 2A gate-drive net" (comments
  said so explicitly: `"2A external, 1 oz: IPC-2221B minimum is
  0.786mm"`). Renamed to `"GATE_HS"`. One of these,
  `test_copper_weight_stackup_missing_uses_role_aware_fallback`, would have
  **silently gone vacuous** without the rename: it asserts `VIOLATIONS` for
  a 0.5mm/In3.Cu trace specifically because 0.5mm is undersized *for 2A*
  internal — at the old key's post-rename fallback (0.1A default), 0.5mm
  is nowhere close to undersized and the assertion would have started
  failing (confirmed: this test was one of two real failures caught by
  running the real differential/property suite before it was fixed).

All fixed, all green:

```
$ .venv/bin/python -m pytest tests/placer/cp_sat/test_net_currents_rust_differential.py \
    tests/placer/cp_sat/test_stackup_gate.py tests/core/test_ipc2152.py \
    tests/router_v6/test_trace_width_assignment.py -q
86 + 21 passed

$ cargo test --manifest-path packages/temper-drc-rs/Cargo.toml --no-default-features ipc::
22 passed; 0 failed
```

`scripts/check_fact_registry_drift.py`'s `gate_hs_net_current_rating_a`/
`gate_ls_net_current_rating_a` facts move from **TOOL ERROR** (missing
citation) to **CLEAN** at both homes:

```
Before: EXIT 5 (TOOL ERROR priority)
After:  EXIT 3 (VIOLATION — from the 4 pre-existing, unrelated,
        already-documented reds: mains_voltage_v, pollution_degree,
        default_via_diameter_mm's Rust site, hv_lv_separation_gate_
        threshold_mm — none touched by this fix, all still red exactly
        as PR #1320 left them)
```

This closes the registry's TOOL ERROR window entirely — the gate is now a
genuine two-sided check for this fact family (a future rename miss will
show as a red `DIFF`/site failure, not silently pass and not error out).
`scripts/tests/test_check_fact_registry_drift.py`'s
`test_gate_exits_tool_error_on_the_real_repo` (renamed back to
`test_gate_exits_violation_on_the_real_repo`) and
`test_gate_net_current_citations_are_known_tool_errors` (renamed to
`..._agree_regression_guard`) updated to pin the fixed state, following
the exact "regression guard, not merely absent from a known_red list"
pattern `test_gate_drive_net_names_agree_regression_guard` already used
for PR #1310's earlier `_GATE_NETS` fix. All 25 registry tests pass.

## 3. Trace widths before/after, and the tradeoff

**Trace widths (assignment path, i.e. what actually sizes copper on a
fresh route): unchanged, exactly 2.0A → same physics width, before and
after.** `_resolve_current_a` calls `temper_drc_rs.get_net_current`
directly; that already returned 2.0A pre-fix (substring match on the
stale `"GATE_H"` key, which happens to be a literal prefix of
`"GATE_HS"`) and returns 2.0A post-fix (now an exact match). Zero
numeric difference. `test_layer_aware_internal_widens_power_and_hv` (an
existing test using the literal `"GATE_H"` on an internal layer) still
passes post-fix, because it went from the "specific citation" branch to
the "GATE"-keyword back-derivation branch (`_implied_legacy_current_a`) —
a different current internally (~2.25A vs 2.0A, since `"GATE_H"` is not a
real net either way) but the test's actual assertion (`> 0.508*0.6`, i.e.
"internal needs more copper than the flat external legacy constant") is
satisfied by either path, confirmed by running it.

**Trace widths (the committed board's real GATE_HS/GATE_LS copper):**
unaffected, because `pcb/temper.kicad_pcb` is not modified by this task.
Measured directly from the board file: both nets are uniformly **0.4mm**
on **B.Cu** (outer layer) — 81 segments for `GATE_HS` (net 7), 132 for
`GATE_LS` (net 8), zero width variance within each net.

**IPC-2221B minimum width for GATE_HS/GATE_LS, before vs after** (2oz
outer copper, 20°C, this project's own `TRACE_TEMP_RISE_C`, computed with
the real `_min_width_ipc2152`):

| | Before (resolved 0.1A default) | After (resolved 2.0A citation) |
|---|---|---|
| Outer (2oz), e.g. `GATE_HS`/`GATE_LS` on B.Cu | 0.0040mm | **0.2580mm** |
| Inner (1oz), hypothetical | 0.0220mm | 1.3430mm |

The committed board's actual 0.4mm trace clears **both** thresholds with
margin — `StackupGate.check()` on the real routed widths is `CLEAN` before
and after (verified: constructing the real `BoardState`/`_FakeRoute` shape
with `width_mm=0.4, layer="B.Cu"` for both nets → `GateStatus.CLEAN, ()`
post-fix; pre-fix the even-more-permissive 0.1A threshold was trivially
also `CLEAN`). **No regression, no new violation, on the current board.**

**The false negative this fix closes** (demonstrated live, not
hypothesized): a genuinely undersized 2A gate-drive trace —
`width_mm=0.15` (well under the correct 0.258mm minimum, well over the
broken 0.004mm one) — is `CLEAN` under the pre-fix table and
`VIOLATIONS` (`"Net GATE_HS trace width 0.150mm is below IPC-2221B
minimum 0.258mm for 2.0A"`) under the post-fix one. That gap is closed.
It was never exercised on the real board (0.4mm ≫ 0.15mm), but it was a
live false-negative risk in the gate's own logic that a future
narrower-routed gate-drive net would have silently passed.

## 4. Full DRC before/after — full project context

**Byte-identical, by construction, and this is expected, not a
measurement failure.** `pcb/temper.kicad_pcb` is not modified by this
task (hard rule), `scripts/generate_kicad_dru.py` does not reference
`net_currents()`/`_DEFAULT_NET_CURRENTS` at all (grepped, zero hits), and
`kicad-cli`'s DRC engine has no knowledge of this repo's custom
Python/Rust ampacity tables — it is a static geometry checker against the
board file and the generated `.kicad_dru` rules only. Since neither input
changes, the DRC output cannot change. Measured anyway, once, as the
single "before == after" baseline, full project context (`.kicad_pro` +
freshly generated `.kicad_dru` copied beside a scratch `.kicad_pcb`, sha256
verified identical to the committed board), `kicad-cli 10.0.5`,
`--severity-all --all-track-errors`, with and without `--refill-zones`:

| category | no `--refill-zones` | `--refill-zones` |
|---|---|---|
| clearance | 224 | 225 |
| silk_overlap | 199 (capped — not a true count) | 199 (capped) |
| track_width | 120 | 120 |
| via_dangling | 106 | 23 |
| creepage | 100 | 121 |
| shorting_items | 53 | 53 |
| silk_over_copper | 42 | 42 |
| hole_clearance | 26 | 26 |
| lib_footprint_mismatch | 26 | 26 |
| solder_mask_bridge | 15 | 15 |
| lib_footprint_issues | 13 | 13 |
| copper_edge_clearance | 12 | 12 |
| tracks_crossing | 8 | 8 |
| drill_out_of_range | 6 | 6 |
| missing_courtyard | 5 | 5 |
| courtyards_overlap | 1 | 1 |
| silk_edge_clearance | 1 | 1 |
| **violations total** | **957** | **896** |
| unconnected_items | 300 | 247 |

**Connectivity**: `pad_connectivity_audit.py`'s `fully_connected` count
against the same scratch board = **63/139** (exact match to the task
brief's baseline), with 36/139 genuine multi-pad connections — computed
directly, not estimated.

**On the task brief's stated baseline ("DRC total 1086, track_width
122, connectivity 63/139"): `track_width` (120 vs 122) and `connectivity`
(63/139, exact) both corroborate closely against this board's own recent
history** — `docs/evidence/2026-08-17-blind-via-annular-floor-fix.md`
independently measured, on a very close ancestor of this exact board
(same methodology: `kicad-cli 10.0.5`, `--all-track-errors
--severity-all`, full project context), `track_width: 120`, `clearance:
224`, `creepage: 100`, `via_dangling: 106`, `shorting_items: 53`,
`hole_clearance: 26`, `copper_edge_clearance: 12` — **all identical to
what this task measured**, and that same document independently confirms
`63/139` connectivity for this board lineage. **"1086" itself could not be
traced to anything in this repo** — a targeted search of every `docs/`,
`scripts/`, and JSON artifact found no DRC total of 1086 (or within
1085-1090) for this board or any nearby sha; the only "1086" hits in the
repo are PR #1086 references and unrelated line numbers/current figures.
Per this project's own hard rule ("never invent or reconstruct a
value"), this figure is reported as **not obtainable/not corroborated**
rather than force-fit — the individually-verified numbers above
(track_width, connectivity, and the full 17-category breakdown, each
independently cross-checked against a sibling evidence doc) are the
measured ground truth for this board.

**The tradeoff, stated rather than decided**: there is none to report for
*this specific fix* — wider gate traces do not cost connectivity or
clearance here, because no trace got wider. The fix closes a
verification-only false negative (§3) without touching board geometry,
DRC counts, or the trace-width-assignment algorithm's output. If a future
re-route ever narrows a gate-drive trace below 0.258mm, this fix is what
would now catch it (still only when `--all-gates` is explicitly used,
since `StackupGate` remains off the default CI gate list — a separate,
pre-existing, unfixed gap this task did not touch, per §1's "dark by
default" finding, matching PR #1322's identical finding for
`IECCreepageGate`).

## 5. Other homes of the stale `GATE_H`/`GATE_L` literal

Swept beyond the two ampacity tables (`_GATE_NETS`, `_DEFAULT_NET_CURRENTS`,
`net_currents()` were three homes of the original 2026-08-17 rename; this
sweep covers what's left as literal net-name usages, excluding component
reference designators like `R_GATE_H`/`R_GATE_L` which are legitimate,
unrelated component refs, and excluding `tests/`/`experiments/`/
`ablation_feature_tests/` fixture data beyond what §2 already fixed):

- **`packages/temper-placer/src/temper_placer/core/design_rules.py:658-661`,
  `TEMPER_NET_ASSIGNMENTS`** — has *both* the correct `"GATE_HS"`/
  `"GATE_LS"` keys (already correct, live) **and** vestigial duplicate
  `"GATE_H"`/`"GATE_L"` keys mapping to the same `"GateDriveHV"` class.
  Harmless (the real keys are present and used; the dead ones match no
  real net), but stale dead weight. Not fixed here (out of this task's
  scope, zero behavioral effect); flagged for an owner/hygiene pass.
- **`scripts/check_netclass_map_board_correspondence.py:41`** — its own
  docstring claims `gate_driver_constraints.yaml`'s `net_classes:` map
  keys on `"GATE_H"`/`"GATE_L"`. Read the file directly:
  `net_classes: {GATE_HS: "GateDrive", GATE_LS: "GateDrive", ...}` — it is
  **already correct**; only the docstring describing it is stale (describes
  a pre-#1310 state). Not a functional miss. Flagged for whoever next
  touches that script.
- **`packages/temper-placer/configs/temper_constraints.yaml:541`**
  (`routing_priority.gate_drive.nets: ["GATE_H","GATE_L",...]`) — loaded
  into a `routing_priority` config field with **zero read sites** anywhere
  in `packages/temper-placer/src` or `temper-design-bundle/src` (grepped).
  Loaded, never consulted. Dead, not live.
- **`configs/templates/loops/gate_drive_high.yaml` /
  `gate_drive_low.yaml`** (`net: GATE_H`/`net: GATE_H_DRV` etc.) — loaded
  only by `load_loop_collection`, whose only production caller is a
  load-time-only profiling benchmark (`profiling/pipeline_metrics.py`);
  `merge_loops()` (the function that would fold these into real
  loop-extraction analysis) has zero call sites outside its own docstring
  example. Not on the path that produced the committed board.
- **`packages/temper-placer/src/temper_placer/deterministic/stages/
  fine_pitch_escape.py`** and **`configs/temper_deterministic_config.yaml`**
  (`GATE_H`/`GATE_L` in an `hv_exclusion_zones.excluded_nets` list, among
  others) — both belong to `temper_placer.deterministic.
  create_drc_aware_pipeline`, a separate grid-based router whose only
  drivers are `scripts/run_feedback_loop.py` and
  `examples/demo_integrated_pipeline.py` — **not** `route_board.py`/
  `_pipeline_route.py` (the confirmed production router that built the
  committed board). Architecturally live and tested code, but not on the
  path that produced `pcb/temper.kicad_pcb`. Flagged with medium
  confidence for an owner sanity check, not fixed here (would be scope
  creep into a parallel/legacy router this task was not asked to touch).
- **Confirmed inert, no action needed**: `router_v6/net_ordering.py:21`
  (docstring example, not a doctest assertion),
  `physics/operating_point.py:877-889` (a synthetic SPICE node label for
  simulation, independent of real board net names),
  `design_rules.rs`'s `hv_word_boundary_match` test assertions (test-only,
  and the word-boundary matcher already matches `GATE_HS`/`GATE_LS` fine
  via the generic `"GATE"` keyword), `loop_extraction_contracts.rs`/
  `loops.rs` (test/docstring only).

No other production, CI-wired code path keys on the literal `"GATE_H"`/
`"GATE_L"` in a way that silently mismatches the real board nets.

## 6. What was NOT changed

- `pcb/temper.kicad_pcb` — untouched; sha256 verified unchanged before,
  during, and after every step:
  `6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1`.
- No clearance/creepage/copper-weight/DRU threshold value edited anywhere.
- The 2.0A gate-drive rating itself — unchanged, not questioned (this
  task found no evidence it is wrong; if it ever is, that is a separate,
  unraised finding).
- No pinned `_*_py_oracle.py` oracle re-pinned or deleted.
- `hv_lv_separation_gate_threshold_mm` (the `PhysicsGate._CREEPAGE_MIN_MM`
  / `IECCreepageGate` 6.0mm-vs-12.6mm divergence PR #1320 also left red) —
  not touched; sibling/PR #1322 territory, and already independently fixed
  on that open branch (read, not merged into this diff, kept separable per
  the coordination note).
- `TEMPER_NET_ASSIGNMENTS`'s vestigial duplicate keys, the stale
  `check_netclass_map_board_correspondence.py` docstring, and the
  dead/parallel-router homes in §5 — reported, not fixed (zero behavioral
  effect or out of this task's scope).

## 7. Status checklist

- [x] Defect verified by tracing (executing) the lookup, not reading the
      table — both pre-fix (via a faithful re-implementation against the
      pre-fix source) and post-fix (via the real pyo3-built module).
- [x] Fixed both tables, kept in lockstep, differential + Rust unit tests
      pass (86+21 Python, 22 Rust).
- [x] Measured the actual consequence rather than assuming one: trace
      widths unchanged (assignment path was never broken; committed board
      untouched), full DRC unchanged (byte-identical by construction,
      verified once as the before==after baseline), connectivity 63/139
      exact match, no tradeoff to report because nothing regressed.
- [x] Searched for other homes of the stale literal; found 2 dead, 2
      architecturally-live-but-off-the-production-path, 1 stale-docstring
      -only, all reported in §5, none silently fixed.
- [x] Registered invariant confirmed closed: `check_fact_registry_drift.py`
      moved from TOOL ERROR to CLEAN for both new facts; its own tests
      updated as a regression guard, matching the pattern already used for
      PR #1310's `_GATE_NETS` fix.
- [x] Board sha256 unchanged throughout.
