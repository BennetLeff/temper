---
title: Pour Derivation Rule - Plan
type: fix
date: 2026-07-29
topic: pour-derivation-rule
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ce-brainstorm
execution: code
---

# Pour Derivation Rule - Plan

## Goal Capsule

- **Objective:** Settle the copper-pour derivation rule for R7 of
  `docs/plans/2026-07-28-001-feat-provable-safety-place-and-route-plan.md`
  (copper pours become derived output, regenerated from the routed result) —
  decide which nets should regenerate zone pours and give the eventual
  planner a rule it does not need to re-derive.
- **Product authority:** This artifact owns net-class and net-level
  pour-eligibility (which nets get `F.Cu`/`B.Cu` zone treatment after
  routing). It does not own inner-layer stackup architecture (`U2`/`R8` of
  the provable-safety plan), zone geometry/sizing/clustering mechanics
  (`zone_emission.py`), or the `PWR_RTN` safety-category classification
  question raised below — those are named as follow-ups, not decided here.
- **Open blockers:** None. Every sub-question below is resolved from repo
  evidence; two residual items are recorded as conservative assumptions with
  the measurement that would confirm or refute them (Outstanding Questions).

## Product Contract

### Summary

The rule implemented for R7 — `_zone_layers_for_net()` grants a pour only to
nets whose netclass declares `routing_strategy == "plane_required"`
(`ACMains`, `HighVoltage`) — is **correct for `Power` and `GateDrive`** and
**incomplete for `GND`**. `Power`/`GateDrive` losing their pours is a
deliberate, triply-corroborated decision. `GND` losing its pour is an
accident: a second, human-authored SSOT already declares `GND`
`routing_strategy: "plane_preferred"`, and the rule as implemented never
reads it. The fix is to make `core/design_rules.py`'s `GND` entry agree with
that declaration and make the eligibility check recognize the `preferred`
tier, not to invent a bespoke exception.

### Problem Frame

R7 replaces committed, hand-authored zones with zones regenerated from the
routed result. Measured: the committed board carries 96 zones; regeneration
today produces 10 (`ac_l`, `ac_n`, `DC_BUS_RTN`, `SW_NODE`, `+170V_BUS`, 2
layers each). The 86 zones that disappear belong to `Power`
(`+3V3` ×34, `vcc` ×24, `+15V` ×8, `+15V_LS` ×4, `V_BUS_SENSE` ×6) and
`GateDrive` (`GATE_LS` ×4, `GATE_HS`/`PWM_HS`/`PWM_LS` ×2 each) — every one of
these zone counts matches, hull-for-hull, the per-net cluster counts
`docs/evidence/2026-07-28-pour-strategy-audit.md` Task 1 measured
independently (17 `+3V3` hulls ×2 = 34, 12 `vcc` hulls ×2 = 24, 4 `+15V`
hulls ×2 = 8, and so on) — the audit and this measurement describe the same
board.

`_zone_layers_for_net()`'s own docstring records the change as fixing a
drifted, hardcoded 5-class list (`GND`, `Power`, `GateDrive`, `HighVoltage`,
`ACMains`) to instead read `NetClassRules.routing_strategy` from
`core/design_rules.py`. Only `ACMains`/`HighVoltage` set that field there;
`Power` and `GateDrive` leave it at the dataclass default, `None`
(`netclass_rules_gen.py:71`); `GND` does too. The docstring cites the
audit's Task 0 as the fix's basis — but Task 0 only diagnoses that the
hardcoded list and the declared field disagreed. It does not, by itself,
say what should happen to `GND`; that question sits in the audit's Task 1
and Task 3, and those two sections of the same document disagree with each
other (see Key Decisions).

### Key Decisions

- **KD1. `Power`/`GateDrive` route as traces by default; this is a
  deliberate decision, corroborated three independent ways, not an accident
  of the SSOT fix.** Governs R1, R2.
- **KD2. `GND` losing its pour is the accident the SSOT fix was not
  supposed to produce.** A second, human-authored config already declares
  `GND` should prefer a plane; the implemented fix reads a different file
  that never says so. Governs R3, R4, R5.
- **KD3. `plane_required` and `plane_preferred` are not the same claim, and
  today's eligibility check collapses them to one.** The field has four
  documented values; only one is consulted. Governs R4.
