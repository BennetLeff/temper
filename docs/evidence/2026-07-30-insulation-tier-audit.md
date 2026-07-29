<!-- provenance: branch docs/insulation-tier-audit, from origin/main at bd352015 -->

# Insulation tier audit: is `BASIC` vs `REINFORCED` correctly assigned in `IEC60335_REQUIREMENTS`?

## Verdict, up front

**Every tier in `IEC60335_REQUIREMENTS` is correctly assigned. No correction
is made in this change.** The two rows that matter for this question —
`(MAINS, LV_CONTROL, REINFORCED)` and `(DC_BUS, LV_CONTROL, REINFORCED)` —
are both genuinely REINFORCED, not BASIC, because `LV_CONTROL` (this
validator's name for the manifest's `SELV` domain) is (a) operator-accessible
— a food-contact RTD probe and a full panel of user controls (encoder/knob,
power button, start/stop button) are wired directly onto it — and (b) its
bond to protective earth is a SELV-domain noise-reference decision on
ordinary PCB copper, not a certified, continuity-tested protective-earth
conductor of the kind IEC 60335-1's Class I basic-insulation-plus-earthing
exception actually requires. Neither condition that would license BASIC
insulation for this boundary is met.

**`U3` and `U7` both straddle `(DC_BUS, LV_CONTROL, REINFORCED)`** — the
10.0mm-creepage row, not a 5.0mm one. **The blocker does not dissolve.**
`U3` (8.560mm, best achievable on a resourceable lead-form) and `U7`
(8.100mm, best achievable on TI's own published land pattern) both still
fall short of 10.0mm even after their known footprint/lead-form fixes are
applied. `C6`, `K2`, and `K3` sit on the identical boundary and tier.

Violation count: **unchanged, 98** (52 pairs, 13 intra-footprint), because
no value in the matrix changed. Reproduced on this branch before writing
this document (see §6).

This is the outcome the task's own framing warned would be the
disappointing one to report. It is reported anyway, for the reasons in §2.

---

## 1. What "tier" question this validator is actually answering, and for which rows

`IEC60335_REQUIREMENTS` (`packages/temper-placer/src/temper_placer/requirements/validators/clearance.py`)
has six rows:

| # | `(domain_a, domain_b, insulation_type)` | Populated on the real board? |
|---|---|---|
| 1 | `(MAINS, LV_CONTROL, BASIC)` | Yes (via the reinforced row's same pairs; see §4) |
| 2 | `(MAINS, LV_CONTROL, REINFORCED)` | Yes, but `MAINS` (`ac_l`/`ac_n` only, per `_real_board_fixture.py`) never actually pairs with `LV_CONTROL` in a violation on this board — every real violation below is DC_BUS-side |
| 3 | `(DC_BUS, LV_CONTROL, BASIC)` | Yes — same pairs as row 4, reported as a second, redundant record when a pair fails both floors |
| 4 | `(DC_BUS, LV_CONTROL, REINFORCED)` | Yes — this is the row every one of the board's 98 violations, including all five problem isolators, actually comes from |
| 5 | `(MAINS, ISOLATED, REINFORCED)` | No — `VoltageDomain.ISOLATED` is never populated by `_real_board_fixture.py` (documented gap, not a silent one; see its own module docstring) |
| 6 | `(LV_CONTROL, LV_CONTROL, FUNCTIONAL)` | Yes, but this is a within-domain floor, not a shock-hazard boundary |

So the question this audit actually has to answer is narrower than "six
tiers": it is "is `LV_CONTROL`'s boundary against a hazardous-voltage domain
(`MAINS` or `DC_BUS`) genuinely REINFORCED, or could it legitimately be
BASIC" — because that is the one question every real violation on the board,
and both U3 and U7 specifically, depends on. Rows 5 and 6 are addressed
separately in §5 for completeness, since the task asks about every entry.

---

## 2. The governing IEC 60335-1 question, and why it cuts toward REINFORCED here

IEC 60335-1's insulation-coordination scheme recognizes, in outline (Clause 8,
protection against access to live parts; Clause 3's insulation-type
definitions; Clause 29, clearances/creepage/solid insulation — primary text
is paywalled, not independently re-fetched in this pass, consistent with
every other creepage-related evidence doc in this repo's history, e.g.
`docs/evidence/2026-07-30-creepage-requirement-reconciliation.md` §7's
identical caveat):

- **BASIC insulation is sufficient between a hazardous-voltage circuit and a
  part that is separately protected another way** — the standard Class I
  construction is a hazardous circuit separated from an **earthed, accessible
  metal part** by basic insulation only, because a single insulation failure
  becomes a live-to-earth fault: fault current flows through a verified,
  low-impedance, adequately-rated protective-earth path and opens the
  branch protective device, so the metal part never sustains a hazardous
  potential for more than the disconnection time. This exception has to be
  **earned** — it requires an actual protective-earth conductor meeting the
  standard's own continuity/impedance construction, not merely "this net
  happens to be DC-bonded to PE somewhere."
- **REINFORCED (or double) insulation is required between a hazardous-voltage
  circuit and any other circuit — SELV or otherwise — that is (a) accessible
  to the user, and (b) not backed by that verified protective-earth
  exception.** This is the default for an isolated low-voltage control
  domain, and is exactly the category `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md`
  §2.1 already places "Low Voltage Control / Domain D" in ("Classification:
  SELV"), and the category `IEC60335_REQUIREMENTS`'s existing REINFORCED rows
  already assume.

**The determination is which of these two applies to `LV_CONTROL`, made
against this product's own architecture — not assumed either way.**

### 2.1 Is `LV_CONTROL` operator-accessible?

Yes, unambiguously, on multiple independent paths, all traced directly:

- **The RTD food probe.** `elec/domain_manifest.yaml`'s own comment block
  (the OVP-01 protective-impedance justification) explicitly calls this "a
  user-touchable RTD probe" sitting on `gnd`. `docs/hardware/IEC60335_CRITICAL_COMPONENTS.md`
  §2 independently confirms: `RTDSensing`'s own docstring
  (`elec/src/modules.ato:1259-1265`) asserts "the user-touchable RTD food
  probe is therefore separated from AC mains potential" — a claim about a
  part that is, by the design's own description, in the user's hand and in
  contact with food during normal use.
- **Physical user controls, per this product's own requirements.**
  `docs/specs/REQUIREMENTS.md` §6 (REQ-UI-01, "Physical Controls") lists an
  **Encoder** (rotary with push — temperature setpoint/menu), a **Power
  Button**, and a **Start/Stop** button, all panel-mount, vintage-styled
  ("Knobs should match RCA 12A3 era"). `docs/hardware/SAFETY_INTERLOCK_DESIGN.md`
  independently lists a panel-mount **Reset button** (`S1`, "Momentary, NO |
  1 | Panel mount"), wired to `RESET_N` — a net `elec/domain_manifest.yaml`
  declares under `SELV`. These are physical controls a user's hand touches
  every time the appliance is operated, wired directly onto the same
  `LV_CONTROL`/`gnd` domain the RTD probe sits on.

`LV_CONTROL` is not an internal-only reference plane; it is directly wired to
parts the user touches by design, in normal use, not only under fault
conditions.

### 2.2 Is `LV_CONTROL`'s earth bond the kind that earns the BASIC exception?

No. `docs/hardware/SELV_ISOLATION_REDESIGN.md` §3 documents the actual
construction: `gnd ~ pe` is a **0Ω DC bond added to give the floated SELV
domain a stable noise reference** (explicitly reasoned through as an EMI/
stability decision — "a floated SELV domain with no defined reference is not
safe either — it capacitively couples to nearby HV nodes and drifts with
EMI"), not as a Class I protective-earthing scheme for this boundary. Three
facts distinguish it from the exception BASIC insulation actually requires:

1. **It is ordinary signal-reference PCB copper, not a protective-earth
   conductor.** IEC 60335-1's Class I exception is normally evidenced by an
   **earth-continuity/bonding-impedance test on the actual earthing path
   to accessible metal** — and this product's own test plan
   (`docs/specs/REQUIREMENTS.md` §4, "Ground Continuity: Measure resistance
   from PE to all exposed metal (<0.1Ω)") applies that test to **exposed
   metal**, not to the internal `gnd` net `LV_CONTROL` copper sits on. No
   document anywhere in this repo claims or verifies that `gnd`'s trace/via
   construction is sized or rated to safely carry and clear a full
   DC-bus-to-LV_CONTROL prospective fault current the way an appliance's
   protective-earth conductor to its chassis is required to.
2. **The one place this repo already applies "PE-bonded ⇒ basic/protective-impedance is
   legitimate" reasoning is a narrower, different provision, not a license to
   relax the general boundary.** `elec/domain_manifest.yaml`'s
   `protective_impedance_chains` (the OVP-01 comparator/ADC dividers) invoke
   exactly this argument — but only for two specific, **engineered,
   redundant, current-limited** resistor chains, each independently verified
   to keep touch current under the applicable limit even under a double
   fault. That is IEC 60335-1's recognized **protective-impedance
   alternative to insulation** for a deliberate bridging connection — a
   different clause from "what creepage/clearance does this domain pair need
   everywhere else on the board." `U3`, `U7`, `C6`, `K2`, `K3` have no such
   engineered current limiting; a creepage/clearance shortfall at any of them
   is an uncontrolled arc/tracking/dust-bridging path capable of putting the
   **full, unlimited** DC-bus potential directly onto `LV_CONTROL` copper —
   the RTD probe and every panel control included — with nothing standing
   between the fault and the user. The manifest's own reasoning for the
   protective-impedance chains does not extend to this case, and nothing else
   in this repo claims it does.
3. **The design's own trajectory treats this boundary as a true isolation
   barrier requiring a certified isolator, not as Class I earthing.**
   `docs/hardware/SELV_ISOLATION_REDESIGN.md` exists specifically to *remove*
   an accidental short of the aux-supply's 4.2kVAC-rated isolation barrier
   and replace a raw resistive ZCD path with a real optocoupler — i.e. the
   whole redesign's premise is that `LV_CONTROL` must be genuinely,
   galvanically separated from HV by certified isolation devices (the
   Mean Well IRM-10-15, the H11L1 opto, the UCC21550 gate driver), each rated
   for reinforced isolation on its own datasheet. A design built around
   maintaining a floating, transformer/opto-isolated domain is not,
   simultaneously, a design that intends to rely on Class I basic-insulation
   earthing for the same boundary — those are two different protective
   strategies, and this product has already committed to the first one.

**Conclusion: neither element of the BASIC exception is earned.**
`LV_CONTROL` is operator-accessible and its PE bond is a stability/reference
decision, not a verified protective-earth path built and tested to the
standard the exception requires. REINFORCED is the correct tier for
`(MAINS, LV_CONTROL)` and `(DC_BUS, LV_CONTROL)`, exactly as currently coded.

---

## 3. Which `(domain_a, domain_b)` pair each of the five problem isolators actually straddles

Traced directly from `elec/domain_manifest.yaml`'s `isolators:` pin-group
declarations, cross-checked against `_real_board_fixture.py`'s domain-mapping
rule (`ac_l`/`ac_n` → `MAINS`; every other declared `HV` net → `DC_BUS`;
every declared `SELV` net → `LV_CONTROL`), and confirmed against this
session's own live test run (§6) rather than assumed:

| Ref | HV-side pin(s) / net(s) | SELV-side pin(s) / net(s) | Resolved pair | Confirmed in live violation report |
|---|---|---|---|---|
| `U3` (H11L1 opto, `power_in.zcd_opto`) | pins 1,2 (A, K) on `a` / `PWR_RTN` — neither is `ac_l`/`ac_n` | pins 4,5,6 (VO, GND, VCC) on `ZCD_ISO` / `gnd` / `+3V3` | **`DC_BUS <-> LV_CONTROL`** | `U3 (intra) DC_BUS<->LV_CONTROL reinforced creepage 6.020 10.0 3.980` |
| `U7` (UCC21550, `hb.gate_hs.driver`) | secondary pins 9,10,11,14,15,16 on `DC_BUS_RTN`/`SW_NODE`/`GATE_HS`/`GATE_LS`-family nets — none is `ac_l`/`ac_n` | primary pins (GNDI etc.) on `gnd`/`PWM_HS`/`PWM_LS` | **`DC_BUS <-> LV_CONTROL`** | `U7 (intra) DC_BUS<->LV_CONTROL reinforced creepage 7.250 10.0 2.750` |
| `C6` (Y1 cap, `power_in.y_cap_pe`) | pin 1 on `PWR_RTN` | pin 2 on `pe` (merged into `gnd`) | **`DC_BUS <-> LV_CONTROL`** | `C6 (intra) DC_BUS<->LV_CONTROL reinforced creepage 3.200 10.0 6.800` |
| `K2` (`discharge.k_dis1`) | contacts on `PWR_RTN`/HV bus nets | coil on `discharge.k_dis1-coil1/2` (`SELV`) | **`DC_BUS <-> LV_CONTROL`** | `K2 (intra) DC_BUS<->LV_CONTROL reinforced creepage 3.559 10.0 6.441` |
| `K3` (`discharge.k_dis2`) | contacts on `DC_BUS_RTN`/HV bus nets | coil on `discharge.k_dis1-coil2`/`discharge.k_dis2-coil1` (`SELV`) | **`DC_BUS <-> LV_CONTROL`** | `K3 (intra) DC_BUS<->LV_CONTROL reinforced creepage 3.559 10.0 6.441` |

**All five sit on the identical `(DC_BUS, LV_CONTROL, REINFORCED)` row — none
is on `(MAINS, LV_CONTROL, ...)`.** Every HV-side net any of them touches is
a declared `HV` net other than the literal `ac_l`/`ac_n` pair (the doubler
midpoint, the switch node, the floating gate-drive rails, etc.), which this
project's own domain classification (justified in
`docs/evidence/2026-07-30-creepage-requirement-reconciliation.md` §1) buckets
into `DC_BUS` precisely because a single clearance/creepage figure must
protect against whichever member of that HV bucket sits nearest, not just the
lowest-potential one.

**U3 and U7 specifically, at the board's actual current footprints, measure
6.020mm and 7.250mm** — worse than the 8.560mm/8.100mm figures in the
sourcing brief, because the board (`pcb/temper.kicad_pcb`, read-only here)
has not yet been resynced to the already-corrected library footprints
(per `docs/brainstorms/2026-07-30-isolator-component-sourcing.md` §2-3). That
resync is a separate, already-identified task. It would not fix this
finding either way: even at the best achievable 8.560mm/8.100mm, both parts
remain short of the 10.0mm REINFORCED requirement established in §2.

---

## 4. Do rows 1/3 (the BASIC rows for the same domain pairs) need to be removed?

No — they are redundant, not wrong. `verify_iec60335_compliance` runs every
row in the matrix independently; for a domain pair that also has a
REINFORCED row, the BASIC row can only ever flag a pair that is *already*
flagged (more severely) by the REINFORCED row at the same domain pair (a
pair passing the 5.0mm/3.0mm BASIC floor but failing 10.0mm/6.0mm REINFORCED
produces one violation record, from REINFORCED only; a pair failing both
floors produces two records for the same pair, one per row — visible in
§6's raw output, e.g. `C22<->U15` reported once as `reinforced` and once as
`basic`). Since §2 establishes REINFORCED is what this boundary actually
requires, the BASIC rows never represent a legitimate lower bar a pair could
satisfy instead — they are conservative, duplicate reporting, not an unsafe
gap. Leaving them in place does not hide anything a fix would need to
address; removing them is out of scope for a tier-correctness audit (no
pass/fail outcome changes either way) and is not done here.

---

## 5. The remaining two rows, for completeness

- **`(MAINS, ISOLATED, REINFORCED)`.** `VoltageDomain.ISOLATED` is meant for
  a genuinely floating conductor at unknown potential (per the enum's own
  "Floating" docstring) that is neither `LV_CONTROL` nor part of the earthed
  `SELV` domain. A floating node has, by definition, no protective-earth
  reference at all, so it cannot qualify for the BASIC exception under any
  reading of §2 — REINFORCED is the only tier that could apply here, and it
  is what is coded. This row is currently unpopulated on the real board
  (`_real_board_fixture.py`'s own docstring already documents this as an
  honest, open coverage gap, not something this task's scope covers), so it
  contributes nothing to the violation count either way; no correction is
  warranted or made.
- **`(LV_CONTROL, LV_CONTROL, FUNCTIONAL)`.** This is a within-domain floor,
  not a hazardous-voltage boundary — both sides of every pair it checks are
  already SELV, so there is no shock-hazard case for BASIC or REINFORCED to
  even apply to. FUNCTIONAL is the correct classification. (Its specific
  1.0mm/2.0mm values predate and sit below Table 16's own 50V floor — an
  existing, separately-flagged, out-of-scope observation from
  `docs/evidence/2026-07-30-creepage-requirement-reconciliation.md` §3, not a
  tier-correctness question and not touched here.)

---

## 6. Reproduction: violation count before and after this audit

**No value in `IEC60335_REQUIREMENTS` was changed by this document**, so
there is no "after" distinct from "before" — both are the same measured
state, reproduced fresh on this branch rather than assumed carried over from
PR #442:

```
git fetch origin && git checkout -b docs/insulation-tier-audit origin/main
uv sync --all-packages
make netlist   # elec/build/ is gitignored; the test skips without this
uv run --no-sync pytest packages/temper-placer/tests/requirements/safety/test_clearance.py::TestClearanceIntegration::test_temper_board_clearance_compliance -q
```

Result:

| | Before this audit (PR #442's post-fix state) | After this audit |
|---|---|---|
| REQ-SAFE-01 violations | 98 | **98 (unchanged)** |
| Violating pairs | 52 | **52 (unchanged)** |
| Intra-footprint records | 13 | **13 (unchanged)**, includes `C6`, `K2`, `K3`, `U3`, `U7` |
| Components matched | 158 | **158 (unchanged)** |

Full suite touched by this class of change, re-run on this branch:

```
uv run --no-sync pytest packages/temper-placer/tests/requirements/safety/ \
  packages/temper-placer/tests/placer/cp_sat/test_domain_clearance.py \
  packages/temper-placer/tests/requirements/validators/ -q
# 1 failed (test_temper_board_clearance_compliance, expected -- unmodified), 101 passed
```

Identical to the count PR #442 already reported as its own "after." This is
the expected, correct outcome of an audit that concludes no value needs to
change — not evidence the audit was skipped. `test_temper_board_clearance_compliance`
was not modified in any way.

---

## 7. A related, unresolved, explicitly out-of-scope tension found while reading history

Several now-orphaned branches in this repository's history
(`fix/pd3-retarget-u3-u7-slots`, `pd3-retarget-keepout`, `pd3-retarget-relay`,
none an ancestor of `origin/main` at the commit this audit branched from —
verified via `git merge-base --is-ancestor`) contain a separate, prior
determination that this appliance's true pollution degree is **PD3**, not the
**PD2** `docs/ENVIRONMENTAL_SPEC.md` §3.1 and `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md`
§3.2 both currently state (`docs/solutions/best-practices/check-the-exception-before-the-default-2026-07-28.md`).
If correct, PD3 would raise the REINFORCED creepage figure this document
treats as 10.0mm to **12.6mm** (a governing-row question, the same axis PR
#442 already audited for voltage — not a tier/BASIC-vs-REINFORCED question,
which is this document's scope). That branch line was never merged to
`main` and is not reflected in `scripts/check_isolation_keepout.py` (still
`MIN_BARRIER_WIDTH_MM = 8.0`, PD2) or anywhere in the current
`IEC60335_REQUIREMENTS` matrix. **Not evaluated or acted on in this
document** — it is a different axis of the same standard's requirement,
already the subject of its own (unmerged) investigation, and reconciling it
is out of this task's scope (tier, not pollution degree). Flagged here only
so whoever next touches this matrix's voltage row knows the PD2 assumption
itself has an open, unmerged challenge on record, separate from and
unaffected by this tier audit's conclusion.

---

## 8. Hard-constraint compliance

- `pcb/**` and `elec/src/**`: not modified (read-only, verified via
  `git status` before writing this document).
- `packages/temper-placer/src/temper_placer/requirements/validators/clearance.py`:
  **not modified** — every tier verdict in §2/§5 concluded the existing
  assignment is already correct; there is nothing to correct.
- `test_temper_board_clearance_compliance`: not modified, still fails with
  the same 98 real violations as before this document — not softened,
  skipped, or reasoned away.
- No skip/xfail/deletion/assertion-weakening, no `continue-on-error`, no
  `git stash` used anywhere in this session.
- Every tier verdict above cites either a product fact traced directly to
  `elec/domain_manifest.yaml`/`elec/src/*.ato`/`docs/specs/REQUIREMENTS.md`/
  `docs/hardware/SAFETY_INTERLOCK_DESIGN.md`/`docs/hardware/SELV_ISOLATION_REDESIGN.md`/
  `docs/hardware/IEC60335_CRITICAL_COMPONENTS.md`, or a standard concept
  already established and cited elsewhere in this repo's own prior
  (paywalled-primary-text-caveated) creepage work — none invented for this
  pass.

## Sources

- `packages/temper-placer/src/temper_placer/requirements/validators/clearance.py`
  — `IEC60335_REQUIREMENTS`, `VoltageDomain`, `InsulationType`.
- `packages/temper-placer/tests/requirements/safety/_real_board_fixture.py`
  — the `HV`/`SELV` → `MAINS`/`DC_BUS`/`LV_CONTROL` domain-mapping rule.
- `elec/domain_manifest.yaml` — isolator pin-group declarations for `U3`/`U7`/
  `C6`/`K2`/`K3`; the `protective_impedance_chains` reasoning distinguished
  from the general boundary question in §2.2.
- `docs/hardware/SELV_ISOLATION_REDESIGN.md` §3-4 — the `gnd ~ pe` bond's
  actual purpose (SELV reference stability, not Class I earthing), and the
  crossing survey confirming the design's isolation-device-based strategy.
- `docs/hardware/IEC60335_CRITICAL_COMPONENTS.md` §2 — the RTD probe
  accessibility finding, independently confirming `domain_manifest.yaml`'s
  own comment.
- `docs/specs/REQUIREMENTS.md` §4 (REQ-SAFE test plan, ground-continuity
  scope), §6 (REQ-UI-01, physical controls).
- `docs/hardware/SAFETY_INTERLOCK_DESIGN.md` — the panel-mount reset button
  on `RESET_N` (`SELV`).
- `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` §2.1, §5.1-5.2 — Domain D's
  SELV classification; the Table 16 creepage figures this audit does not
  change.
- `docs/evidence/2026-07-30-creepage-requirement-reconciliation.md` — the
  voltage-row audit this tier audit is the companion to; its own
  paywalled-primary-text caveat, reused identically here.
- `docs/brainstorms/2026-07-30-isolator-component-sourcing.md` — U3/U7's
  achievable footprint figures (8.560mm/8.100mm) and the board-resync gap
  that makes today's live measurement worse (6.020mm/7.250mm) than those
  figures.
- `docs/solutions/best-practices/check-the-exception-before-the-default-2026-07-28.md`,
  `docs/solutions/best-practices/sufficient-condition-infeasible-is-not-requirement-infeasible-2026-07-28.md`
  — the unmerged PD2/PD3 branch line, flagged in §7 as out of scope.
- `docs/solutions/best-practices/claimed-isolation-vs-actual-connectivity-2026-07-26.md`
  — independent confirmation of the RTD probe's user-touchable, food-contact
  status and the design's isolation-device-based (not earthing-based)
  protective strategy.
