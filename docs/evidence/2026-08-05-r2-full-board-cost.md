<!-- provenance: commit=f2c5af948ba2264b3fc05d1f7e6e63ce4d8fc59a dirty=false -->

# R2 — full-board rule pass: per-case CPU and peak RSS (U4 measurement)

**Date:** 2026-08-06

**Task:** Unit U4 of
`docs/plans/2026-08-05-001-feat-wasm-tier-phase0-plan.md`.  Measure
per-case CPU cost and peak resident memory for a full-board pass of
every rule in every family in `packages/temper-drc-rs/src/rules/`,
natively, against `pcb/temper.kicad_pcb`.

**Status of the input pipeline (plan STEP 1).** The Rust rules consume a
`BoardState` struct.  The only path from a production `.kicad_pcb` file
to a `BoardState` is through the Python bridge
(`board_py_bridge::build_board_state`), which is gated on the default-on
`python` feature.  No non-Python deserialization path existed before this
measurement.  To decouple the measurement process from Python (so that
peak RSS reflects the rules, not the interpreter), this task:

1. Added `serde::Deserialize` to `BoardState` and its 13 constituent
   types in `board.rs`, and enabled `geo/use-serde` in `Cargo.toml`
   (commit `f2c5af948` + patches on branch `wasm/u4-full-board-cost`).
2. Added `serialize_board_state` as a pyfunction in `lib.rs` so the
   Python bridge can capture its output as a JSON string.
3. Wrote `tools/wasm/r2_serialize_board.py` — parses the KiCad file,
   serializes `BoardState` to JSON via the bridge (run once).
4. Wrote `packages/temper-drc-rs/examples/r2_full_board_pass.rs` — reads
   the JSON, runs all 27 rules, measures per-case CPU and peak RSS in a
   pure-Rust process (`--no-default-features`).

The board is serialized once; every measurement sample is a fresh
pure-Rust process.

---

## Headline

**The full-board Rust rule pass consumes ~3 MB peak RSS — 2.3% of the
128 MiB Cloudflare Workers isolate limit.  The whole pass completes in
~1.5 ms wall time (median, N=32).  The verdict is PASS with ample
headroom.**

---

## Machine and tool context

| Field | Value |
|---|---|
| Machine | Apple M2 Pro, 12 cores, 32 GB RAM |
| OS | macOS 26.5.1 (build 25F80), arm64 |
| Commit | `f2c5af948ba2264b3fc05d1f7e6e63ce4d8fc59a` (= `origin/main`), + U4 patches on branch `wasm/u4-full-board-cost` |
| Worktree | `/private/tmp/wasm-u4`, own `.venv` via `uv sync --package temper-placer` |
| Rust | stable-aarch64-apple-darwin (edition 2024) |
| Board under test | `pcb/temper.kicad_pcb`, sha256 `1cce4a0872051675b0339de3378ff7ec2c16bb4b035c999dfa408dec5ecbc3f6`, 1,032,079 bytes |
| `ru_maxrss` unit | bytes (Darwin / macOS) |
| Isolate limit | 134,217,728 bytes (128 MiB, Cloudflare Workers) |

---

## 1. What was measured and what was not

### Measured

- **Full pass of all 27 rules** from `create_default_registry()` over
  the production board's component and net data:
  - 169 electrical components, 0 mechanical
  - 110 nets, 1 net class ("Default")
  - Empty traces, vias, and zones (the KiCad parser does not populate
    these fields in the `board_dict` consumed by the bridge — see §4)
- **Per-rule CPU cost** (ns/case): `std::hint::black_box` on inputs and
  outputs, warm-up of `iters/10`, iters auto-scaled by probe cost
- **Whole-pass wall time**: one `reg.run_all()` call
- **Peak resident memory**: `getrusage(RUSAGE_SELF).ru_maxrss`, read
  once at process exit, normalized to bytes
- **N = 32 fresh processes**, median and full observed range

### Not measured

- **Rules that need trace/via/zone data** (routing checks, via spacing,
  trace clearance, zone containment, stitch via density, etc.) execute
  but return empty results because the production board's routing data
  is not present in the `BoardState` produced by the bridge (see §4).
  Their per-case cost reflects the fixed overhead of the `check()`
  method (bounds checks, empty-iterator returns), not a realistic
  routing workload.
