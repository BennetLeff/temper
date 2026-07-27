---
type: feat
origin: docs/brainstorms/2026-07-05-acceptance-gate-real-drc-and-unsat-ux-requirements.md
status: abandoned
swept: 2026-07-25
swept_basis: "only 0/9 named paths exist"
---
# feat: Acceptance Gate — Two-Tier DRC + UNSAT as Product Feature + Oracle Hygiene

## Summary

Land the placement pipeline's two-tier acceptance gate: fast inner gate (CP-SAT audit + physics oracle) for iteration, truth gate (`validation/drc_runner.py` against real 6mm KiCad DRC rules) for acceptance. Promote UNSAT from debug log to first-class product output — Rich-formatted panel to stderr and optional `--unsat-report` JSON. Execute oracle-worktree hierarchy decisions: land `physics-derived-oracle` as inner-gate oracle, demote `human-reference-corpus-oracle` to regression-floor, `viz-server` out of scope. Decisive result: temper board passes KiCad DRC at 6mm with zero violations; an over-constrained PCL produces a surfaced UNSAT report naming the conflicting constraints with their physics rationale.

**Scale:** New `AcceptanceGate` class + UNSAT surfacing layer (~200 lines), Rich panel formatting (~100 lines), JSON report schema. Oracle worktree decisions are documentation changes, not code changes — the code already exists in worktree branches.

---

## Problem Frame

Two failures this workstream prevents:

1. **Inner-gate misclassifies a real violation as satisfied.** The CP-SAT audit verifies encoder invariants (Chebyshev clearance at 8.5mm), but the physical DRC rule is Euclidean 6mm. Chebyshev over-approximation (8.5mm × sin(45°) ≈ 6.0mm) can pass audit but fail DRC. If only the audit passes for acceptance, a placement can ship with a 6mm Euclidean DRC violation that Chebyshev passes.

2. **UNSAT remains a developer-side debug log, not a domain-expert output.** The existing `UnsatReport` (to be built in the constraint-completion workstream) outputs to structured data classes; surfacing to a panel, formatted report, or JSON file is this workstream's UX contribution. CP-SAT's unique value — telling the domain expert *which constraints conflict* — is unrealized if the report stays in `pprint`.

The oracle-worktree hierarchy decisions (F5 of the umbrella) are documented here per the umbrella's R6 enumeration: the physics oracle becomes the fast inner gate; the human-reference-corpus oracle is demoted to regression-floor; the viz-server worktree remains out of scope.

---

## Implementation Units

### U1. Build the UNSAT Core Extraction Pipeline

**Goal:** Implement `unsat.extract_unsat_core` — the OR-Tools proto-index → human-readable constraint names pipeline. This must exist before U4 can surface it.

**Requirements:** R3 (UNSAT report data source), R4 (because from PCL spec)

**Dependencies:** F2 constraint-completion workstream (encoder creates assumption Booleans with constraint-name mapping)

**Files:**
- Create: `src/temper_placer/placer/cp_sat/unsat.py` — `UnsatReport`, `extract_unsat_core`, `refine_mus`, `_build_proto_index_map`
- Create: `tests/placer/cp_sat/test_unsat.py` — extraction pipeline tests

**Approach:**

```python
@dataclass
class UnsatConstraint:
    name: str          # e.g., "loop_area 'commutation'"
    constraint_type: ConstraintType
    because: str | None  # from PCL spec; None if unannotated
    assumption_literal: int

@dataclass
class UnsatReport:
    sufficient_core: list[UnsatConstraint]   # all conflicting assumptions
    minimal_core: list[UnsatConstraint]      # MUS-refined subset
    is_minimal: bool                          # True if MUS converged

def extract_unsat_core(
    solver: CpSolver,
    model: CpModel,
    assumption_vars: list[IntVar],
    constraint_map: dict[int, UnsatConstraint],
) -> UnsatReport:
```

Implementation:
1. After solver returns INFEASIBLE, call `solver.SufficientAssumptionsForInfeasibility()` → proto-index list
2. Translate proto-indices to constraint names via `_build_proto_index_map` (maps assumption literal index → constraint name)
3. Refine to MUS (Minimal Unsatisfiable Subset) by iteratively removing assumptions and re-solving — the smallest subset that's still INFEASIBLE
4. Extract `because` text from the constraint map (populated from PCL spec during encoding)
5. If `because` is None or empty, annotate the constraint as "unannotated — rationale not available from PCL spec"

