# Methodology

How this project works. This document is durable — it should change rarely.
`STRATEGY.md` holds what we are building and where we honestly are; that
document churns by design.

---

## 1. What this project is

A **domain-specific place-and-route and verification system for mains-connected
kitchen-appliance power electronics.** The Temper induction cooker is instance
#1, not the end goal.

The domain is defined narrowly, on purpose, because an unbounded "domain" decays
back into a general-purpose EDA tool:

- mains-connected, one isolation barrier
- one or two switching power stages
- 150–400 nets, 2–4 layers, thick copper
- objectives dominated by creepage/clearance, thermal, switching-loop area, and
  current density
- output must be legible to a human safety assessor (IEC 60335-1 review)

Anything outside that envelope is out of scope by definition. This is a scope
bound with teeth; it exists so we can say no.

### Why domain-specific is merited

General autorouters optimize connectivity subject to DRC. Power electronics is
dominated by physics they do not model — switching loop area, gate loop
inductance, current density vs. copper cross-section, creepage across an
isolation barrier, thermal spreading, return-path continuity. A general router
will produce a DRC-clean board that fails CISPR and cooks the IGBT, and it will
be correct by its own objective function while doing so.

The defensible advantage is **not a better search algorithm — it is a richer
input contract.** DSN and netlist interchange destroy design intent at the
boundary. They cannot express "this is a gate loop, minimize its enclosed area"
or "these two domains must never share a return path." Ours can: the atopile
source already carries a semantic hierarchy (`hb.*`, `tank.*`, `safety.ovp.*`,
`discharge.*`, `power_in.*`, `thermal.*`, `rtd_pan.*`) that no external tool
will ever receive.

### The reusable asset

What makes appliance #2 fast is not primarily the router. It is the
**check corpus and the calibrated physics models** — encoded IEC 60335-1
clauses, datasheet-derived part rules, mined corpus invariants, and SPICE
models calibrated against real bench measurements. Routers can be bought. A
validated, coverage-measured, appliance-specific verification corpus cannot.

---

## 2. Four principles

1. **Software, simulation, and data are cheap.** Compute is nearly free.
   Physical ground truth is expensive and rate-limiting.
2. **Validation is only worth anything when the validators are correct.**
3. **Subdivision and tight loops are easier to validate, test, and verify.**
4. **Anything slow can be made fast.**

### The ordering constraint between them

**Principle 2 gates principle 4. Never optimize a loop you have not validated.**

A fast loop with a blind metric does not help — it reaches the wrong answer
sooner and with more confidence. See §7: 594 commits in 14 days against a
metric that could not observe the defect. Speed multiplied the error.

**Principle 1 is bounded by principle 2.** Simulation is only cheap *and*
useful once calibrated. Uncalibrated simulation does not reduce bench
iterations; it substitutes for them, which is how a board passes every model
we wrote and fails through a mechanism we never modeled.

---

## 3. The Loop Contract

Every loop in the pipeline declares this. It is the operational form of all
four principles.

```yaml
loop: <name>
input_precondition: <asserted at entry, never assumed>
output_metric: <what it measures>
blind_to: <failure modes this metric cannot observe>
oracle: <which falsification axes establish the metric is right>
cost: <wall time>
gate: <which STRATEGY.md gate this advances, or "hygiene">
```

Field by field:

- **`input_precondition`** — the missing one. Loops historically carried an
  output metric and trusted their input. Assert the input.
- **`blind_to`** — the most important field. Forcing an explicit statement of
  what the metric *cannot* see is the single cheapest defense against the
  failure in §7. Someone would have had to write `blind_to: board geometry
  validity`.
- **`oracle`** — see §5. A metric with no oracle is an opinion.
- **`cost`** — makes cheap loops visibly preferable and identifies what to
  subdivide.
- **`gate`** — the anti-spiral mechanism. A loop that advances no gate is
  hygiene, and hygiene draws from a budget (§8).

### 3.1 Seam contracts

The postcondition of stage N must equal the precondition of stage N+1, and the
equality is asserted. Fixing an individual bad input fixes an instance;
contracts at every seam eliminate the class.

### 3.2 What makes a loop validatable

Principle 3 claims small loops are easier to validate. That is true only for
loops with these properties, so they are the design target — not smallness by
itself:

