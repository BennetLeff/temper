# Temper Project Strategy

**Version:** 1.0  
**Date:** 2026-06-22

## Target Problem

The Temper is a consumer induction cooker. It must deliver safe, precise, and efficient cooking to end users while meeting regulatory requirements for electrical safety and electromagnetic compatibility.

## Approach

- **Firmware-first safety**: All protection circuits (OCP, OVP, thermal shutdown, UVLO) are hardware-latched with firmware monitoring. Software cannot override hardware protection.
- **Test-everything validation**: Every protection and performance gate listed below is tested via Unity test, hardware procedure, or simulation before fab sign-off. No gate ships without coverage or an acknowledged gap.

## Non-Negotiable Safety and Performance Gates

These gates must be verified before any PCB fabrication release. A traceability mapping of each gate to its test coverage is maintained in `docs/TRACEABILITY.md`.

### Performance Gates

| Gate ID | Description | Reference |
|---------|-------------|-----------|
| EFF-01 | Efficiency >90% @1000W | `docs/FUNCTIONAL_TEST_CRITERIA.md` §1.1 |
| EFF-02 | Efficiency >92% @1800W | `docs/FUNCTIONAL_TEST_CRITERIA.md` §1.1 |
| EFF-03 | Standby power <1.0W | `docs/FUNCTIONAL_TEST_CRITERIA.md` §1.1 |
| PWR-01 | Power accuracy ±10% @1000W | `docs/FUNCTIONAL_TEST_CRITERIA.md` §1.2 |
| PWR-02 | Power accuracy ±5% @1800W | `docs/FUNCTIONAL_TEST_CRITERIA.md` §1.2 |
| PID-01 | Temperature accuracy ±2°C | `docs/FUNCTIONAL_TEST_CRITERIA.md` §1.3 |
| PID-02 | Temperature stability ±1°C (30min) | `docs/FUNCTIONAL_TEST_CRITERIA.md` §1.3 |
| PID-03 | Overshoot <5°C | `docs/FUNCTIONAL_TEST_CRITERIA.md` §1.3 |
| PID-04 | Settling time <5min | `docs/FUNCTIONAL_TEST_CRITERIA.md` §1.3 |

### Protection Gates

| Gate ID | Description | Reference |
|---------|-------------|-----------|
| OCP-01 | Primary OCP 45-55A, <1µs | `docs/FUNCTIONAL_TEST_CRITERIA.md` §2.1 |
| OCP-02 | Secondary OCP 55-65A, <5µs | `docs/FUNCTIONAL_TEST_CRITERIA.md` §2.1 |
| OVP-01 | DC Bus OVP 390-410V | `docs/FUNCTIONAL_TEST_CRITERIA.md` §2.2 |
| THM-01 | Heatsink NTC 85°C shutdown | `docs/FUNCTIONAL_TEST_CRITERIA.md` §2.3 |
| THM-02 | Coil NTC 120°C shutdown | `docs/FUNCTIONAL_TEST_CRITERIA.md` §2.3 |
| UVL-01 | Gate Drive UVLO <12.0V | `docs/FUNCTIONAL_TEST_CRITERIA.md` §2.4 |
| UVL-02 | Logic UVLO <2.9V | `docs/FUNCTIONAL_TEST_CRITERIA.md` §2.4 |

### EMC Gates

| Gate ID | Description | Reference |
|---------|-------------|-----------|
| EMC-01 | CISPR 14-1 Class B 150-500kHz | `docs/FUNCTIONAL_TEST_CRITERIA.md` §3.1 |
| EMC-02 | CISPR 14-1 Class B 0.5-5MHz | `docs/FUNCTIONAL_TEST_CRITERIA.md` §3.1 |
| EMC-03 | CISPR 14-1 Class B 5-30MHz | `docs/FUNCTIONAL_TEST_CRITERIA.md` §3.1 |

### Mechanical Gates

| Gate ID | Description | Reference |
|---------|-------------|-----------|
| MCH-01 | Button Force 2-5N | `docs/FUNCTIONAL_TEST_CRITERIA.md` §4 |
| MCH-02 | Knob Torque 0.5-2 N·cm | `docs/FUNCTIONAL_TEST_CRITERIA.md` §4 |
| MCH-03 | Glass Load 20kg | `docs/FUNCTIONAL_TEST_CRITERIA.md` §4 |

## Current Board Closure State (2026-07-24)

The board-level closure frontier, recorded so planning decisions anchor on
honest numbers rather than a stale "24/24 routed" figure. The frontier shifts
as pending honesty work (forced-segment fail-closed generalization,
DRC/ERC gate) ships, so this section is treated as the current snapshot, not a
fixed target.

- **Total nets** on `pcb/temper.kicad_pcb`: **151** (`(net 0)` through
  `(net 150)`).
- **A* router signal-net subset**: **~95 nets** (per commit `f53aa042`).
  Power/ground/HV nets are excluded from A* by `_should_route()`
  (`router_v6/_astar_reconstruct.py`) because they require zone pours, not
  point-to-point pathfinding. Current frontier: **72/95 routed** as of
  `f53aa042` (a regression from 71→62 on a `_should_route()` loss was
  restored to 72). The historical **"24/24 routed"** figure found in older
  docs (`ROUTER_V6_VERIFICATION_REPORT.md`, `2026-07-11` handoff, `2026-06-23`
  closure tests) refers to the **piantor benchmark board**, NOT the temper
  production board — it must not be carried forward as the temper frontier.
