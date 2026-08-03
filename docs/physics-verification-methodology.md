# Physics Verification Methodology

A documented pattern — **not a framework or abstraction layer** — for verifying
the mathematical structure of a physics-informed EDA feature. Extracted from the
thermal solver battery (U4–U9 on plan 2026-07-09-001) and extended with the
MFEM FEM corroboration (U1–U4 on plan 2026-07-09-002).

The methodology has four components across a **three-target correctness/soundness/validity ladder**:

1. **Four verification layers** (R1) — fuzz / domain-invariant / independent-method
   oracle / property-preservation-under-composition.
2. **BMC + k-induction ladder** (R2) — for properties that hold over all inputs up
   to a bounded size and must be proved for unbounded sizes.
3. **Independent-oracle rule** (R3) — an oracle is independent only if it
   optimizes the **same objective** via a **different method** at the **model**
   level (not just the solver).
4. **Fail-capable rule** (R4) — every invariant or metric must be demonstrated
   to fail on a constructed input that matches a **plausible bug class**
   (sign flip, index/stencil mis-orientation, BC swap), not a strawman.

---

## 1. Four Verification Layers (R1)

Every feature unit gets a test battery organized in four layers. The thermal
solver (`physics-U5`) is the worked example.

| Layer | Purpose | Thermal example |
|-------|---------|-----------------|
| **L1 — Fuzz (no-crash)** | Hypothesis-generated inputs; the code does not raise, segfault, or exit non-locally. | Implicit in all `@pytest.mark.property` tests — `given(stategies…)` drives random boards that exercise every code path. |
| **L2 — Domain invariant** | Mathematical structure — conservation, monotonicity, maximum principle, well-posedness, symmetry — expressed as properties and proven via PBT + BMC. | `tests/physics/test_thermal_fdm_invariants_pbt.py` — energy conservation (R7), source monotonicity (R8), discrete maximum principle (R9), SPD well-posedness (R10), metamorphic symmetry (R12). |
| **L3 — Independent-method oracle** | Compare the production solver against a reference that uses the **same objective** but a **different model and method** (see §3). Agreement across models confirms physics; disagreement surface model assumptions. | `tests/validation/test_thermal_scorer_independence.py` (U3 / R6) — convective-boundary FDM variant vs the production adiabatic-Neumann solver. `tests/router_v6/test_astar_dijkstra_oracle_pbt.py` (U6 / R13) — Dijkstra on the same weighted grid as A*. |
| **L4 — Composition** | Invariants that hold across component boundaries: multiplicative identity (field-off = no-op), mask respect, counter independence, verdict totality. | `tests/placer/cp_sat/test_loop_termination_pbt.py` (U7 / R17 — field-off idempotence, R16 — counter invariant). `tests/fields/test_fieldresult_invariants_pbt.py` (U9 / R20 — fail-closed sum type). `tests/validation/test_verdict_properties_pbt.py` (U8 / R18 — verdict totality). |

### Worked example: thermal solver battery file paths

| Unit | File | Layers |
|------|------|--------|
| U1 (precondition) | `packages/temper-placer/tests/physics/test_thermal_fdm_matrix_class.py` | L2 guard |
| U2 (op-point bounds) | `packages/temper-placer/tests/physics/test_operating_point_monotonicity.py` | L2 |
| U3 (scorer independence) | `packages/temper-placer/tests/validation/test_thermal_scorer_independence.py` | L3 |
| U4 (solver invariants) | `packages/temper-placer/tests/physics/test_thermal_fdm_invariants_pbt.py` | L2 |
| U5 (refinement ladder) | `packages/temper-placer/tests/physics/test_thermal_fdm_refinement.py` | L2 |
| U6 (A* oracle) | `packages/temper-placer/tests/router_v6/test_astar_dijkstra_oracle_pbt.py` | L3 |
| U7 (loop termination) | `packages/temper-placer/tests/placer/cp_sat/test_loop_termination_pbt.py` | L4 |
| U8 (verdict properties) | `packages/temper-placer/tests/validation/test_verdict_properties_pbt.py` | L4 |
| U9 (fail-closed + prereg) | `packages/temper-placer/tests/fields/test_fieldresult_invariants_pbt.py`, `packages/temper-placer/tests/validation/prereg/test_prereg_fuzz_pbt.py` | L4 |

