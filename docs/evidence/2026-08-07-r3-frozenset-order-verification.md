<!-- provenance: commit=00ec5f94a dirty=false -->

# R3 — Board producer + frozenset-order caveat verification

**Date:** 2026-08-07
**Base:** `origin/main` @ `00ec5f94a` (branch `feat/wasm-tier-phase0`, HEAD
`67a99bf8f`)
**Base assertion:** `scripts/assert-base.sh origin/main` exited 0.

This document records the R3 (board regeneration producer) verification for
the WASM tier Phase-0 execution brief: identify the board-writer entry point,
verify the producer requirement, and empirically check the writer's
frozenset-order caveat (is regeneration byte-nondeterministic?).

---

## 1. Producer status — landed on `origin/main` via #904

The R3 CI producer (plan `2026-08-05-001` §U7) is **already on `origin/main`**
(merge #904, commit `3dfb91ede`), merged minutes before this work reached it:

| Artifact | What it does |
|---|---|
| `.github/workflows/board-regeneration.yml` | Nightly (05:00 UTC) + `workflow_dispatch`; netlist → route → inject-defect (manual) → verify → sha256 + upload; `permissions: contents: read`; hard prohibitions (never writes the DRC ceiling, never commits `pcb/temper.kicad_pcb`, never authors a `Ceiling-Approval:` trailer, never opens a PR) |
| `scripts/verify_regenerated_board.py` | Assertions 2–4 of plan §U7: output parses (`parse_kicad_pcb_v6`), order-insensitive structural equivalence vs the committed board (canonical frozensets of components/nets/tracks/vias), DRC within the committed ceiling |
| `docs/evidence/2026-08-05-r3-producer-anti-vacuity.md` | U8: demonstrated-red mechanism + synthetic local runs (full production run deferred to CI) |

This matches the brief's requirement: regenerates the board on harness change,
validates it still produces a valid board, and **discards** the regenerated
artifact (uploads with 7-day retention; the committed board stays
human-reviewed). Reviewed, not re-written — no file in this list is touched by
this branch.

## 2. Board-writer entry point

```
make route
  → uv run python3 scripts/route_board.py --pcb pcb/temper.kicad_pcb --output pcb/temper_routed.kicad_pcb
    → temper_placer.router_v6.adapter.route_pcb
      → temper_placer.router_v6._adapter_convert._write_routes_to_content
```

`route_board.py` is the single live entry point (its docstring: "the only
routing entry point, and `make route` invokes it"). The board is written as a
modified KiCad PCB by `_write_routes_to_content`, not by the io-layer writer
below.

## 3. The frozenset-order caveat — two writers, two answers

### 3a. The io-layer writer the plan's caveat names — FIXED (#770)

The parent plan's assumption ("the board writer emits track and via order from
a `frozenset`, so regeneration is not byte-reproducible across processes")
names `packages/temper-placer/src/temper_placer/io/_write_tracks.py::write_routes_to_pcb`.
That writer **no longer has the defect**: commit `90bc85a97` (#770,
"fix(io): make KiCad board track/via emission order deterministic") imposed a
canonical emission order — segments sorted by `_trace_emission_key`, vias by
`_via_emission_key` (net index → layer → geometry), with both keys proven total
against element equality, so nothing is left to set iteration order. The
docstring records the history: "Before this ordering, the byte order of tracks
and vias followed CPython's per-process string hash salt (PEP 456), so
re-writing an identical route set produced a different file on every process."

An anti-vacuity test enforces it:
`packages/temper-placer/tests/io/test_write_tracks_determinism.py` fails with
"write_routes_to_pcb emission order depends on PYTHONHASHSEED" if the writer
ever reverts to raw set iteration.

**So the specific caveat the parent plan records is resolved** — regeneration
via `write_routes_to_pcb` is byte-deterministic. The plan's Dependencies text
is stale on this point; R3's structural-equivalence assertion is order-
insensitive regardless, so nothing downstream depends on which is true.

### 3b. The production route writer — order is dict-insertion, byte-level unverified

`route_pcb` does **not** use that io writer. It uses
`_adapter_convert._write_routes_to_content`, which iterates nets over
`{**tree_compiled, **partial_tree_compiled}.items()` (dict insertion order,
line 76) and per-net geometry segments via `iter_segments()` (deterministic
Vec order). Whether the *dict's insertion order* is itself identical across
fresh processes depends on upstream construction — which is not end-to-end
byte-verified. The R3 workflow pins `PYTHONHASHSEED=0` for exactly this
reason (its own comment: "variance comes from HashMap hasher seeding, which
PYTHONHASHSEED controls"). The `2026-07-27-router-determinism.md` doc's
53.1%-vs-37.5% net-completion discrepancy remains UNVERIFIED.

### 3c. The mechanism, demonstrated cheaply (language level)

The caveat's root mechanism is real and reproducible without the router. A
frozenset of string-keyed elements iterates in per-process hash order:

```
$ for seed in "" 0 0; do PYTHONHASHSEED=$seed python3 -c "
nets = {f'net_{i}' for i in range(200)}
tracks = frozenset((n, i % 7) for i, n in enumerate(nets))
print([t[0] for t in tracks][:6])
"; done
['net_163', 'net_168', 'net_179', 'net_177', 'net_57', 'net_82']   # unseeded
['net_181', 'net_173', 'net_106', 'net_72', 'net_5', 'net_32']     # seed 0
['net_181', 'net_173', 'net_106', 'net_72', 'net_5', 'net_32']     # seed 0
```

Unseeded processes emit a different byte order; `PYTHONHASHSEED=0` pins it.
Any writer that emits an unsorted set is byte-nondeterministic across
processes; a canonical sort (3a) or a pinned seed (the workflow) both remove
the variance.

## 4. Byte-determinism of a full regeneration — COULD NOT BE MEASURED

The two-run sha256 protocol (`docs/evidence/2026-07-27-router-determinism.md`)
requires `route_pcb()` to complete twice. On this machine it was **SIGKILL'd by
the OS OOM killer** at ~12,448 MB RSS after ~7 minutes (`ps` showed the process
gone with no output file and no error in the log) — the same environmental
OOM the `2026-08-07-router-oom-diagnosis.md` records: the ~7 GB route on a
shared machine with concurrent-agent memory pressure. `ulimit -v` is not
available on macOS (the workflow's 8 GB cap runs on `ubuntu-latest`). Free
memory at attempt time was <1 GB with 4 GB of swap in use.

**Recorded, not worked around.** The byte-determinism answer for a *full*
regeneration therefore remains UNVERIFIED at this machine, exactly as it was
for U6. The R3 producer does not depend on it: assertion 3 is order-insensitive
canonical-set equivalence, and the regenerated artifact is discarded, per D11.

## 5. R3 verdict

| Requirement (brief) | Status |
|---|---|
| CI workflow regenerates the board per harness change | **PASS** — landed #904 (`board-regeneration.yml`), scheduled + manual dispatch |
| Validates it still produces a valid board | **PASS** — `verify_regenerated_board.py` assertions 2–4, anti-vacuity demonstrated (#904 U8) |
| Discards the regenerated artifact | **PASS** — artifact uploaded with 7-day retention, never committed; `permissions: contents: read` |
| Board-writer entry point identified | **PASS** — `route_board.py` → `route_pcb` → `_write_routes_to_content` |
| frozenset-order caveat verified + recorded | **PASS (recorded)** — io writer fixed by #770 (canonical emission keys + anti-vacuity test); production writer order is dict-insertion, byte-level end-to-end determinism UNVERIFIED (route OOM-killed on this machine); mechanism demonstrated at language level; `PYTHONHASHSEED=0` pins the variance |

R3 does not gate D3 (per the Phase-0 plan's Track-C status), and its producer
component is satisfied. The open item — full-route byte determinism — is the
same UNVERIFIED item U6 carried and is scheduled to be answered by the nightly
producer's own sha256 output in CI (which uploads the routed artifact hash on
every run).
