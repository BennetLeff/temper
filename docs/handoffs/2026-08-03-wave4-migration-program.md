# Wave-4 Python→Rust Migration — Session Handoff

**Date:** 2026-08-03
**Trunk:** `origin/main`
**Open PRs:** none from this session (all landed)
**Tracked issue:** #575 (open)
**Scope:** Wave-4 full-migration program execution — Phase 0/1 complete, Phase A 5 kernels landed, Phase 2 5 contracts landed + residuals decided, Phase 3 plan ready to pull

**Status:** PROGRAM ON TRACK. The discipline contract, pipeline, Phase-1 ortools verdict, five Phase-A compute kernels, five Phase-2 contract pyclass modules, the type-stub infrastructure, and the Phase-3 plan are all merged. The remaining main-state CI debt is one tracked issue (#575) owned by the board workstream. Phase 3 (formats/IO) is planned and ready for its first pull.

---

## What landed this session (53 commits to main)

### Program infrastructure
- **#553** Wave-4 full-migration program plan (discipline contract as the durable artifact; phases A-F)
- **#554** Migration pipeline doc (`docs/migration-pipeline.md` — brainstorm → doc-review → work → code-review → verify → land, with `ce-doc-review` as a subagent step)
- **#555** Phase 0 discipline contract (`docs/wave4-discipline-contract.md` — G1-G8 gate checklist, B1-B10 bit-exactness catalog, R3 residual procedure)

### Phase 1 — ortools boundary
- **#556** Spike verdict: **KEEP** ortools CP-SAT + Python boundary, version-locked contract (`==9.15.6755`, frozen params), KTD9-style parity (tolerance 0 for deterministic completion), R24 audit across the boundary. WRAP recorded as the re-decidable path; REPLACE rejected (R1a unassertable cross-engine). Evidence: `docs/evidence/2026-08-01-ortools-cpsat-spike.md`. 13 constraint classes + 10 model types enumerated with file:line evidence.

### Phase A — compute kernels (5 landed)
| Kernel | Home crate | PR |
|---|---|---|
| `metrics/routing_quality.py` | temper-quality-oracle | #558 |
| `physics/device_power.py` | temper-thermal | #577 |
| `physics/thermal.py::estimate_junction_temp` | temper-thermal | #585 |
| `physics/inductance.py` | temper-thermal | #597 |
| `metrics/quality_score.py` | temper-quality-oracle | #623 |

### Phase 2 — contracts-as-pyclasses (5 landed + residuals decided)
| Contract | Home crate | PR |
|---|---|---|
| `core/net_types.py` | temper-design-bundle | #560 |
| `core/loop.py` | temper-design-bundle | #578 |
| `core/design_rules.py` | temper-design-bundle | #586 |
| `placer/cp_sat/gates.py` contract types | temper-design-bundle | #599 |
| `core/priority.py` | temper-design-bundle | #622 |

- **#622** also recorded the **R7 residual decisions** (in the program plan, Phase 2 section): `pcl/constraints.py`, `routing_results.py`, `protocol.py` JUSTIFIED-KEEP'd with concrete blockers (ortools-encoder entanglement; 9 unmigrated router_v6 types; structural-typing Protocols); `core/loss_types.py` → RETIRE (self-declared JAX stubs); board/netlist deferred to the Phase 3 pull; 11 more surfaces decided with Step-3 evidence.

### Phase 3 — formats/IO (planned, ready to pull)
- **#634** Phase 3 plan (`docs/plans/2026-08-02-001-feat-wave4-phase3-formats-io-plan.md`): board/netlist MIGRATE as parse targets (D5 re-decide), kiutils REMOVE (17 importing modules incl. 2 outside io/), parse chain = critical path (contracts → parse → write), loaders + DSN opportunistic parallel, residuals decided. 7 candidates, 1,243+9,229 LOC. Passed adversarial + coherence doc review; all findings fixed in place.

### Main-state CI debt fixed
- **#559** required-checks manifest sync (unblocked the gate break from the ladder merge)
- **#569** DRC ceiling re-measure (K2 re-solve) + golden baseline + evidence provenance (3 docs) + config reference + vacuous metamorphic gate fix
- **#582** DRC ceiling re-measure (#568 edge-nudge) + golden baseline
- **#600** plan inventory regen; **#601** + **#620** evidence provenance reachable-commit fixes (19 + 13 docs)
- **#632** R8 living inventory refresh (123,568 product Python; migration progress masked by board-workstream growth, disclosed)
- **#587** ruff SIM201 lint debt in net_types test

---

## The type-stub infrastructure (the biggest durable win of the session)

`packages/temper-placer/stubs/temper_design_bundle_python/__init__.pyi` — a full `.pyi` stub for the compiled pyo3 extension, covering all five landed pyclass modules (net_types, loops, design_rules, gates, priority) plus the module functions (`sha256_hex`, `preflight_identity`). `mypy_path` already pointed at `stubs/`.

**Why it matters:** the gates.py migration (#599) re-exported pyclasses but mypy cannot introspect compiled extensions — gates.py went 1→43 allowlisted errors. The stub fixed that AND the pre-existing #586 design_rules regression (2 unallowlisted errors that had been silently merged). Allowlist shrank 220→214 errors, 5 entries removed.

**Keep-in-sync rule:** any new pyclass or signature change in `packages/temper-design-bundle/src/*.rs` MUST be mirrored in the `.pyi` — the Type Check gate catches drift. This is now the standard step for every Phase 3 migration.

---

## Tracked issue (#575) — board-workstream decision

`test_regression_drc.py` has 4 stale DRC ratchet constants (committed-board total 1283 vs measured 1405; committed-board shorting 90 vs 133; router-output total 1436 vs 1524; router-output shorting 125 vs 145-199). All date from 2026-07-29, pre-dating the K2 RT314012 re-solve (#517, #568) that changed the board.

**This is a real quality signal, not a test bug** — the K2 re-solve increased cross-net shorts on the board itself (~1.5× committed-board shorting). The ratchets are correctly catching it. The test's own text says "do not raise it to go green."

**Decision needed from the board workstream:** whether the K2-resolve router-output shorts are acceptable (keep the placement + re-baseline with justification) or a defect to fix (revise placement; ratchet passes without touching). Do NOT silently re-baseline.

---

## Session lessons (hard-won, some already codified)

1. **`grep -c "eigh"` lies** — substring matches ("weight", "eight") inflated a count to 27; the real `np.linalg.eigh` at `netlist.py:427` needed honest treatment in the Phase 3 plan's D5 re-decide. Always `grep -n` the exact call pattern.
2. **Fresh `.so` verification is mandatory** — after `maturin develop`, verify `python -c "import ...; hasattr(t, '<NewType>')"`. Stale extensions from concurrent `uv sync` evictions bit 3+ times this session.
3. **Vulture gate fixtures** — test fixtures MUST be underscore-prefixed (`_restore_kernel`); the vulture gate flags bare fixture names as dead code.
4. **CPython repr divergences are real** — `py_str_repr` (single quotes, B9) and `py_float_str` (exponent sign/padding + `nan`, B10) are required in any `__repr__` asserted byte-for-byte. `{:?}` writes `1e300`/`1e-5`/`NaN`; CPython writes `1e+300`/`1e-05`/`nan`.
5. **Enum semantics** — plain `Enum` ≠ `IntEnum`; pyo3 `#[pyclass(eq, hash)]` gives member identity (load-bearing: consumers do `x is GateStatus.CLEAN`) but NOT int-comparison or class-iteration. `members()` staticmethod is the iteration substitute; consumer adaptations (loop_loader) land inside the migration PR.
6. **The anti-vacuity gate flags `X is X`** — even when the intent (member identity caching) is legitimate. Rewrite as `getattr(Cls, "M") is Cls.M` (different access paths, Call-free exclusion).
7. **The CI queue saturates** — the repo's concurrent agents back up runners for 30+ min. Docs-only PRs with 0 failures and verified-clean local gates merge with admin per convention; the Required Python Tests aggregator often completes independently.
8. **Branch contamination risk** — rebasing in a worktree that has another branch's files checked out can pull the wrong commits into a push (the #581 incident: the loop migration leaked into the ceiling-fix branch). Always verify `git log origin/main..<branch>` before pushing.
9. **R8 living inventory** — the migration progress is masked by concurrent board-workstream growth (placer +2,200 LOC from #523 machinery). The plan's inventory is refreshed with this disclosed; measure per-area deltas, not just totals.

---

## Next actions (in dependency order)

1. **Phase 3 first pulls** (plan ready): candidate 2 (loaders — netclass/loop, low risk, contracts already Rust) opportunistically; candidate 1 (board/netlist contracts, the critical-path spine) with the consumer-semantics audit budgeted (iteration, dunders, numpy dtype behavior — the honest loop_loader precedent applies).
2. **Phase A continues** in parallel — more small kernels from metrics/regression/physics; if nothing clean remains, apply the R7 procedure (JUSTIFIED-KEEP with evidence) rather than forcing.
3. **#575 board-workstream decision** — blocks the regression job's full green; needs an owner call.
4. **Remaining phases** — Phase 5 orchestration (ParsedPCB verdict owned there), Phase 6 residuals (visualization, scripts/, test suite — R3 decisions).

## Standing constraints (unchanged)

- `pcb/**` and `elec/src/**` read-only except for tasks explicitly scoped to them.
- The board path is the critical path (STRATEGY.md); the program commits no capacity (R5).
- Never weaken a ratchet/allowlist/cap to pass; never add `continue-on-error`; report-and-record over fake convergence.
- DRC ceiling re-measurement is part of any board-changing PR (AGENTS.md protocol).