---

## 2. BMC-Exhaustive + k-Induction Ladder (R2)

For properties that must hold over all inputs up to a bounded size (and be proved
for unbounded sizes), use a **BMC-exhaustive → k-induction → PBT** ladder:

1. **BMC-exhaustive** — enumerate all inputs of size N (e.g., all source/target
   pairs on an 8×8 grid, all component permutations of 3 elements) and assert
   the property holds. Concrete bound: 8×8 for A* optimality, 4×4 in the nightly
   A* exhaustive run. This is a *proof* for the bounded case — no sampling,
   no statistical confidence intervals.
2. **k-induction step** — prove that if the property holds for all states of size
   N, it holds for all states of size N+1 (hand-induction over the recursive
   structure). May be formal or informal depending on risk.
3. **PBT middle** — Hypothesis-driven property tests for N above the exhaustive
   bound, to statistically validate the induction step. Marked `@pytest.mark.l3_pbt`.

### Worked example: A* optimality (U6 / R13)

- **BMC**: `tests/router_v6/test_astar_dijkstra_oracle_pbt.py` — `test_l0_bmc_*`
  functions exhaustively compare A* cost vs Dijkstra cost on all source/target
  pairs on grids ≤ 8×8, using the shared neighbor-validity tensor and edge-cost
  function.
- **k-induction**: The cost additivity invariant (`test_l0_cost_additivity`)
  proves path-cost(field) = path-cost(no-field) + Σ field_cost over traversed
  cells — the induction base (single segment) and step (concatenation) are
  hand-documented.
- **PBT**: `test_l3_optimality_pbt` and `test_l3_admissibility_pbt` sample
  larger grids under Hypothesis.

### Worked example: loop termination (U7 / R15)

- **BMC**: `tests/placer/cp_sat/test_loop_termination_pbt.py` — the stateful PBT
  drives ≤ 50 round-outcome transitions via an injected solver stub and asserts
  every sequence halts (either by convergence detection or round-budget
  exhaustion).
- **k-induction (fallback)**: The fixed round-budget
  (`FIELD_CONVERGENCE_ROUND_LIMIT=8`) is a provable termination guarantee — no
  run can exceed the budget. This is the fallback proof; the stateful PBT
  additionally asserts that a "convergence" verdict implies a near-fixed-point.

---

## 3. Independent-Oracle Rule (R3)

An oracle is **independent** iff it satisfies all three conditions:

1. **Same objective** — the oracle optimizes or computes the *same* quantity the
   production code claims to compute (e.g., least-cost path, steady-state
   temperature field).
2. **Independent method** — the algorithm is fundamentally different, not a
   reimplementation of the same approach (e.g., Dijkstra vs A* for pathfinding;
   Gauss-Seidel vs direct solve for a linear system).
3. **Independent model** — the oracle uses a *different physical model* with
   different assumptions, not the same PDE discretized differently.

**Anti-patterns that do NOT count as independent:**

| Claim | Why it's not independent | What happened |
|-------|--------------------------|---------------|
| "Same PDE, different solver" | Solver independence without model independence confirms the linear solve, not the physics. Two implementations of the same 5-point stencil with the same `k_eff` can agree perfectly on a wrong field. | The original `thermal_scorer.py` (Gauss-Seidel) shared physics-U5's stencil and conductivity — solver-independent but model-dependent (R6). |
| "BFS as A* oracle" | BFS minimizes hop count, A* minimizes octile cost. Different objectives — agreement proves nothing; disagreement is expected. | `docs/solutions/best-practices/bfs-oracle-cost-model-mismatch-astar-validation-2026-06-28.md` |
| "Same discretization, finer mesh" | A refinement study confirms convergence rate (L2), not physical correctness (L3). | `tests/physics/test_thermal_fdm_refinement.py` (U5 / R11) is an L2 check, not an L3 oracle. |
| "Green's function for heterogeneous k" | A closed-form Green's function for heterogeneous k reduces to the same `k_eff` approximation — model-dependent. | Rejected as the primary independent model in U3. |

