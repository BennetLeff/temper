<!-- provenance: worktree branched from origin/fix/pyo3-dup-kw-boundary-match (PR #1185, commit fd27bcda2). elec/build/default.net rebuilt in this worktree via `make netlist` (write-build-stamp digest 8cfd715e60a3…, 162 nets -- same digest #1185's own evidence doc cites). All numbers below measured against the actually-built, freshly-rebuilt temper_geometry.so (`make venv-isolate` then `make extensions`; `scripts/check_stale_extensions.py` 10/10 fresh before AND after every rebuild in this session). pcb/temper.kicad_pcb never modified (git status confirms; also confirmed by direct inspection, see Sec 4). -->

# `hb-gnd` was getting a 4x under-width trace on a live, unrouted mains-referenced return path. Fixed without touching the frozen clearance/creepage boundary matcher.

**Verdict up front: this was LIVE, not latent, and it is now fixed.** `determine_trace_width` (the function `assign_trace_widths` calls for every net the router lays copper for, in `packages/temper-placer/src/temper_placer/router_v6/_pipeline_route.py:674`) computed trace width from net name alone -- no netclass, no `TEMPER_NET_ASSIGNMENTS`, no `kicad_pro`/`domain_manifest.yaml` lookup anywhere in the call chain. `hb-gnd` itself is **not** declared in any of those three places (checked directly, Sec 2) -- despite this task's own brief claiming it was declared HV by PRs #1123/#1145/#1164/#1165, no such declaration exists in the current tree for the literal net name `hb-gnd`; that claim does not hold up and is called out here rather than silently assumed. The pattern-match path was therefore the only path deciding this net's width, and it was undersizing it 4x. Fixed in Rust, in `packages/temper-geometry/src/trace_width_assignment.rs`, without widening the shared `via_clearance::kw_boundary_match`/`word_bounded` (frozen behind a byte-exact oracle pin, and still used, unchanged, by `net_class_to_voltage_class` and every clearance/creepage classification path).

---

## 1. The defect, confirmed against the real board and the real built extension

`hb-gnd` is a real, placed, 6-pad net on the committed board (`elec/build/default.net`, net code 39; `pcb/temper.kicad_pcb`, net 55):

```
(net (code "39") (name "hb-gnd")
  (node (ref "R23") (pin "2")) (node (ref "U6") (pin "9"))
  (node (ref "C23") (pin "2")) (node (ref "C24") (pin "2"))
  (node (ref "U5") (pin "3")) (node (ref "T2") (pin "1")))
```

U5 is `Package_TO_SOT_THT:TO-247-3` (the low-side switch, Q_low) and U6 is `lib:SOIC16W_Isolated` (the isolated gate driver) -- consistent with U5.3 = Q_low emitter, U6.9 = VSSB. T2 (`temper:CST3015`, a current-sense transformer) pin 1 is on `hb-gnd`; T2 pin 2 is on `DC_BUS_RTN` (already-declared HV, `elec/domain_manifest.yaml:94`). `hb-gnd` is therefore the low-side switch's return conductor threaded through CT2's primary -- physically in series with `DC_BUS_RTN`, one CT winding upstream -- not a separate, lower-current node.

Pre-fix, measured against the built extension on `origin/fix/pyo3-dup-kw-boundary-match` (the base this branch was cut from):

```
>>> tg.determine_trace_width_py("hb-gnd", 0.127, 0.508, 0.635)
(0.127, 'Standard signal trace')
```

`0.127mm` (5mil) is the *default signal* width; `hb-gnd` needed the 20mil `Power` width (`0.508mm`) at minimum. Two siblings share the identical defect: `hb.gate_hs-vdd`, `hb.gate_ls-vdd` (both `0.127` -> should be `0.508`) -- exactly the 3-net result PR #1185's own evidence doc (`docs/evidence/2026-08-13-pyo3-duplicate-registration-kw-boundary-match.md` Sec 3) already flagged and scoped out.

**Root cause**, located in `via_clearance.rs::word_bounded` (the sole boundary-match implementation this crate's `kw_boundary_match`/`determine_trace_width` used pre-fix, post-#1185's consolidation): a word boundary is `_`, start-of-string, end-of-string, or a trailing digit -- never `-`. `hb-gnd` upper-cased is `HB-GND`; `GND` starts at index 3, but the preceding byte is `-`, not `_`, so the leading-boundary check failed and the net fell through every branch to the default.

## 2. Is `hb-gnd` explicitly netclassed elsewhere? No -- checked directly, this path is genuinely live

Searched all three places an explicit assignment could live, for the literal net name `hb-gnd`:

- `elec/domain_manifest.yaml` -- absent. The HV domain's net list (lines 83-250) enumerates `ac_l`, `ac_n`, `+170V_BUS`, `DC_BUS_RTN`, `PWR_RTN`, `SW_NODE`, `GATE_HS`, `GATE_LS`, `hb.power_loop.q_high-g`, `hb.gate_hs.driver-p1-1`, `hb.gate_hs.driver-p2`, and others -- `hb-gnd` is not among them. This file's own ground rule (line 9: "every entry below is an exact, literal net name... never a pattern") rules out an indirect match.
- `pcb/temper.kicad_pro`'s `net_settings.netclass_assignments` -- absent (grepped for `"hb-gnd"` directly; only `hb.gate_hs.driver-p1-1` / `hb.gate_hs.driver-p2` are present, two different nets).
- `packages/temper-placer/src/temper_placer/core/design_rules.py`'s `TEMPER_NET_ASSIGNMENTS` -- absent, same two entries as above and nothing else `hb.*`.

So the task brief's claim that PRs #1123/#1145/#1164/#1165 declared `hb-gnd` itself HV does not hold up against the current tree -- worth surfacing rather than silently assuming it and reporting the defect as moot. Regardless, **this would not have made the defect latent even if it were declared**: `assign_trace_widths` -> `_determine_trace_width` -> `determine_trace_width_py` never reads `kicad_pro`, `domain_manifest.yaml`, or `TEMPER_NET_ASSIGNMENTS` at any point in the call chain (`packages/temper-placer/src/temper_placer/router_v6/trace_width_assignment.py`, `_pipeline_route.py:670-676`) -- it is a pure function of net name and the three width literals. The pattern match is the *only* thing deciding this net's routed width, confirmed by reading the full call chain, not inferred from its absence.

## 3. Current-capacity consequence: this is a live thermal-hazard-grade under-sizing, not a cosmetic miss

Using this repo's own method (`docs/hardware/TRACE_WIDTH_CALCULATIONS.md`, IPC-2221B `I = k * dT^0.44 * A^0.725`, `k = 0.048` external, 2oz outer copper -- this board's outer-layer spec):

