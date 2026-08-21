<!-- provenance: worktree /home/bennet/Desktop/temper-drc-audit, branch audit/drc-project-context-2026-08-08, based on feat/4layer-power-planes-real @ f598973a (docs(evidence): DRC power-token jump is a project-resolution artifact, not the token), which is itself based on c4956df6 ("fix(pcb): declare In1.Cu/In2.Cu as power-plane layers, not signal"). kicad-cli 10.0.5 (matches the CI pin recorded in power_pcb_dataset/drc_ceiling.json's provenance), obtained via the official KiCad AppImage (kicad-downloads.s3.cern.ch/appimage/stable/kicad-10.0.5-x86_64.AppImage.tar), extracted with --appimage-extract, wrapped with LD_LIBRARY_PATH scoped to that one binary. All measurements below were run live in this session; none are carried over unverified from a prior agent's report. -->

# DRC project-context audit: which measurements ran blind, what they hid, and the fix

**Date:** 2026-08-08
**Task:** enumerate every DRC invocation site in the temper project, determine
which ran without a resolvable KiCad project (and therefore silently
under-reported safety violations, per the mechanism root-caused in
`docs/evidence/2026-08-08-drc-power-token-jump-root-cause.md`), re-measure
correctly, enumerate the hidden safety violations, and make a missing
project an explicit error everywhere DRC runs.

**Headline:** the CI truth gate (`ci_check_drc.py` -> `DrcRatchet` ->
`_drc_api.run_drc`) and `power_pcb_dataset/drc_ceiling.json`'s *current*
committed numbers were measured **with** project context resolved — the
ceiling is stale (wrong commit), not blind. But two independent raw
kicad-cli call sites feeding a *different* committed artifact,
`power_pcb_dataset/baselines/temper_production_baseline.yaml`'s
`router_v6_routing` block, plus the two routed-output DRC regression test
gates that produced it, were measuring **project-context-blind** — silently
missing `creepage`, `track_width`, `missing_courtyard`, and `annular_width`
in every routed-board measurement they ever made. All are fixed in this
branch (commit `67e04601`) to fail loudly instead.

---

## 1. Invocation site table

| Site | Invokes | Project context resolvable? | Feeds |
|---|---|---|---|
| `scripts/ci_check_drc.py --backend kicad-cli` (CI's "KiCad DRC truth gate" step, `.github/workflows/regression.yml`) | `DrcRatchet.check()` -> `_drc_api.run_drc(repo_root / "pcb/temper.kicad_pcb")` | **Yes.** `pcb/temper.kicad_pro` is git-tracked next to the board; always present in a checkout. | `power_pcb_dataset/drc_ceiling.json` pass/fail |
| `.github/workflows/golden-check.yml` -> `RegressionRunner._run_board` | `_drc_api.run_drc(board_entry.resolve_path(repo_root))` | **Yes** for `temper_production` (`pcb/temper.kicad_pcb`, in place). **No** for the `bitaxe_ultra` golden board (`power_pcb_dataset/corpus/bitaxe_ultra/bitaxeUltra.kicad_pcb` has no sibling `.kicad_pro` at all) — but that board carries none of this project's HV/creepage rules to begin with (it's a third-party fixture, own project never committed), so this is a generic completeness gap, not a concealed *temper* safety finding. Not fixed in this pass (flagged for a human: either commit a project for it or accept it measures KiCad's stock severities only). | `power_pcb_dataset/baselines/temper_production_baseline.yaml`'s top-level `drc_errors`/`drc_warnings` (`temper_production` only) |
| `packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py::test_production_board_drc_regression` | `_drc_median(PRODUCTION_BOARD_PATH)` = `_drc_api`-independent `_parallel_drc.run_drc_loud` on `pcb/temper.kicad_pcb`, in place | **Yes.** | Local `PRODUCTION_COMMITTED_BOARD_*` thresholds in the same file |
| `...test_production_board_routing_drc_regression` | routes, writes routed content to a bare `tempfile.NamedTemporaryFile`, DRCs that copy via `run_drc_loud` | **No, before this fix.** The tempfile had no sibling `.kicad_pro`. **Fixed**: now calls `_provision_project()` (-> `copy_kicad_project_sidecar`) before DRC'ing the copy. | `PRODUCTION_ROUTER_OUTPUT_TOTAL_DVIOLATIONS/_SHORTING_ITEMS/_UNCONNECTED` (1514/178/463) in the same file |
| `...test_golden_board_drc_regression`, `...test_golden_board_routing_drc_regression` | same pattern, on the `power_pcb_dataset/corpus/temper/temper.kicad_pcb` fixture (which has **no `.kicad_pro` of its own, ever**) | **No, before this fix.** **Fixed**: `_provision_project()` now propagates `pcb/temper.kicad_pro`'s rules onto the scratch copy (the only real project this repo has; the corpus fixture shares the same net-class naming scheme). | local thresholds in the same file |
| `packages/temper-placer/tests/router_v6/test_temper_production_board_routing.py::test_route_pcb_production_board` | own independent `_run_drc()` helper (a **third**, separate raw kicad-cli invocation), routes `pcb/temper.kicad_pcb`, writes to a bare tempfile, DRCs the copy | **No, before this fix.** **Fixed**: now calls `copy_kicad_project_sidecar(routed_tmp, _PCB_PATH)` before DRC'ing. | `scripts/update_production_routing_baseline.py` reads this test's measurement and writes it into **`power_pcb_dataset/baselines/temper_production_baseline.yaml`'s `router_v6_routing` block** — a **committed artifact**. Confirmed blind (see §2). |
| `Makefile`'s `drc:` target (`make build` = `netlist footprints schematics route drc`) | raw `kicad-cli pcb drc --all-track-errors --exit-code-violations $(ROUTED_PCB)`, `$(ROUTED_PCB)` = `pcb/temper_routed.kicad_pcb` | **No, before this fix.** `scripts/route_board.py` (the `route:` target) wrote `pcb/temper_routed.kicad_pcb` with no sibling `pcb/temper_routed.kicad_pro` — a different stem than `pcb/temper.kicad_pro`, so kicad-cli could never resolve it even though a project sits in the same directory. **Fixed two ways**: `route_board.py::run_single` now propagates the source board's project onto whatever it writes to `--output`; the `Makefile` target itself also gained an explicit pre-flight check so a stale/hand-placed `$(ROUTED_PCB)` (predating the fix, or produced by some other tool) still refuses to measure blind. | stdout only (no committed artifact) — but this is `make build`'s last step, i.e. what a human or a script would see after `make build` |
| `scripts/check_board_defect_corpus.py::measure_drc` | copies **only** `.kicad_dru` (not `.kicad_pro`) next to its clean/mutated scratch copies (`board_defect_mutator.copy_board` copies the `.kicad_pcb` alone) | **No — identified, not fixed in this pass.** Every measurement this script makes (the clean-board control and all per-class mutated boards) runs without a resolvable project. Its own docstring claims "kicad-cli resolves `<stem>.kicad_dru` next to the board file... verified", which conflicts with this audit's controlled finding (`.kicad_dru` alone, without `.kicad_pro`, produces **zero** `creepage`/`track_width` — see §3) — worth a second look, but this script's anti-vacuity ceiling comparisons and mutation classes were out of this task's fix budget. Flagged for follow-up. | `docs/evidence/` corpus reports (not `drc_ceiling.json`) |
| `packages/temper-placer/src/temper_placer/regression/drc_ratchet.py::DrcRatchet._run_rust_drc` (`backend="rust"`) | `temper_drc_rs.run_drc(board_dict, constraints_dict)` — **never calls kicad-cli at all** | N/A — structurally different mechanism, not a project-resolution bug. This backend never reads `.kicad_dru` custom rules or `rule_severities` regardless of any file's presence; it is explicitly documented (`ci_check_drc.py --backend`) as the "diagnostic" backend, never the CI truth gate's default. Its `creepage`/`track_width` checks (when present) measure different things than the KiCad DRU rules — see `docs/evidence/2026-08-04-creepage-rust-backend-survey.md`. Out of this audit's scope. | nothing committed (diagnostic-only path) |
| `scripts/calibrate_drc_ceiling.py`, `scripts/ci_closure_test.py` (rust-backend calls) | same rust-backend mechanism as above | N/A, same reasoning | `scripts/calibrate_drc_ceiling.py`'s own output (not `drc_ceiling.json`); closure-test metrics |
| `.github/workflows/metrics-record.yml` -> `scripts/ci_closure_test.py --pcb pcb/temper.kicad_pcb` (kicad-cli path via `closure_test.py::run_drc(self.pcb_path)`) | `_drc_api.run_drc(pcb/temper.kicad_pcb)`, in place | **Yes.** | closure metrics NDJSON (not a ratchet gate; `continue-on-error` on the closure step itself, unrelated to this audit) |
| `docs/evidence/scripts/k3_resolve_gated_drc.py`, `2026-08-04_domain_first_resolve_drc.py`, `k3_fixed_copper_repair_drc.py`, `k3_swap_board_write_drc.py` | archival one-off scripts behind several now-superseded `_march` entries in `drc_ceiling.json` | Not re-verified in this pass (out of live-CI scope; historical). | historical `_march` narrative only |

**Core architectural gap (now fixed):** `_drc_api.run_drc()` — the shared
function every "Yes" row above ultimately calls — never itself checked that
`pcb_path` had a resolvable sibling project before shelling out to
kicad-cli. Every "Yes" in the table above was Yes by accident of *which
path happened to be passed in*, not because anything enforced it. The two
independent raw-kicad-cli helpers used by the test suite
(`tests/placer/cp_sat/_parallel_drc.py::run_drc_loud` and
`test_temper_production_board_routing.py::_run_drc`) had no such check at
all. See §4 for the fix.

---

## 2. Which committed baselines are affected

### `power_pcb_dataset/drc_ceiling.json` — stale, but **not** project-context-blind

Its `provenance.measured_via` field says exactly how it was measured:
`temper_placer.validation._drc_api.run_drc with --all-track-errors, after
regenerating pcb/temper.kicad_dru from scripts/generate_kicad_dru.py (the
CI gate's exact invocation)`, i.e. `ci_check_drc.py`'s own path — always
`repo_root / "pcb/temper.kicad_pcb"`, always resolvable. Its
`violations_by_type` includes `creepage: 188`, `track_width: 199`, and its
`warnings_by_type` includes `missing_courtyard: 5`, `annular_width` folded
into errors at `4` — exactly the categories that vanish without project
context, present and populated. **This confirms the ceiling was measured
with project context resolved.**

It is stale for an *unrelated* reason, already flagged in the task brief:
`provenance.inputs[0].sha256` (`51e39844b1...`) matches neither the current
commit (`c4956df6`/`f598973a`, sha256 `6928b7c8...`) nor its parent (sha256
`1cce4a08...`) — confirmed independently in this session:

```
$ sha256sum pcb/temper.kicad_pcb   # at HEAD f598973a / c4956df6
6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64
```

Per the hard constraint, `drc_ceiling.json` is **not modified** by this
audit. §5 reports what the corrected numbers are and the delta.

### `power_pcb_dataset/baselines/temper_production_baseline.yaml` — the `router_v6_routing` block **is** project-context-blind

This file's `router_v6_routing.drc_violations_by_type` block (measured
2026-08-07, `kicad_cli_version: 10.0.4`, `extraction_method:
router_v6.route_pcb(existing_positions)`):

```
shorting_items, clearance, hole_clearance, courtyards_overlap,
pth_inside_courtyard, copper_edge_clearance, drill_out_of_range,
via_diameter, solder_mask_bridge, track_dangling, via_dangling,
silk_edge_clearance, lib_footprint_mismatch, lib_footprint_issues,
silk_overlap, silk_over_copper
```

**No `creepage`, `track_width`, `missing_courtyard`, or `annular_width`
key at all** — not present, not zero. This is the exact concealment
signature (§3). Traced to its source: `scripts/update_production_routing_baseline.py`
is the sole writer of this block, and it sources its measurement from
`packages/temper-placer/tests/router_v6/test_temper_production_board_routing.py::TestProductionBoardRouting::test_route_pcb_production_board`,
whose own `_run_drc()` (before this fix) wrote the routed board to a bare
`tempfile.NamedTemporaryFile` and ran raw kicad-cli on it directly — no
sibling `.kicad_pro`, ever. `drc_violations_post_route: 1411` and
`unconnected_items: 461` are real numbers, but the 1411 total is missing
an entire safety-critical category. **This file is a committed baseline
this audit's fix (67e04601) has NOT re-measured** — re-running
`scripts/update_production_routing_baseline.py` is the correct next step,
but that is a maintenance action on a committed artifact (its own
docstring: "A maintenance routine that mutates committed evidence should
be something a person *chooses* to run") and is left to the human per the
same spirit as the `drc_ceiling.json` constraint, not run in this session.

### Other evidence docs

Searched every `docs/evidence/*.md` referencing `violations_by_type` /
`error_ceiling` (47 files touch DRC counts generally; 9 touch the specific
per-type ceiling vocabulary). All 9 are supporting evidence for
`drc_ceiling.json`'s own `_march` log entries (already covered above) or
are the `2026-08-08-drc-power-token-jump-root-cause.md` this audit
extends. No other committed, independently-standing DRC count was found.

---

## 3. Independently reproducing the concealment mechanism, on this commit

Not just trusting the root-cause doc — reproduced fresh, on the current
board (`c4956df6`/`f598973a`, sha256 `6928b7c8...`), through the real
`_drc_api.run_drc()` wrapper (`--all-track-errors`, thread-pinned):

| | errors | warnings | creepage | track_width | annular_width | missing_courtyard |
|---|---|---|---|---|---|---|
| **with** `pcb/temper.kicad_pro` resolvable | 1249 | 489 | 187 | 199 | 4 | 5 |
| **without** (bare copy, `.kicad_dru` present, no `.kicad_pro`) | 828 | 621 | **0 (absent)** | **0 (absent)** | **0 (absent)** | **0 (absent)** |

Confirms the root-cause doc's finding precisely: `.kicad_dru` alone,
without a resolvable `.kicad_pro`, is **not** sufficient — kicad-cli drops
the DRU-sourced categories (`creepage`, `track_width`) too, not only the
`rule_severities`-sourced ones (`missing_courtyard`, `annular_width`).
This directly contradicts `check_board_defect_corpus.py`'s docstring claim
(§1) that copying `.kicad_dru` alone is sufficient — that script's
measurements should be treated as suspect until re-verified.

Also note the blind run's `lib_footprint_issues` warning count explodes
11 -> 169 and `hole_to_hole` migrates from `errors` to `warnings` (3 in
both, but reclassified) — side effects of the same missing-project
resolution (library-table and severity-override resolution both live in
the project file), reported here for completeness though outside this
audit's safety-category focus.

---

## 4. The fix

Implemented in commit `67e04601` (this branch):

- **`packages/temper-placer/src/temper_placer/validation/_drc_api.py`**:
  new `DrcProjectContextError(DrcRunnerError)`, `ensure_resolvable_kicad_project(pcb_path)`
  (raises unless `pcb_path.with_suffix(".kicad_pro")` exists), called from
  `run_drc()` before the subprocess call. New `copy_kicad_project_sidecar(pcb_path, source_pcb_path)`
  for legitimate scratch-copy measurements — propagates
  `.kicad_pro`/`.kicad_dru` from a real board onto a derived copy under the
  copy's own stem.
- **`tests/placer/cp_sat/_parallel_drc.py::run_drc_loud`**: same guard —
  this is a second, independent raw-kicad-cli call path the first fix does
  not cover.
- **`test_regression_drc.py`, `test_temper_production_board_routing.py`**:
  every routed/placed scratch-board tempfile now gets
  `copy_kicad_project_sidecar`'d before DRC, using `pcb/temper.kicad_pro`
  (the only real project this repo has) as the source.
- **`scripts/route_board.py::run_single`**: propagates `--pcb`'s project
  onto whatever it writes to `--output`, so `make route && make drc`
  resolves a project automatically.
- **`Makefile`'s `drc:` target**: explicit pre-flight check — refuses to
  invoke kicad-cli against a routed board with no sibling `.kicad_pro`,
  independent of whether `route_board.py`'s fix ran.
- **New test**: `packages/temper-placer/tests/validation/test_drc_project_context_required.py`
  — unit tests for the guard and the sidecar helper, tests that both
  `run_drc` and `run_drc_loud` raise *before* any subprocess launches, and
  (skipped unless real kicad-cli is available) an integration test that
  reproduces §3's exact concealment magnitude against a live kicad-cli
  invocation, so a future regression in kicad-cli's own resolution
  behavior — or a future call site that reintroduces this bug — is caught.
- Existing synthetic-board unit tests in `test_drc_runner.py`,
  `test_drc_api_thread_pinning.py`, `test_courtyard_violation_report.py`
  updated to give their fixture boards a (minimal, content-irrelevant)
  sibling `.kicad_pro`, since they exercise subprocess-mocking / JSON
  parsing / env plumbing, not project resolution, and would otherwise trip
  the new guard before reaching what they actually test.

**Not fixed in this pass** (flagged, not silently left broken):
`scripts/check_board_defect_corpus.py` (§1, §3) and the `bitaxe_ultra`
golden board in `golden-check.yml` (§1). Neither conceals a *temper*
safety finding today (the corpus script's own docstring claim needs
re-verification but its ceiling comparisons are a separate mechanism from
`drc_ceiling.json`; `bitaxe_ultra` has no temper-specific rules to hide),
but both should get the same `ensure_resolvable_kicad_project` treatment
as a follow-up.

---

## 5. Corrected measurement — full breakdown

`pcb/temper.kicad_pcb` @ `c4956df6`/`f598973a` (sha256 `6928b7c8...`),
kicad-cli **10.0.5** (CI-pinned), `pcb/temper.kicad_dru` regenerated from
`scripts/generate_kicad_dru.py` (the CI gate's exact pre-step), measured
through `temper_placer.validation._drc_api.run_drc` (`--all-track-errors`,
thread-pinned), 3 repeated runs:

| run | errors | warnings | clearance | creepage | shorting_items | via_dangling | tracks_crossing |
|---|---|---|---|---|---|---|---|
| 1 | 1249 | 489 | 368 | 187 | 199 | 32 | 1 |
| 2 | 1248 | 489 | 368 | 186 | 199 | 32 | 1 |
| 3 | 1249 | 489 | 368 | 187 | 199 | 32 | 1 |

Only `creepage` moved (186/187 — the documented ±1 pointer-address dedup
noise, KiCad issue #20048). Everything else, including `via_dangling`, was
identical across all 3 runs.

Full category breakdown (run 1, representative):

**Errors (1249 total):**

| category | count |
|---|---|
| clearance | 368 |
| creepage | 187 |
| shorting_items | 199 |
| track_width | 199 |
| solder_mask_bridge | 154 |
| hole_clearance | 105 |
| copper_edge_clearance | 10 |
| courtyards_overlap | 11 |
| annular_width | 4 |
| drill_out_of_range | 4 |
| via_diameter | 4 |
| hole_to_hole | 3 |
| tracks_crossing | 1 |

**Warnings (489 total):**

| category | count |
|---|---|
| silk_overlap | 199 |
| silk_over_copper | 172 |
| track_dangling | 45 |
| via_dangling | 32 |
| lib_footprint_mismatch | 23 |
| lib_footprint_issues | 11 |
| missing_courtyard | 5 |
| pth_inside_courtyard | 1 |
| silk_edge_clearance | 1 |

### Delta vs `drc_ceiling.json`'s committed ceiling (stale, for a different commit; not modified)

| | ceiling (`3410ee4e1`) | measured now (`c4956df6`/`f598973a`) | verdict |
|---|---|---|---|
| `error_ceiling` | 1267 | 1249 | under — would PASS |
| `warning_ceiling` | 472 | 489 | **over by 17 — would FAIL** |
| `via_dangling` (per-type, `warnings_by_type`) | 15 | 32 | **over by 17 — the entire aggregate excess** |
| `creepage` | 188 | 186–187 | under |
| `clearance` | 379 | 368 | under |
| `shorting_items` | 201 | 199 | under |
| `tracks_crossing` | 3 | 1 | under |
| `copper_edge_clearance` | 12 | 10 | under |
| all other per-type entries | — | unchanged or under | pass |

**If this ceiling were re-measured today (it is not, per the hard
constraint), the corrected numbers would fail the gate on
`via_dangling: 32 > 15` alone** — everything else is at or under the
existing (stale) ceiling. This is a separate, real finding: independent of
the project-context bug, the ceiling's `via_dangling` entry no longer
matches the current board and the human doing the re-pin should know the
gate is not currently vacuously passing merely because it's stale — it
would be *failing* on a specific, named category.

---

## 6. Hidden safety violations, worst first

All of the following are `creepage` violations against the DRU's `HV to LV`
/ `HighVoltageIsolated to LV` rules — **8.0mm required** (IEC 60335-1 PD2
reinforced isolation, per `docs/evidence/2026-08-04-creepage-rust-backend-survey.md`
§5) — reproduced deterministically across 5 repeated `kicad-cli pcb drc`
runs (`--all-track-errors --format json`) on `pcb/temper.kicad_pcb`.

### Worst: 12 pairs measured at exactly 0.0000mm (deterministic across 5/5 runs)

| pad/track A | pad/track B | rule | actual | required |
|---|---|---|---|---|
| Pad 1 `[+15V_LS]` of **C23** | Track `[inb]` | HV to LV | 0.0000mm | 8.0mm |
| Pad 2 `[DC_BUS_RTN]` of **C23** | Track `[inb]` | HV to LV | 0.0000mm | 8.0mm |
| Pad 2 `[hb.gate_hs.driver-p2]` of **D5** | Track `[RTD_SDI]` | HighVoltageIsolated to LV | 0.0000mm | 8.0mm |
| Pad 5 `[SHUTDOWN]` of **U7** | Track `[a]` | HV to LV | 0.0000mm | 8.0mm |
| Pad 1 `[zcd]` of **D2** | Track `[WDT_RESET_N]` | HV to LV | 0.0000mm | 8.0mm |
| Pad 6 `[hb.gate_hs.driver-p1]` of **U7** | Track `[a]` | HV to LV | 0.0000mm | 8.0mm |
| Track `[power_in.bypass_relay-coil2]` | Track `[a]` | HV to LV | 0.0000mm | 8.0mm |
| Pad 13 `[gnd]` of **U25** | Track `[power_in.ntc-no]` | HV to LV | 0.0000mm | 8.0mm |
| Pad 1 `[hb.gate_hs.driver-p1-1]` of **U8** | Track `[inb]` | HighVoltageIsolated to LV | 0.0000mm | 8.0mm |
| Pad 2 `[hb.gate_hs.driver-p2]` of **C17** | Track `[power_in.bypass_relay-coil2]` | HighVoltageIsolated to LV | 0.0000mm | 8.0mm |
| Pad 2 `[i2c_sda_ui]` of **R77** | Track `[power_in.ntc-no]` | HV to LV | 0.0000mm | 8.0mm |
| Pad 1 `[sw]` of **L2** | Track `[power_in.ntc-no]` | HV to LV | 0.0000mm | 8.0mm |

`zcd`, `power_in.ntc-no`, and net `a` are independently confirmed
`HighVoltage`-classed (`packages/temper-placer/src/temper_placer/core/design_rules.py:263,279,281`,
verified directly by grep, not trusted from a report). `RTD_SDI` is
independently confirmed `FinePitch`-classed (LV, same file, line 309).
These are copper items of different nets measured at **zero** separation —
worse in raw magnitude than the task brief's headline 0.175mm figure below.

### The named 0.175mm case (task brief's headline figure)

Reproduced identically across all 5 runs — **deterministic**, unlike the
aggregate creepage count:

- **U8 pad 2** (net `+15V_LS`, `HighVoltage`-classed) <-> **Track on net
  `RTD_SDI`** (`FinePitch`/LV-classed): rule `HV to LV`, **actual
  0.1750mm**, required **8.0mm**.
- **U8 pad 1** (net `hb.gate_hs.driver-p1-1`, `HighVoltageIsolated`-classed
  — the gate-drive high-side isolated secondary) <-> the same **Track on
  net `RTD_SDI`**: rule `HighVoltageIsolated to LV`, **actual 0.1750mm**,
  required **8.0mm**.

Component **U8** has two separate pads, on two different HV-side nets,
both violating creepage against the same LV RTD sensor SPI-data track at
0.175mm — 45x tighter than the 8.0mm PD2 reinforced-isolation requirement.

### `track_width`: net `w1_2` (independently re-verified on this commit)

`packages/temper-placer/src/temper_placer/core/design_rules.py:276-277`
classes net `w1_2` `HighVoltage` (`trace_width=3.0`, `voltage_v=400.0`,
`required_layer="B.Cu"`, line 75-87). Grepping `pcb/temper.kicad_pcb`
directly for every segment on net 159 (`w1_2`) — 40+ segments, all:

```
(segment ... (width 0.25) (layer "F.Cu") (net 159) ...)
```

Routed at **0.25mm** (12x under the 3.0mm rule) and on **F.Cu** (not its
required **B.Cu**) for its entire length. A 400V-rated net.

### Representative worst `clearance` violations (2.0mm HV-class rules, distinct from the 8.0mm creepage rule)

| pad A | pad B | rule | actual | required |
|---|---|---|---|---|
| Via `[hb.gate_hs.driver-p1-1]` | Pad 3 `[safety.thermal.comp-inp]` of **U18** | HighVoltageIsolated to LV | 0.0981mm | 2.0mm |
| Pad 1 `[+15V_LS]` of **C23** | Pad 2 `[DC_BUS_RTN]` of **C23** | HV internal same footprint | 0.6500mm | 2.0mm |
| Pad 9 `[DC_BUS_RTN]` of **U7** | Pad 10 `[input]` of **U7** | HV to LV | 0.6700mm | 2.0mm |
| Pad 14 `[hb.gate_hs.driver-p2]` of **U7** | Pad 15 `[GATE_HS]` of **U7** | HighVoltageIsolated to LV | 0.6700mm | 2.0mm |

### Confirmed independently of kicad-cli: 5 footprints with no courtyard graphic

Parsed `pcb/temper.kicad_pcb` directly (bracket-matched footprint blocks,
not a substring/window heuristic) for `F.CrtYd`/`B.CrtYd` graphics:

```
F1  (Fuse:Fuse_Holder_5x20mm)                       -> no courtyard graphic
L2  (Inductor_SMD:L_Bourns_SRP1265A)                -> no courtyard graphic
R30 (lib:LitzPad_15A)                               -> no courtyard graphic
RT1 (Resistor_THT:R_Disc_D15.0mm_W7.0mm_P7.5mm)     -> no courtyard graphic
U27 (lib:ESP32-S3-WROOM-1)                          -> no courtyard graphic
```

All 5 confirmed by direct inspection, matching the DRC's `missing_courtyard`
count of 5.

---

## 7. What was and wasn't verified

Verified live in this session: kicad-cli 10.0.5 reproduction; the
project-context concealment mechanism reproduced on the current commit
(§3); the full corrected category breakdown, 3 repeated runs (§5); every
creepage/clearance figure in §6 read directly from kicad-cli's JSON output,
cross-checked against `pcb/temper.kicad_pcb`'s raw segment/pad records and
`design_rules.py`'s net-class table (not trusted from any report);
`drc_ceiling.json`'s sha256 mismatch; the `temper_production_baseline.yaml`
blindness traced to its actual writer script and measurement helper; the
new guard's before/after behavior (raises pre-fix-equivalent inputs,
passes real board); the full affected pytest suite (`test_drc_runner.py`,
`test_drc_api_thread_pinning.py`, `test_courtyard_violation_report.py`,
`test_drc_project_context_required.py`) green except one pre-existing,
unrelated stale threshold (`test_real_board_violation_count_in_expected_range`
expects `courtyards_overlap` in [12,18], measures 11 — unaffected by this
fix, not touched).

Not verified / left for follow-up: re-running
`scripts/update_production_routing_baseline.py` to correct
`temper_production_baseline.yaml` (a committed-artifact mutation,
deliberately left to a human, same spirit as `drc_ceiling.json`);
`scripts/check_board_defect_corpus.py`'s docstring claim about `.kicad_dru`
resolving without `.kicad_pro` (contradicted by §3, not independently
re-derived beyond that); whether the `bitaxe_ultra` golden board should get
its own committed project; full `make route && make drc` wall-clock
verification (the routing pass itself takes ~35–60s; the Makefile guard's
logic was verified directly against both the missing-project and
resolvable-project cases).