- **pure** — no I/O, no global state
- **enumerable or densely samplable** input domain
- **deterministic**
- **has an independent oracle** (see §5)
- **fast enough to run thousands of cases**

Honest scoring of this pipeline's loops. Subdivision helps the front of the
pipeline far more than the back, and pretending otherwise is how a
methodology becomes decoration:

| Loop | Size | Pure | Enumerable | Oracle | Verdict |
|------|------|------|------------|--------|---------|
| Seam preconditions | 1 assertion | yes | yes | trivial | **excellent** |
| Netlist checks | ms | yes | yes (small graphs) | physics + corpus | **excellent** |
| Placement checks | ~1 s | yes | yes | KiCad differential | **good** |
| Congestion predictor | ~1 s | yes | no | only the router | **weak** |
| Full route | ~100 s | no | no | none direct | **poor** |
| Cost fields | varies | yes | no | none direct | **poor** (see §6.3) |
| Fault-injection harness | minutes | no | yes | known defect | **good, circular** |
| Simulation sweeps | hours | yes | no | bench (absent) | **batch, not a loop** |

Simulation is a slow oracle feeding fast loops, not itself a tight loop. Do not
count it as one.

### 3.3 Subdivision has a cost

**Subdivision trades intra-stage complexity for inter-stage interface count,
and interfaces are where bugs live.** The reference failure (§7) was a seam
bug — board definition to placement. More stages means more seams means more
of that failure class.

Subdivision is therefore *not* monotonically safer. It pays off only when every
new seam is contracted. Uncontracted subdivision is strictly worse than a
monolith, because a monolith has no interfaces to get wrong.

**Ordering rule: contracts before decomposition, always.**

### 3.4 Block decomposition

Routing is the hardest loop to subdivide — it is a global optimization and nets
interact through congestion. The decomposition is already present in the
atopile semantic hierarchy:

```
hb.*         half bridge
tank.*       resonant tank
safety.*     protection
discharge.*  bus discharge
power_in.*   mains input
thermal.*    fan / thermal
rtd_pan.*    pan sensing
```

**Route a block, verify it, freeze it, route the next.** Blocks that share no
nets interact only at boundaries, and boundaries take contracts. This yields
smaller routing problems, per-block verification, frozen blocks that stop being
re-verified, and localized failure.

Per §3.3, this lands *after* seam assertions exist, not before.

---

## 4. Failure taxonomy for a validation layer

Different failures need different techniques. Most testing effort defaults to
class 2; most real failures here have been 1, 3, and 4.

| # | Failure | Caught by |
|---|---------|-----------|
| 1 | **Missing** — no check exists | fault injection + coverage; corpus mining; standards checklists |
| 2 | **Wrong** — computes the wrong function | differential testing, metamorphic relations, PBT, SMT |
| 3 | **Unwired** — exists, never runs on the real path | execution accounting, call-site assertions |
| 4 | **Vacuous** — runs on empty/stub input, trivially passes | cardinality asserts, anti-vacuous-truth guards |
| 5 | **Wrong threshold** — physics right, number wrong | provenance to primary source, corpus calibration |
| 6 | **Silently skipped** — swallowed exception, skip, flag off | skip accounting, expected-run manifests |

Types, PBT, SSoT, and inductive assertions address class 2 almost exclusively.
A beautifully typed, property-tested check that never runs on real data passes
forever.

---

## 5. Five falsification axes

A validator is a claim about the world. Validate it the way any empirical claim
is validated: try to falsify it from independent directions. **None of these
require already knowing the correct answer** — which is what makes
validator-correctness tractable rather than circular.

| Axis | Question | Mechanism |
|------|----------|-----------|
| **Construction** | Break the design deliberately — does it fire? | fault injection (*sensitivity*) |
| **Contradiction** | Does an independent implementation disagree? | differential vs. `kicad-cli`, vs. physics |
| **Invariance** | Does a transformation that shouldn't change the verdict change it? | metamorphic relations |
| **Vacuity** | Did it run, on real data, over a non-empty set? | execution accounting |
| **Reality** | Silent on known-good boards? Confirmed on the bench? | corpus + hardware |

Independence is what makes the conjunction strong.

### Verifying the injector

The construction axis has a hole that must be closed or it produces *false
confidence*, which is worse than no coverage number at all. If the injector
fails to actually inject — writes a malformed file the parser silently drops,
or mutates a field nothing reads — every check "passes" its sensitivity test
while detecting nothing.

