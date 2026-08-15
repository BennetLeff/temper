<!-- provenance: commit=c47761757de8f62dc307c3bb79d1180ebe412ef3 dirty=false. This is a SYNTHESIS-AND-DETERMINATION document: no new measurement was taken, no pcb/** file was opened for writing, nothing under pcb/** was touched (git status --porcelain shows only this file). Every figure below is carried forward, with path:line or section citation, from documents already on `origin/main` at this commit: docs/evidence/2026-08-12-hv-hv-creepage-determination.md (c2b03fb23, PR #1081), docs/evidence/2026-08-12-hv-clearance-adequacy.md (9187aab62, PR #1080), docs/evidence/2026-08-12-hv-hv-creepage-enforcement.md (3231dc3db, PR #1084), docs/evidence/2026-08-12-tank-creepage-placement.md (ad8498f7d, PR #1089), docs/evidence/2026-08-11-pd2-decision-record.md (ae233f394, PR #1035), docs/evidence/2026-08-01-pd2-enclosure-legitimacy.md (ea194f965, PR #592), docs/evidence/2026-07-30-pcb-compartment-thermal-bound.md, docs/evidence/2026-07-28-conformal-coating-pd1.md (c2b03fb23 / 50df12f32, recovered from f8b5f43c235eb12cc3f4d7a9ecddc69d8b5a1d62), plus docs/CHASSIS_AIRFLOW_DESIGN.md, docs/COIL_BRACKET_DESIGN.md, docs/ENVIRONMENTAL_SPEC.md, docs/ASSEMBLY_GUIDE.md, docs/hardware/BOM.md, pcb/libs/lib.pretty/LitzPad_15A.kicad_mod, and scripts/generate_kicad_dru.py, all read first-hand this session at this commit. No standards citation in this document is stated from memory; every clause/table reference reproduces a citation already recovered and quoted verbatim in one of the cited evidence docs, with that doc's own citation preserved. -->

# PD3/10.0mm is what the standard's own condition requires today. The board's worst measured HV↔HV creepage is 2.2656mm — 4.4× short — and the cheapest fix is two geometry changes, one of them already solver-proven, neither coating nor the compartment.

**Verdict, up front.**

1. **Pollution degree: PD3.** IEC 60335-2-6 cl. 29.2's Addition makes PD3 the
   default microenvironment for a cooking appliance; PD2 is an exception that
   must be *earned* by a genuinely sealed, gasketed PCB compartment isolated
   from the coil/heatsink forced-air path (`docs/ENVIRONMENTAL_SPEC.md:45,
   49-66`). That compartment does not exist: no cover, gasket, partition, or
   inspection geometry is committed anywhere in this repository — board
   outline is a plain rectangle, `docs/specs/pd2_compartment_evidence.yaml`
   does not exist, and `scripts/check_pd2_compartment_evidence.py` fails today
   (`docs/evidence/2026-08-11-pd2-decision-record.md:174-197`). PD2 is the
   repo's **selected target**, not an earned classification. On the standard's
   own condition, **PD3 governs the as-built board now.**

2. **Required creepage at 570.5 Vrms: IEC 60335-1 Table 18** (functional
   insulation, cl. 29.2.4), band **>500 and ≤800 V**, material group
   IIIa/IIIb: **6.3mm at PD2, 10.0mm at PD3**
   (`docs/evidence/2026-08-12-hv-hv-creepage-determination.md:188-207`,
   quoted from IS 302-1:2008). **PD3 governs, so 10.0mm is the requirement.**
   This is already the exact pair of constants the repo's own DRU generator
   carries (`scripts/generate_kicad_dru.py:179-180`,
   `HV_TANK_CREEPAGE_PD2_MM = 6.3` / `HV_TANK_CREEPAGE_PD3_MM = 10.0`) — but
   line 210 sets `_TANK_POLLUTION_DEGREE = "PD2"`, so the repo is currently
   **enforcing the unearned target (6.3mm), not the standard's actual
   condition (10.0mm)**.

3. **The board does not meet either bar, measured, not estimated.** With the
   enforcement rule that now exists (`docs/evidence/2026-08-12-hv-hv-creepage-enforcement.md`,
   PR #1084, on `main`), kicad-cli reports two real HV↔HV creepage violations
   at the tank node, deterministic across 10 samples
   (`hv-hv-creepage-enforcement.md:252-264`):
   - **C25 pad 2 ↔ a routed track of `discharge.k_dis1-nc`: 2.2656mm actual.**
     Against 6.3mm (PD2): **2.8× short.** Against 10.0mm (PD3, governing):
     **4.4× short.**
   - **R30 pad 1 ↔ pad 2 (the coil's own two litz-wire terminals): 5.0mm
     actual.** Against 6.3mm: **1.26× short.** Against 10.0mm: **2.0× short.**
   These are tighter and more precise than the "2.0mm / 5×" figures the task
   brief quotes — that 2.0mm is the netclass *clearance* value used as a
   worst-case stand-in before this DRC rule existed
   (`docs/evidence/2026-08-12-hv-clearance-adequacy.md:270-317`); the real
   measured worst pair is 2.2656mm. Same conclusion, same direction, more
   precise number.

4. **Coating (PD1) is not the fix, and the reason is structural, not
   marginal.** IEC 60664-3 cl. 4.3 requires "one or both conductive parts,
   **together with all the spacings between them**, [to be] covered by the
   protection" for a path to earn PD1
   (`docs/evidence/2026-07-28-conformal-coating-pd1.md:38-52`, quoted
   verbatim). Applied to the board's two real violations:
   - **R30's own 5.0mm gap cannot get PD1 credit under any circumstances.**
     Both of R30's pads are the litz-wire termination points for the
     resonant coil itself — bare-metal, wire-attachment surfaces that must
     stay uncoated (`conformal-coating-pd1.md:552-556`, R30's two pads named
     explicitly in the masking inventory). Clause 4.3 requires at least one
     of the two conductive parts to be covered; here **neither** can be. PD1
     structurally does not reach this violation, at any coating quality,
     forever, by construction.
   - **C25's 2.2656mm gap is *plausibly* coatable but is unverified and the
     board-wide coverage survey never measured this specific pair.** C25 is
     a leaded axial capacitor (`temper:C_Axial_L34.0mm_D22.5mm_P40.00mm_Horizontal`)
     whose body sits raised off the board on leads — the same geometry the
     coating doc flags as "plausibly reaches under it" for `R1`
     (`conformal-coating-pd1.md:393-399`). If the C25↔track path is genuinely
     open-surface and 100% coating-covered, PD1's Table 18 figure at this
     band is **1.8mm** (row vi, PD1 column;
     `hv-hv-creepage-determination.md:195`), which the measured 2.2656mm
     already clears. But: no coverage measurement exists for this pair (the
     recovered survey covers only the eight declared HV↔SELV isolators, not
     this HV↔HV pair); no maximum PCB working-surface temperature is
     declared anywhere in the repo, which is the input that selects the
     qualification conditioning row (`conformal-coating-pd1.md:441-464`); and
     no coating of any kind appears in `docs/hardware/BOM.md` or
     `docs/ASSEMBLY_GUIDE.md` today (grepped both, zero hits).
   - **Net effect: even a perfectly-qualified coating leaves R30's 5.0mm
     violation standing.** This reproduces, at the tank node, the same
     structural finding the coating document already reached for the board's
     eight declared isolators: "a partial route… and it does not reach a
     single one of the isolation paths that are currently failing"
     (`conformal-coating-pd1.md:28-29`). Coating is not the cheapest path
     here because it cannot, even in principle, close one of the two known
     violations, and the qualification cost (a 6+ week test program per
     `conformal-coating-pd1.md:233-253`) is not small for the one violation
     it might reach.

5. **The airflow design and the sealed-compartment plan are not textually
   contradictory — both `docs/CHASSIS_AIRFLOW_DESIGN.md` §3.3 and
   `docs/ENVIRONMENTAL_SPEC.md` §3.1 explicitly require the barrier — but they
   are in real, quantified engineering tension that no document reconciles.**
   `docs/COIL_BRACKET_DESIGN.md` §4 specifies an **open-frame bracket with
   large triangular cutouts** that route bottom-intake kitchen air directly
   through the coil and onward to the IGBT heatsink, sitting in the same
   stack the PCB occupies, by design (`docs/COIL_BRACKET_DESIGN.md:44-46`:
   *"Large triangular cutouts around the central coil ring allow air from
   the bottom intake to flow directly through the Litz wire strands. The
   bracket itself acts as a baffle to direct air toward the IGBT heatsink
   after cooling the coil."*). That is not a seal; it is a baffle built to
   pass unfiltered air across the exact cavity a PCB compartment would need
   to be walled off from. Separately, and more decisively, the repo's own
   thermal analysis already asked "would a sealed PCB compartment overheat?"
   and answered **marginal**: at the appliance's own declared 55–70°C
   worst-case ambient band, the LMR51430 buck and (on an assumed θJA) the
   UCC21550 gate driver land at **zero to slightly negative margin** to their
   absolute maximum junction temperature specifically because sealing
   removes the airflow their existing thermal budget counts on
   (`docs/evidence/2026-07-30-pcb-compartment-thermal-bound.md:384-401`). **So
   the sealed compartment is not free: building it either requires
   mitigations that are not currently designed (conduction to chassis metal,
   more copper pour, component relocation, higher-emissivity finish — all
   named but none committed,** `pcb-compartment-thermal-bound.md:416-437`**),
   or it creates a new thermal failure the moment it is built.** That is the
   headline finding the task asked me to check for, stated at the precision
   the evidence supports: not a logical contradiction between two documents,
   but a real, already-quantified cost the PD2 decision has never priced in.

6. **Recommended path: fix the geometry. It is cheaper than every other
   option and one half of it is already solver-proven.** Ranked below.

---

## 1. Why PD3, not PD2 — the standard's own condition, checked against the repo

The chain is fully recovered and cited, not asserted:

- **IEC 60335-2-6 cl. 29.2 Addition** (the appliance's own particular
  standard): PD3 is the default microenvironment for cooking appliances;
  PD2 is earned only if the insulation "is enclosed or located so that it is
  unlikely to be exposed to pollution during normal use"
  (`docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md:3.2.1`, quoted in
  `docs/evidence/2026-08-01-pd2-enclosure-legitimacy.md:183-192`).
- **`docs/ENVIRONMENTAL_SPEC.md:49-66`** states the condition as five
  concrete release requirements — gasketed compartment, no duct path into
  it, no exposed insulation in the aerosol path, assembly/inspection
  criteria, documented review — and says plainly: **"Until those conditions
  are verified, the electrical design must be treated as PD3 and the 12.6mm
  reinforced-creepage fallback applies."** (That 12.6mm figure is stale —
  it predates the Aug-12 Table 18/functional-insulation correction that
  brought the reinforced-basic 8.0/12.6mm figures down to the
  functional-insulation 6.3/10.0mm figures for the tank node specifically;
  see §2 below. The *condition* — PD3 if unearned — is unchanged.)
- **The condition is unmet, verified against real repo state at this
  commit**, three ways: (a) no `docs/specs/pd2_compartment_evidence.yaml`
  exists (`ls` returns nothing); (b)
  `scripts/check_pd2_compartment_evidence.py` fails with exit 3 today,
  proven in `docs/evidence/2026-08-11-pd2-decision-record.md:174-197`; (c)
  the board's `Edge.Cuts` outline is a single plain rectangle with zero
  vent/compartment/keepout geometry
  (`docs/evidence/2026-08-01-pd2-enclosure-legitimacy.md:76-99`).
- **The owner's own decision record agrees with this reading.** "PD2/8.0mm
  is the target; the sealed compartment is a hard, unmet prerequisite... the
  board is PD3-governed as built, and any figure measured or reported
  against [the PD2] bar carries an unearned credit"
  (`docs/evidence/2026-08-11-pd2-decision-record.md:65-71`).

**PD3 is not a novel conclusion of this document — it is what every prior
determination on `main` already says, restated as the answer to the question
this task asked.**

---

## 2. Required creepage: Table 18, row vi, PD3 column = 10.0mm

`docs/evidence/2026-08-12-hv-hv-creepage-determination.md` recovers clause
29.2.4 and Table 18 from primary text (IS 302-1:2008, the BIS identical
adoption of IEC 60335-1) and settles the table question directly: functional
insulation (the correct classification for this same-domain HV↔HV pair,
`hv-hv-creepage-determination.md:319-350`) takes Table 18, not Table 17. At
the working voltage measured for this board (570.5 Vrms,
`docs/evidence/2026-08-12-hv-clearance-adequacy.md` §2.3, ngspice-42,
worst OCP-01-passing corner), **Table 18's >500–800 V band is
row-for-row identical to Table 17's** — the functional-insulation concession
exists only below 500 V, and this node sits 14% above that cliff
(`hv-hv-creepage-determination.md:248-268`). So:

| | PD2 | PD3 |
|---|---:|---:|
| Table 18, row vi (>500–800 V), material group IIIa/IIIb | **6.3mm** | **10.0mm** |

**PD3 governs (§1) → the required creepage is 10.0mm.**

The 29.2.4 short-circuit-test exemption (clause 19, functional insulation
short-circuited) is available in principle but unearned: no clause-19
fault-injection test exists anywhere in this repository, the terminating
component (mains fuse F1) has no I²t characterization
(`elec/src/modules.ato:665-673`) and its holder footprint is still a stub
that doesn't match the real part's drilling diagram
(`docs/hardware/BOM.md:77`), and the standard's own wording ("may be
reduced," not "waived," contrasted deliberately against the clearance
clause's "not specified") leaves no stated floor even if the test passed
(`hv-hv-creepage-determination.md:352-421`). This document does not revisit
that finding — it stands as read.

---

## 3. Does the board meet 10.0mm? No — measured, two real violations

`docs/evidence/2026-08-12-hv-hv-creepage-enforcement.md` (PR #1084, merged
to `main`) is the operative measurement: it landed the missing DRU rule
(`(rule "HighVoltageTank functional creepage") (constraint creepage (min
6.3mm))`, currently set to the PD2 figure per
`scripts/generate_kicad_dru.py:210`) and ran kicad-cli 10.0.5 against the
real committed board. Deterministic across 10 final samples
(`hv-hv-creepage-enforcement.md:252-264`):

| Pair | Actual | Required (PD2, enforced) | Required (PD3, governs) | Shortfall vs PD3 |
|---|---:|---:|---:|---:|
| `C25` pad 2 ↔ track on `discharge.k_dis1-nc` | **2.2656mm** | 6.3mm | 10.0mm | **4.4×** |
| `R30` pad 1 ↔ pad 2 (own footprint, tank↔`tank-out`) | **5.0000mm** | 6.3mm | 10.0mm | **2.0×** |

At the currently-*enforced* PD2 figure (6.3mm, which per §1 is not the
figure that legitimately applies), the rule already fails with these same
two violations — the repo's own DRC is red at the bar it claims to be
checking. At the honest PD3 figure it fails worse (§5.2 of the enforcement
doc measures 4 violations at 10.0mm, up from 2 at 6.3mm, sweeping the same
rule).

**One more open item, not fully closed by this document:** the enforcement
rule is scoped to exactly one net, `tank.c_tank1-p2`, because it is the only
`HighVoltage` net measured above 500 Vrms
(`hv-hv-creepage-enforcement.md:43-66`). The other 13 `HighVoltage` nets sit
at ≤400 V (Table 18 row iv or lower, 3.2mm PD2 / 5.0mm PD3) and have **no
HV↔HV creepage rule at all** — same structural gap the tank node had before
PR #1084. Whether any of those pairs are also short is **not measured**
anywhere in this repository. Given the `HighVoltage` netclass clearance is
2.0mm and 2.0mm < 3.2mm, a violation there is plausible but unconfirmed. This
is a real scope gap, reported rather than assumed closed.

---

## 4. Why coating does not close either violation (full argument)

Covered in the Verdict (item 4) with citations; the one addition worth
stating plainly here: **this is the same structural finding the coating
document already reached for the board's eight declared HV↔SELV isolators —
"100.0% of the shortest path under the [component] body" on every one of
them (`conformal-coating-pd1.md:54-67`) — applied to a different geometry
(a wire-termination pad rather than a seated package) that fails the
*identical* clause-4.3 coverage test for a different physical reason** (the
pad itself must stay bare, not that a package body sits over it). Coating
keeps failing the tank node's worst violation whether the obstruction is a
relay base or a wire lug, because clause 4.3's coverage requirement is
about the conductive parts, not about what happens to be sitting over them.

The C25 path is the one genuinely open question in this document: it is
plausibly coatable, would clear PD1's 1.8mm bar if fully qualified and
covered, and is worth a follow-up coverage measurement in the style of
`conformal-coating-pd1.md` §4 (body-box proxy against `F.Fab`/`F.SilkS`
geometry) scoped to this one pair specifically. But even a "yes" on that
measurement (a) leaves R30's 5.0mm violation untouched, (b) requires a
declared max PCB working-surface temperature that does not exist today
(`conformal-coating-pd1.md:456-464`), and (c) requires a real qualification
program (`conformal-coating-pd1.md:233-253`, six-plus weeks of oven time)
for a board with no coating anywhere in its BOM or assembly process
(`docs/hardware/BOM.md`, `docs/ASSEMBLY_GUIDE.md`, both grepped, zero hits).
It is not the cheap path even in the best case.

---

## 5. The airflow/compartment tension, precisely

**What is not true:** that `docs/CHASSIS_AIRFLOW_DESIGN.md` and the
sealed-compartment requirement contradict each other on paper. §3.3 of the
airflow doc states the requirement explicitly: *"The production enclosure
must keep the mains/SELV PCB insulation outside the forced-air path...
[t]his separation is a release requirement for the selected PD2 electrical
rules. If production hardware does not preserve this separation, the board
reverts to the PD3... requirement."* `docs/ENVIRONMENTAL_SPEC.md` §3.1 and
`docs/ASSEMBLY_GUIDE.md` Phase 4.2 say the same thing. All three documents
already anticipate exactly the failure mode being asked about, in writing.

**What is true, and is the actual finding:**

1. **No document commits the geometry that would satisfy the requirement.**
   Confirmed independently by `docs/evidence/2026-08-01-pd2-enclosure-legitimacy.md`
   §1.2: no CAD/STEP file anywhere in the repo, no cover/gasket/partition
   BOM line, no `MAINS_SELV_ISOLATION_BARRIER` keepout on the board.
2. **The coil bracket's own design works against it by construction.**
   `docs/COIL_BRACKET_DESIGN.md` §4 specifies an open-frame bracket whose
   "large triangular cutouts... allow air from the bottom intake to flow
   directly through the Litz wire strands," explicitly "act[ing] as a
   baffle to direct air toward the IGBT heatsink after cooling the coil" —
   i.e., by design, unfiltered kitchen air is routed through the same
   general volume the PCB occupies, on its way from the bottom vents to the
   heatsink. A compartment is not geometrically impossible in this
   arrangement (a separately walled sub-enclosure around just the PCB,
   inside the shared cavity, remains physically conceivable), but nothing
   in the repo designs that sub-enclosure, and the coil bracket's own stated
   cooling strategy is not written with one in mind.
3. **Sealing the PCB compartment is independently shown to be thermally
   marginal, for reasons that trace directly to removing this same
   airflow.** `docs/evidence/2026-07-30-pcb-compartment-thermal-bound.md`
   §4 (viability verdict): *"At the repo's own 'worst case' 55–70°C ambient
   band... LMR51430 and... the UCC21550 gate driver have zero to slightly
   negative margin under central assumptions."* Both parts already run near
   their thermal limits **with** airflow (per
   `docs/hardware/LMR51430_THERMAL_ANALYSIS.md` and
   `docs/hardware/SYSTEM_THERMAL_BUDGET.md` §3.4, cited in the thermal-bound
   doc §3.1–3.2); removing the air they currently receive and adding the
   compartment's own self-heating on top consumes what little margin they
   have.

**So: not a logical contradiction, but an un-costed dependency.** The PD2
decision record (`docs/evidence/2026-08-11-pd2-decision-record.md`) commits
the owner to building the compartment without naming the thermal
mitigation it would require, and the airflow/coil-bracket documents were
written without reference to the compartment they are supposed to be
compatible with. Building the compartment as currently designed elsewhere in
this repo would plausibly reopen a thermal problem to close a pollution-
degree one.

---

## 6. Ranked recommendation

### (a) — Fix the geometry. Recommended.

**Cost: low. Risk: low. Half of it is already solver-proven on `main`.**

Two independent, small, board-local fixes:

1. **C25 ↔ `discharge.k_dis1-nc` (2.2656mm → needs 10.0mm).** A placement
   constraint for exactly this problem already exists, is already wired into
   the production placer entry point, and has already been demonstrated to
   solve: `packages/temper-placer/src/temper_placer/placer/cp_sat/tank_creepage.py`
   (PR #1089, merged to `main`) encodes a `separated` constraint at
   10.0mm (the PD3 figure — `DEFAULT_TANK_CREEPAGE_MM =
   HV_TANK_CREEPAGE_PD3_MM`, `tank_creepage.py`, confirmed in
   `docs/evidence/2026-08-12-tank-creepage-placement.md:36`) between every
   tank-node component and every other `HighVoltage`-classified component.
   **Already measured: solves `optimal` in 1.29s with the 168-pair
   constraint active, all 8 committed isolators unrelaxed, 0 post-solve
   violations** (`tank-creepage-placement.md:126-133`). What remains is
   running a production placement + re-route cycle with this constraint
   enabled and confirming the DRC rule from §3 above goes clean — not new
   engineering, an execution step on work already landed.
2. **R30's own pads (5.0mm → needs 10.0mm) — a footprint change, not a
   placement problem.** `tank_creepage.py` says so itself: *"What this
   cannot fix even in principle: R30's own two pads... [E]very one of a
   component's own pads moves as one rigid unit under placement; no
   `SeparatedConstraint` can separate a two-pin part from itself"*
   (`tank-creepage-placement.md:38`). Confirmed directly against the
   footprint file, `pcb/libs/lib.pretty/LitzPad_15A.kicad_mod`: pad diameter
   8.0mm, pad pitch 13.0mm → edge-to-edge gap exactly 5.0mm, matching the
   DRC measurement. The footprint's own embedded description already
   records that this 13.0mm pitch was sized to a **now-superseded** figure
   (5.0mm PD2 *basic* insulation at an assumed 400V, from before the Aug-12
   Table 18/functional-insulation/570.5Vrms correction) and flags itself as
   "NOT FULLY RESOLVED... must be re-derived at the higher voltage." The fix
   is arithmetic on a single library file: widen the pitch to
   `8.0mm pad + 10.0mm creepage = 18.0mm` (PD3) or `8.0mm + 6.3mm = 14.3mm`
   (if the owner instead formally commits to closing PD2 legitimately, §6b).
   This is a footprint dimension change plus a re-placement/re-route pass —
   not a material, process, or test-program change.

**This is the cheapest option on the table**: no new BOM line, no
qualification program, no mechanical/thermal redesign, no certification-lab
test. It also does not require resolving the PD2-vs-PD3 policy question to
start — 10.0mm clears both bars, so this fix is correct regardless of how
§6b/c/d below get decided.

### (b) — Formally retarget the enforced constant to PD3 (10.0mm), stop
enforcing the unearned PD2 target. Recommended alongside (a), as documentation/gate hygiene.

Cost: near-zero (one line, `scripts/generate_kicad_dru.py:210`,
`_TANK_POLLUTION_DEGREE = "PD3"`, plus whatever else the drift gate
requires to move in lockstep per
`docs/evidence/2026-08-01-pd2-enclosure-legitimacy.md` §3.2's "any future
retarget must move every point in the table together" warning). Risk: this
raises the *stated* requirement everywhere the tank node's netclass is
checked, which is honest but makes (a)'s target 10.0mm instead of 6.3mm
regardless — already priced into (a) above. This does not resolve the
board; it stops the repo from claiming a bar it has not earned while the
compartment does not exist.

### (c) — Build the sealed compartment (keeps the PD2/6.3mm target
legitimate). Not recommended as the near-term path.

Cost: real mechanical engineering (cover, gasket, partition, assembly
drawing, inspection criteria — none exist), **plus a thermal mitigation
program** (§5: chassis-metal conduction paths for LMR51430/UCC21550,
verified copper-pour layout, possibly component relocation or a
higher-emissivity finish) that is not currently designed and whose omission
was the actual gap this task surfaced. Even fully executed, it does not
change §3's finding that R30 needs 6.3mm minimum (still more than the
5.0mm provided) — (a)'s footprint fix is still required. Highest cost,
highest schedule risk, and does not remove the need for (a).

### (d) — Coating. Not recommended as a primary path; a legitimate
secondary supplement elsewhere on the board.

Per §4: cannot reach R30's violation under any circumstances (clause 4.3,
bare wire-attachment pads); plausibly reaches C25's, unverified;
6+ week qualification program; no coating in the BOM or process today; no
declared max PCB working-surface temperature (a qualification prerequisite);
rework voids the claim (`conformal-coating-pd1.md:568-585`). Worth pursuing
later, in parallel, for the 116-of-222 board-wide open-surface HV↔SELV
pairs the coating document already identifies as a genuine target
(`conformal-coating-pd1.md:408-412`) — not as the fix for either of the two
violations this document is about.

### (e) — Clause 19 short-circuit test route (29.2.4's exemption). Not
recommended as the near-term path.

Available per §2, but requires characterizing F1's I²t behavior (currently
absent, `elec/src/modules.ato:665-673`), drawing F1's real footprint
(currently a stub, `docs/hardware/BOM.md:77`), running an actual
fault-injection test program, and even a pass leaves "may be reduced" with
no stated floor (`hv-hv-creepage-determination.md:400-421`) — a
certification body's judgment call, not a number this repo can commit to in
advance. Slower and less certain than (a) for the same two violations.

---

## 7. What this document does not do

- **It changes no netclass value, no DRU constant, no footprint file, no
  board file.** `git status --porcelain` shows only this document.
  `pcb/**` was never opened for writing.
- **It does not run the (a) placement + re-route cycle.** PR #1089 already
  proves it solves; executing it against the production board and
  re-measuring DRC is the next PR, not this one.
- **It does not resolve the scope gap in §3** (the 13 other `HighVoltage`
  nets with no HV↔HV creepage rule at all) — flagged, not measured.
- **It does not close IEC 60664-4** (high-frequency insulation coordination
  above 30kHz; this tank runs at 44–50kHz). Zero coverage anywhere in this
  repository, carried forward unchanged from
  `docs/evidence/2026-08-12-hv-clearance-adequacy.md` §3.3. Could only raise
  the requirement, never lower it.
- **It does not settle OVC II vs OVC III** (`hv-clearance-adequacy.md`
  §6.2), which affects the *clearance* determination, not the creepage
  figure this document is about. **[Resolved after this document was
  written: OVC II governs — IEC 60335-1 cl. 29.1, unconditional
  ("Appliances are in overvoltage category II"); `HIGH_VOLTAGE_CLEARANCE_SPEC.md`
  §3.2 corrected 2026-08-14. See that document's revision-history v1.4.]**

---

## Files

- This document: `docs/evidence/2026-08-12-pollution-degree-resolution.md`
- Primary chain: `docs/evidence/2026-08-12-hv-hv-creepage-determination.md`,
  `docs/evidence/2026-08-12-hv-clearance-adequacy.md`,
  `docs/evidence/2026-08-12-hv-hv-creepage-enforcement.md`,
  `docs/evidence/2026-08-12-tank-creepage-placement.md`,
  `docs/evidence/2026-08-11-pd2-decision-record.md`,
  `docs/evidence/2026-08-01-pd2-enclosure-legitimacy.md`,
  `docs/evidence/2026-07-30-pcb-compartment-thermal-bound.md`,
  `docs/evidence/2026-07-28-conformal-coating-pd1.md`
- Repo state read directly: `docs/CHASSIS_AIRFLOW_DESIGN.md`,
  `docs/COIL_BRACKET_DESIGN.md`, `docs/ENVIRONMENTAL_SPEC.md`,
  `docs/ASSEMBLY_GUIDE.md`, `docs/hardware/BOM.md`,
  `pcb/libs/lib.pretty/LitzPad_15A.kicad_mod`,
  `scripts/generate_kicad_dru.py`,
  `packages/temper-placer/src/temper_placer/placer/cp_sat/tank_creepage.py`
- Not modified by this document: `pcb/**`, `scripts/generate_kicad_dru.py`,
  any netclass, DRU rule, footprint, or `power_pcb_dataset/drc_ceiling.json`
  entry.