| Width | Capacity @ dT=20C | Capacity @ dT=40C |
|---|---:|---:|
| 0.127mm (5mil, pre-fix default) | **1.20A** | **1.62A** |
| 0.508mm (20mil, post-fix Power) | **3.27A** | **4.43A** |
| 0.635mm (25mil, HV class) | 3.84A | 5.21A |

`hb-gnd` carries the low-side switch's return current -- the same current that flows through `DC_BUS_RTN`, whose own required width per this document's own worked example (Sec 3.1) is **5.0mm/pour for 22A peak / 15A RMS**. Independently, `elec/src/modules.ato:585-592` documents this specific tank/coil loop's actual current at the design's 1800W operating point: **~20.7-22.5A RMS** (ngspice harness vs. first-harmonic solve), peak **28.7-31.9A** (flagged there as its own unresolved, pre-existing, out-of-scope finding -- already exceeding the design's 25A/`LitzPad_15A` constraints, unrelated to trace width). Even allocating only Q_low's own conduction-duty share of that loop current (a conservative ~50% split in a half-bridge) puts `hb-gnd`'s real current in the **10-16A RMS** range.

**Verdict: 0.127mm (rated ~1.2-1.6A) was a live thermal hazard, not a latent classification bug** -- roughly a 10-18x shortfall against the net's actual current, on a mains-referenced return path in an IEC 60335-1 appliance. **The fix (0.508mm, rated ~3.3-4.4A) is a real, necessary 4x improvement, but is honestly still short of this net's full current** by a further 3-6x. The pattern-based `assign_trace_widths` mechanism assigns one of three flat literals (default/power/HV) regardless of a net's actual measured current, so even the corrected classification does not reach the current-appropriate 5mm/pour treatment `DC_BUS_RTN` gets. **Flagged as a residual, separate follow-up** (per-current trace sizing for CT-primary/switch-return nets specifically, not a name-pattern fix) -- out of this task's scope, which is the boundary-matching defect, not a redesign of the width-assignment mechanism itself.

## 4. Not yet baked into the committed board

`pcb/temper.kicad_pcb` (net 55 = `hb-gnd`, net 56 = `hb.gate_hs-vdd`, net 60 = `hb.gate_ls-vdd`) carries **zero routed track segments for all three nets today** (grepped `(net 55)` / `(net 56)` / `(net 60)` against every `(segment ...)` block in the file -- 0 hits each, out of 2149 total segments on the board). `hb-gnd`'s 6 pads are placed and connected via ratsnest, not yet copper. **This defect has no already-manufactured or already-DRC'd consequence on the current committed board** -- it would only take effect the next time the router pipeline routes these three nets. This does not make the fix less necessary (the very next full route would bake in the under-width copper), but it means there is no DRC delta to measure against the currently committed board today, and no full re-route was run in this session (out of scope of the hard constraint not to touch `pcb/temper.kicad_pcb`, and per environment notes, an unbatched full route risks OOM on this machine). The expected geometric impact when these nets are next routed is small in absolute terms: 3 nets, one width-class step each (+0.381mm each), not a bulk widening.

## 5. Fix: a separate, hyphen-aware matcher for `determine_trace_width` ONLY -- the shared, oracle-pinned matcher is untouched

The obvious fix -- widen `via_clearance::word_bounded`/`kw_boundary_match` in place to treat `-` as a boundary -- was rejected, for a reason this task's own brief anticipated (the #1136/#1137 "one-armed fix regresses a cross-arm differential" shape): that function is **shared** with `net_class_to_voltage_class` (the IEC 60335-1 creepage/clearance voltage-class path) and is frozen behind a byte-exact oracle pin (`test_via_clearance_tier2_rust_differential.py`'s `_ORACLE_PIN_SHA`). That file's own `test_net_class_to_voltage_class_oracle_parity` asserts `"AC-DC"` / `"ac-dc"` do **NOT** match keyword `"AC"` -- widening the shared boundary would flip that assertion and regress a pinned, still-current test.

