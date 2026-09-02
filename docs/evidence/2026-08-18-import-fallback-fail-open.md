# Silent fail-open on `except ImportError` — measurement, fixes, and a gate

Date: 2026-08-18
Branch: `fix/importerror-fail-closed`
Board: `pcb/temper.kicad_pcb` @ `26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b`
(unmodified; verified before and after)

Refresh note (2026-09-01): the measurements below remain historical to the
recorded board hash. The gate was rebuilt on current main and now audits 37
handlers with 12 narrow exemptions. Explicit Python/reference backends in
`clearance_check.py`, `drc_oracle.py`, and loop extraction are preserved and
allowlisted because their degraded state is observable; they are not silent
passing sentinels.

## 0. Count correction: 36 handlers, not 37

`grep -c "except ImportError"` over `packages/temper-placer/src/temper_placer/`
reports 37. One of those is prose inside a docstring
(`physics/gate_drive.py:8`, "every call fell through the
``try/except ImportError``"), not a handler. The AST-accurate count on the
pre-fix tree is **36 handlers**, of which **19 fail open** under the rules
below. Across all of `packages/*/src` the tree now has 39 handlers.

## 1. Priority 1 — the gate-drive check

### 1.1 It was never the `except ImportError` inside `gate_drive.py`

The brief (and the module's own docstring) attributed the permanent
`UNMEASURED` to the guard in `_resolve_gate_loop`. That is not what was
happening. Measured directly:

```
OK   temper_placer.io.kicad_parser.parse_kicad_pcb
OK   temper_placer.core.loop.LoopType
OK   temper_placer.core.loop_extractor.auto_extract_loops
```

All three guarded internal imports resolve. There is **no circular import
and no transitively-missing optional dependency**. The historical
`UNMEASURED` came from `gates.py`'s own
`from temper_placer.physics.gate_drive import ...` failing, because the
module did not exist at all. A prior change created it; the guards inside
it were dead safety nets that masked nothing — but would have masked a
genuine bug the moment one appeared.

### 1.2 What it actually measures now

With the module present and the extensions built, the topology walk
succeeds on the real board for both nets:

| gate net | forward nets | switch | footprint | return net |
|---|---|---|---|---|
| `GATE_HS` | `GATE_HS`, `hb.power_loop.q_high-g` (via R18) | `U4` | `TO-247-3_Vertical` | `SW_NODE` |
| `GATE_LS` | `GATE_LS` | `U5` | `TO-247-3_Vertical` | `hb-gnd` |

Both still return `None`. The reason is **not** a dependency and **not** a
bug in the walk — it is the board:

| net | id | segments | vias |
|---|---|---|---|
| `GATE_HS` | 7 | 81 | 2 |
| `GATE_LS` | 8 | 132 | 1 |
| `SW_NODE` | 22 | **0** | **0** |
| `hb-gnd` | 55 | **0** | **0** |
| `hb.power_loop.q_high-g` | 61 | **0** | **0** |

The board contains **zero zones** (`filled_polygon` count 0), so those nets
have no copper of any kind. **100 of 139 pad-bearing nets carry no copper.**
The gate-drive return conductor does not exist yet, so there is no geometry
to measure. `UNMEASURED` is the correct verdict — but it is now reported
*with its reason* instead of as a bare `None`.

### 1.3 A real violation is provable anyway

Convex-hull area is monotonic under point-set inclusion, so the hull over
the go-arm alone is a valid **lower bound** on the sub-check's own metric
(verified over 300 randomised trials, no counterexample):

```
hull(go) <= hull(go ∪ return)   for any return routing
```

Measured on the real board:

| gate net | go-arm hull area | threshold | verdict |
|---|---|---|---|
| `GATE_HS` | 96.4727 mm² | 500 mm² | inconclusive (return arm may push it over) |
| `GATE_LS` | **1131.3443 mm²** | 500 mm² | **VIOLATION — ≥ 2.26× the limit** |

**`GATE_LS`'s gate-drive loop exceeds the 500 mm² limit by at least 2.26×,
and no routing of the return path can bring it back under**, because adding
points can only grow the hull. On a board switching 44–50 kHz this is a real
gate-drive loop-inductance finding, and it is the first thing this sub-check
has ever produced. Nothing was tuned, relaxed, or suppressed to reach it;
the 500 mm² threshold and the kernel are untouched.

`GATE_LS`'s routed extent is x∈[51.75, 100.07], y∈[159.33, 183.395] mm —
a ~48 × 24 mm sprawl for a gate net.

### 1.4 Sub-check 1 is also permanently UNMEASURED

`commutation_loop_area` returns `None` because `auto_extract_loops` finds
**0 loops of any type** on this board, consistent with
`docs/evidence/2026-08-11-loop-area-cycle-basis-order-spike.md`. Separately,
the Rust extractor *raises* on the real board —
`No bus capacitor path between power_in.q_relay_drv-g and gnd` — and
`loop_extractor.py:510` warns and falls back to the Python extractor. So the
Rust path is not the one running today.

### 1.5 The false-zero

`loop_area.py::_convex_hull_area` ended `except Exception: return 0.0`. On a
loop-**area** check compared as `area > 2000 mm²`, `0.0` is not a neutral
placeholder — it is the most-passing value available. A throwing kernel
reported a perfect board. Now raises `MeasurementError`.

## 2. Port baselines (for the blocked Rust port)

**GEOS/shapely is NOT in the computation path of either module.** Traced
every shapely frame entered during both calls:

- `loop_area.commutation_loop_area` → **no shapely frames at all**.
- `gate_drive.gate_drive_loop_area` → shapely frames only from
  `<frozen importlib._bootstrap>:_call_with_frames_removed` executing module
  and class bodies (`CollectionOperator`, `PreparedGeometry`, `SplitOp`) —
  i.e. **import-time side effects, not computation**.

This is the opposite of the `_ground_plane.py` blocker (868/907 keepout
vertices emitted verbatim from GEOS). Both modules are **pure arithmetic
over extracted geometry plus two Rust kernels**, so a faithful port is
possible.

**Determinism: confirmed identical across 3 consecutive runs** (full
snapshot JSON-serialised and compared).

### Inputs

Single accessor: `temper_placer.io.kicad_parser.parse_kicad_pcb(Path)` →
`ParseResult(board, netlist, pads, traces, vias, warnings, has_warnings)`.
Fields read: `result.netlist.components[].{ref, footprint, pins[]}`,
`Pin.{name, net}`, and `result.traces[].{start, end, net}`. The board has
168 components, 4553 traces, 169 vias, 139 pad-bearing nets, 36 nets with
routed copper, 0 zones.

### Outputs (full precision)

```json
{
  "gate_drive": {
    "GATE_HS": {"forward_nets": ["GATE_HS", "hb.power_loop.q_high-g"],
                "switch_ref": "U4", "return_net": "SW_NODE",
                "go_segments": 81, "return_segments": 0,
                "go_unique_endpoints": 82,
                "go_endpoint_sha256": "75657e251bd999d48822b3c90a2f7b1e",
                "area_mm2": null, "spacing_mm": null},
    "GATE_LS": {"forward_nets": ["GATE_LS"],
                "switch_ref": "U5", "return_net": "hb-gnd",
                "go_segments": 132, "return_segments": 0,
                "go_unique_endpoints": 133,
                "go_endpoint_sha256": "633f72c7c0c7221d8a3968b95a721097",
                "area_mm2": null, "spacing_mm": null}
  },
  "loop_area": {"loops_found": 0, "commutation_area_mm2": null}
}
```

### Kernel baselines (real board data, 3 runs identical)

These exercise the two Rust kernels on real geometry and are the usable
numeric oracle until the return path is routed. **They are kernel
baselines, not sub-check verdicts.**

| call | result |
|---|---|
| `convex_hull_area_py(GATE_HS go-arm, 82 pts)` | `96.47270000000022` |
| `convex_hull_area_py(GATE_LS go-arm, 133 pts)` | `1131.3442699999998` |
| `min_hv_lv_trace_clearance(GATE_HS, GATE_LS)` | `27.832586117714612` |

A port must reproduce these bit-for-bit, and must reproduce the `None`
outcomes with their reasons.

## 3. The failure taxonomy now enforced

`None` used to mean three unrelated things. Split into:

1. **Broken install / build** — missing first-party module or Rust
   extension → `ImportError` naming the package and the command.
2. **Measurement precondition failure** — unparseable board, throwing
   kernel, throwing extractor → `MeasurementError`.
3. **Genuinely unmeasurable topology** → still `None`, but logged at
   WARNING with the specific reason (which net, how many segments).

`PhysicsGate.check()` maps all three to `UNMEASURED` and never to `CLEAN`,
so this changes the diagnosis, not the verdict.

## 4. The gate

`scripts/check_import_fallback_hygiene.py`, wired into the `hygiene-gates`
CI job, allowlist at `scripts/import_fallback_allowlist.yaml`, 26 tests in
`scripts/tests/test_check_import_fallback_hygiene.py`.

- **R1** — a handler catching `ImportError` around a **first-party** import
  (prefixes read from `packages/*/pyproject.toml`, so they cannot drift)
  must terminate by raising.
- **R2** — no `ImportError` handler may exit via
  `None`/`[]`/`{}`/`0`/`False`/`""`/`pass`/`continue` **silently**; it must
  raise, or log/warn/record the degradation.

**Anti-vacuity: run against the pre-fix tree the gate reports 19 violations**,
including both `physics/gate_drive.py:165` and `physics/loop_area.py:57`.
It fails closed on: <5 first-party packages discovered, zero source files,
zero handlers found, and unparseable source. Allowlist entries require a
reason, and entries that stop matching are reported STALE and fail the gate.

### A rule exception worth recording

R1 as first drafted flagged `placer/cp_sat/gates.py`, which does:

```python
except ImportError as exc:
    return GateResult(GateStatus.UNMEASURED, error_message=f"gate-drive: {exc}")
```

That is **correct** — `UNMEASURED` is a distinct non-passing state and the
reason travels with it. The refined rule therefore treats *binding the
exception and referencing it* as equivalent to re-raising: the evidence
survives. Likewise `validation/gate_input_registry.py` appends the failure
to an `errors` list and then `continue`s, so R2 tests for **silence**, not
for the keyword. Without these two carve-outs the gate would have been
`# noqa`'d within weeks.

## 5. Sites fixed

| file | was | now |
|---|---|---|
| `physics/gate_drive.py` | `return None` ×1, `except Exception: return None` ×2 | raise + reasoned WARNING |
| `physics/loop_area.py` | `return None` ×3, `return 0.0` | raise + reasoned WARNING |
| `core/loop_extractor_rs.py` | warn → `return None` → different extractor | raise (ImportError path only) |
| `validation/drc_oracle.py` | `_HAS_RUST_DRC = False` → Python DRC path | raise |
| `router_v6/clearance_check.py` ×2 | flags → Python clearance backend | raise |
| `router_v6/_pipeline_verify.py` | bare `return` → DRC checks never registered | raise |
| `deterministic/stages/_phase_core.py` | `pass` → **HV DRC fence never ran** | raise |
| `placer/cp_sat/_loop_routing.py` | `placed = raw_pcb` → **unplaced board sent downstream** | raise |
| `profiling/pipeline_metrics.py` ×3 | zero timings / `return []` recorded as measured | raise |

## 6. Two other findings

- **`TEMPER_REQUIRE_RUST_DRC` is dead.** Set in 9 places across
  `python-tests.yml` and `r9-evidence.yml`, with a comment claiming it
  "makes this step -- and the differential" fail without Rust DRC. **No
  Python code anywhere reads it.** The guard is vacuous.
- **`scripts/check_venv_integrity.py` always fails from a nested
  worktree.** `classify_path` checks `other_worktrees` first and by design
  lets that win over the "under repo_root" test. When `repo_root` *is*
  `.claude/worktrees/agent-X`, the main checkout is an "other worktree" and
  every legitimate path under `repo_root` is also under it, so all 11
  editable installs report VIOLATION. Isolation was verified correct by
  other means (`temper_placer.__file__` resolves into this worktree;
  `make extensions-check` reports 10/10 fresh). Fix would be to match the
  *longest* worktree prefix, not the first.

## 7. Not done in this pass

- No Rust porting (explicitly out of scope). Port-needed list: the sites in
  §5 that route to a Python implementation —
  `core/loop_extractor_rs.py`, `validation/drc_oracle.py`,
  `router_v6/clearance_check.py`.
- 7 allowlisted sites, 4 of them owned by other in-flight changes.
- The `GATE_LS` loop-area violation in §1.3 is reported, not remediated.
- 6 pre-existing `test_physics_gate.py` creepage failures
  (`copy_kicad_project_sidecar`) reproduce identically on unmodified
  source; not caused by this change.
