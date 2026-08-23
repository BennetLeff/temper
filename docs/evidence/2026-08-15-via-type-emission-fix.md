<!-- provenance: commit=dabbeaf73c678be2aa969d30f547eeda41d18c07 dirty=UNKNOWN -->
---
module: temper-orchestration / temper-placer router_v6
tags: [router, kiCad, via, drc, sexpr, emission, honesty-audit]
problem_type: correctness-bug
---

# 2026-08-15 — Router via-type emission fix (phantom through vias)

## Summary

Every via the router emitted carried **no `blind`/`buried`/`micro` type
token**, so KiCad read every one as a **THROUGH via** piercing all six
copper layers — regardless of the `(layers "F.Cu" "In3.Cu")` pair the
router wrote. The honesty audit (agent 58) found all 74 vias on the
routed scratch board in this state. This change makes the router emit the
correct type token for every layer-pair via, and makes the pad-
connectivity audit's via model read the type token, so the two agree with
KiCad's file-format semantics.

Verified end-to-end: on agent 58's exact audited board, adding the type
tokens the fixed router now emits removes **6 provable phantom shorts**
(other copper strictly outside the declared pair) plus **22 phantom
hole-clearance violations** (886 → 858 total DRC errors), and reveals 6
dangling vias that the phantom through-copper was masking.

## Root cause

The router's live emission core is
`packages/temper-orchestration/src/pipeline_route.rs` →
`emit_route()` (the `router_v6/_adapter_convert.py` shim delegates to it
via `run_write_route_segments`). The via loop rendered:

```
(via (at X Y) (size S) (drill D) (layers "F.Cu" "In3.Cu") (net N) (tstamp T))
```

with **no type token**. Per the KiCad s-expression board format
(`dev-docs.kicad.org/en/file-formats/sexpr-pcb/`, Track Via):
"the optional type attribute specifies the via type. Valid via types are
`blind` and `micro`. **If no type is defined, the via is a through hole
type**." KiCad's parser (`pcb_io_kicad_sexpr_parser.cpp`, `parsePCB_VIA`)
defaults to `VIATYPE::THROUGH` and accepts the bare tokens `blind`,
`buried`, `micro`.

The router's `Via` model carries `from_layer`/`to_layer` (the *intended*
pair, derived from the actual routed layer transition by
`temper-geometry::via_clearance::via_layer_pair_py`), but the emission
never translated that pair into a type token. This was an **emission bug,
not an intentional limitation**: the router's own occupancy-grid marking
(`astar_grid._mark_route_blocked`) and the pad-connectivity audit model
vias as pair-restricted, i.e. the design intent is blind vias for
outer↔inner transitions.

## Distribution on the audited board