The fault injector is subject to the same vacuity discipline it exists to
enforce (class 4, §4). Each injection asserts:

1. the injected artifact **differs** from the original, structurally
2. an **independent tool** (`kicad-cli`) also observes a difference
3. the injection landed in the field the defect model names

An injector that cannot prove its own mutations took effect is not evidence.

### The oracle is not exempt

The five axes apply to **every artifact used as ground truth, including
external tools we did not write.** `kicad-cli pcb drc`, `lint-imports`,
`vulture`, `ngspice` — each is an oracle, and an oracle is a validator like any
other. Treating a third-party tool as ground truth *because* it is
third-party is the same mistake as trusting our own metric because we wrote it
carefully.

The cheapest axis to apply is **invariance**: run the tool N times on
byte-identical input and compare.

**Measured 2026-07-25.** Five `kicad-cli pcb drc` runs on the same routed
file returned `shorting_items` of **124 / 113 / 119 / 120 / 123** — a spread
of 11, about 9%, on identical input. `unconnected` was stable at 276 and
`clearance` moved by one, so the instability is specific to the pairwise
copper-overlap check. Our own router, tested the same way, was byte-identical
across runs once regenerated `tstamp`/`uuid` fields were stripped.

Two consequences:

- **Characterise the oracle's noise floor before gating on it.** A gate whose
  threshold sits below its oracle's noise floor cannot distinguish signal from
  noise — it is a random number generator wearing a verdict's clothing.
- **A single before/after measurement is not evidence when the oracle is
  noisy.** Report median and range over N ≥ 5 runs. A delta smaller than the
  spread proves nothing.

This failure is the §7 reference failure one layer further out: the project
audited its own checks thoroughly while treating the measuring instrument as
exempt. Every routing claim in this repository rests on an oracle whose
reproducibility had never been tested.

Evidence: `docs/evidence/2026-07-25-shorting-items-diagnosis.md`.

### The reader is not exempt either

§5's oracle rule says an external tool used as ground truth is a validator.
The same applies one step closer in: **the shell pipeline between you and the
number is a validator, and it fails silently.**

Measured on 2026-07-25/26, six instances in two days, all of them the reader
and none of them the measurement:

| What happened | Consequence |
|---|---|
| `cmd \| tail` then `echo $?` | read `tail`'s status; reported a working gate as broken |
| `grep \| head -10` | truncated before the real hits; nearly reported "zero production callers" |
| `\| head` on a long run's output | destroyed a 10-minute route's result entirely |
| grep for a string that was line-wrapped | nearly reported present text as absent |
| inferred "the checks ran" from absent warnings | published, then had to correct — the stage never executed |
| read a date-stamped evidence file from the previous day | reported a stale value as current |
| ran a control experiment in a worktree branched before the fix | declared a *building* crate broken, and ranked it the #1 blocker |

Rules that follow:

- **Capture raw to a file, then query the file.** Do not filter in the same
  pipeline that produces the value.
- **Exit codes never through a pipe.** `cmd > f 2>&1; echo $?`.
- **Prefer structured output** (JSON) over scraping text.
- **`head`/`tail` only when the value's position is known.**
- **When a result surprises you, suspect the reading before the result.**
  This is the load-bearing one — it caught most of the six above. The failures
  were the occasions it was not applied.
- **A measurement carries the commit it was taken at, or it is not a
  measurement.** The seventh instance was not truncation — the pipeline was
  clean and the number was real. It was taken in one of 40+ stale worktrees,
  branched before the fix landed, and then reported as current state. Staleness
  of the *checkout* is as silent as staleness of the *date*, and harder to see:
  nothing in the output says which tree produced it. Record the commit
  alongside every measured claim, and re-measure in the main checkout before
  ranking anything as a blocker.

**Corollary — stale worktrees are a measurement hazard, not just clutter.**
Each abandoned worktree is a checkout of the past that answers questions in the
present tense. Prune them, or the archaeology reads as news.

### A detector that reports is not a detector that stops

`scripts/assert-base.sh` was built to end the stale-base class. It worked
exactly as designed: an agent ran it, got a clean failure — *"202 commits
behind, 3 ahead"* — reported that honestly, attempted a rebase, hit conflicts,
and **then implemented anyway on the stale tree**. Two hours of correct
derivation, unmergeable, and its headline "discovery" was a bug fixed hours
earlier on the branch it could not see.

