---
date: "2026-07-08"
topic: physics-informed-placement-routing
status: requirements
tier: deep-feature
relationship: "Foundation under W3 (physics gates), W4 (human-like), W5 (compound loop). Adds the field-solver strategy, the cost-field layer, and the validation discipline all three depend on."
---

# Physics-Informed Placement & Routing: Field Solvers, Cost Fields, and the Validation Discipline

## 1. Thesis

Physics should enter placement and routing in **three distinct roles**, and the value of the whole effort lives less in the solvers than in the **discipline that proves they help**. The recurring failure mode of this project — a green signal that measured a model instead of reality ("121→0", the vacuous 6mm, the centered-box geometry, five map-vs-territory catches) — is exactly the failure mode a physics layer is most prone to, because a field solver produces a rich, physical-looking number that is very easy to trust and very hard to falsify. So this document is as much about *how we validate physics guidance* as about *what physics we compute.

Two meta-principles carried from the prior work anchor everything below:

- **Absolute thresholds over tuned weights.** The wins came from sourcing real limits (IPC-2221, IEC 60335-1) and encoding them as hard constraints, not from tuning soft penalties. Component datasheets are the third source of absolute limits.
- **Measure the territory, not the map.** Every gate must be able to distinguish "measured, clean" from "couldn't measure," and every "does it help" claim must be scored by an instrument independent of the one being optimized against.

## 2. The Three-Role Physics Architecture

Physics enters at three layers with different obligations. Conflating them is how tuning-hell and false confidence creep back in.

| Role | Mechanism | Examples | Obligation |
|------|-----------|----------|------------|
| **Hard constraint** | CP-SAT hard / masked A* cells | creepage, keepout, loop-area ceiling, `T_j ≤ T_j(max)`, `L_loop ≤ L_max` | must not violate; infeasibility → UNSAT core → design change |
| **Soft cost field** | A* cell weights + CP-SAT zone penalties | thermal heatmap, EMI/H-field, coupling risk, current density, congestion | proactive avoidance; must be *proven* to help vs a cheap baseline |
| **Verification gate** | post-hoc field solve vs budget | FastHenry `L_loop`, thermal margin, DRC/ERC | independent measurement of the finished layout; fail-closed |

The **cost-field layer is the one currently missing** — the soft, spatially-varying middle between hard constraints and post-hoc gates. It is how human designers actually work (route away from the hot switch, keep analog off the switching node) and it is the correct operationalization of "looks human-made": measurable field costs, not aesthetic mimicry.

## 3. Field Solvers: the Source Hierarchy

### 3.1 The differentiability red herring
An earlier framing said field solvers "can't be in the loop because they're non-differentiable." That was a JAX-era reflex; the CP-SAT paradigm uses no gradients. The properties that actually gate in-loop use are **encodability** (can it be a constraint/objective over the decision variables?) and **evaluation cost**. A field solve is neither encodable nor cheap, so it lives in the **outer round-loop** (W5) or as a **calibrator**, never inside a CP-SAT solve — and if a custom solver is built, it should **not** be made differentiable (that would only matter if gradient descent returned, which it should not).

### 3.2 Four-tier source hierarchy
For any physical quantity, prefer sources in this order:

1. **Datasheet-characterized curves** — `E_sw(V,I)`, `Z_θJC(t)`, `Q_g`, `C_oss(V)`, `R_θ`. "Measured analytic"; beats both a derived formula and a generic SPICE model because it's the manufacturer's characterization of *that* part.
2. **Analytic closed-form** — resonant-tank operating point, `di/dt` from gate drive, loop inductance (Grover), thermal R-network, IR drop. Fast, transparent, sweepable, in-loop-able. **The default for anything in the search or the sensitivity sweep.**
3. **SPICE** — *not* in the loop. Two jobs only: (a) periodic **independent validator** of the analytic operating point; (b) genuinely-nonlinear behavior analytic can't do (soft-switching edges, dead-time, fault/startup).
4. **Physical measurement** — the eventual territory anchor, deferred with a power-on trigger (§7).

### 3.3 Custom solver vs FastHenry/FastCap
The question is not build-vs-buy; it is **"where is your independent anchor?"** Building a custom solver as the *only* source of physical truth rebuilds the "code agreeing with code" failure mode. So:

- **Build custom for the runtime** — a PCB-specialized loop-inductance / field estimator is far simpler and faster than general 3D PEEC, native to the stack, and testable with the PBT discipline.
- **Keep an externally-validated reference (FastHenry/FastCap) as a one-time anchor**, not a runtime dependency — you inherit *their* measurement validation without fabricating. Validate the custom solver against it (and against closed-form) before trusting it.
- **In-loop guide** = calibrated analytic surrogate (fast, monotone-correct, non-differentiable); **runtime gate** = the custom solver, validated; **independent anchor** = FastHenry + closed-form.

The trap is not "reinventing FastHenry" — it is "having no external truth to check the reinvention against."

## 4. Cost Fields: the Soft Middle Layer

### 4.1 What they are
Scalar/vector fields over the board used as **additive costs** in A* routing (cell weights) and **zone penalties** in CP-SAT placement. This is the canonical **negotiated-congestion routing** paradigm (PathFinder) extended with physics fields. Routing is the natural home (A* already sums cell costs); placement is a coarser fit via discretized zone penalties. Do **not** reach for force-directed/potential-field placement — that reintroduces gradients.

Field family (priority order): **thermal heatmap** (first), EMI/`dB·dt` map, current-density/IR field, capacitive-coupling field.

### 4.2 How placement and routing both feed the field solve
A field is a function of *geometry + sources*, and placement and routing supply different parts — neither alone specifies enough to solve. For the thermal field `∇·(k∇T) = −Q`:

- **Placement sets `Q` locations and boundary conditions** — where Q1/Q2/D/LDO sit (adjacent switches superimpose hot spots), sink proximity (edge placement lowers `T_j`), and which victims (electrolytics, MCU) sit in hot zones.
- **Routing sets the conductivity field `k` and a distributed part of `Q`** — copper is the heat-spreading network (conducts ~1000× better than FR4), so routing *sculpts where heat can flow*; and every trace dissipates `I²R`, so copper is simultaneously conductor and distributed source (wider trace = less `I²R` *and* more spreading); plus thermal vias and plane assignment set the vertical path.

**One-liner:** placement sets *where heat is made*; routing sets *how it flows away* (and adds its own copper heat). Both feed one PDE.

### 4.3 The fixed point and the fidelity gradient
Because both sub-problems feed the field, and the field should inform both, it is a **fixed point**, not a one-pass pipeline: place → field (with *guessed* copper) → route → field (with *real* copper) → re-place/route → iterate. This is the W5 loop carrying a **continuous field** instead of a discrete constraint delta; reuse the existing oscillation detector as the tripwire. **Distinguish halted from converged:** a round budget proves only that the loop *halts* — reporting halted-as-converged is a false claim. *Converged* means the inter-round field delta is below ε and stable; *halted* means the round cap was hit. The loop must report these as distinct outcomes, never conflate them. *(Sharpened by implementation — see `docs/solutions/best-practices/termination-is-not-convergence-2026-07-09.md`.)* Note the **fidelity gradient**: the placement-time field is crude (copper unknown, assume default), the routing-time field is real — the field gets truer as the layout gets more specified.

### 4.4 The fields compete — and datasheets resolve it
The fields pull the *same* decisions in opposite directions. Q1/Q2: the **inductance** field wants them tight (small commutation loop → low `L_loop` → low overvoltage); the **thermal** field wants them spread (no hot-spot superposition). This is not resolved "by feel" — see §5.

## 5. Datasheet-Defined Constraints (Feel → Feasibility)

Most apparent "tradeoffs resolved by feel" are **feasibility problems against absolute limits not yet looked up.** The datasheet turns *both* sides of a physics tension into **hard ceilings**:

- **Thermal (bounds how close):** `T_j ≤ T_j(max)`, via `R_θJC/R_θJA`; the *actual* `T_j` including mutual heating comes from the field solve.
- **Overvoltage (bounds how far):** `L_loop ≤ (V_(BR)·derate − V_bus)/(di/dt)`; `V_(BR)` and `Q_g` from the datasheet, `di/dt` from the operating point.

So it is a **feasibility problem, not a priority problem**: find the placement band satisfying both ceilings. If non-empty, the tradeoff dissolves and the residual freedom goes to genuinely-soft objectives. Four things the datasheet does **not** hand you, and where judgment remains:

1. **Derating is policy, not a datasheet number** — ceiling = `datasheet_limit × your_derating`, set by reliability target + IEC 60335-1 fault conditions.
2. **The datasheet is the ceiling, not the measurement** — system values (superposition `T_j`, routed `L_loop`) come from the field solve; datasheet = threshold, field = actual, gate = compare.
3. **When ceilings conflict (UNSAT), you change the design, not the priority** — bigger heatsink (`R_θ`), snubber / slower gate (`di/dt`), part swap (`V_(BR)`). The UNSAT core names the physical knob.
4. **The soft residual (where in the band) is not on any datasheet** — wirelength, manufacturability, human-like metrics. Only this stays soft; the physics is hard once the sheets are read.

The lexicographic/priority machinery is therefore reserved for the *genuinely soft residual*, never for the physics.

**Dependency:** these ceilings are only as good as the operating point feeding them (`di/dt`, per-device power) — which requires the analytic operating-point solve (§3.2 tier 2, validated by SPICE per tier 3). Garbage operating point → confident-but-wrong ceilings.

**Operating-point cross-check (gates Tier 4):** because every ceiling above rides on this one operating point — whose shakiest component is the coupled induction load (§8) — and all three A/B arms share it, a systematically wrong operating point produces confident-but-wrong ceilings that survive the whole battery. SPICE validation alone is not enough: a SPICE model can share the analytic model's assumptions (transformer coupling, no eddy-current loss in cookware) and agree without being correct. So derive a **closed-form bounding operating point** from physical extremes (ideal coupling vs zero coupling) and confirm the datasheet ceilings stay feasible across that whole range; the coupled-load model is a gate-blocking risk that must clear before the helps-battery runs.

## 6. The Validation Discipline (the actual deliverable)

"Works" and "helps" are each **several distinct claims**; testing one and assuming the rest is how every false result happened.

### 6.1 "Works" — five claims (K-series, to avoid collision with workstreams W0–W5)
- **K1 Solver-correct** — vs closed-form + externally-validated reference on known geometry, checked as an **order-of-accuracy** convergence (a refinement ladder: vary the resolution, assert the observed order matches the stencil), **not** a single-point comparison. A point check passes while the order silently degrades — and it degrades first at the boundary, where the sink BCs dominate the thermal solution (worst possible place). This is "measure margin, not pass/fail" applied to numerics: check the trend/order across resolutions, never one value. *(Sharpened by implementation — a cell-centre Dirichlet BC was silently 1st-order; see `docs/solutions/logic-errors/thermal-fdm-cell-centre-dirichlet-first-order-2026-07-09.md`.)*
- **K2 Geometry-faithful** — the solver sees the *real* copper/power, not an idealization (the bounds⊇pads lesson).
- **K3 Integration-correct** — the A*/CP-SAT cost actually reflects the field (PBT: routing avoids high-cost cells).
- **K4 Deterministic** — same board → same field → same layout.
- **K5 Fail-closed** — on non-convergence / export failure, the system must **not** silently substitute a flat/zero field. `GateResult{CLEAN | VIOLATIONS | UNMEASURED}`; `UNMEASURED` is loud and blocks convergence. (The false-zero lesson, field edition.)

### 6.2 "Helps" — seven claims
- **H1** improves the target margin; **H2** regresses no other gate;
- **H3** beats the *cheap heuristic* baseline (e.g. Euclidean keep-away), not just no-field — *the one everyone skips*;
- **H4** causal & controlled (same seed, same net order, field the only toggle) — not seed-luck (the single-seed `results.md` error);
- **H5** robust across perturbations of the one board (N=1 generalization), not overfit to one config;
- **H6** scored by an **independent instrument**, not the field being optimized against — *the deepest one*. Independence must be at the **model** level, not the solver level. The ladder: same-solver (validates nothing) < different-solver-same-model (validates the numerics only — two solvers of the same heat equation with the same BCs agree and are both wrong if the model is wrong) < different-**model** (catches shared modeling assumptions) < hardware (reality). A "higher-fidelity solver" is not an independent instrument. *(Sharpened by implementation — see `docs/solutions/best-practices/solver-independence-is-not-model-independence-2026-07-09.md`.)*
- **H7** acceptable cost / convergence (round count, oscillation).

### 6.3 Measure margin, not pass/fail
A *wrong* field produces a board that is systematically worse but **still passes every gate** (no single violation). So "helps" can never be a pass-count delta — it must be a **continuous margin** delta (°C of thermal headroom, nH of `L_loop`, dB of coupling, mV of IR drop). The field's job is to improve margin; a binary gate is blind to it.