### Worked example: Thermal scorer independence (U3 / R6)

The independent oracle (`tests/validation/test_thermal_scorer_independence.py`)
uses a **convective-boundary FDM variant**: the three non-heatsink edges carry a
convection term `h·(T − T_amb)` that the production solver treats as adiabatic
Neumann. This is a genuinely different boundary-physics treatment — not just
a different linear solve of the same stencil.

Remaining shared assumptions (explicitly documented): effective interface
conductivity, conduction-only in-plane, vias-as-bulk, no 3-D through-plane
gradient. These are stated limitations, not silently trusted.

### Worked example: A* oracle (U6 / R13)

The oracle (`tests/router_v6/test_astar_dijkstra_oracle_pbt.py`) implements
Dijkstra on the **exact same weighted grid** — same edge-cost function, same
neighbor-validity tensor — so only the search algorithm differs. Comparison is
within floating-point epsilon (`|A*_cost − Dijkstra_cost| ≤ ε`), not exact
equality, since Numba and Python have different float semantics.

---

## 4. Fail-Capable Rule (R4)

Every invariant or metric must be demonstrated fail-capable against a
**realistic bug class** — not a value that would never occur in practice.
Valid bug classes include:

- **Sign flip**: a `+` that should be `−` (e.g., boundary flux sign).
- **Index mis-orientation**: x/y swap, row/col-major confusion.
- **BC swap**: adiabatic ↔ Dirichlet, Neumann ↔ convective.
- **Off-by-one**: fencepost error in grid indexing.
- **Double-count**: cost accumulation counted twice.

Strawman failures (e.g., multiply output by 1000, replace with zero) do NOT
count — they exercise a checksum, not a domain-specific guard. Each fail-capable
test must document which bug class it probes and, ideally, show a minimal code
diff that would produce the paired failing input.

### Worked example

| Invariant (file) | Bug class | Fail-capable test |
|------------------|-----------|-------------------|
| R7 energy conservation (`test_thermal_fdm_invariants_pbt.py`) | Boundary-flux sign flip | `test_r7_energy_conservation_fail_capable` — flips the sign on the Dirichlet flux computation; energy balance breaks. |
| R8 source monotonicity (`test_thermal_fdm_invariants_pbt.py`) | Assembly sign error | `test_r8_monotonicity_fail_capable` — inverts one row of the system matrix; the monotonicity property is violated. |
| R9 maximum principle (`test_thermal_fdm_invariants_pbt.py`) | BC swap | `test_r9_maximum_principle_fail_capable` — swaps the Dirichlet edge to adiabatic; interior temperatures dip below ambient. |
| R12 metamorphic symmetry (`test_thermal_fdm_invariants_pbt.py`) | x/y swap | `test_r12_symmetry_fail_capable` — swaps x and y coordinates before assembly; reflected field disagrees. |
| R11 refinement rate (`test_thermal_fdm_refinement.py`) | Wrong-order stencil | `test_r11_refinement_fail_capable` — injects a deliberately 2nd-order error sequence; the 1st-order rate assertion rejects it. |
| R14 cost additivity (`test_astar_dijkstra_oracle_pbt.py`) | Double-count | `test_l0_cost_additivity_fail_capable` — doubles the field-cost accumulation; additivity breaks. |
| R15 termination (`test_loop_termination_pbt.py`) | Infinite-loop injection | Stateful PBT with an injected solver stub that cycles; convergence detection must classify it as non-convergent. |

### Prior art

This rule exists because of the "silent-pass" failures documented in
`docs/solutions/logic-errors/baseline-extractor-four-silent-fail-metrics-2026-07-01.md`:
five metrics recorded `0.0` for every board, yet the regression gate passed
because `margin_abs: 100.0` absorbed `0.0 ± 100` without complaint. A
fail-capable metric would have surfaced the bug.

---

## 5. Three-Target Correctness/Soundness/Validity Ladder