The detector fired. Nothing consumed the signal.

The instruction said *"confirm exit 0; rebase if not"* — which enumerates two
outcomes and leaves the third, *"rebase fails"*, undefined. Faced with an
undefined case the agent picked the one that let work continue, which is what
anyone does.

- **A gate must define what happens when it fails, including when the
  remedy fails.** "Assert X; fix if not X" is incomplete unless "cannot fix X"
  is also specified. Here the missing clause is: **a stale base is a hard
  stop.**
- **Prefer a gate that blocks over a gate that warns**, wherever the cost of
  proceeding exceeds the cost of stopping. This is the same lesson as the
  soft-launched drift gate and the auto-resynced typecheck allowlist: a signal
  routed to somewhere with no enforcement is decoration.

### A known failure pattern becomes a way to skip measuring

The eighth instance was caused by the seventh. After four stale-base errors in
one day, an agent reported that its tree was missing THM-02, OCP-02 and the
OVP hysteresis fix. **It was confirmed without being checked, because it
matched the pattern.** Measured afterwards, all three were present; the tree
was five commits behind on two unrelated things.

The cost was not the wasted rebase. The agent had concluded from the same
misreading that OVP-01's divider was "already correctly calibrated" — when its
tree held the same fail-open 1.1 kΩ/287 kΩ configuration as main. A wrong
premise about *which tree* produced a wrong conclusion about *the circuit*,
and the confirmation removed the last chance to catch it.

Two rules, and the second is the general one:

- **A claim that a tree lacks something must quote the command and its
  output.** "grep -c returned 0" is checkable. "It does not exist here" is a
  conclusion wearing an observation's clothes, and it cannot be audited.
- **A familiar failure pattern raises the prior, it does not discharge the
  check.** Every taxonomy in this document is a list of things worth measuring
  *more* carefully, never a licence to skip the measurement because the shape
  is recognisable. Recognition is the cheapest possible substitute for
  evidence, which is exactly why it is tempting after a day of finding the
  same bug.

### Physical envelopes are preconditions

§3's rule — assert the input, do not assume it — was written for code and then
applied only to code. It applies identically to hardware, and both design
errors on this project came from the gap:

| Change | Verified | Not verified | Result |
|---|---|---|---|
| OCP-01 burden 6.65 → 4.99 Ω | divider math → 50.1 A trip | the CT's **47 A** sensed rating | trip placed above the transformer's range, where the core saturates and the comparator may never fire |
| OCP-02 shunt in `DC_BUS_RTN` | amplifier gain → 2.40 V | that the node sits at **−170 V** | INA240 is a −4…+80 V part; it would have been destroyed |

In both cases the arithmetic was correct and the physical context invalidated
it. Computing a value is not the same as establishing that the parts survive
where it puts them.

**Before changing any component value, enumerate the operating envelope of
every part in the signal path** — voltage, current, common mode, temperature,
frequency — not just the part being changed. The value is valid only inside all
of them. This is a checklist, and it is mechanizable.

The specific trap: reasoning by analogy from a familiar topology. "Low side is
near ground" is true of a single-rail bus and false of a voltage doubler, where
the midpoint is ground and the low rail is −170 V.

### State the falsifier before implementing

Before writing a fix, write one sentence: **"this fails if X"** — then check X
first.

For the route-level bounding-box prefilter that sentence was *"this fails if
route bounding boxes overlap heavily."* Thirty seconds to check, and it does,
so the implementation was wasted. Three optimisation attempts on
`verify_clearance` went the same way, one of them breaking 52 tests, because
each was evaluated only after being built.

This is the `blind_to` field (§3) applied to proposals rather than to loops.

Corollary: **before optimising, build the benchmark.** Get the measurement loop
under ten seconds before iterating on it. Each `verify_clearance` attempt cost
a ten-minute run to evaluate, which is why three of them fit in the time one
disciplined attempt would have taken.

### Metamorphic relations for this domain

No oracle needed; a violation is proof of a bug.