- **In-isolate RSS** (WASM linear memory + runtime overhead).  This
  measurement is native-only.  The plan's §U4 protocol states that a
  native pass consuming >50% of 128 MiB should be treated as FAIL
  pending an in-isolate measurement.  At 2.3% this is not triggered.
- **The occupancy grid** (the subject of the existing `r2_cost_model.rs`
  projection).  The Rust rules do not allocate an occupancy grid;
  `r2_cost_model.rs` computes a *hypothetical* grid size arithmetically.
  The memory figures there are projections for a data structure that
  does not yet exist.  The RSS reported here is the *actual* memory
  consumed by the rules as they exist today.

---

## 2. Full-board pass: whole-pass wall time and RSS (N=32)

### Whole-pass wall time

```
Median:  1.51 ms  (1,513,812 ns)
Range :  1.44 ms – 5.61 ms  (1,439,541 – 5,613,708 ns)
```

The bimodal distribution (half the samples ~1.5 ms, half ~3.5 ms, one
outlier at 5.6 ms) is consistent with the macOS process scheduler and
the M2 Pro's heterogenous core layout.  The fast samples likely ran on
a performance core; the slower ones on an efficiency core or contended
with background `make extensions` builds.

### Peak RSS

```
Median:  3,080,192 bytes  (2.94 MiB)
Range :  3,014,656 – 3,129,344 bytes  (2.88 – 2.98 MiB)

Verdict:  PASS  (2.3% of 128 MiB isolate limit)
```

The RSS is dominated by the binary's own code and data segments plus the
deserialized `BoardState`.  The `rss_max` across all 32 samples is
3,129,344 bytes — **42× below the 128 MiB limit and 21× below the 50%
warning threshold (64 MiB)**.

### Violations

```
Errors:   79  (deterministic across all 32 runs)
Warnings: 38  (deterministic)
```

Violation counts are deterministic at N=32.

---

## 3. Per-rule-family CPU cost (median ns/case, N=32)

| Family | Rules | Median ns/case | Dominant rule |
|---|---|---|---|
| `drc` | 8 | 1,210.7 | `drc_clearance` 1,216,308 ns |
| `safety` | 6 | 6.2 | `safety_hv_lv_separation` 60,002 ns |
| `dfm` | 4 | 181.8 | `routing_tht_thermal_relief` 431 ns |
| `emc` | 6 | 4.9 | `emc_noise_coupling` 27,100 ns |
| `erc` | 3 | 1.9 | `erc_floating_pins` 15,938 ns |

### Per-rule detail (median ns/case, N=32)

| Rule | Category | Median ns |
|---|---|---|
| `drc_clearance` | drc | 1,216,308 |
| `drc_courtyard` | drc | 59,356 |
| `safety_hv_lv_separation` | safety | 60,002 |
| `drc_component_overlap` | drc | 49,643 |
| `emc_noise_coupling` | emc | 27,101 |
| `safety_creepage` | safety | 18,601 |
| `erc_floating_pins` | erc | 15,938 |
| `emc_ground_plane` | emc | 13,114 |
| `drc_trace_clearance` | drc | 2,313 |
| `routing_tht_thermal_relief` | dfm | 431 |
| `placement_wave_solder_keepout` | dfm | 356 |
| `drc_zone_containment` | drc | 109 |
| `routing_power_pad_teardrop` | dfm | 8 |
| `routing_pad_entry_width` | dfm | 8 |
| `routing_partial_discharge` | safety | 7 |
| `safety_isolation` | safety | 5 |
| `routing_stitching_via_density` | emc | 5 |
| `routing_split_plane_crossing` | emc | 5 |
| `routing_parallel_run` | emc | 4 |
| `drc_via_spacing` | drc | 4 |
| `placement_thermal_via_count` | drc | 4 |
| `emc_loop_area` | emc | 4 |
| `routing_copper_pullback` | drc | 4 |
| `routing_isolation_barrier` | safety | 4 |
| `erc_net_connectivity` | erc | 2 |
| `erc_power_domain` | erc | 1 |

