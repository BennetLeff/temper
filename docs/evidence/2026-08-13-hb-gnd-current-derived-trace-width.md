# `hb-gnd` current-derived trace width: the mechanism map, and closing the shortfall #1187 flagged

PR #1187 fixed the hyphen-boundary defect that had `hb-gnd`,
`hb.gate_hs-vdd`, and `hb.gate_ls-vdd` falling through
`determine_trace_width`'s keyword classifier to the 0.127mm "standard
signal trace" default. That took `hb-gnd` to 0.508mm and flagged, but did
not fix, that 0.508mm is still 3x-9x short of what this repo's own
IPC-2221B method requires for `hb-gnd`'s real current. This document is
that follow-up.

## 1. The mechanism map (three, not two)

**Live for actual routed copper width:** `determine_trace_width`
(`packages/temper-geometry/src/trace_width_assignment.rs`), called via

```
_pipeline_route.py:674  assign_trace_widths(pathfinding_result, default_width=pcb.design_rules.default_trace_width_mm)
  -> trace_width_assignment.py: assign_trace_widths()
    -> (this fix) _determine_trace_width_ipc_aware()
       -> temper_geometry.determine_trace_width_ipc_aware_py()
          -> Rust determine_trace_width_ipc_aware()
             -> determine_trace_width() [keyword bucket, unchanged]
             -> ipc2221b_current_width::lookup() [current-derived floor, new]
```

This is the *only* call chain that sets the `(width ...)` KiCad emits for
a newly-routed segment. It is a pure function of the net NAME (three
hardcoded buckets: default/power/hv) — before this fix, it never consulted
current, netclass, or any per-net figure.

