---
date: "2026-07-11"
topic: finish-the-board-agent-handoff
status: handoff
---

# Agent Brief: Finish the Temper Board (100% routed, literal-zero DRC/ERC)

## CURRENT STATE (2026-07-12, latest) — 100% routed; DRC at 381 after all fixes

**Mission half #1 (routing completeness): DONE.** On the CP-SAT-optimized placement the board routes **100% (24/24 nets, 0 unconnected items confirmed by `kicad-cli`)**.

**Mission half #2 (literal-zero DRC): 991 → 381 (62% reduction).**

Full campaign tally (all fixes committed):

| Fix | DRC | delta | commit |
|---|---|---|---|
| Baseline (7 placement-seam bugs fixed) | 948 | — | `71dacba5` |
| Zero-width plane-net tracks | 948 | − | `ae3b9fa8` |
| Segment merge at emission (8,908→700 segs) | 948→403 | −545 | `a0581a49` |
| R4 FinePitch clearance (0.15mm routing) | 403→381 | −22 | `051152e7` |
| **Cumulative** | **948→381** | **−567** | — |

(From the original 991 before zero-width, the true reduction is 62%).

0 unconnected items throughout. Routing remains 100% on the CP-SAT-placed
substrate.

**Current violation breakdown (381):** clearance 123, crossing 67, mask-bridge
86, shorting 68, lib/config 33, other 4. Decomposed to ~235 unique physical
positions: signal-only 205, power-only 97, zero mixed. The MCU/SPI fanout
(SPI_MISO/SPI_MOSI/SPI_CLK) remains the densest cluster; the power-stage edge
is a secondary cluster. Twin-number confirmed: 50 positions co-fire both
shorting AND mask-bridge.

**Levers tried and measured:**
- Grid refinement (0.1mm cells): no-op — already at 0.1mm; hypothesis wrong
- Congestion routing (congestion_weight=2.0): 381→369 but +1 unconnected —
  net negative; not committed
- Visibility-gated segment merge: 381→626 — massive regression; not committed

**Honest frontier — architecture-level, not micro-optimization:**
The levers that work at the emission level (merge, clearance tuning) are
exhausted. The remaining ~235 physical spots need:
- Multi-layer routing (use the 4-layer stackup for MCU fanout — crossing
  traces on F.Cu separate onto inner layers)
- Or a post-route shove pass (adjust trace coordinates locally to meet
  clearance without changing topology)
- Or re-routing specific nets with higher path cost in congested regions

The crossing penalty from segment merging (67 crossings) is accepted as
inherent — the spatial-hash visibility gate was counterproductive (recovers 7
crossings, costs 242 additional violations). The merge is a net +545 win.

**The `routed_pcb_content` is available — `kicad-cli` confirms 0 unconnected.**
To reproduce: CP-SAT place (commutation loop retained, gate-drive loop-area
excluded pending R24), `route_pcb` with committed pipeline defaults, write
`routed_pcb_content`, `kicad-cli pcb drc --format json`.

**Still-open R24 modeling question (unchanged):** the gate-drive loop-area
constraint is modeled as AABB-of-component-bodies, making ≤100 mm² infeasible.
Needs physics owner + Chebyshev-soundness proof.

**Commits this arc:** `71dacba5` (placement seam), `ae3b9fa8` (zero-width),
`a0581a49` (segment merge), `051152e7` (R4 FinePitch + netclass parser),
`27edee76`/`cf29bfd7` (compound docs + handoff).

---

## Mission (historical — the investigation trail)

*The sections below are the original ARC investigation record, retained for context.
The current ground truth is in the section above.*

---

# Agent Brief (historical) — the placement-seam investigation trail