**The fix**, in `packages/temper-geometry/src/trace_width_assignment.rs`:

- Added `word_bounded_hyphen_aware` / `kw_boundary_match_hyphen_aware` -- the identical `(?:^|[_-])kw(?:$|[\d_-])` shape as `via_clearance::word_bounded`, widened only to also accept `-` as a boundary character on both the leading and trailing side.
- `determine_trace_width` now calls `kw_boundary_match_hyphen_aware` instead of `crate::via_clearance::kw_boundary_match`, for all three of its keyword groups (HV, Power/GND, Gate/Drive).
- `via_clearance::word_bounded`/`kw_boundary_match` (and therefore `net_class_to_voltage_class`, `kw_boundary_match_py`, and every clearance/creepage classification keyed off them) is **completely unchanged** -- 0 lines touched in `via_clearance.rs`.
- Two other independent boundary-match families in this codebase were surveyed and confirmed **also unaffected** (they don't call into `via_clearance.rs` at all, so this fix cannot regress them): `creepage_check.rs::is_high_voltage_net`, whose keyword set includes `"LINE"` (would sweep every `*-line` SELV net into HV if its own boundary were widened -- not touched here), and `design_rules.rs::hv_word_boundary_match`, whose keyword set includes `"COIL"` (would sweep `*-coil1`/`*-coil2` relay-drive nets into HV -- not touched here, and that file already carries a regression test, `design_rules.rs:315`, pinning `"DISCHARGE.K_DIS1-COIL1"` as a non-match).

## 6. Over-match check: all 162 real nets simulated, 3 changed, 0 unwanted

Ran `determine_trace_width_py` against every one of the 162 real net names in `elec/build/default.net` (digest `8cfd715e60a3…`), before and after the fix:

| Net | Before | After | Ratio |
|---|---|---|---:|
| `hb-gnd` | 0.127mm, "Standard signal trace" | 0.508mm, "Power net requires wider trace for current capacity" | 4x |
| `hb.gate_hs-vdd` | 0.127mm, "Standard signal trace" | 0.508mm, "Power net requires wider trace for current capacity" | 4x |
| `hb.gate_ls-vdd` | 0.127mm, "Standard signal trace" | 0.508mm, "Power net requires wider trace for current capacity" | 4x |

**Exactly these 3 nets change; the other 159 are bit-identical before and after** (post-fix width distribution: 144 x 0.127mm, 14 x 0.508mm [11 pre-existing + 3 newly fixed], 2 x 0.635mm, 2 x 0.3048mm gate-drive -- matches the pre-fix distribution plus exactly the 3 expected moves). All 3 changes are `Default -> Power`, the correct direction for return/bias nets carrying real current; none land in the HV or Gate/Drive branches unexpectedly.

Also re-ran `net_class_to_voltage_class_py` (the clearance/creepage path, sharing the now-*unchanged* `via_clearance::kw_boundary_match`) across all 162 nets: **0 changes**, confirming this fix has zero blast radius on that path, as designed -- and confirming, independently, that no real net on this board would have exercised the `"AC-DC"`-style regression the shared-matcher approach would have caused.

## 7. Verification

- `cargo test --manifest-path packages/temper-geometry/Cargo.toml --lib`: **8391/8391 pass** (8389 baseline + 2 new tests; 0 regressions).
- `cargo test` for `temper-design-bundle` (33/33) and `temper-drc-rs` (3312/3312), both real path-dependents of `temper-geometry`: pass, unchanged.
- `cargo clippy --lib --features python -- -D warnings`: clean.
- `make venv-isolate` -> `scripts/check_stale_extensions.py`: **PASSED, 10/10 fresh**, before this branch's edits and after every rebuild (`Compiling temper-geometry`/`temper-design-bundle`/`temper-drc-rs` lines confirmed present each `make extensions` run).
- Built-extension probe, before and after: `determine_trace_width_py("hb-gnd", 0.127, 0.508, 0.635)` -> `(0.127, ...)` pre-fix, `(0.508, ...)` post-fix. `net_class_to_voltage_class_py("AC-DC")` / `kw_boundary_match_py("AC-DC", ["AC"])` -> unchanged (`1` / `False`) before and after.
- `pytest packages/temper-placer/tests/router_v6/test_via_clearance_tier2_rust_differential.py packages/temper-placer/tests/router_v6/test_spatial_drc_cluster_rust_differential.py`: **54/54 pass**, including the pinned `test_kw_boundary_match_oracle_parity` / `test_net_class_to_voltage_class_oracle_parity` / `test_determine_trace_width_matches_reference` differentials -- none needed modification, because none of their fixed enumerated cases exercise a hyphen-adjacent-keyword collision (verified directly, not assumed).
- `pytest packages/temper-placer/tests/router_v6/ -k "clearance or trace_width or creepage"`: **796 passed, 3 skipped, 15 xfailed** -- byte-identical to PR #1185's own recorded baseline.
- `scripts/check_oracle_hashes.py`: 167/167 oracle files byte-identical to their pins (none of the ~187 `_*_py_oracle.py` files were touched).
- `scripts/check_pyo3_duplicate_registration.py`: 10 pymodules, 666 registrations, 0 duplicates (this fix adds no new pyo3-exported symbol -- `kw_boundary_match_hyphen_aware` is a private Rust function, never wrapped or registered).
- `scripts/gen_wasm_test_registry.py --crate temper-geometry --check`: up to date after regeneration (2 new test names added to the per-module `WASM_TESTS` const and the crate-root aggregator).
- `git status --porcelain` / `git grep -l "^<<<<<<< "`: clean throughout. Diff touches exactly 2 files: `trace_width_assignment.rs` and the generated `wasm_test_registry.rs`.
- `pcb/temper.kicad_pcb`, any clearance/creepage/DRU threshold, and `power_pcb_dataset/drc_ceiling.json`: **not touched** (confirmed by `git diff --name-only`).
- `scripts/check_venv_integrity.py`: reports 18 pre-existing violations in this session's isolated `.venv`, all `.pth`/`direct_url.json` entries resolving relative to this nested `.claude/worktrees/...` location -- appears to be an artifact of this worktree's nested path under the parent checkout rather than anything caused by this change (the direct built-extension probes above are unaffected and behave exactly as expected both before and after the fix). Not investigated further; flagged rather than silently ignored.

## 8. What this fix does NOT do

- Does not widen `via_clearance::kw_boundary_match`/`word_bounded` -- the shared, oracle-pinned matcher `net_class_to_voltage_class` depends on is byte-for-byte unchanged.
- Does not touch `creepage_check.rs` or `design_rules.rs`'s independent boundary-match families (their own `"LINE"`/`"COIL"` over-match risks are real but out of scope here, and this fix's file-scoped change cannot affect them regardless).
- Does not rename any net in `elec/src/**`.
- Does not touch `pcb/temper.kicad_pcb`, any clearance/creepage/DRU threshold, or `power_pcb_dataset/drc_ceiling.json`.
- Does not bring `hb-gnd` up to full current-appropriate (5mm/pour-class) width -- flagged in Sec 3 as a genuine, separate follow-up.
- Does not touch any of the ~187 `_*_py_oracle.py` pinned oracle files.