**Live, but only for DRC clearance math, not width assignment:**
`TEMPER_NET_CLASSES` / `DesignRules.get_rules_for_net(net).trace_width`
(`packages/temper-placer/src/temper_placer/core/design_rules.py`), read
only by `ClearanceMatrix.get_track_width`
(`router_v6/constraints_design_rules.py:264`), whose sole caller is
`add_differential_pair` (spacing math for differential pairs). It never
touches the width the router assigns to ordinary copper. PR #1117 (open,
unmerged, `fix/router-netclass-trace-widths`, verified via
`gh pr view 1117 --json state,mergedAt` → `state: OPEN`, `mergedAt: null`)
proposes wiring `assign_trace_widths` through this table instead of the
keyword cascade — **it is not live on this branch**. Even if it were:
`hb-gnd` has no entry in `TEMPER_NET_ASSIGNMENTS` (confirmed directly,
and independently by #1187's own PR body), so it would still fall through
to whatever the unclassified-net default resolves to, not a
current-appropriate figure — merging #1117 alone would not have fixed
this net.

**A third, independently-invented mechanism, inert for these 3 nets, not
touched by this fix:** `temper-drc-rs::ipc` (`calculate_min_trace_width`,
`net_currents()`, `get_net_current`; exposed to Python as
`temper_placer.core.ipc2152`). This IS a genuine current-derived IPC
calculator — but it is wired only into `placer/cp_sat/gates.py`'s
`StackupGate`, a POST-ROUTE acceptance audit (checks already-routed
copper; never assigns width). Its own 9-net table (`DC_BUS+`, `AC_L`,
`AC_N`, `SW_NODE`, `GATE_H`, `GATE_L`, `+3V3`, `+5V`, `+15V`) does not
include `hb-gnd` or either VDD net, so an unlisted net falls back to
`DEFAULT_SIGNAL_CURRENT` (0.1A) — this gate would not have caught the
under-sizing either, even once routed. It also defaults to 1oz/10°C rise,
diverging from this repo's own documented 2oz-external/20°C-trace/
40°C-pour standard (`docs/hardware/TRACE_WIDTH_CALCULATIONS.md` Sec 1).
`temper-drc-rs` depends on `temper-geometry` (not the reverse), so this
crate cannot call the new registry directly without a dependency cycle.
Left alone deliberately: 0 routed segments for these 3 nets today means
`StackupGate` never fires for them, and rewiring a third crate's
feature-gated wasm surface is out of this fix's time-box. Flagged here as
a distinct follow-up, not duplicated.

**Verdict:** only one mechanism (`determine_trace_width` via
`assign_trace_widths`) is actually authoritative for copper width today.
The netclass table (#1117's target) and the IPC-2152 audit (`StackupGate`)
are real but serve different purposes and don't currently disagree with
it in a way that matters for these 3 nets, because neither currently
constrains their width at all. This fix keeps `determine_trace_width`
authoritative for the *name-based floor*, and adds a new, narrowly-scoped
current-derived layer (`ipc2221b_current_width` +
`determine_trace_width_ipc_aware`) that only ever widens it — current,
not a keyword guess, decides the final number wherever current is known.

## 2. Per-net current-vs-width table

IPC-2221B, `docs/hardware/TRACE_WIDTH_CALCULATIONS.md`'s own method:
`I = k·ΔT^0.44·A^0.725`, external k=0.048, 2oz outer copper.

| Net | Current (derivation) | Required width (40°C rise) | Width before #1187 | Width after #1187 | Width after this fix |
|---|---|---|---:|---:|---:|
| `hb-gnd` | 10A (50%-duty conservative floor, PR #1187) – 22.5A RMS (`elec/src/modules.ato:585-593`, tank RMS current, higher of 22.5A first-harmonic-solve / 20.7A ngspice) | 1.56mm (10A) – **4.77mm (22.5A, worst case)** | 0.127mm | 0.508mm | **4.77mm** (current-derived, worst case) |
| `hb.gate_hs-vdd` | **Not derivable**: 0 nodes in `elec/build/default.net` net code 53 (verified via a fresh `make netlist`) — no component pin resolves to this net name in the current compiled design | n/a (no current to size against) | 0.127mm | 0.508mm | 0.508mm (unchanged; not registered) |
| `hb.gate_ls-vdd` | **Not derivable**: 0 nodes, net code 54, same as above | n/a | 0.127mm | 0.508mm | 0.508mm (unchanged; not registered) |

`elec/src/constraints.ato:8` declares `Constraints.i_max = 25A` while
`modules.ato:585-593` records a 28.7-31.9A tank **peak** against it,
marked UNRESOLVED in-source. That conflict is a peak-current question;
`hb-gnd`'s width here is sized against the RMS/continuous-heating figure
(22.5A), which is the correct IPC-2221B input (ampacity is a thermal/RMS
model, not a peak model) and is unaffected by the peak-vs-i_max conflict.
Not resolved here, per the task's explicit instruction not to.

### Why the two VDD nets are not under-served despite having no derivable current

`hb.gate_hs-vdd` / `hb.gate_ls-vdd` are net codes 53/54 in
`elec/build/default.net` — both declared with **zero nodes**. Tracing the
schematic (`elec/src/modules.ato`): `gate_hs.driver.VDDB` is wired to
`power_15v_ls.vcc`, which resolves to the netlist's `+15V_LS` (net code
7, carrying real nodes: `C23.1`, `U6.11`, `U7.2`) — not to either
`hb.gate_*-vdd` name. `gate_hs.driver.VDDA` (U6 pin 13) does not appear
under *any* net name in the compiled netlist at all — it looks
unconnected. This is very likely a separate, pre-existing
schematic-connectivity anomaly, **not touched by this fix** (out of
scope: this is a trace-width architecture fix, not a schematic fix).

Since no current is derivable for these two names as currently compiled,
they are correctly excluded from the hard, current-derived registry (a
gate must never assert a number it cannot justify from source). As a
sanity check only (not a registry entry): `TRACE_WIDTH_CALCULATIONS.md`
Sec 3.8 ("Gate Driver Supply (15V)": 100mA quiescent + 500mA peak) models
the same physical role these nets' names suggest. At that current
(0.5A, 2oz, 20°C rise), IPC-2221B requires ~0.076mm — far under the
0.508mm they already carry post-#1187. So even under the most
current-hungry plausible reading of their intended role, they are **not**
under-served the way `hb-gnd` is — unlike `hb-gnd`, whose real role
(switching return, not a bias supply) genuinely demands amps, not
milliamps.

## 3. Routing-consequence honesty

**No copper is routed for `hb-gnd` today** (0 segments on the committed
board, confirmed by #1187; unchanged by this fix — `pcb/temper.kicad_pcb`
is not touched here). This is a design-time fix: the next full route will
now attempt to lay `hb-gnd` at 4.77mm instead of 0.508mm.

4.77mm is a severe channel-capacity consumer relative to a board already
reported at 1.31 channel-capacity utilisation on the current two-signal-
layer stackup (PR #1172; PR #1178's proposed 6-layer stackup would bring
that to ~0.657, still not comfortably slack). A single 4.77mm-wide,
worst-case-current-sized trace for one net is a substantial fraction of
typical channel width on this board's geometry. **This fix does not
attempt to make that fit** — per the task's hard constraint, a
safety-required width is never narrowed to protect routability. Whether
4.77mm can be routed at all on the current (or 6-layer) stackup, and if
not what the design response should be (a copper pour instead of a
trace, a wider channel reservation, splitting current across two layers,
or re-litigating the `i_max`/tank-peak conflict) is a **finding for a
human**, not resolved by this PR.

## 4. Verification

- `cargo test --manifest-path packages/temper-geometry/Cargo.toml --lib`: 8400/8400 (8387 baseline + 13 new, 0 regressions).
- `cargo clippy --manifest-path packages/temper-geometry/Cargo.toml --features python -- -D warnings`: clean.
- `cargo clippy --manifest-path packages/temper-geometry/Cargo.toml --no-default-features --features wasm-registry -- -D warnings`: clean.
- `cargo test --manifest-path packages/temper-design-bundle/Cargo.toml --lib`: 33/33 (unchanged).
- `cargo test --manifest-path packages/temper-drc-rs/Cargo.toml --lib`: 3312/3312 (unchanged).
- `make venv-isolate` → `check_stale_extensions.py`: 10/10 fresh, both before this work started and after every rebuild (temper-geometry, temper-design-bundle, temper-drc-rs all rebuilt via `maturin develop --release`; content-hash verdict, not mtime, for all 10 after `write_extension_stamps.py`).
- Built-extension probe (not source) before/after: `determine_trace_width_py("hb-gnd", ...)` unchanged at `(0.508, "Power net requires wider trace...")`; new `determine_trace_width_ipc_aware_py("hb-gnd", ...)` returns `(4.7737..., "IPC-2221B current-derived requirement...")`.
- `scripts/gen_wasm_test_registry.py --crate temper-geometry --check`: up to date after regen.
- `packages/temper-placer/tests/router_v6/test_spatial_drc_cluster_rust_differential.py -k "trace_width or kw_boundary"`: 2/2 pass — the pinned keyword-only oracle (`_oracle_determine_trace_width`) is untouched by this fix (its test corpus contains no name in `ipc2221b_current_width::KNOWN_NET_CURRENTS`) and still tests exactly what it always tested.
- `packages/temper-placer/tests/router_v6/ -k "clearance or trace_width or creepage"`: 796 passed, 3 skipped, 15 xfailed — identical to #1187's own baseline.
- `scripts/check_pyo3_duplicate_registration.py`: 0 duplicates (2 new pyo3 symbols added — `known_net_current_py` family + `determine_trace_width_ipc_aware_py` — none shadow an existing name).
- `scripts/check_oracle_hashes.py`: 167/167 clean — no oracle file touched.
- `scripts/check_unwired_kernels.py`: OK, all new symbols wired (called from `trace_width_assignment.py` and `scripts/check_ipc2221b_trace_width_floor.py`).
- New gate: `scripts/check_ipc2221b_trace_width_floor.py` — passes against the live repo; its own test suite (`scripts/tests/test_check_ipc2221b_trace_width_floor.py`, 7/7 pass) reconstructs the pre-follow-up-fix regression (production wired to the plain keyword classifier) and proves the gate flags it, plus an anti-vacuity case (empty registry = violation, not silent pass).
- Registered in `gate_input_registry._CI_SCRIPT_SURVEY` and wired into `.github/workflows/python-tests.yml` (both path-filter blocks + a job step in `board-provenance-requirements-gates`, alongside the HV netclass coverage gate).
- Pre-existing, unrelated: `test_every_invoked_ci_gate_script_is_registered` was already failing on this branch before this work (naming `check_wasm_covered.py` and `check_router_clearance_floor.py`, confirmed present in `git show f72b9957e:.github/workflows/python-tests.yml`, the branch-point commit) — not touched or worsened by this fix.
- `git status --porcelain` / `git grep -l "^<<<<<<< "`: clean. `pcb/temper.kicad_pcb`, DRU/clearance thresholds, `drc_ceiling.json`: untouched. No `_*_py_oracle.py` file touched.