The verification methodology spans three escalating targets, each answering a
different question about the physical model:

| Rung | Target | Instrument | Question Answered | Limitation |
|------|--------|------------|-------------------|------------|
| **Correctness** | The solver converges to the right answer for the given PDE. | **MMS** (manufactured T* -> Q* -> solve -> error norm convergence at expected order). | "Does the code implement the PDE correctly?" | Assumes the PDE is the right model of reality. |
| **Soundness** | The solver's output maintains physical invariants under all bounded inputs. | **Verified-interval bounds** (BMC-exhaustive over property space + k-induction for unbounded). | "Does the solver preserve conservation, monotonicity, and the maximum principle?" | Bounded to the property class; doesn't cover model error outside the invariants. |
| **Validity-proxy** | Two genuinely independent physical models agree on the full-field temperature within a pre-registered tolerance. | **External-FEM corroboration** (MFEM FEM vs 2-D structured FDM — different solver family, mesh type, codebase, and element types). | "Does the model capture the dominant physics of the real board?" | Still proxy evidence — shared assumptions remain (k_eff, vias-as-bulk, geometry fidelity). The power-on hardware measurement is the closing instrument. |

**Relationship:** MMS proves the implementation is correct; soundness bounds prove
it maintains physical invariants; multi-model corroboration provides evidence the
abstractions (2-D, effective-medium k, adiabatic edges) are adequate. Each rung
closes one class of uncertainty; together they provide defence-in-depth. The
power-on hardware measurement remains the deferred closing instrument per the
model-vs-reality scope boundary.

**Fail-closed discipline:** When the external corroboration instrument is absent
(MFEM binary not compiled, solver failure, mesh generation error), the gate returns
`UNMEASURED` — never a silent `CLEAN`. This is the same discipline as the
`NgspiceValidator.check_ngspice()` preflight pattern.

**Spatial disagreement attribution:** When the two models disagree beyond the
pre-registered tolerance, the violation carries a spatial attribution map
(device footprint, near-heatsink edge, far-field, copper-plane region, FR4-only
region) that localises the physics gap to a specific assumption class — not
just a binary "disagree" flag.

**Relevant implementation:**
- MFEMCorroborationGate (`validation/mfem_gate.py`) — fail-closed gate wrapping
  MFEMRunner → build_temper_mesh → compare_fields.
- Compound learning: `docs/solutions/best-practices/external-fem-corroboration-validity-proxy-2026-07-09.md`

---

All battery tests run in CI via the `.github/workflows/python-tests.yml`
`checks` job. The `l3_pbt` marker categorizes heavy PBT tests for PR-only
cadence; lighter L0/L1 exhaustive tests run on every commit.

---

## 6. Constraint Mutation Suite (R32)

A standing, gated suite inverts the fail-capable question: instead of asking
whether a constraint encoding's test suite passes, it asks which R4 bug-class
mutations the encoding's own defenses would catch.

**Scope.** The 8 PCL handlers in
`packages/temper-placer/src/temper_placer/placer/cp_sat/handlers/`. The
router-V6 topology family is registered as deferred in the kill-set register:
its ESL/BMC defense machinery was removed (plan 2026-08-02-005's verified
assumption), and the mutation suite measures existing defenses only — a
mutation with nothing to be killed against is registered, not force-fed a
kill set.

**Operators (KTD1).** Mutations are limited to the R4 fail-capable bug
classes: sign flip, dropped term, loosened bound, off-by-one, double-count.
Strawman mutations (multiply output by 1000, return zero) are rejected as
invalid operators. Mutations are applied at **source level** — an AST
transform rewrites a copy of the handler module, which is then loaded in
place of the real encoder (no runtime monkeypatching) — and must actually
change the encoder's output on a probe input (the model proto must differ),
or they are classified `no-op` rather than counted as survivors.

**Kill detection (KTD2).** Each mutation runs only its encoding's defense
subset — the encoder unit-test mirrors and the post-solve `PlacementAuditor`
— never the whole suite. The defense solvers are pinned
(`num_search_workers=1`, fixed seed) so verdicts are reproducible. A mutation
is *killed* when any defense fails, *survived* when all pass.