**Patterns to follow:** The OR-Tools `SufficientAssumptionsForInfeasibility` API; existing encoder assumption Boolean pattern from constraint-completion workstream.

**Test scenarios:**
- Artificially over-constrained model (conflicting Separated + Anchored) → solver INFEASIBLE → `extract_unsat_core` returns `UnsatReport` with at least sufficient_core populated
- `sufficient_core` lists the two conflicting constraints
- `minimal_core` is a subset of `sufficient_core` (or same if already minimal)
- Constraint with `because` text → `UnsatConstraint.because` carries the text
- Constraint without `because` → `UnsatConstraint.because` is None; report notes PCL data-quality gap
- MUS refinement converges within 5 iterations on a 2-constraint conflict

**Verification:** `extract_unsat_core` produces valid `UnsatReport`; MUS refinement works on temper-board-scale model.

---

### U2. Build the UNSAT Surfacing Layer (Rich Panel + JSON)

**Goal:** Format `UnsatReport` into human-readable Rich panel output (stderr) and optional structured JSON file (`--unsat-report <path>`).

**Requirements:** R3 (Rich panel + JSON), R4 (because from PCL spec, never fabricated, missing surfaced)

**Dependencies:** U1 (UnsatReport data available)

**Files:**
- Create: `src/temper_placer/placer/cp_sat/unsat_surface.py` — `format_unsat_panel(UnsatReport) -> str`, `write_unsat_json(UnsatReport, path)`
- Create: `tests/placer/cp_sat/test_unsat_surface.py` — output format tests

**Approach:**

**Rich panel (stderr):**
```
Infeasibility detected. Minimum conflicting constraints (2 of 12):

  • loop_area 'commutation' (because: IGBT overvoltage destruction above 635 mm²
    at 1 A/ns di/dt and 80%-derated V_CE=960 V — exceeds derated rating)
    conflicts with:
    - enclosure 'HV_ZONE' (because: HV segregation for touch safety)
    - separated 'Q1_HV_LV' (because: Reinforced isolation per IEC 60335-1)

  The HV zone is too small to hold all HV parts at required clearance.
  Consider: increasing HV_ZONE dimensions, reducing HV component count,
  or relaxing non-physics-grounded clearance constraints.

  • separated 'Q1_Q2' (because field is unannotated; rationale not available
    from PCL spec — PCL data-quality gap)
    conflicts with:
    - loop_area 'commutation'
  
  Tip: Review which constraints are physics-grounded vs. routing-preference.
  Physics-grounded constraints (IGBT overvoltage, thermal anchoring) cannot
  be automatically relaxed.
```

**JSON output (`--unsat-report out.json`):**
```json
{
  "report_type": "unsat",
  "solver": "cp-sat",
  "minimal_core": [
    {
      "constraint_name": "loop_area 'commutation'",
      "constraint_type": "loop_area",
      "because": "IGBT overvoltage destruction above 635 mm² at 1 A/ns di/dt and 80%-derated V_CE=960 V — exceeds derated rating",
      "conflicts_with": ["enclosure 'HV_ZONE'", "separated 'Q1_HV_LV'"]
    }
  ],
  "sufficient_core": [...],
  "is_minimal": true,
  "data_quality_gaps": [
    {"constraint_name": "separated 'Q1_Q2'", "gap": "because field unannotated"}
  ]
}
```

**Key constraints per origin doc:**
- `because` text comes from the PCL spec's `because` field — never fabricated
- Missing or vague `because` text is surfaced as a PCL data-quality finding (e.g., "constraint unannotated, rationale unknowable from the spec")
- The L_loop-derivation-recommended update to `commutation.yaml`'s `because` field (from "EMI" to "IGBT overvoltage destruction") is consumed here — the UNSAT report cites the overvoltage rationale

**Test scenarios:**
- `UnsatReport` with 2 conflicting constraints → Rich panel output contains both constraint names and their `because` text
- `UnsatReport` → `write_unsat_json(path)` produces valid JSON matching the schema
- Missing `because` → panel output includes "because field is unannotated" annotation
- Covers AE2. Over-constrained loop (10mm²) → UNSAT panel names loop_area + because: "IGBT overvoltage destruction."
- Covers AE3. Missing because → surfaced as PCL data-quality gap.

