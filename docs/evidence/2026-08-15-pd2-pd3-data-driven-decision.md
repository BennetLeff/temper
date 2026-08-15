<!-- provenance: commit=8f21d27257a017209cb8969500eb64ba71d1e53b dirty=false (own worktree
     /tmp/opencode/agent-pd2-pd3, branch investigate/pd2-pd3-data-driven-decision, based on
     origin/main at HEAD; git status --porcelain clean apart from this document). pcb/temper.kicad_pcb
     sha256=6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64 -- byte-identical to
     power_pcb_dataset/drc_ceiling.json's own recorded provenance input hash, so every ceiling/count
     cited from that file applies to the exact board measured here. pcb/** was never written: the only
     pcb/ file touched was pcb/temper.kicad_dru, which is gitignored and regenerated from the SSOT by
     scripts/generate_kicad_dru.py (verified git check-ignore before and after; git status --porcelain
     clean). kicad-cli 10.0.5 (/home/bennet/.local/bin/kicad-cli, version 10.0.5), measured live,
     MaximumThreads=1 pinned via a scratch KICAD_CONFIG_HOME. DRC measurements: scripts/
     measure_uncapped_drc.py dru-category creepage|clearance against a scratch copy of the board +
     regenerated .kicad_dru (PD2 = committed rules; PD3 = scratch generator copy with
     HV_CREEPAGE_ENFORCED_MM -> HV_CREEPAGE_PD3_MM, one-line sed, OUTPUT_PATH redirected to scratch --
     never installed). Component attribution: custom script reusing measure_uncapped_drc.py's
     isolation-DRU and net-name-split machinery, capturing per-violation JSON item descriptions and
     counting unique violations per refdes pair; totals reproduce the uncapped tool's to within 1
     (377 vs 376 -- one non-refdes-carrying violation). The PD2 baseline (creepage 199-200) reproduces
     the committed ceiling record's observed band [198,199,200] (260 samples), confirming harness
     agreement. All three gates run this session: check_pd2_compartment_evidence.py exit 3 (VIOLATION),
     check_isolation_keepout.py exit 3 (VIOLATION). -->

# PD2 vs PD3 decision: enforce PD3 (12.6mm reinforced / 10.0mm tank functional). The PD2 bar is unearned credit; the current board does not meet EITHER bar, and PD2's only legitimate route (a sealed compartment) is unbuilt and thermally counterproductive.

**Decision, up front: the enforced creepage bar must move from PD2/8.0mm to PD3/12.6mm
(and the tank functional rule from 6.3mm to 10.0mm).** This is a correction of the
*measurement*, not of the board: the tree currently enforces 8.0mm while the standard's
own condition requires 12.6mm for the as-built construction, and every figure measured
against 8.0mm therefore carries an unearned credit. Enforcing PD3 makes the gate
honestly red (377 creepage violations measured this session, +178 over PD2) instead of
quietly green at a bar the physical product does not earn -- the exact failure mode
`docs/evidence/2026-08-11-pd2-decision-record.md` and the handoff's §11 call the
deepest finding in this project.

This document makes the decision the handoff's §7C asked for, with data measured on
the **current** committed board and **current** rules (origin/main @ 8f21d2725, board
hash 6928b7c8), not on the resync-lineage board the earlier scoping numbers came from.

---

## 1. The data -- measured this session, current board, current rules

### 1.1 Total creepage: PD2 vs PD3

| Bar | Creepage (uncapped, true count) | vs ceiling |
|---|---:|---|
| **PD2 (8.0mm, committed rules -- what is enforced today)** | **199** (raw kicad-cli: 200) | ceiling 202 -- passes, at 2-3 headroom |
| **PD3 (12.6mm at all 5 reinforced sites, tank rule unchanged at 6.3mm)** | **377** | would exceed by 175 |
| **Full PD3 (12.6mm reinforced + 10.0mm tank functional)** | **379** | would exceed by 177 |

Delta PD2→PD3 (full PD3): **+180 creepage violations (+91%)**. The +178 at the
reinforced sites alone is +89%.

The PD2 baseline (199) reproduces the committed ceiling record's own observed band
[198, 199, 200] across 260 samples, which is the check that this harness agrees with
the one the ceiling was measured with.

**These are all LOWER BOUNDS.** The board is mostly unrouted: 88 of 139 multi-pad nets
carry zero copper today, including 19 unrouted HV/mains multi-pad nets (+170V_BUS,
DC_BUS_RTN, SW_NODE, PWR_RTN, tank.c_tank1-p2, w1_1/w1_2, ac_l/ac_n, all six
discharge.k_dis* nets, power_in.ntc-no, +15V_LS, ...). Routing those nets will **add**
violations at both bars, not remove them. The gap between the bars will widen, not
shrink, as the board is routed.

### 1.2 Component breakdown at PD3 (376 violations carrying refdes)

| Group | Violations | Share | Members (count each) |
|---|---:|---:|---|
| **Declared isolators** (C6, K1, K2, K3, PS1, T1, T2, U7) | **77** | 20.5% | U7=29, K2=15, K3=10, T1=10, PS1=6, C6=6, K1=1 |
| **Non-isolator** HV↔LV / HV↔signal | **267** | 71.0% | R5=24, U27=22, RT1=20, C1=16, U3=14, C27=10, R11=10, C4=9, U24=9, C25=9, U2=8, R20=8, ... |
| No refdes (track/via ↔ track/via) | 32 | 8.5% | — |

**At PD2 (28 isolator-touching of 199, 14.1%)** the isolator share is even smaller.

Three consequences, stated plainly because they contradict the handoff's framing:

1. **The isolators are NOT the dominant PD3 burden.** The handoff's "T1/T2/U6 account
   for >half at both figures" does not reproduce on the current board. Isolators are
   20.5% of PD3 violations. The dominant burden is ordinary HV↔LV / HV↔signal
   spacing between non-isolator parts (R5's DC-bus pad against the ESP32 module U27's
   LV pads, RT1 the inrush NTC against LV logic, C1 the mains filter cap, U3, ...).
2. **K1 is NOT "much of the net-new exposure."** K1 carries **1** violation at PD3 on
   this board. Its contact pads are Faston tabs on the `F.Fab` layer only -- zero real
   PCB copper -- so kicad-cli DRC structurally cannot measure the coil↔contact creepage
   the pad-geometry kernel reports at 8.000mm. The PR #1156 K1 swap (RT33K012) is still
   worth landing (it is the only declared isolator whose *intrinsic* geometry fails
   12.6mm and whose replacement clears it by +5.2mm), but it does **not** retire a large
   DRC-visible population, because that population is not DRC-visible on this board.
3. **T2 does not exist on main's board** (the OCP-02 CT was never placed), and on main
   the UCC21550 gate driver is **U7** (U6 is a TO-247 IGBT). The handoff's "T1/T2/U6"
   used the resync-lineage naming. The driver (U7, 29 violations at PD3) is the largest
   single isolator contributor.

### 1.3 Why these numbers differ from the handoff's scoping figures

The handoff §7C cites 167–168 (PD2) / 320–321 (PD3), +152, with T1/T2/U6 >half. Those
numbers were measured on the **resync-lineage board** (b7d865b7) under **older rules**
— before #1109 (R30 pitch fix), #1129 (HighVoltageSignal carve-out, which added a new
rule carrying 54 PD2 / 104 PD3 violations), and #1110/#1113 (clearance enforcement
restored). The current committed board + current rules measures **199 → 377**, i.e. the
situation is **worse** at both figures, and the component mix is different. The decision
below is made on the current numbers, which are the ones CI and the ceiling gate will
see.

### 1.4 Adjacent finding: the committed DRC ceiling is already stale

The committed `power_pcb_dataset/drc_ceiling.json` (last touched by #1108, provenance
`measured_at_commit` 900c79dd9, sample_count 260) records `clearance` 402 and
`error_ceiling` 1298 against DRU hash bad860a0d. The current generator (hash a9bce81f,
regenerated this session) measures **true clearance 1663** (raw kicad-cli saturates at
499) — a 4× breach of the committed clearance ceiling **at the PD2 bar, with current
rules**. Cause: #1129's HighVoltageSignal re-scope added a new "HighVoltageSignal to LV"
rule whose band alone carries 943 violations. This is separate from the PD2/PD3
question but it means "the board passes at PD2 today" is only true against a ceiling
record that predates the rules currently in force. `ci_check_drc.py` is only invoked by
`regression.yml`, which is red and excluded from required checks — consistent with this
stale state having gone unflagged.

---

## 2. The standards analysis

### 2.1 PD3 governs the as-built board

The chain is fully established on `main` and reproduced this session:

- **IEC 60335-2-6 cl. 29.2 Addition** (the appliance's own particular standard): PD3 is
  the default microenvironment for cooking appliances; PD2 is earned only if the
  insulation "is enclosed or located so that it is unlikely to be exposed to pollution
  during normal use" (`docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` §3.2.1, quoted in
  `docs/evidence/2026-08-01-pd2-enclosure-legitimacy.md:183-192`).
- **The condition is unmet, verified against real repo state this session**:
  (a) `docs/specs/pd2_compartment_evidence.yaml` does not exist; (b)
  `scripts/check_pd2_compartment_evidence.py` exits **3** (re-run, same output as the
  2026-08-11 record); (c) the board outline is a plain rectangle with zero
  vent/compartment/keepout geometry; (d) `scripts/check_isolation_keepout.py` also
  exits 3 — `MAINS_SELV_ISOLATION_BARRIER` does not exist on the board.
- **The board is forced-air vented with no cover/gasket/partition.** The coil bracket
  routes bottom-intake air through the PCB cavity by design
  (`docs/COIL_BRACKET_DESIGN.md` §4; `docs/CHASSIS_AIRFLOW_DESIGN.md` §3.3).
- **OVC II governs** (IEC 60335-1 cl. 29.1: "Appliances are in overvoltage category
  II"), not the OVC III the earlier spec claimed — per the handoff §9 correction.

**Therefore the as-built board is PD3.** Required figures: **12.6mm reinforced**
(IEC 60335-1 Table 17 row iv, >250–400 V, material group IIIa/IIIb — the 4 reinforced
HV↔LV sites) and **10.0mm tank functional** (Table 18 row vi, >500–800 V — the
resonant-tank node, `docs/evidence/2026-08-12-hv-hv-creepage-determination.md`). The
current enforcement (8.0mm + 6.3mm) is the *selected target*, not an earned
classification.

### 2.2 Is PD2 achievable with a design change?

Only by building the sealed compartment. That route is **unbuilt and thermally
counterproductive**:

- No cover, gasket, partition, or inspection geometry is committed anywhere; the
  `pd2_compartment_evidence.yaml` schema enumerates what must exist (part references,
  dimensions, a board-cross-referenced keepout zone, an airflow-routing claim, an
  inspection bound) and none of it does.
- Sealing is independently shown **thermally marginal**: at the repo's own 55–70°C
  worst-case ambient band, the LMR51430 buck and the UCC21550 driver land at zero to
  slightly negative margin to absolute-maximum junction temperature *because sealing
  removes the airflow their budgets count on* (`docs/evidence/2026-07-30-pcb-
  compartment-thermal-bound.md` §4). Building the compartment as currently designed
  would plausibly reopen a thermal failure to close a pollution-degree one.
- Even fully executed, the compartment does **not** resolve the violations: the current
  board has 199 creepage violations at the PD2 bar *itself*. PD2 is not "the board
  passes"; it is "the gate reports a smaller number against a bar the product does not
  earn."

### 2.3 Is PD3 the safe default?

PD3 is not merely the safe default — it is what the standard requires for this
construction. The question the owner asked is not "which bar can we defend to a lab"
but "which bar is the truth about this board". The answer is 12.6/10.0mm, and the
repo's own operating rules are decisive here: **never make a check pass by weakening
it**; **a labelled red beats a green that means nothing**. Enforcing 8.0mm while PD3
governs is precisely the check-that-passes-while-meaning-nothing pattern.

---

## 3. The decision

**Enforce PD3: move `HV_CREEPAGE_ENFORCED_MM` to `HV_CREEPAGE_PD3_MM` (12.6mm) and
`_TANK_POLLUTION_DEGREE` to `"PD3"` (10.0mm tank functional) in
`scripts/generate_kicad_dru.py`.**

Justification, in order of weight:

1. **Correctness.** PD3 is what IEC 60335-1/60335-2-6 require of the as-built,
   forced-air-vented, compartment-less board. The current enforcement bar is an unearned
   credit that every PD2-measured figure in this repo has been carrying since the
   decision record's own "interim position" was written. Enforcing the earned bar turns
   a manufactured green into a labelled red.
2. **The data supports it.** PD3 costs +180 violations on the current board, but those
   are *real* violations of the *real* requirement, and 79.5% of them are non-isolator
   spacing that a re-placement/re-route pass addresses — the board is mostly unrouted
   anyway, so routing is the actual work and it must be done against the correct bar.
   The 5 structurally-failing isolators (T1, T2, U7/U6, K1, C6) have staged or
   researched fixes (K1/C6 swaps in PR #1156; T1 slot geometrically viable per the
   2026-08-13 edge-slot determination; U7 slot or discrete-digital-isolator redesign
   per 2026-07-30 part-selection research).
3. **PD2 is not the cheaper option; it is the same debt at a lower, unearned bar.**
   The board fails 8.0mm by 199 violations today. Choosing PD2 does not reduce the
   remediation; it reduces the *reporting* of it, at the cost of the compartment
   (unbuilt, thermally hostile) and of every future measurement's integrity.
4. **Gate 4 resolves cleanly under PD3.** The owner's standing decision is "make Gate 4
   blocking once this resolves". Under PD3 enforcement,
   `check_pd2_compartment_evidence.py` reports **NOT_APPLICABLE** (PD3 governs, the
   compartment prerequisite is moot) — a pass by design. Making it blocking then costs
   nothing and locks in the resolution: anyone who flips the enforcement constant back
   to PD2 without the compartment turns CI red again.

### What the decision does NOT do

- It does not change any clearance, creepage, copper-weight, or DRU threshold to make
  something pass — it changes the enforcement bar **up**, to the standard's own figure.
- It does not touch `pcb/temper.kicad_pcb` (hash verified before and after).
- It does not build the compartment. Under PD3 it is not needed for creepage credit;
  the airflow/thermal design remains exactly as committed.
- It does not raise the ratchet ceiling. The raise (creepage 202 → ~380, error_ceiling
  1298 → ~1474, and the stale clearance record 402 → ~1663) is a separate, R27
  `Ceiling-Approval:`-trailer decision with its own ≥120-sample measured-live record,
  and it is the owner's to grant — the ceiling change accompanies the enforcement
  change, it is not this document's act.

---

## 4. Action plan (PD3 path)

Ranked by feasibility and dependency:

1. **Flip the enforcement constants** — `HV_CREEPAGE_ENFORCED_MM = HV_CREEPAGE_PD3_MM`
   and `_TANK_POLLUTION_DEGREE = "PD3"` in `scripts/generate_kicad_dru.py`; move
   `MIN_BARRIER_WIDTH_MM` in `isolation_constants.py` to 12.6 in lockstep (the two are
   documented as "must remain aligned"); update the REQ-SAFE-01 validator's
   reinforced-creepage figure the same way. One commit, everything moving together per
   the "move every point in the table together" rule.
2. **Re-measure and ratchet** — ≥120-sample measured-live DRC campaign on the
   PD3-enforced rules; raise creepage 202 → max(observed)+spread (~380), error_ceiling
   1298 → ~1474, and correct the stale clearance record 402 → true count, each with a
   `Ceiling-Approval:` trailer and `_march` attribution naming #1129's rule as the
   clearance cause and this enforcement change as the creepage cause. This is an owner
   decision (R27), machine-checked by `scripts/check_drc_ceiling_approval.py`.
3. **Make Gate 4 blocking** — remove `continue-on-error` from the "PD2 compartment-
   evidence gate (Gate 4)" step in `.github/workflows/python-tests.yml`. Under PD3 it
   is NOT_APPLICABLE/pass, so this is risk-free and implements the owner's standing
   decision.
4. **Land PR #1156** (K1/C6 swaps). C6 (B81123C1562M000) is placement-clean; K1
   (RT33K012) is blocked on placement — the reroute of `safety.fault_or-b2` /
   `rtd_pan.high_window-out`, or a placement pass, is the open item, now unblocked by
   the enforcement decision (the swap is required at PD3, not optional).
5. **Resolve the isolator core at 12.6mm** — T1 slot (geometrically viable per
   `2026-08-13-hv-creepage-edge-reaching-slot-determination.md`, 12.83mm worst-case;
   certification-lab question on the closed end remains), U7/U6 slot or
   ISO7741FQDWWRQ1 discrete-isolator redesign (the 2026-07-30 part-selection research
   has the >14.5mm verified path), T2 contingent on its placement, and the
   certification-lab package (`docs/evidence/2026-08-14-certification-lab-package-
   pd3-and-60664-4.md`) sent for the island-slot creepage credit and IEC 60664-4
   applicability questions.
6. **Re-place/re-route against 12.6/10.0mm** — the non-isolator population (267
   violations) is spacing debt across ordinary HV↔LV pairs; the isolation-barrier and
   tank-creepage constraints are already solver-proven (`tank_creepage.py` at 10.0mm
   solves optimal with 0 violations, PR #1089). This is the real routing work, and it
   must now target the correct bar.
7. **Leave the clearance staleness as a named follow-up** — the 1663-vs-402 clearance
   record is a separate defect (stale ceiling, not a board regression) and belongs to
   step 2's re-measurement; it is flagged here so it is not silently absorbed.

---

## 5. Gate 4 status

**Recommendation: make Gate 4 blocking now, as part of the enforcement flip.** The
handoff's owner decision was "make Gate 4 blocking once this resolves, not before".
This document resolves the question: PD3 governs, the compartment is not needed, and
the gate's `not_applicable` verdict is a pass. Removing `continue-on-error` therefore
cannot break any PR while PD3 is enforced, and it locks the resolution in — the gate's
entire purpose was to prevent the tree from claiming PD2 without the compartment, and
under PD3 the tree no longer claims PD2.

---

## 6. What this document does not claim

- It does not claim the board is PD3-compliant — it is not; it has 377–379 violations
  at the PD3 bar, and both figures are lower bounds until the board is routed.
- It does not claim PD2 is impossible forever — only that it is unearned today and its
  only route (a sealed compartment) is unbuilt and thermally counterproductive, so it
  is not the near-term path.
- It does not settle IEC 60664-4 (>30 kHz), the clause-29.2.4/19 short-circuit-test
  question, or the OVC ambiguity — those carry forward unchanged from the cited
  determinations and could only raise, never lower, the requirement.
- It does not invent any standards value. Every figure above (8.0/12.6 reinforced,
  6.3/10.0 tank functional, Table 17/18 rows) is cited to the repo's recovered primary
  text in `docs/evidence/2026-08-12-hv-hv-creepage-determination.md` and the
  pollution-degree resolution.

---

## Files

- This document: `docs/evidence/2026-08-15-pd2-pd3-data-driven-decision.md`
- Measured this session (scratch, not committed): PD2/PD3 uncapped creepage JSON,
  full-PD3 variant, per-refdes attribution JSON, clearance uncapped JSON — all under
  `/tmp/opencode/pd3-measure/`; scripts `attribute_creepage.py` (attribution harness
  reusing `measure_uncapped_drc.py`'s isolation-DRU machinery).
- Governing determinations, all on `main`: `docs/evidence/2026-08-11-pd2-decision-
  record.md`, `docs/evidence/2026-08-12-pollution-degree-resolution.md`,
  `docs/evidence/2026-08-12-hv-hv-creepage-determination.md`,
  `docs/evidence/2026-08-12-hv-hv-creepage-enforcement.md`,
  `docs/evidence/2026-08-12-hv-clearance-adequacy.md`.
- Side-branch measurements read first-hand: `docs/evidence/2026-08-13-hv-creepage-pd3-
  gap-measurement-and-plan.md` (branch `analysis/hv-creepage-pd3-gap`),
  `docs/evidence/2026-08-13-hv-creepage-edge-reaching-slot-determination.md`
  (branch `analysis/edge-slot-through-cut-rescue`), `docs/evidence/2026-08-14-
  certification-lab-package-pd3-and-60664-4.md`.
- **Not modified by this document:** `pcb/**` (board hash verified), any netclass, any
  clearance/creepage/copper-weight/DRU constant, any footprint,
  `power_pcb_dataset/drc_ceiling.json`, `.github/workflows/**`.