**THE WALL WAS NOT A DESIGN CONFLICT — it was two MORE silent constraint bugs (the adversarial gate paid off).**
The earlier draft of this brief concluded the placement was "provably infeasible → a real power-stage geometry conflict." **That conclusion was wrong.** Before treating INFEASIBLE as a design verdict, each constraint in the UNSAT core was verified individually (the session's own discipline). Two were mis-encoded:

1. **`_encode_adjacent` ignored `metric`** (FIXED). The config says `adjacent Q1-Q2 max 10mm metric: edge_to_edge`, but the encoder *always* used center-to-center. For 25.3mm-wide IGBTs placed side-by-side (forced by `on_side top`), no-overlap requires centers ≥25.3mm apart, while center-to-center adjacency demanded ≤10mm — a hard contradiction (25.3 > 10) that is *invisible* in the config and only exists in the encoding. Fixed to honor `EDGE_TO_EDGE`/`PIN_TO_PIN` (per-axis bounding-box gap) vs `CENTER_TO_CENTER`. Tests added.
2. **`pcb_spec.yaml` gate-drive loops referenced phantom `U_GATE_DRV`** (FIXED → `U_GATE`). The loop-area encoder silently computed the loop over a *partial* component set (fail-loud didn't catch it because `loop_components` load via a different path than `validate_constraint_refs`).

**Measured causation (both independently load-bearing):**
| adjacent metric | gate-drive loops | result |
|---|---|---|
| buggy (center) | correct | infeasible |
| fixed (edge) | drifted `U_GATE_DRV` | infeasible |
| fixed (edge) | commutation-only | **optimal, 33/33** |

With both fixes and the correctly-modeled commutation loop, the placement is **`optimal`, 33/33 placed, and `J_AC_IN` (mains) IS contained in HV_ZONE — safety claim now verified TRUE from coordinates.** The ≤500 mm² commutation-loop margin I was about to relax is **innocent and correctly specified** — relaxing it would have masked two real bugs. (Guard #2 held; the adversarial constraint-verification gate is what saved it.)

**ONE REMAINING open item — a modeling question, NOT a bug, do NOT guess:**
With the gate-drive loops now correctly referencing `U_GATE`, the `gate_drive_low` loop (≤100 mm² over {U_GATE, R_GATE_L, Q2}) is infeasible for *any* placement: it contains Q2's full 25.3mm IGBT body + U_GATE's 9.49mm height → minimum AABB ≈ 240 mm² ≫ 100 mm². **This is a soundness/modeling question under R24, not a trivial fix:** the encoder models loop area as the AABB of whole component *bodies*, but the physical gate-drive loop is the current path (driver pin → gate resistor → IGBT *gate pin* → return), which is far smaller than the IGBT body. Either the loop-area model must be pin-based, or the 100 mm² spec is against the wrong geometry. **Needs the physics owner + a Chebyshev-soundness proof (R24) — do not paper over by relaxing 100 mm².** Until resolved, the full end-to-end run is feasible only with the gate-drive loop-area constraints excluded (commutation loop retained).

**New files/fixes this pass:** `placer/cp_sat/encoder.py::_encode_adjacent` (honor `metric`), `configs/pcb_spec.yaml` (U_GATE_DRV→U_GATE), tests in `test_encoder.py::TestAdjacent` (edge-to-edge + center-to-center).

---

## UPDATE 2026-07-11 (later session) — placement path fixed; the wall is now a proven-infeasible placement

The "Step 0: fix the broken placement path" work below is **done**, and it changed the picture. Read this before the original brief.

**What was fixed (all verified by running, not reading):**
1. **Placement→route seam works now.** The two halves run end-to-end for the first time. The break was NOT "CP-SAT unwired" — it was two concrete bugs:
   - **Zone-bounds convention mismatch.** The temper config wrote zones as `(x, y, width, height)` on a phantom 120×80 board; the encoder + every other config use `(x_min, y_min, x_max, y_max)` on the real 100×150 board. Inverted rects silently became empty zones → `model_invalid` → UNSAT round 1. Fixed by (a) a validated `Rect` value type (`core/board.py`) with `from_xyxy`/`from_xywh` constructors that make the convention explicit and reject inverted/degenerate rects at construction, and (b) rewriting the temper config zones to canonical xyxy on the real board (HV top / 10 mm isolation / MCU bottom, consistent with the on_side connector constraints).
   - **The `constraints:` block was silently dropped.** `load_constraints` had no parser for the top-level `constraints:` list — only 1 of ~29 constraints reached the solver. Added `_parse_pcl_constraints` (delegates to `parse_constraint_dict`) + registered the keys.
2. **Initial-solve budget** (`loop.py`): round 1 solves the full model cold and needs a bigger budget than the 1 s warm re-solve target. Added `INITIAL_SOLVE_TIMEOUT_MS = 30000` used only for round 1. *Measured* before committing: 1 s → 0 placed; 30 s → 33/33.
3. **Fail-closed guard for config↔netlist drift** (`encoder.validate_constraint_refs`): a constraint whose operand resolves to no component/zone/loop now RAISES instead of silently dropping. This is the guard that surfaced finding #4 below at the source instead of in a log grep. Override with `TEMPER_UNRESOLVED_REF_POLICY=warn` for exploratory runs.

**Config↔netlist drift found + partially reconciled:**
- **Mechanical renames applied** (unambiguous): `J_AC → J_AC_IN` (AC mains connector), `U_RTD → MAX31865` (the RTD sensor frontend).
- **Genuinely-missing parts, DISABLED with documented NOTEs in the config, NOT guessed** (these are board-completeness decisions, not renames): `C_TANK` (resonant tank cap — functionally required for a resonant stage, likely a real missing part), `D_BOOT` (bootstrap diode), `J_FAN` (fan connector), `U_SPI_FLASH`, `C_VCC1/C_VCC2` (board has single `C_VCC`), `CT1` (board has `U_CT`/`U_OPAMP_CT` — mapping unclear). **Decide whether these components should exist on the board.**
- **`pcb_spec.yaml` loop drift** (out of scope, flagged): `gate_drive_high/low` loops reference `U_GATE_DRV`, absent from the board (board has `U_GATE`).

**THE NEW WALL — the placement is now PROVABLY INFEASIBLE (this is a real result, not a timeout):**
> ⚠️ **SUPERSEDED by the section at the top of this file.** The "genuine power-stage geometry conflict" conclusion below was WRONG — verifying each core constraint (per the adversarial gate) found two more silent constraint bugs (`_encode_adjacent` ignoring `metric`, and the `U_GATE_DRV` phantom loop ref). Once fixed, the placement is `optimal` 33/33 with J_AC_IN contained. Kept here only for the investigation trail. Read the top section for the real state.

With the drift corrected and all constraints actually applied, CP-SAT returns `INFEASIBLE` (proven in ~15 s, not `unknown`). The UNSAT core (`SufficientAssumptionsForInfeasibility`) *appeared* to be a power-stage geometry conflict:
```
edge_margin_{C_BUS1,Q1,Q2} + loop_area_commutation_loop (≤500mm²)
+ oside_side_top_{Q1,Q2} + align_x_{Q1,Q2} + adj_C_BUS1_Q1
```
Q1/Q2 pinned to the top edge, x-aligned, with C_BUS1/C_BUS2 inside a ≤500 mm² commutation loop, all within edge margins — cannot be simultaneously satisfied on this board. **This is exactly the kind of conflict you must NOT resolve by relaxing a constraint (guard #2).** It is a design-geometry / board-completeness question: either the board/zone geometry is wrong, the loop-area budget is wrong, or missing parts (C_TANK etc.) change the layout. Re-diagnose with the UNSAT core; do not paper over it.

**⚠️ Safety claim status (UPDATED — now verified):** Once the two constraint bugs above were fixed, `J_AC_IN` (mains input) HV-zone containment was confirmed TRUE from the produced coordinates (optimal placement, commutation loop retained, gate-drive loop-area excluded pending the R24 modeling question). Earlier this could not be asserted; it now can, for that configuration.

**Downstream, do not chase as a router bug:** the loop's `no_classifiable_feedback` exit is downstream of the config drift (the feedback classifier referenced unresolved refs). Re-evaluate it only after the placement is feasible.

**Files touched this session:** `core/board.py` (Rect + Zone validation), `io/config_loader.py` (`_parse_pcl_constraints` + known keys), `placer/cp_sat/encoder.py` (`validate_constraint_refs` + zone coercion + INITIAL budget wiring point), `placer/cp_sat/loop.py` (`INITIAL_SOLVE_TIMEOUT_MS`), `configs/constraints/temper_induction_cooker.yaml` (zones + renames + disabled-drift NOTEs). Tests: `tests/core/test_board.py::TestRect`, `tests/placer/cp_sat/test_encoder.py::TestValidateConstraintRefs`.

---

## Mission
Take the temper induction-cooker board (`power_pcb_dataset/corpus/temper/temper.kicad_pcb`) to **100% routed** and **literal-zero DRC/ERC**, **without relaxing any constraint**. Verify every claim by running the tool on the actual board — not by reading code or trusting a solver's "OPTIMAL."

## READ THIS FIRST — the diagnosis's fix is already in the code and may not work
A prior agent diagnosed the 3 failing nets (SPI_MOSI, SPI_CLK, I_SENSE) as an *ordering* problem — "route signals after power nets so they aren't displaced" — and concluded it's a cheap one-line fix, not a congestion engine. **That conclusion is in doubt, because the fix is already implemented:**

- `router_v6/pipeline.py:466–476` — `pcb.nets.sort(key=_prio)` already orders power/HV first, signals last, at Stage 0 *before routing*. This is real and in effect.
- `router_v6/adapter.py:288–298` — the *same* sort, but a **no-op**: applied after `pipeline.run()` (line 270), and `net_order` is never passed into the router. Dead code; remove or wire it, but it changes nothing today.

The router is `rrr_route_all_nets` — **rip-up-and-reroute**. In RRR, initial net order is a *weak lever*: nets are ripped up and rerouted by congestion cost across rounds regardless of start order. So "signals last" (already applied in the pipeline) does not prevent later-round displacement — which is likely *why the board is still not closing despite the fix being present*.

## MEASURED STATE (2026-07-11) — read this, it's the ground truth
Router completion on the temper board, current code as-is: **83.3% (20/24 nets)** — not 100%, not the diagnosis's 87.5%. Failed nets (exactly 4): **SPI_MOSI, SPI_CS_TEMP, PWM_L, PWM_H**. (~20s wall; 22 DRC / 33 warnings, but those are *unqualified* — R5 library-table config is unaddressed, so they're the mismeasured instrument, not a verdict.) Note: the summary line "Router completion: 0.8%" is a **display bug** — it prints the 0.833 fraction with a `%` sign; the real figure is 83.3%. Fix that formatting so nobody misreads it.

**The ordering conclusion is dead, and the measurement proved it *stronger* than predicted.** The pipeline's signals-last sort *is* taking effect — it changed *which* nets fail (SPI_CLK and I_SENSE now route; SPI_CS_TEMP, PWM_L, PWM_H now fail instead) **without reducing the count** (4, not 3). Ordering shuffles the MCU-region contention around; it does not resolve it. That's the RRR weak-lever signature. Do not re-attempt ordering.

## Step 0 — the real first task: FIX THE PLACEMENT PATH (it is broken)
**Placement did not run in the measured route.** The runner reported `benders_iterations: 0` and "All strategies exhausted (JAX placer removed; use CP-SAT deterministic)" — so routing used the board's **original positions, not a CP-SAT placement.** This is the headline finding:

1. Every routing number in this project's arc (87.5%, 83.3%, Round 4, the isolation test) is on the **un-optimized original layout**, never on the CP-SAT placement the project is built around.
2. **R3 (placement-side) is re-opened.** The diagnosis closed it via "isolation → legal paths exist → router-side," but that was isolation *on the original placement*. The MCU-region contention is plausibly a *placement* property a routability-aware CP-SAT placement would relieve. R3 wasn't eliminated — it was never tested, because the placer never ran.
3. The CP-SAT placer and the router **have never run end-to-end together.** That is a bigger gap than the 4 failing nets.

**So the first task is to repair the place→route pipeline's placement step** (JAX retired, CP-SAT not wired into this path) so the router runs on the CP-SAT placement, then **re-measure completion.** A working placement may resolve the MCU congestion for free. Do NOT tune negotiated-congestion or add a 4th layer against the original positions — you'd be optimizing the router for a placement you're about to replace.

- Prereq: `import temper_rust_router` must work on `.venv` (it does — Framework/shared-libpython Python; if it crashes, the venv regressed to miniforge-static, rebuild with `uv venv --python /opt/homebrew/bin/python3.12`).

## Then branch on the re-measurement (router running on the CP-SAT placement)

**If it routes 100%** → the placement was the fix; skip to R4/R5, then verify literal-zero DRC/ERC.

**If it's still < 100%** → *now* the failure is genuinely router-side on the right substrate. Re-diagnose *within RRR reality*:
1. Confirm the pipeline's Stage-0 sort is actually taking effect (add logging; is the routed order what you expect?).
2. Since order is a weak lever in RRR, the real fix is one of:
   - **Congestion management** — the negotiated-congestion / rip-up-reroute *cost* tuning (history increment/decay, penalty scaling — see `rrr_route_all_nets` params `_history_increment`, `_history_decay`, `_p_scale_*`). This is the "cathedral" the diagnosis thought it had escaped. It may be unavoidable.
   - **The 4th layer for the contended nets** — legitimate and diagnosis-justified *if* congestion can't fit them in the current stackup. 4-layer is the target; use it only if congestion genuinely can't resolve the MCU-region contention.
3. Re-verify the Round-4 "slack proven" claim under the *current* ordering. Round 4 showed the six nets *can* coexist; if signals-last is already applied and they still fail, the slack may not survive RRR's full net set. Re-check.

## The rest of the work (independent of routing)

**R4 — FinePitch netclass calibration.** Intra-component pad↔pad clearances on U_MCU/J_USB (same component both sides — place-and-route cannot fix) are legal only if the netclass rule matches the QFN/connector pad pitch. Assign the fine-pitch nets (SPI/USB/PWM on U_MCU; USB on J_USB) to `FinePitch` (0.1 mm) in `packages/temper-placer/configs/netclass_rules.yaml` + net assignments. This is a rule-accuracy fix (rule → geometry), **not** a relaxation.

**R5 — DRC gate library-table config.** The 33 `lib_footprint_issues` are "footprint library 'Capacitor_SMD'/'Package_SO'/… not in current configuration" — the headless `kicad-cli` DRC lacks the standard KiCad libraries. Configure the footprint library table so they resolve. This fixes the *measuring instrument*, not the board.

## Success criteria (the bar)
1. `kicad-cli pcb drc` (library table configured) on the final board: **0 DRC, 0 unconnected, 0 ERC**.
2. **No constraint relaxed** — diff the constraint config vs. today; unchanged except any deliberate, *documented* design-margin decision.
3. Every closure traceable to a diagnosis, not to a resource/constraint change.

## Non-negotiable guards (this project's hard-won discipline)
1. **Measure the territory, not the map.** Verify *outcomes* — actual `kicad-cli` DRC on the actual generated board. This project has been bitten repeatedly by false zeros, sentinels, asymmetric comparisons, and — as this very brief documents — a *phantom fix that looked applied but was a no-op*. Assume nothing is done until you've run it.
2. **Never relax a hard safety/regulatory constraint to buy completion.** Creepage, edge clearance, the 3.0 mm IEC 60335-1 floor are inviolable. A 100%/zero bought by relaxing a constraint is a FALSE result and fails the bar.
3. **Fail-closed measurement.** A DRC/route run that can't complete (tool error, board won't load) is NOT "zero" — it's "unmeasured." Surface it loudly.
4. **A fix that exists in code is not a fix that works.** Confirm effect by measurement, at the point in the pipeline where it can actually take effect (the phantom adapter sort is the cautionary example).

## Key files
- Router adapter: `packages/temper-placer/src/temper_placer/router_v6/adapter.py` (`route_pcb`, `rrr_route_all_nets`)
- Router pipeline: `packages/temper-placer/src/temper_placer/router_v6/pipeline.py` (`run`, Stage-0 net sort at 466–476)
- Net ordering module: `packages/temper-placer/src/temper_placer/router_v6/net_ordering.py` (`order_nets`, priority config — a third ordering path; reconcile which governs)
- Netclass SSOT: `packages/temper-placer/configs/netclass_rules.yaml`
- Board: `power_pcb_dataset/corpus/temper/temper.kicad_pcb`

## Context docs (read for the "why")
- `docs/brainstorms/2026-07-10-finish-the-board-requirements.md` — the requirements + guards
- `docs/plans/2026-07-10-001-feat-finish-the-board-plan.md` — the plan
- `docs/solutions/best-practices/per-net-isolation-routing-diagnosis-2026-07-10.md` + `round-coexistence-*` + `seed-stability-*` — the diagnosis ladder (note: its "ordering fix" conclusion is the thing now in doubt — see above)

## The one-sentence version
Routing is at 83.3% on the board's *original* positions because the CP-SAT placement step is broken; the ordering fix is already in the pipeline and only shuffles the 4 failures around — so fix the placement path and re-measure *before* touching congestion tuning or the 4th layer, and never re-attempt ordering.