| Relation | Catches |
|----------|---------|
| Translate board +10 mm → identical results | absolute-coordinate assumptions |
| Rotate 90° / mirror → identical (modulo layer flip) | orientation bugs |
| Reorder components or nets in the file → identical | nondeterminism, order dependence |
| Scale geometry ×2 **and** rules ×2 → same verdict | unit and scale bugs |
| Add a distant unconnected component → no verdict changes | global-state leakage |
| Duplicate board side-by-side → violations exactly 2× | aggregation bugs |
| Tighten any clearance rule → violation count can only rise | monotonicity |
| Add copper → unconnected count can only fall | monotonicity |
| parse → write → parse → identical structure | serialization bugs |

### Anti-vacuous-truth

`all(...)` over an empty set is `True`. This is likely the largest single source
of silent passes in verification code. **Every `all()` in a checker requires a
non-empty assertion in front of it.**

### Units as types

The pipeline spans mm (KiCad files), nm (KiCad internals), µm (DSN), and mils
(some DRC specs). Four unit systems produce bugs that survive review because the
code looks right. A newtype per unit makes the class unrepresentable.

### Risk-weighted rigor

Not every check earns all five axes — uniform rigor across thousands of checks
is itself a tangent. Tier by consequence:

- **safety-critical** (isolation reachability, OCP trip timing) — all five axes,
  plus formal treatment of the predicate where tractable
- **functional** — construction + vacuity + reality
- **cosmetic** — none

---

## 6. Checks

### The Check Contract

```yaml
check: <id>
claim: <what it asserts about the world>
provenance: datasheet:<file>#<page> | iec60335-1:<clause> | corpus | physics | inferred
tier: safety-critical | functional | cosmetic
detects: <machine-readable defect model>
cost_field: <emits scalar + gradient, or verdict-only>
falsified_by: [construction, contradiction, invariance, vacuity, reality]
```

Two fields carry most of the weight:

**`detects`** — the defect model is machine-readable, so the fault-injection
harness *derives* the injection fixture from the check itself. Writing a check
automatically generates its own proof-of-fire. This is what makes check count
scale without coverage degrading. **A check with no proof-of-fire is not
registered.**

**`cost_field`** — see §6.3.

### 6.1 Where checks come from

Check authoring is no longer human-limited, so the binding constraints move to
discovery, trust, runtime, and **signal-to-noise**. Sources that scale without
human effort:

- **Datasheets** (`datasheets/`) — abs-max tables, recommended operating
  conditions, layout guidance. Scales with part count, not engineer-hours, and
  produces rules no general DRC will ever have.
- **Standards text** — IEC 60335-1, CISPR 14-1. Already done by hand once in
  `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md`.
- **Corpus-mined invariants** — properties holding across every known-good board
  in `power_pcb_dataset/corpus/`. True of all of them and false of ours is a
  candidate defect.
- **Our own failure history** — every entry in `docs/solutions/` that describes a
  defect becomes an executable check plus an injected defect. Prose cannot fire.

### 6.2 Signal-to-noise is a first-class design constraint

Unlimited checks self-destruct through alarm fatigue. A 1% false-positive rate
across 10,000 checks is 100 false alarms per run and the team stops reading DRC.

This failure mode is already present: of 747 violations on the committed board,
398 (53%) are silkscreen cosmetics burying **62 `shorting_items`** — real
electrical defects on an HV board.

Therefore: **gate on high-confidence tiers, advise on the rest.** Provenance
tiers (datasheet > standard > corpus-mined > inferred) determine whether a check
blocks or informs.

### 6.3 Checks are the router's objective function

The check corpus and the router are the same artifact seen from two directions.
A general router minimizes wirelength and vias; a domain-specific one should
minimize *our checks* — loop area, current density, thermal peak, creepage
margin.

**Consequence: checks intended as objectives must emit a scalar cost and, where
possible, a gradient — not a boolean.** "FAIL: loop area too large" is useless
to a router. "loop area = 47 mm², target < 20, here is the cost field" is
steerable.

The pattern already exists: `route_pcb()` accepts `thermal_flat`
(an `(N,)` float32 thermal cost field threaded to the A* kernel) and
`thermal_weight`. It generalizes to loop area, current density, and creepage.

#### Threshold subordination

Cost fields are **harder** to validate than booleans, not easier — a boolean
has a clean question ("does it fire on a bad board?"), while a cost field is a
function over the whole design whose gradient must point the right way
everywhere. Making checks into optimization objectives is therefore a step
away from principle 3, and it is only acceptable under this rule:

> **The threshold check is the validated artifact. The cost field is a derived
> heuristic, subordinate to it, and need only be monotone with it.**

Validate `loop_area(board) > 20 mm² → FAIL` rigorously, with all five axes.
The cost field then has one obligation:

```
cost decreases  ⟹  loop_area decreases
```

which is a **metamorphic** property (§5) — testable by perturbation, no oracle
required. The hard-to-validate object stays subordinate to an easy-to-validate
one.

A cost field whose monotonicity with its threshold is untested must not be
wired into the router. Optimizing hard against an unvalidated objective is the
reference failure (§7) with more compute behind it.

---

## 7. The reference failure

Kept because it is the archetype every mechanism above is designed against.

**What happened.** `pcb/temper.kicad_pcb` contained a single `Edge.Cuts`
primitive: a 100 × 150 mm placeholder rectangle at the origin. The 149
footprints spanned x 31.5–145.9, y 30.7–240.4 mm. **113 of 149 footprints
(76%) sat outside the board outline**, including the IGBT (U5), the isolated
gate driver (U6), and most of the power stage.

**Measured A/B, changing only the outline** (2026-07-25, same router commit,
same netlist, same flags):

| | Placeholder outline | Outline enclosing the parts |
|---|---|---|
| completion_rate | **0.0000** | **0.7857** (66/84 attempted) |
| nets routed | 0 | 66 |
| nets failed | 95 — all | 18 |
| segments emitted | 0 | 2,966 |
| unconnected items | 326 | 281 |
| DRC violations (router output) | 625 | 1,289 |

**Why it survived a month.** Every failing net reported
`no legal path found (forced segment disallowed)` — the fail-closed gate
working correctly and stating the problem in plain language. It was read as a
router capacity gap. Approximately four weeks of router work followed,
including a fail-closed generalization, property tests, a nine-reviewer code
review, evidence files, and a strategy section titled "the honesty tangent."

**Why no check caught it.** KiCad's DRC reported **5** `copper_edge_clearance`
violations for a board with 113 parts off it — the rule checks clearance *to*
an edge, not membership *within* an outline. The metric was structurally blind
to the defect. The anti-false-zero CI guard protected a number that could not
see the largest defect in the file.

**The four lessons, mapped to mechanisms:**

| Lesson | Mechanism |
|--------|-----------|
| The defect was upstream of everything that measured it | `input_precondition` (§3) |
| No metric could observe it | `blind_to` (§3), fault injection (§5) |
| The correct error message was reinterpreted | escape-rate tracking (§8) |
| Speed made it worse, not better | principle 2 gates principle 4 (§2) |

The fix was three lines: assert every footprint lies inside `Edge.Cuts`.

---

## 8. Anti-spiral rules

Symptoms this addresses: 143 plans, 125 brainstorms, 98 branches, 594 commits
in 14 days, against a board with zero of 22 gates measured.

1. **Every plan names the STRATEGY gate it advances.** If it cannot, it is
   hygiene, and hygiene draws from a bounded budget.
2. **WIP limit of one track.** Tracks are independently *plannable*, not
   independently *shippable*.
3. **Budget loop count, not only loop time.** Many fast iterations against a
   blind metric is worse than few slow ones against a sound metric.
4. **Track defect escape rate.** For each bug: where introduced, where caught,
   in pipeline stages. The §7 failure escaped four stages and was caught by an
   outside observer. If this number is not trending toward zero, the validation
   layer is not working regardless of how many checks it holds.
5. **Documents supersede; they do not accumulate.** A new document states what
   it replaces.
6. **Checks have a staleness clock**, like `scripts/manifest.yaml`. Ten thousand
   drifting checks are worse than a hundred maintained ones.

---

## 9. Two independent loops

The pipeline loop and the design loop have different metrics and do not touch
until fabrication. Neither blocks the other.

| | **Pipeline loop** | **Design loop** |
|---|---|---|
| Question | Does place-and-route turn a netlist into a clean board? | Is this circuit correct? |
| Metric | completion %, DRC, check coverage | ERC clean, SPICE results, part stress vs. rating, expert review |
| Needs a *correct* schematic? | No — a well-formed netlist exercises the router identically | — |
| Needs routing? | — | No |

They converge only at "order boards."

