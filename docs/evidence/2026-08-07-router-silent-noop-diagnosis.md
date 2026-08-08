<!-- provenance: commit=90d5fd983f825d1895f416b8535dee6a169b8979 dirty=false -->

# The router builds an empty model on the committed board — and a 42M-variable model on a stripped copy of the same board. Both are true, on different code paths.

**Date:** 2026-08-07

**Task:** Diagnose why `ModelBuilder.build()` produces `variables=0,
constraints=0` when `route_pcb()` is called on `pcb/temper.kicad_pcb`
(traced to the known plane-condemnation bug,
`docs/solutions/logic-errors/single-zone-condemns-whole-copper-layer-plane-2026-07-29.md`),
and reconcile that against `docs/evidence/2026-08-07-router-oom-diagnosis.md`
and issue #871, which record `route_pcb()` OOMing at >13 GB RSS with a
42M-variable / 78M-clause CNF **on the same board**. Diagnosis only — no
production code changed.

**Bottom line up front:**

1. **Transition commit: `556ccf4f`**, 2026-07-27T18:28:22-06:00 — the commit
   that first wrote zone pours into `pcb/temper.kicad_pcb` (0→96 zones,
   0→2338 segments). The moment the board acquired plane-required zones on
   F.Cu/B.Cu, the pre-existing (already-latent, previously-inert) plane-
   condemnation bug in `_extract_stackup()` started firing on every
   subsequent direct parse of that file.