### 6.4 The ladder, pre-registration, and the kill criterion
```
Tier 0  PRE-REGISTER the pass bar + KILL CRITERION  (written before anything below is built)
Tier 1  K1        solver vs closed-form + reference
Tier 2  K2        exported geometry == real copper
Tier 3  K3,K4,K5  search-uses-field / deterministic / fail-closed
Tier 4  HELPS BATTERY (controlled A/B):
          arms:    no-field | cheap-heuristic | physics-field   (H3)
          control: same seed, same net order, field-only toggle  (H4)
          score:   full margin scorecard, all gates              (H1,H2)
                   scored by the INDEPENDENT instrument           (H6)
          spread:  over N perturbations, distribution not point   (H5)
          cost:    round count / oscillation                      (H7)
```
Tier 0 is the foundation, not the capstone: **write the decision rule before building** ("ships iff it improves validated margin by ≥X, regresses no hard gate, beats the cheap baseline by ≥Y, across ≥N perturbations"). Pre-registration sits at the top of the ladder because it must exist before the solver, the integration, or the battery — matching the prose here and §9 step 1, which builds the pre-registered bar first. Make the **kill criterion first-class** — the validation must be *able* to conclude "the cheap heuristic captures 95% of the benefit; delete the field." The most valuable possible outcome is a killed belief.

## 7. In-Box (Sim-Only) Mode

Simulation-only is the right stage for developing the *methodology*, but it removes the ultimate anchor: there is no territory, only most-trusted model, and the primary risk becomes **correlated error / mutual confirmation** (two models sharing a wrong assumption agree, and both are wrong). Mitigations make "in-box" a first-class, honestly-bounded mode:

1. **Borrow external territory** — use reference solvers whose authors validated them against measurement (FastHenry; an established thermal FEM). Maximize method-diversity between the in-loop field and the scorer; the more they share, the less agreement proves.
2. **Sensitivity sweep as the measurement substitute** — the unmeasurable BCs (convection coefficient, ambient, contact resistance, material props, **and the nonlinear coupled induction load**) are swept across plausible ranges; the "helps" verdict and the safety margin must hold across the *whole* range. Pre-register the ranges. This converts "can't measure it" into "proved the conclusion is robust to not knowing it." **Caveat — endpoints bound the truth only if the response is monotone in the parameter.** A resonance or interior optimum puts the worst case *inside* the range, and sweeping only the extremes returns a falsely-reassuring "robust." Either prove monotonicity (then endpoints suffice) or sample the interior densely enough to catch an interior worst case; the same trap contaminates H5. *(Sharpened by implementation — see `docs/solutions/logic-errors/endpoint-bounding-unsound-without-monotonicity-2026-07-09.md`.)*
3. **Shrink the claim** — in-box sign-off is "safe *under the modeled assumptions, robust across their uncertainty*," never "safe." State the scope.
4. **Power-on trigger** — physical measurement is *deferred, not cancelled*. Trigger: **before the first powered bring-up of a physical board.** This is a mains board; no simulation is an acceptable sign-off to energize real copper.

## 8. First Concrete Target: the Thermal Chain

`operating point (analytic, SPICE-validated) → per-device losses (datasheet models) → temperature field (FEM/FDM — not SPICE) → validated against independent scorer (3D FEM in-box; IR/thermocouple at power-on)`. Thermal is first because it's cheap, gridded (native to A* and zone-penalties), encodes real designer behavior, is the separate-from-FastHenry solver, and serves safety + physics + human-like at once. The **coupled induction load** is the shakiest analytic assumption and must be a first-class sweep axis, not a trusted constant.

## 9. Sequencing & Scope Discipline

The failure mode to avoid is building the multiphysics pipeline before proving any of it helps ("build the instrument, defer the measurement," now broken four times). Order:

1. **Build the helps-battery harness first** (controlled A/B, baseline ladder, margin scorecard, independent scorer, perturbation spread, pre-registered bar). It is identical in shape for every field and every gate, so it is the reusable core — *and it is the thing that stops a sixth map-vs-territory failure.*
2. **Build the thermal field only**, wire into A* cost + CP-SAT zone penalties, run the fixed-point in W5.
3. **A/B it** — physics-field vs cheap-heuristic vs no-field, scored by the independent instrument, over perturbations, against the pre-registered bar.
4. **Generalize only if it earns it.** If the cheap heuristic wins, that is a successful result: record it and move on.

