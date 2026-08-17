<!-- provenance: commit=e81196c87b5998555feca78f27c612b11331bee7 dirty=false
     board sha256 (verified unchanged before and after this investigation):
     9c1f4a37b03c6433275704c3bed917f7ff16877c762f0aa8d37cc6858d7c16dd
     (matches the 2026-08-17-corrected value in docs/HANDOFF-2026-08-17.md) -->

# `test_hyphenated_hb_gnd_and_vdd_nets_classify_correctly` — stale test, not a live bug

**Date:** 2026-08-17

## Verdict, up front

**Stale test. Not a live misclassification bug. Not permissive. Not hazardous.**

`_classify_net_class("hb-gnd")` on current main returns `"HV"`, correctly, on
**both** the Python reference implementation and the production Rust backend
(`backend="auto"`, which `verify_clearance`'s only production call site uses —
see §4). `hb-gnd` is genuinely an HV-domain net (the half-bridge low-side
switch's return conductor, ~-170V relative to signal ground) per
`elec/domain_manifest.yaml`'s own sourced trace of the compiled netlist. The
failing test asserted `"GND"` — the *wrong*, weaker classification. If the
code had been changed to make the test pass instead of the reverse, that
would have been the exact hazard this investigation was dispatched to rule
out: a mains/HV-referenced net picking up the 0.127mm default clearance
instead of the 12.6mm IEC 60335-1 PD3 reinforced figure. That did not happen.
The test has been corrected in place (not skipped, not xfailed, not
weakened) to assert the safety-correct `"HV"` outcome, with a docstring
explaining why.

## 1. Reproduction

```
packages/temper-placer/tests/router_v6/test_clearance_check.py:391
assert _classify_net_class("hb-gnd") == "GND"
AssertionError: assert 'HV' == 'GND'
```

Confirmed locally against `e81196c87` (current main tip) with a fresh
`make venv-isolate` build in this worktree (`agent-a5f51b85574de8118`,
own `.venv`, no shared-checkout `.so` rebuilt). All three assertions in
the test were checked individually:

| Net | Test expected | Actual | Verdict |
|---|---|---|---|
| `hb-gnd` | `"GND"` | `"HV"` | test wrong, code correct |
| `hb.gate_hs-vdd` | `"POWER"` | `"POWER"` | matches, unaffected |
| `hb.gate_ls-vdd` | `"POWER"` | `"POWER"` | matches, unaffected |

Only the `hb-gnd` assertion fails.

## 2. Root cause: a race between two same-wave PRs, not a code defect

`_classify_net_class` (`packages/temper-placer/src/temper_placer/router_v6/clearance_check.py:900`)
has checked manifest membership *before* the keyword cascade since before
either PR discussed below:

```python
def _classify_net_class(net_name: str) -> str:
    if net_name in _load_manifest_hv_net_names():   # checked FIRST
        return "HV"
    upper = net_name.upper()
    if _is_hv_keyword_match(upper):
        return "HV"
    if any(... for kw in ("GND", "VSS", "PGND", "CGND", "AGND")):
        return "GND"
    ...
```

`_load_manifest_hv_net_names()` reads `elec/domain_manifest.yaml`'s `HV`
domain (27 nets as of main tip). Two commits landed **10 seconds apart** in
the same merge wave:

| Commit | Time | PR | Content |
|---|---|---|---|
| `72d4a083d` | 2026-08-15 19:54:28 | #1145 | Declares `hb-gnd` under `elec/domain_manifest.yaml`'s `HV` domain — a detailed, netlist-traced finding (R23.2, U6.9 pin 9/VSSB, C23.2, C24.2, U5.3 Emitter, T2.1 all on this one compiled net; the half-bridge low-side switch's return conductor, ~-170V relative to signal ground, one CT primary winding from the already-declared HV net `DC_BUS_RTN`). |
| `bb3d99d1` | 2026-08-15 19:54:38 | #1174 | "Family C" hyphen-boundary fix to `_is_hv_keyword_match`/`_classify_net_class`'s GND/POWER branches. Adds the now-failing test, asserting `hb-gnd` flips `SIGNAL`→`GND` via the widened GND-keyword boundary. |

PR #1174's **own evidence doc**
(`docs/evidence/2026-08-13-hyphen-boundary-clearance-creepage-defect.md`,
§2 item 1) states plainly, of its own measurement branch:

> "`hb-gnd` is not yet manifest-declared on this base branch (that is
> PR #1145's own, separate, not-yet-merged change) — so this PR's
> classification fix (`hb-gnd` now correctly reads `GND`, not `SIGNAL`)
> does **not**, by itself, close the live routed-clearance gap for this
> exact pairing; PR #1145 landing is still required for that."

That is: the PR #1174 author already knew, and documented, that the `"GND"`
result was contingent on #1145 *not yet* being merged into that branch's
world. The two branches were developed in parallel and merged into main
essentially simultaneously. From the moment both landed, the manifest
check's priority in `_classify_net_class` has made `hb-gnd` classify `"HV"`
unconditionally — the keyword-cascade `"GND"` result the test asserts has
never been reachable on main. This is handoff mechanism 5 (stale ground
truth): a test correct for the world it was measured against, invalidated
by a second change landing in the same window, and never re-verified after.

Nothing needed fixing in the classification code. `_classify_net_class`'s
manifest-first ordering is exactly the intended, safety-correct behavior —
electrical ground truth (a real netlist trace) overrides a name-shaped
heuristic.

## 3. Confirming `hb-gnd` is genuinely HV, not a naming artifact

`elec/domain_manifest.yaml` lines 367-427 (PR #1145) give the full trace:
`hb-gnd` is the compiled net atopile assigned to `hb.dc_bus.hv_minus`,
carrying R23.2 (`hb.gate_ls.rgs`), U6.9 (`hb.gate_hs.driver` pin 9 = VSSB,
already documented elsewhere in the same manifest as "floats on
DC_BUS_RTN"), C23.2, C24.2 (the HF DC-bus cap), U5.3 (`hb.power_loop.q_low`'s
Emitter, `power_loop.q_low.E ~ dc_bus.hv_minus` per `modules.ato:379`), and
T2.1 (`safety.ocp2.ct` primary). It sits at the same ~-170V potential as the
already-declared HV net `DC_BUS_RTN`, separated only by a few milliohms of
CT primary winding — not a galvanic isolation boundary. Classifying it as
`GND` would be actively wrong, not merely imprecise.

## 4. Liveness: this is the production path, not a dead fallback

Traced by call site and CI wiring, not by naming, per handoff §3 mechanism 2:

- `verify_clearance()`'s only non-test, non-docstring call site is
  `_run_manufacturing_drc()` in
  `packages/temper-placer/src/temper_placer/router_v6/_pipeline_verify.py:421-425`,
  called with the default `backend="auto"`. `_run_manufacturing_drc` is
  bound onto `RouterV6Pipeline` (`_pipeline_core.py:38,434`) as Stage 5 —
  live, not orphaned.
- `backend="auto"` resolves to the Rust engine
  (`temper_orchestration.run_clearance_check` →
  `temper_drc_rs.verify_route_clearance`) whenever `temper_drc_rs` is
  importable — true in every environment this check ships to (confirmed by
  `_HAS_RUST_CLEARANCE`/`_HAS_RUN_CLEARANCE_CHECK` gating in
  `clearance_check.py`, and by direct import in this worktree's fresh build).
- `_verify_clearance_rust` passes `sorted(_load_manifest_hv_net_names())`
  into the Rust call (`clearance_check.py:323-325`) as `hv_net_names`, which
  `router_clearance.rs::classify_net_class_named`/`is_hv_gate_named`
  (lines 356-368) check **first**, identical priority to the Python
  reference. The manifest fix reaches the live backend, not just the
  Python fallback.
- Empirical, end-to-end check in this worktree (both backends, synthetic
  routes 0.2mm apart, nets `hb-gnd` and `gnd`):

  ```
  python -> violations: 1   required: 12.6mm  actual: 0.073mm
  rust   -> violations: 1   required: 12.6mm  actual: 0.073mm
  ```

  Both backends correctly flag the violation at the full PD3 reinforced
  figure. Production is safe today.
- `test_clearance_check.py` (the file containing the failing test) is
  itself explicitly listed in `.github/workflows/python-tests.yml`'s
  "Invariant tests (router_v6 group 3)" job (line ~3985) — not one of the
  handoff's "49→109 router_v6 files not collected by CI." No
  `continue-on-error` on that job. The failure is real, required, and
  currently red on main, exactly as reported.

## 5. Does `1a7d1dde0` fix this? No — because it's already on main.

The task flagged `1a7d1dde0` ("fix(drc): word-boundary net classification in
router_clearance (resolves #1175)") as not reachable from current main and
asked whether it is the fix, stranded.

It is **not stranded and not needed** — its content is already on main,
merged via a different commit hash:

```
$ git show 1a7d1dde0 --format="%H %ad" --date=iso -s
1a7d1dde09271946f790712f2c7414af8e89e44d 2026-08-15 09:11:36 -0600

$ git log --oneline -S"is_hv_gate_named" -- packages/temper-drc-rs/src/router_clearance.rs
3f110fa3f fix(clearance): thread manifest HV net names through to the Rust backend
8f21d2725 fix(drc): word-boundary net classification in router_clearance (resolves #1175)
...

$ git show 8f21d2725 --format="%H %ad %s" --date=iso -s
8f21d27257a017209cb8969500eb64ba71d1e53b 2026-08-15 09:11:36 -0600 fix(drc): word-boundary net classification in router_clearance (resolves #1175)

$ git diff 1a7d1dde0 8f21d2725 -- packages/temper-drc-rs/src/router_clearance.rs
(empty)

$ git merge-base --is-ancestor 8f21d2725 HEAD && echo ANCESTOR
ANCESTOR
```

`1a7d1dde0` and `8f21d2725` are the identical change (same author, same
commit message, same timestamp to the second, byte-identical diff to
`router_clearance.rs`) — evidently the same fix produced in two sibling
worktrees, one of which (`8f21d2725`) made it into main's history and the
other (`1a7d1dde0`) did not get merged and is now a dead, superseded
duplicate. `8f21d2725` **is** an ancestor of current main
(`e81196c87`). Nothing needs to be landed from `1a7d1dde0` — it would be a
no-op merge (identical tree diff) if attempted, and its title ("resolves
#1175") describes work that resolved #1175 through the already-merged
route. This is the answer to deliverable §4: no further action needed on
`1a7d1dde0`.

## 6. Is this inside the reserved PWR_RTN/CGND scope (handoff §9 item 6)? No — independent.

`scripts/check_hv_netclass_coverage.py`'s docstring reserves a specific,
narrower question as an open human decision:

> "The wrong-class shape — a manifest-HV net assigned to an LV class, e.g.
> the historical `+15V_LS -> Power` defect or the still-open
> `PWR_RTN -> GND` case ... is deliberately NOT enforced here: enforcing it
> would flag `PWR_RTN`, whose reclassification carries an order-of-magnitude
> larger blast radius..."

That reserved decision is about `TEMPER_NET_ASSIGNMENTS`
(`packages/temper-placer/src/temper_placer/core/design_rules.py`) — the
placer/router netclass-assignment table that drives KiCad netclass rule
generation — specifically whether `PWR_RTN`'s current `GND`-family
netclass assignment should be reclassified. This failing test exercises a
**different function** (`clearance_check._classify_net_class`, Stage 5.7's
own net-name pattern classifier plus `elec/domain_manifest.yaml` lookup,
used only for the Router V6 clearance/creepage DFM check) on a
**different net** (`hb-gnd`, not `PWR_RTN` or `CGND`). Neither the net nor
the classification mechanism overlaps the reserved decision's scope.
**Independent of §9 item 6.** No PWR_RTN/CGND reclassification is implied,
required, or touched by this fix.

## 7. What was changed

Only `packages/temper-placer/tests/router_v6/test_clearance_check.py`:
`test_hyphenated_hb_gnd_and_vdd_nets_classify_correctly` now asserts
`_classify_net_class("hb-gnd") == "HV"` (was `"GND"`), with a docstring
recording the root cause above. The `hb.gate_hs-vdd`/`hb.gate_ls-vdd`
assertions are unchanged (both were already correct and remain `"POWER"`).

No production code changed. No clearance, creepage, copper-weight, or DRU
threshold changed. No oracle file
(`_clearance_family_py_oracle.py` or any other) touched — verified via
`scripts/check_oracle_hashes.py` (166/167 OK before and after this change;
the sole drift, `_graph_py_oracle.py`, is pre-existing and unrelated).
`pcb/temper.kicad_pcb` untouched — sha256 verified unchanged before and
after (see header).

## 8. Verification run

```
$ .venv/bin/python -m pytest packages/temper-placer/tests/router_v6/test_clearance_check.py -v
...
20 passed in 0.16s

$ .venv/bin/python -m pytest packages/temper-placer/tests/router_v6/test_creepage_check.py \
    packages/temper-placer/tests/router_v6/test_clearance_rust_differential.py \
    packages/temper-placer/tests/router_v6/test_net_class_parser.py -q
87 passed in 0.51s
```