**Verification:** Rich panel output is readable and domain-expert-friendly; JSON schema is machine-parseable.

---

### U3. Build the Two-Tier Acceptance Gate

**Goal:** Create `AcceptanceGate` with inner (audit + physics oracle) and truth (KiCad DRC) stages. The inner gate runs every solve; the truth gate runs only on accepted placements.

**Requirements:** R1 (two-tier gate, explicit in code and docs), R2 (DrcResult.errors == 0 at 6mm), R6(a) (temper KiCad DRC zero)

**Dependencies:** F2 constraint-completion (audit checks from U6 of that plan, DRC runner exists), U1 (UNSAT extraction)

**Files:**
- Create: `src/temper_placer/placer/cp_sat/gate.py` — `AcceptanceGate`, `GateResult`
- Create: `tests/placer/cp_sat/test_gate.py` — gate behavior tests

**Approach:**

```python
@dataclass
class GateResult:
    inner_passed: bool
    truth_passed: bool | None = None  # None if truth gate not run
    audit_violations: list[AuditViolation] = field(default_factory=list)
    drc_errors: list[DrcError] = field(default_factory=list)
    drc_warnings: list[DrcWarning] = field(default_factory=list)

class AcceptanceGate:
    def inner_gate(self, placement: PlacementResult, constraints: ConstraintCollection) -> GateResult:
        """Runs audit checks + physics oracle. Fast; per-solve. Returns pass/fail."""
    
    def truth_gate(self, pcb_path: Path) -> GateResult:
        """Runs KiCad DRC. Slow; per-acceptance. Accepted iff len(errors) == 0."""
    
    def accept(self, placement, constraints, pcb_path) -> GateResult:
        """Full acceptance: inner → truth. Returns GateResult with both stages."""
```

**Inner gate (fast, every solve):**
1. Run all audit checks (6 types from constraint-completion U6)
2. Run physics oracle: thermal scores, clearance_3mm/6mm, dual-rail
3. Decision: pass (continue iterating), fail (surface with metric breakdown), or escalate (pass at threshold where real-DRC likelihood is high — e.g., all audit checks green AND clearance_6mm ≥ 0.85)

**Truth gate (slow, per-acceptance):**
1. Write placement to `.kicad_pcb` (via `kicad_writer`)
2. Run `drc_runner.run_drc(pcb_path)` at 6mm design rules
3. Accepted iff `len(drc_result.errors) == 0`
4. Warnings are surfaced but do not block

**Two-tier distinction is explicit:**
- `inner_passed=true, truth_passed=false` → NOT acceptance (AE5 scenario)
- `inner_passed=false, truth_passed=true` → NOT acceptance (shouldn't happen, but audit catches what DRC doesn't)
- `inner_passed=true, truth_passed=true` → acceptance
- Audit-vs-DRC disagreement (AE5) is the truth gate's whole signal — when they disagree, DRC wins

**Test scenarios:**
- Valid placement with clean audit + clean DRC → both gates pass
- Placement with audit violation → inner gate fails, truth gate not run
- Placement with audit pass but DRC fail (5.8mm clearance with 6.0mm rule) → inner_passed=true, truth_passed=false, NOT accepted
- Covers AE1. Routed temper → DrcResult.errors empty → accepted.
- Covers AE5. Audit pass + DRC fail → surfaced as signal that blocks acceptance.

**Verification:** `temper optimize` on temper → inner gate passes → truth gate runs → `DrcResult.errors == 0`.

---

### U4. Wire UNSAT Panel into the CLI Pipeline

**Goal:** When CP-SAT returns INFEASIBLE (either initial placement or feedback-injection round in the place→route loop), surface the UNSAT report as Rich panel output to stderr and write JSON if `--unsat-report` is specified.

**Requirements:** R3 (panel + JSON), R6(b) (over-constrained PCL → UNSAT report with because)

**Dependencies:** U2 (surfacing layer), U3 (acceptance gate)

**Files:**
- Modify: `src/temper_placer/cli/__init__.py` — add `--unsat-report` flag to `optimize` command; wire UNSAT surfacing into the optimize flow
- Modify: `src/temper_placer/placer/cp_sat/encoder.py` — integrate UNSAT surfacing into the solve path