- **KD4. `SW_NODE`'s oversized, board-spanning pour is a pre-existing,
  already-diagnosed defect this rule change must not silently re-adopt as
  fixed.** It lives in `zone_emission.py`'s clustering behavior, not in
  `_zone_layers_for_net`'s eligibility check. Governs R6.
- **KD5. Nothing today observes a pour-eligibility regression by net
  class.** One blunt gate would catch the *aggregate* zone-count change;
  nothing checks the per-class policy itself. Governs R7.

### Requirements

**Class-level baseline (Power, GateDrive — confirmed correct)**

- R1. No net in `Power` or `GateDrive` gets a default pour: `+3V3`, `vcc`,
  `+15V`, `+15V_LS`, `V_BUS_SENSE`, `GATE_HS`, `GATE_LS`, `PWM_HS`, `PWM_LS`
  route as traces only. Three independent sources agree for every one of
  these nine nets: `docs/hardware/TRACE_WIDTH_CALCULATIONS.md` §3.4/3.6-3.8
  gives each a trace-width spec with local decoupling, never a pour spec;
  `packages/temper-placer/configs/temper_constraints.yaml:313,333`
  explicitly declares `Power`/`GateDrive` `routing_strategy: "wide_trace"`
  (a human-authored config `_zone_layers_for_net` does not even read);
  and `docs/evidence/2026-07-28-pour-strategy-audit.md` Task 1 independently
  reaches DELETE for all nine after checking actual current budgets.
- R2. `_zone_layers_for_net()` continues to key eligibility off
  `NetClassRules.routing_strategy` rather than a hardcoded net-class list,
  per the 2026-07-28 fix already landed — this requirement is confirmatory,
  not new.

**GND correction (the gap)**

- R3. `core/design_rules.py`'s `GND` entry in `TEMPER_NET_CLASSES` sets
  `routing_strategy="plane_preferred"`, matching what
  `packages/temper-placer/configs/temper_constraints.yaml:315-323` already
  declares for `GND` (`max_current_rating: 5.0  # ground return`,
  `routing_strategy: "plane_preferred"`) and what
  `docs/evidence/2026-07-28-pour-strategy-audit.md` Task 1 independently
  concluded for `PWR_RTN` specifically (KEEP the copper, shrink the area,
  relocate to an inner layer — never DELETE). Today `core/design_rules.py`'s
  `GND` entry leaves `routing_strategy` at the Python default `None`
  (`netclass_rules_gen.py:71`), silently disagreeing with the config file
  that already states an opinion.
- R4. `_zone_layers_for_net()`'s eligibility check recognizes both
  `"plane_required"` and `"plane_preferred"`, not only the former. The field
  has four documented values (`plane_required`, `plane_preferred`,
  `wide_trace`, `standard` — comment at `netclass_rules_gen.py:70`) but the
  code branches on exactly one string literal; the other three are
  currently decorative.
- R5. This correction changes emitted copper for exactly one net in
  practice: `PWR_RTN`. `GND`'s only other member, `CGND`, carries zero
  committed zones on the board today regardless — the audit's Task 1
  14-net/96-zone accounting does not include it — so recognizing
  `plane_preferred` for the whole `GND` class is not a broad new grant of
  copper; it is the single correction the evidence calls for.

**Known residual defect (flagged, not fixed here)**

- R6. `SW_NODE` (already `HighVoltage`/`plane_required`) must not receive
  the same full clustered convex-hull zone `DC_BUS_RTN` receives.
  `docs/evidence/2026-07-28-pour-strategy-audit.md` Task 1 found `SW_NODE`'s
  existing hull covers 40% of board area because `HighVoltage` is
  clustering-exempt and the router used the zone as a cross-pad stitch
  rather than a power pour — the opposite of
  `docs/hardware/TRACE_WIDTH_CALCULATIONS.md` §3.2's own instruction to
  "keep switch node AREA minimal (EMI source)." This is a
  `zone_emission.py` clustering defect, independent of the `Power`/`GND`
  eligibility question this artifact resolves, and R3/R4 must not be read
  as having fixed it — the audit's own Task 3 recommendation #4 (a small,
  direct pour at the IGBT-output-to-tank connection only) remains open.

**Observability**

