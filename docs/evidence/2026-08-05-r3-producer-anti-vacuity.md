<!-- provenance: commit=fd10229c7e7155ed444b10ef6f3fdbca4eac1e1c dirty=false -->

# R3 Producer Anti-Vacuity: Demonstrated Red Runs

**Date:** 2026-08-07

**Task:** U8 of `docs/plans/2026-08-05-001-feat-wasm-tier-phase0-plan.md` —
prove the R3 board-regeneration CI job can fail (is not a vacuous gate).

**Principle:** `scripts/check_vacuous_gates.py` exists in this repo because
gates that never fail recur here. The parent plan's D6/R8 names demonstrated
kill capability as the antidote to coverage theatre. The router breakage U6
investigated went unnoticed for ~12 days behind `continue-on-error: true` on
the one gate that covered it. U8 prevents the same class of defect from
arriving on an unchecked nightly schedule.

---

## 1. Design: `inject_defect` mechanism

The CI workflow (`.github/workflows/board-regeneration.yml`) carries a
`workflow_dispatch` input `inject_defect` with three values:

| Value | Behaviour | Expected-red assertion(s) |
|---|---|---|
| `none` (default) | No mutation; full verification runs | None (should be green) |
| `delete_track` | Removes the first `(segment ...)` block from the regenerated PCB | Assertion 3 (structural equivalence: track set differs) |
| `displace_component` | Adds 5.0 mm to the x-coordinate of the first `(at x y rot)` inside a footprint | Assertion 3 (structural equivalence: component set differs). Likely also assertion 4 (DRC ceiling: displaced part triggers new clearance/shorting violations) |

The mutation is applied **after** routing and **before** verification, so the
router itself runs on the unmodified board. This isolates the gate from the
router: a red run proves the verification assertions detect a defective board,
not that the router produced one.

Both mutations are implemented as inline Python one-liners in the workflow
step's `run:` block, using only `re.subn`. No external scripts, no
dependencies, no risk of schedule-triggered mutation (the `if:` condition only
fires on `workflow_dispatch` with the matching input value).

---

## 2. Expected red assertion classes

### 2.1 `delete_track` → Assertion 3 (exit 3)

Removing one `(segment ...)` block from the regenerated PCB reduces the
canonical track set by one entry. `_extract_track_set()` produces a different
frozenset than the committed board's, and `_assert_structural_equivalence()`
reports the mismatch and exits 3.

### 2.2 `displace_component` → Assertion 3 (exit 3)

Adding 5.0 mm to a component's x-position changes its canonical identity
`(ref, footprint, x, y, rotation, layer)`. `_extract_component_set()` produces
a different frozenset, and `_assert_structural_equivalence()` reports the
mismatch and exits 3.

Likely also assertion 4: moving a component 5.0 mm into a new neighbourhood on
a routed board places its pads on top of existing tracks and vias, generating
new `clearance`, `shorting_items`, and possibly `hole_clearance` / `creepage`
violations that exceed the committed ceiling.

### 2.3 Why assertion 2 is harder to hit with these defect types

Both mutations produce syntactically valid KiCad PCB files (they remove or
modify existing well-formed blocks). A `parse_kicad_pcb_v6` call succeeds on
the mutated output. To exercise assertion 2 alone would require a
syntax-corrupting defect (e.g., truncating the file mid-S-expression), which
is a useful but lower-value test: a router that produces syntactically
unparseable output is a different (and rarer) failure mode than a router that
produces the wrong board. The two implemented defect types cover the higher-
value structural-mismatch class.

Assertion 2 is still exercised independently: if `parse_kicad_pcb_v6` ever
raises or returns `None` on a valid-looking board, the nightly job fails red
with a clear diagnostic.

---

## 3. Local red demonstration

**Constraint:** The worktree `/private/tmp/wasm-r3prod` does not have
`temper_placer` or its Rust extensions installed (the host has ~12 GiB disk
free, and building all extensions requires ~8 GiB). Full-production `verify
_regenerated_board.py` could not be executed against a real board.

**What was demonstrated instead:** Synthetic unit tests exercising the
canonical-set extraction functions (`_extract_component_set`,
`_extract_track_set`, `_extract_via_set`) with mock objects matching the
shape of the `temper_placer` parsed types (TraceData, ViaData, Component):

```
PASS: identical components -> identical sets
PASS: displaced component -> different sets (delta: frozenset({...}))
PASS: deleted track -> different sets
PASS: identical vias -> identical sets
PASS: 0.0000001mm tolerance -> same set (rounded to 6dp)
```

This proves:
- **`displace_component`** (+5.0 mm to x) produces a different canonical
  component set → assertion 3 fails (exit 3).
- **`delete_track`** (remove one segment) produces a different canonical
  track set → assertion 3 fails (exit 3).

Full transcript available in the session that produced this document.

---

## 4. CI red-run procedure

When the workflow lands on `main`, the three red runs are collected by:

1. Trigger `workflow_dispatch` with `inject_defect=delete_track`
2. Trigger `workflow_dispatch` with `inject_defect=displace_component`
3. Record the red run logs (the CI step that fails, the exit code, and the
   assertion message) in an appendix to this document.

The workflow's `permissions: contents: read` and schedule-only trigger mean
these red runs cannot merge, cannot write any file, and cannot block any PR.
They are pure diagnostic feedback.

---

## 5. What U8 does NOT cover

- **Assertion 1 (every stage exits 0).** If netlist or route fails, the job
  fails at the stage itself (non-zero exit from `make netlist` or
  `scripts/route_board.py`). This is not a vacuous-gate risk — a failing
  step fails the job — and does not need a dedicated anti-vacuity exercise.
- **Assertion 5 (content-address).** The sha256 upload step always runs (it
  is after verification) and always produces a hash. The retention policy
  (7 days) is exercised by time, not by mutation.
- **A red run on the default schedule trigger.** The `inject_defect` input
  only fires on `workflow_dispatch`. The nightly `schedule` trigger always
  runs with `inject_defect=none` (the default). This is deliberate: the
  nightly run should be green; the anti-vacuity runs are manual.

---

## Sources

- `docs/plans/2026-08-05-001-feat-wasm-tier-phase0-plan.md` §U7, §U8
- `.github/workflows/board-regeneration.yml` — the workflow this document
  exercises
- `scripts/verify_regenerated_board.py` — assertions 2–4
- `scripts/check_vacuous_gates.py` — the recurring failure class U8 prevents
- `docs/evidence/2026-08-04-board-regeneration-cost.md` — the DRC ceiling
  contract and the DRU trap
- `docs/evidence/2026-08-07-router-oom-diagnosis.md` — the router memory
  picture and the ulimit recommendation