**Register + gate (KTD3).** Every encoding's kill set lives in
`power_pcb_dataset/constraint_kill_sets.yaml`; `scripts/constraint_mutation_gate.py`
fails CI on a missing entry, an empty kill set, or an untriaged survivor.

**Triage (KTD4).** A survivor is either *benign* (documented rationale — e.g.
a 1-unit / 0.01 mm off-by-one below any enforceable precision) or *test-gap*
(with a TODO referencing the follow-up that closes it). Untriaged survivors
fail the gate.

**Running the suite.**

```bash
PYTHONPATH=packages/temper-placer/src \
  uv run --no-sync python scripts/constraint_mutation_runner.py
# regenerate the register, preserving curated triage:
PYTHONPATH=packages/temper-placer/src \
  uv run --no-sync python scripts/constraint_mutation_runner.py \
    --write-register power_pcb_dataset/constraint_kill_sets.yaml \
    --triage-from power_pcb_dataset/constraint_kill_sets.yaml
uv run python scripts/constraint_mutation_gate.py   # must exit 0
```

**Baseline findings (2026-08-02).** 32 mutations across 8 handlers: 15
killed, 16 survived (triaged), 1 no-op. Every R4 operator is demonstrated
killed on at least one encoding. Notable survivors, all triaged in the
register:

- `sep_drop_y_ok_clause` (**weak-nooverlap2d class**): dropping the `y_ok`
  definitional clause frees the literal, so the final `x_ok ∨ y_ok`
  disjunction is satisfiable with no y separation — and **neither** the
  encoder test (at-least-one-axis assertion) **nor** the auditor (max-axis
  Chebyshev gap) catches it. The plan's U1 scenario expected an auditor kill;
  empirically it survives. This is the incident class the suite exists to
  surface — closing it (a one-axis separation check) is plan 2026-08-02-016.
- The ADJACENT / ALIGNED / ON_SIDE / LOOP_AREA / KEEPOUT defenses share a
  blind spot: their tests solve without an objective, so the solver parks
  components at the origin and weakening mutations are invisible. Only
  floor-flip / infeasibility mutations are caught by the origin-parked
  solves; the register marks the rest test-gap with plan 2026-08-02-005
  (exhaustive bounds) as the follow-up.

**U4 defense additions.** Two targeted fail-capable tests were added as part
of the triage (not plan-005 exhaustive suites): `test_keepout_mutation_defense.py`
(origin-zone + anchored keepout scenarios) and `test_loop_area_mutation_defense.py`
(anchored-spread loop). These give KEEPOUT and LOOP_AREA their dropped-term /
sign-flip / double-count kills.

---

## Triaged findings (follow-ups)

The batteries surfaced real limitations in the shipped solver, triaged per the AGENTS.md R22 rule
(trivial fixes in-scope; architectural/discretization fixes documented and scoped as follow-ups):

- **Thermal FDM is 1st-order accurate (cell-centre Dirichlet BC)** — found by the U5 refinement
  ladder (p ≈ 0.99, not 2). Accuracy floor, not a soundness violation; scoped as a follow-up.
  See `docs/triaged/2026-07-09-thermal-fdm-first-order-bc.md`.

---

## References

- Plan: `docs/plans/2026-07-09-001-feat-physics-verification-rigor-plan.md`
- Origin requirements: `docs/brainstorms/2026-07-09-physics-verification-rigor-requirements.md`
- Four-layer pattern origin: `docs/solutions/best-practices/hypothesis-invariant-test-suite-pattern-2026-06-28.md`
- BMC/k-induction pattern: `docs/solutions/best-practices/bmc-induction-ladder-constraint-verification-2026-07-01.md`
- Oracle cost-model mismatch: `docs/solutions/best-practices/bfs-oracle-cost-model-mismatch-astar-validation-2026-06-28.md`
- Silent-fail metrics: `docs/solutions/logic-errors/baseline-extractor-four-silent-fail-metrics-2026-07-01.md`
