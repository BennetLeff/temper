<!-- provenance: commit=775a7a40e72048846474d74d22461df8bbc42765 (main, HEAD at start of this task), worktree agent-a4e5afd80067cb887.
pcb/temper.kicad_pcb sha256 33205399398fa053d93c046a460272ede4a728701d6f34c3c2bac6796e953962
verified unchanged before, during, and after this task (never opened for writing --
analysis and read-only scripts only). uv sync --all-packages + make extensions run in
THIS worktree's own .venv (not the shared repo .venv). Prototype script committed
separately: 96ae9df49 (scripts/check_placement_pair_creepage.py). This doc: commit
following 96ae9df49. -->

# Spike: does the CP-SAT placer know about creepage/clearance, and would it have avoided J1/K1?

**Bottom line.** The placer does not enforce PD3 creepage anywhere in its default
path. A correct, sound, already-implemented mechanism for exactly this
(`domain_clearance.py`) exists in the codebase and is wired into exactly one place —
a narrow single-component repair CLI, never the main placement solve. The gate
that looks like it should catch this (`IECCreepageGate`) is a post-hoc,
already-routed-board verdict that is, separately, never even registered in any
gate list the production loop actually runs. And the one cross-class separation
mechanism that *is* live by default (`netclass_constraints.py`) uses a
name-pattern net classifier that misclassifies K1's mains-connected relay
contacts as "signal" — the same bucket as J1's RTD sense lines — so it generates
**zero** constraint for the exact pair that produced the unroutable placement.
This is not one gap; it is three independently-maintained classification/margin
systems, only one of which has the correct number, and that one is disconnected
from the solve.

A near-identical full-board wiring of the correct mechanism was already measured
once, at a slightly lower margin (2026-07-30, PD2-era 8.0/10.0mm): 11,856
pairwise constraints over 158 classified components, CP-SAT solved to `optimal`
in 40.5–82.2 seconds. This is direct evidence the design is computationally
tractable, not a guess.

---

## 1. What the placer's CP-SAT model actually enforces today

Traced from constraint construction in `packages/temper-placer/src/temper_placer/placer/cp_sat/`,
not from file names or docstrings.

`_encoder_solve.py::solve_placement()` is the single production entry point
(`PlaceRouteLoop` and `temper optimize` both funnel through it). Its constraint
sources, and whether each is live by default:

| Mechanism | Margin used | Classifier | Live by default in `temper optimize` (`--loop`, no flags)? |
|---|---|---|---|
| `_generate_courtyard_separated_constraints` (`_encoder_core.py`) | `ctx.courtyard_clearance_mm`, one flat scalar for **every** pair | none (uniform) | Yes — but knows nothing about voltage/domain |
| `netclass_constraints.py::generate_netclass_separated_constraints` | `DesignRules.get_rules_for_net(class).clearance` per cross-class pair | `classify_net_type()`, a **net-name keyword heuristic** (ground/power/hv/signal, 4 buckets) | **Yes**, unconditionally — `_encoder_solve.py:635` calls it inside `solve_placement` itself, not CLI-gated |
| `tank_creepage.py::add_tank_creepage_to_model` | `DEFAULT_TANK_CREEPAGE_MM` = 10.0mm (correct PD3 figure for the tank row) | narrow: `tank.c_tank1-p2` vs. every classified-HighVoltage component only | **Only on `--no-loop`** (`cli/__init__.py:676`) — absent from the default `--loop` path entirely (`_loop_core.py::_call_solver`'s `solver_kwargs` dict has no `tank_creepage` key) |
| `isolation_barrier.py::add_isolation_barrier_to_model` | corridor width, opt-in | HV/SELV via `elec/domain_manifest.yaml` | No — opt-in kwarg, never passed by CLI. Also: the module's own docstring records the barrier as **provably infeasible on this board's actual layout** (HV/SELV interleave board-wide) |
| `domain_clearance.py::generate_domain_clearance_constraints` | `IEC60335_REQUIREMENTS[(domain_a,domain_b,insulation)]` — **carries the correct 12.6mm PD3 reinforced figure** | `VoltageDomain` via `elec/domain_manifest.yaml` (same source the CI-gate validator uses) | **No.** Only caller in the entire `src/` tree is `cli/repair_commands.py`'s `repair-unplaced` subcommand (a single/few-component minimal-disruption repair tool) and `_encoder_solve.py`'s own post-solve audit path (which needs the constraint list already built by a caller — nothing builds one by default) |

**The one mechanism with the correct 12.6mm PD3 number
(`domain_clearance.py`) is never called by the code path that produces
`pcb/temper.kicad_pcb`'s placement.** Confirmed by exhaustive grep of every
call site of `generate_domain_clearance_constraints` /
`generate_unclassified_hv_keepaway_constraints` in `src/`: `domain_clearance.py`
itself, `cli/repair_commands.py` (3 call sites, all inside the `repair-unplaced`
command body), and nowhere in `loop.py`, `_loop_core.py`, `_encoder_core.py`, or
the `optimize` CLI command.

### 1a. The mechanism that *is* live by default actively fails on K1

`netclass_constraints.py`'s classifier is a plain net-name keyword match
(`temper_placer.core.net_classification.classify_net_type`). Probed directly
against this board's real net names:

```
rtd_force_p      -> signal
rtd_sense_n      -> signal
rtd_sense_p      -> signal
power_in.ntc-no  -> signal   <- K1's HV relay contact, per elec/domain_manifest.yaml
w1_2             -> signal   <- K1's HV relay contact, per elec/domain_manifest.yaml
w1_1             -> signal
ac_l             -> hv
ac_n             -> hv
```

Only `ac_l`/`ac_n` classify as `"hv"` under this heuristic. K1's own
contact-tab nets (`power_in.ntc-no`, `w1_2` — declared **HV** in
`elec/domain_manifest.yaml`, the design's actual, hand-reviewed domain
authority) fall through to `"signal"`, the exact same bucket J1's RTD nets
land in. In `generate_netclass_separated_constraints`, `ca == cb` for the pair
`(J1, K1)` (`netclass_constraints.py:122`, `if ca == cb: continue`) — **no
constraint is generated for this pair at all**, by the one mechanism that
runs unconditionally on every solve. `elec/domain_manifest.yaml`'s own ground
rule states this exact failure mode by name: "net names lied in this design
... domain membership must never be inferred from how a net is spelled" — a
rule this specific live-by-default mechanism does not follow.

---

## 2. Is `IECCreepageGate` a constraint or a verdict?

**A verdict, and an orphaned one.**

`gates.py::IECCreepageGate.check()` requires `state.routed_pcb_path` to
already exist (`gates.py:757`) — it runs `kicad-cli pcb drc` on a **routed**
board and filters clearance violations whose net pair crosses HV/LV. It
cannot run before routing and therefore cannot influence placement; by the
time it has an opinion, the router has already spent time trying (and, for
J1's three RTD nets, failing) to route the pads this gate would flag.

It is also never reached. `PlaceRouteLoop`'s gate registry
(`_loop_core.py:142-190`) is exactly one of two fixed lists:

```
all_gates=False (default): [DrcGate, RoutingGate]
all_gates=True  (--all-gates): [DrcGate, RoutingGate, StackupGate, PhysicsGate, QualityGate]
```

`IECCreepageGate` and `ErcGate` are in neither list, in either mode, anywhere
in `loop.py` / `_loop_core.py`. Confirmed by grep: `IECCreepageGate()` /
`ErcGate()` are instantiated only inside their own unit test files
(`test_physics_gate.py`, `test_erc_gate.py`, `test_coverage_paydown_v22.py`) —
never in production code. This is the handoff's mechanism 2 ("the live path
is not where it looks") applied to a gate whose *name* says "IEC creepage":
it reads as the safety gate for exactly this defect class and is dead code
outside its own tests.

**Its number is stale regardless.** `IECCreepageGate.check()` hardcodes
`severity=6.0, threshold=6.0` (`gates.py:803-804`) — a flat 6mm HV↔LV figure,
not the 12.6mm PD3 reinforced figure this project's own SSOT settled on
(handoff §2, PR #1219/#1224). `PhysicsGate`'s internal creepage sub-check
(the one gate of the two live-by-default-eligible sets that *does* mention
creepage) hardcodes the same `6.0`. `DeltaMapper.map()`'s `CREEPAGE` branch
(`delta_mapper.py:148-167`) — the mechanism that would turn a gate violation
into a corrective constraint for the *next* solve round, i.e. the one place
a genuine iterative "measure, then constrain" loop exists in this codebase —
sets `min_dist = violation.threshold`, inheriting the same stale 6.0mm. So
even in the one configuration where creepage feedback is structurally wired
(`--all-gates`, via `PhysicsGate` → `to_delta` → `DeltaMapper`), it converges
on a value 6.6mm short of what the board's own DRU actually requires — a
second, independent instance of the "one fact, many homes, drifting"
mechanism (handoff §3.1), inside the very machinery meant to close the loop.
A prior evidence doc (`docs/evidence/2026-08-07-creepage-authority-and-pullback-analysis.md`)
independently found and flagged this exact 6.0mm figure as
non-conservative and superseded, for a sibling code path
(`design_rules.py`'s netclass `creepage_mm` field) — this spike found the
same number, independently reintroduced, inside the gate/delta-mapper layer.

**Conclusion for item 2:** creepage knowledge in this codebase exists in
exactly one live, wired, board-scale form today
(`netclass_constraints.py`, §1a) and it is wrong for K1 specifically. Every
other creepage-aware code path is either a verdict that runs after the
router has already tried and failed (`IECCreepageGate`, `--all-gates`'s
`PhysicsGate` sub-check), unregistered dead code (`IECCreepageGate`,
`ErcGate`), or a correct-and-sound constraint generator that nothing calls
by default (`domain_clearance.py`).

---

## 3. The generated pairwise tables: right shape, wrong consumer

`packages/temper-placer/configs/pair_clearance.generated.yaml` /
`pair_creepage.generated.yaml`, emitted by `scripts/generate_kicad_dru.py`
from the safety SSOT, carry the correct current figures — spot-checked
directly: `Default|HighVoltage: 12.6` in `pair_creepage.generated.yaml`,
matching PD3 reinforced. Their **only** production consumer, confirmed by
grep of every import site, is `temper_placer.router_v6.pair_creepage` /
`pair_clearance` — the N-layer A* obstacle-halo stamping the router uses
*after* placement is fixed (per PR #1267, per the handoff). Nothing in
`placer/cp_sat/` imports either file.

This is a genuinely different classification scheme from `domain_clearance.py`'s:
`pair_creepage.generated.yaml` is keyed on 14 **KiCad NetClass** names
(`ACMains`, `HighVoltage`, `HighVoltageSignal`, `HighVoltageTank`,
`HighVoltageIsolated`, `GateDriveHV`, `GateDriveSELV`, `Default`, ...),
resolved from `pcb/temper.kicad_dru`'s own rule text under KiCad's
last-matching-rule-wins precedence. `domain_clearance.py`'s
`IEC60335_REQUIREMENTS` is keyed on 5 **VoltageDomain** buckets (`MAINS`,
`DC_BUS`, `LV_CONTROL`, `ISOLATED`, `BOOTSTRAP`), resolved from
`elec/domain_manifest.yaml`. Both currently agree on the number (12.6mm PD3
reinforced for an HV↔LV-equivalent pair) — but they are two independently
maintained SSOTs describing the same physics, and nothing enforces that
agreement; the project's own history (handoff mechanism 1) is a long list of
exactly this kind of pair drifting.

**The data pipeline works end to end, proven directly, not inferred.**
`scripts/check_placement_pair_creepage.py` (committed separately, commit
`96ae9df49`) is a ~230-line standalone, read-only script that loads
`pair_clearance.generated.yaml` + `pair_creepage.generated.yaml` via their
existing production loaders (`router_v6.pair_clearance.load_pair_clearance_table`
/ `router_v6.pair_creepage.load_pair_creepage_table`), classifies every pad's
net via `create_temper_design_rules().get_class_for_net()` (the same
classifier the DRU tables were resolved against), computes every pad's
world position via the canonical rotation-aware `core.pin_geometry.pin_world_position`
/ `pin_world_radius` (the same functions the router trusts, and the same
ones the independent J1/K1 diagnosis in
`docs/evidence/2026-08-17-per-pair-clearance-halo-regression-nets.md`
cross-checked against a naive reading before trusting), and reports every
cross-class pad pair whose conservative gap (`center_distance - radius_a -
radius_b` — an under-estimate of true separation, so this can only
over-report, never under-report, a violation) is below the required
`max(clearance, creepage)`.

Run against the current board (523 net-bearing pads, 136,503 pad-pairs
checked, sub-second):

```
$ .venv/bin/python scripts/check_placement_pair_creepage.py --refs J1,K1 --top 15
...
ref_a  ref_b  class_a   class_b       gap_mm   req_mm kind       net_a / net_b
J1     K1     Default   HighVoltage     1.36    12.60 creepage   rtd_force_p / w1_2
```

This independently reproduces the J1/K1 finding from
`docs/evidence/2026-08-17-per-pair-clearance-halo-regression-nets.md` — using
a completely different code path (no router, no A* grid instrumentation, no
routed board required) and a different, more conservative geometric model
(circumscribing pad radius vs. that doc's exact rotated-rectangle pad edges,
which is why the reported gap here, 1.36mm, is smaller than that doc's
4.05mm pad-edge measurement — both agree the pair is far short of 12.6mm; the
difference is exactly the documented conservatism of the circle-radius
model). **86 distinct component-ref pairs** violate this way board-wide —
substantially more than the "14" figure the handoff cites, because that
figure comes from the `VoltageDomain`/`elec/domain_manifest.yaml` classifier
(3 populated buckets: MAINS/DC_BUS/LV_CONTROL) while this script uses the
finer 14-class KiCad NetClass table, which draws more pairs as
cross-class. This numeric gap between the two classifiers, on the identical
board, at the identical instant, is itself worth flagging: it is a live,
measured instance of the same "two homes, one fact" pattern as §1a and §2,
not a contradiction to resolve by picking whichever number is smaller.

---

## 4. Would a creepage-aware placer have avoided J1/K1, or proven infeasibility?

**It would very likely have forced the solver to either relocate J1's local
neighborhood or report the model infeasible — both strictly better outcomes
than what happened.** Evidence, not speculation:

1. `elec/domain_manifest.yaml` already, correctly, classifies J1's
   `rtd_force_p`/`rtd_force_n`/`rtd_sense_p`/`rtd_sense_n` as **SELV** and
   K1's `power_in.ntc-no`/`w1_2` as **HV** (manifest lines 106, 187, 449-452).
   `io/real_board.py::_domain_for_manifest_domain` maps these onto
   `VoltageDomain.LV_CONTROL` and `VoltageDomain.DC_BUS` respectively (only
   `ac_l`/`ac_n` map to `MAINS`; every other HV net maps to `DC_BUS`, which
   the module docstring documents as intentional — every matrix row that
   fires for `MAINS` fires identically for `DC_BUS`).
2. `IEC60335_REQUIREMENTS[(DC_BUS, LV_CONTROL, REINFORCED)]` =
   `min_creepage_mm: 12.6` (`requirements/validators/clearance.py:278-281`,
   matching the Rust mirror `req_safe_01.rs:1124`) — the current, correct PD3
   figure, and `generate_domain_clearance_constraints` takes the **max**
   across every matching matrix row per pair (docstring: "the stricter one
   wins"), so a J1↔K1 pair would be constrained at 12.6mm regardless of
   whether the encoder also matches a basic-tier row.
3. Therefore, if `generate_domain_clearance_constraints(placement,
   voltage_domains, component_refs)` — using exactly this manifest and this
   matrix, both already correct and already used by the CI-gate validator —
   were included in `solve_placement`'s constraint set, it would emit a
   **HARD** `SeparatedConstraint(J1, K1, min_distance_mm=12.6)`, encoded as a
   Chebyshev box-separation disjunction with a machine-checked soundness
   proof (`domain_clearance.py`'s module docstring, BMC-exhaustive tested by
   `test_domain_clearance.py::TestChebyshevSoundnessBMC`).
4. The independent router-side diagnosis
   (`docs/evidence/2026-08-17-per-pair-clearance-halo-regression-nets.md`
   §2.3) already established, by direct 1,000,000-iteration-budget grid
   search on every routable layer, that **J1 is boxed in by six other
   components (C9, SW1, R45, R54, R58, U22) in addition to K1, regardless of
   layer** — there is no legal routing escape today. A hard 12.6mm
   box-separation constraint between J1 and K1 interacts with the *existing*
   courtyard/netclass constraints already holding those same six neighbors
   in place: satisfying the new constraint requires moving J1 far enough
   that the neighborhood's other constraints must also re-solve, which is
   precisely the class of problem CP-SAT (a global solver over all
   components simultaneously) is suited for and manual point-fixes (#1248,
   #1269, #1279) are not — those PRs each moved a handful of components by
   hand, in sequence, without ever seeing this constraint at all.
5. **Both possible outcomes are the honest, wanted result.** If a
   satisfying rearrangement exists, the solver finds it — J1 (or K1, or
   both) moves before any router time is spent on nets that cannot legally
   connect. If no rearrangement exists at this board outline with this
   component set, CP-SAT reports `infeasible` with a `SufficientAssumptionsForInfeasibility`
   core naming exactly which constraints conflict (the same UNSAT-core
   machinery `repair_commands.py` already surfaces for its narrower use
   case) — an early, precise, honest "this outline cannot satisfy its own
   PD3 rule with this component set" instead of the current loop's
   discovery path (place → route → DRC → notice 5 pairs are "physically
   infeasible" only after full routing was attempted).

**What this spike did not do:** re-run a full 168-component
`generate_domain_clearance_constraints` + `solve_placement` at the current
12.6mm PD3 margin on today's board and observe whether it returns `optimal`
or `infeasible`. That is the natural, bounded next step (§7) and was judged
out of scope for a spike given the time a full CP-SAT solve plus routing
re-verification would take on top of the investigation above — but §5 below
gives a direct, measured data point at a nearby margin (8.0/10.0mm) on this
same mechanism, which is the basis for "would very likely have," not a
guess.

---

## 5. The router's solvers: still downstream of placement, still not creepage-aware at the capacity-assignment stage

`packages/temper-rust-router-core/src/direct_topology.rs` (the direct,
capacity-aware topology solver that replaced the vacuous Stage-3 SAT,
PR #1260) assigns each net's skeleton-graph path with a capacity-aware
Dijkstra where an edge's usable capacity is reduced by `trace_width +
clearance` (`DirectNet.width`, module docstring "Capacity semantics mirror
the SAT model exactly"). This is **uniform CLEARANCE headroom per edge**,
computed once as a scalar per net — there is no NetClass or VoltageDomain
lookup anywhere in this file, no per-pair table, no HV/LV distinction.
Creepage-awareness in the router lives one stage later, in Stage 4's
occupancy-grid A* obstacle-halo stamping (`router_v6.pair_creepage`, PR
#1267) — which is exactly the mechanism that correctly, fail-closed, refused
to route J1's three RTD nets in §2.3's diagnosis above.

So: neither router stage can relocate a component (placement is already
fixed by the time either runs), and neither is a defect — Stage 4's refusal
is the system doing the right thing given an unroutable placement. The
question the task poses ("does this knowledge belong earlier") has a direct
answer: yes, both router stages are structurally incapable of fixing a
placement-level violation; the earliest point in the pipeline capable of
*avoiding* rather than merely *detecting* J1/K1 is the CP-SAT placement
solve, which is exactly where `domain_clearance.py` already lives, unwired.

---

## 6. Feasibility and cost — measured, not estimated

**Directly measured evidence exists for this exact mechanism, at a nearby
margin, on a comparably-sized board state**
(`docs/evidence/2026-07-30-copper-aware-domain-resolve.md` §3, predating the
PD2→PD3 decision, so at 8.0mm/10.0mm rather than today's 12.6mm):

| Margin | Constraints generated | Classified components | CP-SAT status | Solve time |
|---|---|---|---|---|
| 8.0mm | 11,856 | 158 / 168 | `optimal` | 40.5s |
| 10.0mm | 11,856 | 158 / 168 | `optimal` | 82.2s |

11,856 is close to the theoretical maximum `C(158,2) = 12,403` — i.e. at this
board's HV/SELV split, **nearly every pair of classified components crosses
a domain boundary**, so "cross-domain pairs only" is not a meaningfully
smaller subset than "all pairs" for this specific board. Despite that,
CP-SAT solved to `optimal` in under 90 seconds both times, well inside the
180s timeout given. `SeparatedConstraint`'s encoding (a 4-way Chebyshev
disjunction per pair, §4 point 3) is cheap per-constraint even at this
count — the prior Stage-3 SAT blowup (182–200GB, handoff §6) came from a
structurally different encoding (a sequential-counter `AtMostK` cardinality
constraint per capacity edge, not a simple box-separation disjunction) and
is not informative about this mechanism's cost.

**Scoping to only currently-violating pairs is unsound — proven, not
assumed.** The same evidence doc's §2 measured this directly: encoding only
the 21 known-violating pairs (rather than every classified cross-domain
pair) left every other pair unconstrained, and CP-SAT — free to drift
previously-compliant components anywhere else on the board while satisfying
the 21 explicit constraints — increased total REQ-SAFE-01 violations from
76 to 217–265. **The full classified-pair set must be encoded every time**,
which §"measured" above shows is affordable at this board's scale (~11,800
constraints, sub-90s).

**At today's 12.6mm PD3 margin, on today's board (168 components, some
different placements than 2026-07-30's baseline):** not separately
re-measured by this spike (see §4's stated scope limit). The 8.0mm→10.0mm
trend (40.5s → 82.2s, roughly 2× for a 2.0mm tighter margin) suggests 12.6mm
would take longer still, plausibly several minutes — still well inside
CP-SAT timeout budgets already used elsewhere in this project (180s–1000ms
defaults seen in various callers, easily raised for a placement solve that
currently has no time-box at all in practice, since it's a human-gated,
one-off operation per `Makefile`'s own comment: "CP-SAT placement is only
deterministic when it terminates without hitting its timeout, which is why
it is not automated"). **A cheaper proxy is not needed**: the full 12.6mm
figure is exactly what §5's evidence shows is tractable at a nearby margin,
and using a proxy would reopen the "which number is the real one" drift
problem this spike documents twice already (§2, §3). The existing
`audit_domain_clearance` (cheap, coordinate-only post-solve sanity check)
and `validator_audit.audit_domain_clearance_validator` (exact, re-runs the
CI-gate validator itself on the solved placement) are both already
implemented and should run after every solve regardless — that is the
project's own stated discipline (R24 item 3, "the audit is the one that
matters most").

---

## 7. Recommended design

1. **Wire `domain_clearance.generate_domain_clearance_constraints` into the
   default `solve_placement` path**, not just `repair_commands.py`. Concretely:
   `cli/__init__.py`'s `optimize` command already loads exactly the inputs
   this needs (`_build_validator_input(input_pcb)`, used today only for the
   post-hoc `validator_input` audit) — extend that same load to also build
   the constraint list and pass it through `extra_constraints` (or a new
   dedicated `domain_clearance=` kwarg mirroring `tank_creepage=`'s shape) on
   **both** the `--loop` and `--no-loop` paths. This closes the gap
   identified in §1 with no new data derivation: the loader, the matrix, and
   the classifier already exist and are already correct.
2. **Always encode the full classified cross-domain pair set**, never a
   subset scoped to currently-known violations (§6, proven unsound). Filter
   only by `touch_refs`/`component_refs` the way `repair_commands.py`
   already does for its narrower minimal-disruption case — full-board solves
   need the full set.
3. **Retire or fix `netclass_constraints.py`'s classifier** (§1a). At
   minimum, stop treating it as an adequate substitute for domain-aware
   creepage: it is live by default today and silently produces zero
   protection for exactly the K1/J1-shaped case (an HV net whose name
   doesn't contain an HV-sounding keyword). Either point it at
   `elec/domain_manifest.yaml`'s classification (making it redundant with
   `domain_clearance.py`, which then becomes the one thing to fix instead of
   two) or explicitly document it as courtyard-density-only and unrelated to
   safety, so nobody reads its presence as coverage.
4. **Fix or remove `IECCreepageGate` / `PhysicsGate`'s creepage sub-check's
   hardcoded 6.0mm** (§2) — it is stale under the current PD3 SSOT
   independent of whether the gate is ever wired in, and the same number
   propagates into `DeltaMapper`'s feedback path. If `IECCreepageGate` stays
   unregistered, say so in the module docstring rather than leaving a
   plausible-looking, fully-implemented, tested class that nothing calls.
5. **Reconcile or explicitly document the three classifiers** (§1a's
   name-keyword heuristic, §3's KiCad-NetClass DRU tables, §4's
   `elec/domain_manifest.yaml`-backed `VoltageDomain`). They currently agree
   on the PD3 number by coincidence, not by construction; `domain_clearance.py`
   already has a `MAX_IEC_MARGIN_MM`-style pattern (deriving a bound from the
   matrix rather than hardcoding it) that is the right template for the
   other two to follow.
6. **Run `audit_domain_clearance` + `audit_domain_clearance_validator` after
   every solve** (already implemented, R24 items 2–3) — box-separation SAT is
   a sound but not sufficient guarantee (it does not cover intra-footprint
   straddlers, §domain_clearance.py's documented limitation, nor
   trace/via-level creepage during routing, which stays the router's job via
   #1267's halos).
7. **Do not treat this as a proxy-vs-exact tradeoff.** §6 found the exact
   12.6mm PD3 figure tractable at a nearby margin; use it directly rather
   than inventing a cheaper approximation that reintroduces the
   many-homes-one-fact problem this spike documents happening twice already
   on this exact board.

**Cost of implementing this properly**: primarily wiring and testing, not
new modeling. Every piece — the correct matrix, the correct classifier
source, the constraint generator, its soundness proof, its BMC-exhaustive
test, and both post-solve audits — already exists and is already used
elsewhere (`repair_commands.py`, the CI-gate validator). The work is:
(a) building the constraint list at the same point `_build_validator_input`
already runs, (b) threading it through both CLI paths, (c) re-verifying
solve time at the real 12.6mm margin and board size (§6's stated gap),
(d) deciding what to do about the three-classifier drift (§7.5) and the two
stale-6.0mm sites (§7.4) as separate, smaller fixes. None of this requires
new CP-SAT machinery, a new constraint type, or a new data source. It is
**not** a weekend job, because (c) alone (a full board re-solve, then a full
re-route + DRC pass to confirm the new placement is actually an improvement,
not just PD3-clean) is the same multi-hour cycle every placement change in
this project has needed — but it is materially smaller than "large
architectural change": no new constraint semantics, no new solver, no new
data pipeline.

---

## 8. What this spike did not settle

- Whether `solve_placement` at 12.6mm PD3, full classified pair set, on
  *today's* 168-component board returns `optimal` (and where J1/K1's
  neighborhood lands) or `infeasible` (and what UNSAT core it names). §4/§6
  give strong grounds to expect a resolvable or cleanly-infeasible result,
  not a repeat of "silently produces a still-unroutable placement," but this
  was not re-run live in this task.
- Whether wiring `domain_clearance.py` in by default would regress solve
  time or completion on other, currently-passing parts of the board (the
  2026-07-30 evidence doc's own §3.2 found it moved effectively every
  component — 167/168 moved more than 1mm — which is expected for a
  first-time full-coverage encode, but means routing would need a full
  re-verification pass, not an incremental one).
- Resolution of the three-classifier drift (§7.5) or the two stale-6.0mm
  sites (§7.4) — flagged, not fixed, per this task's hard rule against
  changing any clearance/creepage/DRU threshold.

## Files referenced

- `packages/temper-placer/src/temper_placer/placer/cp_sat/domain_clearance.py` — the correct, sound, unwired mechanism
- `packages/temper-placer/src/temper_placer/placer/cp_sat/netclass_constraints.py` — the live-by-default, misclassifying mechanism (§1a)
- `packages/temper-placer/src/temper_placer/placer/cp_sat/gates.py` — `IECCreepageGate` (§2), `PhysicsGate`
- `packages/temper-placer/src/temper_placer/placer/cp_sat/delta_mapper.py` — stale 6.0mm feedback (§2)
- `packages/temper-placer/src/temper_placer/placer/cp_sat/_loop_core.py`, `loop.py` — gate registry (§2), constraint wiring (§1)
- `packages/temper-placer/src/temper_placer/cli/__init__.py` — the `optimize` command's two solve paths (§1)
- `packages/temper-placer/src/temper_placer/cli/repair_commands.py` — the only current caller of `domain_clearance.py`
- `packages/temper-placer/src/temper_placer/requirements/validators/clearance.py` — `IEC60335_REQUIREMENTS`, `VoltageDomain`
- `packages/temper-placer/src/temper_placer/io/real_board.py` — `elec/domain_manifest.yaml` loader, HV→MAINS/DC_BUS mapping
- `packages/temper-rust-router-core/src/direct_topology.rs` — capacity-only Stage 3 (§5)
- `packages/temper-placer/src/temper_placer/router_v6/pair_creepage.py`, `pair_clearance.py` — the router-only consumers of the generated tables (§3)
- `packages/temper-placer/configs/pair_creepage.generated.yaml`, `pair_clearance.generated.yaml` — correct data, wrong-only consumer (§3)
- `elec/domain_manifest.yaml` — the hand-reviewed domain authority (§4)
- `scripts/check_placement_pair_creepage.py` — prototype (§3), committed separately (`96ae9df49`)
- `docs/evidence/2026-07-30-copper-aware-domain-resolve.md` — the measured cost/feasibility evidence (§6)
- `docs/evidence/2026-08-17-per-pair-clearance-halo-regression-nets.md` — the original J1/K1 router-side diagnosis this spike cross-checks
- `docs/evidence/2026-08-07-creepage-authority-and-pullback-analysis.md` — prior, independent discovery of the same stale 6.0mm figure in a sibling code path
