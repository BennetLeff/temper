# Manufacturing DRC swallows check crashes into empty reports

**Provenance: commit=UNKNOWN dirty=UNKNOWN** -- backfilled prior to the provenance gate's introduction (2026-07-26); no self-declared commit exists in this file's own content and none was fabricated. See .evidence-provenance-allowlist.

**Date:** 2026-07-25
**Status:** verified latent defect — **did not fire during the rung-1 route**
**Severity:** high (covers creepage and clearance on a mains-connected board)

## The defect

`router_v6/_pipeline_verify.py:252`:

```python
def _run_one(name, fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception:
        _logger.warning("Manufacturing DRC: %s check failed, continuing", name, exc_info=True)
        return None
```

Every call site then substitutes an **empty report** for the `None`:

```python
clearance = _run_one("clearance", verify_clearance, routing_results) \
    or ClearanceReport(violations=[], total_checks=0)
```

**A manufacturing DRC check that raises is reported as clean.** Zero violations,
zero checks performed, logged at `warning` and otherwise invisible.

Nine `_run_one` call sites share this: `acid_trap`, `annular_ring`, `teardrop`,
`thermal_relief`, `power_planes`, `copper_balance`, **`creepage`**,
**`clearance`**.

Creepage and clearance are the two that carry HV safety meaning on a
mains-connected appliance.

Live path: `_pipeline_core.py:358` calls `_run_manufacturing_drc` during
`route_pcb()`. This is not dead code.

## CORRECTION (same day) — the stage never runs at all

An earlier revision of this document said the checks "ran" during the rung-1
route, inferred from zero `Manufacturing DRC: … check failed` warnings in the
log. **That inference was wrong**, and the real finding is larger.

`_pipeline_core.py:355`:

```python
# Stage 5: Manufacturing DRC (opt-in)
manufacturing_report = None
if self.enable_manufacturing_drc:
```

with `_pipeline_core.py:63`:

```python
enable_manufacturing_drc: bool = False,
```

**`route_pcb()` never sets it.** `grep -rn "enable_manufacturing_drc"` across
`packages/temper-placer/src/` returns hits only inside `_pipeline_core.py`
itself — no caller enables it.

So the entire manufacturing DRC stage — acid traps, annular rings, teardrops,
thermal relief, power planes, copper balance, **creepage**, and **clearance** —
**does not execute during routing.** The absence of failure warnings proved
nothing, because the code path was never entered.

### This is the shorts root cause

The router emits copper without ever running its own clearance or creepage
verification. That is why 499 `clearance` violations and ~51 router-attributed
`shorting_items` reach the output: nothing checks them at emission time.

`clearance_check.py` is 498 lines, imported by **17 test files**, and
exercised by property-based tests. It is thoroughly tested and, in the
production routing path, never called.

### The crash-swallow below is still real, and now second-order

`_run_one`'s empty-report fallback remains a genuine defect. It simply cannot
have fired yet, because the function containing it has never been reached in a
`route_pcb()` call. **It becomes live the moment the stage is enabled** — which
is the obvious next step — so it must be fixed *before or with* that change,
not after.

## Why it still matters

The failure mode is silent and safety-relevant. If `verify_creepage` ever
raises — a malformed geometry, an unexpected net class, a `None` where a float
was expected — the board's creepage report reads `violations=[]` and the
pipeline continues. On a 340 V bus that is the difference between a caught
defect and a shipped one.

`total_checks=0` in the substituted report is the tell: the report states it
checked nothing, and nothing acts on that.

This is the same shape as the import-linter gate fixed earlier today, which
scraped stdout for violations and read a crash as "zero violations"
(`METHODOLOGY.md` §4 classes 4 and 6).

## Required fix

1. A crashed check must **not** become an empty report. Distinguish
   `clean` / `violations found` / `check errored`, as
   `scripts/import_linter_gate.py` now does.
2. `total_checks == 0` on a board with routed copper is itself a failure
   condition — assert non-empty, per `METHODOLOGY.md` §5 anti-vacuous-truth.
3. For `creepage` and `clearance` specifically, a check error must **fail
   closed**, matching the `_allow_forced_segments` precedent.
4. The distinction must be visible in the returned report, not only in a log
   line nobody reads.

## Reproduction

```bash
grep -n "_run_one" packages/temper-placer/src/temper_placer/router_v6/_pipeline_verify.py
grep -rn "_run_manufacturing_drc" packages/temper-placer/src/ | grep -v __pycache__
```