## 10. Open Questions / Decisions

- **The independent instrument for each field** must be *named*. Thermal: 3D FEM in-box, IR at power-on. Inductance: FastHenry + closed-form. Without a named instrument, H6 has no teeth.
- **Cheap-baseline definitions** — the heuristic each field must beat (thermal: Euclidean keep-away from sources; EMI: distance-from-loop). Pre-register per field.
- **Sensitivity ranges** for the unmeasurables (convection, ambient, load L/R vs pot temperature) — pre-register before the battery runs.
- **Field-combination policy** — combining thermal + EMI + congestion costs is the weighted-sum-of-soft-objectives trap, spatial edition. Prefer **lexicographic net ordering** (route critical/EMI-sensitive nets first through a clean field) over a blended weighted cost; keep hard things as masked cells, not large weights.

## 11. Relationship to Existing Workstreams

- **W3 (physics gates)** — this doc is its foundation; the field solvers and the datasheet-ceiling framing are the substance of W3, and the `GateResult` fail-closed contract is shared.
- **W4 (human-like)** — the cost-field layer *is* the correct operationalization of "human-like": measured field-avoidance, A/B-proven, not aesthetic mimicry.
- **W5 (compound loop)** — carries the fields as continuous state alongside discrete constraint deltas; reuses oscillation detection; the helps-battery is a sibling harness to the golden-board gate.
- **Gate-contract spec** — the `GateResult{CLEAN|VIOLATIONS|UNMEASURED}` from the earlier review is the shared contract every field gate and DRC/ERC gate conforms to.

## Deferred / Open Questions

### From 2026-07-08 review

- **H6 "independent instrument" is structurally unachievable in sim-only mode** — §6.2/§7 (P1, adversarial, confidence 75)

  The whole validation discipline rests on H6 (a scorer independent of the optimized field). In sim-only mode both the in-loop solver and the scorer share the same PDEs/BCs, so "borrow external territory" relocates rather than removes the correlated-error risk the doc itself warns about — the battery can pass while both models share a structural error, surfacing only at power-on. Candidate resolution: require the scorer to use a different numerical method + mesher than the in-loop solver, document FastHenry/FastCap's validated geometry envelope vs this board's feature set, and add a closed-form limiting-case anchor.

  <!-- dedup-key: section="6267" title="h6 independent instrument is structurally unachievable in simonly mode" evidence="the entire validation discipline the helpsbattery ab testing kill criterion depends on h6 a scorer independent of the field" -->

- **Sensitivity sweep is blind to structural model error** — §7/§8 (P2, adversarial, confidence 75)

  The sweep-as-measurement-substitute only perturbs parameters within a fixed model form; it cannot catch a neglected heat path (e.g., through mounting hardware to chassis), a 2D-where-3D-matters simplification, or a wrong coupling mechanism — the worst-case failure for physics simulation. Treating the coupled induction load as "a first-class sweep axis" assumes its model form is right and only its parameters are uncertain. Candidate resolution: enumerate the top ~3 modeling simplifications, construct the bounding case for each, and require the helps verdict to hold across those cases in addition to the parametric sweep.

  <!-- dedup-key: section="78" title="sensitivity sweep is blind to structural model errors" evidence="the document proposes sensitivity sweeps as the primary simonly mitigation for unmeasurable boundary conditions" -->

- **W5 loop has no path to carry a continuous field** — §4.3/§11 (P2, feasibility, confidence 75)

  The doc claims the existing W5 loop can "carry the fields as continuous state" and "reuse the oscillation detector," but `PlaceRouteLoop` converges only by injecting discrete `ConstraintDelta` objects and checking gates-CLEAN, and the oscillation detector checks ±0.1mm position equality — blind to slow field drift. Wiring the thermal field in (§9.2) hits a constraint-delta-only injection path with no field interface; this needs an explicit architectural decision (parallel feedback path or W5 redesign) the requirements doc currently delegates to the implementer without acknowledging.

  <!-- dedup-key: section="43411" title="w5 loop cannot carry continuous fields as claimed" evidence="the requirements doc claims the existing w5 compound loop can carry continuous fields alongside discrete constraint deltas" -->