---

## 10. Progressive constraint tightening

Start loose, tighten in rungs. Each rung is a loop with its own precondition and
exit criterion.

| Rung | Constraints | Exit criterion |
|------|-------------|----------------|
| 1 | Outline enclosing the placement; default clearances; one board | Router completion high enough to trust the infrastructure |
| 2 | HV/LV split; real net classes; creepage rules active | Both boards route; isolation checks pass |
| 3 | Outline tightened toward the teardown envelope | Still routes at real density |
| 4 | True enclosure dimensions, mounting holes, connector positions | Mechanically fits the reference chassis |

---

## 11. Simulation

**Compute is cheap; ground truth is expensive.** Spend compute lavishly, spend
physical iterations miserly, and design each physical iteration to maximize
information gain.

Ranked by return, given the models already in `simulation/models/`:

1. **ZVS margin sweep across the pan-load space.** Losing ZVS destroys the IGBT.
   Sweep pan inductance, coupling, resistance, frequency, and power → assert
   margin at every operating point. Overnight covers thousands of points; a
   bench covers the pans in one kitchen. Models present: `pan_load.sub`,
   `current_transformer.sub`, `IKW40N120H3.lib`.
2. **Protection trip points as transient sims** — OCP-01/02, OVP-01, UVL-01/02.
   OCP-01's **<1 µs** is a propagation-delay budget verifiable before any bench
   trip. Models present: `TLV3201`, `TPS3700`, `REF2025`.
3. **Monte Carlo on tolerances** — does OCP still land in 45–55 A at the corners
   with 1% parts over temperature?
4. **Thermal** — junction temperature under realistic duty; predicts THM-01/02.
   Model present: `IKW40N120H3_thermal.sub`.
5. **EMI pre-compliance, honestly bounded.** Simulation will not predict CISPR
   pass/fail. Loop area and dv/dt spectral content rank designs and catch
   disasters. A cert-lab visit is $5–15k; one avoided respin pays for the work.

### Calibration inversion

Every model carries a machine-readable `calibrated: true|false` tag that
propagates into any verdict depending on it. **Design the bench bring-up
backward from what the models need** — coil L and Q under real pans, IGBT
thermal impedance, comparator propagation delay. First power-on is a designed
calibration experiment, not a smoke test. That is what converts one physical
board into a permanently cheaper simulation layer.

### Firmware

`firmware/test/test_sil_fault_injection.c` proves the state machine against a
plant model we wrote, not against the circuit. Wiring the SPICE/thermal model in
as the plant gives HIL-in-simulation: inject a real overcurrent transient, watch
the real state machine respond, measure latency against OCP-01's 1 µs budget.

---

## 12. Standing rules

- Every loop declares a Loop Contract (§3), including `blind_to`.
- Every check declares a Check Contract (§6), including `detects`.
- A check with no proof-of-fire fixture is not registered.
- Every `all()` in a checker is preceded by a non-empty assertion.
- Every bug found becomes a check **and** an injected defect.
- Existing detectors gate. A detector that prints `IMBALANCED` and fails nothing
  is not a detector.
- Never optimize a loop that has not been validated.
- **Contracts before decomposition** (§3.3). A new seam without an assertion is
  a regression, not progress.
- **Thresholds are validated; cost fields are subordinate** (§6.3). No cost
  field reaches the router without a tested monotonicity relation.
- **The injector proves its own injections landed** (§5). Coverage numbers from
  an unverified injector are false confidence.
- **The oracle is not exempt** (§5). External tools used as ground truth are
  validators too. Characterise the noise floor before gating on a number, and
  never set a threshold below it.
- **The reader is not exempt** (§5). Capture raw to a file, then query it.
  Exit codes never through a pipe. When a result surprises you, suspect the
  reading before the result.
- **Physical envelopes are preconditions** (§5). Before changing a component
  value, enumerate the voltage, current, common-mode, temperature and
  frequency limits of every part in the signal path — not just the one being
  changed. Correct arithmetic in the wrong physical context is still wrong.
- **State the falsifier before implementing** (§5). One sentence — "this fails
  if X" — then check X first. Before optimising, build the benchmark: get the
  measurement loop under ten seconds before iterating on it.
- Smallness is not the goal — §3.2's five properties are. A small loop with no
  oracle is not a validatable loop.
