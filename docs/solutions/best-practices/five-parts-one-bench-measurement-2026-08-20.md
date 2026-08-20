---
title: "Five blocking components became one bench measurement — and it hasn't happened yet"
date: "2026-08-20"
category: best-practices
module: pcb-hardware-design
problem_type: best_practice
component: isolation-barrier
severity: high
applies_when:
  - "a sourcing sweep finds no compliant replacement part exists in a required package category"
  - "a footprint's intrinsic pad-to-pad distance is in dispute — check rotation-invariance before trusting either figure"
  - "a design decision is about to rest on a simulated value instead of a bench measurement — verify which one it actually is"
  - "a per-pairing or per-domain requirement recomputation changes which components are actually blocking"
tags:
  - creepage
  - cst3015
  - rotation-invariance
  - bench-measurement
  - sourcing-sweep
  - simulated-vs-measured
  - tank-sense-node
---

# Five blocking components became one bench measurement — and it hasn't happened yet

## Verdict, up front

**Under the enforced single scalar (12.6 mm), five components (C6, K1, U6,
T1, T2) were believed to need substitution.** A sourcing sweep found **no
compliant part exists** in either affected category (isolated gate drivers,
package ceiling **10.0 mm**; current-sense transformers, package ceiling
**9.2 mm**, on a 6 A part) — meaning substitution was not merely expensive,
it was not available.

**Under the per-pairing figures derived separately** (see
`docs/solutions/architecture-patterns/isolation-barrier-single-scalar-vs-per-pairing-2026-08-20.md`),
**C6, K1, and U6 clear outright** — the bus-crossing requirement they were
being checked against drops from 12.6 mm to 4.8/8.0 mm. That leaves an UNSAT
core of `{T1, T2}`. A separate finding — a footprint-rotation defect in the
tool that measured T1/T2's intrinsic geometry — then clears **T2** as well,
settling the CST3015 footprint's true primary-to-secondary span at
**9.100 mm** (not the disputed 7.800 mm). **T1 alone remains blocking.**

**T1's remaining question turns on a bench measurement of V(tank-out) that
has not been performed.** A simulation brackets the expected answer at
**41–53 mV**, against a stated falsification threshold of **1.0 V**. This is
a simulated result, not a measured one — `elec/tank_out_working_voltage.yaml`
is deliberately left empty and `scripts/check_tank_out_declaration.py` exits
6 pending the real reading. **Any claim that this question is closed is
premature; the bench measurement is the next action item, not a completed
step.**

## The five components and why they were flagged

| Ref | Category | Required at 12.6mm scalar | Sourcing sweep result | Required at per-pairing figure | Status |
|---|---|---|---|---|---|
| C6 | Y-capacitor | 12.6 mm creepage | — | 4.8 mm (row ii) | **Clears** |
| K1 | Relay | 12.6 mm creepage | No compliant part found | 4.8 mm (row ii) | **Clears** |
| U6 | Isolated gate driver | 12.6 mm creepage | No isolated gate driver reaches it — verified package ceiling **10.0 mm** | 8.0 mm (row iii) | **Clears** |
| T1 | CST3015 current-sense transformer | 12.6 mm creepage | No compliant drop-in CT exists — verified package ceiling **9.2 mm**, on a 6 A part | 8.0 mm (row iii); footprint's own span 9.100 mm | **Remains blocking** — turns on the tank-out bench measurement |
| T2 | CST3015 current-sense transformer (OCP-02) | 12.6 mm creepage | Same category ceiling as T1 | 8.0 mm; footprint span 9.100 mm (see below) | **Clears** once the rotation defect is corrected |

Source: `docs/evidence/2026-08-19-certified-component-creepage-exemption-and-pd3-sourcing.md`
(commit `23d58210d`, initial disposition table against `MIN_BARRIER_WIDTH_MM =
12.6`), updated at commit `582035aee` with the verified category ceilings
(10.0 mm drivers, 9.2 mm CTs).

```
git show 23d58210d:docs/evidence/2026-08-19-certified-component-creepage-exemption-and-pd3-sourcing.md
git show 582035aee -- docs/evidence/2026-08-19-certified-component-creepage-exemption-and-pd3-sourcing.md
```

## Why C6/K1/U6 clear, and T1/T2 do not, moving to per-pairing figures

The five-part UNSAT core is the endpoint of two separate steps, not one:

1. **`30edd0a93`** (`analysis/per-pairing-placer-solve`, built on
   `feat/per-pairing-creepage-derivation`): re-solving placement against the
   per-pairing figures instead of the 12.6 mm scalar shrinks the UNSAT core
   from five parts to two: `{T1, T2}`. Quote: *"C6, K1 and U6 were never real
   failures... at 4.8/4.8/8.0 mm all three place."*
2. **`6a240af9b`** (`analysis/settle-cst3015-copper-span`): resolves a
   dispute about the CST3015 footprint's own intrinsic primary-secondary
   pad-to-pad distance — see below — which flips **T2** from FAIL to PASS,
   leaving **T1 alone**.

## The CST3015 span dispute, settled by rotation-invariance

Two different measurements of the same footprint (`temper:CST3015`)
disagreed: one said the primary-to-secondary edge-to-edge gap was 9.1 mm,
another said 7.8 mm. The dispute was settled with a physical argument that
does not depend on trusting either transform directly: **an intra-package
distance is a property of the footprint, and cannot change when the
footprint rotates.** Rotating each footprint instance rigidly through 0°,
90°, 180°, 270° and recomputing the disputed transform's answer at each
angle:

> "the correct transform returns 9.1000 and 8.0000 every time; the disputed
> one returns 9.1000/7.8000/9.1000/7.8000."

That 9.1/7.8/9.1/7.8 alternation, changing with rotation angle for a
quantity that is physically rotation-invariant, is itself the proof the
disputed transform is wrong. **Note on attribution:** that exact sequence
(9.1/7.8/9.1/7.8) is **T2's** row in the source table; **T1**'s row for the
same disputed transform is the same four values phase-shifted —
7.8/9.1/7.8/9.1. Both instances of the same footprint show the same
rotation-dependence artifact; only the phase differs, which is expected
since T1 and T2 are placed at different rotations on the board.

**Settled span: 9.100 mm for both T1 and T2** (Coilcraft CST3015). K1
(Omron G4A-E) settles at **8.000 mm** by the same method.

```
git show 6a240af9b:docs/evidence/2026-08-19-cst3015-g4a-span-settlement.md
```

(`origin/investigate/cst3015-reinforced-isolation`, holding commits
`23d58210d`/`c2ceb0abd`, carries the original PD3/12.6 mm framing and the
initial 9.1-vs-7.8 dispute before it was settled — cited here for context,
superseded by `6a240af9b` on the settlement question.)

## T1's remaining question: the tank-out sense node

T1's sensing function (`tank-out`) reads the current-sense transformer's
secondary. The open question was whether relocating T1's sensing to avoid
the barrier requires the sense node to move to a different potential than
originally assumed. `docs/evidence/2026-08-19-...` (commit `5e53ceaa0`,
`analysis/t1-sense-node-relocation`) establishes that `tank-out` is one
0.6 V winding away from `PWR_RTN` — not at tank potential — meaning T1's
sensing function does not itself need to move.

What T1's remaining creepage status turns on is a **direct measurement** of
the actual working voltage at the `tank-out` node against SELV, because (per
the isolation-barrier document) the tank crossing is the barrier's
worst-case pairing and is not fully determinable from any standard obtained
this session. The relevant falsifiable question for this specific node:
does `V(tank-out)` stay low enough, in practice, to support the design's
assumption that it is a low-voltage sense point rather than a node that
needs its own barrier treatment?

**Falsification threshold, stated explicitly in the record:** *"A steady-
state cyclic r.m.s. above 1.0 V at the committed 1800 W operating point
falsifies the MAINS reading. That is the number to beat."*

**Simulated result:** V(tank-out) = **41–53 mV**, computed at a geometric
leakage-inductance anchor of 5.6–7.2 nH (sourced to
`docs/evidence/2026-07-28-coil-selection-research.md` §4.2). Well under the
1.0 V threshold — **if the simulation's assumptions hold.**

**Status: this is a simulation bracketing the expected answer, not a
completed bench measurement.** `elec/tank_out_working_voltage.yaml` is
deliberately left empty; `scripts/check_tank_out_declaration.py` exits 6
pending a real reading. **This is the single most important open item in
this document: T1's conclusion currently rests on a simulated 41–53 mV, not
a measured one, and every citation of this number elsewhere should say so.**

```
git show 4245bcdd5:docs/hardware/BENCH-tank-out-winding-voltage.md
git show 4245bcdd5:simulation/harness/run_tank_out_winding_voltage.py
# (branch analysis/tank-out-winding-voltage-simulation)
.venv/bin/python simulation/harness/run_tank_out_winding_voltage.py
```

## What remains open

- **The bench measurement itself.** Nothing in this document, or in the
  branches it cites, substitutes for actually measuring `V(tank-out)` on a
  populated board at the 1800 W operating point (note: see
  `docs/solutions/logic-errors/power-stage-1800w-rating-unreachable-2026-08-20.md`
  for why 1800 W itself is not achievable on this branch circuit — the
  bench measurement will need to be taken at whatever operating point is
  actually reachable, and the 1.0 V threshold re-examined against that
  point if it changes).
- **Whether `MIN_BARRIER_WIDTH_MM` moves to the per-pairing scheme.** This
  document, like the isolation-barrier document, does not recommend an
  answer — `feat/per-pairing-creepage-derivation` is unmerged.
- **T2's disposition** is described here as clearing once the rotation
  defect is corrected; it has not been independently re-measured on the
  physical board after a placement/routing pass incorporating the fix.

## Related

- `docs/solutions/architecture-patterns/isolation-barrier-single-scalar-vs-per-pairing-2026-08-20.md` — the per-pairing figures this document's UNSAT-core reduction depends on.
- `docs/evidence/2026-08-13-t1-ct-sense-hv-lv-creepage-finding.md` — an earlier, independent measurement of T1's real DRC violations (8 clearance/creepage violations, worst 0.3715 mm), and the same footprint's intrinsic 9.1 mm span, measured before this session's rotation-invariance settlement — the two figures agree.
- Branches: `analysis/settle-cst3015-copper-span` (`6a240af9b`), `analysis/t1-sense-node-relocation` (`5e53ceaa0`), `analysis/tank-out-winding-voltage-simulation` (`4245bcdd5`), `evidence/component-certification-creepage-exemption` (`23d58210d` and successors), `analysis/per-pairing-placer-solve` (`30edd0a93`), `investigate/cst3015-reinforced-isolation`.

## Verification notes

All figures above were independently checked twice — once by a dedicated
verification pass against the cited branches, and a second time via a
correction relayed by the task coordinator (itself independently verified
by a peer session) — and the two passes agree exactly, including the
T1/T2 rotation-phase attribution and the simulated-not-measured status of
the tank-out figure. No figure in this document failed to reproduce.