`temper_routed_nlayer.kicad_pcb` (agent 58's audit artifact, 74 vias):

| pair | count | correct token |
|---|---|---|
| F.Cu ↔ In3.Cu | 32 | `blind` |
| F.Cu ↔ In4.Cu | 26 | `blind` |
| In3.Cu ↔ B.Cu | 2 | `blind` |
| In4.Cu ↔ B.Cu | 4 | `blind` |
| F.Cu ↔ B.Cu | 10 | (none — through) |

## Fix

### 1. Emission core (Rust) — `temper-orchestration/src/pipeline_route.rs`

New `via_type_token(from_layer, to_layer)` helper + token in the via
format string. Classification (KiCad's canonical outer copper layers are
always `F.Cu`/`B.Cu`):

- `F.Cu ↔ B.Cu` → through → **no token** (byte-identical to pre-fix
  output for this pair)
- exactly one outer layer → `blind`
- two inner layers → `buried`
- same layer both ends → through (degenerate; total classification, keeps
  pre-fix emission)

The `(via blind (at ...))` form is what kiutils and KiCad itself write,
and exactly what `parsePCB_VIA` accepts.

### 2. Pinned oracle — `tests/router_v6/_adapter_convert_py_oracle.py`

Byte-identical `_via_type_token()` + emission change, so the Rust core
and its pinned oracle stay bit-for-bit in sync (the differential suites
pin them to each other). This is a deliberate re-pin: the oracle is the
emission specification, and the specification had the bug. The registry
diff (`scripts/oracle_hashes.json`, exactly one entry) and the body
digest pin (`_BODY_DIGESTS` in `test_pipeline_route_rust_differential.py`)
were updated in the same commit.

### 3. Audit via model — `router_v6/pad_connectivity_audit.py`

`_parse_segments_and_vias` now reads the via type token (`blind`/`buried`/
`micro`):

- **token present** → via connects exactly its declared pair
- **no token** → THROUGH → `layers=()` (the existing `CopperVia` "every
  layer" convention)

Before this change the audit modeled *every* via as pair-restricted,
which under-reported real connectivity on boards whose vias were actually
through (agent 58: under-reports by 2). It also made the audit wrong for
the fixed router output's *opposite* direction — pair-restricted vias
whose declared pair is the only connectivity. The type-token read makes
the audit truthful for both file states.

## Verification

### Kernel + differential

- `cargo test --no-default-features -p temper-orchestration --lib` —
  3 new `via_type_token` unit tests pass (9 total in the module).
- `pytest tests/router_v6/test_via_output_writer.py` — 3 new tests:
  `blind` token for F.Cu↔In3.Cu, `buried` for In1.Cu↔In3.Cu, no token for
  F.Cu↔B.Cu.
- `pytest tests/router_v6/test_pad_connectivity_audit.py` — new test:
  no-token via → all layers; `blind` → pair; `buried` → pair.
- Full adapter/pipeline differential + metamorphic + PBT suites:
  **145 passed** (Rust vs oracle byte-identical with the fix).
- Oracle content-hash gate: 167/167 OK.
- `cargo clippy --all-features --all-targets -- -D warnings`: clean.
- `scripts/import_linter_gate.py`: PASSED.
- Ruff: zero new findings (all 8 findings on the touched files are
  pre-existing on origin/main, verified against a clean base worktree).
- Pre-existing failures (identical on origin/main, unrelated): 6 router_v6
  real-board routing tests (documented power/ground policy-mismatch +
  `SkeletonGraph` fixture issues), 4 io/ tests (footprint-dir / netclass
  fixture drift), 4 unused-import clippy errors under
  `--no-default-features`.

### DRC controlled experiment

Same copper, one byte-level difference: the type tokens the fixed router
now emits (64 `blind` on the pair vias, none on the 10 through vias).
Both files DRC'd with `kicad-cli pcb drc --all-track-errors` under the
same `.kicad_pro` sidecar (single-threaded env, the repo's reproducible
measurement convention):

| metric | baseline (untyped) | typed | Δ |
|---|---|---|---|
| total errors | 886 | 858 | **-28** |
| shorting_items | 107 | 101 | **-6** |
| hole_clearance | 184 | 162 | **-22** |
| clearance | 499 | 499 | (saturated at ERROR_LIMIT 499) |
| via_dangling (warnings) | 2 | 8 | +6 |

The 6 shorting_items eliminated are precisely the provably-phantom ones:
a via-involved short whose other copper sits strictly **outside** the
via's declared pair — e.g. a via declared `F.Cu ↔ In4.Cu` shorting a
`bias` track on `B.Cu`, and a via declared `F.Cu ↔ In3.Cu` shorting `fb`
tracks on `In4.Cu`. All six vanish; zero out-of-pair shorts remain in the
typed file. (Agent 58's "16 phantom" figure used a broader classification
window / different board snapshot; the mechanism and direction match
exactly.)

The 22 hole_clearance delta is the same phantom mechanism: an untyped via's
drill passes through out-of-pair layers, colliding with copper there.

**The +6 via_dangling warnings are honest signal, not noise**: 6 vias
(blind pairs like `B.Cu ↔ In3.Cu`) were only ever "connected" through the
phantom through-copper. With honest blind vias they dangle — a genuine
router layer-assignment follow-up that the bug was masking. The emission
fix is correct regardless; these are the router's real remaining defects
in via placement, newly visible.

### Batched route — OUTSTANDING (OOM)

A fresh `scripts/route_board.py` run was attempted twice and **OOM-killed
both times** (global OOM at ~50 GB anon-rss — the documented Stage 3 SAT
memory blowup, `journalctl` kernel OOM record, pid 636431). Per the
session rules the run was not relaunched to compete for the memory that
killed it. The kernel-level emission proof + the controlled DRC experiment
cover both halves of the verification; the fresh-route re-measurement
remains outstanding until the Stage 3 memory issue (handoff §6) is fixed
or the machine is quiet.

## Latent same-pattern risk (documented, not changed)

Two legacy exporters — `io/kicad_exporter.py::add_vias_to_board` and
`io/_write_tracks.py::write_routes_to_pcb` — create kiutils `Via` objects
from `TraceVia.layers` without setting `type`. They have **no production
callers** (verified: only test files reference them), so they were left
unchanged (YAGNI); any future consumer that re-activates them must emit
the type token too.

## Files changed

- `packages/temper-orchestration/src/pipeline_route.rs` — emission fix,
  `via_type_token`, unit tests, wasm test registry
- `packages/temper-placer/tests/router_v6/_adapter_convert_py_oracle.py` —
  oracle mirrored + `_via_type_token`
- `packages/temper-placer/tests/router_v6/test_pipeline_route_rust_differential.py` —
  `_BODY_DIGESTS` re-pin
- `packages/temper-placer/src/temper_placer/router_v6/pad_connectivity_audit.py` —
  type-token-aware via parse
- `packages/temper-placer/tests/router_v6/test_via_output_writer.py` — 3 new tests
- `packages/temper-placer/tests/router_v6/test_pad_connectivity_audit.py` — 1 new test
- `scripts/oracle_hashes.json` — re-pin (1 entry)