- R7. Pour eligibility per net class is asserted by an explicit test that
  fails by name when a specific class's eligibility changes. Today, unit
  tests assert `GateDrive` nets are zone-eligible
  (`tests/router_v6/test_adapter.py:109-143`,
  `TestZoneLayersForNet`) but no equivalent test exists for `Power`; a
  regression silently dropping `"Power"` from an eligibility list would
  pass every unit test. Separately,
  `tests/placer/cp_sat/test_regression_drc.py`'s
  `PRODUCTION_BOARD_BASELINE_SHAPE` (`zones: 96`) would catch the
  *aggregate* 96→10 change, but only as a blunt shape assertion requiring a
  baseline number update — it does not name which net class changed or why,
  and a developer updating the baseline to land R3-R6 would not be
  prompted to re-examine the per-class policy.

### Acceptance Examples

- AE1. Power/GateDrive stay trace-only.
  - **Covers R1.**
  - **Given:** A full regeneration run on the current board.
  - **When:** Zones are derived from the routed result.
  - **Then:** None of `+3V3`, `vcc`, `+15V`, `+15V_LS`, `V_BUS_SENSE`,
    `GATE_HS`, `GATE_LS`, `PWM_HS`, `PWM_LS` has an emitted zone.

- AE2. GND's pour is restored for the net that needs it.
  - **Covers R3, R4, R5.**
  - **Given:** `GND`'s `routing_strategy` is `"plane_preferred"` and the
    eligibility check recognizes that tier.
  - **When:** Zones are derived from the routed result.
  - **Then:** `PWR_RTN` has an emitted zone on `F.Cu`/`B.Cu`; `CGND` does
    not gain one it didn't already have.

- AE3. SW_NODE's defect is not silently declared fixed.
  - **Covers R6.**
  - **Given:** `SW_NODE` remains `HighVoltage`/`plane_required` after this
    change.
  - **When:** Zones are derived from the routed result.
  - **Then:** `SW_NODE`'s emitted zone area is unchanged by R3/R4 (still
    the pre-existing oversized hull) — this artifact's changes do not touch
    it, and the backlog item from the audit's Task 3 #4 stays open.

- AE4. A future eligibility regression is caught by name.
  - **Covers R7.**
  - **Given:** A future change reintroduces a hardcoded list, or otherwise
    removes `Power`/`GateDrive`/`GND` from eligibility incorrectly (or adds
    them incorrectly).
  - **When:** The new per-class test suite runs.
  - **Then:** It fails naming the specific net class and expected vs. actual
    eligibility, not just an aggregate zone count.

### Scope Boundaries

**Deferred for later**

- Inner-layer (`In1.Cu`/`In2.Cu`) stackup and plane architecture — `U2`/`R8`
  of the provable-safety plan; this artifact only decides outer-layer
  (`F.Cu`/`B.Cu`) eligibility, which is all `_zone_layers_for_net()`
  currently emits.
- Zone geometry/margin sizing for `PWR_RTN`, `DC_BUS_RTN`, `ac_l`, `ac_n` —
  the audit's own "shrink" recommendation (current areas are 5-14× larger
  than `TRACE_WIDTH_CALCULATIONS.md`'s pour spec implies) is unresolved and
  is a `zone_emission.py` sizing question, not an eligibility question.
- `SW_NODE`'s clustering-exemption defect (R6) — flagged, not fixed, here.
- Consolidating `core/design_rules.py`'s `TEMPER_NET_CLASSES` and
  `packages/temper-placer/configs/temper_constraints.yaml` into one SSOT.
  The two files disagree on more than `routing_strategy` alone (e.g. `GND`
  clearance: `0.3` in the former, `0.2mm` in the latter) — R3 corrects the
  one disagreement load-bearing for this decision without resolving the
  general duplication risk.

**Outside this artifact's identity**

- Rewriting `zone_emission.py`'s clustering algorithm in general — R6 only
  requires that whatever change lands for R3/R4 does not get credited with
  also having fixed `SW_NODE`.

### Dependencies and Assumptions

- Assumes `CGND` carries no current/EMI justification for a pour distinct
  from `PWR_RTN`'s. Not independently re-audited net-by-net in this pass;
  the audit's Task 1 never analyzed `CGND` at all (it has no committed
  zones today), so there is no per-net verdict to overturn. Safer default
  on a mains board: R3/R4's `GND`-class correction changes real emitted
  copper for `PWR_RTN` only, and `CGND` is not granted anything new by
  construction (R5) rather than by a separate judgment call about its
  current budget.