Rules below `drc_trace_clearance` are effectively no-ops on the current
board state (empty traces/vias/zones).  Their sub-500 ns figures
represent the fixed cost of the `check()` method entry, bounds checks,
and empty-iterator return.

`drc_clearance` dominates at 1.2 ms because it performs an O(n²)
all-pairs component distance computation over 169 components (14,196
pairs), each involving polygon edge-to-edge distance via the `geo`
crate.

---

## 4. U5: memory-strategy verdict (Q7 resolution table)

The plan's Q7 asks: for each grid resolution in {1.0, 0.5, 0.1, 0.05,
0.01} mm, the measured peak RSS and the cheapest memory strategy that
brings it under 128 MiB.

**The Rust rules do not allocate an occupancy grid at any resolution.**
The rules iterate components, traces, vias, and zones directly; the
largest in-memory structure is the `Vec<Component>` (169 entries, each a
few hundred bytes).  The 128 MiB limit is **not the binding constraint**
for the rules as they exist today — the binding constraint is the
O(n²) clearance check's CPU time, which at 1.2 ms is already cheap.

The occupancy grid is a *hypothetical* structure projected in
`r2_cost_model.rs`.  If it were allocated:

| Cell (mm) | Cells (100mm board) | Bytes/layer (i32) | 6 layers | vs 128 MiB |
|---|---|---|---|---|
| 1.0 | 10,000 | 39.1 KiB | 0.23 MB | — |
| 0.5 | 40,000 | 156.3 KiB | 0.94 MB | — |
| 0.1 | 1,000,000 | 3.8 MB | 22.9 MB | — |
| 0.05 | 4,000,000 | 15.3 MB | 91.6 MB | — |
| 0.01 | 100,000,000 | 381.5 MB | 2,289.1 MB | OVER |

**Verdict: "No memory strategy is required for Phase 1."**  Even if a
naive `[i32; N]` grid were allocated, the production resolution of
1.0 mm (used at 131 call sites per the plan) would consume 0.23 MB —
well within the limit.  Q7's four candidates (bitmap packing, region
sharding, per-row RLE, hash-consed quadtree) become live only if a
future phase introduces a sub-0.05 mm grid, which the plan's own §U5
notes is a Phase 2 concern and not this plan's to schedule.

**One caveat on the "no traces" gap.**  The current measurement does
not include routing data (traces, vias, zones) in the `BoardState`
because the Python bridge's `build_board_state` path does not populate
them.  If routing data were present, the wall time would increase
(because routing rules would do real work) and the RSS would increase
(because `Vec<TraceSegment>`, `Vec<Via>`, `Vec<CopperZone>` would have
content).  The trace/via/zone data in `pcb/temper.kicad_pcb` is O(1,000)
segments, not O(1,000,000), so the RSS impact is bounded.  This does
not change the verdict, but it should be re-measured if a future bridge
revision populates those fields.

---

## 5. What could not be measured and why

- **Rules that depend on trace/via/zone data** (routing family, trace
  clearance, via spacing, zone containment, stitch via density, parallel
  run, etc.) execute but return empty results.  Their per-case cost is a
  lower bound on the true routing workload.  The gap is a limitation of
  the `board_py_bridge` path, which does not map KiCad routing data into
  the `BoardState`.  This is recorded as a scope discovery, not a
  measurement failure.  See §6 below for why this gap exists and what
  would close it.
