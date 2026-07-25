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

### Seam contracts

The postcondition of stage N must equal the precondition of stage N+1, and the
equality is asserted. Fixing an individual bad input fixes an instance;
contracts at every seam eliminate the class.

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
steerable. Pass/fail thresholds layer on top of the cost field, not instead of
it.

The pattern already exists: `route_pcb()` accepts `thermal_flat`
(an `(N,)` float32 thermal cost field threaded to the A* kernel) and
`thermal_weight`. It generalizes to loop area, current density, and creepage.

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