- **High-fanout plane-style nets** (power/ground/return rails: `PWR_RTN`,
  `+3V3`, `+15V`, `DC_BUS_RTN`, `+340V_BUS` and similar, ~56 of 151 nets):
  handled by hybrid pour + trace-stitch
  (`docs/plans/2026-07-22-001-feat-hybrid-pour-trace-stitch-plan.md`), not the
  A* signal router. Zone pours enabled by default as of commit `b9cfbdb4`.
- **Forced-segment fail-closed generalization** (brainstorm `2026-07-24-router-
  forced-segment-fail-closed-requirements`): pending. Once shipped, the honest
  A*-routable completion number (currently 72/95) becomes the new baseline —
  possibly **lower than 72/95**. The frontier will be re-stated here after
  re-measurement and must not be carried forward as a stale figure.
- **DRC frontier**: **381 honest violations** per the `2026-07-11` handoff,
  unchanged by routing completion. Emitter-cleanup is a separate follow-up
  track; the measurement gate (`docs/plans/2026-07-23-001`) ensures the number
  is trustworthy, not zero.
- **ERC**: no `kicad-cli pcb erc` code path exists yet. Plan `2026-07-23-001`
  U2 is the activation track; frontier is currently **UNMEASURED**.

### Strategy-Level Move Set (in order)

The strategy is now sequenced at the level above the placement/router subtree.
These are not leaf hygiene fixes; they lift the planning horizon from "CAD
closure" toward the performance/protection gates that actually gate fabrication
sign-off and eventual IEC 60335-1 certification.

1. **Close the honesty tangent deliberately** — verify the already-shipped
   forced-segment fail-closed generalization (commit `f53aa042` + code
   references to `2026-07-24-001-fix-forced-segment-fail-closed-plan.md`),
   ship the DRC/ERC anti-false-zero guard (`2026-07-23-001`), then
   explicitly halt new placer/router hygiene leaves. Declare the measurement
   trustworthy enough to act on; do not optimize it further.
2. **Pivot the top-level plan from CAD closure to a fab-ready board** — define
   "done" as a digital file set (Gerbers + BOM + placement) that clears, via
   a single per-gate verdict layer, the *board-level* gates feeding the safety
   envelope: HV/LV creepage/clearance (already partially built in `temper-drc`),
   OCP/OVP/UVLO component selection + layout interlock with firmware —
   including a **static `@req`-traceability assertion** per protection gate
   (OCP-01/02, OVP-01, THM-01/02, UVL-01/02) on `firmware/main/state_machine.c`
   and `firmware/main/transition_table.h`, thermal (heatsink NTC 85°C gate,
   coil NTC 120°C gate placement), and a functional power stage that can in
   principle hit EFF-01/02. **The verdict PASS is a precondition for
   fabrication, not a product milestone** — no board exists, no protection
   has tripped, no performance has been measured yet. This plan does not yet
   exist; it is the next-level anchor.
3. **Open the firmware + hardware validation track** as a first-class plan tied
   to the protection gates (OCP-01/02, OVP-01, THM-01/02, UVL-01/02). The
   firmware state-machine (`main/state_machine.c`), transition-table codegen,
   and SIL fault-injection plans are all active but disconnected from a
   "power this board on a bench and trip each protection" exit criterion —
   which is what fabrication sign-off and eventually IEC 60335-1 actually
   gate on.
4. **Fabrication + Mechanical + Cert-Lab Handoff Track** — owns CM
   submission of move 2's file set, component procurement, board turnaround,
   delivery of a built board to move 3, **mechanical-gate validation
   (MCH-01/02/03: button force, knob torque, glass load)**, and the
   handoff to the accredited IEC 60335-1 / CISPR Class B certification lab.
   MCH gates are non-negotiable per the gates above but cannot be
   validated digitally; this track owns them physically. Trigger:
   unlocked when move 3a (protection-trip validation only) shows PASS for
   every protection gate. No move prior to move 4 owns fabrication or
   mechanical validation.

The moves are sequenced — each is enabled by the trustworthiness of the
prior — and track-owned separately so each can hand off to `ce-plan`
independently for *planning*. **The moves are independently plannable, NOT
independently shippable**: move 2's verdict PASS is gated on move 1's
recorded-honest frontier; move 3's bench PASS is gated on move 2's R7
firmware-traceability assertion; move 4 is gated on move 3a's
protection-trip PASS. In the floor-failure branch (move 1 R4: hard-safety
nets not all routed), move 2 cannot ship until a separate routing-recovery
track restores routability — the moves collapse into one serial chain in
that branch. Brainstorm artifacts for all three live under `docs/plans/`
once written.

### Hygiene-tangent halt friction

Reopening a placer/router hygiene leaf after the halt fires (move 1 R3)
requires a stated reason logged against the Current Board Closure State
section above — the halt is a recorded-frontier discipline, not a deployment
of a CI mechanism, and the friction is what keeps a regression from
silently re-rotting the recorded frontier. The anti-false-zero CI guard
(`docs/plans/2026-07-23-001` U3) is the mechanical backstop for drift.