**Approach:**
- Add `@click.option("--unsat-report", type=click.Path(), default=None)` to the `optimize` command
- In the solve path: if solver returns INFEASIBLE, call `extract_unsat_core` → `format_unsat_panel` → print to stderr
- If `--unsat-report <path>` is specified, write JSON to the path
- The UNSAT panel output replaces the current behavior (silent INFEASIBLE or `pprint(UnsatReport)`)

**Test scenarios:**
- Over-constrained PCL (loop_area max_area_mm2=10) → CP-SAT INFEASIBLE → stderr shows Rich UNSAT panel
- `--unsat-report out.json` → JSON file written with minimal core and because fields
- Covers AE2 (full): over-constrained loop → UNSAT panel names loop_area + because: "IGBT overvoltage destruction" AND JSON file contains same core
- `--unsat-report` without UNSAT → no file written (or writes empty report)

**Verification:** `temper optimize --config overconstrained.yaml` → UNSAT panel on stderr; `temper optimize --config overconstrained.yaml --unsat-report out.json` → JSON file produced.

---

### U5. Execute Oracle-Worktree Hierarchy Decisions

**Goal:** Land `physics-derived-oracle` as the acceptance inner-gate oracle, demote `human-reference-corpus-oracle` to regression-floor status, document both decisions. `viz-server` remains out of scope.

**Requirements:** R5 (oracle-worktree decisions per umbrella R6)

**Dependencies:** None — these are documentation and git-branch decisions, not code changes. Can run independently.

**Files:**
- Documentation: update README in `physics-derived-oracle` worktree (if it lands as a module) or in `docs/solutions/` — state "acceptance inner-gate oracle"
- Documentation: update README in `human-reference-corpus-oracle` worktree or `docs/solutions/` — state "regression-floor corpus liveness — 49 boards, no-crash / geometric-no-regress; not acceptance"
- No code changes — the oracle code exists in worktree branches

**Approach:**

1. **`physics-derived-oracle` → LAND as inner-gate oracle:**
   - Merge the worktree branch into main
   - Integrate its oracle entry point into `AcceptanceGate.inner_gate()` (U3 consumes it)
   - Document: "Acceptance inner-gate oracle — provides thermal, dual-rail clearance, and non-DRC physics scores per-solve"

2. **`human-reference-corpus-oracle` → LAND demoted to regression-floor:**
   - Merge the worktree branch into main
   - Document in its README and in `docs/solutions/`: "Regression-floor corpus liveness: runs across 49-board corpus, checks no-crash and no-geometric-regression. NOT invoked by the acceptance path."
   - The acceptance path never imports from this oracle — it's a separate CI regression gate

3. **`viz-server` → out of scope:**
   - Document as out of scope in the umbrella and this plan
   - Whatever disposition is decided for it belongs in a future workstream

4. **Five placement-init-* worktrees → handled by F1 (JAX retirement) workstream — NOT here.**

**Test scenarios:**
- `physics-derived-oracle` README states "acceptance inner-gate oracle"
- `human-reference-corpus-oracle` README states "regression-floor corpus liveness"
- Covers AE4. Oracle-worktree READMEs reflect correct roles; acceptance path imports from physics oracle, never from corpus oracle.
- `temper optimize` on temper board → physics oracle scores appear in inner-gate output

**Verification:** Oracle hierarchy reflects the post-paradigm-swap shape: one acceptance oracle, one regression oracle. No parallel-branch mental model residue.

---

## Key Technical Decisions

1. **Two-tier gate: audit + physics-oracle as inner; KiCad DRC as truth.** The audit verifies encoder invariants; the physics oracle produces non-DRC physics scores; DRC verifies physical-rule satisfaction. When audit and DRC disagree, DRC wins — the disagreement is the signal the truth gate exists to produce (Chebyshev-vs-Euclidean safety-factor gaps, encoder bugs, spec-vs-reality drift). (see origin: Key Decisions)

2. **Errors block, warnings don't.** `DrcResult.errors` are design-rule failures that prevent fabrication; `DrcResult.warnings` are non-blocking manufacturability suggestions. The bar is on the former; the latter is surfaced for human review. (see origin: Key Decisions)

3. **UNSAT surfacing as panel+JSON, not as `pprint(UnsatReport)`.** The `UnsatReport` dataclass carries `sufficient_core` + `minimal_core` + `is_minimal`. The surfacing layer translates that into human-readable panel and machine-readable JSON — the extraction logic is already built (constraint-completion U7 of the F2 plan). (see origin: Key Decisions)