2. **Both figures in the "contradiction" are real, measured today, on
   byte-identical board content — they differ because of an input-
   preparation step, not a code difference.** Calling `route_pcb()` with
   `parsed.source_path` pointed straight at the committed
   `pcb/temper.kicad_pcb` (what the CI gate test and most evidence docs do)
   reads the board's own zones, trips the plane bug, and gets `skeletons={}`
   → 0 variables. Calling it via `scripts/route_board.py`'s default path
   (what produced the original committed route, and what the nightly
   `board-regeneration.yml` workflow and issue #871's own measurement use)
   **strips all committed copper — including zones — from a temp copy
   first**, so F.Cu/B.Cu classify as `signal` again and the full-size model
   (millions of raw variables, tens of millions of CNF variables) gets
   built, exactly as before.
3. **Every CI-gate baseline for `test_production_board_routing_drc_regression`
   re-measured since 2026-07-27 evening has been re-certifying the degraded,
   empty-model fallback's output as the new normal**, not real SAT-driven
   routing. `docs/evidence/2026-08-07-router-oom-diagnosis.md`'s central
   claim — that this test "passed... same code path" as the OOM'd
   production route — is false: they are different code paths with
   different model sizes.
4. **#871 is still live**, but only via the stripped-copper path
   (`route_board.py` / the board-regeneration workflow), which is also the
   board's only re-route producer. It is not reproducible via the direct/
   production `route_pcb()` call the CI DRC gate uses — that path cannot
   build a large enough model to OOM.
5. **No gate catches the empty-model case.** Two stage validators
   (`validate_routing_space`, `validate_channel_skeleton`) exist and both
   have the exact "iterate over a dict that already lost the interesting
   keys" shape that `scripts/check_vacuous_gates.py` exists to catch — and
   `router_v6` is explicitly excluded from that scanner.

---

## 1. Bisection: the transition is `556ccf4f`

`git log --oneline -- pcb/temper.kicad_pcb`, cross-referenced with a
zone/segment count at every commit touching the file (`git show
<commit>:pcb/temper.kicad_pcb | grep -c '(zone'` /
`'(segment '`):

| Commit | Date | zones | segments |
|---|---|---:|---:|
| `c6b1b463` (and everything before it) | 2026-07-27 (earlier) | 0 | 0 |
| **`556ccf4f`** "commit first route of temper.kicad_pcb (51/96 nets, 53.1%)" | **2026-07-27T18:28:22-06:00** | **96** | **2338** |
| `65bd0159` … `de59c045` | 2026-07-27 – 2026-08-03 | 96 | 2338 |
| `e5a89b1e` "stop emitting a zero-length track at every via" (#771) | 2026-08-05 | 96 | 2290 |
| `7e3608bc` "move R24 so the mains↔SELV barrier becomes admissible" | 2026-08-06 | 96 | 2290 |
| HEAD (`90d5fd98`) | 2026-08-07 | 96 | 2290 |

Direct repro at both sides of the transition, using temporary `git worktree
add` checkouts (code + board matched to each commit, no changes to this
worktree's tracked files):

```
$ git worktree add /tmp/wt-c6b1b463 c6b1b463   # last zoneless commit
$ PYTHONPATH=.../wt-c6b1b463/packages/temper-placer/src python3 -c "
from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
pcb = parse_kicad_pcb_v6('.../wt-c6b1b463/pcb/temper.kicad_pcb')
for ly in pcb.stackup.layers: print(ly.name, ly.layer_type)"
F.Cu signal
In1.Cu mixed
In2.Cu mixed
B.Cu signal

$ git worktree add /tmp/wt-556ccf4f 556ccf4f   # the transition commit itself
$ PYTHONPATH=.../wt-556ccf4f/packages/temper-placer/src python3 -c "... same probe ..."
F.Cu plane
In1.Cu mixed
In2.Cu mixed
In3.Cu mixed
B.Cu plane
```

(`In3.Cu` is the separate phantom-layer bug that `a1fe623e`, five hours
later the same day, fixed — orthogonal to the plane-condemnation issue and
not relevant to this transition.)

**At HEAD**, the same probe against the live committed board:

```
$ PYTHONPATH=packages/temper-placer/src python3 -c "
from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
pcb = parse_kicad_pcb_v6('pcb/temper.kicad_pcb')
for ly in pcb.stackup.layers: print(ly.name, ly.layer_type)"
F.Cu plane
In1.Cu mixed
In2.Cu mixed
B.Cu plane
```

Unchanged since `556ccf4f`. The classifier code itself moved twice more
after the transition (`a1fe623e` briefly forced outer layers to `signal`;
`60d441f2`, ~8 hours later, deliberately reverted that half — see §2) but
the **net effect on this board has been "F.Cu/B.Cu = plane" continuously
since 2026-07-27T18:28**.

## 2. Mechanism: two independent bugs, only one of which is new information here

**Bug A (known, documented 2026-07-29):** `_extract_stackup()`
(`packages/temper-placer/src/temper_placer/io/_parse_board.py`) sets a whole
physical layer's `layer_type = "plane"` if **any** zone on it sits on a
plane-required net (existential quantifier over zones, not an area
threshold). `routing_space.py:85` (`if layer_info.layer_type not in
["signal", "mixed"]: continue`) then drops that layer from
`compute_routing_space()`'s output entirely. Full writeup:
`docs/solutions/logic-errors/single-zone-condemns-whole-copper-layer-plane-2026-07-29.md`.
This bug's code shape is old (present since `_extract_stackup` was written)
but was **inert** until the board had zones to trigger it — `plane_assignments`
is built from zone content, and the board had zero zones before `556ccf4f`.

Its live/dead history on this repo, by commit:

| Commit | Time | State |
|---|---|---|
| (inception) → `556ccf4f` | — | Latent — no zones exist, `plane_assignments` always empty |
| `556ccf4f` | 2026-07-27 18:28 | **Triggers for the first time** — board gets 96 zones |
| `a1fe623e` "stop fabricating a phantom In3.Cu and misclassifying F.Cu/B.Cu as planes" | 2026-07-27 23:53 | Fixed (forces F.Cu/B.Cu to `signal` on a 4-layer board, per `docs/hardware/POWER_PLANE_DESIGN.md`'s documented intent) |
| `60d441f2` "revert the outer-layer half of the stackup fix, keep the phantom-layer half" | 2026-07-28 08:07 | **Deliberately re-broken.** Measured: forcing outer=signal gave 3.12% completion (93/96 unrouted, `test_astar_3d_production_scale_spike`'s failure moved from `KeyError: 'F.Cu'` to `'Could not construct any short same-layer segment'` — the layers were reachable but the zone pours physically block them) vs. 38.54% honoring the zone heuristic. This revert is a considered decision documented in `docs/evidence/2026-07-28-stackup-partial-revert.md`, not an accident — the code the board runs today still does this, on purpose, because the alternative measured worse on the A* reconstruction path that existed at the time. |
| `81f3c69a` (slice 4/8 of the netclass SSOT landing, 2026-07-29) | 2026-07-29 13:43 | Predicate improved (`_is_plane_required_net`, SSOT-driven, replacing a bare `"+" in netName` substring test) and `use_declared_layer_roles` opt-in added (default `False`, never set `True` by any production caller) — neither changes whether the quantifier bug fires on this board. |

**Bug B (new finding, this task):** `ChannelSkeletonStage.run()`
(`packages/temper-placer/src/temper_placer/router_v6/channel_skeleton.py:341-346`)
hardcodes:

```python
outer_layers = {k: v for k, v in routing_spaces.items() if k in ("F.Cu", "B.Cu")}
for layer_name, routing_space in outer_layers.items():
    skeleton = extract_channel_skeleton(routing_space, pcb=pcb)
    skeletons[layer_name] = skeleton
```

This stage **only ever builds a channel skeleton for layers literally named
`F.Cu` or `B.Cu`**, unconditionally — it never looks at `In1.Cu`/`In2.Cu`
even when they are present and routable in `routing_spaces`. This
restriction has been in the code since the stage's original implementation
(`4bf34600`, `git log -p` confirms the line is unchanged since inception) —
it is not a recent regression by itself. It is a design assumption ("the
signal layers are always named F.Cu/B.Cu") that was true before this board
had a 4-layer stackup with F.Cu/B.Cu repurposed as planes, and stayed
syntactically valid but became **functionally wrong** the moment Bug A
started excluding F.Cu/B.Cu from `routing_spaces`. With both bugs
combined, `state.channel_skeletons == {}` unconditionally, regardless of
whether `In1.Cu`/`In2.Cu` are present and usable — Bug B never checks them.

`ModelBuilder._create_per_net_channel_vars`
(`packages/temper-placer/src/temper_placer/router_v6/constraint_model.py`)
iterates `for layer_name, skeleton in self.skeletons.items()` — with an
empty dict, zero `NetChannelVar`s are created, for **every** net,
regardless of `enable_geographic_pruning`, exactly matching the concurrent
agent's independent measurement (`nets=110, skeletons=0, variables=0,
constraints=0`, identical with the pruning flag True/False — both loop over
the same empty dict).

## 3. Direct measurement, confirming the mechanism end-to-end at HEAD

Ran `route_pcb()` directly against `pcb/temper.kicad_pcb` (same call shape
as `test_production_board_routing_drc_regression`), with `ModelBuilder.build`
monkeypatched to print stats:

```
[TRACE] ModelBuilder.build() called: nets=110 skeletons=0 enable_geographic_pruning=False
[TRACE] ModelBuilder.build() done: variables=0 constraints=0
[TRACE] route_pcb() wall time: 92.91s
[TRACE] completion_rate=0.37755102040816324
[TRACE] routed_pcb_content is None: False
```

`route_pcb()` **does not error and does not hang** — it completes in ~93s
and returns a routed board with 37.75% completion. The empty Stage-3 model
means Stage 3 contributes nothing; the ~38% completion comes entirely from
whatever fallback the pipeline runs afterward (per-net "legal path" search —
the log shows per-net `✓ routed successfully` / `✗ FAILED: no legal path
found (forced segment disallowed)` lines, not a SAT solve). This is
consistent, almost to the point, with `docs/evidence/2026-07-27-committed-route.md`'s
"37.5%" figure and `docs/evidence/2026-07-27-router-determinism.md`'s N=10
all-37.5% characterization (§5 below).

Repeating the same call through `scripts/route_board.py`'s default
(`keep_existing_copper=False`) path — which strips `(segment ...)`,
`(via ...)`, and `(zone ...)` blocks from a temp copy before parsing —
produces the opposite result. Instrumented the same way, stopping
immediately after `ModelBuilder.build()` is entered:

```
Extracted 29459 skeleton lines
Added 511 / 497 pad anchor nodes to skeleton
[TRACE] ModelBuilder.build() called: nets=110 skeletons=2 skeleton_layers=['F.Cu', 'B.Cu'] enable_geographic_pruning=False
```

`skeletons=2` (F.Cu and B.Cu both present, non-empty) — because the input
to the parser is a temp file with no zones, so Bug A never fires and Bug B's
hardcoded F.Cu/B.Cu restriction, for once, matches reality. Model
construction was still running (RSS climbing past 4 GB) when this
observation was recorded; independent corroboration that this path
reliably produces the full-size model comes from
`docs/evidence/2026-08-07-r3-frozenset-order-verification.md` §4, which
records a **real SIGKILL at ~12,448 MB RSS after ~7 minutes**, via the same
`route_board.py`-shaped call, on the exact board content in this worktree
(same 2290-segment/96-zone board), attributed there to environmental memory
pressure (<1 GB free at attempt time) — the same explanation
`2026-08-07-router-oom-diagnosis.md` gives.

**This resolves the stated contradiction.** A 42M-variable model and a
0-variable model are not describing the same computation on the same board
under the same code — they are describing the *same board content* fed
through two different preparation steps. Stripping existing copper before
parsing (route_board.py's default, and the only board-regeneration
producer) avoids Bug A entirely and gets the real, large, OOM-capable
model. Parsing the committed file directly (the CI DRC gate, and most
evidence-doc scripts) hits Bug A and gets nothing.

## 4. Where the committed board's 2290 segments came from

Not from a currently-working router run, and not imported from elsewhere —
they are `556ccf4f`'s own output, lightly edited twice since, never
re-routed:

1. `556ccf4f` (2026-07-27T18:28:22-06:00): `route_pcb()` run against the
   board **before** it had any zones (`docs/evidence/2026-07-27-committed-route.md`:
   "Board going in: ... 0 segments / 0 vias / 0 zones"). At that moment Bug
   A had nothing to condemn F.Cu/B.Cu with, so the real SAT-driven Stage 3
   ran, producing 51/96 = 53.1% completion, 2338 segments, 48 vias, 96
   zones (zone pours are a separate output of the same call, from the pour
   stage, not from Stage 3's SAT model). This is the last — and only —
   time this board was routed by a working model.
2. `e5a89b1e` (2026-08-05, #771): a **direct 48-line deletion** of
   `pcb/temper.kicad_pcb` removing exactly the 48 zero-length
   `(segment ...)` stubs (one per via, an unrelated emission bug in
   `_write_routes_to_content`'s path-merge loop). No re-route; commit
   message: "Also removes the 48 from `pcb/temper.kicad_pcb` (48 deletions,
   0 insertions, nothing else touched)." 2338 → 2290.
3. `7e3608bc` (2026-08-06, #711): moves one component (R24) by one line to
   clear a mains↔SELV isolation-barrier admissibility failure. Does not
   touch segments/vias/zones (still 2290/48/96 today).

Every attempt to re-route this board since `556ccf4f` — via the direct path
— has produced the degraded ~37.5% fallback, not a replacement route, and
none of those attempts overwrote the committed file (evidence docs
consistently note `route_pcb()` returns content in memory; nothing in this
period wrote `pcb/temper.kicad_pcb` from a fresh route).

## 5. The "37.5%-53.1% non-determinism" was this transition, misdiagnosed

`docs/evidence/2026-07-27-committed-route.md` (provenance: `556ccf4f`
itself) ran 4 routing passes to test whether the Stage-3 speed fix changed
completion rate:

| Run | Completion | When, relative to the transition |
|---|---:|---|
| 1 (committed) | 51/96 = 53.1% | Board going in had 0 zones — this run *is* the transition; its own output became `556ccf4f` |
| 2 | 36/96 = 37.5% | Board on disk now has `556ccf4f`'s 96 zones — Bug A live |
| 3 (DRC on) | 36/96 = 37.5% | Same |
| 4 (DRC on, repeat) | 36/96 = 37.5% | Same |

The doc treats this as "real process-to-process variance... root cause
UNVERIFIED (candidates: PYTHONHASHSEED, SAT-solve timing jitter)." The
follow-up, `docs/evidence/2026-07-27-router-determinism.md` (`9abf7ef88`,
2026-07-27 18:30 — **two minutes after `556ccf4f`**), found and fixed a
real, separate bug (`uuid4()`-generated `tstamp` fields making every route's
byte content differ even when structurally identical) and its own N=10
characterization landed on 37.5% in **every single run** — never 53.1%
again. Both docs' own data is consistent with the transition documented
here: run 1 is the last pre-transition measurement; every run after it,
including all 10 in the determinism doc, is post-transition. Neither doc
made the connection because neither compared a 53.1%-completion output
against a 37.5%-completion output byte-for-byte — the determinism doc only
diffed two *same-completion* (37.5%) runs against each other, which by
construction cannot reveal what changed between the two completion levels.

## 6. Invalidated measurements

Full doc-by-doc audit against the transition (`556ccf4f`,
2026-07-27T18:28:22-06:00) and the direct-vs-stripped-copper path
distinction from §3:

| Doc | Commit/date | Before/after transition | Code path | Verdict |
|---|---|---|---|---|
| `docs/STRATEGY.md` (all routing figures) | 2026-07-25 | Before | — | **Valid** — predates the board having any zones |
| `docs/evidence/2026-07-27-committed-route.md` | `556ccf4f` itself | Run 1 before / runs 2-4 after | Direct, unstripped | Run 1 (53.1%) is the last valid SAT-driven measurement; runs 2-4 (37.5%) are the *first* instances of this bug, recorded as unexplained "variance" |
| `docs/evidence/2026-07-27-router-determinism.md` | `9abf7ef88`, +2 min | After | Direct, unstripped | Its uuid4/tstamp fix is real and correct; its N=10 completion figures (all 37.5%) are the degraded-fallback path, and its "root cause UNVERIFIED" note for the completion level itself is this bug |
| `docs/evidence/2026-07-30-router-copper-shorts.md` | `bad833fb`, 2026-07-29 | After | Direct, `keep_existing_copper=True` | Absolute completion/segment figures (37.5%/35.4%, "36/96") are the degraded fallback; any purely-relative A/B comparison within the doc is internally self-consistent but not comparable to the pre-transition 50-53% baseline |
| `docs/evidence/2026-08-04-router-output-rebaseline-interim.md` | 2026-08-04 | After | Direct, via `test_production_board_routing_drc_regression` | DRC baselines re-measured on the degraded fallback's output, not real SAT-driven routing |
| `docs/evidence/2026-08-05-r3-router-status.md` | `c6b5402684`/`f2c5af948` | After | `route_board.py`-shaped (`--runs 1`, `route_once()`) | OOM figures are a genuine measurement of the large-model path (§3); its own "37.5% vs 53.1%, NOT RE-VERIFIED" note is exactly this transition, already sensed but not resolved |
| `docs/evidence/2026-08-07-router-oom-diagnosis.md` | `f7a1fbf8f`, dirty=true | After | Claims same path as the direct-call CI test | **Central claim is false.** The CI test it cites as "same code path, passed at 56s" uses the direct/unstripped path, proven here to build a 0-variable model, not 42M. `dirty=true` means this doc's own measurement state is unknown; its "no commit changes the model size" conclusion does not hold for the path it names |
| `docs/evidence/2026-08-07-r3-frozenset-order-verification.md` | `00ec5f94a` | After | `route_board.py`-shaped (board-regeneration producer) | **Valid** as an OOM data point for the large-model path — corroborates §3 directly |
| `docs/evidence/2026-08-07-router-encoding-u3u4.md`, `docs/evidence/2026-08-07-pruning-u1u2-implementation.md` | 2026-08-07 | After | Synthetic/unit-test CNFs only | Not applicable — both explicitly defer production-board measurement to a future step not yet done |
| `power_pcb_dataset/drc_ceiling.json` | `3410ee4e1` | After | Static-file DRC on the committed `.kicad_pcb`, no `route_pcb()` call | Not applicable to this bug (already independently stale, unrelated provenance-hash mismatch per `AGENTS.md`'s DRC-ceiling section) |
| `packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py::test_production_board_drc_regression` | (test, not a doc) | — | DRCs the committed file directly, no route call | Not applicable — its own docstring already notes it measures the file "as committed at `556ccf4f`" |
| `...::test_production_board_routing_drc_regression` | re-baselined 2026-07-28, -29, 08-02, 08-03, and the 2338→2290 shape re-baseline (08-05/08-06) | After | Direct, unstripped | **Every baseline in this test since 2026-07-27 evening has been chasing the degraded fallback's output**, not real routing. This is the CI gate for the board's routing DRC. |

**Not invalidated, and outside this bug's blast radius:** anything that
never calls `route_pcb()` against a zoned board directly — placement
(CP-SAT), netlist/schematic validation, static DRC on the committed file,
Rust unit/differential tests on synthetic CNFs, and the `route_board.py`/
board-regeneration-producer measurements, which structurally avoid Bug A by
stripping copper first.

## 7. Is #871 still live?

**Yes — but only via the code path that produced it, not via the direct
production entry point the CI DRC gate uses.**

Issue #871 ("route_pcb() OOM at >13 GB RSS") cites
`docs/evidence/2026-08-05-r3-router-status.md` §3, which used
`route_board.py --runs 1` / `route_once()` — the stripped-copper path. That
path is confirmed live and reproducible today: `skeletons=2` (non-empty,
§3), and `docs/evidence/2026-08-07-r3-frozenset-order-verification.md`
independently reproduced a real SIGKILL at ~12,448 MB RSS via the same
shape of call, on this exact board content, four days ago. `route_board.py`
is also **the only re-route producer this repo has** — `make route`'s
target, and the nightly `board-regeneration.yml` workflow's board writer
(`.github/workflows/board-regeneration.yml` → `route_board.py` →
`route_pcb`). So #871's OOM mechanism is not stale; it is the live state of
the one code path capable of regenerating this board.

What #871 as literally titled does **not** currently describe is the
direct/production `route_pcb()` call (`test_production_board_routing_drc_regression`,
and most evidence-doc scripts) — that path cannot OOM today because Bug A
+ Bug B together prevent it from ever building a model large enough to. The
issue's own text says "route_pcb() on the production board," which is
ambiguous between the two call shapes; as measured, the OOM only
reproduces through the stripped-copper shape.

## 8. Does any gate catch this?

**No.** Two mechanisms exist that look like they should, and neither fires:

**`validate_routing_space`** (`routing_space.py`, `register_validator`)
iterates `for layer_name, rs in state.routing_spaces.items()` and checks
each present layer's area is non-negative. It has no check for "did we
expect N copper layers and got fewer" — a layer that's silently *absent*
from the dict (Bug A's actual effect) produces zero failures, because the
loop never visits a key that isn't there.

**`validate_channel_skeleton`** (`channel_skeleton.py`) has the identical
shape: `for layer_name, skeleton in state.channel_skeletons.items()`,
checking each present skeleton's `node_count`. When `channel_skeletons ==
{}` (Bug B's effect once Bug A has emptied `routing_spaces` of F.Cu/B.Cu),
the loop body never executes and the validator returns `[]` — a clean pass
for a completely vacuous stage. This is a textbook instance of the failure
class `scripts/check_vacuous_gates.py` exists to catch (an aggregation over
a possibly-empty collection with no non-emptiness assertion in front of
it, `docs/METHODOLOGY.md` Sec 4-5).

**`scripts/check_vacuous_gates.py` does not scan `router_v6` at all.** Its
own docstring: *"Every `.py` file under `packages/*/src` ... except the
`router_v6` package — excluded per the forced-segment fail-closed plan
(`docs/plans/2026-07-24-001-fix-forced-segment-fail-closed-plan.md`); see
that plan's current status before assuming this exclusion still applies
(UNVERIFIED as of this rewrite — a concurrent agent is actively working
router_v6 code and this gate does not touch it)."* So even the
repo's general-purpose anti-vacuity linter would not have flagged either
validator above.

**`ModelBuilder.build()` has no non-emptiness assertion at all** — nothing
in `constraint_model.py`, `_pipeline_route.py`, or `adapter.route_pcb`
asserts `len(model.variables) > 0` (or checks `skeletons` is non-empty)
before proceeding. The pipeline runs Stage 3 → Stage 4 → fallback routing
→ returns a `RoutingResult` with a real (if degraded) `completion_rate`,
which reads as success at every layer above it.

**This absence is itself the most actionable finding in this diagnosis**:
a repo with an explicit "goal-set" anti-vacuity doctrine (`R9`/`R10` in
`docs/plans/2026-08-04-002-docs-temper-goal-set-plan.md`, applied so far to
safety-critical DRC constraint families) has no equivalent assertion for
"the router actually built something" on the one stage where it matters
most.

---

## Sources

- `docs/solutions/logic-errors/single-zone-condemns-whole-copper-layer-plane-2026-07-29.md`
  — Bug A, documented.
- `packages/temper-placer/src/temper_placer/router_v6/channel_skeleton.py:341-347`
  — Bug B, the F.Cu/B.Cu hardcode (`ChannelSkeletonStage.run`), and
  `:350-378` (`validate_channel_skeleton`, the vacuous validator).
- `packages/temper-placer/src/temper_placer/router_v6/routing_space.py:85`,
  `:193-217` — where a condemned layer's exclusion takes effect
  (`compute_routing_space`), and `validate_routing_space`, the other
  vacuous validator.
- `packages/temper-placer/src/temper_placer/router_v6/constraint_model.py:445-484`
  (`ModelBuilder.build`, `_create_per_net_channel_vars`).
- `scripts/route_board.py` — the stripped-copper path (`strip_existing_copper`,
  `route_once`), and its docstring's own note that this is `make route`'s
  and the board-regeneration producer's entry point.
- `scripts/check_vacuous_gates.py:40-44` — the `router_v6` exclusion.
- `docs/evidence/2026-07-27-committed-route.md`,
  `docs/evidence/2026-07-27-router-determinism.md` — the misdiagnosed
  53.1%→37.5% transition.
- `docs/evidence/2026-08-05-r3-router-status.md`,
  `docs/evidence/2026-08-07-router-oom-diagnosis.md`,
  `docs/evidence/2026-08-07-r3-frozenset-order-verification.md` — the OOM
  chain, and the doc whose central claim this diagnosis refutes.
- `docs/evidence/2026-07-28-stackup-partial-revert.md` — the deliberate
  `60d441f2` revert decision and its 3.12%-vs-38.54% measurement.
- Issue #871.
- Commits: `556ccf4f` (transition), `a1fe623e`/`60d441f2` (the brief fix
  and deliberate revert), `81f3c69a` (predicate improvement, quantifier
  bug left live by design), `e5a89b1e`/`7e3608bc` (the two post-transition
  edits to the committed board, neither a re-route), `4bf34600` (Bug B's
  origin, pre-dates this board having 4 copper layers).