- Assumes `PWR_RTN`'s `GND`-netclass `safety_category="LV"`
  (`core/design_rules.py:372-382`) is itself a separate, likely-stale
  classification, given `elec/domain_manifest.yaml:71-72` declares
  `PWR_RTN` a member of the `HV` domain (alongside `DC_BUS_RTN`, on the
  same doubler-midpoint node). This artifact does not fix that
  classification — it is a DRC/domain-separation question, not a
  pour-eligibility one — but it is additional, independent corroboration
  that `PWR_RTN` was never meant to be treated like a low-current logic
  ground, reinforcing R3 rather than depending on it.
- Treats `docs/evidence/2026-07-28-pour-strategy-audit.md` Task 1's
  per-net current-budget analysis as authoritative for `Power`/`GateDrive`;
  this document re-derives none of that arithmetic, only cites it.

### Outstanding Questions

**Resolve Before Planning**

- None. R3-R5 fully resolve the `GND` question from evidence already in the
  repo (two SSOTs, one audit) without requiring new measurement.

**Deferred to Planning**

- Whether `PWR_RTN`'s regenerated pour, once restored by R3/R4, should also
  be resized/relocated at the same time (the audit's "shrink to an inner
  layer" recommendation) or land first at whatever size the existing
  `zone_emission.py` clustering produces, with sizing as a fast-follow.
- Whether `PWR_RTN`'s `safety_category` mismatch (LV declared vs. HV
  domain-manifest membership) should be fixed in the same change or
  ticketed separately — this artifact takes no position beyond flagging it.
- Whether `routing_strategy` should become a `Literal` type (matching
  `safety_category`'s existing `Literal["HV","LV","AC","iso"] | None` at
  `netclass_rules_gen.py:68`) now that R4 makes a second value
  load-bearing, or whether string comparison remains adequate.

### Sources

- `docs/plans/2026-07-28-001-feat-provable-safety-place-and-route-plan.md`
  — R7/R8, KD3, U3 (this artifact resolves a sub-question of that plan).
- `docs/evidence/2026-07-28-pour-strategy-audit.md` — Task 0 (SSOT-drift
  root cause), Task 1 (per-net verdicts, including `PWR_RTN` KEEP and
  `SW_NODE` DELETE-then-replace), Task 3 recommendation #5 (the text the
  landed fix implements) and #4 (`SW_NODE`'s unresolved fix).
- `packages/temper-placer/src/temper_placer/router_v6/_adapter_convert.py`
  — `_zone_layers_for_net()` (eligibility check) and its docstring citing
  the 2026-07-28 fix.
- `packages/temper-placer/src/temper_placer/core/design_rules.py:310-382`
  — `TEMPER_NET_CLASSES`, the SSOT `_zone_layers_for_net()` reads.
- `packages/temper-placer/src/temper_placer/core/netclass_rules_gen.py:58-71`
  — `NetClassRules` field definitions; `routing_strategy`'s four documented
  values vs. its unenforced `str | None` type.
- `packages/temper-placer/configs/temper_constraints.yaml:280-366` — the
  second, human-authored net-class config; `GND`'s `"plane_preferred"`
  declaration at lines 315-323 is the crux evidence for R3.
- `docs/hardware/TRACE_WIDTH_CALCULATIONS.md` §3.2 (switch node), §3.4
  (gate drive), §3.6-3.8 (5V/3.3V/15V) — REQ-ELEC-02, the authoritative
  current/width table.
- `docs/specs/NET_CLASS_SPECIFICATION.md` §3.2-3.4 — REQ-ELEC-01, agrees
  `Power`/`GateDrive` are trace classes; note its `GND` entry is folded
  under `Power` and predates the star-point removal, so it is not cited for
  `GND`'s own treatment.
- `elec/domain_manifest.yaml:71-72` — `PWR_RTN`'s `HV`-domain membership.
- `tests/router_v6/test_adapter.py:109-143` (`TestZoneLayersForNet`) and
  `tests/placer/cp_sat/test_regression_drc.py`
  (`PRODUCTION_BOARD_BASELINE_SHAPE`) — existing partial observability,
  and the gap R7 closes.
- `docs/evidence/2026-07-28-zone-pour-differential-verdict.md` — a
  related, distinct finding that `enable_zone_pours` duplicating
  already-committed zones does not improve `unconnected_items`; cited as
  context that pour presence/absence on this board has been measured
  before and found not to move routing completion either way (matching the
  audit's own Task 2 falsifier result).