- **In-isolate (WASM runtime) RSS.**  Measured natively only.  At 2.3%
  of the 128 MiB limit, the native headroom is so large that in-isolate
  overhead cannot plausibly close the gap.  Re-measuring in-isolate is
  deferred to when a `.wasm` artifact exists (U1's rung 3).
- **The `validation.rs` kernels** (10 kernels, 922 lines).  These are
  gated on `#[cfg(feature = "python")]` and are not part of the
  `--no-default-features` rule pass measured here.  They are also not
  part of `create_default_registry()` — they are separate PyO3 entry
  points.  Their cost is not measured here, consistent with the plan's
  §5 item 1 ("the landed R2 measurement is narrower than R2's text").

---

## 6. The input-pipeline gap (plan STEP 1 discovery)

The `board_py_bridge::build_board_state()` function maps a Python dict
with keys `board`, `components`, `nets`, `net_classes`, `net_class_rules`
→ Rust `BoardState`.  It does **not** read `traces`, `vias`, or `zones`
from the dict — the bridge maps only placement and net topology data.

The upstream parser (`temper_placer.io.kicad_parser`) parses traces,
vias, and zones from the `.kicad_pcb` file into `ParsedPCB.traces`,
`.vias`, and `.copper_zones`.  But neither `ci_closure_test.py` nor
`calibrate_drc_ceiling.py` maps them into the `board_dict` they pass to
`run_drc()`.  So the production call path never populates routing data.

**What would close this gap:**
1. Extend the `board_dict` construction in the Python bridge caller to
   include `traces`, `vias`, and `zones` keys.
2. Extend `board_py_bridge::build_board_state()` to read those keys and
   populate the corresponding `BoardState` fields.

This is a known limitation of the current bridge, not a bug in the
measurement.  Closing it is Phase 1 scope (per U2's un-gating work).

---

## 7. Reproducibility

### Serialize the board (once)

```bash
uv run python3 tools/wasm/r2_serialize_board.py --output /tmp/board.json
# Records board hash: sha256 of pcb/temper.kicad_pcb
```

### Build the benchmark

```bash
cargo build --release --no-default-features \
  --manifest-path packages/temper-drc-rs/Cargo.toml \
  --example r2_full_board_pass
# Binary at: target-shared/release/examples/r2_full_board_pass
```

### Run the sampling driver (N=32)

```bash
uv run python3 tools/wasm/r2_sample.py \
  --binary target-shared/release/examples/r2_full_board_pass \
  --board /tmp/board.json \
  --samples 32
```

### Single-run verbose mode

```bash
./target-shared/release/examples/r2_full_board_pass /tmp/board.json
```

---

## 8. Changes to production source

The following changes were made on branch `wasm/u4-full-board-cost` to
enable this measurement.  They are **not** on `origin/main` and are
not proposed for merge in this unit — they are measurement scaffolding:

| File | Change | Purpose |
|---|---|---|
| `packages/temper-drc-rs/src/board.rs` | Added `Deserialize` to 14 type derives; added `#[serde(transparent)]` to 3 newtypes | Enables pure-Rust deserialization of BoardState from JSON |
| `packages/temper-drc-rs/Cargo.toml` | `geo = { version = "0.28", features = ["use-serde"] }` | Enables serde for geo types (Point, Line, Polygon) |
| `packages/temper-drc-rs/src/lib.rs` | Added `serialize_board_state` pyfunction | Captures Python bridge output as JSON |
| `packages/temper-drc-rs/src/rules/mod.rs` | Added `pub fn rules()` accessor on `RuleRegistry` | Allows per-rule iteration in benchmarks |

## UNVERIFIED

- **In-isolate (WASM) RSS.**  See §5.
- **Routing-data-inclusive cost.**  See §4 caveat and §6.
- **Linux RSS.**  Measured on macOS only.  The `ru_maxrss` normalization
  (`bytes` on Darwin, `KiB → bytes` on Linux) is implemented but
  untested on Linux.

## Sources

- `docs/plans/2026-08-05-001-feat-wasm-tier-phase0-plan.md` — §U4, §U5,
  §5 item 1
- `packages/temper-drc-rs/examples/r2_full_board_pass.rs` — the
  benchmark binary (new in this task)
- `tools/wasm/r2_sample.py` — the sampling driver (new in this task)
- `tools/wasm/r2_serialize_board.py` — the board serialization helper
  (new in this task)
- `packages/temper-drc-rs/src/board.rs` — BoardState types (Deserialize
  added)
- `packages/temper-drc-rs/src/board_py_bridge.rs` — the Python→Rust
  bridge (not modified; gap documented in §6)
- `packages/temper-geometry/examples/r2_cost_model.rs` — the existing
  cost model for geometry kernels and grid projection
- `scripts/ci_closure_test.py:140-280` — the existing Python→Rust DRC
  call path
- `docs/evidence/2026-08-04-board-regeneration-cost.md` — the evidence
  doc format this document follows