4. **`because` from PCL spec, never fabricated.** The report does not invent rationales. If a constraint's `because` field is missing, the report surfaces that as a PCL data-quality finding — the candor surface for spec quality. The L_loop derivation's `commutation.yaml` `because` update (EMI → IGBT overvoltage) is consumed here; the gap between current spec and correct physics is surfaced. (see origin: Key Decisions)

5. **`human-reference-corpus-oracle` demoted, not deleted.** It was correct at its purpose (corpus liveness regression, 49-board no-crash / geometric-no-regress); it was wrong at its aspirational purpose (acceptance gate). Demotion + documented scope statement lands it fit-for-purpose. (see origin: Key Decisions)

---

## Scope Boundaries

### Deferred for Later

- PCL `because`-field audit across all spec entries — fixing missing/inaccurate `because` text is deferred; this workstream surfaces the gaps in UNSAT reports
- Rich-panel layout refinement (per-constraint vs. grouped-core-block) — implementer's discretion

### Deferred to Follow-Up Work

- UNSAT UI beyond panel+JSON (future IDE/PR-comment-bot integration)
- `kicad-cli` CI availability — if `kicad-cli` is unavailable in CI, truth gate must fall back to oracle-proxy DRC for CI and reserve real DRC for local/run-acceptance
- `viz-server` disposition — separate workstream (not here)

### Outside This Product's Identity

- Routing completion bar — owned by F3 (Place→Route Loop) workstream
- Continuous-angle rotation, soft-routed loop-area — per constraint-completion doc
- Corpus-oracle producing confidence-coded acceptance verdicts — demoted, not re-tooled
- Truth-gate performance optimization — `kicad-cli` runs as fast as it runs

---

## Dependencies / Prerequisites

- **F2 constraint-completion workstream complete** — `commutation.yaml`'s `because` field updated to cite IGBT overvoltage (consumed by UNSAT report); audit checks (6 types) functional; CP-SAT encoder creates assumption Booleans with constraint-name mapping
- **F3 place→route loop workstream complete** — truth-gate accepts a routed PCB; placement-only DRC is structurally inadequate
- `validation/drc_runner.run_drc()` functional — verified at `drc_runner.py:162` + `_parse_drc_json:104`
- `kicad-cli` available in execution environment — deferred to planning (if unavailable in CI, fall back to oracle-proxy DRC)
- Five placement-init worktree closures completed by F1 (JAX retirement) workstream — NOT here

---

## Risks

| Risk | Mitigation |
|------|-----------|
| `unsat.extract_unsat_core` does not exist yet — must be built from scratch | U1 builds it; the origin doc's claim that it "already exists" was incorrect per doc-review finding |
| Chebyshev-vs-Euclidean safety-factor gap causes audit-pass/DRC-fail | AE5 explicitly tests this; the gap is surfaced as signal, not hidden. Encoder clearance values may need Euclidean correction |
| `kicad-cli` not available in CI → truth gate can't run in CI | U3: fall back to oracle-proxy DRC for CI runs; reserve real DRC for local/run-acceptance. Docs must surface the proxy-vs-truth distinction |
| `commutation.yaml` `because` field still says "EMI" instead of "IGBT overvoltage" | U2 relies on the PCL spec; if the constraint-completion workstream's Deferred-to-Planning question about the `because` update is not resolved, the UNSAT report surfaces the outdated EMI text — accurate to spec, but spec is wrong. The report's candor surface (missing/incorrect because) handles this |
| UNSAT panel too verbose for the expected failure frequency | If UNSAT is rare (only on deliberately over-constrained PCLs), Rich panel may be over-engineered. Structured text output may suffice; Rich panel is the v1 but doesn't block |

---

## Test Strategy

- **Unit tests:** UNSAT extraction pipeline (U1), surfacing formatter (U2), acceptance gate (U3) each have targeted unit tests.
- **Integration tests:** U4 tests the full CLI path — `temper optimize --unsat-report` on over-constrained config produces panel + JSON.
- **End-to-end test:** U3 + U4: `temper optimize` on temper board → inner gate passes → truth gate runs → DRC zero.
- **A/B divergence test:** AE5 — audit pass + DRC fail case is explicitly tested to verify the truth gate blocks acceptance.
